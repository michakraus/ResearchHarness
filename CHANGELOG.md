# Changelog

## Unreleased

- **Antigravity's guard hook decides the sandbox of each command, so `git` and `gh` work in the
  app.** An allow rule such as `command(git)` lets a command start with no dialog, but it still ran
  in the app's terminal sandbox, where `git` could not read `~/.gitconfig` and stopped with exit
  128. `adapters/antigravity/guard.py` now answers each `run_command` that it does not deny with
  `"overwrite": {"BypassSandbox": …}`: true when `top_level` of the installed
  `sandbox-semantics.py`, Claude Code's rule for `sandbox.excludedCommands`, lifts the command
  (every part led by `git`, `gh`, `glab` or `ps`, and no file redirected), false otherwise. A probe
  in the app showed that any command that an allow rule covers, `julia --version` among them,
  leaves the sandbox with no dialog when the agent sets `BypassSandbox`; the guard therefore also
  forces false on every other command. A deny and a call of another tool carry no `overwrite`.
  `ANTIGRAVITY-DELTA.md` tells the agent not to set `BypassSandbox` itself. `hooks/probe.py` covers
  the lifted and the sandboxed commands, the agent's own `BypassSandbox`, a deny, the other tools,
  a rule read from the installed file, and no bytecode cache in the installed `hooks/`.

- **`scripts/julia-update-test.jl` runs on ubuntu-26.04.** There `/usr/bin/sleep` is a relative
  symlink, so the fixture's copy of it dangled and every case with a live server failed on
  `chmod` (ENOENT). The fixture copies the file the link names, and starts it through `bash`'s
  `exec -a sleep`, because a multi-call coreutils binary chooses its tool by `argv[0]`. A control
  with a relative-symlink `sleep` first on the PATH fails the old fixture in 10 cases and passes
  the new one, 55 of 55, on macOS.

- **`bibliography` is no longer a fixed repository of the research tree.** The example tree keeps
  its citation keys and the tools that build the shared bibliography in `Library`, and the shared
  `.bib` in `Latex`. `WIKI_REPOSITORIES`, and with it the fixed repositories of `harness clone` and
  `harness repos`, is `Knowledge`, `Environment`, `Tasks` and `Library`; `wiki-lint.jl` lints those
  four trees, and `pre-commit-wiki` says so. A `bibliography` key in `repositories.toml` is an
  error: remove it before the next `harness repos`. `wiki-lint.jl` still reads a
  `` `Bibliography/…` `` span as a path, so a stale reference shows as a dead path.
  `literature-scout` checks `~/Research/Latex/shared.bib` and the manuscripts' own `.bib` files for
  duplicates, and marks one as "already in a .bib". The examples and the docs follow.

- **`harness doctor` checks the Kaimon token when Antigravity is installed.** Antigravity's
  `mcp_config.json` gets the token from `~/.config/kaimon/auth-token`, but the doctor skipped the
  check on a machine with neither OpenCode nor oh-my-pi, saying that only they read the file. It
  treats Antigravity as installed when `~/.gemini` is a directory, as its adapter does, so a
  missing or empty token, or one of a mode other than 600, is a FAIL there too. Three new cases cover Antigravity
  alone with a token, without one, and a `~/.gemini` that is a file.

- **Kaimon's bearer token lives in `~/.config/kaimon/auth-token`, not `opencode-token`.** OpenCode,
  oh-my-pi and Antigravity all read the file, so its name no longer names one frontend. The three
  adapters, `harness doctor`, the read and sandbox denies of the settings template, OpenCode's
  `guard-paths.json` and permission denies, and the setup pages use the new path. An existing
  install moves the file before its next `harness install --apply`:
  `mv ~/.config/kaimon/opencode-token ~/.config/kaimon/auth-token`. An install applied before the
  move leaves the old file with no deny that protects it, and the Kaimon entries with no token.

- **Floating-point differences up to at least `8 ulp` never block, and the package compatibility
  floor is Julia 1.12.** `skills/build-part/evidence.md`, `skills/build-part/edges.md`,
  `agents/julia-critic.md`, `agents/part-critic.md`, `agents/julia-pr-reviewer.md`,
  `agents/arbitrator.md` and `rules/julia-tests.md` state that a floating-point difference of one or
  a few ULPs — at least up to `8 ulp`, `8 * eps(real(T))`, across platforms, architectures, Julia
  versions or compilation contexts — is acceptable and never fails a clause or blocks a round; when
  a test or a critic fails only on a difference of a few ULPs, the arbitrator chooses `test round`
  rather than `park`. `rules/julia-code.md`, `rules/julia-tests.md`,
  `skills/julia-package-audit/SKILL.md`, `skills/julia-performance/SKILL.md`,
  `skills/build-part/evidence.md`, `skills/build-part/edges.md`, `agents/julia-test-runner.md`,
  `agents/julia-load-doctor.md` and `agents/julia-perf-analyst.md` state the Julia 1.12 package
  compatibility floor and drop 1.10- and 1.11-only floor workarounds.

- **A settings file nested just deeper than the second parse reads exits 2, not with a traceback:
  K100 and K105 leave `KNOWN_ISSUES.md`.** `rewritten_numbers`, which parses a settings file a
  second time to keep the text of each number, turns a `RecursionError` of that parse into "… is
  JSON nested too deep for the parser", naming the file, as `json_object` does for the first
  parse. On Python 3.11 a settings object nested 990 or 991 deep passed the first parse and
  stopped `harness install` with a traceback and exit 1, in Claude Code's settings merge, in the
  Antigravity `merge_settings` and in `merge_grants` of the app's `config.json`; all three now
  exit 2 before anything is written. A new case of the Claude adapter and one of `merge_grants`
  make that parse raise `RecursionError` at any depth, so they hold on each Python.

- **The dotfiles kit's test of a review cut short no longer depends on GNU `cat`.** In
  `examples/dotfiles/tests/update-check.py`, the chezmoi stub's large `diff` ran `exec cat`, and
  the test relied on that `cat` dying of SIGPIPE, with 141, when the pager quits early, as the real
  chezmoi does. Ubuntu 26.04 ships the `cat` of uutils, which ignores SIGPIPE, so the `dotfiles` job
  failed the 8 `chezmoi diff` cases of section 16 on `ubuntu-latest` once it moved to that image.
  The stub now writes through a Python writer that restores the default SIGPIPE action, which dies
  of SIGPIPE on any system. The kit itself is unchanged: chezmoi, a Go program, dies of SIGPIPE on a
  broken standard output. The `dotfiles` job gains a step that prints the runner's `cat --version`
  and the exit status of `cat` on a broken pipe.

- **`harness install` allows `gh`, `git`, `glab` and `ps` in Antigravity, as Claude Code runs
  them outside its sandbox.** The first word of each command of `sandbox.excludedCommands` in the
  settings template becomes a `command(<word>)` rule at the end of the `allow` list, after the
  Kaimon rules, once: `command(gh)`, `command(git)` and `command(glab)` are new, and
  `command(ps)` was already there from `Bash(ps *)`. The CLI's `settings.json` and the app's
  `config.json` get them, and a grant that the user already holds is not added again. Without
  them the app asked before each `git`, `gh` and `glab` command. No `unsandboxed(…)` rule is
  written. The guard hook applies the template's Bash denies and asks before the app's rules, so
  `git push --force origin x` and `git add -A` are still refused and `gh pr merge 1` still asks;
  the probe checks the three. The setup pages and the adapter page name the four rules.

- **`harness install` writes the permission rules into the Antigravity app's grants, and grants
  each Kaimon tool on its own.** Each Kaimon tool of the settings template,
  `mcp__kaimon__<tool>`, becomes the rule `mcp(kaimon/<tool>)` in its list, `allow`, `deny` or
  `ask` (27, 7 and 5 tools), after the other rules of the list; the wildcard
  `mcp(kaimon/*)` is no longer written, because the app asked for each Kaimon tool even with it
  set. The CLI's `settings.json` gets these rules in its `permissions`. The desktop app reads no
  rule from that file, and keeps its grants in `~/.gemini/config/config.json`, so the install now
  merges the same rules, the command, path and host rules and the Kaimon rules, into
  `userSettings.globalPermissionGrants` there: each rule once, after the entries of its list.
  Every other key and every grant of the user stays in its place, the install removes no entry,
  a missing file is created, and the file it replaces is backed up. A file that is not a regular
  file or not a JSON object, a `userSettings` or `globalPermissionGrants` that is not an object,
  or an `allow`, `deny` or `ask` that is not a list exits 2 before any write. The app's grants per
  project, in `config/projects/`, are not touched. The guard hook refuses a write to
  `config.json` by a tool that writes a file, so an agent cannot widen its own grants with one; a
  command or a `multi_replace_file_content` call that writes the file gets `ask` from the guard
  (K103).
  The setup pages and the adapter page say that the install writes the app's grants, and the
  delta states that in the app a subagent's call that needs a grant shows the app's dialog, where
  it said that a subagent shows no prompt; the agents' rule that the caller opens the pull request
  no longer gives that as its reason.

- **The documentation names Antigravity as the fourth frontend.** The README, the home page, the
  introduction, the architecture, the dependencies, the command page and the component pages count
  four frontends where they counted three, and list Antigravity where they listed Claude Code,
  OpenCode and oh-my-pi. The table of the neutral vocabulary in `architecture.md` gains an
  Antigravity column: the `[antigravity]` table for `model:`, the tool names of `TOOLS`, and
  `inheritMcp: true` with `call_mcp_tool` for a Kaimon tool; the text states that a tier is the
  only model an Antigravity agent can name. `components/adapters.md` describes the Antigravity
  group in the form of the other adapters: `adapter.py` with the files it writes and its exits,
  then `guard.py`, `ANTIGRAVITY-DELTA.md` with its facts, and `UNDER-ANTIGRAVITY.md`. The setup
  pages for macOS and Linux gain the install of the app, the step that adds `[antigravity]` to an
  older `models.toml`, and the app's permission settings, each with its check: the app keeps its
  grants under **General → Tool Permissions**, which writes them to `~/.gemini/config/config.json`;
  no wildcard grant for Kaimon works there; a workspace below `~/Research` asks once for read
  access to each parent `CLAUDE.md`. The tier step
  has the user select "Gemini 4 Argon (Medium)" in the app's model menu, which an agent of tier
  `large` inherits, and the Kaimon check starts `julia-critic`. The Kaimon token step names
  Antigravity, whose `mcp_config.json` holds the token itself. The pages on rules, Kaimon, the tree
  instructions and `frontends.py` name Antigravity beside OpenCode and oh-my-pi.

- **`harness install` writes the agents and Kaimon for Antigravity.** `models.toml` gains a table
  `[antigravity]`, beside `[claude]`, which maps the tiers `large`, `medium` and `small` to
  Antigravity's tiers `inherit` (the session model), `flash`, `flash_lite` or `pro`, with an
  optional `[antigravity.model_overrides]` of agent to tier; `examples/models.toml` holds
  `inherit`, `flash` and `flash_lite`. Once `~/.gemini/` exists, a missing table or tier, another
  key, another value, or an override of no agent of `agents/` exits 2 before any write, naming the
  table and the key. The table is read on its own, and the plans of OpenCode and oh-my-pi stay as
  they are. Each agent of `agents/` goes to `~/.gemini/config/agents/<name>.md` with `name`,
  `description`, its tier's `model`, its tools in the family of a subagent's default set
  (`view_file`, `list_dir`, `replace_file_content`, `write_to_file`, `grep_search`,
  `find_by_name`, `run_command`, `invoke_subagent`, `search_web`, `read_url_content`; `[]` for an
  agent with none), `subagent: true`, and `inheritMcp: true` for an agent with a Kaimon tool; no
  effort and no isolation. An "Under Antigravity" section from the new
  `adapters/antigravity/UNDER-ANTIGRAVITY.md` replaces each Claude Code mechanism that the agent
  uses: a preloaded skill, worktree isolation, the `Agent` tool, a background run, a Kaimon tool,
  the pull request. A council gives one warning for each agent that it names, and no seat file.
  `~/.gemini/config/mcp_config.json` gains the server `kaimon`, with the token of
  `~/.config/kaimon/opencode-token` written out, mode 600 and no backup, and the dry run never
  prints it; every other server and key of the file stays as it is, an empty file holds none, and
  a file that is not a JSON object, whose `mcpServers` is not one, or that holds a key twice in
  one object outside its Kaimon entry exits 2 before any write. With no token, the file is
  neither read nor written, and one warning says so. The guard hook refuses a write to the
  installed agents. A file of `config/agents/` with no source is listed as EXTRA. The delta
  states the agents' tiers and that round 1 of `build-part` runs two critics on the session
  model.

- **`harness install` writes Antigravity's instructions, rules and skills**, below
  `~/.gemini/config/`. The global instruction file `GEMINI.md` is the new
  `adapters/antigravity/ANTIGRAVITY-DELTA.md`: the sandbox and the guard hook as the controls, no
  RTK rewrite, a worktree made with `git worktree add` in `~/Research/.worktrees/`,
  `invoke_subagent` for the `Agent` tool, no effort per agent, each scoped `CLAUDE.md` read by the
  model itself, and the path rules with their scopes. `RTK.md`, the core and the tree
  instructions are each a rule of `rules/` with `trigger: always_on`. Each rule that Claude Code
  installs goes to `rules/` too, its `paths` as `trigger: glob` and `globs`, and a rule with no
  `paths` as `trigger: always_on`; Antigravity does not load a global glob rule, so the model
  reads the rule that the delta names. Each skill goes to `skills/<name>/` with its own files and
  their modes, its `SKILL.md` without `model:`. Every Markdown file but `GEMINI.md` names
  `~/.gemini/config/` where it named a copied path below `~/.claude/`: `RTK.md` and the files of
  `instructions/` in `rules/`, where the always-on files are, and `hooks/`, `rules/` and
  `skills/` at the same path. The install exits 2 before any write when an instruction file or a
  rule holds an include, `@[label](path)`, whose expanded size it cannot measure, or has 24,000
  bytes or more, the size at which Antigravity cuts it, or when together they have 80,000 bytes or
  more, Antigravity's 20,000-token rules budget at 4 bytes a token; and when two sources give one
  rule path. A rule or a `SKILL.md` with CRLF line ends gets the frontmatter keys of one with LF
  ends. A file below `config/rules/`, `config/skills/` or `config/hooks/` with no source is listed
  as EXTRA with its removal command. The guard hook refuses a write to these copies as the
  settings template refuses one to Claude Code's: `guard-paths.json` adds the copy of each Edit
  deny and ask of the template on `~/.claude/RTK.md`, `instructions/`, `hooks/`, `rules/` or
  `skills/`, and Edit denies for the global instruction files that Antigravity loads,
  `~/.gemini/config/GEMINI.md`, `~/.gemini/config/AGENTS.md` and `~/.gemini/GEMINI.md`; a read
  of them passes. `hooks.json` gains a `SessionStart` handler that runs a copy of
  `install-drift.py` and gives its warning as an `injectSteps` system message, `{}` when the
  install is current, and a warning that names the copy when it exits with an error or its
  output is not a JSON object with a text `systemMessage`; `hooks/probe.py` checks that it gives
  the verdict and the text of `install-drift.py` on each drift case, and a warning on each such
  failure.

- **`harness install` writes the permission layer of Antigravity**, below `~/.gemini/`, once
  Antigravity has made that directory; without it the plan holds no file and one warning. The new
  adapter `adapters/antigravity/` writes `config/hooks.json`, one hook that runs
  `config/hooks/guard.py` by its absolute path on every tool call, the seven guard scripts beside
  it, `config/guard-paths.json`, and three keys of the CLI's `antigravity-cli/settings.json`:
  `permissions`, `toolPermission: "proceed-in-sandbox"` and `enableTerminalSandbox: true`. The
  merge keeps every other key and the file's indent, and backs up the file it replaces; a file that
  is not a regular file or not a JSON object exits 2 before any write. `guard.py` gives the guard
  scripts Claude Code's payload, from the `CommandLine` and the resolved `Cwd` or first workspace
  path of a shell call and the `Arguments` of a Kaimon `ex` or `manage_repl` call. It refuses a
  path of the `deny` list in any path argument or any word of a command; that list adds
  `~/.gemini/config/mcp_config.json` and the files of the layer itself. As OpenCode's guard does,
  it also refuses a directory that holds such a path when a word globs into it, the command
  recurses or `cd`s into it, or it is the call's `Cwd` or `SearchPath`. On a shell call it applies
  the template's Bash denies and asks to each segment of the command, the bodies of `$(…)`,
  backticks and `( … )` included, on the words of the segment from any word, so that the desktop
  app, which reads no `permissions`, still refuses `git push --force`, also after `FOO=1`, `env`
  or `then`. On a tool that writes a file, it also refuses a path of the `edit` list, every Edit
  deny of the template, and asks for a path of the `ask` list, every Edit ask. A pass answers
  `ask`, which leaves Antigravity's own rules in force, and any failure of a guard answers `deny`.
  The rules are the settings template's: each Bash entry a `command(…)` rule, whose `*` in an
  allow rule matches no text across a segment, each Read and Edit path a `read_file(…)` or
  `write_file(…)` rule, each allow host a `read_url(…)` rule, a `read_file(…)` deny for
  `mcp_config.json`, and `write_file(…)` denies for it and the files of the layer. A path with a
  glob that Antigravity cannot express is dropped from the rules, and `guard.py` still covers it:
  the seven `Read(**/X)` denies in its `deny` list, seven Edit denies and two Edit asks in its
  `edit` and `ask` lists.
  `hooks/probe.py` runs `guard.py` on a fixture home, with cases for its refusals and for each way
  in which it fails closed.

- **`verify-workflows.jl` knows the majors of `docker/setup-buildx-action` (v4),
  `docker/login-action` (v4) and `docker/build-push-action` (v7).** A package with an extra
  workflow that builds a Docker image made the check report those actions as unknown and fail,
  so `harness ci-protection` refused to run.

- **`pre-push` passes `--check-bounds=auto` to the test process through `Pkg.test`'s
  `julia_args`.** Up to Julia 1.12, `Pkg.test` gives the test process `--check-bounds=yes` whatever
  the calling process uses, so on a 1.12 default the hook ran the suite with `yes` and recompiled
  every dependency into a separate cache. A probe package reports `check_bounds` 1 in its test
  process on 1.12 without the keyword and 0 with it; on 1.13 it reports 0 either way.

- **A spec check that needs a device is tagged `(device: metal)`, and runs from a Kaimon session.**
  The Bash sandbox has no GPU, so a Metal premise failed there and `spec-gate.py` reported the spec
  `INVALID`. `spec-validate.py` runs a tagged command only with `--devices metal`; elsewhere it
  prints `not run (needs metal)` and ends `UNMEASURED` with exit status 2, never a pass.
  `spec-gate.py` passes `--devices` through and prints `UNMEASURED <devices>`. `spec-format.md`
  gives the Kaimon route, a detached run that writes a log, and `build-part` and `build-reviewed`
  rerun an unmeasured gate that way.

- **`spec-validate.py`'s rule 10 refuses a `git grep` without `-P` that uses `\b`, `\s`, `\w` or
  `\d`**, in a command or in a file of the spec's `checks/`. Apple Git ignores those escapes, so
  the pattern matches nothing and an absence check cannot fail; the first draft of a converted spec
  had three such checks. `spec-format.md` also requires each absence grep to find its target on
  the base as a premise.

- **A new plan specifies each part in the spec-delta format.** `plan-parts` writes the spec of a
  part of tier `build` or `reviewed` as a file, `Tasks/Evidence/<plan>/<part>/spec.md` with its
  `checks/`, after `skills/plan-parts/spec-format.md`: a living spec whose premises run on the
  base, a change proposal, a delta of requirements with WHEN/THEN scenarios, a `check:` and a
  `catches:` each, and the mutant table. Two rules come from the P38b pilot: a premise for each
  API convention a clause depends on, and a `domain:` for each scenario that enforces a reference.
  The premise check marks a convention with no premise. The part's cell is `spec, §V, §L`. A plan
  whose parts have spec sections keeps them.

- **`scripts/spec-validate.py` is the strict validator of such a spec**, ported from the pilot's
  `validate.py`: headings, not substrings, nine rules, and the premises run on the base commit,
  which `--repo` exports with `git archive`. `spec-gate.py` runs it in place of its label test for
  a part whose cell names `spec`, and prints `INVALID` or `MISSING spec`; `build-part` and
  `build-reviewed` start no invalid part. `spec-bundle.py` copies the spec into the bundle whole
  and names `$SPEC`, and `evidence.md` says how a builder and a critic read it.

- **The gate of a spec-delta part runs the spec's checks and CI in every round** (B5).
  `julia-test-runner` runs `spec-validate.py --head` on the worktree after the suite, which fails a
  check that writes into the head; the dispatcher pushes the branch and reads every CI job. A
  failed check or job blocks the round. The pilot's gate found a broken commit order and a Windows
  path bug that no critic had judged.

- **The pull-request body lists every decision taken without the user** (B9): each advisor and
  arbitrator line and each clause the head does not meet as the spec writes it, under
  `## Decisions taken without the user`, in `julia-builder` and `part-builder`. Before, only the
  advisor's lines were listed.

- **The settings template allows the four read-only Zotero tools** `mcp__zotero__ping`,
  `search_items`, `get_item` and `list_attachments`. Before, they were allowed only in a
  `settings.local.json`, which `harness settings` does not measure and the installer warns about.

- **`latex-revision` allows for a shared preamble that already defines the marking block.** A
  document that inputs one adds only the dated comment of its pass and any new colour; defining
  the block a second time stops LaTeX with `Command \fixed already defined`.

- **Julia jobs over shared packages run together when their `CacheFlags` match.** The concurrency
  rule of `julia-test-runner`, `build-part`, `julia-package-audit` and `julia-load-doctor` states
  the condition, not a ban: on Julia 1.13 with no `--check-bounds` set, `Pkg.test()` and
  `run-tests.jl` pass the session's own setting, so a suite and another job are safe together; up
  to 1.12, or in a session started with a `--check-bounds` flag, they are not. `julia-test-runner`
  gives the cases as a table and keeps the advice to suspect a concurrent job before the code on a
  `CacheFlags` or extension `MethodError` failure. `build-part` lets two parts run their suites
  together on 1.13. Before, each file forbade a suite beside any other heavy Julia job over shared
  packages, which ruled out safe parallel builds.

