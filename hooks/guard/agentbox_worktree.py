"""Under `agentbox`, deny a `git worktree add`, `move` or `remove`, and name `harness worktree`.

Under `agentbox` every `git` runs inside srt, whatever `sandbox.excludedCommands` says, and srt
denies every write below a `.githooks`. A `git worktree add` there stops at the first such file. A
`git worktree remove` deletes the work tree's files up to the first such file, fails, and still
deletes the worktree's record below `.git/worktrees/`: the directory stays, and no `git worktree`
command knows it. `harness worktree add <branch> --apply` and `harness worktree remove <path>
--apply` run the worktree hook, which under `agentbox` asks its broker outside srt.

The check reads `AGENTBOX` in its own environment, as the worktree hook does. The variable is no
boundary, since anyone can unset it: the check only sends a call that would fail to the route that
works. It finds each `git` call of the command, also after an assignment, an operator or in the
script of `sh -c`, `bash -c` or `eval`, skips its global options as `git` does, and denies it where
the subcommand is `worktree` and the next word `add`, `move` or `remove`. Every other call passes,
and so does every call without `AGENTBOX`.
"""

import os
from pathlib import PurePosixPath

from .contract import PASS, Call, Verdict, strongest
from .rm_scope import TAKES_VALUE
from .shell import Tokens, joined, readings

# The variable that `agentbox` sets in the frontend's environment.
AGENTBOX = "AGENTBOX"
# The actions of `git worktree` that write below `.git/worktrees/` and in the work tree.
ACTIONS = frozenset({"add", "move", "remove"})
# The `harness worktree` command for each action.
ROUTES = {
    "add": "harness worktree add <branch> --apply",
    "remove": "harness worktree remove <path> --apply",
    "move": "harness worktree remove <path> --apply, then harness worktree add <branch> --apply",
}

REFUSED = """Refused: {command}

This session runs under `agentbox`, where every `git` runs inside srt, and srt denies writes below
`.githooks`, so `git worktree {action}` fails halfway: a remove deletes the worktree's record and
leaves most of its files. Run `{route}` instead, from the repository's main checkout: it asks the
worktree broker, which runs outside srt.
"""


def actions(words: list[str]) -> list[str]:
    """The action of each `git worktree add`, `move` or `remove` call in `words`, in order."""
    found: list[str] = []
    for index, word in enumerate(words):
        if PurePosixPath(word).name != "git":
            continue
        at = index + 1
        while at < len(words) and words[at].startswith("-"):
            at += 2 if words[at] in TAKES_VALUE else 1
        if words[at : at + 1] == ["worktree"] and at + 1 < len(words) and words[at + 1] in ACTIONS:
            found.append(words[at + 1])
    return found


def decide(tokens: Tokens, command: str) -> Verdict:
    """The denial of the first worktree write of one reading, or PASS."""
    words = [text for kind, text in tokens if kind == "word"]
    found = actions(words)
    if not found:
        return PASS
    action = found[0]
    return Verdict("deny", REFUSED.format(command=command, action=action, route=ROUTES[action]))


def check(call: Call) -> Verdict:
    """Under `agentbox`, deny `git worktree add`, `move` and `remove`; pass every other call."""
    command = call.command
    if call.action != "shell" or AGENTBOX not in os.environ or "worktree" not in joined(command):
        return PASS
    return strongest(decide(tokens, command) for tokens in readings(command, nested=True) or [])
