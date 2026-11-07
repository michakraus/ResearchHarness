- **A main Claude Code session hands off at 400k tokens of context, and a Kaimon `ex` call waits
  up to 240 s before it becomes a job.** Each model call reads the whole context again: in the
  two weeks to 2026-11-01, desktop main sessions cost $1,744 of $4,932 input at a mean context of
  336k, and the 29 that reached 500k cost $1,152. The new hook `context-handoff.py` runs on
  `UserPromptSubmit` and `PostToolUse`, reads the size of the last model call from the transcript,
  and at 400k or more tells the session to finish the step, record its state and propose a new
  session; a tool call gets the line once per 100k. In the same window Antigravity agents called
  `check_eval` 11,840 times, 95 % of them as a model turn of their own at a median gap of 8 s,
  because a job id leaves an agent no way to wait. `kaimon.plist` and `kaimon.service` set
  `KAIMON_GATE_PROMOTE_AFTER=240`, which would have removed 61 % of those polls; oh-my-pi's
  request timeout for Kaimon rises from 120 s to 300 s to stay above it. `evidence.md` and
  `ANTIGRAVITY-DELTA.md` say to collect a job once, after other work, and to hand a longer run to
  the caller. Install with `harness install --apply`, then load the rendered Kaimon unit again.
