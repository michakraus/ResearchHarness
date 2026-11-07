"""Ask before a `gh api` write, except a review or a comment; refuse a `gh api` or `glab api` DELETE.

The check finds each top-level `gh api` and `glab api` call and works out the HTTP method the way
`gh` does: `-X`/`--method` when given, else POST when a body flag is present, else GET.

  * **GET, HEAD, `search/…`**: pass. The search API has no write.
  * **DELETE, from `gh api` or `glab api`**: deny.
  * **`glab api`, any method but DELETE**: pass. The `glab api` globs decide.
  * **A review or a comment**: pass, so `Bash(gh api *)` in `allow` lets it run: a review, an
    inline comment or a reply on a pull request, a comment on a pull request or an issue, and a
    commit comment.
  * **A Git Data write in an own organisation**: pass for POST to `repos/<owner>/<repo>/git/blobs`,
    `…/git/trees`, `…/git/commits` and `…/git/refs`, which builds a new branch as a `git push` of
    it does: the refs endpoint only creates a ref, and a PATCH of `…/git/refs/<ref>`, which can
    force a branch, still asks. `<owner>` is one of the `org` list of the profile, compared
    without case, and the call names no `--hostname`. The profile is the file of
    `$RESEARCH_HARNESS_PROFILE`, else `~/.config/research-harness/profile.toml`, read once per
    process (`own_organisations`). A profile that is missing, cannot be read, is not UTF-8 TOML or
    holds no `org` list of strings gives no own organisation, so the write asks.
  * **`graphql`**: pass for a query with no `mutation`, and for a mutation whose every field is a
    review or comment operation; anything else asks. The query is the value of `-f query=…`, which
    `gh` sends as it is; the file of `-F query=@<path>`; or the string `query` of the JSON object
    in the file of `--input <path>`. A relative path resolves against the call's working
    directory. The query asks when the check cannot read it: a call with no working directory and
    a relative path, a command with a `cd`, `pushd` or `popd`, which moves the directory that `gh`
    reads from, a file whose name another part of the command holds, which can write the file
    before `gh` reads it, standard input (`-`), a path that names no regular file, a file that is
    not UTF-8, an `--input` that is no JSON object with a string `query`, and a call with more than
    one query.
  * **Any other write**: ask, so the user sees a prompt. That includes an edit of an existing
    comment, because the token can edit other people's.

No `permissions` glob can state this: `ask` outranks `allow`, so an `ask` rule on `-f` or `--input`
also catches a review post. The decision needs the method and the endpoint together.
"""

import functools
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from . import HarnessError
from .contract import PASS, Call, Verdict, strongest
from .jsonio import loads
from .paths import contents, regular_text
from .shell import Tokens, parts, readings

# Flags of `gh api` that consume the token after them.
TAKES_VALUE = frozenset(
    {
        "-X",
        "--method",
        "-f",
        "--raw-field",
        "-F",
        "--field",
        "-H",
        "--header",
        "--input",
        "-q",
        "--jq",
        "-t",
        "--template",
        "--cache",
        "--hostname",
        "-p",
        "--preview",
    }
)
BODY = frozenset({"-f", "--raw-field", "-F", "--field", "--input"})
# The body flags whose value `gh` reads as a file when it starts with `@`.
TYPED = frozenset({"-F", "--field"})
# The commands that move the working directory of the parts after them.
MOVES = frozenset({"cd", "pushd", "popd"})

REPO = r"repos/[^/]+/[^/]+"

# The writes a review needs, as (methods, endpoint). Everything else asks.
REVIEW_WRITES = (
    (frozenset({"POST"}), re.compile(rf"^{REPO}/pulls/[^/]+/reviews$")),
    (frozenset({"POST", "PUT"}), re.compile(rf"^{REPO}/pulls/[^/]+/reviews/[^/]+(/events)?$")),
    (frozenset({"POST"}), re.compile(rf"^{REPO}/pulls/[^/]+/comments$")),
    (frozenset({"POST"}), re.compile(rf"^{REPO}/pulls/[^/]+/comments/[^/]+/replies$")),
    (frozenset({"POST"}), re.compile(rf"^{REPO}/issues/[^/]+/comments$")),
    (frozenset({"POST"}), re.compile(rf"^{REPO}/commits/[^/]+/comments$")),
)

# The Git Data writes that build a new branch, POST only, with the owner as group 1. An owner and a
# repository are of the characters that GitHub allows in their names, so that no `%2F` or `..` in
# the path names another repository.
GIT_WRITE = re.compile(r"^repos/([A-Za-z0-9-]+)/(?!\.\.?/)[A-Za-z0-9._-]+/git/(?:blobs|trees|commits|refs)$")

# The profile without `$RESEARCH_HARNESS_PROFILE`, below the home directory.
PROFILE = Path(".config", "research-harness", "profile.toml")

