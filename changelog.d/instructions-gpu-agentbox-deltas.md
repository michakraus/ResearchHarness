- **Under `agentbox`, OpenCode and oh-my-pi are told that the shell has no GPU.** Their deltas
  said only that there is no sandbox, and named neither the GPU nor a call to Kaimon; oh-my-pi ran
  Metal in a shell `julia` as its first call. `OPENCODE-DELTA.md` and `OMP-DELTA.md` now say that
  `agentbox` starts the frontend inside srt, which hides the GPU, and how that frontend calls
  Kaimon. The budget of a delta rises from 5,120 to 5,632 bytes to hold the paragraph: the two
  deltas were within 41 and 62 bytes of the old one.
