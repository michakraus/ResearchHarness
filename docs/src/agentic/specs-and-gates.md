# Specs and gates

An agent that has no fixed goal stops when the work looks done. A critic that has no fixed
benchmark passes what looks right. So each part of a plan has a *spec*, written before the build,
and each step of the loop ends at a *gate*: a command whose exit status says pass or fail. This
page describes what a spec holds, how its facts are checked, and the gates that a part passes.

## What a spec holds

The spec of a part is what the builder builds to and what the critic judges against. It has six
blocks:

1. **Done when.** The acceptance criteria, as clauses. **Every clause is checkable by a command**: a
   test that fails before the change, a `grep` that finds nothing, a number with its tolerance and
   the reason for it. "Works", "is clean" and "matches the old code" give a critic nothing to fail.
   A clause with *every* or *each* names its finite set, because the critic blocks only on a failure
   in that set.
2. **Decided at the edges.** What the code does at each edge that the part reaches: for a numerical
   method `NaN` and `Inf`, a zero or subnormal input, an empty or a one-element case, the other
   precision. The list of edges for each kind of part is the [edge catalogue](edges.md). An edge
   left open is found by a critic, one per round, as a blocking defect, so the planner decides each
   one in advance, or the part waits for you.
3. **Tests catch.** For each clause that a test covers, the [mutant](mutants.md) that the test must
   catch: "deleting the lower bound of the step factor makes the controller test fail". Without a
   named mutant, a test that passes with the feature deleted passes the loop.
4. **Files.** The files that the part creates or changes, all in one repository. This is the part's
   row of the [collision map](tasks.md#the-collision-map).
5. **Not in this part.** What a builder might add and must not, with the part that owns it.
6. **Traps.** A failure that an earlier attempt met, with its cause.

A spec does not prescribe the order of the builder's work. The steps of a build are in the
builder's own instructions, and a longer brief improves the first build more than the result.

## The spec-delta format

A new plan writes the spec of a `build` or `reviewed` part as a file of its own, in the spec-delta
format. It states the base as requirements and the change as a delta, and each requirement has
scenarios with commands:

```markdown
### Requirement: The step factor stays in its bounds

The controller SHALL return a factor in [0.2, 5.0] for every finite error estimate.

#### Scenario: A zero error estimate

- WHEN `step_factor(0.0)` is called
- THEN it returns `5.0`
- check: `julia --project -e 'using Pendulum; Pendulum.step_factor(0.0) == 5.0 || exit(1)'`
- catches: MU1, the upper bound removed: `test/controller.jl`, testset "bounds"
```

| section | holds |
|:--|:--|
| `1 · Living spec` | each fact of the base that the change relies on, as a requirement whose `check:` passes on the base |
| `2 · Change proposal` | why, what is in and out of scope, the files, the commits, the seams |
| `3 · Delta` | the requirements that the part modifies, adds and removes, each with its scenarios |
| `4 · What stays from the plan` | the named mutants, the decisions that bind the part, the traps |

Each decided edge is a scenario. A named mutant is killed by a kept test, never by a command that
runs once. A block stands on its own: a scenario that says "as above" fails the validator.

## The premise check

A plan rests on facts: what a function returns, what a tool prints, which line holds a call. A
fact that is false sends the builder in the wrong direction, and the loop finds it only after a
round. Two checks run before the build:

- **A `reader` agent measures the facts of each spec.** It lists each fact that the spec states,
  such as a count, a `file:line`, a version or what a tool does, and marks each one `holds`,
  `false` or `cannot`, with the command or the file that it read. The planner fixes every `false`
  fact. A reader in its own context does the check, because a planner reads its own facts as true.
- **`spec-validate.py` runs every premise on the base.** It checks the structure of the spec and
  runs each `check:` of the living spec on the base commit. Planning ends when it passes. A check
  that needs a GPU runs from a Kaimon session, because the shell sandbox has no GPU; without that
  run, the verdict is `UNMEASURED`, never a pass.

The check finds false facts, not stale ones: a premise that was true when the spec was written can
go stale when another part merges. A `file:line` in a spec therefore names the commit that it was
read at.

## The gates

A gate is a command with an exit status. The loop moves on only when the gate passes.

| gate | when | what it checks | exit status |
|:--|:--|:--|:--|
| [`spec-gate.py`](../components/scripts.md#spec-gate-py) | before a `build` part starts | the spec holds *Decided at the edges* and *Tests catch*; its files lie in one repository; a spec-delta spec passes `spec-validate.py` | `PASS` or `EXEMPT` 0; `MISSING`, `INVALID` or `SPANS` 1; `UNMEASURED` 2 |
| [`spec-validate.py --head`](../components/scripts.md#spec-validate-py) | each critic round of a spec-delta part | every `check:` of the delta on the branch head | 0 when every check passes |
| [`gate.jl`](../components/scripts.md#gate-jl-and-gate-test-jl) | by hand, for a Julia part: no skill or agent calls it | the affected tests, the named mutants, the generated mutants, the [dispatch delta](static-checks.md#what-a-change-adds-to-the-method-table), the format | 0 pass, 1 fail, 2 bad arguments, 3 no verdict |
| [`harness test`](../harness-command.md#test) | every round of a part in the harness itself | the whole Python suite, the hook probe and the verb sweep | 0 when every case passes |
| the test suite | beside each critic round | the full suite of the repository, run by `julia-test-runner` | the suite's own |
| CI | for a spec-delta part, on each pushed head | every job of the repository's workflows | the job conclusions |

A round passes only when the critic says PASS and the suite is green, and for a spec-delta part
also every check and every CI job of the head. A failed check goes to the fix builder as a blocking
defect, verbatim, beside the critic's defects.

### The steps of `gate.jl`

`gate.jl` runs five steps on a Julia package against a base, by default `origin/main`, and writes
its report to `gate.md`:

1. **`tests`**: the test files that the diff reaches, with `run-tests.jl affected`, and the quality
   tests.
2. **`named`**: the named mutants, with `mutate.jl --warm`. A mutant that survives fails the step.
3. **`generated`**: a sweep of operator mutants over the diff. It reports, and never fails.
4. **`dispatch`**: `dispatch-delta.jl` against the base: new ambiguities, piracies, abstract
   fields and stale explicit imports fail.
5. **`format`**: JuliaFormatter on the changed files.

A step that reports gives INFO, which counts as a pass. A step that gives no verdict, such as a
base that does not load, makes the gate exit 3 when no step fails: no verdict is never a pass.

## Why the gates are commands

An instruction such as "check for method ambiguities" works only when the agent reads it and acts
on it. A gate works every time, and its result does not depend on the model. Where a rule of the
harness can be a command, it becomes one, and its prose goes. [Static checks](static-checks.md)
lists the checks that replace prose rules, and those that are planned.
