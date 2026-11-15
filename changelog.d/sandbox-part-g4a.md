- **The guard passes a Claude Code session that `claudex` starts.** Such a session runs with
  Claude Code's own sandbox outside `agentbox`, and the launcher check of
  `hooks/guard/launcher.py` refused it. It now passes when `CLAUDE_CONFIG_DIR` is an absolute path
  that resolves to `~/.config/claudex` and `settings.json` there holds `sandbox.enabled` as
  `true`. A plain `claude` session stays refused, and its refusal names both `agentbox claude` and
  `claudex`. OpenCode and oh-my-pi get no such exception. The hook probe tests the exception in
  fixture homes.
