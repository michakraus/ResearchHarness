# Adapting the profile

Two private files adapt the harness to one user and one machine. Neither is in the repository.

- **The profile** holds every value that names a person, an institution or a machine. Its path is
  `harness --profile F`, else `$RESEARCH_HARNESS_PROFILE`, else
  `~/.config/research-harness/profile.toml`.
- **The model tables** hold the model of each tier for each frontend. Their path is
  `harness --models F`, else `$RESEARCH_HARNESS_MODELS`, else `models.toml` beside the profile.

`examples/profile.toml` and `examples/models.toml` show every key and every table, each with a
comment that says what the value is. Copy them and write your values into the copies, as
[setup-macos.md](setup-macos.md#the-profile-and-the-model-tables) shows. A template of the
repository names a profile key as `{key}`, and a verb renders the template with the profile
before it uses it. A template that names a key that the profile does not have stops the verb,
and the message names the key.

## Read a value

`harness get` prints the value of one key, one line for each item of a list. `harness render`
prints a template rendered with the profile. Run these commands in the checkout:

```bash
harness get repository_roots
harness render launchagents/kaimon.plist
```

Both verbs read every key that they name.

## The keys of the profile

The table names each key of `examples/profile.toml` and the verbs that read it, beside
`harness get` and `harness render`.

| key | what it holds | read by |
|:--|:--|:--|
| `home` | the home directory, an absolute path | `install` and `settings` |
| `harness` | the path of the checkout of this repository | `install`, in the OpenCode configuration |
| `memory_project` | the name of the project directory of the research tree below `~/.claude/projects/`, which holds the memory | `install` and `settings`, in the settings template |
| `tree_agents` | the directory of the tree instructions | `install`, which installs them into `~/.claude/` |
| `launchd_prefix` | the prefix of the labels of the launchd jobs in `launchagents/` | `render` of the `launchagents/` templates; the update job `scripts/julia-update.jl` |
| `org` | the GitHub accounts and organisations where a session can open and comment on a pull request or an issue with no prompt | `install` and `settings`, in the settings template; `leaks`, which also searches for each of them |
| `repository_roots` | the directories that hold the repositories of the research tree | `leaks`, which searches for the name of each directory below them |
| `docs_exceptions` | the repositories that keep a documentation workflow of their own | `workflows`; `ci-protection`, through `githooks/verify-workflows.jl` |
| `docs_additions` | the repositories that add steps to the canonical documentation workflow | `workflows`; `ci-protection`, through `githooks/verify-workflows.jl` |
| `extra_domain` | the hosts beyond the template's list that `WebFetch` and a sandboxed command can reach | `install` and `settings`, in the settings template |
| `protected_dir` | the directories below `home` that no session can edit | `install`, in the settings template and the OpenCode configuration; `settings` |
| `opencode_providers` | the model servers of OpenCode beyond its own providers, as lines of JSONC | `install`, in the OpenCode configuration |
| `leak` | the strings that must never appear in the repository | `leaks` |

`install` reads the settings template too, because it writes the permission layer of oh-my-pi
from it. So each key of the settings template is a key that `install` reads.

`leaks` also renders every template of the repository, but with `examples/profile.toml`, not
with your profile. From your profile it reads only `leak`, `org` and `repository_roots`.

## The tables of the model tables

An agent or a skill names a tier in its `model:`: `large`, `medium` or `small`. Only
`harness install` reads the model tables. It maps each tier to the model of each frontend.

| table | what it holds | read by |
|:--|:--|:--|
| `[claude]` | the Claude Code model of each tier, written as the `model:` of the installed agent or skill; all three tiers are required | `install` |
| `[opencode]` | the tables of OpenCode below | `install` |
| `[opencode.models]` | the OpenCode model of each tier | `install` |
| `[opencode.model_overrides]` | an agent whose OpenCode model is not the model of its tier | `install` |
| `[opencode.model_variants]` | the `variant:` of every agent on one model | `install` |
| `[opencode.variants]` | the `variant:` of one agent, over the variant of its model | `install` |
| `[opencode.reasoning_effort]` | the `reasoningEffort:` of one agent | `install` |
| `[opencode.councils]` | the copies of an agent on other models | `install` |
| `[omp]` | the oh-my-pi model of each tier, written to `config.yml` as a role; `medium` is also the default model; all three tiers are required | `install` |

A table that names a tier by an old name, `opus`, `sonnet` or `haiku`, stops `harness install`
with exit 2 and names the rename. [architecture.md](architecture.md#the-neutral-vocabulary)
shows how each frontend reads a tier.
