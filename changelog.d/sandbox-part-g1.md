- **The guard refuses every call of a Claude Code, OpenCode or oh-my-pi session that runs outside
  `agentbox` on macOS.** Outside the launcher no sandbox holds a frontend's file tools, hooks and
  MCP servers, and OpenCode and oh-my-pi have none at all. The new launcher check of
  `hooks/guard/launcher.py` lists `~/.ssh`, which the sandbox of `agentbox` denies: a listing that
  fails with `PermissionError` passes, one that fails otherwise is refused because the guard cannot
  tell, and one that succeeds is refused with a reason that asks the agent to have the session
  started again with `agentbox <frontend>`. Claude Code's own sandbox counts in the Code tab of the
  desktop app, with `sandbox.enabled` on. Antigravity is not checked, and nothing is refused on
  Linux. The hook probe runs the guard in fixture homes whose `.ssh` it cannot list.
