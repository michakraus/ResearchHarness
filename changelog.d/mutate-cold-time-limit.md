- **`mutate.jl` stops a cold run of a mutant at a time limit.** Only a warm worker had one, so a
  mutant that loops forever in a cold run (the edit mode, `--list`, a list of 20 warm mutants or
  fewer, a run again cold of a survivor, or the smoke mutant) hung the whole run with no verdict,
  and MUTATE_TIME_LIMIT had no effect on it. A cold run now has MUTATE_TIME_LIMIT seconds, or
  600 s, the limit that a warm worker has before its first baseline, which loads the copy and runs
  every unit once as a cold run does; past it the mutant is UNKNOWN with "the time limit of N s".
  run-tests.jl runs in a process group of its own, and the limit kills the group with SIGKILL, so
  the julia that run-tests.jl starts dies with it, as do the cold runs that still run when
  mutate.jl exits; a kill of run-tests.jl alone left that julia spinning. The copy is removed as
  before. A new test set of `run-tests-test.jl` checks the verdict, the end of the spinning julia
  and the removed copy; with a kill of run-tests.jl alone, its check of the spinning julia fails.
