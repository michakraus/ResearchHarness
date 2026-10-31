- **The Julia packages' hooks need Julia only where they run a check, and check renamed, non-ASCII
  and unparsable files.** Without `julia` on the `PATH`, `pre-commit` passes a commit with no
  staged `.jl` file and no change below `test/`, and `pre-push` passes a push that updates no
  `main` or `master`, as the shell hooks before `pre-commit.jl` did; every other commit or push is
  still refused. `pre-commit.jl` lists the staged files with `-z`, so a path with non-ASCII
  characters reaches the stages as itself and not in git's quoted form; it includes renamed files
  (`--diff-filter=ACMR`), which skipped every stage before; and it formats with
  `throw_on_error = true`, so a file that does not parse fails the formatting stage, where
  JuliaFormatter 2.14 reported it formatted. K128 records that every stage reads the working
  tree, not the index.
