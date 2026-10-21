# Setup on Linux

This page gives each step from a clean Linux machine to a working harness. For each step it says
what the step does, why the harness needs it, and how to check that it worked.
[setup-macos.md](setup-macos.md) is the page for macOS, with the same steps in the same order.
This page adds one section at its end, [A machine reached over SSH](#a-machine-reached-over-ssh).

The commands are for Debian and Ubuntu, with `apt-get`. The package names and the versions that
this page gives are checked on Ubuntu 26.04 only; other distributions and releases are not
checked. The commands run on the two architectures `x86_64` and `aarch64` (64-bit Arm). The steps
use `~/Research/Harness` as the path of the checkout. [Introduction](concepts.md) explains the
terms that this page uses, and the glossary there has an entry for each.

**Without Julia code.** If you write no Julia, you can skip the steps and lines that this page
marks. You still need Julia itself, because the [install](concepts.md#install) runs it once.

**Without an administrator.** The `apt-get` lines and the lingering of [The jobs](#the-jobs)
need an administrator. Every tool that goes into `~/.local/bin` installs without one.

**The exit codes.** Each `harness` subcommand ends with an exit status. Exit status 0 means
that nothing would change or that the subcommand succeeded, 1 that a dry run found something to
change, and 2 an error. Each step below names the status that it expects, with its meaning.

## Check the machine

**What it does.** These commands change nothing. They print the facts of the machine that the
later steps depend on: the system, the architecture, the settings for user namespaces, your login
shell, the systemd user manager, the groups of your account, the tools and directories that are
already there, and the versions that `apt-get` would install.

```bash
. /etc/os-release; echo "$PRETTY_NAME"
uname -m
uname -r
sysctl kernel.apparmor_restrict_unprivileged_userns kernel.unprivileged_userns_clone
echo "$SHELL"
getent passwd "$USER" | cut -d: -f7
systemctl --user is-system-running
loginctl show-user "$USER" -p Linger
id -nG
command -v claude opencode omp julia juliaup rtk
for d in ~/.claude ~/.config/opencode ~/.omp ~/.julia ~/.juliaup ~/Research; do test -e "$d" && echo "exists $d" || echo "absent $d"; done
grep -n -E 'opencode|juliaup|\.local/bin' ~/.bashrc ~/.profile ~/.bash_profile ~/.zshrc
apt-cache policy python3 git gh nodejs npm shellcheck rsync curl jq bubblewrap socat lsof gitleaks | grep -E '^[a-z0-9]|Installed|Candidate'
busctl --user status org.freedesktop.secrets >/dev/null 2>&1 && echo SECRETS-OK
```

A line that fails prints its error, and the next line runs.

**Why.** Each line answers a question of a later step:

- The system and the architecture select the commands. This page covers Ubuntu 26.04 on `x86_64`
  and `aarch64`. With another value of `uname -m`, the release files of
  [The dependencies](#the-dependencies) do not exist; install those tools from their own sites.
- The two `sysctl` keys decide whether the Claude Code [sandbox](concepts.md#sandbox) can start.
  `kernel.unprivileged_userns_clone = 0` means that the kernel does not let an unprivileged user
  create user namespaces. `kernel.apparmor_restrict_unprivileged_userns = 1` means that AppArmor
  blocks user namespaces for each program that AppArmor does not explicitly allow. Then the check of
  [The sandbox of Claude Code](#the-sandbox-of-claude-code) can fail, and Claude Code does not
  start. A key that does not exist sets no limit. Only an administrator can fix this, with a
  change of the kernel or AppArmor settings.
- `$SHELL` and the shell in the `getent` line are your login shell. The OpenCode installer writes
  its `PATH` lines into the first shell startup file of that shell that exists, for example
  `~/.bashrc` for bash or `~/.zshrc` for zsh, when its directory is not on the `PATH`. The
  juliaup installer writes its `PATH` block into each of `~/.bashrc`, `~/.profile`,
  `~/.bash_profile`, `~/.bash_login` and `~/.zshrc` that exists, whatever the login shell.
- `systemctl --user is-system-running` prints `running` when the systemd user manager runs, or
  `degraded` when it runs and a unit failed; [The jobs](#the-jobs) need it. `Linger=no` means
  that the user manager stops at your last logout.
- `id -nG` lists the groups of your account. On Ubuntu, a member of the group `sudo` may run
  `sudo`, so you are an administrator. Without `sudo` in the list, ask an administrator to run the
  lines of this page that start with `sudo`.
- The `command -v`, `exists` and `grep` lines show what an earlier install left: a
  [frontend](concepts.md#frontend), a Julia, a directory of a frontend, or a `PATH` line in a
  shell startup file. Each step below installs over it or adds to it, except the juliaup
  installer, which stops when juliaup is installed already;
  [The dependencies](#the-dependencies) says what to do then. Read the output before you
  continue.
- The `apt-cache` line gives the version that `apt-get` installs, under `Candidate`, and the
  version that is there, under `Installed`. Compare each with the minimum of
  [Dependencies](dependencies.md).
- `SECRETS-OK` means that a Secret Service provider, such as GNOME Keyring, is available, as at
  the desktop of the machine. Over SSH, the line prints nothing;
  [A machine reached over SSH](#a-machine-reached-over-ssh) says what follows.

**Check.** The first line names the system, for example `Ubuntu 26.04.1 LTS`, and the second line
prints `x86_64` or `aarch64`.

## The dependencies

**What it does.** These commands install every required tool that the harness calls, the two
tools of the sandbox, and the optional tools jq and RTK. `apt-get` installs each tool whose
Ubuntu 26.04 package meets the minimum of [Dependencies](dependencies.md), and also bubblewrap,
socat, lsof and jq. These two lines need an administrator:

```bash
sudo apt-get update
sudo apt-get install -y python3 git gh nodejs npm shellcheck coreutils rsync curl jq bubblewrap socat lsof
```

The tools of `~/.local/bin` need no administrator. First put that directory on the `PATH`:

```bash
mkdir -p ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
```

Add the `export` line to your shell startup file too, `~/.bashrc` for bash or `~/.zshrc` for
zsh, so that each new shell finds the tools.

gitleaks and RTK come from their releases, which have one file for each architecture. This block
sets the names of the two files for the architecture of the machine. On an architecture other
than `x86_64` and `aarch64`, it prints a message, sets no name, and the download lines below
download nothing:

```bash
case "$(uname -m)" in
  x86_64)  gl=gitleaks_8.30.1_linux_x64.tar.gz;   rt=rtk-x86_64-unknown-linux-musl.tar.gz ;;
  aarch64) gl=gitleaks_8.30.1_linux_arm64.tar.gz; rt=rtk-aarch64-unknown-linux-gnu.tar.gz ;;
  *)       gl=; rt=; echo "This page covers x86_64 and aarch64, not $(uname -m): install gitleaks and RTK from their own sites." ;;
esac
```

**Optional: RTK.** RTK shortens the output of shell commands. The OpenCode plugin of the harness
asks `rtk` to rewrite each shell command; without RTK, the plugin passes each command unchanged.
These lines download the release 1.0.1 and its checksum file `checksums.txt`, check the release
against the checksum, and only then install `rtk` into `~/.local/bin`:

```bash
d=$(mktemp -d); cd "$d"
v=1.0.1
[ -n "$rt" ] && curl -fsSL -O "https://github.com/rtk-ai/rtk/releases/download/v$v/$rt" -O "https://github.com/rtk-ai/rtk/releases/download/v$v/checksums.txt"
grep " $rt\$" checksums.txt | sha256sum -c - && tar -xzf "$rt" rtk && install -m 755 rtk ~/.local/bin/
cd ~
```

**Only to push to the harness**, install gitleaks. Only the pre-push [hook](concepts.md#hook) of
the harness runs gitleaks, before a push to the harness. A user who only installs the harness
skips these lines. They download the release 8.30.1 and its checksum file
`gitleaks_8.30.1_checksums.txt`, check the release against the checksum, and only then install
`gitleaks` into `~/.local/bin`:

```bash
d=$(mktemp -d); cd "$d"
v=8.30.1
[ -n "$gl" ] && curl -fsSL -O "https://github.com/gitleaks/gitleaks/releases/download/v$v/$gl" -O "https://github.com/gitleaks/gitleaks/releases/download/v$v/gitleaks_${v}_checksums.txt"
grep " $gl\$" "gitleaks_${v}_checksums.txt" | sha256sum -c - && tar -xzf "$gl" gitleaks && install -m 755 gitleaks ~/.local/bin/
cd ~
```

A failed `sha256sum` stops its line, and nothing is installed. To update RTK or gitleaks, change
its version in the `case` block and in `v=`, and run the lines again.

actionlint, fatou and Julia come from their own installers, which their projects give. Each
installer selects the file for the architecture itself:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) latest ~/.local/bin
curl --proto '=https' --tlsv1.2 -sSf https://fatou.dev/install | sh
curl -fsSL https://install.julialang.org | sh -s -- --yes
export PATH="$HOME/.juliaup/bin:$PATH"
```

**Without Julia code**, skip the fatou line: fatou checks Julia code only.

The actionlint line installs `actionlint` into `~/.local/bin`. The fatou installer installs
`fatou` into `~/.local/bin`, and checks the checksum of its download when the release publishes
one. The juliaup installer
asks no question with `--yes`: with its default settings, it installs `juliaup` and the `julia`
launcher into `~/.juliaup/bin`, and the current Julia release below `~/.julia`. It adds
`~/.juliaup/bin` to the `PATH` in a block between the lines `# >>> juliaup initialize >>>` and
`# <<< juliaup initialize <<<`, in each of `~/.bashrc`, `~/.profile`, `~/.bash_profile`,
`~/.bash_login` and `~/.zshrc` that exists. The `export` line puts `~/.juliaup/bin` on the `PATH`
of the shell that you are in.

**With juliaup installed already**, its installer stops with the message `It seems that Juliaup
is already installed on this system. Please remove the previous installation of Juliaup before
you try to install a new version.` and installs nothing. So when `juliaup --version` prints a
version, skip the `install.julialang.org` line, or run `juliaup self update` in its place. Run the
`export` line and the **Check** below either way.

The six Julia packages of
[Dependencies](dependencies.md#julia-and-its-packages) need no command: the first install adds
them.

**Why.** Each tool has the job that [Dependencies](dependencies.md#what-each-tool-does)
describes. Ubuntu 26.04 packages Python 3.14 and Node.js 22.22, which meet their minimums, but
gitleaks only in version 8.16.0, below the minimum 8.21. So gitleaks comes from its release. A
release of a distribution can package an older version than the minimum that Dependencies gives.
Then install that tool from its own site. The pre-push hook also runs `python3.11`; where
`python3.11` is missing, the hook skips that run with one line, because CI runs it. bubblewrap and
socat are the tools of [The sandbox of Claude Code](#the-sandbox-of-claude-code). The Julia update
job of [The jobs](#the-jobs) calls `lsof`. jq is optional: the status line of Claude Code reads
its data with jq, and without it, the status line shows no values. You need Julia even if you
write no Julia code: the first install instantiates the Julia environment of the harness's
scripts, and it stops without `julia`.

**Check.** The first command prints the version of each package that `apt-get` installed. Each
command after it prints the version of one tool: Python 3.11 or later, Node.js 22.3 or later (or
20.16 or later in 20.x), RTK 1.0.1, actionlint 1.7.12 or later, fatou 0.22.0 or later, and Julia
1.13 or later.

```bash
dpkg-query -W python3 git gh nodejs npm shellcheck coreutils rsync curl jq bubblewrap socat lsof
python3 --version
node --version
jq --version
rtk --version
actionlint --version
fatou --version
juliaup --version
julia --version
```

**Without RTK**, skip the `rtk` line. **Without Julia code**, skip the `fatou` line.

**Only to push to the harness**, check gitleaks too. It prints its version, 8.21 or later:

```bash
gitleaks version
```

## The frontends

**What it does.** These steps install the three [frontends](concepts.md#frontend) that the
harness configures: Claude Code, OpenCode 2 and oh-my-pi. Each frontend is optional, as
[Dependencies](dependencies.md#optional) says. Skip the subsection of each frontend that you do
not use. `harness install` writes the configuration of all three either way. Of the frontend
directories, it needs only the OpenCode configuration directory, which the `mkdir` line of
[`harness install --apply`](#harness-install-apply) creates.

**Why.** Each frontend reads the configuration that `harness install` writes; a frontend that is
not installed reads nothing. The installers below are the ones that the projects give, and each
selects the file for the architecture of the machine itself.

### Install Claude Code

This command runs the Claude Code installer:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

The installer puts the launcher at `~/.local/bin/claude`, a symbolic link to the current version
in `~/.local/share/claude/versions/`. Claude Code updates itself in the background, and
`claude update` updates it at once. The installer changes no shell startup file: it needs
`~/.local/bin` on the `PATH`, which [The dependencies](#the-dependencies) puts there.

**Check.** The command prints the version, for example `2.1.303 (Claude Code)`:

```bash
claude --version
```

**Optional: the signed manifest.** On Linux, the Claude Code binaries are not code-signed. Each
release has a file `manifest.json` with the SHA-256 checksum of each binary, and a signature of
that file made with the release key of Anthropic. These commands check the installed
version against the manifest. They need `gpg`, from the package `gnupg`, and jq:

```bash
d=$(mktemp -d); cd "$d"
curl -fsSL https://downloads.claude.ai/keys/claude-code.asc | gpg --import
gpg --fingerprint security@anthropic.com
REPO=https://downloads.claude.ai/claude-code-releases
VERSION=$(claude --version | cut -d' ' -f1)
curl -fsSLO "$REPO/$VERSION/manifest.json"
curl -fsSLO "$REPO/$VERSION/manifest.json.sig"
gpg --verify manifest.json.sig manifest.json
jq -r '.platforms[].checksum' manifest.json | grep -qFx "$(sha256sum < ~/.local/share/claude/versions/"$VERSION" | cut -d' ' -f1)" && echo CHECKSUM-OK
cd ~
```

The fingerprint must be `31DD DE24 DDFA B679 F42D  7BD2 BAA9 29FF 1A7E CACE`. `gpg --verify`
must print `Good signature from "Anthropic Claude Code Release Signing <security@anthropic.com>"`;
its warning that the key is not certified with a trusted signature is expected for a key that you
have just imported. The last line prints `CHECKSUM-OK` when the checksum of the installed binary
is one of the checksums of the manifest. The manifests of releases before 2.1.89 have no
signature.

### Install OpenCode 2

This command runs the OpenCode 2 installer:

```bash
curl -fsSL https://opencode.ai/v2/install | bash
```

The installer puts `opencode` into `~/.opencode/bin`. When that directory is not on the `PATH`, it
adds two lines to the first shell startup file of your login shell that exists, for example
`~/.bashrc` for bash or `~/.zshrc` for zsh: the line `# opencode`, and the line
`export PATH=/home/me/.opencode/bin:$PATH` with your home directory in place of
`/home/me`. Its option `--no-modify-path` leaves the shell startup files as they are.
`opencode upgrade` updates it. This command puts the directory on the `PATH` of the shell that you
are in:

```bash
export PATH="$HOME/.opencode/bin:$PATH"
```

The command `curl -fsSL https://opencode.ai/install | bash`, without `v2`, installs OpenCode 1
only. Both versions use the command `opencode` and the directory `~/.opencode/bin`, so install
one of them only. The harness configures OpenCode 2.

**Check.** The command prints the version, 2.0 or later:

```bash
opencode --version
```

### Install oh-my-pi

This command runs the oh-my-pi installer, with its option `--binary`:

```bash
curl -fsSL https://omp.sh/install | sh -s -- --binary
```

The installer downloads the prebuilt binary for the machine, checks its SHA-256 checksum, and
only then puts `omp` into `~/.local/bin`, or into `$PI_INSTALL_DIR` when that variable is set.
Without `--binary`, an installer that finds `bun` uses `bun` to install oh-my-pi into the
directory of `bun` instead. The installer changes no shell startup file: it needs `~/.local/bin`
on the `PATH`, which [The dependencies](#the-dependencies) puts there. `omp update` updates it.

**Check.** The command prints the version, for example `omp/18.12.3`:

```bash
omp --version
```

## The sandbox of Claude Code

**What it does.** On Linux, Claude Code runs the shell commands of a
[session](concepts.md#session) in a bubblewrap (`bwrap`) sandbox, and it also needs socat.
The settings template of the harness sets `sandbox.enabled` and `failIfUnavailable: true`. So
without a working sandbox, Claude Code does not start, instead of running the commands without a
sandbox. [The dependencies](#the-dependencies) installs both tools.

**Why.** bubblewrap makes the sandbox from user namespaces of the kernel, and the settings of a
machine can refuse them to a user. Then `bwrap` fails, and Claude Code does not start. The cause
is in the machine's settings for unprivileged user namespaces, which only an administrator can
change;
[Check the machine](#check-the-machine) prints them.

**Check.** The first command prints the paths of the two tools. The second makes a sandbox and
prints `BWRAP-OK`:

```bash
command -v bwrap socat
bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid true && echo BWRAP-OK
```

## The clone

**What it does.** These commands clone the harness repository and put its `bin/` directory on the
`PATH`, so that your shell finds the command `harness`.

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to your shell startup file too, `~/.bashrc` for bash or `~/.zshrc` for
zsh, so that each new shell finds `harness`.

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
strings that must never be in the repository, such as your user name; `memory_project`, the label
of the Claude Code memory of your research tree; and `template_host`, the output of `hostname -s`
on the template host. The template host is the machine whose Claude Code memory is the template
for the other machines. With the example value of `template_host`, the autocommit job of no
machine pushes to `main`. `launchd_prefix` names the launchd jobs of macOS, and nothing on Linux
reads it: fill it in when the same profile also serves a Mac. [profile.md](profile.md) names each
key and table, and the comments in the two files say what each value is.

Then open `~/.config/research-harness/models.toml`, and write the models that you use into it.
The example names the Claude Code models of the three [tiers](concepts.md#tier) in `[claude]`,
and these work as copied. The tables for OpenCode and oh-my-pi name example providers, such as
`provider-a/large-model`, which no frontend knows: replace them with your own models before you
use OpenCode or oh-my-pi. [The tables of `models.toml`](profile.md#the-tables-of-the-model-tables)
says what each table holds.

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
limits a shell command. On Linux, the `sandbox` section needs the tools of
[The sandbox of Claude Code](#the-sandbox-of-claude-code). An `/effort` or `/autocompact` that you
type holds until the next install, which replaces it. The settings come first, so that a new deny
rule is in place before the files that it protects. The dry run prints the diff of the four
sections after the line of the file, for example:

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
[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter. The
settings template keeps a Claude Code session from writing to `~/.opencode/bin`, where the
OpenCode installer puts the program, and to `~/.local/bin`.

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

Add the `export` line to your shell startup file too, `~/.bashrc` for bash or `~/.zshrc` for
zsh, so that each new shell finds `kaimon`.

**Why.** The Kaimon server of [The jobs](#the-jobs) runs `~/.julia/bin/kaimon`, and the Julia
update job updates Kaimon.

**Check.** The command prints `KAIMON-OK`:

```bash
test -x ~/.julia/bin/kaimon && echo KAIMON-OK
```

## The jobs

**What it does.** The `systemd --user` units of the harness run three jobs: the Kaimon server, the
Julia update job and the autocommit job of `~/.claude`.
[components/other.md](components/other.md) says what each unit runs.

The units of the update job and the autocommit job run installed copies of two scripts of the
checkout, in `~/.local/bin`, not the scripts in the checkout: a session cannot write
`~/.local/bin`, and the jobs run outside the sandbox. These commands install the two copies:

```bash
install -m 755 ~/Research/Harness/launchagents/claude-autocommit ~/.local/bin/
install -m 755 ~/Research/Harness/scripts/julia-update.jl ~/.local/bin/
```

After you change one of the two scripts in the checkout, run its line again.

These commands render each unit with the profile into `~/.config/systemd/user/`:

```bash
mkdir -p ~/.config/systemd/user
for u in kaimon.service julia-update.service julia-update.timer claude-autocommit.service claude-autocommit.timer; do harness render ~/Research/Harness/systemd/"$u" > ~/.config/systemd/user/"$u"; done
systemctl --user daemon-reload
```

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
the timer would start the autocommit job, and the job would fail. Otherwise, this command enables
the timer of the autocommit job:

```bash
systemctl --user enable --now claude-autocommit.timer
```

**With Kaimon only.** The server runs `~/.julia/bin/kaimon`, and the update job stops with an
error without Kaimon. [Kaimon](#kaimon) installs it. With Kaimon in `~/.julia/bin`, this command
enables the server and the timer of the update job:

```bash
systemctl --user enable --now kaimon.service julia-update.timer
```

Then an administrator turns on lingering for your account. When your account may run `sudo`, run
this line in your own account:

```bash
sudo loginctl enable-linger "$USER"
```

When your account may not run `sudo`, an administrator runs this block in the administrator's own
account, where `$USER` names the administrator. First edit the line `account=me`: replace `me`
with the name of your account, which `id -un` prints in your account.

```bash
account=me
sudo loginctl enable-linger "$account"
```

**Why.** Without lingering, the systemd user manager starts at your first login and stops at your
last logout, and the units stop with it. Lingering keeps the server and the timers running when
no one is logged in.

**Check.** The first command prints `Linger=yes`. The second lists the timer of the autocommit
job when you enabled it, and prints nothing when you skipped it:

```bash
loginctl show-user "$USER" -p Linger
systemctl --user list-timers --no-pager | grep claude-autocommit
```

With Kaimon, the first command prints `active`, and the second lists the timer of the update job:

```bash
systemctl --user is-active kaimon.service
systemctl --user list-timers --no-pager | grep julia-update
```

## The Kaimon token

**With Kaimon and OpenCode only.** Skip this step without one of them.

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
settings do not let a session read either file.

**Check.** The first command prints `600 47`: the mode, and the 47 characters of the key. The dry
run prints no warning about `~/.config/kaimon/opencode-token`:

```bash
stat -c '%a %s' ~/.config/kaimon/opencode-token
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
`harness leaks` before a push of any other branch. Its leak checks run gitleaks. [development.md](development.md#the-pre-push-hook) describes the hook.

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
missing optional tool or a warning of the install, does not count as a failure. Run it in a
plain terminal: in a Claude Code session, the sandbox refuses some of its commands, and those
checks are `SKIP`. `--full` also runs `harness test`.

```bash
harness doctor
```

## A machine reached over SSH

In an SSH session, no Secret Service provider, such as GNOME Keyring, is available, so `gh` and
`glab` cannot store their tokens in the system keyring. They keep them in files: `gh` in
`~/.config/gh/hosts.yml`, and `glab` in `~/.config/glab-cli/config.yml`, when you answer no to
its question about a keyring. The settings do not let a session read either file. `gh` and
`glab` run outside the sandbox, so they still read their own files.

Over SSH, `gh` logs in with a device code: it prints a code and a URL, which you open on another
machine.

```bash
gh auth login --hostname github.com --git-protocol https
```

In Claude Code, `/login` prints a URL. Open it on another machine, and paste the code that it
gives back into Claude Code.

Claude Code can also log in with a token. `claude setup-token`, with no argument, runs the same
login in a browser as `/login`, then prints a token and does not save it. The token is valid for
one year, and it needs a Pro, Max, Team or Enterprise plan. Run it where you can open its URL,
for example on a machine with a browser:

```bash
claude setup-token
```

Keep the token in a file under `~/.config/api-keys/`, the token alone, with mode 600: the settings
do not let a session read that directory. These commands create the file. The `read` line waits
for the token: paste it, and press Enter.

```bash
mkdir -p ~/.config/api-keys
(umask 077; read -r token; printf '%s' "$token" > ~/.config/api-keys/claude-code-oauth-token)
chmod 600 ~/.config/api-keys/claude-code-oauth-token
```

Then add this line to your shell startup file, `~/.bashrc` for bash or `~/.zshrc` for zsh, so
that Claude Code reads the token in each new shell. The shell startup file holds the path, not the
token.

```bash
export CLAUDE_CODE_OAUTH_TOKEN="$(cat ~/.config/api-keys/claude-code-oauth-token)"
```

`CLAUDE_CODE_OAUTH_TOKEN` takes precedence over a login that Claude Code keeps. The documentation
of Claude Code does not say that Claude Code removes the variable from the environment of the
shell commands of a [session](concepts.md#session), so they may see it. With
`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, Claude Code removes credentials from the environments of the
programs that it starts.

**Check.** The first command prints `600`, and in a new shell the second prints `TOKEN-SET`:

```bash
stat -c '%a' ~/.config/api-keys/claude-code-oauth-token
test -n "$CLAUDE_CODE_OAUTH_TOKEN" && echo TOKEN-SET
```

A desktop session has a Secret Service provider, so there `gh` and `glab` store their tokens in
the system keyring. The read-deny rules of the settings apply either way.
