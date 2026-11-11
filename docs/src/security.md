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
| **The guard hooks**, `PreToolUse` hooks in `hooks/` | on a shell command: a `git add` that stages more than the paths it names; a shell write to a file in a git working tree; a command that fails in the sandbox with a misleading error, such as a `git`, `gh` or `glab` write that the sandbox does not exempt; a `git init` or `git clone` inside a git working tree; a `gh api` write that is not a review or a comment in a repository of an own organisation (a prompt), and a `glab api` DELETE; a `gh pr create` that names no repository, and one outside the own organisations (a prompt); a recursive `rm` outside the worktrees and the scratch directory of the research tree; a `git archive` that writes its file with `-o` or `--output`; a lease push that names a default branch or no branch; a forced worktree removal that loses commits or tracked changes, a cherry-pick outside a worktree or a checkout of an own organisation, and a lease push to another organisation (a prompt). On the directory and worktree tools: a move out of the research tree, and the removal of a worktree (a prompt). On a shell command, a web call and a Kaimon call: a token of a known form of GitHub, GitLab or an `sk-` provider, as it is or percent-decoded, which the token check `token_forms` refuses to prevent an accident. A hook that exits with status 2 refuses the call | a token that is encoded in another way, split into parts, given without its prefix or read by a script from a file, which passes `token_forms`: the check is no boundary against a session that sends a secret out. A command shape that the hook does not parse: each check reads the command text with its quotes and ANSI-C quotes, and each check except those of a shell write, of a misleading sandbox error and of a `git init` or `git clone` also reads the scripts of `sh -c`, `bash -c` and `eval`, so a program or a subcommand that a variable or a substitution names, a script on standard input, and a shell write or a `git init` in such a script pass. A write through the `Edit` and `Write` tools. Antigravity runs the guard package with `--from antigravity`, oh-my-pi through an extension with `--from omp`, and OpenCode through a plugin with `--from opencode`; the extension and the plugin refuse a call when the guard cannot answer | 2.1.293 |
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
- **A session can write the Julia depot, which Julia outside the sandbox loads later.** The
  template allows writes to `~/.julia`, so a sandboxed command can change a precompiled cache in
  `~/.julia/compiled`, and a Julia process that starts outside every sandbox can then load it. This
  path stays open by decision: Julia needs a writable depot. In `~/.cache` the template allows
  writes to `~/.cache/pocl` only; the `srt` settings of a frontend add its own cache, such as
  `~/.cache/claude` for `claude` and `~/.cache/opencode` for `opencode`.
- **Under `agentbox`, a command that a frontend runs can read the frontend's own credentials.**
  The `srt` settings of a frontend allow reads of its own credential files by name, and every
  other frontend's settings deny them: `~/.claude.json`, `~/.claude/.credentials.json` and the
  Anthropic profile's `~/.config/anthropic/credentials` for `claude`; `auth.json` and
  `mcp-auth.json` in `~/.local/share/opencode` for `opencode`; `agent.db`, `agent.db-wal` and
  `.env` in `~/.omp/agent` for `omp`; and `~/.gemini/jetski-standalone-oauth-token` for
  `antigravity`. The sandbox of the whole process cannot tell the frontend from its own shell.
  The `claude` settings also allow writes to `~/.config/anthropic/credentials` and to the lock
  directory `~/.config/anthropic/credentials.lock`, which Claude Code makes before a token
  refresh.
- **An allowed host takes what a command sends to it.** The network allowlist names hosts, not
  methods, so a sandboxed command can send a write to any host of `allowedDomains`. The harness
  list holds no `archive.org`, because its `*.archive.org` form would cover `web.archive.org`,
  whose Save Page Now publishes any URL without a login, and the upload host `s3.us.archive.org`.
  Of the hosts below `archive.org`, it holds `scholar.archive.org` alone. A host that accepts
  writes and that a session only reads is in the list `fetch`: the `WebFetch` tool reaches it
  with a GET, and a sandboxed command does not reach it. A GET can still carry data in its URL to
  such a host. Under `agentbox` a frontend does not reach a `fetch` host at all, because srt takes
  `allowedDomains` alone.
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
  job runs under its own profile from the same file. For every other MCP server no profile
  applies.
