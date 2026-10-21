# The `harness` command

## Synopsis

```text
harness [--profile F] [--models F] <subcommand> [options] [arguments]
harness --help
harness <subcommand> --help
```

## Description

`bin/harness` is the entry point of the harness. It needs Python 3.11 or later and nothing beyond
the standard library. Put `bin/` on the `PATH`, as the step *The clone*
of [setup-macos.md](setup-macos.md#the-clone) and [setup-linux.md](setup-linux.md#the-clone) shows.
An older Python prints the version that it found and the version that it needs, and exits 2.

Each subcommand of `harness`, such as `install` or `doctor`, keeps one contract:

- **A subcommand that changes something is dry by default.** It prints its plan, and exits 1
  when something would change, 0 when nothing would. `--apply` makes the change, and exits 0.
- **A read-only subcommand takes no mode flag.** It exits 0, or 1 where its section says so.
- **Exit 2 is a usage error or a failure**, with one line on standard error:
  `harness <subcommand>: <reason>`.

So a dry run in a script tells you whether there is work to do: exit 1 means "run it again with
`--apply`". The two checks differ: `harness test` exits 1 when a test case fails, and
`harness doctor` exits 1 when a check fails.

[development.md](development.md) describes the cases of `harness test`, and
[architecture.md](architecture.md) the Claude Code layer that `harness install` writes.

## Global options

These options come before the subcommand.

| option | meaning |
|:--|:--|
| `--profile F` | the private profile. If it is not given, the profile is `$RESEARCH_HARNESS_PROFILE`, or `~/.config/research-harness/profile.toml` if that is not set. `examples/profile.toml` shows every key |
| `--models F` | the model tables. They map each model tier to its Claude Code, OpenCode and oh-my-pi model, and an agent to its own model. If the option is not given, the model tables are `$RESEARCH_HARNESS_MODELS`, or `models.toml` beside the profile if that is not set. `examples/models.toml` shows the layout |
| `-h`, `--help` | print the list of subcommands. `harness <subcommand> --help` prints the options of one subcommand |

## Subcommands

| subcommand | does | changes something |
|:--|:--|:--|
| [`install`](#install) | installs the Julia environment of the scripts, the Claude Code layer with the sections `permissions`, `hooks`, `sandbox` and `modelSettings` of `settings.json`, the OpenCode configuration, and the oh-my-pi permission layer, instructions, rules, agents, models and MCP entry | yes |
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
| [`wiki-lint-hook`](#wiki-lint-hook) | installs the wiki-lint hook into the prose repositories | yes |
| [`workflows`](#workflows) | installs the canonical GitHub workflows into every package and experiment | yes |
| [`ci-protection`](#ci-protection) | protects every default branch on GitHub with a ruleset | yes |
| [`format`](#format) | runs JuliaFormatter over every tracked `.jl` file of the packages and experiments | yes |
| [`render`](#render) | prints a template rendered with the profile | no |
| [`get`](#get) | prints a profile value | no |
| [`leaks`](#leaks) | searches the repository for the private strings of the profile | no |
| [`settings`](#settings) | measures and checks the Claude Code settings: `surface`, `compare`, `twins`, `selftest` | no |
| [`permissions`](#permissions) | generates the OpenCode permission block and path-guard list from the settings template | yes |
| [`test`](#test) | runs the harness's own test cases | no |
| [`skill-triggers`](#skill-triggers) | tests whether each skill loads on its queries | runs paid sessions with `--apply` |

The sections below give each subcommand's synopsis, what it does, its options, its exit status,
the files that it reads and writes, where to run it, and examples. *Where to run it* says whether
an agent session can run the subcommand. A session runs in the Claude Code sandbox, which refuses
some writes and some network calls; a subcommand that needs them runs in your own terminal.

## Set up and keep a machine

### `install`

```text
harness install [--apply] [--force]
```

Installs the Julia environment of the scripts and the configuration of each frontend: Claude
Code, OpenCode and oh-my-pi. The installed configuration is not writable from a session, so the
sources live in the harness repository, and `install` copies them into place. It plans every
frontend first and writes nothing while it plans. So a refusal stops the install before the first
write. After `--apply`, it prints the restart line of each frontend whose files changed.

| option | meaning |
|:--|:--|
| `--apply` | install; without it, print the plan |
| `--force` | replace a file that the plan refuses to replace; the refusal names the file |

**Exit status:** 0 when nothing would change or `--apply` installed; 1 when the dry run has a
change; 2 when a plan refuses, or the profile or the model tables do not load.

**Reads:** the profile, the model tables, `providers.toml` and `network.toml` beside the profile,
the tree instructions (`tree_agents` of the profile), and the sources of the harness checkout.
**Writes:** below `~/.claude/`, the OpenCode configuration directory, the oh-my-pi directory, and
the Julia environment (see [The Julia environment](#the-julia-environment)). It writes the stamp
`~/.claude/.harness-install.json`, which the drift warning at session start reads.

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
setup page that fixes it. The checks are, in this order: the machine; the tools of
[dependencies.md](dependencies.md), each with its minimum version; the profile; the dry run of
`install` and its warnings; and the jobs (Kaimon, the update job, the autocommit job).

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

The fixed repositories are `knowledge`, `environment`, `tasks`, `bibliography` and `library`.
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
as it is. The dry run fetches too: a fetch changes no working tree.

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

Copies `githooks/pre-commit`, `githooks/pre-push` and `scripts/test-layout.jl` into `.githooks/`
of each git repository below `Packages/` and `Experiments/`, and sets `core.hooksPath` to
`.githooks`. The copies are tracked files of each repository: read the diff, then commit each file
by name. `core.hooksPath` is local configuration, so a new clone needs this subcommand again.

**Exit status:** 0 when every copy is current, or after `--apply`; 1 when the dry run has a
change; 2 when `core.hooksPath` cannot be set. The subcommand then prints the command for each
repository.

**Where to run it:** in your own terminal. A session cannot write `.git/config`.

### `wiki-lint-hook`

```text
harness wiki-lint-hook [--apply]
```

Copies `githooks/pre-commit-wiki` as `.githooks/pre-commit` into each prose repository of the
research tree (`Knowledge`, `Environment`, `Tasks`, `Bibliography`, `Library`), and sets
`core.hooksPath`. It skips a name that is not a git repository.

**Exit status and where to run it:** as `githooks`.

### `workflows`

```text
harness workflows [--apply]
```

Copies the canonical files of `githooks/workflows/` into each package and experiment that has a
`Project.toml`: `CI.yml`, `dependabot.yml` and `codecov.yml` into each, `TagBot.yml` into each
package, and `Documenter.yml` where a tracked `docs/make.jl` exists. A repository that the profile
keys `docs_exceptions` or `docs_additions` name keeps its own documentation workflow. It deletes
the retired `CompatHelper.yml`.

**Exit status:** 0 when every file is current, or after `--apply`; 1 when the dry run has a
change; 2 when a template is missing.

**Where to run it:** anywhere; it writes tracked files only. Commit each file by name.

### `ci-protection`

```text
harness ci-protection [--apply] [--remove-classic]
```

Protects the default branch of each repository that has a `CI.yml` with a GitHub ruleset named
`main`, which requires the status checks of the canonical `CI.yml`. It also turns on auto-merge
and the deletion of merged branches. It reads the current state first and writes only what
differs. It refuses to run unless `verify-workflows.jl` passes: a required check that never
reports leaves every pull request pending.

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

Prints the profile value of `KEY`, one line per item of a list. A path that starts with `~` is
printed with the home directory.

**Exit status:** 0; 2 when the profile has no `KEY`.

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
harness settings compare [--days N] OLD NEW
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
harness test
```

Runs the harness's own test cases: the cases of each module and adapter, the hook probe, and the
contract sweep. The sweep runs the dry run of each subcommand on a fixture home directory and
checks the contract above. It prints `<n> cases, <w> wrong`.
[development.md](development.md#tests) describes the cases.

**Exit status:** 0 when every case passes, 1 when a case fails.

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
| `OPENCODE_CONFIG_DIR` | OpenCode's configuration directory; `~/.config/opencode` if it is not set |
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
| 1 | the dry run has work to do; a check (`doctor`, `leaks`, `test`, `settings selftest`, `skill-triggers`) failed |
| 2 | a usage error, a refusal or a failure, with one line on standard error |

## The Julia environment

The Julia scripts load their packages from `Project.toml`, which `harness install --apply`
instantiates in `~/.local/share/research-harness/julia/`; no caller needs `--project`.
