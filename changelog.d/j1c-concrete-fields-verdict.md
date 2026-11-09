- **`scripts/concrete-fields.jl` takes its verdict from a result file of the load process, not from
  its exit code (K149).** An `exit(10)`, `exit(11)` or `exit(13)` in a package's own code, such as
  in its `__init__`, gave PASS, FAIL or UNKNOWN with no verdict line; it now gives the `UNKNOWN`
  line and exit 3, as every other exit and a signal do. Package code that writes the result file
  itself is not guarded.
