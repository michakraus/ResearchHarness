# Known issues

### K13 · A `write` path in a header nested twice passes the oh-my-pi path guard.

- location: `hooks/guard/frontends/omp.py:198`
- evidence: oh-my-pi's `write` tool unwraps a hashline header twice (`Zje` in `execute`, and again
  in `SL` when it resolves the path), so `{"path": "[[~/.omp/agent/config.yml]]"}` writes
  `~/.omp/agent/config.yml`. `write_path` unwraps once, and the guard checks
  `[~/.omp/agent/config.yml]` as a relative path, which no rule matches. The same holds for
  `[[~/.claude/hooks/gh-api-writes.py#1A2B]#1A2B]`. The user decided to land the guard with this
  gap, for oh-my-pi under the sandbox launcher. The launcher `sandbox/agentbox` runs the whole
  oh-my-pi process under srt, so its `write` tool too. The srt file of oh-my-pi denies writes to
  `~/.omp/agent/config.yml` (`sandbox/policy.toml:71`) and allows none below `~/.claude/hooks`;
  the probes W10 and W2 of `scripts/probe-agentbox.py` try the two places. The launcher is
  opt-in: an oh-my-pi started without it has only the guard, and the gap is open there.
- kind: defect
- found: 2026-10-06

### K14 · The oh-my-pi path guard misreads a chained `cd`.

- location: `hooks/guard/path_list.py:356`
- evidence: from a subdirectory of `~/Research`, the guard (`--from omp`) passes
  `cd .. && cd .. && cat .netrc` and `cd .. && cat ../.netrc`: each `cd` target and each later word
  resolves against the session's directory, not against the directory that the earlier `cd` set.
  Each command reads `~/.netrc`. No `bash.patterns` rule allows a bare `cd` segment, so an
  interactive run asks. The user decided to land the guard with this gap, as for K13. The guard
  refuses `cd >/dev/null && cat .netrc`, `cd 2>/dev/null; cat .netrc`, `X=1 cd && cat .netrc` and
  `time cd; cat .netrc` from `~/Research`.
- kind: defect
- found: 2026-10-06

### K88 · The Antigravity guard applies no Bash rule to a command whose program a variable or a substitution names.

- location: `hooks/guard/path_list.py:526`
- evidence: the guard matches the template's Bash denies and asks on the words of each segment,
  with quotes, ANSI-C and locale quotes and the scripts of `sh -c`, `bash -c`, `zsh -c` and `eval`
  read, and does not run the shell's other expansions. On a fixture home it answers `deny` to
  `git push --force origin x` and to `bash -c 'git push --force origin x'`, and `ask` to
  `g=git; $g push --force origin x`, which runs the same push. In the desktop app, which reads no
  `permissions`, such a push then runs unless the app's own settings refuse it. The user decided
  to land the guard with this limit of a text-pattern rule; the sandbox stays the containment.
- kind: defect
- found: 2026-10-23

### K92 · The path check of the Antigravity guard reads no substitution.

- location: `hooks/guard/path_list.py:379`
- evidence: `command_words()` reads the words of the line, with the scripts of `sh -c`, `bash -c`
  and `eval` read, and runs no expansion. On a fixture home the guard answers `deny` to
  `cat ~/.netrc` and to `sh -c "cat ~/.config/gh/hosts.yml"`, and `ask` to
  `cat $(printf ~/.ne)trc`, which reads the denied file.
- kind: defect
- found: 2026-10-23, PR #76; the same class as K88

### K22 · Under OpenCode, a verify critic carries the round-1 rule of the council.

- location: `adapters/opencode/adapter.py:262-270`
- evidence: `preamble` adds "Round 1 has three critics here, `1a`, `1b` and `1c` … your probe
  directory is `round-1a/`, `round-1b/` or `round-1c/`" to the agent that a council is keyed on.
  The council of `examples/models.toml` and the draft `models.toml` is keyed on `julia-critic`,
  which OpenCode's copy of the `build-part` skill also spawns alone for a verify round, so the
  rendered verify critic gets the round-1 rule with no condition. OpenCode is not in use; part W3
  of the agent configuration plan fixes it. A fix changes the preamble and the fixtures in
  `adapters/opencode/fixtures/expected/`.
- kind: defect
- found: 2026-10-08

### K28 · A `file://~/…` path passes the `edit` and `ask` lists of the oh-my-pi path guard.

- location: `hooks/guard/frontends/omp.py:144`
- evidence: `file_url` decodes a `file://` URL as Node's `fileURLToPath` does, which reads `~` in
  `file://~/.claude/hooks/x.py` as a host and gives no path. The guard then checks the URL as
  written, as a path relative to the working directory, and no rule matches it. So
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

- location: `.github/workflows/test.yml:230`, `.githooks/pre-push:330-333`
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

- location: `lib/harness/units.py:166`
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

### K73 · A public file cites a task file that the repository does not hold.

- location: `adapters/opencode/opencode.jsonc:30`
- evidence: `adapters/opencode/opencode.jsonc:30` cites `Tasks/Migrate the Claude Code project
  memory.md`; `git ls-files` lists no `Tasks/` file. A reader of the
  public repository cannot open it. The harness's own `Tasks/` convention (`Tasks/CLAUDE.md`,
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

- location: `hooks/guard/path_list.py:235`
- evidence: `expanded()` reads `~.netrc` as the home of a user `.netrc`, finds none, and the guard
  joins the path to the working directory. So `read {"path": "~.netrc"}` and
  `read {"path": ":~.netrc"}` from `~/Research` pass the guard, as `~/Research/~.netrc`, while the
  path utilities of oh-my-pi 18.11.1 map `~foo` to `$HOME/foo`. That the `read` tool resolves
  its path through that function is not verified. Reproducer: the probe cases of
  `.scratch/critic/Harness-P7/edges.py` in the research root, run on a copy of the checkout.
