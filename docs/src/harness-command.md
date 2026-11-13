# The `harness` command

## Synopsis

```text
harness [--profile F] [--models F] <subcommand> [options] [arguments]
harness --help
harness <subcommand> --help
```

## Description

`bin/harness` is the entry point of the harness. It starts on Python 3.9 or later and needs
nothing beyond the standard library. Put `bin/` on the `PATH`, as the step *The clone*
of [setup-macos.md](setup-macos.md#the-clone) and [setup-linux.md](setup-linux.md#the-clone) shows.
A Python below 3.9 prints the version that it found, 3.9 and 3.14, and exits 2.
Every subcommand runs on the interpreter of the Python environment of the harness, Python 3.14 or
later, which `bin/harness` makes with [uv](dependencies.md#uv) the first time that it runs outside
a session. Where the Python that starts it is below 3.14, uv fetches Python 3.14 for the
environment; a session with no environment cannot, and exits 2.

Each subcommand of `harness`, such as `install` or `doctor`, keeps one contract:

- **A subcommand that changes something is dry by default.** It prints its plan, and exits 1
  when something would change, 0 when nothing would. `--apply` makes the change, and exits 0.
- **A read-only subcommand takes no mode flag.** It exits 0, or 1 where its section says so.
- **Exit 2 is a usage error or a failure**, with one line on standard error:
  `harness <subcommand>: <reason>`.

So a dry run in a script tells you whether there is work to do: exit 1 means "run it again with
`--apply`". [`setup`](#setup) is the one exception: it has no `--apply`, because its y/N in a
terminal, or `--yes` in a script, is the confirmation, and `--dry-run` prints its plan. The two
checks differ: `harness test` exits 1 when a test case fails, and `harness doctor` exits 1 when a
check fails.

[development.md](development.md) describes the cases of `harness test`, and
[architecture.md](architecture.md) the Claude Code layer that `harness install` writes.

## Global options

These options come before the subcommand.

| option | meaning |
|:--|:--|
| `--profile F` | the private profile. If it is not given, the profile is `$RESEARCH_HARNESS_PROFILE`, or `~/.config/research-harness/profile.toml` if that is not set. `examples/profile.toml` shows every key |
| `--models F` | the model tables. They map each model tier to its model in each frontend, which is a tier of Antigravity's own in Antigravity, and an agent to its own model. If the option is not given, the model tables are `$RESEARCH_HARNESS_MODELS`, or `models.toml` beside the profile if that is not set. `examples/models.toml` shows the layout |
| `-h`, `--help` | print the list of subcommands. `harness <subcommand> --help` prints the options of one subcommand |

## Subcommands

| subcommand | does | changes something |
|:--|:--|:--|
| [`setup`](#setup) | installs the tools and frontends that the profile's `[setup]` chooses, then runs `install --apply`, `trust --apply`, the jobs and `doctor` | yes, after y/N or with `--yes` |
| [`install`](#install) | installs the Julia environment of the scripts, syncs the Python environment of the harness, and installs the Claude Code layer with the sections `permissions`, `hooks`, `sandbox` and `modelSettings` of `settings.json`, the OpenCode configuration, the oh-my-pi permission layer, instructions, rules, agents, models and MCP entry, and the Antigravity guard hook, permission rules, instructions, rules, skills, agents and MCP entry | yes |
| [`update`](#update) | brings the harness checkout up to `origin/main`, then runs `install --apply`. It does not move a checkout that is pinned to a commit | yes |
| [`doctor`](#doctor) | checks the setup of this machine: the tools, the profile, the install and the jobs | no |
| [`trust`](#trust) | sets Claude Code workspace trust for every repository of the tree | yes |
| [`dotfiles-kit`](#dotfiles-kit) | copies the dotfiles kit of the harness into a chezmoi source | yes |
| [`clone`](#clone) | clones each repository of the repository table that has no directory yet | yes |
| [`repos status`](#repos-status) | reports each repository: its branch, its commits ahead and behind, its changed files and its open pull requests | no |
| [`repos pull`](#repos-pull) | fast-forwards each repository that is behind its upstream | yes |
| [`repos push`](#repos-push) | pushes each repository that is ahead of its upstream, one at a time | yes |
| [`repos sync`](#repos-sync) | `repos pull`, then `repos push` | yes |
| [`githooks`](#githooks) | installs the shared git hooks into every package and experiment | yes |
| [`wiki-lint`](#wiki-lint) | lints the Markdown of the prose repositories: links, paths, line citations, frontmatter | no |
| [`wiki-lint-hook`](#wiki-lint-hook) | installs the wiki-lint hook into the prose repositories | yes |
| [`workflows`](#workflows) | installs the canonical GitHub workflows into every package and experiment | yes |
| [`dependents`](#dependents) | writes the list of direct dependents into each base of the profile key `dependents_bases` | yes |
| [`ci-protection`](#ci-protection) | protects every default branch on GitHub with a ruleset | yes |
| [`format`](#format) | runs JuliaFormatter over every tracked `.jl` file of the packages and experiments | yes |
| [`render`](#render) | prints a template rendered with the profile | no |
| [`get`](#get) | prints a profile value | no |
| [`leaks`](#leaks) | searches the repository for the private strings of the profile | no |
| [`settings`](#settings) | measures and checks the Claude Code settings: `surface`, `compare`, `twins`, `selftest` | no |
| [`permissions`](#permissions) | generates the OpenCode permission block and path-guard list from the settings template | yes |
| [`test`](#test) | runs the harness's own test cases | no |
| [`mutate`](#mutate) | runs named mutants of the Python code against the parts of `test` that should kill them | no |
| [`changelog`](#changelog) | joins the changelog fragments of `changelog.d/` into `CHANGELOG.md`, or checks that a branch adds one | yes |
| [`skill-triggers`](#skill-triggers) | tests whether each skill loads on its queries | runs paid sessions with `--apply` |

The sections below give each subcommand's synopsis, what it does, its options, its exit status,
the files that it reads and writes, where to run it, and examples. *Where to run it* says whether
an agent session can run the subcommand. A session runs in the Claude Code sandbox, which refuses
some writes and some network calls; a subcommand that needs them runs in your own terminal.

## Set up and keep a machine

### `setup`

```text
harness setup [--yes] [--dry-run]
```

Sets up a machine in one run: the tools and the frontends that the profile's
[`[setup]`](profile.md#the-setup-table) chooses, then the harness's own steps. The machine needs
Python 3.9 or later (uv fetches Python 3.14 below it), uv, git and the clone before it, and on
macOS Homebrew. It runs on macOS and on
Ubuntu, on the architectures `arm64` and `x86_64` of macOS and `x86_64` and `aarch64` of Linux.

In a terminal, `setup` asks its questions. Without a profile, it copies `examples/profile.toml`
and asks only for the keys that have no default, `memory_project`, `tree_agents`, `org`,
`repository_roots` and `leak`; an empty answer keeps the example's value. It then asks for the
frontends and the components, each from a checkbox list, or from a numbered list where the
checkbox list cannot run, and whether this machine develops the harness (`develop`), y/N. It
shows the plan and runs it after y/N. The plan's first step writes
the answers into `[setup]` of the profile. A missing `models.toml` beside the profile is copied
from `examples/models.toml`.

The plan holds these steps, in this order:

1. the directories that `install` needs: the tree instructions, each `repository_roots` entry,
   and with `opencode` the OpenCode configuration directory;
2. the packages. On macOS, one `brew install` line of the missing tools and of the tools below
   their minimum that Homebrew does not list as installed, and one `brew upgrade` line of the
   tools below their minimum that it lists. On Ubuntu, one `sudo apt-get install -y` line of each
   package whose apt candidate meets the tool's minimum;
3. on Ubuntu, each tool that apt does not meet, from its pinned release of `setup/tools.toml`
   into `~/.local/bin`, after a check of the sha256 of the archive; the release of Node.js is a
   whole tree, unpacked into `~/.local/share/research-harness/node/<version>/`, and `node`, `npm`
   and `npx` in `~/.local/bin` link into it;
4. the vendor installers, in this order: juliaup, Julia through juliaup when juliaup is there
   (`juliaup update` when Julia is below its minimum), fatou on Ubuntu, Kaimon as a Julia app,
   Claude Code, and on Ubuntu OpenCode (with `--no-modify-path`) and oh-my-pi;
5. with any frontend, `srt` from `sandbox/srt/package-lock.json`: `npm ci --ignore-scripts` into
   `~/.local/share/research-harness/srt/<version>/`, and `~/.local/bin/srt` linked into it, unless
   that tree of the same lockfile is linked already
   (*The pinned srt* of [The srt settings](components/sandbox.md));
6. `harness install --apply`;
7. `git config core.hooksPath .githooks` in the clone;
8. `harness trust --apply`;
9. with the component `jobs`, the jobs as the dotfiles kit's services step does them: the copies
   in `~/.local/bin`, then the launch agents or the `systemd --user` units, rendered with
   `harness render` and loaded; on macOS, the Seatbelt profiles of the Kaimon and julia-update
   jobs, rendered with `harness render sandbox/<job>.sb` into
   `~/.config/research-harness/sandbox/` before each one's launch agent, and before the Kaimon
   job's profile the `ps` shim `sandbox/shims/ps`, mode 755, into that directory's `shims/`; on
   Linux, first the sandbox check of `harness doctor`, which ends the run with exit 2 and one line
   that names `kernel.apparmor_restrict_unprivileged_userns` when `bwrap` cannot make a sandbox,
   then before the units `sandbox/jobbox` and `scripts/julia-update-server`, mode 755, into
   `~/.local/bin`, the `bwrap` arguments of the Kaimon and julia-update jobs, rendered with
   `harness render sandbox/<job>.bwrap` into `~/.config/research-harness/sandbox/`, and each
   write deny and pin of those arguments and `~/.cache/julia-update` that is missing, each new
   directory with mode 700 and the pin juliaup's lock file empty with mode 600; on both systems, `~/.cache/kaimon/pocl`, the directory of the Kaimon job's `POCL_CACHE_DIR`,
   created before that job is loaded, each new directory with mode 700;
10. with the component `julia`, the Kaimon token `~/.config/kaimon/auth-token`, mode 600, from
    the first key of `~/.config/kaimon/config.json` when that file exists and the token does not;
11. `harness doctor`, after the lines under *By hand*, so that its report ends the run.

A tool that is installed at or above its minimum of [dependencies.md](dependencies.md) is skipped;
a tool with no minimum, only a version that it is tested with, is met by any version. After a
Homebrew line or `juliaup update` for a tool below its minimum, `setup` reads the tool's version
again. When it is still below, the step fails: for Julia, whose `juliaup update` keeps the
default channel, with the line `juliaup add release && juliaup default release`; for another
tool, with the path of the copy that comes first on the `PATH`.
`setup/tools.toml` holds the minimums and the pinned releases. The OpenCode installer runs only
when `opencode` is not on the `PATH`, and the juliaup installer only when `juliaup` is not.
`setup` runs the OpenCode installer with `--no-modify-path` and prints the `PATH` line of
`~/.opencode/bin` instead; the juliaup installer adds its own `PATH` block to the shell startup
files. Each step that `setup` cannot do, such as the Antigravity app and
`loginctl enable-linger` for the jobs on Linux, is printed under *By hand*.

| option | meaning |
|:--|:--|
| `--yes` | read `[setup]` of the profile, or the defaults of a profile without it, and ask nothing. It never writes the profile |
| `--dry-run` | print every command of the plan and change nothing, not even the profile |

**Exit status:** 0 after the plan ran and `harness doctor` passed, after the dry run, and when
the answer to the plan is no; 1 after the plan ran and `harness doctor` reported a FAIL; 2 when a
step fails, which prints its output first, `harness doctor` with a status other than 0 or 1
included; when stdin is no terminal and `--yes` is not given; when `--yes` finds no profile; when
`[setup]` cannot be written into the profile in place, naming the table to write; when an answer
is not valid UTF-8; on Ubuntu when `apt-cache` fails, and without `sudo`, or when `sudo -n true`
is refused, after the apt line is printed for an administrator; and on a system other than macOS
and Ubuntu, or an unknown architecture. A second run plans again and starts from the first step;
each step skips what is done.

**Reads:** the profile, `setup/tools.toml`, the versions of the installed tools, and on Ubuntu
`apt-cache policy`. **Writes:** the profile (in a terminal), `models.toml` when it is missing, the
packages and programs that the steps install, and what `install`, `trust` and the jobs write.

**Where to run it:** in your own terminal. A session runs only `--dry-run`.

```bash
harness setup --dry-run --yes   # the plan for [setup], with no question
harness setup                   # ask, show the plan, run it after y/N
harness setup --yes             # the dotfiles kit's harness step
```

### `install`

```text
harness install [--apply] [--force]
```

Installs the Julia environment of the scripts, syncs the Python environment of the harness, and
installs the configuration of each frontend that the profile's
[`[setup]`](profile.md#the-setup-table) chooses: Claude Code, OpenCode, oh-my-pi and
Antigravity. Without `[setup]`, it installs all four and the Julia environment; with it, the Julia
environment only with the `julia` component, and the Python environment always. A layer of a
frontend that `[setup]` does not choose is neither planned nor removed. The installed
configuration is not writable from a session, so the sources live in the harness repository, and
`install` copies them into place. It plans every chosen frontend first and writes nothing while
it plans. So a refusal stops the install before the first write. After `--apply`, it prints the
restart line of each frontend whose files changed.

| option | meaning |
|:--|:--|
| `--apply` | install; without it, print the plan |
| `--force` | replace a file that the plan refuses to replace; the refusal names the file |

**Exit status:** 0 when nothing would change or `--apply` installed; 1 when the dry run has a
change; 2 when a plan refuses, or the profile or the model tables do not load.

**Reads:** the profile, the model tables, `providers.toml` and `network.toml` beside the profile,
the tree instructions (`tree_agents` of the profile), and the sources of the harness checkout.
**Writes:** for each chosen frontend, below `~/.claude/`, the OpenCode configuration directory,
the oh-my-pi directory, and `~/.gemini/` when Antigravity has made it; the Julia environment with
the `julia` component (see [The Julia environment](#the-julia-environment)); and the Python
environment (`~/.local/share/research-harness/python/`, with the `dev` group when `[setup]` of
the profile sets `develop = true`). With `claude` chosen, it writes the stamp
`~/.claude/.harness-install.json`, which the drift warning at session start reads. For each
chosen frontend it also writes the `srt` settings,
`~/.config/research-harness/sandbox/<frontend>.json`; with any frontend chosen, the launcher
`~/.local/bin/agentbox`; and with `claude` chosen, Claude Code's override
`~/.config/research-harness/sandbox/claude-inner-off.json`
([The srt settings](components/sandbox.md)).

**Where to run it:** in your own terminal. A session cannot write the installed files.

`install` warns when its checkout is behind its `origin/main`, as the last fetch saw it. It
fetches nothing, and it installs the checkout as it is. To fetch, merge and install in one step,
use `update`.

```bash
harness install            # the plan
harness install --apply    # install
```

### `update`

```text
harness update [--apply]
```

Brings the harness checkout up to `origin/main`, and installs it. It works on the checkout that
runs it, and only when its branch is `main` with the upstream `origin/main`: a development
checkout. The dry run fetches, prints the new commits and the files that they change, and exits 1
when there is a new commit. `--apply` also shows the whole diff, through git's pager, and asks
`y/N`. On `y` it merges `--ff-only` and runs `harness install --apply` from the merged checkout.
Any other answer merges and installs nothing.

A checkout at a detached HEAD is pinned to a commit, for example by the dotfiles of a machine.
Only a reviewed change of the pin moves it, so `update` stops there and moves nothing.

| option | meaning |
|:--|:--|
| `--apply` | show the diff, ask, merge and install |

**Exit status:** 0 when the checkout is up to date, or after `--apply`; 1 when the dry run finds
a new commit; 2 when the checkout is pinned, is on another branch, tracks another upstream, has
commits that `origin/main` lacks, cannot fetch, has changes to tracked files (`--apply`), or has
no terminal for the question (`--apply`), and when `install --apply` fails after the merge.

**Where to run it:** in your own terminal. `--apply` asks a question, and the install writes files
that a session cannot write.

```bash
harness update            # fetch and list the new commits
harness update --apply    # read the diff, answer y, merge and install
```

### `doctor`

```text
harness doctor [--full]
```

Checks this machine's setup and changes nothing. It prints one line per check: `PASS`, `WARN`,
`FAIL` or `SKIP`, the name of the check and a detail. A `FAIL` line also names the section of the
setup pages that fixes it. The checks are, in this order: the machine; the tools of
[dependencies.md](dependencies.md), each with its minimum version; the profile; the dry run of
`install` and its warnings; and the jobs (Kaimon, the update job, the autocommit job). Where the
profile's `[setup]` does not choose `opencode`, the OpenCode directory check is a `SKIP`, and
without the `julia` component so are the Julia packages. A layer of a frontend that `[setup]`
does not choose and that is still on disk is a `WARN` that names `[setup]` and the frontend, and
so is such a frontend whose plan refuses, with the refusal; `doctor` removes nothing.

| option | meaning |
|:--|:--|
| `--full` | also run `harness test` and `julia -e 'using Revise'`, which take minutes |

**Exit status:** 1 when a check fails, else 0. A `WARN` or a `SKIP` does not count.

**Where to run it:** in a plain terminal. In a session, the sandbox refuses some commands, and
those checks are `SKIP` with the reason.

```bash
harness doctor
harness doctor --full
```

### `trust`

```text
harness trust [--apply]
```

Marks the research root and every git repository below it as trusted in Claude Code's
`~/.claude.json`, so that Claude Code shows no trust dialog. The dry run lists each untrusted
root.

**Exit status:** 0 when every root is trusted, or after `--apply`; 1 when the dry run finds an
untrusted root; 2 when `~/.claude.json` cannot be read or is not a JSON object.

**Where to run it:** in your own terminal. A session cannot read `~/.claude.json`. Run it again
after `clone`: a new clone is not trusted.

### `dotfiles-kit`

```text
harness dotfiles-kit [--apply] DEST
```

Compares the chezmoi source `DEST` with the dotfiles kit of the harness, `examples/dotfiles/`.
The file `examples/dotfiles/kit.toml` names each file of the kit and its class. A *code* file
stays identical to the kit, so the dry run lists each code file that is missing from `DEST`, or
differs in its bytes or in its execute bit. A *seed* file belongs to `DEST` once it is there, so
the dry run lists each seed file that is missing, and `--apply` never writes a seed file that
exists. A file of `DEST` that `kit.toml` does not name is not listed and not changed.

`DEST` is a clone of your dotfiles repository. `dotfiles-kit` refuses the source that chezmoi
applies, `~/.local/share/chezmoi`, and each directory below it, under any name of the same
directory: a symbolic link, `..`, a case variant or a firmlink. A change of the applied source
goes through a branch and a merge request. Every file that `dotfiles-kit` lists or writes stays
inside `DEST`: when the directory of a file of `kit.toml` links out of `DEST`, the dry run and
`--apply` stop before the first write and name the file. A symbolic link at a code file's own path
is replaced by the file; anything else there that is not a regular file, such as a directory or
a FIFO, stops `--apply`.

| option | meaning |
|:--|:--|
| `--apply` | copy the listed files; without it, print the list |

**Exit status:** 0 when nothing would change, or after `--apply`; 1 when the dry run lists a file;
2 when `DEST` is not a directory or is the applied source, when `kit.toml` cannot be read or
names a file that the harness lacks or a class other than `code` and `seed`, when the directory of
a file resolves outside `DEST`, when a code file of `DEST` cannot be read, and when a file cannot
be written.

**Where to run it:** where you can write `DEST`. Commit the change on a branch of the clone.
[The `dotfiles` command](dotfiles-command.md#start-a-private-copy) gives the steps of a private
copy, and the scripts that the kit installs.

```bash
harness dotfiles-kit ~/src/dotfiles            # the list
harness dotfiles-kit --apply ~/src/dotfiles    # copy
```

## The repositories of the research tree

These subcommands find the research tree at `$RESEARCH_ROOT`, or `~/Research` if it is not set.
[The research tree](research-tree.md#clone-sync-and-trust) shows them in the order of a working
day.

### The repository table

`clone` and `repos` read the repository table: `$RESEARCH_HARNESS_REPOSITORIES`, or
`repositories.toml` beside the profile if that is not set. It names each repository of the tree
and its clone URL:

```toml
# A fixed repository: its directory is the key in title case, ~/Research/Knowledge.
knowledge = "https://git.example.org/example/knowledge.git"

# A group: its directory is the table's name in title case, and each key a directory there.
[packages]
Example = "https://github.com/example/Example.jl.git"

[papers]
"A Paper Title" = "https://git.example.org/example/papers/a-paper.git"
```

The fixed repositories are `knowledge`, `environment`, `tasks` and `library`.
The groups are `packages`, `experiments`, `papers`, `books`, `talks` and `projects`. Another key
is an error, and so is a directory name that holds a `/` or starts with `.`.
`examples/repositories.toml` shows a whole table.

The table is optional. Without it, `repos` takes each git repository that it finds directly below
the group directories, and each fixed repository that exists; `clone` stops. Directory names
compare in Unicode NFC, so a name that the file system stores decomposed matches the table.

### Selections

`clone` and each action of `repos` take zero or more selections: a group (`packages`) or a fixed
repository (`knowledge`), in any case. Without a selection, `clone`, `repos status` and
`repos pull` take every group and every fixed repository, and `repos push` and `repos sync` take
`packages` and `experiments`. An unknown selection exits 2 and names the valid ones.

### `clone`

```text
harness clone [SELECTION ...] [--apply]
```

Clones each repository of the table that has no directory yet. A directory that exists and is
a clone of its URL is skipped. Two URLs are the same when they agree without a trailing `/` and
`.git`. A directory that exists and is not a clone of its URL is in the way: the subcommand names
it and stops before the first clone, and nothing is cloned.

| option | meaning |
|:--|:--|
| `SELECTION` | a group or a fixed repository; none means all |
| `--apply` | clone; without it, list the clones |

**Exit status:** 0 when nothing is to clone, or after `--apply`; 1 when the dry run lists a clone;
2 when there is no table, the table is wrong, a directory is in the way, or a clone fails.

**Where to run it:** in your own terminal: a clone needs the network and your credentials. A new
clone has no git hooks and no workspace trust. After `--apply`, the subcommand names the three
runs that give them.

```bash
harness clone                 # list what a new machine still lacks
harness clone --apply         # clone it all
harness clone papers --apply  # clone the papers only
harness githooks --apply      # then the hooks,
harness wiki-lint-hook --apply
harness trust --apply         # and the workspace trust
```

### `repos status`

```text
harness repos status [SELECTION ...] [--no-fetch] [--no-prs]
```

Fetches every repository that has an origin, eight at a time, then prints one line for each
repository: the branch, the commits ahead of and behind its upstream, the number of changed
tracked files, and the numbers of the open pull requests. It asks `gh` for a repository on
github.com, and `glab` for a repository on any other host. A `?` means that the host could not be
asked; a `-` means no open pull request. A line also names:

- `MISSING`: a repository of the table that is not cloned;
- `not in the table`: a git repository in a group directory that the table does not list;
- `no origin` and `no upstream`;
- `origin … is not the table's …`: a clone whose origin differs from the table;
- `fetch failed`, with the last line of git's error.

| option | meaning |
|:--|:--|
| `SELECTION` | a group or a fixed repository; none means all |
| `--no-fetch` | read the remote-tracking refs as the last fetch left them |
| `--no-prs` | ask no host for pull requests |

**Exit status:** 0; 2 when the table is wrong or a selection is unknown. The report itself never
makes it exit 1.

**Where to run it:** anywhere. In a session's sandbox, the fetches and the pull-request queries
can fail; `--no-fetch --no-prs` then reports from the local state.

```bash
harness repos status
harness repos status packages experiments
harness repos status --no-fetch --no-prs
```

### `repos pull`

```text
harness repos pull [SELECTION ...] [--apply]
```

Fetches, then fast-forwards each branch that is behind its upstream, with `git merge --ff-only`.
It skips a branch with no upstream, a branch that has diverged from its upstream, and a branch
whose incoming commits change a file with local changes. A local change to any other file stays
as it is. A local change whose content already equals the upstream's is no clash: `pull` resets
the file to `HEAD`, fast-forwards, and names the file. The dry run fetches too: a fetch changes no
working tree.

| option | meaning |
|:--|:--|
| `SELECTION` | a group or a fixed repository; none means all |
| `--apply` | fast-forward; without it, list the branches that would move |

**Exit status:** 0 when nothing is behind, or after `--apply`; 1 when the dry run lists a branch;
2 when a merge fails.

**Where to run it:** in your own terminal, which can reach the network.

```bash
harness repos pull
harness repos pull --apply
```

### `repos push`

```text
harness repos push [SELECTION ...] [--apply] [--no-verify] [--include-topic-branches]
```

Fetches, then pushes each branch that is ahead of its upstream, one repository at a time. It
checks each push against the remote ref, as `git ls-remote` reports it, not by the exit status of
`git push`. It skips a branch with no upstream, and a branch that is also behind its upstream:
pull or rebase it first. It skips a branch that is not the default branch, because a commit on a
topic branch does not reach the required checks. The dry run names up to three `.jl` files of
each push.

The pushes run in sequence, never in parallel. The pre-push hook of a package runs its full test
suite, and two suites that load the same package with different settings invalidate each other's
precompiled files.

| option | meaning |
|:--|:--|
| `SELECTION` | a group or a fixed repository; none means `packages` and `experiments` |
| `--apply` | push; without it, list the pushes |
| `--no-verify`, `--skip-hooks` | push with `git push --no-verify`: the pre-push hook does not run |
| `--include-topic-branches` | also push a branch that is not the default branch |

Use `--no-verify` only for a push that touches no Julia source and no `[compat]` entry, such as a
workflow, a README or a changelog. CI runs on the push anyway.

**Exit status:** 0 when nothing is ahead, or after `--apply`; 1 when the dry run lists a push;
2 when a push fails. A failed push prints the last lines of git's output.

**Where to run it:** in your own terminal, and expect it to take hours. A pre-push suite takes a
few minutes in most packages and 10 to 30 minutes in the large ones, and prints nothing while it
runs. A tool call of a session stops after ten minutes. Stopping a push in the middle of its suite
leaves a Julia process behind; stop that process too.

```bash
harness repos push                           # the plan
harness repos push --apply                   # push, with each pre-push suite
harness repos push experiments --apply --no-verify
```

### `repos sync`

```text
harness repos sync [SELECTION ...] [--apply] [--no-verify] [--include-topic-branches]
```

Runs `repos pull`, then `repos push`, on the same selection, with the same options. Without a
selection it takes `packages` and `experiments`.

**Exit status:** as `repos pull` and `repos push`: 1 when the dry run has something to pull or to
push; 2 when a merge or a push fails.

**Where to run it:** in your own terminal, as `repos push`.

```bash
harness repos sync
harness repos sync --apply
```

### `githooks`

```text
harness githooks [--apply]
```

Copies `githooks/pre-commit`, `githooks/pre-commit.jl`, `githooks/pre-push`,
`githooks/pre-push.jl` and `scripts/test-layout.jl` into `.githooks/` of each git repository
below `Packages/` and `Experiments/`, and sets `core.hooksPath` to `.githooks`. The copies are
tracked files of each repository: read the diff, then commit each file by name. `core.hooksPath`
is local configuration, so a new clone needs this subcommand again.

**Exit status:** 0 when every copy is current, or after `--apply`; 1 when the dry run has a
change; 2 when `core.hooksPath` cannot be set. The subcommand then prints the command for each
repository.

**Where to run it:** in your own terminal. A session cannot write `.git/config`.

### `wiki-lint`

```text
harness wiki-lint [TREE ...] [--strict] [--quiet]
```

Checks the structure of the Markdown in the prose repositories of the research tree: the vaults
`Knowledge` and `Environment`, and the reference trees `Tasks` and `Library`, or the trees that
`TREE` names. It finds text that a later change of the tree made false, for example a broken
link, a path that does not exist, or a line citation past the end of its file. A vault gets every
check. A reference tree gets the checks of paths and line citations; `Tasks` gets the schema of
the task board too. The lint skips each `CHANGELOG.md`. It reads only the working tree: no model,
no index, no network.

A frontmatter is YAML. In the vaults and in `Tasks`, a block that does not parse is an ERROR on
the line that PyYAML names, and so is a key that a block repeats. A key or a value that YAML 1.1
converts, an item of a list included, such as `draft: no` (false) or `mode: 0755` (493), is a
WARN that names the key and the value; quote it to keep the text. The date of `verified:` is text
of the form `YYYY-MM-DD`.

It prints one line per finding, `<SEVERITY>  [<check>]  <file>[:<line>] — <message>`, then the
counts by check and the totals. `--quiet` prints no WARN line, and the ERROR lines only when there
is one. The hook `pre-commit-wiki` (see [Git hooks and workflows](components/githooks.md)) runs
it with `--quiet` before each commit in a prose repository.

**Exit status:** 0 when there is no ERROR, and with `--strict` no WARN; 1 on a finding at the
failing level; 2 for a `TREE` that is no directory, and when the Python environment lacks PyYAML.

**Where to run it:** anywhere; it changes nothing.

### `wiki-lint-hook`

```text
harness wiki-lint-hook [--apply]
```

Copies `githooks/pre-commit-wiki` as `.githooks/pre-commit` into each prose repository of the
research tree (`Knowledge`, `Environment`, `Tasks`, `Library`), and sets
`core.hooksPath`. It skips a name that is not a git repository.

**Exit status and where to run it:** as `githooks`.

### `workflows`

```text
harness workflows [--apply]
```

Copies the canonical files of `githooks/workflows/` into each package and experiment that has a
`Project.toml`: `CI.yml`, `dependabot.yml` and `codecov.yml` into each, `TagBot.yml` into each
package, and `Documenter.yml` where a tracked `docs/make.jl` exists. A repository that the profile
keys `docs_exceptions` or `docs_additions` name keeps its own documentation workflow. It copies
`Dependents.yml` to `.github/workflows/Dependents.yml` and `dependents.jl` to
`.github/dependents.jl` of each base that the profile key `dependents_bases` names, and deletes
both from every other repository. It deletes the retired `CompatHelper.yml`.

**Exit status:** 0 when every file is current, or after `--apply`; 1 when the dry run has a
change. 2 when a template is missing. 2 also when `dependents_bases` names a repository that is
not a git repository with a `Project.toml` below `Packages/`.

**Where to run it:** anywhere; it writes tracked files only. Commit each file by name.

### `dependents`

```text
harness dependents [--apply]
```

Writes `.github/dependents.toml` into each base that the profile key `dependents_bases` names.
A direct dependent of a base is a git repository below `Packages/` whose `Project.toml` has the
base's UUID in `[deps]`. `[weakdeps]`, `[extras]`, `test/Project.toml` and `Experiments/` do not
count, and a base is not its own dependent. The file holds one `[[dependent]]` table per
dependent, sorted by name. Each table has two keys:

- `name`: the name of the dependent's directory;
- `repository`: the GitHub `owner/name` of the dependent's `origin`.

An `origin` has one of two forms. The first is a URL
`<scheme>://[user@]github.com[:port]/owner/name[.git][/]`, with the scheme `https`, `http`,
`ssh`, `git+ssh` or `ssh+git`. The second is the scp form `[user@]github.com:owner/name[.git][/]`.
Scheme and host match in any case. Every other form is refused, such as another scheme or host, a
local path, a query or a fragment, or a name `.` or `..`. The census of every base and the read of
every old file run before the first write, so a refusal writes no file.
Without `--apply` it prints the diff of each file that would change. The `Dependents.yml` workflow
of the base reads the file into its matrix.

**Exit status:** 0 when every file is current, or after `--apply`; 1 when the dry run has a
change. 2, with a message that names the repository or the file, for each of these refusals:

- `dependents_bases` names a repository that is not a git repository with a `Project.toml` below
  `Packages/`;
- a base has no `uuid`;
- the `Project.toml` of a base or of a package is not TOML;
- the directory name of a dependent is not a name that `dependents.toml` can hold, such as a name
  with a space;
- a dependent has no `origin`, or an `origin` of neither form above;
- the old `.github/dependents.toml` is not a regular file, or is not UTF-8, or its `.github` is a
  symbolic link or not a directory.

**Where to run it:** anywhere; it writes tracked files only and does not commit. Commit
`.github/dependents.toml` by name in each base.

### `ci-protection`

```text
harness ci-protection [--apply] [--remove-classic]
```

Protects the default branch of each repository that has a `CI.yml` with a GitHub ruleset named
`main`, which requires the status checks of the canonical `CI.yml`. A repository with a
`test/ci-groups.toml` requires one check per test group, version and system, as `CI.yml` names its
jobs there, and the jobs of each workflow that the file names in `workflows`, such as
`Metal.yml`. Then it protects the Harness
itself, the checkout that runs the command, with the same ruleset; there the required checks are
the jobs of `.github/workflows/test.yml` that report on every pull request and are not warnings.
It also turns on auto-merge and the deletion of merged branches. It reads the current state first
and writes only what differs. It refuses to run unless `verify-workflows.jl` passes: a required
check that never reports leaves every pull request pending.

| option | meaning |
|:--|:--|
| `--apply` | write through `gh api`; without it, print what would change |
| `--remove-classic` | delete classic branch protection where the ruleset passes every check |

Run the ruleset first and `--remove-classic` afterwards, so that a branch is never left
unprotected.

**Exit status:** 0 when nothing would change, or after `--apply`; 1 when the dry run has a change;
2 when the workflows are not canonical or a call fails.

**Where to run it:** in your own terminal. In a session's sandbox only the first `gh` call of a
process succeeds.

### `format`

```text
harness format [--apply]
```

Runs JuliaFormatter over the tracked `.jl` files of the repositories below `Packages/` and
`Experiments/`. It skips a repository that has no `.JuliaFormatter.toml`, and each file on which
JuliaFormatter crashes. The dry run counts the files that would change.

**Exit status:** 0 when no file would change, or after `--apply`; 1 when the dry run counts a
file; 2 on a failure.

**Files:** the marker, the skip list and the log go to `$FMT_OUT`, or `$TMPDIR` if that is not
set. The skip list that remains names the files that JuliaFormatter cannot format.

**Where to run it:** in your own terminal; it runs Julia over the whole tree.

## The profile

### `render`

```text
harness render TEMPLATE
```

Prints `TEMPLATE` with each placeholder `{key}` replaced by its profile value.
[profile.md](profile.md) describes the placeholders.

**Exit status:** 0; 2 when a placeholder has no profile value.

### `get`

```text
harness get KEY
```

Prints the profile value of `KEY`, one line per item of a list, and `develop` of `[setup]` as
`true` or `false`. A path that starts with `~` is printed with the home directory.

**Exit status:** 0; 2 when the profile does not load or has no `KEY`.

```bash
harness get repository_roots
```

### `leaks`

```text
harness leaks [--commits FILE]
```

Searches the tracked files of the harness repository, and the templates rendered with the dummy
profile, for the private strings of the profile's `leak` list and for the names of the research
tree. It matches a whole word. The pre-push hook of the harness runs it.

| option | meaning |
|:--|:--|
| `--commits FILE` | also search the paths and lines that each commit of `FILE` adds, and its message; one SHA per line |

**Exit status:** 0 with no hit, 1 on a hit, 2 when the profile does not load.

## Settings and permissions

### `settings`

```text
harness settings surface [--settings F] [--days N] [--head N]
harness settings compare OLD NEW [--days N]
harness settings twins [--settings F] [--list allow|ask|deny]
harness settings selftest
```

Measures and checks the Claude Code settings against the Bash commands of the recent session
transcripts in `~/.claude/projects/`. Each subcommand of `settings` is read-only.

| subcommand | does |
|:--|:--|
| `surface` | counts the segments of the recent Bash commands that reach a permission prompt under one settings file, by leading word. `--days N` reads the last `N` days (default 5); `--head N` prints the `N` most frequent prompting segments |
| `compare` | the same count for two settings files, side by side, with the difference |
| `twins` | prints the `git -C * <sub>` twin of each plain `git` rule: `Bash(git status *)` does not match `git -C /path status` |
| `selftest` | checks the matcher against the recorded cases of Claude Code; run it after a Claude Code update. Exits 1 when a case fails |

`--settings F` defaults to `~/.claude/settings.json`.

**Exit status:** 0; 1 for a failed `selftest` case; 2 when a settings file is missing, cannot be
read, or is not a JSON object.

### `permissions`

```text
harness permissions [--apply]
```

Regenerates the permission block of `adapters/opencode/opencode.jsonc` and
`adapters/opencode/plugins/guard-paths.json` in the harness repository from the `deny` and `ask`
rules of the settings template. The dry run prints the report and the diff.

**Exit status:** 0 when the files are current, or after `--apply`; 1 when the dry run has a diff.

**Where to run it:** in the harness checkout; commit the two files with the change of the
template.

## Tests

### `test`

```text
harness test [NAME ...] [--changed BASE] [--list] [--jobs N] [--log FILE]
```

Runs the harness's own test cases as parts, each in a process of its own: the cases of each
module and adapter, the groups of the hook probe and of `doctor`, and the contract sweep. The
sweep runs the dry run of each subcommand on a fixture home directory and checks the contract
above. It prints each part's lines and, last, `<n> cases, <w> wrong`.
[development.md](development.md#tests) describes the parts and the selection.

| option | meaning |
|:--|:--|
| `NAME ...` | run these parts, with `docs` and `sweep` |
| `--changed BASE` | run the parts that own a path of `git diff --name-status BASE...HEAD`, with `docs` and `sweep`; a path that no part owns selects every part |
| `--list` | print the selected part names, one per line, and run nothing |
| `--jobs N` | run at most N parts at once; the default is half the CPUs |
| `--log FILE` | write every line and a line `part <name>: <n> cases, <w> wrong` per part to `FILE`; print only the `BAD` lines and the summary |

At most two runs share a machine; a third waits for one of them to end.

**Exit status:** 0 when every case passes, 1 when a case fails, 2 on a usage error: an unknown
part, part names together with `--changed`, an empty `BASE` or one that git cannot resolve,
`--jobs` below 1, a `--log` file whose directory does not exist, or a directory of the slot files
that cannot be made or written.

### `mutate`

```text
harness mutate SPEC
```

Runs named mutants of the Python code of the harness. `SPEC` is a TOML file with one table per
mutant, in the order in which they run:

```toml
[MU1]
file = "lib/harness/changelog.py"   # a path relative to the harness checkout
anchor = 'DIRECTORY = "changelog.d"' # a text on exactly one line of file
old = 'HEADING = "## Unreleased"'    # a text that occurs exactly once after the end of that line
new = 'HEADING = "## Released"'      # the text that replaces it
tests = ["changelog"]                # the parts of harness test that should kill the mutant
```

The anchor tells two equal texts apart without a line number. `mutate` copies the checkout into a
temporary directory: its tracked files and its untracked files that git does not ignore, with
their working-tree bytes, as a git repository, because the parts `docs` and `sweep` read
`git ls-files`. It writes nothing into the checkout or its `.git`, and removes the copy after the
run, also after an error or an interrupt. The copy first runs `harness test` with the parts of
every mutant, unmutated. Then each mutant is applied alone to the copy, `harness test` runs with
its parts, and the file is reverted. It prints one line per mutant and, last,
`<n> mutants, <k> killed, <s> survived, <i> invalid`:

| line | meaning |
|:--|:--|
| `<name> killed: <line>` | the first `BAD` line of the run. A run that fails with no `BAD` line, such as a crash at import, gives `exit <status> with no BAD line: <its last line>` |
| `<name> killed (timeout): <line>` | the first `BAD` line is that of a part stopped after its timeout of 300 s |
| `<name> SURVIVED` | every case of the mutant's parts passes |
| `<name> invalid: <error>` | `ast.parse` refuses the mutated file; no test runs |

A line of `file` ends at a newline only; a form feed does not end it. `mutate` stops before any
mutant runs, and the message names the mutant, when a table lacks one of the five keys, has
another key, or has a value of the wrong type; `old` is empty; `file` is not a file of the copy or
is not UTF-8; `anchor` is on no line or on more than one; `old` does not occur exactly once after
the anchor's line; `tests` is empty, or names a part that `harness test --list` does not name. It
also stops when the spec cannot be read or holds no mutant, with a message that names the spec;
when `harness test --list` of the copy fails, with its exit status; and when the unmutated copy
fails the parts of the spec, with the first `BAD` line.

**Exit status:** 0 when every mutant is killed, 1 when a mutant survives or is invalid, 2 when it
stops.

**Where to run it:** in the harness checkout. It runs `harness test`, so it takes as long as the
parts that it names, once for the unmutated copy and once per valid mutant.

### `changelog`

```text
harness changelog [--apply | --check BASE]
```

Joins the changelog fragments of the harness checkout into its `CHANGELOG.md`. A fragment is a
file `changelog.d/*.md` other than `README.md`, and holds the entry of one branch;
`changelog.d/README.md` gives its name and its form. The dry run prints the `## Unreleased` block
that the fragments make: each fragment's text, with a final newline added where it lacks one,
separated by one blank line. The newest fragment comes first, by the committer date of the commit
that added it; a fragment that no commit holds comes before them, and fragments of the same date
go by file name.

| option | meaning |
|:--|:--|
| `--apply` | put the block at the top of the `## Unreleased` section of `CHANGELOG.md`, above its entries, and delete the fragments. Without that heading, it inserts `## Unreleased` above the first `## ` heading, or at the end |
| `--check BASE` | read `git diff --name-status BASE...HEAD`, and fail when the branch changes a path below `lib/`, `hooks/`, `adapters/`, `bin/`, `scripts/`, `githooks/`, `agents/`, `skills/` or `rules/` and adds no fragment |

A fragment that is empty, holds only whitespace, holds a carriage return or is not UTF-8 stops the
dry run and `--apply`; the message names it, and no file changes.

**Exit status:** without `--check`, 0 when there is no fragment, or after `--apply`; 1 when the
dry run prints a block; 2 on a bad fragment or a failure. With `--check`, 0 when a fragment is
added or no code changes; 1 when code changes without a fragment, and the output names the first
such path; 2 when `BASE` is empty or git cannot resolve it.

**Where to run it:** in the harness checkout. CI runs `--check` on each pull request.

### `skill-triggers`

```text
harness skill-triggers [--skill NAME ...] [--apply --model ALIAS]
```

Tests whether each skill loads on the queries of `tests/skill-triggers/<skill>.toml`, and stays
unloaded on its near misses. The dry run prints the number of queries per skill and the number of
sessions that `--apply` starts.

| option | meaning |
|:--|:--|
| `--skill NAME` | only the query file of this skill; can repeat |
| `--apply` | run the sessions and write the report |
| `--model ALIAS` | the model of the sessions; `--apply` needs it |

`--apply` runs one `claude -p` session of 3 turns per query, **at your cost**, and writes the
report to `$RESEARCH_ROOT/.scratch/skill-triggers/<date>-<model>.md`.

**Exit status:** the dry run exits 1; `--apply` exits 0 when every skill passes, else 1.

**Where to run it:** in your own terminal.

## Environment

| variable | meaning |
|:--|:--|
| `RESEARCH_ROOT` | the research tree; `~/Research` if it is not set |
| `RESEARCH_HARNESS_PROFILE` | the profile, when `--profile` is not given |
| `RESEARCH_HARNESS_MODELS` | the model tables, when `--models` is not given |
| `RESEARCH_HARNESS_REPOSITORIES` | the repository table of `clone` and `repos` |
| `RESEARCH_HARNESS_JULIA` | the Julia environment of the scripts; `~/.local/share/research-harness/julia/` if it is not set |
| `RESEARCH_HARNESS_PYTHON` | the Python environment of the harness; `~/.local/share/research-harness/python/` if it is not set |
| `OPENCODE_CONFIG_DIR` | OpenCode's configuration directory; `~/.config/opencode` if it is not set |
| `PI_CODING_AGENT_DIR` | oh-my-pi's agent directory; `~/.omp/agent` if it is not set |
| `FMT_OUT` | the directory of the marker, the skip list and the log of `format` |
| `SANDBOX_RUNTIME` | set by the Claude Code sandbox; `doctor` reports a refused check as `SKIP` |

## Files

| file | meaning |
|:--|:--|
| `~/.config/research-harness/profile.toml` | the private profile; `examples/profile.toml` shows every key |
| `models.toml` beside the profile | the model tables; `examples/models.toml` |
| `providers.toml` beside the profile | the model providers of OpenCode and oh-my-pi; `examples/providers.toml` |
| `network.toml` beside the profile | the overlay of the network lists of the settings; `examples/network.toml` |
| `repositories.toml` beside the profile | the repository table; `examples/repositories.toml` |
| `~/.claude/.harness-install.json` | the stamp of the last `install --apply` |
| `~/.claude.json` | Claude Code's state, which `trust` writes |

## Exit status

| status | meaning |
|:--|:--|
| 0 | nothing to do, the change is made, or the read-only subcommand finished |
| 1 | the dry run has work to do; a check (`doctor`, `leaks`, `test`, `mutate`, `settings selftest`, `skill-triggers`) failed |
| 2 | a usage error, a refusal or a failure, with one line on standard error |

## The Julia environment

The Julia scripts load their packages from `Project.toml`, which `harness install --apply`
instantiates in `~/.local/share/research-harness/julia/`; no caller needs `--project`.

## The implementation

`harness` is the one command of the harness. The sections above describe its subcommands for a
user, and this section describes the code: which module implements which subcommand, and which
modules have only test cases.

The entry point is `bin/harness`. The code is the Python package `lib/harness/`, which uses the
standard library and one package of the environment, PyYAML, with which `harness wiki-lint` reads
a frontmatter. Each module that owns a subcommand has a function `register`, which adds its
subcommand to the argument parser. Most modules also have a function `selftest`, which runs
their own test cases. `harness test` runs every `selftest`, the groups of the hook probe
`hooks/probe.py` and the contract sweep, each as a part in a process of its own. Three
subcommands live in the adapters: `settings` and `trust` in `adapters/claude/adapter.py`, and
`permissions` in `adapters/opencode/adapter.py`.
[The adapters](components/adapters.md) describes them.

| subcommand | module |
|:--|:--|
| `setup` | `setup.py` |
| `install` | `install.py` |
| `render`, `get`, `leaks` | `profile.py` |
| `githooks`, `wiki-lint-hook`, `workflows`, `dependents` | `githooks.py` |
| `clone`, `repos` | `repos.py` |
| `update` | `update.py` |
| `dotfiles-kit` | `dotfiles_kit.py` |
| `ci-protection` | `protection.py` |
| `format` | `fmt.py` |
| `skill-triggers` | `skill_triggers.py` |
| `doctor` | `doctor.py` |
| `changelog` | `changelog.py` |
| `mutate` | `mutate.py` |
| `wiki-lint` | `wikilint.py` |
| `test` | `testrun.py` |

`frontmatter.py`, `docs.py`, `units.py`, `script_cases.py`, `network.py`, `providers.py`,
`sources.py`, `strict.py`, `sweep.py` and `environment.py` have no subcommand. Their cases run
only in `harness test`. `install_cases.py` holds helpers for the cases of other modules, and
`githooks_cases.py` the cases of `githooks.py`. The
sections start with the entry point and the parser, then the subcommands, then the shared modules,
then the modules of the tests.

### `harness`

The executable script `bin/harness`, the entry point of the harness. Put `bin/` on the `PATH`, then
run `harness --help` for the list of subcommands, or `harness <subcommand> --help` for one
subcommand.

The script first checks the version of Python. The harness needs Python 3.14 or later, the one
version that it is tested on, and the script itself needs 3.9 or later. An interpreter older than
3.9 prints the version that it found and the two versions, and the script exits with status 2.
The script uses no syntax newer than Python 3.0, so an old interpreter reads it without a syntax
error. From 3.9 to 3.13 the script goes on, and runs the command only on an interpreter of 3.14
or later: that of the environment, for which `uv sync` downloads Python 3.14 where none is
installed.

Then the script chooses the interpreter of the command. The Python environment of the harness is
at `$RESEARCH_HARNESS_PYTHON`, an absolute path, or else at
`~/.local/share/research-harness/python/`; it is working when its `bin/python` exists and starts.

- With a working environment, the command runs on its `bin/python`. On another interpreter, the
  script starts itself there with the same arguments, in the same process.
- In a session, where `SANDBOX_RUNTIME` or `CLAUDECODE` is set, with no working environment, the
  command runs on the interpreter that started it, after one line on stderr that names the
  environment and `harness install --apply`; on an interpreter older than 3.14 the script exits
  with status 2 instead, after one line that says to run `harness` once in a plain terminal. A
  session never starts uv.
- Otherwise the script finds `uv` on the `PATH` or in `~/.local/bin`. On Linux without one, it
  fetches the uv release that it pins into `~/.local/bin` and checks the sha256 of the archive;
  the download follows one redirect, to `release-assets.githubusercontent.com`, and no other.
  After a transient failure, an HTTP 408, 429 or 5xx or a network error, it tries again after 5,
  15 and 45 s, with one line on stderr each time; any other failure refuses at once. Then
  it runs `uv sync --locked --no-dev` into the environment, writes the environment's stamp, the
  sha256 of `uv.lock` and the group, and starts itself on the new interpreter. The environment is
  made on Python 3.14 (`UV_PYTHON` overrides it), and uv downloads a managed 3.14 where none is
  installed. A sync that fails, or that leaves no working environment, removes the environment
  when the sync made it; a uv that the fetch wrote and checked stays in `~/.local/bin`.

The chosen interpreter goes into `RESEARCH_HARNESS_INTERPRETER`, which each child process
inherits. A process that finds it set does no lookup: it runs when it runs on that interpreter,
and otherwise starts itself there once; a process that such a restart started and that still runs
elsewhere exits with status 2, so the restart never loops. Two paths name one interpreter when
their real paths and the directories of their environments, where a `pyvenv.cfg` lies, are equal.
Each refusal is one line on stderr and exit status 2: no uv on macOS or on a system other than
Linux, a relative `$RESEARCH_HARNESS_PYTHON`, a sync that fails or that leaves no working
environment, and on Linux a download that fails, a checksum that is not the pinned one, an
archive with no `uv`, an architecture other than `x86_64` and `aarch64`, and a redirect to another
host. On an interpreter older than 3.14 with `UV_PYTHON_DOWNLOADS=never` set, a sync that fails
adds a second line, which names `uv python install 3.14`.

Last, the script adds `lib/` to the module path and calls `main` of `cli.py`. It follows a symbolic
link to find `lib/`, so a link to the script in another directory also works. `install.py` loads
the script as a module, `boot`, for the environment's path, its stamp and the sync; only a run as
a script starts the command.

### `__init__.py`

The package file of `lib/harness/`. Its docstring is the contract of every subcommand, and
`harness --help` prints it: a subcommand that changes something does a dry run by default, exits
with status 1 when something would change and 0 when nothing would, and `--apply` makes the
change.
Exit status 2 is a usage error or a failure.

It defines what the other modules share:

- `REPO`, the path of the checkout;
- `HarnessError`, a failure that the subcommand reports in one line, after which `harness` exits
  with status 2;
- `changing(parser)`, which gives a subcommand its `--apply` flag;
- `outcome(args, changes)`, the exit status of a subcommand that changes something: 0 after
  `--apply` or with no change, otherwise 1.

A new subcommand that changes something uses `changing` and `outcome`, so that it keeps the
contract.

### `cli.py`

The argument parser of `harness`. `main` loads the adapters through `frontends.py` first.
When an adapter fails to load, `harness` exits with status 2 before any subcommand runs. Then
`main` adds the global options `--profile F` and `--models F`, each subcommand of the modules and
the adapters, and `harness test` from `testrun.py`. On a `HarnessError` of a subcommand,
`harness` prints one line, `harness <subcommand>: <message>`, and exits with status 2. A program
that a subcommand runs and that runs longer than its timeout is such an error, and the line names
the program's command and the timeout (`dispatch`).

### `testrun.py`

The subcommand `harness test`. `parts` gives the table of the parts, by name: each module and
adapter with a `selftest`, the groups of `doctor.py` (its `GROUPS`) and of `hooks/probe.py`
(`PROBE_GROUPS`, which a case checks against the probe's `GROUPS`), and the sweep. A part runs in
a child process: a probe group as `hooks/probe.py <group>`, every other part as
`harness test --part <name>`, an option that `--help` does not show. The child prints one line
per case and, last, `<n> cases, <w> wrong`.

`run_parts` runs the parts in a pool of `--jobs` threads, each of which waits on one child, and
`report` prints each part's output whole, in the order of the part names. A child that prints no
summary line, or whose exit status does not agree with it, counts as one more failed case, with
its stderr; a crash so shows its traceback. A child that runs longer than 300 s is stopped with
its process group and counts as one failed case. An error, an interrupt, a SIGTERM or a SIGHUP of
the run stops the children that still run.

`changed` reads `git diff --name-status BASE...HEAD`, both paths of a rename or a copy, and
`owners` maps each path to its parts by the table `OWNERS`. `take_slot` holds one of the two slot
files with an exclusive `flock`. [Development](development.md#tests) describes the selection,
the options and the slots for a user.

### `frontends.py`

The list of the frontends, `claude`, `opencode`, `omp` and `antigravity`, and the loader of their
adapters. `load` imports each `adapters/<frontend>/adapter.py` by its path, in that order, once.

Each adapter must define six members: `NAME`, `TEMPLATES`, `register`, `plan`, `selftest` and
`RESTART`. When an adapter fails to import, `harness` exits with status 2 and prints its path,
its line and the last line of the exception. When an adapter lacks a member, `harness` exits with
status 2 and prints its path. No adapter is skipped.

The module also defines `Plan`, the part of `harness install` that one frontend returns: the
files to install, the warnings, the installed files with no source, the refused files with their
messages, and the steps that run after the files. A later frontend reads the plan of an earlier
one; oh-my-pi reads the rules of the Claude Code plan.

The adapters are described in [the adapters](components/adapters.md).

### `install.py`

The subcommand `harness install [--apply] [--force]`. It reads the profile and the model tables,
and asks the adapter of each frontend that the profile's `[setup]` chooses for its plan, in the
order of `frontends.py` (`frontends.planned`); without `[setup]`, every frontend is chosen. A
plan writes nothing, so on a refusal the subcommand exits with status 2 before any file is
written. Where `claude` is not chosen and another frontend is, the Claude Code adapter's `copies`
stand in for its plan: the rules and the shared files that OpenCode, oh-my-pi and Antigravity
copy, made from the sources alone, with nothing read below `~/.claude/` and nothing installed
there. A layer of a frontend that is not chosen is neither planned nor removed.

Before it writes, the subcommand checks every target of the Julia environment, of each plan and
of the `srt` settings (`check_files`). The subcommand exits with status 2 at once if a target is
a symbolic link, a directory or a file that cannot be read, or if a directory above a target is a
symbolic link or a file.
Under `--apply`, it also exits with status 2 before anything is written if the install changes a
target that it cannot write, or whose mode it cannot change. A target with a mode, and a backup,
are written by `write_private` of `fsutil.py`, which renames a temporary name in the target's
directory, so that directory must be writable too. A dry run prints its whole plan and count line
first, then that refusal, and exits with status 2.

Then the subcommand installs the Julia environment of the scripts, where the profile's `[setup]`
chooses the `julia` component or the profile has no `[setup]`: it copies `Project.toml` to
`~/.local/share/research-harness/julia/`, or to `$RESEARCH_HARNESS_JULIA`, and instantiates it.
Then it plans the Python environment of the harness as one line, `python environment`
(`install_python_env`), on every machine: a change when its interpreter does not start or when
its stamp names another `uv.lock` or group. Under `--apply` it runs `uv sync --locked` into it,
with the `dev` group when `[setup]` of the profile sets `develop = true` and with `--no-dev`
otherwise; a sync that fails exits with status 2 and its last stderr line.
Then it installs the files of each plan, then the `srt` settings of each chosen frontend
(`sandbox.py`), prints the warnings, and runs the steps after the files.
The subcommand adds one warning of its own: `behind_origin` warns when the checkout is behind its
local `origin/main`. It fetches nothing.
It prints the count line, and after `--apply` the restart line of each frontend whose files
changed. A file that differs in its bytes or its mode is a change. `--force` replaces a file that
an adapter refuses to replace.

The module also holds the helpers of a layer that copies its sources one to one: `source_files`,
`check_targets` and `stamp_bytes`, the stamp that the `SessionStart` hook `hooks/install-drift.py`
computes again.

Its cases check that the install exits with status 2 and names the file on a broken profile or
`models.toml`, and that it exits with status 2 and writes nothing when an adapter fails to load.
They also run the restart cases of `install_cases.py`, and `behind_origin` on a scratch
repository whose `origin/main` is ahead of, level with and behind its `HEAD`. Under umask 0, they
check that no file that holds the bytes of a new file of mode 0600, or of its backup, has a group
or other bit at any `chmod`, any rename or the end.

### `install_cases.py`

The helpers for the test cases that run `harness install` end to end. It has no subcommand and
no `selftest` of its own.

`Scratch` creates a scratch `HOME` below a temporary directory: `~/.claude/skills/`, an OpenCode
directory, a Julia directory with a copy of `Project.toml`, a Python environment that the install
plans as synced (`python_env`), the tree instructions, and the dummy profile with `tree_agents`
set. `Scratch.run` runs `harness install` in a process of its own, with `HOME`,
`OPENCODE_CONFIG_DIR`, `RESEARCH_HARNESS_JULIA`, `RESEARCH_HARNESS_PYTHON` and
`PI_CODING_AGENT_DIR` in the scratch directory. A run that takes more than 60 s is a timeout.

`restart_cases` checks the restart lines of `harness install`. Each case changes the files of one
frontend, or of no frontend, and checks that only the restart lines of the frontends that changed
follow the count line. `install.py` calls it, and the adapters use `Scratch` in their own cases.

### `profile.py`

The private profile and the rendered output of a template. It gives three subcommands:

```
harness render TEMPLATE
harness get KEY
harness leaks [--commits F]
```

`render` prints a template with each placeholder `{key}` replaced by its profile value. A list
value repeats the line, or the JSON list element, once for each item. A table value renders only
on a line that holds the placeholder alone, as the members of a JSON object. On a placeholder that
the profile does not have, the subcommand exits with status 2. Every subcommand reads a value of
`autocommit_branch`. If the key is missing, the default is `main` on the template host, or on
every machine when `template_host` is not set, and `memory/<short host name>` on every other
machine. The template
host is the machine whose Claude Code memory is the template for the other machines; the profile
key `template_host` names it by its short host name.
`get` prints one value, one line for each item of a list; on a key that the profile does not
have, it exits with status 2. `render` of the settings template also adds its network rules
(`network.py`). Each subcommand loads the profile into a frozen dataclass, `Profile`, and exits
with status 2 on an unknown key, a missing required key, a value of the wrong type or a retired
key, with one line that names the file and the key.

`leaks` searches every tracked file and its path for each of the private strings (the profile's
`leak` list), and for the name of each directory below a `repository_roots` entry and each `org`
entry. The repository's own `owner/name` and the host of its GitHub Pages site,
`owner.github.io`, do not count as a hit. It also renders each template with
`examples/profile.toml` and searches the result. With `--commits F` it also searches the paths,
the added lines and the message of each commit that `F` names. The pre-push hook calls it in
this way. The subcommand exits with status 1 on a hit.

The module also reads the model tables for the adapters, into frozen dataclasses. On a table that
names a model tier by an old name, a table that no frontend reads, a key that a table does not
name or a value of the wrong type, the subcommand exits with status 2.
[Adapting the profile](profile.md) describes the keys.

### `githooks.py`

Four subcommands that write shared files into the repositories of the research tree. The research
root is `$RESEARCH_ROOT`, or `~/Research` if it is not set.

```
harness githooks [--apply]
harness wiki-lint-hook [--apply]
harness workflows [--apply]
harness dependents [--apply]
```

`githooks` copies `githooks/pre-commit`, `githooks/pre-commit.jl`, `githooks/pre-push`,
`githooks/pre-push.jl` and `scripts/test-layout.jl` into `.githooks/` of each git repository
directly below `Packages/` and `Experiments/`, and sets `core.hooksPath`. `wiki-lint-hook` copies
`githooks/pre-commit-wiki` as the pre-commit hook of the prose repositories that
`WIKI_REPOSITORIES` names. `workflows` copies the canonical files of `githooks/workflows/` and
deletes the retired `CompatHelper.yml`. `Dependents.yml` and `dependents.jl` go only into the
bases of the profile key `dependents_bases` (`bases`), and out of every other repository.
`dependents` writes `.github/dependents.toml` into each base, from the census of its direct
dependents (`census`).

A session cannot write `.git/config`. So a run that cannot set `core.hooksPath` prints the command
for each repository, and exits with status 2. The module also gives `research_root`,
`repositories` and `git` to other modules. Its `selftest` runs the cases of `githooks_cases.py`.
The sweep runs the dry runs and the `--apply` of its subcommands.
[Git hooks and workflows](components/githooks.md) describes the copied files.

### `githooks_cases.py`

The test cases of the dependents workflow and of `harness workflows`, which the `selftest` of
`githooks.py` runs. It has no subcommand and no `selftest` of its own. The cases of the two
subcommands and of `verify-workflows.jl` build fixture research roots below a temporary
directory. Each root has git repositories under `Packages/` and `Experiments/`, and the case
writes its own profile.

The cases run these commands:

- `harness dependents`: dependents through `[deps]`, beside packages with the base only in
  `[weakdeps]` or `test/Project.toml`, and beside an experiment. The case compares the written file
  byte for byte. Other cases give the refusals of the subcommand.
- `harness workflows`, with and without `dependents_bases`.
- `github_name` on the forms of an `origin` URL.
- The settings of `Dependents.yml`, read with the YAML reader of `wikilint.py`, and `actionlint` on
  it where `actionlint` is on the `PATH`.
- `dependents.jl`, where `julia` is on the `PATH`: `excluded` on fixture `Project.toml` pairs,
  `row` on the four rows, `list`, and their refusals.
- The format of `dependents.jl`: JuliaFormatter's SciML style, which the pre-commit hook of a base
  checks on the installed copy.
- `verify-workflows.jl`, where `julia` is on the `PATH`: a clean fixture, each of its four
  dependents findings, and a profile without `docs_exceptions` and `docs_additions`.

Without `julia`, a group that needs it prints one `skip` line and does not run.
The format case and `verify-workflows.jl` also need the Julia environment of the harness.

### `repos.py`

The subcommands `harness clone [SELECTION ...] [--apply]` and
`harness repos status|pull|push|sync [SELECTION ...]`. They read the repository table,
`repositories.toml` beside the profile or `$RESEARCH_HARNESS_REPOSITORIES`. A top-level key
names a fixed repository (`knowledge`, `environment`, `tasks`, `library`), and a
table names a group (`packages`, `experiments`, `papers`, `books`, `talks`, `projects`); each
directory is the key in title case below the research root. `load_table` refuses an unknown key
and a directory name that has a `/` or starts with `.`. Without a table, `repos` takes each git
repository that it finds, and `clone` stops.

`clone` refuses the whole run when a directory is in the way, before the first clone. `status`,
`pull`, `push` and `sync` fetch in parallel, eight at a time, and `status` asks `gh` or `glab`
for the open pull requests, also in parallel. `pull` merges `--ff-only`, and skips a branch whose
incoming commits change a file with local changes unless its content equals the upstream's.
`push` pushes one repository at a time and skips a branch that is also behind, and a branch that
is not the default branch unless `--include-topic-branches`. The dry run names the `.jl` files of each push. `--no-verify` (or
`--skip-hooks`) skips the pre-push suite; use it only for a push with no Julia source and no
`[compat]` change. After a push, the subcommand compares the local commit with the remote branch,
as `git ls-remote` reports it.

Run `push` and `sync` in your own terminal. The pre-push hook of each repository can run a full
test suite, so the subcommand can take hours, and a tool call of a session stops after ten
minutes. The `selftest` runs each subcommand on scratch remotes below a temporary directory, and
the query for pull requests on a stub of `gh` and `glab`; the sweep runs the dry runs.

### `update.py`

The subcommand `harness update [--apply]`. It works on the checkout that runs it, when its branch
is `main` with the upstream `origin/main`. It fetches, prints the new commits and their files,
and exits 1 when there is one. `--apply` needs a terminal: it shows the whole diff, asks `y/N`,
merges `--ff-only` and runs `harness install --apply` in a process of its own, from the merged
checkout. It stops at a detached HEAD, a pinned checkout, at changes to tracked files, and at
commits that `origin/main` lacks. The `selftest` runs it on a scratch remote and its clone.

### `setup.py`

The subcommand `harness setup [--yes] [--dry-run]`. It asks for the choices of `[setup]` in a
terminal, or reads them with `--yes`, and makes one plan (`plan`) for the machine (`Machine`):
first the clone of the profile's `claude_remote` into `~/.claude` with the jobs (`cloned`), then
the directories that `install` needs, the Homebrew lines on macOS, or the apt line and the pinned
releases of `setup/tools.toml` (`load_pins`) on Ubuntu, the vendor installers,
`harness install --apply`, `core.hooksPath`, `harness trust --apply`, the jobs (on macOS with
the Seatbelt profiles of [`jobsandbox.py`](#jobsandbox-py), on Linux after the `bwrap` check with
`jobbox` and the arguments of `bwrap`), the Kaimon token
and `harness doctor`, and one `export PATH=…` line by hand for the directories that the starting
`PATH` lacks (`missing_path`); `install`, `trust`, `render` and `doctor` each run in a child
process of `bin/harness`. `TOOLS` names each tool, the component or frontend that needs it, and
how each system installs it; a tool that is installed at its minimum is skipped, and one below it
is read again after its upgrade (`rechecked`). The run stops at the first failed step with status
2, and otherwise exits with the status of `harness doctor`, 0 or 1.

Its cases run every apply path on a scratch `HOME` with fake programs first on the `PATH`, `brew`,
`apt-cache`, `apt-get`, `sudo`, `curl`, `launchctl`, `systemctl` and `harness` among them, each of
which logs its call, and serve a pinned release from a local file server; a case reaches no
network and runs `git` only in scratch directories, where it clones `~/.claude` from a local bare
repository. They also hold the minimums of
`setup/tools.toml` equal to the `≥` cells of [dependencies.md](dependencies.md).

### `jobsandbox.py`

The Seatbelt profiles of the launch agents of Kaimon and `julia-update` on macOS, and the
arguments of `bwrap` for their `systemd --user` units on Linux. The module has no subcommand of
its own: `harness render sandbox/<job>.sb` prints the profile of `kaimon` or `julia-update`, and
`harness render sandbox/<job>.bwrap` prints `bwrap_args` of the job, one argument per line.
`load` reads the rule list `sandbox/daemon.toml` into a frozen dataclass and
refuses a missing job or key, an unknown key, a path that is neither one of the tokens
`$DARWIN_USER_TEMP_DIR`, `$DARWIN_USER_CACHE_DIR` and `$HARNESS` alone nor `~`, nothing or a
token followed by `/`, a path with an empty, `.` or `..` segment, the root `/` anywhere but in
`read_files`, a system path in its link form such as `/etc/hosts`, an operation that is not
lower-case words joined by `-`, a file that is not UTF-8, a `pty` that is not `true` or `false`,
and another value that is not a list of strings. `profile` renders one job's SBPL text: deny every
file read and write, allow the read and write lists, with the root directory `/` itself as a read
file of both jobs because dyld reads it when a process starts, then, for a job with `pty = true`,
allow pseudo-terminals, then deny the write denies and the repository parts `.git/hooks`,
`.git/config` and `.githooks` below `~/Research`, then allow the single files of
`allow_write_files` inside a write deny, then deny the operations `lsopen`, `appleevent-send`,
`file-mount` and `file-unmount`, and two Mach services of Launch Services; the deny of
`appleevent-send` and the deny of the two services each stop an Apple Event to another app.
Kaimon's only such file
is juliaup's lock file `~/.julia/juliaup/.juliaup-lock`: the juliaup launcher, which starts the
server and every Julia of its sessions, opens it for writing at every start and exits when that
fails, while `juliaup.json` and the installed Julia versions in the same directory stay
unwritable. The required key `pty` of each job is `true` for Kaimon, which starts every Julia
session on a pseudo-terminal with `forkpty`, and `false` for `julia-update`. With `true`, the
profile holds `(allow pseudo-tty)` and one rule that allows reads, writes and ioctls of
`/dev/ptmx` and of every path that the regex `^/dev/ttys[0-9]+$` matches, after the write allows
and before every write deny; both paths are constants of the module, and the rule list names no
device. Seatbelt cannot tell a pseudo-terminal of the job from a terminal of another program of
the same user, so [the security model](safeguards/security-model.md) states what this leaves open.
The required key `network` of each job is `"loopback"` for Kaimon and `"open"` for `julia-update`,
and `unix_sockets` holds the paths below which a loopback job connects to a Unix socket:
`~/.cache/kaimon` for Kaimon; `load` refuses a socket path of an open job, and a `network` that
is another value. A loopback job's profile ends, after the Mach-service deny, with
`(deny network-outbound)`, an allow of a connect to the loopback addresses, and an allow of a
connect to a Unix socket below each path of `unix_sockets`; an open job's profile holds no rule
of the network. The render takes `home` and `harness` from the profile and the two per-user
directories from `getconf`; a `getconf` that fails exits 2. `harness setup` writes each render into
`~/.config/research-harness/sandbox/` before it renders and loads the job's plist, and both plists
start their program with `/usr/bin/sandbox-exec -f` and that file. Before Kaimon's profile it
installs `sandbox/shims/ps` into the directory `SHIMS`, `~/.config/research-harness/sandbox/shims`,
which Kaimon's profile reads and does not write and Kaimon's plist puts first on the `PATH`: the
exec of the setuid `/bin/ps` fails under a Seatbelt profile, and Kaimon reads a failed
`ps -o state= -p PID` as a dead session. The shim prints `S` for that form where `kill -0 PID`
succeeds and exits 1 otherwise, exits 1 with no output for `-o rss=,%cpu= -p PID`, and exits 2
with one line on stderr for any other form or a PID that is not digits.

On Linux the same rule list holds two top-level keys, `linux_read`, the system paths that both
jobs read, and `linux_links`, the root entries such as `/bin` and `/lib` that are a link into
`/usr` on one Linux and a directory on another, and each job a key `linux_write`, the `~/`
directories that it writes on Linux only; `profile` leaves `linux_write` out, so the Seatbelt
profiles do not change. `load` refuses a Linux path that is not `/` and segments, none of them
empty, `.` or `..`, a `linux_links` entry below the root's first level, and a `linux_write` path
that is not below `~/`. `bwrap_args` gives the arguments of one job: `--unshare-all --share-net
--die-with-parent`, a new `/proc`, the host's `/dev`, `/sys` read-only and a new `/tmp`; each path
of `linux_read` read-only where it exists; each entry of `linux_links` as the host has it
(`linux_root`), a link or a read-only directory; an empty home; then the job's `~/` and `$HARNESS`
paths, the reads, the writes and `linux_write` with the pins (`pins`) among them, the write denies
read-only and the files written back. A pin is a path from a write path of the job down to a bind
source of the other job, its pins included, that is no effective mount point of the job yet. The
job binds it onto itself with `--bind`, before any of its write binds below it, so that it cannot
rename or remove it while it runs; a pin below the job's own write deny raises `HarnessError`.
The pins of the two jobs are computed against each other until no new pin appears. An absolute
path, the `$DARWIN` tokens, `~/Library`, `pty`, `network` and `unix_sockets` are macOS's and
give no argument, so both jobs keep the network on Linux, a write deny that no read or write
path of the job holds is left out, and an argument with a newline raises
`HarnessError`. `harness setup` and the services script of the dotfiles kit check `bwrap` first,
install `sandbox/jobbox` and `scripts/julia-update-server` into `~/.local/bin`, write each render
into `~/.config/research-harness/sandbox/<job>.bwrap` and create each write deny, `linux_write`
directory and pin that is missing (`linux_dirs`, `linux_files`), before the units.
`jobbox <job> <program> [args…]`, a POSIX `sh` script, reads that file one argument per line,
adds `--chdir` and the working directory and, for a job that binds `~/Research`, the read-only
binds of `.git/hooks`, `.git/config` and `.githooks` of each repository at most four levels below
`~/Research`, and runs `bwrap`; both units start their program through it. It exits 2 before
`bwrap` when the source of a bind below an entry of the home is a symbolic link or lies below one
under that entry, because `bwrap` follows the link; the entry itself, such as `~/.julia`, may be a
link.

Its cases load the shipped list and a broken copy of it for each refusal, render both jobs with a
home path that holds a dot and one that holds a quote, run `harness render` through `bin/harness`
with a `getconf` stub, run the shim on each form, start `/bin/sh -c true` under each job's
profile with `/usr/bin/sandbox-exec` and expect exit 0, under Kaimon's profile Python's
`pty.openpty()` and a `pty.fork()` of `/bin/sh -c true` with the resolved path of the Python that
runs the cases, the juliaup launcher with `julia --startup-file=no -e 'exit(0)'` when
`~/.juliaup/bin/julia` exists, and `ps -o state= -p $$` with the plist's `PATH`, which must print
`S` from the repository's shim and from the installed one where it exists, or print a skip line
where that cannot run, as inside another Seatbelt sandbox, and run
every probe of `sandbox/probe-daemon.jl`, the probes that a session runs through Kaimon's `ex`
after the server restarts under its profile, against a scratch home, when `julia` is on the `PATH`.
Where `sandbox-exec` applies a profile, under Kaimon's profile a connect to a TCP listener of the
case on `127.0.0.1` succeeds and one to `192.0.2.1` port 9 fails with `EPERM`; under Kaimon's
rules with a scratch socket path below `$DARWIN_USER_TEMP_DIR`, a connect to a Unix socket below
it succeeds and one beside it fails with `EPERM`; under the profile of `julia-update` the connect
to `192.0.2.1` gives no `EPERM`. No case connects to another address or resolves a host name,
and the network probes of the probe file run against a listener and two resolver stubs of the
case on loopback.
The probe file's constant `OPEN_GAPS` names the negative probes that the profile does not stop,
which report `:allowed` under it: none, and the cases check that value, that the file's header
comment expects no exception class of an open gap and `:ProcessFailedException` of `appleevent`,
an `IOError` class of `connect_remote` and `:DNSError` of `resolve_name`, that the network probes
default to `127.0.0.1:2828`, `1.1.1.1:443` and `julialang.org`, and that the default command of
`appleevent` asks the Finder for `name of startup disk`, which only an Apple Event answers. On
Linux `run_all` runs the probe set of Linux, with `systemd_run` and `session_bus` in place of
`lsopen`, `appleevent`, `metal` and `read_documents`, and with none of `connect_loopback`,
`pkg_offline`, `connect_remote` and `resolve_name`. The cases also check the order and the edges
of `bwrap_args` and `linux_root`, run `jobbox` with a stub `bwrap` that writes its arguments,
render `sandbox/<job>.bwrap` through `bin/harness`, and run `scripts/julia-update.jl` as on Linux
and `scripts/julia-update-server` with stubs of juliaup, `lsof`, `readlink`, `systemctl` and
`notify-send`: the update phase calls none of the last four, and the server phase reads its state
as data. No case starts the real `bwrap`.
[The daemon profiles](safeguards/sandbox.md#the-daemon-profiles) say what the profile and the
arguments allow and what they leave open.

### `dotfiles_kit.py`

The subcommand `harness dotfiles-kit [--apply] DEST`. It reads `examples/dotfiles/kit.toml`, which
names each file of the dotfiles kit and its class, and compares the chezmoi source `DEST` with the
kit. A code file that is missing, or that differs in its bytes or in its execute bit, is a change.
A seed file is a change only when it is missing. `--apply` copies each change, and replaces a
symbolic link at a code file's path rather than write through it. The subcommand refuses a `DEST`
that is not a directory, and the applied source `~/.local/share/chezmoi` or a directory below it;
it compares the resolved `DEST` and each of its parents with the applied source by device and
inode, so a case variant or a firmlink of the applied source is refused too. Before it compares the
first file, it checks that the directory of each file of `kit.toml` resolves inside the resolved
`DEST`, and exits 2 on one that resolves outside it, or that does not resolve because of a loop of
symbolic links. A code file that cannot be read exits 2, and `--apply` exits 2 on anything at a
code file's path that is not a regular file or a link, such as a directory or a FIFO.
[The `dotfiles` command](dotfiles-command.md) describes the kit and the scripts that it
installs.

The `selftest` runs it on a scratch kit with its own `kit.toml`: the dry run's list, `--apply` and
the dry run after it, a seed file that exists, each refusal of `DEST`, each directory that links
out of `DEST`, and each malformed `kit.toml`. Then it runs the command on an empty directory and
checks that the list holds every file of the harness's `kit.toml`. The sweep runs the dry run on
an empty fixture directory.

### `protection.py`

The subcommand `harness ci-protection [--remove-classic] [--apply]`. It protects the default
branch of each repository with a `CI.yml` with a GitHub ruleset named `main`: no deletion, no
force push, and the required status checks of the canonical `CI.yml`: `REQUIRED_CHECKS`, or with a
`test/ci-groups.toml` the list of `required_checks`, each `Julia` check once per test group. Last it
protects the Harness itself, the checkout that runs the command, with the same ruleset and its own
list, `HARNESS_CHECKS`: the jobs of `.github/workflows/test.yml` that report on every pull request
and are not warnings. `julia.yml` and `docs.yml` have path filters, so a check of theirs would
not report on every pull request, and they are not in the list. It also turns on auto-merge and
the deletion of merged branches. `--remove-classic` deletes the classic branch protection, but
only where the ruleset passes every check.

The subcommand first runs `githooks/verify-workflows.jl`, and refuses when the workflows are not
canonical, because the list of required checks depends on them. It calls `gh api` for each
repository, and skips a repository that is private or where the user is not an admin. Run it in
your own terminal: in a sandboxed session, only the first `gh` call of a process succeeds.

Its cases check `ruleset_problem` against the ruleset as GitHub returns it, against one break
of each check, and with the ruleset of each list judged against the other list. They list the
repositories with a scratch research root, with and without a group file, check that
`required_checks` refuses each malformed group file, and run the subcommand there with `gh`
replaced. A case reads `test.yml` with `workflow_checks` and fails when `HARNESS_CHECKS` differs
from it, so a renamed or an added job fails `harness test`. The sweep does not run this subcommand, because it
needs `gh` with a login.

### `fmt.py`

The subcommand `harness format [--apply]`. It runs `githooks/format-tree.jl`, which runs
JuliaFormatter over each tracked `.jl` file of the tree.

JuliaFormatter can stop the whole Julia process on some files. `format-tree.jl` records the file
that it is about to format in a marker. When the process stops, the subcommand moves that file
into a skip list and runs the script again, at most 40 times. At the end it prints the files that
JuliaFormatter cannot handle. The marker, the skip list and the log go to `$FMT_OUT`, or to
`$TMPDIR` if it is not set.

The dry run counts the files that the script would format, from its summary line. The module has
no `selftest`, and the sweep does not run it, because it runs Julia over the tree.

### `changelog.py`

The subcommand `harness changelog [--apply | --check BASE]`, the changelog fragments of the
harness checkout. Each branch writes its entry into a file of `changelog.d/`, so two pull requests
never change the same lines of `CHANGELOG.md`. `fragments` lists the fragments, every
`changelog.d/*.md` but `README.md`, and the dry run and `--apply` read that list. The dry run
prints the `## Unreleased` block that they make, newest first by the committer date of the commit
that added each; `--apply` writes the block at the top of the `## Unreleased` section of
`CHANGELOG.md` and deletes the fragments. `--check BASE` reads
`git diff --name-status -z BASE...HEAD`; `unrecorded`, a function of the changed paths and their
status alone, names the first path below a code directory when no added path is a fragment. CI
runs `--check` on each pull request.

Its cases check the join, the insertion into `CHANGELOG.md`, the order and the path
classification without git, and the dry run, `--apply` and `--check` on scratch repositories with
fixed commit dates. The sweep does not run it, because it reads the harness checkout and its
history, not the fixture.

### `mutate.py`

The subcommand `harness mutate SPEC`, the named mutants of the Python code. `load` reads the TOML
spec, one table per mutant with `file`, `anchor`, `old`, `new` and `tests`. `copy` copies the
tracked files of the checkout and its untracked files that git does not ignore into a temporary
directory and makes it a git repository, because the parts `docs` and `sweep` read
`git ls-files`. `mutated` replaces the one `old` after the anchor's line. Before any mutant runs,
`run` refuses a spec that it cannot apply, a part that `harness test --list` of the copy does not
name, and a copy that fails the spec's parts unmutated. `each` then applies each mutant alone,
skips the test of a mutated file that `ast.parse` refuses, runs `harness test` of the copy with
the mutant's parts, reverts the file, and prints the line that `verdict` gives.

Its cases check the spec, the anchor, the verdicts and the copy, and run whole runs and each
refusal on a fixture git repository with a stub `bin/harness`; they never run the real suite. The
sweep does not run it, because it needs a spec and runs `harness test`.

### `wikilint.py`

The subcommand `harness wiki-lint [TREE ...] [--strict] [--quiet]`, the lint of the prose
repositories. `lint` reads the Markdown of each tree below the research root and runs the checks
of the module docstring; `report` prints the finding lines, the counts by check and the totals,
and gives the exit status. A tree that is no directory raises `HarnessError`.

`yaml_reader` imports PyYAML when the first frontmatter is read, so an environment synced without
it fails only this subcommand, with one line that names `harness install --apply`. Its loader,
`FrontmatterLoader`, is a `SafeLoader` that keeps a date as its text, reads a float of YAML 1.2
such as `1e3` as a float, refuses a duplicate key and records each plain key, mapping value and
item of a list in a mapping value that YAML 1.1 converts, such as `no` or `0755`. The vault checks
and the task board's check report the refusal as an ERROR on PyYAML's line, and each conversion as
a WARN; the lint reads the frontmatter of the other trees only for their `aliases`, and a block
that repeats a key keeps its last value for them. `shown` spells a value in a message as Julia's
`string` spells the value that YAML.jl reads, such as `["a", "b"]` or `Any["a", 1]` for a list.

Its cases run every check on a research root in a temporary directory, the exit statuses of
`--strict` and `--quiet`, the reader's decisions, and the hook `githooks/pre-commit-wiki`, which
they commit through in scratch repositories with stubs of `ruff` and `basedpyright`. The sweep
runs `harness wiki-lint Knowledge` on its fixture.

### `skill_triggers.py`

The subcommand `harness skill-triggers [--skill <name> …] [--apply --model <alias>]`, the test of
whether each skill loads on the right queries.

It reads `tests/skill-triggers/<skill>.toml` for each skill of `skills/`. The dry run prints the
number of queries per skill and the number of sessions that `--apply` starts. `--apply` runs each
query as one `claude -p` session of 3 turns on the model that `--model` names, without the tools
that write or run commands. A query loads a skill when the first `Skill` call of the first three
assistant messages names it. A failed query runs twice more, and the majority counts. A skill
passes when at least 8 of its 10 `load` queries load it and at most 1 of its 5 `near` queries does.
The report goes to `.scratch/skill-triggers/` below the research root. Every session costs tokens.

Its cases run the parser, the verdict, the majority and the pass rule, and run `--apply` on a fake
`claude`. [Typical use](daily-use.md) shows the commands.

### `doctor.py`

The subcommand `harness doctor [--full]`, the check that a machine's setup works. It is read-only,
so it takes no `--apply`. It prints one line for each check: `PASS`, `WARN`, `FAIL` or `SKIP`, the
name of the check and a detail, such as a version, a path or the reason. A `FAIL` line also names
the section of the setup pages that fixes it. The subcommand exits with status 1 when a check
fails, otherwise with status 0; a `WARN` or a `SKIP` does not count. On a usage error, it exits
with status 2.

It checks, in this order:

- the machine: the system and the architecture. On Linux also the two kernel settings for user
  namespaces, the sandbox check `bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid true`,
  and `socat`.
- the tools of [Dependencies](dependencies.md): each required tool is on the `PATH`, and each
  tool with a minimum on that page is at or above it; below it, or missing, is a `FAIL`. A
  `python3` below the minimum of Python is a `WARN` instead where the interpreter of the Python
  environment meets it, because only a hook run by hand then needs that version. A missing
  tool that serves one frontend, one job or a push to the harness (the frontends, RTK, jq,
  juliaup and gitleaks), or that only the sync of the Python environment needs (uv), is a
  `WARN` that says what stops without it. uv is looked for as the sync looks for it, on the `PATH`
  or in `~/.local/bin`. When the version flag
  of a tool exits with a status other than 0, the check is a `FAIL` for a required tool and a
  `WARN` for an optional one. In a session's sandbox, which can refuse the flag, the check is a
  `SKIP`. When the flag exits with status 0 but the subcommand cannot read a version from its
  output, the check is a `WARN` with the tool's own text. The minimums are in
  `MINIMUMS`, and a case compares each with the page. The eight Julia packages are read from the
  `Manifest.toml` of the Julia environment of the scripts; each is a `SKIP` where the profile's
  `[setup]` does not choose the `julia` component. The Python environment of the harness
  is a `FAIL` when its interpreter does not start or is below the minimum of Python, a `WARN`
  when its stamp names another `uv.lock` or another group than `develop` of the profile's
  `[setup]`, and otherwise a `PASS`. A lagging environment is also one change of the dry run of
  `harness install`, so the same run gives a `FAIL` on the install line, and `doctor` exits 1;
  `harness install --apply` fixes both.
- the profile: it loads, the `tree_agents` directory and the OpenCode configuration directory
  exist, and the line `autocommit_branch` prints the value. The OpenCode directory is a `SKIP`
  where `[setup]` does not choose `opencode`.
- the install: the dry run of `harness install` reports `0 change(s)`, otherwise a `FAIL` with
  the count. Each warning of the dry run is a `WARN` line, with each further line of the warning
  indented below it (`indented`). Each frontend that `[setup]` does not
  choose and whose layer is still on disk, one file or more that its plan installs, is a `WARN`
  line `<frontend> layer` that names `[setup]` and the frontend (`unchosen`). The check plans
  OpenCode, oh-my-pi and Antigravity alone, as the install does; the Claude Code layer's files are
  the Claude Code adapter's `copies`, its `settings.json` and its stamp, found without a read of
  `settings.json`. OpenCode without its directory has no layer on disk. A plan that refuses for
  another cause is a `WARN` that names the frontend and the refusal. The check removes nothing.
- the jobs: Kaimon, `~/.julia/bin/kaimon`; its server and the update job, with `systemctl --user`
  on Linux and `launchctl list` with the profile's `launchd_prefix` on macOS; lingering on Linux.
  When the autocommit job is enabled, `~/.claude` must be the top of its own git repository, with
  an `origin`. The Kaimon token file must exist, with mode 600, and not be empty. Without Kaimon,
  its jobs and the token are `SKIP`, and so is the token without OpenCode, oh-my-pi and
  Antigravity, which read it. Antigravity counts as installed when `~/.gemini` is a directory.
- with `--full`, `harness test` and `julia -e 'using Revise'`. Without `--full`, both are `SKIP`.

The subcommand writes no file, starts no service and runs no `--apply`. It prints no secret: it
reads only the existence, the mode and the size of the token file, and does not print the URL of
the `origin` of `~/.claude`. A session's sandbox refuses some of the commands, such as
`launchctl`, and denies the read of the token file. There, these checks are `SKIP` with the
reason, so run the subcommand in a plain terminal for its real verdict.

Its cases run each status of each check on a fixture: a scratch `HOME` and stub commands on the
`PATH` that print what each tool prints on Linux and on macOS. They also check the exit status,
the minimums against the page, that each section of `FIX` is a level-2 heading of its setup page,
that no token reaches the output, and one run of the subcommand on the fixture of the contract
sweep, which changes no file. `GROUPS` splits them into five groups, `minimum`, `linux`, `darwin`,
`exit` and `process`, and `harness test` runs each as the part `doctor:<group>`.

### `units.py`

The cases of the `systemd --user` units in `systemd/`. The module has no subcommand. It renders
each unit and its plist in `launchagents/` with `examples/profile.toml`. Then it checks that both
describe one job: the program and its arguments, after the `sandbox-exec -f <profile>` that the
plist starts with on macOS, the working directory, the environment and its `PATH`, after the
shim directory `~/.config/research-harness/sandbox/shims` that such a plist may put first on its
`PATH` and after the pair `JULIA_PKG_OFFLINE=true`, which such a plist alone may set,
the timer's triggers, the start at login, and `Restart=always` where the plist has
`KeepAlive`. A section, a key or a repeated key that the check does not read is a problem. A
continued line is a problem too. Every element of the `PATH` must be an absolute directory that
the settings template keeps out of a session's writes, or a system directory; the shim directory
too. An empty element,
which means the working directory, is a problem. The cases also apply a mutant to the rendered
templates and expect a problem: for example a removed restart, an extra trigger or a
session-writable directory on the `PATH`. Last, they check that `render` gives
`autocommit_branch` its default when the profile has no such key: `main`, and
`memory/<short host name>` on a host that is not the template host. One case checks that the
plist and the unit of `claude-autocommit` start the interpreter that `bin/harness` names by
default for the profile's home, with the installed copy of the script as its argument.
[Jobs and configuration](components/other.md) describes the units.

### `autocommit.py`

The cases of `launchagents/claude-autocommit`. The module has no subcommand. Each case builds a
fixture `.claude` repository in a scratch HOME, with a bare remote, and runs the script on it on
this interpreter, with HOME, TMPDIR, the git identity and `XDG_STATE_HOME` set in the child's
environment. The cases check the commit and its message, the staged file that the commit leaves
alone, the branch that receives the push, the lock's path on this system, a held, a stale and a
fresh lock, a SIGTERM during a run and during `git commit`, a `git commit` that outlasts the
timeout, the dry run, a path that is not UTF-8, the deferral of a memory that is still settling,
and the refusals: a rename, too many deletions, a repository with no tracked plan or memory, a
missing or plain directory, a setting that is not an integer, no git, and a git that fails. A git on the `PATH`
that fails one command, or reports a status, stands for the failures and the names that a fixture
cannot make.
[Jobs and configuration](components/other.md#claude-autocommit-and-claude-autocommit-plist) describes the
script.

### `script_cases.py`

The cases of scripts in `scripts/` that need no Julia. The module has no subcommand. It reads
the critic's `rsync` copy from `skills/build-part/evidence.md` and `copy_command` from
`scripts/run-tests.jl`, runs each on a fixture tree with a `.env`, a `.env.ts`, a `.git` and a
`.claude`, and checks that the copy holds none of them and holds each `env.ts`. A control copy
with no flag must hold the `.env.ts`. Each copy must carry `--inplace`: without it, rsync writes
the temporary copy of `env.ts` as `.env.ts.XXXXXX`, a name the sandbox denies. Then it runs
`scripts/spec-gate.py` on a fixture task file and checks the verdict of each part: a part whose
*Files* lie in two repositories is `SPANS`, unless its part tier is
`direct`. It runs `scripts/spec-validate.py` on a fixture spec in the spec-delta format, with a
control for each of a missing domain, a failing premise, a mutant with no row, a failing check on a
head and a check that writes into the head; and it checks that `spec-gate.py` and `spec-bundle.py`
take a part whose cell names `spec`.

### `network.py`

The network rules of the Claude Code settings. The module has no subcommand. It reads
`settings/network.toml` and the overlay `network.toml` beside the profile, and writes into the
rendered settings template the `WebFetch(domain:…)` rules of `permissions.allow` and
`permissions.deny` and the lists `allowedDomains`, `deniedDomains` and `deniedDomainReasons` of
`sandbox.network`. A `deny` entry removes each `allow`, `fetch` and `infrastructure` host that it
matches. `install`, `render` of the settings template and `settings` call it. It also reads the
overlay's `[frontend.<name>]` tables, the hosts that one frontend's `srt` file adds, and holds
their grammar (`frontend_entries`), which `sandbox.py` uses for the policy file too; `generate`
and `apply` do not read the tables. The module exits with status 2 in four cases: a file breaks
the schema, the harness list holds a frontend table, the template holds a host of its own, or an
`allowedDomains` entry covers a `fetch` host. Its cases check each rule, each of these exits,
and that an overlay, also one with frontend tables, changes no file of OpenCode or oh-my-pi. The
profile's loader refuses the retired profile key `extra_domain`.
[Adapting the profile](profile.md#the-network-overlay) describes the keys.

### `sandbox.py`

The `srt` settings of the CLI frontends. The module has no subcommand. It reads
`sandbox/policy.toml` (`load_policy`) and renders one frontend's `srt` settings from the `sandbox`
object of the rendered Claude Code settings and the policy (`srt_settings`). `install` writes one
file per chosen frontend below `~/.config/research-harness/sandbox/`, Claude Code's override there
when `claude` is chosen, and the launcher `sandbox/agentbox` at `~/.local/bin/agentbox`
(`plan_files`). Each frontend's `allowedDomains` adds its `network` of the policy and of the
overlay's frontend table to the template's. The module exits with status 2 on a policy file that
breaks its schema, and on a frontend's `network` entry that covers a `fetch` host. Its cases
check the shipped policy, each refusal, each rendering rule on a fixture and on the settings
template, the frontend hosts of `plan_files` with overlays (`plan_network_cases`), and the
launcher on scratch homes with a stub `srt` (`agentbox_cases`). Its
`install_file_cases`, which the cases of `install.py` run, check the install on scratch homes.
[The srt settings](components/sandbox.md) describes the files.

### `providers.py`

The model providers of OpenCode and oh-my-pi. The module has no subcommand. It reads
`providers.toml` beside the profile, which may be missing, and gives each frontend its entries:
the `provider` object of `opencode.jsonc` and the providers of oh-my-pi's `models.yml`. The
OpenCode and oh-my-pi adapters call it in `install`. The module exits with status 2 on a literal
key, an unknown key or a value of the wrong type. Its cases check the mapping of each key, the
merge of a frontend's own keys, and each of these exits. The profile's loader refuses the retired
profile keys `opencode_providers` and `omp_providers`.
[Adapting the profile](profile.md#the-providers) describes the keys.

### `sources.py`

The names of the neutral sources: the five directories `agents/`, `skills/`, `rules/`,
`instructions/` and `commands/`, which belong to no single frontend. Each adapter reads them from
here. The module has no subcommand and no cases.

`curated_skills` lists the curated skills below a directory: each subdirectory with a `SKILL.md`,
except a hidden one and the directories of `EXCLUDED_SKILLS`. `listing` gives the agents of
`agents/` and the `SKILL.md` of each curated skill of `skills/`. `code_list` writes names as
Markdown code in a sentence, for the text that the adapters generate.

### `frontmatter.py`

The strict parser of the frontmatter of an agent or a skill, the block between the first two `---`
lines. It has no subcommand. Its cases run in `harness test`.

The parser accepts eleven keys, each once. A value is plain or in double quotes, and `tools` and
`skills` take a block list. It refuses each other form, such as a flow list, a comment, an unknown
key or a control character, with the file and the line, and `harness` exits with status 2.

`parse_file` also checks the neutral vocabulary. `model` must be a model tier: `large`, `medium` or
`small`. Each `tools` item must be a neutral tool or `mcp/kaimon/<tool>`. The `description` of a
skill has at most 1,024 characters and no `<` or `>`.

Its cases check each refused and each accepted form, and parse every agent of `agents/` and every
curated skill of `skills/`.

### `jsonio.py`

The reader of JSON text. It has no subcommand. Its cases run in `harness test`.

`loads(text, *, where, top=dict)` returns the top-level object of `text`, and `load(path)` the one
of a UTF-8 file. With `top=list` or `top=str`, `loads` returns a top-level array or string, and
with `top=object` a value of any type. Python's `json` keeps the last value of a key that occurs
twice, and reads `NaN`, `Infinity`, `-Infinity` and a number that overflows, such as `1e400`.
These readers refuse each of them with a `HarnessError` that names `where`, or the path, and the
line. They also refuse a nesting deeper than 200, where the top-level value is depth 1, with its
line, and an empty text, a byte order mark and a top level of another type than `top` names. A
path that cannot be read, is not a regular file or holds bytes that are not UTF-8 is refused with
the path. No other exception leaves them. The module imports only the standard library and
`HarnessError`.

Its cases check a value, a file and CRLF line ends, each refusal and its line, a depth of 200, 201
and 100000, and each kind of top level under each `top`. `hooks/guard/jsonio.py` is a copy of the
module, byte for byte, and a case of `hooks/probe.py` holds the copy; ruff bans `json.load` and
`json.loads` outside the two copies and the tests of the dotfiles kit.

### `ownedjson.py`

The merge into a JSON file that another program owns. It has no subcommand. Its cases run in
`harness test`.

`merged(text, change, *, where)` reads `text` with the refusals of `jsonio.py`, passes the object
to `change`, and returns the text in which only the changed values are written again. The key
order, the indentation, the separators, a minified layout, CRLF line ends, the escapes, the final
newline or its absence and the text of each number that the change leaves stay as they are. A
float that the change writes and the text spells exactly keeps the text's spelling. A changed
string keeps its characters; a lone surrogate stays a `\u` escape. An added key goes at the end of
its object, in the file's indentation and separators, and a removed key goes with its separator. A
value written into an object or an array on one line stays on that line. An empty file is read as
`{}` and written as `{}` and a newline. A change that nests a value deeper than 200, or gives a
text that `jsonio.py` refuses, such as one with a key that is not a string, is refused.

`merge(path, change)` does the same to a file, and writes it through `write_private` of
`fsutil.py` with the file's own mode. A missing file is created with mode 0600. A symlink stays a
link, and its target is written. A file with a key twice, a byte order mark or a top level that is
not an object is refused and keeps its bytes, and so is a path that is not a regular file.

### `fsutil.py`

The writer of a private file. It has no subcommand. Its cases run in `harness test`.

`write_private(path, data, mode=0o600)` creates a temporary name beside `path` with `os.open`,
`O_CREAT | O_EXCL` and `mode`, sets `mode` on the empty file, writes `data` and moves the file onto
`path` with `os.replace`. So no file that holds `data` has more permission bits than `mode`, under
any umask, and an existing file ends with `mode`. A symlink at `path` is replaced, not written
through. Any failure removes the temporary name. An `OSError`, a NUL character in `path` and a
path that names no file raise a `HarnessError` that names `path`.

Its cases run the writes under umask 0, read the mode of each file that `os.open` creates and the
mode before each `chmod`, and check that no other file stays beside `path`.

### `sweep.py`

The contract sweep, the part `sweep` of `harness test`, which runs in every selection. It has no
subcommand.

The sweep creates a fixture `HOME` in a temporary directory: the dummy profile and model tables,
the files that the subcommands read, and a research root with one package and one prose
repository. Then:

- it runs the dry run of each subcommand and checks that it exits with status 0 or 1, prints no
  traceback and changes no file;
- it removes each precondition alone, such as the profile or `~/.claude.json`, and checks that each
  subcommand that needs it exits with status 2 and one line;
- it runs `--apply` of `githooks`, `wiki-lint-hook`, `workflows`, `dependents` and `trust`, and
  checks that the dry run after it exits with status 0.

It does not run `format`, `ci-protection`, `skill-triggers`, `doctor`, `test` or `mutate`.
[Development](development.md) describes the tests.

### `environment.py`

The cases of the Python environment of the harness. The module has no subcommand. Its cases run
`bin/harness` as a child process under a scratch `HOME`, with a fake `uv` that logs its arguments
and makes the environment with `python -m venv`: a session with no environment, the marker, the
first sync and a second run, the Python that uv is asked for, the restart with its arguments onto
a working environment, in a session too, each refusal of the start, a failed sync that removes
the environment that it made and keeps a directory that was there, and a restart that lands on
another interpreter, which exits with status 2 instead of a loop. In the process of the cases,
they check the marker that a start exports to its children. They also run the script, under a
scratch `HOME`, on an interpreter that reports 3.13, and check that the script uses only a closed
set of forms, each of which Python 3.0 reads.

The cases of the Linux download set the platform and the release URL through
`RESEARCH_HARNESS_TEST_PLATFORM` and `RESEARCH_HARNESS_TEST_UV_URL`, which only they set, and
serve fake archives from a local `http.server`: an unknown architecture, a download that fails, a
checksum that is not the pinned one and a redirect to another host. No fake archive has the pinned
sha256, so the download that succeeds, and the redirects, run in the process of the cases, with a
patched checksum, and so does a start whose fetched uv makes no environment: the start refuses,
and the uv stays in `~/.local/bin`. Last, the cases run `harness install` on `Scratch`: the plan
line, the sync with and without the `dev` group, an interpreter that does not start, a sync that
fails, no uv, and a `develop` that is not `true` or `false`.

### `strict.py`

The cases of the strict profile of the Python code. The module has no subcommand. Its first cases
parse each `.py` file below `hooks/`, each `adapters/*/guard*.py` and `githooks/pre-commit-wiki`
with `ast` and fail on an import outside the standard library, in this repository and in scratch trees: `hooks/probe.py`
may also import `harness`, the guard's tables of its frontends and the four hooks that read JSON
may import `guard`, and another file may not. The timeout and chmod cases read each file
that ruff reads with `ast`, in this repository and in scratch trees: each call of `subprocess.run`
names a `timeout=` or carries `# no timeout: <reason>` on the line where it starts, and no `chmod`
to a private mode follows a file write in one function outside `fsutil.py`, but one that carries
`# not private: <reason>`. A handler case runs `harness` with a subcommand whose program sleeps
past its timeout, and checks exit 2 and one line that names the program. The other cases run
`.githooks/pre-commit` through `git commit` in scratch repositories, with stubs of `ruff` and
`basedpyright` in a scratch Python environment and a second pair on the `PATH`: a clean commit, a
staged file that each check refuses, a staged file that the formatter would change, which stays
as it was in the work tree and the index, a violation that is not staged, and an environment
without one tool or both. [Development](development.md#the-strict-profile) describes the
profile.

### `docs.py`

The check of the component pages of the documentation site, which runs in `harness test`. It has
no subcommand.

The table `KINDS` maps each page of `docs/src/components/` to the tracked files that are its
components, and to the name of each. The check reads the level-2 headings of each page and the
names in backticks in them. It fails when a component has no heading on its page. It also fails
when a heading names something that is not a component of its page, so a removed component leaves no
old section.

It also checks `docs/src/dependencies.md`: its two tables, and one level-3 heading below them
for each tool of the tables, with no heading that names a tool outside them. So a new agent,
skill, hook, script or tool needs its section in the same change.
