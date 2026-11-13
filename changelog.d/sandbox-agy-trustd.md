- **`agy` works under `agentbox`.** `agy` is a Go program, which checks a TLS certificate through
  the macOS service `com.apple.trustd.agent`; `srt` refused the lookup, so every request failed
  with `x509: OSStatus -26276` and `agy` asked for a new login at each start. `antigravity`'s
  `mach_lookup` in `sandbox/policy.toml` now names that service, and its `network` adds
  `daily-cloudcode-pa.googleapis.com` (eligibility and model) and `www.googleapis.com` (the
  account) beside `oauth2.googleapis.com`. A command of `agy` can reach the trust service too,
  which `srt` names a possible path for data out of the sandbox. Run `harness install --apply` to
  rewrite the files.
