# Workflow scripts

Canonical, version-controlled `Workflow` scripts of Claude Code.

## Why they live here and not in `~/.claude/workflows/`

`~/.claude/workflows/` became writable with settings round two on 2026-09-01, but it is **not under
version control** — so a script there has no diff, no changelog and no review. That is the reason
these live here; the earlier reason, that the directory could not be written at all, no longer
applies. `scriptPath` accepts any path, so nothing is lost:

```
Workflow({scriptPath: '~/Research/Harness/agent-workflows/repo-drift.js',
          args: ['~/Research/Packages/Example', '~/Research/Packages/Other']})
```

Only the `{name: '…'}` shorthand needs the other directory. Round two granted the write; the
shorthand is a convenience, and these scripts do not depend on it.

Keeping them here also means a workflow arrives in a **diff** — which matters, because a workflow
script composes prompts for sub-agents and is therefore instruction-bearing code.

## What is here

| script | does | writes? |
|:--|:--|:--|
| `repo-drift.js` | audits repositories against `../githooks/` — hooks, the five workflows, `core.hooksPath`, `.gitignore`, `CHANGELOG.md` | **no** — read-only by construction |

## House rules for a script in this directory

- **`meta` is a pure literal.** No variables, calls or interpolation. `meta.phases` titles must
  match the `phase()` calls exactly, by string.
- **Say what was not checked.** Return the names of items that produced no result, not a count and
  never nothing. A `null` from `parallel` or `pipeline` is silent, and a fan-out that reports 36 of
  37 as "all clear" is the failure these scripts exist to avoid.
- **Read-only unless it must write**, and if it writes, `isolation: 'worktree'` — more than one task
  may be running in this tree.
- **Never fan out `Pkg.test()`, a load probe, or anything that precompiles.** Shared depot,
  divergent `check_bounds`, and failures that look exactly like real bugs. Serialise or partition by
  disjoint dependency sets, and `log()` the partition.
- **Set `model` per call.** Untiered agents inherit `opus[1m]` at high effort; a stage that diffs two
  files does not need that. Cheap for extraction, expensive for judgement.
- **A verify stage must be able to disagree.** Prompt it to overturn the finding, with uncertainty
  resolving against the finding — not "confirm this".
- No `Date.now()`, `Math.random()` or argless `new Date()` — they throw, because they would break
  resume.

## Grading a script

A workflow's output is a claim, and it gets checked like any other. `repo-drift.js` has ground
truth: `../githooks/verify-workflows.jl`. Run both and compare.

`harness workflows` (`../lib/harness/githooks.py`) iterates the repositories of `Packages/` and
`Experiments/` alike, and adds `TagBot.yml` only for a package. It copies the templates and
removes only the files of its `RETIRED` list, so a `TagBot.yml` left in an experiment stays there.
`verify-workflows.jl` asserts that no experiment holds a `TagBot.yml`, and reports such a file.
`repo-drift.js` compares `TagBot.yml` in every repository, so it reports the file as missing in
an experiment: that row is expected.

A script whose output has never been compared against something independent is an unverified script,
which is the same standard this tree applies to a mathematical claim.
