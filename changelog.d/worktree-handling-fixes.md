- **Under `agentbox`, the guard refuses `git worktree add`, `move` and `remove` and names
  `harness worktree`.** In `srt` every `git` is sandboxed, and `srt` denies writes below
  `.githooks`: a `git worktree remove` deleted the files up to the first one there, then the
  worktree's record, and left the rest of the directory with no record. The new check
  `agentbox_worktree.py` runs on every frontend and sends the call to the broker's route.
- **The worktree hook refuses a remove that it cannot finish.** Before `git worktree remove` it
  makes and removes one file in each `.githooks` and `.claude` of the worktree, and refuses where a
  sandbox denies the write, so that a sandboxed caller gets a refusal and no orphan.
- **The worktree hook retries a fetch that lost a ref's lock.** Two creates in one repository fetch
  at the same time, and the second failed with `cannot lock ref`; the hook now runs the fetch up to
  three times, 2 seconds apart, for that error alone.
- **The hook's refusal for a `cwd` in no repository names the side-session route.** Claude Desktop
  sends the session's folder, `~/Research`, for a side session: start it with `use_worktree`
  false, `cwd` in the repository, and `EnterWorktree` first. `CLAUDE.md` states the same route,
  the `agentbox` route for a remove, and that a shell must not enter a worktree before its removal.
- **`harness worktree sweep [--apply]` lists the worktrees as removable, kept or orphan**, and with
  `--apply` removes the clean ones whose HEAD `origin/HEAD` holds and that nobody used for 12 hours.
- **The settings template gives `WorktreeCreate` and `WorktreeRemove` 480 seconds**, more than the
  hook's fetch and the broker's answer take. This closes K173.
- **The guard corpus takes an `env` object per record**, and the probe runs without the caller's
  `AGENTBOX` and `AGENTBOX_BROKER`.
