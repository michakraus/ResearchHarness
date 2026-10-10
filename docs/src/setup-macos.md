# Setup on macOS

This page gives each step from a clean Mac to a working harness. For each step it says what the
step does, why the harness needs it, and how you see that it worked.
[Installation](https://github.com/michakraus/ResearchHarness#installation) in the README gives
the short form of the same steps. [setup-linux.md](setup-linux.md) is the page for Linux.

The steps use `~/Research/Harness` as the path of the checkout. [Concepts](concepts.md) explains
the words that this page uses, and the glossary there has an entry for each.

**Without Julia code.** If you write no Julia, you can skip the steps and lines that this page
marks. You still need Julia itself, because the [install](concepts.md#install) runs it once.

**The exit codes.** Each verb of `harness` ends with an exit code, which your shell keeps in
`$?`. Exit 0 means that nothing would change or that the verb succeeded, exit 1 that a dry run
found something to change, and exit 2 an error. Each step below names the code that it expects,
with its meaning.

## The dependencies

**What it does.** Homebrew installs the tools that the harness calls.
[Dependencies](dependencies.md) lists each tool, its minimum version and what the harness uses it
for. Its section [What each tool does](dependencies.md#what-each-tool-does) says why the harness
needs each tool, and where it calls it.

```bash
brew install python python@3.11 git gh gitleaks node shellcheck actionlint coreutils rsync juliaup
brew install jolars/tap/fatou
```

**Without Julia code**, skip the second line: fatou checks Julia code only.

**Why.** `harness` runs on the `python3` of the `PATH`, which must be 3.11 or later. `python`
supplies a current `python3`, and `python@3.11` supplies `python3.11`, which the pre-push
[hook](concepts.md#hook) also runs. `coreutils` supplies `timeout`, which macOS does not have.
The optional tools serve one [frontend](concepts.md#frontend) or one job each. Install them when
you need that frontend or that job.

Then install Julia 1.13 or later with `juliaup`. You need Julia even if you write no Julia code:
the first install instantiates the Julia environment of the harness's
scripts, and it stops without `julia`.

**Check.** Each command prints its version: Python 3.11 or later, and Julia 1.13 or later.

```bash
python3 --version
julia --version
```

## The clone

**What it does.** These commands clone the repository and put its `bin/` directory on the `PATH`,
so that your shell finds the command `harness`.

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to your shell's start file too, for example `~/.zshrc`, so that each new
shell finds `harness`.

**Why.** Every step after this one uses `harness`, and the installed configuration names files of
the checkout.

**Check.** `harness --help` lists the verbs. A Python older than 3.11 makes `harness` stop with
exit 2, an error, and the message names the version that it found.

```bash
harness --help
```

## The profile and the model tables

**What it does.** These commands copy the example [profile](concepts.md#profile) and the example
model tables of `examples/` into your configuration directory.

```bash
mkdir -p ~/.config/research-harness
cp ~/Research/Harness/examples/profile.toml ~/.config/research-harness/profile.toml
cp ~/Research/Harness/examples/models.toml ~/.config/research-harness/models.toml
```

Then open `~/.config/research-harness/profile.toml` in an editor. Replace the example path
`/home/example` with your home directory, for example `/Users/me`, in each value. The key `harness`
then holds the absolute path of the checkout, for example `/Users/me/Research/Harness`.
[profile.md](profile.md) names each key and table, and the comments in the two files say what each
value is.

The key `repository_roots` names the directories that hold the repositories of your research
tree. Each entry must be a directory. With the example values, these commands make them:

```bash
mkdir -p ~/Research/Packages ~/Research/Experiments
```

**Why.** The profile holds every value that names a person, an institution or a machine, so the
repository holds none. The model tables give the model of each [tier](concepts.md#tier) for each
frontend.

**Check.** `harness get` prints the value of one key. It must print your home directory, not
`/home/example`.

```bash
harness get home
```

## The tree instructions

**What it does.** These commands make the directory of the
[tree instructions](concepts.md#tree-instructions), with one empty file in it. The profile key
`tree_agents` gives the path of the directory; the commands use the example value.

```bash
mkdir -p ~/Research/Environment/Agents/instructions
touch ~/Research/Environment/Agents/instructions/research-tree.md
```

**Why.** The tree instructions hold your own instruction text about your research tree.
`harness install` installs them into `~/.claude/` beside the sources of the harness. The directory
has the layout of `~/.claude/`. `adapters/claude/CLAUDE.md` imports
`instructions/research-tree.md`, so put the facts about your tree into that file. The directory
must exist, else `harness install` stops with exit 2, an error.
[architecture.md](architecture.md#the-three-layers) says how the tree instructions relate to the
harness and the profile.

**Check.** `harness get tree_agents` prints the path of the directory, and the directory holds the
file.

```bash
harness get tree_agents
ls ~/Research/Environment/Agents/instructions
```

## `harness install --apply`

**What it does.** `harness install` writes the configuration of each frontend from the sources of
the harness, the profile and the tree instructions. It needs two directories:
`~/.claude/skills/` and the OpenCode configuration directory, `$OPENCODE_CONFIG_DIR`, else
`~/.config/opencode/`. On a new machine, make them before the first install:

```bash
mkdir -p ~/.claude/skills ~/.config/opencode
```

Then run the dry run. It prints each file that it would install, and it exits 1, which means that
it would change files:

```bash
harness install
```

Read the plan, then make the change:

```bash
harness install --apply
```

**Why.** Each frontend reads its own configuration directory, never the checkout. The install
copies each [agent](concepts.md#agent), [skill](concepts.md#skill), [rule](concepts.md#rule) and
[instruction file](concepts.md#instruction-file) to the place where its frontend reads it.

The first `--apply` also instantiates the Julia environment of the scripts, so it downloads the
Julia packages of `Project.toml`. The warnings after the plan name what the install does not do
for you. For example, the Kaimon entry needs a token file, and `harness install` does not write
`~/.claude/settings.json`.

Without the OpenCode directory, `harness install` stops with exit 2, an error, and tells you to
start OpenCode once. Without `~/.claude/skills/`, it stops with exit 2 and says that the path is
not a directory.

**Check.** Run the dry run again. Its last line is `0 change(s) to make.`, and it exits 0, which
means that the installed files are the files of the sources.

```bash
harness install
```

### OpenCode

`harness install` writes the OpenCode configuration into the OpenCode configuration directory:
`opencode.jsonc` with its permission block, the plugins, the global instruction file `AGENTS.md`
and the agents. It also links the skills into `~/.agents/skills/`.
[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter.

### oh-my-pi

`harness install` writes the oh-my-pi configuration into its agent directory,
`$PI_CODING_AGENT_DIR`, else `~/.omp/agent/`: `config.yml` with the permission layer and the
models, the guard extension, `AGENTS.md`, the rules, the agents and `mcp.json`.
[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter.

## `harness settings install --apply`

**What it does.** `harness settings install` writes the sections `permissions`, `hooks` and
`sandbox` of `~/.claude/settings.json` from the settings template
`settings/settings.proposal.json`. It keeps every other key of the file. The file must exist,
else the verb stops with exit 2, an error. If it does not exist, make an empty one:

```bash
test -f ~/.claude/settings.json || echo '{}' > ~/.claude/settings.json
```

Run the dry run. It prints the difference, and it exits 1, which means that it would change the
file:

```bash
harness settings install
```

Then install the sections:

```bash
harness settings install --apply
```

**Why.** These sections are the permission settings, the hooks and the
[sandbox](concepts.md#sandbox) of Claude Code. Without them, Claude Code runs with its own
defaults: no guard hook refuses a command, and no sandbox limits a shell command. The installed
settings refuse an edit of `~/.claude/settings.json` from a [session](concepts.md#session), so
you run this verb yourself, in your own terminal. [security.md](security.md) describes what the
settings stop, and how to check a change of them.

**Check.** Run the dry run again. It prints
`the owned sections are identical — nothing to install`, and it exits 0, which means that the
file holds the sections of the template.

```bash
harness settings install
```

## `git config core.hooksPath .githooks`

**Only to change the harness.** A user who only installs the harness skips this step.

**What it does.** These commands turn on the pre-push hook of this repository, once in the
checkout:

```bash
cd ~/Research/Harness
git config core.hooksPath .githooks
```

**Why.** The pre-push hook runs the leak checks and the tests before a push to `main`.
[development.md](development.md#the-pre-push-hook) describes the hook.

**Check.** `git config core.hooksPath` in the checkout prints `.githooks`.

## The check that it worked

Run the harness's own test cases. The last line gives the number of cases, and it must say
`0 wrong`:

```bash
harness test
```

At the start of each new Claude Code session, a hook compares `~/.claude/` with the sources. A
session that starts with no warning has the installed layer of the sources. When a source changed
after the last install, the session starts with a warning about [drift](concepts.md#drift).
The [tutorial](tutorial.md) starts your first session.