- **A builder and a critic read one spec bundle per part, not line ranges of the task file.** The
  new `scripts/spec-bundle.py` writes the part's rows, the sections its `sections` cell names, §V,
  §L and the sections that §L's lines *The builder also reads* and *The critic also reads* name
  (`§6`, `*Traps*`, the preamble of a section) into one file, with a hash and the line range of
  each section; a name that matches nothing is printed as `unresolved` and exits 1. The
  `build-part` skill writes it before every spawn of a builder or a critic and passes its path, so
  a decision written into the task file reaches the next spawn; an unresolved name holds the part
  back. `julia-builder` and `julia-critic` read the bundle whole and nothing else of the task file,
  and name its hash in their reports. `plan-parts` writes each part's bundle before a plan is done
  and treats an unresolved name, or a needed section that the bundle lacks, as a defect of the
  plan; its §L template names sections by key or heading. Before, a builder read the sections of
  its cell and found the rest by `grep -n`: most builders and fixers of six measured builds skipped
  the *Traps* or the working rules that §L named only for the critic, and a fixer often read a
  pointer to one decision and nothing else. The bundle leaves out the narration of the state cell
  and any handover filed below §L. `part-builder`, `part-critic`, `advisor` and `arbitrator` still
  read the task file by line range.

- **The landing page, the README and the Introduction list the same six features, in the same
  order.** The features are: one configuration for three frontends, private data across
  machines, the sandbox and safety in layers, a directory tree for research work, research memory,
  and agentic software engineering. Each tile of the landing page links its page. The tiles
  *Instructions that load when they apply*, *Long work goes to a sub-agent* and *Ideas for any
  language* are gone; a line below the tiles says that most ideas apply to any language. The
  hero tagline names the configuration, the safety settings and the working environment. The
  README keeps one more feature, the tools for Julia packages and papers, and names
  `harness doctor` under the first one. In the Introduction, *What a harness adds* becomes *What
  the harness does*, with the six features. The overview figure is now *The research tree, the
  components and the frontends*, so that "layers" names only the three layers of an install and
  the layers of control. The glossary gains *Research tree*, and each newcomer page links its
  first use.

- **The documentation site has a page for each main feature of the harness.** Three pages are new:
  *The research tree* (`research-tree.md`, under *Use*) replaces *An example tree*. It says why
  the work is one tree, gives the example layout in one table, says how to adapt it, and names the
  places of the worktrees and of `.scratch/`. It also states that the settings template and the
  guard hooks name `~/Research` itself, whatever `$RESEARCH_ROOT` says. The section on the
  subcommands for the whole tree moves to it from *Typical use*. *Private data across machines*
  (`private-data.md`) says what is private, how `harness leaks` and gitleaks keep it out of the
  repository, and how the dotfiles kit, `claude-autocommit` and git carry it to each machine.
  *Research memory* (`memory.md`) lists the kinds of memory, with who writes each one and when a
  session reads it, says where a fact belongs, and names the checks that keep the memory correct;
  it is marked as in development. *Agents at work* becomes *Agentic software engineering*
  (`agentic-engineering.md`). It gains sections on sub-agents, on the path from a plan to a pull
  request, on worktrees, on pull requests and on models, and its call graphs are under *Who spawns
  whom*. The sidebar lists *Use* as Typical use, The research tree, the two commands and the
  profile, and *Background* in the order of the features: architecture, private data, security,
  memory and agentic software engineering. `check-site.mjs`, `newcomer.mjs` and the docs check of
  `harness test` follow the new file names; the code-span check of the research-tree page accepts
  the path `docs/make.jl`.

- **`dotfiles-merge` and `dotfiles-update` of the dotfiles kit say why they stop when you quit
  the review early.** A pager that quits before the log, the diff or `chezmoi diff` is written to
  its end made git exit 141 and `set -e` end the script with no message, and made `chezmoi diff`
  hang. Each part of the review now goes through git's pager in a pipe of the script's own. A
  broken pipe prints one line on standard error, such as `dotfiles-merge: you quit the review
  early; nothing is merged. Run dotfiles merge <branch> again and read the review to its end.`,
  and exits 1. After the merge is pushed, or in `dotfiles-update`, the line says that nothing is
  applied, and names `chezmoi diff` and then `chezmoi apply`. Any other failure stops the script
  with its own status. Clause 16 of `tests/update-check.py` covers the stops, a pager that reads
  to the end, and two mutants; the manual page gains the section *The review*.

- **The documentation site gains the manual page of the dotfiles kit, `dotfiles-command.md`.** It
  gives the synopsis, the exit status, the files and where to run each of `dotfiles update`,
  `dotfiles check [--full]` and `dotfiles merge <number | branch>`; the update path and its trust
  model, in which a machine applies only commits signed by a key of its applied `allowed_signers`;
  the steps of a new machine and of the first signed commit; the data keys of
  `.chezmoidata/machines.toml`; and how to start a private copy with `harness dotfiles-kit`. The
  page is in the sidebar, under *Use*, and in the menu of the site check. The two setup pages
  gain a section *Dotfiles (optional)* that links it, the CI section of `development.md` names the
  job `dotfiles`, the `examples/` row of `architecture.md` names the kit, and the sections of
  `harness dotfiles-kit` link the page. The edge catalogue of `build-part` gains two edges of a
  tool that reads files or a tree: a refusal of a directory compared by path, and a write to a
  path that holds a FIFO or a file that cannot be read.

- **`harness dotfiles-kit [--apply] DEST` copies the dotfiles kit into a chezmoi source.** It
  reads `examples/dotfiles/kit.toml` and lists each code file of `DEST` that is missing or
  differs from the kit in its bytes or its execute bit, and each seed file that `DEST` lacks; the
  dry run exits 1 when it lists one. `--apply` copies them and never writes a seed file that
  exists; a file that `kit.toml` does not name stays as it is. It refuses, with exit 2, a `DEST`
  that is not a directory, and the applied source `~/.local/share/chezmoi` or a directory below
  it, by device and inode, so a link, `..`, a case variant or a firmlink of it is refused too: the
  copy goes into a clone, on a branch, and through a merge request. A `kit.toml` entry whose file
  the harness lacks exits 2 with one line that names it, and so does a file whose directory
  resolves outside `DEST` through a symbolic link, before the first write, and a code file that
  cannot be read. A link at a code file's own path is replaced; `--apply` exits 2 on anything
  else there that is not a regular file, such as a directory or a FIFO. The contract sweep gains
  the argument `{kit}`, an empty fixture directory, and runs the dry run on it.

- **The dotfiles kit gains its setup scripts and the files of `~/.config/research-harness/`.**
  `examples/dotfiles/.chezmoiscripts/` holds the five scripts that set up a machine: the tool
  check, the clones, Julia, the harness at its pin, and the services. The seeds are
  `.chezmoidata/julia.toml`, the Julia packages of every host, and the five files of
  `dot_config/research-harness/`, with the placeholder values of `examples/profile.toml`,
  `models.toml`, `network.toml`, `providers.toml` and `repositories.toml`. The profile keeps two
  template actions: the home directory, and `autocommit_branch` `memory/<host>` on every host but
  the template host. The clone script reads its four remotes, the harness's among them, from a
  new `[remotes]` table of `.chezmoidata/machines.toml`, which also gains a placeholder Linux
  host, `example-linux`. The services script loads the three jobs of the harness and no personal
  job. Two new tests come with the scripts: `render-check.py` renders the kit for each host,
  checks the kit's targets only and allows any other target, and `script-check.py` runs each
  script in scratch homes with stub programs. When the kit is `examples/dotfiles/` of a harness
  checkout, `script-check.py` renders the services with that checkout at its HEAD; otherwise it
  uses `~/Research/Harness` at `harness_commit`. Both run in the CI job `dotfiles` and in the
  pre-push hook beside the three tests of the update path.

- **The dotfiles kit, `examples/dotfiles/`, starts with its update path.** The scripts that keep
  a chezmoi source signed and applied lived only in a private dotfiles repository, with its
  private values written into them. The kit ships them as a chezmoi source with placeholder data:
  the driver `dotfiles`, `dotfiles-update`, `dotfiles-merge` and `dotfiles-check`, the templates
  that they share, the signing settings of git as `.chezmoitemplates/gitconfig-signing`, and the
  seeds `.chezmoidata/machines.toml`, `dot_config/git/allowed_signers` and
  `.chezmoitemplates/chezmoiignore.local`, which `.chezmoiignore` includes at its end.
  `examples/dotfiles/kit.toml` names each file as code, which a copy keeps byte-identical, or
  seed, which a copy owns once it has it. Three changes come with the move. `dotfiles-merge` signs
  with the `signing_key` of the host data, sets `SSH_SK_PROVIDER` only from a non-empty
  `sk_provider`, and stops before the fetch when the host has no `signing_key`. `dotfiles-check`
  prints a `kit` line: WARN that names each code file of `kit.toml` that differs from the harness
  at `harness_commit` or that the source lacks, WARN when that `kit.toml` has no code line in the
  form `"<path>" = "code"`, and SKIP when that commit has no kit or the harness checkout lacks it.
  `dotfiles merge <number>` asks `gh` for an origin on github.com and `glab` for any other host,
  as `harness repos status` reads the origin, and stops with "not found" when that program cannot
  read it. The tests `update-check.py`, `check-check.py` and `driver-check.py` run in a new CI job
  `dotfiles`, with chezmoi 2.73.2 from its release tarball, checked by its SHA256, and in the
  pre-push hook on a push to `main` when `chezmoi` is on the `PATH`.

- **`harness clone`, `harness repos` and `harness update`.** A second machine had no way to clone
  the research tree, no command pulled every repository, and no command showed which
  repositories were ahead, behind or had open pull requests. `harness clone [SELECTION ...]`
  clones each repository of a new repository table, `repositories.toml` beside the profile
  (`examples/repositories.toml` shows the form), and refuses the whole run when a directory is in
  the way. `harness repos status` fetches every repository in parallel and prints its branch, its
  commits ahead and behind, its changed files and its open pull requests, from `gh` or `glab`,
  and names each drift from the table. `harness repos pull` fast-forwards, `harness repos push`
  pushes one repository at a time, and `harness repos sync` does both. A selection such as
  `papers` or `knowledge` limits each to one group or one fixed repository. `harness update`
  brings the harness checkout on `main` up to `origin/main`: it shows the diff, asks, merges
  `--ff-only` and runs `harness install --apply`, and it does not move a pinned checkout at a
  detached HEAD. **`harness push-all` is now `harness repos push`**: the flag `--skip-hooks` is
  `--no-verify`, with the old name as an alias. The push now fetches first, so it sees a commit
  behind on the remote; it no longer prints the one-off hint to run `ci-protection`.

- **`harness-command.md` is a manual page.** It gave one table row per subcommand and left the
  options, the exit status and the place to run each subcommand to `--help` and other pages. It
  now has a synopsis, the global options, a section for each subcommand with its options, exit
  status, files, where to run it and examples, and tables of the environment variables, the files
  and the exit status.

- **"Subcommand" in place of "verb".** The docs, the help, the docstrings, the code and the
  `build-part` skill called `install`, `doctor` and the others the verbs of `harness`.
  "Subcommand" is the term that a reader of a command-line tool knows, and "command" has three
  meanings here already: a shell command, a slash command and the `harness` command itself. The
  usage line of `harness --help` now reads `<subcommand>`, and the heading *The subcommands for
  the whole research tree* of `daily-use.md` replaces *The verbs for the whole research tree*.
  In the code, `args.verb` is `args.subcommand`, and `VERBS` and `settings_verbs` of the contract
  sweep are `SUBCOMMANDS` and `settings_subcommands`. A name that means a grammatical verb, such
  as the word "wrote" in `githooks.py`, keeps `verb`.

- **The docs, the README and the docstrings use one set of standard terms, and every verb has
  its help.** A review of the language found word-for-word phrases where a standard term exists
  ("the installer of Claude Code", "the user manager of systemd", "start file"), long sentences
  with a file or a condition as the subject of "exits 2", internal words used before any
  definition (dispatcher, council, verify round, §V and §L), and terms with several meanings.
  The pages now say "shell startup file", "the systemd user manager", "lingering", "the Claude
  Code sandbox", "working tree", "sub-agent", "diff", "private strings" and "the template host",
  define the internal words at first use, and split the long sentences. `harness-command.md`
  defines a verb as a subcommand of `harness`. The docstrings lose the private paths, the dated
  incidents, the round numbers and the benchmark labels, and keep each mechanism. Eight
  docstrings and help strings that were false against the code are corrected; among them the
  `--apply` help of `skill-triggers`, which runs paid `claude -p` sessions, and the `format` help,
  which skips some directories. `harness <verb> --help` now prints a description for every verb
  and every `settings` sub-verb, and every option and argument has help. K73 lists four files
  in place of six.

- **The README describes the harness and links the setup pages.** Its short *Installation* left
  out the frontends, Kaimon and the jobs, so a reader who followed it had no frontend for the
  next section, and it drifted from the setup pages. Its *A first session* repeated the first
  steps of the tutorial. Both sections are gone. *Features* now also names the builder-critic
  loop, the tools for Julia packages and for papers, one profile for every machine and
  `harness doctor`; *Getting started* links the two setup pages, the tutorial and the
  introduction. The README, the setup pages, the tutorial and the introduction call the entries
  of the glossary terms, not words.

- **The output of `harness install` and of the Julia test files is in columns.** The install
  padded each label to 34 characters, so a longer label pushed its status out of the column. The
  label column now has the width of the longest label of the install, and two spaces separate it
  from the status. `gate-test.jl`, `mutants-test.jl`, `run-tests-test.jl` and
  `test-layout-test.jl` printed one summary table per top-level test set, each with its own
  widths. Run as a script, each file now runs its test sets inside one verbose test set and prints
  one table. A failure no longer stops the file at the end of its test set: the other test sets
  run, and the file exits non-zero at the end.

- **The two setup pages have the same steps in the same order, and the docs match the code
  again.** *Setup on macOS* gained the steps that only *Setup on Linux* had: *Check the machine*,
  the frontends (Claude Code by its installer, OpenCode 2 and oh-my-pi by their Homebrew taps),
  the Seatbelt sandbox, Kaimon, the launch agents with `launchctl bootstrap`, and the Kaimon
  token. It no longer makes `~/.claude/skills`, which the install does not need; the README's
  short form dropped it too and names `template_host`. Each page holds its own text for the
  install's three frontend sections, the providers and the network overlay. `harness doctor`
  names `setup-macos.md` for each `FAIL` on macOS. *Adapting the profile* opens with a table of
  the four files in `~/.config/research-harness/`, and says that `launchd_prefix` is for macOS
  only, that `protected_dir` is relative to `home` and that the `leak` item `~` is the home path.
  `/review-pr` waits for the CI runs that `julia-pr-shepherd` names, since the agent does not
  wait. Corrected stale statements: the frontmatter keys (eleven), the five shell guards of
  oh-my-pi, the settings keys that the install adds, the users of `parts-table.awk`, the tutorial's
  dry run, the branch push of the pre-push hook, the counts of the Julia test files and the
  applied verbs, the new builder per round of `build-reviewed`, `ci-protection` and `format` among
  the tree verbs, and the layout table of *Architecture*.

- **`harness doctor` checks a machine's setup in one command.** The checks of the setup pages ran
  one by one, by hand, on each machine. The new read-only verb prints one line per check, `PASS`,
  `WARN`, `FAIL` or `SKIP` with a detail, and a `FAIL` line names the section that fixes it: the
  system and, on Linux, the user-namespace settings, the `bwrap` sandbox and `socat`; each tool of
  `docs/src/dependencies.md` against its minimum, which a case compares with the page, and the Julia
  packages of the scripts' environment; the profile, the `tree_agents` and OpenCode directories,
  and `autocommit_branch`; the dry run of `harness install` and each of its warnings; Kaimon, its
  jobs under `systemd --user` or launchd, linger, `~/.claude` as a repository with an `origin`
  when the autocommit job is enabled, and the Kaimon token by its mode and size only. `--full`
  adds `harness test` and `julia -e 'using Revise'`. It exits 1 when a check fails, else 0. In a
  session's sandbox, a command or a file that the sandbox refuses gives `SKIP`, so the verb runs
  in a plain terminal for its real verdict. *The check that it worked* of both setup pages ends
  with it.

