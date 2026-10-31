# Setup on macOS

This page sets up a Mac in four steps: the prerequisites, the clone, `harness setup` and the check
that it worked. `harness setup` puts the tools and the [frontends](concepts.md#frontend) that you
choose on the machine, and then sets up the harness, with its [install](concepts.md#install).
[setup-reference.md](setup-reference.md) gives each step of `harness setup`: what it does, why,
and how to do it by hand. [setup-linux.md](setup-linux.md) is the page for Linux.

The steps are checked on macOS 27 on Apple silicon (`arm64`) only, and they use
`~/Research/Harness` as the path of the checkout. [Introduction](concepts.md) explains the terms
that this page uses, and the glossary there has an entry for each.

## The prerequisites

`harness setup` needs Homebrew, Python 3.14, uv and git. When `command -v brew` prints nothing,
install Homebrew first. Its installer needs the password of an administrator, once. This line
runs the installer, and the second line puts `brew` on the `PATH` of the shell that you are in:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Add the `eval` line to `~/.zprofile` too, as the installer says. Then this line installs the
other three:

```bash
brew install python@3.14 uv git
```

[Dependencies](dependencies.md#you-provide) says why each one is a prerequisite.

## The clone

These commands clone the harness repository and put its `bin/` directory on the `PATH`, so that
your shell finds the command `harness`:

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to `~/.zshrc` too, so that each new shell finds `harness`. The first run of
`harness` outside a [session](concepts.md#session) makes the Python environment of the harness,
with `uv sync`, and names it in one line; in a session, its line names `harness install --apply`,
which makes it. A Python older than 3.14 stops `harness` with exit status 2, an error that names
the version found. This line lists the subcommands:

```bash
harness --help
```

## `harness setup`

Run `harness setup` in your own terminal:

```bash
~/Research/Harness/bin/harness setup
```

Without a [profile](concepts.md#profile), it copies the example profile and asks for the keys
that have no default: `memory_project`, `tree_agents`, `org`, `repository_roots` and `leak`. An
empty answer keeps the example's value. Then it asks for the frontends and the components, each
from a numbered list, and whether this machine develops the harness. It writes the answers into
`[setup]` of the profile, shows its plan, and runs the plan after y/N: the directories, the
Homebrew packages, the installers of Julia, Kaimon and Claude Code, `harness install --apply`,
`git config core.hooksPath .githooks`, `harness trust --apply`, the jobs and the Kaimon token
where `[setup]` chooses their components, and `harness doctor`.
[setup-reference.md](setup-reference.md) has a section for each step.

Two options change the run:

```bash
harness setup --dry-run   # print every command of the plan, and change nothing
harness setup --yes       # read [setup] of the profile, and ask nothing
```

**When a step fails**, `harness setup` prints its output and stops with exit status 2. Fix the
cause, then run `harness setup` again: it plans again and skips what is done. On a new machine,
the step `harness trust --apply` waits for `~/.claude.json`, which Claude Code writes at its first
start: the run names the step and goes on. Start `claude` once, then run `harness trust --apply`.

**By hand.** `harness setup` prints the steps that it cannot do under *By hand*, before its last
step. With the frontend `antigravity`, install the Antigravity app from
<https://antigravity.google/> and start it once. The installers put their programs into
`~/.local/bin` and `~/.julia/bin`. Add these lines to `~/.zshrc`, so that each new shell finds
them:

```bash
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.julia/bin:$PATH"
```

## The check that it worked

The last step of `harness setup` is `harness doctor`. It checks the machine, the tools, the
profile, the install and the jobs, read-only, and prints one line for each check: `PASS`, `WARN`,
`FAIL` or `SKIP`. A `FAIL` line names the section of [setup-reference.md](setup-reference.md)
that fixes it. Run it again after each fix, in a plain terminal:

```bash
harness doctor
```

It exits with status 0 when no check fails, and 1 when one fails. Then run the harness's own test
cases. The last line gives the number of cases, and it must say `0 wrong`:

```bash
harness test
```

At the start of each new Claude Code or Antigravity session, a [hook](concepts.md#hook) compares
`~/.claude/` with the sources. When a source changed after the last install, the session starts
with a warning about [drift](concepts.md#drift). The [tutorial](tutorial.md) starts your first
session.

**More.** To keep several machines the same, see
[Dotfiles (optional)](setup-reference.md#dotfiles-optional).
