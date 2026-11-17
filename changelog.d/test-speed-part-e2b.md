- **The CI jobs and the required checks follow `split` and `once` of `test/ci-groups.toml`.** The
  `groups` job of `CI.yml` and `Downgrade.yml` writes the matrix rows of `test` and `test-other`
  in place of its `versions` output, and both jobs read them as the `include` of their matrix and
  pass each row's test arguments. `split = false` runs all groups of a matrix entry in one job,
  with the job names and the five required checks of a repository without groups; the job names
  its groups as its test arguments, so an empty `ARGS` never adds a device group. `once` runs its
  groups on Ubuntu with Julia `1` alone on a pull request and a push to a branch, while the weekly
  run, a tag and a run by hand run every group everywhere. `harness ci-protection` requires the
  checks of those rows, and refuses a `split` or `once` that the `groups` job refuses, with the same
  text; `verify-workflows.jl` prints the same list, and none for a group file that its check 6
  refuses. A suite in the parallel form can then run one job per matrix entry, and keep the groups
  of `once` off macOS and Windows on a pull request.
