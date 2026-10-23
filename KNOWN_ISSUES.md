# Known issues

### K13 · A `write` path in a header nested twice passes the oh-my-pi path guard.

- location: `adapters/omp/guards.ts:327`
- evidence: oh-my-pi's `write` tool unwraps a hashline header twice (`Zje` in `execute`, and again
  in `SL` when it resolves the path), so `{"path": "[[~/.omp/agent/config.yml]]"}` writes
  `~/.omp/agent/config.yml`. `writePath` unwraps once, and the guard checks
  `[~/.omp/agent/config.yml]` as a relative path, which no rule matches. The same holds for
  `[[~/.claude/hooks/gh-api-writes.py#1A2B]#1A2B]`. The user decided to land the guard with this
  gap: oh-my-pi is not used before the sandbox launcher exists, and the launcher's profile then
  checks the real path.
- kind: defect
- found: 2026-10-06

### K14 · The oh-my-pi path guard misreads a `cd` with a redirection, an assignment, `time`, or a chained `cd`.

- location: `adapters/omp/guards.ts:274`
- evidence: from `~/Research`, the guard passes `cd >/dev/null && cat .netrc`,
  `cd 2>/dev/null; cat .netrc`, `X=1 cd && cat .netrc` and `time cd; cat .netrc`: a redirection
  target counts as the directory of the `cd`, and `X=1` and `time` are not in `LEAD`. From a
  subdirectory, `cd .. && cd .. && cat .netrc` and `cd .. && cat ../.netrc` pass: each `cd` target
  and each later word resolves against the session's directory, not against the directory that the
  earlier `cd` set. Each command reads `~/.netrc`. No `bash.patterns` rule allows a bare `cd`
  segment, so `omp -p` refuses the first four and an interactive run asks. The user decided to land
  the guard with this gap, as for K13.
- kind: defect
- found: 2026-10-06

### K88 · The Antigravity guard applies no Bash rule to a command that a string argument, ANSI-C or locale quoting, or a variable or substitution holds.

- location: `adapters/antigravity/guard.py:249`
- evidence: `guard.py` matches the template's Bash denies and asks on the words of each segment as
  the line writes them, and does not run the shell's expansions. On a fixture home it answers
  `deny` to `git push --force origin x` and `ask` to each of these lines, which run the same push:
  `bash -c 'git push --force origin x'`, the same with `sh -c` and `zsh -c`,
  `eval 'git push --force origin x'`, `git push $'--force' origin x`,
  `git push $"--force" origin x`, `g=git; $g push --force origin x` and
  `$(echo git) push --force origin x`. In the desktop app, which reads no `permissions`, such a
  push then runs unless the app's own settings refuse it. The user decided to land the guard with
  this limit of a text-pattern rule; the sandbox stays the containment.
- kind: defect
- found: 2026-10-23

### K89 · The path check of the Antigravity guard keeps a backslash-newline inside a word.

- location: `adapters/antigravity/guard.py:179`
- evidence: `words()` splits the line with `shlex`, which keeps the newline of a backslash-newline
  in the word (`~/.ssh/id_\ned25519`), where the shell joins the two lines. On a fixture home the
  guard answers `deny` to `cat ~/.ssh/id_ed25519` and `ask` to `cat ~/.ssh/id_\<NL>ed25519` and
  to `cat ~/.config/gh/hosts\<NL>.yml` (`<NL>` a newline), which read the same files.
- kind: defect
- found: 2026-10-23, PR #76

### K90 · The path check of the Antigravity guard reads a `#` inside a word as a comment.

- location: `adapters/antigravity/guard.py:182`
- evidence: `shlex` starts a comment at a `#` inside a word, and the shell starts one only at the
  start of a word. On a fixture home the guard answers `deny` to `cat ~/.netrc` and `ask` to
  `cat x# ~/.netrc`, which reads `~/.netrc` (`bash -c 'echo x# ~/.netrc'` prints the expanded
  path).
- kind: defect
- found: 2026-10-23, PR #76

### K91 · A comment that ends in a backslash-newline hides the next line from the Bash rules of the Antigravity guard.

- location: `adapters/antigravity/guard.py:216`
- evidence: `segments()` reads no comment and drops the backslash-newline, so the first word of the
  next line joins the comment's word (`#git`), and no rule sees the command word. The shell ends
  the comment at the newline and runs the next line. On a fixture home the guard answers `deny`
  to `git push --force origin x` and `ask` to `echo #\<NL>git push --force origin x` (`<NL>` a
  newline), which runs the push.
