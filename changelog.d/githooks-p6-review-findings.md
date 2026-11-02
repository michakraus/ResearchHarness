- **The Julia packages' hooks fix the findings of the second review of their rollout.** After an
  interrupt, `pre-push` waits until no process of the suite's group is left, and kills a process
  that still runs at the grace time also after the suite itself has ended; it starts the suite
  with the interrupt deferred, so no interrupt finds the suite started and not yet watched. The
  time box of `pre-commit` closes its SIGKILL timer before it returns. Both programs count a
  `Project.toml` as a package only with a `name` and a `uuid`, and refuse a name that is not a
  Julia identifier before they build code from it, so a name can no longer run code of its own.
  The lint stage passes the staged paths after `--`, and reports a `fatou` exit with no finding
  line as a failure of `fatou` with its exit status, not as a count of findings. A failed load
  report starts at its `ERROR:` line. The refusals for a `Project.toml` or a `.jl` file that does
  not parse also print the error's location. K131 to K135 record what the review found and this
  change does not fix: no cap on the output that the time box captures, no bound for a process
  in uninterruptible I/O, a suite that tests the working tree and not the pushed commit, a
  fallback suite that ignores `test/Project.toml`, and a time-out at the moment the program ends
  that can still signal its freed group ID.
