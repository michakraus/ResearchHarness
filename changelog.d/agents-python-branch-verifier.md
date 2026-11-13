- **A new agent, `python-branch-verifier`, checks and fixes the branch of a Python repository
  before its pull request, or before its commit where the repository takes none.** A Python branch
  had no pre-PR gate: `python-builder` opened its pull request straight after the critic's PASS,
  and `part-builder` ran a verifier only in a Julia repository. The agent reads the gate from the
  repository's own hook, instructions and CI, and runs seven points on the diff only: correctness,
  the strict profile and its records, the idioms of the `python-code` rule, the tests that the
  diff reaches, `shellcheck` and `actionlint`, text that the diff makes stale anywhere in the
  repository, and history outside the changelog. `python-builder` starts it after a PASS, and
  `part-builder` starts it in a Python repository; `python-builder` takes the `agent` tool for it.
  The call graphs of the docs fill the rows of one depth from the last row, so that two callers
  share a row, which keeps the figure of `build-part` inside the doc column.
