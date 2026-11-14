- **The finish of `julia-builder` and `python-builder` records a passing critic's other defects
  that the branch does not cause.** Both builders receive the passing critic's *Other defects* with
  `Round: finish`, but acted only on a text-only defect that the branch causes, so the rest reached
  no `KNOWN_ISSUES.md`. They record the rest as a fix round does, before the reread of the branch's
  text. The finish of `julia-builder` also commits its own text changes before the verifier runs,
  so a new `KNOWN_ISSUES.md` entry reaches `## Known issues added` in the pull-request body.
