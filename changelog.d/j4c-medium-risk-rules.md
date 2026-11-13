- **Three more ast-grep rules for Julia: `test-throws-bare-type` blocks, `unspecialised-callable`
  and `float-accumulator` only warn.** `test-throws-bare-type` finds `@test_throws` with a bare
  exception type under `test/`, which passes when a later guard or a library call raises the same
  type; its severity is `error`, so the pre-commit stage refuses a hit on an added line.
  `unspecialised-callable` finds a parameter typed `::Function` or `::Base.Callable` that the
  method only passes on or stores, with no call of it in the definition, and `float-accumulator`
  an accumulator started from a `Float64` literal; both have the severity `warning`, so the stage
  prints their hits and never blocks. Over `src/` and `ext/` of the 37 packages,
  `unspecialised-callable` hits 50 places, of which 2 are false hits. Each rule has a rule test,
  `rule-tests/scope/` gains `throws.jl`, and the `ast-grep` job of `julia.yml` checks that a scan
  with `test-throws-bare-type` hits only `test/throws.jl`, with the severity `error`. The entries
  of `build-part/edges.md` on a bare exception type and on `::Base.Callable`, and the accumulator
  sentence of `rules/julia-code.md`, name their rule.
