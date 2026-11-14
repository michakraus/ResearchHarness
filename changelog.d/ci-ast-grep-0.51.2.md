- **CI installs ast-grep 0.51.2.** The `ast-grep` job and the `pre-commit-test.jl` matrix job of
  `julia.yml` pin the release 0.51.2 and the SHA-256 of its `app-x86_64-unknown-linux-gnu.zip`,
  so the rule tests in CI run the same ast-grep release as a local install of 0.51.2.