# The GraphQL mutations a review needs. Every top-level field of a mutation must be one.
REVIEW_MUTATIONS = frozenset(
    {
        "addPullRequestReview",
        "submitPullRequestReview",
        "updatePullRequestReview",
        "addPullRequestReviewComment",
        "addPullRequestReviewThread",
        "addPullRequestReviewThreadReply",
        "resolveReviewThread",
        "unresolveReviewThread",
        "addComment",
    }
)

STRING = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\])*"')
# A string or a comment, whichever starts first, so a `"` inside a comment opens no string.
LEXEME = re.compile(rf"{STRING.pattern}|#[^\n]*")
NAME = re.compile(r"[_A-Za-z][_0-9A-Za-z]*")

TOOLS = ("gh", "glab")

DELETE_MESSAGE = """Refused: {tool} api DELETE {endpoint}

A remote delete through `{tool} api` is refused. Give the user the command to run in their
own terminal.
"""

GRAPHQL_MESSAGE = (
    "gh api graphql holds a mutation outside the review and comment operations, or a query that the "
    "check cannot read: give the query with -f query=…, -F query=@<file> or --input <file>.json, "
    "with a path that is absolute or relative to the working directory, no cd in the command, and "
    "a query file that no other part of the command names: write the file in a call of its own."
)


def option(arguments: list[str], index: int) -> tuple[str | None, str, int]:
    """(the option of `arguments[index]`, its value, the index after them); the option is None for
    an argument that is no option of `TAKES_VALUE`, whose value is then the argument itself."""
    argument = arguments[index]
    flag, _, attached = argument.partition("=")
    if argument.startswith("-X") and argument != "-X":
        return "-X", argument[2:], index + 1
    if flag in ("--method", "--raw-field", "--field", "--input") and attached:
        return flag, attached, index + 1
    if argument[:2] in ("-f", "-F") and argument not in ("-f", "-F"):
        return argument[:2], argument[2:], index + 1
    if argument in TAKES_VALUE:
        return argument, arguments[index + 1] if index + 1 < len(arguments) else "", index + 2
    return None, argument, index + 1


@dataclass(frozen=True, slots=True)
class Request:
    """One `gh api` call: its method, its endpoint, each body field as (flag, `key=value`), the
    path of its `--input` or None, and whether it names a `--hostname`."""

    method: str
    endpoint: str
    fields: tuple[tuple[str, str], ...]
    input: str | None
    hosted: bool


def request(arguments: list[str]) -> Request:
    """The `Request` of the arguments after `gh api`."""
    method: str | None = None
    endpoint: str | None = None
    fields: list[tuple[str, str]] = []
    source: str | None = None
    hosted = False
    index = 0
    while index < len(arguments):
        name, value, index = option(arguments, index)
        if name in ("-X", "--method"):
            method = value
        elif name == "--hostname" or (name is None and value.startswith("--hostname=")):
            hosted = True
        elif name == "--input":
            source = value
        elif name in BODY:
            fields.append((name, value))
        elif name is None and not value.startswith("-") and endpoint is None:
            endpoint = value
    if method is None:
        method = "POST" if fields or source is not None else "GET"
    endpoint = (endpoint or "").lstrip("/").split("?", 1)[0]
    return Request(method.upper(), endpoint, tuple(fields), source, hosted)


@functools.cache
def own_organisations() -> frozenset[str]:
    """The `org` list of the profile, in lower case, read once per process: the file of
    `$RESEARCH_HARNESS_PROFILE`, else PROFILE below the home directory. It fails closed: a profile
    that is missing, cannot be read, is not UTF-8 TOML or holds no `org` list of strings gives
    none."""
    location = os.environ.get("RESEARCH_HARNESS_PROFILE") or str(Path.home() / PROFILE)
    try:
        org = tomllib.loads(contents(location)).get("org")
    except OSError, UnicodeDecodeError, tomllib.TOMLDecodeError:
        return frozenset()
    if not isinstance(org, list):
        return frozenset()
    names = cast("list[object]", org)
    if not all(isinstance(name, str) for name in names):
        return frozenset()
    return frozenset(name.lower() for name in cast("list[str]", names))


def own_git_write(method: str, endpoint: str, *, hosted: bool) -> bool:
    """Whether the call is a POST of GIT_WRITE to a repository of an own organisation on GitHub."""
    found = GIT_WRITE.match(endpoint)
    return (
        method == "POST"
        and not hosted
        and found is not None
        and found.group(1).lower() in own_organisations()
    )


