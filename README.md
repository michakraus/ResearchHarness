# Research Harness

[![Documentation](https://img.shields.io/badge/docs-dev-blue.svg)](https://michakraus.github.io/ResearchHarness/)

Research Harness is the configuration, the safety settings and the working environment for coding
agents that work on research software. A coding agent is a language model that reads your files,
runs commands and edits code in your terminal.
The harness gives three coding agents, Claude Code, OpenCode and oh-my-pi, one shared set of
instructions, skills, sub-agents, permission settings and guard hooks. One command, `harness`,
installs this configuration and checks it.

The harness is for a researcher who wants a coding agent to keep the same rules in every
repository of a research tree: the packages, the experiments, the papers. Its own tools are for
Julia code, but most of its ideas transfer to any language. [Dependencies](docs/src/dependencies.md#julia-and-its-packages)
says what needs Julia. The [documentation site](https://michakraus.github.io/ResearchHarness/)
has two figures. The first shows the research tree, the components and the frontends. The second
shows how the install turns the sources into the configuration of each frontend.

## Features

- **[One configuration for three frontends.](docs/src/architecture.md)** The agents, skills,
  rules, commands and instruction files are neutral sources in this repository. `harness install`
  writes the configuration of each frontend from them, and gives each agent the model that your
  model tables set for its tier. The core instructions load in every session, a rule when the
  agent reads a matching file, and a skill when your request matches its description. You edit a
  source, never its installed copy. `harness doctor` checks a machine, read-only, and names the
  setup step that fixes each failure.
- **[Private data across machines.](docs/src/private-data.md)** A private profile holds every
  value that names a person, an institution or a machine, so one profile serves every machine and
  the repository holds none. `harness leaks` and gitleaks keep these values and secrets out of the
  repository. A signed private copy of the dotfiles kit carries the profile to each machine, and
  git carries the memory and the tree instructions.
- **[Sandbox and safety in layers.](docs/src/security.md)** One settings template gives the
  permission and sandbox settings, and the network hosts that Claude Code's sandbox can reach. The
  sandbox limits the files that a shell command can write and the hosts that it can reach. Guard
  hooks refuse unsafe shell commands before they run, such as a file edit through `sed -i` or a
  `git add -A`. A hook at session start warns when the installed configuration is behind its
  sources.
- **[A directory tree for research work.](docs/src/research-tree.md)** The research tree is one
  directory for the packages, experiments, papers, notes and literature, each in its own
  repository. `harness clone` and `harness repos` clone and sync them, `harness githooks` and
  `harness workflows` give every package the same git hooks and CI workflows, and each directory
  gets its own rules and agents.
- **[Research memory.](docs/src/memory.md)** A session starts with an empty context. Instruction
  files, task files, a knowledge base and project memory carry what earlier sessions learned into
  the next one, and `wiki-lint.jl` finds the notes that a later change made false. This feature is
  in development.
- **[Agentic software engineering.](docs/src/agentic-engineering.md)** A plan is split into parts,
  and each part becomes one pull request. A builder writes the tests and the code of a part. A
  critic that has not seen the builder's reasoning judges it against the part's acceptance
  criteria, and checks the tests with mutants: altered copies of the code that a good test must
  catch. Sub-agents run the long test runs, the reviews and the literature searches in their own
  contexts, so the context of your session stays free for the main work.
- **Tools for Julia packages and papers.** Agents run the tests, measure allocations and timings,
  find why a package does not load, and review and fix pull requests. Kaimon gives an agent a live
  Julia session. For papers, agents search the literature, check the claims of a manuscript with
  Julia scripts, and mark the changes of a revision.

## Getting started

- [Setup on macOS](docs/src/setup-macos.md) and [Setup on Linux](docs/src/setup-linux.md) give
  each step from a clean machine to a working harness, with the check of each step.
- [Tutorial: a first session](docs/src/tutorial.md) starts your first session and shows the
  guard hooks and the drift warning at work.
- [Introduction](docs/src/concepts.md) explains the ideas and the terminology of the harness.

## Documentation

Everything that this README leaves out is on the documentation site,
<https://michakraus.github.io/ResearchHarness/>.

## License

The code is under the MIT license, in
[`LICENSE`](https://github.com/michakraus/ResearchHarness/blob/main/LICENSE). The documentation is
under CC BY 4.0, in
[`LICENSE-docs`](https://github.com/michakraus/ResearchHarness/blob/main/LICENSE-docs).
