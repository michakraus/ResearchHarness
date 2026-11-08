"""Ask before a session leaves `~/Research`, or removes a worktree; refuse an `EnterWorktree` call
that Claude Code asks the person for anyway.

The check reads the calls that change the session's directory or worktree, by their neutral names:
`directory.<tool>` (the desktop app's `change_directory` and `request_directory`), `worktree.enter`
and `worktree.exit`. A frontend allows these tools, and the check carves out the calls that the
allow must not cover:

  * a directory change: pass when the path resolves inside `~/Research`, after `~`, `..` and
    symlinks; else ask;
  * `worktree.enter` with a path: ask when the path resolves outside `~/Research`; pass when it
    resolves into a `.claude/worktrees/` directory; else deny. Claude Code asks the person for
    every other path itself, and neither a hook's allow nor auto mode approves that ask, so the
    denial names the way that needs no prompt: `cd <path>` as a shell call of its own;
  * `worktree.enter` with a name only: pass. The `WorktreeCreate` hook decides where the worktree
    goes, and it fails closed;
  * `worktree.exit`: pass for `action: "keep"` with no `discard_changes`; else ask, since a
    `remove` can discard changes;
  * anything else: ask. A relative or missing path opens the folder picker.
"""

from pathlib import Path, PurePosixPath

from .contract import PASS, Call, Verdict

ROOT = Path(Path.home(), "Research").resolve()
HOME = str(Path.home())

# The directory below a repository that holds the worktrees Claude Code makes itself.
MANAGED = (".claude", "worktrees")


def resolved(path: str) -> Path | None:
    """The path that `path` resolves to, after `~`, `..` and symlinks, when it resolves to `ROOT`
    or below it; None for a relative path and for a path outside `ROOT`."""
    if path == "~" or path.startswith("~/"):
        path = HOME + path[1:]
    if not PurePosixPath(path).is_absolute():
        return None
    found = Path(path).resolve()
    return found if found.is_relative_to(ROOT) else None


def managed(path: Path) -> bool:
    """True when `path` lies in a `.claude/worktrees/` directory, below a worktree's own name."""
    parts = path.parts
    return any(parts[i : i + 2] == MANAGED for i in range(len(parts) - 2))


def entered(path: str) -> Verdict:
    """The verdict on `worktree.enter` with the path `path`."""
    found = resolved(path)
    if found is None:
        return Verdict("ask", f"The target is outside {ROOT}.")
    if managed(found):
        return PASS
    return Verdict(
        "deny",
        f"Refused: EnterWorktree with the path {path}\n\n"
        "Claude Code asks the person for every EnterWorktree call whose path is outside a "
        "repository's .claude/worktrees/, and neither a hook nor auto mode can approve it. Reach an "
        f"existing worktree with `cd {path}` as a Bash call of its own: a bare `git` in the next "
        "call then runs there. To have an agent work there, spawn it with `cwd` set to the "
        "worktree. Make a new worktree with EnterWorktree and `name`.\n",
    )


def passes(call: Call) -> bool:
    """True when a directory change or `worktree.exit` may run on the allow rule with no prompt."""
    if call.command == "worktree.exit":
        return call.argument("action") == "keep" and call.argument("discard_changes") is None
    return bool(call.paths) and resolved(call.paths[0]) is not None


def check(call: Call) -> Verdict:
    """Ask for a directory change outside `~/Research` and for a worktree removal; refuse
    `worktree.enter` with a path that Claude Code asks the person for."""
    if call.action != "mcp" or not call.command.startswith(("directory.", "worktree.")):
        return PASS
    if call.command == "worktree.enter":
        if call.paths:
            return entered(call.paths[0])
        if call.argument("name") is not None:
            return PASS
    elif passes(call):
        return PASS
    return Verdict("ask", f"The target is outside {ROOT}, or the call removes a worktree.")
