- **The `using Kaimon` check of `julia-update.jl` loads Kaimon with an empty `KAIMON_CONFIG_DIR`.**
  The job's profile refuses `~/.config/kaimon`, which holds the server's keys, so every run logged
  `Failed to load global config`. The check now reads no configuration, and the warning is gone.
