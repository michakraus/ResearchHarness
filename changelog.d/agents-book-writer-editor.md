- **Two lean agents write books and papers: `editor` and `writer`.** A session that writes a
  manuscript starts one `editor` per unit (a chapter, an appendix or a section) in the background.
  The editor fills the writer's brief, starts a `writer` in the foreground, verifies every page,
  proof and script itself, sends its findings to a new writer (at most three writers per unit),
  merges the shared files and commits. Both load no `CLAUDE.md` and read the `Papers/` and `Books/`
  instruction files instead. By the size of their text, each starts at about 15k tokens, the 10k of
  `worker` plus its body and the `math-verify` and `latex-revision` skills, against about 66k for
  `general-purpose`, which ran this work before. A fix round is a new writer because a `SendMessage`
  to a writer resumes it in the background: the editor's turn then ends, and with it the editor's
  run, before the commit. The editor keeps its cache for one hour, because it waits for each writer
  with the unit read into its context. Both agents port to OpenCode (editor to writer is the second
  level that `subagent_depth` 2 allows), oh-my-pi and Antigravity through the adapters.
