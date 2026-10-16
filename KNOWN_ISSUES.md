# Known issues

### K10 · Under OpenCode, an edit of the installed `~/.claude/rules/**` asks, where the settings template denies it.

- location: `adapters/opencode/adapter.py:161`
- evidence: `OPENCODE_ONLY_RULES` appends `"{home}/.claude/rules/**": "ask"` to the `edit` block,
  after the rules that `harness permissions` generates from the settings template. The generated
  `adapters/opencode/opencode.jsonc` holds `"{home}/.claude/rules/**": "deny"` at line 137 and the
  OpenCode-only `"ask"` at line 176, and OpenCode takes the last rule that matches (the comment at
  `adapters/opencode/adapter.py:432`). Every other installed path of the template's `Edit` denies
  is a deny under OpenCode too. The fix removes that entry, and the fixtures
  `adapters/opencode/fixtures/permission-block.txt` and `report.txt` with it.
- kind: found late
- found: 2026-10-06

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

### K16 · A leading `:` before `./` or `../` passes the oh-my-pi path guard.

- location: `adapters/omp/guards.ts:341`
- evidence: `refusedToolPath` drops a leading `:` only before `/` or `~`. oh-my-pi's path resolver
  (`KS`, which the `write` tool calls) also drops it before `./` and `../`, so
  `{"path": ":../.claude/hooks/gh-api-writes.py"}` from `~/Research` passes the guard, and
  `read {"path": ":../.netrc"}` does too (that the `read` tool resolves through `KS` is not
  verified).
- kind: found late
- found: 2026-10-06

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

### K26 · Under OpenCode, a `$OPENCODE_CONFIG_DIR/guard-paths.json` that is not JSON is ignored, and its `allow` list with it.

- location: `adapters/opencode/plugins/guards.ts:176`
- evidence: `lists()` refuses every `shell` call when the list beside the plugin is missing or
  not JSON, but `load` returns null for a local list that does not parse, and the plugin then
  runs with the global list only. With a valid local list `{"allow": ["{home}/Research/**"]}`,
  `cat /etc/hosts` is refused; with the same file cut to `{"allow": [`, it passes. v1 behaves the
  same way. Found by the critics of part W1, round 1.
- kind: defect
- found: 2026-10-09

### K27 · Under OpenCode, a leading space before `rtk ` hides the rest of the command from the guard scripts.

- location: `adapters/opencode/plugins/guards.ts:241`
- evidence: the guard checks the form without `rtk ` only when `command.startsWith('rtk ')`, on
  the command as given. So `rtk git add -A` is refused by `no-blind-stage.py`, but ` rtk git add -A`,
  with one leading space, passes. v1 behaves the same way. The path guard and the in-place check
  scan the whole command and are not affected. Found by the critics of part W1, round 1.
- kind: defect
- found: 2026-10-09

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

### K29 · No probe case reaches the `process.cwd()` fallback of the OpenCode guard plugin.

- location: `adapters/opencode/plugins/guards.ts:262`
- evidence: the guard takes the working directory of a call without `workdir` from
  `ctx.location.directory`, and from `process.cwd()` when `ctx.location` has no string
  `directory`. Every OpenCode case of `hooks/probe.py` gives the stub context a `location`. A
  mutant that replaces `: process.cwd()` with `: '/'` passes all 38 OpenCode cases of the probe. A case with no
  `location` in the stub context, the `node` working directory in the fixture repository, and
  `rm -rf build`, expecting a refusal, would catch it. Found by the verify critic of part W1.
- kind: missing test
- found: 2026-10-09

### K30 · No probe case gives the OpenCode guard plugin a `deny` decision.

- location: `adapters/opencode/plugins/guards.ts:120`
- evidence: the plugin refuses a guard's `permissionDecision` of `ask` or of `deny`. Only
  `gh-api-writes.py:228` and `rm-scope.py:245` print a decision, and both print `ask`, so no
  script reaches the `deny` half. A mutant that removes `|| hook?.permissionDecision === 'deny'`
  passes all 38 OpenCode cases of the probe. A fixture guard that prints a `deny` decision would catch it. Found by the
  verify critic of part W1.
- kind: missing test
- found: 2026-10-09

### K31 · `harness leaks --commits` labels a line hit in a path that git quotes with the quoted path.

