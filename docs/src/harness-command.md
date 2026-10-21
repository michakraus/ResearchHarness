# The `harness` command

`bin/harness` is the entry point of the harness. It needs Python 3.11 or later and nothing beyond
the standard library. Put `bin/` on the `PATH`, as the step *The clone*
of [setup-macos.md](setup-macos.md#the-clone) and [setup-linux.md](setup-linux.md#the-clone) shows.

Each subcommand of `harness`, such as `install` or `doctor`, keeps one contract. A subcommand
that changes something is dry by default: it prints its plan and exits 1 when something would
change, 0 when nothing would. `--apply` makes the change. Exit 2 is a usage error or a failure.
The two checks differ: `harness test` exits 1 when a test case fails, and `harness doctor` exits 1
when a check fails. `harness --profile F` names the private profile. If it is not given, the
profile is `$RESEARCH_HARNESS_PROFILE`, or `~/.config/research-harness/profile.toml` if that is
not set; `examples/profile.toml` shows every key. `harness --help` and
`harness <subcommand> --help` describe each subcommand.

`harness --models F` names the model tables. They map each model tier to its Claude Code,
OpenCode and oh-my-pi model, and an agent to its own model. If the flag is not given, the model
tables are `$RESEARCH_HARNESS_MODELS`, or `models.toml` beside the profile if that is not set;
`examples/models.toml` shows the layout.

| subcommand | does |
|:--|:--|
| `install` | installs the Julia environment of the scripts, the Claude Code layer with the sections `permissions`, `hooks`, `sandbox` and `modelSettings` of `settings.json`, the OpenCode configuration, and the oh-my-pi permission layer, instructions, rules, agents, models and MCP entry |
| `permissions` | generates the OpenCode permission block and path-guard list, from the settings template |
| `settings <sub>` | measures and checks the Claude Code settings: `surface`, `compare`, `twins`, `selftest` |
| `githooks`, `wiki-lint-hook`, `workflows` | install the shared git hooks and GitHub workflows into every repository of the research tree |
| `push-all`, `ci-protection` | push every repository ahead of its upstream; protect every default branch |
| `format` | runs JuliaFormatter over every tracked `.jl` file of the tree |
| `trust` | sets Claude Code workspace trust for every repository of the tree |
| `doctor` | checks the setup of this machine, read-only: the tools, the profile, the install and the jobs; `--full` adds `harness test` and checks that Revise loads. In the Claude Code sandbox, some checks report `SKIP`, so run it in a plain terminal |
| `render`, `get`, `leaks`, `test` | render a template with the profile, read a profile value, search for private strings, run the tool's own cases |
| `skill-triggers` | runs the skill-trigger test: whether each skill loads on the queries of `tests/skill-triggers/<skill>.toml`; `--skill <name>`, which can repeat, limits it to those skills; `--apply --model <alias>` runs one `claude -p` session of 3 turns per query, at the user's cost |

[development.md](development.md) describes the cases of `harness test`, and
[architecture.md](architecture.md) the Claude Code layer that `harness install` writes.
`harness install` warns when its checkout is behind its `origin/main`, as the last fetch saw it.
It fetches nothing, and it installs the checkout as it is.

## The Julia environment

The Julia scripts load their packages from `Project.toml`, which `harness install --apply`
instantiates in `~/.local/share/research-harness/julia/`; no caller needs `--project`.
