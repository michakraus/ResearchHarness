- **Claude Code signs in under `agentbox`.** It refreshes its sign-in token at
  `platform.claude.com`, which the `srt` proxy refused, so a start under `agentbox claude` stopped
  at "Claude Code couldn't verify your sign-in". `claude`'s `network` list in
  `sandbox/policy.toml` now holds that host, and only `claude`'s `srt` settings file gets it. Run
  `harness install --apply` to rewrite the files.
