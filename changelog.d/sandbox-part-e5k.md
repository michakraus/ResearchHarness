- **Each frontend's `srt` settings file adds its own hosts to the template's `allowedDomains`.**
  A key `network` in each frontend table of `sandbox/policy.toml` lists the hosts that the
  frontend itself reaches, `oauth2.googleapis.com` for `antigravity`, where `agy` exchanges its
  login token, which srt refused before; and a `[frontend.<name>]` table of the overlay
  `network.toml` adds the user's own hosts, such as a model provider's API host, to that
  frontend's file alone. An entry is `host` or `host:port` of a closed grammar that srt takes, a
  deny entry without a port removes it, and an entry that reaches a `fetch` host, an unknown
  frontend, or a frontend table in `settings/network.toml` exits 2. The Claude Code settings do
  not change. `KNOWN_ISSUES.md` records K158: `deny` and `infrastructure` entries take forms that
  srt refuses.
