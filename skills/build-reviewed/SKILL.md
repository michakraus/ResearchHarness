---
name: build-reviewed
model: large
description: "Build one part of a decomposed task file whose tier cell is reviewed: one part-builder, one blind part-critic, at most one fix round by the same builder, and the dispatching session's own read before the finish. Triggers on: build this reviewed part, take the next reviewed part, run part T, build the small part. The dispatching session decides the questions inside the part and takes real decisions to the user; no advisor and no arbitrator run. A FAIL that the fix round does not close goes to the user. Use the build-part skill for a part of tier build, and the plan-parts skill to choose a part's tier."
---

# A reviewed part: one builder, one critic, one fix round

A part of tier `reviewed` is a small code change with a fast gate: a script, a tool, a check, a
change to a test layout. `Environment/Notes/Builder-Critic-Loop.md`, *Three loop levels*, holds the
reasons. One builder holds the whole part. One fresh critic judges it blind, once. This session
reads the result before the finish.

**Run this in a session on the large model.** This session decides the questions inside the part
and reads the diff, so it is a reviewer, not only a dispatcher.

## 1 · Choose the part and check its spec

```bash
cd ~/Research && awk -f Harness/scripts/parts-table.awk "Tasks/<file>.md"
```

Take the part the user names, or the first part of tier `reviewed` that is `open`, has no unmerged
`blocked by` part, and collides with no part `in progress`. Check every `PR #NN in review` cell
with `gh pr view` first, as `build-part` says.

Read the part's sections and the file's §V and §L by line range. **The spec needs a *Done when*
whose clauses a command can check, and §V or §L must name the gate.** A part in `Packages/` or
`Experiments/` also needs *Decided at the edges* and *Tests catch*:
`python3 Harness/scripts/spec-gate.py "Tasks/<file>.md" <part>`. Write what is missing into the
section yourself, marked `(dispatcher, <date>)`, and commit the task file. An edge that changes a
public answer or picks between designs is the user's: ask, and go on with the next part.

Set the state cell to `in progress`.

## 2 · Spawn the builder

Spawn `part-builder`; its frontmatter sets its tier. Pass the task file, the part, its
`PART` row and the `COLLISION` rows that name it, verbatim. Read `git remote get-url origin` first:
outside the user's own organisations, a push or a pull request needs the user's approval.

- **A part in `Packages/` or `Experiments/`**: `cd` into the repository as a Bash call of its own,
  then spawn with `isolation: "worktree"`.
- **A part that commits to `main`** (the plan's §L says so): spawn it in a worktree the same way,
  or without isolation from the repository, as §L says.

**Keep the builder's agentId.** You message this builder through the whole part. Before each
`SendMessage`, `cd` into its directory as a Bash call of its own.

**A report whose *Question for the dispatcher* is not `none` holds the critic back.** Decide it from
the part's sections and the evidence, and write the decision into the section as
`**Decided (dispatcher, <date>):** <decision>`. Commit the task file, and send the builder the
section and the line. Where the question changes a public answer, picks between designs, or weakens
the *Done when*, ask the user instead, and set the state to `waiting for the user — <question>`.

A run under *Left for the dispatcher* goes to `julia-test-runner` (no `model` parameter), or you run
it yourself when it is short. Send the builder its verdict line and its failures.

## 3 · One critic

When the builder returns `ready for critic`, spawn **one** `part-critic`, without isolation. Pass the task file, the part, the builder's directory, the
base and the head. **Never pass the builder's report.** For a part whose gate runs longer than 5
minutes, spawn `julia-test-runner` on the head in the same message.

The critic's report is finished when it holds `Verdict:` and its evidence table. Otherwise spawn a
new critic once.

## 4 · Read the verdict

- **PASS, and the gate green** — go to 5.
- **FAIL** — `SendMessage` the builder the critic's *Blocking defects* and *Other defects*
  verbatim, with the gate's failures. Add no instruction of your own; a decision goes into the
  section first, as in 2. When the builder returns `ready for review`, **check the fix yourself**:
  run each reproducer of the critic, run the gate, and read `git diff <judged head>..HEAD`. Each
  blocking defect is closed, and the fix diff adds nothing outside it.
  - All closed — go to 5.
  - **One is open, or the fix breaks a clause** — stop. Set the state to
    `waiting for the user — <the open defect>`, and report it with your recommendation: one more
    fix round, a change of design, a narrower clause, or the full loop of `build-part` from the
    base. No second critic runs without the user's decision.

**A blocking defect whose cause is the harness** — a tool, the environment, a moved `main` — is
not the part's. Repair it, and run the critic again.

## 5 · Your read, then the finish

Read `git diff <base>...HEAD` once against the *Done when* and the critic's evidence table. Your
read is the last check, not a second critic: a doubt you can show with a command goes to the
builder as a blocking defect, under 4. Then `SendMessage` the builder `Round: finish`. It
finishes as the plan's §L says: a pull request in `Packages/` and `Experiments/`, else a push to
`main`. After a push to a repository with CI, background `gh run watch <id> --exit-status -R
<owner>/<repo>`.

Write the state cell from the builder's report, and add one line to the part's section:
`**The loop:**` the rounds, each decision, and each defect the critic found, with its class. For a
defect class that is not in `~/.claude/skills/build-part/edges.md`, add one line to that file's
source, `~/Research/Harness/skills/build-part/edges.md`.

## What this skill does not do

It does not merge, and it runs no advisor, no arbitrator and no second critic without the user.
It does not build a part of tier `build` or `decision`, and it does not change a part's tier: that
is `plan-parts` and the user.