- kind: defect
- found: 2026-10-16, the critic of publish part P7

### K76 · Under OpenCode v2 an agent with `bash: deny` still has the `execute` tool, and no probe shows that a `permission` rule binds a tool called inside it.

- location: `adapters/opencode/adapter.py:456`
- evidence: v2 (2.0.30) gives an agent the `execute` tool of Code Mode. In a decoy probe of
  2026-10-16, agents with `bash`, `edit`, `task`, `webfetch` and `websearch` denied still had it.
  Its catalog listed 14 of Kaimon's 33 MCP tools, and `search` inside `execute` finds the rest. The
  generated block has no rule that names `execute`. No probe called it, so whether a `kaimon_*`,
  `read` or `external_directory` rule applies to a call inside `execute` is not measured.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K77 · Under OpenCode v2 no rule of the generated block stops the `read` tool on a credential file inside the session's project root.

- location: `adapters/opencode/adapter.py:177`
- evidence: v2 (2.0.30) binds a `read` deny only in project-relative form: an absolute or `~/`
  pattern, in an agent or in `opencode.jsonc`, did not stop the `read` tool on a decoy in decoy
  probes of 2026-10-16, and a project-relative one did. The credential denies are absolute, so
  `external_directory` with `"*": "deny"` is what refuses them, and it consults only a path outside
  the project root. A session whose project root holds the file, for example one started in the
  home directory outside any git repository, meets neither rule. Not probed.
- kind: not verified
- found: 2026-10-16, the `read` deny decoy probe

### K78 · Under OpenCode v2 a `**/` `edit` deny probably does not stop the `edit` tool on a file in the project root.

- location: `adapters/opencode/adapter.py:437`
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

- location: `lib/harness/profile.py:1712`
- evidence: `prepush_branch_cases` puts no `chezmoi` on the `PATH` of its cases. So a hook that
  moves the kit step above the branch exit at `.githooks/pre-push:532-534` passes every case. A
  removed `exit 0` is still caught, because the stub suite prints "the suite ran"
  (`lib/harness/profile.py:1751`, `1857`).
- kind: missing test
- found: #67

### K85 · With chezmoi and without shellcheck, the pre-push hook refuses a push to `main` while its own shellcheck step prints `skip`.

- location: `.githooks/pre-push:486`
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

- location: `adapters/omp/adapter.py:495`
- evidence: `"isolation" in body` is true for any body that holds the word, so an agent that says
  "the caller spawned you without isolation" (`agents/julia-builder.md:86`) gets the worktree rule
  of its "Under OpenCode" or "Under oh-my-pi" section. The same test is at
  `adapters/omp/adapter.py:1672` and `adapters/opencode/adapter.py:289`.
- kind: defect
- found: #78

### K97 · The OpenCode skill rule says "Claude Code loads them for you" for a single skill.

- location: `adapters/opencode/adapter.py:285`
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
  `adapters/omp/adapter.py:485` writes inline for `UNDER-OMP.md`.
- kind: dead code
- found: #78

### K103 · The Antigravity guard answers `ask`, not `deny`, to a command that writes `config.json` or an installed agent.

- location: `adapters/antigravity/adapter.py:397`
- evidence: `guard_paths` puts `~/.gemini/config/config.json` and `~/.gemini/config/agents/**` in
  the `edit` list, which the guard applies to the tools that write or edit a file only, not to the
  words of a command (`hooks/guard/path_list.py:599`). On a fixture home the guard answers `deny`
  to `write_to_file` and to `multi_replace_file_content` {`TargetFile`:
  `~/.gemini/config/config.json`} and `ask` to `run_command` {`CommandLine`:
  `cp /tmp/x ~/.gemini/config/config.json`} and to the same with
  `~/.gemini/config/agents/julia-critic.md`.
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

- location: `githooks/pre-push.jl:96`
- evidence: `run_suite` starts the suite with `Cmd(cmd; detach = true)`, in a session of its own,
  and passes an interrupt on to the suite's process group: the case "pre-push: an interrupted hook
  stops its suite" sends SIGINT to the hook and sees the suite end. A hangup of the terminal goes
  to the terminal's session, which does not hold the suite, and a SIGTERM ends the hook's `julia`,
  which has no handler for it. In both cases the suite and the test process of `Pkg.test` go on as
  orphans. A handler that passes these signals on as well trades one orphan case for another.
- kind: defect
- found: 2026-10-26, the critic of the hook programs

### K109 · A SIGKILL of `harness test` leaves its running parts as orphans, and frees its slot while they run.

- location: `lib/harness/testrun.py:168`
- evidence: `run_part` starts each part with `start_new_session=True`, and the run stops the
  parts' process groups only from Python: on an error, an interrupt, a SIGTERM or a SIGHUP. A
  SIGKILL ends the run with no handler, so each running part goes on, and the 300 s limit, which
  the run keeps, no longer applies to it. The kernel frees the run's slot at once, so a third run
  can start beside the orphans.
- kind: defect
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

- location: `.githooks/pre-push:248`
- evidence: each of these mutants, applied alone with `harness mutate` and the parts `profile`
  and `environment`, survives, and the differential of the hook's 24 pushes (nine early pushes and
  the 15 runs of the profile part's cases) gives `0 differ` for each: the remote SHA of a branch
  never excluded (`:248`), the range of a push to `main` always the SHA alone (`:306`), the
  messages of an empty commit list sent to `git log` (`:340`), a leak found on a push to `main`
  not refusing it (`:372`), the `BAD` lines of a failed suite not printed (`:394`), and a change
  of `Project.toml` selecting no Julia test (`:504`). The cases of the hook are
  `prepush_case` and `prepush_branch_cases` of `lib/harness/profile.py`, which run no push to
  `main` with a leak, with an earlier `main` or with a failing suite, and no branch push whose
  remote SHA is on no branch of `origin`; the bash hook had the same cases.
