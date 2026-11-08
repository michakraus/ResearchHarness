- **`latex-verifier` runs Julia checks in Kaimon, and `math-verify` says where a check runs.** The
  agent gains Kaimon's `ex`, `check_eval`, `ping`, `start_session`, `manage_repl`,
  `search_methods` and `type_info`, so it iterates in a warm session instead of a new process for
  each probe. A new section of `math-verify`, which the agent loads, holds the rules: iterate in
  Kaimon, take every exit status and check count from `julia --startup-file=no`, run a script
  that loads `PythonCall` or `SymPyPythonCall` only in a fresh process, and reuse one Kaimon
  session per tree.
