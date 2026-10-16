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

### K73 · Six public files cite a task file that the repository does not hold.

- location: `adapters/opencode/opencode.jsonc:31`
- evidence: `adapters/opencode/opencode.jsonc:31` cites `Tasks/Migrate the Claude Code project
  memory.md`, `agents/ci-triage.md:21` cites `~/Research/Tasks/Fix the packages that do not
  load.md`, `githooks/pre-commit:28` cites `~/Research/Tasks/Clear the Fatou lint backlog.md`,
  `rules/changelog.md:57` cites `Tasks/Decisions pending.md`, `scripts/parts-table.awk:39` cites
  `Tasks/Rewrite the reduced basis packages.md`, and `scripts/wiki-lint.jl:87` cites
  `Tasks/Stop Knowledge going stale.md`; `git ls-files` lists no `Tasks/` file. A reader of the
  public repository cannot open them. The harness's own `Tasks/` convention (`Tasks/CLAUDE.md`,
  `Board.base`, the test fixtures) is not such a citation.
- kind: docs
- found: 2026-10-16, the builder of publish part P6

### K74 · A `~` with no `/` after it passes the oh-my-pi path guard.

- location: `adapters/omp/guards.ts:207`
- evidence: `absolute()` expands `~` only before `/` or at the end of the path, and joins any
  other path to the working directory. So `read {"path": "~.netrc"}` and
  `read {"path": ":~.netrc"}` from `~/Research` pass the guard, as `~/Research/~.netrc`, while the
  path utilities of oh-my-pi 18.11.1 map `~foo` to `$HOME/foo`. That the `read` tool resolves
  its path through that function is not verified. Reproducer: the probe cases of
  `.scratch/critic/Harness-P7/edges.py` in the research root, run on a copy of the checkout.
- kind: defect
- found: 2026-10-16, the critic of publish part P7
