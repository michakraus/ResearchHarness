# The security model

The harness gives an agent session several layers of control. Only one of them is a security
boundary: the OS sandbox. The other layers prevent accidents. They stop common mistakes
and tell the session what to do instead, but a session that tries to get past them can do
so. [Risks of agentic coding](risks.md) says which risk each layer answers.

`harness install` writes the sandbox, the permission lists and the hooks from the settings
template `settings/settings.proposal.json` into `~/.claude/settings.json`.
[The setup reference](../setup-reference.md#claude-code) gives the steps.

<ControlFigure />

*The layers of control around one tool call.* The instructions guide the agent. Before a tool call
runs, the guard hooks and the permission settings check it, and refuse it, ask you, or let it run.
A shell command then runs inside the sandbox.

<WalkThrough name="tool-call" />

*One tool call through the layers of control.* The agent reads the instructions and plans a shell
command. The guard hooks and the permission settings check the call: a deny refuses it, an ask
shows you a prompt, and an allow lets it run. After your yes, the command runs inside the
sandbox.

## The mechanisms

Each row states the behaviour of the Claude Code version in the last column, in a session with
the installed template. A later version can behave differently. A page of this section describes
each mechanism: [Sandboxes](sandbox.md), [Permissions](permissions.md),
[Guard hooks](guard-hooks.md), [Git safety](git-safety.md) and
[Leak checks and gitleaks](leaks.md).

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
  which of its tools a session can call. The launch agents of Kaimon and `julia-update` start
  their programs under a Seatbelt profile, which denies every file read and write that it does
  not name. Kaimon's profile allows outbound connections only to the loopback addresses and to
  Kaimon's own Unix sockets below `~/.cache/kaimon`, and its launch agent sets
  `JULIA_PKG_OFFLINE=true`, so Pkg in a session downloads nothing: a session's own `julia` or the
  `julia-update` job downloads the packages. The profile refuses the connect to the resolver's
  socket, so code under it is meant to resolve no host name, and it refuses a client that connects
  to `::ffff:127.0.0.1`. Inbound connections and binds stay open, and `julia-update` keeps the
  network and loads the depot that Kaimon writes, so code that a session plants there reaches the
  network at the next update. The profile leaves open every write inside `~/Research` outside the
  repository parts that it denies, such as `~/Research/.claude/hooks`, which the session sandbox
  denies: through Kaimon's `ex`, code can write a hook that a later session runs outside every
  sandbox. A process under Kaimon's profile can also write text into any terminal of the user.
  [The daemon profiles](sandbox.md#the-daemon-profiles) give the rules in full. On Linux, `jobbox`
  starts Kaimon and `julia-update` under [`bwrap`](sandbox.md#the-daemon-profiles), with
  arguments from the same rule list, and both keep the network. For every other MCP server, no
  profile applies.
- **OpenCode and oh-my-pi have no sandbox of their own.** Started without `agentbox`, their
  permission blocks and guard extensions check text, as the deny list and the hooks do. Started
  through [`agentbox`](sandbox.md#the-launcher-agentbox), each runs with every command that it
  starts inside the sandbox of `srt`. Antigravity runs commands in its terminal sandbox in the
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

## Planned safeguards

These safeguards are decided, and none of them runs yet. [Sandboxes](sandbox.md#planned) gives
each sandbox item in more detail.

- **A guard against a session with no sandbox** ([planned](../planned.md#no-sandbox-guard)): a
  guard hook refuses every tool call when `~/.ssh` is readable and no sandbox is on.
- **Kaimon without the network on Linux** ([planned](../planned.md#kaimon-without-network)):
  only the loopback addresses and Kaimon's own sockets stay reachable, as on macOS.
- **The desktop apps under an outer sandbox** ([planned](../planned.md#desktop-apps)), and
  **a Linux launcher** ([planned](../planned.md#linux-launcher)).
- **Masked keys** ([planned](../planned.md#masked-keys)), and **a forge token per owner**
  ([planned](../planned.md#token-per-owner)).
- **A credential proxy** ([planned](../planned.md#credential-proxy), optional and last).
