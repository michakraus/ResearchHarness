- **The shared pre-commit hook refuses a commit in which a staged `.jl` file also has changes
  that are not staged.** Every stage reads the files on disk, so such a file was judged on text
  that the commit does not hold: an unformatted staged version with a formatted edit on top
  passed, and an added `@show` could read as advisory. The hook now lists the staged `.jl` files
  that `git diff --name-only` also lists, with literal paths, no external diff program or
  textconv driver, and without `GIT_DIFF_OPTS`, `GIT_ICASE_PATHSPECS` and `GIT_GLOB_PATHSPECS`,
  and refuses before any stage runs, with one line per file and the advice to stage the rest of
  the file or move the unstaged edits aside. A fully staged file passes, also beside an unstaged
  edit of another file. K128 stays open: the full fix checks a copy of the index in every stage,
  which also closes the symlink case. The hook reaches the packages at the next
  `harness githooks --apply`.
