- **The new launcher `claudex` starts Claude Code with its own sandbox in `~/.config/claudex`.**
  It runs `claude` with `CLAUDE_CONFIG_DIR=~/.config/claudex`, outside `agentbox`, where Claude
  Code's sandbox wraps the `Bash` commands only. On each start it links `agents`, `commands`,
  `hooks`, `instructions`, `rules`, `skills`, `CLAUDE.md`, `RTK.md`, `statusline-command.sh` and
  `projects` there to the same names in `~/.claude`, after it has checked every name. It refuses,
  with exit 2 and nothing started or linked, inside `agentbox`, without the settings file, without
  `claude` on the `PATH`, with a `--settings` of the caller's, and when a name is not a link to its
  target or the target is missing. `harness install --apply` installs it at
  `~/.local/bin/claudex` where `[setup]` chooses `claude`.
