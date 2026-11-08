# The srt settings of the CLI frontends

`srt`, the sandbox runtime, runs one process and everything that it starts inside one sandbox. It
reads one settings file. `harness install` writes one such file for each CLI frontend that the
profile's `[setup]` chooses:

```text
~/.config/research-harness/sandbox/claude.json
~/.config/research-harness/sandbox/opencode.json
~/.config/research-harness/sandbox/omp.json
~/.config/research-harness/sandbox/antigravity.json
```

The launcher `agentbox` starts a frontend under `srt` with its file, as
[the launcher](#the-launcher-agentbox) describes. A frontend that starts without it does not read
the file.

The files come from two sources. The `sandbox` section of the Claude Code settings template,
`settings/settings.proposal.json`, stays the source of the lists that every frontend shares: the
write paths, the write and read denies, the credential files and the network rules, with the
domains that `settings/network.toml` and the profile's overlay give. The policy file
`sandbox/policy.toml` holds only what `srt` adds to them. `lib/harness/sandbox.py` renders the
files from both.

## The policy file

`sandbox/policy.toml` has a table `[read]` and a table `[frontend.<name>]` for each of `claude`,
`opencode`, `omp` and `antigravity`. Every path starts with `~/`.

| key | what it holds |
|:--|:--|
| `read.allow` | the paths that every frontend reads under the read limit |
| `frontend.<name>.state` | the frontend's own directories and files, which it reads and writes |
| `frontend.<name>.deny_write` | write denies that the frontend adds to the template's |
| `frontend.<name>.own` | the template's deny entries that the frontend reads and writes itself |

The read limit denies reads of the whole home directory and allows the paths of `read.allow`
again. A path that the template denies stays hidden inside an allowed path: in `srt` a deny inside
an allowed path wins. Claude Code's `own` is `~/.claude.json`, which Claude Code writes itself; a
write deny of it would stop the whole process under `srt`. The cost is that a command that Claude
Code runs can also write the file, because the sandbox of the whole process cannot tell the
frontend from its own shell. oh-my-pi adds the write denies `~/.omp/agent/config.yml` and
`~/.omp/agent/extensions`.

`harness install` exits with status 2 on a policy file with an unknown key, a missing key or
frontend, a value that is not a list of strings, a path that does not start with `~/`, or a path
with a `..` segment, which could leave the home directory. The message names the key or the path.

## The rendering rules

`srt_settings` gives one frontend's object, with the keys `network` and `filesystem` and no other:

| key | value |
|:--|:--|
| `network.allowedDomains` | the template's, in order |
| `network.deniedDomains` | the template's, or `[]` where it has none; `srt` refuses a file without the key |
| `network.allowLocalBinding` | the template's |
| `filesystem.allowWrite` | the template's, without each entry at or below another frontend's `state` path; then the frontend's `state`; then the real path of `$TMPDIR`, where it is set and not empty |
| `filesystem.denyWrite` | the template's, without the frontend's `own`; then its `deny_write` |
| `filesystem.denyRead` | the home directory; then the template's; then each path of `credentials.files`; without the frontend's `own` |
| `filesystem.allowRead` | `read.allow`; then the frontend's `state` |

Each `~` and `~/` prefix becomes the home directory, so the files hold absolute paths. A list holds
no entry twice, and the first occurrence keeps its place. "At or below" compares whole path
components: `~/.claude.json` is not below `~/.claude`. So no frontend's file allows a write to
another frontend's state. A glob of the template, such as `~/Research/**/.git/hooks`, passes
through after the expansion. The template's `excludedCommands` is not carried: under `srt` the
whole process is inside the sandbox, so no command can run outside it. The masked credentials of
`srt` are not used.

## The install

`harness install` renders the Claude Code settings template as it does for
`~/.claude/settings.json`, with the profile and the network overlay, and gives its `sandbox`
object to `srt_settings`. It writes each file as JSON indented by two spaces, with the keys in the
order above and a final newline. The files belong to no frontend's plan: a change of them prints
no restart line. A frontend that `[setup]` does not choose gets no file, and with no frontend
chosen the install renders no file. The install does not change what it writes to
`~/.claude/settings.json`. Because it renders the template with the network overlay for every
chosen frontend, a broken overlay stops the install with status 2 also when `claude` is not
chosen, for example an `allow` entry that is a URL.

With at least one frontend chosen, the install also copies the launcher `sandbox/agentbox` to
`~/.local/bin/agentbox` with mode 755, a directory that a session cannot write. With `claude`
chosen it writes Claude Code's override beside the settings files:

```text
~/.config/research-harness/sandbox/claude-inner-off.json   {"sandbox": {"enabled": false}}
```

A launcher whose mode differs from 755 is a change, as a file whose bytes differ is.

## The launcher agentbox

`agentbox` is a POSIX `sh` script that starts one CLI frontend under `srt`:

```sh
agentbox <frontend> [args...]
```

The frontends are the commands `claude`, `opencode`, `omp` and `agy`. `agentbox` runs

```sh
~/.local/bin/srt --settings ~/.config/research-harness/sandbox/<policy name>.json -- \
    <program> <extra> <args...>
```

with `exec`, so the exit status of `srt` is its own. The policy name is `antigravity` for `agy`
and the frontend's name otherwise. `<program>` is the path that `command -v` gives on the caller's
`PATH`, and the caller's arguments follow `<extra>`, each passed as one argument, unchanged. The
`--` ends the options of `srt`, which otherwise reads a `--settings` of the frontend as its own.

| frontend | `<extra>` | why |
|:--|:--|:--|
| `claude` | `--settings ~/.config/research-harness/sandbox/claude-inner-off.json` | Claude Code's own sandbox fails inside the sandbox of `srt`, so the override turns it off |
| `opencode` | `--standalone` | OpenCode runs its server as its own child inside the sandbox, not in a background service that a run outside the launcher could have started |
| `omp` | `--approval-mode yolo` | oh-my-pi runs its tools without a prompt; the sandbox of `srt` is the boundary |
| `agy` | nothing | |

The frontend gets `AGENTBOX=1` in its environment; every other variable stays the caller's.
`agentbox` runs only the `srt` in `~/.local/bin`, never one found on the `PATH`. So it starts
nothing before `harness setup` has installed `srt` in `~/.local/bin`.

`agentbox` exits with status 2, starts nothing and prints one line on stderr when:

- no frontend is named, or the name is not one of the four; the line lists the four;
- `AGENTBOX` is set, so it runs inside a launcher already;
- `~/.local/bin/srt` is not an executable file; the line names `harness setup`;
- the frontend's settings file, or for `claude` the override, is not a file; the line names the
  file and `harness install --apply`;
- `command -v` finds no program of the frontend's name;
- the frontend is `claude` and an argument is `--settings` or starts with `--settings=`: Claude
  Code keeps only the last `--settings`, so the caller's would replace the override and turn
  Claude Code's own sandbox on again. More settings go in the user settings instead.

`agentbox -h` and `agentbox --help` print the usage and exit 0.

## The pinned srt

`harness setup` installs `~/.local/bin/srt`, the `srt` that `agentbox` runs, with any frontend
chosen, from two files of the harness:

| file | what it holds |
|:--|:--|
| `sandbox/srt/package.json` | a private package with one dependency, `@anthropic-ai/sandbox-runtime` at exactly 0.0.81, and the override of `node-forge` to exactly 1.4.1 |
| `sandbox/srt/package-lock.json` | the tree that npm resolves from that file: srt 0.0.81, `node-forge` 1.4.1, `zod`, `commander` and `@pondwader/socks5-server`, each with its `resolved` URL on `registry.npmjs.org` and its sha512 `integrity` |

The srt package ships no lockfile of its own, so a pin of srt alone would leave its four
dependencies to the registry on each install. `npm ci` installs exactly the tree of the lockfile,
refuses a package whose bytes do not match its sha512, and fails on a lockfile whose dependencies
do not match those of `package.json`; it does not compare the override with the lockfile. The
override keeps `node-forge` at 1.4.1: srt asks for `^1.4.0`, and 1.4.0 has eleven advisories that
1.4.1 fixes.

The step copies both files into a scratch directory below `~/.local/share/research-harness/`,
beside `srt/`, and runs `npm ci --ignore-scripts --no-audit --no-fund` there with the `npm` of the
`PATH`, so no install script of a package runs. After npm exits 0 and has made
`node_modules/.bin/srt`, the step moves the directory to
`~/.local/share/research-harness/srt/0.0.81/`, links `~/.local/bin/srt` to
`~/.local/share/research-harness/srt/0.0.81/node_modules/.bin/srt`, and removes the directories
of other versions and the links below `srt/`. A file at `~/.local/bin/srt` is replaced by the
link. The settings template allows no write at or above `~/.local/share/research-harness` and
denies writes to `~/.local/bin`, so a Claude Code session can change neither the tree nor the
link.

The step fails, and writes nothing below `srt/` and nothing in `~/.local/bin`, when `npm` is not on
the `PATH`, when `node --version` is below 22.12.0, the `engines.node` of srt 0.0.81 (`npm ci`
only warns there), when npm exits non-zero, or when `~/.local/bin/srt` is a directory. For a
failed npm, the line holds the cause from npm's stderr: the text of its `npm error code` line and
its first `npm error` line of other text, such as
`code ENOTFOUND; network request to https://registry.npmjs.org/… failed`. It removes its scratch
directory in every case. A plan finds nothing to do, and has no such step, when
`srt/0.0.81/package-lock.json` holds the bytes of the shipped lockfile, `node_modules/.bin/srt`
exists, and `~/.local/bin/srt` links to it; so a change of the shipped lockfile installs again.
The Homebrew copy of srt, where one is installed, stays as it is.