- **On Linux, Kaimon and `julia-update` run under `bwrap`.** Each unit starts its program with
  `~/.local/bin/jobbox <job>`, which runs `bwrap` with the arguments that `harness setup` renders
  from the same `sandbox/daemon.toml` into `~/.config/research-harness/sandbox/<job>.bwrap`. The
  job gets new namespaces of every kind but the network (`--unshare-all --share-net`), ends with
  the unit (`--die-with-parent`), and sees a new `/proc`, a new empty `/tmp`, `/dev`, `/sys`
  read-only, the system paths of `linux_read` read-only, and an empty home. In that home only the
  job's `~/` paths are bound: Kaimon reads and writes `~/Research`, the depot and its own
  directories, as on macOS, and the same write denies are bound read-only. `jobbox` also binds
  `.git/hooks`, `.git/config` and `.githooks` read-only in each repository that it finds at most
  four levels below `~/Research` when a job that binds `~/Research` starts. `bwrap` follows a
  symbolic link in a bind, and each job writes directories below the home that hold sources of
  the other job's binds, such as `~/.julia/environments/apps` of `julia-update` in Kaimon's
  `~/.julia`. So `jobbox` stops with exit 2, before `bwrap`, when a source of any bind below the
  home is a link, or lies below one under the entry of the home that holds it, which may itself
  be a link. A check before the mount does not hold against the other job while it runs, so each
  job binds onto itself each path from its own write path down to such a source of the other:
  in its namespace that path is a mount point, which it can neither rename nor remove. A pin is a
  bind source too, so each job also pins the paths to the other job's pins that it writes and
  does not bind yet, and binds each pin before any of its write binds below it, which would
  otherwise cover it. Kaimon pins `~/.julia/environments` and `~/.julia/environments/apps`, and
  `julia-update` pins Kaimon's pin `~/.julia/environments` and juliaup's lock file. Neither job
  sees `/run/user/<uid>`, so neither reaches the session bus or the user's service manager;
  `julia-update` therefore runs its server check, the restart of the server and its alerts in a
  second phase, `~/.local/bin/julia-update-server`, a POSIX `sh` script outside `bwrap`, after
  the update phase. It runs no Julia and no program of a `PATH` entry whose physical path lies at
  or below the physical home, or below the target of a link directly in the home, and reads the
  update phase's state as data. Kaimon writes the depot whose packages the update phase loads, so
  the two jobs are one trust domain: what `julia-update` writes, `~/.juliaup`, `~/.julia/bin`,
  `~/.julia/juliaup` and the harness's Julia environment, Kaimon's code can write at the next run
  of the update phase, Kaimon's own write denies of `~/.julia/bin` and `~/.julia/juliaup`
  included.
  `harness setup` and the services script of the dotfiles kit first run the sandbox check of
  `harness doctor` and stop with exit 2 when `bwrap` cannot make a sandbox, which names the
  AppArmor setting `kernel.apparmor_restrict_unprivileged_userns`; no job then starts unconfined.
  The arguments leave open the network, every abstract Unix socket of the host's network
  namespace, such as an X server's `@/tmp/.X11-unix/X0`, through which a client can type into any
  window of the user, the host's terminals in `/dev/pts`, which `--dev-bind /dev /dev` shows the
  job (not measured on Linux), every write inside `~/Research` outside the bound repository parts,
  the parts of a repository cloned after the job's start, a `.githooks` that did not exist at the
  start, the `.git` file of a worktree, which the job can point at a git directory with hooks of
  its own, and the hooks and the configuration of a submodule in `.git/modules/<name>`, which get
  no bind. A network namespace of its own for each job, which would close the network and
  abstract-socket gaps, is planned.
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
