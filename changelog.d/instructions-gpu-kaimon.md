- **The core rule's fallback to a fresh process excludes GPU code.** When Kaimon fails, a
  sandboxed shell is no route for GPU code, because it has no GPU: the agent reports the failure
  and stops. Under `agentbox`, OpenCode took this fallback for Metal code when `ping` listed only
  other agents' sessions, and ran it in a shell `julia` inside srt.

- **Under `agentbox`, OpenCode and oh-my-pi are told that the shell has no GPU.** Their deltas
  said only that there is no sandbox, and named neither the GPU nor Kaimon; oh-my-pi ran Metal in
  a shell `julia` as its first call. `OPENCODE-DELTA.md` and `OMP-DELTA.md` now say that `agentbox`
  starts the frontend inside srt, which hides the GPU, and how that frontend calls Kaimon. The
  budget of a delta rises from 5,120 to 5,632 bytes to hold the paragraph: each delta was within
  62 and 41 bytes of the old one.
