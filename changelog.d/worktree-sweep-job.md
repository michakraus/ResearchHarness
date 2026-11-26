- **A nightly job, `worktree-sweep`, removes the finished worktrees.** `harness setup` installs a
  launch agent on macOS and a `systemd --user` timer on Linux that run the installed hook's
  `worktree.py sweep --apply` at 05:00, after `julia-update`. It runs outside every sandbox and
  without a job profile, because a sandbox denies the `.githooks` and `.claude` directories that a
  removal deletes; it runs the hook on the harness's own interpreter, never `harness`, because a
  session can write `~/Research/Harness`. Its log is `~/Library/Logs/worktree-sweep/` on macOS and
  the journal on Linux.
