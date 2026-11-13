- **The battery's F2 runs under `claude`.** It started `claude -p` with the allow rule
  `Bash(echo *)`, which does not admit the probe's command `echo SR=$SANDBOX_RUNTIME AB=$AGENTBOX`
  with its `$` expansions; in `-p` mode Claude Code cannot ask, so it refused the command and F2
  was a MISMATCH that the sandbox did not cause. F2's rule is now the whole `Bash` tool; the
  command still runs under `srt`.
