# Adapting the profile

Four private files adapt the harness to one user and one machine. None of them is in the
repository. They are in `~/.config/research-harness/`, and `examples/` holds an example of each,
with a comment on every key that says what its value is.

| file | what it holds | required | its path | read by |
|:--|:--|:--|:--|:--|
| `profile.toml`, the [profile](concepts.md#profile) | every value that names a person, an institution or a machine | yes | `harness --profile F`, otherwise `$RESEARCH_HARNESS_PROFILE`, otherwise `~/.config/research-harness/profile.toml` | the subcommands that [The keys of the profile](#the-keys-of-the-profile) names for each key |
| `models.toml`, the model tables | the model of each [tier](concepts.md#tier) for each [frontend](concepts.md#frontend) | for `install` | `harness --models F`, otherwise `$RESEARCH_HARNESS_MODELS`, otherwise beside the profile | `install` only |
| [`providers.toml`](#the-providers) | the model servers and accounts of OpenCode and oh-my-pi | no | beside the profile | `install` only |
| [`network.toml`](#the-network-overlay), the network overlay | your own hosts for the network lists of Claude Code | no | beside the profile | `install`, `render` of the settings template, `settings` |

Copy each example that you need and write your values into the copy, as the step
*The profile and the model tables* of [setup-macos.md](setup-macos.md#the-profile-and-the-model-tables)
and [setup-linux.md](setup-linux.md#the-profile-and-the-model-tables) shows. A template of the
repository names a profile key as `{key}`, and a subcommand renders the template with the profile
before it uses it. A template that names a key that the profile does not have stops the
subcommand, and the message names the key.

## Read a value

`harness get` prints the value of one key, one line for each item of a list. `harness render`
prints a template rendered with the profile. Run these commands in the checkout:

```bash
harness get repository_roots
harness render launchagents/kaimon.plist
```

Both subcommands read every key that they name.

## The home directory and `~`

The key `home` is optional. Without it, `home` is the home directory of the user who runs
`harness`. A given `home` must be an absolute path without `~`; otherwise the subcommand stops,
and the message names the key. A trailing slash is removed.

A string value that is `~`, or that starts with `~/`, means `home`: `~` becomes `home`, and
`~/Research` becomes `home` followed by `/Research`. The same holds for each such item of a list.
Any other `~` stays as written, `a~b` and `~name/x` too. So `examples/profile.toml` works as
copied, on every machine.

## One profile for every machine

The template host is the machine whose Claude Code memory is the template for the other machines.
The key `autocommit_branch` names the branch of the `origin` of `~/.claude` that
`claude-autocommit` pushes to: `main` on the template host, and a branch of its own on each other
machine. The optional key `template_host` names the template host by its short host name: the
host name up to its first `.`, as `hostname -s` prints it. Without `autocommit_branch` in the
profile, its value is:

- `main` when the profile has no `template_host`;
- `main` on the machine whose short host name is `template_host`;
- `memory/<short host name>` on every other machine.

The comparison is exact, so `Alpha` and `alpha` are two machines, and an empty host name gives
`main`. A given `autocommit_branch` is the branch on every machine. A `template_host` that is
empty, holds a `.` or is not a string stops the subcommand, and the message names the key. Every
subcommand reads the same value, and `harness get autocommit_branch` prints it. So with
`template_host` and no `autocommit_branch`, one profile works unedited on every machine of one
user: write it once, keep it in a private place, and copy it to each machine.

## The keys of the profile

The table names each key of `examples/profile.toml` and the subcommands that read it, in addition
to `harness get` and `harness render`.

| key | what it holds | read by |
|:--|:--|:--|
| `home` | the home directory, an absolute path. Optional: without it, the home directory of the user who runs `harness` | `install` and `settings` |
| `harness` | the path of the checkout of this repository | `install`, in the OpenCode configuration |
| `memory_project` | a label, not a path: the settings set `autoMemoryDirectory` to `~/.claude/projects/<memory_project>/memory`, so Claude Code keeps the tree's memory there, whatever the tree's path is. The same value on every machine that shares one memory pool, such as Claude Code's name of the tree's project on the first machine (its path with each `/` replaced by `-`); it need not match the path on another machine | `install` and `settings`, in the settings template |
| `tree_agents` | the directory of the [tree instructions](concepts.md#tree-instructions) | `install`, which [installs](concepts.md#install) them into `~/.claude/` |
| `launchd_prefix` | the reverse-domain prefix of the labels of the launchd jobs in `launchagents/`, such as `org.example`: the label of the Kaimon server is `<launchd_prefix>.kaimon`. macOS only; nothing on Linux reads it | `render` of the `launchagents/` templates; `doctor`; the update job `scripts/julia-update.jl` on macOS |
| `template_host` | the short host name of the template host. Optional | every subcommand that reads the profile, for the value of `autocommit_branch` |
| `autocommit_branch` | the branch of the `origin` of `~/.claude` that `claude-autocommit` pushes to: `main` on the template host, a branch of its own on each other machine. Optional: without it, `main` on the machine of `template_host` or without `template_host`, otherwise `memory/<short host name>`, as [One profile for every machine](#one-profile-for-every-machine) says | `render` of `launchagents/claude-autocommit.plist` and `systemd/claude-autocommit.service` |
| `org` | the GitHub accounts and organisations where a [session](concepts.md#session) can open and comment on a pull request or an issue with no prompt | `install` and `settings`, in the settings template; `leaks`, which also searches for each of them |
| `repository_roots` | the directories that hold the repositories of the [research tree](concepts.md#research-tree) | `leaks`, which searches for the name of each directory below them |
| `docs_exceptions` | the repositories that keep a documentation workflow of their own | `workflows`; `ci-protection`, through `githooks/verify-workflows.jl` |
| `docs_additions` | the repositories that add steps to the canonical documentation workflow | `workflows`; `ci-protection`, through `githooks/verify-workflows.jl` |
| `protected_dir` | the directories below `home` that no session can edit, each as a path relative to `home`, such as `Nextcloud` | `install`, in the settings template and the OpenCode configuration; `settings` |
| `leak` | the strings that must never appear in the repository, such as your user name and the hosts of your institution. The item `~` stands for the path of your home directory, as each `~` of the profile does | `leaks` |
| `develop` | `true` on a machine that develops the harness: the Python environment of the harness then also holds the `dev` group of `uv.lock`, the tools that check the Python code. Optional: without it, `false`. A value that is not `true` or `false` stops every subcommand that reads the profile, and the message names the key | `install`, which syncs the environment; `doctor`, which checks it |

`install` reads the settings template too, because it writes the permission layer of oh-my-pi
from it. So each key of the settings template is a key that `install` reads.

`leaks` also renders every template of the repository, but with `examples/profile.toml`, the
home `/home/example` and the host name `example-other`, not with your profile. From your profile it reads only `leak`, `org` and
`repository_roots`.

## The tables of the model tables

An [agent](concepts.md#agent) or a [skill](concepts.md#skill) names a tier in its `model:`:
`large`, `medium` or `small`. Only `harness install` reads the model tables. It maps each tier to
the model of each frontend.

| table | what it holds | read by |
|:--|:--|:--|
| `[claude]` | the Claude Code model of each tier, written as the `model:` of the installed agent or skill; all three tiers are required | `install` |
| `[models]` | the OpenCode and oh-my-pi model of each tier, as `provider/model`; the `medium` model is also oh-my-pi's default model, in `harness.yml`, and oh-my-pi needs all three tiers | `install` |
| `[model_overrides]` | an agent whose model is not the model of its tier | `install` |
| `[model_variants]` | the [effort](concepts.md#effort) of every agent on one model: OpenCode's `variant:`, oh-my-pi's `thinking-level` | `install` |
| `[variants]` | the effort of one agent or council seat, over the effort of its model | `install` |
| `[reasoning_effort]` | the effort of one agent or council seat, for a model that has no variant for it: OpenCode's `reasoningEffort:`, oh-my-pi's `thinking-level` | `install` |
| `[councils]` | the copies of an agent on other models; one seat may add `verify = true`, and then it also judges each verify round | `install` |
| `[context_limits]` | the input tokens that a model of a built-in provider may hold: a provider entry in `opencode.jsonc`, `contextWindow` in oh-my-pi's `models.yml`. A provider of `providers.toml` stops `install` with exit status 2: its model holds the limit as `context` | `install` |
| `[opencode]`, `[omp]` | the same sub-tables, such as `[omp.models]`; each key replaces the shared key for that frontend alone | `install` |

OpenCode and oh-my-pi share every table but `[claude]` and `[antigravity]`, Antigravity's table of
the tiers, so that their agents run on the same models.

A table that names a tier by an old name, `opus`, `sonnet` or `haiku`, stops `harness install`
with exit status 2, an error, and the message names the rename.
[architecture.md](architecture.md#the-neutral-vocabulary) shows how each frontend reads a tier.

## The providers

`providers.toml` beside the profile lists, once each, the model servers and accounts that are not
built into OpenCode and oh-my-pi. `install` writes each provider into the `provider`
object of OpenCode's `opencode.jsonc` and into oh-my-pi's `models.yml`. The file is optional.
`examples/providers.toml` shows it. A table is one provider, named as `models.toml` names it in
`provider/model`.

| key | what it holds | OpenCode | oh-my-pi |
|:--|:--|:--|:--|
| `api` | `"anthropic"` or `"openai-compatible"` | `npm`: `@ai-sdk/anthropic`, `@ai-sdk/openai-compatible` | `api`: `anthropic-messages`, `openai-completions` |
| `url` | the base URL, with its `/v1` | `options.baseURL` | `baseUrl`, without the `/v1` for `"anthropic"` |
| `name` | the name that the frontend shows; optional | `name` | — |
| `key` | `{env:VAR}` or `{file:PATH}`; optional. A literal key stops `install` with exit status 2 | `options.apiKey`, as written | `apiKey`: `VAR`, or `!cat PATH` |
| `frontends` | the frontends that get the provider; optional, both by default | | |
| `[<name>.models."<id>"]` | a model: `name`, `reasoning`, and `context` with `output`, each optional | `models.<id>`: `name`, `reasoning`, `limit` | an item of `models`: `id`, `name`, `reasoning` (`false` when the model has none, so that oh-my-pi sends no effort, as OpenCode does), `contextWindow`, `maxTokens` |
| `effort` of a model | the reasoning effort that the model always gets, such as `"none"`; optional | `options.reasoningEffort` | `reasoning = true`, and in `compat` a `reasoningEffortMap` that maps each thinking level to it and `reasoningDisableMode = "none-effort"`; an agent that turns thinking off sends `"none"` |
| `opencode`, `omp` | a frontend's own keys, of a provider or of a model, merged over the rest | merged | merged |

A key that the table does not name stops `install` with exit status 2, and so does the profile key
`opencode_providers` or `omp_providers`: move its providers into `providers.toml`.

## The network overlay

The settings template names no host. `settings/network.toml` holds the hosts of the harness, and
the overlay `network.toml` beside the profile adds your own, such as the library resolver of your
institution. The overlay is optional. `examples/network.toml` shows it. Both files have the same
keys, and each key is optional in the overlay.

| key | what it holds | what the install writes |
|:--|:--|:--|
| `allow` | the hosts that the `WebFetch` tool and a sandboxed command can reach; write a host, never `*.X` | `WebFetch(domain:X)` in `permissions.allow`; `X` in `sandbox.network.allowedDomains`, and `*.X` too when `X` is its own registrable domain |
| `infrastructure` | the hosts that only a sandboxed command can reach, such as a package registry; `*.X` is allowed | `X` in `allowedDomains`, as written |
| `deny` | the hosts that neither can reach; `*`, `*.X` and `X:port` are allowed | `X` in `sandbox.network.deniedDomains`; `WebFetch(domain:X)` in `permissions.deny`, except for an entry with a port |
| `[deny_reasons]` | a reason for a `deny` entry, keyed by the exact entry | `sandbox.network.deniedDomainReasons`, which Claude Code shows the model when the [sandbox](concepts.md#sandbox) refuses the host |

`install`, `render` of the settings template and `settings` read both files. A `deny` entry of
either file removes each `allow` and `infrastructure` host that it matches from the generated
allow lists. A `deny` entry with a port leaves the host on the allow lists. The sandbox refuses a
host that no list names, with no prompt, because the template sets `strictAllowlist`. A `WebFetch`
of such a host is on no list either, so it asks in the default permission mode.

These cases stop the subcommand with exit status 2:

- an entry that is a URL;
- an entry with a port outside `deny`;
- a host in both `allow` and `deny` of one file;
- a key that the table does not name;
- the profile key `extra_domain`: move its hosts into the overlay's `allow`.

The lists apply to Claude Code only. OpenCode and oh-my-pi have no network allowlist.
