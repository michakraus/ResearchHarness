- **`mutate.jl` shows its progress in a redirected log.** A run prints a `start:` line first (the
  mode, the mutants, the jobs and the units), and the list modes print a `progress:` line when the
  run of a mutant ends, warm and cold, with the verdict, the name and the seconds since the start.
  Every line is flushed: a redirected stdout is a buffered `IOStream`, so a `--warm` run sent to a
  log with `> log 2>&1` left it at 0 bytes until the end, and a healthy run and a hung one looked
  the same. The verdict lines, the totals line and the `result:` line do not change.
- **`skills/build-part/edges.md` names one more edge of a numerical method.** A test of a guard's
  inclusive bound that runs a real solve at a huge budget, such as `maxit = typemax(Int32)`, never
  fails fast under a regression that stops convergence.
