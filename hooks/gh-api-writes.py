#!/usr/bin/env python3
"""Ask before a `gh api` write, except a review or a comment; refuse a `glab api` DELETE.

A `PreToolUse` hook on the `Bash` matcher. It reads the tool call on stdin, finds each
top-level `gh api` and `glab api` call, and works out the HTTP method the way `gh` does:
`-X`/`--method` when given, else POST when a body flag is present, else GET.

  * **GET, HEAD, `search/…`** — no output. The search API has no write.
  * **DELETE, from `gh api` or `glab api`** — exit 2. The deny globs cover the common
    spellings and this covers the rest.
  * **`glab api`, any method but DELETE** — no output. The `glab api` globs decide.
  * **A review or a comment** — no output, so `Bash(gh api *)` in `allow` lets it run: a
    review, an inline comment or a reply on a pull request, a comment on a pull request or
    an issue, and a commit comment. `julia-pr-reviewer`, `julia-pr-shepherd` and
    `julia-release` write to these.
  * **`graphql`** — no output for a query with no `mutation`, and for a mutation whose every
    field is a review or comment operation. A query the hook cannot read — from a file, or
    through `--input` — asks.
  * **Any other write** — `permissionDecision: "ask"`, so the user sees a prompt. That
    includes an edit of an existing comment, because the token can edit other people's.

No `permissions` glob can state this. `ask` outranks `allow`, so an `ask` rule on `-f` or
`--input` also catches a review post, and no `allow` rule can carve it back out. The
decision needs the method and the endpoint together.

**It fails open.** Input it does not understand exits 0 with no output.

Test it without installing:

    echo '{"tool_input":{"command":"gh api repos/o/r/hooks -f url=x"}}' | ./gh-api-writes.py
"""

import json
import re
import shlex
import sys

PUNCTUATION = "();<>|&\n"
SEPARATORS = set(";|&\n")

# Flags of `gh api` that consume the token after them.
TAKES_VALUE = {
    "-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header",
    "--input", "-q", "--jq", "-t", "--template", "--cache", "--hostname", "-p", "--preview",
}
BODY = {"-f", "--raw-field", "-F", "--field", "--input"}

REPO = r"repos/[^/]+/[^/]+"

# The writes a review needs, as (methods, endpoint). Everything else asks.
REVIEW_WRITES = [
    ({"POST"}, re.compile(rf"^{REPO}/pulls/[^/]+/reviews$")),
    ({"POST", "PUT"}, re.compile(rf"^{REPO}/pulls/[^/]+/reviews/[^/]+(/events)?$")),
    ({"POST"}, re.compile(rf"^{REPO}/pulls/[^/]+/comments$")),
    ({"POST"}, re.compile(rf"^{REPO}/pulls/[^/]+/comments/[^/]+/replies$")),
    ({"POST"}, re.compile(rf"^{REPO}/issues/[^/]+/comments$")),
    ({"POST"}, re.compile(rf"^{REPO}/commits/[^/]+/comments$")),
]

# The GraphQL mutations a review needs. Every top-level field of a mutation must be one.
REVIEW_MUTATIONS = {
    "addPullRequestReview", "submitPullRequestReview", "updatePullRequestReview",
    "addPullRequestReviewComment", "addPullRequestReviewThread",
    "addPullRequestReviewThreadReply", "resolveReviewThread", "unresolveReviewThread",
    "addComment",
}

STRING = re.compile(r'"""(?:.|\n)*?"""|"(?:\\.|[^"\\])*"')
NAME = re.compile(r"[_A-Za-z][_0-9A-Za-z]*")

TOOLS = ("gh", "glab")

DELETE_MESSAGE = """Refused: {tool} api DELETE {endpoint}

A remote delete through `{tool} api` is refused. Give the user the command to run in their
own terminal.
"""


def parts(command):
    """Return the top-level parts of a command as token lists, or None."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    result, current = [], []
    for token in tokens:
        if set(token) <= set(PUNCTUATION):
            bare = token.replace("(", "").replace(")", "")
            if bare and set(bare) <= SEPARATORS and current:
                result.append(current)
                current = []
            continue
        current.append(token)
    if current:
        result.append(current)
    return result


def request(arguments):
    """Return (method, endpoint, fields, from_input) for the arguments after `gh api`."""
    method, endpoint, fields, from_input = None, None, [], False
    index = 0
    while index < len(arguments):
        token = arguments[index]
        flag, _, attached = token.partition("=")
        if token.startswith("-X") and len(token) > 2:
            method = token[2:]
        elif flag == "--method" and attached:
            method = attached
        elif flag in ("--raw-field", "--field") and attached:
            fields.append(attached)
        elif flag == "--input" and attached:
            from_input = True
        elif token[:2] in ("-f", "-F") and len(token) > 2:
            fields.append(token[2:])
        elif token in TAKES_VALUE:
            value = arguments[index + 1] if index + 1 < len(arguments) else ""
            if token in ("-X", "--method"):
                method = value
            elif token == "--input":
                from_input = True
            elif token in BODY:
                fields.append(value)
            index += 1
        elif not token.startswith("-") and endpoint is None:
            endpoint = token
        index += 1
    if method is None:
        method = "POST" if fields or from_input else "GET"
    endpoint = (endpoint or "").lstrip("/").split("?", 1)[0]
    return method.upper(), endpoint, fields, from_input


def mutation_fields(text):
    """Return the top-level field names of every mutation in a query, or None if it has none."""
    text = STRING.sub('""', text)
    if not re.search(r"\bmutation\b", text):
        return None
    names = set()
    for match in re.finditer(r"\bmutation\b", text):
        start = text.find("{", match.end())
        if start < 0:
            names.add("")
            continue
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
                    rest = text[name.end():].lstrip()
                    if not rest.startswith(":"):
                        names.add(name.group())
                    index = name.end()
                    continue
            index += 1
    return names


def graphql(fields, from_input):
    """Return None to pass a GraphQL call, or 'ask'."""
    queries = [field.split("=", 1)[1] for field in fields if field.startswith("query=")]
    if from_input or len(queries) != 1 or queries[0].startswith("@"):
        return "ask"
    names = mutation_fields(queries[0])
    if names is None or (names and names <= REVIEW_MUTATIONS):
        return None
    return "ask"


def decide(method, endpoint, fields=(), from_input=False, tool="gh"):
    """Return None to pass, 'deny' or 'ask'."""
    if method == "DELETE":
        return "deny"
    if tool == "glab":
        return None
    if endpoint == "graphql":
        return graphql(fields, from_input)
    if method in ("GET", "HEAD") or endpoint.startswith("search/"):
        return None
    for methods, pattern in REVIEW_WRITES:
        if method in methods and pattern.match(endpoint):
            return None
    return "ask"


def main():
    try:
        command = json.load(sys.stdin)["tool_input"]["command"]
    except Exception:
        return 0
    if not isinstance(command, str) or ("gh" not in command and "glab" not in command):
        return 0
    split = parts(command)
    if split is None:
        return 0

    for tokens in split:
        tool = tokens[0].rsplit("/", 1)[-1] if tokens else ""
        if len(tokens) < 2 or tool not in TOOLS or tokens[1] != "api":
            continue
        method, endpoint, fields, from_input = request(tokens[2:])
        verdict = decide(method, endpoint, fields, from_input, tool)
        if verdict == "deny":
            sys.stderr.write(DELETE_MESSAGE.format(tool=tool, endpoint=endpoint))
            return 2
        if verdict == "ask":
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason":
                    f"gh api {method} {endpoint} writes outside the review and comment endpoints.",
            }}))
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
