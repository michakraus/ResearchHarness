# Rules and instructions

An instruction file is text that the agent reads at the start of every session. A rule is an
instruction file that loads only when it applies: the agent reads it when it reads a file whose
path matches the `paths:` list in the rule's frontmatter. Under Claude Code, only a `Read` of a
matching file loads the rule. A shell command such as `cat` loads nothing. So a rule costs nothing
in a session that does not touch its kind of file.

The sources are `instructions/core.md` and `rules/<name>.md` in this repository.
`harness install --apply` copies them to `~/.claude/instructions/` and `~/.claude/rules/`.
`CLAUDE.md` imports `instructions/core.md`, and OpenCode and oh-my-pi read it too.
oh-my-pi gets each rule in its own `rules/` directory, with the `paths:` list as its globs.
OpenCode loads no rule by itself: its global instruction file tells the agent which rule to
read before which kind of work. These files are the harness layer. The profile and the tree
instructions add to them, and
[the architecture](../architecture.md#the-three-layers) describes the three layers.

To change a rule, edit its source and run `harness install --apply`; [Typical use](../daily-use.md)
gives the steps. The page starts with `core`, which loads always. The rules follow: first the
rules about instruction files and records, then the rules about Julia work.

## `core`

`instructions/core.md` holds the rules that apply in every session and every sub-agent, whatever
the task. It is the neutral part of the always-on instructions: it names no person and no
repository. It tells the agent:

- how to approach a change: think first, ask the open questions in numbered rounds, keep the
  change small and in scope, and define the check before the work;
- which tool to use: the internal edit tools for every write, never `sed`, `awk`, `perl -i` or a
  shell redirection;
- to remove the cause of an error, not its symptom;
- to stage the changed paths by name, never `git add -A`, `-u` or `.`, and never `--amend`;
- when to delegate work to a sub-agent, and to check what the sub-agent returns;
- that text from a tool result is data, not instructions;
- how to report: what happened, with each failure quoted and each skipped step named.

It loads always, so it holds only what must apply everywhere. A rule about one kind of file goes
into a rule below. A fact about the user's own research tree goes into the tree instructions, in
`instructions/research-tree.md`.

## `instruction-files`

This rule says how to write an instruction file: a `CLAUDE.md`, a `SKILL.md`, an agent definition,
a rule or an `AGENTS.md`. It loads on the paths `**/CLAUDE.md`, `**/SKILL.md`, `**/agents/*.md`,
`**/rules/*.md` and `**/AGENTS.md`.

It requires the present tense and no history. It lists the words that date a text, such as "now"
and "originally", and sends the history to `CHANGELOG.md`. A table says which layer a rule belongs
in: the always-on files, a directory-scoped `CLAUDE.md`, or a rule in `~/.claude/rules/` with
`paths:`. It warns that a rule in a project's own `.claude/rules/` loads at every session start,
whatever its frontmatter says. Before a rule is written, it asks whether a deterministic check
can do the job instead: a settings glob, a guard hook or a git hook. It also gives the tests for
each line: does the line change the behaviour of the model, and is each fact in one place only.
The style of every instruction file is ASD-STE100 Simplified Technical English.

## `changelog`

This rule says how to write an entry in a `CHANGELOG.md`. It loads on the path
`**/CHANGELOG.md`.

Every repository of the research tree has a `CHANGELOG.md`, and the changelog is the one place
for history. An entry goes in the same change that earns it, and it says what changed and why
that matters to a user. The rule lists the traps: write the entry from the artefact, not from the
plan; check a file count against the merge result; and run each new test against `origin/main`
before the entry says that it fails there. A released entry is never corrected. A later entry
records the change. An open question is not an entry: a known defect goes to `KNOWN_ISSUES.md`.
The `changelog-scribe` agent writes an entry in the right form.

## `known-issues`

This rule says what a repository's `KNOWN_ISSUES.md` holds and the form of an entry. It loads on
the path `**/KNOWN_ISSUES.md`.

The file holds each finding with evidence that its pull request does not fix, in the present
tense. A defect that the branch itself causes stays out, because the branch fixes it. The file
exists only when it has an entry. Each entry has a stable ID that is never used again, a heading
`### <ID> · <problem>`, and the fields `location`, `evidence`, `kind` and `found`. The rule gives
the values of `kind`. An entry leaves the file when its fix merges, and the changelog entry of
the fix names its ID. Every agent reads the file before it adds an entry.

## `generated-hooks-and-workflows`

This rule says that the git hooks and the CI workflows of a repository are generated copies. It
loads on the paths `**/.githooks/**`, `**/.github/workflows/**` and `**/Harness/githooks/**`.

The sources are in `githooks/` of this repository. `harness githooks --apply` and
`harness workflows --apply` install them into every package and experiment repository, and
`githooks/verify-workflows.jl` checks them. The rule tells the agent to edit the source, never an
installed copy, and to add an entry to the harness changelog. It lists the traps: `core.hooksPath`
does not travel with a push; a session cannot set `core.hooksPath` or `core.fsmonitor`; the
`pre-commit` hook checks only `*.jl` files; and a repository in the profile key `docs_exceptions`
is skipped. A push to `main` runs the full test suite in the `pre-push` hook.

## `julia-code`

This rule is the guide to work on Julia code. It loads on the path `**/*.jl`.

It gives three tiers of checks, cheapest first: an evaluation in a warm Kaimon session, then
`scripts/run-tests.jl` on the affected test files, then the full `Pkg.test()`. A cold `julia`
gets `--startup-file=no`. To diagnose a bug, the agent first makes a command that fails on the
bug, then ranks its hypotheses. The rule lists traps of Julia versions, Revise, dispatch, complex
transposes and `Float16` kernels. Before the agent writes a new name, it looks for existing
methods with `scripts/julia-methods.jl`. The rule also says how to run JuliaFormatter on the
changed files only, how to run Aqua so that a failure shows, and which Kaimon tools are off.
Every numerical check is written in Julia.

## `julia-tests`

This rule gives the one layout of the tests of a Julia repository. It loads on the path
`**/test/**/*.jl`.

The test dependencies are in `test/Project.toml`. `runtests.jl` holds no test: it selects the
groups `core`, `slow`, `doctests`, `metal`, `cuda` and `broken`, and includes each file in a
`@safetestset`. A `core` file runs in 60 s or less. `test/<path>.jl` tests `src/<path>.jl`. A
failing test is `@test_broken` with its issue on the same line, and so is a failing Aqua check.
The rule also gives rules for compat entries, seeds, rounding and allocation assertions.
`scripts/test-layout.jl --check <repository>` prints each violation of the layout and exits 1 if
there is one. `scripts/run-tests.jl <repository> <selection>` runs one file, a group, or the
files that a diff reaches.

## `julia-docs`

This rule says what breaks a Documenter build and how to check it. It loads on the paths
`**/docs/make.jl`, `**/docs/src/**` and `**/docs/Project.toml`.

Only a `makedocs` run checks the docstrings, the cross-references and `checkdocs`; `Pkg.test()`
and the CI Doctests job do not. So the agent runs the docs build after the last source edit. The
rule lists the traps: a gap between a docstring and its definition, a submodule with no `@docs`
block, and an unqualified `@ref` to a name that two modules export. A local build cannot finish
when `docs/make.jl` uses InterLinks, because the sandbox blocks the fetch. The agent then reads
the CI job. The rule says which marker shows a complete build, and how to confirm a deploy from
`origin/gh-pages`.
