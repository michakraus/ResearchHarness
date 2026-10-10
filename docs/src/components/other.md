# Jobs and configuration

This page describes the components that are neither agents, skills, hooks, scripts nor adapters:
the background jobs, an agent workflow, the configuration files and the test queries of the skills.
Most of them reach the user through a copy that the user makes once. `harness install` copies only
`Project.toml` of this page. `harness render` prints a template of this page with the values of the
profile.

The sections follow the purpose of the files:

- the launch agents of macOS, in `launchagents/`;
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
profile key `launchd_prefix`, and their paths hold `{home}`. The harness has no verb that installs
them. `harness render launchagents/<name>` prints the rendered plist.

`claude-autocommit` is a bash script that commits the plan files and the project memories of
`~/.claude/`, which must be a git repository. It commits `plans/` and `projects/*/memory/` only, and
pushes to `origin main`. It stages each path by name and commits with a pathspec, so a file that
another session staged stays staged. It skips a file that changed in the last 5 minutes, and refuses
a rename or more than 20 deletions.

```
claude-autocommit [--dry-run] [--no-push] [--help]
```

`claude-autocommit.plist` runs the installed copy `~/.local/bin/claude-autocommit` at load and every
15 minutes. Edit the script here, then copy it there again.

## `julia-update.plist`

A launch agent that keeps the Julia installation and the Kaimon server current. It runs daily at
04:30, and not at login. The job runs `~/.local/bin/julia-update.jl`, the installed copy of
`scripts/julia-update.jl`, with the juliaup launcher `~/.juliaup/bin/julia`. [The
scripts](scripts.md) describes what the script does.

The job runs the installed copy and not the copy in `~/Research`, because a session can write
`~/Research` and the job runs outside the sandbox. It sets `JULIA_PKG_USE_CLI_GIT=true`, so Pkg
uses the `git` program, and a `PATH` for that `git`. It runs at a low priority, so it does not
compete with an interactive Julia session. Its output goes to `~/Library/Logs/julia-update/`.

The label is `<launchd_prefix>.julia-update`. Render the plist with
`harness render launchagents/julia-update.plist`. `harness leaks` renders it with the example
profile.

## `kaimon.plist`

A launch agent that runs the Kaimon MCP server. Kaimon gives an agent a Julia session and tools
for Julia code. The job starts at login, and launchd restarts it when it exits. It runs
`~/.julia/bin/kaimon --headless --port 2828`.

The working directory is `~/Research`. Do not remove it: Kaimon reads its tool policy from
`.kaimon/tools.json` in its working directory, and without it Kaimon offers every default tool. A
restart waits at least 60 s, so a second server that cannot use the port does not restart many
times a second. `JULIA_APPS_JULIA_CMD` names the juliaup launcher, so the job does not depend on one
Julia release. `KAIMON_QDRANT_MANAGED=off` stops the background index.

OpenCode and oh-my-pi connect to this server at `http://127.0.0.1:2828/`. The update job
`julia-update.plist` restarts it when its Julia release is deleted. Render the plist with
`harness render launchagents/kaimon.plist`.

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
exist. A second stage reads each file that differs again, and confirms or overturns the finding.
The result names each repository that returned nothing.

The script only reads. Check its result against `githooks/verify-workflows.jl`. To correct a drift,
run `harness workflows` or `harness githooks`.

## `settings.proposal.json`

The settings template, the policy source of all three frontends. It holds the Claude Code settings
with placeholders such as `{home}`, `{org}` and `{protected_dir}`, which the profile fills in.

The template has the sections `permissions`, `hooks` and `sandbox`, and other keys of
`settings.json`. These components read it:

- `harness install` merges `permissions`, `hooks` and `sandbox` into
  `~/.claude/settings.json`. It keeps every other key of that file, and does not install the other
  keys of the template;
- `harness settings surface`, `compare`, `twins` and `domains` measure and check it;
- `harness permissions` writes the OpenCode permission block from its `ask` and `deny` rules;
- `harness install` writes the `bash.patterns` and the path list of oh-my-pi from it;
- `harness leaks` renders it with the example profile.

