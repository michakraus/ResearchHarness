- **The Kaimon check refuses a session key that names no live session, and a key under a name
  that the tool does not take, on every Kaimon tool in all four frontends.** Most stale keys named
  a session that had died, and Kaimon drops `session` on `ex` and `ses` on the other tools without
  a word, so the call ran in whatever session Kaimon picked. The check reads the gate files in
  Kaimon's `sock/` directory at each call and keeps nothing; `manage_repl` keeps its `shutdown` of
  a gone session. The core instructions and *A warm session for probes* ask for one session per
  tree, reused, and send "disconnected", "No session matched" and a Kaimon that is not connected to
  a fresh process, as a start that timed out twice already was. Claude Code's guard matcher is now
  `mcp__kaimon__.*`.
