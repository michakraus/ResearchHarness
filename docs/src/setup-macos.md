# Setup on macOS

This page gives each step from a clean Mac to a working harness. [Installation](../README.md#installation)
gives the short form of the same steps. [setup-linux.md](setup-linux.md) is the page for Linux.

The steps use `~/Research/Harness` as the path of the checkout. The profile key `harness` holds
the absolute path of the checkout, for example `/Users/me/Research/Harness`.

## The dependencies

[Dependencies](../README.md#dependencies) lists each tool, its minimum version and what the
harness uses it for. [tools.md](tools.md) says what each tool does, why the harness needs it, and
where the harness calls it.

Homebrew supplies most of the required tools on macOS. These commands install them:

```bash
brew install python python@3.11 git gh gitleaks node shellcheck actionlint coreutils rsync juliaup
brew install jolars/tap/fatou
```

`harness` runs on the `python3` of the `PATH`, which must be 3.11 or later. `python` supplies a
current `python3`, and `python@3.11` supplies `python3.11`, which the pre-push hook also runs.
`coreutils` supplies `timeout`, which macOS does not have. Then install Julia 1.13 or later with
`juliaup`. The optional tools serve one frontend or one job each. Install them when you need that
frontend or that job.

## The clone

Clone the repository:

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
```

Put its `bin/` directory on the `PATH`. Add the same line to your shell's start file, for example
`~/.zshrc`, so that each new shell finds `harness`:

```bash
export PATH="$HOME/Research/Harness/bin:$PATH"
```

`harness --help` must now list the verbs. A Python older than 3.11 makes `harness` stop with
exit 2 and the version that it found.

## The profile and the model tables

The profile holds every value that names a person, an institution or a machine. The model tables
hold the model of each tier for each frontend. The repository holds an example of each in
`examples/`. Copy the two examples, then write your values into them:

```bash
mkdir -p ~/.config/research-harness
cp ~/Research/Harness/examples/profile.toml ~/.config/research-harness/profile.toml
cp ~/Research/Harness/examples/models.toml ~/.config/research-harness/models.toml
```

In the profile, replace the example path `/home/example` with your home directory, for example
`/Users/me`, in each value. The key `harness` then holds the absolute path of the checkout. Each
entry of `repository_roots` must be a directory, else `harness leaks` stops with exit 2.
[profile.md](profile.md) names each key and table, and the verbs that read it. The comments in
the two examples say what each value is.

## The tree instructions

The tree instructions are a directory of private instruction text about your own research tree.
`harness install` installs them into `~/.claude/` beside the sources of this repository. The
profile key `tree_agents` gives the absolute path of the directory. The directory must exist,
else `harness install` stops with exit 2.

The directory has the layout of `~/.claude/`. `adapters/claude/CLAUDE.md` imports
`instructions/research-tree.md`, so put the facts about your tree into that file. A minimal
directory holds that one file. With the example value of `tree_agents`, these commands make it:

```bash
mkdir -p ~/Research/Environment/Agents/instructions
touch ~/Research/Environment/Agents/instructions/research-tree.md
```

[architecture.md](architecture.md#the-three-layers) says how the tree instructions relate to the
harness and the profile.

## `harness install --apply`

`harness install` needs two directories: `~/.claude/skills/` and the OpenCode configuration
directory, `$OPENCODE_CONFIG_DIR`, else `~/.config/opencode/`. On a new machine, make them before
the first install:

```bash
mkdir -p ~/.claude/skills ~/.config/opencode
```

Without the OpenCode directory, `harness install` stops with exit 2 and tells you to start
OpenCode once. Without `~/.claude/skills/`, it stops with exit 2 and says that the path is not a
directory.

Then run the dry run. It prints each file that it would install and exits 1:

```bash
harness install
```

Read the plan, then make the change:

```bash
harness install --apply
```

The first `--apply` also instantiates the Julia environment of the scripts, so it downloads the
Julia packages of `Project.toml`. The warnings after the plan name what the install does not do
for you. For example, the Kaimon entry needs a token file, and `harness install` does not write
`~/.claude/settings.json`.

### OpenCode

`harness install` writes the OpenCode configuration into the OpenCode configuration directory:
`opencode.jsonc` with its permission block, the plugins, the global instruction file `AGENTS.md`
and the agents. It also links the skills into `~/.agents/skills/`. [architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters)
describes the adapter.

### oh-my-pi

`harness install` writes the oh-my-pi configuration into its agent directory,
`$PI_CODING_AGENT_DIR`, else `~/.omp/agent/`: `config.yml` with the permission layer and the
models, the guard extension, `AGENTS.md`, the rules, the agents and `mcp.json`.
[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter.

## `harness settings install --apply`

`harness settings install` writes the sections `permissions`, `hooks` and `sandbox` of
`~/.claude/settings.json` from the settings template. It keeps every other key of the file. The
file must exist, else the verb stops with exit 2. If it does not exist, make an empty one:

```bash
test -f ~/.claude/settings.json || echo '{}' > ~/.claude/settings.json
```

Run the dry run. It prints the difference and exits 1:

```bash
harness settings install
```

Then install the sections:

```bash
harness settings install --apply
```

The installed settings refuse an edit of `~/.claude/settings.json` from a session. So you run this
verb yourself, in your own terminal. [security.md](security.md) describes what the settings
stop, and how to check a change of them.

## `git config core.hooksPath .githooks`

The pre-push hook of this repository runs the leak checks and the tests before a push to `main`.
Enable it once in the checkout:

```bash
cd ~/Research/Harness
git config core.hooksPath .githooks
```

[development.md](development.md#the-pre-push-hook) describes the hook. Do this step when you
change the harness and push. A user who only installs the harness can skip it.

## The check that it worked

Run the dry run of the install again. It must report `0 change(s) to make.` and exit 0:

```bash
harness install
```

The dry run of the settings must exit 0 too:

```bash
harness settings install
```

Then run the harness's own test cases. The last line gives the number of cases, and it must say
`0 wrong`:

```bash
harness test
```

At the start of each new Claude Code session, the `SessionStart` hook compares `~/.claude/` with
the sources. A session that starts with no warning has the installed layer of the sources.
