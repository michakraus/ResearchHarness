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
| `frontend.<name>.own` | the template's deny entries that the frontend reads itself: its own credential files, by name, and a file that it reads only, which a write deny above it keeps read-only |
| `frontend.<name>.read_files` | files below a read deny directory that the frontend reads and does not write |
| `frontend.<name>.network` | hosts that the frontend itself reaches, which its file adds to the template's `allowedDomains` |
| `frontend.<name>.mach_lookup` | macOS services, each by its exact name, that the frontend itself looks up over XPC or Mach |

The read limit denies reads of the whole home directory and allows the paths of `read.allow`
again. A path that the template denies stays hidden inside an allowed path: in `srt` a deny inside
an allowed path wins. Each frontend's `own` lifts its own credential files from the deny lists of
its file alone, and every frontend that does not name a file in its `own` still denies reads of
it:

| frontend | `own` |
|:--|:--|
| `claude` | `~/.claude.json`, `~/.claude/.credentials.json`, `~/.config/anthropic/credentials` |
| `opencode` | `~/.local/share/opencode/auth.json`, `~/.local/share/opencode/mcp-auth.json`, `~/.config/kaimon/auth-token` |
| `omp` | `~/.omp/agent/agent.db`, `~/.omp/agent/agent.db-wal`, `~/.omp/agent/.env`, `~/.config/kaimon/auth-token` |
| `antigravity` | `~/.gemini/jetski-standalone-oauth-token` |

Kaimon's token `~/.config/kaimon/auth-token` is shared: OpenCode reads it in its configuration,
and oh-my-pi reads it in the header command of its connection to Kaimon. Neither writes it, and
the write deny `~/.config` above it stays in both files, so the token stays read-only. The files
of `claude` and `antigravity` deny its read: Claude Code and Antigravity keep Kaimon's bearer in
their own configuration, `~/.claude.json` and `~/.gemini/config/mcp_config.json`.

Claude Code writes `~/.claude.json` itself; a write deny of it would stop the whole process under
`srt`. The cost is that a command that a frontend runs can also read the frontend's own files, and
write those that the frontend writes, because the sandbox of the whole process cannot tell the
frontend from its own shell.

Claude Code reads its Anthropic profile in `~/.config/anthropic/`. Before a token refresh it makes
the lock directory `~/.config/anthropic/credentials.lock`, and the refresh rewrites a file in
`~/.config/anthropic/credentials`. So `claude`'s `state` holds both paths, and its `own` holds the
credentials directory, which the template denies to every other frontend. `agy` keeps its Google
login in the login keychain, which the read limit hides; its file
`~/.gemini/jetski-standalone-oauth-token` is in `antigravity`'s `own` and denied to every other
frontend.

OpenCode's `read_files` are its three provider tokens, `gwdg-token`, `opendesign-token` and
`tokenharbor-token` below `~/.config/api-keys`, which its configuration reads by file. A token has
no deny entry of its own, so `own` cannot lift it; and `~/.config` is a write deny, so the token
stays read-only. No other frontend has a `read_files` entry. oh-my-pi adds the write denies
`~/.omp/agent/config.yml` and `~/.omp/agent/extensions`.

`claude`'s `network` is `platform.claude.com`, where Claude Code refreshes its sign-in token, and
`antigravity`'s is `agy`'s three hosts: `oauth2.googleapis.com`, where it refreshes its login
token, `daily-cloudcode-pa.googleapis.com`, where it checks its eligibility and calls its model,
and `www.googleapis.com`, where it reads the account. The other two frontends have an empty
`network`. An entry is `host` or `host:port`: `host` is
`localhost`, a name of two or more labels, or `*.` before such a name, and `port` is 1 to 65535
with no leading zero. Each form is one that `srt` takes in `allowedDomains`, so no entry makes
`srt` refuse the file. The user's own hosts for a frontend go in a `[frontend.<name>]` table of the
overlay `network.toml` beside the profile ([The profile](../profile.md)), not in this file.

