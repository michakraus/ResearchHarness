- **The core rule's fallback to a fresh process excludes GPU code.** When Kaimon fails, a
  sandboxed shell is no route for GPU code, because it has no GPU: the agent reports the failure
  and stops. Under `agentbox`, OpenCode took this fallback for Metal code when `ping` listed only
  other agents' sessions, and ran it in a shell `julia` inside srt.
