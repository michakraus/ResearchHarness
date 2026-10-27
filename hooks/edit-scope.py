#!/usr/bin/env python3
"""Ask once per worktree and session before an edit of a git hook or a CI workflow.

A file below `.githooks/` runs as the user, outside the sandbox, at the next `git commit` or
`git push`. A file below `.github/workflows/` runs in CI with the repository's secrets when its
branch is pushed. So an edit of either under `~/Research` is gated. An `ask` on every such edit
stops protecting anything once a person approves forty of them in a row, so this hook asks once
per worktree and session:

  * **`PreToolUse`** on `Edit|Write|MultiEdit|NotebookEdit` — for a gated path in a main
    checkout, "ask". For a gated path below a worktree, `~/Research/.worktrees/<name>/`, "ask"
    unless `GRANTS` records this session and this worktree; then no output.
  * **`PostToolUse`** on the same tools, as `edit-scope.py --record` — after an edit of a gated
    path below a worktree, append the session and the worktree to `GRANTS`. `PostToolUse` runs
    only after the tool ran, so only an edit that was approved, by a person or the `auto`-mode
    classifier, records a grant. It never asks and never blocks.

`GRANTS` lies in `~/.claude/logs/`, which the sandbox and an `Edit` deny keep from a session.
The settings hold no `Edit` ask for these paths: an `ask` rule outranks the hook's silence.

**It fails closed, to a prompt**, on a payload it cannot read. Claude Code treats a hook that
does not run as non-blocking, so a missing or broken hook lets every gated edit through.

Test it without installing:

    echo '{"session_id":"s","tool_input":{"file_path":"'"$HOME"'/Research/Harness/.githooks/pre-push"}}' | ./edit-scope.py
"""

import datetime
import json
import os
import sys

HOME = os.path.realpath(os.path.expanduser("~"))
ROOT = os.path.join(HOME, "Research")
WORKTREES = os.path.join(ROOT, ".worktrees")
GRANTS = os.path.join(HOME, ".claude", "logs", "edit-scope.jsonl")
GATED = ("/.githooks/", "/.github/workflows/")

REASON = ("An edit of a git hook or a CI workflow: the hook runs outside the sandbox at the next "
          "commit, the workflow runs with the repository's secrets when its branch is pushed.{more}")
ONCE = " Approve it once, and this session's later edits of these files in {worktree} do not ask."


def target(payload):
    """The absolute path that the tool call edits, or None."""
    tool_input = payload["tool_input"]
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path:
        return None
    if not os.path.isabs(path):
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            raise ValueError("a relative path with no working directory")
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def gated(path):
    return path.startswith(ROOT + "/") and any(part in path for part in GATED)


def worktree(path):
    """The worktree `~/Research/.worktrees/<name>` that holds `path`, or None."""
    if not path.startswith(WORKTREES + "/"):
        return None
    name = path[len(WORKTREES) + 1:].split("/")[0]
    return os.path.join(WORKTREES, name) if name else None


def granted(session, tree):
    try:
        with open(GRANTS, encoding="utf-8") as grants:
            for line in grants:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("session_id") == session and record.get("worktree") == tree:
                    return True
    except FileNotFoundError:
        pass
    return False


def grant(session, tree):
    if granted(session, tree):
        return
    os.makedirs(os.path.dirname(GRANTS), exist_ok=True)
    record = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "session_id": session, "worktree": tree}
    with open(GRANTS, "a", encoding="utf-8") as grants:
        grants.write(json.dumps(record) + "\n")


def ask(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}))
    return 0


def main(argv):
    record = argv == ["--record"]
    try:
        payload = json.load(sys.stdin)
        path = target(payload)
        if path is None or not gated(path):
            return 0
        session = payload.get("session_id")
        session = session if isinstance(session, str) and session else None
        tree = worktree(path)
        if record:
            if tree is not None and session is not None:
                grant(session, tree)
            return 0
        if tree is not None and session is not None and granted(session, tree):
            return 0
        more = ONCE.format(worktree=os.path.basename(tree)) if tree is not None else ""
        return ask(REASON.format(more=more))
    except Exception:
        return 0 if record else ask("edit-scope could not read the call, and asks.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
