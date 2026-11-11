# Tasks

A session forgets everything when it ends, but a change of any size takes more than one session. A
task file carries the work from one session to the next. It holds the goal, the plan, the
decisions and the state of each part, so that a new session starts from the file and not from your
memory. This page describes a task file and its life.

## A task file

A task file is one Markdown file in the directory `Tasks/` of the
[research tree](../research-tree.md), one file for each task. Its name is the task in the
imperative, such as `Add the adaptive step to the integrator package.md`. It opens with a
frontmatter that says where the task stands:

```markdown
---
status: wip
created: 2026-11-02
started: 2026-11-03
---

# Add the adaptive step to the integrator package
```

| `status` | the task |
|:--|:--|
| `incoming` | is new, and you have not seen it |
| `next` | continues work that you have decided on |
| `wip` | has a session working on it |
| `backlog` | waits; nobody has decided that it goes on |
| `done` | meets its done condition; the file moves into `Tasks/Archive/` |

A session that starts a task writes `wip` and `started:`; a session that stops before the end
writes `next` or `backlog`. The board `Tasks/Board.base` groups the task files by `status`, and
rule 14 of [`harness wiki-lint`](../harness-command.md#wiki-lint) checks the schema: an unknown
status, a missing date, and a done task outside `Archive/`.

A task file is an instruction from you, but not a blank cheque. "Work through this task file"
lets a session do the work that the file describes. It does not let the session do an
irreversible step that the file only mentions, such as a merge, a release or a forced push, and it
does not let the session make the done condition easier.

## What a task file holds

| section | holds | written by |
|:--|:--|:--|
| the goal and **Done when** | what the task is for, and the condition that ends it | you and your session |
| **Parts** | the parts table: one row per pull request | [`plan-parts`](../components/skills.md#plan-parts) |
| **File collisions** | which files each part touches | `plan-parts` |
| **§V** and **§L** | the plan's own rules for building and verifying, and its changes to the loop | `plan-parts` |
| the part sections, or a spec file per part | the spec of each part | `plan-parts`, then the loop's decisions |
| findings, checkboxes, measurements | what the sessions learned, with the dead ends | every session |

**Findings stay.** A session checks off an item; it does not delete it. The history of what was
tried keeps the next session off a path that failed.

**Decisions carry their author and date.** A decision has one of these forms, so a reader sees who
decided and how sure the decision is:

```markdown
**Decided (the user, 2026-11-09):** the check recurses into type parameters.
**Recommendation (advisor, 2026-11-09, medium confidence):** allow `Union{Nothing, X}`.
**Decided (arbitrator, 2026-11-10, high):** redesign: refuse what the parser cannot read.
```

A recommendation waits for you; a decision binds the next round. Each decision goes into the task
file before the next round starts, so the builder and the critic read the same text.

## The parts table

A part is one pull request: one branch, one worktree, one *Done when*. A part is the right size when
one person can review its diff in one sitting and say yes or no. The parts table is the
machine-readable half of the plan:

```markdown
| part | repository | sections | what it is | tier | state |
|:--|:--|:--|:--|:--|:--|
| **A** | `Pendulum` | spec, §V, §L | The adaptive step controller. A numerical method. | build | merged — PR #12 |
| **B** | `Pendulum` | §4, §V, §L | Which norm the error estimate takes. Changes a public answer. | decision | waiting for the user |
| **C** | `Pendulum` | spec, §V, §L | The docs page and the example. Small, with a fast gate. | reviewed | blocked by A |
```

- **`sections`** names what the builder and the critic read. A builder never reads the whole task
  file: the script `spec-bundle.py` copies the named sections, §V and §L into one *spec bundle*,
  and the loop passes only that file. A rule that is not in the bundle does not reach the builder.
- **`what it is`** says in one or two sentences what the part does and why it has its tier.
- **`tier`** is `decision`, `build`, `reviewed` or `direct`; [the builder-critic
  loop](loop.md#the-tier-of-a-part) says what each one means. The planner gives a part its tier
  only after its edges are decided, because an edge left open makes the part a `decision`.
- **`state`** is `open`, `in progress`, `waiting for the user`, `PR #NN in review`, `merged`,
  `declined`, or `blocked by <part>`. The loop writes it, and nothing else of the file.

The script `parts-table.awk` prints the table and the collision map of a task file, so that a
session can choose the next part without reading the rest.

## The collision map

Two parts that change the same lines of one file cannot be built at the same time. The collision
map lists the files of each part, so you see which parts can run in parallel:

```markdown
| file | parts |
|:--|:--|
| `src/step.jl` | A |
| `docs/src/adaptive.md` | C |
| `CHANGELOG.md` | A, C; added lines only, the later branch rebases |
```

Added lines do not serialise: when two parts only add their own lines to a shared file, such as a
`CHANGELOG.md` entry, the later branch rebases. A map with no collision is still written, because
a stated absence is a result.

## The life of a task

1. **Discuss.** You and your session agree on the goal and the done condition. The session reads
   the code, measures what it can, and writes the findings into a new task file.
2. **Plan.** `plan-parts` splits the work into parts, writes the parts table, the collision map,
   §V, §L and a spec for each part. A `reader` agent checks the facts of each spec against the
   code ([Specs and gates](specs-and-gates.md#the-premise-check)).
3. **Decide.** You answer the questions of the `decision` parts. Each answer goes into the file
   with your name and the date.
4. **Build.** `build-part` or `build-reviewed` builds the next open part, and writes its state.
   Parts with no collision can run at the same time.
5. **Merge.** You merge each pull request. No agent merges a pull request that its own session
   opened ([Review and pull requests](review.md#who-merges)).
6. **Close.** When the done condition holds, the session writes `status: done` and moves the file
   into `Tasks/Archive/`.

[Example: a feature in a Julia package](example.md) follows one task through these steps.

**In another language.** A task file is plain Markdown and the parts table works for any
repository. The loop picks its builder by the language of the part:
[the builder-critic loop](loop.md#the-full-loop-build-part) names the pairs.
