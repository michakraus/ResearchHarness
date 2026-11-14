#!/usr/bin/env python3
"""Warn after a Bash call that runs Julia when the depot holds a stale copy of the General registry.

Claude Code runs this hook on `PostToolUse` for `Bash`. Every Julia version of a machine shares one
depot, and `registries/General.toml` names in its key `path` the file of the General registry that
Pkg reads. Pkg of Julia 1.10 to 1.12 writes `General.tar.gz`, Pkg of Julia 1.13 writes
`General.tar.zst`, and neither removes the other's file. So both can exist, and a read of the file
that `General.toml` does not name disagrees with what Pkg resolves.

The registries directory is `registries/` of the first entry of `JULIA_DEPOT_PATH`, or of
`~/.julia` when the variable is unset or its first entry is empty. The hook adds a warning to the
model's context as `additionalContext` when that directory holds more than one `General.tar.*`
file, or when the file that `path` names is not the newest of them by modification time. The
warning names each file with its modification time, the file that `General.toml` names, and the
remedy: `Pkg.Registry.update()` on the default Julia, then a delete of the copy that `General.toml`
does not name.

A simple command of the call runs Julia when its program, read after the reserved words such as
`then` and `do` and after the environment assignments, is `julia` or `juliaup`, or a path whose last
part is one of them. **It never blocks and edits nothing.** Every payload exits 0. A payload it
cannot read, a call that runs no Julia, a missing directory, a missing or unreadable `General.toml`
and a directory with one copy that `General.toml` names give no output.

Test it without installing:

    echo '{"tool_name":"Bash","tool_input":{"command":"julia -e 1"}}' | ./registry-copies.py
"""

import contextlib
import json
import os
import sys
import time
import tomllib
from pathlib import Path

from guard import HarnessError
from guard.jsonio import loads
from guard.shell import SEPARATORS, lex

PROGRAMS = frozenset({"julia", "juliaup"})
# The reserved words that can stand before the name of a command and leave it the command name.
RESERVED = frozenset({"!", "if", "then", "elif", "else", "while", "until", "do", "{"})
REMEDY = (
    "Run `Pkg.Registry.update()` on the default Julia, then delete the copy that `General.toml` "
    "does not name."
)


def runs_julia(command: str) -> bool:
    """Whether a simple command of `command` has `julia` or `juliaup` as its program."""
    tokens = lex(command)
    if tokens is None:
        return False
    start, target = True, False
    for kind, token in tokens:
        if kind == "op":
            if set(token) & SEPARATORS or "(" in token or ")" in token:
                start, target = True, False
            elif "<" in token or ">" in token:
                target = True
            continue
        if target:
            target = False
        elif start and token not in RESERVED and not ("=" in token and token.split("=", 1)[0].isidentifier()):
            if token.rsplit("/", 1)[-1] in PROGRAMS:
                return True
            start = False
    return False


def registries() -> Path:
    """The registries directory of the first depot."""
    first = os.environ.get("JULIA_DEPOT_PATH", "").split(os.pathsep, 1)[0]
    return (Path(first) if first else Path.home() / ".julia") / "registries"


def stamp(path: Path) -> str:
    """The modification time of `path` in local time."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))


def warning(directory: Path) -> str | None:
    """The warning for the registries directory `directory`, or None when it needs none."""
    copies = sorted(directory.glob("General.tar.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not copies:
        return None
    with (directory / "General.toml").open("rb") as file:
        named = tomllib.load(file).get("path")
    if not isinstance(named, str):
        return None
    if len(copies) == 1 and copies[0].name == named:
        return None
    listed = ", ".join(f"`{p.name}` (modified {stamp(p)})" for p in copies)
    if named not in (p.name for p in copies):
        state = f"`General.toml` names `{named}`, which is missing."
    elif copies[0].name == named:
        state = f"`General.toml` names `{named}`, the newest; the other copies are stale."
    else:
        state = (
            f"`General.toml` names `{named}`, which is older than `{copies[0].name}`: "
            f"Pkg reads the older copy."
        )
    return (
        f"Warning: the registries directory `{directory}` holds {listed}. "
        f"Pkg reads only the file that `path` in `General.toml` names. {state}\n{REMEDY}"
    )


def main() -> int:
    with contextlib.suppress(OSError, UnicodeDecodeError, HarnessError, tomllib.TOMLDecodeError):
        payload = loads(sys.stdin.read(), where="the payload")
        tool_input = payload.get("tool_input")
        if payload.get("tool_name") != "Bash" or not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not isinstance(command, str) or not runs_julia(command):
            return 0
        text = warning(registries())
        if text is not None:
            print(
                json.dumps(
                    {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