- location: `lib/harness/profile.py:302`
- evidence: `added_lines` takes the path of a line from the `+++ ` header of `git show`, which
  git quotes for a path with a non-ASCII character or a `"`. A leak line in `café.txt` is
  reported at `"b/caf\303\251.txt":1`, not at `café.txt:1`. The hit still counts and still
  refuses the push; only the place label is wrong. Reproducer:
  `.scratch/critic/Harness-E2/round-2/label_probe.py` in the research root. Found by the verify
  critic of part E2, round 2.
- kind: defect
- found: 2026-10-09

### K32 · No case reaches `own_repository(repo)` in `cmd_leaks`.

- location: `lib/harness/profile.py:327`
- evidence: the mutant that calls `own_repository()` in place of `own_repository(repo)` (P8 of
  the critics of part E2) survives `bin/harness test`. In the pre-push hook `repo` is `REPO`, so
  the two calls agree there; a case would run `cmd_leaks` on a fixture repository whose `origin`
  differs from this checkout's. Found by the verify critic of part E2, round 2.
- kind: missing test
- found: 2026-10-09

### K33 · No case reaches the de-duplication of the `-m` paths or the second parent's column of `git diff-tree`.

- location: `lib/harness/profile.py:283-287`
- evidence: the mutants Q1 (`dict.fromkeys` removed) and Q2 (`--first-parent` added) both
  survive `commit_cases()`, `(15, 0)`. Neither turns a hit into no hit: Q1 only prints a path
  twice when an evil merge changes it against both parents. An evil-merge case that expects
  exactly one `:0` hit would catch both. Reproducer:
  `.scratch/critic/Harness-E2/round-3/own_mutants.py` in the research root, on a clone of
  `80fdc4a`. Found by the verify critic of part E2, round 3.
- kind: found late
- found: 2026-10-09

### K34 · No case reaches a line of a merge's combined diff in `added_lines`.

- location: `lib/harness/profile.py:299`
- evidence: the mutant D4 of the critics of part E2 (`parents, number = 1, int(hunk.group(2))`)
  survives `bin/harness test`, `977 cases, 0 wrong`. The merge case of `commit_cases` has no
  lines in its combined diff. A merge whose resolution adds a `LEAK` line that neither parent has
  would catch it. Found by the critics of part E2, round 1a, and again in round 3.
- kind: found late
- found: 2026-10-09

### K35 · No committed test covers the `origin` URL that the pre-push hook sets in its clone.

- location: `.githooks/pre-push:92`
- evidence: the hook runs `git remote set-url origin "$origin_url"` in the clone, so that
  `harness leaks --commits` allows the checkout's own `owner/name`. A mutant that drops the line
  (d3 of the critics of part E2) passes the hook in a real worktree. The only check is the
  fixture case `ownrepo` of the critic of part E2, round 1b, which is not committed.
- kind: missing test
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

### K39 · Two `run-tests.jl` runs of packages of one name, started in the same second, write one log and one times file.

- location: `scripts/run-tests.jl:343`
- evidence: the log, the times file and the one-process driver are
  `~/Research/.scratch/tests/<name>-<yyyymmdd-HHMMSS>-…`, with no process ID. Two `--jobs 2 core`
  runs of two fixtures with one basename, started together, both print
  `PASS in 12 s — log: …/jl_HrnNyd-20261009-130118-named.log`: one log for both. Each verdict
  comes from its own processes' exit codes, so it stays correct. The summary under it, the log
  and the times file can be the other run's. A `--jobs` run keeps its workers' files in a
  directory of its own (`mktempdir`). Found by the critic of part I1.
- kind: defect
- found: 2026-10-09

### K50 · A throw in the setup of a figure component does not stop the build.

- location: `docs/.vitepress/theme/figures/FigCard.vue:25`, `docs/.vitepress/theme/figures/WalkThrough.vue:16`
- evidence: the comment of `FigCard.vue` says that a card with too little room "stops the build".
  VitePress logs a throw in a component's setup during SSR and still prints `build complete`.
  With `<WalkThrough name="instal" />` in `daily-use.md`, `npm run docs:build` prints
  `Error: no walk-through instal…` and then `build complete in 1.89s.`, and the page has no
  figure. `docs:check` then names the missing title. A throw in a data loader does stop the
  build. Found by the critic of part J4.
