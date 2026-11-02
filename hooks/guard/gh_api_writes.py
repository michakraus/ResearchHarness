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
    review or comment operation. A query the check cannot read, from a file or through `--input`,
    asks.
  * **Any other write**: ask, so the user sees a prompt. That includes an edit of an existing
    comment, because the token can edit other people's.

No `permissions` glob can state this: `ask` outranks `allow`, so an `ask` rule on `-f` or `--input`
also catches a review post. The decision needs the method and the endpoint together.
"""

import functools
import os
import re
import tomllib
from pathlib import Path
from typing import cast

from .contract import PASS, Call, Verdict, strongest
from .paths import contents
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
NAME = re.compile(r"[_A-Za-z][_0-9A-Za-z]*")

TOOLS = ("gh", "glab")

DELETE_MESSAGE = """Refused: {tool} api DELETE {endpoint}

A remote delete through `{tool} api` is refused. Give the user the command to run in their
own terminal.
"""


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


def request(arguments: list[str]) -> tuple[str, str, list[str], bool, bool]:
    """(method, endpoint, fields, from_input, hosted) for the arguments after `gh api`; `hosted`
    when they name a `--hostname`."""
    method: str | None = None
    endpoint: str | None = None
    fields: list[str] = []
    from_input = hosted = False
    index = 0
    while index < len(arguments):
        name, value, index = option(arguments, index)
        if name in ("-X", "--method"):
            method = value
        elif name == "--hostname" or (name is None and value.startswith("--hostname=")):
            hosted = True
        elif name == "--input":
            from_input = True
        elif name in BODY:
            fields.append(value)
        elif name is None and not value.startswith("-") and endpoint is None:
            endpoint = value
    if method is None:
        method = "POST" if fields or from_input else "GET"
    endpoint = (endpoint or "").lstrip("/").split("?", 1)[0]
    return method.upper(), endpoint, fields, from_input, hosted


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
    text = STRING.sub('""', text)
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


def graphql(fields: list[str], *, from_input: bool) -> str | None:
    """None to pass a GraphQL call, or 'ask'."""
    queries = [field.split("=", 1)[1] for field in fields if field.startswith("query=")]
    if from_input or len(queries) != 1 or queries[0].startswith("@"):
        return "ask"
    names = mutation_fields(queries[0])
    if names is None or (names and names <= REVIEW_MUTATIONS):
        return None
    return "ask"


def decide(method: str, endpoint: str, fields: list[str], *, from_input: bool, tool: str) -> str | None:
    """None to pass, 'deny' or 'ask', before the own Git Data writes (`own_git_write`)."""
    if method == "DELETE":
        return "deny"
    if tool == "glab":
        return None
    if endpoint == "graphql":
        return graphql(fields, from_input=from_input)
    if method in ("GET", "HEAD") or endpoint.startswith("search/"):
        return None
    for methods, pattern in REVIEW_WRITES:
        if method in methods and pattern.match(endpoint):
            return None
    return "ask"


def verdict_of(tokens: Tokens) -> Verdict:
    """The verdict of the first `gh api` or `glab api` part that does not pass."""
    for words in parts(tokens):
        tool = words[0].rsplit("/", 1)[-1] if words else ""
        if tool not in TOOLS or words[1:2] != ["api"]:
            continue
        method, endpoint, fields, from_input, hosted = request(words[2:])
        found = decide(method, endpoint, fields, from_input=from_input, tool=tool)
        if found == "ask" and own_git_write(method, endpoint, hosted=hosted):
            found = None
        if found == "deny":
            return Verdict("deny", DELETE_MESSAGE.format(tool=tool, endpoint=endpoint))
        if found == "ask":
            return Verdict(
                "ask", f"gh api {method} {endpoint} writes outside the review and comment endpoints."
            )
    return PASS


def check(call: Call) -> Verdict:
    """Ask before a `gh api` write; deny an API DELETE."""
    command = call.command
    if "gh" not in command and "glab" not in command:
        return PASS
    return strongest(verdict_of(tokens) for tokens in readings(command) or [])
