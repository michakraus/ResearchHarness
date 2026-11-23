- **Under `agentbox`, OpenCode and oh-my-pi are told that the shell has no GPU.** Their deltas
  said only that there is no sandbox, and named neither the GPU nor a call to Kaimon; oh-my-pi ran
  Metal in a shell `julia` as its first call. `OPENCODE-DELTA.md` and `OMP-DELTA.md` now say that
  `agentbox` starts the frontend inside srt, which hides the GPU, and how that frontend calls
  Kaimon. The budget of a delta rises from 5,120 to 5,632 bytes to hold the paragraph: the two
  deltas were within 41 and 62 bytes of the old one.

- **The guard tables of OpenCode and oh-my-pi say how a nested Kaimon call reaches the Kaimon
  check.** No check changes. OpenCode's code mode runs each tool that `execute` calls through that
  tool's own `execute.before` event, under its id `kaimon_<tool>` (read in the source of OpenCode
  2.3.2). oh-my-pi's `bash` command `mcp__kaimon_<tool>` reaches the extension as a `tool_call` of
  that tool: a recorded session's `mcp__kaimon_ex` without `--ses` got the check's refusal.