- kind: defect
- found: 2026-10-10

### K51 · The effort check of a walk-through box accepts a spawn of any caller.

- location: `lib/harness/docs.py:279`
- evidence: a box with `effort` passes when any entry of `calls.toml` spawns its agent at that
  effort. The check does not compare the caller of that entry with the skill or agent of the
  walk-through, so a box of a skill that never spawns the agent at that effort passes. Found by
  the critic of part J4.
- kind: missing test
- found: 2026-10-10

### K53 · The colour scan of `docs:check` passes a named colour.

- location: `docs/scripts/check-site.mjs:246`
- evidence: the scan matches a hex literal, `rgb(` and `hsl(` only, as J2b defined it. With
  `const TOKEN = 'red'` in `walkthroughs.data.ts`, `docs:check` exits 0. Found by the critic of
  part J4.
- kind: defect
- found: 2026-10-10

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

### K66 · A public rule and skill cite a notes page that the repository does not hold.

- location: `rules/julia-code.md:256`
- evidence: `rules/julia-code.md:256` and `skills/julia-structure/SKILL.md:9`, `:62` and `:73`
  cite `Environment/Notes/Helpers-and-MCPs.md`; `git ls-files` lists no such file. The citations
  stay: `harness install` puts the rule and the skill into a tree where the page exists, and the
  pointer is how a session there finds the evidence. A reader of the public repository cannot open
  it.
- kind: docs
- found: 2026-10-15

### K67 · Three more public files cite a notes page that the repository does not hold.

- location: `adapters/opencode/opencode.jsonc:46`
- evidence: `adapters/opencode/opencode.jsonc:46` and `githooks/pre-commit:150` cite
  `Environment/Notes/Helpers-and-MCPs.md`, and `adapters/claude/CLAUDE.md:37` cites
  `Environment/Notes/Dynamic-Workflows.md`; `git ls-files` lists neither page. Found by the builder
  of the part that cleared K42 and K44, which names only `scripts/` and `agent-workflows/`.
- kind: docs
- found: 2026-10-15

### K68 · A stray settings file nested deeper than the JSON parser reads stops `harness install` with `RecursionError`.

- location: `adapters/claude/adapter.py:682`
- evidence: `stray_warnings` turns `OSError`, `ValueError`, `AttributeError` and `TypeError` into a
  warning, but not `RecursionError`. With `~/Research/.claude/settings.local.json` holding
  `"[" * 400000 + "]" * 400000`, `stray_warnings()` raises `RecursionError` on Python 3.14, so the
  dry run of `harness install` ends in a traceback and exit 1. Python 3.11 raises it from a depth
  of 1000. The settings verbs and the merge of `~/.claude/settings.json` refuse such a file with
  exit 2 (`json_object`); this read of the other settings files does not use it.
- kind: defect
- found: 2026-10-15, the builder of publish part P1, after its critic's finding on deep nesting

### K69 · No case shows a stray settings path with a lone surrogate.

- location: `adapters/claude/adapter.py:682`
- evidence: `stray_warnings` escapes each whole line, so a lone surrogate in the path is escaped
  as one in the rule is. A case cannot make such a path on macOS: APFS refuses a name that is not
  UTF-8 (`OSError: [Errno 92] Illegal byte sequence`). The rule case in
  `install_cases.target_cases` covers the escape.
- kind: not verified
- found: 2026-10-15, the critic of publish part P1

### K70 · `install.selftest()` prints a stray line `x.md  INSTALL` with no `ok` or `BAD` prefix.

- location: `lib/harness/install_cases.py:287`
- evidence: `python3 -c "from harness import install; install.selftest()"` from `lib/` prints
  `x.md                               INSTALL` just before the case "an OSError in the write is a
  HarnessError that names the target", on `699ad23` too. That case of `target_cases` calls
  `install.install_file(True, b"x\n", target, "x.md")` in-process, and `install_file` prints its
  plan line (`lib/harness/install.py:82`) before the write fails; the case does not capture
  stdout. The line is not a case and changes no count, but it reads as install output inside the
  case list.
- kind: defect
- found: 2026-10-16, the builder of publish part P3
