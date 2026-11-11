#!/usr/bin/env python3
"""Add a note that names Kaimon to a Bash call that runs a Julia probe in a fresh process.

Claude Code runs this hook on `PreToolUse` for `Bash`, beside `rtk hook claude` and the guard. A
probe in a fresh `julia` process pays the process start and the package load on each call, which a
warm Kaimon session pays once. The hook adds a note to the model's context as `additionalContext`
and lets the call run: some probes have a reason to run fresh, such as a base, a head or a scratch
environment. It holds no state between calls, so every matching call gets the note.

A simple command of the call is a probe when its program, read after the environment assignments,
is `julia` (a path whose last part is `julia` too) and it runs code: with `-e`, `-E`, `--eval`,
`-p` or `--print` (also as `--eval=<code>` and with the code attached to a short option), with a
first argument that ends in `.jl`, or, with neither, with its standard input from a pipe or a
redirection (also with the script `-`). A command whose program is another one, such as `time`,
`env` or `timeout`, is no probe. Nor is a command whose options hold a `+<version>`, `--version`
or `-v` or a module (`-m`), whose script path holds `/Harness/` or `.githooks/`, whose script's
name is `runtests.jl` or `make.jl` or ends in `-test.jl`, or whose code names `Pkg.` or a timing
(TIMING). The code of a command that reads its standard input is the whole text of the call. One
probe among the simple commands is enough for the note.

The hook reads the command only, as Claude Code sends it: it opens no script. It removes the body
of each here-document before it splits the command with the guard's `lex`, so the lines of a body
are no commands. **It never blocks.** Every payload exits 0. A payload it cannot read (no JSON, no
`tool_input`, no string `command`, a tool other than `Bash`) gives no output: the guard, which runs
beside it, refuses a `Bash` payload that it cannot read. A command with an open quote gives no
output either, since the shell does not run it.

Test it without installing:

    echo '{"tool_name":"Bash","tool_input":{"command":"julia -e 1"}}' | ./kaimon-note.py
"""

import contextlib
import json
import re
import sys
from dataclasses import dataclass, field

from guard import HarnessError
from guard.jsonio import loads
from guard.kaimon_session import live_keys, live_sentence
from guard.shell import SEPARATORS, lex

# The options of `julia` whose value is code to run.
CODE = frozenset({"-e", "-E", "-p", "--eval", "--print"})
# The other long options of `julia` that take the next word as their value.
VALUED = frozenset(
    {"--sysimage", "--home", "--load", "--threads", "--procs", "--machine-file", "--cpu-target"}
)
# The short options of `julia` that take a value, attached or in the next word.
SHORT_VALUED = frozenset("eEpJHLtCm")
# The short options of `julia` that take no value. Any other letter ends the reading of a cluster,
# as `-O3` and `-g2` end it with their attached value.
SHORT_FLAGS = frozenset("vhiq")
# The texts of code that times or benchmarks, which a fresh process measures as intended.
TIMING = ("@time", "@btime", "@benchmark", "@allocated", "@ballocated", "@elapsed", "BenchmarkTools")
# The texts of a script path, and the ends of a script's name, that mark a harness or test script.
HARNESS_PATHS = ("/Harness/", ".githooks/")
TEST_NAMES = ("runtests.jl", "make.jl")
TEST_SUFFIX = "-test.jl"
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# The start of a here-document: `<<` or `<<-`, not `<<<`, and its delimiter, quoted or bare.
HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z0-9_.-]+))")

NOTE = (
    "Note: this `julia` call starts a fresh process and loads its packages again. A warm Kaimon "
    "session runs a probe without either: `mcp__kaimon__ex` with `ses = <key>`.\n"
    "{live}Call `ping` for the session of your tree, or `start_session(project_path = <tree>)`.\n"
    "Run the call as it is when it needs a fresh process: a base, a head or a scratch environment."
)


def without_heredocs(text: str) -> str:
    """`text` without the body and the closing line of each here-document."""
    kept: list[str] = []
    pending: list[tuple[bool, str]] = []
    for line in text.split("\n"):
        if pending:
            strip, delimiter = pending[0]
            if (line.lstrip("\t") if strip else line) == delimiter:
                pending.pop(0)
            continue
        kept.append(line)
        pending = [
            (found.group(1) == "-", next(g for g in found.groups()[1:] if g is not None))
            for found in HEREDOC.finditer(line)
        ]
    return "\n".join(kept)


