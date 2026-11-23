- **A GPU probe has no fresh-process fallback in `build-part` either.** The skill's *A warm
  session for probes* and the Kaimon check's refusal of a stale key sent a builder or a critic
  whose Kaimon session failed to `julia --startup-file=no <probe file>`, with no exception. A
  sandboxed shell has no GPU, so such a probe measures nothing on the device: both now say to
  report the failure and leave the device run to the caller, as the core rule does since its GPU
  exception.
