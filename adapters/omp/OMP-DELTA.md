@~/.claude/RTK.md
@~/.claude/instructions/core.md
@~/.claude/instructions/research-tree.md

# oh-my-pi

You are in oh-my-pi. This file states the facts of this harness. The core rules, `RTK.md` and the
tree instructions above describe the work; this file describes the tools.

## There is no sandbox

oh-my-pi has no filesystem or network allowlist. Two controls stand in its place: the
`bash.patterns` of `config.yml`, and the guard extension. A deny pattern is escaped by any command
carried inside a string argument, so treat every command as unconfined. Where a sandbox would make
a mistake survivable, ask. A rule that exists only because of Claude Code's sandbox or its
permission matcher does not bind here: the unsandboxed programs, a `git` alone on its line, no
`cd … &&`, no `git -C`, no `$?`, and a failed `ps` read as a refusal. A compound command and a
`git -C` still cost a prompt, because an `allow` pattern matches only a whole command.

oh-my-pi runs no RTK rewrite: a command runs as typed, so the rewrite facts of `RTK.md` do not
apply, and `grep` returns every match.

The approval mode is `write`. A read or an edit runs; a command that no pattern allows asks, and
in `omp -p` it is refused. The `eval` tool is denied: run code through `bash`.

## The guard extension

`extensions/guards.ts` runs `no-blind-stage.py`, `no-shell-file-write.py`, `gh-api-writes.py` and
`rm-scope.py` from `~/.claude/hooks/` on each `bash` call. It refuses a path that the `read` tool
may not read, such as a credential file or oh-my-pi's own directory, in `read`, `grep` and `bash`,
and an installed `~/.claude` path or `~/.config/**` in `edit` and `write`. A refusal is final for
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

The skills are the links in `~/.agents/skills/`, which oh-my-pi reads by default.
