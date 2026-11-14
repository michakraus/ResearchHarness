- **`Dependents.yml` no longer reads a failed setup as a failed test (K159).** Each run against
  the head and against the base's default branch has a setup step, `Pkg.develop`, and a test step
  that runs only after its setup succeeded. `dependents.jl row` takes the four outcomes. A failed
  setup against the head beside a default branch that installs is a regression. A failed setup
  against the default branch is a new row, *inconclusive*, which names the failed setups and fails
  the job, so that a person reads the log or runs the job again. Before, such a failure read as
  *known red* and could hide a regression of the pull request.
