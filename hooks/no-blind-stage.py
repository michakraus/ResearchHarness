#!/usr/bin/env python3
"""Refuse a `git add` that stages more than the paths it names.

A `PreToolUse` hook on the `Bash` matcher. It reads the tool call on stdin, parses each
segment of the command, and exits 2 when a `git add` would stage a file the session did
not write. Exit 2 refuses the call and shows this script's stderr to the model.

It exists for the one case a `permissions.deny` glob cannot express: a short-flag cluster.
`Bash(git add -A*)` does not match `git add -nA`, and `Bash(git add *A*)` would refuse
`git add src/Abc.jl`. A parser reads the cluster and has no such problem.

**It fails open.** Any input it does not understand exits 0. The deny list in
`settings.json` still refuses every spelling it was written for, so a failure here loses
the flag-cluster case and nothing else. A hook that failed closed would block every Bash
call in every session the moment it met an input its author did not foresee.

Test it without installing:

    echo '{"tool_input":{"command":"git add -nA"}}' | ./no-blind-stage.py ; echo "exit $?"
"""

import json
import re
import shlex
import sys

# The permission matcher evaluates each segment of a compound command separately, and so
# does this. `harness settings` splits on the same set. The split is quote-aware, so a
# line of a quoted commit message is not a segment; `SEGMENT` is the fallback for text
# that does not parse.
SEGMENT = re.compile(r"(?:&&|\|\||;|\||\n)")
PUNCTUATION = "();<>|&\n"

# `git` global options that consume the token after them. Anything else starting with `-`
# before the subcommand is a flag that stands alone.
TAKES_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"}

# `-A` is `--all` is `--no-ignore-removal`; `-u` is `--update`.
SWEEP_LONG = {"--all", "--update", "--no-ignore-removal"}

# A pathspec that names the whole tree rather than a file.
SWEEP_PATHSPEC = {".", "./", ":/"}

MESSAGE = """Refused: {segment}

`{argument}` stages files this session did not write. This tree holds many projects and
more than one session may be running in it, so a sweep commits whatever appeared since
your last look, under your message.

Stage the paths you changed, by name:

    git add path/one path/two

Read `git status --short` first. If a path there is not yours, leave it alone and say so
in your report.
"""


def subcommand(tokens):
    """Return (subcommand, its arguments) for a `git` invocation."""
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


def sweep(arguments):
    """Return the argument that makes this `git add` stage unnamed paths, or None."""
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


def segments(command):
    """Return the command's segments as token lists, reading quotes across the whole text."""
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
            if current:
                result.append(current)
            current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def fallback_segments(command):
    """Split on the separators first, for text whose quotes do not balance."""
    for raw in SEGMENT.split(command):
        try:
            yield shlex.split(raw.strip().lstrip("(").strip())
        except ValueError:
            continue


def main():
    try:
        command = json.load(sys.stdin)["tool_input"]["command"]
    except Exception:
        return 0
    if not isinstance(command, str) or "add" not in command:
        return 0

    parsed = segments(command)
    for tokens in parsed if parsed is not None else fallback_segments(command):
        if not tokens or tokens[0] != "git":
            continue
        segment = " ".join(tokens)
        name, arguments = subcommand(tokens)
        if name != "add":
            continue
        found = sweep(arguments)
        if found:
            sys.stderr.write(MESSAGE.format(segment=segment, argument=found))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
