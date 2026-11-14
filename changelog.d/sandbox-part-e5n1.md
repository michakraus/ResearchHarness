- **`scripts/sealed.py` runs gh, glab and git with the user's own broad tokens, which only Touch
  ID decrypts.** One script with three names: `ghx` and `glabx` decrypt the secret `github` or
  `gitlab` from `~/.config/research-harness/sealed/<name>.age` with `age` and an `age-plugin-se`
  identity, and run the real gh (the first `gh` on the `PATH` that is no `#!` script, so not the
  agents' wrapper) or glab with the token in `GH_TOKEN` or `GITLAB_TOKEN`, an empty configuration
  directory, and the caller's other token and host variables removed. `git-credential-sealed
  <name> https://<host>` is a git credential helper that decrypts only for a `get` of its own host
  and never stores or erases. Each refusal exits 2 with one `sealed:` line that holds no token, and
  a decryption stops after 120 s. The user's shell gets broad forge access that a session, which
  runs gh, glab and git outside its sandbox, cannot read without the user's finger.
