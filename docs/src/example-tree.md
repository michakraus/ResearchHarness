# An example tree

The harness works in a research tree: one directory that holds your repositories and your notes.
This page describes one such tree, the tree of the harness's author, as an example of how a user
organises work around the harness. The overview figure of the
[Introduction](concepts.md#the-parts-of-the-harness) shows its six directories: a library, a store
of knowledge, the packages, the experiments, the projects and the papers. Your tree can have other
directories and other names.

In the example, the tree is `~/Research`. The verbs of the `harness` command that look for
repositories of the tree read its path from `$RESEARCH_ROOT`, else they use `~/Research`.

Each section below says three things about one directory:

- **Holds:** what the directory holds.
- **Served by:** the components of the harness that work on it. Each name links its section in
  *Components*. A component that serves more than one directory is in each of their sections.
  The components are [agents](concepts.md#agent), [skills](concepts.md#skill),
  [rules](concepts.md#rule), commands, git [hooks](concepts.md#hook), scripts and verbs of the
  `harness` command.
- **Named by:** the key of the [profile](concepts.md#profile), the verb, or the
  [tree instructions](concepts.md#tree-instructions) that give the directory's name.

## Library

**Holds:** a catalogue of the papers and books of other authors. Each paper has a directory with
its file and a short Markdown description.

**Served by:**

- [`literature-scout`](components/agents.md#literature-scout) searches the literature for a
  question. When a paper is already in the library, it says so and proposes no download.
- [`wiki-lint.jl`](components/scripts.md#wiki-lint-jl) checks the paths and the line citations in
  the Markdown of the library.
- [`pre-commit-wiki`](components/githooks.md#pre-commit-wiki) runs `wiki-lint.jl` before each
  commit in the library. `harness wiki-lint-hook --apply` [installs](concepts.md#install) it.

**Named by:** no profile key. The verb `harness wiki-lint-hook` and the script `wiki-lint.jl` find
the library by its name, `Library`, below the research tree. In the example, the tree
instructions name the directory's own [instruction file](concepts.md#instruction-file).

## Knowledge

**Holds:** a vault of Markdown notes that record what is established: facts, methods and
measurements, with links between the notes.

**Served by:**

- [`wiki-lint.jl`](components/scripts.md#wiki-lint-jl) gives the vault every check: links,
  paths, line citations and the structure of the notes.
- [`pre-commit-wiki`](components/githooks.md#pre-commit-wiki) runs `wiki-lint.jl` before each
  commit in the vault.
- [`changelog-scribe`](components/agents.md#changelog-scribe) writes a dated entry in the vault's
  `CHANGELOG.md`, only for a change to what is established.
- [`math-verify`](components/skills.md#math-verify) keeps the script of a mathematical check, and
  a note of the vault links that script.
- [`wait-what`](components/skills.md#wait-what) asks the agent to explain its work again in the
  words that the vault uses.

**Named by:** no profile key. The verb `harness wiki-lint-hook` and the script `wiki-lint.jl` find
the vault by its name, `Knowledge`, below the research tree. In the example, the tree
instructions name it among the directories where a change goes to `main` directly, with no pull
request.

## Packages

**Holds:** the software packages, one git repository each, with their tests, their documentation
and a `CHANGELOG.md`. In the example, they are Julia packages.

**Served by:**

- The agents of a planned change:
  [`julia-builder`](components/agents.md#julia-builder) builds one part of a plan, and
  [`julia-critic`](components/agents.md#julia-critic) judges it. The skill
  [`build-part`](components/skills.md#build-part) runs the two in a loop. For a smaller part, the
  skill [`build-reviewed`](components/skills.md#build-reviewed) runs
  [`part-builder`](components/agents.md#part-builder) and
  [`part-critic`](components/agents.md#part-critic) once. A part of a package ends in a pull
  request.
- [`worker`](components/agents.md#worker) reads the directory's own instruction file before its
  first edit here.
- [`changelog-scribe`](components/agents.md#changelog-scribe) writes an entry of a
  `CHANGELOG.md`, under a version heading.
- The agents of a pull request:
  [`julia-branch-verifier`](components/agents.md#julia-branch-verifier) checks a branch before the
  pull request opens, [`julia-pr-reviewer`](components/agents.md#julia-pr-reviewer) reviews it,
  and [`julia-pr-shepherd`](components/agents.md#julia-pr-shepherd) takes it to green CI. The
  commands [`review-pr`](components/commands.md#review-pr) and
  [`merge-pr`](components/commands.md#merge-pr) look for the repository in this directory first.
- The agents of a diagnosis:
  [`julia-test-runner`](components/agents.md#julia-test-runner),
  [`julia-load-doctor`](components/agents.md#julia-load-doctor),
  [`ci-triage`](components/agents.md#ci-triage) and
  [`git-hook-triage`](components/agents.md#git-hook-triage).
- The skills of package work:
  [`julia-structure`](components/skills.md#julia-structure),
  [`julia-package-audit`](components/skills.md#julia-package-audit),
  [`julia-surgical-fix`](components/skills.md#julia-surgical-fix) and
  [`julia-release`](components/skills.md#julia-release).
- The rules that load when the agent reads a matching file:
  [`julia-code`](components/rules.md#julia-code), [`julia-tests`](components/rules.md#julia-tests),
  [`julia-docs`](components/rules.md#julia-docs), [`changelog`](components/rules.md#changelog) and
  [`known-issues`](components/rules.md#known-issues).
- The shared git hooks [`pre-commit`](components/githooks.md#pre-commit) and
  [`pre-push`](components/githooks.md#pre-push), and the workflows such as
  [`workflows/CI.yml`](components/githooks.md#workflows-ci-yml). The verbs `harness githooks`,
  `harness push-all` and `harness ci-protection` work on every git repository of this directory.
  `harness workflows` works on each of them that has a `Project.toml`.

**Named by:** the profile key `repository_roots`, which holds the path of this directory. The
keys `docs_exceptions` and `docs_additions` name single repositories in it. The four verbs above
find the directory by its name, `Packages`, below the research tree.

## Experiments

**Holds:** the numerical experiments, one git repository each: code whose results you can make
again, with its tests and a `CHANGELOG.md`.

**Served by:**

- The same agents of a planned change and of a pull request as in [Packages](#packages):
  [`julia-builder`](components/agents.md#julia-builder),
  [`julia-critic`](components/agents.md#julia-critic),
  [`part-builder`](components/agents.md#part-builder),
  [`part-critic`](components/agents.md#part-critic),
  [`julia-branch-verifier`](components/agents.md#julia-branch-verifier),
  [`julia-pr-reviewer`](components/agents.md#julia-pr-reviewer) and
  [`julia-pr-shepherd`](components/agents.md#julia-pr-shepherd), with the skills
  [`build-part`](components/skills.md#build-part) and
  [`build-reviewed`](components/skills.md#build-reviewed) and the commands
  [`review-pr`](components/commands.md#review-pr) and
  [`merge-pr`](components/commands.md#merge-pr).
- [`worker`](components/agents.md#worker) reads the directory's own instruction file before its
  first edit here.
- [`changelog-scribe`](components/agents.md#changelog-scribe) writes an entry of a
  `CHANGELOG.md`, under a version heading.
- [`git-hook-triage`](components/agents.md#git-hook-triage) finds why a git hook blocked a commit
  or a push, or seems to hang.
- The agents and the skill of a measurement:
  [`julia-perf-analyst`](components/agents.md#julia-perf-analyst) measures time and allocations
  before and after a change, and [`julia-performance`](components/skills.md#julia-performance)
  holds the method.
  [`julia-test-runner`](components/agents.md#julia-test-runner) runs the tests.
- The rules [`julia-code`](components/rules.md#julia-code),
  [`julia-tests`](components/rules.md#julia-tests) and
  [`changelog`](components/rules.md#changelog).
- The git hooks [`pre-commit`](components/githooks.md#pre-commit) and
  [`pre-push`](components/githooks.md#pre-push), and the same four verbs as in
  [Packages](#packages).

**Named by:** the profile key `repository_roots`, which holds the path of this directory beside
the packages. The four verbs find the directory by its name, `Experiments`, below the research
tree.

## Projects

**Holds:** derivations and analysis: notes, calculations and scripts, with a research log of
what was tried and what it showed.

**Served by:**

- [`math-verify`](components/skills.md#math-verify) checks one mathematical statement in Julia,
  with a case that must make the check fail, and keeps the check as a script.
- [`changelog-scribe`](components/agents.md#changelog-scribe) writes an entry of the research
  log.
- [`julia-builder`](components/agents.md#julia-builder) builds a part of a plan here too, but the
  part ends in a commit to `main`, not in a pull request.
- [`worker`](components/agents.md#worker) reads the directory's own instruction file before its
  first edit here.

**Named by:** no profile key and no verb. In the example, the tree instructions name the
directory's own instruction file.

## Papers

**Holds:** the manuscripts, as LaTeX sources, each with the scripts that check its claims.

**Served by:**

- [`latex-revision`](components/skills.md#latex-revision) runs a revision pass with marked
  changes, for example after a referee report.
- [`latex-verifier`](components/agents.md#latex-verifier) checks the mathematics of a manuscript
  claim by claim, and writes a Julia script for each claim.
- [`math-verify`](components/skills.md#math-verify) checks one statement, and the manuscript cites
  its script.
- [`literature-scout`](components/agents.md#literature-scout) finds the references that a
  manuscript needs.
- [`changelog-scribe`](components/agents.md#changelog-scribe) writes a dated pass, not a release,
  because a manuscript has no versions.
- [`julia-builder`](components/agents.md#julia-builder) builds a part of a plan here too, but the
  part ends in a commit to `main`, not in a pull request.
- [`worker`](components/agents.md#worker) reads the directory's own instruction file before its
  first edit here.

**Named by:** no profile key and no verb. In the example, the tree instructions name the
directory's own instruction file.

## The profile values of the tree

A tree such as this one sets two values of the profile. `examples/profile.toml` has them with an
example home directory:

```toml
repository_roots = ["/home/example/Research/Packages", "/home/example/Research/Experiments"]
tree_agents = "/home/example/Research/Environment/Agents"
```

- `repository_roots` holds the directories that hold the repositories of the tree. `harness leaks`
  searches the harness for the name of each directory below them, so that no source of the
  harness names one of your repositories.
- `tree_agents` holds the directory of your tree instructions. `harness install`
  installs them into `~/.claude/` beside the sources of the harness. In
  the example, this directory is in the tree but is not one of the six directories of the figure.

[Adapting the profile](profile.md#the-keys-of-the-profile) describes every key.

## Another layout

Your tree can have other directories. Adapt the two values to it:

1. Put each directory that holds your repositories into `repository_roots`, with its absolute
   path. Its name can be any name.
2. Put the path of your tree instructions into `tree_agents`. The directory can be anywhere.
3. Write your own directories, and the instruction file of each, into your tree instructions.

Some verbs do not take their directories from the profile. They find them by a fixed name below
the research tree, `$RESEARCH_ROOT` or `~/Research`:

- `harness githooks`, `harness workflows`, `harness push-all` and `harness ci-protection` look in
  `Packages` and `Experiments`.
- `harness wiki-lint-hook` looks for the prose repositories, `Knowledge` and `Library` among
  them. The script `wiki-lint.jl` reads the same names.

A verb that finds no directory with its name skips it and changes nothing there. To use these
verbs, keep the two names for the directories of your repositories, or set `$RESEARCH_ROOT` to a
tree that has them.
