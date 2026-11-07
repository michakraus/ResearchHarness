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

Nothing runs under `srt` yet. A launcher that starts a frontend under `srt` with its file is a
later change; until then the files have no effect.

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
frontend, a value that is not a list of strings, or a path that does not start with `~/`. The
message names the key or the path.

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
`~/.claude/settings.json`.
