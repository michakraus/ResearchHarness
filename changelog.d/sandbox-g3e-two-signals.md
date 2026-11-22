- **`harness worktree` has a case for two signals before the hook starts.** Only the first
  goes on to the hook's process group, and the case now fails if a later one is forwarded instead.
