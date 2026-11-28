- **The Antigravity cases of commands of 1 MiB and the `probe_timeout` case of
  `probe-agentbox.py` no longer pass or fail on their seconds (K224, K163).** `[agy-work]` is
  decided by its decision and its counts of reads and spawns, and the `[agy-guard]` commands of
  many words and of 1 MiB by their decision and a bound of their matcher calls, as `[mib-rules]`
  is; each line still gives the seconds, and `MIB_HANG` only stops a guard that hangs. In
  `probe_timeout`, F1's stub sleeps 300 s and holds the probe's pipes, so a probe that does not
  kill its process group never ends, and `--timeout 10` leaves every other stub ample time; the
  timed `ask` of `probe_words` takes 10 s too. K224 is the entry that #396 recorded under K222,
  an ID that an earlier fix had already closed.
