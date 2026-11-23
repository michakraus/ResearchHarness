- **A builder ends each Bash call within 170 seconds and runs each test or probe under
  `timeout -k 10 160`.** Claude Code 2.1.328 moves a Bash call of a background sub-agent to the
  background after 180 s, whatever its `timeout`, and the builder cannot report while that job
  runs. Julia answers SIGTERM with its exit path, which a bare `timeout` waits for without limit;
  `-k 10` sends SIGKILL. `julia-builder`, `python-builder` and `part-builder` say so, and so do
  `julia-critic`, `python-critic`, `part-critic` and `python-branch-verifier`, which run in the
  background too.
  `python-builder` runs the parts that `harness test --changed <base> --list` names, a few per
  call, and leaves the full suite of the Harness, which takes longer than one call, to its
  dispatcher. A `timeout 295` run of a `julia-builder` hung so at 0 % CPU for 7 h 33 m.
- **`build-part` checks a builder that waits on its own background work at once.** It reads a bare
  `ps -eo pid,ppid,etime,%cpu,command`, the worktree and the job's logs, and stops the builder with
  `TaskStop` when the job is idle, rather than wait for a "finished" notice that may never come.