`omp`'s `mach_lookup` starts with `mul-xpc (Apple)_OpenStep`, the macOS spell service. oh-my-pi's
typo detection, the setting `spelling.typoDetection`, which is on by default, asks it for each word
of the prompt. `srt`'s profile allows a fixed list of services, without this one, so the lookup
fails and AppKit prints the refusal into the terminal. The service receives the prompt's words and
can write learned words to `~/Library/Spelling`. The name holds the language of the system's
spelling setting: `mul` is *automatic by language*, and a fixed language has another name, which
needs its own entry.

Every frontend's `mach_lookup` holds `com.apple.trustd.agent`, the trust service: it is the whole
list of `claude`, `opencode` and `antigravity`, and follows the spell service in `omp`'s. `gh`,
which every frontend runs, and `agy` are Go programs, and on macOS Go checks a TLS certificate
through this service; without it every request of either fails with `x509: OSStatus -26276`.
`srt` names the service a possible path for data out of the sandbox, and allows it otherwise only
with its setting `enableWeakerNetworkIsolation`.

`harness install` exits with status 2 on a policy file with an unknown key, a missing key or
frontend, a value that is not a list of strings, a path that does not start with `~/`, a path
with a `..` segment, which could leave the home directory, a `network` entry of another form, or
a `mach_lookup` entry that is empty or holds `*` or a control character: `srt` reads a trailing
`*` as a prefix of names, so the policy names each service whole. The message names the key or
the path.
It also exits with status 2 on a `read_files` path that is itself an entry of the frontend's read
denies, compared as paths after the `~` expansion, so `~/x/`, `~//x` and `~/./x` are `~/x`, and
`~/` is the home directory; such a file goes in `own`.

## The rendering rules

`srt_settings` gives one frontend's object, with the keys `network`, `filesystem` and `allowPty`
and no other:

| key | value |
|:--|:--|
| `network.allowedDomains` | the template's, in order; then the frontend's `network` of the policy; then that of the overlay's `[frontend.<name>]` table; without each entry of the policy or the overlay whose host, its `:port` cut off, an entry of `deniedDomains` without a port matches |
| `network.deniedDomains` | the template's, or `[]` where it has none; `srt` refuses a file without the key |
| `network.allowLocalBinding` | the template's |
| `network.allowMachLookup` | the frontend's `mach_lookup`, in order, each name once; no such key where it is empty |
| `filesystem.allowWrite` | the template's, without each entry at or below another frontend's `state` path; then the frontend's `state`; then the real path of `$TMPDIR`, where it is set and not empty |
| `filesystem.denyWrite` | the template's, without the frontend's `own` and without each literal entry other than the home directory that lies strictly above a path of the frontend's `state`; then its `deny_write` |
| `filesystem.denyRead` | the home directory; then the template's; then each path of `credentials.files`; without the frontend's `own`; each literal entry other than the home directory that lies strictly above a path of the frontend's `read_files` written as the entry followed by `/*`, in its place |
| `filesystem.allowRead` | `read.allow`; then the frontend's `state`; then its `own`; then its `read_files` |
| `allowPty` | `true`, for every frontend; `srt` then allows pseudo-terminals, which the frontend's terminal user interface needs, on macOS only ([The launcher `agentbox`](../safeguards/sandbox.md#the-launcher-agentbox)) |

Each `~` and `~/` prefix becomes the home directory, so the files hold absolute paths. A list holds
no entry twice, and the first occurrence keeps its place. "At or below" compares whole path
components: `~/.claude.json` is not below `~/.claude`. So no frontend's file allows a write to
another frontend's state. A glob of the template, such as `~/Research/**/.git/hooks`, passes
through after the expansion.

`srt` emits the write denies after the write allows, so a write deny above a `state` path would
refuse every write to it. A frontend's file therefore leaves out each literal write deny of the
template that lies strictly above one of its `state` paths, compared as paths after the `~`
expansion, so `~/x/` and `~//x` are `~/x`. The home directory and a glob stay, and so does an entry
equal to a `state` path unless `own` names it. `srt` denies a write by default, so without the
entry a write below it passes only where `allowWrite` names the path. In the shipped files this
leaves the write deny `~/.config` out of `claude`'s file alone, which keeps the template's write
deny below it, `~/.config/systemd/user`.

