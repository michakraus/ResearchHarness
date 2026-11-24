- **`skills/build-part/edges.md` names the edge of a host-factor routing that moves the last bits of
  a solve.** Other parts' tests pin outcomes that read the same factor, an iteration bound and a
  set of cells that return SUCCESS, and only the full suite runs them, so two rounds failed on
  them after the kernel had no defect left. The new edge tells the planner to regenerate the
  reference first, run the full suite on that head in the same round, and search the tests for
  counts and cell sets that read the changed solver's outcomes before the critic.
