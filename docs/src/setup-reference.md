# Setup reference

The setup pages for [macOS](setup-macos.md) and [Linux](setup-linux.md) run one command,
`harness setup`, after the prerequisites and the clone. This page gives each step of that
command, in the order of its plan: what the step does, why the harness needs it, how to do it by
hand on macOS and on Ubuntu, and how to check that it worked. It also gives the steps that
`harness setup` does not do, or only prints for you: *Check the machine*, the Antigravity app,
lingering on Linux, the dotfiles and a machine reached over SSH.

Do a step by hand when `harness setup` stops at it, when you want to see what it does, or when
`harness doctor` names its section. Each `FAIL` line of `harness doctor` ends with the section that
fixes it, for example `(fix: setup-reference.md, The packages)`.

The commands for macOS use Homebrew. They are checked on macOS 27 on Apple silicon (`arm64`) only.
On an Intel Mac, Homebrew is in `/usr/local` in place of `/opt/homebrew`, and the launchd jobs of
[The jobs](#the-jobs) put only `/opt/homebrew/bin` on their `PATH`; that case is not checked. The
commands for Linux are for Debian and Ubuntu, with `apt-get`. They are checked on Ubuntu 26.04
only, on the two architectures `x86_64` and `aarch64` (64-bit Arm); other distributions and
releases are not checked, and `harness setup` stops on a Linux that is not Ubuntu. The steps use
`~/Research/Harness` as the path of the checkout. [Introduction](concepts.md) explains the terms
that this page uses, and the glossary there has an entry for each.

**Without Julia code.** If you write no Julia, leave the component `julia` out of `[setup]` of the
[profile](concepts.md#profile), and skip the steps and lines that this page marks. Then the
[install](concepts.md#install) needs no Julia, as
[Dependencies](dependencies.md#harness-setup-installs) says.

**Without an administrator.** On macOS, the Homebrew installer needs an administrator, once. After
it, every step installs without one. On Linux, the `apt-get` lines and the lingering of
[The jobs](#the-jobs) need an administrator. Every tool that goes into `~/.local/bin` installs
without one.

**The exit codes.** Each `harness` subcommand ends with an exit status. Exit status 0 means
that nothing would change or that the subcommand succeeded, 1 that a dry run found something to
change, and 2 an error. Each step below names the status that it expects, with its meaning.

## Check the machine

**`harness setup` does not do this step.** It only reads the system and the architecture, and
stops with exit status 2 on a system other than macOS and Ubuntu, or on another architecture.

**What it does.** These commands change nothing. They print the facts of the machine that the
later steps depend on: the system, the architecture, your login shell, the groups of your
account, the tools and directories that are already there, and the `PATH` lines of your shell
startup files. On Linux, they also print the settings for user namespaces, the systemd user
manager, and the versions that `apt-get` would install.

On macOS:

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

On Linux:

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

- `sw_vers`, the `os-release` line and `uname -m` give the system and the architecture. This page
  covers Apple silicon, where `uname -m` prints `arm64`, and Ubuntu 26.04 on `x86_64` and
  `aarch64`. With another value of `uname -m` on Linux, the release files of
  [The pinned releases](#the-pinned-releases) do not exist; install those tools from their own
  sites.
- On Linux, the two `sysctl` keys decide whether the Claude Code [sandbox](concepts.md#sandbox)
  can start. `kernel.unprivileged_userns_clone = 0` means that the kernel does not let an
  unprivileged user create user namespaces. `kernel.apparmor_restrict_unprivileged_userns = 1`
  means that AppArmor blocks user namespaces for each program that AppArmor does not explicitly
  allow. Then the check of [The sandbox of Claude Code](#the-sandbox-of-claude-code) can fail, and
  Claude Code does not start. A key that does not exist sets no limit. Only an administrator can
  fix this, with a change of the kernel or AppArmor settings.
- `$SHELL`, the `UserShell` of `dscl` and the shell in the `getent` line are your login shell. On
  macOS it is zsh unless you changed it, and its shell startup files are `~/.zprofile`,
  `~/.zshenv` and `~/.zshrc`. This page puts each `export` line into `~/.zshrc` on macOS; with
  bash, use `~/.bash_profile`. On Linux, put it into `~/.bashrc` for bash or `~/.zshrc` for zsh.
  The juliaup installer writes its `PATH` block into each of `~/.bashrc`, `~/.profile`,
  `~/.bash_profile`, `~/.bash_login` and `~/.zshrc` that exists, whatever the login shell.
- On Linux, `systemctl --user is-system-running` prints `running` when the systemd user manager
  runs, or `degraded` when it runs and a unit failed; [The jobs](#the-jobs) need it. `Linger=no`
  means that the user manager stops at your last logout.
- `id -Gn` and `id -nG` list the groups of your account. On macOS, a member of the group `admin`
  is an administrator; without `admin` in the list, ask an administrator to install Homebrew. On
  Ubuntu, a member of the group `sudo` may run `sudo`, so you are an administrator; without `sudo`
  in the list, ask an administrator to run the lines of this page that start with `sudo`.
- `xcode-select -p` prints the directory of the Command Line Tools of macOS, which hold `git`,
  `make` and the compiler. Without them, it prints an error, and the Homebrew installer installs
  them.
- The `command -v`, `exists` and `grep` lines show what an earlier install left: Homebrew, a
  [frontend](concepts.md#frontend), a Julia, a directory of a frontend, or a `PATH` line in a
  shell startup file. Each step below installs over it or adds to it. `harness setup` skips a
  tool that is installed and meets its minimum, and runs the juliaup installer only when
  `juliaup` is not on the `PATH`. Read the output before you continue.
- On Linux, the `apt-cache` line gives the version that `apt-get` installs, under `Candidate`,
  and the version that is there, under `Installed`. `harness setup` compares each candidate with
  the minimum of [Dependencies](dependencies.md), as this line lets you do by hand.
- On Linux, `SECRETS-OK` means that a Secret Service provider, such as GNOME Keyring, is
  available, as at the desktop of the machine. Over SSH, the line prints nothing;
  [A machine reached over SSH](#a-machine-reached-over-ssh) says what follows.

**Check.** `sw_vers` names the system, for example `ProductName: macOS` and
`ProductVersion: 27.0.1`, and `uname -m` prints `arm64`. On Linux, the first line names the
system, for example `Ubuntu 26.04.1 LTS`, and the second line prints `x86_64` or `aarch64`.

## The profile and the model tables

**What `harness setup` does.** In a terminal, without a profile, `harness setup` copies
`examples/profile.toml` and asks only for the keys that have no default: `memory_project`,
`tree_agents`, `org`, `repository_roots` and `leak`. An empty answer keeps the example's value. It
then asks for the frontends and the components, each from a numbered list, and whether this
machine develops the harness (`develop`), y/N. The first step of its plan writes the profile, or
the answers into the table `[setup]` of an existing profile. When `models.toml` is missing beside
the profile, the next step copies `examples/models.toml`. `harness setup --yes` asks nothing and
writes no profile: it reads `[setup]` of the profile that is there.

**By hand.** These commands copy the example profile and the example model tables of `examples/`
into your configuration directory.

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
reverse-domain prefix of the job labels of [The jobs](#the-jobs) on macOS; `memory_project`, the
label of the Claude Code memory of your [research tree](concepts.md#research-tree); and
`template_host`, the output of `hostname -s` on the template host. The template host is the
machine whose Claude Code memory is the template for the other machines. With the example value
of `template_host`, the autocommit job of no machine pushes to `main`. Nothing on Linux reads
`launchd_prefix`: fill it in when the same profile also serves a Mac. The table `[setup]` names the
frontends and the components that `harness setup` installs and `harness install` writes, and
`develop`. [profile.md](profile.md) names each key and table, and the comments in the two files
say what each value is.

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

**What `harness setup` does.** The first step after the profile creates each directory that
`harness install` needs and that is missing: the directory of the
[tree instructions](concepts.md#tree-instructions), which the profile key `tree_agents` names,
each entry of `repository_roots`, and with the frontend `opencode` the OpenCode configuration
directory. It creates no file in them.

**By hand.** These commands create the directory of the tree instructions, with one empty file in
it, and the directories of `repository_roots`. They use the example values.

```bash
mkdir -p ~/Research/Environment/Agents/instructions
touch ~/Research/Environment/Agents/instructions/research-tree.md
mkdir -p ~/Research/Packages ~/Research/Experiments
```

**Why.** The tree instructions hold your own instruction text about your research tree.
`harness install` installs them into `~/.claude/` beside the sources of the harness. The directory
has the layout of `~/.claude/`. `adapters/claude/CLAUDE.md` imports
`instructions/research-tree.md`, so put the facts about your tree into that file. The directory
must exist; otherwise `harness install` stops with exit status 2, an error.
[architecture.md](architecture.md#the-three-layers) says how the tree instructions relate to the
harness and the profile. The key `repository_roots` names the directories that hold the
repositories of your research tree, and each entry must be a directory.

**Check.** `harness get tree_agents` prints the path of the directory, and the directory holds the
file.

```bash
harness get tree_agents
ls ~/Research/Environment/Agents/instructions
```

## The packages

**What `harness setup` does.** It installs each tool of
[Dependencies](dependencies.md#harness-setup-installs) that the profile chooses and that is
missing or below its minimum. On macOS, Homebrew installs them: one `brew install` line of the
missing tools and of the tools below their minimum that Homebrew does not list as installed, one
`brew upgrade` line of the tools below their minimum that it lists, and
`brew install --cask iterm2` with the component `iterm`. Without `brew` on the `PATH`, it stops
and names <https://brew.sh>. On Ubuntu, it asks `apt-cache` for the candidate of each package,
and puts each package whose candidate meets the tool's minimum into one
`sudo apt-get install -y` line. Without `sudo`, or when `sudo -n true` is refused, it prints that
line for an administrator and stops with exit status 2: run `sudo -v` first, or have an
administrator run the line, then run `harness setup` again. A tool that the packages do not meet
comes from [The pinned releases](#the-pinned-releases) or from the installer of its project.

**Why.** Each tool has the job that [Dependencies](dependencies.md#what-each-tool-does)
describes. The package manager of the system installs and updates most of them.

### macOS

When `command -v brew` of [Check the machine](#check-the-machine) printed nothing, install
Homebrew first, as a prerequisite. Its installer asks for the password of an administrator, and
at its end it prints the lines that put `brew` on the `PATH`. This line runs the installer, and
the second line puts `brew` on the `PATH` of the shell that you are in:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Add the `eval` line to `~/.zprofile` too, as the installer says, so that each new shell finds
`brew`.

The Claude Code installer and other installers put their programs into `~/.local/bin`. Put that
directory on the `PATH`:

```bash
mkdir -p ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
```

Add the `export` line to `~/.zshrc` too, so that each new shell finds the tools.

This command installs the tools that Homebrew packages:

```bash
brew install python python@3.14 uv git gh node shellcheck actionlint rsync jq rtk
```

**Optional: jq and RTK.** Leave `jq` or `rtk` out of the line if you do not want it, as the
components `jq` and `rtk` do for `harness setup`. RTK shortens the output of shell commands: the
OpenCode plugin of the harness asks `rtk` to rewrite each shell command, and without RTK, the
plugin passes each command unchanged.

**Only to push to the harness**, install gitleaks. Only the pre-push [hook](concepts.md#hook) of
the harness runs gitleaks, before a push to the harness. `harness setup` installs it on every
machine; by hand, a user who only installs the harness can skip this line:

```bash
brew install gitleaks
```

fatou comes from the tap of its author. **Without Julia code**, skip this line: fatou checks
Julia code only.

```bash
brew install jolars/tap/fatou
```

`harness` starts on the `python3` of the `PATH`, which must be 3.14 or later, and then runs on the
interpreter of its Python environment, which it makes with `uv` the first time that it runs
outside a [session](concepts.md#session). `python` supplies a current `python3`, and `python@3.14`
supplies the Python 3.14 that uv makes the environment on. Homebrew's `rsync` replaces the `rsync`
of macOS on the `PATH`. jq is optional: the status line of Claude Code reads its data with jq,
and without it, the status line shows no values. macOS supplies `lsof`, `launchctl` and the other
system tools of [Dependencies](dependencies.md#harness-setup-installs).

**Check.** Each command prints the version of one tool: Python 3.14 or later, Python 3.14, uv,
Node.js 22.3 or later, RTK 1.0.1 or later, actionlint 1.7.12 or later, and fatou 0.22.0 or later.
**Without jq or RTK**, skip its line. **Without Julia code**, skip the `fatou` line.

```bash
python3 --version
python3.14 --version
uv --version
node --version
jq --version
rtk --version
actionlint --version
fatou --version
```

### Ubuntu

These commands install every package that the harness calls, the two tools of the sandbox, and
the optional tool jq. `apt-get` installs each tool whose Ubuntu 26.04 package meets the minimum of
[Dependencies](dependencies.md), and also bubblewrap, socat, lsof and jq. These two lines need an
administrator:

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

Ubuntu 26.04 packages Python 3.14 and Node.js 22.22, which meet their minimums, but gitleaks only
in version 8.16.0, below the minimum 8.21. So gitleaks comes from its release, in
[The pinned releases](#the-pinned-releases). A release of a distribution can package an older
version than the minimum that Dependencies gives; then `harness setup` installs that tool from its
pinned release, where `setup/tools.toml` has one. Ubuntu 26.04 packages no uv: the first run of
`harness` outside a session fetches the uv release that `bin/harness` pins into `~/.local/bin`,
checks its sha256, and makes the Python environment of the harness with it. bubblewrap and socat
are the tools of [The sandbox of Claude Code](#the-sandbox-of-claude-code). The Julia update job
of [The jobs](#the-jobs) calls `lsof`. jq is optional: the status line of Claude Code reads its
data with jq, and without it, the status line shows no values.

**Check.** The first command prints the version of each package that `apt-get` installed. Each
command after it prints the version of one tool: Python 3.14 or later, Node.js 22.3 or later (or
20.16 or later in 20.x).

```bash
dpkg-query -W python3 git gh nodejs npm shellcheck coreutils rsync curl jq bubblewrap socat lsof
python3 --version
node --version
jq --version
```

## The pinned releases

**What `harness setup` does.** On Ubuntu, each tool that no apt candidate meets installs from its
pinned release of `setup/tools.toml`: gitleaks, actionlint and RTK, each for `x86_64` and
`aarch64`. `harness setup` downloads the archive, checks its sha256 against the file, and only
then installs the program into `~/.local/bin`; a download whose sha256 differs installs nothing.
On macOS, Homebrew installs these tools, and this step does not run.

**Why.** A pinned release with a checked sha256 installs the version that the harness is tested
with, where the distribution packages an older one.

**By hand.** gitleaks and RTK come from their releases, which have one file for each
architecture. This block sets the names of the two files for the architecture of the machine. On
an architecture other than `x86_64` and `aarch64`, it prints a message, sets no name, and the
download lines below download nothing:

```bash
case "$(uname -m)" in
  x86_64)  gl=gitleaks_8.30.1_linux_x64.tar.gz;   rt=rtk-x86_64-unknown-linux-musl.tar.gz ;;
  aarch64) gl=gitleaks_8.30.1_linux_arm64.tar.gz; rt=rtk-aarch64-unknown-linux-gnu.tar.gz ;;
  *)       gl=; rt=; echo "This page covers x86_64 and aarch64, not $(uname -m): install gitleaks and RTK from their own sites." ;;
esac
```

**Optional: RTK.** These lines download the release 1.0.1 and its checksum file `checksums.txt`,
check the release against the checksum, and only then install `rtk` into `~/.local/bin`:

```bash
d=$(mktemp -d); cd "$d"
v=1.0.1
[ -n "$rt" ] && curl -fsSL -O "https://github.com/rtk-ai/rtk/releases/download/v$v/$rt" -O "https://github.com/rtk-ai/rtk/releases/download/v$v/checksums.txt"
grep " $rt\$" checksums.txt | sha256sum -c - && tar -xzf "$rt" rtk && install -m 755 rtk ~/.local/bin/
cd ~
```

**Only to push to the harness**, install gitleaks. A user who only installs the harness can skip
these lines. They download the release 8.30.1 and its checksum file
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

actionlint comes from the installer script of its project, which selects the file for the
architecture itself, and installs `actionlint` into `~/.local/bin`:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) latest ~/.local/bin
```

**Check.** Each command prints the version of one tool: RTK 1.0.1, actionlint 1.7.12 or later,
and gitleaks 8.21 or later. **Without RTK**, skip the `rtk` line.

```bash
rtk --version
actionlint --version
gitleaks version
```

## Julia and its tools

**With the component `julia` only.** **Without Julia code, skip this step.**

**What `harness setup` does.** It runs the installer of each tool that its project gives, where
the installer runs unattended: the juliaup installer, only when `juliaup` is not on the `PATH`,
which installs Julia too; `juliaup add release` when juliaup is there and Julia is not;
`juliaup update` for a Julia below its minimum; the fatou installer on Ubuntu, where Homebrew does
not install fatou; and Kaimon as a Julia app. After `juliaup update`, it reads the version of
Julia again. When Julia is still below its minimum, the step fails and names
`juliaup add release && juliaup default release`, because `juliaup update` keeps the default
channel of juliaup.

**Why.** Julia runs the Julia scripts of the harness, and juliaup installs and updates the Julia
releases. fatou checks Julia code. Kaimon gives an [agent](concepts.md#agent) a Julia session
and tools for Julia code; [Dependencies](dependencies.md#kaimon) says what it does.

### juliaup and Julia

The juliaup installer is the same on macOS and on Linux. The `export` line puts `~/.juliaup/bin`
on the `PATH` of the shell that you are in:

```bash
curl -fsSL https://install.julialang.org | sh -s -- --yes
export PATH="$HOME/.juliaup/bin:$PATH"
```

The juliaup installer asks no question with `--yes`: with its default settings, it installs
`juliaup` and the `julia` launcher into `~/.juliaup/bin`, and the current Julia release below
`~/.julia`. It adds `~/.juliaup/bin` to the `PATH` in a block between the lines
`# >>> juliaup initialize >>>` and `# <<< juliaup initialize <<<`, in each shell startup file
that exists.

**With juliaup installed already**, its installer stops with the message `It seems that Juliaup
is already installed on this system. Please remove the previous installation of Juliaup before
you try to install a new version.` and installs nothing. So when `juliaup --version` prints a
version, skip the `install.julialang.org` line, or run `juliaup self update` in its place. Run the
`export` line and the **Check** below either way.

The six Julia packages of [Dependencies](dependencies.md#harness-setup-installs) need no command:
the first install adds them.

### fatou

On macOS, Homebrew installs fatou, in [The packages](#the-packages). On Linux, the fatou installer
installs `fatou` into `~/.local/bin`, and checks the checksum of its download when the release
publishes one:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://fatou.dev/install | sh
```

### Kaimon

The first command installs Kaimon as a Julia app, which puts the command `kaimon` into
`~/.julia/bin`. The second puts that directory on the `PATH` of the shell that you are in:

```bash
julia -e 'using Pkg; Pkg.Apps.add("Kaimon")'
export PATH="$HOME/.julia/bin:$PATH"
```

Add the `export` line to your shell startup file too, so that each new shell finds `kaimon`. The
Kaimon server of [The jobs](#the-jobs) runs `~/.julia/bin/kaimon`, and the Julia update job
updates Kaimon.

**Check.** Each command prints the version of one tool: fatou 0.22.0 or later, juliaup, and Julia
1.13 or later. The last command prints `KAIMON-OK`:

```bash
fatou --version
juliaup --version
julia --version
test -x ~/.julia/bin/kaimon && echo KAIMON-OK
```

## The frontends

**What `harness setup` does.** It installs each [frontend](concepts.md#frontend) that `[setup]`
chooses, with the installer that its project gives: Claude Code with its installer on both
systems; OpenCode 2 and oh-my-pi with Homebrew on macOS, and with their installers on Ubuntu. The
OpenCode installer runs only when `opencode` is not on the `PATH`, with `--no-modify-path`, and
`harness setup` prints the `PATH` line of `~/.opencode/bin` under *By hand* instead. It installs
no Antigravity: it prints the step under *By hand*.

**Why.** Each frontend reads the configuration that `harness install` writes; a frontend that is
not installed reads nothing. `harness install` writes the configuration of each frontend that
`[setup]` chooses, except that of Antigravity, which it writes once `~/.gemini/` exists. The
installers below are the ones that the projects give, and each selects the file for the
architecture of the machine itself.

### Install Claude Code

This command runs the Claude Code installer, on macOS and on Linux:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

The installer puts the launcher at `~/.local/bin/claude`, a symbolic link to the current version
in `~/.local/share/claude/versions/`. Claude Code updates itself in the background, and
`claude update` updates it at once. The installer changes no shell startup file: it needs
`~/.local/bin` on the `PATH`, which [The packages](#the-packages) puts there.

**Check.** The command prints the version, for example `2.1.304 (Claude Code)`:

```bash
claude --version
```

**Optional on Linux: the signed manifest.** On Linux, the Claude Code binaries are not
code-signed. Each release has a file `manifest.json` with the SHA-256 checksum of each binary, and
a signature of that file made with the release key of Anthropic. These commands check the
installed version against the manifest. They need `gpg`, from the package `gnupg`, and jq:

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

On macOS, this command installs OpenCode 2 from the Homebrew tap of its project:

```bash
brew install anomalyco/tap/opencode-v2
```

Homebrew puts `opencode` into `/opt/homebrew/bin`, which is on the `PATH` already.
`brew upgrade opencode-v2` updates it. The formula `opencode`, without `-v2`, installs
OpenCode 1.

On Linux, this command runs the OpenCode 2 installer:

```bash
curl -fsSL https://opencode.ai/v2/install | bash
```

The installer puts `opencode` into `~/.opencode/bin`. When that directory is not on the `PATH`, it
adds two lines to the first shell startup file of your login shell that exists, for example
`~/.bashrc` for bash or `~/.zshrc` for zsh: the line `# opencode`, and the line
`export PATH=/home/me/.opencode/bin:$PATH` with your home directory in place of
`/home/me`. Its option `--no-modify-path` leaves the shell startup files as they are, and
`harness setup` gives it. `opencode upgrade` updates it. This command puts the directory on the
`PATH` of the shell that you are in:

```bash
export PATH="$HOME/.opencode/bin:$PATH"
```

The command `curl -fsSL https://opencode.ai/install | bash`, without `v2`, installs OpenCode 1
only. Both versions use the command `opencode`, so install one of them only. The harness
configures OpenCode 2.

**Check.** The command prints the version, 2.0 or later:

```bash
opencode --version
```

### Install oh-my-pi

On macOS, this command installs oh-my-pi from the Homebrew tap of its project:

```bash
brew install can1357/tap/omp
```

Homebrew puts `omp` into `/opt/homebrew/bin`. `brew upgrade omp` updates it.

On Linux, this command runs the oh-my-pi installer, with its option `--binary`:

```bash
curl -fsSL https://omp.sh/install | sh -s -- --binary
```

The installer downloads the prebuilt binary for the machine, checks its SHA-256 checksum, and
only then puts `omp` into `~/.local/bin`, or into `$PI_INSTALL_DIR` when that variable is set.
Without `--binary`, an installer that finds `bun` uses `bun` to install oh-my-pi into the
directory of `bun` instead. The installer changes no shell startup file: it needs `~/.local/bin`
on the `PATH`, which [The packages](#the-packages) puts there. `omp update` updates it.

**Check.** The command prints the version, for example `omp/18.12.3`:

```bash
omp --version
```

### Install Antigravity

`harness setup` does not install Antigravity. Install the Antigravity desktop app from its site,
<https://antigravity.google/>, and start it once. The app keeps its data in `~/.gemini/`, and the
desktop app, the IDE and the CLI `agy` read one configuration directory, `~/.gemini/config/`.
`harness install` writes the Antigravity layer only when `~/.gemini/` exists; without it, the
install gives one warning and writes no file there.

**Check.** The command prints `GEMINI-OK`:

```bash
test -d ~/.gemini && echo GEMINI-OK
```

## The sandbox of Claude Code

**What it does.** Claude Code runs the shell commands of a session in a sandbox. On macOS, the
sandbox is Seatbelt, through `sandbox-exec`, which macOS supplies. On Linux, it is a bubblewrap
(`bwrap`) sandbox, and Claude Code also needs socat; `harness setup` installs both in its
`apt-get` line. The settings template of the harness sets `sandbox.enabled` and
`failIfUnavailable: true`. So without a working sandbox, Claude Code does not start, instead of
running the commands without a sandbox. `harness setup` installs the tools, and `harness doctor`
runs the check below on Linux.

**Why.** The check shows that the machine lets your account make a sandbox, before the first
session depends on it. On Linux, bubblewrap makes the sandbox from user namespaces of the kernel,
and the settings of a machine can refuse them to a user. Then `bwrap` fails, and Claude Code does
not start. The cause is in the machine's settings for unprivileged user namespaces, which only an
administrator can change; [Check the machine](#check-the-machine) prints them.

**Check.** Run the commands in a plain terminal, not in a Claude Code session: a sandbox cannot
make a second sandbox inside it. On macOS, the command prints `SANDBOX-OK`:

```bash
sandbox-exec -p '(version 1)(allow default)' /usr/bin/true && echo SANDBOX-OK
```

On Linux, the first command prints the paths of the two tools. The second makes a sandbox and
prints `BWRAP-OK`:

```bash
command -v bwrap socat
bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid true && echo BWRAP-OK
```

## `harness install --apply`

**What `harness setup` does.** It runs `harness install --apply`, with the profile and the model
tables of its run.

**What it does.** `harness install` writes the configuration of each frontend from the sources of
the harness, the profile and the tree instructions. It needs two directories: the directory of the
tree instructions, which the profile key `tree_agents` names, and, with the frontend `opencode`,
the OpenCode configuration directory, `$OPENCODE_CONFIG_DIR`, or `~/.config/opencode/` if that
variable is not set. Without either, it stops with exit status 2, an error. It creates
`~/.claude/` and `~/.omp/agent/` itself. On a new machine, create the two directories before the
first install; the command uses the example value of `tree_agents`:

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
copies each agent, [skill](concepts.md#skill), [rule](concepts.md#rule) and
[instruction file](concepts.md#instruction-file) to the place where its frontend reads it. With
the component `julia`, the first `--apply` also instantiates the Julia environment of the
scripts, so it downloads the Julia packages of `Project.toml`. It syncs the Python environment of
the harness with `uv`. The warnings after the plan name what the install does not do for you. For
example, the Kaimon entry of OpenCode needs the token file `~/.config/kaimon/auth-token`. Kaimon
makes its key at its first start, so that warning stays until
[The Kaimon token](#the-kaimon-token), after [The jobs](#the-jobs).

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

These sections are the permission settings, the hooks, the sandbox, and the
[effort](concepts.md#effort) and auto-compact window of each model. Without them, Claude Code runs
with its own defaults: no guard hook refuses a command, and no sandbox limits a shell command. On
Linux, the `sandbox` section needs the tools of
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
`~/.claude/settings.json` from a session, so you run the install yourself, in your own terminal.
The install reads the file when it makes its plan, so do not change the model of a running
session while `--apply` runs: Claude Code writes the file then, and that change is lost.

If `~/.claude/settings.json` is not a JSON object, is a symbolic link, or holds one of the four
sections as a value that is not an object, the install stops with exit status 2, an error, and
writes no file.

### OpenCode

`harness install` writes the OpenCode configuration into the OpenCode configuration directory:
`opencode.jsonc` with its permission block, the plugins, the global instruction file `AGENTS.md`
and the agents, and OpenCode's own copies of the instructions, the rules, the guard hooks and
the skills. It removes the links in `~/.agents/skills/` that an earlier install wrote.
[architecture.md](architecture.md#the-opencode-and-oh-my-pi-adapters) describes the adapter. On
Linux, the settings template keeps a Claude Code session from writing to `~/.opencode/bin`, where
the OpenCode installer puts the program, and to `~/.local/bin`.

### oh-my-pi

`harness install` writes the oh-my-pi configuration into its agent directory,
`$PI_CODING_AGENT_DIR`, or `~/.omp/agent/` if that variable is not set: `harness.yml` with the
permission layer and the default model, `models.yml`, the guard extension, `AGENTS.md`, the rules,
the agents, `mcp.json`, and oh-my-pi's own copies of the instructions, the guard hooks and the
skills. It never writes oh-my-pi's own `config.yml`. oh-my-pi lets `harness.yml` override
`config.yml` only when the line
`PI_CONFIG_FILES=~/.omp/agent/harness.yml` is in `~/.omp/agent/.env`. oh-my-pi has no `env`
setting, so its shell commands get the variables of the settings template's `env` from the same
file. The install warns until the lines are there, and `harness setup` does not write them. This
block adds the four lines to the end of `~/.omp/agent/.env`. Run it once: a second run adds the
lines again.

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
`hooks.json` with the guard package, the path list, and the Kaimon entry of
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
dialog "Allow using this MCP tool?" and the name of the tool. The install also writes the grants
`command(gh)`, `command(git)`, `command(glab)` and `command(ps)`: the first words of
`sandbox.excludedCommands` of the settings template, the commands that Claude Code runs outside
its sandbox. With these grants, the app runs such a command with no prompt. The guard hook applies
the template's Bash denies and asks first, so `git push --force` is still refused and
`gh pr merge` still asks. The install leaves
`allowNonWorkspaceAccess` at its default, `false`, so a workspace below `~/Research` asks once for
read access to each parent `CLAUDE.md` that `GEMINI.md` has the model read. Approve each of these
requests once.

**Check.** Start a conversation in the app, in a workspace below `~/Research`, and paste this
prompt. Approve each request for a `CLAUDE.md`. The app asks for no grant for `kaimon/ping`, and
the reply holds Kaimon's answer:

```text
Start the subagent julia-critic with the prompt "Call the tool ping of the MCP server kaimon, and report its reply verbatim". Report its reply verbatim.
```

## `git config core.hooksPath .githooks`

**What `harness setup` does.** It runs `git config core.hooksPath .githooks` in the clone, on
every machine.

**What it does.** These commands turn on the pre-commit and the pre-push hook of this repository,
once in the checkout:

```bash
cd ~/Research/Harness
git config core.hooksPath .githooks
```

**Why.** The hooks check a change of the harness before it leaves the machine. The pre-commit
hook runs `ruff format --check`, `ruff check` and `basedpyright` on each commit, with the tools
that `develop = true` in `[setup]` of the profile puts into the Python environment at the next
`harness install --apply`; without them it refuses every commit. The pre-push hook runs the leak
checks, the tests and the same three checks before a push to `main`, and `harness leaks` before a
push of any other branch. Its leak checks run gitleaks.
[development.md](development.md#the-pre-commit-hook) describes the hooks.

**Check.** `git config core.hooksPath` in the checkout prints `.githooks`.

## `harness trust --apply`

**What `harness setup` does.** It runs `harness trust --apply` on every machine.

**What it does.** `harness trust` marks the research root and every git repository below it as
trusted in Claude Code's state file, `~/.claude.json`, so that Claude Code shows no trust dialog
for them. The dry run lists each root that is not trusted yet:

```bash
harness trust
harness trust --apply
```

**Why.** Claude Code asks once for each workspace whether you trust it. The harness trusts the
repositories of your research tree in one step, so that a session in any of them starts at once.

Claude Code writes `~/.claude.json` at its first start. Without that file, `harness trust` stops
with exit status 2, an error, and so does the run of `harness setup` at this step. Start
`claude` once in a terminal, then run `harness setup` again: it plans again and skips what is
done. When `[setup]` does not choose the frontend `claude`, nothing installs Claude Code: write an
empty JSON object into the file with `echo {} > ~/.claude.json` instead. Run
`harness trust --apply` again after `harness clone`, because a new clone is not trusted.

**Check.** `harness trust` prints `0 untrusted` and exits with status 0.

## The jobs

**With the component `jobs` only.**

**What `harness setup` does.** It copies two scripts into `~/.local/bin`, then renders each job
with the profile and loads it. On macOS, it renders the three launch agents into
`~/Library/LaunchAgents/` and loads each one, after an unload when it is loaded already; the
profile must have `launchd_prefix`. On Linux, it renders the `systemd --user` units into
`~/.config/systemd/user/`, then runs `systemctl --user daemon-reload`, enables and starts the
server and the two timers, and restarts them. It prints the lingering line under *By hand*, for an
administrator.

**What it does.** The jobs are three: the Kaimon server, the Julia update job and the autocommit
job of `~/.claude`. On macOS, launch agents run them: a launch agent is a job that launchd, the
service manager of macOS, runs for your account while you are logged in. On Linux, the
`systemd --user` units run them. [components/other.md](components/other.md) says what each job
runs.

The update job and the autocommit job run installed copies of two scripts of the checkout, in
`~/.local/bin`, not the scripts in the checkout: a session cannot write `~/.local/bin`, and the
jobs run outside the sandbox. These commands install the two copies:

```bash
install -m 755 ~/Research/Harness/launchagents/claude-autocommit ~/.local/bin/
install -m 755 ~/Research/Harness/scripts/julia-update.jl ~/.local/bin/
```

After you change one of the two scripts in the checkout, run its line again.

**With a git repository in `~/.claude` only.** The autocommit job commits in `~/.claude/` and
pushes to the `origin` of that repository, so `~/.claude` must be a git repository with a remote
`origin`. No step of this page makes it one. The first command prints `REPOSITORY-OK` when
`~/.claude` is the top directory of its own repository, not a directory inside another repository.
The second prints the URL of the remote:

```bash
test "$(git -C ~/.claude rev-parse --show-toplevel)" = "$HOME/.claude" && echo REPOSITORY-OK
git -C ~/.claude remote get-url origin
```

When the first prints no `REPOSITORY-OK`, or the second prints an error, the autocommit job fails
each time that it runs. By hand, skip the line that loads or enables it below.

**With Kaimon only.** The server runs `~/.julia/bin/kaimon`, and the update job stops with an
error without Kaimon. [Kaimon](#kaimon) installs it.

**Why.** The server must run before the agents of OpenCode, oh-my-pi and Antigravity can use
Kaimon. The update job keeps the Julia releases and Kaimon current, and the autocommit job commits
and pushes `~/.claude`.

### macOS

These commands render each launch agent with the profile into `~/Library/LaunchAgents/`, under
its label, and create the log directories of the jobs. `p` holds the profile key
`launchd_prefix`; the commands of this step after it use `p` too, so run them in the same shell:

```bash
p=$(harness get launchd_prefix)
mkdir -p ~/Library/LaunchAgents ~/Library/Logs/kaimon ~/Library/Logs/julia-update ~/Library/Logs/claude-autocommit
for j in kaimon julia-update claude-autocommit; do harness render ~/Research/Harness/launchagents/"$j".plist > ~/Library/LaunchAgents/"$p.$j".plist; done
plutil -lint ~/Library/LaunchAgents/"$p".*.plist
```

`plutil -lint` prints `OK` after the path of each file. This command loads the launch agent of
the autocommit job:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/"$p".claude-autocommit.plist
```

With Kaimon in `~/.julia/bin`, these commands load the launch agents of the server and the update
job:

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

launchd loads each launch agent of `~/Library/LaunchAgents/` again at each login, so the jobs need
this step only once. launchd has no equivalent of lingering: a launch agent runs only while you
are logged in.

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

### Linux

These commands render each unit with the profile into `~/.config/systemd/user/`:

```bash
mkdir -p ~/.config/systemd/user
for u in kaimon.service julia-update.service julia-update.timer claude-autocommit.service claude-autocommit.timer; do harness render ~/Research/Harness/systemd/"$u" > ~/.config/systemd/user/"$u"; done
systemctl --user daemon-reload
```

This command enables the timer of the autocommit job:

```bash
systemctl --user enable --now claude-autocommit.timer
```

With Kaimon in `~/.julia/bin`, this command enables the server and the timer of the update job:

```bash
systemctl --user enable --now kaimon.service julia-update.timer
```

Then an administrator turns on lingering for your account. `harness setup` does not do this
step. When your account may run `sudo`, run this line in your own account:

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

Without lingering, the systemd user manager starts at your first login and stops at your last
logout, and the units stop with it. Lingering keeps the server and the timers running when no one
is logged in.

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

**With Kaimon and OpenCode or Antigravity only.** Skip this step without Kaimon, or without both
frontends.

**What `harness setup` does.** With the component `julia`, it writes the token file
`~/.config/kaimon/auth-token`, mode 600, from the first key of `~/.config/kaimon/config.json`, when
that file exists and the token file does not. A token file that exists is kept. Without a key yet,
it prints the step and goes on.

**What it does.** In its strict mode, Kaimon refuses a request that does not carry one of its API
keys. Kaimon keeps its mode and its keys in `~/.config/kaimon/config.json`, and writes that file
at its first start: the server of [The jobs](#the-jobs) starts with `--headless`, and then Kaimon
writes a configuration in the strict mode with one new key, `kaimon_` followed by 40 hexadecimal
digits. `kaimon` started in a terminal asks the questions of its setup wizard instead. The Kaimon
entry of OpenCode sends a key in the header `Authorization: Bearer`, and it reads the key from the
file `~/.config/kaimon/auth-token`. These commands write the first key of the configuration
into that file, the key alone, with mode 600. They write a temporary file first, and move it into
place only when the key is not empty. Without `config.json`, or without a key in it, they leave no
token file, and the dry run keeps its warning:

```bash
(umask 077; python3 -c 'import json, os; print(json.load(open(os.path.expanduser("~/.config/kaimon/config.json")))["api_keys"][0], end="")' > ~/.config/kaimon/auth-token.new) && test -s ~/.config/kaimon/auth-token.new && mv ~/.config/kaimon/auth-token.new ~/.config/kaimon/auth-token
rm -f ~/.config/kaimon/auth-token.new
```

**Why.** Without the file, OpenCode sends no key, and Kaimon answers each request with 401. The
settings do not let a session read either file. Antigravity expands no shell form in its MCP
configuration, so `harness install` writes the key itself into `~/.gemini/config/mcp_config.json`,
with mode 600; without the file, the install writes no Kaimon entry there and warns. The token
step of `harness setup` comes after its install, so with Antigravity, run
`harness install --apply` once more after this step.

**Check.** The first command prints `600 47`: the mode, and the 47 characters of the key, on macOS
with `stat -f` and on Linux with `stat -c`. The dry run prints no warning about
`~/.config/kaimon/auth-token`:

```bash
stat -f '%Lp %z' ~/.config/kaimon/auth-token
stat -c '%a %s' ~/.config/kaimon/auth-token
harness install
```

## `harness doctor`

**What `harness setup` does.** It runs `harness doctor` last, after the lines under *By hand*, so
that its report ends the run. The run then exits with the status of `harness doctor`: 0 when no
check fails, and 1 when one fails.

**What it does.** `harness doctor` checks the machine, the tools, the profile, the install and the
jobs, read-only, and prints one line for each check: `PASS`, `WARN`, `FAIL` or `SKIP`, the name
and a detail. A `FAIL` line names the section of the setup pages that fixes it. It exits with
status 0 when no check fails, and 1 when one fails. A `WARN`, for example for a missing optional
tool or a warning of the install, does not count as a failure. On macOS, it also checks for
iTerm2, which the hook `cc-status` uses, and gives a `WARN` without it. Run it in a plain
terminal: in a Claude Code session, the sandbox refuses some of its commands, and those checks
are `SKIP`. `--full` also runs `harness test`.

```bash
harness doctor
```

**Why.** One command shows the state of the whole machine, and each `FAIL` names the section that
fixes it: a section of this page, or, for `harness test`, *The check that it worked* of
[setup-linux.md](setup-linux.md) or [setup-macos.md](setup-macos.md).

**Check.** Its last lines name no `FAIL`, and it exits with status 0.

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

The kit needs chezmoi. With the component `dotfiles`, `harness setup` installs it, with Homebrew
on macOS and with `apt-get` on Ubuntu. By hand, on macOS:

```bash
brew install chezmoi
```

On Linux, install it as the documentation of chezmoi shows for your distribution.

**Check.** `dotfiles check`, in a plain terminal, ends with a count line that says `0 FAIL`.

## A machine reached over SSH

**`harness setup` does not do this step.** It logs in no account.

In an SSH session on Linux, no Secret Service provider, such as GNOME Keyring, is available, so
`gh` and `glab` cannot store their tokens in the system keyring. They keep them in files: `gh` in
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
shell commands of a session, so they may see it. With
`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, Claude Code removes credentials from the environments of the
programs that it starts.

**Check.** The first command prints `600`, and in a new shell the second prints `TOKEN-SET`:

```bash
stat -c '%a' ~/.config/api-keys/claude-code-oauth-token
test -n "$CLAUDE_CODE_OAUTH_TOKEN" && echo TOKEN-SET
```

A desktop session has a Secret Service provider, so there `gh` and `glab` store their tokens in
the system keyring. The read-deny rules of the settings apply either way.
