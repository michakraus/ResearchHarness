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

- location: `adapters/antigravity/guard.py:267`
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

- location: `adapters/antigravity/guard.py:217`
- evidence: `words()` splits the line with `shlex`, which keeps the newline of a backslash-newline
  in the word (`~/.ssh/id_\ned25519`), where the shell joins the two lines. On a fixture home the
  guard answers `deny` to `cat ~/.ssh/id_ed25519` and `ask` to `cat ~/.ssh/id_\<NL>ed25519` and
  to `cat ~/.config/gh/hosts\<NL>.yml` (`<NL>` a newline), which read the same files.
- kind: defect
- found: 2026-10-23, PR #76

### K90 · The path check of the Antigravity guard reads a `#` inside a word as a comment.

- location: `adapters/antigravity/guard.py:217`
- evidence: `shlex` starts a comment at a `#` inside a word, and the shell starts one only at the
  start of a word. On a fixture home the guard answers `deny` to `cat ~/.netrc` and `ask` to
  `cat x# ~/.netrc`, which reads `~/.netrc` (`bash -c 'echo x# ~/.netrc'` prints the expanded
  path).
- kind: defect
- found: 2026-10-23, PR #76

### K91 · A comment that ends in a backslash-newline hides the next line from the Bash rules of the Antigravity guard.

- location: `adapters/antigravity/guard.py:251`
- evidence: `segments()` reads no comment and drops the backslash-newline, so the first word of the
  next line joins the comment's word (`#git`), and no rule sees the command word. The shell ends
  the comment at the newline and runs the next line. On a fixture home the guard answers `deny`
  to `git push --force origin x` and `ask` to `echo #\<NL>git push --force origin x` (`<NL>` a
  newline), which runs the push.
- kind: defect
- found: 2026-10-23, PR #76

### K92 · The path check of the Antigravity guard reads no string argument and no substitution.

- location: `adapters/antigravity/guard.py:225`
- evidence: `refused_command()` checks the words of the line as it writes them. On a fixture home
  the guard answers `deny` to `cat ~/.netrc` and `ask` to `bash -c 'cat ~/.netrc'`, to
  `sh -c "cat ~/.config/gh/hosts.yml"` and to `cat $(printf ~/.ne)trc`, which read the denied
  files.
- kind: defect
- found: 2026-10-23, PR #76; the same class as K88

### K93 · No case covers the "outside single quotes" condition of the backslash-newline drop in `segments()` of the Antigravity guard.

- location: `adapters/antigravity/guard.py:251`
- evidence: the mutant that drops a backslash-newline inside single quotes too (`line[i:j]` →
  `line[i:j].replace("\\\n", "")` at `guard.py:256`) passes the adapter selftest and the `agy`
  cases of `hooks/probe.py`: "TOTAL 182 cases, 0 wrong". The mutant fails closed: it answers
  `deny` to `rm -rf '/\<NL>'` (`<NL>` a newline), where the head answers `ask`. A case
  `rm -rf '/\<NL>'` → `ask` closes the gap.
- kind: missing test
- found: 2026-10-23, PR #76

### K22 · Under OpenCode, a verify critic carries the round-1 rule of the council.

- location: `adapters/opencode/adapter.py:242-251`
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

- location: `.github/workflows/test.yml:224`
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

- location: `.github/workflows/test.yml:230`, `.githooks/pre-push:318-321`
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

- location: `lib/harness/units.py:164`
- evidence: Claude Code's sandbox lets a session write its working directory, which no entry of
  `sandbox.filesystem.allowWrite` of `settings/settings.proposal.json` names. `path_problems`
  fails a `PATH` element at or below `$TMPDIR`, `/var/folders` or `/private/var/folders`, but a
  working directory has no fixed value, so an element below a directory where a session may start,
  outside every `allowWrite` entry and in no `denyWrite` entry, passes the check. No unit's `PATH`
  holds such a directory. The user decided to keep it a recorded limit.
- kind: defect
- found: 2026-10-12, the critic of part D2

### K69 · No case shows a stray settings path with a lone surrogate.

- location: `adapters/claude/adapter.py:730`
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

