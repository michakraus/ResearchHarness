- **A new `PreToolUse` hook, `kaimon-note.py`, adds a note to a Bash call that runs a Julia
  probe in a fresh `julia` process, in Claude Code.** The note names `mcp__kaimon__ex`, `ping`,
  `start_session` and the live session keys, and the call runs as it is; a probe pays the process
  start and the package load on every call, which a warm Kaimon session pays once. OpenCode,
  oh-my-pi and Antigravity show no such note.
