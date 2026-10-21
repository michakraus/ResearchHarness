# The harness command

`harness` is the one command of the harness. [The `harness` command](../harness-command.md)
describes its subcommands and their contract for a user: a subcommand that changes something
prints its plan, and `--apply` makes the change. This page describes the code: which module
implements which subcommand, and which modules have only test cases.

The entry point is `bin/harness`. The code is the Python package `lib/harness/`, which uses the
standard library only. Each module that owns a subcommand has a function `register`, which adds
its subcommand to the argument parser. Most modules also have a function `selftest`, which runs
their own test cases. `harness test` runs every `selftest`, then the hook probe `hooks/probe.py`,
then the contract sweep. Three subcommands live in the adapters: `settings` and `trust` in
`adapters/claude/adapter.py`, and `permissions` in `adapters/opencode/adapter.py`.
[The adapters](adapters.md) describes them.

| subcommand | module |
|:--|:--|
| `install` | `install.py` |
| `render`, `get`, `leaks` | `profile.py` |
| `githooks`, `wiki-lint-hook`, `workflows` | `githooks.py` |
| `clone`, `repos` | `repos.py` |
| `update` | `update.py` |
| `dotfiles-kit` | `dotfiles_kit.py` |
| `ci-protection` | `protection.py` |
| `format` | `fmt.py` |
| `skill-triggers` | `skill_triggers.py` |
| `doctor` | `doctor.py` |
| `test` | `cli.py` |

`frontmatter.py`, `docs.py` and `sweep.py` have no subcommand. Their cases run only in
`harness test`. `install_cases.py` holds helpers for the cases of other modules. The sections
start with the entry point and the parser, then the subcommands, then the shared modules, then the
modules of the tests.

## `harness`

The executable script `bin/harness`, the entry point of the harness. Put `bin/` on the `PATH`, then
run `harness --help` for the list of subcommands, or `harness <subcommand> --help` for one
subcommand.

The script first checks the version of Python. It needs Python 3.11 or later, because the profile
and the model tables are TOML and `tomllib` came into the standard library with 3.11. An older
interpreter prints the version that it found and the version that it needs, and the script exits
with status 2. The check uses no new syntax, so an old interpreter reads it without a syntax
error.

Then the script adds `lib/` to the module path and calls `main` of `cli.py`. It follows a symbolic
link to find `lib/`, so a link to the script in another directory also works.

## `__init__.py`

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

## `cli.py`

The argument parser of `harness`, and the subcommand `harness test`. `main` loads the three
adapters through `frontends.py` first. When an adapter fails to load, `harness` exits with status
2 before any subcommand runs. Then `main` adds the global options `--profile F` and `--models F`,
and each subcommand of the modules and the adapters. On a `HarnessError` of a subcommand,
`harness` prints one line, `harness <subcommand>: <message>`, and exits with status 2.

`harness test` runs the cases in this order:

1. the `selftest` of `install.py`, then of each adapter, then of `frontmatter.py`,
   `protection.py`, `profile.py`, `skill_triggers.py`, `docs.py`, `units.py`, `script_cases.py`,
   `network.py`, `providers.py` and `doctor.py`;
2. the hook probe `hooks/probe.py`, in a process of its own;
3. the contract sweep of `sweep.py`.

It prints one summary line, `<n> cases, <w> wrong`, and exits with status 1 when a case fails. A
probe that prints no summary line, or whose exit status does not agree with it, counts as one more
failed case.

## `frontends.py`

The list of the frontends, `claude`, `opencode` and `omp`, and the loader of their adapters.
`load` imports each `adapters/<frontend>/adapter.py` by its path, in that order, once.

Each adapter must define six members: `NAME`, `TEMPLATES`, `register`, `plan`, `selftest` and
`RESTART`. When an adapter fails to import, `harness` exits with status 2 and prints its path,
its line and the last line of the exception. When an adapter lacks a member, `harness` exits with
status 2 and prints its path. No adapter is skipped.

The module also defines `Plan`, the part of `harness install` that one frontend returns: the
files to install, the warnings, the installed files with no source, the refused files with their
messages, and the steps that run after the files. A later frontend reads the plan of an earlier
one; oh-my-pi reads the rules of the Claude Code plan.

