- **`transcripts.jl` reports the Python loop agents, and `part-builder`'s finish commits the
  verifier's paths before `gh pr create`.** `LOOP_TYPES` gains `python-builder`, `python-critic`
  and `python-branch-verifier`, so their runs go to `reports.jsonl` beside the Julia loop agents'.
  `sample.jl` cuts a `python-critic` report at the length of a Julia critic's. The finish of
  `part-builder` named the verifier and then the pull request with no commit between them, so the
  verifier's fixes could stay uncommitted in the worktree.
