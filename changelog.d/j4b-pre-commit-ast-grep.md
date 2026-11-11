- **The shared pre-commit hook runs the ast-grep rules, as stage 2.7, and blocks a hit on a line
  that the commit adds.** `ast-grep scan --custom-languages allow` runs once over the staged `.jl`
  files with the `sgconfig.yml` that it finds in the repository or above it. A hit of severity
  `error` refuses the commit when one of its lines is a line that the commit adds, from the hunks
  of `git diff --cached -U0 -M`; a hit on any other line only warns, so the hits that a file
  already holds do not block an unrelated commit, and a pure rename adds no line. The `info` hits
  of `parse-error` are not printed, and `# ast-grep-ignore: <rule-id>` silences one hit. Without
  `ast-grep` on the `PATH`, without an `sgconfig.yml`, with a configuration that applies no rule,
  on an exit code other than 0 and 1, on an output that is not one JSON object per line, without
  a JSON package that loads, or after the limit of 60 s, the stage prints one `ast-grep: skipped —` line and the commit passes. The
  time box can keep the stdout and the stderr of its command apart, and the matrix job of
  `julia.yml` installs ast-grep 0.51.1 and builds the parser for `pre-commit-test.jl`, whose
  summary lists every test set. The entries of `build-part/edges.md` on `@allocated` readings and
  on `p.exitcode`, the comment case of its docstring entry, and the two sentences of
  `rules/julia-code.md` on an untagged `@show` and on a line number in a comment are removed: the
  rules check them on each commit. The hook reaches the packages at the next
  `harness githooks --apply`.
