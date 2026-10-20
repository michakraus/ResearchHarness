# Research Harness

[![Documentation](https://img.shields.io/badge/docs-dev-blue.svg)](https://michakraus.github.io/ResearchHarness/)

Research Harness is a configuration for coding agents that work on research software. A coding
agent is a language model that reads your files, runs commands and edits code in your terminal.
The harness gives three of them, Claude Code, OpenCode and oh-my-pi, one set of instructions,
skills, sub-agents, permission settings and guard hooks. One command, `harness`, installs this
configuration and checks it.

The harness is for a researcher who wants a coding agent to keep the same rules in every
repository of a research tree: the packages, the experiments, the papers. Its own tools are for
Julia code, but most of its ideas transfer to any language. [Dependencies](docs/src/dependencies.md#julia-and-its-packages)
says what needs Julia. The [documentation site](https://michakraus.github.io/ResearchHarness/)
shows the harness and its layers, and the way from its sources to the frontends, in two figures.

## Features

- **One set of sources for three frontends.** The agents, skills, rules, commands and instruction
  files are neutral sources in this repository. `harness install` writes the configuration of
  each frontend from them, with the model of each tier that your model tables give. You edit a
  source, never its installed copy.
- **Instructions that load when they apply.** The core instructions load in every session. A rule
  loads when the agent reads a matching file, and a skill when your request matches its
  description. Your own instructions about your research tree install beside them.
- **Safety in layers.** One settings template gives the permission and sandbox settings of all
  three frontends, and the network hosts that Claude Code's sandbox can reach. Guard hooks refuse
  unsafe shell commands before they run, such as a file edit through `sed -i` or a `git add -A`.
  A hook at session start warns when the installed configuration is behind its sources.
- **Long work goes to a sub-agent.** A test run, a review or a literature search runs in its own
  context and returns a short report, so your session keeps its room for the work.
- **A builder and a critic for each change.** A plan is split into parts, each one pull request.
  A builder writes the tests and the code of a part, and a critic that has not seen the builder's
  reasoning judges it against the part's done-condition, with mutants that a good test must catch.
  The skills `plan-parts`, `build-part` and `build-reviewed` run the loop.
- **Tools for Julia packages.** Agents run the tests, measure allocations and timings, find why a
  package does not load, and review and fix pull requests. Kaimon gives an agent a live Julia
  session. `harness githooks` and `harness workflows` give every package of the tree the same git
  hooks and CI workflows.
- **Tools for papers.** Agents search the literature, check the claims of a manuscript with Julia
  scripts, and mark the changes of a revision.
- **Private values stay private.** A private profile holds every value that names a person, an
  institution or a machine, so one profile serves every machine and the repository holds none.
  `harness leaks` and gitleaks keep these values and secrets out of the repository.
- **One command checks a machine.** `harness doctor` checks the tools, the profile, the install
  and the background jobs, read-only, and names the setup step that fixes each failure.

## Getting started

- [Setup on macOS](docs/src/setup-macos.md) and [Setup on Linux](docs/src/setup-linux.md) give
  each step from a clean machine to a working harness, with the check of each step.
- [Tutorial: a first session](docs/src/tutorial.md) starts your first session and shows the
  guard hooks and the drift warning at work.
- [Introduction](docs/src/concepts.md) explains the ideas and the words of the harness.

## Documentation

Everything that this README leaves out is on the documentation site,
<https://michakraus.github.io/ResearchHarness/>.

## License

The code is under the MIT license, in
[`LICENSE`](https://github.com/michakraus/ResearchHarness/blob/main/LICENSE). The documentation is
under CC BY 4.0, in
[`LICENSE-docs`](https://github.com/michakraus/ResearchHarness/blob/main/LICENSE-docs).