The adapters are described in [the adapters](adapters.md).

## `install.py`

The subcommand `harness install [--apply] [--force]`. It reads the profile and the model tables,
and asks each adapter for its plan, in the order of `frontends.py`. A plan writes nothing, so on a
refusal the subcommand exits with status 2 before any file is written.

Before it writes, the subcommand checks every target of the Julia environment and of each plan
(`check_files`). The subcommand exits with status 2 at once if a target is a symbolic link, a
directory or a file that cannot be read, or if a directory above a target is a symbolic link or a
file.
Under `--apply`, it also exits with status 2 before anything is written if the install changes a
target that it cannot write, or whose mode it cannot change. A dry run prints its whole plan and
count line first, then that refusal, and exits with status 2.

Then the subcommand installs the Julia environment of the scripts: it copies `Project.toml` to
`~/.local/share/research-harness/julia/`, or to `$RESEARCH_HARNESS_JULIA`, and instantiates it.
Then it installs the files of each plan, prints the warnings, and runs the steps after the files.
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
repository whose `origin/main` is ahead of, level with and behind its `HEAD`.

## `install_cases.py`

The helpers for the test cases that run `harness install` end to end. It has no subcommand and
no `selftest` of its own.

`Scratch` creates a scratch `HOME` below a temporary directory: `~/.claude/skills/`, an OpenCode
directory, a Julia directory with a copy of `Project.toml`, the tree instructions, and the dummy
profile with `tree_agents` set. `Scratch.run` runs `harness install` in a process of its own, with
`HOME`, `OPENCODE_CONFIG_DIR`, `RESEARCH_HARNESS_JULIA` and `PI_CODING_AGENT_DIR` in the scratch
directory. A run that takes more than 60 s is a timeout.

`restart_cases` checks the restart lines of `harness install`. Each case changes the files of one
frontend, or of no frontend, and checks that only the restart lines of the frontends that changed
follow the count line. `install.py` calls it, and the adapters use `Scratch` in their own cases.

## `profile.py`

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
(`network.py`).

`leaks` searches every tracked file and its path for each of the private strings (the profile's
`leak` list), and for the name of each directory below a `repository_roots` entry and each `org`
entry. The repository's own `owner/name` and the host of its GitHub Pages site,
`owner.github.io`, do not count as a hit. It also renders each template with
`examples/profile.toml` and searches the result. With `--commits F` it also searches the paths,
the added lines and the message of each commit that `F` names. The pre-push hook calls it in
this way. The subcommand exits with status 1 on a hit.

The module also reads the model tables for the adapters. On a table that names a model tier by an
old name, the subcommand exits with status 2. [Adapting the profile](../profile.md) describes the
keys.

## `githooks.py`

Three subcommands that copy shared files into the repositories of the research tree. The research
root is `$RESEARCH_ROOT`, or `~/Research` if it is not set.

```
harness githooks [--apply]
harness wiki-lint-hook [--apply]
harness workflows [--apply]
```

`githooks` copies `githooks/pre-commit`, `githooks/pre-push` and `scripts/test-layout.jl` into
`.githooks/` of each git repository directly below `Packages/` and `Experiments/`, and sets
`core.hooksPath`. `wiki-lint-hook` copies `githooks/pre-commit-wiki` as the pre-commit hook of the
prose repositories that `WIKI_REPOSITORIES` names. `workflows` copies the canonical files of
`githooks/workflows/` and deletes the retired `CompatHelper.yml`.

A session cannot write `.git/config`. So a run that cannot set `core.hooksPath` prints the command
for each repository, and exits with status 2. The module also gives `research_root`,
`repositories` and `git` to other modules. It has no `selftest`; the sweep runs its dry runs and
its `--apply`. [Git hooks and workflows](githooks.md) describes the copied files.

## `repos.py`

The subcommands `harness clone [SELECTION ...] [--apply]` and
`harness repos status|pull|push|sync [SELECTION ...]`. They read the repository table,
`repositories.toml` beside the profile or `$RESEARCH_HARNESS_REPOSITORIES`. A top-level key
names a fixed repository (`knowledge`, `environment`, `tasks`, `bibliography`, `library`), and a
table names a group (`packages`, `experiments`, `papers`, `books`, `talks`, `projects`); each
directory is the key in title case below the research root. `load_table` refuses an unknown key
and a directory name that has a `/` or starts with `.`. Without a table, `repos` takes each git
repository that it finds, and `clone` stops.

