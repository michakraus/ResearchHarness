# Dependencies

The harness calls the tools below. A tool is required when a verb, a [hook](concepts.md#hook), the
pre-push gate, CI or an installed git hook calls it. An optional tool serves one
[frontend](concepts.md#frontend) or one job; the `used for`
column also says what stops without it. The minimum is the floor that the code checks, that CI
pins, that `[compat]` sets or that a release note names for a feature the code uses; each floor
names its source. Where no floor exists, the cell gives the version that the harness is tested
with.

The tools are in three tables. *Generic tools* are the required tools that serve any language.
*Julia and its packages* are the tools that only Julia code needs; in this table, Kaimon and
juliaup are optional, as their rows say. *Optional* are the other optional tools. Below the tables,
[What each tool does](#what-each-tool-does) says what each tool does, why the harness needs it,
and where the harness calls it.

## Generic tools

| tool | minimum | used for |
|:--|:--|:--|
| Python | ≥ 3.11, the check in `bin/harness` | runs the `harness` command, the guard hooks and the pre-push gate |
| git | tested with 2.54.0 | reads and pushes the repositories of the tree, makes the worktrees of Claude Code, and clones the pushed commit for the pre-push gate |
| gh | tested with 2.102.0 | protects the default branch of each repository on GitHub, in `harness ci-protection` |
| gitleaks | ≥ 8.21, the check in `.githooks/pre-push` | finds secrets in the commits of a push, in the pre-push gate and in CI |
| Node.js | ≥ 20.16 (20.x), ≥ 22.3, for `process.getBuiltinModule`, as the API documentation says: <https://nodejs.org/api/process.html#processgetbuiltinmoduleid> | loads the guard extensions of oh-my-pi and OpenCode in the hook probe of `harness test`, and builds the documentation site with npm and VitePress |
| shellcheck | tested with 0.11.0 | checks the shell scripts, in the pre-push gate and in CI |
| actionlint | ≥ 1.7.12, the CI pin in `.github/workflows/test.yml` | checks the GitHub workflow files, in CI |
| timeout | tested with 9.12 | stops `fatou lint` in the installed pre-commit hook after 60 seconds |
| rsync | tested with 3.5.1 | copies a package without its `.git` directory, for the test runner and the mutation tests |

## Julia and its packages

| tool | minimum | used for |
|:--|:--|:--|
| Julia | ≥ 1.13, `[compat]` in `Project.toml` | runs the Julia scripts: the formatter, the test runner, the mutation tests, the workflow check and the installed git hooks |
| ExplicitImports | ≥ 1.15, `[compat]` in `Project.toml` | finds the names that a package uses without an explicit import, in the script `explicit-imports.jl` and the package audit |
| JSON | ≥ 1.10, `[compat]` in `Project.toml` | writes the reports of the test gate and the mutation tests |
| JuliaFormatter | ≥ 2.14, `[compat]` in `Project.toml` | formats Julia code, in `harness format` and the installed pre-commit hook |
| JuliaSyntax | ≥ 1.0.2, `[compat]` in `Project.toml` | parses Julia code to make the mutants of a mutation test |
| TestEnv | ≥ 1.103.7, `[compat]` in `Project.toml` | runs the tests of a package in its test environment, for the test runner and the mutation tests |
| YAML | ≥ 0.4.17, `[compat]` in `Project.toml` | reads the CI workflows and the frontmatter of the wiki pages |
| fatou | ≥ 0.22.0, the CI pin in `.github/workflows/julia.yml` | lints the staged Julia files before a commit, and rejects a mutant that uses an undefined name |
| Kaimon | tested with 2.10.0, the `version` of its app project | gives an [agent](concepts.md#agent) a Julia [session](concepts.md#session) and tools for Julia code; without it, the update job stops with an error, and the agents have no Julia session |
| juliaup | tested with 1.18.9 | updates the Julia releases, in the update job; without it, the job cannot update them |

**For a reader who writes no Julia.** The rows of this table serve Julia code only: the formatter,
the test runner and the mutation tests, the git hooks and workflows that `harness githooks` and
`harness workflows` [install](concepts.md#install) into Julia packages, the workflow check of
`harness ci-protection`, the wiki lint, the update job, and the Julia session of an agent through
Kaimon. Without them, a reader who writes no Julia loses these tools and nothing else: the
instruction layer, the settings, the guard hooks, the leak checks and the warning about
[drift](concepts.md#drift) work the same. Julia itself is
the one exception. `harness install --apply` instantiates the Julia environment of the scripts
before it writes the configuration, and without `julia` it stops and writes nothing. So install
Julia even if you write no Julia code; the install then adds the six packages itself, and fatou,
Kaimon and juliaup can stay out.

## Optional

| tool | minimum | used for |
|:--|:--|:--|
| Claude Code | tested with 2.1.295 | reads the layer that `harness install` writes into `~/.claude/`, and runs the triggering test of the [skills](concepts.md#skill); without it, neither happens |
| OpenCode | tested with 2.0.26 | reads the configuration that `harness install` writes into `~/.config/opencode/`; without it, nothing reads that configuration |
| oh-my-pi | tested with 18.8.6 | reads the configuration that `harness install` writes into `~/.omp/agent/`; without it, nothing reads that configuration |
| RTK | tested with 0.51.0 | shortens the output of shell commands in OpenCode; without it, the plugin passes each command unchanged |
| jq | tested with 1.7.1 | reads the session data for the Claude Code status line; without it, the status line shows no values |
| iTerm2 | tested with 3.7.3, the `CFBundleShortVersionString` of the app | shows the state of a Claude Code session in the terminal tab; without it, the hook `hooks/cc-status` does nothing and exits 0, which blocks nothing |

The tables leave out the system tools: the POSIX shell utilities, such as `awk`, `sed`, `grep`,
`ps`, `kill`, `id` and `mktemp`; the tools that macOS supplies, `launchctl`, `security`,
`osascript`, `lsof`, `pgrep` and `tar`; and the tools of the GitHub runner that the CI jobs call,
`curl`, `tar` and `sha256sum`. On Linux, the update job `julia-update.jl` calls `lsof`,
`systemctl` and `notify-send` in place of the macOS tools, and finds each on the `PATH`. Without
`lsof` its server check fails; without `notify-send` it writes the log line only.

## What each tool does

Each section below describes one tool of the tables, or the six Julia packages together: what the
tool does, what the harness uses it for, why the harness needs it, and where the harness calls it.
The sections follow the order of the tables.

### Python

Python is the language of the `harness` command, the guard hooks and the hook probe. The
command uses the standard library only, so no package must be installed.

Every verb runs on Python. The pre-push gate runs `bin/harness test` on `python3` and on
`python3.11`, and CI runs it on Python 3.11 and the latest 3.x. The guard hooks are Python
scripts, which Claude Code, OpenCode and oh-my-pi call before a [tool call](concepts.md#tool-call).

The harness needs Python 3.11 or later because the [profile](concepts.md#profile) and the model
tables are TOML, and
`tomllib` is in the standard library from 3.11. A shell script cannot parse TOML or JSON safely,
and a compiled tool needs a build step on each machine.

Call sites: every verb (`bin/harness`); the pre-push gate (`.githooks/pre-push`, also for
`python3.11`, which the gate skips when it is missing, because CI job `python` runs Python 3.11);
the guard hooks, which oh-my-pi calls (`adapters/omp/guards.ts`).

### git

git is the version control system. Each repository of the research tree is a git repository.

The verbs that work across the tree use git: `harness githooks` reads each repository's
configuration, `harness push-all` pushes each repository, and `harness leaks --commits` reads the
commits of a push. The hook `hooks/worktree.py` makes the worktrees of Claude Code, and the
pre-push gate clones the pushed commit and tests it.

The harness needs git because its work is on git repositories: the hooks, the commits and the
pushes are git's own objects. No other tool reads them.

Call sites: the verbs (`lib/harness/githooks.py`, `lib/harness/profile.py`); the hook
`hooks/worktree.py`; the pre-push gate (`.githooks/pre-push`).

### gh

gh is the command-line client of GitHub. It calls the GitHub API with the credentials of the
user.

`harness ci-protection` calls `gh api` to protect the default branch of each repository on GitHub.

The harness needs gh because branch protection is a setting on GitHub, which only the API
changes. gh holds the user's credentials, so the harness stores no token of its own.

Call site: `harness ci-protection` (`lib/harness/protection.py`).

### gitleaks

gitleaks finds secrets in text: tokens, keys and other values with a known shape. It reads a
directory, the commits of a git repository, or standard input.

The pre-push gate runs gitleaks over the commits that a push sends, over their messages and over
the tree of the pushed commit. The CI job `leaks` does the same with gitleaks 8.30.1 at a fixed
checksum. The configuration `.gitleaks.toml` adds a pattern for home paths.

The harness needs gitleaks because the repository is public, and a leak is permanent once it is
pushed. The patterns of gitleaks for known secret shapes are maintained upstream; the harness's own
`harness leaks` finds only the private strings of the profile. Version 8.19 added the `git`, `dir`
and `stdin` commands
([release note](https://github.com/gitleaks/gitleaks/releases/tag/v8.19.0)). Version 8.21 is the
first with several allowlists for one pattern, `[[rules.allowlists]]`, which `.gitleaks.toml` uses
([release note](https://github.com/gitleaks/gitleaks/releases/tag/v8.21.0)).

Call sites: the pre-push gate (`.githooks/pre-push`); CI job `leaks`, which pins 8.30.1.

### Node.js

Node.js runs JavaScript outside a browser.

`harness test` runs the hook probe, which loads the guard extension of oh-my-pi and the OpenCode
plugins under Node.js and checks their decisions. A missing `node` is a wrong case of the probe.

The harness needs Node.js because these extensions are JavaScript, and their frontends run them
in a JavaScript runtime. The plugins take the Node.js built-in modules from
`process.getBuiltinModule`, which Node.js 22.3 and 20.16 added.

The documentation site is a VitePress project, and its build runs under Node.js too: `npm`
installs the packages that `docs/package-lock.json` pins, and VitePress builds the site and draws
the call graphs. Only the docs build needs these packages; the harness itself does not.

Call sites: the hook probe of `harness test` (`hooks/probe.py`); the
docs build (`docs/package.json`, `.github/workflows/docs.yml`).

### shellcheck

shellcheck finds errors in shell scripts: a missing quote, an unset variable, a construct that
does not work in the given shell.

The pre-push gate and CI job `lint` run `shellcheck -S warning` over each tracked file with a sh
or bash shebang: the git hooks, the hook `hooks/cc-status` and the status line script. The gate
skips shellcheck when it is missing, because CI runs it.

The harness needs shellcheck because the git hooks run in every repository of the tree, and an
error in a hook can let a commit through unchecked. The shell does not report most of these
errors itself.

Call sites: the pre-push gate (`.githooks/pre-push`); CI job `lint`.

### actionlint

actionlint checks GitHub Actions workflow files: the syntax, the expressions and the shell
scripts in the `run:` steps.

CI job `lint` runs actionlint 1.7.12, at a fixed checksum, over `.github/workflows/`.

The harness needs actionlint because GitHub reports an error in a workflow only when the workflow
runs. actionlint finds the error before the push.

Call site: CI job `lint` (`.github/workflows/test.yml`).

### timeout

`timeout` runs a command with a time limit and stops the command when the limit is reached. It is
part of GNU coreutils. macOS does not supply it.

The installed pre-commit hook runs `fatou lint` under `timeout -k 5 60`.

The harness needs `timeout` because `fatou lint` does not always stop: on one large generated
file it ran for hours. Without `timeout`, the hook runs `fatou lint` with no limit, and a commit
can wait for a long time.

Call site: the installed pre-commit hook (`githooks/pre-commit`).

### rsync

rsync copies a directory tree, with patterns for the files that it leaves out.

`run-tests.jl` and `mutate.jl` use rsync to copy a package without its `.git` directory and
without a manifest that another Julia version made. The tests of `run-tests.jl` in CI make such a
copy too.

The harness needs rsync because the copy must leave out paths by pattern, which a plain `cp`
cannot do.

Call site: `scripts/run-tests.jl`, which the Julia tests in CI call through
`scripts/run-tests-test.jl`.

### Julia

Julia is the language of the research code in the tree. The harness's tools for Julia code are
Julia scripts too: the test runner, the mutation tests, the formatter run, the workflow check and
the wiki lint.

`harness install` instantiates the Julia environment of the scripts. `harness format` and
`harness ci-protection` run Julia scripts. The installed git hooks run Julia to check the format,
the Unicode form and the load of a package before a commit, and the test suite before a push to
`main`. CI job `test` runs the Julia test files of the harness on Julia 1.13.

The harness needs Julia because a tool that reads, runs or rewrites Julia code must parse it as
Julia does. Only Julia's own parser and loader give that result.

Call sites: `harness install` (`lib/harness/install.py`), `harness format`
(`lib/harness/fmt.py`) and `harness ci-protection` (`lib/harness/protection.py`); the installed
git hooks (`githooks/pre-commit`, `githooks/pre-push`, `githooks/pre-commit-wiki`); the pre-push
gate (`.githooks/pre-push`), which skips it when it is missing, because CI job `test` runs the
Julia tests.

### ExplicitImports, JSON, JuliaFormatter, JuliaSyntax, TestEnv and YAML

These six Julia packages are the dependencies of the Julia scripts, in `Project.toml`.
`harness install --apply` installs them into the environment
`~/.local/share/research-harness/julia/`, and each script adds that environment to its load path.
ExplicitImports finds the names that a module uses without an explicit import. JSON reads and
writes JSON. JuliaFormatter formats Julia code. JuliaSyntax parses Julia code into a syntax tree.
TestEnv activates the test environment of a package. YAML reads YAML.

The scripts use them as follows. `explicit-imports.jl` uses ExplicitImports. `gate.jl`,
`mutate.jl` and `fatou-lsp.jl` use JSON for their reports and messages. `harness format` and the
installed pre-commit hook use JuliaFormatter. `mutants.jl` uses JuliaSyntax to make the mutants,
and `mutate.jl` uses it to read the names in a mutant. `run-tests.jl` and `mutate-worker.jl` use
TestEnv to run a package's test files in its test environment. `verify-workflows.jl` and
`wiki-lint.jl` use YAML to read the workflows and the frontmatter of the wiki pages.

The harness needs these packages because each does a task that Julia's standard library does not
do. A copy of their code in the harness would be larger and less correct.

Call sites: ExplicitImports, `githooks/explicit-imports.jl`; JSON, `scripts/gate.jl` and
`scripts/mutate.jl`; JuliaFormatter, `harness format` (`githooks/format-tree.jl`) and the
installed pre-commit hook (`githooks/pre-commit`); JuliaSyntax, `scripts/mutate.jl` and
`scripts/mutants.jl`; TestEnv, `scripts/run-tests.jl` and `scripts/mutate-worker.jl`; YAML,
`harness ci-protection` through `githooks/verify-workflows.jl`, and the installed wiki hook
through `scripts/wiki-lint.jl`. `harness install` instantiates all six with
`Project.toml`.

### fatou

fatou is a linter and a language server for Julia code.

The installed pre-commit hook runs `fatou lint` on the staged Julia files and prints its findings
as advice. `mutate.jl` runs `fatou lint` to reject a mutant that uses an undefined name, and
`fatou-lsp.jl` uses its language server. CI job `test` installs fatou 0.22.0 for the tests of
`mutate.jl`.

The harness needs fatou because it reports an undefined name from the source alone. Julia reports
such a name only when the code runs.

Call sites: the installed pre-commit hook (`githooks/pre-commit`); `scripts/mutate.jl`; CI job
`test` (`.github/workflows/julia.yml`).

### Kaimon

Kaimon is an MCP server that gives an agent a Julia session and tools to search and change Julia
code.

The update job `julia-update.jl` updates Kaimon, checks that it loads, and reports when its
server must restart. The oh-my-pi and OpenCode configurations hold its MCP entry.

The harness does not need Kaimon to run. Without it, the update job stops with an error, and an
agent has no Julia session and no Kaimon tools.

Call sites: the update job (`scripts/julia-update.jl`).

### juliaup

juliaup installs and updates the Julia releases, and selects a release per command.

The update job `julia-update.jl` runs `juliaup update` and finds the installed channels in the
configuration of juliaup.

The harness needs juliaup only for the update job. Without it, the job cannot update the Julia
releases.

Call site: the update job (`scripts/julia-update.jl`).

### Claude Code

Claude Code is Anthropic's [coding agent](concepts.md#coding-agent) for the terminal. It is one
of the three frontends that the harness configures.

`harness install` writes the Claude Code layer into `~/.claude/`: the agents, skills,
[rules](concepts.md#rule),
instructions, commands and hooks, and the permission settings of `~/.claude/settings.json`.
`harness skill-triggers --apply` runs `claude -p` to measure which skill loads on a query.

The harness does not need Claude Code to run. Without it, nothing reads the layer in
`~/.claude/`, and the triggering test of the skills cannot run.

Call site: `harness skill-triggers --apply` (`lib/harness/skill_triggers.py`).

### OpenCode

OpenCode is an open-source coding agent for the terminal. It is one of the three frontends that
the harness configures.

`harness install` writes the OpenCode configuration into `~/.config/opencode/`: the permission
block, the agents, the plugins and the global [instruction file](concepts.md#instruction-file).

The harness does not need OpenCode to run. Without it, nothing reads that configuration.

Call site: `harness install` (`adapters/opencode/adapter.py`).

### oh-my-pi

oh-my-pi is a coding agent for the terminal. It is one of the three frontends that the harness
configures.

`harness install` writes the oh-my-pi configuration into `~/.omp/agent/`: the permission layer,
the guard extension, the rules, the agents, the models and the MCP entry.

The harness does not need oh-my-pi to run. Without it, nothing reads that configuration.

Call site: `harness install` (`adapters/omp/adapter.py`).

### RTK

RTK (Rust Token Killer) rewrites shell commands so that their output uses fewer tokens: for
example, it replaces `cat` with its own reader.

The OpenCode plugin `rtk.ts` asks `rtk hook check` for the rewrite of each shell command.

The harness does not need RTK. Without it, the plugin passes each command unchanged, and the
output of a command is longer.

Call site: the OpenCode plugin `adapters/opencode/plugins/rtk.ts`.

### jq

jq reads and transforms JSON on the command line.

The Claude Code status line script reads the session data from JSON with jq.

The harness needs jq only for the status line. A shell script cannot parse JSON safely. jq is a
small tool: macOS supplies it, and the Linux distributions package it.

Call site: the status line script (`adapters/claude/statusline-command.sh`).

### iTerm2

iTerm2 is a terminal application for macOS. Its `cc-status` utility shows the state of a Claude
Code session in the terminal tab.

The hook `hooks/cc-status` passes each Claude Code hook event to that utility.

The harness does not need iTerm2. Without the utility, the hook does nothing and exits 0, which
blocks nothing.

Call site: `hooks/cc-status`.