Edit the template, never the installed `settings.json`, and commit it when you install it.
[Typical use](../daily-use.md) gives the steps. [The security model](../security.md) says which of
its mechanisms is a boundary and which only prevents accidents.

## `profile.toml`

The example of the private profile, `examples/profile.toml`. The profile holds every value that
names a person, an institution or a machine, for example the home directory, the GitHub accounts
and the strings that must never be in the repository. A template names a key as `{key}`.

Copy the file to `~/.config/research-harness/profile.toml`, and write your values into the copy.
`harness --profile F` and `$RESEARCH_HARNESS_PROFILE` name another path. The example uses the home
`/home/example`.

The harness uses the example too. `harness leaks` renders every template with it, and the test
cases use it as their dummy profile. So it must name every key that a template uses.
[Adapting the profile](../profile.md) names each key and the verbs that read it.

## `models.toml`

The example of the model tables, `examples/models.toml`. An agent or a skill names a tier in its
`model:`: `large`, `medium` or `small`. The model tables map each tier to a model of each frontend.

The file has one table for each frontend. `[claude]` gives the Claude Code model of each tier.
`[opencode]` has sub-tables: the model of each tier, a model for one agent, the variants, the
reasoning effort, and the councils, which copy an agent onto other models. `[omp]` gives the
oh-my-pi model of each tier. A table that names a tier by an old name, `opus`, `sonnet` or `haiku`,
stops `harness install` with exit 2.

Copy the file to `models.toml` beside the profile. `harness --models F` and
`$RESEARCH_HARNESS_MODELS` name another path. Only `harness install` reads it. The test cases use
the example as it is. [Adapting the profile](../profile.md) describes each table.

## `Project.toml`

The Julia environment of the scripts of the harness. It names the six packages that the scripts
load beyond the standard library, with their `[compat]` bounds: ExplicitImports, JSON,
JuliaFormatter, JuliaSyntax, TestEnv and YAML.

`harness install --apply` copies the file to `~/.local/share/research-harness/julia/`, or to
`$RESEARCH_HARNESS_JULIA`, and instantiates it there. Each script that loads one of the packages
puts that environment on its load path. No `Manifest.toml` is committed.

The scripts never use this file in place. A session can edit the checkout, and the update job runs
outside the sandbox, so it must install only what the installed copy names.
[Dependencies](../dependencies.md#explicitimports-json-juliaformatter-juliasyntax-testenv-and-yaml) says what each package does.

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
It also names `Harness/ast-grep/rules` as the directory of the rules. The paths are relative to
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

## `.gitleaks.toml`

The configuration of gitleaks, the tool that finds secrets in text. The pre-push hook of this
repository and the `leaks` job of CI read it.

It keeps the default rules of gitleaks, and adds the rule `home-path`: a path below `/Users/` or
`/home/` that names a user. The rule allows only the two example homes of the repository,
`/Users/me` and `/home/example`. Every call of gitleaks passes `--ignore-gitleaks-allow`, so a
`gitleaks:allow` comment has no effect.

Fix a false positive in the text. A new allowlist entry needs the approval of the user and its own
line in `CHANGELOG.md`. `harness leaks` finds the private strings of the profile, which gitleaks does
not know. [Development](../development.md) describes both checks.

## `tests/skill-triggers`

The queries of the triggering test of the skills, one TOML file for each skill of `skills/`,
`tests/skill-triggers/<skill>.toml`. `harness skill-triggers` reads them.

A skill that the model can load has `load`, 10 queries that must load it, and `near`, 5 queries
that must not. Each `near` entry names the skill that the query belongs to, or `none`. A skill with
`disable-model-invocation: true` has one `near` query and no `load`. A query must not start with
`/`, and must not occur twice in one file. A `near` entry must not name the skill of its own file.
Another count or form exits 2.

`fixtures/` holds recorded `stream-json` output of Claude Code sessions, with the private content
removed, and some streams written by hand. The cases of `harness test` read them to check how a
session's output is judged.

Run the test after you change the `description` of a skill. [Typical use](../daily-use.md) shows the
commands.
