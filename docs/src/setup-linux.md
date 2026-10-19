# Setup on Linux

This page gives each step from a clean Linux machine to a working harness. For each step it says
what the step does, why the harness needs it, and how you see that it worked.
[setup-macos.md](setup-macos.md) is the page for macOS.

The commands are for Debian and Ubuntu, with `apt-get`. The package names and the versions that
this page gives are checked on Ubuntu 26.04 only; other distributions and releases are not
checked. The steps use `~/Research/Harness` as the path of the checkout.
[Introduction](concepts.md) explains the words that this page uses, and the glossary there has an
entry for each.

**Without Julia code.** If you write no Julia, you can skip the steps and lines that this page
marks. You still need Julia itself, because the [install](concepts.md#install) runs it once.

**Without an administrator.** The `apt-get` lines and the linger of [The jobs](#the-jobs) need an
administrator, a user who may run `sudo`. Every tool that goes into `~/.local/bin` installs
without one.

**The exit codes.** Each verb of `harness` ends with an exit code, which your shell keeps in
`$?`. Exit 0 means that nothing would change or that the verb succeeded, exit 1 that a dry run
found something to change, and exit 2 an error. Each step below names the code that it expects,
with its meaning.

## The dependencies

**What it does.** These commands install every required tool that the harness calls, and the two
tools of the [sandbox](concepts.md#sandbox) of Claude Code. `apt-get` installs the tools that
Ubuntu 26.04 packages at or above the minimum of [Dependencies](dependencies.md), and bubblewrap,
socat and lsof. These two lines need an administrator:

```bash
sudo apt-get update
sudo apt-get install -y python3 git gh nodejs npm shellcheck coreutils rsync curl bubblewrap socat lsof
```

The tools of `~/.local/bin` need no administrator. First put that directory on the `PATH`:

```bash
mkdir -p ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
```

Add the `export` line to your shell's start file too, for example `~/.bashrc`, so that each new
shell finds the tools.

gitleaks comes from its release. These lines download the release and its checksum file
`gitleaks_<version>_checksums.txt`, check the release against the checksum, and only then install
`gitleaks` into `~/.local/bin`. The file names are those for x86_64:

```bash
d=$(mktemp -d); cd "$d"
v=8.30.1; f=gitleaks_${v}_linux_x64.tar.gz
curl -fsSL -O "https://github.com/gitleaks/gitleaks/releases/download/v$v/$f" -O "https://github.com/gitleaks/gitleaks/releases/download/v$v/gitleaks_${v}_checksums.txt"
grep " $f\$" "gitleaks_${v}_checksums.txt" | sha256sum -c - && tar -xzf "$f" gitleaks && install -m 755 gitleaks ~/.local/bin/
cd ~
```

**Only to push to the harness**, install gitleaks: on your machine, only the pre-push
[hook](concepts.md#hook) of the harness runs it, before a push to the harness. A user who only
installs the harness skips these lines. To update gitleaks, run the lines again with a new `v=`.

actionlint, fatou and Julia come from their own installers, which their projects give:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) latest ~/.local/bin
curl --proto '=https' --tlsv1.2 -sSf https://fatou.dev/install | sh
curl -fsSL https://install.julialang.org | sh
```

**Without Julia code**, skip the fatou line: fatou checks Julia code only.

The actionlint line installs `actionlint` into `~/.local/bin`, and the fatou installer checks
the checksum of its download. The installer of `juliaup` asks you to confirm its settings; with
its default settings, it installs `juliaup` and the current Julia release, and adds them to the
`PATH` in your shell's start file. Open a new terminal after it, so that your shell finds
`julia`. The six Julia packages of [Dependencies](dependencies.md#julia-and-its-packages) need no
command: the first install adds them.

The installer of OpenCode puts `opencode` into `~/.opencode/bin`, and adds that directory to the
`PATH` in your shell's start file.

**Why.** Each tool has the job that [Dependencies](dependencies.md#what-each-tool-does)
describes. Ubuntu 26.04 packages Python 3.14 and Node.js 22.22, which meet their minimums, but
gitleaks 8.16.0, below the minimum 8.21; so gitleaks comes from its release. A release of a
distribution can package an older version than the minimum that Dependencies gives. Then install
that tool from its own site. The pre-push hook also runs `python3.11`; where it is missing, the
hook prints one skip line, because CI runs it. bubblewrap and socat are the tools of
[The sandbox of Claude Code](#the-sandbox-of-claude-code). The update job of
[The jobs](#the-jobs) calls `lsof`. You need Julia even if you write no Julia code: the first
install instantiates the Julia environment of the harness's scripts, and it stops without
`julia`.

**Check.** Each command prints its version: Python 3.11 or later, Node.js 22.3 or later (or 20.16
or later in 20.x), actionlint 1.7.12 or later, and Julia 1.13 or later.

```bash
python3 --version
node --version
actionlint --version
julia --version
```

**Only to push to the harness**, check gitleaks too. It prints its version, 8.21 or later:

```bash
gitleaks version
```

## The sandbox of Claude Code

**What it does.** On Linux, Claude Code runs the shell commands of a
[session](concepts.md#session) in a sandbox of bubblewrap, `bwrap`, and it needs socat beside it.
The settings template of the harness sets `sandbox.enabled` and `failIfUnavailable: true`. So
without a working sandbox, Claude Code does not start, rather than run the commands without one.
[The dependencies](#the-dependencies) installs both tools.

**Why.** bubblewrap makes the sandbox from user namespaces of the kernel, and the settings of a
machine can refuse them to a user. Then `bwrap` fails, and Claude Code does not start. The cause
is in the machine's settings for unprivileged user namespaces, which are the administrator's.

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
[frontend](concepts.md#frontend).

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
line `PI_CONFIG_FILES=~/.omp/agent/harness.yml` is in `~/.omp/agent/.env`, so add that line once;
the install warns until it is there.

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
error without Kaimon. This page does not install Kaimon;
[Dependencies](dependencies.md#kaimon) says what it does. With Kaimon in `~/.julia/bin`, this
command enables the server and the timer of the update job:

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
