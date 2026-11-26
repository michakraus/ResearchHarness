- **The git-write check no longer asks for a command that it cannot read and that holds no `git`
  write.** An open quote, such as a Julia adjoint `x'` in a heredoc body, made the parser give up,
  and the check then asked for any command with `push`, `worktree` or `cherry-pick` in its text:
  each heredoc probe with `push!` and each path below `.worktrees/` stopped a sub-agent for
  approval. Such a command now asks only when it holds a word `git` and after it one of these
  keywords as a word of its own, or a `$` before a quote or a backslash, which can open an ANSI-C
  quote such as `$'\x67it'` that the shell decodes into `git`; a readable command is decided as
  before.
