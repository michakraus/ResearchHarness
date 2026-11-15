- **`harness ci-protection` writes with the user's own broad GitHub token where it is sealed.** It
  ran `gh` from the `PATH`, which is the wrapper `~/.local/bin/gh`, and that wrapper gives each
  call the organisation token of the repository's owner. That token can read a ruleset but has no
  *Administration: write*, so the dry run passed and every write of `--apply` failed with
  `Resource not accessible by personal access token`, and the sealed `github.age` was never used.
  Where `~/.config/research-harness/sealed/github.age` exists, the command now decrypts it once,
  as `ghx` does, with one Touch ID prompt, and runs every `gh` call with the real `gh`, the token
  as `GH_TOKEN`, without the variables that `ghx` removes, and with a new empty `GH_CONFIG_DIR`.
  Without the file, `gh` runs from the `PATH` as before.
