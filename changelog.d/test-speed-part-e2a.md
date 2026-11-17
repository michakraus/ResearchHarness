- **`test-layout.jl` accepts and judges the keys `split` and `once` of `test/ci-groups.toml`,
  and the new `ci_options` gives them with their defaults, `true` and an empty list.** Check 6 of
  `verify-workflows.jl` then passes a file with `split = false` or `once = [...]`, and reports a
  `split` that is not `true` or `false`, a `once` that is not a list of group names, and a group of
  `once` that `groups` does not list, that is there twice or that is `core`. The pre-commit layout
  check of a repository does the same once `harness githooks --apply` copies the script into its
  `.githooks/`. The CI jobs do not read either key yet. `tests_table` takes the parsed
  `runtests.jl`, and `test-census.jl` counts the files of `TESTS` of a suite in the parallel form
  in a column of its own.
