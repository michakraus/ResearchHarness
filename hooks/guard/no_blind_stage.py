"""Refuse a `git add` that stages more than the paths it names.

The check reads each segment of a shell command and denies a `git add` whose flags or pathspecs
stage a file the session did not write: `-A`, `-u` and their long forms, also inside a short-flag
cluster (`git add -nA`), and a pathspec of the whole tree (`.`, `:/`). A `permissions.deny` glob
cannot read a cluster: `Bash(git add -A*)` does not match `git add -nA`, and `Bash(git add *A*)`
would refuse `git add src/Abc.jl`.

A text whose quotes do not balance is split on the separators first, and each piece that reads is
checked.
"""

from .contract import PASS, Call, Verdict
from .shell import SEGMENT, Tokens, readings, words

# `git` global options that consume the token after them. Anything else starting with `-` before
# the subcommand is a flag that stands alone.
TAKES_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"})

# `-A` is `--all` is `--no-ignore-removal`; `-u` is `--update`.
SWEEP_LONG = frozenset({"--all", "--update", "--no-ignore-removal"})

# A pathspec that names the whole tree rather than a file.
SWEEP_PATHSPEC = frozenset({".", "./", ":/"})

MESSAGE = """Refused: {segment}

`{argument}` stages files this session did not write. This tree holds many projects and
more than one session may be running in it, so a sweep commits whatever appeared since
your last look, under your message.

Stage the paths you changed, by name:

    git add path/one path/two

Read `git status --short` first. If a path there is not yours, leave it alone and say so
in your report.
"""


def subcommand(tokens: list[str]) -> tuple[str | None, list[str]]:
    """The subcommand of a `git` invocation and its arguments."""
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in TAKES_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, tokens[index + 1 :]
    return None, []


def sweep(arguments: list[str]) -> str | None:
    """The argument that makes this `git add` stage unnamed paths, or None."""
    after_ddash = False
    for argument in arguments:
        if argument == "--":
            after_ddash = True
            continue
        if not after_ddash:
            if argument in SWEEP_LONG:
                return argument
            if argument.startswith("-") and not argument.startswith("--"):
                cluster = argument[1:]
                if "A" in cluster or "u" in cluster:
                    return argument
        if argument in SWEEP_PATHSPEC or argument.startswith(":/"):
            return argument
    return None


def segments(tokens: Tokens) -> list[list[str]]:
    """The words of each segment: every operator ends one."""
    result: list[list[str]] = []
    current: list[str] = []
    for kind, value in tokens:
        if kind == "op":
            if current:
                result.append(current)
            current = []
        else:
            current.append(value)
    if current:
        result.append(current)
    return result


def fallback_segments(command: str) -> list[list[str]]:
    """The segments of a text whose quotes do not balance: split on the separators first."""
    found: list[list[str]] = []
    for raw in SEGMENT.split(command):
        piece = words(raw.strip().lstrip("(").strip())
        if piece is not None:
            found.append(piece)
    return found


def check(call: Call) -> Verdict:
    """Deny a `git add` that sweeps."""
    command = call.command
    if "add" not in command:
        return PASS
    read = readings(command)
    for tokens_list in (
        [segments(tokens) for tokens in read] if read is not None else [fallback_segments(command)]
    ):
        for tokens in tokens_list:
            if not tokens or tokens[0] != "git":
                continue
            name, arguments = subcommand(tokens)
            if name != "add":
                continue
            found = sweep(arguments)
            if found:
                return Verdict("deny", MESSAGE.format(segment=" ".join(tokens), argument=found))
    return PASS
