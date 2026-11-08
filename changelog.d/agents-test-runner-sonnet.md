- **`julia-test-runner` and `changelog-scribe` run on the `medium` tier, Sonnet, not on `small`,
  Haiku.** On Haiku the runner reported totals that its own rows did not sum to, among them 3102
  for a base whose rows sum to 2902, and each such report cost the dispatcher a check and sometimes
  a run on Opus. The scribe drafted an entry that named four files that do not exist. Both agents
  read and report, which needs no Opus, so `medium` is the tier between the two. `build-part` still
  forbids a `model` override when it spawns the runner. With no agent of `agents/` left on the
  small tier, the Antigravity selftest renders a scratch agent of that tier.
