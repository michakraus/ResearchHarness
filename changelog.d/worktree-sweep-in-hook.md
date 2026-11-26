- **The worktree hook holds the sweep, and takes `add <name>`, `remove <path>` and
  `sweep [--apply]` on its command line.** `harness worktree sweep` runs the hook's sweep instead
  of a copy of its own, so the logic exists once, in the installed hook that no session can
  write. The sweep's `git` runs as every `git` of the hook does: it reads no repository that the
  hook's checks refuse, which keeps a forged `.git` file or a `core.fsmonitor` from running a
  command outside the sandbox. The dry run's last line is `would remove <n> worktrees`.
