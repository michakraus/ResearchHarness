- **An agent leaves a finished worktree in place, and hands the user a removal command only on
  request.** The global instructions name the nightly `worktree-sweep` job as the route that
  removes a merged, clean and idle worktree, also one that holds a `.githooks/` or a `.claude/`,
  which no session can remove. An agent gives the user `git -C <main checkout> worktree remove
  <path>` only when the user asks for a worktree to go now, or for one that the sweep keeps.