`clone` refuses the whole run when a directory is in the way, before the first clone. `status`,
`pull`, `push` and `sync` fetch in parallel, eight at a time, and `status` asks `gh` or `glab`
for the open pull requests, also in parallel. `pull` merges `--ff-only`, and skips a branch whose
incoming commits change a file with local changes. `push` pushes one repository at a time and
skips a branch that is also behind, and a branch that is not the default branch unless
`--include-topic-branches`. The dry run names the `.jl` files of each push. `--no-verify` (or
`--skip-hooks`) skips the pre-push suite; use it only for a push with no Julia source and no
`[compat]` change. After a push, the subcommand compares the local commit with the remote branch,
as `git ls-remote` reports it.

Run `push` and `sync` in your own terminal. The pre-push hook of each repository can run a full
test suite, so the subcommand can take hours, and a tool call of a session stops after ten
minutes. The `selftest` runs each subcommand on scratch remotes below a temporary directory, and
the query for pull requests on a stub of `gh` and `glab`; the sweep runs the dry runs.

## `update.py`

The subcommand `harness update [--apply]`. It works on the checkout that runs it, when its branch
is `main` with the upstream `origin/main`. It fetches, prints the new commits and their files,
and exits 1 when there is one. `--apply` needs a terminal: it shows the whole diff, asks `y/N`,
merges `--ff-only` and runs `harness install --apply` in a process of its own, from the merged
checkout. It stops at a detached HEAD, a pinned checkout, at changes to tracked files, and at
commits that `origin/main` lacks. The `selftest` runs it on a scratch remote and its clone.

## `dotfiles_kit.py`

The subcommand `harness dotfiles-kit [--apply] DEST`. It reads `examples/dotfiles/kit.toml`, which
names each file of the dotfiles kit and its class, and compares the chezmoi source `DEST` with the
kit. A code file that is missing, or that differs in its bytes or in its execute bit, is a change.
A seed file is a change only when it is missing. `--apply` copies each change, and replaces a
symbolic link at a code file's path rather than write through it. The subcommand refuses a `DEST`
that is not a directory, and the applied source `~/.local/share/chezmoi` or a directory below it;
it compares the resolved paths. Before it compares the first file, it checks that the directory of
each file of `kit.toml` resolves inside the resolved `DEST`, and exits 2 on one that resolves
outside it, or that does not resolve because of a loop of symbolic links.

The `selftest` runs it on a scratch kit with its own `kit.toml`: the dry run's list, `--apply` and
the dry run after it, a seed file that exists, each refusal of `DEST`, each directory that links
out of `DEST`, and each malformed `kit.toml`. Then it runs the command on an empty directory and
checks that the list holds every file of the harness's `kit.toml`. The sweep runs the dry run on an empty fixture directory.

## `protection.py`

The subcommand `harness ci-protection [--remove-classic] [--apply]`. It protects the default
branch of each repository with a GitHub ruleset named `main`: no deletion, no force push, and the
required status checks of the canonical `CI.yml`. It also turns on auto-merge and the deletion of
merged branches. `--remove-classic` deletes the classic branch protection, but only where the
ruleset passes every check.

The subcommand first runs `githooks/verify-workflows.jl`, and refuses when the workflows are not
canonical, because the list of required checks depends on them. It calls `gh api` for each
repository, and skips a repository that is private or where the user is not an admin. Run it in
your own terminal: in a sandboxed session, only the first `gh` call of a process succeeds.

Its cases check `ruleset_problem` against the ruleset as GitHub returns it, and against one break
of each check. The sweep does not run this subcommand, because it needs `gh` with a login.

## `fmt.py`

The subcommand `harness format [--apply]`. It runs `githooks/format-tree.jl`, which runs
JuliaFormatter over each tracked `.jl` file of the tree.

JuliaFormatter can stop the whole Julia process on some files. `format-tree.jl` records the file
that it is about to format in a marker. When the process stops, the subcommand moves that file
into a skip list and runs the script again, at most 40 times. At the end it prints the files that
JuliaFormatter cannot handle. The marker, the skip list and the log go to `$FMT_OUT`, or to
`$TMPDIR` if it is not set.

