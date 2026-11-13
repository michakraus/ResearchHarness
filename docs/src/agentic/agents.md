# Agents and their roles

One session of a [coding agent](../concepts.md#coding-agent) can write a change, run its tests
and review it. It does all three badly at once: its context fills with test output, and it judges
its own code too kindly. The harness therefore gives each kind of work to an agent of its own. This
page names the roles, says why each one is separate, and shows which agent starts which.
[The builder-critic loop](loop.md) shows the roles at work on one change.

## Sub-agents

A session can start a [sub-agent](../concepts.md#sub-agent) for one job. The sub-agent works in a
context of its own and returns one short report, so the output of its job never fills the context
of the session. The harness gives sub-agents three kinds of jobs:

- **A long job**, such as a test suite:
  [`julia-test-runner`](../components/agents.md#julia-test-runner) runs it and returns pass or
  fail per testset, with the failures.
- **A wide job**, such as a change across many repositories: one sub-agent for each repository,
  and one verdict for each.
- **A bounded diagnosis**, such as a package that does not load:
  [`julia-load-doctor`](../components/agents.md#julia-load-doctor) returns the cause and the
  smallest fix.

A sub-agent costs a new context, so a session starts one only where a fresh context or a smaller
model does the work better. [`reader`](../components/agents.md#reader) and
[`worker`](../components/agents.md#worker) load no `CLAUDE.md`, so they start with a small
context. A reader changes nothing; a worker does one fully specified change.

## The roles

| role | agents | what it does | why it is separate |
|:--|:--|:--|:--|
| planner | your session, with the skill [`plan-parts`](../components/skills.md#plan-parts) | splits a task into parts and writes the spec of each part | the plan is the user's decision; a builder does not choose its own goal |
| builder | `julia-builder`, `python-builder`, `part-builder` | writes the tests, then the code, in a worktree; runs the gate | it holds the design in its context |
| critic | `julia-critic`, `python-critic`, `part-critic` | judges the branch against the spec, blind | a context that wrote the code does not judge it well |
| advisor | `advisor` | decides one question inside the loop, in place of the user | the builder stops less often, and the critic stays blind |
| arbitrator | `arbitrator` | rules on a loop that does not converge | a third round of the same approach seldom closes |
| test runner | `julia-test-runner` | runs a long suite and returns the verdict | the large contexts do not wait on a slow suite |
| verifier | `julia-branch-verifier`, `python-branch-verifier` | checks and fixes the diff of a branch before its pull request, or before its commit where the repository takes none | a fixed list of checks, on the diff only |
| reviewer | `julia-pr-reviewer` | reviews a pull request and posts the review | the review comes from a context that has not decided how to fix anything |
| shepherd | `julia-pr-shepherd` | has the review done, fixes the findings and pushes | it takes a pull request from review to green CI |
| specialists | `julia-load-doctor`, `julia-perf-analyst`, `ci-triage`, `changelog-scribe`, `exhaustive-auditor`, `literature-scout`, `latex-verifier`, `editor`, `writer` | one bounded kind of work each | each returns a short, fixed verdict |

[Agents](../components/agents.md) describes each agent: its tools, its model and its report.

**The builder and the critic never share a context.** The critic gets the spec, the branch and
the base, and never the builder's report or reasoning. A FAIL goes to a new builder, and the next
round to a new critic. So each judgement comes from a context that has no stake in the code.

**A question goes to an agent, not to you, while the loop runs.** The advisor decides a question
that the spec leaves open, and says how sure it is. When the decision is not reversible inside the
pull request, the loop parks the part and asks you. The arbitrator reads the whole loop and picks
one move from a fixed list, such as a redesign or a fresh build. Both edit nothing.

## Models and efforts

An agent names a [tier](../concepts.md#tier): `large`, `medium` or `small`. The model tables of
the [profile](../concepts.md#profile) give the model of each tier for each frontend. A builder and
a critic need a large model; a test run needs only a medium one, so the large contexts do not wait
on it. An agent can also name an [effort](../concepts.md#effort). The figures below show the model
and the effort of each agent.

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
- **The model.** The source names a model tier, `large`, `medium` or `small`, and the `[claude]`
  table of `examples/models.toml` gives the model of each tier: `opus`, `sonnet` and `haiku`.
  Your own `models.toml` changes these models (see [Adapting the profile](../profile.md)). A
  source with no `model:` runs on the model of its caller, and its box says "the caller's model".
  A skill runs in the session that loads it, on the session's model, so a skill box says "the
  session's model".
- **The effort**, from the source's `effort:`. A source with no `effort:` runs at the effort of
  the session, and its box says "the session's effort". Where a caller sets a different effort for
  one spawn, the arrow says so: "at high effort".

The figures show Claude Code. OpenCode and oh-my-pi can run a council: copies of an agent on
other models, each copy a seat. The figures do not draw the councils.

The arrows come from one file, `docs/figures/calls.toml`. It has one entry for each spawn, with
the `file:line` of the instruction that spawns the agent. `harness test` checks each entry against
the sources, and the docs build draws the figures from it. So a figure changes when an agent
changes.

### The builder-critic loop: `build-part`

```calls build-part
title: The calls of build-part
desc: The build-part skill spawns julia-builder or python-builder, julia-critic or python-critic in round 1 at high effort and in each verify round at its own effort, julia-test-runner, advisor and arbitrator. julia-builder spawns julia-branch-verifier and changelog-scribe. python-builder spawns python-branch-verifier.
```

You start `build-part` in your session when a part is ready to build. The skill does not write
code. It spawns a builder to build the part, and then new critics to judge the result:
`julia-builder` and `julia-critic` for a Julia part, `python-builder` and `python-critic` for a
Python part, and `part-builder` and `part-critic` in a repository with neither a `Project.toml`
nor a `pyproject.toml`. Beside each critic, `julia-test-runner` runs the full test suite of a
Julia part; for any other part the skill's session runs the repository's own suite in the
background. A question inside the loop goes to the `advisor`, and a loop that does not converge
goes to the `arbitrator`. Before the pull request of a Julia part, `julia-builder` spawns
`julia-branch-verifier`, and it can spawn `changelog-scribe` for a fix of the CHANGELOG. Before
the pull request of a Python part, `python-builder` spawns `python-branch-verifier`.
[The builder-critic loop](loop.md#the-full-loop-build-part) follows one part through it.

### A smaller loop: `build-reviewed`

```calls build-reviewed
title: The calls of build-reviewed
desc: The build-reviewed skill spawns part-builder, part-critic and julia-test-runner. part-builder spawns julia-branch-verifier or python-branch-verifier.
```

A part of tier `reviewed` is small, with a fast gate. The skill spawns one `part-builder`, and a
new one for each later round, and one `part-critic`, which judges the work once. A run longer than
five minutes goes to `julia-test-runner`. Before the pull request, or before the commit where the
repository takes none, the builder spawns `julia-branch-verifier` in a Julia repository and
`python-branch-verifier` in a Python repository.
[The builder-critic loop](loop.md#the-small-loop-build-reviewed) follows one part through it.

### From review to green CI: `julia-pr-shepherd`

```calls julia-pr-shepherd
title: The calls of julia-pr-shepherd
desc: The julia-pr-shepherd agent spawns julia-pr-reviewer, changelog-scribe and ci-triage.
```

You spawn `julia-pr-shepherd` with a pull request of a Julia package. It does not review the pull
request itself: it spawns `julia-pr-reviewer`, which posts the review. Then the shepherd fixes the
findings. When the fix changes behaviour, it spawns `changelog-scribe` for the CHANGELOG entry.
When CI is red in several jobs, it spawns `ci-triage` to separate the real failures from the known
ones. [Review and pull requests](review.md) describes the three agents of a pull request.

### Every spawn

```calls
title: Every spawn
desc: Every edge of calls.toml: the build-part, build-reviewed, plan-parts and julia-structure skills, and the julia-builder, python-builder, part-builder, julia-pr-shepherd and editor agents, with each agent that they spawn.
```

This figure shows every entry of `calls.toml`. It adds two skills: `plan-parts` sends each part's
spec to a `reader` that measures its facts, and `julia-structure` sends a claim that nothing uses
a name to `exhaustive-auditor`. An agent that is not in this figure is spawned only from your
session. Only the agents with the tool `agent` can spawn another agent: `julia-builder`,
`python-builder`, `part-builder`, `julia-pr-shepherd` and `editor`. Each spawn costs a new
context, so an agent spawns another only where a fresh context or a smaller model does the work
better.