### K73 · Three public files cite a task file that the repository does not hold.

- location: `adapters/opencode/opencode.jsonc:30`
- evidence: `adapters/opencode/opencode.jsonc:30` cites `Tasks/Migrate the Claude Code project
  memory.md`, `agents/ci-triage.md:21` cites `~/Research/Tasks/Fix the packages that do not
  load.md`, and `scripts/parts-table.awk:39` cites `Tasks/Rewrite the reduced basis packages.md`;
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

- location: `adapters/opencode/adapter.py:444`
- evidence: v2 (2.0.30) gives an agent the `execute` tool of Code Mode. In a decoy probe of
  2026-10-16, agents with `bash`, `edit`, `task`, `webfetch` and `websearch` denied still had it.
  Its catalog listed 14 of Kaimon's 33 MCP tools, and `search` inside `execute` finds the rest. The
  generated block has no rule that names `execute`. No probe called it, so whether a `kaimon_*`,
  `read` or `external_directory` rule applies to a call inside `execute` is not measured.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K77 · Under OpenCode v2 no rule of the generated block stops the `read` tool on a credential file inside the session's project root.

- location: `adapters/opencode/adapter.py:165`
- evidence: v2 (2.0.30) binds a `read` deny only in project-relative form: an absolute or `~/`
  pattern, in an agent or in `opencode.jsonc`, did not stop the `read` tool on a decoy in decoy
  probes of 2026-10-16, and a project-relative one did. The credential denies are absolute, so
  `external_directory` with `"*": "deny"` is what refuses them, and it consults only a path outside
  the project root. A session whose project root holds the file, for example one started in the
  home directory outside any git repository, meets neither rule. Not probed.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K78 · Under OpenCode v2 a `**/` `edit` deny probably does not stop the `edit` tool on a file in the project root.

- location: `adapters/opencode/adapter.py:425`
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

- location: `lib/harness/profile.py:793`
- evidence: `render_file` opens `pathlib.Path(path)`, so `harness render systemd/kaimon.service`
  run outside the checkout prints `FileNotFoundError: [Errno 2] No such file or directory:
  'systemd/kaimon.service'` and exits 1: `cmd_render` (lines 803–810) catches nothing, and `main`
  in `lib/harness/cli.py` catches only `HarnessError`. The verb contract of `harness --help` gives
  exit 1 to a dry run with something to change and exit 2 to a usage error or a failure. A
  redirect of the output leaves an empty file in place of the unit.
  `docs/src/components/other.md:89` gives the same relative form, `harness render
  systemd/<name>`, with no working directory.
- kind: defect
- found: 2026-10-19

### K80 · A profile with no `home` key, loaded with `HOME` set to the empty string, gets `home = "/"`.

- location: `lib/harness/profile.py:280`
- evidence: `expand_home` takes the default of `home` from `pathlib.Path.home()`, which gives
  `/` for an empty `HOME`, and `/` is an absolute path, so the profile loads and a `~/…` value
  loses its home directory. A profile of the required keys with `tree_agents = "~/a"`, loaded
  with `HOME=""`, gives `home` `/` and `tree_agents` `/a`, with no error.
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

- location: `lib/harness/doctor.py:697`
- evidence: `read()` returns None on any `OSError`, a `PermissionError` too, and `namespaces()`
  (`lib/harness/doctor.py:272-282`) reads None as a missing key. So a file that holds `0` and
  cannot be read gives `PASS  userns clone  absent: no limit`, not the `FAIL` of a file that
  holds `0`. procfs makes the file mode 0644, so no real machine is known to give this input.
- kind: defect
- found: 2026-10-20

### K83 · `harness doctor` counts a pre-release as its release.

- location: `lib/harness/doctor.py:135`
- evidence: `VERSION` reads the numbers only, and `tool()` (`lib/harness/doctor.py:329`) compares
  them with the minimum. `meets(numbers_of('julia version 1.13.0-rc1'), ('1.13',))` and
  `meets(numbers_of('8.21.0-rc1'), ('8.21',))` both give `True`, so a release candidate passes
  Julia ≥ 1.13 and gitleaks ≥ 8.21.
