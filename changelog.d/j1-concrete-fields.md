- **`scripts/concrete-fields.jl <package>` lists the fields of a package's structs whose types are
  not concrete up to type variables.** It loads the package in a fresh process with
  `--project=<package>` and prints one `<Type path>.<field>::<field type>` line per violation and a
  verdict: exit 0 on PASS, 1 on FAIL, 2 on bad arguments, 3 where the package does not load. A
  field passes as a type variable, a non-abstract type whose parameters all pass, or exactly
  `Union{Nothing, X}` or `Union{Missing, X}` with `X` passing; `Function`, `Any`, a bare or partly
  applied `UnionAll`, every other `Union` and a type such as `Vector{Real}` are flagged. The function
  `concrete_field_violations(M::Module)` gives the same check in process. It reads the struct types
  that the root module and its submodules define, not `ext/`, and takes no exception list.
  `scripts/concrete-fields-test.jl` holds its tests, and the pre-push hook and CI run them.
