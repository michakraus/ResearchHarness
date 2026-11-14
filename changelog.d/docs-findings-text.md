- **The ast-grep page states which rules a comment can silence, and `parts-table.awk` cites no
  task file.** `agentic/static-checks.md` said that `# ast-grep-ignore: <rule-id>` on a line
  silences any hit; it now says that the comment works at the end of the line or on the line
  above, that `docstring-comment` cannot be silenced, and that `line-citation-comment` is silenced
  only from the line above, as `components/other.md` says. The comment of `mask` in
  `scripts/parts-table.awk` gives its example cell without the name of a task file that the
  public repository does not hold; K73 keeps the other two such citations.