- kind: missing test
- found: 2026-10-29

### K113 · The shell-write check passes a target whose text starts with a scratch root and then climbs out of it with `..`.

- location: `hooks/guard/no_shell_file_write.py:338`
- evidence: `tree_write` returns False when the raw target starts with a scratch prefix, before it
  resolves `..`, so `echo x > /tmp/../<tree>/f.txt`, `echo x > $TMPDIR/../f.txt` and
  `echo x > ~/Research/.scratch/../Harness/f.jl` pass.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K114 · The shell-write check reads no `<>` redirection as a write.

- location: `hooks/guard/no_shell_file_write.py:44`
- evidence: `REDIRECT` matches `<>`, and `split` keeps a target only for an operator that does not
  start with `<`, so `echo x <> f.txt` in a work tree passes.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K115 · The shell-write check reads a command substitution inside a heredoc body as data.

- location: `hooks/guard/no_shell_file_write.py:142`
- evidence: `cut_heredocs` removes each body before the command is read, and the shell runs a
  `$( … )` in an unquoted heredoc body, so `cat <<EOF` with the body line `$(echo x > f.txt)`
  passes.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K116 · The staging check finds no `git add` behind a prefix word or inside a compound command, and misses some spellings of `.`.

- location: `hooks/guard/no_blind_stage.py:41`
- evidence: from a package work tree, `env git add -A`, `command git add -A`, `time git add -A`,
  `X=1 git add -A`, `! git add -A`, `{ git add -A; }`, `if true; then git add -A; fi`,
  `git add $'-A'`, `git add ./.` and `git add .//` pass the guard. The corpus holds no `$'…'` record for the staging check.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K117 · The rm check reads no recursive `rm` behind `sudo`, and none in `rm --r`.

- location: `hooks/guard/rm_scope.py:187`
- evidence: `decide` skips only assignments, `command`, `nohup` and `time` before the program,
  and `rm_arguments` takes only `--recursive` of the long options, so `sudo rm -rf ~` and
  `rm --r ~` pass the guard.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K118 · The `gh api` check finds no call behind `env` or an assignment, and the archive check none behind `env`.

- location: `hooks/guard/gh_api_writes.py:355`
- evidence: the `gh api` check needs the tool as a part's first word, and the archive check skips
  only assignments before `git`, so `env gh api -X DELETE x`, `GH_HOST=x gh api -X DELETE x` and
  `env git archive -o x HEAD` pass the guard. The same holds for the own-organisation rule of the
  review and comment writes: `env gh api repos/other-org/r/issues/3/comments -f body=x`,
  `A=1 gh api …` and `GH_HOST=example.com gh api …` with the same arguments pass.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K119 · The `gh api` check answers the first part that does not pass, so an `ask` before a `deny` is `ask`.

- location: `hooks/guard/gh_api_writes.py:369`
- evidence: `verdict_of` returns at the first part that asks, so
  `gh api -X POST repos/example-org/X/issues && gh api -X DELETE repos/example-org/X` is `ask`, not
  `deny`.
- kind: defect
- found: 2026-10-29, the critics of the guard core

### K151 · The `gh api` check reads a cluster of short flags such as `-if` or `-iq` as no option, so it can read another endpoint than `gh` sends to.

- location: `hooks/guard/gh_api_writes.py:150`
- evidence: `gh` reads `-if V` as `-i` and `-f V`, and `-iq V` as `-i` and `-q V`; `option` takes
  neither cluster as an option and reads `V` as the endpoint. So
  `gh api -if repos/own-org/r/issues/3=x/comments repos/other-org/r/issues/3/comments -f body=x`
  and the same command with `-iq` pass, while the command without the cluster asks.
- kind: defect
- found: 2026-11-09, the critics of the own-organisation rule of the `gh api` check

### K150 · Claude Code's guard does not read a `gh api` call behind a leading `rtk`.

- location: `hooks/guard/frontends/claude.py:48`
- evidence: OpenCode's table checks a command again with a leading `rtk ` removed; Claude Code's
  does not, so `rtk gh api -X DELETE repos/o/r`, `rtk gh api -X POST repos/o/r/issues -f title=x`
  and `rtk gh api repos/other-org/r/issues/3/comments -f body=x` pass, while the same commands
  without `rtk` are denied or ask.
- kind: defect
- found: 2026-11-09, the critics of the own-organisation rule of the `gh api` check

### K121 · What Claude Code does with a `PreToolUse` hook that passes its `timeout` is not measured here.

- location: `settings/settings.proposal.json:717`
- evidence: the template gives each guard hook `"timeout": 5`. If Claude Code reads a timeout as
  a non-blocking error, a guard that runs longer lets the call run. The probe holds the guard's
  commands of 1 MiB to 10 s, its `MIB_LIMIT`, and no probe of Claude Code itself
  shows the effect.
- kind: not verified
- found: 2026-10-29, the critics of the guard core

### K122 · The work-tree check passes a `git init` whose program name a quote splits, such as `g''it init x`.

- location: `hooks/guard/sandbox_semantics.py:439`
- evidence: `work_tree_check` reads the command only when its text holds `git`, and `g''it init x`
  does not; the shell runs it as `git init x`. In a workspace that is a work tree, Antigravity's
  guard answers `ask` with `BypassSandbox` true, where `git init x` is `deny`. The guard runs the
  same check for oh-my-pi and OpenCode, and the core's `check` filters the text the same way.
- kind: found late
- found: 2026-10-31, the critics of the Antigravity guard

### K124 · The oh-my-pi path guard reads no `cd` after `if`, and no `cd` whose directory a substitution makes empty, as a `cd` home.

