@RTK.md

# Working rules

Two layers add to these rules, and both load only
when they apply: a directory-scoped `CLAUDE.md`, and a `~/.claude/rules/*.md` whose `paths:` match
a file you **Read**.

@instructions/core.md

@instructions/research-tree.md

## Worktrees and clones under Claude Code

**The `WorktreeCreate` hook makes every worktree.** Claude Code runs a `git worktree add` to
`~/Research/.worktrees/` sandboxed, where it cannot write `.git`, so do not run one. From a working directory inside the
repository, call `EnterWorktree` with the branch as `name`: `compat/bump` in `Example` gives
`~/Research/.worktrees/Example-compat-bump` on `compat/bump` from `origin/HEAD`. A sub-agent
gets one through `isolation: "worktree"`, detached at `origin/HEAD`, and makes its own branch with
`git switch -c`. `julia-pr-reviewer` and `julia-pr-shepherd` declare it themselves, so spawn them,
too, from a working directory inside the repository. For a PR head or a merge base, `git switch` inside the worktree once it exists.

Do not use `ExitWorktree` with `remove`: the harness cannot inspect a hook-made
worktree and asks for `discard_changes`. Leave one with `ExitWorktree` and `keep`. **An isolated
sub-agent's worktree stays after it returns**, and the caller removes it.

**A new clone under `~/Research` is untrusted until the user adds its entry.** Claude Code keys
workspace trust on the repository root, a trusted parent does not cover it, and a session cannot
write `~/.claude.json`. After a `git clone` or a `gh repo clone`, put this command in the report,
in its own `bash` block, for the user to run:
`harness trust --apply`. A worktree
uses its main checkout's trust and needs no entry.

## Workflows

For fan-out over more than a handful of repositories, use a workflow rather than hand-rolled agent
calls: `Environment/Notes/Dynamic-Workflows.md`.

## Waiting is not work. Background the answer, not a sleep.

**No tool holds a turn open.** A foreground `sleep` is blocked. `run_in_background: true` returns a
task id at once, and only the completion notification resumes the session.

**Background the command that answers the question, not a sleep in front of it**, so that
notification carries the verdict:

```bash
gh run watch <run-id> -R <owner>/Example.jl --exit-status
```

`gh` is the whole command there, which is what keeps the sandbox exclusion. Nested in a
loop it loses that and fails, and the loop reads the failure as "no checks yet" — **not `gh api`,
and never inside an `until` loop.** **Never background a bare `sleep`**: it buys nothing, because
it does not hold the turn either. Do the work that does not depend on the answer, end the turn, and
name what is still pending. **Never start two waiters for one thing.**

**A wait costs what the waiting context costs.** A sub-agent's prompt cache lives 5 minutes; its
first call after a longer pause writes the whole context again, $2.5–3.5 at 500–700 k tokens. Keep a wait of more than 5 minutes — a full suite, a docs build, a CI run — in a
small context, such as a `julia-test-runner` or the dispatcher, and never make a large context wait
on it. Measurement: `Environment/Notes/Builder-Critic-Loop.md`, *What the loop costs*.

## `git` and `gh` are the whole command

Reach another repository with a `cd <path>` call of its own, then run `git <sub> …` as the next
Bash call; the working directory persists between calls. So pass `-R <owner>/<repo>` on every
`gh` write, and read the repository in the URL it returns. A refused `cd` does not stop the next
call: the `git` runs in the previous repository. In a loop that writes, send the `cd` and the `git`
write in separate turns. **Nothing goes before `git` or `gh` on the
line**, not even `cd … &&`: the sandbox exclusion applies only when every part of a command
matches, so a `cd` in front puts `git` back in the sandbox, where it cannot write `.git`.
**`~/Research` and `~/.claude` are working directories, so commit and push there yourself**: a `cd`
into any repository in them persists, and the bare `git` after it is exempt. That covers `Tasks/`
and `~/.claude` from a session started anywhere. Claude Code withdraws the sandbox exclusion from
any `git -c`, `git -C` or `git --git-dir` command, so those forms read but never commit: `add`
fails on `.git/index.lock`. **The meta repository is the one exception**, because every command
there needs `--git-dir`; give the user its commands. The allow rules are `git <sub> *`, and the
`-C` form matches none of them, so it is not pre-approved either.

**A path argument also withdraws the exclusion** from `git init`, `git clone`, `git worktree add`,
`git worktree move` and `git bundle create`: any argument that is not a flag and starts with `/`,
`~` or `$`, or holds a `..` segment. The command then fails with `.git: Operation not permitted`,
and every other spelling of the same path fails the same way, so do not retry it. `cd <parent>` as
a call of its own, then give a relative name: `git init <name>`, `git clone <url> <name>`. A
worktree comes from `EnterWorktree`. A `--bare` or `--mirror` repository has no `.git` directory,
so it works with any path.

Mechanisms and measurements: `Environment/Notes/Git-and-GitHub.md`.

## The sandbox is the security boundary, not the deny list

`settings.json`'s `deny` list is accident-prevention, not containment: deny rules are text
patterns, and any command carried inside a string argument escapes them. What contains a command is
the OS sandbox — the filesystem and network allowlists.

- **`autoAllowBashIfSandboxed` is on and the excluded set is `git`, `gh`, `glab`, `ps`.** A
  sandboxed command is auto-approved without consulting `allow`, so an `allow` entry for anything
  else is inert. `deny` is still consulted. Those four run unsandboxed.
- **A `git` *write* needs `git` as the whole command.** After `cd … &&`, nested in `$( … )`, in a
  plain subshell or a loop body it runs sandboxed and cannot write `.git`. Reads still work, which
  hides this.
- **A `$?` refuses the whole call** before it runs, and a leading `git` does not protect it.
  Capture a status with `&& echo OK`, or run the command alone and read `Exit code N`.
- **`$TMPDIR` is one directory for every session on this machine.** A file that a later command
  reads back goes in the session scratchpad, under a name that carries its repository or task.
  Read back what you posted.
- **A failed `ps` is not evidence a process is gone.** `ps`, `pgrep`, `pkill` and `top` refuse
  together in the sandbox, and the failure reads as zero. Prefer `lsof -c <name> -t`.
- **A prompt is a real control; a deny pattern may not be.**

**Read `rtk hook check '<cmd>'` rather than any sentence about which commands are rewritten.**
Evidence and the rest: `Environment/Notes/Sandbox-and-Permissions.md`.
