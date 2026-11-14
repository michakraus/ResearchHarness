- **`dependents.jl row` classifies a cancelled step as inconclusive.** When a test job of
  `Dependents.yml` reaches its timeout, GitHub reports the running step as `cancelled`, and the
  row step refused the outcome with exit 2 and wrote no row. The row now reads *inconclusive*,
  names the cancelled step — for example "inconclusive: the test against the head was cancelled"
  — and exits 1, so that a person runs the job again. An excluded dependent stays *excluded*.
