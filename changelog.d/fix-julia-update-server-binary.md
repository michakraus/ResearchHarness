- **On macOS, `julia-update.jl` reads the Kaimon server's binary with `lsof`, not `ps` (K61).**
  The job's profile refuses the exec of the setuid `/bin/ps`, so the server check crashed on every
  run and never restarted a server whose Julia release `juliaup` had deleted. An `lsof` that cannot
  start or lists no binary is now a failure with an alert, never a stack trace.
  The macOS run of `julia-update-test.jl` reads a deleted binary with the real `lsof`.
