- **`.githooks/pre-push` runs `scripts/dispatch-delta-test.jl` when a script that
  `dispatch-delta.jl` includes changes: `base-tree.jl`, `run-tests.jl` or `concrete-fields.jl`.** A
  changed path selects the test file of every row that names it, not only of the first.
