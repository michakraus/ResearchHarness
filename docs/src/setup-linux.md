# Setup on Linux

This page sets up a Linux machine in four steps: the prerequisites, the clone, `harness setup`
and the check that it worked. `harness setup` puts the tools and the
[frontends](concepts.md#frontend) that you choose on the machine, and then sets up the harness,
with its [install](concepts.md#install).
[setup-reference.md](setup-reference.md) gives each step of `harness setup`: what it does, why,
and how to do it by hand. [setup-macos.md](setup-macos.md) is the page for macOS.

`harness setup` runs on Ubuntu 26.04 and 24.04, on `x86_64` and `aarch64` (64-bit Arm). The steps
are checked on Ubuntu 26.04; on Ubuntu 24.04, no step is checked yet. They use
`~/Research/Harness` as the path of the checkout.
[Introduction](concepts.md) explains the terms that this page uses, and the glossary there has an
entry for each.

## The prerequisites

`harness setup` needs Python and git, and the installers that it runs need curl. This line
installs them, and it needs an administrator, a user who may run `sudo`. Without `sudo`, ask an
administrator to run it for you:

```bash
sudo apt-get install python3 python3-venv git curl
```

Ubuntu 24.04 needs no other line, though its `python3` is 3.12. The harness runs on Python 3.14,
in its own Python environment: where the `python3` of the machine is older, at least 3.9, the
first run of `harness` lets uv fetch Python 3.14 for that environment. Ubuntu 26.04 and 24.04
package no uv: the first run of `harness` fetches the uv release that it pins.
[Dependencies](dependencies.md#you-provide) says why each one is a prerequisite.

## The clone

These commands clone the harness repository and put its `bin/` directory on the `PATH`, so that
your shell finds the command `harness`:

```bash
git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
export PATH="$HOME/Research/Harness/bin:$PATH"
```

Add the `export` line to your shell startup file too, `~/.bashrc` for bash or `~/.zshrc` for zsh,
so that each new shell finds `harness`. The first run of `harness` outside a
[session](concepts.md#session) fetches uv into `~/.local/bin`, checks its sha256, makes the Python
environment of the harness with `uv sync`, and names it in one line. Where no Python 3.14 is
installed, `uv sync` downloads it first. In a session, its line names `harness install --apply`,
which makes it; a session cannot fetch Python 3.14, so with a `python3` older than 3.14 it stops
`harness` with exit status 2 and says to run `harness` once in a plain terminal. A Python older
than 3.9 stops `harness` with exit status 2, an error that names the version found. This line
lists the subcommands:

```bash
harness --help
```

## `harness setup`

Run `harness setup` in your own terminal:

```bash
~/Research/Harness/bin/harness setup
```

Without a [profile](concepts.md#profile), it copies the example profile and asks for the keys
that have no default: `memory_project`, `tree_agents`, `org`, `repository_roots` and `leak`.
Before each question it says what the key holds and whether the answer is the same on every
machine, as the table of [The questions of harness setup](profile.md#the-questions-of-harness-setup)
gives it. An empty answer keeps the example's value; a list takes items separated by commas or a
TOML list, and replaces the example's list. Then it asks for the frontends and the components, and
whether this machine develops the harness. In a terminal, the frontends and the components are a
checkbox list: the arrow keys move, space checks or unchecks a name, and Enter accepts. Without a
terminal on both standard input and standard output, with `TERM` unset or `dumb`, without curses,
or in a window too small for the list, it asks from a numbered list instead. With the component
`jobs` and a profile without `claude_remote`, it asks for the URL of your `~/.claude` repository; an
empty answer means no autocommit job. It writes the answers into the profile, shows its plan, and
runs the plan after y/N: `git clone` of `claude_remote` into a `~/.claude` that is missing or
empty, first, before an installer can write below `~/.claude`; the directories, one
`sudo apt-get install -y` line, the pinned releases, the installers of the projects,
`harness install --apply`, `git config core.hooksPath .githooks`,
`harness trust --apply`, the jobs and the Kaimon token where `[setup]` chooses their components,
and `harness doctor`. After the jobs start the Kaimon server, the token step waits up to 60 s for
the server's key. [setup-reference.md](setup-reference.md) has a section for each step.

Two options change the run:

```bash
harness setup --dry-run   # print every command of the plan, and change nothing
harness setup --yes       # read [setup] of the profile, and ask nothing
```

**When a step fails**, `harness setup` prints its output and stops with exit status 2. Fix the
cause, then run `harness setup` again: it plans again and skips what is done. Without `sudo`, or
when `sudo -n true` is refused, it prints the `apt-get` line for an administrator and stops there:
run `sudo -v` first, or have an administrator run the line. On a new machine, the step
`harness trust --apply` waits for `~/.claude.json`, which Claude Code writes at its first start:
the run names the step and goes on. Start `claude` once, then run `harness trust --apply`.

**By hand.** `harness setup` prints the steps that it cannot do under *By hand*, before its last
step: with `jobs`, the lingering line for an administrator, unless `loginctl show-user` reads
`Linger=yes`, and without `claude_remote`, the key that the autocommit job needs (the script
`claude-autocommit` is still copied into `~/.local/bin`, but its job is not enabled); with
`antigravity`, the Antigravity app, and `harness install --apply` after its first start; each tool
with no package, release or installer; and one `export PATH=…` line. That line holds each
directory that the installed programs are in and that the `PATH` of the shell that started
`harness setup` lacks: `~/.local/bin`, with `julia` also `~/.juliaup/bin` and `~/.julia/bin`, and
with `opencode` also `~/.opencode/bin`. With zsh as your login shell, `harness setup` asks y/N
to append the line to `~/.zshrc`, after a comment line, unless `~/.zshrc` holds the line already;
with another shell, with `--yes`, or with a `~/.zshrc` that is a symlink, add the line to your
shell startup file yourself.

Over SSH, log in `gh` and Claude Code as
[A machine reached over SSH](setup-reference.md#a-machine-reached-over-ssh) says.

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