- location: `hooks/guard/path_list.py:356`
- evidence: `cd_words` takes a `cd` as the first word of a part or after a word of `LEAD`, which
  holds no `if`, and reads `$(true)` as a directory. On a fixture home, with `~/.netrc` denied and
  the session in `~/Research`, the guard (`--from omp`) answers `deny` to ``cd `true`; cat .netrc``
  and passes ``if cd `true`; then cat .netrc; fi`` and `cd $(true); cat .netrc`, which read
  `~/.netrc`. The base's extension passes both too.
- kind: defect
- found: 2026-10-31, the critics of the OpenCode and oh-my-pi guard core

### K125 · The OpenCode path guard reads no `cd`, so a relative path after a `cd` home passes.

- location: `hooks/guard/frontends/opencode.py:114`
- evidence: `shell_calls` gives the call the `workdir` or the session's directory as its working
  directory, and the path list resolves a relative word against it, not against the directory
  that a `cd` in the command sets. On a fixture home, with `~/.netrc` denied and the session in `~/Research`, the guard
  (`--from opencode`) answers `deny` to `cat ~/.netrc` and passes `cd; cat .netrc` and
  ``cd `true`; cat .netrc``, which read `~/.netrc`. The base's plugin passes both too.
- kind: defect
- found: 2026-10-31, the critics of the OpenCode and oh-my-pi guard core

### K127 · The SessionStart handler of the Antigravity layer reads the drift hook's output with `json`, not `jsonio`.

- location: `adapters/antigravity/adapter.py:205`
- evidence: `TRANSLATE`, the handler that `hooks.json` runs as `python -c`, reads the output of
  `install-drift.py` with `json.loads(t)`, which keeps the last value of a key that an object
  holds twice and reads `NaN`. A `python -c` text has no `guard` package on its path, so it
  cannot import `guard.jsonio`, and ruff's ban of `json.loads` reads no code inside a string. The
  drift hook writes its output with `json.dumps`, so no such output of it is known.
- kind: defect
- found: 2026-10-31

### K128 · The stages of the Julia packages' pre-commit hook read the working tree, not the staged content.

- location: `githooks/pre-commit.jl:203`
- evidence: `formatting`, `lint`, `nfc`, `ast_grep`, `test_layout` and `load` read the files on
  disk. The hook refuses a commit in which a staged `.jl` file also has changes that are not
  staged, that is, one that `git diff --name-only` lists, before any stage runs (`unstaged`), so
  each stage reads the staged text of every staged `.jl` file. The refusal costs the user a
  workflow: a `.jl` file cannot be committed in part, with `git add -p` or `git commit -p`, while
  the rest of its edits stay on disk. It leaves three cases open. `load` loads the whole package
  from disk, and `test_layout` reads every file below `test/`, the `.jl` files of `src/` and the
  pages of `docs/src/` on disk, so an unstaged edit of a file that the commit does not stage, or
  a file that is not tracked, still changes their verdict. A staged file of another type below
  `test/` is checked by `test_layout` as it is on disk. A
  `.jl` file that becomes a symlink to a file that is not tracked passes the formatting and load
  stages on that file, and a fresh checkout has the symlink without its target, so the package
  can fail to load there. The full fix, which may deserve doing later, checks a copy of the
  index, for example from `git checkout-index` into a temporary directory, in every stage; it
  removes the refusal and closes the three cases. The shell hook that `pre-commit.jl` replaced
  read the working tree the same way.
- kind: defect
- found: 2026-10-31, a review of the hook rollout's pull requests

### K130 · The formatting stage of the Julia packages' pre-commit hook has no time limit.

- location: `githooks/pre-commit.jl:177`
- evidence: `formatted` calls JuliaFormatter's `format` in the hook's own process, one staged
  file at a time, with no limit. The lint stage and the load test run in `run_boxed`, with a
  limit of 60 s and 600 s; a staged file on which `format` does not end holds the commit until
  the user stops it. A whole-tree JuliaFormatter run has died inside SciML's `nest!` after 62
  minutes of CPU, as the header of `pre-commit.jl` records. The shell hook that `pre-commit.jl`
  replaced had no limit either. A fix runs the formatter in a child process under `run_boxed`,
  which loads JuliaFormatter once more per commit.
- kind: defect
- found: 2026-11-01, a review of the hook rollout's pull requests

### K131 · The time box of the Julia packages' pre-commit hook does not cap the output that it captures.

- location: `githooks/pre-commit.jl:93`
- evidence: `run_boxed` reads the whole output of the lint stage and of the load test into one
  string, `read(out, String)`, and the stdout and the stderr of the ast-grep stage into two, and
  its limit is one of time only: 60 s for `fatou lint` and `ast-grep`, and 600 s for the load. A
  program that prints without end within the limit fills the hook's memory before the limit stops
  it. A fix reads the stream in blocks and keeps the first part only, for example the first
  megabyte, which the stages print from anyway: the lint stage prints its lines, and the load test
  at most 20 of them. The ast-grep stage reads each line of its stdout as one JSON object and
  skips itself on a line that does not parse, so a cut inside a line skips the stage.
- kind: defect
- found: 2026-11-02, a review of the hook rollout's pull requests

### K132 · The time box of the Julia packages' pre-commit hook has no bound for a process in uninterruptible I/O.

- location: `githooks/pre-commit.jl:103`
- evidence: `run_boxed` sends the group SIGTERM at the limit and SIGKILL 5 s later, and waits
  for the program with `wait(p)`, which has no limit of its own. A process in uninterruptible
  I/O, such as a read from a network file system that does not answer, does not end on SIGKILL
  until the I/O returns, so the commit waits as long as the I/O does. The bound of 6 s after the
  SIGTERM covers the wait for the rest of the group, which comes after `wait(p)`, and not the
  wait for the program itself.
- kind: defect
- found: 2026-11-02, a review of the hook rollout's pull requests