A file below a read deny directory is read by name, through a glob. `srt` emits a literal read
deny that lies inside a read allow after the allows, so a file allow below it never takes effect;
it emits a glob read deny without each file allow that the glob covers. So in OpenCode's file the
literal `~/.config/api-keys` becomes `~/.config/api-keys/*`, and the three tokens join
`allowRead`; every other frontend's file keeps the literal entry. The glob ends in `/*`, not
`/**`: `srt` strips a trailing `/**` before it tells a glob from a literal, so `D/**` is the
literal `D` again. `D/*` covers everything below `D` and not `D` itself, so OpenCode can list the
names in `~/.config/api-keys` and read no other file there. An entry that holds `*`, `?`, `[` or
`]` is a glob already and stays as it is, and the home directory is the read limit and is never
converted. The `own` files join `allowRead` for the same reason: oh-my-pi's `~/.omp/agent/.env`
lies below the template's glob `~/**/.env`, and only a file allow lifts it there.

A frontend's `network` entries reach its own file alone. A deny entry without a port matches a
host as it does in the network lists (`lib/harness/network.py`), case folded: the same host, any
host for `*`, and a host or `*.` form below `*.X`. A deny entry with a port leaves the entry in
place, and `srt`, which checks `deniedDomains` first, refuses that port alone. An entry that the
template's list already holds stays once, at the template's place.

The template's `excludedCommands` is not carried: under `srt` the whole process is inside the
sandbox, so no command can run outside it. The masked credentials of `srt` are not used.

## The install

`harness install` renders the Claude Code settings template as it does for
`~/.claude/settings.json`, with the profile and the network overlay, and gives its `sandbox`
object to `srt_settings`. It writes each file as JSON indented by two spaces, with the keys in the
order above and a final newline. The files belong to no frontend's plan: a change of them prints
no restart line. A frontend that `[setup]` does not choose gets no file, and with no frontend
chosen the install renders no file. The install does not change what it writes to
`~/.claude/settings.json`. Because it renders the template with the network overlay for every
chosen frontend, a broken overlay stops the install with status 2 also when `claude` is not
chosen, for example an `allow` entry that is a URL. It also exits with status 2 on a `network`
entry of any frontend, chosen or not, once one is chosen, from the policy or the overlay, whose
host matches a `fetch` host of the network lists as a deny entry would, because a command of that
frontend would reach the host; a `fetch` host that a `deny` entry without a port removes is no
conflict. The message names the frontend's key, the entry and the host.

