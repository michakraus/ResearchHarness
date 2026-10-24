# Antigravity

You are in Antigravity. This file states the facts of this harness. The core rules, `RTK.md` and
the tree instructions load beside it as always-on rules and describe the work; this file describes
the tools.

## Two controls: the sandbox and the guard hook

The CLI `agy` runs a command in its terminal sandbox, and the permission rules of its
`settings.json` apply there; the desktop app reads no rule from that file. The guard hook
`~/.gemini/config/hooks/guard.py` runs on every tool call, in the app and in `agy`: it runs the
guard scripts on each `run_command`, refuses a path that the path list denies in any tool, and
applies the settings template's Bash denies and asks to each segment of a command. A refusal is
final for that path or command: do not reach it in another form. The hook fails closed: a guard
that cannot run refuses the call. Change a file with the edit tool, never with `sed -i` or
`perl -pi`.

A subagent shows no prompt: a call that needs one is refused there. Run such a call yourself, or
give the user the command.

## No RTK rewrite

Antigravity runs no RTK hook: a command runs as typed, so the rewrite facts of `RTK.md` do not
apply, and `grep` returns every match.

## Worktrees: make them yourself

There is no `WorktreeCreate` hook, no `EnterWorktree` and no `isolation: "worktree"`. Make the
worktree with `git worktree add`, in `~/Research/.worktrees/`, from the base that the tree
instructions give:

```bash
cd <repository> && git fetch origin && git worktree add -b <branch> ~/Research/.worktrees/<Repository>-<slug> origin/main
```

Where a text says that your caller made the worktree, read it as the worktree that you or your
caller made with this command. Report its path; your caller removes it.

## Subagents

The `Agent` tool is `invoke_subagent` here. Where a text says to `SendMessage` an agent, make a
new `invoke_subagent` call with its last report as the handoff. A subagent replies through
`send_message`. No agent sets an effort: an instruction that names an effort for a spawn does not
apply.

An agent of `~/.gemini/config/agents/` runs on the Antigravity tier that `[antigravity]` of
`models.toml` gives its tier, or its override: `inherit`, the session model, `flash`, `flash_lite`
or `pro`. A council has no seat here: round 1 of `build-part` runs two critics, each on the
session model, as under Claude Code.

## Read a directory's `CLAUDE.md` yourself

Antigravity reads `GEMINI.md` and `AGENTS.md` files, never a `CLAUDE.md`. Before you work in a
directory, read each `CLAUDE.md` on the path from `~/Research` down to it, such as
`Packages/CLAUDE.md` and `Packages/<Name>/CLAUDE.md`. Write no `GEMINI.md` or `AGENTS.md` in the
tree. `~/.claude/CLAUDE.md` does not load: this file takes its place.

## Read the matching rule yourself

The rules below are in `~/.gemini/config/rules/`, and none loads by itself. Read the rule before
you start that kind of work:

| rule | before you work on |
|:--|:--|
| `julia-code.md` | any `.jl` file |
| `julia-tests.md` | a `.jl` file under `test/` |
| `julia-docs.md` | `docs/make.jl`, a file under `docs/src/`, or `docs/Project.toml` |
| `changelog.md` | a `CHANGELOG.md` |
| `known-issues.md` | a `KNOWN_ISSUES.md` |
| `generated-hooks-and-workflows.md` | a file under `.githooks/`, `.github/workflows/` or `Harness/githooks/` |
| `meta-repository.md` | a `CLAUDE.md` |
| `instruction-files.md` | a `CLAUDE.md`, `SKILL.md`, `AGENTS.md`, or a `.md` file of an `agents/` or `rules/` directory |

The rule keeps the mechanism that the instructions only name, such as the formatter call and the
Aqua wrapper.

## Skills

The skills are Antigravity's own copies in `~/.gemini/config/skills/`. A file beside a skill's
`SKILL.md`, such as `build-part/evidence.md`, is read with the file tool. A skill runs on the
session model.

## There is no session scratchpad

A file that a later command reads back goes in `~/Research/.scratch/<task>/`, under a name that
carries the repository or task. `$TMPDIR` is shared by every session, so such a file never goes
there.