- kind: defect
- found: 2026-10-20

### K84 · No branch case of the pre-push hook has a stub chezmoi on its `PATH`.

- location: `lib/harness/profile.py:1679`
- evidence: `prepush_branch_cases` puts no `chezmoi` on the `PATH` of its cases. So a hook that
  moves the kit step above the branch exit at `.githooks/pre-push:524-526` passes every case. A
  removed `exit 0` is still caught, because the stub suite prints "the suite ran"
  (`lib/harness/profile.py:1718`, `1824`).
- kind: missing test
- found: #67

### K85 · With chezmoi and without shellcheck, the pre-push hook refuses a push to `main` while its own shellcheck step prints `skip`.

- location: `.githooks/pre-push:478`
- evidence: with chezmoi and without shellcheck, the kit tests exit 1 with "<test>: shellcheck is
  not on the PATH" (`examples/dotfiles/tests/update-check.py:1236-1239`,
  `examples/dotfiles/tests/check-check.py:1119-1122`,
  `examples/dotfiles/tests/driver-check.py:180`).
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

- location: `adapters/antigravity/guard.py:99`
- evidence: `WRITE_TOOLS` names the four write tools that the G0 probe of Antigravity saw:
  `write_file`, `edit_file`, `write_to_file` and `replace_file_content`. The binary also names
  `multi_replace_file_content`, which the probe did not see, and its `TargetFile` meets only the
  `deny` list. So `multi_replace_file_content` {`TargetFile`: `<repo>/.git/config`} gets `ask`,
  where `write_to_file` with the same path gets `deny`. A probe of the tool's arguments decides
  whether it joins `WRITE_TOOLS`.
- kind: found late
- found: 2026-10-23

### K94 · A new `mcp_config.json` holds Kaimon's token under the umask mode for a short time.

- location: `lib/harness/install.py:119`
- evidence: `install_file` writes the bytes with `dst.write_bytes(data)` (line 125) and sets the
  mode with `dst.chmod(mode)` (line 127) after it. A file that does not exist yet is created with
  the mode of the umask, 644 under the usual umask 022, so between the two calls another user can
  read the token that the Antigravity plan writes into `~/.gemini/config/mcp_config.json`.
- kind: defect
- found: #78

### K95 · The worktree rule of the Antigravity agents matches only `isolation: worktree`, with or without double quotes.

- location: `adapters/antigravity/adapter.py:737`
- evidence: `under_antigravity` uses the worktree rule when the frontmatter has `isolation:
  worktree` or the body matches `isolation: "?worktree`. `re.search(r'isolation: "?worktree', s)`
  is true for `isolation: worktree` and `isolation: "worktree"`, and false for
  `isolation: 'worktree'`, `isolation:worktree`, `"isolation": "worktree"` and the prose
  "worktree isolation". No agent of `agents/` uses one of the four missed forms, so no rendered
  agent changes.
- kind: defect
- found: #78

### K96 · The worktree rule of the OpenCode and oh-my-pi agents fires on the bare word `isolation`.

- location: `adapters/omp/adapter.py:453`
- evidence: `"isolation" in body` is true for any body that holds the word, so an agent that says
  "the caller spawned you without isolation" (`agents/julia-builder.md:86`) gets the worktree rule
  of its "Under OpenCode" or "Under oh-my-pi" section. The same test is at
  `adapters/omp/adapter.py:1557` and `adapters/opencode/adapter.py:269`.
- kind: defect
- found: #78

### K97 · The OpenCode skill rule says "Claude Code loads them for you" for a single skill.

- location: `adapters/opencode/adapter.py:266`
- evidence: the rule writes "Claude Code loads them for you" whatever the number of skills.
  `adapters/opencode/fixtures/expected/judge.md:23` shows it for the one skill `which-model`.
- kind: docs
- found: #78

### K98 · `gh pr review` from an Antigravity subagent may need a permission prompt.

