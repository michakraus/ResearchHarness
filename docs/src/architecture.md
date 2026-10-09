# Architecture

## The three layers

An installation comes from three layers. `harness install` reads all three and writes the
configuration of each frontend.

| layer | where it is | what it holds |
|:--|:--|:--|
| **the harness** | this repository, public | the neutral sources of the agents, skills, rules, commands and the core instruction file; the adapters of the frontends; the guard hooks; the settings template; the git hooks, workflows and scripts |
| **the profile** | `~/.config/research-harness/`, private | `profile.toml`, every value that names a person, an institution or a machine, and `models.toml`, the model of each tier for each frontend; [profile.md](profile.md) names each key |
| **the tree instructions** | the directory that the profile key `tree_agents` names, private | instruction text about the user's own research tree, in the layout of `~/.claude/` |

The sources of the instruction layer name no person, no repository of a research tree and no
organisation. A value of that kind goes into the profile, and a template of the harness names its
key. `harness leaks` checks the repository for the private strings of the profile. A rule or a fact
about one research tree goes into the tree instructions. `adapters/claude/CLAUDE.md` imports
their `instructions/research-tree.md`, and OpenCode and oh-my-pi read that file too. So a user
adapts the harness without a change of the repository.

## The state in `~/.claude`

`~/.claude/` holds files of four kinds. Each kind has one owner.

| files | owner | how they change |
|:--|:--|:--|
| the installed layer: `CLAUDE.md`, `RTK.md`, the status line script, `agents/`, `skills/`, `rules/`, `instructions/`, `commands/` and `hooks/` | `harness install --apply`, from the harness and the tree instructions | edit the source, then install; the settings template denies an edit of an installed copy |
| the stamp `.harness-install.json` | `harness install --apply` | written after each install; the `SessionStart` hook compares it with the sources |
| the sections `permissions`, `hooks` and `sandbox` of `settings.json` | `harness settings install --apply`, from the settings template | edit the template, then install; the install keeps the other keys of the file |
| everything else: the other keys of `settings.json`, the memory and the sessions below `projects/`, the plans | Claude Code | the harness does not write them |

`~/.claude.json` belongs to Claude Code too. Only `harness trust --apply` writes it, and it
changes only the trust of each repository of the research tree. The Julia environment of the
scripts is outside `~/.claude/`, in `~/.local/share/research-harness/julia/`.

## The Claude Code layer

`harness install` also writes the Claude Code layer into `~/.claude/`, from these sources in this
repository: the five neutral directories `agents/`, `skills/`, `rules/`, `instructions/` and
`commands/`, each at its own path below `~/.claude/`; `adapters/claude/`, at the top of
`~/.claude/`; and `hooks/`, which goes to `~/.claude/hooks/`. The last source is the tree
instructions, a private directory of instruction text about the user's own tree that mirrors the
layout of `~/.claude/`; the profile key `tree_agents` names it. A file of `adapters/claude/` below
a directory that a neutral directory or `hooks/` installs exits 2.
A path that two sources hold, and an installed path that is a symlink, exit 2. The verb writes
neither `~/.claude/settings.json`, which `harness settings install` owns, nor `~/.claude.json`.
After the layer, `--apply` writes the stamp `~/.claude/.harness-install.json`: the sources
and a SHA-256 over the paths, modes and source bytes that it installs. At each session start the
`SessionStart` hook `hooks/install-drift.py` computes the same digest from the sources and warns
when the two differ, when the stamp is missing, or when a source cannot be read. It only warns,
and it exits 0. The settings template makes every installed path an `Edit` deny, so a session
edits the sources.

The neutral directories hold the public instruction layer: the agents, the skills, the rules,
the commands and `instructions/core.md`. `adapters/claude/` holds what is Claude Code's own:
`CLAUDE.md`, `RTK.md` and the status line script. None of them names a repository or an
organisation; a fact about the user's own tree goes into the tree instructions, and `CLAUDE.md`
imports their `instructions/research-tree.md`. Edit a file here, not its installed copy in
`~/.claude/`, which the next `--apply` overwrites. The OpenCode agents are rendered from
`agents/`.

## The neutral vocabulary

The `model:` and the `tools:` of an agent in `agents/` and a skill in `skills/` name no frontend.
`model:` is a tier, and each `tools:` item a neutral tool; each adapter maps them to its
frontend. A source with any other value exits 2, naming the file; so does a wildcard such as
`mcp/kaimon/*`. Every other frontmatter key keeps its name and its value, and the body keeps
Claude Code's tool names.

| neutral, in `agents/` and `skills/` | Claude Code | OpenCode | oh-my-pi |
|:--|:--|:--|:--|
| `model: large`, `medium`, `small` | the `[claude]` table: `opus`, `sonnet`, `haiku` | the `[opencode.models]` table | the `[omp]` table, as the roles `@opus`, `@sonnet`, `@haiku`; the `default` role takes the `medium` model |
| `read`, `edit`, `write`, `grep`, `glob` | `Read`, `Edit`, `Write`, `Grep`, `Glob` | `read`, `edit`, `edit`, `grep`, `glob` | `read`, `edit`, `write`, `grep`, `glob` |
| `shell` | `Bash` | `bash` | `bash` |
| `agent` | `Agent` | `task` | `task` |
| `web_search`, `web_fetch` | `WebSearch`, `WebFetch` | `websearch`, `webfetch` | `web_search`, `read` |
| `mcp/kaimon/<tool>` | `mcp__kaimon__<tool>` | `kaimon_<tool>` | `mcp__kaimon_<tool>` |

The Claude Code layer copies an agent or a skill with these two values rewritten in place and
every other byte as it is. A table of `models.toml` that names a tier by its old name, `opus`,
`sonnet` or `haiku`, exits 2 and names the rename; so does a `models.toml` without `[claude]`,
and a `[claude]` model that is not a letter followed by letters, digits and `. _ - [ ]`, or that
YAML reads as a boolean or null.

