# The `harness` command

`bin/harness` is the front door to the tooling. It needs Python 3.11 or later and nothing beyond
the standard library. Put `bin/` on the `PATH`, as
[Installation](https://github.com/michakraus/ResearchHarness#installation) shows.

Every verb keeps one contract. A verb that changes something is dry by default: it prints its
plan and exits 1 when something would change, 0 when nothing would. `--apply` makes the change.
Exit 2 is a usage error or a failure. `harness --profile F` names the private profile, else
`$RESEARCH_HARNESS_PROFILE`, else `~/.config/research-harness/profile.toml`; `examples/profile.toml`
shows every key. `harness --help` and `harness <verb> --help` describe each verb.
`harness --models F` names the model tables, which map each tier to its Claude Code, OpenCode and
oh-my-pi model, and an agent to its own OpenCode model, else `$RESEARCH_HARNESS_MODELS`, else
`models.toml` beside the profile; `examples/models.toml` shows the layout.

| verb | does |
|:--|:--|
| `install` | the Julia environment of the scripts, the OpenCode configuration, and the oh-my-pi permission layer, instructions, rules, agents, models and MCP entry |
| `permissions` | the OpenCode permission block and path-guard list, from the settings template |
| `settings <sub>` | measure (`surface`, `compare`, `twins`, `domains`, `selftest`) and `install` the Claude Code settings |
| `githooks`, `wiki-lint-hook`, `workflows` | the shared git hooks and GitHub workflows, into every repository of the research tree |
| `push-all`, `ci-protection` | push every repository ahead of its upstream; protect every default branch |
| `format` | JuliaFormatter over every tracked `.jl` file of the tree |
| `trust` | Claude Code workspace trust for every repository of the tree |
| `render`, `get`, `leaks`, `test` | render a template with the profile, read a profile value, search for personal strings, run the tool's own cases |
| `skill-triggers` | the triggering test of the skills: whether each skill loads on the queries of `tests/skill-triggers/<skill>.toml`; `--skill <name>`, which can repeat, limits it to those skills; `--apply --model <alias>` runs one `claude -p` session of 3 turns per query, at the user's cost |

[development.md](development.md) describes the cases of `harness test`, and
[architecture.md](architecture.md) the Claude Code layer that `harness install` writes.

## The Julia environment

The Julia scripts load their packages from `Project.toml`, which `harness install --apply`
instantiates in `~/.local/share/research-harness/julia/`; no caller needs `--project`.
