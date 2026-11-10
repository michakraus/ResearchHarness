- **A critic's copy of a worktree leaves out `.githooks`.** The `rsync` command in
  `skills/build-part/evidence.md` that copies a builder's worktree into a round directory gained
  `--exclude=.githooks`: the sandbox denies a write to `.githooks` under `~/Research`, so every
  copy of a package failed with exit 23. The header of `scripts/run-tests-test.jl` no longer says
  that a sandboxed process cannot create a `.git`; its fixtures need no history because the changed
  paths are given directly.
