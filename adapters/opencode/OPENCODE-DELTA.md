# OpenCode

You are in OpenCode. This file states the facts of this harness. The core rules, `RTK.md` and the
tree instructions load beside it and describe the work; this file describes the tools.

## Read the matching rule file yourself

OpenCode loads no file of `~/.claude/rules/` by itself. Read the rule before you start that kind
of work:

| rule | before you work on |
|:--|:--|
| `julia-code.md` | any `.jl` file |
| `julia-tests.md` | a file under `test/` |
| `julia-docs.md` | `docs/make.jl`, a file under `docs/src/`, or `docs/Project.toml` |
| `changelog.md` | a `CHANGELOG.md` |
| `known-issues.md` | a `KNOWN_ISSUES.md` |
| `generated-hooks-and-workflows.md` | a git hook or a CI workflow |
| `meta-repository.md` | a directory-scoped `CLAUDE.md` |
| `instruction-files.md` | a `CLAUDE.md`, `SKILL.md`, agent or rule file |

The rule keeps the mechanism that the instructions only name: the formatter call, the Aqua
wrapper, the NFC characters with no precomposed form.

## There is no sandbox

OpenCode has no filesystem or network allowlist. The deny list in `opencode.jsonc` is the **only**
control, and a deny pattern is escaped by any command carried inside a string argument. Treat every
command as unconfined. Where a sandbox would make a mistake survivable, ask. A rule that exists
only because of Claude Code's sandbox or its permission matcher does not bind here: the
unsandboxed programs, a `git` alone on its line, no `cd … &&`, no `git -C`, no `$?`, and a failed
`ps` read as a refusal. `ps` and `pgrep` run here.

**`external_directory` is the one boundary here.** A tool that touches a path outside the workspace
root asks first; in `opencode run` it refuses. A session rooted at `/` has no such path.

**Pass `workdir`; do not `cd` inside a command, and do not write `..`.** OpenCode resolves the path
arguments of `cd`, `cat`, `cp`, `mv`, `rm`, `mkdir`, `touch`, `chmod` and `chown` against `workdir`,
not against an earlier `cd`. So `cd X && cat ../f` asks for `~`. Use absolute paths.

## There is no session scratchpad

A file that a later command reads back goes in `~/Research/.scratch/<task>/`, under a name that
carries the repository or task. `$TMPDIR` is shared by every session, so such a file never goes
there.

## Worktrees: make them yourself

There is no `WorktreeCreate` hook, no `EnterWorktree` and no `isolation: "worktree"`. Make the
worktree with `git`, at the location and from the base that the tree instructions give:

```bash
cd <repository> && git fetch origin && git worktree add -b <branch> ~/Research/.worktrees/<Repository>-<slug> origin/HEAD
```

## Nothing runs in the background

There is no `run_in_background`, `Monitor` or `Workflow`. A long command holds the turn until it
ends, so give it a `timeout` that covers it, or delegate it to `julia-test-runner`.

## Hooks are plugins

`plugins/rtk.ts` does RTK's rewrite through `rtk hook check`, which differs from Claude Code's hook:
it rewrites the first command of a pipeline too, so `grep -n p f | cat` stays at the cap of
`rtk grep`. For a whole search, use the `grep` tool. `plugins/guards.ts` runs `no-blind-stage.py`, `no-shell-file-write.py`, `gh-api-writes.py`
and `rm-scope.py` from `~/.claude/hooks/` on every `shell` tool call. A guard that would ask refuses
instead: ask the user in chat, and give the user the command. The plugin fails closed: a guard that
cannot start, exits with a status other than 0 or 2, prints output that is not JSON or times
out refuses the command, and so does a missing path list. Such a refusal names the plugin; tell
the user, and do not run the command in another form.

The same plugin's path guard refuses a `shell` command that names a path the `read` tool may not
read, such as a credential file. A refusal is final for that path: do not reach it in another
form. Change a file with the edit tool, never with `sed -i` or `perl -pi`.

## A refusal is expensive

A command that a permission rule blocks returns **the whole matching rule list**, about 6,000
tokens. Do not probe the boundary; read `opencode.jsonc`.

## `--auto` removes every prompt

`opencode --auto` approves each `ask` rule — `gh pr merge`, `gh release create` and the rest. **Do not
use it for work that pushes, merges or releases.**

## This is the one `AGENTS.md`

`harness install` writes this file as `AGENTS.md` in OpenCode's configuration directory. An
`AGENTS.md` in a directory of the tree, in any letter case, takes the place of that directory's
`CLAUDE.md` with no message. Write none.

## Agents

Every agent but `local` and `qwen-worker` is rendered from its source in `agents/` of the
harness by `harness install`. Each of those starts with an *Under OpenCode* section that replaces
the Claude Code mechanisms it uses. Its skills do not load by themselves; the section names them.

**Each agent's model is in its own frontmatter**, so a spawn passes no `model:` and names no tier.
To `SendMessage` an agent, call `task` again with the `task_id` that its first call returned.

## `build-part`: round 1 is a council of critics

Where step 3 spawns two critics, spawn the council of `julia-critic` in one message:
`julia-critic` as `Round: 1a`, and each of its council copies as `1b`, `1c`, … in the
alphabetical order of their names. A council copy is a hidden agent whose description says "The
same agent as julia-critic". Each critic runs on a different model. The `task` tool takes no
effort, so `1a` runs at the variant of `julia-critic`, and each copy at its own. Everything else
in step 3 holds for every critic: the round fails when any critic fails, its findings are the
union of the reports, and you wait for all of them. A verify round spawns `julia-critic` alone.