- location: `agents/julia-pr-reviewer.md:68`
- evidence: `julia-pr-reviewer` posts its review with `gh pr review <n> --comment --body-file <f>`.
  `julia-pr-shepherd` spawns it (`agents/julia-pr-shepherd.md:99`) and posts with
  `gh pr comment` itself (line 215). In the app, a subagent's call of Kaimon's `ping` showed the
  app's dialog, as a call of the main agent does. No run of either agent under Antigravity has
  measured `gh pr review`, and no run has measured a subagent's prompt under `agy`.
- kind: not verified
- found: #78

### K99 · `sections()` of the Antigravity adapter repeats the section parser of the oh-my-pi adapter.

- location: `adapters/antigravity/adapter.py:716`
- evidence: `sections(text)` returns `{m.group(1): m.group(2).strip() for m in
  re.finditer(r"(?m)^## (\w+)\n(.*?)(?=^## |\Z)", text, re.S)}`, the same expression that
  `adapters/omp/adapter.py:442` writes inline for `UNDER-OMP.md`.
- kind: dead code
- found: #78

### K101 · A `config.json` with a key twice in one object loses the first value when the install merges the app's grants.

- location: `adapters/antigravity/adapter.py:652`
- evidence: `merge_grants` reads the file with `json_object`, which keeps the last value of a key.
  On `{"userSettings": {"theme": "dark", "theme": "light"}}` it returns
  `{"userSettings": {"theme": "light", "globalPermissionGrants": {…}}}` and raises no error, so
  the install exits 0. `merge_settings` of the CLI's `settings.json` does the same, and
  `merge_mcp` refuses a key twice in one object of `mcp_config.json` with exit 2.
- kind: defect
- found: #80

### K102 · A minified `config.json` comes back with spaces after each separator, so every install replaces it.

- location: `adapters/antigravity/adapter.py:672`
- evidence: `merge_grants` writes the file with `claude.dumps` and the file's indent, which is none
  for a file on one line, and `json` then writes `", "` and `": "`. On
  `{"a":1,"userSettings":{"globalPermissionGrants":{"allow":["command(git status)"],"deny":[],"ask":[]}}}`
  with that rule already in `allow`, it returns the same object with the spaces and a final
  newline added, so the bytes differ and the install lists the file as REPLACE and keeps a backup
  each time. Whether the app writes its `config.json` minified is not measured.
- kind: defect
- found: #80

### K103 · The Antigravity guard answers `ask`, not `deny`, to a command or a `multi_replace_file_content` call that writes `config.json` or an installed agent.

- location: `adapters/antigravity/adapter.py:382`
- evidence: `guard_paths` puts `~/.gemini/config/config.json` and `~/.gemini/config/agents/**` in
  the `edit` list, which the guard applies to the write tools only, not to the words of a command
  (`hooks/probe.py:1750`: "a read and a command word pass them"). On a fixture home the guard
  answers `deny` to `write_to_file` {`TargetFile`: `~/.gemini/config/config.json`} and `ask` to
  `run_command` {`CommandLine`: `cp /tmp/x ~/.gemini/config/config.json`}, to the same with
  `~/.gemini/config/agents/julia-critic.md`, and to `multi_replace_file_content` {`TargetFile`:
  either path}. The `multi_replace_file_content` half is K87.
- kind: defect
- found: #80

### K104 · A rule that the install once wrote into the Antigravity grants stays after the settings template drops it.

- location: `adapters/antigravity/adapter.py:634`
- evidence: `merge_grants` adds each rendered rule that a list lacks and removes no entry, because
  it cannot tell its own rules from the user's. A Kaimon tool or a command that the template moves
  from `allow` to `ask` or drops therefore stays in `config.json`'s `allow` list. The CLI's
  `settings.json` does not keep it: `merge_settings` sets its `permissions` to the rendered rules.
  Deny > Ask > Allow still applies a rule that moves to `deny` or `ask`.
- kind: defect
- found: #80

### K106 · `render_permissions` checks no entry of `sandbox.excludedCommands`, so a malformed one stops the install or renders a rule that allows every command.

- location: `adapters/antigravity/adapter.py:511`
- evidence: the loop takes `command.split()[0]` of each entry of
  `cfg.get("sandbox", {}).get("excludedCommands", [])` and checks nothing. An entry `""` raises
  `IndexError`, `excludedCommands: null` a `TypeError` and `sandbox: null` an `AttributeError`,
  each a traceback with exit 1. An entry `"*"` renders `command(*)`, and the app's documented rule
  syntax reads `*` as every command. The settings template holds none of them.
