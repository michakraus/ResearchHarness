- **The ast-grep stage of the pre-commit hook no longer blocks a merge on the hits of the merged
  branch.** A hit of severity `error` blocks only on a line that the commit adds, and the added
  lines came from `git diff --cached` against HEAD alone. In a merge, every line that the other
  parent brings in counted as added: a merge of `main` into a topic branch was blocked on lines
  that `main` already held, and only `--no-verify` got it through. During a merge (`MERGE_HEAD`
  exists), a line now counts as added only when it is new against every parent, HEAD and each
  commit of `MERGE_HEAD`, an octopus merge's too; outside a merge nothing changes. No other stage
  reads added lines. `pre-commit-test.jl` gains two cases: a merge that brings in a hit from the
  merged branch passes, and a merge whose resolution adds a hit of its own is refused while the
  merged-in hit stays advisory. Both fail on the base commit: the first blocks, and the second
  reports the merged-in hit as blocking; the refusal of the new hit held before too. Roll out with
  `harness githooks --apply`.