def commands(text: str) -> list[tuple[list[str], bool]] | None:
    """The simple commands of `text`: the words of each, without the targets of its redirections,
    and whether its standard input comes from a pipe or a redirection; None when a quote is open."""
    tokens = lex(without_heredocs(text))
    if tokens is None:
        return None
    found: list[tuple[list[str], bool]] = []
    words: list[str] = []
    fed = target = False
    for kind, token in tokens:
        if kind == "word":
            if not target:
                words.append(token)
            target = False
            continue
        bare = token.replace("(", "").replace(")", "")
        if bare and set(bare) <= SEPARATORS:
            if words:
                found.append((words, fed))
            words, fed = [], bare in ("|", "|&")
        elif "<" in bare or ">" in bare:
            target = True
            fed = fed or "<" in bare
    if words:
        found.append((words, fed))
    return found


@dataclass
class Options:
    """What the options of one `julia` command say: the code that they run, whether one of them is
    a `+<version>`, `--version` or `-v`, and whether one names a module to run (`-m`)."""

    code: list[str] = field(default_factory=list[str])
    excluded: bool = False
    module: bool = False


def long_option(word: str, args: list[str], index: int, found: Options) -> int:
    """Read the long option `word`, whose value, when it takes one and has no `=`, is `args[index]`,
    into `found`; the index of the next word."""
    name, equals, value = word.partition("=")
    found.excluded = found.excluded or name == "--version"
    found.module = found.module or name == "--module"
    if name in CODE or name in VALUED or name == "--module":
        if not equals:
            value = args[index] if index < len(args) else ""
            index += 1
        if name in CODE:
            found.code.append(value)
    return index


def short_options(word: str, args: list[str], index: int, found: Options) -> int:
    """Read the cluster of short options `word`, whose last option's value, when it takes one and
    has none attached, is `args[index]`, into `found`; the index of the next word."""
    for at, letter in enumerate(word[1:], start=1):
        if letter in SHORT_FLAGS:
            found.excluded = found.excluded or letter == "v"
            continue
        if letter in SHORT_VALUED:
            value = word[at + 1 :]
            if not value:
                value = args[index] if index < len(args) else ""
                index += 1
            if f"-{letter}" in CODE:
                found.code.append(value)
            found.module = found.module or letter == "m"
        break
    return index


def options(args: list[str]) -> tuple[Options, str | None]:
    """What the options of the arguments `args` of `julia` say, and the script that it runs, or
    None: julia reads its options up to the first word that is no option, or up to `--`, and runs
    that word as its script when no option gives code or a module."""
    found = Options()
    index = 0
    while index < len(args):
        word = args[index]
        index += 1
        if word == "--":
            break
        if word.startswith("+"):
            found.excluded = True
        elif not word.startswith("-") or word == "-":
            index -= 1
            break
        elif word.startswith("--"):
            index = long_option(word, args, index, found)
        else:
            index = short_options(word, args, index, found)
    runs = index < len(args) and not found.code and not found.module
    return found, args[index] if runs else None


def probe(words: list[str], text: str, *, fed: bool) -> bool:
    """Whether the simple command `words`, with its standard input from a pipe or a redirection
    when `fed`, in the call `text`, runs a Julia probe that a warm Kaimon session could run."""
    at = 0
    while at < len(words) and ASSIGNMENT.match(words[at]):
        at += 1
    if at == len(words) or words[at].rsplit("/", 1)[-1] != "julia":
        return False
    found, script = options(words[at + 1 :])
    code = found.code
    if found.excluded or found.module:
        return False
    # The script `-` is the standard input.
    if script is not None and script != "-":
        name = script.rsplit("/", 1)[-1]
        if (
            not script.endswith(".jl")
            or any(part in script for part in HARNESS_PATHS)
            or name in TEST_NAMES
            or name.endswith(TEST_SUFFIX)
        ):
            return False
    elif not code:
        if not fed:
            return False
        code = [text]
    return not any("Pkg." in piece or any(t in piece for t in TIMING) for piece in code)


def main() -> int:
    with contextlib.suppress(OSError, UnicodeDecodeError, HarnessError):
        payload = loads(sys.stdin.read(), where="the payload")
        tool_input = payload.get("tool_input")
        if payload.get("tool_name") != "Bash" or not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not isinstance(command, str):
            return 0
        found = commands(command)
        if not found or not any(probe(words, command, fed=fed) for words, fed in found):
            return 0
        # A gate directory that cannot be listed gives no sentence: no key, and no claim that none
        # is live.
        keys = live_keys()
        text = NOTE.format(live="" if keys is None else live_sentence(keys) + " ")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
