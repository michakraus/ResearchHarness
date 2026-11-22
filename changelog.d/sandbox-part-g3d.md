- **The worktree hook stops a `git` that times out with its whole process group, and a failed
  boxed create deletes the branch that it made.** Every `git` of `hooks/worktree.py`, and the
  `srt` of a boxed `git`, now starts in a session of its own; past its timeout the hook sends
  `SIGTERM` to the group and `SIGKILL` 5 seconds later where it has not ended, so the stop reaches
  the `git` inside `srt` and the `ssh` of a fetch, not only `srt` or `git`. A `SIGINT`, `SIGTERM`
  or `SIGHUP` of the hook, such as `harness worktree` passes on, stops that group the same way
  before the hook ends, and a `SIGTERM` or `SIGHUP` during a stop that a `SIGTERM` or `SIGHUP`
  began does not cut it short, while a `git` that the hook starts after the signal keeps the
  default handlers of both. A `SIGINT` during any stop, and any of the three signals during a
  stop that a timeout or a `SIGINT` began, ends that stop before its `SIGKILL`, and such a signal
  during the undo of a failed create can end the undo before its `git branch -D`. A program that
  cannot start is a one-line refusal, not a traceback, and a boxed remove whose `srt` cannot start
  puts the worktree back at its path. A broker that refuses to start because of a directory at
  its profile's path now exits with that refusal, not with a traceback, and leaves the directory.
  A boxed create now makes a new branch with `git branch --no-track` before its
  `git worktree add`, and deletes it with `git branch -D` where a later step fails, the add
  included, unless a signal ends that undo first; a branch that another process made first, an
  existing branch and a sub-agent's detached worktree lose nothing. A worktree name that ends in a
  newline is refused (K186), and so is one that begins with `-`, which `git` reads as an option.
  `--serve … --parent` takes ASCII digits only (K184).
