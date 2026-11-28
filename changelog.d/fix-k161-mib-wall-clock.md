- **The probe's `[mib-rules]` case and the timed commands of 1 MiB of `probe:commands` no longer
  pass or fail on their seconds (K161).** The `[mib-rules]` case of `probe:antigravity` is decided
  by the guard's decision and its count of matcher calls, and the timed commands of 1 MiB of
  `probe:commands` by their decisions; each line still gives the seconds. `MIB_LIMIT`, 10 s, gives
  way to `MIB_HANG`, 120 s, a timeout that only stops a guard that hangs, so a loaded CI runner no
  longer turns these cases red for a correct guard.
