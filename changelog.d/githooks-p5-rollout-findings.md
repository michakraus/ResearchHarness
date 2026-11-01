- **The Julia packages' hooks no longer hang past their time limits, and check what the rollout
  review found unchecked.** The lint stage and the load test of `pre-commit` run in a process
  group of their own: at the time limit the hook kills the group and returns without waiting for
  the output, so a `fatou` launcher whose child holds the output no longer holds the commit
  (K108, K129). The load test has a limit of 600 s, and also runs for a commit that only deletes a
  `.jl` file. One file that does not parse no longer lists every staged file as not formatted. A
  staged `.jl` symlink to a missing file or to a directory is refused with one line instead of a
  stack trace. Both programs read the package name with `TOML.parsefile`, so an indented or
  single-quoted `name` counts, and a `Project.toml` that does not parse is refused. Both
  launchers decide without `julia` whether a check must run, so a `julia` that cannot start no
  longer blocks a commit with no `.jl` file or a push of a topic branch. `pre-push` kills a suite
  that still runs 30 s after an interrupt, keeps waiting through a second interrupt, and names
  both `main` and `master` when it refuses a push. K130 records that the formatting stage has no
  time limit.