- **One profile for every machine, and the findings of a test of *Setup on Linux*.** The
  profile needed one edit per machine: `autocommit_branch` is `main` on the machine whose memory
  is the template and a branch of its own on each other. A new optional key, `template_host`,
  names the template machine by its short host name (up to the first `.`, as `hostname -s`
  prints it). Without `autocommit_branch`, every verb now reads `main` without `template_host` or
  on that machine, and `memory/<short host name>` on every other; a given `autocommit_branch`
  still wins, and `harness get autocommit_branch` prints the value. A `template_host` that is
  empty, holds a `.` or is not a string exits 2. `examples/profile.toml` sets `template_host` and
  no `autocommit_branch`, and `harness leaks` renders it under the host name `example-other`. Both
  setup pages say to write the profile once and copy it to each machine. *Setup on Linux* names
  `~/.bashrc` and `~/.zshrc` for each `export` line, says that the juliaup installer stops over an
  earlier juliaup, gives the `.env` lines of oh-my-pi as a command with a check, adds *The Kaimon
  token* (the first key of Kaimon's `config.json` into `~/.config/kaimon/opencode-token`), checks
  that `~/.claude` is the top of its own git repository before it enables the autocommit timer,
  gives the administrator's linger command with the account name in a line of its own, and shows
  the login of Claude Code with `claude setup-token` and `CLAUDE_CODE_OAUTH_TOKEN` read from a
  file under `~/.config/api-keys/`. *Setup on macOS* names both start files too.

- **The profile takes `~`, and `home` is optional.** `examples/profile.toml` held the home path
  `/home/example` in five keys, and a reader had to replace every occurrence. `harness` now reads
  the profile with `home` set to the home directory of the user who runs it when the profile names
  none; a given `home` must be an absolute path without `~`, else the verb exits 2 and names the
  key, and a trailing slash is removed. A string value that is `~` or starts with `~/`, at the top
  level or as an item of a list, becomes `home` or `home` with the rest; any other `~` stays.
  `get`, `render`, `install`, `leaks` and the other verbs read these values. The example writes
  `harness`, `tree_agents`, `repository_roots` and the home entry of `leak` with `~`, has `home`
  as a comment, and works as copied: CI's `systemd-analyze verify` job renders the units with it
  unchanged, and the contract sweep copies it unchanged. `harness leaks` renders the templates
  with the example under the home `/home/example`, so that the running user's home in `leak`
  matches no rendered path. The comment of `memory_project` and its row in `profile.md` say that
  the value is a label, not a path, and that it must be the same on every machine that shares one
  memory pool. The profile sections of *Setup on macOS* and *Setup on Linux* no longer ask the
  reader to replace the example path.

- **Setup on Linux installs the frontends and covers `aarch64`.** The page gave no command for
  Claude Code, OpenCode or oh-my-pi, nor for RTK, jq or Kaimon, its release file names were for
  `x86_64` only, and its juliaup line asked questions. It now starts with *Check the machine*,
  which changes nothing and prints the system, the architecture, the two `sysctl` keys of user
  namespaces, the login shell, the user manager of systemd, the groups that show an administrator,
  what an earlier install left, the `apt-get` candidates and the Secret Service. *The
  dependencies* adds jq to the `apt-get` line, sets the gitleaks and RTK file names in one
  `case "$(uname -m)"` block for `x86_64` and `aarch64` (another value prints a message and
  downloads nothing), installs RTK 1.0.1 after the `sha256sum -c` of its `checksums.txt`, runs the
  juliaup installer with `--yes`, and checks the version of each tool. A new section, *The
  frontends*, installs Claude Code, OpenCode 2 (`opencode.ai/v2/install`; the installer without
  `v2` installs OpenCode 1 only) and oh-my-pi (with `--binary`, so that `omp` goes into
  `~/.local/bin`), each with its directory, its update command, its `PATH` line and a version
  check, and an optional check of Claude Code against its signed manifest. A new *Kaimon* step
  installs Kaimon with `Pkg.Apps.add`, and *The jobs* refers to it. *`harness install --apply`*
  makes the two directories that the install needs, the tree instructions and the OpenCode
  configuration; it no longer makes `~/.claude/skills`, which the install makes itself.

- **A new guard hook, `git-archive-output.py`, refuses `git archive -o` and names the read that
  needs no prompt.** Agents wrote an archive of a commit to read its unmodified tree, usually the
  base of their branch: the permission log holds 35 such prompts from 2026-10-04 to 2026-10-19,
  from critics, builders, shepherds, reviewers and main sessions. `-o` writes outside the sandbox,
  so the `ask` rules on it prompted for what is a read. The hook exits 2, and its message gives
  `scripts/base-tree.jl` for the tree or some paths of it, `git show` for one file and
  `git ls-tree` for the list of files; a tar file that is itself the result goes to the user. It
  reads the option in every spelling git takes, which no glob states: behind other short options
  (`-vo`), with the value attached (`-oout.tar`), as a prefix of `--output`, and after global
  options. Claude Code runs it on `PreToolUse`/`Bash`, and the guards of oh-my-pi and OpenCode run
  it on each shell call. It starts in about 18 ms, as `gh-api-writes.py` does. `hooks/probe.py`
  holds 29 cases for it. The `ask` rules stay for a call that reaches git another way.

- **`OMP-DELTA.md` says that a compound command and a `git -C` run without a prompt.** It said
  they cost a prompt. Under `yolo` only a `prompt` pattern asks; a probe in an interactive
  oh-my-pi session ran `git -C <repo> status` and `cd <repo> && git log` unasked, and
  `cd <repo> && gh pr create --help` asked.

- **The pre-push hook runs `harness leaks` on a push of a topic branch.** It gated a push to
  `main` only, and CI cannot run `harness leaks`, because the leak list is in the user's profile.
  So a changelog entry of #53 named a private repository, passed CI, merged on GitHub, and the
  next push of `main` was refused for a leak it did not add. A push of any ref other than `main`
  now gets `harness leaks --commits` over the tree at the pushed SHA and the commits that the
  push sends (remote..local, or the commits that `origin/main` lacks for a new branch), in a
  `git clone --shared` at that SHA, and a hit or a failure refuses the push with one line. A
  branch runs no gitleaks check and no suite; CI runs them. The path for `main` does not change.
  Three cases of `harness test` push a fixture branch: a clean branch passes, a branch whose new
  commit adds the leak string is refused although its next commit removes it, and a branch whose
  tree holds the string of an earlier commit is refused. `development.md` and `setup-macos.md`
  describe the branch check.

- **`glab auth status --hostname <host>` runs without a prompt, and the forms that print the
  token are refused.** Only the bare `glab auth status` was allowed, so a check of one GitLab
  instance asked. `glab auth status --show-token`, `-t` and `-at` print the token, so `deny`
  holds `glab auth status *--show-token*`, `*-t*` and `*-at*`; a host name that contains `-t`
  is refused too. The permission block of `opencode.jsonc` carries the three `deny` rules.

- **A clone under `.worktrees/` or `.scratch/` gets no trust command in the report.** The global
  `CLAUDE.md` told a session to give `harness trust --apply` after every clone under
  `~/Research`, and named only a worktree as an exception. `harness trust` skips `.worktrees/` and
  `.scratch/`, so for a temporary clone there the command adds no entry, and the report asked the
  user to trust a clone that was deleted after its merge. The rule now names both directories.

- **A fix round runs only the mutants that its fix touches.** Round 1 still runs the full set.
  On 2026-10-19 the second fix round of the oh-my-pi part M5 (the learning package) spent
  about 76 of its 103 minutes on mutant runs: its builder ran all 36 mutants of the earlier
  rounds again, in six lists of 20 or fewer, so each mutant ran cold, at about a minute each, with
  a smoke run per list; that one run took 37 minutes. The fix changed three test files and no source file, so none of the 36
  had a site in it. The new section *A fix round's mutants* of `skills/build-part/evidence.md`
  selects four kinds: an own mutant per guard, branch, comparison and decided edge of the fix;
  an earlier mutant whose `from` lies in a function that the fix changes; a named mutant whose
  test in *Tests catch* the fix changes or deletes a line of; and each survivor that the last
  critic names. Every other mutant keeps its earlier verdict, and the selected ones run in one
  list. `julia-builder` and `part-builder` follow it in a fix round, their *Mutants* table gives
  the kind of each selected earlier mutant and the count of kept verdicts, and `build-part` and
  `build-reviewed` name it in their check of the report. `mutate.jl` does not change. A case of
  `harness test` checks that the section holds its four rules and that the four files point at
  it.

- **The walk-throughs cite the lines that state their steps.** Each edge of a walk-through
  figure cites the `file:line` that states its step, and `harness test` checked only that the
  line exists. Ten edges of `walkthrough-build-part.toml`, all eight of
  `walkthrough-build-reviewed.toml` and two of `walkthrough-install.toml` cited a line that does
  not state the step, five of them a blank line. Each now cites its step, and `harness test`
  also refuses a citation of a blank line.

- **Agent shell commands run Julia with two threads and two BLAS threads.** A part runs up to
  three critics and a suite at the same time, and an unset `OPENBLAS_NUM_THREADS` gives each Julia
  process one BLAS thread per core. On 2026-10-19 two oh-my-pi parts that ran together held the
  load average at 160–240 for almost two hours, and the 3600 s job deadline killed a full suite
  run. The settings template's `env` now sets `JULIA_NUM_THREADS=2` and `OPENBLAS_NUM_THREADS=2`,
  and OpenCode's `plugins/env.ts` sets both. `harness install` now adds each variable of the
  template's `env` that `~/.claude/settings.json` lacks, and keeps a value that the file sets;
  before, it added a missing top-level key only, so a new variable never reached an existing
  file. oh-my-pi has no `env` setting, so the install warns, with the lines, until
  `~/.omp/agent/.env` or the environment sets each variable of the template's `env` but the
  `CLAUDE_CODE_*` ones. This also covers `JULIA_PKG_USE_CLI_GIT`, which oh-my-pi's shell commands
  did not get. A `-t` flag on a command still sets its Julia threads, and a script can still call
  `BLAS.set_num_threads`.

- **Setup on Linux gives all the steps.** Before, `docs/src/setup-linux.md` gave the dependencies
  only and said the other steps were coming. It now has the sections of `setup-macos.md`, each
  with what it does, why and its check, for Debian and Ubuntu, with the package names and versions
  checked on Ubuntu 26.04 only, and three sections of its own: the sandbox of Claude Code
  (bubblewrap and socat, with a `bwrap` check), the jobs (the `systemd --user` units and linger),
  and a machine reached over SSH. Its
  `apt-get` line no longer installs gitleaks, because Ubuntu 26.04 packages 8.16.0, below the
  minimum 8.21: gitleaks comes from its release into `~/.local/bin`, checked against the
  release's checksum file, and only a push to the harness needs it. The page is a newcomer page
  of `docs/scripts/newcomer.mjs`. `dependencies.md` names bubblewrap and socat for the sandbox on
  Linux. The README links the page for Linux, and `setup-macos.md` says that it gives all the
  steps for Linux.

- **A session cannot replace OpenCode's binary in `~/.opencode/bin`.** OpenCode's installer puts
  it there on Linux, and the template protected `~/.local/bin` but not this directory. The
  template now has `~/.opencode/bin` in `sandbox.filesystem.denyWrite` and
  `Edit(/{home}/.opencode/bin/**)` in the denies, beside `~/.local/bin`; `harness permissions
  --apply` writes the `Edit` deny into the OpenCode and oh-my-pi lists. OpenCode's own updater
  runs outside the sandbox and still writes the directory.

- **A session cannot read `glab`'s configuration file.** Without a keyring, as on a Linux host
  with no Secret Service, `glab auth login` stores the token in `config.yml`, and the template
  denied a read of `gh`'s `hosts.yml` but of no `glab` file. The template now has
  `~/.config/glab-cli/config.yml` (Linux) and `~/Library/Application Support/glab-cli/config.yml`
  (macOS) in the `Read(…)` denies, in `sandbox.filesystem.denyRead` and in
  `sandbox.credentials.files`; `harness permissions --apply` writes both into the OpenCode and
  oh-my-pi deny lists. `glab` runs outside the sandbox, so it still reads its own file.

- **`harness trust` skips `.scratch/`.** A critic's probe clone or a source checkout there is a
  git repository, so the walk listed each one, and `--apply` trusted dozens of throwaway
  directories. The walk now skips a directory named `.scratch`, as it skips `.worktrees`. An entry
  that an earlier `--apply` wrote stays in `~/.claude.json`.

- **A model of `providers.toml` can fix its reasoning effort for both frontends, with `effort`.**
  Before, only OpenCode's own `options.reasoningEffort` held it, so oh-my-pi sent the effort that
  the agent asked for, or none. GWDG SAIA answers `high` slowly or not at all on some models, and
  a model whose default is `xhigh` needs `none`. `effort = "none"` gives OpenCode
  `options.reasoningEffort`, and gives oh-my-pi `reasoning = true`, a `compat.reasoningEffortMap`
  that maps each of its thinking levels to the effort, and `compat.reasoningDisableMode =
  "none-effort"`. Without `reasoning`, oh-my-pi 18.12.0 sends no effort; without the disable mode,
  a Qwen model on a generic host sends `enable_thinking` and no `reasoning_effort`. A model with
  neither `effort` nor `reasoning` gets `reasoning = false` under oh-my-pi, which sends no effort,
  as OpenCode does; before, oh-my-pi sent the agent's level, such as `high`. A probe of oh-my-pi
  18.12.0 against a local endpoint that recorded each request measured both: `effort = "none"`
  sent `reasoning_effort: "none"` at thinking `high`, `off` and unset, `effort = "medium"` sent
  `medium` at `high` and `none` at `off`, and `reasoning = false` sent no effort. One difference
  stays: when an agent turns thinking off, oh-my-pi sends `none`, and OpenCode still sends the
  fixed effort. A frontend's own `opencode` or `omp` table merges over `effort`. A blank `effort`
  exits 2.

- **The model providers of OpenCode and oh-my-pi are in one file, `providers.toml` beside the
  profile, and each provider is written once.** The profile held the same accounts twice, as
  `opencode_providers` and `omp_providers`, in each frontend's own keys. A provider of the new
  file is a table with neutral keys: `api` (`"anthropic"` or `"openai-compatible"`), `url`, `name`,
  `key` (`{env:VAR}` or `{file:PATH}`), `frontends`, and models with `name`, `reasoning`, `context`
  and `output`. `harness install` writes each provider into the `provider` object of
  `opencode.jsonc` and into oh-my-pi's `models.yml`. It writes the `url` of an `"anthropic"`
  provider without its `/v1` for oh-my-pi, whose client appends `/v1/messages`, and a `{file:…}`
  key as `!cat PATH`. The tables `opencode` and `omp` hold a frontend's own keys, of a provider or a
  model, such as OpenCode's `tool_call` and `reasoningEffort`. A literal key, an unknown key, an
  `"anthropic"` URL without `/v1` and a context limit of `models.toml` on a provider of the file
  exit 2 and name the file. For oh-my-pi the last one is new: such a limit joined the provider's
  table before. A model of oh-my-pi now has the `name` of its table. The placeholder of
  `opencode.jsonc` is `{providers}`, which `harness render` and `harness leaks` render empty.
  **Migration:** a profile that still has `opencode_providers` or `omp_providers` makes
  `harness install` exit 2. Write each provider once in
  `~/.config/research-harness/providers.toml`, then remove both keys from the profile.
  `examples/providers.toml` shows the form, and [profile.md](docs/src/profile.md#the-providers)
  maps each key to each frontend.

- **The hosts of the Claude Code network rules are in `settings/network.toml`, not in the settings
  template.** The template held each host twice by hand: 73 `WebFetch(domain:…)` rules in
  `permissions.allow`, one of them the placeholder `{extra_domain}`, and their mirror plus the infrastructure hosts in
  `sandbox.network.allowedDomains`, which `harness settings domains` checked. The new file has
  three arrays with comment headings: `allow` (72 hosts), `infrastructure` (17) and `deny` (empty),
  and a table `[deny_reasons]`. `harness install`, `harness render` of the template and the
  `harness settings` verbs generate the rules from it: `allow` X gives `WebFetch(domain:X)` and X in
  `allowedDomains`, with `*.X` when X is its own registrable domain; `infrastructure` X gives X in
  `allowedDomains` as written; `deny` X gives `WebFetch(domain:X)` in `permissions.deny`, except for
  an entry with a port, and X in `sandbox.network.deniedDomains`, with the reasons in
  `sandbox.network.deniedDomainReasons`, which Claude Code 2.1.302 reads. An optional overlay
  `network.toml` beside the profile adds its own entries, and a `deny` entry of either file removes
  each matching allow host from the generated lists. A URL, a port outside `deny`, `*.` in `allow`,
  a host in `allow` and `deny` of one file, a reason for no `deny` entry and an unknown key exit 2,
  naming the file and the key. The generated settings equal the earlier ones as sets of hosts, and
  every other key is unchanged. `harness settings domains` is removed: no hand-kept mirror is left
  to check. OpenCode and oh-my-pi do not read the lists; their output is unchanged.
  **Migration:** the profile key `extra_domain` is retired, and a profile that still has it makes
  `harness install` exit 2. Move its hosts into the `allow` array of
  `~/.config/research-harness/network.toml`, then remove the key. `examples/network.toml` shows the
  overlay.

- **`opencode_providers` in the profile is TOML tables, one `[opencode_providers.<name>]` per
  provider, the same form as `omp_providers`.** The JSONC text in a TOML string was hard to edit.
  `harness install` serialises each provider table as JSON and writes it as one entry of the
  `provider` object of `opencode.jsonc`, after the entries of the `context_limits`. A model id with
  `.`, `/` or `:` is a quoted key, such as `models."org/model:7b"`. Comments stay in the profile;
  the generated `opencode.jsonc` holds none. The check that a context limit names no provider of
  the profile compares the parsed names, not text, and still exits 2 with the same advice. The
  renderer gains one rule for this: a table placeholder alone on its line renders as the members
  of a JSON object, so `harness render` and `harness leaks` render the template too.
  **Migration:** a profile with the string form makes `harness install` exit 2, with a message that
  names the profile and the new form; there is no converter. Convert the profile before the next
  install: each top-level entry of the JSONC object becomes a table `[opencode_providers.<name>]`,
  each of its keys a TOML key, and each model a table `[opencode_providers.<name>.models."<id>"]`.
  `examples/profile.toml` shows the form.

- **Six remedies for the harness friction of the Claude Code loop.** The harness audit sorted 50
  failure lines of class *harness* into nine mechanisms; four were still open. Each remedy has its
  own cases in `harness test`:
  - A critic's or an advisor's `git init`, `git clone` or `git checkout` ran in the builder's
    worktree, in `Tasks` or in `Environment`, because a `cd` outside the agent's working
    directories is reset before the next call (9 lines). `sandbox-semantics.py` refuses a `git
    init` or `git clone` whose working directory, or target below it, is inside a work tree, with
    a message that names the reset. `julia-critic`, `part-critic` and `advisor` say that a probe
    needs no repository: `git diff --no-index` compares copies. The cases that let `git init` and
    `git clone` pass in the probe's own work tree now run in a directory that is no work tree.
  - `mutate.jl` wrote a list's result beside the list, under the worktree's `.claude/scratch/`,
    where the sandbox refuses the write (7 lines). It writes the result under
    `~/Research/.scratch/mutants/`, named for the package directory, the list and a hash of the
    list's path, and prints the path on its `result:` line; `gate.jl` reads the result from that
    line. The lists stay where they are.
  - A Kaimon `ex` without `ses` ran in another agent's session (part of 8 lines). The new hook
    `kaimon-session.py`, on `mcp__kaimon__ex|mcp__kaimon__manage_repl`, refuses an `ex` without
    `ses` and a `manage_repl` without `session`. `check_eval` takes only an `eval_id` and no session
    key, so the hook does not cover it. `build-part/evidence.md` says to probe in a fresh process
    when `start_session` times out twice, and its `manage_repl` restart, like the one in
    `rules/julia-code.md`, names the session.
  - The critic's `rsync` copy and `run-tests.jl`'s `copy_command` copied `.env.*` files, and the
    sandbox, which denies them, left temporary files that no one could remove (2 lines). Both
    copies exclude `.env` and `.env.*`.
  - A spec gave an isolated builder a file outside its repository (2 lines). `plan-parts` keeps a
    part's *Files* in one repository and makes a file elsewhere a dispatcher step; `spec-gate.py`
    reports `SPANS <repositories>` and exits 1 for a part, other than a `direct` one, whose *Files*
    span two. Over the 438 parts of the 200 task files, it reports only the parts of one archived
    task file whose `repository` cell names `Environment` and whose files are in `Harness/`.
  - `worktree.py` copied a stale `Manifest.toml` into a new worktree, and `harness install` read
    an unpulled checkout (3 lines). The hook copies the manifest only when it holds every package
    of the worktree's `[deps]` at a version inside its `[compat]`, and else says why. Pkg's
    `project_hash` is not the test, because Pkg computes it with an internal function whose input
    changes between Pkg versions. On the main checkouts of the tree, 8 of 43 manifests lie outside
    their own `[compat]`. `harness install` warns, without a fetch, when its checkout is behind its
    local `origin/main`.
  - oh-my-pi's guard extension and OpenCode's guard plugin run the R1 and R3 checks too. They run
    `sandbox-semantics.py --work-tree`, its work-tree check alone, on each shell call, because they
    have no sandbox for its other shapes; the check follows each `cd` of the command, since neither
    refuses a `cd … &&` form. They run `kaimon-session.py` on their names of the Kaimon tools,
    `mcp__kaimon_ex` and `mcp__kaimon_manage_repl` under oh-my-pi, `kaimon_ex` and
    `kaimon_manage_repl` under OpenCode. `harness install` copies both scripts into each
    frontend's `hooks/`.

- **`skills/build-part/edges.md` states the same-error-type guard case as a mechanism, in the
  present tense.** The example of the edge class "a case meant for one guard that a later guard
  also catches" told one part's history in the past tense. It now says that a fix which adds a
  later guard raising the same error type makes an `isa` test pass whether or not the earlier guard
  is dropped, so a named mutant survives. The citation and the advice to assert the refusing
  guard's own phrase are unchanged. The tense lint reports 7 hits in the file in place of 8.

- **OpenCode's default model is `opencode-go/deepseek-v4.1-flash`, on the paid OpenCode Go plan,
  in place of `opencode/deepseek-v4.1-flash-free`, Zen's free DeepSeek.** The default model is the
  dispatcher's seat, and a dispatcher whose free seat stops stalls the whole builder-critic loop.
  The builder's and the verifier's seats, and the free seats of the diagnostic agents, come from
  the user's `models.toml` and are unchanged here.

- **oh-my-pi keeps a fallback that only switches the provider.** The empty fallback chains of
  `harness.yml` also replaced a chain in `config.yml` that sends a model to the same model through
  another provider, such as `opendesign/deepseek-v4.1-flash` to `opencode-go/deepseek-v4.1-flash`.
  That model was the session's default and the `medium` tier's, so a rate limit on one provider
  stopped the session instead of moving it to the other account. The install reads
  `retry.fallbackChains` of `config.yml` and writes no empty chain for a model whose chain names
  only the same model, with or without a thinking level or as `<provider>/*`. A chain to another
  model, a key with no selector and a form that the install cannot read still get the empty chain,
  so a council seat still keeps its model. A change of that chain takes effect at the next install.

- **oh-my-pi: no revived agents, a Kaimon timeout of 120 s, a path guard that reads a pattern as
  a pattern, approvals returned to the caller, and no silent model fallback.** Five failures that
  only the oh-my-pi runs showed, with their mechanisms:
  - A parked agent was woken by `write agent://<name>` 11 times in 6 sessions, 3 of them by a
    sub-agent; a woken agent returned the output of its earlier run, or worked the same worktree
    beside its replacement. `OMP-DELTA.md` has the dispatcher continue an agent only by a new
    spawn with the last report as the handoff, also for a placeholder or empty report; the new
    `write` section of `UNDER-OMP.md` tells each agent with the write tool never to write to
    another agent; and the guard extension refuses a sub-agent's write to `agent://`, which it
    tells by oh-my-pi's `ctx.agent.kind` (`"sub"`, the session's `"main"`).
  - oh-my-pi cut an MCP call after 30 s in 141 of 445 runs. `mcp.json` gives Kaimon a `timeout` of
    120 000 ms, above Kaimon's own move of a slow eval to the background at about 30 s.
  - The path guard cut a word with a glob character back to its last `/`, so a pattern such as
    `/\[compat\]/` became `/`, which holds every denied path: 55 refusals in 32 runs. A glob now
    reaches only the names that its first glob segment matches, and the program argument of an
    awk, sed or grep is no path. Of the 65 such refusals in the transcripts, 52 pass; the other
    13 hold no pattern: a `find /`, which still refuses, a `tr / _`, and 11 heredoc bodies whose
    division `/` stands in a command that a word such as `tree` or `zip` in the body marks as
    recursive. 20 probe cases check both sides: 11 pattern forms pass, 9 path forms still refuse.
  - A sub-agent has no approval prompt: 9 prompts in 2 runs, and one builder dropped `--repo` from
    `gh pr create`, which then matched no rule and ran unasked under `yolo`. `UNDER-OMP.md` has a
    sub-agent return a command that needs approval to its caller, and the finish builder return
    `gh pr create`; `harness.yml` ends `bash.patterns` with a `prompt` for `gh pr create*`, so the
    command asks with or without `--repo` unless `-R` or `--repo` names an organisation first.
    Claude Code's template is unchanged: it already asks for an unmatched command.
  - After one rate limit, oh-my-pi moved a critic seat to another model in 2 runs, through
    `retry.fallbackChains`. `harness.yml` gives each model of an agent or a seat an empty chain,
    which oh-my-pi's exact-model lookup takes before a role or `default`, so a seat fails on its
    own model. The session's model loses its chain too where an agent shares it.

- **OpenCode: two levels of sub-agents.** `opencode.jsonc` sets `experimental.subagent_depth` to
  2, so that a builder that the dispatcher spawns can spawn `julia-branch-verifier` or a `reader`.
  OpenCode allows one level by default: in a probe, `julia-builder` could not spawn `reader` and
  got "Subagent depth limit reached (1)".

- **The builders reread the text of their change as the last step of every round.**
  `julia-builder` (step 9) and `part-builder` (step 8) list each comment, docstring, message,
  `CHANGELOG.md`, `KNOWN_ISSUES.md`, README and docs line that the diff adds or changes, each one
  in or next to a changed block, and each one that names what the diff changes; they check each
  claim against the code, the spec or a short command, and fix what is false, has no support, is
  stale, tells history, records a branch-caused defect in `KNOWN_ISSUES.md`, or breaks the file's
  form. A fix round rereads the text that its fix adds, changes or makes false; the finish rereads
  the whole branch before the verifier and fixes text only. A new *Text checked* table in the
  report lists the lines checked and fixed, and `build-part` and `build-reviewed` hold a report
  without it back from the critic. Before, no build step reread the text: the builders left it to
  the verifier, which runs once after the last critic, so 51 of 80 false text lines in the audit
  sample were found after the PASS or merged false. In a replay on 48 recorded heads the text pass
  found 49 of 76 such lines (64 %), with a median of 2 false alarms per unit. A lint script over
  the diff found 12 of the 33 lines of its classes (36 %) with 260 false alarms, and is not added.
  The critics and the verifier are unchanged.

- **The builders write and run mutants of their own change.** `julia-builder` and `part-builder`
  write one mutant per guard, branch, comparison and decided edge that the change adds or
  changes, in any language, and run each before they return; a fixer does the same for its fix.
  Each survivor is closed with a test or justified as no-defect (equivalent, dead code, or message
  text that no clause names), and a new *Mutants* table in the report lists every mutant with its
  verdict. `build-part` and `build-reviewed` hold a report back from the critic while the table
  is missing or holds an open survivor; `evidence.md` adds the kind *own* to *Which mutants run*.
  Before, `julia-builder` ran only the named mutants and wrote no others, so a decided edge with no
  named mutant got no test. In a replay on 31 recorded round-1 heads the builders' own mutants
  found 29 of 42 tests that cannot fail (69 %), in every language, with a median of 2.5
  no-defect survivors per unit; the generated sweep of `mutants.jl` found 5 of 10 Julia lines,
  none beyond them, and timed out on 2 of 3 large-package units, so it stays where a plan's §L
  asks for it. The critics are unchanged.

- **`plan-parts` checks the facts of each spec before it is final.** One `reader` agent per part
  measures each fact that the part's section states, and each fact of another section that its
  clauses rest on, at `origin/main` of the part's repository, and marks it `holds`, `false` or
  `cannot`; the planner fixes each `false` fact before the build. The brief is
  `skills/plan-parts/premise-check.md`. On 21 recorded specs the same check found 96 false facts
  at 0.24 false alarms per spec, for about $1 per spec, but only 4 of the 18 stale premises that
  cost a loop a round or an advisor call, so it is a check of stated facts, not a guard against
  stale specs. It runs in a `reader`, not in the planner's context, because that is the measured
  form and the planner reads its own facts as true. `calls.toml` has the new edge.

- **OpenCode: the file tools are refused outside the allowed directories, and a `**/` read deny
  also binds a file of the project root.** OpenCode v2's built-in rule set allows every path and
  the last matching rule wins, so a path outside every `external_directory` allow entry was
  allowed; the absolute read denies of the credential files do not bind the `read` tool, so they
  did not close that gap. The generated block starts
  `external_directory` with `"*": "deny"`, before the allow entries. v2 matches a read pattern
  against the path relative to the project root, with `*` crossing `/` and both ends anchored, so
  `**/.env` did not match `.env` in the root and `**/*.pem` did not match `x.pem`. Each `**/X`
  read rule is followed by its root form `X`; `harness permissions` reports their count, and
  `plugins/guard-paths.json` leaves them out, because the path guard tests absolute paths, where
  `**/X` already matches.

- **The OpenCode agents `local` and `qwen-worker` are retired.** They ran a local model for
  offline work and were an experiment; no run of 2026-10-02 to 2026-10-16 used either. Every
  OpenCode agent is rendered from `agents/`, so the adapter drops `adapters/opencode/agents/`
  and its checks. `opencode.jsonc` keeps the local model as `small_model`. `harness install`
  reports the two installed copies as EXTRA, with the command that removes each.

- **`harness install` adds each key of the settings template that `~/.claude/settings.json`
  lacks.** It replaced the four sections `permissions`, `hooks`, `sandbox` and `modelSettings` and
  installed no other key, so `cleanupPeriodDays` of the template never reached the installed
  settings. A key that the file has keeps its value, so the model and the effort that the app
  writes stay. The dry run shows each added key in its diff, as `null` against the template's
  value. A key of the template that the user deletes from the file comes back at the next
  install; to keep another value, set it in the file. A missing settings file is created with
  every key of the template.

- **New: three audit scripts measure the instruction files.** `instructions.jl` writes one table of
  the agents, skills, rules, commands and global files of a harness checkout, the tree's own
  instructions and rules, every `CLAUDE.md`, every evidence page and every memory file: tokens,
  when each loads, how many runs loaded it in a window, and which failure classes of the
  taxonomy cite it. A load is what the transcripts record: the `instructions` record at the start
  of a Claude Code run, a rule or `CLAUDE.md` that loads on a Read, a Skill call, an agent type, a
  slash command, or a Read of the file. `citations.jl` checks what these files cite: each path,
  command, long flag, tool name, agent and skill. It reads the flags from the help of `git`, `gh`,
  `glab`, `juliaup`, `rtk`, `jq`, `rg` and `harness`, and from the source of a script it finds.
  `tense-lint.jl` reports each word that dates an instruction file or tells its history, the list
  of `rules/instruction-files.md`, outside code, quotations and mentions, and exits 1 on a hit.

- **Transcripts stay 90 days, and the one-hour prompt cache of three agents takes effect.** The
  settings template sets `cleanupPeriodDays` to 90. Claude Code deletes a transcript after 30 days
  by default, and a re-measurement two weeks after a change must still read the baseline of the
  two weeks before it. `harness install` writes the `cacheTtl:` line of an agent below a new
  `experimental:` line. Claude Code 2.1.299 to 2.1.301 reads an agent's prompt-cache TTL there
  alone and ignores a top-level `cacheTtl:`, so the `cacheTtl: 1h` of `julia-pr-shepherd`,
  `julia-test-runner` and `ci-triage` had no effect: from 2026-10-11 on, 39 shepherd runs wrote
  32.7 M tokens to the 5-minute cache and none to the one-hour cache. Claude Code still refuses
  the one-hour TTL of an agent while a subscription is in overage, and a `subagentPromptCacheTtl`
  setting or `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` takes precedence over the agent. The sources
  keep `cacheTtl: 1h`; OpenCode and oh-my-pi drop it, as before.

- **Waits move out of the large contexts, and builders get the rule for comments.** In 14 days of
  transcripts, 161 of the 182 cache rewrites of `julia-pr-shepherd` followed a CI wait
  (`gh run watch`, `gh pr checks`), 40 % of its input cost, and 32 of the 40 rewrites of
  `part-builder` followed a resume after its critic. A sub-agent's cache lives 5 minutes; the
  `cacheTtl: 1h` of the shepherd's frontmatter gave no one-hour write in its 39 runs from
  2026-10-11 on. So `julia-pr-shepherd` no longer waits for CI: it pushes, names the runs of the push and the
  `gh run watch` command for each, and its caller waits. `build-reviewed` spawns a new
  `part-builder` for each later round, with the last report as the handoff note, as `build-part`
  does for `julia-builder`. The two facts about reading a red `gh run watch` move to `ci-triage`.
  `julia-builder` and `part-builder` state that a comment or docstring tells no history and names no
  part, clause or round; only the critic's file and the CHANGELOG rule said so. `build-part` asks
  its session to say so when it does not run on sonnet: all 32 dispatcher sessions of the skill in
  the window ran on Opus. `transcripts.jl` records what each run waited on before a cache rewrite,
  and report 7 of `report.jl` lists the three most frequent per agent type.

- **New: the audit scripts in `scripts/audit/` measure the harness from its own transcripts.**
  `transcripts.jl` reads the sessions of Claude Code, OpenCode and oh-my-pi in a window of time
  and writes one table of runs: agent type, model, effort, tokens by kind, input cost, tool calls,
  verdict, part, pull requests, the rules that loaded, and the cache rewrites after a pause.
  `report.jl` turns it into the cost per part and tier, the critic rounds to a PASS, the advisor
  and arbitrator calls, the largest tool results, the first-call context per agent type and, with
  the output of one `gh api graphql` query, the commits and checks of each loop pull request.
  `sample.jl` draws a seeded sample of parts as dossiers for a failure taxonomy, and `taxonomy.jl`
  counts the readers' failure lines. `crosscheck.sh` computes two totals again with `jq`, and they
  must agree to the token. Output tokens stay out of the cost, because most transcripts do not
  record them completely.

- **The pre-push case of K35 passes inside a real `git push`.** `prepush_case` linked its tools
  from the PATH, and inside a git hook git puts its exec path first there, so the case linked the
  `git` of `libexec/git-core`. On macOS, that `git` started from a link looks for `git-upload-pack`
  beside the link, so the hook's `git clone` failed and every push to `main` was refused, while CI
  and a plain `harness test` passed. The case links its tools without a `git-core` directory, and
  `harness test` runs it a second time with git's exec path first, as a hook does.

- **The quick fixes: K10, K16, K26, K27, K29, K30, K31, K32, K33, K34, K35 and K68 leave
  `KNOWN_ISSUES.md`.** A stray settings file nested deeper than the JSON parser reads is a warning
  line of `harness install`, as one that is not JSON is, not a traceback (K68). Under OpenCode an
  edit of the installed `~/.claude/rules/**` is a deny, as under Claude Code: the OpenCode-only
  `ask` that came after the template's deny is gone, from `opencode.jsonc` and its fixtures too
  (K10). The OpenCode guard plugin also checks the form without `rtk` when white space comes
  before `rtk` or a tab after it, so ` rtk git add -A` and `rtk<tab>git add -A` are refused (K27),
  and a `$OPENCODE_CONFIG_DIR/guard-paths.json` that is present and cannot be read or is not JSON
  refuses every `shell` call, as a missing global list does (K26); `docs/src/components/adapters.md`
  says so. The oh-my-pi path guard drops a leading `:` before `./` and `../`, as before `/` and
  `~`, so `write {"path": ":../.claude/hooks/x.py"}` from `~/Research` blocks (K16). New probe
  cases give the OpenCode guard plugin a context with no `location`, where the session's directory
  is the `node` process's (K29), and a guard script that prints a `deny` decision (K30).
  `harness leaks --commits` labels a hit in a path that git quotes, such as `café.txt` or
  `a"b.txt`, with the path, not git's quoted form (K31). New cases of the leak gate run
  `cmd_leaks` on a fixture whose `origin` is not this checkout's (K32), take an evil merge whose
  paths are each named once, one of them differing from the second parent only (K33), and a merge
  whose resolution adds a leak line that neither parent has (K34); a case in `harness test` runs
  `.githooks/pre-push` on a fixture checkout with stubs of gitleaks and `bin/harness`, and checks
  the `origin` URL that `harness leaks` sees in the hook's clone (K35). K75 records that a `~`
  with no `/` after it, as in `read {"path": "~.netrc"}`, passes the oh-my-pi path guard.

- **No public file cites a notes page of the tree: K66, K67 and K70 leave `KNOWN_ISSUES.md`.**
  `adapters/claude/CLAUDE.md`, `RTK.md`, `opencode.jsonc`, `githooks/pre-commit`,
  `launchagents/claude-autocommit`, four rules and three skills named an `Environment/Notes/` page
  that this repository does not hold, and `launchagents/kaimon.plist`,
  `scripts/known-issues-similar.py`, `scripts/session-tokens.py`, `skills/build-part/SKILL.md`,
  `hooks/worktree.py` and `rules/generated-hooks-and-workflows.md` named one by its file name. A
  sentence that held only the pointer is gone; a sentence that also states a fact or an
  instruction keeps it. `rules/instruction-files.md` says "an evidence page" and "the hooks page".
  The tree instructions keep the pointers (K66, K67). K73 records six citations of a task file,
  another class. The case of `install_cases.target_cases` for an OSError in the write captures the
  plan line that `install_file` prints, and asserts it, so `install.selftest()` prints no stray
  `x.md  INSTALL` line (K70).

- **OpenCode's default model is `opencode/deepseek-v4.1-flash-free`, Zen's free DeepSeek, in
  place of `opencode-go/deepseek-v4.1-flash`.**

- **The docs checks and `run-tests.jl`: K39, K50, K51 and K53 leave `KNOWN_ISSUES.md`.** The log, the
  times file and the one-process driver of a `run-tests.jl` run carry its process ID after the
  date stamp, so two runs of packages of one name, started in one second, write files of their
  own; a case asserts that their logs differ and name each run's process ID (K39). A throw in the
  setup of a figure component, such as `<WalkThrough name="instal" />`, makes `npm run docs:build`
  exit 1: an error handler of the theme logs it during the server render and sets the exit status,
  where VitePress went on to `build complete` and exited 0 (K50). The effort of a walk-through box
  passes only when an entry of `calls.toml` gives the box's agent that effort from a caller that a
  skill or agent box of the same walk-through shows; a spawn at that effort by any other caller no
  longer passes (K51). The colour scan of `docs:check` also refuses a CSS named colour as a quoted
  string or after `fill`, `stroke` or `color`, such as `const TOKEN = 'red'`; `none`,
  `currentColor`, `transparent` and `inherit` pass, and so does an accent name of `figures.css` as
  a quoted string after `accent`, as in `accent: 'teal'` (K53).
  `docs/src/components/other.md` says that `repo-drift.js` reports `TagBot.yml` as missing in an
  experiment, as expected, and `docs/src/components/harness.md` names the checks of the targets
  that `harness install` makes before it writes.

- **Seven small fixes in the Python code, and one decision: K8, K11, K20, K21, K46, K47, K62 and
  K63 leave `KNOWN_ISSUES.md`.** K8 is closed by the user's decision: no `ask` rule surfaces an
  edit of the instruction sources, because the git history and the pull request are the review of
  such an edit. The stamp `~/.claude/.harness-install.json` names each source of this repository
  below the profile's `harness` path, whatever checkout runs `harness install --apply`, so a dry
  run from a worktree with the same sources no longer lists the stamp as `REPLACE`, and the `SessionStart` hook reads
  the profile's checkout. With no `harness` key the stamp names the running checkout, as before,
  and a `harness` value that is not an absolute path exits 2 (K11). `omp_agent_cases` uses
  `Scratch.tail` in place of its own copy (K20). A `[claude]` model that is not a plain YAML
  string, such as the Bedrock ID `us.anthropic.claude-opus-4-1-20250805-v1:0` or the Vertex ID
  `claude-opus-4-1@20250805`, loads and is written into `model:` as JSON writes the string; a
  model with a control character, or a word that YAML reads as a boolean or null, still exits 2
  (K21). A stray settings file whose `allow`, `ask` or `deny` is not a list is one warning line
  that names the file and the key, not one rule per character (K46). The merge of
  `~/.claude/settings.json` keeps a tab indent, and writes a one-line file on one line. When it
  writes the file, a number outside the owned sections that it would write in other text, such as
  `1.10`, `1e400` or `1E5`, makes the dry run and `--apply` exit 2 with one line that names the
  key, and nothing is written (K47). The `PATH` check of the units fails an element at or below
  `$TMPDIR` or its real path, `/var/folders` or `/private/var/folders`, which the live sandbox
  lets a session write; a session's working directory has no fixed value and stays a recorded
  limit, K71, in K62's place (K62). A curated skill that fails `parse_file` is one wrong case of
  the skill-triggers cases and one of the `calls.toml` cases of `docs.py`, and `harness test` goes on to its summary line, where it
  exited 2 with none (K63). The scratch
  profile of the install cases names this checkout as `harness`. The comment of `[claude]` in
  `examples/models.toml`, `docs/src/architecture.md` and `docs/src/components/other.md` state the
  new rules of the model and of the `PATH`.

- **Nine missing cases and checks: K6, K15, K17, K19, K45, K49, K52, K64 and K65 leave
  `KNOWN_ISSUES.md`.** The contract sweep runs one verb through `sweep.run`, whose timeout is a
  parameter; a case gives it a child that outlives 1 s and passes the result through the sweep's
  own checks, now the functions `dry_run_ok`, `refused_ok` and `applied_ok`, each of which counts it
  wrong. The sweep's own timeout stays 120 s (K6). A probe case writes
  `[~/.zshrc#1A2B]`, an exact-file deny, so it blocks only when `writePath` drops the tag (K15). A
  case of `harness leaks` shows that it renders each adapter's `TEMPLATES` (K17), and one calls
  `frontends.load()` twice on an adapter that lacks a member (K19). `harness test` requires each
  code span of `docs/src/example-tree.md` with the shape of a component's name, a script or a
  hyphenated lowercase name, to name a component (K45). `docs:check` requires one card width per
  column on every walk-through (K49). `harness test` reads every
  `docs/figures/walkthrough-*.toml` on disk, tracked or not, as the site's data loader does (K52).
  In the hook probe's `[inst-drif]` group, a failed `harness install --apply` is one wrong case
  with its exit status and last line, and the group stops there; a case in `setup_guard_cases`
  shows it (K64). The no-julia `PATH` of the precondition cases is a scratch directory of links to
  `git` and `sh`, so a `julia` in `/usr/bin` takes neither with it (K65).

- **The generated-by comment of an OpenCode agent names its source, and six stale comments and
  docs say what the code does.** Each agent that `harness install` renders for OpenCode reads
  "Generated by `harness install` from agents/<name>.md of the harness repository", oh-my-pi's
  wording, in place of "from ~/.claude/agents/<name>.md" (K7). The next `harness install` dry run
  therefore shows every installed OpenCode agent as a change: 22 with the example model tables, the
  20 of `agents/` and 2 council copies. The header of `scripts/fatou-lsp.jl` names its two
  includers, `julia-methods.jl` and `fatou-lsp-test.jl` (K40); the usage comment of
  `scripts/wiki-lint.jl` names the five trees of `SCOPES` (K41); `scripts/julia-callers.jl` and
  `scripts/fatou-lsp.jl` state their claim inline and cite no notes page outside the repository
  (K42); the description of the `which-model` skill names the tier `small` of its `model:` (K43);
  and `agent-workflows/repo-drift.js` and `agent-workflows/README.md` say that `harness workflows`
  installs into `Packages/` and `Experiments/` alike and `TagBot.yml` only into packages, and cite
  only tracked files (K44). K7 and K40–K44 leave `KNOWN_ISSUES.md`. The citations of the same
  notes page in `rules/julia-code.md` and `skills/julia-structure/SKILL.md` stay, because they are
  installed into a tree that holds the page: K66. Three other files that cite a notes page outside
  the repository are K67.

- **Four tracebacks of `harness` become one line and exit 2: K4, K9, K48 and K60 leave
  `KNOWN_ISSUES.md`.** Exit 1 means "changes to make" in the verb contract, so a traceback with
  exit 1 read as a pending change. A settings file that is not UTF-8, not JSON, JSON but not an
  object, JSON nested deeper than the parser reads, or an object whose `permissions` is not an
  object makes `settings surface`, `compare`, `twins` and `domains` exit 2 with one line that
  names the file and what is wrong with it. Such a `~/.claude.json`, or one whose `projects` is
  not an object, does the same for `trust` (K4). The merge of `~/.claude/settings.json` refuses
  deep nesting the same way. `harness install` now checks every target of every frontend and of
  the Julia environment before it writes anything. Before, only the Claude Code layer had this
  check. A symlink at a target, or at a directory above one, is refused and not written through.
  A directory at a target is refused too. In the dry run and under `--apply`, each refusal is one
  line that names the target once and what it is, and nothing else is printed (K9). A target with
  a change that the user cannot write, or a new target below a directory that cannot be written,
  makes `--apply` exit 2 with one line, before any file or backup is written. So does a target
  whose mode the install changes and that another user owns, because only the owner can change
  a mode. The dry run prints its whole plan and its count line, then that line, and exits 2, so
  that a session, which cannot write the installed files, still sees the plan (K48). An `OSError`
  in the write itself, from a full disk say, also exits 2 with the target. A backup now has mode
  0600, whatever the mode of the file it keeps, so a backup of a 0644 file is no longer readable
  by others, and a backup never carries a 0444 that blocks the next one. A permission rule
  outside `~/.claude/settings.json` with a lone surrogate prints it as `\ud800`; the dry run no
  longer stops with `UnicodeEncodeError` (K60). New cases in `harness test` show each refusal: 30
  in the contract sweep for K4, 17 in `install_cases.target_cases`, and one more input in the
  settings-merge cases of the Claude Code adapter. `claude_plan` takes no `root` any more, because
  the target check left it. A stray settings file nested too deep still ends the dry run in a
  traceback (K68).

- **`harness install --apply` with no `julia` exits 2 with one line, and new cases show K18's fix
  and measure the leak gate's limits.** With a change pending in the Julia environment and no `julia` that starts
  (none on the `PATH`, or one that is not executable), the apply exits 2 with
  `julia cannot be started (…): it is not found on the PATH, or not executable; install Julia with
  juliaup`, in place of a `FileNotFoundError` traceback and exit 1; a `julia` that starts and
  fails keeps `Pkg.instantiate failed in …`, and the dry run still starts nothing. A new case in
  `harness test` (`precondition_cases`) runs the dry run on a scratch `HOME` with no
  `~/.claude/skills/` and shows exit 1 with its count line: K18, fixed by `8a99f73`, which
  replaced the OpenCode skill links with own copies, and leaves `KNOWN_ISSUES.md`. Four cases in
  `commit_cases` measure the limits of the leak gate that `docs/src/security.md` states:
  `harness leaks --commits` reports no hit for a leak string only in a commit's author name, only
  in the message of an annotated tag on a listed commit, or only in a `git notes` note on one, and
  one hit for the same string in the commit's message. A failed setup install no longer turns
  the cases after it into a `FileNotFoundError` traceback or into wrong cases that name a
  follow-on file: `restart_cases`, the Claude Code adapter's `layer_cases`, the OpenCode
  adapter's `install_cases` and the oh-my-pi adapter's `omp_cases` each report it as one wrong
  case with the install's exit status and last line, and that group of cases stops. A new case,
  `setup_guard_cases`, runs the three adapter groups with every install failing and checks this.
  With a curated skill that fails `parse_file`, `harness test` now prints the
  frontmatter case's `BAD` line that names the file, prints no traceback, and exits nonzero; K23
  and K25 leave `KNOWN_ISSUES.md`. It still ends early, in the skill-triggers cases, with exit 2
  and no summary line: K63.

- **No session changes RTK's configuration, its user filters or its filter trust store.** RTK
  keeps the SHA-256 hashes of the filter files that it may apply in `trusted_filters.json`, in its
  data directory, which a session must write for the tracking database. A session could write a
  project's `.rtk/filters.toml` and trust it there, and a filter can rewrite what every later
  agent sees. The settings template now denies that file to the `Edit` tool and in the sandbox's
  `denyWrite`, in both of RTK's data directories (`~/Library/Application Support/rtk` on macOS,
  `~/.local/share/rtk` on Linux). On macOS, where the same directory holds `config.toml` and
  `filters.toml`, it denies those two files too; on Linux they are under `~/.config`, which is
  denied already. Only `rtk trust`, `rtk untrust`, `rtk init` and `rtk config` write these files,
  and the user runs them outside the sandbox. `harness permissions --apply` carries the four
  denies into OpenCode's list.

