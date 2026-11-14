- **The Claude Code instructions tell a session to remove a worktree itself.** Since Claude Code
  2.1.323 the model reads that `.git/worktrees` is read-only in the sandbox, and sessions handed
  `git worktree remove` to the user; that holds only for a sandboxed `git`, and the plain command
  runs outside the sandbox.
