- **`harness worktree` exits 128 + n for every signal that arrives while its hook runs, the stop
  after a timeout included.** A SIGINT, SIGTERM or SIGHUP that arrives before the hook's
  process starts now goes on to the hook's process group right after the start, where before the
  hook ran to its end (K187). A signal while a timeout stops the hook now gives 128 + n, not the
  exit 2 of the timeout (K188); a timeout without a signal still exits 2. So `harness worktree
  sweep --apply` now also ends with 128 + n at a removal where a signal arrives while a timeout
  stops the hook, where before it counted that removal as failed and asked the hook for the next
  one; a signal during any other removal ended the sweep before, too. The OpenCode and
  oh-my-pi instructions now say that the frontend has no `WorktreeCreate` event and send the agent
  to Claude Code's installed worktree hook, where they said "There is no `WorktreeCreate` hook"
  and then "Ask the installed hook". The development page names all ten subcommands that the
  contract sweep skips: `setup`, `update`, `test` and `worktree` too (K185).
