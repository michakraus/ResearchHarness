# Guard hooks

A hook is a program that the frontend runs at a fixed event, for example before a tool call or
at the start of a session. The frontend sends the event as JSON on standard input. A `PreToolUse`
hook runs before a tool call and can refuse it: exit 2 refuses the call and shows the hook's
standard error to the model, and an `ask` decision on standard output shows a prompt to the user.
The hooks of this page use the Claude Code events `PreToolUse`, `SessionStart`,
`PermissionRequest`, `WorktreeCreate` and `WorktreeRemove`. `cc-status` also runs on the other
events of a session.

The sources are in `hooks/`. `harness install --apply` copies them to `~/.claude/hooks/`.
Claude Code calls them through the `hooks` section of its settings, which
`harness settings install --apply` writes from `settings/settings.proposal.json`. oh-my-pi calls
four of them through its guard extension `adapters/omp/guards.ts`, and OpenCode calls the same
four through its plugin `adapters/opencode/plugins/guards.ts`. Both run the scripts from
`~/.claude/hooks/`, so each hook has one source. `hooks/probe.py` holds the test cases of the
hooks, and `harness test` runs it.

The hooks prevent accidents. They are not a security boundary: each one reads the text of a
command. [The security model](../security.md) says what they stop and what they do not stop. The
page groups the hooks: first the five shell guards, then the hooks of the directory and worktree
tools, then the session hooks, and last the probe.

## `no-blind-stage.py`

This hook refuses a `git add` that stages more than the paths it names. Claude Code runs it as a
`PreToolUse` hook on the `Bash` matcher. oh-my-pi and OpenCode run it on each shell call.

It reads the command, splits it into segments, and finds each `git add`. It exits 2 on `-A`,
`-u`, `--all`, `--update`, `--no-ignore-removal`, a short-flag cluster that holds `A` or `u`, and
the pathspecs `.`, `./` and `:/`. The flag cluster is the reason for the hook: a deny glob cannot
match `git add -nA` without also matching a file name that holds an `A`. The refusal tells the
model to stage its paths by name.

It fails open: an input that it cannot read exits 0. The deny list of the settings still refuses
the common spellings. Test it without an install:

```bash
echo '{"tool_input":{"command":"git add -nA"}}' | ./no-blind-stage.py ; echo "exit $?"
```

## `no-shell-file-write.py`

This hook refuses a shell command that writes a file in a git working tree. Claude Code runs it as
a `PreToolUse` hook on the `Bash` matcher. oh-my-pi and OpenCode run it on each shell call.

It exits 2 on a redirection such as `>` or `>>`, on `tee`, on an in-place flag of `sed`, `perl`
or `awk`, and on a `python3 -c` or a Python heredoc that opens a file to write. It resolves each
target against the working directory and each `cd` of the command. A target under a scratch
directory passes: `$TMPDIR`, `/tmp/`, `/private/tmp/`, `/var/folders/`, `/dev/` or
`~/Research/.scratch/`. In a git working tree, every file is refused unless git ignores it.
Outside one, only a file with a source suffix such as `.jl` or `.md` is refused. A quoted `>` is
text, not a redirection. The refusal tells the model to use the `Edit` and `Write` tools.

It fails open. It does not see a target that the shell computes, a Julia one-liner, or a writer
inside a string argument such as `perl -e`. Test it without an install:

```bash
echo '{"tool_input":{"command":"echo x > src/Foo.jl"},"cwd":"/path/in/a/repo"}' | ./no-shell-file-write.py
```

## `sandbox-semantics.py`

This hook refuses a command whose shape makes the Claude Code sandbox give a false result. Claude
Code runs it as a `PreToolUse` hook on the `Bash` matcher. oh-my-pi and OpenCode do not run it.

The settings let a command run outside the sandbox only when every part of it starts with `git`,
`gh`, `glab` or `ps` and no part redirects a file. A sandboxed `gh` cannot reach the network, and
a sandboxed `git` cannot write `.git`. The failure then reads as a negative result or as a
certificate fault. The hook exits 2 on four shapes:

