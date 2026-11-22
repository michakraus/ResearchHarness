- **The Claude Code instructions give the user the removal of a worktree that holds a
  `.githooks/` or a `.claude/`.** On Claude Code 2.1.327, `sandbox.filesystem.denyWrite` binds a
  `git` that `excludedCommands` takes out of the sandbox. A session's `git worktree remove` of
  such a worktree deletes its record and leaves its files as an orphan. A worktree that holds
  neither is still the session's to clean up, and the session deletes the local branch after the
  removal. The same list protects `.git/hooks`, so a `git init` or `git clone` under `~/Research`
  is the user's too. `julia-pr-shepherd` and `julia-pr-reviewer` leave the removal to their
  caller, and the shepherd reports the reviewer's worktree.
