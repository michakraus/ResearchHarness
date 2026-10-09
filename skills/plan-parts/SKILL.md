---
name: plan-parts
model: large
description: "Plan work as parts that are each one pull request, and write each part's spec so that the builder-critic loop can build it and judge it: the parts table, the collision map, a tier per part, and each part's Done when, edge-case decisions, named mutants and files, plus the plan's own §V and §L rules. Use when the user wants a task planned or broken into pull requests, wants to know what can run in parallel, asks which parts need a decision first, or wants a part's done-condition sharpened for a critic. Two entry paths — before a plan exists, to shape it; and on a finished plan, to add the table and the specs. Use the build-part skill to run the loop, julia-branch-verifier to check a part's branch, and the julia-pr-shepherd agent to take its pull request to green."
---

# Planning parts for the builder-critic loop

A **part** is one pull request. One branch, one worktree, one *Done when*. The parts table is the
plan's machine-readable half: a later session reads one row and builds it without reading the rest
of the file. Each part's own section is its **spec**: what `julia-builder` builds to and what
`julia-critic` judges against, blind.

Two entry paths, same output.

| path | you have | do |
|:--|:--|:--|
| **forward** | a discussion, no file yet | write the table and the specs as the plan forms, not after |
| **backward** | a finished task file | read it, add the table, the specs, §V and §L, change nothing else |

**Contents**

