# Permissions

Before a tool call runs, Claude Code compares it with three lists of rules: `allow`, `ask` and
`deny`. A deny refuses the call, an ask shows you a prompt, and an allow lets it run with no
prompt. The harness writes the three lists from the settings template
`settings/settings.proposal.json`. This page gives the principle behind each list, the main groups
of rules, and how the lists reach the other frontends.

## The principle of the three lists

Most rules of the template state no reason of their own. One principle sorts them:

| list | a command goes here when it is | examples |
|:--|:--|:--|
| `allow` | local and reversible: a mistake costs a command to undo | `git status`, `git commit`, `git push origin <branch>`, read-only tools, `julia` |
| `ask` | irreversible or outward-facing: it changes what other people see, or cannot be undone | `gh pr merge`, `gh release create`, `git revert`, a remote branch deleted |
| `deny` | destructive, a sweep, a way around a gate, or a read of a secret | `git reset --hard`, `git add -A`, `sed -i`, `curl`, `gh auth token` |

Claude Code resolves the lists by category, not by order: a deny wins over an ask, and an ask wins
over an allow. So a broad allow, such as `git push origin *`, stays safe as long as the forms that
must not run, such as a forced push, have their own deny.

### Allow

The `allow` list holds the everyday commands of the work: the `git` commands of a change (`status`,
`log`, `add`, `commit`, `push origin`, `rebase`, `merge`, `branch -D`, and `worktree add` below
`~/Research/.worktrees/`), the reads of `gh` and `glab`, the writes of `gh` in your own
organisations, such as `gh pr create -R <org>/*`, the read-only tools, `julia`, and the Kaimon and
Zotero MCP tools. A rule that names `{org}` expands to one rule for each organisation of the
profile's `org` list.

**Under the sandbox, most `Bash` allows are inert.** The template sets `autoAllowBashIfSandboxed`,
so Claude Code approves every command that runs inside the sandbox without reading `allow`. An
allow matters for the commands that run outside the sandbox, `git`, `gh`, `glab` and `ps`, and for
the tools that are not shell commands.

### Ask

The `ask` list holds the steps that you decide: a merge, a release, the creation, edit or fork of
a repository, a deletion on a remote (`git push --delete`, a push of `:<ref>`), a local tag
deleted or moved (`git tag -d`, `-f`), `git revert`, the `git -C` forms of these,
`git archive -o`, the `gh issue create` forms with `-R` after other arguments and the `gh`
comments that name two repositories or a URL, and an edit of a skill that does not come from the
harness. A `gh` write outside your own organisations matches no `allow` rule and runs outside the
sandbox, so it asks too. A prompt is a real control: you see the exact call, and nothing runs
until you answer.

### Deny

The `deny` list holds the forms that are never right in a session:

- **In-place editors**: `sed -i`, `perl -pi`, `ast-grep -U`. A shell rewrite reports success
  whether it matched or not; a session edits a file with its edit tools. `fatou format` too,
  because it reformats against the repository's style.
- **Destructive commands**: `git reset --hard`, `git clean -f`, a forced or mirror push, a lease
  push to `main` or `master`, `gh repo delete`, a `gh api` DELETE, and destructive system commands.
- **Sweeps**: `git add -A`, `git commit -a`, `git commit --amend`, and the `git stash` forms that
  act on everything that changed ([Git safety](git-safety.md#staging)).
- **Ways around a gate**: `git config --global`, `git -c core.hooksPath=…`, the `-c` forms of
  `credential`, `http`, `include` and `protocol`, and `git --exec-path`.
- **The network outside the tools**: `curl`, `ssh` and `rtk curl`. A web read goes through the
  `WebFetch` tool, whose hosts `harness install` adds from `settings/network.toml` and the
  profile's overlay.
- **Self-configuration and persistence**: `claude mcp`, `launchctl` and `crontab`, which add a
  program that runs later, outside every check of the session.
- **Secrets**: `gh auth token`, and `Read` denies on the files that hold keys and tokens.
- **Installed files**: `Edit` denies on the files that `harness install` writes into `~/.claude/`,
  on the settings, on `**/.git/**`, `.githooks`, the shell's startup files and the tool installs. A
  session cannot change the rules that bind the next session.

A `Read` or `Edit` deny of a path also goes into the sandbox's read or write deny list, so it
holds for a shell command too ([Sandboxes](sandbox.md#the-session-sandbox)).

## What a rule cannot see

A rule is a text pattern. It matches the text of the command, not what the command does:

- **A command inside a string escapes it.** `sh -c '…'`, `find -exec` and `julia -e 'run(…)'`
  carry a command that no pattern of the outer command sees. The class is open, so a longer deny
  list does not close it.
- **A rule cannot see the state of the repository.** "A forced worktree removal is fine when it
  loses nothing" depends on the worktree, not on the text. Such a check is a
  [guard hook](guard-hooks.md), which runs code.
- **A rule cannot see the directory.** `git -C <path> status` does not match `Bash(git status *)`.
  `harness settings twins` prints the `git -C` twin of each plain `git` rule.

So the permission lists prevent accidents, and the [sandbox](sandbox.md) is the boundary
([The security model](security-model.md)).

## The permission modes

The template sets `defaultMode: default`, so an ask shows a prompt, and
`disableBypassPermissionsMode: disable`, so a session cannot turn the lists off. In the `auto`
mode of Claude Code, an ask goes to an auto-mode classifier, which can let the call run with no
prompt. A deny still refuses the call in every mode.

## The other frontends

The template is written for Claude Code. `harness install` renders it for each other frontend as
far as that frontend's grammar can say the same:

| frontend | gets |
|:--|:--|
| OpenCode | the `ask` and `deny` rules, as its permission block; `ask` first, because OpenCode takes the last match. The `allow` list is not ported: OpenCode allows by default, and the guard plugin checks the rest |
| oh-my-pi | the `Bash` rules of all three lists as `deny`, `prompt` and `allow` patterns, and the path list `guard-paths.json`, with `approvalMode: yolo`. Its guard extension refuses the paths of the `Edit` denies and of the `Edit` asks, which it cannot ask for, and runs the guard checks |
| Antigravity | all three lists, where its grammar can state the rule |

[`harness permissions`](../harness-command.md#permissions) regenerates the OpenCode block and the
path list from the template. [Adapters](../components/adapters.md) describes each rendering.

## Change a rule

Change the template in the harness, never the installed `~/.claude/settings.json`: the template
denies an edit of the installed file. Run `harness install` and read the diff of the section
`permissions`, then `harness install --apply`. Test each changed rule in a new session with a call
that it must stop and a call that it must let through
([The security model](security-model.md#check-a-change-of-the-settings)). `harness settings
surface` counts how many recent commands reach a prompt under a settings file, and `harness
settings compare` compares two files.
