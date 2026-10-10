# The tools

This page describes each tool of the dependency tables in the README: what the tool does, what
the harness uses it for, why the harness needs it, and where the harness calls it. The sections
follow the order of the tables. The required tools come first, then the optional tools.

## Python

Python is the language of the `harness` command, the guard hooks and the hook probe. The
command uses the standard library only, so no package must be installed.

Every verb runs on Python. The pre-push gate runs `bin/harness test` on `python3` and on
`python3.11`, and CI runs it on Python 3.11 and the latest 3.x. The guard hooks are Python
scripts, which Claude Code, OpenCode and oh-my-pi call before a tool call.

The harness needs Python 3.11 or later because the profile and the model tables are TOML, and
`tomllib` is in the standard library from 3.11. A shell script cannot parse TOML or JSON safely,
and a compiled tool needs a build step on each machine.

Call sites: every verb (`bin/harness:1`); the pre-push gate (`.githooks/pre-push:56`, and
`.githooks/pre-push:143` for `python3.11`, which the gate skips when it is missing, because CI job
`python` runs Python 3.11); the guard hooks, which oh-my-pi calls (`adapters/omp/guards.ts:105`).

## git

git is the version control system. Each repository of the research tree is a git repository.

The verbs that work across the tree use git: `harness githooks` reads each repository's
configuration, `harness push-all` pushes each repository, and `harness leaks --commits` reads the
commits of a push. The hook `hooks/worktree.py` makes the worktrees of Claude Code, and the
pre-push gate clones the pushed commit and tests it.

The harness needs git because its work is on git repositories: the hooks, the commits and the
pushes are git's own objects. No other tool reads them.

Call sites: the verbs (`lib/harness/githooks.py:75`, `lib/harness/profile.py:247`); the hook
`hooks/worktree.py:50`; the pre-push gate (`.githooks/pre-push:21`).

## gh

gh is the command-line client of GitHub. It calls the GitHub API with the credentials of the
user.

`harness ci-protection` calls `gh api` to protect the default branch of each repository on GitHub.

The harness needs gh because branch protection is a setting on GitHub, which only the API
changes. gh holds the user's credentials, so the harness stores no token of its own.

Call site: `harness ci-protection` (`lib/harness/protection.py:102`).

## gitleaks

gitleaks finds secrets in text: tokens, keys and other values with a known shape. It reads a
directory, the commits of a git repository, or standard input.

The pre-push gate runs gitleaks over the commits that a push sends, over their messages and over
the tree of the pushed commit. The CI job `leaks` does the same with gitleaks 8.30.1 at a fixed
checksum. The configuration `.gitleaks.toml` adds a rule for home paths.

