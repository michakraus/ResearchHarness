- **`run-tests-test.jl` no longer fails when a temporary package name holds `D6`.** The test set
  of a `--jobs` core run looked for the letters `D6` anywhere in the output, and the output starts
  with the random name of the fixture package, such as `jl_RD6qZf`. Its two assertions now look for
  a verdict line, `D6: …` or `No D6 verdict: …`, at the start of a line.
