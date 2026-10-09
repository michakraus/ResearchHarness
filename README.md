# ResearchHarness

ResearchHarness configures AI coding agents for work on research software in Julia. It configures
three frontends: Claude Code, OpenCode and oh-my-pi. One set of neutral sources gives each
frontend its configuration. One command, `harness`, installs the configuration and checks it.

The harness has these features:

- **One instruction layer for three frontends.** The agents, skills, rules, commands and
  instruction files are neutral sources. `harness install` writes them into the configuration of
  Claude Code, OpenCode and oh-my-pi.
- **Permission settings and their auditor.** One settings template is the policy source of all
  three frontends. `harness settings` measures the prompt surface of the Claude Code settings and
  installs them.
- **Guard hooks.** Python hooks refuse unsafe shell commands before they run. Claude Code calls
  them, and oh-my-pi calls them through an extension. A hook at session start warns when the
  installed layer is behind its sources.
- **Git hooks and CI workflows for Julia packages.** `harness githooks` and `harness workflows`
  install the shared git hooks and GitHub workflows into every repository of a research tree.
- **Julia tools.** Scripts for tests, mutation tests and code structure, and JuliaFormatter over
  every tracked Julia file of the tree.
- **Leak checks.** A private profile holds every value that names a person, an institution or a
  machine. `harness leaks` and gitleaks keep these values and secrets out of the repository. The
  pre-push hook and CI run both checks.

## Installation

