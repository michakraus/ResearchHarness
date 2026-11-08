# The security model

The harness gives an agent session several layers of control. Only one of them is a security
boundary: the Claude Code sandbox. The other layers prevent accidents. They stop common mistakes
and tell the session what to do instead, but a session that tries to get past them can do
so.

`harness install` writes the sandbox, the permission lists and the hooks from the settings
template `settings/settings.proposal.json` into `~/.claude/settings.json`.
[setup-reference.md](setup-reference.md#claude-code) gives the steps.

<WalkThrough name="tool-call" />

*One tool call through the layers of control.* The agent reads the instructions and plans a shell
command. The guard hooks and the permission settings check the call: a deny refuses it, an ask
shows you a prompt, and an allow lets it run. After your yes, the command runs inside the
sandbox.

## The mechanisms

Each row states the behaviour of the Claude Code version in the last column, in a session with
the installed template. A later version can behave differently.

| mechanism | what it stops | what it does not stop | Claude Code version |
|:--|:--|:--|:--|
| **The sandbox**, the `sandbox` section of the template | a shell command that writes outside the write allowlist, that reads a path of the read deny list, or that connects to a host that is not on the network allowlist. The template turns the sandbox on, refuses to start without it, and does not let a command ask to run outside it | a command of `excludedCommands`, which runs outside the sandbox; the `Read`, `Edit` and `Write` tools, which the permission lists govern; an MCP server, which is not a shell command of the session. The network allowlist names hosts, so it does not stop what a command sends to an allowed host | 2.1.293 |
| **The `deny` and `ask` lists**, in `permissions` of the template | a tool call that matches a `deny` rule: the call is refused. A tool call that matches an `ask` rule: in the `default` mode the user sees a prompt. A `Read` or `Edit` deny of a path also goes into the sandbox's read or write deny list, so it stops a shell command too | a command that a rule does not match as text, such as a command inside a string argument. In the `auto` mode, an `ask` goes to the auto-mode classifier, which can let the call run with no prompt | 2.1.293 |
| **The guard hooks**, `PreToolUse` hooks in `hooks/` | on a shell command: a `git add` that stages more than the paths it names; a shell write to a file in a git working tree; a command that fails in the sandbox with a misleading error, such as a `git`, `gh` or `glab` write that the sandbox does not exempt; a `git init` or `git clone` inside a git working tree; a `gh api` write that is not a review or a comment (a prompt), and a `glab api` DELETE; a `gh pr create` that names no repository, and one outside the own organisations (a prompt); a recursive `rm` outside the worktrees and the scratch directory of the research tree; a `git archive` that writes its file with `-o` or `--output`; a lease push that names a default branch or no branch; a forced worktree removal that loses commits or tracked changes, a cherry-pick outside a worktree or a checkout of an own organisation, and a lease push to another organisation (a prompt). On the directory and worktree tools: a move out of the research tree, and the removal of a worktree (a prompt). A hook that exits with status 2 refuses the call | a command shape that the hook does not parse: each check reads the command text with its quotes and ANSI-C quotes, and each check except those of a shell write, of a misleading sandbox error and of a `git init` or `git clone` also reads the scripts of `sh -c`, `bash -c` and `eval`, so a program or a subcommand that a variable or a substitution names, a script on standard input, and a shell write or a `git init` in such a script pass. A write through the `Edit` and `Write` tools. Antigravity runs the guard package with `--from antigravity`, oh-my-pi through an extension with `--from omp`, and OpenCode through a plugin with `--from opencode`; the extension and the plugin refuse a call when the guard cannot answer | 2.1.293 |
| **The deny-write install and its drift warning** | the template has an `Edit` deny for each file and directory that `harness install` installs from this repository into `~/.claude/`, so a session cannot change an installed agent, skill, rule, hook or instruction file with a tool or a sandboxed shell command. At each Claude Code or Antigravity session start, `hooks/install-drift.py` warns when the installed files differ from their sources | a command that runs outside the sandbox, such as a `git checkout` or `git restore` in `~/.claude/` when it is a git repository; an edit of the sources in the checkout, which a session can write and which no rule of the template shows to the user; the next `harness install --apply` installs that edit. The warning blocks nothing. A skill that does not come from this repository, for example one of the tree instructions, has an `ask` rule, not a deny | 2.1.293 |
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
- **An MCP server runs outside the session's sandbox; on macOS, Kaimon runs under a profile of its
  own.** The sandbox wraps the shell commands of a session. An MCP server is a process of its own,
  for example a server that launchd starts, and the code that it runs for a session does not see
  the session's write allowlist, read deny list or network allowlist. The permission lists control
  which of its tools a session can call. The launch agent of Kaimon starts the server with
  `/usr/bin/sandbox-exec -f ~/.config/research-harness/sandbox/kaimon.sb`, a Seatbelt profile that
  `harness setup` renders from `sandbox/daemon.toml`. The profile denies every file read and
  write, then allows reads of `~/Research`, the Julia depot, juliaup, Kaimon's configuration,
  cache and logs, git's configuration, the per-user temporary and cache directories, the
  system directories, the root directory `/` itself, which dyld reads when a process starts,
  and `~/.config/research-harness/sandbox/shims`, the first directory of the job's `PATH`; and
  writes of `~/Research`, the depot, Kaimon's directories, the per-user directories and
  `/private/tmp`. It denies writes to `~/.julia/bin`, `~/.julia/config`,
  `~/.julia/juliaup`, the harness's `githooks/`, and `.git/hooks`, `.git/config` and `.githooks`
  at any depth below `~/Research`. After these denies it allows one file again, juliaup's lock
  file `~/.julia/juliaup/.juliaup-lock`, because the juliaup launcher that starts Julia opens it
  for writing at every start and exits when that fails; `juliaup.json` and the installed Julia
  versions stay unwritable. The rule allows every write to that one path, so a confined process
  can also hold the lock, which makes every juliaup command outside the profile wait, or put a
  symbolic link in the file's place, which a juliaup command outside the profile then opens for
  writing. Kaimon starts every Julia session on a pseudo-terminal, so the profile allows the
  operation `pseudo-tty` and reads, writes and ioctls of `/dev/ptmx` and of every
  `/dev/ttysNNN` (the key `pty` of the job). Seatbelt cannot tell the job's own pseudo-terminal
  from the terminal window of another program of the same user, so a confined process can open
  the `/dev/ttysNNN` of any terminal of the user and write text into it, which that terminal
  shows as output. The rule also allows a change of the device's mode, which the user owns, so it
  does not stop a read of that terminal's input either. Whether such a process can also push
  input into another terminal with the ioctl `TIOCSTI` is not checked on macOS 27. The
  `julia-update` job has `pty = false` and no such rule. Kaimon's profile denies an app or
  document opened through Launch Services, and a mount. It denies an Apple Event to another app
  twice: `(deny appleevent-send)`, and a deny of the Mach services
  `com.apple.coreservices.launchservicesd` and `com.apple.CoreServices.coreservicesd`. On macOS
  27.2, under the rendered profile and outside every agent sandbox,
  `osascript -e 'tell app "Finder" to get name of startup disk'` fails with error `-54`, and with
  `-600` when the profile lacks the Mach-service deny; an `AESendMessage` call that does not go
  through `osascript` also fails, with `-600`. Each rule alone stops the event before the
  Automation consent of macOS. The probe `appleevent` of `sandbox/probe-daemon.jl` sends this
  event: AppleScript answers `name` of an application from the script itself and sends no event.
  The profile leaves open the
  network, the other Mach services, which Metal needs, every write inside `~/Research` outside the denied repository parts, and the rename of a
  directory above a denied part, which moves the part out of the denied path. The writes inside
  `~/Research` include `~/Research/.claude/hooks`, `skills` and `settings.json`, which the session
  sandbox denies: through Kaimon's `ex`, code can write a hook that a later session runs outside
  every sandbox. The exec of the setuid `/bin/ps` fails under the profile, and Kaimon reads a
  failed `ps -o state= -p PID` as a dead session, so the shims directory holds a `ps` of the
  harness that answers that form with `kill -0`. It says that any process that `kill -0` can
  signal exists, which the job could already learn with `kill -0` itself, counts a zombie as
  alive, and counts a process that `kill -0` may not signal, such as one of another user, as
  gone. The `julia-update`
  job runs under its own profile from the same file. On Linux, and for every other MCP server,
  no profile applies.
- **OpenCode and oh-my-pi have no sandbox.** Their permission blocks and guard extensions check
  text, as the deny list and the hooks do. Antigravity runs commands in its terminal sandbox in the
  CLI and the desktop app, and its guard hook sets `BypassSandbox` on each command and checks paths
  and command segments.
- **A session cannot edit the settings.** The template denies an edit of
  `~/.claude/settings.json` and of `~/.claude.json`. A change of the settings is a change that you
  install yourself.

## Check a change of the settings

Before `harness install --apply`, read the diff of the sections `permissions`, `hooks`, `sandbox`
and `modelSettings` that the dry run prints after the line of `~/.claude/settings.json`. After the
`--apply`, run `harness install` again. It must print `already identical` for
`~/.claude/settings.json` and exit 0.

Then check the change in a new session. For each changed rule, run more than one test: a call
that the rule must stop, and a call that it must let through. One result can mislead, and a
result that lets a call through is the more dangerous one. Repeat the exact call before you
decide that a rule does not work.

## The outer sandbox

An outer sandbox, one OS boundary around every frontend, is planned. This page gives no steps for
it yet.