### K133 · The pre-push hook of the Julia packages tests the working tree, not the commit that it pushes.

- location: `githooks/pre-push.jl:71`
- evidence: `suite` runs the tests in the repository's working tree, and `main` reads from the
  ref lines only whether a line pushes to `main` or `master`. The local SHA of the line is not
  checked out. So `git push origin topic:main` from a checkout of another branch tests that
  branch, and a change that is not committed takes part in the suite. A fix checks the pushed
  SHA out into a temporary worktree and runs the suite there, which costs a precompilation of
  the package in that tree.
- kind: defect
- found: 2026-11-02, a review of the hook rollout's pull requests

### K134 · The pre-push hook of a Julia project that is not a package ignores `test/Project.toml`.

- location: `githooks/pre-push.jl:75`
- evidence: for a `Project.toml` without a `name` or a `uuid`, `suite` runs
  `julia --project=. test/runtests.jl` in the root environment. `Pkg.test`, which a package
  gets, runs the tests in the environment of `test/Project.toml`; the fallback does not, so a test
  dependency that only `test/Project.toml` lists loads from the user's default environment where
  it is installed there, and fails to load otherwise. A project with a `name` and no `uuid` gets
  the fallback too, as the case "pre-push: a Project.toml with a name and no uuid runs
  test/runtests.jl" shows, although its `name` reads as a package.
- kind: defect
- found: 2026-11-02, a review of the hook rollout's pull requests

### K135 · The Julia packages' pre-commit and pre-push hooks can signal a freed group ID.

- location: `githooks/pre-commit.jl:107`
- evidence: `run_boxed` closes its `stop` timer after the program and the output reader end. A
  timer that fires before `close` still runs its callback: Julia's `_trywait`
  (`base/asyncevent.jl:164` on 1.13.3) returns `true` for a timer that is set, also when it is
  closed. So a program that ends within the last yield before `close(stop)` gets a normal
  return, and the callback then sends SIGTERM to its group ID, which the system can have given to
  another group, and starts a SIGKILL timer that nothing closes. A probe of 300 runs, each with
  the limit at the program's end time, found no late signal, so the race is not seen to happen.
  The SIGKILL timers have the same race: `close(killer[])` of `run_boxed`
  (`githooks/pre-commit.jl:112`) and `close(killer)` of `run_suite` in `pre-push`
  (`githooks/pre-push.jl:124`) do not stop a callback that is already queued, so its SIGKILL can
  reach the group ID after the box or the wait has ended. The wait of `run_suite` also checks the
  group with `group_alive`, by default `kill(-group, 0)` (`githooks/pre-push.jl:117`), and its
  `killer` sends SIGKILL to `-group` (`githooks/pre-push.jl:113`), on the raw group ID after the
  suite's leader is reaped, when the system can have given the ID to another group. No probe has
  been run for these.
- kind: not verified
- found: 2026-11-02, a review of the hook rollout's pull requests

### K137 · `srt_settings` raises a bare `KeyError` for a frontend that the policy does not name.

- location: `lib/harness/sandbox.py:243`
- evidence: `policy.frontends[frontend]` has no guard, so `srt_settings("codex", …)` ends with
  `KeyError: 'codex'`, not with a `HarnessError`. Every caller passes a name of `FRONTENDS`, and
  `load_policy` requires a table for each of them, so no command reaches it.
- kind: defect
- found: 2026-11-08, the review of the srt settings' pull request

### K138 · The shell checks of the guard do not read a word that an expansion makes, a script on standard input, or a script nested more than three levels deep.

- location: `hooks/guard/shell.py:310`
- evidence: the checks read quotes, ANSI-C and locale quotes, and the scripts of `sh -c`,
  `bash -c`, `zsh -c` (and the other shells of `SHELLS`) and `eval`, three levels deep, and run
  no other expansion. `guard --from claude` in a checkout of an own organisation answers `deny`
  to `bash -c 'git push --force-with-lease origin main'` and `pass` to each of these, which run
  the same push: `g=git; $g push --force-with-lease origin main`,
  `git p$(printf u)sh --force-with-lease origin main`, `o=--force-with-lease; git push $o origin
  main` and `echo 'git push --force-with-lease origin main' | sh`. The same holds for the other
  writes of the checks, such as `x=rm; $x -rf ~/Research/Papers`, and for a script four levels
  deep, such as `eval eval eval eval rm -rf ~/Research/Papers`. The check of a shell write and the
  check of a `git init` or `git clone` in a working tree read no script of `sh -c` or `eval`:
  `bash -c 'echo x > CHANGELOG.md'` and `bash -c 'git init probe'` pass in a working tree. The
  check of a shell write, and the misleading-error check where it reads a `$( … )` fragment, read
  an ANSI-C quote in bash's dialect only: `python3 $'\-'c "open('src/x.jl','w').write('x')"`
  passes, which zsh runs as `python3 -c`. fish's `-C` and `--init-command` scripts are not read.
  A lease push through `git -C $d` whose target is a default branch of that repository other than
  `main` and `master` asks rather than refuses: the check cannot read the directory. The sandbox
  stays the containment; for Antigravity, K88 is the same limit of its Bash rules.
- kind: defect
- found: 2026-11-08

### K139 · A long command with an ANSI-C quote can take the guard past the hook's time limit.

- location: `hooks/guard/shell.py:154`
- evidence: `readings` and `joined` read a text that holds `$'` or `$"` in three dialects, so such
  a command costs about three readings where another costs one. A probe of the third pre-PR
  verification, one process per run under a load average of 40 to 44, measured a 1 MiB command
  of `eval rm …` units with one `$'x'` at 7.1 s, against 3.2 s for the same command read in one
  dialect, and the settings template gives the guard hook a `timeout` of 5 s. No case of
  `hooks/probe.py` times a 1 MiB command that holds `$'`, and its `MIB_LIMIT` of 10 s is above
  the hook's limit. Not measured on an idle machine.
