- **The guard refuses `EnterWorktree` with a `path` inside `~/Research` outside a repository's
  `.claude/worktrees/`, and names `cd <path>` as a Bash call of its own.** Claude Code 2.1.319 asks
  the person for every such call ("permission-root relocation … a model-supplied worktree outside
  .claude/worktrees/"), as a safety check with `classifierApprovable: false`. After a hook's
  `allow`, Claude Code still runs the tool's own permission check, and that check's ask goes to the
  prompt, so neither a hook, an allow rule nor auto mode removes it. The worktrees here come from
  the `WorktreeCreate` hook into `~/Research/.worktrees/`, so every switch into one by path
  prompted. A `cd` into a worktree inside the working directory `~/Research` needs no prompt. The
  global worktree section says the same; a path in `.claude/worktrees/` passes, and a path outside
  `~/Research` still asks.
