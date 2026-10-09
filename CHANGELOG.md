# Changelog

## Unreleased

- **The documentation site is a VitePress site.** `docs/make.jl` renders the pages with
  DocumenterVitepress (`[compat]` 0.3.7). Documenter's `deploydocs` still deploys the site to the
  root of `gh-pages` and removes the files of the old site, so the URL stays
  `https://michakraus.github.io/ResearchHarness/`; a page's URL loses its trailing slash, as
  `/tutorial`. `DocumenterVitepress.deploydocs` deploys only to a subdirectory. The site holds a
  `.nojekyll`, so that GitHub Pages also serves a VitePress file whose name starts with `_`.
  DocumenterVitepress 0.3.7 drops the alt text of a local image, so `docs/make.jl` adds a method
  that keeps it: the call graphs of *Agents at work* keep their text description.
  The site has VitePress's light and dark themes, a search box, and an edit link to `main`; the
  edit link of the home page opens the README. The VitePress configuration and theme are in
  `docs/src/.vitepress/`, and `docs/package.json` names the npm packages. The build runs `npm`
  from `NodeJS_20_jll` and writes the site to `docs/build/1/`; `docs/node_modules/` and
  `docs/package-lock.json` are not tracked. A local build decides not to deploy, so it prints no
  warning.

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
