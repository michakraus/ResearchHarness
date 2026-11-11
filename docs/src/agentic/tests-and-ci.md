# Tests and CI

A test runs the code and compares what it does with what it must do. An agent writes tests
easily, and runs them often, so the questions are which tests run when, how long the agent waits
for them, and which result counts. This page describes the test layout of a Julia package, the
three tiers of a test run, and the checks between an edit and a merge.

## The test layout

Each test file of a Julia package belongs to one group, and `test/runtests.jl` runs the groups
that its arguments name:

| group | holds | runs |
|:--|:--|:--|
| `core` | the fast tests: each file runs in at most 60 s, cold | by default, and in every affected run |
| `slow` | the tests that take longer | by default |
| `doctests` | `test/quality/doctests.jl` only | when named |
| `metal`, `cuda` | the tests of a device backend | `metal` by default on Apple silicon, where the package has it; otherwise when named |
| `broken` | a file that cannot load, with its issue | when named |

Aqua and, where the package has a hot path, JET run as quality tests in `test/quality/`. The rule
[`julia-tests`](../components/rules.md#julia-tests) states the layout, and `test-layout.jl` checks
it on every commit that touches `test/`. A fixed layout lets a script, not the agent, decide which
tests a change reaches.

## The three tiers of a test run

An agent checks its work many times during a change. A cold Julia process pays for the start, the
package load and the compilation each time, so the harness gives three tiers, cheapest first
([`julia-code`](../components/rules.md#julia-code)):

0. **A warm session.** A [Kaimon](../dependencies.md#kaimon) session reloads `src/` before every
   evaluation, so an edit is checkable in seconds. This is the default while the agent works.
1. **The affected tests.** [`run-tests.jl <package> affected`](../components/scripts.md#run-tests-jl-and-run-tests-test-jl)
   runs the `core` files that the diff against `origin/main` can reach, and the quality files, in
   one fresh process. A changed `Project.toml` runs the full suite.
2. **The full suite.** `Pkg.test()`, before a push. It takes seconds in a small package and up to
   100 minutes in CI in the large ones.

A measurement of time or allocations is the exception: it needs a cold process, never the warm
session.

`run-tests.jl` exits 0 on a pass, 1 on a failure, 2 on bad arguments or a layout outside the
convention, and 3 on a failure of the script. Its mode `select` prints what `affected` would run,
and runs nothing. The log goes to a file, so the agent reads a short verdict and not the whole
output.

## Waiting for a long run

A full suite of a large package runs for many minutes and prints nothing. An agent that waits for
it in its own context keeps that context alive at full cost. So the long runs go to
[`julia-test-runner`](../components/agents.md#julia-test-runner), on a medium model, which returns
one verdict per testset and the failing output verbatim. In the builder-critic loop it runs beside
each critic, so the suite and the critic finish at about the same time. A builder runs every
command under five minutes itself, and leaves the longer runs to its caller.

## From an edit to a merge

<ChecksFigure />

*The checks between an edit and a merge.* An edit meets three groups of checks before you merge
it: the pre-commit hook on every commit, the part's gate in every build round, and CI on every
push of the branch.

1. **The pre-commit hook**, on every commit: the test layout, JuliaFormatter, Unicode NFC, and
   whether the package loads in a fresh process. `fatou lint` runs too, as advice only. The hook is
   the same in every package, and `harness githooks --apply` installs it
   ([`pre-commit`](../components/githooks.md#pre-commit-pre-commit-jl-and-pre-commit-test-jl)).
2. **The part's gate**, in every build round: [`gate.jl`](specs-and-gates.md#the-steps-of-gate-jl)
   runs the affected tests, the named mutants, the generated mutants, the dispatch delta and the
   format, and `julia-test-runner` runs the full suite beside the critic.
3. **CI**, on every push of the branch and on the pull request: the workflow `CI.yml` below.

The shared pre-push hook runs `Pkg.test` on a push to `main` or `master` only; a push of another
branch passes at once, and CI tests it. **Known issue (K133):** the hook tests the working tree,
not the commit that it pushes.

## The CI of a package

The CI workflows of a package come from the harness, and are byte-identical in every package.
`harness workflows --apply` copies them, and
[`verify-workflows.jl`](../components/githooks.md#verify-workflows-jl) checks that every copy
matches its template:

| job or file | what it runs | required |
|:--|:--|:--|
| `test` | the tests on Julia `min` and `1`, on Ubuntu, macOS and Windows; `pre` and `nightly` on Ubuntu | yes, except `pre` and `nightly` |
| `downgrade` | the tests with each direct dependency at the lower bound of its `[compat]` entry | no: information only |
| `doctest` | the doctests of the manual, where `docs/Project.toml` exists | yes |
| `Documenter.yml` | the documentation build and its deploy | no |
| `TagBot.yml`, `codecov.yml`, `dependabot.yml` | the tag of a registered release, the coverage threshold, the weekly `[compat]` proposals | no |

The matrix names Julia by the aliases `min` and `1`, so the names of the checks are the same in
every repository. [`harness ci-protection`](../harness-command.md#ci-protection) sets a ruleset on
the default branch with those names as required checks, and refuses to run while
`verify-workflows.jl` fails. A red required check stops the merge; the
[`ci-triage`](../components/agents.md#ci-triage) agent separates a real failure from a known one.

## The harness's own tests

The harness is Python and has its own suite. [`harness test`](../harness-command.md#test) runs the
selftest of each module in a process of its own, the hook probe and the verb sweep. Its CI has
three workflows:

| workflow | jobs |
|:--|:--|
| `test.yml` | `python`, `empty-home`, `changelog`, `systemd`, `dotfiles`, `lint`, `leaks`, `strict` |
| `julia.yml` | `test`, the tests of the Julia scripts, and `ast-grep`, the tests of the syntax rules |
| `docs.yml` | `docs`, the build and the checks of this site |

[Development](../development.md#ci) describes each job.

## Planned

- **A regression set for the critics** (work in progress): known defects, planted in branches, to
  measure whether a change of a critic's prompt finds more or fewer of them.
- **Tests of the dependents** (planned): a change of a base package runs the tests of the packages
  that depend on it, before its release.
- **Property-based tests** (planned): generators for the inputs of a numerical method, so that a
  test covers a class of inputs and not only the cases that its author chose.

**In another language.** The tiers and the order of the checks work in any language. The harness's
Python uses `harness test` as its gate, and `ruff` and `basedpyright` as its static checks;
[the builder-critic loop](loop.md#the-full-loop-build-part) names the agents for each language.
