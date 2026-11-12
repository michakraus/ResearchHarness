- **OpenCode and oh-my-pi read Kaimon's token under `agentbox`.** Both reach Kaimon with the
  bearer in `~/.config/kaimon/auth-token`, which their `srt` settings files denied, so Kaimon
  answered 401. The token is now in the `own` list of `opencode` and of `omp` in
  `sandbox/policy.toml`: their files allow its read, and the write deny `~/.config` above it keeps
  it read-only. A command of either frontend can thus run Julia through Kaimon's `ex`, under
  Kaimon's profile, which allows outbound connections only to the loopback address and Kaimon's
  own sockets. The files of `claude` and `antigravity` still deny its read.
