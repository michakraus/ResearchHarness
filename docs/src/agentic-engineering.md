# Agentic software engineering

Research software must be correct, and a wrong result that nobody notices is expensive. A coding
agent writes code fast, but it also judges its own work too kindly, and a long test run fills its
context. The harness therefore divides the work of a change among several agents. A plan states
what done means before the work starts, one agent builds, another agent judges, and the long runs
go to agents of their own.

## Sub-agents

A session can start a sub-agent for one job. The sub-agent works in a context of its own and
returns one short report, so the output of its job never fills the context of the session. The
harness gives sub-agents three kinds of jobs:

- **A long job**, such as a test suite: [`julia-test-runner`](components/agents.md#julia-test-runner)
  runs it and returns pass or fail per testset, with the failures.
- **A wide job**, such as a change across many repositories: one sub-agent for each repository, and
  one verdict for each.
- **A bounded diagnosis**, such as a package that does not load:
  [`julia-load-doctor`](components/agents.md#julia-load-doctor) returns the cause and the smallest
  fix.

A sub-agent costs a new context, so a session starts one only where a fresh context or a smaller
model does the work better. [`reader`](components/agents.md#reader) and
[`worker`](components/agents.md#worker) load no `CLAUDE.md`, so they start with a small context.

## From a plan to a pull request

A change that needs more than a few edits goes through a plan:

1. **Plan the parts.** [`plan-parts`](components/skills.md#plan-parts) splits the task into parts,
   and each part is one pull request. Each part gets a spec: its *Done when*, which states the
   acceptance criteria as checks; the edge cases decided in advance; the mutants that its tests
   must catch; and its files. A collision map shows which parts touch the same files, and so which
   parts can run at the same time. The plan is a task file.
2. **Choose the tier of each part.** A `decision` part waits for you. A `build` part runs the full
   builder-critic loop of [`build-part`](components/skills.md#build-part). A `reviewed` part is
   small, with a fast gate, and runs [`build-reviewed`](components/skills.md#build-reviewed): one
   builder and one critic. A `direct` part is a mechanical change whose every check is a command, such as
   a rename across many repositories; the session or a workflow makes it, with no critic.
3. **Build.** A builder writes the tests first, then the code, in a worktree of its own. For each
   guard, branch and comparison of its change, it writes a mutant: a copy of the code with one
   deliberate defect, which a good test must catch.
4. **Judge.** A critic that has not seen the builder's report or reasoning judges the result
   against the *Done when*. It runs the checks itself, runs each named mutant, and probes the
   edges of each clause. A FAIL goes back to a new builder, which fixes the blocking defects.
5. **Open the pull request.** After a PASS, a builder opens the pull request. In `build-part`, a
   question inside the loop goes to the [`advisor`](components/agents.md#advisor), and a loop that
   does not converge goes to the [`arbitrator`](components/agents.md#arbitrator), not to you.

The critic is blind for a reason: a context that wrote the code does not judge it well. A fresh
context, with no knowledge of the builder's reasons, finds more defects.

## One worktree for each part

Each part is built in a worktree: a second checkout of the repository on its own branch, below
`~/Research/.worktrees/`. The main checkout stays on `main`, and two parts can be built at the same
time in two worktrees. Each new builder and critic of the same part works on the same worktree.
[The research tree](research-tree.md#temporary-work) says where the worktrees are.

## Pull requests

Three agents work on a pull request of a Julia package:

- [`julia-branch-verifier`](components/agents.md#julia-branch-verifier) checks and fixes the branch
  before the pull request opens, on the diff only.
- [`julia-pr-reviewer`](components/agents.md#julia-pr-reviewer) reviews the pull request blind,
  posts the review, and reads the CI jobs.
- [`julia-pr-shepherd`](components/agents.md#julia-pr-shepherd) has the review done, fixes the
  findings and pushes the fix.

No agent merges a pull request that its own session opened. The command
[`merge-pr`](components/commands.md#merge-pr) merges only a pull request that its session did not
open or push to, once the required checks are green.

## Models and efforts

An agent names a [tier](concepts.md#tier): `large`, `medium` or `small`. The model tables of the
profile give the model of each tier for each frontend. A builder and a critic need a large model; a
test run needs only a small one, so the large contexts do not wait on it. An agent can also name an
[effort](concepts.md#effort). The figures below show the model and the effort of each agent.

## Who spawns whom

An agent can start another agent. This page calls this a *spawn*: the first agent gives a task
to a new agent, the new agent works in a context of its own, and it returns one report. Some
skills spawn agents too. A skill runs in the session that loads it, so the session does the spawn.

Each figure below is a call graph: a box is an agent or a skill, and an arrow goes from the caller
to the agent that it spawns. The text on an arrow says when or why the caller spawns the agent.

### How to read a figure

Each box shows three facts:

- **The name**, in bold. A blue box is an agent of `agents/`. A yellow box is a skill of
  `skills/`.
- **The model.** The source names a model tier, `large`, `medium` or `small`, and the `[claude]` table
  of `examples/models.toml` gives the model of each tier: `opus`, `sonnet` and `haiku`. Your own
  `models.toml` changes these models (see [profile.md](profile.md)). A source with no `model:`
  runs on the model of its caller, and its box says "the caller's model". A skill runs in the
  session that loads it, on the session's model, so a skill box says "the session's model".
- **The effort**, from the source's `effort:`. A source with no `effort:` runs at the effort of
  the session, and its box says "the session's effort". Where a caller sets a different effort for
  one spawn, the arrow says so: "at high effort".

The figures show Claude Code. OpenCode and oh-my-pi can run a council: copies of an agent on
other models, each copy a seat. The figures do not draw the councils.

The arrows come from one file, `docs/figures/calls.toml`. It has one entry for each spawn, with
the `file:line` of the instruction that spawns the agent. `harness test` checks each entry against the
sources, and the docs build draws the figures from it. So a figure changes when an agent changes.

### The builder-critic loop: `build-part`

```calls build-part
title: The calls of build-part
desc: The build-part skill spawns julia-builder or python-builder, julia-critic or python-critic in round 1 at high effort and in each verify round at its own effort, julia-test-runner, advisor and arbitrator. julia-builder spawns julia-branch-verifier and changelog-scribe.
```

A part is one pull request of a plan. You start `build-part` in your session when a part is ready
to build. The skill does not write code. It spawns a builder to build the part, and then a new
critic to judge the result: `julia-builder` and `julia-critic` for a Julia part,
`python-builder` and `python-critic` for a Python part, and `part-builder` and `part-critic` in a
repository with neither a `Project.toml` nor a `pyproject.toml`. In the first critic round, two critics judge at high
effort, and each one sees only the branch, never the builder's report. In each later verify
round, which checks only the fix, the critic sees only the fix. Beside each
critic, `julia-test-runner` runs the full test suite of a Julia part; for any other part the
skill's session runs the repository's own suite in the background. A question inside the loop goes to the
`advisor`, and a loop that does not converge goes to the `arbitrator`. Before the pull request of
a Julia part, `julia-builder` spawns `julia-branch-verifier`, and it can spawn `changelog-scribe`
for a fix of the CHANGELOG.

The work is split because a context that wrote the code does not judge it well. A fresh critic
with no knowledge of the builder's reasons finds more defects. A long test run goes to an agent
on a small model, so that the large contexts of the builder and the critic do not wait on it.

<WalkThrough name="build-part" />

*From a task to a pull request with build-part.* The `plan-parts` skill writes the parts table,
the list of the parts of a plan, and `build-part` runs one part. In the first critic round, two
critics judge the work at high effort beside a run of
the full suite. After a FAIL, a new builder fixes the work, and one critic judges the fix. The
second FAIL goes to the arbitrator. After a PASS, a new builder finishes the part and opens the
pull request. The figure shows the default models of Claude Code. Your `models.toml` can add a
council of critics on other models for OpenCode and oh-my-pi.

### A smaller loop: `build-reviewed`

```calls build-reviewed
title: The calls of build-reviewed
desc: The build-reviewed skill spawns part-builder, part-critic and julia-test-runner. part-builder spawns julia-branch-verifier.
```

A part of tier `reviewed` is small, with a fast gate. You start `build-reviewed` in a session on
the large model. It spawns one `part-builder`, and a new one for each later round. When the builder
is ready, the skill spawns one `part-critic`, which judges the work once, without seeing the
builder's report. A run longer
than five minutes goes to `julia-test-runner`. Before the pull request, the builder spawns
`julia-branch-verifier`.

The split is smaller here: one builder, one critic. Your session reads the result before the
finish, the last builder round, which opens the pull request. So your session is the second
reviewer.

<WalkThrough name="build-reviewed" />

*From a task to a pull request with build-reviewed.* The skill spawns one `part-builder`, and one
`part-critic` judges its work. After a FAIL, a new builder fixes the findings, and your session
checks the fix before it tells the builder to finish the part. With a PASS, your session reads
the result, and then it tells the builder to finish the part.

### From review to green CI: `julia-pr-shepherd`

```calls julia-pr-shepherd
title: The calls of julia-pr-shepherd
desc: The julia-pr-shepherd agent spawns julia-pr-reviewer, changelog-scribe and ci-triage.
```

You spawn `julia-pr-shepherd` with a pull request of a Julia package. It does not review the pull
request itself: it spawns `julia-pr-reviewer`, which posts the review. Then the shepherd fixes the
findings. When the fix changes behaviour, it spawns `changelog-scribe` for the CHANGELOG entry.
When CI is red in several jobs, it spawns `ci-triage` to separate the real failures from the known
ones.

The review comes from a context that has not decided how to fix anything. So the findings are
not shaped by the fix.

### Every spawn

```calls
title: Every spawn
desc: Every edge of calls.toml: the build-part, build-reviewed, plan-parts and julia-structure skills, and the julia-builder, part-builder and julia-pr-shepherd agents, with each agent that they spawn.
```

This figure shows every entry of `calls.toml`. It adds two skills: `plan-parts` sends each part's
spec to a `reader` that measures its facts, and `julia-structure` sends a claim that nothing uses
a name to `exhaustive-auditor`. An agent that is not in this figure is spawned
only from your session. Only the agents with the tool `agent` can spawn another agent:
`julia-builder`, `part-builder` and `julia-pr-shepherd`. Each spawn costs a new context, so an
agent spawns another only where a fresh context or a smaller model does the work better.
