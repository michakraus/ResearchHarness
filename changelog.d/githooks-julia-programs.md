- **The Julia packages' `pre-commit` and `pre-push` hooks are each one Julia program,
  `githooks/pre-commit.jl` and `githooks/pre-push.jl`, behind a short bash launcher.** A commit
  started `julia` up to four times and loaded JuliaFormatter in a process of its own; it now
  starts `julia` once, and only the load test runs in a child process, started with
  `Base.julia_cmd()` in the package's environment. Without `julia` on the `PATH`, each launcher
  prints one line and refuses; without `fatou`, the lint stage prints that it is skipped. The
  60 s limit of `fatou lint` is a Julia timer and holds on every system, so the harness no longer
  needs `timeout`: `harness doctor` no longer checks for it, and the macOS setup page no longer
  installs `coreutils`. On an interrupt, `pre-push` passes the signal to its suite's process
  group and waits for it. `harness githooks` installs the two programs beside their launchers, and
  `githooks/pre-commit-test.jl` now also covers the NFC stage, the lint stage and `pre-push`.