- **No session writes a `systemd --user` unit or juliaup's own directory, and RTK can write its
  data on Linux.** The settings template denies `~/.config/systemd/user` and
  `~/.local/share/systemd`, the two directories from which `systemd --user` loads a user's units,
  to the `Edit` tool and in the sandbox's `denyWrite`, as it denies `~/Library/LaunchAgents`.
  `~/.config` was denied already; the second directory was not. It denies `~/.juliaup`, where
  juliaup's upstream installer puts `juliaup` and the `julia` launcher, the same way. RTK's Linux
  data directory, `~/.local/share/rtk` (the tracking database, the tee spool and the hook markers),
  joins `allowWrite` beside `~/Library/Application Support/rtk`; its Linux configuration directory,
  `~/.config/rtk`, stays denied. `harness permissions --apply` carries the three denies into
  OpenCode's list.

- **The three launch agents have `systemd --user` units for Linux, and `claude-autocommit` pushes
  to a branch per machine.** `systemd/` holds `kaimon.service`, `julia-update.service` with
  `julia-update.timer`, and `claude-autocommit.service` with `claude-autocommit.timer`, templates
  of the profile like the plists (`harness render systemd/<name>`). Each runs the program, the
  arguments, the environment and the `PATH` of its plist, on the same schedule; the server restarts
  on exit, and both timers are `Persistent=true`. The new module `lib/harness/units.py` checks
  this in `harness test`, with the example profile. It refuses a unit key that it does not read,
  such as an extra timer trigger, and checks that every element of a `PATH` is an absolute
  directory that the settings template keeps out of a session's writes, or a system directory. CI's
  new `systemd` job renders each unit on `ubuntu-latest` and runs `systemd-analyze verify --user`
  on it. `claude-autocommit` pushes the local `main` to `$CLAUDE_AUTOCOMMIT_BRANCH`, `main` when
  unset; the plist and the unit set it from the new optional profile key `autocommit_branch`,
  which `harness render` fills with `main` when the profile has none. `harness leaks` and CI's
  gitleaks step now also render `claude-autocommit.plist` and the five units. Installing a unit
  stays a step by hand.