- [1 · A part is one pull request](#1--a-part-is-one-pull-request)
- [2 · The parts table, first section after the done-condition](#2--the-parts-table-first-section-after-the-done-condition)
- [3 · The collision map, before the split is fixed](#3--the-collision-map-before-the-split-is-fixed)
- [4 · A tier cell per part, from a stated reason](#4--a-tier-cell-per-part-from-a-stated-reason)
- [5 · What must not be split](#5--what-must-not-be-split)
- [6 · Each part's section is its spec](#6--each-parts-section-is-its-spec)
- [7 · The plan's §V and §L hold only what the plan adds](#7--the-plans-v-and-l-hold-only-what-the-plan-adds)
- [What this skill does not do](#what-this-skill-does-not-do)
- [Run this on the capable model](#run-this-on-the-capable-model)
- [Grading a table you produced](#grading-a-table-you-produced)

## 1 · A part is one pull request

One sentence describes it. A part that needs two sentences is two parts.

The test is the reviewer: **a part is right-sized when one person can review its diff in one
sitting and say yes or no.** Not "how long will this take" — a mechanical rename across forty files
is one part; two design decisions in one file are two.

**One part per finding is not a decomposition.** Group by theme — what a reviewer judges together —
not by numbered item. Findings that share a cause, a file set or a kind of fix belong in one part.

> **The check: if your part count is within two of your finding count, start again.** Twenty
> findings become about seven parts, not eighteen. Over-fragmentation is the common failure and it
> is worse than a part that is slightly too large: every extra part is another branch, another pull
> request, another review, and another row in the collision map.

**A part that changes ten or more source files (`src/`, `ext/`), or four or more kinds of work,
is two parts.** The kinds are source, tests, docs, scripts, CI and the project files; `CHANGELOG.md`
and `KNOWN_ISSUES.md` do not count. In the production loops such a part takes a median of three
critic rounds and a builder context near 480 k tokens, against one round and about 100 k for a part
of three source files or fewer. Split it where a reviewer judges apart: the interface, the
algorithm behind it, the migration of its callers. A mechanical change is exempt, as above.

**Do not split one part into steps with a critic loop each.** Each step pays a full loop, and no
critic judges the part as a whole.

**The exception is a change too wide to land green at once.** A rename or a signature change whose
blast radius reaches thousands of call sites breaks the suite the moment it starts, so no single
part can both make the change and pass CI. Sequence it as **expand → migrate → contract**:

| step | the part | state |
|:--|:--|:--|
| **expand** | add the new form beside the old one. Nothing breaks | open |
| **migrate** | move the call sites over in batches sized by repository or directory, one part each | `blocked by` the expand |
| **contract** | delete the old form once no caller remains | `blocked by` every migrate part |

Each migrate part stays green on its own, because the old form still exists. Where even a batch
cannot stay green alone, keep the sequence and give the batches a shared integration branch that a
final verify part is `blocked by`; green is promised there and nowhere earlier.

## 2 · The parts table, first section after the done-condition

```markdown
## Parts

A session given a part reads this table, §V, §L and that part's sections. It does not read the
whole file.

| part | repository | sections | what it is | tier | state |
|:--|:--|:--|:--|:--|:--|
| **A** | `Example` | §1–§4, §V, §L | Wrong answers and unreachable API. No design decision. | build | open |
| **B** | `Example` | §5–§7, §V, §L | What `periodicity` returns. Changes the public answer. | decision | open |
| **C** | `ExampleTools` | §11, §V, §L | The accessor loops. Mechanical. | build | blocked by B |
```

`state` is one of `open · in progress · waiting for the user · PR #NN in review · merged ·
declined`.

**Every `sections` cell ends in `§V, §L`.** `julia-builder` and `julia-critic` read only the
sections a cell names, so a rule in any other section does not reach them.

**The table does not replace the checkboxes.** Checkboxes record findings; the table records units
of work. A file carries both.

## 3 · The collision map, before the split is fixed

List which files each part touches. Two parts that share a file **cannot be built in parallel**,
whatever they cost to run.

```markdown
### File collisions

| file | parts |
|:--|:--|
| `src/utils.jl` | B, D, E |
| `src/Package.jl` | D, E, F |
```

This is the table that decides whether a plan can be worked in parallel at all. Write it even when
the answer is "no collisions" — a stated absence is a result, and a missing map reads as one.

**Added lines do not serialise.** Where parts only add or remove their own lines in a shared file —
an `include`, an `export` or a `using` in the module file, a `CHANGELOG.md` entry, a `docs/` page
entry, a `[deps]` or `[compat]` line — the later branch rebases. Say so in the file's row, and do
not let that file order the parts. A file whose shared lines a part changes is a real collision.

Work it out from the sections, not from memory. Where the parts are already written, `grep` the
file names out of them rather than guessing.

## 4 · A tier cell per part, from a stated reason

**The tiers name roles, not parts.** Each role always runs at its own tier:

| tier | role | who |
|:--|:--|:--|
| **`opus-high`** | decisions and planning | the user's own session, on opus at high effort. This skill runs here. A question inside a build part's loop goes to the `advisor` agent, at the same tier |
| **`opus-medium`** | the builder and the critic | `julia-builder`, `julia-critic`; `part-builder`, `part-critic` |

The planner, the builder, the critic and the advisor never run on sonnet or haiku. The dispatcher's
session and the suite runner are not tiers of a part, and `build-part` sets them.
`Environment/Notes/Loop-Benchmark.md` holds the measurements behind these tiers; a change to a
tier follows a measurement there, not this skill.

**A part's `tier` cell says whether the user decides first, and how the part is built.** It holds
one of four values:

| cell | the part is | signals | then |
|:--|:--|:--|:--|
| **`decision`** | invention or a decision | changes a public answer, picks between designs, resolves a dispute, touches an API others depend on, **or leaves an edge case of §6 undecided** | the user decides at `opus-high` and records the decisions in the part's section; then the part gets one of the three tiers below |
| **`build`** | decided, with a large search space | a numerical method; a guard, a parser or a renderer that predicts what another tool reads; a security boundary | the full loop of `build-part`: two blind critics, then verify rounds |
| **`reviewed`** | decided, small, with a fast gate | a script, a tool or a check of a few files whose gate runs in minutes | `build-reviewed`: one builder, one blind critic, one fix round |
| **`direct`** | mechanical, with a deterministic oracle | a move, a rename, a one-line change rolled out to many repositories; every clause is a command such as a diff, a count or a listing | the main session, or a workflow; no critic |

`Environment/Notes/Builder-Critic-Loop.md`, *Three loop levels*, holds the evidence. When unsure
between two of the three build tiers, take the heavier one.

**Write the reason in the `what it is` cell for every part, and never assign one value
throughout.** A cell with no reason beside it collapses to all-`decision` and stops carrying
information. *"Nothing here needs a design decision"* and *"Large, mechanical, low risk"* are
assignments in prose, and they survive a rename.

**Assign a part's tier after its *Decided at the edges* is written, never before.** An edge left
undecided makes the part `decision` (§6). On the backward path, a tier written from the finding
alone reads `build` for a part whose edges nobody has decided yet.

**When uncertain, assign `decision`** — but uncertainty is a verdict you reach on one part, not a
default you apply to the table. A design decision left to an agent produces a plausible wrong
answer that looks like work. The `advisor` decides only the smaller questions inside a `build`
part's loop, writes each into the part's section, and the user reviews each in the pull request.

**The `tier` cell is read by machine.** The `build-part` skill reads it, and treats an empty or
unrecognised value as `decision`. Write `decision`, `build`, `reviewed` or `direct` in that cell,
and put the reason beside it in `what it is`.

## 5 · What must not be split

A part whose *Done when* depends on another part merging is **not independent**. Say so in `state`
as `blocked by <part>`. Do not pretend a dependency away to make the table look parallel.

Three dependencies are easy to miss:

- a part that adds the function another part calls;
- a part that changes a `[compat]` bound another part's tests need;
- a part whose measurement another part's decision rests on.

## 6 · Each part's section is its spec

The part's own section opens with its spec, in this order. Keep it out of the table: the table
stays scannable, and a done-condition that fits in a cell is usually too weak.

1. **Done when** — the critic's benchmark. **Every clause is checkable by a command**: a test that
   fails before the change, a `grep` that finds nothing, a number with its tolerance and the
   reason for it, a figure compared with a named value. "Works", "is clean", "to tolerance" and
   "matches the old code" give a critic nothing to fail. Where a clause needs a number you do not
   have, ask the user for it. `~/.claude/skills/build-part/evidence.md` is how the builder and the
   critic split the clauses and fill the evidence table; write for that. **A clause with *every*,
   *each* or *one … per* names its finite set** — the repositories of a table, the example of a
   section, the decided edges, the named mutants — because the critic blocks only on a failure in
   that set.
2. **Decided at the edges** — what the code does at each edge the part reaches, from the list for
   its kind in `~/.claude/skills/build-part/edges.md`: for a numerical method `NaN` and `Inf`, a
   subnormal or zero input, an empty or one-element case, a zero-width interval, the scale
   extremes, the other precision, a device array. One line per edge, with the answer. **An edge
   left open is found by a critic, one per round, as a new blocking defect**, and the loop does not
   converge until someone decides it. An edge you cannot decide makes the part `decision`. A part
   whose code predicts what another tool reads or does also takes the edges of that kind, and its
   design first.
3. **Tests catch** — for each clause that a test covers, the mutant that the test must catch:
   *"deleting the `η` update in `backtracking.jl` makes the Eisenstat–Walker test fail"*. The
   builder runs it, and the critic runs it again, with `mutate.jl`. Without a named mutant, a test
   that passes with the feature deleted passes the loop.
4. **Files** — the files the part creates or changes, which is its row of the collision map.
5. **Not in this part** — what a builder might reasonably add and must not, with the part that
   owns it.
6. **Traps**, where the plan knows one: a failure that a previous attempt met, with its cause.

**A `file:line` in a spec names the commit it was read at**, such as "on `origin/main` `1344dab`".
Lines move when other parts merge, and a spec that cites a line without its commit gives the
builder no way to tell a moved line from a wrong premise.

A spec is not a workflow. Do not prescribe the order of the builder's work: its steps are in
`julia-builder`, and a longer brief improves the first build more than the final result.

## 7 · The plan's §V and §L hold only what the plan adds

The generic build steps are in `julia-builder`, the judging rules in `julia-critic`, the evidence
table and its rules in `build-part/evidence.md`, and the loop in the `build-part` skill. **Copy
none of them into the plan.** Write §V and §L from `plan-sections.md` beside this skill, after the
collision map: the plan's own rules, one sentence each, and the extra sections the critic reads.

## What this skill does not do

**It does not run anything.** It produces a table, the specs, §V and §L. The `build-part` skill
runs the loop, and so can a human or a `/loop`. A planning step that also spawns builders is an
agent graph, and the merge gate stops it one step later anyway.

**It does not merge, and it does not plan a merge.** Merging is the user's, every time.

**It does not rewrite the findings.** On the backward path, add the table, the collision map, the
specs, §V and §L. Leave the prose, the checkboxes and the recorded dead ends exactly as they are —
the history of what was tried is the point.

**It does not split a task that is already one pull request.** Say so and stop. A one-row table is
overhead. The one part still gets its spec, §V and §L.

## Run this on the capable model

The frontmatter runs this skill on opus. A cheaper model splits a file into one part per finding,
and costs more tokens doing it.

The measurements behind this skill's rules, the graded set, and how to remove the answer from it
are in `Environment/Notes/Builder-Critic-Loop.md`, *Planning parts*.

## Grading a table you produced

Six failure shapes to check for in your own output:

- **parts that mirror the section numbering.** One part per finding is a renumbering.
- **a tier column with one value throughout.** It has stopped carrying information.
- **an empty collision map on a file that obviously has collisions**, or one so broad that it
  declares nothing parallel. Re-derive it from the sections before believing either.
- **a `sections` cell without `§V, §L`.** That part's builder and critic never read the plan rules.
- **a *Done when* that a critic cannot fail.** Split it into clauses and ask of each: which command
  shows it false?
- **a spec with no edge decided and no mutant named.** Its critic loop will find the edges for you,
  one round at a time.
