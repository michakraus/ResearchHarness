"""Ask before a session leaves `~/Research`, or removes a worktree.

The check reads the calls that change the session's directory or worktree, by their neutral names:
`directory.<tool>` (the desktop app's `change_directory` and `request_directory`), `worktree.enter`
and `worktree.exit`. A frontend allows these tools, and the check carves out the calls that the
allow must not cover:

  * a directory change, and `worktree.enter` with a path: pass when the path resolves inside
    `~/Research`, after `~`, `..` and symlinks; else ask;
  * `worktree.enter` with a name only: pass. The `WorktreeCreate` hook decides where the worktree
    goes, and it fails closed;
  * `worktree.exit`: pass for `action: "keep"` with no `discard_changes`; else ask, since a
    `remove` can discard changes;
  * anything else: ask. A relative or missing path opens the folder picker.
"""

import os
from pathlib import Path, PurePosixPath

from .contract import PASS, Call, Verdict

ROOT = os.path.realpath(PurePosixPath(Path.home(), "Research"))
HOME = str(Path.home())


def inside(path: str) -> bool:
    """True when `path` is absolute and resolves to `ROOT` or below it."""
    if path == "~" or path.startswith("~/"):
        path = HOME + path[1:]
    if not PurePosixPath(path).is_absolute():
        return False
    target = os.path.realpath(path)
    return os.path.commonpath([ROOT, target]) == ROOT


def passes(call: Call) -> bool:
    """True when the call may run on the allow rule with no prompt."""
    if call.command == "worktree.exit":
        return call.argument("action") == "keep" and call.argument("discard_changes") is None
    if call.command == "worktree.enter" and not call.paths:
        return call.argument("name") is not None
    return bool(call.paths) and inside(call.paths[0])


def check(call: Call) -> Verdict:
    """Ask for a directory change outside `~/Research`, and for a worktree removal."""
    if call.action != "mcp" or not call.command.startswith(("directory.", "worktree.")):
        return PASS
    if passes(call):
        return PASS
    return Verdict("ask", f"The target is outside {ROOT}, or the call removes a worktree.")