The harness needs gitleaks because the repository is public, and a leak is permanent once it is
pushed. The rules of gitleaks for known secret shapes are maintained upstream; the harness's own
`harness leaks` finds only the private strings of the profile. Version 8.19 added the `git`, `dir`
and `stdin` commands
([release note](https://github.com/gitleaks/gitleaks/releases/tag/v8.19.0)). Version 8.21 is the
first with several allowlists per rule, `[[rules.allowlists]]`, which `.gitleaks.toml` uses
([release note](https://github.com/gitleaks/gitleaks/releases/tag/v8.21.0)).

Call sites: the pre-push gate (`.githooks/pre-push:46`); CI job `leaks`, which pins 8.30.1.

## Julia

Julia is the language of the research code in the tree. The harness's tools for Julia code are
Julia scripts too: the test runner, the mutation tests, the formatter run, the workflow check and
the wiki lint.

`harness install` instantiates the Julia environment of the scripts. `harness format` and
`harness ci-protection` run Julia scripts. The installed git hooks run Julia to check the format,
the Unicode form and the load of a package before a commit, and the test suite before a push to
`main`. CI job `test` runs the Julia test files of the harness on Julia 1.13.

The harness needs Julia because a tool that reads, runs or rewrites Julia code must parse it as
Julia does. Only Julia's own parser and loader give that result.

Call sites: `harness install` (`lib/harness/install.py:174`), `harness format`
(`lib/harness/fmt.py:31`) and `harness ci-protection` (`lib/harness/protection.py:137`); the
installed git hooks (`githooks/pre-commit:104`, `githooks/pre-push:50`,
`githooks/pre-commit-wiki:56`); the pre-push gate (`.githooks/pre-push:204`), which skips it when
it is missing, because CI job `test` runs the Julia tests.

## ExplicitImports, JSON, JuliaFormatter, JuliaSyntax, TestEnv and YAML

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

Call sites: ExplicitImports, `githooks/explicit-imports.jl:28`; JSON, `scripts/gate.jl:27` and
`scripts/mutate.jl:88`; JuliaFormatter, `harness format` (`githooks/format-tree.jl:37`) and the
installed pre-commit hook (`githooks/pre-commit:108`); JuliaSyntax, `scripts/mutate.jl:90` and
`scripts/mutants.jl:34`; TestEnv, `scripts/run-tests.jl:189` and `scripts/mutate-worker.jl:32`;
YAML, `harness ci-protection` through `githooks/verify-workflows.jl:43`, and the installed wiki
hook through `scripts/wiki-lint.jl:104`. `harness install` instantiates all six with
`Project.toml`.

## Node.js

Node.js runs JavaScript outside a browser.

`harness test` runs the hook probe, which loads the guard extension of oh-my-pi and the OpenCode
plugins under Node.js and checks their decisions. A missing `node` is a wrong case of the probe.

The harness needs Node.js because these extensions are JavaScript, and their frontends run them
in a JavaScript runtime. The plugins take the Node.js built-in modules from
`process.getBuiltinModule`, which Node.js 22.3 and 20.16 added.

The documentation site is a VitePress project, and its build runs under Node.js too: `npm`
installs the packages that `docs/package-lock.json` pins, and VitePress builds the site and draws
the call graphs. Only the docs build needs these packages; the harness itself does not.

Call sites: the hook probe of `harness test` (`hooks/probe.py:616`, `hooks/probe.py:839`); the
docs build (`docs/package.json`, `.github/workflows/docs.yml`).

## shellcheck

shellcheck finds errors in shell scripts: a missing quote, an unset variable, a construct that
does not work in the given shell.

The pre-push gate and CI job `lint` run `shellcheck -S warning` over each tracked file with a sh
or bash shebang: the git hooks, the hook `hooks/cc-status` and the status line script. The gate
skips shellcheck when it is missing, because CI runs it.

The harness needs shellcheck because the git hooks run in every repository of the tree, and an
error in a hook can let a commit through unchecked. The shell does not report most of these
errors itself.

Call sites: the pre-push gate (`.githooks/pre-push:154`); CI job `lint`.

## actionlint

actionlint checks GitHub Actions workflow files: the syntax, the expressions and the shell
scripts in the `run:` steps.

CI job `lint` runs actionlint 1.7.12, at a fixed checksum, over `.github/workflows/`.

The harness needs actionlint because GitHub reports an error in a workflow only when the workflow
runs. actionlint finds the error before the push.

Call site: CI job `lint` (`.github/workflows/test.yml:49`).

## timeout

`timeout` runs a command with a time limit and stops the command when the limit is reached. It is
part of GNU coreutils. macOS does not supply it.

The installed pre-commit hook runs `fatou lint` under `timeout -k 5 60`.

The harness needs `timeout` because `fatou lint` does not always stop: on one large generated
file it ran for hours. Without `timeout`, the hook runs `fatou lint` with no limit, and a commit
can wait for a long time.

Call site: the installed pre-commit hook (`githooks/pre-commit:137`).

## fatou

fatou is a linter and a language server for Julia code.

The installed pre-commit hook runs `fatou lint` on the staged Julia files and prints its findings
as advice. `mutate.jl` runs `fatou lint` to reject a mutant that uses an undefined name, and
`fatou-lsp.jl` uses its language server. CI job `test` installs fatou 0.22.0 for the tests of
`mutate.jl`.

The harness needs fatou because it reports an undefined name from the source alone. Julia reports
such a name only when the code runs.

Call sites: the installed pre-commit hook (`githooks/pre-commit:135`); `scripts/mutate.jl:151`;
CI job `test` (`.github/workflows/julia.yml:45`).

## rsync

rsync copies a directory tree, with rules for the files that it leaves out.

`run-tests.jl` and `mutate.jl` use rsync to copy a package without its `.git` directory and
without a manifest that another Julia version made. The tests of `run-tests.jl` in CI make such a
copy too.

The harness needs rsync because the copy must leave out paths by pattern, which a plain `cp`
cannot do.

Call site: `scripts/run-tests.jl:81`, which the Julia tests in CI call through
`scripts/run-tests-test.jl`.

## Claude Code

Claude Code is Anthropic's coding agent for the terminal. It is one of the three frontends that
the harness configures.

`harness install` writes the Claude Code layer into `~/.claude/`: the agents, skills, rules,
instructions, commands and hooks. `harness settings` writes its permission settings.
`harness skill-triggers --apply` runs `claude -p` to measure which skill loads on a query.

The harness does not need Claude Code to run. Without it, nothing reads the layer in
`~/.claude/`, and the triggering test of the skills cannot run.

Call site: `harness skill-triggers --apply` (`lib/harness/skill_triggers.py:188`).

## OpenCode

OpenCode is an open-source coding agent for the terminal. It is one of the three frontends that
the harness configures.

`harness install` writes the OpenCode configuration into `~/.config/opencode/`: the permission
block, the agents, the plugins and the global instruction file.

The harness does not need OpenCode to run. Without it, nothing reads that configuration.

Call site: `harness install` (`adapters/opencode/adapter.py:553`).

## oh-my-pi

oh-my-pi is a coding agent for the terminal. It is one of the three frontends that the harness
configures.

`harness install` writes the oh-my-pi configuration into `~/.omp/agent/`: the permission layer,
the guard extension, the rules, the agents, the models and the MCP entry.

The harness does not need oh-my-pi to run. Without it, nothing reads that configuration.

Call site: `harness install` (`adapters/omp/adapter.py:108`).

## RTK

RTK (Rust Token Killer) rewrites shell commands so that their output uses fewer tokens: for
example, it replaces `cat` with its own reader.

The OpenCode plugin `rtk.ts` asks `rtk hook check` for the rewrite of each shell command.

The harness does not need RTK. Without it, the plugin passes each command unchanged, and the
output of a command is longer.

Call site: the OpenCode plugin `adapters/opencode/plugins/rtk.ts:41`.

## Kaimon

Kaimon is an MCP server that gives an agent a Julia session and tools to search and change Julia
code.

The update job `julia-update.jl` updates Kaimon, checks that it loads, and reports when its
server must restart. The oh-my-pi and OpenCode configurations hold its MCP entry.

The harness does not need Kaimon to run. Without it, the update job stops with an error, and an
agent has no Julia session and no Kaimon tools.

Call sites: the update job (`scripts/julia-update.jl:123`, `scripts/julia-update.jl:126`).

## jq

jq reads and transforms JSON on the command line.

The Claude Code status line script reads the session data from JSON with jq.

The harness needs jq only for the status line. A shell script cannot parse JSON safely. jq is a
small tool: macOS supplies it, and the Linux distributions package it.

Call site: the status line script (`adapters/claude/statusline-command.sh:6`).

## juliaup

juliaup installs and updates the Julia releases, and selects a release per command.

The update job `julia-update.jl` runs `juliaup update` and finds the installed channels in the
configuration of juliaup.

The harness needs juliaup only for the update job. Without it, the job cannot update the Julia
releases.

Call site: the update job (`scripts/julia-update.jl:105`).

## iTerm2

iTerm2 is a terminal application for macOS. Its `cc-status` utility shows the state of a Claude
Code session in the terminal tab.

The hook `hooks/cc-status` passes each Claude Code hook event to that utility.

The harness does not need iTerm2. Without the utility, the hook does nothing and exits 0.

Call site: `hooks/cc-status:11`.
