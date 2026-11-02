- **The Julia packages' hooks fix the findings of the review of their combined rollout.** After
  an interrupt, `pre-push` waits at most 10 s after the SIGKILL of the suite's group; a group
  that still has a process then ends the hook with exit status 130 and one line that names the
  group ID and says that processes of the suite are left, so a process that SIGKILL cannot end no
  longer holds the push for ever. A further interrupt anywhere in that wait is caught. The time
  box of `pre-commit` measures its grace after the SIGTERM on the monotonic clock, so a step of
  the wall clock cannot end it early. For a `Project.toml` with a `name` and no `uuid`,
  `pre-commit` prints one line that no load test runs, and why. A file that does not parse is
  refused with the parser's reason after its location. K134 now also covers a project with a
  `name` and no `uuid`, and K135 the SIGKILL timers and the group check on a group ID after the
  suite is reaped.
