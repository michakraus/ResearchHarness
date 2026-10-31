- **K123 leaves `KNOWN_ISSUES.md`: Antigravity refuses a tool call whose `PreToolUse` handler
  passes its `timeout`.** In Antigravity 2.28.2, a handler with `"timeout": 2` that slept 5 s was
  killed, and `run_command` of `echo timeout-probe` failed with `JSON hook
  "jsonhook__harness-guards_PreToolUse_0_0" failed: command failed: signal: killed`; the command did
  not run, and no dialog appeared. So the guard's handler, which carries no `|| exit 2`, fails
  closed at its 15 s timeout as it does on a non-zero exit, and a slow guard costs time but lets no
  call through.