## The OpenCode and oh-my-pi adapters

OpenCode reads `adapters/opencode/OPENCODE-DELTA.md`, which `harness install` writes as `AGENTS.md` in
OpenCode's configuration directory, in place of `~/.claude/CLAUDE.md`. `RTK.md`,
`instructions/core.md` and `instructions/research-tree.md` reach it through `instructions` in
`opencode.jsonc`. `CLAUDE.md` holds the Claude Code mechanics only.

oh-my-pi gets its permission layer from the same settings template. `harness install` writes
`config.yml` into its agent directory, `$PI_CODING_AGENT_DIR`, else `~/.omp/agent`:
`tools.approvalMode: write`, the `eval` tool denied, and the template's Bash entries as
`bash.patterns`, every `deny`, then every `ask` as `prompt`, then every `allow`, since oh-my-pi
takes the first rule that matches. Beside it go `extensions/guards.ts`, from
`adapters/omp/guards.ts`, and the rendered path list `extensions/guard-paths.json`. The extension
runs four of the guard hooks on every `bash` call, `rm-scope.py` among them, the template's read
denies on `read`, `grep` and `bash`, and its Edit denies on `edit` and `write`, with `~/.omp/**`
added to both; it refuses the paths of the template's Edit asks on `edit` and `write` too, and
tells the model to ask the user in chat; it blocks the call when a guard cannot run, fails or
times out.

oh-my-pi reads the same instructions. `harness install` writes `adapters/omp/OMP-DELTA.md` as
`AGENTS.md` in its agent directory; its first lines import `~/.claude/RTK.md`,
`instructions/core.md` and `instructions/research-tree.md`, and the rest states the facts of
oh-my-pi. Each rule that the Claude Code layer installs goes to `rules/<name>.md` there, its
frontmatter written anew as `globs: <JSON list>` and `description: <JSON string>`, which YAML
reads as the source's `paths` and `description`: oh-my-pi lists it by its name, globs and
`description`. A rule source exits 2 unless its frontmatter holds only one line
`description: <text>`, not blank, and at most one line `paths: ["…", …]`, with no tab and no
whitespace at a line's edge (`render_rule` gives the grammar), and a rule source in a
subdirectory of `rules/` exits 2, as oh-my-pi reads none.
The skills need no file: oh-my-pi reads the links of `~/.agents/skills/` by default.

oh-my-pi gets the agents, the models and the MCP entry too. Each agent of `agents/` goes to
`agents/<name>.md` in its agent directory, with `name`, `description`, `tools` mapped by the table
`TOOLS` of `adapters/omp/adapter.py` (a tool it does not map exits 2), `model` the role that
`ROLES` names for the tier, `@opus`, `@sonnet` or `@haiku`, `effort` as `thinking-level`, `skills`
as `autoloadSkills`, and the body, after an "Under oh-my-pi" section from
`adapters/omp/UNDER-OMP.md` for an agent that uses a Claude Code mechanism. The `[omp]` table of
`models.toml` gives the model of each tier, `large`, `medium` and `small`; `config.yml` holds them
as those roles of `modelRoles`, and `modelRoles.default` is the `medium` model.
`mcp.json` holds Kaimon alone, over HTTP, with its token read from
`~/.config/kaimon/opencode-token` by a command when oh-my-pi connects, so that no secret is in the
file.

## Layout

The sources of the instruction layer are neutral: they belong to no one frontend. What is one
frontend's own goes below `adapters/<frontend>/`. The other top-level directories belong to no
frontend either: `hooks/` holds the guard scripts that Claude Code and oh-my-pi both call,
`settings/` the policy source of all three frontends, and the rest the tools.

| directory | holds |
|:--|:--|
| `agents/`, `skills/`, `rules/`, `instructions/`, `commands/` | the neutral sources: the agents, skills, rules, the core instruction file and the commands, which `harness install` copies into `~/.claude/` at the same path, and from which it renders the OpenCode and oh-my-pi agents and the oh-my-pi rules |
| `adapters/claude/` | Claude Code's own: `CLAUDE.md`, `RTK.md` and the status line script, which `harness install` copies to the top of `~/.claude/` |
| `adapters/opencode/` | the OpenCode configuration, plugins, global instruction file, and the agents that have no Claude Code source |
| `adapters/omp/` | the oh-my-pi guard extension, global instruction file and agent text |
| `bin/`, `lib/harness/` | the `harness` command |
| `adapters/<frontend>/adapter.py` | each frontend's part of the `harness` command, which `lib/harness/frontends.py` loads: the Claude Code layer, the settings and the trust; the generators of the OpenCode agents, permission block and skill links; the generator of oh-my-pi's `config.yml`, rules, agents and `mcp.json` |
| `hooks/` | the shared guard scripts: Claude Code `PreToolUse` hooks that refuse unsafe shell commands, which oh-my-pi's `guards.ts` calls too, the `SessionStart` hook that warns when `~/.claude/` is behind its sources, and their test cases (`probe.py`) |
| `settings/` | the permission and sandbox settings template, the policy source of all three frontends |
| `githooks/` | git hooks and GitHub Actions workflow templates for Julia packages, and their installers |
| `scripts/` | Julia test, mutation, and code-structure tools; transcript and lint tools |
| `launchagents/` | macOS launchd job templates |
| `ast-grep/`, `fatou.toml` | linter configuration |
| `agent-workflows/` | workflow scripts for fan-out over many repositories |
| `examples/` | the example profile and model tables |
| `docs/` | the pages of the documentation site in `docs/src/`, and its build, `docs/make.jl` |
