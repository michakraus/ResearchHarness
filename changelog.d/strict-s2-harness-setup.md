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
  `juliaup`. A tool that is still below its minimum after its upgrade fails its step; for Julia,
  whose `juliaup update` keeps the default channel, the line names
  `juliaup add release && juliaup default release`. A failed step, a missing `sudo`, no terminal
  without `--yes`, a profile whose `[setup]` cannot be written in place, and an unknown system or
  architecture exit 2; a FAIL of the final `harness doctor` exits 1. The dotfiles kit's harness
  step now runs `harness setup --yes` in place of `harness install --apply`, and the kit's example
  machines use the Julia channel 1.13, the minimum of `dependencies.md`: a copy of the kit whose
  `julia_default` is below 1.13 must raise it, or `harness setup --yes` stops at Julia.
