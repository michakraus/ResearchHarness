- **`git-hook-triage` is retired, as superseded.** In about ten weeks of transcripts, hooks blocked
  297 commits and 73 pushes, and no session or sub-agent called the agent. The hook output names
  the failed stage and its fix, so a session reads it in one step and a hand-off costs more. The
  silence of a push to `main` and the `git ls-remote` check are in the tree instructions, which
  every session loads, and a failed load test goes to `julia-load-doctor`. `ci-triage`,
  `julia-load-doctor` and the agents page no longer point to it. `harness install` reports each
  installed copy as `EXTRA` and leaves it; remove those by hand.
