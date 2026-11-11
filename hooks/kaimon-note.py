#!/usr/bin/env python3
"""Add a note that names Kaimon to a Bash call that runs a Julia probe in a fresh process.

Claude Code runs this hook on `PreToolUse` for `Bash`, beside `rtk hook claude` and the guard. A
probe in a fresh `julia` process pays the process start and the package load on each call, which a
warm Kaimon session pays once. The hook adds a note to the model's context as `additionalContext`
and lets the call run: some probes have a reason to run fresh, such as a base, a head or a scratch
environment. It holds no state between calls, so every matching call gets the note.

A simple command of the call is a probe when its program, read after the reserved words such as
`then`, `do` and `!` and after the environment assignments, is `julia` (a path whose last part is
`julia` too) and it runs code: with `-e`, `-E`, `--eval` or `--print` (also as `--eval=<code>` and
with the code attached to a short option), with a first argument that ends in `.jl`, or, with
neither, with its standard input from a pipe or a redirection (also with the script `-`), or from
one into a group `( … )` or `{ …; }` that holds it. The value of an option, such as the `no` of
`--startup-file no` or the number of `-p` or `--procs`, is no script and no code. A command whose
program is another one, such as `time`, `env` or `timeout`, is no probe. Nor is a command whose
options hold a `+<version>`, `--version` or `-v` or a module (`-m`), whose script path holds
`/Harness/` or `.githooks/`, whose script's name is `runtests.jl` or `make.jl` or ends in
`-test.jl`, or whose code names `Pkg.` or a timing (TIMING). The code of a command that reads its
standard input is the whole text of the call. One probe among the simple commands is enough for
the note.

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
CODE = frozenset({"-e", "-E", "--eval", "--print"})
# The other long options of `julia` that take the next word as their value when they have no `=`,
# as julia 1.13 reads them: `julia --startup-file no -e 1` runs `1`. `--project`, `--code-coverage`,
# `--track-allocation`, `--optimize`, `--min-optlevel`, `--debug-info`, `--trim`, `--trace-eval`
# and `--worker` take a value only after `=`.
VALUED = frozenset(
    {
        "--sysimage",
        "--home",
        "--load",
        "--threads",
        "--procs",
        "--machine-file",
        "--cpu-target",
        "--banner",
        "--startup-file",
        "--handle-signals",
        "--sysimage-native-code",
        "--compiled-modules",
        "--pkgimages",
        "--gcthreads",
        "--color",
        "--history-file",
        "--depwarn",
        "--warn-overwrite",
        "--warn-scope",
        "--inline",
        "--check-bounds",
        "--math-mode",
        "--heap-size-hint",
        "--hard-heap-limit",
        "--heap-target-increment",
        "--compile",
        "--compress-sysimage",
        "--output-incremental",
        "--timeout-for-safepoint-straggler",
        "--trace-compile",
        "--trace-dispatch",
        "--task-metrics",
        "--permalloc-pkgimg",
        "--output-o",
        "--output-ji",
        "--output-bc",
        "--output-unopt-bc",
        "--output-asm",
        "--bug-report",
        "--bind-to",
    }
)
# The short options of `julia` that take a value, attached or in the next word.
SHORT_VALUED = frozenset("eEpJHLtCmOg")
# The short options of `julia` that take no value. Any other letter ends the reading of a cluster.
SHORT_FLAGS = frozenset("vhiq")
# The reserved words that can stand before the name of a command and leave it the command name.
# `{` opens a group and `}` closes one. `time` is none of them: a `julia` after it gets no note.
RESERVED = frozenset({"!", "if", "then", "elif", "else", "while", "until", "do"})
# The parentheses of an operator, each alone, and the runs of its other characters.
PIECE = re.compile(r"[()]|[^()]+")
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


@dataclass
class Group:
    """An open group, `( … )`, `$( … )`, `<( … )` or `{ …; }`: the word that closes it, the words and
    the input of the command around it, the index of its first command, and whether its commands
    read a pipe."""

    closer: str
    words: list[str]
    fed: bool
    pipe: bool
    start: int
    piped: bool


@dataclass
class Reader:
    """The simple commands read so far, each with whether its standard input comes from a pipe or a
    redirection, and the state of the command being read: whether its input comes from a pipe or a
    redirection (`fed`), and from a pipe (`pipe`)."""

    found: list[tuple[list[str], bool]] = field(default_factory=list[tuple[list[str], bool]])
    words: list[str] = field(default_factory=list[str])
    fed: bool = False
    pipe: bool = False
    target: bool = False
    groups: list[Group] = field(default_factory=list[Group])
    # The index of the first command of the group that closed last in this command: a `<` after
    # the group feeds every command in it.
    closed: int | None = None

    def end(self) -> None:
        """End the command being read; it reads the pipe of each group that it is in."""
        if self.words:
            self.found.append((self.words, self.fed or (bool(self.groups) and self.groups[-1].piped)))
        self.words = []

    def open(self, closer: str) -> None:
        """Open a group that `closer` closes. Its commands read the pipe into the command that holds
        it, and the one into each group around it; a redirection of that command after the group
        feeds them too."""
        piped = self.pipe or (bool(self.groups) and self.groups[-1].piped)
        self.groups.append(Group(closer, self.words, self.fed, self.pipe, len(self.found), piped))
        self.words, self.fed, self.pipe, self.target, self.closed = [], False, False, False, None

    def close(self) -> None:
        """Close the innermost group, and go on with the command around it."""
        self.end()
        group = self.groups.pop()
        self.words, self.fed, self.pipe = group.words, group.fed, group.pipe
        self.target, self.closed = False, group.start

    def word(self, text: str) -> None:
        """Read the word `text`. A reserved word, `{` and `}` are such only before the first word of
        a command, and a `}` only in a group that `{` opens."""
        if self.target:
            self.target = False
        elif self.words:
            self.words.append(text)
        elif text == "{":
            self.open("}")
        elif text == "}" and self.groups and self.groups[-1].closer == "}":
            self.close()
        elif text not in RESERVED:
            self.words.append(text)

    def operator(self, piece: str) -> None:
        """Read the piece `piece` of an operator: a parenthesis, or a run of other characters. A `)`
        that closes no `(` ends a pattern of `case`, and the command after it starts."""
        if piece == "(":
            self.open(")")
        elif piece == ")" and self.groups and self.groups[-1].closer == ")":
            self.close()
        elif piece == ")":
            self.end()
        elif set(piece) <= SEPARATORS:
            self.end()
            self.fed = self.pipe = piece in ("|", "|&")
            self.closed = None
        elif "<" in piece or ">" in piece:
            self.target = True
            if "<" in piece:
                self.fed = True
                if self.closed is not None:
                    self.found[self.closed :] = [(words, True) for words, _ in self.found[self.closed :]]


def commands(text: str) -> list[tuple[list[str], bool]] | None:
    """The simple commands of `text`: the words of each, without the reserved words before it and
    the targets of its redirections, and whether its standard input comes from a pipe or a
    redirection, also one into a group that holds it; None when a quote is open."""
    tokens = lex(without_heredocs(text))
    if tokens is None:
        return None
    reader = Reader()
    for kind, token in tokens:
        if kind == "word":
            reader.word(token)
        else:
            for found in PIECE.finditer(token):
                reader.operator(found.group())
    reader.end()
    return reader.found


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