- kind: not verified
- found: 2026-11-08

### K140 · The shell checks of the guard read no command whose bash reading has an open quote, also where dash's reading is closed.

- location: `hooks/guard/shell.py:336`
- evidence: `readings` returns None when a quote of bash's reading is open, and drops the `plain`
  reading, which can be closed. `rm_scope` and `git_writes` ask on None; the other checks pass.
  `guard --from claude` answers `pass` to `git add -A $'\'' $'`,
  `gh api -X DELETE repos/a/b $'\'' $'`, `git archive -o x.tar HEAD $'\'' $'`,
  `gh pr create … $'\'' $'` and
  `gh run watch --interval 5 $'\'' $'`, where origin/main (28b2706f) answers `deny`; it asks for
  the same suffix after `rm -rf ~/Research/Papers` and after a lease push to `main`. bash, zsh and
  macOS `/bin/sh` refuse each line and run nothing. dash reads `$'` as a `$` and a quote, and runs
  each write. Returning None only when no dialect reads the text changes the contract that the
  checks build on.
- kind: defect
- found: 2026-11-08, the fourth pre-PR verification of `guard/bypass-gaps`

### K141 · The bash dialect of the guard reads `\c` of an ANSI-C quote as bash 3.2 does in one case and as bash 5.3 does in another.

- location: `hooks/guard/shell.py:102`
- evidence: bash 5.3 reads `$'x\c\\y'` as `x`, the control character 0x1C and `y`; bash 3.2
  (`/bin/bash` and `/bin/sh` on macOS) and the guard keep a backslash after the 0x1C. bash 3.2
  reads `$'x\c'y` as `x\y`; bash 5.3 and the guard read it as `x\cy`. Each difference leaves a
  control character or a backslash in the word, so no word of ASCII letters comes of it.
- kind: defect
- found: 2026-11-08, the fourth pre-PR verification of `guard/bypass-gaps`

### K142 · `install_tree` fails after it has linked the new tree when a file or a link is in `<command>/`.

- location: `lib/harness/setup.py:1039`
- evidence: after `part.replace(link)`, the loop calls `shutil.rmtree` on each entry of
  `<command>/` but the new version. A file there, such as the `.DS_Store` that Finder writes, makes
  it raise `Not a directory`, and a link makes it raise too. The step
  then reports `cannot install the tree of …`, while `~/.local/bin` already links into the new
  version, and the old version stays. Read from the code, not probed. The srt step removes only
  the links and the directories (`remove_others`).
- kind: defect
- found: 2026-11-08, the review of the srt pin's pull request

### K143 · `harness setup` counts a pre-release as its release.

- location: `lib/harness/setup.py:389`
- evidence: `installed_version` returns the first match of `VERSION`, `\d+(?:\.\d+)+`, so
  `v22.12.0-rc.1` reads as `22.12.0`, and `meets` passes it for each minimum of a tool and for the
  Node.js 22.12.0 that the srt step asks for. K83 is the same reading in `harness doctor`, with its
  own code.
- kind: defect
- found: 2026-11-08, the review of the srt pin's pull request

### K144 · The site check does not check the sidebar link to `components/sandbox.md`.

- location: `docs/scripts/check-site.mjs:36`
- evidence: `MENU`, the list of "every page of docs/src/", names ten pages of
  `docs/src/components/` and not `components/sandbox.md`, which `docs/.vitepress/config.mts:105`
  links in the sidebar. So `node scripts/check-site.mjs` does not check that each sidebar links the
  page, that its built page exists, that its built tables keep the rows of its source, or that each
  link of its text to a heading finds that heading.
- kind: missing test
- found: 2026-11-09, the review of the probe battery's pull request

### K145 · In a cmux terminal `agentbox agy` gives `srt` cmux's `agy` wrapper, not the real `agy`.

- location: `sandbox/agentbox:68`
- evidence: a cmux terminal puts `/Applications/cmux.app/Contents/Resources/bin` early on the
  `PATH`, and that directory holds `agy`, a bash script whose header reads `# cmux agy wrapper -
  installs cmux hooks and captures launch metadata.` The filter of `resolve` skips only the
  entries that match `*/cmux-cli-shims/*` or `*/cmux-cli-shims`, so `command -v agy` there finds
  the wrapper. A critic's probe with that directory first on the `PATH` saw
  `srt-program='/Applications/cmux.app/Contents/Resources/bin/agy'`. Whether `agentbox` skips this
  directory too is a decision that the cmux-cli-shims filter does not make.
- kind: found late
- found: 2026-11-09, the review of the cmux and caches pull request of `agentbox`

### K146 · A frontend probe past its time limit expects `holds <word>`, also where it expects the word to be missing.

- location: `scripts/probe-agentbox.py:533`
- evidence: `ask_row` writes the expectation of a timeout as `expected or f"holds {ask.word}"`
  and does not read `ask.holds`. So an F3 that passes `--timeout` has the expectation
  `holds READABLE` in its row, where F3 expects `lacks READABLE`. The verdict `timeout` is right;
  only the `expected` cell is false. Read from the code, not probed.
- kind: defect
- found: 2026-11-09, the build of the probe battery's fixes

### K147 · A line of `## Listeners` can name a frontend for a port where that frontend got another status.

- location: `scripts/probe-agentbox.py:668`
- evidence: `listener_lines` collects the ports and the frontends of one command, status and
  verdict as two separate sets, so a line names every port of the group under every frontend of
  the group. With `alpha` on 7001 and 56925, where `omp` gets 200 at 7001 and every other row is
  401, `report.md` holds ``- `alpha` answers `401`, `match`: 2 ports (7001, 56925), under claude,
  omp and agy``, and a second line ``- `alpha` answers `200`, `MISMATCH`: 1 port (7001), under
  omp``. `report.tsv` holds the exact rows.
