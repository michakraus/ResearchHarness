- **On Linux, the Kaimon and julia-update units start their program under `bwrap` through
  `~/.local/bin/jobbox`.** The arguments come from the same `sandbox/daemon.toml` as the macOS
  Seatbelt profiles, through `harness render sandbox/<job>.bwrap`: new namespaces but the network,
  an empty home with only the job's paths bound, the write denies read-only, and for Kaimon the
  git hooks and configuration of each repository at most four levels below `~/Research`
  read-only. `jobbox`
  stops with exit 2 when the source of a bind below an entry of the home is a symbolic link or
  lies below one under that entry, because `bwrap` follows it (the entry itself, such as
  `~/.julia`, may be a link), and each job binds onto itself the paths of the other job's
  bind sources that it writes, so that it cannot swap them while it runs. `harness setup` and the
  kit's services script run the `bwrap` check first and stop with exit 2 when it fails, naming
  `kernel.apparmor_restrict_unprivileged_userns`. julia-update runs its server check, the restart
  and its alerts in `~/.local/bin/julia-update-server`, a POSIX `sh` script outside `bwrap` that
  runs no Julia and reads the update phase's state as data. The macOS profiles keep their bytes.