- a `gh`, `glab` or `git` write inside `$( … )`, backticks or a loop;
- a top-level `gh`, `glab` or `git` write in a command that is not exempt, for example after
  `cd other &&`, or a `gh` command that holds a backtick or `$(`;
- a `$?` in a command that runs sandboxed;
- a path argument of `git init`, `git clone`, `git worktree add`, `git worktree move` or
  `git bundle create` that starts with `/`, `~` or `$`, or holds `..`.

Each refusal gives the form that works, for example a separate Bash call. It fails open. Test it:

```bash
echo '{"tool_input":{"command":"echo $(gh run view 1)"}}' | ./sandbox-semantics.py ; echo "exit $?"
```

## `gh-api-writes.py`

This hook asks before a `gh api` write that is not a review or a comment, and refuses a remote
delete. Claude Code runs it as a `PreToolUse` hook on the `Bash` matcher. oh-my-pi and OpenCode
run it on each shell call.

It finds each top-level `gh api` and `glab api` call and works out the HTTP method as `gh` does:
`-X` or `--method`, else POST when a body flag is present, else GET. A GET, a HEAD and a
`search/…` endpoint pass. A DELETE from `gh api` or `glab api` exits 2. Any other `glab api` call
passes. A review, an inline comment, a reply, and a comment on a pull request, an issue or a
commit pass, so the review agents can post. A GraphQL query passes when it holds no mutation, or
when each mutation is a review or comment operation. Every other write gets an `ask` decision,
and the user sees a prompt. The edit of an existing comment asks too.

It fails open. Test it:

```bash
echo '{"tool_input":{"command":"gh api repos/o/r/hooks -f url=x"}}' | ./gh-api-writes.py
```

## `rm-scope.py`

This hook refuses a recursive `rm` outside the scratch zones, and asks before a `git rm` outside a
worktree. Claude Code runs it as a `PreToolUse` hook on the `Bash` matcher. oh-my-pi and OpenCode
run it on each shell call.

It follows the working directory through each `cd` and resolves each operand. A recursive `rm`
passes when every operand is strictly below a worktree, `~/Research/.worktrees/<name>/`, or
strictly below `~/Research/.scratch/`. It exits 2 for a recursive `rm` of `/`, of the users'
directory, or of any path below it. So a worktree itself goes through `git worktree remove`. A
plain `rm`, and an operand that it cannot resolve, get no decision. A `git rm` gets an `ask`
decision outside a worktree, with `-f` or `--force`, or with `-C`, `--git-dir` or `--work-tree`.

It fails closed to a prompt: a command that holds `rm` and that it cannot read gets `ask`. Test
it:

```bash
echo '{"tool_input":{"command":"rm -rf ../x"},"cwd":"/Users/me/Research/Packages/A"}' | ./rm-scope.py
```

## `directory-scope.py`

This hook asks before a session leaves `~/Research`, or removes a worktree. Claude Code runs it as
a `PreToolUse` hook on the matcher `mcp__ccd_directory__.*|EnterWorktree|ExitWorktree`: the
app's `change_directory` and `request_directory` tools, and the two worktree tools. The settings
allow these tools, and the hook takes the unsafe calls back out of that allow.

A call with a `path` passes when the path resolves inside `~/Research`, after `~`, `..` and
symlinks. An `EnterWorktree` with a `name` only passes, because `worktree.py` then decides the
place. An `ExitWorktree` passes only with `action: "keep"` and no `discard_changes`. Every other
call gets an `ask` decision: a path outside `~/Research`, a relative or missing path, a removal,
and an input that the hook cannot read. So it fails closed to a prompt. Test it:

```bash
echo '{"tool_input":{"path":"~/Research/Packages"}}' | ./directory-scope.py
```

## `worktree.py`