- kind: defect
- found: 2026-10-23, PR #76

### K92 · The path check of the Antigravity guard reads no string argument and no substitution.

- location: `adapters/antigravity/guard.py:190`
- evidence: `refused_command()` checks the words of the line as it writes them. On a fixture home
  the guard answers `deny` to `cat ~/.netrc` and `ask` to `bash -c 'cat ~/.netrc'`, to
  `sh -c "cat ~/.config/gh/hosts.yml"` and to `cat $(printf ~/.ne)trc`, which read the denied
  files.
- kind: defect
- found: 2026-10-23, PR #76; the same class as K88

### K93 · No case covers the "outside single quotes" condition of the backslash-newline drop in `segments()` of the Antigravity guard.

- location: `adapters/antigravity/guard.py:216`
- evidence: the mutant that drops a backslash-newline inside single quotes too (`line[i:j]` →
  `line[i:j].replace("\\\n", "")` at `guard.py:221`) passes the adapter selftest and the `agy`
  cases of `hooks/probe.py`: "TOTAL 182 cases, 0 wrong". The mutant fails closed: it answers
  `deny` to `rm -rf '/\<NL>'` (`<NL>` a newline), where the head answers `ask`. A case
  `rm -rf '/\<NL>'` → `ask` closes the gap.
- kind: missing test
- found: 2026-10-23, PR #76

### K22 · Under OpenCode, a verify critic carries the round-1 rule of the council.

- location: `adapters/opencode/adapter.py:291-297`
- evidence: `preamble` adds "Round 1 has three critics here, `1a`, `1b` and `1c` … your probe
  directory is `round-1a/`, `round-1b/` or `round-1c/`" to the agent that a council is keyed on.
  The council of `examples/models.toml` and the draft `models.toml` is keyed on `julia-critic`,
  which `OPENCODE-DELTA.md` also spawns alone for a verify round, so the rendered verify critic
  gets the round-1 rule with no condition. OpenCode is not in use; part W3 of the agent
  configuration plan fixes it. A fix changes the preamble and the fixtures in
  `adapters/opencode/fixtures/expected/`.
- kind: defect
- found: 2026-10-08

### K28 · A `file://~/…` path passes the `edit` and `ask` lists of the oh-my-pi path guard.

- location: `adapters/omp/guards.ts:343`
- evidence: `refusedToolPath` converts a `file://` URL with `fileURLToPath`, which throws
  `ERR_INVALID_FILE_URL_HOST` on `file://~/.claude/hooks/x.py`, because `~` is read as a host. The
  guard then checks the URL as written, as a path relative to the working directory, and no rule
  matches it. So
  `write {"path": "file://~/.claude/hooks/x.py"}` passes the `edit` list, and
  `write {"path": "file://~/.claude/workflows/w.js"}` passes the `ask` list; each should block.
  Reproducer: the probe cases of `.scratch/critic/Harness-L/edges2.py` in the research root, which
  report 2 wrong. Whether oh-my-pi itself resolves `file://~` to the home directory is not
  verified.
- kind: defect
- found: 2026-10-09

### K36 · A whole-history gitleaks scan is red until the history is rewritten.

- location: `.github/workflows/test.yml:124`
- evidence: the root commit `a78062a` holds 166 `home-path` findings. The `leaks` job scans the
  whole history on a `workflow_dispatch` on `main`, on a forced push to `main` (the `before`
  SHA is not in the clone), and on a new `main` on a remote, and each of these runs is red until
  the history is rewritten.
- kind: defect
- found: 2026-10-09

### K37 · `useDefault = true` brings gitleaks' default global path allowlists into `.gitleaks.toml`.

- location: `.gitleaks.toml:8`
- evidence: gitleaks' default configuration allows some paths for every rule, `.svg` files
  among them. A home path `/Users/<name>` in an `.svg` file passes both gitleaks checks of the
  pre-push hook (the fixture case `svg` of the critic of part E2, round 1b).
- kind: defect
- found: 2026-10-09

### K38 · `gitleaks git` exits 0 on a `--log-opts` range that it cannot read.

- location: `.github/workflows/test.yml:131`, `.githooks/pre-push:90`
- evidence: `gitleaks git --log-opts=<a range it cannot read>` prints `fatal: Invalid revision
  range` and still exits 0 with "no leaks found". Both `gitleaks git` calls, of the CI step
  *gitleaks over the pushed range* and of the pre-push hook, rely on its status. The CI step
  fails anyway, through the next line, `git log --format=%B "$range" | gitleaks stdin`, under
  `set -o pipefail`. The hook's range `<sha> --not --remotes=origin` is always readable.
