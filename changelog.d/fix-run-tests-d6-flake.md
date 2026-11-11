- **`run-tests-test.jl` no longer fails when a temporary package name holds `D6`.** Four of its
  assertions looked for `D6` or `D6:` anywhere in the output, and the output starts with the random
  name of the fixture package, such as `jl_RD6qZf`. They now look for a verdict line, `D6: …` or
  `No D6 verdict: …`, at the start of a line.