These steps install the harness on macOS. [docs/setup-macos.md](docs/setup-macos.md) gives the
details. First, install the required tools of [Dependencies](#dependencies).

1. Clone the repository. These steps use the checkout `~/Research/Harness`.

   ```bash
   git clone https://github.com/michakraus/ResearchHarness.git ~/Research/Harness
   ```

2. Put `bin/` on the `PATH`. Also add this line to your shell's start file, for example
   `~/.zshrc`.

   ```bash
   export PATH="$HOME/Research/Harness/bin:$PATH"
   ```

3. Make the private profile and the model tables from the examples.

   ```bash
   mkdir -p ~/.config/research-harness
   cp ~/Research/Harness/examples/profile.toml ~/.config/research-harness/profile.toml
   cp ~/Research/Harness/examples/models.toml ~/.config/research-harness/models.toml
   ```

4. Write your values into `~/.config/research-harness/profile.toml`. Each value replaces the
   example path `/home/example` with your home directory, for example `/Users/me`. The key
   `harness` holds the absolute path of the checkout, for example `/Users/me/Research/Harness`.
   The key `tree_agents` names the directory of your tree instructions, and each entry of
   `repository_roots` names a directory of your research tree. These directories must exist.
   With the example values, these commands make them:

   ```bash
   mkdir -p ~/Research/Environment/Agents/instructions ~/Research/Packages ~/Research/Experiments
   touch ~/Research/Environment/Agents/instructions/research-tree.md
   ```

5. Make the two directories and the settings file that the install needs on a new machine.
   Without the directories, `harness install` stops with exit 2. Without the file,
   `harness settings install` stops with exit 2.

   ```bash
   mkdir -p ~/.claude/skills ~/.config/opencode
   test -f ~/.claude/settings.json || echo '{}' > ~/.claude/settings.json
   ```

6. Install the configuration of each frontend. The first command prints the plan. The second
   command makes the change.

   ```bash
   harness install
   harness install --apply
   ```

7. Install the Claude Code settings in the same way.

   ```bash
   harness settings install
   harness settings install --apply
   ```

## Basic usage

A verb that changes something prints its plan. `--apply` makes the change. These are the daily
verbs:

- `harness install` installs the configuration of each frontend from the sources.
- `harness test` runs the harness's own test cases.
- `harness leaks` searches the repository and its renders for the leak list of the profile.
- `harness settings` measures, checks and installs the Claude Code settings.

[docs/harness-command.md](docs/harness-command.md) describes every verb, the profile and the
flags.

## Dependencies

The harness calls the tools below. A tool is required when a verb, a hook, the pre-push gate, CI
or an installed git hook calls it. An optional tool serves one frontend or one job; the `needed
by` column says what stops without it. The minimum is the floor that the code checks, that CI pins,
that `[compat]` sets or that a release note names for a feature the code uses; each floor names
its source. Where no floor exists, the cell gives the version that the harness is tested with.
[`docs/tools.md`](docs/tools.md) says what each tool does and why the harness needs it.

### Required

| tool | minimum | needed by |
|:--|:--|:--|
| Python | ≥ 3.11, the check at `bin/harness:9` | every verb (`bin/harness:1`); the pre-push gate (`.githooks/pre-push:56`, and `.githooks/pre-push:143` for `python3.11`, which the gate skips when it is missing, because CI job `python` runs Python 3.11); the guard hooks, which oh-my-pi calls (`adapters/omp/guards.ts:105`) |
| git | tested with 2.54.0 | the verbs (`lib/harness/githooks.py:75`, `lib/harness/profile.py:247`); the hook `hooks/worktree.py:50`; the pre-push gate (`.githooks/pre-push:21`) |
| gh | tested with 2.102.0 | `harness ci-protection` (`lib/harness/protection.py:102`) |
| gitleaks | ≥ 8.21, the check at `.githooks/pre-push:54` | the pre-push gate (`.githooks/pre-push:46`); CI job `leaks`, which pins 8.30.1 |
| Julia | ≥ 1.13, `[compat]` at `Project.toml:22` | `harness install` (`lib/harness/install.py:174`), `harness format` (`lib/harness/fmt.py:31`) and `harness ci-protection` (`lib/harness/protection.py:137`); the installed git hooks (`githooks/pre-commit:104`, `githooks/pre-push:50`, `githooks/pre-commit-wiki:56`); the pre-push gate (`.githooks/pre-push:204`), which skips it when it is missing, because CI job `test` runs the Julia tests |
| ExplicitImports | ≥ 1.15, `[compat]` at `Project.toml:16` | `githooks/explicit-imports.jl:28`; `harness install` instantiates it with the other packages of `Project.toml` |
| JSON | ≥ 1.10, `[compat]` at `Project.toml:17` | `scripts/gate.jl:27`, `scripts/mutate.jl:88` |
| JuliaFormatter | ≥ 2.14, `[compat]` at `Project.toml:18` | `harness format` (`githooks/format-tree.jl:37`); the installed pre-commit hook (`githooks/pre-commit:108`) |
| JuliaSyntax | ≥ 1.0.2, `[compat]` at `Project.toml:19` | `scripts/mutate.jl:90`, `scripts/mutants.jl:34` |
| TestEnv | ≥ 1.103.7, `[compat]` at `Project.toml:20` | `scripts/run-tests.jl:189`, `scripts/mutate-worker.jl:32` |
| YAML | ≥ 0.4.17, `[compat]` at `Project.toml:21` | `harness ci-protection`, through `githooks/verify-workflows.jl:43`; the installed wiki hook, through `scripts/wiki-lint.jl:104` |
| Node.js | ≥ 20.16 (20.x), ≥ 22.3, for `process.getBuiltinModule`, as the API documentation says: <https://nodejs.org/api/process.html#processgetbuiltinmoduleid> | `harness test`, whose hook probe loads the guard extensions (`hooks/probe.py:616`, `hooks/probe.py:839`) |
| shellcheck | tested with 0.11.0 | the pre-push gate (`.githooks/pre-push:154`), which skips it when it is missing, because CI job `lint` runs it |
| actionlint | ≥ 1.7.12, the CI pin at `.github/workflows/test.yml:49` | CI job `lint` |
| timeout | tested with 9.12 | the installed pre-commit hook (`githooks/pre-commit:137`), which runs `fatou lint` without a time limit when `timeout` is missing |
| fatou | ≥ 0.22.0, the CI pin at `.github/workflows/julia.yml:45` | the installed pre-commit hook (`githooks/pre-commit:135`); `scripts/mutate.jl:151`; CI job `test` |
| rsync | tested with 3.5.1 | `scripts/run-tests.jl:81`, which the Julia tests in CI call through `scripts/run-tests-test.jl` |

### Optional

| tool | minimum | needed by |
|:--|:--|:--|
| Claude Code | tested with 2.1.295 | `harness skill-triggers --apply` (`lib/harness/skill_triggers.py:188`); without it, the triggering test of the skills cannot run, and nothing reads the layer that `harness install` writes into `~/.claude/` |
| OpenCode | tested with 2.0.26 | `harness install` writes its configuration (`adapters/opencode/adapter.py:553`); without it, nothing reads that configuration |
| oh-my-pi | tested with 18.8.6 | `harness install` writes its configuration (`adapters/omp/adapter.py:108`); without it, nothing reads that configuration |
| RTK | tested with 0.51.0 | the OpenCode plugin `adapters/opencode/plugins/rtk.ts:41`; without it, the plugin passes each command unchanged |
| Kaimon | tested with 2.10.0, the `version` of its app project | the update job `scripts/julia-update.jl:123` and `scripts/julia-update.jl:126`; without it, the job stops with an error, and the agents have no Julia session |
| jq | tested with 1.7.1 | the Claude Code status line (`adapters/claude/statusline-command.sh:6`); without it, the status line shows no values |
| juliaup | tested with 1.18.9 | the update job (`scripts/julia-update.jl:105`); without it, the job cannot update the Julia releases |
| iTerm2 | tested with 3.7.3, the `CFBundleShortVersionString` of the app | the hook `hooks/cc-status:11`, which calls iTerm2's `cc-status` utility; without it, the hook does nothing and exits 0 |

The tables leave out the system tools: the POSIX shell utilities, such as `awk`, `sed`, `grep`,
`ps`, `kill`, `id` and `mktemp`; the tools that macOS supplies, `launchctl`, `security`,
`osascript`, `lsof`, `pgrep` and `tar`; and the tools of the GitHub runner that the CI jobs call,
`curl`, `tar` and `sha256sum`.

## Documentation

- [docs/setup-macos.md](docs/setup-macos.md): each step of the setup on macOS, and the check
  that it worked.
- [docs/setup-linux.md](docs/setup-linux.md): the setup on Linux, which is coming.
- [docs/daily-use.md](docs/daily-use.md): a change of a source or of the settings, the drift
  warning, the leak check, the verbs for the whole research tree and the triggering test of the
  skills.
- [docs/security.md](docs/security.md): what each security mechanism stops and does not stop,
  and the limits of the model.
- [docs/profile.md](docs/profile.md): each key of the profile and each table of the model
  tables, and the verbs that read them.
- [docs/harness-command.md](docs/harness-command.md): the contract of every verb, the profile
  and the model tables, the verbs, and the Julia environment.
- [docs/architecture.md](docs/architecture.md): the three layers and the state in `~/.claude`,
  the Claude Code layer and its stamp, the neutral vocabulary, the OpenCode and oh-my-pi
  adapters, and the layout of the repository.
- [docs/development.md](docs/development.md): the tests, the pre-push hook, the leak checks and
  CI.
- [docs/tools.md](docs/tools.md): what each dependency does, and why the harness needs it.

## License

Code: MIT (`LICENSE`). Documentation: CC BY 4.0 (`LICENSE-docs`).
