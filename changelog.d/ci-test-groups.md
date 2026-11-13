- **A repository can split its CI test jobs into the test groups of `test/ci-groups.toml`, and
  `CI.yml` stays byte-identical in every repository.** A new `groups` job of `CI.yml` reads the
  file, and the `test` and `downgrade` jobs run once per group, with the group as the argument of
  `Pkg.test` and ` - <group>` at the end of the job name; without the file the jobs and their names
  are those of today, beside the new `Test groups` check. `harness ci-protection` requires one
  check per group from the file, `verify-workflows.jl` accepts the new job name and checks the file
  against `runtests.jl`, and `test-layout.jl` accepts the file's groups, in the `GROUPS` line that
  an empty `ARGS` runs, so `Pkg.test()` still runs every group. `run-tests.jl` selects such a group
  by name. A suite longer than the 120-minute timeout of one job can then pass its required checks.