- kind: defect, upstream behaviour
- found: 2026-10-09, by the critic of part E3

### K61 · No test runs the real macOS `ps` against a deleted server binary.

- location: `scripts/julia-update-test.jl`, the `ps` stub in `fixture`
- evidence: the macOS half of `julia-update.jl` reads the server's binary with `ps -o comm=`, as
  before the Linux change. The test stubs `ps`, because the agent sandbox refuses the real `ps`
  and `kill -0` (EPERM). That `ps -o comm=` still prints the full path after the binary is deleted
  rests on the base behaviour, not on a test. A live server's path was read by hand:
  `ps -o comm= -p <pid>` printed the full path of the julia binary of the juliaup release.
- kind: not verified
- found: 2026-10-11

### K71 · The PATH check of the units does not place a session's working directory, which the live sandbox lets the session write.

- location: `lib/harness/units.py:152`
- evidence: Claude Code's sandbox lets a session write its working directory, which no entry of
  `sandbox.filesystem.allowWrite` of `settings/settings.proposal.json` names. `path_problems`
  fails a `PATH` element at or below `$TMPDIR`, `/var/folders` or `/private/var/folders`, but a
  working directory has no fixed value, so an element below a directory where a session may start,
  outside every `allowWrite` entry and in no `denyWrite` entry, passes the check. No unit's `PATH`
  holds such a directory. The user decided to keep it a recorded limit.
- kind: defect
- found: 2026-10-12, the critic of part D2

### K69 · No case shows a stray settings path with a lone surrogate.

- location: `adapters/claude/adapter.py:698`
- evidence: `stray_warnings` escapes each whole line, so a lone surrogate in the path is escaped
  as one in the rule is. A case cannot make such a path on macOS: APFS refuses a name that is not
  UTF-8 (`OSError: [Errno 92] Illegal byte sequence`). The rule case in
  `install_cases.target_cases` covers the escape.
- kind: not verified
- found: 2026-10-15, the critic of publish part P1

### K72 · The named-colour scan of `docs:check` passes a colour inside a longer string.

- location: `docs/scripts/check-site.mjs:275`
- evidence: `colourIn` refuses a CSS named colour only as a whole quoted string or after `fill`,
  `stroke` or `color`. With `const B = { border: '1px solid red' }` or
  `<rect style="background: red" />` in a file of `docs/.vitepress/theme/figures/`,
  `node scripts/check-site.mjs` exits 0.
- kind: defect
- found: 2026-10-16, the critic of publish part P5

### K73 · Four public files cite a task file that the repository does not hold.

- location: `adapters/opencode/opencode.jsonc:30`
- evidence: `adapters/opencode/opencode.jsonc:30` cites `Tasks/Migrate the Claude Code project
  memory.md`, `agents/ci-triage.md:21` cites `~/Research/Tasks/Fix the packages that do not
  load.md`, `rules/changelog.md:57` cites `Tasks/Decisions pending.md`, and
  `scripts/parts-table.awk:39` cites `Tasks/Rewrite the reduced basis packages.md`;
  `git ls-files` lists no `Tasks/` file. A reader of the
  public repository cannot open them. The harness's own `Tasks/` convention (`Tasks/CLAUDE.md`,
  `Board.base`, the test fixtures) is not such a citation.
- kind: docs
- found: 2026-10-16, the builder of publish part P6

### K74 · `mutate.jl --warm` is unsound for a mutant that changes a method signature.

- location: `scripts/mutate-worker.jl:99`
- evidence: a warm worker restores a mutant by re-`include`ing the file, and an `include` cannot
  remove a method that the previous copy defined. Measured on part L-a of the solver package
  (2026-10-16, Julia 1.13.2, `MUTATE_WARM_MIN=100`): the narrowing mutant `N5` — `buffer`'s value
  method narrowed from `StaticArray` to `StaticVector` — read `SURVIVED` in the warm run and
  `CAUGHT` in a single-mutant cold run of the same list and the same units; the widening mutant
  `V1` left a live method after its restore, so the worker's final baseline failed and 31 of 32
  mutants read `UNKNOWN` (`1 CAUGHT, 0 SURVIVED, 31 UNKNOWN, 0 INVALID, of 32`). A cold run of the
  same list on the same tree gives 32 CAUGHT, 0 SURVIVED. The warm mode's own note in
  `build-part/evidence.md` already sends a survivor to a cold re-run; a *signature* mutant needs
  the cold run for every verdict, not only for a survivor.
