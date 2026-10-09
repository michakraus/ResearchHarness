---
name: julia-surgical-fix
description: "Fix a reported problem in a Julia repository so that the diff holds that fix and nothing else, then check it again: the scope rule, the fix and re-verify loop, two passes at most, and the hard stops. Load it first, before any file is edited, whenever the request is to repair or act on something that a review, an audit, a critic or a CI run reported, even a one-line request. Typical words: findings, review comments, reviewer, flagged, requested changes, nit, address, resolve, repair, patch, follow-up commit, re-verify, re-run the check, keep the diff small, scope creep, tidy up. For what to check, use julia-package-audit; before quoting any number, julia-performance."
---

# Fixing a Julia change surgically

This is the *how to fix* layer. `julia-package-audit` is the *what to check* layer, and
`julia-performance` owns any number you quote. Your caller supplies the findings; this skill
supplies the discipline that keeps a fix from becoming a second change.

**Contents**

- [Scope — the rule that decides every edit](#scope--the-rule-that-decides-every-edit)
- [The fix → re-verify loop](#the-fix--re-verify-loop)
- [What stops the loop](#what-stops-the-loop)
- [Four endings that are not stops](#four-endings-that-are-not-stops)
- [Universal prohibitions](#universal-prohibitions)
- [Evidence](#evidence)

## Scope — the rule that decides every edit

> **Every edit you make lands inside a hunk the change already touched, or in a line the
> change itself made wrong. If you are opening a file the diff does not touch, you have stopped
> fixing this change and started a new one.**

- Do not improve adjacent code, comments or formatting. Do not refactor what is not broken. Match
  the surrounding style. Every changed line traces to a finding you listed.
- **Pre-existing defects adjacent to the diff are reported, not fixed.** They may well belong in
  this change — but that is the user's call. State the one-line fix in your report's
  *Pre-existing, adjacent* section and let the main session ask.
- **Never remove a symptom.** No widened tolerance, no `try` that swallows, no deleted testset, no
  `@inbounds` applied to make a number look better.
- After the last edit, run **JuliaFormatter on the files you wrote and no others** — through `ex`
  on the session, or the cold form; both are in `~/.claude/rules/julia-code.md`,
  which loads when you read a `.jl` file. This is
  load-bearing, not cosmetic: `pre-commit` blocks on `JuliaFormatter --check` over staged `.jl`, so
  an unformatted edit hands back a commit that cannot be made. Several repositories here are not
  formatted to their own config, so a wider run buries the change.

## The fix → re-verify loop

| what you fixed | what re-runs |
|:--|:--|
| a comment, a docstring word | nothing — re-read the hunk |
| any source line | `fatou lint` on that file · the `using <Package>` load test |
| a signature, a dispatch, a type annotation | Aqua `test_piracies` and `code_typed` on that method again, both through `ex` |
| anything that could change results | the one named `@testset` via `~/.julia/bin/testrunner` — **absolute path**. A session shell inherits an environment snapshot and need not carry `~/.julia/bin` |
| an allocation | re-measure in a **fresh process**, `--check-bounds=auto` |

A docstring edit needs one more step that no local check catches: only a **docs build** sees a
docstring detached from its definition, and `Pkg.test()` passes a build that is already broken.

## What stops the loop

Stop, all of these hard:

- **Two passes maximum.** If a fix produces a new finding and the second pass does not clear it,
  stop and report both states.
- At the first fix that would require touching a file outside the diff.
- When a fix needs a design decision — an API change, a new type parameter, a tolerance. Not yours.
- If the load test or the named testset goes green→red and an immediate revert does not restore
  it. Report the revert.
- **Never run `Pkg.test()`.** A 10–30 minute suite inside a fix loop is exactly the cost this must
  not have; that is `julia-test-runner`'s job and the main session's call.

You cannot check for a concurrent Julia job — `ps` and `pgrep` are blocked in the sandbox. State
the assumption; if you are told another job is running, the measured points go to *Not checked*
with that reason.

**Nothing else may change the tree while you work.** A plain `Edit` from another session is enough
to make your verdict describe a tree that no longer exists. If you find the working tree different
from how you left it, stop and report it rather than re-deriving.

## Four endings that are not stops

Your caller reads the turn you end as your report, and nothing resumes you. End your turn once,
with your report, when the work is done or a stop above applies. Until then, put a status note in
the same message as your next tool call.

Four endings look like a report and are not one:

- a summary that names the next step and does not take it;
- an offer to continue "unless you prefer otherwise";
- a list of decisions for your caller when none of them blocks the rest of the work;
- a stop because the turn is long or a milestone is done.

When your draft ends in one of these, delete it and take the next step. A decision that does block
goes into your report as a question, with your recommended answer, after the work that does not
depend on it.

## Universal prohibitions

Whatever your caller permits you to do with git, these hold:

`git stash` · `git checkout` / `switch` / `restore` · `Pkg.test()` · reformat any file you did not
write · edit a git hook or a workflow (canonical copies are in `Harness/githooks/`) · edit
`CHANGELOG.md`, which `changelog-scribe` owns · grant yourself an exemption for an unresolved
finding.

Your caller's own file states what it may do with `git add`, `git commit`, `git push` and `gh`.
That list is narrower than this one, never wider.

## Evidence

Every finding you report as fixed carries evidence **that was actually produced** — a command and
its output, or a `file:line` that was read. A fix you did not re-verify is reported as *applied,
not re-checked*, never as clean.

Say what was **not** checked. A fix report that silently skips a re-run reads as a clean bill of
health for it.