- **OpenCode loads `opencode-anthropic-login-via-cli` again, pinned to 1.7.0.** OpenCode v2
  refused 1.6.1 at every start ("Plugin must export a default definition with an id and an effect
  or setup function"), so the `anthropic` provider had no login. The adapter named `@latest`, but
  OpenCode keeps the version it fetched first under that name and never fetched 1.7.0, the first
  release with a v2 export. The pin also means a later release loads only after a review and a
  new pin.

- **The deny lists refuse the login stores of OpenCode and oh-my-pi.** A sandboxed Claude Code
  session could read OpenCode's `~/.local/share/opencode/auth.json` (every provider key that
  `opencode auth login` stores) and `mcp-auth.json`, and oh-my-pi's `~/.omp/agent/agent.db` with
  its write-ahead log `agent.db-wal` (the `/login` credentials). The settings template now denies
  the four paths in `permissions.deny` (`Read`), in `sandbox.filesystem.denyRead` and in
  `sandbox.credentials.files`, each directly after the `~/.omp/agent/.env` entry. The OpenCode
  `opencode.jsonc` and `plugins/guard-paths.json`, and with them the oh-my-pi
  `extensions/guard-paths.json`, add the four paths, as `harness permissions` derives them from
  the template; they already denied all of `~/.local/share/opencode/`. Each frontend still reads its own store, because the denies act on an
  agent's tools and commands, not on the frontend's process.

- **`scripts/base-tree.jl` puts the tree of one commit into a directory, with no permission
  prompt.** The builders and critics of the loop need the unmodified tree for the "on the
  unmodified tree" column of `evidence.md`, and wrote it with `git archive -o <file> <ref>` and a
  second `tar -x` call: about one call in five, and each one asks, because `-o` writes any path
  from outside the sandbox. A worktree-isolated agent has no other choice, because Claude Code
  refuses a pipeline that holds `git` there. `base-tree.jl <package> <ref> <dir> [<path> ...]`
  does it in one call, refuses a directory that is not empty, and prints the number of files and
  the commit. `evidence.md` names it in its rules for a row and in its table of tools, and
  `julia-pr-reviewer`, which is worktree-isolated and used `-o` too, names it for a probe on the
  base.
  `scripts/base-tree-test.jl` checks it on the commits of this repository, in `julia.yml`'s matrix
  and in the selection of `.githooks/pre-push`.

- **Performance is a trade against simplicity, not a limit on it.** `rules/julia-code.md` named
  performance as the third limit of a simplification and kept only the version that is not slower,
  so a reviewer rejected a much shorter implementation for a loss of about 10 %. The rule now keeps
  readability and comprehensibility as limits, and weighs performance as an equal: measured at
  more than one system size, judged by how the loss scales and by how much clarity it buys, with
  no fixed threshold, and never a reason on its own to reject a simplification. The reviewer's
  `quality` finding asks for the trade measured per size.

- **The two timer jobs run on Linux, and four scripts have a test that CI runs on Linux.**
  `julia-update.jl` branches on the system once and stops with an error on a system that is
  neither macOS nor Linux. On Linux it reads the Kaimon server's binary from `/proc/<pid>/exe`,
  without its ` (deleted)` suffix, because `ps -o comm=` prints only a 15-character name there;
  it restarts the server with `systemctl --user restart kaimon.service`, notifies with
  `notify-send`, names `journalctl --user -u julia-update.service` as its log, and reads no
  profile. On both systems it finds `lsof`, `ps`, `launchctl`, `systemctl`, `osascript` and
  `notify-send` on the `PATH`; a missing `lsof` is now a failure ("cannot read the server") and
  not "no server", a failed restart, or one with no service manager on the `PATH`, is a failure
  in the log where it ended the job with a stack trace, and a missing notifier leaves the log line only. `claude-autocommit`
  takes its lock in `$XDG_STATE_HOME`, or `~/.local/state`, on Linux, and in `~/Library/Logs` on
  macOS as before. New tests: `scripts/julia-update-test.jl`,
  `launchagents/claude-autocommit-test.jl`, `githooks/pre-commit-test.jl` (the hook is
  unchanged) and `scripts/fatou-lsp-test.jl`, in `julia.yml`'s matrix on `ubuntu-latest` and in
  the selection of `.githooks/pre-push`. `julia.yml` also runs on a change in `launchagents/` or
  `githooks/pre-commit`.

- **OpenCode's rtk plugin finds `rtk` on the `PATH`**, as Claude Code's hook `rtk hook claude`
  does, in place of the fixed path `/opt/homebrew/bin/rtk`, which exists on a Mac with Homebrew
  only. `harness install` warns when no `rtk` is on the `PATH`; the warning leaves its exit status
  as it is. When OpenCode's `PATH` has no `rtk`, each command runs unchanged, as before. The probe
  runs the plugin with a fixture `rtk` on the `PATH` of `node` alone, and with none there.
  
- **The docs pages describe OpenCode's and oh-my-pi's own copies and the shared model tables.**
  The pages on the skills, the hooks, the adapters, the profile and the other components, and the
  architecture, setup, command and dependency pages, still named the links in `~/.agents/skills/`,
  the guard scripts of `~/.claude/hooks/` under the other frontends, the `[opencode.*]` tables
  and the `@opus` roles of oh-my-pi. They now name each frontend's copies, the tables that
  OpenCode and oh-my-pi share with `[opencode]` and `[omp]` over them, the context limits and the
  verify seat of a council. `examples/models.toml` names `harness.yml`, not `config.yml`.

- **`harness install` no longer writes oh-my-pi's `config.yml`; its keys go to the overlay
  `~/.omp/agent/harness.yml`.** oh-my-pi's setup and its settings panel write `config.yml` and
  rewrite it as YAML with keys of their own, such as `setupVersion` and `theme`; the install
  replaced the whole file, so oh-my-pi lost them and ran its setup again at almost every start.
  oh-my-pi reads each file that `PI_CONFIG_FILES` names after `config.yml` and over it, and never
  writes one; it loads the agent directory's `.env` before. So `harness.yml` holds the approval
  mode, `bash.patterns` and `modelRoles.default`, and one line in `~/.omp/agent/.env`,
  `PI_CONFIG_FILES=~/.omp/agent/harness.yml`, makes oh-my-pi read it. The install warns, with that
  line, when neither its environment nor the `.env` names the file; it reads the `.env` for that
  key only, prints none of its values, and never writes it. The docs pages on oh-my-pi say so, and
  no longer name the approval mode `write`, the `@opus` roles or the `[omp]` table.

- **`harness install` owns `modelSettings` of `~/.claude/settings.json` too**, beside
  `permissions`, `hooks` and `sandbox`. `modelSettings` holds each model's effort and
  auto-compact window, which OpenCode and oh-my-pi take from `models.toml`; so Claude Code's come
  from the settings template. An `/effort` or `/autocompact` in the UI holds until the next
  install, which shows it in its diff and replaces it. The template's `modelSettings` takes the
  values of the user's live file: `effortLevel` `medium` for `claude-opus-5`, `claude-opus-5-5`,
  `claude-sonnet-5` and `claude-sonnet-5-5`, where the template held `high` for the two 5 models,
  and `autoCompactWindow` 100000 for `claude-haiku-5-5`, the key that `/autocompact` writes, so
  that Haiku 5.5 stays below its price step at 100K input tokens, as under the other frontends.

- **OpenCode and oh-my-pi keep their own copies, and oh-my-pi follows OpenCode's model layer.**
  `harness install` copies the Claude Code layer's `RTK.md`, `instructions/`, rules, the four
  guard scripts and the curated skills into `~/.config/opencode/` and `~/.omp/agent/`. Every
  copied text, rule and agent names the frontend's own copies, not `~/.claude/`
  (`frontends.relocate`). OpenCode's `instructions` and `AGENTS.md` of oh-my-pi import those
  copies, and both guards run the scripts from `hooks/` beside them. The install removes the
  links that it wrote to `~/.agents/skills/`, and writes nothing there. oh-my-pi reads the skills
  through `skill://`; its guard lets `read`, `grep` and `bash` reach its copies of the skills, the
  rules and the instructions, and keeps the rest of `~/.omp` closed.
  **OpenCode and oh-my-pi share one set of model tables** at the top level of `models.toml`:
  `models`, `model_overrides`, `model_variants`, `variants`, `reasoning_effort`, `councils` and
  `context_limits`. `[opencode]` and `[omp]` hold the same sub-tables, and each of their keys
  replaces the shared one for that frontend alone, so a file of the earlier form with complete
  `[opencode]` tables still loads. `[claude]` stays Claude Code's table of the tiers. Tiers
  directly in `[omp]` exit 2 and name `[models]`, and so does an unknown top-level table. So
  oh-my-pi's agents get their model and thinking level as OpenCode's do, and oh-my-pi runs the
  council of critics too. An agent's own `effort` no longer sets its thinking level, as it sets
  no variant under OpenCode. A council seat with `verify = true` judges each verify round alone,
  under both frontends. A new table, `context_limits`, caps
  the input tokens of a model: OpenCode gets a `limit` in its `provider` object, oh-my-pi a
  `contextWindow` in a new `models.yml`, which compaction reads. A new optional profile key,
  `omp_providers`, holds oh-my-pi's own providers, one table each, as `opencode_providers` holds
  OpenCode's; the install writes them into `models.yml`. Name a provider as OpenCode names the
  same account, such as `azure-cognitive-services` for Claude on Azure, so that `models.toml`
  holds one model string for both frontends. An `apiKey` there must name an environment
  variable or be a `!command`; a literal key stops the install, and the message does not show
  it. oh-my-pi's approval mode is
  `yolo`: its deny and prompt patterns, the `eval` deny and the guard extension still apply.
  `config.yml` keeps only `modelRoles.default`. K25 stays: its traceback moves to a later line.

- **Four animated walk-throughs show the work step by step.** *Agents at work* shows a part from
  a task to a pull request with `build-part` and with `build-reviewed`. *The security model* shows
  one tool call through the layers of control. *Typical use* shows a change of a source through
  `harness install` to the drift check at the next session start. A `WalkThrough` component draws
  each one from its data file `docs/figures/walkthrough-<name>.toml`: a title and a subtitle, boxes
  on a grid, dashed groups, and edges with right angles and labels. Each edge cites the
  `file:line` that states its step. A box of an agent or a skill takes its model and effort from
  the source's frontmatter and `examples/models.toml`, through `sources.ts`, which the call
  graphs also read; a box can show the effort of its spawn instead, which an entry of
  `calls.toml` must record, so the two critics of round 1 show `high`. The cards of one column
  have one width, and a walk-through is at most 765 px wide, as a call graph. The colour of a
  box says who acts: you and your session, an agent of each tier, a step with no agent, or a
  dashed outcome; a legend explains the colours. The animation is CSS in the figure's own
  `<style>`: the active box has a dark outline and the others fade, and a red token runs along
  each edge in 0.7 s; each step holds 1.5 s, and the animation loops. Under
  `prefers-reduced-motion` no animation runs, every box shows, and no token shows. With
  JavaScript on, play, pause and step buttons show under the figure. `docs:check` finds each
  walk-through by its title and checks each animated figure: its SVG parses as XML, it holds no
  `<script>`, no SMIL and no other host, it loops, it has the reduced-motion rules, its timing
  is 0.5–0.8 s per edge and at least 1.2 s per step, and it is at most 765 px wide. `harness test`
  names a box that shows no agent or skill of the repository, an effort that no spawn of
  `calls.toml` has, and a cited line that does not exist. The colour scan of
  `docs:check` also reads `docs/figures/`. The *Get started* action of the landing page links the
  *Introduction*, and `docs:check` fails when it links another page.
- **The `pre-push` hook scans the commits that a push brings to `main`**, `old..sha` as CI does,
  in place of the commits that no ref of `origin` holds. A commit that a branch on `origin`
  already held passed the hook unscanned: Unify part M pushed its branch first, and a home path
  that one of its commits added and the next removed reached `main` through the hook and was
  found only by CI. The history of `main` was rewritten to drop that commit.
- **The `pre-push` hook finds a Python of 3.11 or later under a versioned name.** It takes the
  first of `python3`, `python3.14`, `python3.13`, `python3.12` and `python3.11` that is 3.11 or
  later, for `harness leaks` and the suite, and still runs the suite on `python3.11` too. A
  Homebrew upgrade can drop the unversioned `python3` link, and the hook then refused every push
  to `main` because the system's `python3` is 3.9.
- **`harness install` merges the Claude Code settings, and `harness settings install` is gone.**
  `~/.claude/settings.json` is the first file of the Claude Code plan, before the other files
  of its layer, so a new deny rule is in place before the files that it protects. The merge
  replaces each of `permissions`, `hooks` and `sandbox` with the section of the settings template
  `settings/settings.proposal.json`, rendered with the profile, or removes the section when the
  template lacks it. Every other key keeps its value and its place. The indent of the live file
  is kept, and no character is escaped but a lone surrogate. A file whose owned sections equal
  the template's is left untouched. Otherwise the file keeps its mode, and the old file is kept
  as `settings.json.bak-<stamp>`. The backup of each file that `harness install` replaces, for
  every frontend, now keeps the mode of the file it copies. The dry run
  prints a `REPLACE` or `INSTALL` line, then the unified diff of the owned sections, and counts
  the change as one. A missing file is created with the three sections, indent 2 and mode 0644.
  The setup guide and the README no longer have the `echo '{}'` step. A file that cannot be
  merged (not UTF-8, not JSON, not a JSON object, an owned key whose value is not an object, a
  symlink, a directory, or unreadable) stops the install with exit 2 and one line that names
  the file and the reason, before any file of any frontend is written.
  `harness settings install`, with its flags `--proposal` and `--settings`, is removed. The
  verb `harness settings` keeps `surface`, `compare`, `selftest`, `twins` and `domains`. The
  warning of `harness install` that the settings would change is gone. Permission rules in other
  settings files (`settings.local.json` and the `.claude/settings.json` of the research root and
  its directories) now print in the output of `harness install`. A file that cannot be read as
  a settings file is a warning, not a traceback. A Plan file may carry a sixth element, text
  printed after the file's line when the file is a change. The undo of a settings change is
  `git revert <commit>` and `harness install --apply`. The flow figure and the docs no longer
  name the removed verb. The flow figure has a step card, *Merge the settings*, before
  *Write Claude Code*.

- **The call graphs are compact, and the flow figure shows the steps of `harness install`.** A
  call graph of *Agents at work* runs to the right when it fits the doc column, at most 765 px
  wide, so that the column draws it at a scale of 0.9 or more. Else it runs downwards, in rows of
  at most three boxes. The boxes of one column or row have the width of the widest box and share
  their left or top edge. `docs:check` names a call graph that is wider than 765 px, and a layer
  whose boxes differ in width or edge. *Every spawn* is the one exemption from the width rule: it
  has 16 boxes and 16 labelled edges, and it stays drawn to the right, 1171 px wide. In a graph
  that runs downwards, each label sits on a vertical segment of its own edge. `docs:check` names
  a label in every figure that is not on its own edge, that another edge passes through, or that
  overlaps another label. In the flow figure, `harness install` is a dashed group with a card for
  each of its steps, in the order in which `lib/harness/install.py` runs them, and its header is
  in the monospace font. `harness settings install` is below it. `docs:check` checks the cards
  and their order. The landing page says that your session keeps its context, not its room.

- **A new docs page, *An example tree*, describes the research tree of the overview figure.** It
  has one section for each of the six directories (library, knowledge, packages, experiments,
  projects and papers): what the directory holds, which agents, skills, rules, commands, git hooks,
  scripts and verbs serve it, each linked to its component section, and which profile key, verb or
  tree instruction names it. It ends with the profile values `repository_roots` and `tree_agents`
  of such a tree, and how to adapt them to another layout; it also says which verbs find their
  directories by a fixed name. The page is the last entry of *Getting started*, after *Tutorial*.
  The caption of the overview figure on the home page and on the *Introduction* links it.
  `docs/scripts/check-site.mjs` checks the new entry in the order of *Getting started*, and
  `docs/scripts/newcomer.mjs` checks the page as a newcomer page.

- **The newcomer pages: an introduction with a glossary, a setup guide that explains each step,
  and a guided tutorial.** The menu has *Home* as a headline of its own, then *Getting started*
  with *Introduction*, *Dependencies*, *Setup on macOS*, *Setup on Linux* and *Tutorial*; the
  *Setup* group goes, and *Daily use* is now *Typical use*. The new page *Introduction*
  (`concepts.md`) explains what a coding agent is, what a harness adds, the three layers (the
  harness, the profile and the tree instructions), the four layers of control around a tool call,
  and the division of work among agents, each with a note on how it carries to another
  language. It shows two new figures, drawn with the components and the style module of the
  figures, and the overview figure of the home page. Its glossary has one entry for each of 19
  terms. The setup guide for macOS says for each step what it does, why, and how to check it,
  marks what a reader who writes no Julia may skip, installs every required tool with `brew` and
  Julia with the installer of `juliaup`, and now makes the `repository_roots` directories,
  without which `harness leaks` stops. The Linux page gets its first step: the required tools
  with `apt-get`, and actionlint, fatou and Julia with their own installers; its other steps are
  still to come. The tutorial has eight steps, each with what you should see and what to do when
  it does not happen, and a track for a repository with no Julia package; its quoted outputs are
  the real texts of the hooks and verbs. *Typical use* links the tutorial in place of repeating
  it. On the newcomer pages, the first use of a glossary term links its entry, and no page holds
  a `file:line`: the call sites and version floors of *Dependencies* name the file without the
  line. A new check, `docs/scripts/newcomer.mjs` with its cases, enforces both and runs in
  `npm run docs:check`. `docs/scripts/check-site.mjs` now also checks that *Home* is a top-level
  link of the sidebar, that *Getting started* holds its five pages in this order, and that the
  Introduction has its three figures.

- **The figures of the site have a new design, and the home page is a landing page.** Vue
  components draw every figure as inline SVG at build time: cards with an icon, group panels with
  a coloured header band and a number badge, and thin right-angled arrows. One style module,
  `docs/.vitepress/theme/figures.css`, holds every colour of the figures for the light and the
  dark theme, the font, the corner radii and the line widths. The icons come from `lucide`, and
  the build inlines them. The home page is no longer a copy of the README: it has a hero with
  *Get started*, *Tutorial* and *GitHub*, six feature cards, the overview and the flow figure,
  and its own edit link, because the home layout has no doc footer. A change of the README no
  longer starts the docs workflow. In the flow figure, OpenCode and oh-my-pi are above Claude Code, and no arrows cross.
  The four call graphs of *Agents at work* keep their text and are laid out with `elkjs` at build
  time; a graph's block now holds `title:` and `desc:`. The README has no figure and links the
  site for them. `mermaid` and `vitepress-plugin-mermaid` leave `docs/package.json`, and
  `elkjs` 0.12.0 and `lucide` 1.55.0 join it. `npm run docs:check` finds the six figures by
  their title and checks their description, fails on an arrow that crosses another arrow, passes
  through a box or does not end on the box it names, on a figure colour with no dark value, and
  on a home page with no edit link; it checks the anchors and tables of the home page too; it runs the cases of
  `docs/scripts/figures.test.mjs` first.

- **The credentials of oh-my-pi are denied, and the main session keeps its prompt cache for one
  hour.** `~/.omp/agent/.env`, where oh-my-pi keeps its API keys, is in the `Read` denies, the
  sandbox's `denyRead` and `credentials.files` of the settings template, and so in the read
  denies of OpenCode and the path list of its guard. A `Read(**/.env)` rule matches relative to
  the working directory, so it did not cover a file in `~/.omp`. The template sets
  `promptCacheTtl` to `"1h"`, and enables the `cache-tax` mod of the `claude-code-mods`
  marketplace (`karanb192/claude-code-mods`), which keeps the cache warm during a break and shows
  the cost of a cold send. These three top-level keys are outside the sections that
  `harness settings install` merges, so they reach the live file by hand. `subagentPromptCacheTtl`
  stays unset, because it would apply to every subagent and override the agents' own choice: the
  frontmatter key `cacheTtl: 1h` gives `julia-test-runner`, `julia-pr-shepherd` and `ci-triage`,
  which wait on suites and CI, a one-hour cache. OpenCode and oh-my-pi drop the key.

- **A new README, and the dependencies move to their own page.** The README, and so the home page
  of the site, is now an overview for a reader who is new to the harness: what it is and for
  whom, two Mermaid figures (the harness around its three layers, and the flow from the sources
  through `harness install` to the frontends), the shortest installation on macOS in five steps,
  a first session in five steps that needs any git repository and no Julia, and one link to the
  site; it leaves the details to the pages that it links. The dependency tables are on the new
  page *Dependencies* (`docs/src/dependencies.md`), second in the sidebar under *Getting
  started*, in three tables: *Generic tools*, *Julia and its packages* and *Optional*, with the
  same 25 rows, and a paragraph on what a reader who writes no Julia loses without the Julia
  rows. The descriptions of `tools.md` are below the tables, and `tools.md` is gone, so a link
  to `/tools` now finds no page. The case of `harness test` that read the README's tables reads
  the tables of `dependencies.md` and checks both directions: every row has a heading on that
  page, and every name in a heading is a row. The site's title is "Research Harness", and
  `npm run docs:check` also finds the README's two figures on the home page and the
  dependencies page second in the sidebar.