This hook makes and removes the worktrees of Claude Code. Claude Code runs it on the events
`WorktreeCreate` and `WorktreeRemove`. The reason is the sandbox: a `git worktree add` to a path
below `~/Research/.worktrees/` runs sandboxed, where it cannot write `.git`.

On `WorktreeCreate` it fetches `origin` in the repository that holds `cwd`. It then makes
`~/Research/.worktrees/<Repository>-<slug>` on the branch `name`, from `origin/HEAD`, else
`origin/main`. It prints the path on standard output. An existing branch is checked out, and an
existing worktree of the repository is printed as it is. A name `agent-<hex>`, from a sub-agent,
gets a detached worktree with no branch. The hook copies the main checkout's `Manifest.toml` into
the new worktree. On `WorktreeRemove` it runs `git worktree remove` without `--force`, so git
refuses a worktree with changes, and the branch stays.

It fails closed: each error exits 1 with the reason, and no worktree is made. Test it:

```bash
echo '{"hook_event_name":"WorktreeCreate","cwd":"/","name":"x"}' | ./worktree.py ; echo "exit $?"
```

## `install-drift.py`

This hook warns when `~/.claude/` is behind the sources that `harness install` installs. Claude
Code runs it on the event `SessionStart`.

`harness install --apply` writes the stamp `~/.claude/.harness-install.json`. The stamp holds the
sources and a SHA-256 digest over the installed paths, their modes and the source bytes. The hook
computes the same digest from the sources and compares the two. It warns when they differ, when
the stamp is missing or cannot be read, and when a source cannot be read. The warning goes to
the user and to the session, and it names the command to run. It does not run
`harness install`, and an edit of the models table is no drift.

It only warns: it blocks nothing and exits 0 for each input.
[Daily use](../daily-use.md#the-drift-warning-at-session-start) says what to do when the warning
appears.

## `prompt-log.py`

This hook writes one JSON line for each permission dialog to
`~/.claude/logs/permission-requests.jsonl`. The environment variable `LOG` names another file.
Claude Code runs it on the event `PermissionRequest`, for every tool, just before it shows the
dialog.

Each line holds the time, the session, the working directory, the permission mode, the tool and
its input. It cuts each string of the input to 400 characters, so a `Write` call does not log the
whole file. The log shows which prompts a person still answers, by tool, by command and by mode.
The transcript does not show this.

It decides nothing and prints nothing, so the dialog appears as it does without the hook. Each
path exits 0, also when the hook cannot read the input or write the log. Test it:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | LOG=$TMPDIR/p.jsonl ./prompt-log.py
```

## `cc-status`

This shell script passes each Claude Code hook event to the `cc-status` utility of iTerm2, which
shows the state of the session in its tab. Claude Code runs it on the events `SessionStart`,
`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, `Notification`, `Stop`,
`StopFailure`, `SubagentStop` and `SessionEnd`.

It hands its standard input and its arguments to `~/.config/iterm2/cc-status` unchanged. When
that utility is not there, it exits 0 and does nothing. So one settings file serves a machine with
iTerm2 and a machine without it. It guards nothing. [Dependencies](../dependencies.md#iterm2) says more about
iTerm2.

## `probe.py`

This script holds the test cases of the hooks and runs them. `harness test` runs it after the own
cases of each module; [Development](../development.md#tests) describes the run.

A case is a script, an input and the expected result. The probe runs each case in its own
process, with a timeout, and prints one line per case: `ok` or `BAD`, the expected and the actual
result. The last line gives the number of cases and the number wrong, and the exit status is 1
when any case is wrong. It covers each Python hook of this page, the fail-open cases of the shell
guards, the fail-closed cases of `worktree.py`, and the drift cases of `install-drift.py`. It also
loads `adapters/omp/guards.ts` and the OpenCode plugins under `node`, so `node` must be on `PATH`.
The hooks run against a fixture `HOME` in a temporary directory, never the real one. Run it alone:

```bash
./probe.py
```
