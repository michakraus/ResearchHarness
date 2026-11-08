- **The guard reads a write that a quote, an ANSI-C quote or a shell script hides.** The keyword
  pre-filters of the shell checks read the command without its quotes and backslashes and as the
  shell splits it, so `r""m -rf`, `git arch""ive -o`, `g""h api -X DELETE`, `git a""dd -A` and
  `t''ee` reach their checks; before, each passed. The two checks that model Claude Code's own
  text match for the sandbox keep their raw-text filter. The shell reader decodes an ANSI-C quote
  `$'…'` and a locale quote `$"…"` in three readings, and each check answers the strongest: bash's
  (an unknown escape keeps its backslash, a NUL ends the quote), zsh's (an unknown escape drops
  its backslash, a NUL ends the word), and one that decodes neither, as before. So
  `git push --force-$'w'ith-lease origin main`, `--force-$'\w'ith-lease` and `$'rm\0' -rf …` are
  refused. A lease push with an option that the shell expands into a lease (`--force-$w`,
  `--$(…)`) is read as one: refused when it names a default branch, asked otherwise. The scripts
  of `sh -c`, `bash -c`, `zsh -c` (and `dash`, `ksh`, `mksh`, `ash`, `csh`, `tcsh`, and `fish`
  with `-c` or `--command`) and `eval` are read as parts of the command, three levels deep, by the
  checks of `rm`, `git archive`, `gh api`, `gh pr create`, the `gh` watchers, `git add` and the
  three `git` writes, and by the Bash rules and the path check of Antigravity; a `git` write
  inside such a script is never allowed with no prompt. K88 shrinks to a program that a variable
  or a substitution names, and K92 to a path that a substitution makes; K136 records the same
  limit of the other checks.
- **A lease push reads the default branch of the repository that it pushes from.** The test for a
  default branch reads `origin/HEAD` in the directory after each `cd` before the push and each
  `-C` or `--git-dir` of its `git`, as well as in the call's working directory, so
  `git -C ../Other push --force-with-lease origin trunk` is refused when `trunk` is `Other`'s
  default branch; before, it asked. The value of an option, such as `-o main`, no longer reads as
  a target: `git push --force-with-lease -o main origin feature` asks instead of being refused.