- kind: defect
- found: 2026-11-09, the review of the probe battery's fixes

### K152 · The detail of a failed frontend probe misses an `error:` line at the start of stderr when stdout has no final newline.

- location: `scripts/probe-agentbox.py:342`
- evidence: `error_head` splits the joined `out + err` into lines, so stderr's first line joins the
  last line of stdout. `error_head("a\nb\nabc" + "error: bun failed\n")` gives
  `'a b abcerror: bun failed'`, the whole text: the anchored `^\s*error:` of `ERROR_LINE` does not
  match `abcerror:`. With a final newline on stdout it gives `'error: bun failed'`. `says` splits
  each stream on its own; `error_head` does not.
- kind: defect
- found: 2026-11-10, the review of the probe battery's word rule and error head

### K148 · The same-file checks of the network lists and the deduplication of `merged` compare hosts as exact strings, while `denies` folds case.

- location: `lib/harness/network.py:223`
- evidence: `read` refuses a host in `allow` and `deny` of one file, and a host in `fetch` and
  `allow`, only when both entries are the same string (lines 223 and 227), and `merged` drops an
  entry of the overlay only when the harness list holds the same string (line 246). `denies`
  matches without regard to case. So an overlay `allow = ["GitHub.com"]` gives the two rules
  `WebFetch(domain:github.com)` and `WebFetch(domain:GitHub.com)`, and `allow = ["f.org"]` with
  `fetch = ["F.org"]` in one file passes `read`; `generate` then refuses it as a `fetch` host that
  the `allowedDomains` entry `f.org` covers. No host is reached that no entry grants.
- kind: defect
- found: 2026-11-09, the review of the network lists' `fetch` key

### K153 · No `Read` permission deny and no OpenCode guard path covers `~/.config/anthropic/credentials` or `~/.gemini/jetski-standalone-oauth-token`.

- location: `settings/settings.proposal.json:388`
- evidence: `~/.claude/.credentials.json` and the credential files of `omp` and `opencode` each
  have a `Read(/{home}/…)` deny in the template's `permissions.deny` (lines 388-393) and an entry
  in `adapters/opencode/plugins/guard-paths.json`.
  The two paths are only in the template's `sandbox.filesystem.denyRead` (lines 876-877) and
  `sandbox.credentials.files` (lines 925 and 929): `grep -n 'anthropic\|jetski'
  settings/settings.proposal.json adapters/opencode/plugins/guard-paths.json` finds those four
  lines and nothing else. So no permission rule and no guard path refuses a frontend's own read
  tool, as distinct from its shell, on either path.
- kind: found late
- found: 2026-11-10, the review of the srt files for Claude Code's Anthropic login and `agy`'s
  token file

### K154 · With `GIT_GLOB_PATHSPECS=1`, `GIT_LITERAL_PATHSPECS=1` or `GIT_NOGLOB_PATHSPECS=1`, the Julia packages' pre-commit hook lists no staged `.jl` file below the repository's root.

- location: `githooks/pre-commit.jl:550`
- evidence: `main` takes the staged files from `staged("--diff-filter=ACMRT", "--", "*.jl")`.
  Under `GIT_GLOB_PATHSPECS=1`, git reads `*.jl` as a glob in which `*` matches no `/`: with
  `src/Fixture.jl` and `top.jl` staged, `git diff --cached --name-only --diff-filter=ACMRT --
  '*.jl'` prints both by default and only `top.jl` with the variable. Under
  `GIT_LITERAL_PATHSPECS=1`, git reads `*.jl` as a literal path: with `src/Fixture.jl` staged,
  the listing is empty. So no stage checks a file below `src/`, and a commit that adds an `@show`
  to `src/Fixture.jl` passes with exit 0 and no `ast-grep` line, under either variable. Under
  `GIT_NOGLOB_PATHSPECS=1`, git reads `*.jl` as a literal path too: with `src/Fixture.jl` and
  `top.jl` staged, the listing is empty. The launcher `githooks/pre-commit` lists the files with
  the same pathspec, at line 13. A fix runs both listings without `GIT_GLOB_PATHSPECS`,
  `GIT_LITERAL_PATHSPECS` and `GIT_NOGLOB_PATHSPECS`, as `added_lines` runs its diff without the
  variables that change its hunks.
- kind: defect
- found: 2026-11-11, the arbitrator's diagnosis of the second critic round of the pre-commit
  ast-grep stage

### K155 · The docstring of `git_writes.py` and *Guard hooks* say that the settings template holds no rule for the lease push, but the template allows one form and denies three.

- location: `hooks/guard/git_writes.py:58`
- evidence: the docstring (lines 58-60) says "a hook's `allow` does not lift a matching `ask` or
  `deny` rule, so the template holds no rule for these forms and the check answers both ways";
  `docs/src/safeguards/guard-hooks.md:287-289` says the same of the settings. The template's
  `permissions.allow` holds `Bash(git push --force-with-lease=* origin HEAD:refs/heads/*)`
  (`settings/settings.proposal.json:21`), and its `deny` holds `Bash(git push --force-with-lease)`
  (line 288) and the same lease form for `main*` and `master*` (lines 298-299). The denies agree
  with the check, which refuses a lease push to a default branch or to no branch. The allow rule
  matches the `HEAD:refs/heads/<branch>` form whatever `origin` is, where the check asks for an
  `origin` outside the own organisations. Whether Claude Code then asks, because the hook asks,
  or runs the push, because the rule allows it, is not measured here. Either the docstring and
  the page name the four rules, or the template drops the allow rule.
- kind: docs
- found: 2026-11-11, PR #241 (the docs restructure)

