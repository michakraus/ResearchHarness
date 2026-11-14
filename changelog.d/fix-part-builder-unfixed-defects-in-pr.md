- **A defect that `part-builder` leaves unfixed reaches the pull-request body in a repository
  with no `KNOWN_ISSUES.md`.** Such a defect went only to the caller under *Reported, not fixed*,
  and each new builder saw only the last builder's report, so rows of earlier rounds were lost.
  A later-round builder copies the handoff note's *Reported, not fixed* rows into its own report,
  and the finish lists them under `## Reported, not fixed` in the body. `build-part` and
  `build-reviewed` pass the passing critic's *Other defects* with `Round: finish`, which they did
  not pass before; `part-builder` records them, and the finish input lines of `julia-builder` and
  `python-builder` name them.
