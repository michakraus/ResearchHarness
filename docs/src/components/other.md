# Jobs and configuration

This page describes the components that are neither agents, skills, hooks, scripts nor adapters:
the background jobs, an agent workflow, the configuration files and the test queries of the skills.
Most of them reach the user through a copy that the user makes once. Of the files of this page,
`harness install` copies only `Project.toml`. `harness render` prints a template of this page with
the values of the profile.

The sections follow the purpose of the files:

- the launch agents of macOS, in `launchagents/`, and their `systemd --user` units for Linux, in
  `systemd/`;
- the agent workflow `agent-workflows/repo-drift.js`;
- the settings template, the example profile and the example model tables;
- the Julia environment of the scripts, `Project.toml`;
- the linter configuration: `fatou.toml` and the files of `ast-grep/`;
- the leak check, `.gitleaks.toml`;
- the test queries of the skills, `tests/skill-triggers/`.

## `claude-autocommit` and `claude-autocommit.plist`

A macOS launch agent is a job that launchd, the service manager of macOS, runs for one user: on a
schedule, at login, or as a server that it keeps alive. Each job is a plist file in
`~/Library/LaunchAgents/`. The plists in `launchagents/` are templates: their label starts with the
profile key `launchd_prefix`, and their paths hold `{home}`. The harness has no subcommand that
installs them. `harness render launchagents/<name>` prints the rendered plist.