- **A ruling that adds a branch to the code names the test that catches its removal.** The
  `advisor` writes the input, the assertion and the mutant as a `**Tests catch:**` sentence in its
  decision; the `arbitrator` puts them in *Next round* and adds the mutant to the list that must be
  CAUGHT. Without such a test, the mutant that deletes the branch survives, and the round that runs
  on the ruling fails on a missing test while the code is right.

- **The documentation site is built with VitePress, and its build needs no Julia.** The site is a
  plain VitePress project in `docs/`: `npm ci` and `npm run docs:build` build it, and
  `docs/package.json` pins `vitepress` 1.6.4, `vitepress-plugin-mermaid` 2.0.17, `mermaid`
  11.17.2, `smol-toml` and `yaml`, with a committed `docs/package-lock.json`. Documenter,
  Graphviz_jll, `docs/Project.toml`, `docs/make.jl`, `docs/figures/figures.jl` and the committed
  SVG figures are gone, and with them the workflow step that compared the figures. The call
  graphs of *Agents at work* are Mermaid diagrams that `docs/.vitepress/calls.mjs` writes at
  build time from `docs/figures/calls.toml`, the frontmatter of `agents/` and `skills/` and
  `examples/models.toml`, with the same text in each box as before; each has an accessible title
  and description, and its colours follow the site's light and dark theme. The home page
  includes the README. The `@ref` links of the pages are plain Markdown links to a page and a
  heading. A new check, `npm run docs:check`, finds every page of the menu in the sidebar, every
  linked heading, the table rows of each page and the four call graphs. The docs workflow
  builds the site on Node.js 24, runs the check, and on a push to `main` deploys the site to
  `gh-pages` with a `.nojekyll`, at the same address. A page's URL loses its trailing slash:
  `/tutorial/` is now `/tutorial`.

