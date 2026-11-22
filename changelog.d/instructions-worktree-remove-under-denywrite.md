- **The Claude Code instructions give the user the removal of a worktree that tracks `.githooks/`
  or `.claude/`.** On Claude Code 2.1.327, `sandbox.filesystem.denyWrite` binds a `git` that
  `excludedCommands` takes out of the sandbox. A session's `git worktree remove` of such a worktree
  deletes its record and leaves its files as an orphan. A repository that tracks neither is still
  the session's to clean up. The same list protects `.git/hooks`, so a `git init` or `git clone`
  under `~/Research` is the user's too. `julia-pr-shepherd` names the reviewer's worktree in its
  report and does not remove it.
