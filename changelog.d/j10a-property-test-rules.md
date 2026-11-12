- **`rules/julia-tests.md` gives two rules for property-based tests.** A property of a search
  checks what its status claims, a minimum for a `SUCCESS` and the absence of a reachable decrease
  for a `STALLED` or a failure, against a reference the test computes itself; and a check whose
  shrunk counterexample is a false alarm runs again with that class filtered out, because
  Supposition reports one counterexample per check. A blind trial of generated properties on a
  line search missed one known defect on each point.