def mutation_fields(text: str) -> set[str] | None:
    """The top-level field names of every mutation in a query, or None if it has none."""
    text = LEXEME.sub(lambda found: "" if found.group().startswith("#") else '""', text)
    if not re.search(r"\bmutation\b", text):
        return None
    names: set[str] = set()
    for match in re.finditer(r"\bmutation\b", text):
        start = text.find("{", match.end())
        names |= {""} if start < 0 else selection_fields(text, start)
    return names


def selection_fields(text: str, start: int) -> set[str]:
    """The field names, `...` for a fragment spread, at the top of the selection set that opens at
    `start`; an alias (`a: field`) counts as its field."""
    names: set[str] = set()
    braces, parens, index = 0, 0, start
    while index < len(text):
        char = text[index]
        if char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
            if braces == 0:
                break
        elif char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        elif braces == 1 and parens == 0:
            if text.startswith("...", index):
                names.add("...")
                index += 3
                continue
            name = NAME.match(text, index)
            if name:
                if not text[name.end() :].lstrip().startswith(":"):
                    names.add(name.group())
                index = name.end()
                continue
        index += 1
    return names


def file_text(path: str, cwd: str | None, others: tuple[str, ...]) -> str | None:
    """The UTF-8 text of the regular file `path`, a relative one resolved against `cwd`; None when
    it cannot be read: `-`, a relative path with no `cwd`, no regular file, or no UTF-8 text. None
    also when a word of `others`, the other parts of the command, holds the file's name: such a
    part can write the file before `gh` reads it."""
    if path == "-" or any(PurePosixPath(path).name in word for word in others):
        return None
    found = PurePosixPath(path)
    if not found.is_absolute():
        if cwd is None:
            return None
        found = PurePosixPath(cwd, path)
    return regular_text(str(found))


def input_query(path: str, cwd: str | None, others: tuple[str, ...]) -> str | None:
    """The string `query` of the JSON object in the file `path` (`file_text`), or None."""
    text = file_text(path, cwd, others)
    if text is None:
        return None
    try:
        query = loads(text, where=path).get("query")
    except HarnessError:
        return None
    return query if isinstance(query, str) else None


def graphql(call: Request, cwd: str | None, others: tuple[str, ...]) -> str | None:
    """None to pass a GraphQL call, or 'ask'; `cwd` is None when a relative path is unreadable, and
    `others` holds the words of the command's other parts (`file_text`)."""
    queries: list[str | None] = []
    for flag, field in call.fields:
        key, _, value = field.partition("=")
        if key == "query":
            typed = flag in TYPED and value.startswith("@")
            queries.append(file_text(value[1:], cwd, others) if typed else value)
    if call.input is not None:
        queries.append(input_query(call.input, cwd, others))
    if len(queries) != 1 or queries[0] is None:
        return "ask"
    names = mutation_fields(queries[0])
    if names is None or (names and names <= REVIEW_MUTATIONS):
        return None
    return "ask"


def decide(call: Request, cwd: str | None, others: tuple[str, ...], *, tool: str) -> str | None:
    """None to pass, 'deny' or 'ask', before the own Git Data writes (`own_git_write`)."""
    if call.method == "DELETE":
        return "deny"
    if tool == "glab":
        return None
    if call.endpoint == "graphql":
        return graphql(call, cwd, others)
    if call.method in ("GET", "HEAD") or call.endpoint.startswith("search/"):
        return None
    for methods, pattern in REVIEW_WRITES:
        if call.method in methods and pattern.match(call.endpoint):
            return None
    return "ask"


def verdict_of(tokens: Tokens, cwd: str | None) -> Verdict:
    """The verdict of the first `gh api` or `glab api` part that does not pass; a relative path
    resolves against `cwd` unless a part moves the working directory."""
    found_parts = parts(tokens)
    if any(words[0] in MOVES for words in found_parts):
        cwd = None
    for index, words in enumerate(found_parts):
        tool = words[0].rsplit("/", 1)[-1]
        if tool not in TOOLS or words[1:2] != ["api"]:
            continue
        api = request(words[2:])
        others = tuple(word for at, part in enumerate(found_parts) if at != index for word in part)
        found = decide(api, cwd, others, tool=tool)
        if found == "ask" and own_git_write(api.method, api.endpoint, hosted=api.hosted):
            found = None
        if found == "deny":
            return Verdict("deny", DELETE_MESSAGE.format(tool=tool, endpoint=api.endpoint))
        if found == "ask" and api.endpoint == "graphql":
            return Verdict("ask", GRAPHQL_MESSAGE)
        if found == "ask":
            return Verdict(
                "ask", f"gh api {api.method} {api.endpoint} writes outside the review and comment endpoints."
            )
    return PASS


def check(call: Call) -> Verdict:
    """Ask before a `gh api` write; deny an API DELETE."""
    command = call.command
    if "gh" not in command and "glab" not in command:
        return PASS
    return strongest(verdict_of(tokens, call.cwd) for tokens in readings(command) or [])
