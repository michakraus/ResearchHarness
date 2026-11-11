# Example: a feature in a Julia package

This page follows one feature from the first conversation to the merge. The package `Pendulum` is
fictitious: a small Julia package that integrates the equations of a pendulum with a fixed time
step. The feature is an adaptive step: the integrator estimates its error and changes the step to
keep the error near a tolerance. The commands and the files are those of the harness; the
messages of the agents are short illustrations, not real output.

## 1. Discuss

You open a session in the checkout of `Pendulum` and describe what you want:

> Add an adaptive step to `Pendulum`. The error estimate comes from an embedded pair. The step
> grows by at most 5 and shrinks by at most 5. Plan it as parts.

The session reads the code before it plans. It finds the integrator in `src/integrate.jl`, the
tests in `test/integrate.jl`, and the `[compat]` floor of Julia in `Project.toml`. It asks you the
questions that the code cannot answer, in one round, each with its recommendation:

1. Which norm does the error estimate take? *Recommendation: the root mean square, scaled by the
   tolerance.*
2. Does the public function `integrate` keep its signature, with a new keyword `adaptive`?
   *Recommendation: yes, with `adaptive = false`, so that no caller changes.*

You answer the second question at once and leave the first open. The session writes a task file,
`Tasks/Add the adaptive step to Pendulum.md`, with `status: wip`, the goal, the done condition,
your answer with your name and the date, and the open question.

## 2. Plan

The session loads the skill [`plan-parts`](../components/skills.md#plan-parts). It splits the work
into three parts, each one pull request:

| part | repository | sections | what it is | tier | state |
|:--|:--|:--|:--|:--|:--|
| **A** | `Pendulum` | spec, §V, §L | The step controller: a factor from an error estimate. A numerical method. | build | open |
| **B** | `Pendulum` | §4, §V, §L | Which norm the error estimate takes. Changes a public answer. | decision | waiting for the user |
| **C** | `Pendulum` | spec, §V, §L | The docs page and the example. Small, with a fast gate. | reviewed | blocked by A |

Part B is a `decision` part, because only you can choose the norm. The collision map shows that A
and C share only `CHANGELOG.md`, where each adds its own lines, so they do not serialise
([Tasks](tasks.md#the-collision-map)).

## 3. Write the spec

Part A is a numerical method, so the planner reads the section *A numerical method* of the
[edge catalogue](edges.md) and decides each edge that the controller reaches. The spec, in the
spec-delta format, holds requirements such as this one:

```markdown
### Requirement: The step factor stays in its bounds

The controller SHALL return a factor in [0.2, 5.0] for every finite error estimate.

#### Scenario: A zero error estimate

- WHEN `step_factor(0.0)` is called
- THEN it returns `5.0`
- check: `julia --project -e 'using Pendulum; Pendulum.step_factor(0.0) == 5.0 || exit(1)'`
- catches: MU1, the upper bound removed: `test/controller.jl`, testset "bounds"
```

Its *Decided at the edges* gives one line per edge:

```markdown
- an error estimate of `NaN` or `Inf`: the factor is `0.2`, the smallest step
- an error estimate of `0.0`: the factor is `5.0`, the largest step
- `Float32` input: the factor is a `Float32`; every constant is converted with `T(…)`
- a subnormal error estimate: treated as `0.0`
```

Its *Tests catch* names the mutants that the tests must catch, such as MU1, the upper bound
removed, and MU2, the `NaN` branch deleted.

Two checks run before the build ([Specs and gates](specs-and-gates.md#the-premise-check)). A
`reader` agent measures each fact of the spec against the code, and finds one false fact: the
integrator is in `src/integrate.jl`, not in `src/step.jl` as the first draft said. The planner
fixes it. Then `spec-gate.py` runs `spec-validate.py`, which runs every premise on the base commit:

```bash
python3 ~/Research/Harness/scripts/spec-gate.py "Tasks/Add the adaptive step to Pendulum.md" A
```

It prints `A PASS`, and planning ends.

## 4. Build

You start the loop:

> Build part A.

The skill [`build-part`](../components/skills.md#build-part) writes the spec bundle of part A and
spawns `julia-builder` in a new worktree, `~/Research/.worktrees/Pendulum-agent-<id>`. The builder
writes the tests first, then `step_factor`, then runs `gate.jl`, the named mutants and its own
mutants. It returns:

```text
Verdict: ready for critic
Mutants: MU1 CAUGHT, MU2 CAUGHT; own: 6 CAUGHT, 0 SURVIVED
```

**Round 1.** Two `julia-critic` agents judge the branch at high effort, each blind to the other and
to the builder, while `julia-test-runner` runs the full suite. One critic passes. The other fails
the part with one blocking defect:

```text
Verdict: FAIL
Blocking: wrong result — step_factor(1.0f-3) returns a Float64.
  Reproducer: julia -e 'using Pendulum; Pendulum.step_factor(1.0f-3) isa Float32 || exit(1)'
  The safety factor 0.9 is a Float64 literal, against the decided edge "Float32 input".
```

The round fails, because either critic can fail it.

**The fix round.** A new builder gets the defect and the last builder's report, writes the
failing test first, then converts the constant with `T(0.9)`. It reruns the mutants that the fix
touches, and returns `ready for critic`.

**The verify round.** One new critic judges only the fix: it gets the earlier blocking defect and
its reproducer, never the builder's report. It reruns the reproducer, the tests that the fix
reaches, and MU1 and MU2. The suite is green, and the critic says `PASS`.

**The finish.** A new builder rereads the text of the branch, runs `julia-branch-verifier`, stages
the paths that the verifier names, and opens the pull request with `gh pr create -R <owner>/Pendulum`.
`build-part` writes `PR #12 in review` into the parts table, and records the rounds: two critic
rounds, no advisor decision, no ruling.

The defect of round 1 is inside the domain of a decided edge, so it adds nothing to the edge
catalogue. Had the critic found a failure outside every clause, for example on an error estimate
of `-0.0`, it would have recorded it as found late, and `build-part` would have added its class to
the catalogue after the loop.

## 5. Decide and review

While part A is in review, you answer the question of part B: the root mean square, scaled by the
tolerance. The session writes the decision into the task file with your name and the date, and
gives part B the tier `reviewed`, because nothing in it is open any more.

CI runs on the pull request of part A: the tests on Julia `min` and `1` on three systems, the
downgrade job and the doctests ([Tests and CI](tests-and-ci.md#the-ci-of-a-package)). You read the
diff and the evidence table of the critic, and merge on GitHub.

## 6. The rest of the task

Part C is now unblocked. You ask for it:

> Build part C.

The skill [`build-reviewed`](../components/skills.md#build-reviewed) spawns one `part-builder`
and one `part-critic`. The critic passes the docs page at once, your session reads the result, and
the builder opens the pull request. Part B goes the same way.

When the three pull requests are merged, the done condition holds. The session writes
`status: done` and `completed:` into the task file and moves it into `Tasks/Archive/`.

## What the example shows

- **The questions came first.** Each question that only you could answer was asked before the
  build, in one round. The loop then ran without a question to you.
- **The spec decided the edge, and the critic held the code to it.** The `Float32` defect was not
  a matter of taste: a line of the spec named the answer.
- **Each judgement came from a new context.** No critic saw a builder's reasoning, and the verify
  round saw only the fix.
- **You merged.** No agent of the loop merged its own pull request
  ([Review and pull requests](review.md#who-merges)).
