- **The worktree hook stops a `git` that times out with its whole process group, and a failed
  boxed create deletes the branch that it made.** Every `git` of `hooks/worktree.py`, and the
  `srt` of a boxed `git`, now starts in a session of its own; past its timeout the hook sends
  `SIGTERM` to the group and `SIGKILL` 5 seconds later where it has not ended, so the `git` inside
  `srt` or the `ssh` of a fetch no longer outlives the hook. A program that cannot start is a
  one-line refusal, not a traceback, and a boxed remove whose `srt` cannot start puts the worktree
  back at its path. A broker that refuses to start because of a directory at its profile's path
  now exits with that refusal, not with a traceback, and leaves the directory. A boxed create that
  fails after its `git worktree add -b` deletes the new branch with `git branch -D`; an existing
  branch and a sub-agent's detached worktree lose nothing. A worktree name that ends in a newline
  is refused (K186), and `--serve … --parent` takes ASCII digits only (K184).
