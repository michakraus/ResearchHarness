- **`dispatch-delta.jl` reports a stale explicit import that a branch adds.** Each side records the
  stale imports of its own modules from ExplicitImports' `improper_explicit_imports`, and the
  comparison prints `FAIL: new stale import: <module>: <name> at <file>:<line>` for each one that
  the base lacks, or `INFO: new stale import, used in <dirs>: …` where `test/`, `docs/`,
  `scripts/` or `ext/` names it as `<module>.<name>`, and `INFO: gone stale import: …` for each that
  the head removes. A module that ExplicitImports cannot analyse is an `UNKNOWN: stale imports:`
  line, and a missing ExplicitImports gives no verdict. `--api` records none. Point 3 of
  `julia-branch-verifier` says what each line asks: remove the import, and change a caller that
  reaches the name through it. Old stale imports of a package do not fail a branch.
