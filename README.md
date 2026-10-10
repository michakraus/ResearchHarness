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
says what needs Julia.

```mermaid
flowchart TB
  accTitle: The harness and its three layers
  accDescr: The harness surrounds three layers. At the top is the research tree, with the library, the knowledge, the packages, the experiments, the projects and the papers. In the middle are the components: agents, skills, commands, rules, guard hooks, git hooks and workflows, scripts and settings. At the bottom are the frontends: Claude Code, OpenCode and oh-my-pi.
  subgraph harness["Research Harness"]
    direction TB
    subgraph tree["The research tree"]
      direction LR
      t1["Library"] ~~~ t2["Knowledge"] ~~~ t3["Packages"] ~~~ t4["Experiments"] ~~~ t5["Projects"] ~~~ t6["Papers"]
    end
    subgraph components["The components"]
      direction LR
      c1["Agents"] ~~~ c2["Skills"] ~~~ c3["Commands"] ~~~ c4["Rules"] ~~~ c5["Guard hooks"] ~~~ c6["Git hooks and workflows"] ~~~ c7["Scripts"] ~~~ c8["Settings"]
    end
    subgraph frontends["The frontends"]
      direction LR
      f1["Claude Code"] ~~~ f2["OpenCode"] ~~~ f3["oh-my-pi"]
    end
    tree ~~~ components ~~~ frontends
  end
```

*The harness and its three layers.* The research tree is where the work is, the components are
what the harness supplies, and the frontends are the agents that read them. The research-tree
layer shows the tree of the harness's author, as an example; your tree holds your own directories.

These are the main ideas:

- **One set of sources for three frontends.** The agents, skills, rules, commands and instruction
  files are neutral sources in this repository. `harness install` writes the configuration of
  each frontend from them. You edit a source, never its installed copy.
- **Instructions that load when they apply.** The core instructions load in every session. A rule
  loads when the agent reads a matching file, and a skill when your request matches its
  description.
- **Safety in layers.** One settings template gives the permission and sandbox settings of all
  three frontends. Guard hooks refuse unsafe shell commands before they run. A hook at session
  start warns when the installed configuration is behind its sources.
- **Long work goes to a sub-agent.** A test run or a review runs in its own context and returns a
  short report, so your session keeps its room for the work.
- **Private values stay private.** A private profile holds every value that names a person, an
  institution or a machine. `harness leaks` and gitleaks keep these values and secrets out of the
  repository.

```mermaid
flowchart LR
  accTitle: From the sources to the frontends
  accDescr: The sources of this repository, the agents, skills, rules, commands and instructions, the guard hooks, the settings template and the adapters, and two private inputs, the profile with the model tables and the tree instructions, go into harness install. It writes the configuration of Claude Code into ~/.claude/, of OpenCode into ~/.config/opencode/ and of oh-my-pi into ~/.omp/agent/. The settings template also goes into harness settings install, which writes ~/.claude/settings.json for Claude Code.
  subgraph sources["The sources, in this repository"]
    direction TB
    s1["Agents, skills, rules,<br/>commands, instructions"]
    s2["Guard hooks"]
    s3["Settings template"]
    s4["Adapters of the frontends"]
  end
  subgraph private["Private, on your machine"]
    direction TB
    p1["Profile and model tables"]
    p2["Tree instructions"]
  end
  install["harness install"]
  settings["harness settings install"]
  sources --> install
  private --> install
  s3 --> settings
  install --> claude["Claude Code<br/>~/.claude/"]
  install --> opencode["OpenCode<br/>~/.config/opencode/"]
  install --> omp["oh-my-pi<br/>~/.omp/agent/"]
  settings -->|settings.json| claude
```

*From the sources to the frontends.* `harness install` writes the configuration of each frontend
from the sources and your private files. [Architecture](docs/src/architecture.md) describes the
layers and what each frontend receives.

## Installation

These are the shortest steps on macOS. [Setup on macOS](docs/src/setup-macos.md) explains each
step and the check that it worked.

1. Install the required tools of [Dependencies](docs/src/dependencies.md). Setup on macOS gives
   the Homebrew commands.

2. Clone the repository to `~/Research/Harness`, and put its `bin/` on the `PATH`. Add the
   `export` line to your shell's start file too, for example `~/.zshrc`. Then
   `harness --help` lists the verbs.

   ```bash
   git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
   export PATH="$HOME/Research/Harness/bin:$PATH"
   ```

3. Copy the example profile and model tables, and make the directories and the settings file
   that they and the install need.

   ```bash
   mkdir -p ~/.config/research-harness ~/.claude/skills ~/.config/opencode
   cp ~/Research/Harness/examples/{profile,models}.toml ~/.config/research-harness/
   mkdir -p ~/Research/Environment/Agents/instructions ~/Research/Packages ~/Research/Experiments
   touch ~/Research/Environment/Agents/instructions/research-tree.md
   test -f ~/.claude/settings.json || echo '{}' > ~/.claude/settings.json
   ```

4. In `~/.config/research-harness/profile.toml`, replace the example path `/home/example` with
   your home directory, for example `/Users/me`, in each value.

5. Install. `harness install` prints the plan and exits 1, because it would change files.
   `--apply` makes the change; the first one also downloads the Julia packages of the scripts.
   Then the dry run reports `0 change(s) to make.` and exits 0. The settings verb works in the
   same way.

   ```bash
   harness install
   harness install --apply
   harness install
   harness settings install --apply
   ```

## A first session

This short tutorial needs Claude Code and the installed harness, and any git repository. It
needs no Julia. [Tutorial: a first session](docs/src/tutorial.md) is the long form, on a Julia
package.

1. Start Claude Code in your repository. When it asks whether you trust the folder, answer yes.

   ```bash
   cd ~/path/to/your/repository
   claude
   ```

2. Ask a question about the repository, for example `What does this repository hold? Name the
   files that matter most.` Each tool call of the agent shows in the session. Some ask for your
   permission first: read each one before you answer.

3. Ask for an edit through the shell, for example `Replace "old" with "new" in README.md with
   sed -i.` A guard hook refuses the command before it runs, and the session shows
   `Refused: sed -i ...`. The agent then makes the edit with its own edit tool.

4. End the session with `/exit`. Then add an empty line to a source of the harness, so that the
   installed copy is behind its source.

   ```bash
   echo >> ~/Research/Harness/instructions/core.md
   ```

5. Start a new session with `claude`. The harness warns at once: `~/.claude is behind its sources
   (...): an edit there is not installed.` It blocks nothing.

Undo the edit with `git -C ~/Research/Harness restore instructions/core.md`, and the next session
starts with no warning.

## Documentation

Everything that this README leaves out is on the documentation site,
<https://michakraus.github.io/ResearchHarness/>.

## License

The code is under the MIT license, in
[`LICENSE`](https://github.com/michakraus/ResearchHarness/blob/main/LICENSE). The documentation is
under CC BY 4.0, in
[`LICENSE-docs`](https://github.com/michakraus/ResearchHarness/blob/main/LICENSE-docs).
