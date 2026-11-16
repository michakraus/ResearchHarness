- **`test-layout.jl` accepts and judges the keys `split` and `once` of `test/ci-groups.toml`,
  and the new `ci_options` gives them with their defaults, `true` and an empty list.** Check 6 of
  `verify-workflows.jl` and the pre-commit layout check then pass a file with `split = false` or
  `once = [...]`, and report a `split` that is not `true` or `false`, a `once` that is not a list
  of group names, and a group of `once` that `groups` does not list, that is there twice or that
  is `core`. The CI jobs do not read either key yet. `tests_table` takes the parsed `runtests.jl`,
  and `test-census.jl` counts the files of `TESTS` of a suite in the parallel form in a column of
  its own.
