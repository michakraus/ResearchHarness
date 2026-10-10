# Skills

A skill is a packaged set of instructions for the agent. Each skill is a directory
`skills/<name>/` with a `SKILL.md` file, and sometimes other files that the skill reads. The
frontmatter of `SKILL.md` holds the `name` and a `description`. The agent reads the description of
each skill. It loads the whole skill when a request matches a description, or when the user types
`/<name>`. A skill with `disable-model-invocation: true` loads only when the user types its name.
The optional key `model:` names a tier, `large`, `medium` or `small`, which each frontend maps to
a model ([The neutral vocabulary](../architecture.md#the-neutral-vocabulary)).

`harness install` copies each skill to `~/.claude/skills/<name>/` and links it into
`~/.agents/skills/`, where OpenCode and oh-my-pi find it. Edit the source in `skills/`, not the
installed copy. The description decides when a skill loads, so its words are the trigger words of
the requests. `harness skill-triggers` tests which skill loads on a query. The queries of each
skill are in `tests/skill-triggers/<name>.toml`: `load` lists the queries that must load the
skill, and `near` lists near misses that must load another skill or none.
[The triggering test of the skills](../daily-use.md#the-triggering-test-of-the-skills) tells how to run
it. Run it after you change a description.

The skills fall into four groups. `plan-parts`, `build-part` and `build-reviewed` plan work as
parts and build them. Five skills are for Julia code: structure, performance, the package audit,
the surgical fix and the release. `math-verify` and `latex-revision` are for mathematics and
manuscripts. `wait-what` and `which-model` are small session helpers that the user types.

## `plan-parts`

`plan-parts` plans work as parts. A part is one pull request: one branch, one worktree and one
*Done when*. The skill writes the parts table, the collision map, a tier per part, and a spec for
each part. It also writes the plan's own sections §V (rules for building and verifying) and §L
(the loop for this plan), from the template `plan-sections.md` in the skill directory.

It loads when the user wants a task planned or split into pull requests, asks what can run in
parallel, asks which parts need a decision first, or wants a done-condition sharpened. It has two
entry paths. On the forward path, it writes the table and the specs while the plan forms. On the
backward path, it adds them to a finished task file and changes nothing else.

The tier cell holds `decision`, `build`, `reviewed` or `direct`, with the reason beside it. Each
spec holds *Done when*, *Decided at the edges*, *Tests catch* (the mutants that the tests must
catch), *Files*, *Not in this part*, and *Traps*. The skill runs on the `large` tier.

It does not run anything and it does not merge. Use `build-part` or `build-reviewed` to build a
part.

## `build-part`

`build-part` runs the next part of a task file through the builder-critic loop. A builder agent
makes the work, and a separate critic agent with a fresh context judges it blind against the
part's benchmark. The loop repeats until a critic passes the part on a green test suite.

It loads on requests such as "build the next part", "build part D" or "run the open parts". It
reads the parts table with `scripts/parts-table.awk`, not the whole task file. It checks each open
pull request with `gh` and chooses a part that is open, unblocked and free of file collisions. A
part of tier `build` in `Packages/` or `Experiments/` starts only after `scripts/spec-gate.py`
passes. The frontmatter tier `medium` does not apply when the user types `/build-part`, so run the
loop in a session on the medium model.

In round 1, two `julia-critic` agents judge the part beside a full-suite run. After each round, a
fresh `julia-builder` fixes the blocking defects. A question inside the loop goes to the `advisor`
agent, not to the user. A loop without convergence goes to the `arbitrator` agent. At the end, a
builder opens the pull request. The skill writes only the `state` cell of the task file and the
lines that record the loop.

Two other files belong to the skill. `edges.md` is the catalogue of edge cases by kind of part.
`evidence.md` gives the evidence table, the test and mutation tools, and the rules for each row.

The skill does not plan parts, build or judge a part itself, or merge. Use `plan-parts` for a file
without a parts table.

## `build-reviewed`

`build-reviewed` builds one part whose tier cell is `reviewed`: a small change with a fast gate,
such as a script, a tool or a check. One `part-builder` agent builds it, one blind `part-critic`
agent judges it once, and the same builder gets at most one fix round.

It loads on requests such as "build this reviewed part" or "build the small part". Run it in a
session on the large model, because the session decides the questions inside the part and reads
the diff. The skill reads the parts table, checks the spec, and sets the `state` cell. After a
FAIL, the session checks the fix itself with the critic's reproducers, the gate and the diff. A
defect that the fix round does not close goes to the user. Before the finish, the session reads
the whole diff against the *Done when*.

It runs no advisor, no arbitrator and no second critic without the user. It does not merge, and it
does not change a part's tier. Use `build-part` for a part of tier `build`, and `plan-parts` to
choose a tier.

## `julia-structure`

`julia-structure` answers structural questions about Julia code with tools that read the code as
Julia. Grep does not see a module-qualified method definition as a definition, and it does not
know which method dispatch picks.

It loads when a request asks where a name is defined, what calls a function, which method runs,
what a signature change breaks, whether code is dead, or how a package is laid out. It routes each
question to one tool:

- `scripts/julia-methods.jl` lists the methods of a name without a Julia session. It works on a
  package that does not load.
- Kaimon `search_methods`, in a live session, tells which method runs for given argument types.
- `scripts/julia-callers.jl` finds the callers of a function and dead code from the lowered code.
- Kaimon `grep_code` searches all the repositories with a regular expression.

Each tool has blind spots, so an empty result is unknown, not a negative. The answer names the
tool that gave it. The skill reads code and changes nothing. For a claim that nothing uses a name,
use the `exhaustive-auditor` agent. For a whole-package sweep, use `julia-package-audit`.

## `julia-performance`

`julia-performance` gives the rules for a Julia performance measurement that means something:
allocations, type stability, timings, and before-and-after comparisons.

It loads for a question about the speed, the memory or the inference of Julia code, for example a
failing allocation test, a slowdown after an update, or a branch compared with `main`. Its main
rules:

- Measure each variant in a fresh process, and warm up before a timing.
- Do not measure while a test suite runs over the same packages.
- Assert an allocation ceiling, never an exact `@allocated` value.
- Toggle the change itself, with `invoke` or a worktree at the base commit, and keep everything
  else fixed.
- Print the resolved package versions beside a measurement.

The skill gives a report format: a table of the variants, the method and the conclusion. "Not
reproducible" is a valid result. The skill changes no code. For a whole-package quality sweep, use
`julia-package-audit`.

## `julia-package-audit`

`julia-package-audit` audits the correctness and code quality of a whole Julia package. The output
is one findings report in a fixed format, not a set of edits.

It loads when a request covers a whole package or its code quality: an audit, a review, a quality
pass, a check for type piracy or stale comments, or a check before a release. It has two
checklists. The quality pass checks correctness, type piracy, functionality duplicated from
dependencies, and stale, historical or long comments. The performance pass checks correctness,
type piracy, type instabilities and avoidable allocations. A table gives the method for each point,
with Aqua, JET, ExplicitImports.jl and `fatou lint`.

The report lists the findings by severity (`bug`, `correctness-risk`, `quality`, `nit`), each with
evidence. It also lists what is clean and what is not checked. The skill fixes only what the user
asks for, or what is trivially wrong. For one measurement, use `julia-performance`. For a pull
request, use the `julia-pr-reviewer` agent. To fix the findings, use `julia-surgical-fix`.

## `julia-surgical-fix`

`julia-surgical-fix` fixes a reported problem in a Julia repository so that the diff holds that
fix and nothing else. Then it checks the fix again.

It loads before an edit, when the request is to act on what a review, an audit, a critic or a CI
run reported. Its scope rule: every edit lands inside a hunk that the change already touched, or
in a line that the change made wrong. A defect next to the diff goes into the report, not into the
fix. After the last edit, JuliaFormatter runs on the edited files only.

A table tells what runs again after each kind of fix, from a re-read of a comment to a fresh
measurement of an allocation. The loop stops after two passes, at a file outside the diff, at a
design decision, or when a check goes from green to red. The skill never runs `Pkg.test()` and
never removes a symptom. Each fix in the report carries a command and its output. For what to
check, use `julia-package-audit`. Before you quote a number, use `julia-performance`.

## `julia-release`

`julia-release` releases a Julia package and registers it in the General registry. It covers the
path from the close-out of `CHANGELOG.md` to a merged registry pull request.

It loads on requests such as "cut a release", "bump the version" or "tag a version", or when
AutoMerge blocks a registry pull request. The procedure has six steps:

1. Close out the `[Unreleased]` section of `CHANGELOG.md`.
2. Set `version` in `Project.toml` by hand.
3. Commit both files in one release commit.
4. Push, and wait for the pre-push suite.
5. Comment `@JuliaRegistrator register` on the release commit, with the release notes. The script
   `githooks/release-notes.jl` builds the comment body.
6. Watch the registry pull request and TagBot.

AutoMerge blocks a breaking release without release notes. The skill does not use a
`Register.yml` workflow, because that workflow has no release-notes input and bumps the version
itself. The skill also tells how to check that a registration landed.

## `math-verify`

`math-verify` checks one mathematical statement in Julia: analytically, symbolically or
numerically. It runs the check together with a case that must make the check fail.

It loads when a request asks whether a formula, an identity, a scheme or a property holds, for
example an order of convergence, a conserved quantity or symplecticity. Every check is a Julia
script. `Symbolics.jl` is preferred, and `SymPyPythonCall.jl` serves where Julia has no equivalent.
Before the run, the skill states the input that must fail. It asks whether the measured property
is the claimed property or a weaker one. A numerical check uses a tolerance from the method and
fits the rate.

The script goes into the `scripts/` directory of the repository, and the claim cites it. The report
gives the verdict, the method, the control and the script path. For every claim of a whole `.tex`
manuscript, use the `latex-verifier` agent. For timings or allocations, use `julia-performance`.

## `latex-revision`

`latex-revision` runs a revision pass over a LaTeX manuscript with colour-marked changes. The
markings are a review queue: a marked passage is one that the author has not accepted yet.

It loads on requests such as "revise this paper", "address the referee report", "mark the changes"
or "strip the change markings". It gives the preamble block with the macros `\fixed` and `\added`
and their maths forms. A later pass adds a third colour, with `\rev`. A passage in the colour of
this pass waits for review, and one in an older colour is not accepted yet. An unmarked passage is
accepted. The skill never strips a marker that it did not resolve, because to strip a marker is to
accept it. `\markchangesfalse` typesets the document without colour.

Every claim gets a script in `scripts/`, cited with `\script{}`, as in `math-verify`. The skill
does not undo the author's reorganisation, and it does not change a frozen snapshot such as
`arXiv_v1`.

## `wait-what`

`wait-what` asks the agent to explain its last message again. The user types `/wait-what` when a
message is not clear. The skill has `disable-model-invocation: true`, so the agent never loads it
on its own.

The instruction tells the agent to give some context, to use ASD-STE100 Simplified Technical
English, and to use the words that the tree already uses. These words come from the
directory-scoped `CLAUDE.md` of the work, the `CHANGELOG.md` of the repository, and `Knowledge/`.
The skill reads nothing and changes nothing itself.

## `which-model`

`which-model` is a probe. It shows which model runs a typed slash command whose frontmatter names
the `small` tier. The user types `/which-model`, and the agent never loads it on its own.

The agent replies with exactly the sentence "which-model probe ran." and uses no tools. The skill
reads nothing and changes nothing.
