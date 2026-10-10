# The security model

The harness gives an agent session several layers of control. Only one of them is a security
boundary: the OS sandbox of Claude Code. The other layers prevent accidents. They stop the
common mistake and tell the session what to do in its place, but a session that tries to get
past them can do so.

`harness settings install` writes the sandbox, the permission lists and the hooks from the
settings template `settings/settings.proposal.json` into `~/.claude/settings.json`.
[setup-macos.md](setup-macos.md#harness-settings-install-apply) gives the steps.

## The mechanisms

Each row states the behaviour of the Claude Code version in the last column, in a session with
the installed template. A later version can behave differently.

| mechanism | what it stops | what it does not stop | Claude Code version |
|:--|:--|:--|:--|
| **The OS sandbox**, the `sandbox` section of the template | a shell command that writes outside the write allowlist, that reads a path of the read deny list, or that connects to a host that is not on the network allowlist. The template turns the sandbox on, refuses to start without it, and lets no command run outside it on request | a command of `excludedCommands`, which runs outside the sandbox; the `Read`, `Edit` and `Write` tools, which the permission lists govern; an MCP server, which is not a shell command of the session. The network allowlist names hosts, so it does not stop what a command sends to an allowed host | 2.1.293 |
| **The `deny` and `ask` lists**, in `permissions` of the template | a tool call that matches a `deny` rule: the call is refused. A tool call that matches an `ask` rule: in the `default` mode the user sees a prompt. A `Read` or `Edit` deny of a path also goes into the sandbox's read or write deny list, so it stops a shell command too | a command that a rule does not match as text, such as a command inside a string argument. In the `auto` mode, an `ask` goes to the auto-mode classifier, which can let the call run with no prompt | 2.1.293 |
| **The guard hooks**, `PreToolUse` hooks in `hooks/` | on a shell command: a `git add` that stages more than the paths it names; a shell write to a file in a git working tree; a command whose shape makes the sandbox give a false result; a `gh api` write that is not a review or a comment (a prompt), and a `glab api` DELETE; a recursive `rm` outside the worktrees and the scratch directory of the research tree. On the directory and worktree tools: a move out of the research tree, and the removal of a worktree (a prompt). A hook that exits 2 refuses the call | a command shape that the hook does not parse: each hook reads the command text, and `no-blind-stage.py` lets an input it cannot read through. A write through the `Edit` and `Write` tools. OpenCode and oh-my-pi run four of the hooks, through a plugin and an extension | 2.1.293 |
| **The deny-write install and its drift warning** | the template has an `Edit` deny for each file and directory that `harness install` installs from this repository into `~/.claude/`, so a session cannot change an installed agent, skill, rule, hook or instruction file with a tool or a sandboxed shell command. At each session start, `hooks/install-drift.py` warns when the installed layer is not the layer of the sources | a command that runs outside the sandbox, such as a `git checkout` or `git restore` in `~/.claude/` when it is a git repository; an edit of the sources in the checkout, which a session can write and which no rule of the template shows to the user; the next `harness install --apply` installs that edit. The warning blocks nothing. A skill that does not come from this repository, for example one of the tree instructions, has an `ask` rule, not a deny | 2.1.293 |
| **The leak gate**, the pre-push hook and CI | a push to `main` of this repository whose files, paths, added lines or commit messages hold a string of the profile's `leak` list, a name of the research tree, or a secret or home path that gitleaks finds. CI runs gitleaks on every push | a push with the hook off, for example in a clone where `core.hooksPath` is not set; a private string that is not in the `leak` list; the author and committer of a commit, a tag message and `git notes`. CI has no profile, so it does not search for the private strings | none: the gate does not depend on Claude Code. gitleaks 8.21 or later |

## The limits

- **A deny rule is a text pattern.** It matches the text of the command, not what the command
  does. A command inside a string argument escapes it: `sh -c '…'`, `xargs sh -c`,
  `find -exec`, `julia -e 'run(…)'`, and `awk 'BEGIN{system("…")}'`. This class of commands is
  open, so a longer deny list does not close it. The sandbox contains such a command; the deny
  list does not.
- **The commands that the template excludes from the sandbox run outside it.** The template
  excludes `git`, `gh`, `glab` and `ps`. A command runs outside the sandbox when every part of it
  starts with one of these and no part redirects to or from a file. The sandbox does not wrap
  such a command, so none of the sandbox's lists apply to it: not the write allowlist, not the
  network allowlist, and not the write deny list that holds the `Edit` denies. The permission
  lists and the hooks still apply. A command with another part, such as a pipe into `cat` or a
  `cd` to another directory, runs inside the sandbox.
- **An MCP server runs outside the sandbox.** The sandbox wraps the shell commands of a session.
  An MCP server is a process of its own, for example a server that launchd starts. The code that
  it runs for a session does not see the write allowlist, the read deny list or the network
  allowlist. The permission lists control which of its tools a session can call.
- **OpenCode has no OS sandbox.** Its permission block and its guard plugin check text, as the
  deny list and the hooks do.
- **The settings refuse a session's edit of the settings.** The template denies an edit of
  `~/.claude/settings.json` and of `~/.claude.json`. A change of the settings is a change that you
  install yourself.

## Check a change of the settings

After `harness settings install --apply`, run the dry run again. It must say that the owned
sections are identical and exit 0.

Then check the change in a new session. For each changed rule, run more than one test: a call
that the rule must stop, and a call that it must let through. One result can mislead, and a
result that lets a call through is the more dangerous one. Repeat the exact call before you
decide that a rule does not work.

## The outer sandbox

An outer sandbox, one OS boundary around every frontend, is coming. This page gives no steps for
it yet.
