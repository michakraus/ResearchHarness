"""Ask before a `gh api` write, except a review or a comment; refuse a `gh api` or `glab api` DELETE.

The check finds each top-level `gh api` and `glab api` call and works out the HTTP method the way
`gh` does: `-X`/`--method` when given, else POST when a body flag is present, else GET.

  * **GET, HEAD, `search/…`**: pass. The search API has no write.
  * **DELETE, from `gh api` or `glab api`**: deny.
  * **`glab api`, any method but DELETE**: pass. The `glab api` globs decide.
  * **A review or a comment**: pass, so `Bash(gh api *)` in `allow` lets it run: a review, an
    inline comment or a reply on a pull request, a comment on a pull request or an issue, and a
    commit comment.
  * **`graphql`**: pass for a query with no `mutation`, and for a mutation whose every field is a
    review or comment operation. A query the check cannot read, from a file or through `--input`,
    asks.
  * **Any other write**: ask, so the user sees a prompt. That includes an edit of an existing
    comment, because the token can edit other people's.

No `permissions` glob can state this: `ask` outranks `allow`, so an `ask` rule on `-f` or `--input`
also catches a review post. The decision needs the method and the endpoint together.
"""

import re

from .contract import PASS, RANK, Call, Verdict
from .shell import SEPARATORS, Tokens, readings

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


def parts(tokens: Tokens) -> list[list[str]]:
    """The top-level parts of a command as word lists."""
    result: list[list[str]] = []
    current: list[str] = []
    for kind, token in tokens:
        if kind == "op":
            bare = token.replace("(", "").replace(")", "")
            if bare and set(bare) <= SEPARATORS and current:
                result.append(current)
                current = []
            continue
        current.append(token)
    if current:
        result.append(current)
    return result


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


def request(arguments: list[str]) -> tuple[str, str, list[str], bool]:
    """(method, endpoint, fields, from_input) for the arguments after `gh api`."""
    method: str | None = None
    endpoint: str | None = None
    fields: list[str] = []
    from_input = False
    index = 0
    while index < len(arguments):
        name, value, index = option(arguments, index)
        if name in ("-X", "--method"):
            method = value
        elif name == "--input":
            from_input = True
        elif name in BODY:
            fields.append(value)
        elif name is None and not value.startswith("-") and endpoint is None:
            endpoint = value
    if method is None:
        method = "POST" if fields or from_input else "GET"
    endpoint = (endpoint or "").lstrip("/").split("?", 1)[0]
    return method.upper(), endpoint, fields, from_input


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
    """None to pass, 'deny' or 'ask'."""
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
        method, endpoint, fields, from_input = request(words[2:])
        found = decide(method, endpoint, fields, from_input=from_input, tool=tool)
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
    best = PASS
    for tokens in readings(command) or []:
        verdict = verdict_of(tokens)
        if RANK[verdict.decision] > RANK[best.decision]:
            best = verdict
    return best
