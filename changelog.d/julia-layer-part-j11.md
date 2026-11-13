- **The Harness's pre-commit and pre-push hooks run `basedpyright` as CI does.** They pass
  `--pythonpath` with the environment's interpreter and `--baselinemode=lock`, so a commit or a
  push that removes baselined errors fails until `.basedpyright/baseline.json` is written again,
  where it passed before and CI's `ruff and basedpyright` job then failed. That job also runs
  `harness test strict` on its environment, and fails when the case that runs the real hook on
  such a commit skips.
