- **Worktrees: no orphan under `agentbox`, a refusal in place of an orphan, a fetch that waits for
  a lock, and `harness worktree sweep`.** Under `agentbox` every `git` runs in `srt`, which denies
  writes below `.githooks`, so a `git worktree remove` deleted the worktree's record and left its
  files. The new guard check `agentbox_worktree.py` refuses `git worktree add`, `move` and
  `remove` there and names `harness worktree`, which goes through the broker. The worktree hook
  refuses a remove where it cannot write in a `.githooks` or `.claude` of the worktree, runs a
  fetch up to three times on `cannot lock ref`, and names the side-session route (`use_worktree`
  false, `cwd` in the repository, `EnterWorktree` first) when `cwd` is in no repository, as
  Claude Desktop sends for a session in `~/Research`. `harness worktree sweep [--apply]` lists the
  worktrees as removable, kept or orphan, and removes the clean ones that `origin/HEAD` holds. The
  settings template gives both worktree hooks 480 seconds, which closes K173. The guard corpus
  takes an `env` object per record.
