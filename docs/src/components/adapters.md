# Adapters

An adapter is the part of the harness that belongs to one frontend. The neutral sources in
`agents/`, `skills/`, `rules/`, `instructions/` and `commands/` name no frontend. Each adapter
turns them into the configuration of its frontend, and adds the files that only its frontend reads.
The sources of an adapter are below `adapters/<frontend>/`: `adapters/claude/` for Claude Code,
`adapters/opencode/` for OpenCode and `adapters/omp/` for oh-my-pi.

Each adapter has one Python module, `adapter.py`. `lib/harness/frontends.py` loads the three
modules by path, in the order Claude Code, OpenCode, oh-my-pi. Each module gives its own verbs, its
part of `harness install`, its test cases for `harness test`, and the restart line that the install
prints after a change. The other files of an adapter are instruction text, configuration and
extension code. `harness install --apply` copies or renders them into the configuration directory
of the frontend. [The architecture](../architecture.md#the-opencode-and-oh-my-pi-adapters)
describes what each frontend receives, and [the harness command](harness.md) describes the loader.

The sections follow the three frontends: first Claude Code, then OpenCode, then oh-my-pi. In each
group, the module `adapter.py` comes first, then the files that it installs.

## `claude/adapter.py`

The adapter of Claude Code. It writes the Claude Code layer of `harness install`, and it gives the
verbs `harness settings` and `harness trust`.

The layer goes into `~/.claude/`. The five neutral directories install at their own path,
`adapters/claude/` at the top, `hooks/` into `~/.claude/hooks/`, and the tree instructions at their
own path. An agent and a `SKILL.md` get two values rewritten: the tier of `model:` becomes the
model of the `[claude]` table of `models.toml`, and each `tools:` item its Claude Code name. A hook
keeps its mode, and every other file is installed with mode 0644. After the layer, the adapter
writes the stamp `~/.claude/.harness-install.json`. A path that two sources hold, a symlink, or a
source that holds `settings.json` exits 2 before anything is written. An installed file with no
source is an EXTRA line with its removal command.

`harness settings` has six sub-verbs: `surface`, `compare`, `selftest`, `twins`, `domains` and
`install`. `surface` reads the session transcripts below `~/.claude/projects/` and counts the Bash
commands that reach a prompt. `install` merges the sections `permissions`, `hooks` and `sandbox`
of the settings template into `~/.claude/settings.json`, and keeps every other key.
`harness trust` marks the research root and each git repository below it as trusted in
`~/.claude.json`. A session cannot read that file, so run it in your own terminal.

`fixtures/` holds the expected Claude Code renders of two agents, which the cases compare.

## `claude/CLAUDE.md`

The global instruction file of Claude Code. `harness install` copies it to `~/.claude/CLAUDE.md`,
and every Claude Code session reads it at the start.

Its first lines import `RTK.md`, `instructions/core.md` and `instructions/research-tree.md`, the
last from the tree instructions. The rest holds the mechanics of Claude Code only:

- the worktrees, which the `WorktreeCreate` hook makes, and `EnterWorktree` and `ExitWorktree`;
- the trust of a new clone, which needs `harness trust --apply` from the user;
- a workflow for fan-out over many repositories;
- the wait for a long command: run the command that gives the answer in the background, never a
  `sleep`;
- `git` and `gh` as the whole command, so that they run outside the sandbox;
- the sandbox as the security boundary, and the deny list as protection against accidents.

OpenCode and oh-my-pi do not read this file. They read `opencode/OPENCODE-DELTA.md` and
`omp/OMP-DELTA.md` in its place. A rule for every frontend goes into `instructions/core.md`, not
here.

## `claude/RTK.md`

The facts about RTK, a proxy that rewrites shell commands so that their output uses fewer tokens.
Under Claude Code, the `PreToolUse` hook `rtk hook claude` does the rewrite. `harness install`
copies the file to `~/.claude/RTK.md`.

The file tells the agent:

- `rtk run`, `rtk proxy`, `rtk curl` and `rtk wget` are denied;
- `rtk hook check '<cmd>'` shows whether a command is rewritten;
- in Claude Code, a pipeline or a redirection turns the rewrite off for the whole command;
- `head` and `tail` are not rewritten;
- `rtk grep` and `rtk rg` stop at a limit per file, so read the first and the last lines;
- use the `Read` tool when the exact bytes matter.

Three frontends read it. `CLAUDE.md` imports it. OpenCode lists `~/.claude/RTK.md` in the
`instructions` of `opencode.jsonc`. `OMP-DELTA.md` imports it too, but oh-my-pi runs no rewrite.

## `claude/statusline-command.sh`

The status line of Claude Code. The script reads the session data, as JSON, from its standard
input with `jq`. It prints one line: the model, the effort, the input and output tokens, and the
use of the five-hour and the weekly rate limits. A use below 50 % is green, below 80 % yellow, and
from 80 % red. The five-hour limit also shows the time until it resets.

`harness install` copies the script to `~/.claude/statusline-command.sh` and keeps its mode. The
settings template does not name the script. Point the status line setting of Claude Code at the
installed copy.

The script uses POSIX `sh`, `jq` and `date +%s` only, so it runs on macOS and Linux. Without `jq`
the line shows no values.

## `opencode/adapter.py`

The adapter of OpenCode. It writes OpenCode's part of `harness install`, and it gives the verb
`harness permissions`.

The install writes into `$OPENCODE_CONFIG_DIR`, else `~/.config/opencode`. The directory must
exist. The adapter writes:

- `opencode.jsonc`, rendered with the profile, with a backup of a file that it replaces;
- `AGENTS.md`, from `OPENCODE-DELTA.md`;
- `agents/<name>.md` for each agent of `agents/`, and the two agents of `adapters/opencode/agents/`
  that have no Claude Code source;
- the plugins `plugins/*.ts` and the rendered `plugins/guard-paths.json`;
- a link in `~/.agents/skills/` to each curated skill in `~/.claude/skills/`.

The port of an agent maps the tier through the `[opencode]` tables of `models.toml`, turns `tools:`
and `skills:` into a `permission:` block, and adds an "Under OpenCode" section before the body. A
council copies an agent onto other models. The install refuses to replace an `opencode.jsonc` that
holds a literal `Authorization` value, unless you give `--force`.

`harness permissions [--apply]` writes the permission block of `opencode.jsonc` and
`plugins/guard-paths.json` from the `ask` and `deny` rules of the settings template. Its report
shows that every rule is emitted or dropped with a reason.

`fixtures/` holds the input agents, their expected renders, a settings file, and the expected
permission block, path list and report. The cases compare the output with them.

## `opencode/opencode.jsonc`

The configuration template of OpenCode. `harness install` renders it with the profile and writes
it to `opencode.jsonc` in OpenCode's configuration directory.

It sets the default model and the model for background work. Its `instructions` list
`~/.claude/RTK.md`, `instructions/core.md` and `instructions/research-tree.md`, because OpenCode
does not follow a file reference in an instruction file. The `provider` entries come from the
profile key `opencode_providers`. The `mcp` entry connects to the Kaimon server at
`http://127.0.0.1:2828/`, which `launchagents/kaimon.plist` starts. The token comes from
`~/.config/kaimon/opencode-token` when OpenCode reads the file, so no secret is in the repository.

The `permission` block is generated. Do not edit it by hand: run `harness permissions --apply`,
which writes it from the settings template. OpenCode takes the last rule that matches, so each
`ask` comes before each `deny`. The `allow` rules of the template are not ported.

OpenCode has no sandbox. This permission block is its only control, and a command inside a string
argument escapes it.

## `opencode/OPENCODE-DELTA.md`

The global instruction file of OpenCode. `harness install` writes it as `AGENTS.md` in OpenCode's
configuration directory. There it takes the place of `~/.claude/CLAUDE.md`. The core rules,
`RTK.md` and the tree instructions load beside it through `opencode.jsonc`.

It states the facts of OpenCode:

- which rule file to read before which kind of work, because OpenCode loads no rule by itself;
- there is no sandbox, and `external_directory` is the one boundary;
- pass `workdir` and absolute paths, and do not `cd` inside a command;
- there is no session scratchpad, no worktree hook and no background run;
- the plugins `rtk.ts` and `guards.ts` take the place of the hooks;
- `opencode --auto` removes every prompt, so do not use it to push, merge or release;
- how to call the agents, and the council of critics of `build-part`.

The file loads into every session, so keep it small. `opencode.jsonc` gives its budget as 5,120
bytes.

## `opencode/plugins/env.ts`

An OpenCode plugin that sets an environment variable for every shell command. OpenCode has no
`env` key in its configuration, so the plugin sets the variable in the hook `create.before` of the
shell.

It sets `JULIA_PKG_USE_CLI_GIT=true`, as the `env` of the Claude Code settings does. Pkg then uses
the `git` program and not libgit2. It does not port `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, which has no
meaning for OpenCode.

`harness install` copies the plugin to `plugins/env.ts` in OpenCode's configuration directory. The
hook probe `hooks/probe.py` loads it under `node`, so it holds JavaScript syntax only.

## `opencode/plugins/guards.ts`

The OpenCode plugin of the guard hooks. On every `shell` call it runs four guard scripts from
`~/.claude/hooks/`: `no-blind-stage.py`, `no-shell-file-write.py`, `gh-api-writes.py` and
`rm-scope.py`. It sends Claude Code's payload on standard input and reads the answer as Claude
Code does. [The hooks](hooks.md) describes each script.

The plugin adds two checks. The path guard refuses a command that names a path of
`guard-paths.json` beside the plugin, and of `$OPENCODE_CONFIG_DIR/guard-paths.json` when it
exists. It also refuses a directory that holds a denied path when the command recurses, globs or
changes into it. A second check refuses an in-place edit, such as `sed -i`, with a short message.

The plugin fails closed. A script that cannot start, fails or times out after 10 s refuses the
command. A missing path list refuses every `shell` call. A guard that would ask refuses too, and
the model must ask the user in chat.

The path guard checks text only. A path that a command builds at run time, or a relative path,
passes it.

## `opencode/plugins/guard-paths.json`

The deny list of the path guard of `guards.ts`. It holds the `read` denies of OpenCode's permission
block: the `Read` denies of the settings template, and one deny that only OpenCode needs, its own
data directory.

`harness permissions --apply` writes the file from the settings template. Do not edit it by hand.
The paths hold `{home}`, so `harness install` renders the file with the profile and writes it to
`plugins/guard-paths.json` in OpenCode's configuration directory.

A `read` deny binds only the file tools of OpenCode. With this list, `guards.ts` refuses a shell
command that names the same path, for example a `cat` of a credential file.

The oh-my-pi adapter reads the list too. Its `deny` becomes the `deny` of oh-my-pi's path list.

## `opencode/plugins/rtk.ts`

The OpenCode plugin of RTK. RTK has no hook of its own for OpenCode, so this plugin does the
rewrite. On each `shell` call it runs `rtk hook check <command>`. Exit 0 gives the rewritten
command, which replaces the command of the call.

The plugin never fails a command. When RTK is absent, fails or takes more than 10 s, the command
runs as it is. It calls RTK at `/opt/homebrew/bin/rtk`. `harness install` warns when that file is
not executable.

The rewrite differs from the hook of Claude Code: the plugin also rewrites the first command of a
pipeline. So `grep -n p f | cat` stops at the limit of `rtk grep`. For a complete search, use the
`grep` tool.

`harness install` copies the plugin to `plugins/rtk.ts`. OpenCode runs the plugins in the order of
their names, so `guards.ts` checks a command before `rtk.ts` rewrites it.

## `omp/adapter.py`

The adapter of oh-my-pi. It writes oh-my-pi's part of `harness install` and gives no verb of its
own.

The install writes into oh-my-pi's agent directory, `$PI_CODING_AGENT_DIR`, else `~/.omp/agent`:

- `config.yml`, with the approval mode `write`, the `eval` tool denied, and the Bash rules of the
  settings template as `bash.patterns`: every `deny`, then every `ask` as `prompt`, then every
  `allow`;
- `modelRoles` in `config.yml`, from the `[omp]` table of `models.toml`;
- `extensions/guards.ts` and the path list `extensions/guard-paths.json`;
- `AGENTS.md`, from `OMP-DELTA.md`;
- `rules/<name>.md` for each rule that the Claude Code layer installs, with `paths` written as
  `globs`;
- `mcp.json`, with the Kaimon server alone;
- `agents/<name>.md` for each agent of `agents/`, with the section of `UNDER-OMP.md`.

oh-my-pi takes the first pattern that matches, so this order keeps the precedence of Claude Code.
A rule source outside the grammar of `render_rule`, or in a subdirectory of `rules/`, exits 2. A
tool that the table `TOOLS` does not map exits 2 too. An installed rule or agent with no source is
an EXTRA line. The skills need no file, because oh-my-pi reads the links in `~/.agents/skills/`.

The adapter has no `fixtures/` directory. Its cases run the install on a scratch `HOME`.

## `omp/OMP-DELTA.md`

The global instruction file of oh-my-pi. `harness install` writes it as `AGENTS.md` in oh-my-pi's
agent directory, byte for byte. Its first three lines import `~/.claude/RTK.md`,
`instructions/core.md` and `instructions/research-tree.md`.

It states the facts of oh-my-pi:

- there is no sandbox, and `bash.patterns` and the guard extension are the two controls;
- oh-my-pi runs no RTK rewrite, so a command runs as typed;
- the approval mode is `write`, and the `eval` tool is denied;
- what the guard extension refuses;
- there is no session scratchpad, no worktree hook and no background run;
- read a `CLAUDE.md` below the working directory yourself;
- read a rule through `rule://<name>` before work on a file that its globs match;
- the skills are the links in `~/.agents/skills/`.

The cases check that the file is no larger than 5,114 bytes.

## `omp/UNDER-OMP.md`

The text of the "Under oh-my-pi" section that the oh-my-pi adapter puts before the body of an
agent. The section replaces each Claude Code mechanism that the agent uses.

The file has one level-2 section for each mechanism: `intro`, `skills`, `worktree`, `agent`,
`bash` and `mcp`. `render_agent` takes `intro`, then the section of each mechanism that the agent
uses: preloaded skills, worktree isolation, the `Agent` tool, the shell tool, or a Kaimon tool. In
`skills`, `{skills}` becomes the names of the agent's skills. An agent that uses none of these
mechanisms gets no section.

Edit this file to change what every ported agent reads under oh-my-pi. A section that the adapter
needs and does not find exits 2.

## `omp/guards.ts`

The guard extension of oh-my-pi. `harness install` copies it to `extensions/guards.ts` in
oh-my-pi's agent directory. It checks each tool call that a glob of `bash.patterns` cannot check:

- `bash`: the four guard scripts of `~/.claude/hooks/`, which it runs with `python3`, and the path
  list on the words of the command and on its working directory;
- `read` and `grep`: the `deny` list on the path;
- `edit` and `write`: the `edit` list, then the `ask` list, on each path that the call names.

The path list is `guard-paths.json` beside the extension. The `deny` and `edit` lists also get
`~/.omp/**`. The match ignores case. An `ask` match and an "ask" answer of a guard refuse the
call, and tell the model to ask the user in chat.

The extension fails closed: a guard that cannot run, fails or times out blocks the call, and so
does a missing path list. It checks text only. A path that a command builds at run time passes,
and the `find` and `ast_grep` tools are not checked.