- kind: defect
- found: #84

### K107 · A terminal hangup or a SIGTERM to the pre-push hook does not reach its suite.

- location: `githooks/pre-push.jl:56`
- evidence: `run_suite` starts the suite with `Cmd(cmd; detach = true)`, in a session of its own,
  and passes an interrupt on to the suite's process group: the case "pre-push: an interrupted hook
  stops its suite" sends SIGINT to the hook and sees the suite end. A hangup of the terminal goes
  to the terminal's session, which does not hold the suite, and a SIGTERM ends the hook's `julia`,
  which has no handler for it. In both cases the suite and the test process of `Pkg.test` go on as
  orphans. A handler that passes these signals on as well trades one orphan case for another.
- kind: defect
- found: 2026-10-26, the critic of the hook programs

### K108 · The 60 s box of `fatou lint` signals `fatou` alone, so a child of `fatou` that holds the output pipe holds the stage past the box.

- location: `githooks/pre-commit.jl:43`
- evidence: `run_boxed` sends SIGTERM, and SIGKILL 5 s later, to the process `p` only, and then
  reads the pipe to its end. A child that inherits the pipe and outlives `p` keeps the pipe open,
  and the read waits for it. `fatou` is one native binary, and no child of it is known.
- kind: defect
- found: 2026-10-26, the critic of the hook programs

### K109 · A SIGKILL of `harness test` leaves its running parts as orphans, and frees its slot while they run.

- location: `lib/harness/testrun.py:164`
- evidence: `run_part` starts each part with `start_new_session=True`, and the run stops the
  parts' process groups only from Python: on an error, an interrupt, a SIGTERM or a SIGHUP. A
  SIGKILL ends the run with no handler, so each running part goes on, and the 300 s limit, which
  the run keeps, no longer applies to it. The kernel frees the run's slot at once, so a third run
  can start beside the orphans.
- kind: defect
- found: 2026-10-26, the critic of the test runner

### K110 · `changed` runs `git diff` with no `timeout=`.

- location: `lib/harness/testrun.py:113`
- evidence: `subprocess.run(["git", "diff", "--name-status", …], cwd=root, capture_output=True,
  text=True, check=False)` names no `timeout`, so a `git` that does not end holds
  `harness test --changed` with it. No `git diff` that hangs is known, and no configuration of
  the repository checks for a `timeout=` yet.
- kind: not verified
- found: 2026-10-26, the critic of the test runner

### K111 · No case of the `protection` part runs `gh()`.

- location: `lib/harness/protection.py:113`
- evidence: with `check=False` changed to `check=True` in the `subprocess.run` of `gh()`,
  `bin/harness test protection` still prints `part protection: 7 cases, 0 wrong`. So no case
  shows that a failed `gh` call reaches the retry and the `GhError`, and not a
  `CalledProcessError`.
- kind: missing test
- found: 2026-10-27, the critic of the strict-Python part

### K112 · Six branches of the pre-push hook have no case that fails when they change.

- location: `.githooks/pre-push:236`
- evidence: each of these mutants, applied alone with `harness mutate` and the parts `profile`
  and `environment`, survives, and the differential of the hook's 24 pushes (nine early pushes and
  the 15 runs of the profile part's cases) gives `0 differ` for each: the remote SHA of a branch
  never excluded (`:236`), the range of a push to `main` always the SHA alone (`:294`), the
  messages of an empty commit list sent to `git log` (`:328`), a leak found on a push to `main`
  not refusing it (`:359`), the `BAD` lines of a failed suite not printed (`:381`), and a change
  of `Project.toml` selecting no Julia test (`:496`). The cases of the hook are
  `prepush_case` and `prepush_branch_cases` of `lib/harness/profile.py`, which run no push to
  `main` with a leak, with an earlier `main` or with a failing suite, and no branch push whose
  remote SHA is on no branch of `origin`; the bash hook had the same cases.
- kind: missing test
- found: 2026-10-29