The dry run counts the files that the script would format, from its summary line. The module has
no `selftest`, and the sweep does not run it, because it runs Julia over the tree.

## `skill_triggers.py`

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
`claude`. [Typical use](../daily-use.md) shows the commands.

## `doctor.py`

The subcommand `harness doctor [--full]`, the check that a machine's setup works. It is read-only,
so it takes no `--apply`. It prints one line for each check: `PASS`, `WARN`, `FAIL` or `SKIP`, the
name of the check and a detail, such as a version, a path or the reason. A `FAIL` line also names
the section of the setup page that fixes it. The subcommand exits with status 1 when a check
fails, otherwise with status 0; a `WARN` or a `SKIP` does not count. On a usage error, it exits
with status 2.

It checks, in this order:

- the machine: the system and the architecture. On Linux also the two kernel settings for user
  namespaces, the sandbox check `bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid true`,
  and `socat`.
- the tools of [Dependencies](../dependencies.md): each required tool is on the `PATH`, and each
  tool with a minimum on that page is at or above it; below it, or missing, is a `FAIL`. A missing
  tool that serves one frontend, one job or a push to the harness (the frontends, RTK, jq,
  juliaup, iTerm2 and gitleaks) is a `WARN` that says what stops without it. When the version flag
  of a tool exits with a status other than 0, the check is a `FAIL` for a required tool and a
  `WARN` for an optional one. In a session's sandbox, which can refuse the flag, the check is a
  `SKIP`. When the flag exits with status 0 but the subcommand cannot read a version from its
  output, the check is a `WARN` with the tool's own text. The minimums are in
  `MINIMUMS`, and a case compares each with the page. The six Julia packages are read from the
  `Manifest.toml` of the Julia environment of the scripts.
- the profile: it loads, the `tree_agents` directory and the OpenCode configuration directory
  exist, and the line `autocommit_branch` prints the value.
- the install: the dry run of `harness install` reports `0 change(s)`, otherwise a `FAIL` with
  the count. Each warning of the dry run is a `WARN` line.
- the jobs: Kaimon, `~/.julia/bin/kaimon`; its server and the update job, with `systemctl --user`
  on Linux and `launchctl list` with the profile's `launchd_prefix` on macOS; lingering on Linux.
  When the autocommit job is enabled, `~/.claude` must be the top of its own git repository, with
  an `origin`. The Kaimon token file must exist, with mode 600, and not be empty. Without Kaimon,
  its jobs and the token are `SKIP`, and so is the token without OpenCode and oh-my-pi, which read
  it.
- with `--full`, `harness test` and `julia -e 'using Revise'`. Without `--full`, both are `SKIP`.

The subcommand writes no file, starts no service and runs no `--apply`. It prints no secret: it
reads only the existence, the mode and the size of the token file, and does not print the URL of
the `origin` of `~/.claude`. A session's sandbox refuses some of the commands, such as
`launchctl`, and denies the read of the token file. There, these checks are `SKIP` with the
reason, so run the subcommand in a plain terminal for its real verdict.

Its cases run each status of each check on a fixture: a scratch `HOME` and stub commands on the
`PATH` that print what each tool prints on Linux and on macOS. They also check the exit status,
the minimums against the page, that no token reaches the output, and one run of the subcommand on
the fixture of the contract sweep, which changes no file.

## `units.py`

The cases of the `systemd --user` units in `systemd/`. The module has no subcommand. It renders
each unit and its plist in `launchagents/` with `examples/profile.toml`. Then it checks that both
describe one job: the program and its arguments, the working directory, the environment and its
`PATH`, the timer's triggers, the start at login, and `Restart=always` where the plist has
`KeepAlive`. A section, a key or a repeated key that the check does not read is a problem. A
continued line is a problem too. Every element of the `PATH` must be an absolute directory that
the settings template keeps out of a session's writes, or a system directory. An empty element,
which means the working directory, is a problem. The cases also apply a mutant to the rendered
templates and expect a problem: for example a removed restart, an extra trigger or a
session-writable directory on the `PATH`. Last, they check that `render` gives
`autocommit_branch` its default when the profile has no such key: `main`, and
`memory/<short host name>` on a host that is not the template host.
[Jobs and configuration](other.md) describes the units.

