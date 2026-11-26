"""Under `agentbox`, deny a shell `julia` run that names a GPU package, and name the Kaimon route.

Under `agentbox` the shell has no GPU, so a `julia` run of the shell that loads a GPU package or
probes a device cannot answer; it only delays the route that works, Kaimon's `ex`. The check reads
`AGENTBOX` in its own environment, as the agentbox worktree check does. The variable is no
boundary, since anyone can unset it: the check only sends a call that cannot work to the route that
works.

A simple command of the command is a `julia` part when its command word has the name `julia`, in
any case (`shell.commands`, `shell.program`). The command word is the first word after the reserved
words, the assignments `NAME=value` and the wrappers of `shell.WRAPPERS`, such as `env`, `sudo` and
`xargs`, each with its options and operands; `command` with `-v` or `-V` runs nothing. A command
inside `( … )`, `$( … )` or backticks is one of its own, the target of a redirection is no word,
and the string of `env -S` is read as a script. Once some reading of the
command has a `julia` part, the check denies the call when the command's whole text holds a GPU
word, or when the first 1 MiB of a `.jl` file that a `julia` part names holds one. A `julia` part
names each of its words after the command word that ends in `.jl`, a leading `~` expanded and a
relative path taken against the call's working directory; with no working directory it names no
file. The check reads a file through `paths.regular_prefix`, which opens it without blocking and
reads it only when it is a regular file once open, so a FIFO or a directory adds nothing, and
neither does a file that is missing or cannot be read.

Every call without `AGENTBOX` passes, every call that is no shell call, and every command with an
open quote.
"""

import os
import re
from pathlib import PurePosixPath

from .contract import PASS, Call, Verdict
from .path_list import expanded
from .paths import regular_prefix
from .shell import commands, program, readings

# The variable that `agentbox` sets in the frontend's environment.
AGENTBOX = "AGENTBOX"
# The name of a GPU package or of one of its types, as a whole word, case-sensitive: `Metalhead`
# and `metal` are none.
GPU_WORD = re.compile(
    r"(?<![A-Za-z0-9_])(?:Metal|Mtl[A-Za-z0-9_]*|CUDA|Cu[A-Z][A-Za-z0-9_]*|AMDGPU|ROC[A-Z][A-Za-z0-9_]*"
    r"|oneAPI|oneArray)(?![A-Za-z0-9_])"
)
REFUSED = """Refused: {command}

This session runs under `agentbox`, where the shell has no GPU: a shell `julia` run that loads a
GPU package or probes a device cannot answer. Run GPU code through Kaimon: start a session with
`mcp__kaimon_start_session --project-path <project> --private`, then run the code with
`mcp__kaimon_ex --ses <key> --mt --e '<code>'`. When Kaimon does not answer, report the failure and
stop: there is no shell route, neither first nor as a fallback. Where the GPU name belongs to
another command than the `julia` run, such as a `grep`, run the two commands as two calls.
"""


def julia_parts(command: str) -> list[list[str]]:
    """The words after the command word of each `julia` part of each reading of `command`; none
    when a quote is open."""
    return [
        words[1:]
        for tokens in readings(command, nested=True) or []
        for words in commands(tokens)
        if program(words[0]) == "julia"
    ]


def script_path(word: str, cwd: str | None) -> str | None:
    """The path of the script file `word`: a leading `~` expanded, a relative path taken against
    `cwd`; None for a relative path with no `cwd`."""
    path = expanded(word)
    if path.startswith("/"):
        return path
    return None if cwd is None else str(PurePosixPath(cwd, path))


def check(call: Call) -> Verdict:
    """Under `agentbox`, deny a shell `julia` run whose command or script names a GPU package;
    pass every other call."""
    if call.action != "shell" or AGENTBOX not in os.environ:
        return PASS
    runs = julia_parts(call.command)
    if not runs:
        return PASS
    refused = Verdict("deny", REFUSED.format(command=call.command))
    if GPU_WORD.search(call.command):
        return refused
    scripts = dict.fromkeys(
        path
        for words in runs
        for word in words
        if word.endswith(".jl") and (path := script_path(word, call.cwd)) is not None
    )
    return refused if any(GPU_WORD.search(regular_prefix(path)) for path in scripts) else PASS
