- **`harness doctor` checks the `worktree-sweep` job.** It reads `launchctl list` of its label on
  macOS and the list of the `systemd --user` timers on Linux, as for the other jobs, and a job that
  is not loaded is a `FAIL` that names *The jobs* of `setup-reference.md`, so a machine where
  `harness setup` has not loaded the nightly sweep no longer passes.
