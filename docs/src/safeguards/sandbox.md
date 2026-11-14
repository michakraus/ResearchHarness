# Sandboxes

A sandbox is a limit that the operating system puts on a process: the files that it can read and
write, and the hosts that it can reach. A text check reads what a command says; a sandbox limits
what the command does, whatever it says. So the sandbox is the one security boundary of the
harness ([The security model](security-model.md)). This page describes the three sandboxes of the
harness, what each one wraps, and the sandboxes that are planned.

## Three sandboxes

<SandboxFigure />

*The sandboxes of the harness.* In a normal session, Claude Code wraps each shell command in its
own sandbox; `git`, `gh`, `glab` and `ps` run outside it. The Kaimon server, which a session
reaches over MCP, runs under a Seatbelt profile of its own. The launcher `agentbox` puts one
sandbox around a whole frontend, its own process and every command that it starts.

| sandbox | wraps | on | turned on by |
|:--|:--|:--|:--|
| [the session sandbox](#the-session-sandbox) | each shell command of a Claude Code session | macOS, Linux | the settings template; always on |
| [the launcher `agentbox`](#the-launcher-agentbox) | a whole CLI frontend: `claude`, `opencode`, `omp` or `agy` | macOS; on Linux [planned](../planned.md#linux-launcher) | you, by starting the frontend through `agentbox` |
| [the daemon profiles](#the-daemon-profiles) | the Kaimon server and the `julia-update` job | macOS, Linux | `harness setup`, in the launch agents and the `systemd --user` units |

## The session sandbox

The `sandbox` section of the settings template turns Claude Code's sandbox on for every shell
command of a session:

| key | value | effect |
|:--|:--|:--|
| `enabled` | `true` | each `Bash` command runs inside the sandbox |
| `failIfUnavailable` | `true` | a session does not start when the sandbox cannot start |
| `allowUnsandboxedCommands` | `false` | a command cannot ask to run outside the sandbox |
| `autoAllowBashIfSandboxed` | `true` | a sandboxed command runs with no prompt; the [deny list](permissions.md#deny) still applies |
| `excludedCommands` | `git`, `gh`, `glab`, `ps` | these run outside the sandbox |

**Files.** The write allowlist holds `~/Research`, `~/.julia`, the temporary directories, the
cache of PoCL, the directories of rtk and a few directories of `~/.claude`. The write deny list holds the installed files, the settings and the
git hooks, and each `Edit` deny of the permission lists. The read deny list holds the files of
keys and tokens, and each `Read` deny.

**Network.** The allowlist is strict: a host that is not on it is refused. `settings/network.toml`
lists the hosts in three groups, and the profile can add its own. A fourth key, `deny`, names a
host that reaches neither:

| group | reaches the host |
|:--|:--|
| `allow` | the `WebFetch` tool and a sandboxed command |
| `fetch` | the `WebFetch` tool only: a host that accepts writes, which a session only reads |
| `infrastructure` | a sandboxed command only, such as a package server |

**Why four commands run outside it.** A sandboxed `git` cannot write `.git`, and a sandboxed `gh`
fails its TLS check with error `-26276` on macOS. So `git`, `gh`, `glab` and `ps` are excluded. A
command runs outside the sandbox only when every part of it starts with one of the four and no
part redirects to or from a file. `cd <other dir> && git commit` would run inside it and fail, so
the [sandbox check](guard-hooks.md#the-sandbox-check) refuses it before it runs. The
permission lists and the [guard hooks](guard-hooks.md) still apply to an excluded command, and
[Git safety](git-safety.md) describes the checks of `git` and `gh`.

## The launcher `agentbox`

The session sandbox wraps the shell commands of Claude Code. It does not wrap Claude Code itself,
an MCP server that it starts, or another frontend: OpenCode and oh-my-pi have no sandbox of their
own. The launcher `agentbox` closes this gap. It starts one frontend under `srt`, the sandbox
runtime, so the frontend and everything that it starts run inside one sandbox:

```sh
agentbox claude
agentbox opencode
```

`agentbox` runs
`~/.local/bin/srt --settings ~/.config/research-harness/sandbox/<policy name>.json -- <program>`,
where the policy name is the frontend's name, and `antigravity` for `agy`. `harness install` writes one settings file for each CLI frontend, from the
`sandbox` section of the template and the policy file `sandbox/policy.toml`, so every frontend
shares the template's file lists and network lists. Each frontend gets an argument that fits the
outer sandbox:

| frontend | argument | why |
|:--|:--|:--|
| `claude` | `--settings …/claude-inner-off.json` | Claude Code's own sandbox fails inside `srt`, so the inner one is off |
| `opencode` | `--standalone` | its server runs as its own child, inside the sandbox |
| `omp` | `--approval-mode yolo` | no prompts; the sandbox is the boundary |

The launcher sets `AGENTBOX=1` and refuses to start inside a launcher. It gives each run new cache
directories for npm, uv and LaTeX, because the sandbox denies their caches in the home directory.
`harness setup` installs the pinned `srt` with `npm ci --ignore-scripts`.

**`agentbox` is opt-in.** A frontend that you start without it does not read its `srt` file, and
runs as it would without the harness: Claude Code with its session sandbox, OpenCode and oh-my-pi
with none. The probe battery `scripts/probe-agentbox.py` checks the boundary on macOS; run it from
a plain terminal, not from a session. [The srt settings](../components/sandbox.md) describes the
rendering, the launcher and the probe in full.

**Each frontend adds its own hosts.** A frontend's file adds the hosts of its `network` list in
the policy file, and those of a `[frontend.<name>]` table of the overlay `network.toml`, to the
template's `allowedDomains`; no other frontend's file gets them. Claude Code's token host
`platform.claude.com` is in `claude`'s list, and `agy`'s three Google hosts, for its login token,
its model and its account, in `antigravity`'s. An entry `*.X` reaches every host below `X`,
the hosts of other tenants of a shared domain included, so a cloud provider's `*.X` also reaches
every other customer's endpoint below it. `srt` sets `NO_PROXY` for `localhost`, `127.0.0.1` and
`::1`, and its macOS profile allows outbound connections to `localhost` where
`allowLocalBinding` is true, as the template sets it. So a client that honours `NO_PROXY` reaches
a server on the loopback address with no entry; only a client that sends a loopback request
through the proxy needs one.

**A frontend can read its own credentials.** The sandbox wraps the frontend and its shell
together, so it cannot tell them apart. Each frontend's settings allow reads of its own credential
files by name, and deny those of every other frontend
([The security model](security-model.md#the-limits)). OpenCode and oh-my-pi also read Kaimon's
token `~/.config/kaimon/auth-token`, the bearer with which they reach Kaimon, and cannot write
it. So a command that either frontend runs can read the token too, reach Kaimon, and run Julia
through Kaimon's `ex` under [Kaimon's profile](#the-daemon-profiles), which allows no outbound
connection but to the loopback address and to Kaimon's own sockets. The files of Claude Code and
Antigravity deny reads of the token: each keeps Kaimon's bearer in its own configuration,
`~/.claude.json` and `~/.gemini/config/mcp_config.json`, which the frontend and its commands
can read.

**A frontend can read every forge token.** git and the gh wrapper read the token store
`~/.config/research-harness/forge` inside the sandbox, so each frontend's settings allow its
reads, and a command that a frontend runs can read each fine-grained token of it. `agentbox` also
exports the one GitLab token as `GITLAB_TOKEN`. Each token reaches only its own owner's
repositories on its forge, and the forge enforces that limit; the sandbox does not filter the
operations ([The forge tokens](../components/sandbox.md#the-forge-tokens)).

**No frontend can read the dotfiles token.** The token of the dotfiles,
`~/.config/dotfiles-credentials`, is denied where the forge token store is: the settings template
holds `Read(/{home}/.config/dotfiles-credentials/**)` in `permissions.deny` and the path in
`denyRead` and in `credentials.files`, and the guard list of OpenCode, oh-my-pi and Antigravity
denies it. No frontend's `own` names it, so each frontend's settings file denies its reads,
although the files allow reads of `~/.config`.

**No frontend can read the sealed secrets.** On macOS, your own broad forge tokens can be secrets
in `~/.config/research-harness/sealed`, which `ghx`, `glabx` and `git-credential-sealed` decrypt
with `age` and an `age-plugin-se` identity in the Secure Enclave
([The sealed secrets](../components/sandbox.md#the-forge-tokens)). The directory is denied as the
dotfiles token is: `Read(/{home}/.config/research-harness/sealed/**)` in `permissions.deny`, the
path in `denyRead` and in `credentials.files`, the guard list of OpenCode, oh-my-pi and
Antigravity, and each frontend's settings file, because no frontend's `own` names it. The
template's `permissions.deny` also refuses `ghx`, `glabx` and `git-credential-sealed` as commands,
which prevents accidents and is no boundary. The boundary is Touch ID: each decryption asks for
it, and the route is yours alone. A Touch ID prompt that you did not start comes from a session,
and you refuse it.

**A frontend can use every terminal of the user.** A frontend's terminal user interface puts its
terminal, a `/dev/ttysNNN`, in raw mode, and of the terminal devices `srt` allows an ioctl only
on `/dev/tty` by default. Each frontend's settings file therefore holds `"allowPty": true`, and
`srt` then allows the operation `pseudo-tty` and reads, writes and ioctls of `/dev/ptmx` and of
every `/dev/ttysNNN`. The sandbox cannot tell the frontend's own terminal from the terminal
window of another program of the same user, so a sandboxed command can read from and write to
every terminal of the user, as under [the daemon profile of Kaimon](#the-daemon-profiles). The
key acts on macOS only.

**oh-my-pi can reach the macOS spell service.** `srt`'s profile allows a fixed list of Mach
services, such as the font and logging services. oh-my-pi's typo detection asks the spell service
`mul-xpc (Apple)_OpenStep` for each word of the prompt, so `omp`'s settings file adds that
service in `allowMachLookup`, from the key `mach_lookup` of the policy file. A command that
oh-my-pi runs can reach it too: the service receives the words that it is sent and can write
learned words to `~/Library/Spelling`, outside the sandbox.

**Every frontend can reach the trust service.** `gh` and `agy` are Go programs, and Go checks a TLS
certificate through `com.apple.trustd.agent`. Every frontend runs `gh`, so each settings file adds
that service, and without it every request of `gh` fails with `x509: OSStatus -26276`. `srt` names
the service a possible path for data out of the sandbox, and allows it otherwise only with
`enableWeakerNetworkIsolation`. A command that a frontend runs can reach it too.

## The daemon profiles

An MCP server runs outside the session's sandbox: it is a process of its own, for example one that
launchd starts, and the code that it runs for a session does not see the session's lists. The
permission lists control which of its tools a session can call, not what the tools do. On macOS
the harness therefore runs the two launch agents that run Julia outside every session under a
Seatbelt profile of their own: the Kaimon server and the `julia-update` job.

The launch agent of Kaimon starts the server with
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
writing.

Kaimon starts every Julia session on a pseudo-terminal, so the profile allows the
operation `pseudo-tty` and reads, writes and ioctls of `/dev/ptmx` and of every
`/dev/ttysNNN` (the key `pty` of the job). Seatbelt cannot tell the job's own pseudo-terminal
from the terminal window of another program of the same user, so a confined process can open
the `/dev/ttysNNN` of any terminal of the user and write text into it, which that terminal
shows as output. The rule also allows a change of the device's mode, which the user owns, so it
does not stop a read of that terminal's input either. Whether such a process can also push
input into another terminal with the ioctl `TIOCSTI` is not checked on macOS 27. The
`julia-update` job has `pty = false` and no such rule.

Kaimon's profile denies an app or document opened through Launch Services, and a mount. It denies
an Apple Event to another app twice: `(deny appleevent-send)`, and a deny of the Mach services
`com.apple.coreservices.launchservicesd` and `com.apple.CoreServices.coreservicesd`. On macOS
27.2, under the rendered profile and outside every agent sandbox,
`osascript -e 'tell app "Finder" to get name of startup disk'` fails with error `-54`, and with
`-600` when the profile lacks the Mach-service deny; an `AESendMessage` call that does not go
through `osascript` also fails, with `-600`. Each rule alone stops the event before the
Automation consent of macOS. The probe `appleevent` of `sandbox/probe-daemon.jl` sends this
event: AppleScript answers `name` of an application from the script itself and sends no event.

Kaimon's profile ends with three rules on outbound traffic (the keys `network = "loopback"` and
`unix_sockets` of the job), after the Mach-service deny, because Seatbelt applies the last rule
that matches: `(deny network-outbound)`; `(allow network-outbound (remote ip "localhost:*"))`,
a connect to `127.0.0.1` and `::1` on any port, where Kaimon answers MCP; and an allow of a
connect to a Unix socket below `~/.cache/kaimon`, where Kaimon's gate keeps the ZMQ sockets
between the server and its sessions. Seatbelt filters by address and port, not by host name, so
no rule can allow the package servers alone. Kaimon's launch agent therefore sets
`JULIA_PKG_OFFLINE=true`, which every session inherits: Pkg updates no registry and resolves
against the installed versions alone, so a `Pkg.add` or an `instantiate` that needs a download
fails, and so does an artifact download. A session's own `julia`, which the session sandbox lets
reach the package servers, or the `julia-update` job downloads the package. The deny also refuses
the connect of every other Unix socket, among them the resolver's `/var/run/mDNSResponder`, so
code that runs through Kaimon is meant to resolve no host name; the probe `resolve_name` of
`sandbox/probe-daemon.jl` tries one. A client that connects to `::ffff:127.0.0.1`, the IPv4
loopback address in its IPv6 form, is refused.

The rules cover outbound traffic only. Inbound connections and binds stay open: a listener that a
session binds to every interface accepts connections from the network. `julia-update` keeps the
network (`network = "open"`), because it downloads juliaup's releases and the packages. Kaimon
writes the depot whose packages `julia-update`'s `Pkg.update()` precompiles and loads with the
network open, so the two jobs are one trust domain: code that a session plants in the depot
through Kaimon's `ex` reaches the network at the next update.

The profile leaves open the other Mach services, which Metal needs, every write inside
`~/Research` outside the denied repository parts, and the rename of a directory above a denied
part, which moves the part out of the denied path. The writes inside `~/Research` include
`~/Research/.claude/hooks`, `skills` and `settings.json`, which the session sandbox denies: through
Kaimon's `ex`, code can write a hook that a later session runs outside every sandbox.

The exec of the setuid `/bin/ps` fails under the profile, and Kaimon reads a failed
`ps -o state= -p PID` as a dead session, so the shims directory holds a `ps` of the harness that
answers that form with `kill -0`. It says that any process that `kill -0` can signal exists, which
the job could already learn with `kill -0` itself, counts a zombie as alive, and counts a process
that `kill -0` may not signal, such as one of another user, as gone. The `julia-update` job runs
under its own profile from the same file. For every other MCP server, no profile applies.

**On Linux, Kaimon and `julia-update` run under `bwrap`.** Each unit starts its program with
`~/.local/bin/jobbox <job>`, which runs `bwrap` with the arguments that `harness setup` renders
from the same `sandbox/daemon.toml` into `~/.config/research-harness/sandbox/<job>.bwrap`. The
job gets new namespaces of every kind but the network (`--unshare-all --share-net`), ends with
the unit (`--die-with-parent`), and sees a new `/proc`, a new empty `/tmp`, the host's `/dev`,
`/sys` read-only, the system paths of `linux_read` read-only, and an empty home. In that home only
the job's `~/` paths are bound: Kaimon reads and writes `~/Research`, the depot and its own
directories, as on macOS, and the same write denies are bound read-only. `jobbox` also binds
`.git/hooks`, `.git/config` and `.githooks` read-only in each repository that it finds at most
four levels below `~/Research` when a job that binds `~/Research` starts. `bwrap` follows a
symbolic link in a bind, and each job writes directories below the home that hold sources of
the other job's binds, such as `~/.julia/environments/apps` of `julia-update` in Kaimon's
`~/.julia`. So `jobbox` stops with exit 2, before `bwrap`, when a source of any bind below an
entry of the home is a link, or lies below one under that entry, which may itself be a link. A
check before the mount does not hold against the other job while it runs, so each job binds onto
itself each path from its own write path down to such a source of the other:
in its namespace that path is a mount point, which it can neither rename nor remove. A pin is a
bind source too, so each job also pins the paths to the other job's pins that it writes and
does not bind yet, and binds each pin before any of its write binds below it, which would
otherwise cover it. Kaimon pins `~/.julia/environments` and `~/.julia/environments/apps`, and
`julia-update` pins Kaimon's pin `~/.julia/environments` and juliaup's lock file. Neither job
sees `/run/user/<uid>`, so neither reaches the session bus or the user's service manager;
`julia-update` therefore runs its server check, the restart of the server and its alerts in a
second phase, `~/.local/bin/julia-update-server`, a POSIX `sh` script outside `bwrap`, after
the update phase. It runs no Julia and no program of a `PATH` entry whose physical path lies at
or below the physical home, or at or below the target of a link directly in the home, and reads
the update phase's state as data. Kaimon writes the depot whose packages the update phase loads,
so the two jobs are one trust domain: what `julia-update` writes, `~/.juliaup`, `~/.julia/bin`,
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

## Planned

These sandboxes are decided, and none of them runs yet:

- **A guard against a session with no sandbox** ([planned](../planned.md#no-sandbox-guard)): a
  hook that refuses every tool call when `~/.ssh` is readable and no sandbox is on: neither the
  launcher nor Claude Code's own sandbox.
- **Fewer prompts under the launcher** ([planned](../planned.md#fewer-prompts)): the permission
  prompts that the outer sandbox makes safe go, as a settings change with probes.
- **The desktop apps** ([planned](../planned.md#desktop-apps)): an outer sandbox for Claude Code's
  Code tab and the Antigravity desktop app, which `agentbox` cannot start, with the same probe
  battery.
- **A Linux wrapper** ([planned](../planned.md#linux-launcher)): the outer sandbox on Linux, tried
  first on one test machine, then the same battery and a GPU kernel on each Linux machine.
- **Masked keys** ([planned](../planned.md#masked-keys)): the API keys stay in their denied files,
  and the launcher gives them to `srt` as masked variables; the `gh` and `glab` tokens leave the
  key store for masked variables too.
- **A token per owner** ([planned](../planned.md#token-per-owner), waits for your tokens): a
  fine-grained forge token for each organisation, so that a command can write only where the task
  needs it.
- **Kaimon without the network on Linux** ([planned](../planned.md#kaimon-without-network)): the
  Kaimon server under `bwrap` reaches only the loopback addresses and its own sockets, as on macOS.
- **A credential proxy** ([planned](../planned.md#credential-proxy), optional and last): a proxy
  that writes the keys into the requests for their named hosts, so that the agent sees only a
  stand-in. `srt` already filters the network by host, so the proxy does not run by default.
