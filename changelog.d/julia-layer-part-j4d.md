- **Two ast-grep rules for a `catch` in Julia: `catch-binds-type-name` blocks,
  `catch-variable-unused` only warns.** `catch MethodError` binds a variable named `MethodError`
  and catches every exception; `catch-binds-type-name` finds a `catch` whose variable is `Error`,
  `Exception`, or a capitalised name that ends in one of them, and its severity is `error`, so the
  pre-commit stage refuses a hit on an added line. `catch-variable-unused` finds a `catch e` whose
  body never names `e` and calls neither `rethrow` nor `throw`; its severity is `warning`. The
  two rules never hit one clause, and both scan `src/`, `ext/` and `test/`. Over `src/`, `ext/`
  and `test/` of the 37 packages, `catch-binds-type-name` hits 2 places and
  `catch-variable-unused` none. Each rule has a rule test, `rule-tests/scope/` gains `catch.jl`,
  and the `ast-grep` job of `julia.yml` checks the files and the severity of each rule's hits.
