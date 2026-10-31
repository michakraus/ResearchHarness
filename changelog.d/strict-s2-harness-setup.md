- **`harness setup` sets up a machine in one run: the tools and frontends of `[setup]`, then
  `harness install --apply`, `core.hooksPath`, `harness trust --apply`, the jobs, the Kaimon
  token and `harness doctor`.** In a terminal it creates the profile from the example when there is
  none, asks for the frontends and components from numbered lists, writes `[setup]`, shows the
  plan and runs it after y/N; `--yes` reads `[setup]` and asks nothing, and `--dry-run` prints
  every command and changes nothing. macOS installs through Homebrew. Ubuntu installs each package
  whose apt candidate meets the minimum of `dependencies.md` in one `sudo apt-get install` line,
  and gitleaks, actionlint and RTK from the pinned releases of the new `setup/tools.toml`, each
  checked against its sha256. The vendor installers run unattended, the OpenCode one with
  `--no-modify-path` and only without `opencode` on the `PATH`, the juliaup one only without
  `juliaup`. A failed step, a missing `sudo`, no terminal without `--yes`, and an unknown system or
  architecture exit 2. The dotfiles kit's harness step now runs `harness setup --yes` in place of
  `harness install --apply`.
