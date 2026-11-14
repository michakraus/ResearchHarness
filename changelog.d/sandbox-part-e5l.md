- **`gh` works under `agentbox` in every frontend, and no frontend can read the dotfiles token.**
  `gh` is a Go program, which checks a TLS certificate through the macOS service
  `com.apple.trustd.agent`; `srt` refused the lookup in `claude`, `opencode` and `omp`, so every
  request of `gh` failed with `x509: OSStatus -26276`. Each frontend's `mach_lookup` in
  `sandbox/policy.toml` now names that service, which `srt` names a possible path for data out of
  the sandbox. The settings template denies reads of `~/.config/dotfiles-credentials` in
  `permissions.deny`, `denyRead` and `credentials.files`, and the guard list of OpenCode, oh-my-pi
  and Antigravity denies it, so each frontend's `srt` file denies it too. The probe battery
  `scripts/probe-agentbox.py` runs its `srt` probes with `agentbox`'s `GH_CONFIG_DIR`,
  `GLAB_CONFIG_DIR` (empty directories of its own for each frontend) and `GIT_TERMINAL_PROMPT=0`,
  so N9 shows `gh` as a frontend runs it. Run `harness install --apply` to rewrite the files.
