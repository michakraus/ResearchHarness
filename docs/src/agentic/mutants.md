# Mutant testing

A green test suite says that the tests pass. It does not say that they test anything. An agent
that writes a test and the code together can write a test that passes with the feature deleted:
it checks a value that the code always returns, or it never reaches the new branch. A mutant finds
such a test. This page describes the four kinds of mutants of the harness, the tools that run
them, and what a survivor means in the loop.

## A mutant

A mutant is a small, deliberate change of the source: a `<` that becomes `<=`, a deleted lower
bound, a `min` that becomes `max`. The tests run on the mutated code. When a test fails, the
mutant is *caught*: some test sees the change. When every test passes, the mutant *survives*: no
test sees the change, so no test checks what that line does.

<MutantFigure />

*From a source line to a closed survivor.* A mutant changes one line of the source, and the tests
run on a copy. A failing test catches the mutant. A mutant that survives shows a gap, and the
builder closes it with a test that catches it. For a mutant that is not named, a reason why the
change does not matter also closes it.

A mutant tests the tests, not the code. A survivor is a defect of the evidence: the code can be
right, but the suite cannot show it.

## Four kinds of mutants

| kind | who names it | when it runs | a survivor |
|:--|:--|:--|:--|
| **named** | the planner, in the spec's *Tests catch*, as `MU<n>` | by the builder, once, and by each critic of round 1 again; a fix round reruns the mutants that its fix touches | the clause fails, and the round is blocked |
| **own** | the builder, and each fixer for its fix: one per guard, branch, comparison and decided edge | before the builder returns `ready for critic` | a test, or a reason in the report; an open survivor makes the report not ready |
| **doubted** | the critic, for a test that it does not trust | in the critic's round | a blocking defect of cause `evidence`, when it is in a clause's domain |
| **generated** | `mutants.jl`, one per operator node of the lines that the diff adds | by the dispatcher's `julia-test-runner`, before round 1, only where the plan's §L asks for the sweep | a test, or a reason in the report, before round 1 |

A named mutant comes from the spec, before the code exists, so the builder cannot choose the
mutants that its tests happen to catch. The spec names the test that must catch it:

```markdown
- catches: MU1, the upper bound removed: `test/controller.jl`, testset "bounds"
```

A named mutant is caught by a kept test, never by a command that runs once.

## The tools

### Julia: `mutate.jl`

[`mutate.jl`](../components/scripts.md#mutate-jl-mutate-worker-jl-mutants-jl-and-mutants-test-jl)
works on a copy of the package under `~/Research/.scratch/mutants/` and never changes the package.
A mutant list is a TOML file:

```toml
[[mutant]]
name = "MU1: no upper bound of the step factor"
file = "src/step.jl"
from = "clamp(f, 0.2, 5.0)"
to = "max(f, 0.2)"
```

A mutant with several edits has one `[[mutant.edit]]` table per edit. The units are the test units
of [`run-tests.jl`](tests-and-ci.md#the-three-tiers-of-a-test-run); without them, the script runs
the units that the diff against `origin/main` reaches.

| verdict | meaning |
|:--|:--|
| `CAUGHT` | a unit fails |
| `SURVIVED` | every unit passes |
| `NO-COVERAGE` | in warm mode: the coverage lists the mutant's lines, but no unit runs them; a finding, as `SURVIVED` is |
| `UNKNOWN` | no verdict: `run-tests.jl` itself failed; in warm mode also a baseline that failed after the mutant, a time-out, a smoke mutant that was not caught, or a sampled kill that a cold run does not catch |
| `INVALID` | the mutant does not apply, does not parse, or adds an undefined name; it does not run |

The mode `--warm` runs the list in warm worker processes, so each mutant does not pay for a new
process and a new compilation. It guards its own result: a smoke mutant that must be caught, a
rerun of the baseline every 20 mutants and after the last, a cold rerun of every survivor, and a
cold rerun of a sample of 10 kills. The cold verdict counts. A list of 20 mutants or fewer runs
every mutant cold. `--check` validates a list and runs nothing. The script exits 0,
3 on an `UNKNOWN` or `INVALID` verdict, and 2 on a usage error.

**Known issue (K74):** the warm mode is unsound for a mutant that changes a method signature. Run
such a mutant cold.

### Python: `harness mutate`

[`harness mutate SPEC`](../harness-command.md#mutate) runs named mutants of the harness's own
Python. A spec has one table per mutant, with a text anchor in place of a line number:

```toml
[MU1]
file = "lib/harness/changelog.py"
anchor = 'DIRECTORY = "changelog.d"'
old = 'HEADING = "## Unreleased"'
new = 'HEADING = "## Released"'
tests = ["changelog"]
```

It copies the checkout into a temporary git repository, runs the named parts of `harness test`
unmutated first, then each mutant alone. Each line says `killed`, `SURVIVED` or `invalid`. It
exits 0 when every mutant is killed, 1 when one survives or is invalid, and 2 when it stops.

## A survivor in the loop

A survivor is closed in one of two ways:

- **A test that catches it.** The builder adds or sharpens a test, and runs the mutant again. A
  named mutant has only this way: its survivor fails its clause.
- **A reason**, for an own or a generated mutant only. The mutant changes nothing observable: it
  is equivalent, it changes dead code, or it changes a message text that no clause names. The
  builder writes the reason in the *Mutants* table of its report, and the critic judges it.

The builder's report lists every mutant with its verdict. The critic reruns the named mutants and
the mutants that it doubts. A named mutant that survives is a blocking defect, whatever the other
tests show.

**Why not a sweep of every line.** A generated sweep finds many mutants that change nothing that
matters, and each one costs a test run. The loop therefore names the mutants that carry the
clauses, and runs a sweep only where the plan asks for one.

**In another language.** The idea needs only a way to change one line in a copy and run the tests.
`harness mutate` does this for Python; [`part-builder`](../components/agents.md#part-builder) runs
its mutants by hand in another language.
