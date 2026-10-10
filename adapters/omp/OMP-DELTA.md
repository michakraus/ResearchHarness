@~/.omp/agent/RTK.md
@~/.omp/agent/instructions/core.md
@~/.omp/agent/instructions/research-tree.md

# oh-my-pi

You are in oh-my-pi. This file states the facts of this harness. The core rules, `RTK.md` and the
tree instructions above describe the work; this file describes the tools.

## There is no sandbox

oh-my-pi has no filesystem or network allowlist. Two controls stand in its place: the
`bash.patterns` of `harness.yml`, and the guard extension. A deny pattern is escaped by any command
carried inside a string argument, so treat every command as unconfined. Where a sandbox would make
a mistake survivable, ask. A rule that exists only because of Claude Code's sandbox or its
permission matcher does not bind here: the unsandboxed programs, a `git` alone on its line, no
`cd … &&`, no `git -C`, no `$?`, and a failed `ps` read as a refusal. A compound command and a
`git -C` still cost a prompt, because an `allow` pattern matches only a whole command.

oh-my-pi runs no RTK rewrite: a command runs as typed, so the rewrite facts of `RTK.md` do not
apply, and `grep` returns every match.

The approval mode is `yolo`. Every call runs without a prompt, except a command that a `deny`
pattern refuses or a `prompt` pattern asks for; in `omp -p` a `prompt` pattern refuses. The
`eval` tool is denied: run code through `bash`.

## The guard extension

`extensions/guards.ts` runs `no-blind-stage.py`, `no-shell-file-write.py`, `gh-api-writes.py` and
`rm-scope.py` from `~/.omp/agent/hooks/` on each `bash` call. It refuses a path that the `read`
tool may not read, such as a credential file or oh-my-pi's own directory, in `read`, `grep` and
`bash`; the copies of the skills, the rules and the instructions below `~/.omp/agent/` stay
readable. It refuses an installed `~/.claude` path, `~/.omp/**` or `~/.config/**` in `edit` and
`write`. A refusal is final for
that path: do not reach it in another form. Change a file with the edit tool, never with `sed -i`
or `perl -pi`. A guard that would ask refuses instead, as does an edit of a `.githooks/`,
`.github/workflows/`, `~/.claude/skills/` or `~/.claude/workflows/` path: ask the user in chat,
and give the user the command or the change.

## There is no session scratchpad

A file that a later command reads back goes in `~/Research/.scratch/<task>/`, under a name that
carries the repository or task. `$TMPDIR` is shared by every session, so such a file never goes
there.

## Worktrees: make them yourself

There is no `WorktreeCreate` hook, no `EnterWorktree` and no `isolation: "worktree"`. Make the
worktree with `git`, at the location and from the base that the tree instructions give:

```bash
cd <repository> && git fetch origin && git worktree add -b <branch> ~/Research/.worktrees/<Repository>-<slug> origin/main
```

## Nothing runs in the background

There is no `run_in_background`, `Monitor` or `Workflow`. A long command holds the turn until it
ends, so give it a timeout that covers it.

## Read a directory's `CLAUDE.md` yourself

oh-my-pi loads a directory-scoped `CLAUDE.md` only on the path from the session's working
directory up towards the home directory, and only at the start. A session started in
`Packages/<Name>/` loads `Packages/<Name>/CLAUDE.md` and `Packages/CLAUDE.md`; a session started in
`~/Research` loads none of them. No `CLAUDE.md` below the working directory loads later, as it does
under Claude Code after a read. Before you work in a directory below the working directory, read
each `CLAUDE.md` on the path down to it.

`~/.claude/CLAUDE.md` does not load: this file takes its place.

## Read the matching rule yourself

The rules of `~/.claude/rules/` are installed as oh-my-pi rules. Each is listed by its name, its
globs and its description, and its body does not load. Before you work on a file that a rule's
globs match, read the rule through `rule://<name>`, such as `rule://julia-code` for a `.jl` file.
The rule keeps the mechanism that the instructions only name: the formatter call, the Aqua
wrapper, the NFC characters with no precomposed form.

## Skills

The skills are oh-my-pi's own copies in `~/.omp/agent/skills/`. Read a skill as `skill://<name>`,
and a file beside its `SKILL.md` as `skill://<name>/<file>`.

## Agents

**Each agent's model and thinking level are in its own frontmatter**, so a spawn names no model.
A council seat, and an agent that `models.toml` moves to another provider, needs that provider's
credentials: without them oh-my-pi runs the agent on your own model, with only a log warning.

## `build-part`: round 1 is a council of critics

Where step 3 spawns two critics, spawn the council of `julia-critic` in one message:
`julia-critic` as `Round: 1a`, and each of its council copies as `1b`, `1c`, … in the
alphabetical order of their names. A council copy is an agent whose description says "The same
agent as julia-critic". Each critic runs on a different model, at its own thinking level.
Everything else in step 3 holds for every critic: the round fails when any critic fails, its
findings are the union of the reports, and you wait for all of them. A verify round spawns one
critic alone: the council copy whose description says that it judges each verify round, else
`julia-critic`.
