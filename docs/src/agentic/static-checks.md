# Static checks

A static check reads the code, or loads it, and gives a verdict without a run of the test suite.
It is cheap, so it runs often: on every commit, on every branch, and before every release. It is
deterministic, so its verdict does not depend on the model that wrote the code. This page lists the
static checks of the harness, where each one runs, and the checks that are planned.

## A check in place of a rule

An instruction such as "do not leave a comment between a docstring and its definition" works only
when the agent reads it and acts on it. A model follows such rules most of the time, and the cases
where it does not are the expensive ones. So the harness sorts its rules into two kinds:

- **Mechanical**: a fixed pattern, a banned call, a normalisation, a property of the method table.
  It gets a deterministic check, and the prose of the rule goes in the same pull request.
- **Judgement**: test design, the choice of a name, the consistency of a change across files. It
  stays prose, in a rule or in the [edge catalogue](edges.md), and a critic checks it.

A check fires every time; a rule fires when a session reads it. A rule whose check exists is
deleted, so that the instructions do not grow and nothing says the same thing twice.

## Where each check runs

| check | what it finds | where it runs | blocks |
|:--|:--|:--|:--|
| test layout | a test file outside the layout of the test groups | pre-commit, on a commit that touches `test/` | yes |
| JuliaFormatter | code that is not in the repository's style | pre-commit, on the staged files; `gate.jl` step `format` | yes |
| NFC | a source that is not in Unicode normal form C | pre-commit, on the staged files | yes |
| package load | a package that does not load | pre-commit, `using` in a fresh process | yes |
| `fatou lint` | lint findings of the Fatou language server | pre-commit | no: advisory, with a time limit of 60 s |
| [dispatch delta](#what-a-change-adds-to-the-method-table) | new ambiguities, piracies and abstract fields | `gate.jl` step `dispatch`; `julia-branch-verifier` on every branch | yes |
| [concrete fields](#concrete-field-types) | a struct field whose type is not concrete | `concrete-fields.jl`, and inside the dispatch delta | yes, through the dispatch delta |
| [public API diff](#the-public-api-before-a-release) | a public name or method that goes away | the `julia-release` skill, before a release | yes: the skill stops and asks you |
| Aqua | piracy, ambiguities, stale dependencies and other package defects | the package's quality tests, `test/quality/aqua.jl` | yes, in the tests |
| JET | type instabilities on chosen calls | the package's quality tests, where it has a hot path | yes, in the tests |
| [ast-grep rules](#syntax-rules) | five classes of defect from the reviews | the harness CI, on its own rule tests | planned for every commit |
| ruff and basedpyright | style, lint and strict types of the harness's Python | the harness's own pre-commit and pre-push hooks, and its CI | yes |

The pre-commit hook comes from the harness and is the same in every package: `harness githooks
--apply` installs it ([Tests and CI](tests-and-ci.md#from-an-edit-to-a-merge)).
[Git hooks and workflows](../components/githooks.md) describes each stage.

## What a change adds to the method table

Julia code goes wrong in ways that the source text does not show: a new method makes a call
ambiguous, a method on a type of another package changes what that package does, a field of an
abstract type makes every access slow. A search of the text cannot see these. The method table of
a loaded package can.

`dispatch-delta.jl <package> <base>` loads the base and the head in two fresh processes and
compares what each defines. It prints a verdict:

| verdict | when |
|:--|:--|
| `FAIL`, exit 1 | a new ambiguity among the package's own methods, or between its own and another package's; a new piracy; a new abstract field; a head that does not load |
| `UNKNOWN`, exit 3 | the base does not load, a side does not resolve, or a side times out |
| `INFO` | a method added to an existing function, with that function's other methods; a new or a gone JET report; a finding that went away; a dependency version that differs |
| `PASS`, exit 0 | none of the above |

The verifier runs it on every branch, against the merge base. So the rule "look at the methods
before you add one" does not depend on the agent: the gate looks.

## Concrete field types

A field typed `x::Real` or `x::Vector` makes each read of the field a dynamic dispatch. The rule
of the harness is *concrete up to type variables*: a field passes if its type is a type variable,
or a concrete type whose parameters all pass, or `Union{Nothing, X}` or `Union{Missing, X}` with `X`
passing. `Function`, a bare `Matrix` and every other `Union` fail. `concrete-fields.jl <package>`
lists every field of every struct of the package that fails, and exits 1 when it finds one. A
flagged field is fixed in the package; the check has no list of exceptions.

## The public API before a release

`dispatch-delta.jl <package> <tag> --api` compares the head with the last tag. It fails on a
public name that goes away, a name that is no longer public, a method of a public function that no
head method covers, and a keyword that no method accepts any more. Widening `f(::Int)` to
`f(::Integer)` passes, because the new method covers the old one. A new public name is INFO. The
`julia-release` skill runs it, and stops and asks you when it fails and the new version is not a
breaking one.

## Syntax rules

Some defects have a fixed shape in the syntax tree, and ast-grep finds them with the Julia
grammar. The harness has five such rules, each with a test of positive and negative snippets:

| rule | finds |
|:--|:--|
| `docstring-comment` | a comment line between a docstring and its definition, which detaches the docstring |
| `allocated-equality` | `@allocated(a) == @allocated(b)`, which compares two noisy numbers |
| `exitcode-alone` | a process's exit code read without its signal |
| `line-citation-comment` | a `name.jl:NN` citation in a comment, which goes stale when lines move |
| `debug-probe` | an `@show` or a debug print left in `src/` or `ext/` |

A hit on a line can be silenced with `# ast-grep-ignore: <rule-id>` on that line.
[Jobs and configuration](../components/other.md#research-sgconfig-yml) describes the configuration.
**Work in progress:** a pre-commit stage that runs the rules on every commit and blocks a hit on an
added line, and deletes the prose that the rules replace. The rules run only in the harness CI so
far.

## Planned checks

These checks are decided or under discussion, and none of them runs yet:

- **Rules of medium risk** (planned): an accumulator started from a float literal in generic code,
  `@test_throws` with a bare type or an unanchored phrase, and a `::Base.Callable` argument with no
  type parameter. They start as advisory, and block only after a count of their false positives
  over the packages.
- **Checks that load the code** (planned): helpers for groups of defects that only a loaded
  package shows, such as an element type that a function does not keep, or a device backend that a
  path does not support.
- **A catalogue of defensive Julia** (planned): from the findings of the reviews, the code that
  failed, the code that holds, and the check that would have caught it. A triple with a mechanical
  check becomes a check.
- **Interface conformance** (under discussion): a test that each concrete type of a package meets
  the interface of its abstract type, so that a default method on the supertype cannot answer
  wrongly for a subtype.

**In another language.** The split of rules into mechanical and judgement works anywhere. The
harness's own Python uses `ruff` and `basedpyright` in strict mode, and each idiom of its Python
rule names the tool that enforces it ([Development](../development.md#the-strict-profile)).