- kind: defect
- found: 2026-10-16, the fix builder of part L-a of the solver package

### K75 · A `~` with no `/` after it passes the oh-my-pi path guard.

- location: `adapters/omp/guards.ts:207`
- evidence: `absolute()` expands `~` only before `/` or at the end of the path, and joins any
  other path to the working directory. So `read {"path": "~.netrc"}` and
  `read {"path": ":~.netrc"}` from `~/Research` pass the guard, as `~/Research/~.netrc`, while the
  path utilities of oh-my-pi 18.11.1 map `~foo` to `$HOME/foo`. That the `read` tool resolves
  its path through that function is not verified. Reproducer: the probe cases of
  `.scratch/critic/Harness-P7/edges.py` in the research root, run on a copy of the checkout.
- kind: defect
- found: 2026-10-16, the critic of publish part P7

### K76 · Under OpenCode v2 an agent with `bash: deny` still has the `execute` tool, and no probe shows that a `permission` rule binds a tool called inside it.

- location: `adapters/opencode/adapter.py:391`
- evidence: v2 (2.0.30) gives an agent the `execute` tool of Code Mode. In a decoy probe of
  2026-10-16, agents with `bash`, `edit`, `task`, `webfetch` and `websearch` denied still had it.
  Its catalog listed 14 of Kaimon's 33 MCP tools, and `search` inside `execute` finds the rest. The
  generated block has no rule that names `execute`. No probe called it, so whether a `kaimon_*`,
  `read` or `external_directory` rule applies to a call inside `execute` is not measured.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K77 · Under OpenCode v2 no rule of the generated block stops the `read` tool on a credential file inside the session's project root.

- location: `adapters/opencode/adapter.py:154`
- evidence: v2 (2.0.30) binds a `read` deny only in project-relative form: an absolute or `~/`
  pattern, in an agent or in `opencode.jsonc`, did not stop the `read` tool on a decoy in decoy
  probes of 2026-10-16, and a project-relative one did. The credential denies are absolute, so
  `external_directory` with `"*": "deny"` is what refuses them, and it consults only a path outside
  the project root. A session whose project root holds the file, for example one started in the
  home directory outside any git repository, meets neither rule. Not probed.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K78 · Under OpenCode v2 a `**/` `edit` deny probably does not stop the `edit` tool on a file in the project root.

- location: `adapters/opencode/adapter.py:374`
- evidence: v2 (2.0.30) matches a `read` pattern against the path relative to the project root,
  with `*` crossing `/` and both ends anchored: `**/*.pem` did not stop a read of `x.pem` in the
  root, and its root form `*.pem` did, in decoy probes of 2026-10-16. `with_root_forms` adds the
  root form to the `read` rules only, so the `edit` denies `**/.git/**`, `**/.mcp.json`,
  `**/.claude/settings.json` and `**/.claude/settings.local.json` have none
  (`adapters/opencode/opencode.jsonc:165`), and `.git/` and `.mcp.json` of the project root
  are the cases that matter. That the `edit` tool uses the same match is not probed. A root form
  `.git/**` must also not stop an edit that a session needs.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K79 · `harness render` reads a relative template path from the working directory, and a missing template ends in a traceback with exit 1.

- location: `lib/harness/profile.py:361`
- evidence: `render_file` opens `pathlib.Path(path)`, so `harness render systemd/kaimon.service`
  run outside the checkout prints `FileNotFoundError: [Errno 2] No such file or directory:
  'systemd/kaimon.service'` and exits 1: `cmd_render` (lines 371–378) catches nothing, and `main`
  in `lib/harness/cli.py` catches only `HarnessError`. The verb contract of `harness --help` gives
  exit 1 to a dry run with something to change and exit 2 to a usage error or a failure. A
  redirect of the output leaves an empty file in place of the unit.
  `docs/src/components/other.md:89` gives the same relative form, `harness render
  systemd/<name>`, with no working directory.
- kind: defect
- found: 2026-10-19

### K80 · A profile with no `home` key, loaded with `HOME` set to the empty string, gets `home = "/"`.

- location: `lib/harness/profile.py:120`
- evidence: `expand_home` takes the default of `home` from `pathlib.Path.home()`, which gives
  `/` for an empty `HOME`, and `/` is an absolute path, so the profile loads and a `~/…` value
  loses its home directory. A profile `x = "~/a"` loaded with `HOME=""` gives
  `{'x': '/a', 'home': '/'}`, with no error.
