- **Antigravity makes and removes worktrees through the installed worktree hook.** The guard lifts
  exactly `/usr/bin/env -i HOME=<home> PATH=<the sweep's PATH> <python> -E -s <hook> add <name>`
  or `remove <path>` out of Antigravity's terminal sandbox, where `git worktree add` and
  `harness worktree add` fail; any other word on the line keeps it inside. The sandbox cannot
  write the hook or the interpreter, so the lifted program is the installed one, and `env -i`,
  `-E` and `-s` keep a variable that the session exported in a persistent terminal, such as
  `PYTHONPATH`, `PATH`, `HOME` or `GIT_SSH_COMMAND`, from reaching it or its `git`.
  `ANTIGRAVITY-DELTA.md` gives the agent the command line and the `Cwd` to set.
