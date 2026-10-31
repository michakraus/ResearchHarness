# The research tree

The [research tree](concepts.md#research-tree) is one directory that holds all your research
work: the packages, the experiments, the papers, the notes and the literature. Each part of the work is a git repository
of its own, in a directory that says what kind of work it is. The harness knows this layout. It
clones and syncs the repositories, it gives each of them the same checks and workflows, and each
directory gets the [rules](concepts.md#rule) and the [agents](concepts.md#agent) for its kind of
work.

This page describes the tree of the harness's author as an example, then how to adapt it, and
then the commands that work on the whole tree. In the example, the tree is `~/Research`.

## Why one tree

- **A [session](concepts.md#session) can reach every repository.** A change often touches more
  than one: a package and the experiment that uses it, or a paper and the script that checks its
  claims. The settings give a session the tree as one working directory, and the
  [sandbox](concepts.md#sandbox) lets a shell command write in it.
- **Each repository keeps its own history.** It has its own remote, its own tests and its own
  `CHANGELOG.md`. In the example, a change to a package or an experiment goes through a pull
  request, and a change to the notes goes to `main` directly.
- **The directory says what kind of work it is.** A rule, an
  [instruction file](concepts.md#instruction-file) or a [skill](concepts.md#skill) can apply to
  one directory only, so a session in the papers does not load the rules of the packages.
- **Temporary work has fixed places.** A worktree and a log go to directories that the guard
  [hooks](concepts.md#hook) know, not into a repository.

## An example layout

The overview figure of the [Introduction](concepts.md#the-parts-of-the-harness) shows six
directories of the example tree. Each row below names the components of the harness that work on
one of them, and links each to its section in *Components*.

| directory | what it holds | the components that serve it |
|:--|:--|:--|
| `Library` | a catalogue of the papers and books of other authors: for each paper, a directory with its file and a short Markdown description; in the example also the citation keys and the tools that build the shared bibliography | [`literature-scout`](components/agents.md#literature-scout), which says when a paper is already in the library; [`harness wiki-lint`](harness-command.md#wiki-lint), which checks the paths and the line citations; [`pre-commit-wiki`](components/githooks.md#pre-commit-wiki), which runs it before each commit |
| `Knowledge` | a vault of Markdown notes that record what is established: facts, methods and measurements, with links between the notes | [`harness wiki-lint`](harness-command.md#wiki-lint) with every check, and [`pre-commit-wiki`](components/githooks.md#pre-commit-wiki); [`changelog-scribe`](components/agents.md#changelog-scribe), for a change to what is established; [`math-verify`](components/skills.md#math-verify), whose scripts the notes link; [`wait-what`](components/skills.md#wait-what) |
| `Packages` | the software packages, Julia packages in the example, each with its tests, its documentation and a `CHANGELOG.md` | the agents and skills of a planned change and of a pull request, from [Agentic software engineering](agentic-engineering.md); the Julia skills [`julia-structure`](components/skills.md#julia-structure), [`julia-package-audit`](components/skills.md#julia-package-audit), [`julia-surgical-fix`](components/skills.md#julia-surgical-fix) and [`julia-release`](components/skills.md#julia-release); the agents of a diagnosis, such as [`julia-load-doctor`](components/agents.md#julia-load-doctor); the rules [`julia-code`](components/rules.md#julia-code), [`julia-tests`](components/rules.md#julia-tests), [`julia-docs`](components/rules.md#julia-docs), [`changelog`](components/rules.md#changelog) and [`known-issues`](components/rules.md#known-issues); the shared git hooks and workflows of [Git hooks and workflows](components/githooks.md) |
| `Experiments` | the numerical experiments: code with reproducible results, its tests and a `CHANGELOG.md` | the same agents of a planned change and of a pull request as `Packages`; [`julia-perf-analyst`](components/agents.md#julia-perf-analyst) and the skill [`julia-performance`](components/skills.md#julia-performance), for a measurement; the rules [`julia-code`](components/rules.md#julia-code), [`julia-tests`](components/rules.md#julia-tests) and [`changelog`](components/rules.md#changelog); the same git hooks |
| `Projects` | derivations and analysis: notes, calculations and scripts, with a research log of what was tried and what it showed | [`math-verify`](components/skills.md#math-verify); [`changelog-scribe`](components/agents.md#changelog-scribe), for the research log; [`julia-builder`](components/agents.md#julia-builder), whose part ends in a commit to `main` here, not in a pull request |
| `Papers` | the manuscripts, as LaTeX sources, each with the scripts that check its claims | [`latex-revision`](components/skills.md#latex-revision); [`latex-verifier`](components/agents.md#latex-verifier); [`math-verify`](components/skills.md#math-verify); [`literature-scout`](components/agents.md#literature-scout); [`changelog-scribe`](components/agents.md#changelog-scribe), for a dated entry of each revision pass |

[`worker`](components/agents.md#worker) reads the directory's own instruction file before its
first edit in `Packages`, `Experiments`, `Projects` or `Papers`.

The tree has four more directories that the subcommands of the `harness` command know:

| directory | what it holds |
|:--|:--|
| `Environment` | the notes about the machine and the harness, with the evidence behind each rule, and, in the example, the [tree instructions](concepts.md#tree-instructions) |
| `Tasks` | the task files: one Markdown plan for each task, with its parts table and the state of each part |
| `Books` and `Talks` | the books and the talks, one repository each, as in `Papers` |

## Your own layout

Your tree can have other directories and other names. Two values of the
[profile](concepts.md#profile) describe it. `examples/profile.toml` has them below the home
directory, `~`:

```toml
repository_roots = ["~/Research/Packages", "~/Research/Experiments"]
tree_agents = "~/Research/Environment/Agents"
```

- `repository_roots` lists the directories that contain the repositories of the tree.
  `harness leaks` searches the harness for the name of each directory below them, so that no
  source of the harness names one of your repositories.
- `tree_agents` holds the directory of your tree instructions. `harness install`
  [installs](concepts.md#install) them into `~/.claude/` beside the sources of the harness. The
  directory can be anywhere.

Some subcommands do not take their directories from the profile. They find them by a fixed name
below the research tree, `$RESEARCH_ROOT`, or `~/Research` if it is not set:

- `harness githooks`, `harness workflows`, `harness ci-protection` and `harness format` look in
  `Packages` and `Experiments`.
- `harness clone` and `harness repos` look in the group directories `Packages`, `Experiments`,
  `Papers`, `Books`, `Talks` and `Projects`, and for the fixed repositories `Knowledge`,
  `Environment`, `Tasks` and `Library`.
- `harness wiki-lint-hook` looks for the prose repositories, `Knowledge` and `Library` among
  them. `harness wiki-lint` reads the same names.

A subcommand that finds no directory with its name skips it and changes nothing there. To use
these subcommands, keep these names for the directories of your repositories.

The settings template and the guard hooks name `~/Research` itself: the working directory of a
session, the write allowlist of the sandbox, and the places of the worktrees and of the scratch
directory. `$RESEARCH_ROOT` does not move them. So keep the tree at `~/Research`, or change the
template and the hooks.

## Instructions for each directory

The tree instructions hold what is true of your tree and of no other: the names of your
directories, the instruction file of each, and where a change goes. `adapters/claude/CLAUDE.md`
imports their `instructions/research-tree.md`, and OpenCode, oh-my-pi and Antigravity read that
file too.
[Architecture](architecture.md#the-three-layers) describes the layer.

In the example, each directory of the figure has its own instruction file, `CLAUDE.md`, and the
tree instructions name it. Claude Code loads a `CLAUDE.md` when a session works in its directory,
so the conventions of the papers load only in the papers. A rule loads when the agent reads a
file that its `paths:` field matches, wherever the file is.
[Rules and instructions](components/rules.md) describes both.

## Temporary work

Two directories at the top of the tree hold work that is not a repository of the tree. Their names
start with a `.`, so they are not part of the layout above.

- **`.worktrees/`** holds the worktrees: a second checkout of a repository on another branch, for
  a pull request or a part of a plan. The hook [`worktree.py`](components/hooks.md#worktree-py)
  creates each one as `~/Research/.worktrees/<Repository>-<slug>`, from `origin/HEAD`. Remove a
  worktree with `git worktree remove` from its main checkout when its branch is merged.
- **`.scratch/`** holds the logs, the probe environments and the results of the tests that run
  outside a repository. It holds no checkout.

The [rm check](components/hooks.md#the-rm-check) of the guard hook lets a recursive `rm` run only
below these two directories.

## Clone, sync and trust

These subcommands act on every repository of the tree. Each subcommand that changes something is a
dry run first, and `--apply` makes the change. [The `harness` command](harness-command.md#the-repositories-of-the-research-tree)
gives the contract of each.

| subcommand | what it does |
|:--|:--|
| `harness githooks` | copies the shared git hooks of `githooks/` into `.githooks/` of each git repository directly below `Packages/` and `Experiments/`, and sets `core.hooksPath` there |
| `harness workflows` | copies the canonical files of `githooks/workflows/` into each git repository directly below `Packages/` and `Experiments/` that has a `Project.toml`: the CI workflow, `dependabot.yml` and `codecov.yml` into each, and the TagBot workflow into each package. It copies the documentation workflow only where a tracked `docs/make.jl` exists, and never into a repository that the profile key `docs_exceptions` or `docs_additions` names. It deletes the retired `CompatHelper.yml` |
| `harness trust` | marks the research tree and each git repository below it as trusted in Claude Code's `~/.claude.json` |
| `harness clone` | clones each repository of the repository table (see [The `harness` command](harness-command.md#the-repository-table)) that has no directory yet. A selection such as `packages` or `knowledge` limits it to one group or one fixed repository. A directory that is in the way stops the run before the first clone. After the clones, run `harness githooks`, `harness wiki-lint-hook` and `harness trust` with `--apply` |
| `harness repos status` | fetches every repository, then prints its branch, its commits ahead of and behind its upstream, its changed tracked files and its open pull requests, with `gh` for GitHub and `glab` for GitLab. It also names a repository of the table that is not cloned, a clone that the table does not list, and a repository with no origin. It is read-only, and takes no `--apply` |
| `harness repos pull` | fetches, then fast-forwards each branch that is behind its upstream. It skips a branch that has diverged, and one whose incoming commits change a file with local changes |
| `harness repos push` | pushes each git repository below `Packages/` and `Experiments/` whose branch is ahead of its upstream, one at a time. It skips a repository with no upstream, one that is also behind its upstream, and one on a branch that is not the default branch, unless you give `--include-topic-branches`. `--no-verify` skips the pre-push suite |
| `harness repos sync` | runs `repos pull`, then `repos push` |
| `harness ci-protection` | protects the default branch on GitHub of each git repository directly below `Packages/` and `Experiments/` that has a `CI.yml`, with a ruleset that requires the status checks of the canonical `CI.yml`. It first checks that the workflows are canonical, and skips a private repository and one where you are not an admin |
| `harness format` | runs JuliaFormatter over each tracked `.jl` file of the repositories below `Packages/` and `Experiments/`; it skips a repository that has no `.JuliaFormatter.toml` |

Run each one in your own terminal, not from a session. The settings refuse a session's write to
`.git/config` and to `~/.claude.json`. A `githooks` run that cannot set `core.hooksPath` prints
the command for each repository. `repos push` and `repos sync` run the pre-push hook of each
repository, and a hook that runs a full test suite can take a long time.

`status`, `pull` and `clone` take every group (`packages`, `experiments`, `papers`, `books`,
`talks`, `projects`) and every fixed repository (`knowledge`, `environment`, `tasks`,
`library`) when you name none; `push` and `sync` take `packages` and
`experiments`.

The copies of `githooks` and `workflows` are tracked files in each repository. Read the
diff, then commit each copied file by name.

```bash
harness githooks
harness githooks --apply
harness workflows --apply
harness trust --apply
harness repos status
harness repos pull --apply
harness repos push
harness format
```

[Private data across machines](private-data.md) says how the tree instructions, the profile and
the memory reach a second machine.
