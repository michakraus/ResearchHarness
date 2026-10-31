- **`harness setup` no longer stops at `harness trust --apply` on a new machine (K126).** The step
  runs only with the frontend `claude`, and only once Claude Code has written `~/.claude.json` at
  its first start; before that, the run prints the step by hand ("start claude once, then run
  harness trust --apply") and goes on to the jobs, the Kaimon token and `harness doctor`. A machine
  whose `[setup]` does not choose `claude` has no trust step. The harness still writes no
  `~/.claude.json` that Claude Code has not made, and the setup pages drop the `echo {}` way past
  the stop.
