#!/usr/bin/env python3
"""Ask before a session leaves `~/Research`, or removes a worktree through the harness.

A `PreToolUse` hook on the matcher `mcp__ccd_directory__.*|EnterWorktree|ExitWorktree`:
the app's `change_directory` and `request_directory`, and the two worktree tools. All four
are in `allow`, and this hook carves out the calls the `allow` must not cover.

  * **`change_directory`, `request_directory`, `EnterWorktree` with a `path`** — no output
    when the path resolves inside `~/Research`, after `~`, `..` and symlinks. Else "ask".
  * **`EnterWorktree` with a `name` only** — no output. The `WorktreeCreate` hook decides
    where the worktree goes, and it fails closed.
  * **`ExitWorktree`** — no output for `action: "keep"` with no `discard_changes`. Else
    "ask": a `remove` can discard changes.
  * **Anything else** — `permissionDecision: "ask"`: a relative or missing path (which
    opens the folder picker), and input the hook cannot read.

No `permissions` rule can state this. Claude Code skips an `mcp__` rule with parentheses,
so a rule matches the tool name only. And a hook's `allow` does not skip an `ask` rule, so
the tools go in `allow` and the hook carves the exception out of it.

**It fails closed, to a prompt.** A prompt is the behaviour the tools had with no rule.

Test it without installing:

    echo '{"tool_input":{"path":"~/Research/Packages"}}' | ./directory-scope.py
"""

import json
import os
import sys

ROOT = os.path.realpath(os.path.expanduser("~/Research"))


def inside(path):
    """Return True when `path` is absolute and resolves to `ROOT` or below it."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        return False
    target = os.path.realpath(path)
    return os.path.commonpath([ROOT, target]) == ROOT


def passes(call):
    """Return True when the call may run on the `allow` rule with no prompt."""
    tool = call.get("tool_name", "")
    args = call["tool_input"]
    if tool == "ExitWorktree":
        return args.get("action") == "keep" and not args.get("discard_changes")
    if tool == "EnterWorktree" and "path" not in args:
        return isinstance(args.get("name"), str)
    path = args["path"]
    return isinstance(path, str) and inside(path)


def main():
    try:
        if passes(json.load(sys.stdin)):
            return 0
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason":
            f"The target is outside {ROOT}, or the call removes a worktree.",
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
