- **On Linux, the Kaimon and julia-update units start their program under `bwrap` through
  `~/.local/bin/jobbox`.** The arguments come from the same `sandbox/daemon.toml` as the macOS
  Seatbelt profiles, through `harness render sandbox/<job>.bwrap`: new namespaces but the network,
  an empty home with only the job's paths bound, the write denies read-only, and the git hooks and
  configuration of each repository at most four levels below `~/Research` read-only. `jobbox`
  stops with exit 2 when a source of such a bind is a symbolic link or lies below one, because
  `bwrap` follows it. `harness setup` and the kit's services script run the `bwrap` check first
  and stop with exit 2 when it fails, naming `kernel.apparmor_restrict_unprivileged_userns`.
  julia-update runs its server check, the restart and its alerts in a second phase,
  `julia-update.jl --server`, outside `bwrap`; the script loads only the standard library of its
  release, and the server phase removes the update phase's state once it reads it. The macOS
  profiles keep their bytes.
