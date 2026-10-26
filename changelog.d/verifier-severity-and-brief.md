- **`julia-branch-verifier` stops only on a `blocker`, a `bug` or a `correctness-risk`, and leaves
  a choice its prompt states as deliberate.** A `quality` or `nit` finding is fixed or reported,
  and never makes the verdict `stop and ask`. When the prompt names a wording, a pattern or a rule
  as the author's choice, the verifier reports a disagreement instead of editing the line. In
  five pre-PR runs, one verdict stopped on a blank line in a changelog list, and two fixes undid a
  choice the caller had specified; each caller reverted the fix.
