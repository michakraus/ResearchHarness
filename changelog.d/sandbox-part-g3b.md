- **OpenCode and oh-my-pi agents get their worktrees from `harness worktree`, not from `git`.**
  Neither frontend has a `WorktreeCreate` hook, and their instructions told the agent to run
  `git worktree add`, which fails under `agentbox` on the deny of `.githooks/`. The new subcommand
  `harness worktree add <name> --apply` runs the installed `~/.claude/hooks/worktree.py` with the
  payload of a `WorktreeCreate` event, in the working directory, and prints the worktree's path;
  `harness worktree remove <path> --apply` sends `WorktreeRemove`. Under `agentbox` the hook asks
  its broker outside the sandbox, as for Claude Code. Without `--apply` the subcommand prints the
  request and exits 1; a missing hook, or a hook that fails, exits 2 with the hook's last line. The
  section *Worktrees: ask for them* of `OPENCODE-DELTA.md` and `OMP-DELTA.md`, the OpenCode rule
  of an agent with `isolation: worktree` and the `worktree` section of `UNDER-OMP.md` now send the
  agent to `harness worktree add`. Antigravity's instructions keep `git worktree add`: its shell
  tool does not run under `agentbox`.
