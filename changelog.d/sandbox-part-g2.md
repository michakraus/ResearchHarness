- **Claude Code runs the guard on every tool call, in one `PreToolUse` group with the matcher `*`.**
  The launcher check refuses a call only where the guard runs, and the four groups that ran it
  (`Bash`, the directory and worktree tools, the Kaimon tools and the web tools) left `Read`,
  `Edit`, `Write`, `Grep`, `Task` and every other tool unchecked in a session outside `agentbox`.
  The `Bash` group keeps `rtk hook claude` and `kaimon-note.py`; the guard's own table still picks
  the checks of each tool, so no tool loses a check, and each call starts the guard once. The
  safeguard pages and the OpenCode adapter page state the launcher check where they said that a
  frontend started without `agentbox` runs as without the harness, or that the guard lets every
  other tool pass; the planned row of a guard against a session with no sandbox is gone. Two probe
  cases of OpenCode and oh-my-pi no longer inherit `CLAUDE_CODE_ENTRYPOINT` and
  `CLAUDE_CONFIG_DIR` from the session that runs the probe. Run `harness install --apply` to install
  the template.