- kind: defect
- found: 2026-10-20

### K81 · The `home-path` rule of `.gitleaks.toml` finds a macOS home path but no Linux home path.

- location: `.gitleaks.toml:13`
- evidence: the regex names both `/Users` and `/home`, but with gitleaks 8.30.1 and this config,
  `gitleaks dir` over a one-line file `/Users/<name>/x` reports `leaks found: 1`, and over a
  one-line file `/home/<name>/x` reports `no leaks found` (with the same user name in both). So
  the Linux branch of the rule finds nothing. The CI step *gitleaks over the templates rendered
  with examples/profile.toml* renders under the runner's Linux home directory, so this step finds
  no home path in the renders.
- kind: defect
- found: 2026-10-20

### K82 · `harness doctor` reads an unreadable `unprivileged_userns_clone` as absent.

- location: `lib/harness/doctor.py:541`
- evidence: `read()` returns None on any `OSError`, a `PermissionError` too, and `namespaces()`
  (`lib/harness/doctor.py:234-239`) reads None as a missing key. So a file that holds `0` and
  cannot be read gives `PASS  userns clone  absent: no limit`, not the `FAIL` of a file that
  holds `0`. procfs makes the file mode 0644, so no real machine is known to give this input.
- kind: defect
- found: 2026-10-20

### K83 · `harness doctor` counts a pre-release as its release.

- location: `lib/harness/doctor.py:112`
- evidence: `VERSION` reads the numbers only, and `tool()` (`lib/harness/doctor.py:286`) compares
  them with the minimum. `meets(numbers_of('julia version 1.13.0-rc1'), ('1.13',))` and
  `meets(numbers_of('8.21.0-rc1'), ('8.21',))` both give `True`, so a release candidate passes
  Julia ≥ 1.13 and gitleaks ≥ 8.21.
- kind: defect
- found: 2026-10-20

### K84 · No branch case of the pre-push hook has a stub chezmoi on its `PATH`.

- location: `lib/harness/profile.py:1001`
- evidence: `prepush_branch_cases` puts no `chezmoi` on the `PATH` of its cases. So a hook that
  moves the kit step above the branch exit at `.githooks/pre-push:124-127` passes every case. A
  removed `exit 0` is still caught, because the stub suite prints "the suite ran"
  (`lib/harness/profile.py:1032`, `1085`).
- kind: missing test
- found: #67

### K85 · With chezmoi and without shellcheck, the pre-push hook refuses a push to `main` while its own shellcheck step prints `skip`.

- location: `.githooks/pre-push:239`
- evidence: with chezmoi and without shellcheck, the kit tests exit 1 with "<test>: shellcheck is
  not on the PATH" (`examples/dotfiles/tests/update-check.py:920-923`,
  `examples/dotfiles/tests/check-check.py:949-952`, `examples/dotfiles/tests/driver-check.py:141`).
  The hook then refuses the push, but its own shellcheck step prints `skip`. This is what clause 8
  of the kit's update path and K8 of the kit's plan ("The kit's tests run in a CI job of their
  own") decide. The other choice is a K8 change for the user.
- kind: defect
- found: #67

### K86 · A `signing_key` that is not a string stops the render of `dotfiles-merge`.

- location: `examples/dotfiles/dot_local/bin/executable_dotfiles-merge.tmpl:18`
- evidence: the template pipes `get $host "signing_key"` into `shellQuote`. With chezmoi 2.73.2,
  a `.chezmoidata` file `signing_key = 5` and the template `{{ .signing_key | shellQuote }}` give
  `wrong type for value; expected string; got int64`, and exit 1.
- kind: found late
- found: #67

### K87 · A `multi_replace_file_content` call passes the `edit` and `ask` lists of the Antigravity guard.

- location: `adapters/antigravity/guard.py:84`
- evidence: `WRITE_TOOLS` names the four write tools that the G0 probe of Antigravity saw:
  `write_file`, `edit_file`, `write_to_file` and `replace_file_content`. The binary also names
  `multi_replace_file_content`, which the probe did not see, and its `TargetFile` meets only the
  `deny` list. So `multi_replace_file_content` {`TargetFile`: `<repo>/.git/config`} gets `ask`,
  where `write_to_file` with the same path gets `deny`. A probe of the tool's arguments decides
  whether it joins `WRITE_TOOLS`.
- kind: found late
- found: 2026-10-23