With at least one frontend chosen, the install also copies the launcher `sandbox/agentbox` to
`~/.local/bin/agentbox` and the gh wrapper `scripts/gh-token.py` to `~/.local/bin/gh`, each with
mode 755, a directory that a session cannot write ([The forge tokens](#the-forge-tokens)). With
`claude` chosen it writes Claude Code's override beside the settings files:

```text
~/.config/research-harness/sandbox/claude-inner-off.json   {"sandbox": {"enabled": false}}
```

A launcher or a wrapper whose mode differs from 755 is a change, as a file whose bytes differ is.

The install writes nothing through a symlink. So where `~/.local/bin` is a symlink and a frontend
is chosen, `harness install --apply` exits with status 2, writes nothing, and names the path and
the symlink.

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
`PATH` without each entry that matches `*/cmux-cli-shims/*` or `*/cmux-cli-shims`. In a cmux
terminal the first `claude` on the `PATH` is a shim of cmux, which `srt` cannot read; the shim
itself skips the same entries to find the real `claude` where the cmux wrapper is absent. A
`claude` under `agentbox` therefore runs without the cmux wrapper. The filter decides only which
program runs: the program gets the caller's `PATH` unchanged. The caller's arguments follow
`<extra>`, each passed as one argument, unchanged. The `--` ends the options of `srt`, which
otherwise reads a `--settings` of the frontend as its own.

| frontend | `<extra>` | why |
|:--|:--|:--|
| `claude` | `--settings ~/.config/research-harness/sandbox/claude-inner-off.json` | Claude Code's own sandbox fails inside the sandbox of `srt`, so the override turns it off |
| `opencode` | `--standalone` | OpenCode runs its server as its own child inside the sandbox, not in a background service that a run outside the launcher could have started |
| `omp` | `--approval-mode yolo` | oh-my-pi runs its tools without a prompt; the sandbox of `srt` is the boundary |
| `agy` | nothing | |

The frontend gets `AGENTBOX=1`, the three cache variables below and the variables of the forges
([The forge tokens](#the-forge-tokens)) in its environment; every other variable stays the
caller's, but `GITLAB_ACCESS_TOKEN` and `OAUTH_TOKEN`, which `agentbox` removes. `agentbox` runs
only the `srt` in `~/.local/bin`, never one found on the `PATH`. So it starts nothing before
`harness setup` has installed `srt` in `~/.local/bin`.

Each run makes one new directory with `mktemp -d "${TMPDIR:-/tmp}/agentbox.XXXXXX"`, below
`$TMPDIR`, or below `/tmp` where `TMPDIR` is unset or empty, with the subdirectories `npm`, `uv`,
`texmf-var`, `glab` and `gh`. The sandbox denies the caches of these tools in the home directory, so
`agentbox` sets and exports a cache variable for each, where the caller's variable is unset or
empty:

| variable | tool | value |
|:--|:--|:--|
| `npm_config_cache` | npm | `<run directory>/npm` |
| `UV_CACHE_DIR` | uv | `<run directory>/uv` |
| `TEXMFVAR` | LaTeX, for example the font cache of `lualatex` | `<run directory>/texmf-var` |

A caller's non-empty value stays. An empty value counts as unset: an empty `UV_CACHE_DIR` stops
`uv`, and an empty `npm_config_cache` sends npm to `~/.npm`. The settings file of every frontend
lets it write `/tmp` and the `$TMPDIR` of the install. Each run starts with empty caches, so npm
and uv download again and `lualatex` builds its font cache again. The run directory stays after
the run, because `agentbox` ends in `exec`; the system's cleaning of temporary directories removes
it.

`agentbox` exits with status 2, starts nothing and prints one line on stderr when:

- no frontend is named, or the name is not one of the four; the line lists the four;
- `AGENTBOX` is set, so it runs inside a launcher already;
- `~/.local/bin/srt` is not an executable file; the line names `harness setup`;
- the frontend's settings file, or for `claude` the override, is not a file; the line names the
  file and `harness install --apply`;
- `command -v` finds no program of the frontend's name on the `PATH` without the cmux entries;
- what `command -v` gives does not start with `/`: a shell function, for example a bash function
  that the caller exports and that macOS's `/bin/sh` imports, or, where `/bin/sh` is `dash`, a
  program in a relative `PATH` entry; the line names the program and what was found;
- the frontend is `claude` and an argument is `--settings` or starts with `--settings=`: Claude
  Code keeps only the last `--settings`, so the caller's would replace the override and turn
  Claude Code's own sandbox on again. More settings go in the user settings instead;
- `mktemp` cannot make the run directory, for example because `$TMPDIR` is not a directory; the
  line names the directory.

A refused run makes no run directory.

`agentbox -h` and `agentbox --help` print the usage and exit 0.

## The forge tokens

An agent's GitHub and GitLab operations use fine-grained tokens that you make, one for each
GitHub owner and one group access token for the GitLab group. The forge then limits each token
to its owner. The harness passes the tokens and does not filter the operations. git routes them
with its own owner-scoped credential sections and its `credential-store`, glab gets one token from
the environment, and only gh needs a wrapper, because gh reads one token for each host.

**The token store** is `~/.config/research-harness/forge/<host>/<name>.store`, one file for each
token, mode 600, in the format of git's `credential-store`: one line
`https://<user>:<token>@<host>`. `<name>` is an owner of the host, or `default` for every other
owner. The settings template denies reads of the store to Claude Code's sandbox (`denyRead` and
`credentials.files`), and each frontend's `own` in the policy file names it, so every frontend's
srt file allows its reads. git and gh run outside Claude Code's sandbox, and inside the sandbox of
`agentbox`.

**The rendered configuration.** Where the store exists, `harness install` writes
`~/.config/research-harness/forge.gitconfig`, mode 600, beside the store and not inside it: git
exits fatal on an `include` that it cannot read, and the store is a read deny of Claude Code's
sandbox. For each host directory, in the order of the names, it holds:

```ini
[credential "https://<host>"]
	helper =
	helper = "!f() { test \"$1\" = get && exec git credential-store --file <host>/default.store get; }; f"
[credential "https://<host>/<name>"]
	helper =
	helper = "!f() { test \"$1\" = get && exec git credential-store --file <host>/<name>.store get; }; f"
```

with the full path of each file, the host section's second `helper` only where `default.store`
exists, and one section of the second kind for each other store file. Where `github.com/` exists,
a last section `[credential "https://gist.github.com"]` holds only the empty `helper`, so no token
reaches a gist. git applies the helpers of every section whose URL matches, in the order of the
configuration, and an empty `helper` clears those before it. git matches the path by whole
components and with case. So each owner gets its own token, and every other owner of the host the
default's. A remote that spells the owner with another case gets the default, so a write to it
fails at the forge. The helper answers only `get`: a plain `store --file` erases the file's line
on a `reject`, for example after a token expires.

The install exits with status 2 and writes nothing, with one line that names the path, on a store
or host directory that it cannot list, on a store file, after symbolic links, that is no regular
file or that the group or others can read (the line names its mode), on a `<name>` outside
`[A-Za-z0-9-]+` or starting with `-`, on a store file whose bytes are not the one line
`https://<user>:<token>@<host>` with `<host>` its directory's name (a CR before the line feed
too), and on a host directory whose name is no host name in lower case. No message names a token.
Where `~/.gitconfig` holds no `include.path` of the rendered file, the install prints one notice
line and goes on.

The store and the rendered file are also a deny of the frontends' own read tools: the template's
`permissions.deny` holds `Read(/{home}/.config/research-harness/forge/**)`, and OpenCode's path
list `guard-paths.json`, which oh-my-pi and Antigravity also render, holds its path.

**The gh wrapper** `~/.local/bin/gh` ([`gh-token.py`](scripts.md#gh-token-py)) finds the
repository's owner, reads the owner's store file, else `default.store`, and runs the real gh with
`GH_TOKEN` set and `GITHUB_TOKEN` removed. With no token, or for a host other than `github.com`,
it removes both and sets `GH_CONFIG_DIR` to an empty directory, so gh reads no stored login. It
refuses a command, and runs nothing, where an argument that gh may read as `-R`, but that the
wrapper cannot read as `-R` with certainty, names another owner or host.

**glab and gh under `agentbox`.** The launcher exports `GIT_TERMINAL_PROMPT=0`, and
`GLAB_CONFIG_DIR` and `GH_CONFIG_DIR`, the empty directories `glab` and `gh` of the run directory,
in place of the caller's: glab and gh then read no stored login, and do not fail on their
configuration files, which srt denies. It removes the caller's `GITLAB_ACCESS_TOKEN` and
`OAUTH_TOKEN`. Where the store holds exactly one host directory other than `github.com/`, with
exactly one store file whose first line is `https://<user>:<token>@<host>`, `<host>` the
directory's name, and the user and the token not empty and free of `%` and white space, it exports
`GITLAB_HOST` as the directory's name and `GITLAB_TOKEN` as the token; glab sends that token only
to that host. Otherwise it removes the
caller's `GITLAB_TOKEN`, prints one line on stderr that names the store, and starts the frontend.

**The proxy's credentials and a credential manager.** srt's proxy URL carries a user name and a
password, `http://<user>:<password>@<loopback host>:<port>`. After a request through the proxy succeeds,
git passes those proxy credentials to `credential approve`, so every credential helper whose URL
matches the proxy gets a `store`. A credential manager left in `~/.gitconfig` matches it, and its
`store` writes to `~/.gitconfig` and to the keychain. srt refuses both writes, and git prints
`error: could not lock config file ~/.gitconfig: Operation not permitted`. The git operation goes
on: the line is noise, not a failure. git matches the port of a credential URL exactly, and the
proxy's port changes with each run, so no section of `forge.gitconfig` can clear the helper for
the proxy. Removing the credential manager from `~/.gitconfig` (step 5 below) ends the line.

**Your steps**, after the merge and before `harness install --apply`:

1. On GitHub, make one fine-grained token for each owner, each organisation and your account:
   resource owner that owner, all repositories, with the permissions Contents, Pull requests,
   Issues and Workflows read and write, and Actions, Checks, Commit statuses and Metadata read; no
   Gists permission. An organisation may have to approve a token.
2. On the GitLab instance, make one group access token of the group, with the scopes `api`,
   `read_repository` and `write_repository`, and a role that may create projects in the group. By
   GitLab's default that is Maintainer; the group's setting *Roles allowed to create projects*
   decides it.
3. Put each token into `~/.config/research-harness/forge/<host>/<owner>.store` as the one line
   `https://x-access-token:<token>@github.com` or `https://oauth2:<token>@<gitlab host>`, mode
   600, the directories mode 700. Make `github.com/default.store` a copy of, or a symbolic link
   to, your account's file.
4. Run `harness install --apply`.
5. Remove the broad credentials and route your terminal the same way: `gh auth logout`, replace
   glab's stored token by the group token (`glab auth login --hostname <gitlab host>`), erase the
   credential manager's GitHub and GitLab entries, and, in your dotfiles, remove the credential
   manager and `gh auth git-credential` helpers from `~/.gitconfig` and end its credential lines
   with `[include] path = ~/.config/research-harness/forge.gitconfig`. A Claude Code session runs
   git and gh outside its sandbox, so a broad credential that stays there stays usable.

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

## The probe battery

`scripts/probe-agentbox.py` checks that each frontend's settings file holds the boundary that the
policy means. Run it after `harness setup` and `harness install --apply`, from a plain terminal on
macOS: `srt` refuses a sandbox inside its own, so no session and no `agentbox` can run it.

```sh
python3.14 ~/Research/Harness/scripts/probe-agentbox.py [--out DIR] [--timeout S] [--no-model] [FRONTEND ...]
```

| option | what it does |
|:--|:--|
| `FRONTEND` | `claude`, `opencode`, `omp` or `agy`; with none named, all four |
| `--out DIR` | the directory of the report; by default `~/Research/.scratch/agentbox-probes/<UTC date and time>` |
| `--timeout S` | the time limit of each frontend probe, in seconds; 300 by default |
| `--no-model` | runs no frontend probe, so the run makes no model call |

The script exits with status 2, runs no probe and prints one line on stderr when `SANDBOX_RUNTIME`
or `AGENTBOX` is set, on a platform other than macOS, for an argument that is not a frontend or an
option, for `--out` or `--timeout` with no value, for a `--timeout` that is not a whole number
above 0 in ASCII digits, when `~/.local/bin/srt` or `~/.local/bin/agentbox` is not an executable
file, and when the settings file of a chosen frontend is missing. The line names the cause, and
`harness setup` or `harness install --apply` where one of them installs the file.

It runs four classes of probes for each chosen frontend:

| class | ids | how it runs | what it asks |
|:--|:--|:--|:--|
| listener | `L:<port>`, `L:<port>/path` | `curl` under `srt` | does each TCP listener on `127.0.0.1`, on `::1` or on every interface answer 401, 403 or 407 |
| read and write | R1–R9, W1–W14 | `/bin/sh -c` under `srt` | can a command read a secret, or write a hook, a launch agent, a shell start file or another frontend's state |
| network and process | N1–N9, X1–X8 | `/bin/sh -c` under `srt` | which hosts it reaches; can it open an app, send an Apple Event, mount, submit a launchd job, signal a process outside or start a sandbox of its own |
| frontend | F1–F7 | the frontend under `agentbox` | does it start, do its tools run inside the sandbox, does its own file tool read outside, does it reach Kaimon, and do its own gates hold |

A probe under `srt` runs with the script's environment and three variables that `agentbox`
exports too, so that `git`, `gh` and `glab` in a probe act as in a frontend: `GH_CONFIG_DIR` and
`GLAB_CONFIG_DIR` are the directories `gh` and `glab` below `<out>/run/<frontend>`, in place of
the caller's values, and `GIT_TERMINAL_PROMPT` is `0`. The script makes both directories empty,
outside `srt`, before the first probe of the frontend, so no frontend's probe reads a file that
another one's `gh` left.

The script lists the listeners with `lsof -nP -iTCP -sTCP:LISTEN`, outside `srt`, before the other
probes. It asks a listener on every interface (`*:<port>`) at `127.0.0.1:<port>`, and each
address and port once, at `/`. OpenCode's server takes a password, `OPENCODE_SERVER_PASSWORD`, and
`/` of it can answer without one, so a listener whose command is `opencode` is also asked at
`/path`, a route that OpenCode's binary names, in a row `L:<port>/path`. A listener answers as the
policy means with 401, 403 or 407: 407 is a proxy's request for authentication, as `srt`'s own
proxies give it. A shell probe runs as
`~/.local/bin/srt --settings ~/.config/research-harness/sandbox/<policy name>.json -- /bin/sh -c <probe>`
from `~/Research`, so its boundary is the settings file alone. A frontend probe runs the
frontend's non-interactive form under `agentbox`: `claude -p`, `opencode run --auto`, `omp -p` or
`agy --dangerously-skip-permissions -p`, with the prompt as the value of `-p`; past `--timeout` it
is stopped with its process group.
Every probe is harmless where the sandbox fails to stop it: a read prints a count, never content;
an append opens the file and writes nothing; a probe that creates a file deletes it. After each
frontend's shell probes, the script removes the launchd job of X4 and unmounts the devfs of X3
where either is left. The probes use a run directory `<out>/run`, with a `secret.txt`, a `.env` and
a git repository whose remote is this repository.

R4 lists `~/.config/api-keys` and expects `allowed` for `opencode`, whose file denies what lies
below the directory by a glob and not the directory itself, and `refused` for the others. R8
counts the frontend's own credential file, `~/.gemini/jetski-standalone-oauth-token` for `agy`,
and expects `allowed`. R9 counts `~/.config/anthropic/credentials/default.json`, Claude Code's
Anthropic credentials, and expects `allowed` for `claude` and `refused` for the other frontends.

A frontend probe holds its word when one line of its stdout or of its stderr, each stream split
into lines on its own, equals the word with its case once white space, then `` ` ``, `*`, `"` and
`'`, then one trailing `.`, then those four characters again are stripped from the line's ends. A
prompt asks for the word alone, so `**KAIMON-OK**.` holds `KAIMON-OK`, and an answer that quotes
it in a sentence, such as `KAIMON-OK was not printed`, lacks it.

Each probe gets one verdict:

| verdict | meaning |
|:--|:--|
| `match` | the result is the expected one |
| `MISMATCH` | the result is not the expected one |
| `absent` | the file or directory that the probe names does not exist, so the probe does not run |
| `skipped` | the probe does not apply: X5 with no listener on port 2828 of `127.0.0.1` or of every interface, the frontend probes with `--no-model` or with no program on the `PATH`, F6 with no plain `opencode` listening |
| `timeout` | the probe ran past its limit |
| `void` | F3, which expects a word to be missing, where F1 of the same frontend is not `match`: a frontend that never started also lacks the word, so the result proves nothing; its detail is `F1 shows no start` |
| an observation | F5 records the exit status of `agy --sandbox`, and F7 whether `~/.omp/agent/config.yml` changed during F1–F4 of `omp`: `unchanged`, `changed`, or `absent` where the file exists neither before nor after |

The expected value is the policy's intent, not what the current files do. So a `MISMATCH` is a
finding for the policy, the settings files or the launcher, and a run of a policy with a known
gap exits 1. A probe's output goes into the `detail` of its row on one line: whole up to 200
characters, else its first and its last 100 characters joined by ` … `, so a failure keeps its
cause and its last state. A frontend probe that is `MISMATCH` or `timeout` starts its detail at
the first line that holds a word ending in `Error` or `Exception` directly followed by `:`, or
that starts with `error:` after white space: a JavaScript runtime such as Bun can print the
source lines around a throw before the error's name and message. With no such line, and on every
other row, the detail comes from the whole output. The script writes `report.tsv`, every row with
the columns `frontend`, `id`, `expected`, `got`, `verdict` and `detail`, and `report.md`: the rows
other than `L:` as a table; a section `## Listeners` with one line per command, status and
verdict of the `L:` rows, which names the number of ports, the ports in numeric order and the
frontends; the count of each verdict over every row in `## Counts`; and the manual steps: change
the model once under `agentbox omp`, and, where F6 was skipped because no plain `opencode`
listened, run it again with a plain `opencode` in another terminal. It prints the path of
`report.md` last, and exits 0 when no probe is `MISMATCH` or `timeout`, and 1 otherwise; a `void`
alone does not make it 1.
