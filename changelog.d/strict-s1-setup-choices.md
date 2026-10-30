- **The profile takes a `[setup]` table of the machine's frontends, components and `develop`, and
  `harness install` installs only what it chooses.** `frontends` lists the layers to install, of
  `claude`, `opencode`, `omp` and `antigravity`; `components` lists `julia`, `rtk`, `jq`, `iterm`,
  `jobs` and `dotfiles`, of which `julia` makes `install` install the Julia environment and
  `doctor` check its packages; `develop` moves into the table. Without `[setup]`, every frontend
  and component is chosen, as before. A machine without OpenCode or Julia now installs with
  `frontends` and `components` that leave them out, where before the install stopped for a missing
  `~/.config/opencode` and needed Julia. An empty `frontends` installs no layer, and the Python
  environment is synced on every machine. A frontend's layer holds the same files whichever others
  are chosen; without `claude`, the files that OpenCode, oh-my-pi and Antigravity copy from the
  Claude Code layer come from its sources, and nothing below `~/.claude/` is read or written. An
  unknown name, a name given twice, a missing `frontends` or `components` and an unknown key of
  `[setup]` exit 2 with one line that names it. `harness doctor` reports a layer of an unchosen
  frontend that is still on disk as a WARN that names `[setup]` and the frontend, and removes
  nothing; its OpenCode directory check is SKIP without `opencode`, and its Julia packages SKIP
  without `julia`. A `develop` at the top level of the profile now stops every subcommand with
  exit 2: move the line `develop = true` into `[setup]`, which then also needs `frontends` and
  `components`, as `examples/profile.toml` shows.
