- **Antigravity makes and removes worktrees through the installed worktree hook.** The guard lifts
  exactly `<home>/.local/share/research-harness/python/bin/python <home>/.claude/hooks/worktree.py
  add <name>` or `remove <path>` out of Antigravity's terminal sandbox, where `git worktree add`
  and `harness worktree add` fail; any other word on the line keeps it inside. The sandbox cannot
  write the hook or the interpreter, so the lifted program is the installed one.
  `ANTIGRAVITY-DELTA.md` gives the agent the two command lines and the `Cwd` to set.
