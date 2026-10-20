# Setup on Linux

This page gives each step from a clean Linux machine to a working harness. For each step it says
what the step does, why the harness needs it, and how you see that it worked.
[setup-macos.md](setup-macos.md) is the page for macOS.

The commands are for Debian and Ubuntu, with `apt-get`. The package names and the versions that
this page gives are checked on Ubuntu 26.04 only; other distributions and releases are not
checked. The commands run on the two architectures `x86_64` and `aarch64` (64-bit Arm). The steps
use `~/Research/Harness` as the path of the checkout. [Introduction](concepts.md) explains the
words that this page uses, and the glossary there has an entry for each.

**Without Julia code.** If you write no Julia, you can skip the steps and lines that this page
marks. You still need Julia itself, because the [install](concepts.md#install) runs it once.

**Without an administrator.** The `apt-get` lines and the linger of [The jobs](#the-jobs) need an
administrator, a user who may run `sudo`. Every tool that goes into `~/.local/bin` installs
without one.

**The exit codes.** Each verb of `harness` ends with an exit code, which your shell keeps in
`$?`. Exit 0 means that nothing would change or that the verb succeeded, exit 1 that a dry run
found something to change, and exit 2 an error. Each step below names the code that it expects,
with its meaning.

## Check the machine

**What it does.** These commands change nothing. They print the facts of the machine that the
later steps depend on: the system, the architecture, the settings for user namespaces, your login
shell, the user manager of systemd, the groups of your account, the tools and directories that are
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
- The two `sysctl` keys decide whether the [sandbox](concepts.md#sandbox) of Claude Code can
  start. `kernel.unprivileged_userns_clone = 0` means that the kernel refuses user namespaces to a
  user who is not root. `kernel.apparmor_restrict_unprivileged_userns = 1` means that AppArmor
  refuses them to each program, unless AppArmor allows them to that program. Then the check of
  [The sandbox of Claude Code](#the-sandbox-of-claude-code) can fail, and Claude Code does not
  start. A key that does not exist sets no limit. The fix is the administrator's: a change of the
  settings of the kernel or of AppArmor.
- `$SHELL` and the shell in the `getent` line are your login shell. The installer of OpenCode
  writes its `PATH` lines into the first start file of that shell that exists, for example
  `~/.bashrc` for bash or `~/.zshrc` for zsh, when its directory is not on the `PATH`. The
  installer of juliaup writes its `PATH` block into each of `~/.bashrc`, `~/.profile`,
  `~/.bash_profile`, `~/.bash_login` and `~/.zshrc` that exists, whatever the login shell.
- `systemctl --user is-system-running` prints `running` when the user manager of systemd runs,
  or `degraded` when it runs and a unit failed; [The jobs](#the-jobs) need it. `Linger=no` means
  that the user manager stops at your last logout.
- `id -nG` lists the groups of your account. On Ubuntu, a member of the group `sudo` may run
  `sudo`, so you are an administrator. Without `sudo` in the list, ask an administrator to run the
  lines of this page that start with `sudo`.
- The `command -v`, `exists` and `grep` lines show what an earlier install left: a
  [frontend](concepts.md#frontend), a Julia, a directory of a frontend, or a `PATH` line in a
  start file. Each step below installs over it or adds to it; read the output before you
  continue.
- The `apt-cache` line gives the version that `apt-get` installs, under `Candidate`, and the
  version that is there, under `Installed`. Compare each with the minimum of
  [Dependencies](dependencies.md).
- `SECRETS-OK` means that a Secret Service answers, as at the desktop of the machine. Over SSH,
  the line prints nothing; [A machine reached over SSH](#a-machine-reached-over-ssh) says what
  follows.

**Check.** The first line names the system, for example `Ubuntu 26.04.1 LTS`, and the second line
prints `x86_64` or `aarch64`.

## The dependencies

**What it does.** These commands install every required tool that the harness calls, the two
tools of the sandbox of Claude Code, and the optional tools jq and RTK. `apt-get` installs the
tools that Ubuntu 26.04 packages at or above the minimum of [Dependencies](dependencies.md), and
bubblewrap, socat, lsof and jq. These two lines need an administrator:

```bash
sudo apt-get update
sudo apt-get install -y python3 git gh nodejs npm shellcheck coreutils rsync curl jq bubblewrap socat lsof
```

The tools of `~/.local/bin` need no administrator. First put that directory on the `PATH`:

```bash
mkdir -p ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
```

Add the `export` line to your shell's start file too, for example `~/.bashrc`, so that each new
shell finds the tools.

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
asks `rtk` for the rewrite of each shell command; without RTK, the plugin passes each command
unchanged. These lines download the release 1.0.1 and its checksum file `checksums.txt`, check
the release against the checksum, and only then install `rtk` into `~/.local/bin`:

```bash
d=$(mktemp -d); cd "$d"
v=1.0.1
[ -n "$rt" ] && curl -fsSL -O "https://github.com/rtk-ai/rtk/releases/download/v$v/$rt" -O "https://github.com/rtk-ai/rtk/releases/download/v$v/checksums.txt"
grep " $rt\$" checksums.txt | sha256sum -c - && tar -xzf "$rt" rtk && install -m 755 rtk ~/.local/bin/
cd ~
```

**Only to push to the harness**, install gitleaks: on your machine, only the pre-push
[hook](concepts.md#hook) of the harness runs it, before a push to the harness. A user who only
installs the harness skips these lines. They download the release 8.30.1 and its checksum file
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
one. The installer of `juliaup`
asks no question with `--yes`: with its default settings, it installs `juliaup` and the `julia`
launcher into `~/.juliaup/bin`, and the current Julia release below `~/.julia`. It adds
`~/.juliaup/bin` to the `PATH` in a block between the lines `# >>> juliaup initialize >>>` and
`# <<< juliaup initialize <<<`, in each of `~/.bashrc`, `~/.profile`, `~/.bash_profile`,
`~/.bash_login` and `~/.zshrc` that exists. The `export` line puts `~/.juliaup/bin` on the `PATH`
of the shell that you are in. The six Julia packages of
[Dependencies](dependencies.md#julia-and-its-packages) need no command: the first install adds
them.

**Why.** Each tool has the job that [Dependencies](dependencies.md#what-each-tool-does)
describes. Ubuntu 26.04 packages Python 3.14 and Node.js 22.22, which meet their minimums, but
gitleaks 8.16.0, below the minimum 8.21; so gitleaks comes from its release. A release of a
distribution can package an older version than the minimum that Dependencies gives. Then install
that tool from its own site. The pre-push hook also runs `python3.11`; where it is missing, the
hook prints one skip line, because CI runs it. bubblewrap and socat are the tools of
[The sandbox of Claude Code](#the-sandbox-of-claude-code). The update job of
[The jobs](#the-jobs) calls `lsof`. jq is optional: the status line of Claude Code reads its data
with jq, and without it, the status line shows no values. You need Julia even if you write no
Julia code: the first install instantiates the Julia environment of the harness's scripts, and it
stops without `julia`.

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
not use. `harness install` writes the configuration of all three either way. Of the directories
of the frontends, it needs only the configuration directory of OpenCode, which the `mkdir` line
of [`harness install --apply`](#harness-install-apply) makes.

**Why.** Each frontend reads the configuration that `harness install` writes; a frontend that is
not installed reads nothing. The installers below are the ones that the projects give, and each
selects the file for the architecture of the machine itself.

### Install Claude Code

This command runs the installer of Claude Code:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

The installer puts the launcher at `~/.local/bin/claude`, a symbolic link to the current version
in `~/.local/share/claude/versions/`. Claude Code updates itself in the background, and
`claude update` updates it at once. The installer changes no start file: it needs `~/.local/bin`
on the `PATH`, which [The dependencies](#the-dependencies) puts there.

**Check.** The command prints the version, for example `2.1.303 (Claude Code)`:

```bash
claude --version
```

**Optional: the signed manifest.** On Linux, the binaries of Claude Code have no code signature
of their own. Each release has a file `manifest.json` with the SHA-256 checksum of each binary,
and a signature of that file by the release key of Anthropic. These commands check the installed
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

This command runs the installer of OpenCode 2:

```bash
curl -fsSL https://opencode.ai/v2/install | bash
```

The installer puts `opencode` into `~/.opencode/bin`. When that directory is not on the `PATH`, it
adds two lines to the first start file of your login shell that exists, for example `~/.bashrc`
for bash or `~/.zshrc` for zsh: the line `# opencode`, and the line
`export PATH=/home/me/.opencode/bin:$PATH` with your home directory in place of
`/home/me`. Its option `--no-modify-path` leaves the start files as they are.
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

This command runs the installer of oh-my-pi, with its option `--binary`:

```bash
curl -fsSL https://omp.sh/install | sh -s -- --binary
```

The installer downloads the prebuilt binary for the machine, checks its SHA-256 checksum, and
only then puts `omp` into `~/.local/bin`, or into `$PI_INSTALL_DIR` when that variable is set.
Without `--binary`, an installer that finds `bun` installs oh-my-pi with `bun` into the directory
of `bun` instead. The installer changes no start file: it needs `~/.local/bin` on the `PATH`, which
[The dependencies](#the-dependencies) puts there. `omp update` updates it.

**Check.** The command prints the version, for example `omp/18.12.3`:

```bash
omp --version
```

## The sandbox of Claude Code

**What it does.** On Linux, Claude Code runs the shell commands of a
[session](concepts.md#session) in a sandbox of bubblewrap, `bwrap`, and it needs socat beside it.
The settings template of the harness sets `sandbox.enabled` and `failIfUnavailable: true`. So
without a working sandbox, Claude Code does not start, rather than run the commands without one.
[The dependencies](#the-dependencies) installs both tools.

**Why.** bubblewrap makes the sandbox from user namespaces of the kernel, and the settings of a
machine can refuse them to a user. Then `bwrap` fails, and Claude Code does not start. The cause
is in the machine's settings for unprivileged user namespaces, which are the administrator's;
[Check the machine](#check-the-machine) prints them.

**Check.** The first command prints the paths of the two tools. The second makes a sandbox and
prints `BWRAP-OK`:

```bash
command -v bwrap socat
bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid true && echo BWRAP-OK
```

## The clone

**What it does.** These commands clone the repository and put its `bin/` directory on the `PATH`,
so that your shell finds the command `harness`.

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to your shell's start file too, for example `~/.bashrc`, so that each new
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
`/home/example` with your home directory, for example `/home/me`, in each value. The key `harness`
then holds the absolute path of the checkout, for example `/home/me/Research/Harness`.
[profile.md](profile.md) names each key and table, and the comments in the two files say what each
value is.

The key `repository_roots` names the directories that hold the repositories of your research
tree. Each entry must be a directory. With the example values, this command makes them:

```bash
mkdir -p ~/Research/Packages ~/Research/Experiments
```

The [providers](profile.md#the-providers) and the
[network overlay](profile.md#the-network-overlay) are optional.
[setup-macos.md](setup-macos.md#the-profile-and-the-model-tables) says when you need each, and
gives the command that copies its example.

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
the harness, the profile and the tree instructions. It needs two directories, else it stops with
exit 2, an error: the directory of the tree instructions, which the profile key `tree_agents`
names, and the configuration directory of OpenCode, `$OPENCODE_CONFIG_DIR`, else
`~/.config/opencode/`. It needs the directory of OpenCode also when you do not use OpenCode. It
makes `~/.claude/` and `~/.omp/agent/` itself. On a new machine, make the two directories before
the first install; the command uses the example value of `tree_agents`:

```bash
mkdir -p ~/Research/Environment/Agents/instructions ~/.config/opencode
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
[instruction file](concepts.md#instruction-file) to the place where its frontend reads it. The
first `--apply` also instantiates the Julia environment of the scripts, so it downloads the Julia
packages of `Project.toml`. The warnings after the plan name what the install does not do for
you. For example, the Kaimon entry needs a token file.

**Check.** Run the dry run again. Its last line is `0 change(s) to make.`, and it exits 0, which
means that the installed files are the files of the sources.

```bash
harness install
```

### Claude Code

The install writes the same Claude Code layer as on macOS, which
[setup-macos.md](setup-macos.md#claude-code) describes: the four sections of
`~/.claude/settings.json` from the settings template, and the files of the layer. Read the
difference of the sections in the dry run before each `--apply`. On Linux, the `sandbox` section
needs the tools of [The sandbox of Claude Code](#the-sandbox-of-claude-code).

### OpenCode

The install writes the OpenCode configuration as on macOS, which
[setup-macos.md](setup-macos.md#opencode) describes. The settings template keeps `~/.opencode/bin`,
where the installer of OpenCode puts the program, and `~/.local/bin` out of the writes of a
Claude Code session.

### oh-my-pi

The install writes the oh-my-pi configuration as on macOS, which
[setup-macos.md](setup-macos.md#oh-my-pi) describes. oh-my-pi reads `harness.yml` only when the
line `PI_CONFIG_FILES=~/.omp/agent/harness.yml` is in `~/.omp/agent/.env`, and its shell commands
get the variables of the settings template's `env` from the same file. So add the four lines that
[setup-macos.md](setup-macos.md#oh-my-pi) gives once; the install warns until they are there.

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

Add the `export` line to your shell's start file too, for example `~/.bashrc`, so that each new
shell finds `kaimon`.

**Why.** The Kaimon server of [The jobs](#the-jobs) runs `~/.julia/bin/kaimon`, and the update job
updates Kaimon.

**Check.** The command prints `KAIMON-OK`:

```bash
test -x ~/.julia/bin/kaimon && echo KAIMON-OK
```

## The jobs

**What it does.** The `systemd --user` units of the harness run three jobs: the Kaimon server, the
update job of Julia and the autocommit of `~/.claude`.
[components/other.md](components/other.md) says what each unit runs.

The units of the update job and the autocommit run the installed copies of two scripts of the
checkout in `~/.local/bin`, not the copies in the checkout: a session cannot write
`~/.local/bin`, and the jobs run outside the sandbox. These commands install the two copies:

```bash
install -m 755 ~/Research/Harness/launchagents/claude-autocommit ~/.local/bin/
install -m 755 ~/Research/Harness/scripts/julia-update.jl ~/.local/bin/
```

After you change one of the two scripts in the checkout, run its line again. The autocommit
commits in `~/.claude/`, which must be a git repository.

These commands render each unit with the profile into `~/.config/systemd/user/`, and enable the
timer of the autocommit:

```bash
mkdir -p ~/.config/systemd/user
for u in kaimon.service julia-update.service julia-update.timer claude-autocommit.service claude-autocommit.timer; do harness render ~/Research/Harness/systemd/"$u" > ~/.config/systemd/user/"$u"; done
systemctl --user daemon-reload
systemctl --user enable --now claude-autocommit.timer
```

**With Kaimon only.** The server runs `~/.julia/bin/kaimon`, and the update job stops with an
error without Kaimon. [Kaimon](#kaimon) installs it. With Kaimon in `~/.julia/bin`, this command
enables the server and the timer of the update job:

```bash
systemctl --user enable --now kaimon.service julia-update.timer
```

Then an administrator turns on linger for your account:

```bash
sudo loginctl enable-linger "$USER"
```

In an account that may not run `sudo`, an administrator runs this line in the administrator's own
account, with the name of your account in place of `"$USER"`.

**Why.** Without linger, the user manager of systemd starts at your first login and stops at your
last logout, and the units stop with it. Linger keeps the server and the timers running when no
one is logged in.

**Check.** The first command prints `Linger=yes`, and the second lists the timer of the
autocommit:

```bash
loginctl show-user "$USER" -p Linger
systemctl --user list-timers --no-pager | grep claude-autocommit
```

With Kaimon, the first command prints `active`, and the second lists the timer of the update job:

```bash
systemctl --user is-active kaimon.service
systemctl --user list-timers --no-pager | grep julia-update
```

## `git config core.hooksPath .githooks`

**Only to change the harness.** A user who only installs the harness skips this step.

**What it does.** These commands turn on the pre-push hook of this repository, once in the
checkout:

```bash
cd ~/Research/Harness
git config core.hooksPath .githooks
```

**Why.** The pre-push hook runs the leak checks and the tests before a push to `main`. Its leak
checks run gitleaks. [development.md](development.md#the-pre-push-hook) describes the hook.

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

## A machine reached over SSH

In an SSH session, no Secret Service answers, so `gh` and `glab` cannot keep their tokens in a
keyring. They keep them in files: `gh` in `~/.config/gh/hosts.yml`, and `glab` in
`~/.config/glab-cli/config.yml`, when you answer no to its question about a keyring. The settings
deny a session the read of both files. `gh` and `glab` run outside the sandbox of Claude Code, so
they still read their own files.

Over SSH, `gh` logs in with a device code: it prints a code and a URL, which you open on another
machine.

```bash
gh auth login --hostname github.com --git-protocol https
```

In Claude Code, `/login` prints a URL. Open it on another machine, and paste the code that it
gives back into Claude Code.

A desktop session has a Secret Service, so there `gh` and `glab` keep their tokens in it. The read
denies of the settings stay either way.
