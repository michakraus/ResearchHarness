- **`julia-load-doctor` has two more cause classes: missing manifest and stale manifest.** In a
  replay of two real load failures, the agent found both causes but no class fitted either: one
  report answered "nearest is upstream regression", the other "none of the four". One report also
  called the gitignored `Manifest.toml` tracked, which invites a commit of the re-resolved file.
  The agent states that `Manifest.toml` is gitignored, checks it with `git check-ignore`, and
  names why a worktree has no manifest: the worktree hook copies the main checkout's manifest only
  when it fits `[compat]`. The description adds "is required but does not seem to be installed"
  as a trigger, and the agents page lists six classes.