## `script_cases.py`

The cases of scripts in `scripts/` that need no Julia. The module has no subcommand. It reads
the critic's `rsync` copy from `skills/build-part/evidence.md` and `copy_command` from
`scripts/run-tests.jl`, runs each on a fixture tree with a `.env`, a `.env.ts`, a `.git` and a
`.claude`, and checks that the copy holds none of them. A control copy with no flag must hold the
`.env.ts`. Then it runs `scripts/spec-gate.py` on a fixture task file and checks the verdict of
each part: a part whose *Files* lie in two repositories is `SPANS`, unless its part tier is
`direct`.

## `network.py`

The network rules of the Claude Code settings. The module has no subcommand. It reads
`settings/network.toml` and the overlay `network.toml` beside the profile, and writes into the
rendered settings template the `WebFetch(domain:…)` rules of `permissions.allow` and
`permissions.deny` and the lists `allowedDomains`, `deniedDomains` and `deniedDomainReasons` of
`sandbox.network`. A `deny` entry removes each `allow` and `infrastructure` host that it matches.
`install`, `render` of the settings template and `settings` call it. The module exits with status
2 in three cases: a file breaks the schema, the profile has the key `extra_domain`, or the
template holds a host of its own. Its cases check each rule, each of these exits, and that an
overlay changes no file of OpenCode or oh-my-pi.
[Adapting the profile](../profile.md#the-network-overlay) describes the keys.

## `providers.py`

The model providers of OpenCode and oh-my-pi. The module has no subcommand. It reads
`providers.toml` beside the profile, which may be missing, and gives each frontend its entries:
the `provider` object of `opencode.jsonc` and the providers of oh-my-pi's `models.yml`. The
OpenCode and oh-my-pi adapters call it in `install`. The module exits with status 2 on a literal
key, an unknown key or a value of the wrong type, and on a profile with the key
`opencode_providers` or `omp_providers`. Its cases check the mapping of each key, the merge of a
frontend's own keys, and each of these exits.
[Adapting the profile](../profile.md#the-providers) describes the keys.

## `sources.py`

The names of the neutral sources: the five directories `agents/`, `skills/`, `rules/`,
`instructions/` and `commands/`, which belong to no single frontend. Each adapter reads them from
here. The module has no subcommand and no cases.

`curated_skills` lists the curated skills below a directory: each subdirectory with a `SKILL.md`,
except a hidden one and the directories of `EXCLUDED_SKILLS`. `listing` gives the agents of
`agents/` and the `SKILL.md` of each curated skill of `skills/`. `code_list` writes names as
Markdown code in a sentence, for the text that the adapters generate.

## `frontmatter.py`

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

## `sweep.py`

The contract sweep, the last set of cases of `harness test`. It has no subcommand.

The sweep creates a fixture `HOME` in a temporary directory: the dummy profile and model tables,
the files that the subcommands read, and a research root with one package and one prose
repository. Then:

- it runs the dry run of each subcommand and checks that it exits with status 0 or 1, prints no
  traceback and changes no file;
- it removes each precondition alone, such as the profile or `~/.claude.json`, and checks that each
  subcommand that needs it exits with status 2 and one line;
- it runs `--apply` of `githooks`, `wiki-lint-hook`, `workflows` and `trust`, and checks that the
  dry run after it exits with status 0.

It does not run `format`, `ci-protection`, `skill-triggers`, `doctor` or `test`.
[Development](../development.md) describes the tests.

## `docs.py`

The check of the component pages of the documentation site, which runs in `harness test`. It has
no subcommand.

The table `KINDS` maps each page of `docs/src/components/` to the tracked files that are its
components, and to the name of each. The check reads the level-2 headings of each page and the
names in backticks in them. It fails when a component has no heading on its page. It also fails
when a heading names something that is not a component of its page, so a removed component leaves no
old section.

It also checks `docs/src/dependencies.md`: its three tables, and one level-3 heading below them
for each tool of the tables, with no heading that names a tool outside them. So a new agent,
skill, hook, script or tool needs its section in the same change.
