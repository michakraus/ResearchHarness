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

Test it without installing, with a file of `$HOME/Research/Harness/.githooks/` as `file_path`:

    echo '{"session_id":"s","tool_input":{"file_path":"…/.githooks/pre-push"}}' | ./edit-scope.py
"""

import datetime
import json
import pathlib
import sys

from guard import HarnessError
from guard.jsonio import loads

HOME = pathlib.Path.home().resolve()
ROOT = HOME / "Research"
WORKTREES = ROOT / ".worktrees"
GRANTS = HOME / ".claude" / "logs" / "edit-scope.jsonl"
GATED = ("/.githooks/", "/.github/workflows/")

REASON = (
    "An edit of a git hook or a CI workflow: the hook runs outside the sandbox at the next "
    "commit, the workflow runs with the repository's secrets when its branch is pushed.{more}"
)
ONCE = " Approve it once, and this session's later edits of these files in {worktree} do not ask."


def target(payload: dict[str, object]) -> pathlib.Path | None:
    """The absolute path that the tool call edits, or None."""
    tool_input = payload["tool_input"]
    if not isinstance(tool_input, dict):
        raise TypeError("tool_input is no object")
    fields: dict[str, object] = tool_input  # pyright: ignore[reportUnknownVariableType]
    path = fields.get("file_path") or fields.get("notebook_path")
    if not isinstance(path, str) or not path:
        return None
    edited = pathlib.Path(path)
    if not edited.is_absolute():
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not pathlib.Path(cwd).is_absolute():
            raise ValueError("a relative path with no working directory")
        edited = pathlib.Path(cwd) / edited
    return edited.resolve()


def gated(path: pathlib.Path) -> bool:
    return path.is_relative_to(ROOT) and any(part in f"{path}/" for part in GATED)


def worktree(path: pathlib.Path) -> pathlib.Path | None:
    """The worktree `~/Research/.worktrees/<name>` that holds `path`, or None."""
    if not path.is_relative_to(WORKTREES) or path == WORKTREES:
        return None
    return WORKTREES / path.relative_to(WORKTREES).parts[0]


def granted(session: str, tree: pathlib.Path) -> bool:
    try:
        with GRANTS.open(encoding="utf-8") as grants:
            for line in grants:
                try:
                    record = loads(line, where=str(GRANTS))
                except HarnessError:
                    continue
                if record.get("session_id") == session and record.get("worktree") == str(tree):
                    return True
    except FileNotFoundError:
        pass
    return False


def grant(session: str, tree: pathlib.Path) -> None:
    if granted(session, tree):
        return
    GRANTS.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": session,
        "worktree": str(tree),
    }
    with GRANTS.open("a", encoding="utf-8") as grants:
        grants.write(json.dumps(record) + "\n")


def ask(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def main(argv: list[str]) -> int:
    record = argv == ["--record"]
    try:
        # A payload that is empty, not JSON or no JSON object raises HarnessError, which asks below.
        call: dict[str, object] = dict(loads(sys.stdin.read(), where="the payload"))
        path = target(call)
        if path is None or not gated(path):
            return 0
        session = call.get("session_id")
        session = session if isinstance(session, str) and session else None
        tree = worktree(path)
        if record:
            if tree is not None and session is not None:
                grant(session, tree)
            return 0
        if tree is not None and session is not None and granted(session, tree):
            return 0
        more = ONCE.format(worktree=tree.name) if tree is not None else ""
        return ask(REASON.format(more=more))
    # A hook that crashes fails open, so every error before the edit asks; after it, nothing blocks.
    except Exception:  # noqa: BLE001
        return 0 if record else ask("edit-scope could not read the call, and asks.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
