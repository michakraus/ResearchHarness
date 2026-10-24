# Setup on macOS

This page gives each step from a clean Mac to a working harness. For each step it says what the
step does, why the harness needs it, and how to check that it worked.
[setup-linux.md](setup-linux.md) is the page for Linux, with the same steps in the same order.

The commands use Homebrew. The package names and the versions that this page gives are checked
on macOS 27 on Apple silicon (`arm64`) only. On an Intel Mac, Homebrew is in `/usr/local` in place
of `/opt/homebrew`, and the launchd jobs of [The jobs](#the-jobs) put only `/opt/homebrew/bin`
on their `PATH`; that case is not checked. The steps use `~/Research/Harness` as the path
of the checkout. [Introduction](concepts.md) explains the terms that this page uses, and the
glossary there has an entry for each.

**Without Julia code.** If you write no Julia, you can skip the steps and lines that this page
marks. You still need Julia itself, because the [install](concepts.md#install) runs it once.

**Without an administrator.** The Homebrew installer needs an administrator, once. After it,
every step installs without one.

**The exit codes.** Each `harness` subcommand ends with an exit status. Exit status 0 means
that nothing would change or that the subcommand succeeded, 1 that a dry run found something to
change, and 2 an error. Each step below names the status that it expects, with its meaning.

## Check the machine

**What it does.** These commands change nothing. They print the facts of the machine that the
later steps depend on: the system, the architecture, your login shell, the groups of your
account, the tools and directories that are already there, and the `PATH` lines of your shell
startup files.

```bash
sw_vers
uname -m
echo "$SHELL"
dscl . -read "/Users/$USER" UserShell
id -Gn
xcode-select -p
command -v brew claude opencode omp julia juliaup rtk
for d in ~/.claude ~/.config/opencode ~/.omp ~/.julia ~/.juliaup ~/Research; do test -e "$d" && echo "exists $d" || echo "absent $d"; done
grep -n -E 'brew shellenv|opencode|juliaup|\.local/bin' ~/.zprofile ~/.zshrc ~/.zshenv ~/.bash_profile ~/.bashrc
```

A line that fails prints its error, and the next line runs.

**Why.** Each line answers a question of a later step:

- `sw_vers` and `uname -m` give the system and the architecture. This page covers Apple silicon,
  where `uname -m` prints `arm64`.
- `$SHELL` and the `UserShell` of `dscl` are your login shell. On macOS it is zsh unless you
  changed it, and its shell startup files are `~/.zprofile`, `~/.zshenv` and `~/.zshrc`. This
  page puts each `export` line into `~/.zshrc`; with bash, use `~/.bash_profile`.
- `id -Gn` lists the groups of your account. A member of the group `admin` is an administrator.
  Without `admin` in the list, ask an administrator to install Homebrew.
- `xcode-select -p` prints the directory of the Command Line Tools, which hold `git`, `make` and
  the compiler. Without them, it prints an error, and the Homebrew installer installs them.
- The `command -v`, `exists` and `grep` lines show what an earlier install left: Homebrew, a
  [frontend](concepts.md#frontend), a Julia, a directory of a frontend, or a `PATH` line in a
  shell startup file. Each step below installs over it or adds to it, except the juliaup
  installer, which stops when juliaup is installed already;
  [The dependencies](#the-dependencies) says what to do then. Read the output before you
  continue.

**Check.** `sw_vers` names the system, for example `ProductName: macOS` and
`ProductVersion: 27.0.1`, and `uname -m` prints `arm64`.

## The dependencies

**What it does.** These commands install every required tool that the harness calls, and the
optional tools jq and RTK. Homebrew installs all of them but Julia; the juliaup installer
installs Julia. [Dependencies](dependencies.md) lists each tool, its minimum version and what the
harness uses it for.

When `command -v brew` of [Check the machine](#check-the-machine) printed nothing, install
Homebrew first. Its installer asks for the password of an administrator, and at its end it prints
the lines that put `brew` on the `PATH`. This line runs the installer, and the second line puts
`brew` on the `PATH` of the shell that you are in:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Add the `eval` line to `~/.zprofile` too, as the installer says, so that each new shell finds
`brew`.

The Claude Code installer puts its launcher into `~/.local/bin`. Put that directory on the
`PATH`:

```bash
mkdir -p ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
```

Add the `export` line to `~/.zshrc` too, so that each new shell finds the tools.

This command installs the tools that Homebrew packages:

```bash
brew install python python@3.11 git gh node shellcheck actionlint coreutils rsync jq rtk
```

**Optional: jq and RTK.** Leave `jq` or `rtk` out of the line if you do not want it. RTK shortens
the output of shell commands: the OpenCode plugin of the harness asks `rtk` to rewrite each shell
command, and without RTK, the plugin passes each command unchanged.

**Only to push to the harness**, install gitleaks. Only the pre-push [hook](concepts.md#hook) of
the harness runs gitleaks, before a push to the harness. A user who only installs the harness
skips this line:

```bash
brew install gitleaks
```

fatou comes from the tap of its author, and Julia from the juliaup installer:

```bash
brew install jolars/tap/fatou
curl -fsSL https://install.julialang.org | sh -s -- --yes
export PATH="$HOME/.juliaup/bin:$PATH"
```

**Without Julia code**, skip the fatou line: fatou checks Julia code only.

The juliaup installer asks no question with `--yes`: with its default settings, it installs
`juliaup` and the `julia` launcher into `~/.juliaup/bin`, and the current Julia release below
`~/.julia`. It adds `~/.juliaup/bin` to the `PATH` in a block between the lines
`# >>> juliaup initialize >>>` and `# <<< juliaup initialize <<<`, in each shell startup file
that exists. The `export` line puts `~/.juliaup/bin` on the `PATH` of the shell that you are in.

**With juliaup installed already**, its installer stops with the message `It seems that Juliaup
is already installed on this system. Please remove the previous installation of Juliaup before
you try to install a new version.` and installs nothing. So when `juliaup --version` prints a
version, skip the `install.julialang.org` line, or run `juliaup self update` in its place. Run the
`export` line and the **Check** below either way.

The six Julia packages of [Dependencies](dependencies.md#julia-and-its-packages) need no command:
the first install adds them.

**Why.** Each tool has the job that [Dependencies](dependencies.md#what-each-tool-does)
describes. `harness` runs on the `python3` of the `PATH`, which must be 3.11 or later. `python`
supplies a current `python3`, and `python@3.11` supplies `python3.11`, which the pre-push hook
also runs; where `python3.11` is missing, the hook skips that run with one line, because CI runs
it. `coreutils`
supplies `timeout`, which macOS does not have. Homebrew's `rsync` replaces the `rsync` of macOS
on the `PATH`. jq is optional: the status line of Claude Code reads its data with jq, and without
it, the status line shows no values. You need Julia even if you write no Julia code: the first
install instantiates the Julia environment of the harness's scripts, and it stops without
`julia`. macOS supplies `lsof`, `launchctl` and the other system tools of
[Dependencies](dependencies.md#optional).

**Check.** Each command prints the version of one tool: Python 3.11 or later, Python 3.11, Node.js
22.3 or later, RTK 1.0.1 or later, actionlint 1.7.12 or later, fatou 0.22.0 or later, and Julia
1.13 or later.

```bash
python3 --version
python3.11 --version
node --version
jq --version
rtk --version
actionlint --version
fatou --version
juliaup --version
julia --version
```

**Without jq or RTK**, skip its line. **Without Julia code**, skip the `fatou` line.

**Only to push to the harness**, check gitleaks too. It prints its version, 8.21 or later:

```bash
gitleaks version
```

## The frontends

**What it does.** These steps install the four [frontends](concepts.md#frontend) that the
harness configures: Claude Code, OpenCode 2, oh-my-pi and Antigravity. Each frontend is optional,
as [Dependencies](dependencies.md#optional) says. Skip the subsection of each frontend that you do
not use. `harness install` writes the configuration of each frontend either way, except that of
Antigravity, which it writes once `~/.gemini/` exists. Of the frontend directories, it needs only
the OpenCode configuration directory, which the `mkdir` line of
[`harness install --apply`](#harness-install-apply) creates.

**Why.** Each frontend reads the configuration that `harness install` writes; a frontend that is
not installed reads nothing.

### Install Claude Code

This command runs the Claude Code installer:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

The installer puts the launcher at `~/.local/bin/claude`, a symbolic link to the current version
in `~/.local/share/claude/versions/`. Claude Code updates itself in the background, and
`claude update` updates it at once. The installer changes no shell startup file: it needs
`~/.local/bin` on the `PATH`, which [The dependencies](#the-dependencies) puts there.

**Check.** The command prints the version, for example `2.1.304 (Claude Code)`:

```bash
claude --version
```

### Install OpenCode 2

This command installs OpenCode 2 from the Homebrew tap of its project:

```bash
brew install anomalyco/tap/opencode-v2
```

Homebrew puts `opencode` into `/opt/homebrew/bin`, which is on the `PATH` already.
`brew upgrade opencode-v2` updates it. The formula `opencode`, without `-v2`, installs
OpenCode 1. Both versions use the command `opencode`, so install one of them only. The harness
configures OpenCode 2.

**Check.** The command prints the version, 2.0 or later:

```bash
opencode --version
```

### Install oh-my-pi

This command installs oh-my-pi from the Homebrew tap of its project:

```bash
brew install can1357/tap/omp
```

Homebrew puts `omp` into `/opt/homebrew/bin`. `brew upgrade omp` updates it.

**Check.** The command prints the version, for example `omp/18.12.3`:

```bash
omp --version
```

### Install Antigravity

Install the Antigravity desktop app from its site, <https://antigravity.google/>, and start it
once. The app keeps its data in `~/.gemini/`, and the desktop app, the IDE and the CLI `agy` read
one configuration directory, `~/.gemini/config/`. `harness install` writes the Antigravity layer
only when `~/.gemini/` exists; without it, the install gives one warning and writes no file there.

**Check.** The command prints `GEMINI-OK`:

```bash
test -d ~/.gemini && echo GEMINI-OK
```

## The sandbox of Claude Code

**What it does.** On macOS, Claude Code runs the shell commands of a
[session](concepts.md#session) in a Seatbelt [sandbox](concepts.md#sandbox), through
`sandbox-exec`. macOS supplies it, so this step installs nothing. The settings template of the
harness sets `sandbox.enabled` and `failIfUnavailable: true`. So without a working sandbox, Claude
Code does not start, instead of running the commands without a sandbox.

**Why.** The check shows that macOS lets your account make a sandbox, before the first session
depends on it.

**Check.** Run the command in a plain terminal, not in a Claude Code session: a sandbox cannot
make a second sandbox inside it. The command prints `SANDBOX-OK`:

```bash
sandbox-exec -p '(version 1)(allow default)' /usr/bin/true && echo SANDBOX-OK
```

## The clone

**What it does.** These commands clone the harness repository and put its `bin/` directory on the
`PATH`, so that your shell finds the command `harness`.

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to `~/.zshrc` too, so that each new shell finds `harness`.

**Why.** Every step after this one uses `harness`, and the installed configuration names files of
the checkout.

**Check.** `harness --help` lists the subcommands. A Python older than 3.11 makes `harness` stop
with exit status 2, an error, and the message names the version that it found.

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

The example profile works as copied. Its paths start with `~/`, which means your home directory,
and without the key `home` the harness uses the home directory of the user who runs `harness`.
Then open `~/.config/research-harness/profile.toml` in an editor and fill in the keys that name a
person, an organisation or a machine: `org`, your GitHub accounts and organisations; `leak`, the
strings that must never be in the repository, such as your user name; `launchd_prefix`, the
reverse-domain prefix of the job labels of [The jobs](#the-jobs); `memory_project`, the label of
the Claude Code memory of your [research tree](concepts.md#research-tree); and `template_host`,
the output of `hostname -s` on the template host. The template host is the machine whose Claude Code memory is the template for
the other machines. With the example value of `template_host`, the autocommit job of no machine
pushes to `main`. [profile.md](profile.md) names each key and table, and the comments in the two
files say what each value is.

Then open `~/.config/research-harness/models.toml`, and write the models that you use into it.
The example names the Claude Code models of the three [tiers](concepts.md#tier) in `[claude]`,
and these work as copied. The tables for OpenCode and oh-my-pi name example providers, such as
`provider-a/large-model`, which no frontend knows: replace them with your own models before you
use OpenCode or oh-my-pi. The table `[antigravity]` gives the Antigravity tier of each tier, and
works as copied; [Antigravity](#antigravity) below says how to add it to an older copy.
[The tables of `models.toml`](profile.md#the-tables-of-the-model-tables) says what each table
holds.

**On several machines**, the profile is the same on each of them: no key needs an edit per
machine. The branch that the autocommit pushes to differs per machine, and the key
`template_host` gives it on each machine by itself, as
[profile.md](profile.md#one-profile-for-every-machine) says. So write the profile once, keep it in
a private place, such as a private repository or a dotfiles manager, and copy it to each machine.

The key `repository_roots` names the directories that hold the repositories of your research
tree. Each entry must be a directory. With the example values, this command creates them:

```bash
mkdir -p ~/Research/Packages ~/Research/Experiments
```

The [providers](profile.md#the-providers) file is optional. Copy it only when OpenCode or oh-my-pi
uses a model server or an account beyond its built-in providers:

```bash
cp ~/Research/Harness/examples/providers.toml ~/.config/research-harness/providers.toml
```

Then replace the example providers with your own.

The [network overlay](profile.md#the-network-overlay) is optional. Copy it only when Claude Code
must reach a host that `settings/network.toml` does not name, such as the library resolver of your
institution, or must not reach a given host:

```bash
cp ~/Research/Harness/examples/network.toml ~/.config/research-harness/network.toml
```

Then replace the example hosts with your own, or empty the arrays.

**Why.** The profile holds every value that names a person, an institution or a machine, so the
repository holds none. The model tables give the model of each tier for each frontend.

**Check.** `harness get` prints the value of one key. `harness get home` must print your home
directory.

```bash
harness get home
```

## The tree instructions

**What it does.** These commands create the directory of the
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
must exist; otherwise `harness install` stops with exit status 2, an error.
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
the harness, the profile and the tree instructions. It needs two directories: the directory of the
tree instructions, which the profile key `tree_agents` names, and the OpenCode configuration
directory, `$OPENCODE_CONFIG_DIR`, or `~/.config/opencode/` if that variable is not set. Without
either, it stops with exit status 2, an error. It needs the OpenCode directory even if you do not
use OpenCode. It creates `~/.claude/` and `~/.omp/agent/` itself. On a new machine, create the two
directories before the first install; the command uses the example value of `tree_agents`:

```bash
mkdir -p ~/Research/Environment/Agents/instructions ~/.config/opencode
```

Then run `harness install` as a dry run. It prints each file that it would install, and it exits
with status 1, which means that it would change files:

```bash
harness install
```

Read the plan, then make the change:

```bash
harness install --apply
```

**Why.** Each frontend reads its own configuration directory, never the checkout. The install
copies each [agent](concepts.md#agent), [skill](concepts.md#skill), [rule](concepts.md#rule) and
[instruction file](concepts.md#instruction-file) to the place where its frontend reads it. The
first `--apply` also instantiates the Julia environment of the scripts, so it downloads the Julia
packages of `Project.toml`. The warnings after the plan name what the install does not do for
you. For example, the Kaimon entry of OpenCode needs the token file
`~/.config/kaimon/opencode-token`. Kaimon makes its key at its first start, so that warning stays
until [The Kaimon token](#the-kaimon-token), after [The jobs](#the-jobs).

**Check.** Run `harness install` again. Its last line is `0 change(s) to make.`, and it exits
with status 0, which means that the installed files are the files of the sources.

```bash
harness install
```

### Claude Code

`harness install` writes the Claude Code layer into `~/.claude/`. Its first file is
`~/.claude/settings.json`: the install writes the sections `permissions`, `hooks`, `sandbox` and
`modelSettings` of the file from the settings template `settings/settings.proposal.json`, rendered
with the profile. It keeps every other key of the file, such as the model that you choose in
Claude Code, and it keeps the old file as a backup, `settings.json.bak-<date>-<time>`. If the file
does not exist, the install creates it, with these four sections only. Then it writes the
instruction files, the agents, the skills, the rules, the commands and the hooks, and last the
stamp `~/.claude/.harness-install.json`.

These sections are the permission settings, the hooks, the [sandbox](concepts.md#sandbox), and
the [effort](concepts.md#effort) and auto-compact window of each model. Without
them, Claude Code runs with its own defaults: no guard hook refuses a command, and no sandbox
limits a shell command. An `/effort` or `/autocompact` that you type holds until the next install,
which replaces it. The settings come first, so that a new deny rule is in place before the files
that it protects. The dry run prints the diff of the four sections after the line of the file,
for example:

```text
~/.claude/settings.json            REPLACE (backup: settings.json.bak-20261010-175004)
--- ~/.claude/settings.json
+++ settings/settings.proposal.json
```

Read this diff before each `--apply`. [security.md](security.md) describes what the settings
stop, and how to check a change of them. The installed settings refuse an edit of
`~/.claude/settings.json` from a [session](concepts.md#session), so you run the install yourself,
in your own terminal. The install reads the file when it makes its plan, so do not change the
model of a running session while `--apply` runs: Claude Code writes the file then, and that change
is lost.

If `~/.claude/settings.json` is not a JSON object, is a symbolic link, or holds one of the four
sections as a value that is not an object, the install stops with exit status 2, an error, and
writes no file.

### OpenCode

`harness install` writes the OpenCode configuration into the OpenCode configuration directory:
`opencode.jsonc` with its permission block, the plugins, the global instruction file `AGENTS.md`
and the agents, and OpenCode's own copies of the instructions, the rules, the guard hooks and
the skills. It removes the links in `~/.agents/skills/` that an earlier install wrote.
[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter.

### oh-my-pi

`harness install` writes the oh-my-pi configuration into its agent directory,
`$PI_CODING_AGENT_DIR`, or `~/.omp/agent/` if that variable is not set: `harness.yml` with the
permission layer and the default model, `models.yml`, the guard extension, `AGENTS.md`, the rules,
the agents, `mcp.json`, and oh-my-pi's own copies of the instructions, the guard hooks and the
skills. It never writes oh-my-pi's own `config.yml`. oh-my-pi lets `harness.yml` override
`config.yml` only when the line
`PI_CONFIG_FILES=~/.omp/agent/harness.yml` is in `~/.omp/agent/.env`. oh-my-pi has no `env`
setting, so its shell commands get the variables of the settings template's `env` from the same
file. The install warns until the lines are there. This block adds the four lines to the end of
`~/.omp/agent/.env`. Run it once: a second run adds the lines again.

```bash
mkdir -p ~/.omp/agent
cat >> ~/.omp/agent/.env <<'EOF'
PI_CONFIG_FILES=~/.omp/agent/harness.yml
JULIA_PKG_USE_CLI_GIT=true
JULIA_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
EOF
```

[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter.

**Check.** Run `harness install` again. It prints no warning that starts with
`WARNING: oh-my-pi does not load` or with `WARNING: oh-my-pi's bash calls lack`:

```bash
harness install
```

### Antigravity

`harness install` writes the Antigravity layer into `~/.gemini/config/`: the global instruction
file `GEMINI.md`, the always-on rules and the rules, the skills, the agents, the guard hook
`hooks.json` with `guard.py` and the guard scripts, the path list, and the Kaimon entry of
`mcp_config.json`. It also writes the permission rules into the settings of the CLI `agy`,
`~/.gemini/antigravity-cli/settings.json`, and into the grants of the desktop app,
`~/.gemini/config/config.json`, each after a backup.
[components/adapters.md](components/adapters.md) describes the adapter.

**The tiers.** An Antigravity agent names a tier, never a model, so the table `[antigravity]` of
`models.toml` gives each tier of the harness one of Antigravity's tiers: `inherit`, the session
model, `flash`, `flash_lite` or `pro`. Select "Gemini 4 Argon (Medium)" in the model menu of the
app: with `large = "inherit"`, an agent of tier `large` inherits it. Without the table, the
install stops with exit status 2, an error. A copy of `examples/models.toml` has it. To an older
copy, this block adds the table of the example. Run it once: a second table stops the install too.

```bash
cat >> ~/.config/research-harness/models.toml <<'EOF'

[antigravity]
large = "inherit"
medium = "flash"
small = "flash_lite"
EOF
```

**Check.** The command prints `1`, and the dry run of `harness install` prints no error about
`[antigravity]`:

```bash
grep -c '^\[antigravity\]' ~/.config/research-harness/models.toml
harness install
```

**The permission settings of the app.** The desktop app reads no permission rule from the CLI's
`settings.json`. It keeps its grants under **General → Tool Permissions** in its settings, and
writes them to `~/.gemini/config/config.json`. `harness install` writes the permission rules of
`agy` into that file too, in `userSettings.globalPermissionGrants`, and keeps each grant that you
added. A wildcard grant for Kaimon has no effect there, neither `kaimon/*` nor `mcp(kaimon/*)`:
each Kaimon tool needs its own grant, so the install writes a rule for each Kaimon tool that the
settings template names. For a Kaimon tool that the template does not name, the app asks with the
dialog "Allow using this MCP tool?" and the name of the tool. The install leaves
`allowNonWorkspaceAccess` at its default, `false`, so a workspace below `~/Research` asks once for
read access to each parent `CLAUDE.md` that `GEMINI.md` has the model read. Approve each of these
requests once.

**Check.** Start a conversation in the app, in a workspace below `~/Research`, and paste this
prompt. Approve each request for a `CLAUDE.md`. The app asks for no grant for `kaimon/ping`, and
the reply holds Kaimon's answer:

```text
Start the subagent julia-critic with the prompt "Call the tool ping of the MCP server kaimon, and report its reply verbatim". Report its reply verbatim.
```

## Kaimon

**With Kaimon only.** **Without Julia code, skip this step.** Kaimon gives an agent a Julia
session and tools for Julia code; [Dependencies](dependencies.md#kaimon) says what it does.

**What it does.** The first command installs Kaimon as a Julia app, which puts the command
`kaimon` into `~/.julia/bin`. The second puts that directory on the `PATH` of the shell that you
are in:

```bash
julia -e 'using Pkg; Pkg.Apps.add("Kaimon")'
export PATH="$HOME/.julia/bin:$PATH"
```

Add the `export` line to `~/.zshrc` too, so that each new shell finds `kaimon`.

**Why.** The Kaimon server of [The jobs](#the-jobs) runs `~/.julia/bin/kaimon`, and the Julia
update job updates Kaimon.

**Check.** The command prints `KAIMON-OK`:

```bash
test -x ~/.julia/bin/kaimon && echo KAIMON-OK
```

## The jobs

**What it does.** The launch agents of the harness run three jobs: the Kaimon server, the Julia
update job and the autocommit job of `~/.claude`. A launch agent is a job that launchd, the
service manager of macOS, runs for your account while you are logged in.
[components/other.md](components/other.md) says what each launch agent runs.

The launch agents of the update job and the autocommit job run installed copies of two scripts of
the checkout, in `~/.local/bin`, not the scripts in the checkout: a session cannot write
`~/.local/bin`, and the jobs run outside the sandbox. These commands install the two copies:

```bash
install -m 755 ~/Research/Harness/launchagents/claude-autocommit ~/.local/bin/
install -m 755 ~/Research/Harness/scripts/julia-update.jl ~/.local/bin/
```

After you change one of the two scripts in the checkout, run its line again.

These commands render each launch agent with the profile into `~/Library/LaunchAgents/`, under
its label, and create the log directories of the jobs. `p` holds the profile key
`launchd_prefix`; the commands of this step after it use `p` too, so run them in the same shell:

```bash
p=$(harness get launchd_prefix)
mkdir -p ~/Library/LaunchAgents ~/Library/Logs/kaimon ~/Library/Logs/julia-update ~/Library/Logs/claude-autocommit
for j in kaimon julia-update claude-autocommit; do harness render ~/Research/Harness/launchagents/"$j".plist > ~/Library/LaunchAgents/"$p.$j".plist; done
plutil -lint ~/Library/LaunchAgents/"$p".*.plist
```

`plutil -lint` prints `OK` after the path of each file.

**With a git repository in `~/.claude` only.** The autocommit job commits in `~/.claude/` and
pushes to the `origin` of that repository, so `~/.claude` must be a git repository with a remote
`origin`. No step of this page makes it one. The first command prints `REPOSITORY-OK` when
`~/.claude` is the top directory of its own repository, not a directory inside another repository.
The second prints the URL of the remote:

```bash
test "$(git -C ~/.claude rev-parse --show-toplevel)" = "$HOME/.claude" && echo REPOSITORY-OK
git -C ~/.claude remote get-url origin
```

When the first prints no `REPOSITORY-OK`, or the second prints an error, skip the next command:
launchd would start the autocommit job, and the job would fail. Otherwise, this command loads the
launch agent of the autocommit job:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/"$p".claude-autocommit.plist
```

**With Kaimon only.** The server runs `~/.julia/bin/kaimon`, and the update job stops with an
error without Kaimon. [Kaimon](#kaimon) installs it. With Kaimon in `~/.julia/bin`, these commands
load the launch agents of the server and the update job:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/"$p".kaimon.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/"$p".julia-update.plist
```

To load a launch agent again after a change of its template or of the profile, render it again,
then unload it and load it:

```bash
launchctl bootout "gui/$(id -u)/$p.kaimon"
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/"$p".kaimon.plist
```

**Why.** launchd loads each launch agent of `~/Library/LaunchAgents/` again at each login, so the
jobs need this step only once. The server must run before the agents of OpenCode, oh-my-pi and
Antigravity can use Kaimon. launchd has no equivalent of lingering: a launch agent runs only while
you are logged in.

**Check.** The command prints `LOADED` when the launch agent of the autocommit job is loaded, and
an error when you skipped it:

```bash
launchctl list "$p".claude-autocommit >/dev/null && echo LOADED
```

With Kaimon, each command prints `LOADED`:

```bash
launchctl list "$p".kaimon >/dev/null && echo LOADED
launchctl list "$p".julia-update >/dev/null && echo LOADED
```

## The Kaimon token

**With Kaimon and OpenCode or Antigravity only.** Skip this step without Kaimon, or without both
frontends.

**What it does.** In its strict mode, Kaimon refuses a request that does not carry one of its API
keys. Kaimon keeps its mode and its keys in `~/.config/kaimon/config.json`, and writes that file
at its first start: the server of [The jobs](#the-jobs) starts with `--headless`, and then Kaimon
writes a configuration in the strict mode with one new key, `kaimon_` followed by 40 hexadecimal
digits. `kaimon` started in a terminal asks the questions of its setup wizard instead. The Kaimon
entry of OpenCode sends a key in the header `Authorization: Bearer`, and it reads the key from the
file `~/.config/kaimon/opencode-token`. These commands write the first key of the configuration
into that file, the key alone, with mode 600. They write a temporary file first, and move it into
place only when the key is not empty. Without `config.json`, or without a key in it, they leave no
token file, and the dry run keeps its warning:

```bash
(umask 077; python3 -c 'import json, os; print(json.load(open(os.path.expanduser("~/.config/kaimon/config.json")))["api_keys"][0], end="")' > ~/.config/kaimon/opencode-token.new) && test -s ~/.config/kaimon/opencode-token.new && mv ~/.config/kaimon/opencode-token.new ~/.config/kaimon/opencode-token
rm -f ~/.config/kaimon/opencode-token.new
```

**Why.** Without the file, OpenCode sends no key, and Kaimon answers each request with 401. The
settings do not let a session read either file. Antigravity expands no shell form in its MCP
configuration, so `harness install` writes the key itself into `~/.gemini/config/mcp_config.json`,
with mode 600; without the file, the install writes no Kaimon entry there and warns. So with
Antigravity, run `harness install --apply` once more after this step.

**Check.** The first command prints `600 47`: the mode, and the 47 characters of the key. The dry
run prints no warning about `~/.config/kaimon/opencode-token`:

```bash
stat -f '%Lp %z' ~/.config/kaimon/opencode-token
harness install
```

## `git config core.hooksPath .githooks`

**Only to change the harness.** A user who only installs the harness skips this step.

**What it does.** These commands turn on the pre-push hook of this repository, once in the
checkout:

```bash
cd ~/Research/Harness
git config core.hooksPath .githooks
```

**Why.** The pre-push hook runs the leak checks and the tests before a push to `main`, and
`harness leaks` before a push of any other branch. Its leak checks run gitleaks.
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

Then check the whole machine in one command. `harness doctor` checks the machine, the tools, the
profile, the install and the jobs, read-only, and prints one line for each check: `PASS`, `WARN`,
`FAIL` or `SKIP`, the name and a detail. A `FAIL` line names the section of this page that fixes
it. It exits with status 0 when no check fails, and 1 when one fails. A `WARN`, for example for a
missing optional tool or a warning of the install, does not count as a failure. On macOS, it
also checks for iTerm2, which the hook `cc-status` uses, and gives a `WARN` without it. Run it in
a plain terminal: in a Claude Code session, the sandbox refuses some of its commands, and those
checks are `SKIP`. `--full` also runs `harness test`.

```bash
harness doctor
```

## Dotfiles (optional)

**Only for several machines.** A user who sets up one machine, or who keeps the profile in a
place of their own, skips this step. The rest of the setup works without it.

**What it does.** The dotfiles kit of the harness, `examples/dotfiles/`, is a chezmoi source with
placeholder data. You copy it into a private repository with `harness dotfiles-kit`, and chezmoi
applies that repository on each machine. It keeps the profile, the model tables and the commit of
the harness the same on each machine, and each machine applies a change only when your key
signed it. [The `dotfiles` command](dotfiles-command.md) gives the steps, from the private copy
to a new machine.

**Why.** On several machines, the profile is the same on each of them, as
[The profile and the model tables](#the-profile-and-the-model-tables) says, and a copy by hand
can differ. The kit applies one reviewed source on each machine.

The kit needs chezmoi:

```bash
brew install chezmoi
```

**Check.** `dotfiles check`, in a plain terminal, ends with a count line that says `0 FAIL`.
