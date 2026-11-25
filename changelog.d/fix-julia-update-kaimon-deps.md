- **`julia-update.jl` reports `RESTART DUE` when a Kaimon dependency changes in `Manifest.toml`.**
  Previously, the server check compared only Kaimon's own `version` in `Project.toml`, so a
  dependency-only fix such as `Tachikoma 2.8.0 -> 2.8.1` printed `No restart due.` while the live
  server kept running the older dependency. `julia-update.jl` now snapshots the packages in
  Kaimon's app `Manifest.toml` before and after `Pkg.Apps.update("Kaimon")`, lists any added,
  removed, or updated dependencies in `RESTART DUE` on macOS, and writes an optional `deps=` line
  to the Linux state file that `julia-update-server` reads as data. `julia-update-test.jl` and
  `lib/harness/jobsandbox.py` cover dependency upgrades, unchanged manifests, and state-line
  injection.
