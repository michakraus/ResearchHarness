- **The critics and `python-branch-verifier` end each Bash call within 170 seconds and run each
  test or probe under `timeout -k 10 160`, as the builders do.** `julia-critic`, `python-critic`,
  `part-critic` and `python-branch-verifier` run as background sub-agents too, so Claude Code's
  180 s move of a Bash call to the background reaches them. `python-branch-verifier` runs the
  parts that `harness test --changed <base> --list` names, a few per call.
- **`julia-builder` and `julia-critic` name the stack overflow as the case in which Julia does not
  end on SIGTERM.** A script that includes itself overflows Julia's stack; Julia then prints the
  `signal 15` line and does not exit, and only `timeout -k` ends it.