`claude-autocommit` is a Python program that commits the project memories of `~/.claude/`, which
must be a git repository. It commits `projects/*/memory/` only, and
pushes the local `main` to the branch of `origin` that `CLAUDE_AUTOCOMMIT_BRANCH` names, `main`
when the variable is unset. The plist and the unit set it from the profile key
`autocommit_branch`: `main` on the template host, and a branch of its own on each other machine.
The template host is the machine whose Claude Code memory is the template for the other
machines. Without the key `autocommit_branch`, the profile key `template_host` gives the branch:
[One profile for every machine](../profile.md#one-profile-for-every-machine). The script stages
each path by name and commits with a pathspec, so a file that another session staged stays
staged. It skips a file that changed in the last 5 minutes, and refuses a rename or more than 20
deletions.

```
claude-autocommit [--dry-run] [--no-push] [--help]
```

`claude-autocommit.plist` runs the installed copy `~/.local/bin/claude-autocommit` at load and every
15 minutes, on the interpreter of the harness's Python environment,
`~/.local/share/research-harness/python/bin/python`. The script imports only the standard library.
Edit the script here, then copy it there again.

The script runs on macOS and on Linux. A lock directory stops a second run, and the script
removes it on exit and on a SIGTERM. A SIGTERM goes on to the running git, which removes its own
`index.lock`, and the run ends after that git. A git command that takes longer than 10 minutes
also gets a SIGTERM, and the run exits 1 with one `ERROR:` line. On macOS the lock is `~/Library/Logs/claude-autocommit/lock`,
beside the job's log. On Linux it is `$XDG_STATE_HOME/claude-autocommit/lock`, or
`~/.local/state/claude-autocommit/lock` when `XDG_STATE_HOME` is unset or empty. The cases of
`lib/harness/autocommit.py` in `harness test` run the script on fixture repositories with a bare
remote, on the system that runs them, and check the commit, the branch that receives the push, the
lock and the refusals.

## `julia-update.plist`

A launch agent that keeps the Julia installation and the Kaimon server current. It runs daily at
04:30, and not at login. The job runs `~/.local/bin/julia-update.jl`, the installed copy of
`scripts/julia-update.jl`, with the juliaup launcher `~/.juliaup/bin/julia`, under the Seatbelt
profile `~/.config/research-harness/sandbox/julia-update.sb`, as [`kaimon.plist`](#kaimon-plist)
runs under its own. [The scripts](scripts.md) describes what the script does.

The job runs the installed copy and not the copy in `~/Research`, because a session can write
`~/Research` and the job runs outside the Claude Code sandbox. It sets
`JULIA_PKG_USE_CLI_GIT=true`, so Pkg uses the `git` program, and a `PATH` for that `git`. It runs
at a low priority, so it does not compete with an interactive Julia session. Its output goes to
`~/Library/Logs/julia-update/`. On Linux, the script runs as the `systemd --user` unit
`julia-update.service`, whose output goes to
the journal: `journalctl --user -u julia-update.service`.

The label is `<launchd_prefix>.julia-update`. Render the plist with
`harness render launchagents/julia-update.plist`. `harness leaks` renders it with the example
profile.

## `kaimon.plist`

A launch agent that runs the Kaimon MCP server. Kaimon gives an agent a Julia session and tools
for Julia code. The job starts at login, and launchd restarts it when it exits. It runs
`~/.julia/bin/kaimon --headless --port 2828` under the Seatbelt profile
`~/.config/research-harness/sandbox/kaimon.sb`, with `/usr/bin/sandbox-exec -f`; `harness setup`
renders the profile from `sandbox/daemon.toml` ([`jobsandbox.py`](../harness-command.md#jobsandbox-py)).
The first directory of its `PATH`, `~/.config/research-harness/sandbox/shims`, holds the `ps` that
`harness setup` installs from `sandbox/shims/`: the exec of the setuid `/bin/ps` fails under the
profile, and the shim answers Kaimon's check of a session's process with `kill -0`.

The working directory is `~/Research`. Do not remove it: Kaimon reads its tool policy from
`.kaimon/tools.json` in its working directory, and without it Kaimon offers every default tool. A
restart waits at least 60 s, so a second server that cannot use the port does not restart many
times a second. `JULIA_APPS_JULIA_CMD` names the juliaup launcher, so the job does not depend on one
Julia release. `KAIMON_QDRANT_MANAGED=off` stops the background index.
`KAIMON_GATE_PROMOTE_AFTER=240` lets an `ex` call wait up to 240 s for its result before Kaimon
makes it a background job; Kaimon's own default is 30 s. An agent that gets a job id has no way to
wait, so it calls `check_eval` until the job ends, and each call is a model turn that reads the
whole context again. 240 s is below the 5-minute prompt cache of a Claude Code sub-agent and below
the request timeout that the install gives oh-my-pi. Claude Code, OpenCode and Antigravity keep a
Kaimon call open for longer than that. `POCL_CACHE_DIR` gives PoCL, which runs the kernels of the
CPU backend of KernelAbstractions, the kernel cache `~/.cache/kaimon/pocl` in a Julia session.
Kaimon's profile lets the job write below `~/.cache/kaimon` and not PoCL's default
`~/.cache/pocl`, which a sandboxed command may write: so Kaimon has a cache of its own, and no
command can put a compiled kernel where Kaimon loads and runs it. `harness setup` creates the
directory before it loads the job, each directory that it creates with mode 700.

OpenCode, oh-my-pi and Antigravity connect to this server at `http://127.0.0.1:2828/`. The update
job `julia-update.plist` restarts it when its Julia release is deleted. Render the plist with
`harness render launchagents/kaimon.plist`.

## `kaimon.service`, `julia-update.service`, `julia-update.timer`, `claude-autocommit.service` and `claude-autocommit.timer`

The `systemd --user` units in `systemd/` run the three jobs of the plists on Linux. Like the
plists, they are templates of the profile: `harness render systemd/<name>` prints a rendered unit,
and `harness setup` installs them with what they need. `kaimon.service` and
`julia-update.service` start their program through `~/.local/bin/jobbox` under `bwrap`, with the
arguments of `~/.config/research-harness/sandbox/<job>.bwrap` ([`jobsandbox.py`](../harness-command.md#jobsandbox-py)).
By hand, install `sandbox/jobbox` and `scripts/julia-update-server` into `~/.local/bin`, each
with mode 755, write `harness render sandbox/<job>.bwrap` for `kaimon` and `julia-update` into
`~/.config/research-harness/sandbox/`, create each write deny and each pin of the two files,
`~/.julia/juliaup/.juliaup-lock` and `~/.cache/julia-update`, copy each rendered unit into
`~/.config/systemd/user/`, run `systemctl --user daemon-reload`, create the server's PoCL cache,
and enable the server and the two timers:

```
(umask 077 && mkdir -p ~/.cache/kaimon/pocl)
systemctl --user enable --now kaimon.service julia-update.timer claude-autocommit.timer
```

Each unit describes the same job as its plist:

| unit | plist | how it runs |
|:--|:--|:--|
| `kaimon.service` | `kaimon.plist` | at login (`WantedBy=default.target`), restarted on exit after 60 s (`Restart=always`, `RestartSec=60`), in `~/Research` |
| `julia-update.service`, `julia-update.timer` | `julia-update.plist` | daily at 04:30 (`OnCalendar`), not at login |
| `claude-autocommit.service`, `claude-autocommit.timer` | `claude-autocommit.plist` | when the timer starts (`OnActiveSec=0`), then 15 minutes after each run (`OnUnitActiveSec`) |

The program and its arguments, the environment and the `PATH` are those of the plist, with
`jobbox <job>` in place of `sandbox-exec -f <profile>`, and without the shim directory of
`kaimon.plist`, which is for macOS only. `julia-update.service` runs
`~/.local/bin/julia-update-server` outside `bwrap` as its `ExecStopPost`: the server check, the
restart and the alerts of [the script](scripts.md). Both timers
set `Persistent=true`, so a calendar start that the machine missed while it slept runs when the
timer starts again. The units are `--user` units only. Their output goes to the journal:
`journalctl --user -u <name>`. `julia-update-server` restarts the server as `kaimon.service`.

The jobs run outside the sandbox, so their `PATH` holds no directory that a session can write.
Each directory is one that the settings template keeps out of a session's writes, because no
`allowWrite` entry covers it or a `denyWrite` entry names it, or one of `/usr/bin`, `/bin`,
`/usr/sbin`, `/sbin`, `/usr/local/bin` and `/opt/homebrew/bin`. No directory is at or below
`$TMPDIR` (also its real path), `/var/folders` or `/private/var/folders`, which the live sandbox
lets a session write. `harness test` renders each unit and its plist with the example profile and
checks all of this, through `units.py` of [the harness command](../harness-command.md#units-py). CI renders each
unit on `ubuntu-latest` and runs `systemd-analyze verify --user` on it. `harness leaks` renders
them with the example profile.

## `repo-drift.js`

A `Workflow` script of Claude Code that checks whether the repositories of the tree still hold the
canonical copies of `githooks/`. `agent-workflows/README.md` explains the directory and its rules
for a workflow script.

Call it with absolute paths of repositories below a `Research/` directory:

```
Workflow({scriptPath: '<home>/Research/Harness/agent-workflows/repo-drift.js',
          args: ['<home>/Research/Packages/<name>', ...]})
```

The first stage runs one agent per repository, on a small model. It compares the two git hooks, the
CI, dependabot, Documenter and TagBot files, and `codecov.yml` at the repository root with
`Harness/githooks/`. It also reports `core.hooksPath` and whether `.gitignore` and `CHANGELOG.md`
exist. A second stage reads each differing file again, and confirms or overturns the finding.
The result names each repository that returned nothing. The script compares `TagBot.yml` in every
repository, and `harness workflows` adds it only to a package, so its row "missing" in an
experiment is expected.

The script only reads. Check its result against `githooks/verify-workflows.jl`. To correct a drift,
run `harness workflows` or `harness githooks`.

## `settings.proposal.json`

The settings template, the policy source of all four frontends. It holds the Claude Code settings
with placeholders such as `{home}`, `{org}` and `{protected_dir}`, which the profile fills in.

The template has the sections `permissions`, `hooks`, `sandbox` and `modelSettings`, and other
keys of `settings.json`. These components read it:

- `harness install` merges `permissions`, `hooks`, `sandbox` and `modelSettings` into
  `~/.claude/settings.json`. It keeps every other key of that file, and adds each other key of the
  template that the file does not have;
- `harness settings surface`, `compare` and `twins` measure and check it;
- `harness permissions` writes the OpenCode permission block from its `ask` and `deny` rules;
- `harness install` writes the `bash.patterns` and the path list of oh-my-pi from it;
- `harness install` writes the permission rules of Antigravity's CLI, the grants of its desktop
  app and the path list of its guard hook from it;
- `harness leaks` renders it with the example profile.

Edit the template, never the installed `settings.json`, and commit it when you install it.
[Typical use](../daily-use.md) gives the steps. [The security model](../safeguards/security-model.md) says which of
its mechanisms is a boundary and which only prevents accidents.

The template names no host: its `sandbox.network.allowedDomains` is empty, and it has no
`WebFetch(domain:…)` rule. `network.toml` gives them.

## `network.toml`

The hosts of the network rules of Claude Code, in four arrays: `allow`, the hosts that the
`WebFetch` tool and a sandboxed command can reach; `fetch`, the hosts that only the `WebFetch`
tool can reach; `infrastructure`, the hosts that only a sandboxed command can reach; `deny`, the
hosts that neither can reach, with a reason for each in `[deny_reasons]`. Comments group the
hosts: literature, mathematics, Julia, GitHub, package registries.

`harness install`, `harness render` of the settings template and `harness settings` generate the
`WebFetch(domain:…)` rules and the lists of `sandbox.network` from this file and from the overlay
`network.toml` beside the profile, which `examples/network.toml` shows. A `deny` entry of either
file wins over an `allow`, `fetch` or `infrastructure` entry of either file. OpenCode and oh-my-pi
do not read the file; for Antigravity, `harness install` writes the `allow` and `fetch` hosts as
`read_url(<host>)` rules. [Adapting the profile](../profile.md#the-network-overlay) gives the
rules of each key.

## `profile.toml`

The example of the private profile, `examples/profile.toml`. The profile holds every value that
names a person, an institution or a machine, for example the home directory, the GitHub accounts
and the strings that must never be in the repository. A template names a key as `{key}`.

Copy the file to `~/.config/research-harness/profile.toml`, and write your values into the copy.
`harness --profile F` and `$RESEARCH_HARNESS_PROFILE` name another path. The example has no `home`
and writes its paths with `~/`, so it takes the home directory of the user who runs `harness`.

The harness uses the example too. `harness leaks` renders every template with it, and the test
cases use it as their dummy profile. So it must name every key that a template uses.
[Adapting the profile](../profile.md) names each key and the subcommands that read it.

## `models.toml`

The example of the model tables, `examples/models.toml`. An agent or a skill names a tier in its
`model:`: `large`, `medium` or `small`. The model tables map each tier to a model of each frontend.

`[claude]` gives the Claude Code model of each tier, and `[antigravity]` the Antigravity tier of
each tier: `inherit`, `flash`, `flash_lite` or `pro`, because an Antigravity agent can name no
model. OpenCode and oh-my-pi share every other table, so that their agents run on the same models:
the model of each tier, a model for one agent, the variants, the reasoning effort, the councils,
which copy an agent onto other models, and the context limits. `[opencode]` and `[omp]` hold the
same sub-tables, and each of their keys replaces the shared key for that frontend alone. When a
table names a tier by an old name, `opus`, `sonnet` or `haiku`, `harness install` stops with exit
status 2.

Copy the file to `models.toml` beside the profile. `harness --models F` and
`$RESEARCH_HARNESS_MODELS` name another path. Only `harness install` reads it. The test cases use
the example as it is. [Adapting the profile](../profile.md) describes each table.

## `providers.toml`

The example of the providers, `examples/providers.toml`: the model servers and accounts of
OpenCode and oh-my-pi beyond their built-in providers, each written once. A table is one provider,
with neutral keys such as `api`, `url` and `key`, and its models. `harness install` writes each
provider into the `provider` object of OpenCode's `opencode.jsonc` and into oh-my-pi's
`models.yml`.

Copy the file to `providers.toml` beside the profile, and write your providers into the copy. The
file is optional. The test cases copy the example beside their scratch profile.
[Adapting the profile](../profile.md#the-providers) maps each key to each frontend.

## `repositories.toml`

The example of the repository table, `examples/repositories.toml`: the repositories of the
research tree and their clone URLs, for `harness clone` and `harness repos`. A top-level key is a
fixed repository, `knowledge`, `environment`, `tasks` or `library`; a table is a
group, `packages`, `experiments`, `papers`, `books`, `talks` or `projects`, and each key in it a
directory of that group. Each directory is its key in title case below the research root.

Copy the file to `repositories.toml` beside the profile, or name it with
`$RESEARCH_HARNESS_REPOSITORIES`, and write your repositories into the copy. The file is optional:
without it, `harness repos` takes each git repository that it finds, and `harness clone` stops.
The contract sweep writes a table of its own into its fixture.

## `Project.toml`

The Julia environment of the scripts of the harness. It names the eight packages that the scripts
load beyond the standard library, with their `[compat]` bounds: Aqua, ExplicitImports, JET, JSON,
JuliaFormatter, JuliaSyntax, TestEnv and YAML.

`harness install --apply` copies the file to `~/.local/share/research-harness/julia/`, or to
`$RESEARCH_HARNESS_JULIA`, and instantiates it there. Each script that loads one of the packages
puts that environment on its load path. No `Manifest.toml` is committed.

The scripts never use this file in place. A session can edit the checkout, and the update job runs
outside the sandbox, so the job must install only the packages that the installed copy names.
[Dependencies](../dependencies.md#aqua-explicitimports-jet-json-juliaformatter-juliasyntax-testenv-and-yaml) says what each package does.

## `fatou.toml`

The global configuration of fatou, a linter for Julia code. fatou reads
`$XDG_CONFIG_HOME/fatou/fatou.toml`, and does not look above the root of a git repository. Copy the
file by hand, and copy it again after a change:

```bash
cp ~/Research/Harness/fatou.toml ~/.config/fatou/fatou.toml
```

The file turns off the rule `unused-import`. That rule does not follow `include`, so in a package
whose imports are in the module file, almost every finding is false. ExplicitImports answers that
question instead.

The installed pre-commit hook runs `fatou lint` with this configuration, and prints its findings as
advice. `scripts/mutate.jl` writes a configuration of its own and does not read this file.

## `research-sgconfig.yml`

The configuration of ast-grep, a tool that searches code by its syntax tree, for the whole research
tree. Copy it by hand to `~/Research/sgconfig.yml`. ast-grep looks for `sgconfig.yml` in each parent
directory, so the file applies to every repository of the tree.

Julia is not a language that ast-grep knows. The file registers `julia` as a custom language for
`.jl` files, with the parser library `Harness/ast-grep/julia.dylib`, which `build-julia.sh` builds.
It also names `Harness/ast-grep/rules` as the directory of the rules and
`Harness/ast-grep/rule-tests` as the directory of the rule tests. The paths are relative to
`~/Research`, so the checkout must be at `~/Research/Harness`.

## `build-julia.sh`

A bash script that builds the Julia parser library of ast-grep. It fetches the tree-sitter-julia
grammar at a pinned commit into a temporary directory. Then it compiles the grammar with `cc` into
`julia.dylib` beside the script, and deletes the temporary directory.

```bash
ast-grep/build-julia.sh
```

Run it once on each machine, and again after a change of the pinned commit. `julia.dylib` is
ignored by git, so it is never committed. `research-sgconfig.yml` names the library.

## `rules/parse-error.yml`

A rule of ast-grep for Julia code. It marks each place where tree-sitter-julia could not parse the
code: a node of the kind `ERROR`. Its severity is `info`.

The rule tells you where a search with a pattern can miss code, because the syntax tree there is
not correct. `research-sgconfig.yml` names `ast-grep/rules/` as the directory of the rules, so
ast-grep uses the rule in every repository of the tree.

## The rules of severity error

The five rules in the sections below have the severity `error`. Each one finds a defect in Julia
code that a pattern over the syntax tree decides with a low risk of a false hit. The message of
each rule names the fix. To silence one hit, write the comment `# ast-grep-ignore: <rule-id>` at
the end of the line or on the line above. Two rules match a comment, and for them this works only
in part: `docstring-comment` cannot be silenced, and `line-citation-comment` is silenced only from
the line above.

## `rules/docstring-comment.yml`

The rule `docstring-comment` finds a `#` comment directly after the closing `"""` of a docstring,
before its definition. Such a comment detaches the docstring: the definition has no docstring,
and each `@ref` to it fails. Move the comment above the docstring or into the definition.

The rule matches a comment that is the next sibling of a triple-quoted string. It does not match
a comment after a one-line `"…"` string, because a plain string statement has the same shape. It
also does not match a comment inside the definition, or a comment at the end of the definition's
line.

The rule cannot be silenced. A comment `# ast-grep-ignore: docstring-comment` after the docstring
is itself a hit, at the end of the `"""` line too. A comment in this place always detaches the
docstring, so the fix is to move it.

## `rules/allocated-equality.yml`

The rule `allocated-equality` finds two `@allocated` readings compared exactly:
`@allocated(a) == @allocated(b)` or `@allocated(a) === @allocated(b)`, inside `@test` too. A
reading in parentheses, such as `(@allocated a)`, counts too. Windows quantises the figures by 16
bytes, so an exact comparison fails there. Assert the difference under a stated tolerance
instead. A comparison of one reading with a number, or with `<=`, is not a hit.

## `rules/exitcode-alone.yml`

The rule `exitcode-alone` finds `p.exitcode` in a definition that neither reads `termsignal` nor
calls `success`. A process that a signal ends has the exit code 0 in Julia, so the exit code alone
reads it as a success. Check `termsignal` too, or call `success(p)`.

A definition is a `function … end` or a short form `f(…) = …`, also with a return type or a
`where` clause, as in `f(p)::Bool = …`. The rule looks for `termsignal` and a call of `success`,
also as `Base.success(p)`, in the enclosing definition, and for a read at top level in the whole
file. A `termsignal` read in another function does not count.

## `rules/line-citation-comment.yml`

The rule `line-citation-comment` finds a comment that holds a file name ending in `.jl`, a colon
and digits, such as `solver.jl:120`. The next edit that changes the line count of that file makes
the citation false. Name the function instead. A ratio such as `3:1`, a file name without a
line, and the same text in a string are not hits.

A comment `# ast-grep-ignore: line-citation-comment` at the end of the line is part of the same
comment, so it does not silence the hit. Write it on the line above.

## `rules/debug-probe.yml`

The rule `debug-probe` finds a temporary probe in a file under `src/` or `ext/`: an `@show` call,
`Base.@show` too, or a string that holds `[DEBUG-`. Remove the probe before the commit. Tests,
scripts and docs may print, so the rule has the `files:` globs `**/src/**/*.jl` and
`**/ext/**/*.jl`.

## The rule tests

The directory `rule-tests/` holds the rule tests of ast-grep: one file `<rule-id>-test.yml` for
each rule of severity `error`. Each
file holds `valid` snippets, which the rule must not match, and `invalid` snippets, which it must
match. `ast-grep test` runs them:

```bash
ast-grep test -c ~/Research/sgconfig.yml --custom-languages allow --skip-snapshot-tests
```

Without `--custom-languages allow`, ast-grep ignores the language `julia`, and each test that
expects no hit passes. A snippet has no path, so a rule test cannot test the `files:` globs of
`debug-probe`. The directory `rule-tests/scope/` holds the file `probe.jl`, with one `@show x`,
under `src/`, `ext/`, `test/` and `scripts/`. A scan of `scope/` with `debug-probe` must hit
exactly `src/probe.jl` and `ext/probe.jl`.

### The `ast-grep` job of CI

The job `ast-grep` of the workflow `julia.yml` runs the rule tests. The path filter of the
workflow names `ast-grep/**`, so a change of a rule or a rule test alone starts it. The job
installs the release 0.51.1 of ast-grep, with its SHA-256, and builds the parser with
`build-julia.sh`. `research-sgconfig.yml` names its paths relative to `~/Research`, so the job
writes a configuration with the checkout's absolute paths. Then it runs `ast-grep test` and the
scan of `rule-tests/scope/`. The job fails when a test fails, when a test names a rule that does
not exist, or when the scan does not hit exactly `src/probe.jl` and `ext/probe.jl`.

## `.gitleaks.toml`

The configuration of gitleaks, the tool that finds secrets in text. The pre-push hook of this
repository and the `leaks` job of CI read it.

It keeps the default rules of gitleaks, and adds the rule `home-path`: a path below `/Users/` or
`/home/` that names a user. The rule allows only the two example homes of the repository,
`/Users/me` and `/home/example`. Every call of gitleaks passes `--ignore-gitleaks-allow`, so a
`gitleaks:allow` comment has no effect.

Remove a false positive by a change of the text, not of the configuration. A new allowlist entry
needs the approval of the user and its own line in `CHANGELOG.md`. `harness leaks` finds the
private strings of the profile, which gitleaks does not know. [Development](../development.md)
describes both checks.

## `tests/skill-triggers`

The queries of the skill-trigger test, one TOML file for each skill of `skills/`,
`tests/skill-triggers/<skill>.toml`. `harness skill-triggers` reads them.

A skill that the model can load has `load`, 10 queries that must load it, and `near`, 5 queries
that must not. Each `near` entry names the skill that the query belongs to, or `none`. A skill with
`disable-model-invocation: true` has one `near` query and no `load`. A query must not start with
`/`, and must not occur twice in one file. A `near` entry must not name the skill of its own file.
On another count or form, `harness skill-triggers` exits with status 2.

`fixtures/` holds recorded `stream-json` output of Claude Code sessions, with the private content
removed, and some streams written by hand. The cases of `harness test` read them to check how a
session's output is judged.

Run the test after you change the `description` of a skill. [Typical use](../daily-use.md) shows the
commands.
