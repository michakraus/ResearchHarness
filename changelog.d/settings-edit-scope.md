- **An edit of a git hook or a CI workflow in a worktree asks once per session, not on every
  edit.** The new hook `edit-scope.py` asks before the first edit below `.githooks/` or
  `.github/workflows/` in a worktree; its `PostToolUse` run records the approval in
  `~/.claude/logs/edit-scope.jsonl`, and later edits there in the same session run unasked. A
  main checkout asks on every such edit. The settings template drops the two `Edit` asks of these
  paths, which would outrank the hook, adds an `Edit` deny of `~/.claude/logs/`, and registers
  the hook on `Edit|Write|MultiEdit|NotebookEdit`. OpenCode, oh-my-pi and Antigravity keep asking
  on each edit. In 23 days of the permission-dialog log these edits made 241 lines, 151 of them
  in worktrees; one approval now grants the session every later edit of these files in that
  worktree, and a hook that does not run lets them all through.