- **The documentation site shows who spawns whom.** The new page *Agents at work*
  (`docs/src/agents-at-work.md`, under *Background*) has four call graphs: the `build-part`
  loop, the `build-reviewed` loop, the `julia-pr-shepherd` chain and every spawn. Each box shows
  the name, the model (for an agent the default of `examples/models.toml`, for a skill the
  session's model) and the effort; an arrow shows where a
  caller sets another effort. The arrows come from one file, `docs/figures/calls.toml`, one entry
  for each spawn with the `file:line` that spawns; new cases of `harness test` check that each
  entry names agents and skills that exist, that its line names the callee, and that every
  source with the tool `agent`, `build-part` and `build-reviewed` spawns at least once.
  `docs/make.jl` draws the figures with Graphviz_jll (pinned to 15.1.0) into
  `docs/src/assets/figures/`, where they are committed, and the docs workflow fails when the
  build changes one. It also runs on a change of `agents/`, `skills/` or `examples/models.toml`,
  and a local build no longer calls `deploydocs`, so it prints no warning.

- **`harness leaks` allows the host of the repository's GitHub Pages site, and the README links
  the site.** Beside the repository's own `owner/name`, the check now removes `owner.github.io`
  from a line before it searches for the names of the research tree, so the URL of the
  documentation site is no hit. Three new cases show it: the site URL and the bare host pass,
  and `owner.github.com` is still a hit. The README has a documentation badge under its title,
  and its *Documentation* section names the site.

- **The documentation site has a tutorial for a new user.** `docs/src/tutorial.md` explains the
  words that the other pages use, from a session and its context to a skill, a sub-agent and a
  hook, and then walks through one Claude Code session: the install and its check, the start of
  a session and the drift warning, tool calls and permission prompts, a guard hook that refuses a
  shell edit, a skill that loads, a sub-agent that runs the tests, and a correction that lasts.
  It follows the home page in the navigation, and the README links it first.

- **The documentation site describes every component.** Ten pages in `docs/src/components/`
  cover the agents, skills, commands, rules and the core instruction file, guard hooks, git
  hooks and workflow templates, scripts, adapters, the modules of the `harness` command, and the
  jobs and configuration files: one section for each component, which says what it does, who
  calls it, what it reads and changes, and its limits. The new module `lib/harness/docs.py` keeps
  them complete: its cases in `harness test` fail when a component has no section, when a section
  names something that is no component, and when a tool of the README's dependency tables has no
  section in `tools.md`. The README and `docs/src/development.md` link the pages and describe the
  check.

- **The documentation is a Documenter site on GitHub Pages.** The pages move from `docs/` to
  `docs/src/`, and `docs/make.jl` builds them; its home page is the README, so the README stays
  the one source of that text. The new workflow `.github/workflows/docs.yml` builds the site on a
  pull request that changes the README or `docs/`, and Documenter fails the build on a broken
  local link. A push to `main` deploys the site to `gh-pages`. The README names each page by its
  title. Three links from a page to the README now go to the README on
  GitHub, because a link out of `docs/src/` fails the build. A link to a section of another page
  is an `@ref` to its heading, which the build checks; Documenter's anchors differ from GitHub's,
  so a URL fragment cannot serve both. `docs/src/development.md` says how to
  build the site locally. `docs/Manifest.toml` is not tracked.

- **The README's dependency tables say what each tool is used for.** The column `needed by`
  listed the `file:line` of each call, which told a reader where a tool is called but not why.
  The column `used for` now gives one plain sentence per tool, and for an optional tool also what
  stops without it. The 55 call sites move, unchanged, into a *Call sites* paragraph at the end of
  each section of `docs/tools.md`. The minimum column is unchanged. No code changes.

- **The settings template no longer grants one organisation's documentation host.** Its
  `WebFetch` grant and its sandbox host leave `settings/settings.proposal.json`; a user who needs
  such a host lists it in the profile's `extra_domain`. A comment in `adapters/opencode/plugins/env.ts` no longer names an
  institution's GitLab host.

- **`docs/` has a page for the setup on macOS, the daily use, the security model and the
  profile.** `docs/setup-macos.md` gives each step from the dependencies to the check that the
  install worked: the clone, the profile and the model tables from `examples/`, the tree
  instructions, the two directories that `harness install` needs on a new machine,
  `harness install --apply`, `harness settings install --apply`, the pre-push hook, and a short
  section each on what the install writes for OpenCode and oh-my-pi. `docs/setup-linux.md` says
  that the Linux setup is coming. `docs/daily-use.md` covers a change of a source or of the
  settings, the drift warning at session start, the leak check before a push, the five verbs for
  the whole research tree and `harness skill-triggers`. `docs/security.md` has a table of the
  mechanisms, each with what it stops, what it does not stop and the Claude Code version whose
  behaviour it states, then the limits, a check for a change of the settings, and a section on
  the outer sandbox, which is coming. `docs/profile.md` names each key of the profile and each
  table of the model tables, and the verbs that read it. `docs/architecture.md` has two new
  sections before the moved text: the three layers (the harness, the profile and the tree
  instructions) and the state in `~/.claude`. The README's *Documentation* links the five new
  pages. The README's *Installation* and `docs/setup-macos.md` use the checkout
  `~/Research/Harness`, say that the profile key `harness` holds its absolute path, and add the
  steps that a new machine needs before the first install: the values of the profile, the
  directories that the profile names, `~/.claude/skills/`, `~/.config/opencode/` and an empty
  `~/.claude/settings.json`. Without them, `harness install` and `harness settings install` exit
  2 on a new `HOME`. No code changes.

- **The README describes the features, the installation, the basic usage and the dependencies;
  the technical detail moves to `docs/`.** The README has the sections *Installation*, with the
  steps from a clone to the first `harness install --apply` and `harness settings install
  --apply` on macOS, *Basic usage*, with the daily verbs `install`, `test`, `leaks` and
  `settings`, *Dependencies*, unchanged, and *Documentation*, which links each page of `docs/`.
  `docs/harness-command.md` takes the verb contract, the profile and model flags, the verb table
  and the Julia environment; `docs/architecture.md` the Claude Code layer and its stamp, the
  neutral vocabulary, the OpenCode and oh-my-pi adapters and the layout; `docs/development.md`
  the tests, the pre-push hook, the leak checks and CI. The moved text keeps its wording; the references "the contract above" and "Put `bin/` on the `PATH`:"
  that cross a page become links. The new text on these pages is navigation only: the page
  titles *Architecture* and *Development*, the section headings *The Claude Code layer*, *The
  OpenCode and oh-my-pi adapters*, *The Julia environment*, *The pre-push hook* and *CI*, and one
  sentence in `docs/harness-command.md` that links `docs/development.md` for the cases of
  `harness test` and `docs/architecture.md` for the Claude Code layer. No code changes.

- **The README lists the dependencies, and `docs/tools.md` describes each one.** The new section
  *Dependencies* has two tables. *Required* holds the 17 tools that a verb, a hook, the pre-push
  gate, CI or an installed git hook calls: Python, git, gh, gitleaks, Julia, the six Julia
  packages of `Project.toml`, Node.js, shellcheck, actionlint, `timeout`, fatou and rsync.
  *Optional* holds the 8 tools that serve one frontend or one job: Claude Code, OpenCode,
  oh-my-pi, RTK, Kaimon, jq, juliaup and iTerm2. Each row names its callers as `file:line` or a
  CI job. Its minimum is a floor with its source (the check in the code, the CI pin, `[compat]`
  or a release note), or the version that the harness is tested with on the author's machine.
  A sentence under the tables names the system tools that the tables leave out. `docs/tools.md`
  has one section per tool, and one section for the six Julia packages: what the tool does,
  what the harness uses it for, and why the harness needs it. The README's section *Tests* no
  longer says that gitleaks 8.21 is the first release with the `git` and `dir` commands: 8.19
  added them, and 8.21 added several allowlists per rule, which keeps the floor at 8.21. No code
  changes.

- **The descriptions of `julia-surgical-fix`, `math-verify`, `julia-structure` and
  `julia-package-audit` ask for a load before the code is read.** In the full routing run they
  loaded on 0, 1, 2 and 3 of 10 `load` queries, and every miss was a session that loaded no
  skill. Each new description says what the skill does, asks for a load first on any request of
  its kind, even a one-line one, lists the words such a request uses, and names its neighbours
  last, in the form that lifted `julia-performance` from 4 to 7 of 10. None shares a run of 5
  words with any query, `load` or `near`, of `tests/skill-triggers/`. `julia-surgical-fix` no
  longer names the agents that load it: they load it through their `skills:` frontmatter, so the
  sentence routed nothing. The skills' bodies and the query files are unchanged.

- **The leak checks also read the commit messages.** gitleaks 8.30.1 `git` reads no commit
  message: on a fixture whose only commit message held a synthetic `ghp_` token and a home path,
  it scanned 13 bytes and exited 0, while the same strings in a file gave 2 findings. So the
  pre-push hook now pipes the messages of the commits that a push sends (`git log --no-walk
  --format=%B`, in the checkout) into `gitleaks stdin` with the same flags, after `gitleaks git`;
  a hit refuses the push, and so does any status but 0 or 1. CI's step *gitleaks over the pushed
  range* pipes `git log --format=%B "$range"` into `gitleaks stdin`, under `set -o pipefail`.
  `harness leaks --commits FILE` also searches the message of each listed commit (`git show -s
  --format=%B`, subject, body and trailers) for the leak strings and the tree names, the own
  `owner/name` allowed, and prints a hit as `<sha12> message:<n>`, `n` from 1. The author and
  committer, a tag message and `git notes` are not searched. 9 new `harness test` cases on the
  fixture repository: a leak string in a body at `message:3`, a tree name in a subject at
  `message:1`, the own `owner/name`, a clean commit, an empty message, a message that is not
  UTF-8, a line with a leak string and a tree name, a merge's message and a SHA listed twice; the
  `harness leaks` run over every commit prints the message hit. The fixture's other commits now
  carry the message `change`, not their file name, so that a message adds no hit to their cases.

- **The description of `julia-performance` asks for a load before the code is read.** Under the
  3-message rule it loaded on 4 of 10 `load` queries, and most of the misses nearly repeated a
  phrase of its `Triggers on:` list. The new description says what the skill does, asks for a
  load first on any question about the speed, memory or inference of Julia code, even a one-line
  one, lists the words such a question uses, and names `julia-package-audit` last. It shares no
  run of 5 words with a `load` query. The skill's body and the query files are unchanged.

- **`run-tests.jl <package> --jobs <n> <selection>` runs the selected test files in n worker
  processes.** Opt-in; without `--jobs`, and with `--jobs 1`, a run is one process as before. It
  works for a named selection, a group, `affected`, and `full`, where it runs the files of
  `Pkg.test()` (the groups of an empty `ARGS`) through `TestEnv` in place of `Pkg.test()`, and
  so refuses a layout outside the convention. Each worker takes the next file that no worker has
  taken, in the order of `runtests.jl`, so each file runs once, in its own module under a
  `@testset` of its label; the workers use the same `--check-bounds` and so the same precompile
  images, and resolve the test environment one at a time. The run passes, and exits 0, where
  every worker passes; else it fails and exits 1. The log holds each worker's output under a
  line that names it, each file is announced as `worker <k>: test/<path>`, and the times file
  has a fourth column, `worker <k>`. A `core` run with `--jobs` above 1 prints no D6 verdict and
  says why in one line: a file's time in a worker is not its cold time in the order of
  `runtests.jl`. A count that is not a whole number of 1 or more exits 2. The workers' drivers,
  logs, times files and claims are in a directory of the run's own, removed after it. A claim
  that fails for another reason than a file already taken stops its worker. `run-tests-test.jl`
  covers it with ten new test sets; `rules/julia-tests.md` names the form. No `CI.yml` changes.

- **`harness skill-triggers` counts a `Skill` call in the first 3 assistant messages, not only in
  the first.** A recorded session read `Tasks/CLAUDE.md` first and loaded `build-part` in its
  second message; the first-message rule counted it as a miss. Each session is `claude -p --verbose
  --output-format stream-json --max-turns 3 --disallowedTools Edit Write NotebookEdit Agent Bash`,
  so it can read but runs no command in the research root. The verdict groups the top-level
  assistant events by `message.id` and takes the skill of the first `Skill` call in the first 3
  groups; a subagent's call, with a `parent_tool_use_id`, never counts. `--skill <name>`, which
  can repeat, limits the dry run and `--apply` to those skills' query files, and a name with no
  file exits 2. The frontmatter check refuses a `SKILL.md` whose `description` has more than
  1,024 characters or holds `<` or `>`, naming the file and the rule; `harness install` and
  `harness test` read every skill through it. An agent's description is not checked. 28 new
  `harness test` cases, with no API call: two fixtures recorded from Claude Code 2.1.295 sessions
  on `sonnet` with `--max-turns 3`, private content stripped (`read-then-skill`, a `Read` and then
  `Skill` in the second message; `read-read-read`, no `Skill`), seven synthetic streams (a `Skill`
  call in message 3 and in message 4, a message in two events, two `Skill` calls, two with a
  subagent's call, a `success` end after 2 messages), the dry run and `--apply` with `--skill`,
  and the description rule at 1,024 and 1,025 characters and with `<` or `>`, through
  `parse_file` and through the install's `render_source`. The hand-written `skill-second-message`
  fixture now loads `build-part`. The query files are unchanged.

- **oh-my-pi runs `rm-scope.py`, and refuses an edit that the settings template asks for (K12
  closed).** The guard extension `adapters/omp/guards.ts` runs four guard scripts on each `bash`
  call, `rm-scope.py` last: a recursive `rm` outside the scratch zones is refused with its
  message, and a `git rm` outside a worktree, its "ask", is refused with the instruction to ask
  the user in chat. The template has no recursive-`rm` deny and allows `git rm *`, so before
  this neither had a gate under oh-my-pi. The path list `extensions/guard-paths.json` holds a
  third key, `ask`: the template's `Edit` and `Write` asks, rendered as the `edit` list is. The
  extension checks each path of an `edit` or `write` call against the `edit` list first and the
  `ask` list after it, and refuses a match of `ask` with the instruction to ask the user in chat;
  a path in both lists gets the deny text. An `ask` that is missing or not a list of strings
  blocks every `edit` and `write` call. K12 recorded that these four asks (`.githooks/**`,
  `.github/workflows/**`, `~/.claude/skills/**`, `~/.claude/workflows/**`) reached no gate under
  oh-my-pi; it leaves `KNOWN_ISSUES.md`. OpenCode's `guard-paths.json` gets no `ask` key: its
  `edit` asks are rules of `opencode.jsonc`. The comment of `guards.ts` no longer says that
  oh-my-pi runs only inside the sandbox launcher, which does not exist yet; oh-my-pi is not used
  before it does. 17 new `hooks/probe.py` cases (464 in all).

- **The settings template drops two stale `git -C` asks.** `Bash(git -C * rebase *)` goes, as
  `git rebase *` is allowed; `Bash(git -C * merge *)` becomes the nine `git -C *` forms of the
  plain `merge` asks: `--no-ff`, `--squash`, `--no-commit` and `-m`, each in two positions, and
  `--abort`. The permission block of `adapters/opencode/opencode.jsonc` is regenerated, and
  oh-my-pi's `bash.patterns` follow the template at the next `harness install`. Claude
  Code's dialogs do not change, since no `allow` covers a `git -C` merge or rebase.

- **The OpenCode plugins run under OpenCode v2, and the guard plugin fails closed.** OpenCode v2
  loads no v1 plugin, so `guards.ts`, `rtk.ts` and `env.ts` of `adapters/opencode/plugins/` were
  off in every v2 session. Each now has the v2 form: a default export `{id, setup(ctx)}`, with the
  ids `research-harness.guards`, `research-harness.rtk` and `research-harness.env`, and no import;
  the Node built-ins come from `process.getBuiltinModule`. The guard and the rtk rewrite hook the
  tool registry's `execute.before` and act on the `shell` tool, which v2 names `shell`, not `bash`;
  the rewrite assigns `event.input.command`. `env.ts` sets `JULIA_PKG_USE_CLI_GIT=true` in the
  shell's `create.before`. The checks, the rewrite and the variable are those of v1. The guard
  plugin now **fails closed**: a guard script that cannot start, exits with a status other than 0
  or 2, prints output that is not JSON, or does not answer within 10 s refuses the command, with a
  reason that names `research-harness.guards`; under v1 such a failure let the command run. A
  missing or malformed `guard-paths.json` beside the plugin refuses every `shell` call (one in
  `$OPENCODE_CONFIG_DIR` that is not JSON is ignored, as under v1, K26), and `setup` never
  throws, so the plugin still loads. A guard's `ask` stays a refusal, and the path guard keeps its
  text check, which a relative path or a path the command builds at run time passes. The working
  directory of a call without `workdir` is the session's, `ctx.location.directory`.
  `hooks/probe.py` gets an OpenCode driver: it loads each plugin under `node` with a stub context,
  and 38 cases (502 in all) check the v2 form, the guard's refusals, asks and passes, the working directory
  that the guard scripts get, the fail-closed cases, the rewrite and the environment. No case
  reaches the `process.cwd()` fallback or a `deny` decision (K29, K30). `OPENCODE-DELTA.md` names
  the `shell` tool and the fail-closed rule. The live probe under `opencode run` is the user's,
  after `harness install --apply`.

- **A push to `main` runs two leak checks before the suite, and CI runs gitleaks on every push
  and pull request.** The pre-push hook runs `gitleaks git` over the commits that the push sends
  (`git rev-list <sha> --not --remotes=origin`, in the checkout), `gitleaks dir` over the clone
  at the pushed SHA, and `harness leaks --commits` in the clone, whose `origin` URL it sets to the
  checkout's so that the real `owner/name` stays allowed. gitleaks finds tokens, keys and home
  paths: `.gitleaks.toml` extends the default rules with one rule, `home-path`, that allows only
  `/Users/me` and `/home/example`. `harness leaks` finds the profile's `leak` strings and the tree
  names. Each gitleaks call passes `--redact` and `--ignore-gitleaks-allow`. Any hit refuses the
  push with one line that names the check. The gate fails closed: no `gitleaks` on `PATH`, a
  version below 8.21 or one the hook cannot read, no profile, an empty `leak` list, or a check
  that exits with another status than 0 or 1 each refuse the push; none is a skip. 8.21 is the
  first gitleaks with the `git` and `dir` commands (8.19) and `[[rules.allowlists]]` (8.21),
  read from its release notes; the plan's figure was 8.25. **Run `brew install gitleaks` on each
  machine before you pull this, or every push to `main` is refused.**

  `harness leaks --commits FILE` reads one SHA per line and also searches the paths and the lines
  that each commit adds (`git show --format= --text -U0`, binary files included), so a leak that
  a later commit removes or renames away is still a hit; a line that is no SHA exits 2. Fifteen
  new `harness test` cases build a fixture repository, two of them through `harness leaks`
  itself. The `leaks` job of `test.yml` installs the pinned gitleaks 8.30.1
  tarball by its SHA256. A canary step requires gitleaks to find a synthetic token and a
  synthetic home path, built at run time, and the token to be absent from the log. Then the job
  scans the pushed range (`before..sha`; for a new branch `origin/main..sha`, for a new `main` the
  whole history; for a pull request `base..head`), the checkout, and the templates rendered with
  `examples/profile.toml`.

- **The deny lists no longer name `~/.config/tokens`.** The user has moved the directory to
  `~/.config/api-keys`, so the five entries for the old path are gone: the settings template's
  `Read` deny, `denyRead` entry and `credentials.files` entry, and the `{home}/.config/tokens/**`
  line of `adapters/opencode/opencode.jsonc` and `plugins/guard-paths.json`. Each entry for
  `~/.config/api-keys` stays.

- **The deny lists also refuse `~/.config/api-keys`, the new name of `~/.config/tokens`.** The
  settings template denies it in `permissions.deny` (`Read`), in `sandbox.filesystem.denyRead` and
  in `sandbox.credentials.files`, one entry directly after each `tokens` entry; the OpenCode
  `opencode.jsonc` and `plugins/guard-paths.json`, and with it the oh-my-pi
  `extensions/guard-paths.json`, deny `{home}/.config/api-keys/**` beside the old path. Both paths
  stay denied until the user has moved the directory, so no session can read the keys at any
  moment of the move; a later change drops the old path. The draft profile's `gwdg` provider
  reads its key from `{file:~/.config/api-keys/gwdg-token}`: the private profile needs the same
  one-line change before `harness install --apply`.

- **`harness skill-triggers` tests whether each skill loads on the queries that should load it.**
  `tests/skill-triggers/<skill>.toml` holds, for each of the 10 skills that the model can invoke,
  10 `load` queries and 5 `near` queries that belong to a neighbouring skill or to none; for
  `wait-what` and `which-model`, whose model invocation is off, one `near` query. The queries are
  written as a user types them, in English or German, and never name the skill. The dry run
  lists the counts and the 152 sessions that an `--apply` starts at least, and exits 1.
  `--apply --model <alias>` runs each query as one `claude -p --verbose --output-format
  stream-json` session in the research root; there is no default model, and `--apply` without
  `--model` exits 2. The session's turns and tools, and the rule for when a query loads a skill,
  are in the entry above. A query that fails its expectation runs twice more and the
  majority counts; a session that errors or times out after 120 s is `UNKNOWN` and runs once
  more. A skill passes with at least 8 of 10 loads and at most 1 of 5 false loads. The verb
  prints a row per skill and the tokens and cost, writes the table and every query's verdicts to
  `.scratch/skill-triggers/<date>-<model>.md` below the research root, and exits 0 only when every
  skill passes and no session gave `UNKNOWN` twice; the row counts those queries. A query file
  that cannot be read, is not TOML, or has a `near` entry that names its own skill or a value
  that is not a skill name exits 2. Every session costs tokens. 68 new `harness test` cases run
  with no API call: the parser on the repository's files and on 19 refusals; the verdict on 11
  `stream-json` fixtures and on 4 malformed streams. Five fixtures are recorded from Claude Code
  2.1.295 sessions on `sonnet` with `--max-turns 1`, their private content stripped: a `Skill`
  call, a `Skill` call and a `Bash` call in one message, a text answer, a thinking block and a
  text, and two `Read` calls. A session that ends on a tool call under `--max-turns 1` reports
  `error_max_turns` with `is_error: true`, which is no error here. Six fixtures are written by
  hand for the shapes a session does not give on demand: three errors, a `Skill` call after
  another tool, one in a second message, and two in one message. The other cases test the
  majority, the pass rule at its bounds, and `--apply` on a fake `claude`. The live run and its
  table are not part of this change.

- **The committed `opencode.jsonc` denies an edit of the installed `build-reviewed` skill**, as
  the settings template does since `27f64d9`; `harness permissions --apply` regenerated it. The
  install no longer warns that the file is not what the template gives. Closes K24.

- **`harness install` no longer warns about `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` or
  `OPENCODE_DISABLE_CLAUDE_CODE`.** OpenCode v2 (2.0.25) has neither variable and reads no
  `CLAUDE.md` at all: its instruction files are `AGENTS.md` in its configuration directory and
  `AGENTS.md` from the working directory up to the project root. The warning therefore told the
  user that a variable stops files that v2 never loads. Its 23 `harness test` cases go with it.

- **`harness install --apply` names the frontends to restart, and only those.** After the count
  line it prints one line for each frontend whose files or steps changed something in that run,
  from the adapter's `RESTART`: Claude Code, OpenCode, oh-my-pi, in that order. An adapter with
  no `RESTART` exits 2 when it loads, as one with no `plan` does. A dry run, an `--apply` with no
  change, a change of the Julia environment alone, and a file that the install refuses print
  none. The OpenCode text that followed every apply with a change, also one that changed only
  `~/.claude`, is gone: its smoke checks were OpenCode v1 commands (`--variant`, `opencode debug
  skill`), and its `~/.zshrc` steps were personal. The warning that
  `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` is not 1 is gone too: OpenCode v2 has no such variable.
  Nine new `harness test` cases pin the restart lines, and one more the exit 2 of an adapter with
  no `RESTART`. The nine also catch three mutants of K17: no restart text after an `--apply`, no
  backup of `opencode.jsonc`, and a refusal that does not exit 2; K17 keeps the fourth, the
  templates of `harness leaks`.

- **`julia-critic-high` is gone; `build-part` spawns every critic as `julia-critic`.** Claude
  Code's `Agent` tool takes `effort` per spawn (2.1.293 and later), so a round-1 critic gets
  `effort: "high"` on its `Agent` call, and a verify critic gets none and runs at its
  frontmatter's `medium`. The repository has 20 agents. The OpenCode council of
  `examples/models.toml` is keyed on `julia-critic`, and under OpenCode critic `1a` runs at
  `julia-critic`'s variant, because the `task` tool takes no effort. **The private `models.toml`
  needs an edit before the next install:** rename the `[opencode.councils]` key
  `julia-critic-high` to `julia-critic`, and delete the `julia-critic-high` line of
  `[opencode.variants]`; a council key that names no agent exits 2. The install reports the
  installed `julia-critic-high.md` of Claude Code, OpenCode and oh-my-pi as `EXTRA`, each with
  its `rm` command.

- **The canonical `CI.yml` takes the coverage from `Julia 1` on ubuntu, not from `min`**, and its
  test matrix saves the Julia cache only from a job that succeeds (`save-always: false`). The
  instrumented job is the slowest of the matrix, and `min` is the slowest Julia. A cancelled or
  failed job saved a partial cache, which the next run of the branch restored and then
  precompiled some 300 packages again. The job names, and so the required checks, do not change.
  The header names the floors 1.10, 1.11 and 1.12.

- **A part of a task file is built at one of three levels**, chosen by its `tier` cell.
  `build` keeps the full builder-critic loop of `build-part`. The new `reviewed` runs the new
  `build-reviewed` skill: one `part-builder`, one blind `part-critic` at medium effort that blocks
  only on a failure inside a clause's domain, one fix round by the same builder, and the
  dispatching session's own check and read before the finish; a second FAIL goes to the user, and
  no advisor or arbitrator runs. The new `direct` is not a loop: the main session or a workflow
  makes the change, and the commands of the *Done when* check it. The two agents carry no
  language protocol: the plan's §V and §L name the gate. `plan-parts` names when each tier fits,
  and `build-part` hands a `reviewed` or `direct` part on. The settings template denies `Edit` of
  the installed `build-reviewed` skill (round sixty-one).

- **The agents and skills name no frontend in `model:` and `tools:`.** `model:` names a tier,
  `large`, `medium` or `small`, and `tools:` the neutral tools `read`, `edit`, `write`, `grep`,
  `glob`, `shell`, `agent`, `web_search`, `web_fetch` and `mcp/kaimon/<tool>`; README.md has the
  table of each frontend's names. Each adapter maps them. The Claude Code layer copies an agent or
  a skill with the value of `model:` and each `tools:` item rewritten in place, the model from a
  new `[claude]` table of `models.toml`. `[opencode.models]` and `[omp]` are keyed by the tiers;
  oh-my-pi keeps the roles `opus`, `sonnet` and `haiku` of `modelRoles`, so an agent still names
  `@opus`, and its default is the `medium` model. The installed agents and skills of all three
  frontends keep their bytes; two fixtures in `adapters/claude/fixtures/` pin the Claude Code
  render of `julia-builder` and `literature-scout`. A source with another `model:` or `tools:`
  value, a `mcp/kaimon/*` wildcard, a `models.toml` without `[claude]`, a `[claude]` model that
  is not a letter followed by letters, digits and `. _ - [ ]`, or that YAML reads as a boolean or
  null (`true`, `no`, `null`, ...), exit 2, and so does a table of the tiers with an old key. One
  refusal names every old key of every table and a missing `[claude]`, so the user fixes the file
  in one pass. The Claude Code layer writes the model unquoted into the YAML frontmatter.
  **The private `models.toml` needs an edit before the next install:**
  rename `opus`, `sonnet` and `haiku` to `large`, `medium` and `small` in `[opencode.models]` and
  `[omp]`, and add `[claude]` as `examples/models.toml` shows it. The stamp of the Claude Code
  layer and the `SessionStart` hook digest the source bytes, so an edit of `[claude]` is no drift.
  The body of `build-part` names its frontmatter as `model: medium`.

- OpenCode and oh-my-pi drop the rules whose cause is Claude Code's permission matcher, not only
  those whose cause is its sandbox. The override in their global `AGENTS.md` and in each rendered
  agent names both causes, and the oh-my-pi agents get it in their `bash` rule, where they had
  none. The lifted rules are named: a `git` alone on its line, no `cd … &&`, no `git -C`, no `$?`,
  and a failed `ps` read as a refusal; the `ps` rule moves from `RTK.md` to the Claude Code
  `CLAUDE.md`. Four statements were wrong for these frontends and are corrected. OpenCode's RTK
  plugin calls `rtk hook check`, which rewrites the first command of a pipeline, so
  `grep … | cat` stays capped there; `RTK.md` scopes its pipeline facts to Claude Code, and
  `OPENCODE-DELTA.md` names the `grep` tool for a whole search. oh-my-pi rewrites nothing through
  RTK. In oh-my-pi a compound command and a `git -C` still ask, because an `allow` pattern matches
  only a whole command. OpenCode's guard plugin runs four scripts, `rm-scope.py` among them; the
  `--auto` example names `gh release create`, because `git push --force` is a deny; and an
  OpenCode agent that makes its own worktree passes it as `workdir`, as the delta says, not
  `cd <worktree> &&`.

- The skills follow Anthropic's skill guide and its authoring best practices on two points. Each
  skill file of more than 100 lines opens with a **Contents** list of its sections, after the
  opening paragraphs, so that a reader that reads only the head of a file sees its whole scope:
  `build-part` (`SKILL.md`, `edges.md`), `plan-parts`, `julia-release`, `julia-performance`,
  `julia-package-audit`, `julia-structure` and `julia-surgical-fix`; `evidence.md` had one. The
  `build-part` description was 1,267 characters, over the 1,024 that the Agent Skills standard
  allows; it is 1,022, and it no longer names the models, the efforts or `julia-critic-high`.

- The builder-critic loop stops after round 2 and asks a new agent, `arbitrator`, how to go on.
  In the loop records of eleven task files, a loop of three or more rounds kept one cause through
  its rounds. Either the code copied another tool's reading and each round found a neighbour
  input, or each fix made the next defect, or a rule was undecided. A third round of the same
  kind did not close it; a change of design, a decision or a scope cut did. `arbitrator` (opus,
  high effort) reads the whole loop: the first design, every critic's and every builder's report,
  every fix diff and the suite runs. It gives each blocking defect a cause, measures progress
  round by round, and returns one move: `continue`, `redesign`, `decide`, `test round`,
  `fresh build`, `rerun`, `known issue` or `park`. `build-part` spawns it on four triggers:
  - the part's second critic FAIL: verify 2, or a later verify round after a PASS reopened the
    loop;
  - a finish builder that stops to ask for a code change after a PASS;
  - a `spec` defect that turns on a rule outside the part, which the plan's other parts read too;
  - a blocked loop, for the recommendation to the user.

  Another round runs only on its ruling, and a FAIL of that round blocks the part. It parks what
  only the user decides — a critic's counterexample accepted as a limit of the rule counts as a
  weaker *Done when* — and names the move it recommends and the fallback on a `Recommends:` line.
  A replay on three recorded loops matched the move that ended O2 and the kind of move of the
  other two. A round whose
  every blocking defect is `harness` does not count. `julia-critic` and `julia-critic-high` tag
  each blocking defect with its cause: `wrong result`, `evidence`, `spec`, `fix regression`,
  `neighbour` or `harness`. `edges.md` gains the kind *A part that predicts what another tool
  reads or does*: its design is fail-closed or canonical re-emission, decided before the build,
  and `plan-parts` points to it. The agent pins of `harness test` count 19 agents.

- The frontend code leaves `lib/harness/` for one adapter per frontend:
  `adapters/claude/adapter.py`, `adapters/opencode/adapter.py` and `adapters/omp/adapter.py`.
  The OpenCode fixtures move to `adapters/opencode/fixtures/`. `lib/harness/frontends.py` names
  the frontends `claude`, `opencode` and `omp` and loads each adapter by path. An adapter that
  fails to load, or that lacks `NAME`, `TEMPLATES`, `register`, `plan` or `selftest`, makes
  every `harness` verb exit 2 before it runs, with the adapter's path, and its line and the
  exception's last line where it failed. The shared part of `harness install` stays in
  `lib/harness/install.py`, and the neutral directories sit in `lib/harness/sources.py`.
  `adapters/claude/adapter.py` and `adapters/claude/fixtures/` are not installed. The stamp
  records them as not installed, and the hook `install-drift.py` skips every file below a
  top-level name that the stamp records; so the installed stamp and `hooks/install-drift.py`
  change, and the `SessionStart` hook warns until the next `harness install --apply`. The other
  installed bytes do not change. `harness install` no longer prints its head (the `source:`,
  `destination:` and `oh-my-pi:` lines and the blank line after them), and it prints its
  warnings before the skill links, so a dry run whose skill links exit 2 still shows them. The
  help of `install` is "install the configuration of each frontend", and that of `--force`
  "replace a file that the install refuses to replace". The other output of `harness install`,
  `harness permissions`, `harness settings install`, `harness settings selftest`, `harness
  trust`, `harness render` and `harness --help`, dry and sorted, is unchanged. `harness test`
  labels the install cases with their adapter (`claude:`, `opencode:`, `omp:`). The pre-push
  hook and CI compile `adapters/`.

- The sources leave the frontend directories. `claude/agents/`, `claude/skills/`,
  `claude/rules/`, `claude/instructions/` and `claude/commands/` are the neutral directories
  `agents/`, `skills/`, `rules/`, `instructions/` and `commands/` at the top of the repository;
  `CLAUDE.md`, `RTK.md` and `statusline-command.sh` are in `adapters/claude/`; `opencode/` is
  `adapters/opencode/` and `omp/` is `adapters/omp/`, each with the same relative paths. Every
  installed path stays.
  `harness install` reads the Claude Code layer from the five neutral directories, each at its
  own path below `~/.claude/`, from `adapters/claude/` at the top of `~/.claude/`, then from
  `hooks/` and the tree instructions; the stamp names these sources, so the `SessionStart` hook
  warns until the next `harness install --apply`. The OpenCode-only `edit` ask on the
  repository's OpenCode sources is `{harness}/adapters/opencode/**`. The generated-by comment of
  an oh-my-pi agent names `agents/<name>.md`. `harness install` exits 2, before anything is
  written, on a file of `adapters/claude/` below `agents/`, `skills/`, `rules/`,
  `instructions/`, `commands/` or `hooks/` (compared with case and Unicode form folded): those
  installed paths have their sources only in the neutral directories and `hooks/`, and OpenCode
  and oh-my-pi render their agents from `agents/` alone. A new case checks that each `@` import
  of `CLAUDE.md` has a source in the plan.

- `rules/changelog.md`: the rule "a changelog is never corrected" starts at the release, not
  at the merge. A merged entry in `[Unreleased]` may be corrected until it is true for its release.

- `test-layout.jl` and `run-tests.jl` know a sixth test group, `doctests`. D9 requires
  `test/quality/doctests.jl` in `doctests`, and reports it in any other group, `slow` included,
  with the group it is in; a file other than `test/quality/doctests.jl` in `doctests` is a D9
  violation. The `GROUPS` line does not change, so empty `ARGS` runs `core` and `slow`, and the
  group `doctests` runs only when it is named; the CI Doctests job calls `doctest` itself.
  `run-tests.jl <repo> doctests` runs the group, and `affected`, which selects from `core` alone,
  never selects it. `rules/julia-tests.md` names the six groups and the command for a doctest
  change.
- D3 in `test-layout.jl` reports a test file at the top level of `test/` that has no
  `src/<name>.jl` of the same name, compared with case, listed or not; a repository with no
  `src/` is exempt, as from the directory rule of D3. `rules/julia-tests.md` states the rule.
- `test-layout.jl --check` prints nothing on the 43 repositories with tests at their
  `origin/main`, after each repository moved its doctests line into `doctests` and its
  top-level test files into the directories of D3.
- `adapters/claude/statusline-command.sh`: the Claude Code status line, installed as
  `~/.claude/statusline-command.sh`, where the `statusLine` setting runs it. It shows the model,
  the effort, the tokens in and out, and the five-hour and weekly rate limits in green, yellow
  and red by use, with the time until the five-hour reset. It needs POSIX `sh`, `jq` and
  `date +%s` only, so it runs on macOS and Linux; the installed copy that it replaces called
  BSD `date -r`. The settings template does not hold `statusLine`, because
  `harness settings install` owns `permissions`, `hooks` and `sandbox` only.
- `harness install` renders the 18 Claude Code agents to oh-my-pi's agent directory,
  `$PI_CODING_AGENT_DIR` or `~/.omp/agent`, at `agents/<name>.md` for each. Each rendered
  agent has frontmatter with `name`, `description`, `tools` (mapped by `TOOLS` of
  `adapters/omp/adapter.py`: Read, Edit, Write, Grep, Glob, Bash, Agent→task,
  WebSearch→web_search, WebFetch→read;
  mcp__kaimon__<tool> → mcp__kaimon_<tool>), `model` as the role `@<tier>`, `effort` as
  `thinking-level` and `skills` as `autoloadSkills`, each value written as JSON; a
  generated-by comment; an "Under oh-my-pi"
  section from `adapters/omp/UNDER-OMP.md` for agents using Claude Code mechanisms (preloaded
  skills, worktree isolation, the Agent tool, the Bash tool's timeout, Kaimon tools); and the
  body. A tool with no oh-my-pi name or a wildcard, a tier outside `[omp]`, a `name:` that is
  not the file name, or a reserved name `main` or `sub` exits 2. No
  council copies. An installed oh-my-pi agent with no source is `EXTRA` in the dry run.

  `models.toml` gets an `[omp]` table: `opus`, `sonnet`, and `haiku` as strings. `config.yml`
  gets `modelRoles` with one role per tier and `default` set to the sonnet model. A missing
  tier, unknown key, non-string or blank value, or no `[omp]` table exits 2. `mcp.json` holds Kaimon
  alone: type http, url `http://127.0.0.1:2828/`, Authorization header with Bearer token
  from `~/.config/kaimon/opencode-token` (no secret in the file). `config.yml` sets no
  `enabledProviders`, so `~/.claude.json` and OpenCode's MCP servers are not imported.

  `render_agents` of `adapters/opencode/adapter.py` refuses a council keyed by a name that no
  source agent has, which it dropped with no error, and `load_models` refuses a seat whose
  `name` is not a string; the council of `examples/models.toml` is keyed by `julia-critic-high`.
  `hooks/probe.py` passes the example `[omp]` table to `render_config`. `harness test` gains
  cases for each of these, and a `dry_run` case with a regular token file that finds no
  "opencode-token" line in the output. The user's private `models.toml` needs an `[omp]`
  table before the next install, or the install exits 2.
- oh-my-pi reads the same instructions and rules. `harness install` writes
  `adapters/omp/OMP-DELTA.md` byte for byte as `AGENTS.md` in oh-my-pi's agent directory,
  `$PI_CODING_AGENT_DIR` or `~/.omp/agent`. Its first three lines import `~/.claude/RTK.md`,
  `~/.claude/instructions/core.md` and `~/.claude/instructions/research-tree.md`; the rest
  states the facts of oh-my-pi: no sandbox, the approval mode `write` and the guard extension;
  no session scratchpad, no worktree hook, nothing in the background; a directory-scoped
  `CLAUDE.md` loads only at the start, from the working directory up towards the home
  directory, so the model reads one below the working directory itself; the rules are
  listed by name and read through `rule://<name>`; the skills are the links of
  `~/.agents/skills/`. It is 3,508 bytes. Each rule that the Claude Code layer installs goes
  to `rules/<name>.md` in the agent directory, as that layer renders it, with its frontmatter
  written anew (`render_rule`): `globs` and `description` as JSON values, which YAML reads as
  the source's `paths` and `description` whatever the source's spacing, and the body byte for
  byte. oh-my-pi lists a rule by name, globs and `description` and never uses one whose
  `description` YAML does not read as a non-blank string, so a rule source exits 2 before
  anything is written unless its frontmatter, from line 1 `---` to the next line `---`, holds
  only one line `description: <text>` and at most one line `paths: ["…", …]`, no HTML
  comment, no tab, no whitespace at the start or end of a line and no control character. The
  text is plain or in double quotes and not blank, a U+FEFF counted as blank. Each refusal
  names the file and the line. A rule source in a subdirectory of `rules/` exits 2 too, as
  oh-my-pi reads no subdirectory of its `rules/`. An installed rule in oh-my-pi's `rules/` (a
  `.md` or `.mdc` file) with no source is EXTRA in the dry run, with its removal. No rule sets
  `alwaysApply`; no `RULES.md` is written; nothing is written below `skills/`.
  `rules/julia-tests.md` gets a `description`.
  `harness test` gains cases: the dry run lists `AGENTS.md` and one rule per source; the
  delta's first three lines are the imports; the delta is no larger than 5,114 bytes;
  `--apply` writes AGENTS.md byte for byte and each of 8 rules with `globs` equal to the
  source's `paths`, its description, no `paths` key and the body byte for byte, and nothing
  else (nothing below `skills/`); a rule source with no description, no frontmatter, an empty
  description or one below the frontmatter exits 2, names the file and writes nothing, and so
  does a rule source one or two levels deep in a subdirectory of `rules/`; the renderer refuses
  each of 49 other forms of the frontmatter, each refusal naming the file and the line, and
  takes 27, each read back with `json.loads` as the source's globs and description; a template
  rule reaches oh-my-pi rendered; a stale rule is EXTRA. The rule fixtures of the install cases
  and of the `install-drift.py` cases in `hooks/probe.py` carry a description.
- oh-my-pi gets a permission layer. `harness install` writes `config.yml` into oh-my-pi's agent
  directory, `$PI_CODING_AGENT_DIR` or `~/.omp/agent`, from the settings template that
  `harness permissions` reads: `tools.approvalMode: write`, `tools.approval.eval: deny`, `edit`
  and `write` allowed, and every Bash entry of the template as a `bash.patterns` rule, every
  `deny`, then every `ask` as `prompt`, then every `allow`, each in the template's order, because
  oh-my-pi takes the first rule that matches. A `:*` suffix renders to `*` after the same prefix,
  and a bare `Bash` to `*`; the template holds neither. The file is JSON below a comment header,
  which oh-my-pi 18.6.1 reads back (`omp config get`). Beside it go `extensions/guards.ts`, from
  the new `adapters/omp/guards.ts`, and the path list `extensions/guard-paths.json`: under `deny`
  the `read` denies of `adapters/opencode/plugins/guard-paths.json`, under `edit` the template's
  `Edit` and `Write` denies, both rendered. The extension runs `no-blind-stage.py`,
  `no-shell-file-write.py` and `gh-api-writes.py` from `~/.claude/hooks/` with `python3` on
  every `bash` call. It applies `deny` to the path of `read` and `grep` and to each word of a
  `bash` command, quotes removed and resolved against the call's `cwd` or the working directory,
  and `edit` to each path of an `edit` or `write` call; it adds `~/.omp/**`, oh-my-pi's own
  directory and its credentials, to both, and ignores case. Unlike OpenCode's plugin it fails
  closed: a guard that is missing, cannot run, exits with another status than 0 or 2, is killed,
  prints output that is not JSON or takes more than 10 s blocks the call, and so does a missing
  or malformed path list. With the dummy profile the patterns are 184 `deny`, 98 `prompt` and
  210 `allow`; the `deny` and `prompt` counts equal the `bash` counts of OpenCode's block less
  its two OpenCode-only rules. `hooks/probe.py` loads the extension under `node` with a stub of
  oh-my-pi's API and gains 81 cases, among them a `git push --force`, a `sed -i`, a `gh api`
  write, reads of `auth.json` by relative and quoted paths, edits of the installed hooks and of
  `~/.omp`, and each fail-closed path; `harness test` checks the dry run, the installed files,
  the path list and the patterns entry by entry. The cases set `PI_CODING_AGENT_DIR` to a scratch
  directory and the contract sweep unsets it, so that no run of theirs reaches the real `~/.omp`.
- `harness install --apply` writes, after the Claude Code layer, the stamp
  `~/.claude/.harness-install.json`: the sources (the neutral directories, `adapters/claude/`,
  `hooks/` and the tree instructions) and a SHA-256 over the installed path, mode and bytes of each
  file that the apply installs. A stamp that differs is a change, which the dry run lists and
  counts. The new `SessionStart` hook `hooks/install-drift.py` computes the same digest from the
  sources that the stamp names, and warns, as a `systemMessage` and as `additionalContext`, when the
  digests differ, when the stamp is missing or cannot be read, and when a source cannot be read or
  holds a symlink or a FIFO, naming the path. It runs no install, blocks nothing and exits 0; over
  56 files its digest takes about 3 ms. `install.py` takes the stamp's digest from the hook's
  `digest_of`, over the plan it installs, so the stamp and the check are one computation, and a
  source edited while the apply runs is drift. The settings template denies `Edit` on every
  installed path below `~/.claude`: `CLAUDE.md`, `RTK.md`, the stamp, `agents/**`, `commands/**`,
  `instructions/**`, `rules/**` and each of the 11 skills by name, so `skills/synced/` stays
  writable. The `ask` rules of `CLAUDE.md`, `RTK.md`, `agents/**` and `rules/**` go, and
  `hooks.SessionStart` runs the hook. The `edit` block of `adapters/opencode/opencode.jsonc` follows
  the template, but an OpenCode-only `ask` after it still decides `rules/**` (K10). `hooks/probe.py`
  gains 16 cases for the hook against an installation in a fixture (353 in all), and `harness test`
  checks the stamp, a source edited during the apply, and that each installed path is a deny and the
  writable paths are not (682 cases).
- OpenCode reads its own global instruction file in place of `~/.claude/CLAUDE.md`, the Claude
  Code mechanics. `harness install` writes `adapters/opencode/OPENCODE-DELTA.md` as `AGENTS.md` in
  OpenCode's configuration directory; the dry run lists it as `AGENTS.md from OPENCODE-DELTA.md`,
  and a hand-made `AGENTS.md` that differs is `REPLACE`, with no merge. The `instructions` of
  `opencode.jsonc` list exactly `~/.claude/RTK.md`, `~/.claude/instructions/core.md` and
  `~/.claude/instructions/research-tree.md`, and the comment gives the delta's budget, 5 KB. The
  delta states OpenCode facts instead of corrections of `~/.claude/CLAUDE.md`, at 4,979 bytes
  against 5,114: "never create an `AGENTS.md`" becomes "this is the one `AGENTS.md`", and the
  rule against an `AGENTS.md` in a directory of the tree stays. The delta orders the council
  seats alphabetically, so `julia-critic-deepseek-v4.1-flash` is `1b` and
  `julia-critic-gpt-6-sol` is `1c`. `harness install` warns, with the value, when
  `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` or `OPENCODE_DISABLE_CLAUDE_CODE` holds a value that
  OpenCode reads as true (`true`, `yes`, `on`, `1` or `y`): either takes `CLAUDE.md` out of
  OpenCode's project file names, so every directory-scoped `CLAUDE.md` stops. The global file
  goes to `$OPENCODE_CONFIG_DIR` when that is set, as OpenCode reads it from there.
  The harness-neutral paragraphs and sentences of `adapters/claude/CLAUDE.md` move byte for byte:
  `--no-verify` for maintenance commits, a repository query from its root, the zsh colon trap
  and the meaning of a failed status command and of a pipe's status into
  `instructions/core.md`, and the two working directories, the precedence of the more
  specific file, the worktree location and removal, Claude Code's `.claude/worktrees/`, a silent
  push to `main` and the installed-copy rule into the tree instructions'
  `instructions/research-tree.md`. Five places change a word or two to read in their new file or
  without their moved neighbour. Claude Code reads the same words as before, outside the
  headings and those changes. The preamble of each rendered OpenCode agent names the global
  `AGENTS.md` in place of `OPENCODE-DELTA.md`, so the next install replaces all 20: the 18 agents
  and the two council copies. The drift check for an `opencode.jsonc` that names a missing
  delta is gone with the name.
- The Claude Code instruction layer moved from `~/.claude` into the neutral directories and
  `adapters/claude/`: the 18 agents, the 11 own skills (14 files), the rules except
  `meta-repository.md`, `CLAUDE.md`, `RTK.md`, `instructions/core.md` and the two commands, byte for
  byte except the lines that named a repository of the user's tree, an organisation or a personal
  string. Those lines now name `Packages/Example`, a package by its role, or the tree instructions,
  which hold the names. `instructions/profile.md` and `rules/meta-repository.md` moved to the tree
  instructions; the first is renamed `instructions/research-tree.md`, which `CLAUDE.md` imports and
  the `instructions` list of `adapters/opencode/opencode.jsonc` names. After an `--apply`, the
  installed `instructions/profile.md` is reported as `EXTRA`. The text that told a session to edit
  an installed copy names its source and the user's `harness install --apply`. `harness install`
  renders the OpenCode agents from `agents/`, not from `~/.claude/agents/`, and the frontmatter
  cases parse the agents and skills of the neutral directories, not the machine's.
- New `.githooks/pre-push`, `.github/workflows/test.yml` and `.github/workflows/julia.yml` gate
  pushes and testing. The pre-push hook runs on every push to `main`, testing the pushed commit
  (never the working tree) with `bin/harness test` on `python3` and `python3.11`, the compile
  check, `shellcheck` over the shell files, and the Julia test files that the changed paths
  select; a push to any other branch runs nothing. `test.yml` runs the Python checks, `shellcheck`
  and `actionlint` on every push, pull request and dispatch. The workflows pin every `uses:` to a commit SHA with the version in a
  comment, declare `permissions: contents: read`, and use one concurrency group per ref with
  cancel-in-progress; Julia testing runs on Julia 1.13 when a `.jl` file or `Project.toml`
  changes, with fatou 0.22.0 on the `PATH`, which `mutate.jl` needs. README.md gains a `## Tests` section describing the tests. A push of a README-only
  commit to `main` takes about 28 s with the Python steps on both interpreters. `hooks/probe.py`
  closes K5: the cases now run in a git work tree of the fixture, whose `.gitignore` ignores
  `__pycache__/`, never the checkout. Before, with the checkout under `/tmp/` or `$TMPDIR`,
  27 cases failed, because `no-shell-file-write.py` treats such paths as scratch; this unblocks
  every run in a temporary directory. `bin/harness test` in a clone under `$TMPDIR` now gives
  `600 cases, 0 wrong` on both `python3` and `python3.11`.
- `harness test` runs, after each module's own cases, the hook probe `hooks/probe.py` and then
  a contract sweep, `lib/harness/sweep.py`, with one summary line for all three: 518 cases here
  (143 + 337 + 38), in about 10 s. It exits 1 when any case is wrong, a probe case included.
  The probe runs on a fixture `HOME` one level below a temporary directory, with
  `Packages/Example` and `~/.claude` as repositories, so it passes with an empty `HOME`, where 9
  cases failed before, and with `TMPDIR` unset; it names no `/Users/` path. The probe and the
  sweep drop the caller's `GIT_*` variables, so a `GIT_DIR` cannot send their git commands to
  another repository. The hooks get that `HOME` spelt with two leading slashes,
  because `no-shell-file-write.py` treats every path whose text begins with `/tmp/` or
  `$TMPDIR` as scratch. Each Python hook runs with the probe's own interpreter, not its
  shebang, with a 30 s timeout. The sweep runs the dry run of every verb except `format` and
  `ci-protection` on a fixture `HOME` and `RESEARCH_ROOT`: it exits 0 or 1 and changes no
  file; each missing precondition exits 2 with one line; and for `githooks`,
  `wiki-lint-hook`, `workflows`, `trust` and `settings install` the dry run after `--apply`
  exits 0. Fixed on the way: `settings surface`, `twins`, `domains` and `install` with no
  `~/.claude/settings.json` exit 2 with `no settings file at <path>`, not a traceback, and with
  one they cannot read exit 2 with `cannot read <path>: <reason>`.
- `harness install` now copies the Claude Code layer into `~/.claude/` from the neutral
  directories, `adapters/claude/` and `hooks/` in this repository, and the tree instructions,
  the private directory the profile key `tree_agents` names. The neutral directories,
  `adapters/claude/` and the tree instructions mirror the layout of
  `~/.claude/`; the tree instructions' `README.md` is not installed. A file is copied byte for
  byte unless `CLAUDE_TEMPLATES` lists its installed path (empty for now); a template is rendered
  with the profile. A hook keeps its source's mode, and every other file is installed 0644.
  Agents and hooks install from `agents/` and `hooks/` only: a file below `agents/` or `hooks/`
  in the tree instructions is not installed, and is reported as a `SKIP` line, not counted. It
  exits 2, before anything is written, on a missing `tree_agents` key, a value that is not the
  absolute path of a directory, a source that holds `settings.json` or `settings.local.json`, a
  symlink, an entry that is neither a file nor a directory, or a directory or file that cannot be
  read in a source, a path that two sources hold (both named, and compared with case and Unicode
  form folded, on every platform, as the default macOS volume compares them), an installed path or
  a directory above one that is a symlink, or an installed path that is not a readable file below
  directories. An installed file with no source, below a top-level directory the layer writes
  into, is reported as `EXTRA` with its `rm` command, not counted and not removed; `skills/synced/`
  and hidden names are not searched, and a directory there that cannot be read exits 2, before
  anything is written. A mode-only difference is reported as `MODE` and counts as a change. `settings.json`
  is not written; when `harness settings install` would change it, or it cannot be compared, a
  warning says so. `~/.claude.json` is neither read nor written. `harness test` gains 50 cases
  for this layer, run on a scratch HOME. The contract sweep's fixture holds the tree
  instructions, and the sweep gains one case: `install` without them exits 2 with one line.
- The frontmatter parser closes its remaining gaps, and `KNOWN_ISSUES.md` goes with its last
  entries, K1, K2 and K3. It also rejects DEL (U+007F), the C1 controls U+0080–U+009F (NEL
  included), LS (U+2028) and PS (U+2029) with the line and the code point, and a tab at the
  start or the end of a plain value or a list item; spaces at the edges of an item are dropped,
  as for a value. K1: `tools` and `skills` take a block list and every other key a value, so
  `tools: Read, Bash` exits 2 instead of rendering `bash: deny`, and `skills: julia-structure`
  instead of one `allow` line per character. K2: a profile that
  is not TOML or not UTF-8, and a `models.toml` that is not UTF-8, exit 2 and name the file,
  with no traceback. K3: where `stat` of the Kaimon token raises, as under the Claude Code
  sandbox, `harness install` prints a warning that names the path and the error and
  goes on. `harness test` covers each of these.
- OpenCode: the council preamble counts the seats of `[opencode.councils]` in `models.toml`
  ("Round 1 has two critics here, `1a` and `1b`" for one seat), and no seat is named in fixed
  text: `OPENCODE-DELTA.md` tells the dispatcher to spawn each council copy as `1b`, `1c`, … in
  the alphabetical order of their names. A council with no seat or with more than eight, and a
  seat name used twice or by another agent, exit 2 and name the file. The rendered agents of
  the current tables do not change.
- **OpenCode generators are now Python**: `adapters/opencode/adapter.py` replaces the three Julia
  generators (`generate-agents.jl`, `generate-permissions.jl`, `generate-skill-links.jl`);
  `opencode/scripts/` is gone. The 20 auto-generated OpenCode agents no longer live in
  `opencode/agents/`; `harness install` renders them from `~/.claude/agents/` on every run,
  so the next install reports those 20 files as `REPLACE` once. The output equals the Julia
  generators' byte for byte except the generated-by comment, which names `harness install`.
  The model tables — the model of each tier, the per-agent overrides, the variants, the
  reasoning effort and the critic councils — leave the code for `models.toml` beside the
  profile, `harness --models F` or `$RESEARCH_HARNESS_MODELS`; `examples/models.toml` shows the
  layout. A missing table, one without `[opencode]`, or an agent whose tier has no entry exits
  2 and names the file. `harness leaks` with the real profile reports 0 hits: its 10 were all in
  the committed agents.
- `harness permissions [--apply]` replaces `generate-permissions.jl --write`: its dry run
  prints the round-trip report and what would change in `adapters/opencode/opencode.jsonc` and
  `adapters/opencode/plugins/guard-paths.json`. A skill link of the generator's own whose skill is
  no longer curated is now `REMOVE`, counted as a change in the dry run, because `--apply` removes
  it; the Julia `--check` reported it as `EXTRA`, uncounted. A foreign entry in
  `~/.agents/skills/` is reported with its `rm -r` command and not counted.
- The frontmatter parser is strict: a new parser in `lib/harness/frontmatter.py` enforces
  ten keys with plain or double-quoted values and block lists of plain strings only; flow
  lists, block scalars, comments, anchors, duplicate or unknown keys, and a CR or any other
  C0 control character (U+0000–U+001F) except tab exit with status 2 and name the file and
  line.
- **The ten replaced scripts are gone**: `install-githooks.sh`, `install-wiki-lint.sh`,
  `install-workflows.sh`, `push-all.sh`, `ci-protection.sh`, `format-tree.sh`,
  `opencode/install.sh`, `trust-research-repos.py`, and the shims `audit-permissions.py` and
  `render_profile.py`. Every comment, hook message, agent and the README name the `harness`
  verb; `README.md` documents the command, its contract and `PATH`. The comment headers of all
  five workflow templates and of the three hooks change, so the next roll-out writes every copy.
  The OpenCode critics are regenerated from their sources.
- `bin/harness` is the front door to the tooling, a Python 3.11 command with one contract: a
  verb that changes something is dry by default and exits 1 when it would change something,
  `--apply` changes it, exit 2 is a usage error or a failure. `harness --profile F` names the
  profile for every verb. The first verbs are `render`, `get`, `leaks` and `test`, from
  `scripts/render_profile.py`, whose code is now `lib/harness/profile.py`; the old script is a
  shim with its old command line until its callers move.
- `harness githooks`, `harness wiki-lint-hook`, `harness workflows` and `harness trust` do what
  `install-githooks.sh`, `install-wiki-lint.sh`, `install-workflows.sh` and
  `trust-research-repos.py` do, which stay until their callers move. `harness githooks` reports
  only what differs — a file's bytes, a hook's execute bit, `core.hooksPath` — where the script
  listed every repository; both installers name each repository whose `core.hooksPath` a
  sandboxed session could not set.
- `harness push-all`, `harness ci-protection [--remove-classic]` and `harness format` do what
  `push-all.sh`, `ci-protection.sh` and `format-tree.sh` do, which stay until their callers
  move. `harness ci-protection` reads each ruleset and the repository's two flags first and
  writes only what differs, where the script wrote every repository on each run; the ruleset
  check of `--remove-classic` is Python instead of `jq`, with its own cases. `harness test` runs
  the cases of every module.
- `harness settings <sub>` is `audit-permissions.py`, now `adapters/claude/adapter.py`. Its `diff`
  and `install` are one verb: `harness settings install` is the dry run that `diff` was, and
  `--apply` merges. `harness install` does what `opencode/install.sh` does, and exits 2 where
  the script went on silently after refusing to replace an `opencode.jsonc` that holds a
  literal credential. `settings/audit-permissions.py` is a shim with the old command line, and
  `opencode/install.sh` stays, until their callers move.
- **The Julia scripts have their own environment.** `Project.toml` declares the six packages
  they load beyond the standard library — `ExplicitImports`, `JSON`, `JuliaFormatter`,
  `JuliaSyntax`, `TestEnv`, `YAML` — with `[compat]` bounds and no manifest. `harness install
  --apply` copies it to `~/.local/share/research-harness/julia/` (`$RESEARCH_HARNESS_JULIA`) and
  instantiates it there, adding the General registry to a new depot; `julia-update.jl` updates
  that copy, never the checkout's. Each script that loads one of the packages puts the
  environment first in `LOAD_PATH`, so no caller passes `--project=@v1.13`;
  `explicit-imports.jl`, `mutate-worker.jl` and the test driver of `run-tests.jl`, which run
  inside a package's environment, put it last. The formatting stage of `pre-commit` and
  `pre-commit-wiki` follow. With an empty depot, `harness install --apply` and then every
  script's own test pass. **The installed `julia-update.jl` in `~/.local/bin/` needs a
  reinstall.**
- The sources name no repository of the research tree and no organisation. Three new profile
  keys: `repository_roots`, the directories that hold the tree's repositories; and
  `docs_exceptions` and `docs_additions`, the repositories that keep their own documentation
  workflow, which `githooks/install-workflows.sh` and `verify-workflows.jl` read instead of their
  own lists. **An installed profile without the two `docs_` keys stops both scripts.**
  `render_profile.py leaks` also searches the repository for every directory name below
  `repository_roots` and every `org` entry, as whole words, and allows the repository's own
  `owner/name`; `render_profile.py get KEY` prints a profile value for a shell script.
  Comments keep the mechanism without the incident; examples name `Packages/Example`;
  `release-notes-test.jl` builds its changelogs instead of reading the packages' own, and the
  two `probe.py` cases that need a real work tree use the harness checkout. The comments of the
  workflow templates `CI.yml`, `Documenter.yml` and `codecov.yml` change too, so
  `verify-workflows.jl` reports every installed copy as drifted until the next roll-out with
  `install-workflows.sh --apply`.
- `verify-workflows.jl` reads its templates next to itself; it still read them below
  `Environment/Harness/`, which no longer exists, and failed on the first template.
- The checkout is `~/Research/Harness/`, no longer inside `Environment/`. A new profile key,
  `harness`, holds its absolute path: `adapters/opencode/opencode.jsonc` and
  `generate-permissions.jl` write `{harness}` for it, and the instruction path of
  `OPENCODE-DELTA.md` no longer relies on OpenCode's `~` expansion. **An installed profile without
  `harness` stops the render** of `opencode.jsonc`, and so `install.sh`, with the unknown-key error.
  The git hooks, the wiki hook, `install-workflows.sh`, `ci-protection.sh`, `repo-drift.js` and the
  ast-grep configuration name `Harness/` below the research root. The installed copies that still
  name `Environment/Harness/` work through a link there until they are reinstalled.
- OpenCode: seat `1b` of the round-1 critic council is `julia-critic-gpt-6-sol`, GPT-6 Sol on
  Azure at `reasoningEffort: high`, in place of `julia-critic-sonnet-5.5`, so the council needs
  no second Anthropic model. In the critic probe it found 3 and 5 of the head's five defects in
  7–9 minutes, against Sonnet's 4 and 2 in 9–10. `generate-agents.jl` gains `REASONING_EFFORT`,
  which writes `reasoningEffort:` for a model with no OpenCode variant: OpenCode sets no effort
  for a `gpt-6-*` ID. The seat needs `AZURE_RESOURCE_NAME` where OpenCode starts. An installed
  `julia-critic-sonnet-5.5.md` is left in place by `install.sh` and must be removed by hand.
- A private profile holds every value that names a person, an institution or a machine:
  `~/.config/research-harness/profile.toml`, with the dummy `examples/profile.toml` as its
  schema. `scripts/render_profile.py` renders a template with it, and its `leaks` command
  searches the repository for the profile's `leak` strings.
- `settings/settings.proposal.json` is a template: `{home}`, `{org}`, `{extra_domain}`,
  `{protected_dir}` and `{memory_project}` replace the home path, the five organisations, the
  institution's resolver, the synchronised share and the memory directory. Every
  `audit-permissions.py` command renders a file that holds a placeholder, so `diff` and
  `install` compare and merge the render. On the template machine the render equals the live
  file.
- `hooks/cc-status` passes a hook event to iTerm2's `cc-status` utility and exits 0 where
  iTerm2 is not installed. The ten status hooks of the settings template call it, so the
  template serves a machine without iTerm2 (settings round fifty-eight).
- OpenCode: `generate-permissions.jl` writes `{home}` for the home directory, so
  `opencode.jsonc` and `plugins/guard-paths.json` hold no machine's path. The model providers
  come from the profile's `opencode_providers`. `install.sh` renders both files with the
  profile before it compares and copies them.
- `generate-permissions.jl` reads the settings template instead of the live
  `~/.claude/settings.json`, so the generated block keeps `{home}` and `{protected_dir}` and
  needs no machine to run. A text render repeats a line that holds a list placeholder once
  per item.
- `launchagents/`: the plists are templates named by job — `kaimon.plist`,
  `julia-update.plist`, `claude-autocommit.plist` — with `{home}` and `{launchd_prefix}`.
  `render_profile.py render` writes the installed copy. `julia-update.jl` reads the Kaimon
  job's label from the profile, so it needs the profile at run time.
- `hooks/probe.py` and `agent-workflows/repo-drift.js` name no home directory: the probe
  cases use the running user's home, and the workflow takes the research tree's root from its
  first repository path.