### K156 · `julia-branch-verifier` names a "seven-point pass" but defines six points, numbered 1 and 3–7.

- location: `agents/julia-branch-verifier.md:5`
- evidence: the description (line 5) says "Runs the seven-point pass", and the output shape
  (line 171) says "Scope: full seven points". The table of points (lines 92-97) has the rows
  **1 · correctness, quality, concision**, **3 · type piracy and ambiguities**, **4 · type
  instability**, **5 · avoidable allocations**, **6 · stale comments, present tense** and
  **7 · history only in `CHANGELOG.md`**; no point 2 is defined anywhere in the file.
  `docs/src/components/agents.md:197` repeats "seven-point pass". A fix says six, or renumbers
  the points 1–6; a renumbering also changes "points 1,3,6,7 only" of the output shape
  (line 171) and every "point 3" and "point 4" of the file.
- kind: docs
- found: 2026-11-11, PR #241 (the docs restructure)

### K157 · A `--bind-try` or `--ro-bind-try` destination counts as an effective mount point of a job even when its source is missing on the host.

- location: `lib/harness/jobsandbox.py:583`
- evidence: `job_pins` skips each path that `effective([*reads, *writes, *denies, *back])` holds,
  and the read paths, write paths and files written back are bound with `--bind-try` or
  `--ro-bind-try`. Where the source of such a bind is missing, `bwrap` makes no mount, so the path
  is no mount point in the job's namespace, and the other job can put a link there between this
  job's `jobbox` check and its mount. On the shipped list each such path is a write deny or a pin
  of one of the jobs, which `harness setup` creates (`linux_dirs`, `linux_files`): a probe of
  `sandbox/daemon.toml` with the home `/h/a.b` finds
  `~/.julia/bin`, `~/.julia/juliaup`, `~/.julia/environments/apps` and juliaup's lock file. A
  list that E5f extends can add a `-try` destination that setup does not create. A fix counts a
  `-try` destination only where setup creates it.
- kind: defect
- found: 2026-11-11, the verify-4 critic of part D2

### K158 · `check_entry` takes `deny` and `infrastructure` entries that srt 0.0.81 refuses, so one such entry makes every frontend's srt settings file invalid.

- location: `lib/harness/network.py:105`
- evidence: `check_entry` takes a port with a leading zero and a host of one label: `check_entry`
  passes `deny` entries `x.org:08080` and `intranet` and `infrastructure` entries `intranet` and
  `*.org`. srt's schema (`sandbox-config.js`, `domainPortPatternSchema` for `allowedDomains`,
  `deniedDomainPatternSchema` for `deniedDomains`) takes a port only as `[1-9][0-9]{0,4}` and a
  name only with a dot, other than `localhost`, and a `*.X` only where `X` has two labels or more
  (`domain-pattern.js`). The entries reach `allowedDomains` and `deniedDomains` of every
  frontend's file through the template, so srt's schema refuses the file; no session has run
  srt on such a file. No list of the harness holds such an entry; an overlay can. The frontend
  entries of `frontend_entries` have the closed grammar.
- kind: defect
- found: 2026-11-12, the planning of part E5k

### K160 · The committed `opencode.jsonc` holds two `ask` rules of `bash` that `harness permissions` does not generate from the settings template.

- location: `adapters/opencode/opencode.jsonc:260`
- evidence: `python3.14 bin/harness permissions` prints `adapters/opencode/opencode.jsonc REPLACE`
  with the two lines `-      "git push * :**": "ask",` and `-      "git -C * push * :**": "ask",`,
  and `1 change(s) to make.`; `grep -n 'push \* :' settings/settings.proposal.json` finds nothing.
  Either the template lacks the two asks, or the committed file keeps two rules that the template
  dropped.
- kind: defect
- found: 2026-11-13, the fix round 1 of part E5c

### K161 · The probe case `mib-rules` fails on a GitHub runner when the guard needs more than `MIB_LIMIT`, 10 s, for its 1 MiB command.

- location: `hooks/probe.py:1745`
- evidence: in one run of `test.yml` on `ubuntu-26.04`, the job *harness test with an empty HOME*
  reports `BAD exp ask, at most 471 matcher calls got timeout  [mib-rules]  275 rules, …: matcher
  calls -1, 10.02 seconds, within 10 s`, and the job *Python 3.14* of the same run reports
  `matcher calls 471, 7.20 seconds`. The matcher calls stay at their bound, so the guard is right
  and only its time is close to the limit. The case measures wall time while the other parts of
  `harness test` run in parallel.
- kind: defect
- found: #282

### K162 · `spec-gate.py` reads the whole section for a `sections` cell such as `§J (J9)`, not the entry of that part.

- location: `scripts/spec-gate.py:188`
- evidence: line 187 splits the cell at the commas, and line 188 keeps only the first word of
  each key, so `§J (J9)` becomes `J` and the parenthesised entry name is dropped. Line 196 then
  takes the whole text of the `§J` heading, which `sections()` (lines 72-82) maps up to the next
  heading of the same or a higher level, as the part's body. The label check (line 226) and the
  **Files** check (line 197) therefore read every part's entry in the section. A fixture with the
  cells `§J (J1)` and `§J (J2)`, one `## §J` section, and the directories `Packages/Example` and
  `Harness` under `RESEARCH_ROOT`: with only J1's entry holding **Decided at the edges** and
  **Tests catch**, the gate prints `J2	PASS` and exits 0 (a false PASS); with only J2's **Files**
  naming `Harness/scripts/x.py`, it prints `J1	SPANS Harness, Packages/Example` and exits 1 (a
  false FAIL). On a task file whose parts share one section, a `Harness` part gets a false
  `SPANS` from another part's **Files**. The fix waits for the next change to the plan tooling.
- kind: defect
- found: 2026-11-13, a false `SPANS` of the spec gate on a part whose entry shares a section
