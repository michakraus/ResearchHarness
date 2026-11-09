- **`dispatch-delta.jl` fails a branch that adds an abstract field.** Each side records the fields
  of the package's module tree whose types are not concrete up to type variables, by
  `concrete_field_violations` of `concrete-fields.jl`, and the comparison prints
  `FAIL: new abstract field: <type>.<field>::<field type>` for each field that the base lacks and
  `INFO: gone abstract field: …` for each that the head removes. A package with old violations can
  therefore run the check on every branch: the `dispatch` step of `gate.jl` and point 3 of
  `julia-branch-verifier` fail only on a field that the branch adds. The extension modules are not
  read, and `--api` compares no field. The entry B2c of the `build-part` skill's `edges.md`, on an
  abstract field that no critic sees, is deleted, because the check catches its class.
