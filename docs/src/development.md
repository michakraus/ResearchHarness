# Development

## Tests

`harness test` runs the test cases of the harness as parts, each in a process of its own, and
prints one summary line, `<n> cases, <w> wrong`. It exits 1 when a test case fails, and 2 on a
usage error. `harness test --list` prints the part names. The parts are:

1. Each module's own cases, by the module's name (`install`, `profile`, …), and each adapter's,
   by the name of its directory (`claude`, `opencode`, `omp`, `antigravity`). The cases of
   `doctor` run as five groups, `doctor:minimum`, `doctor:linux`, `doctor:darwin`, `doctor:exit`
   and `doctor:process`.
2. The hook probe, `hooks/probe.py`, which runs every Python hook with the same interpreter on a
   fixture `HOME`. Its seven groups run as the parts `probe:commands`, `probe:payloads`,
   `probe:manifest`, `probe:drift`, `probe:omp`, `probe:opencode` and `probe:antigravity`, each on
   a fixture of its own.
3. The contract sweep, `sweep`, from `lib/harness/sweep.py`, which runs the dry run of every
   subcommand except `format`, `ci-protection`, `skill-triggers`, `doctor`, `changelog` and
   `mutate` on a fixture `HOME` and research tree. The cases of `skill-triggers` run its dry run
   and its `--apply` on a fake `claude`, the cases of `doctor` run it on the sweep's fixture with
   stub commands, the cases of `changelog` run it on scratch repositories, and the cases of
   `mutate` run it on a fixture repository with a stub `bin/harness`.

With no argument, `harness test` runs every part. Part names select those parts, and
`--changed BASE` selects the parts that own a path of `git diff --name-status BASE...HEAD`; both
paths of a rename count. The table `OWNERS` of `lib/harness/testrun.py` gives the owners: a
module's own file, an adapter's directory, `hooks/` for the probe's groups, `docs/` for `docs`,
`docs/src/dependencies.md` also for `doctor:minimum`, and `changelog.d/` for `changelog`. The
directories of `omp`, `opencode` and `antigravity` also select the probe group of the same name,
which loads their guard files. A path that no part owns selects every part. `docs` and `sweep` run
in every selection, and `--changed` prints on stderr which path selects which parts. `--changed`
reads the commits only, so an edit that is not committed selects no part beyond `docs` and
`sweep`. While you work on one module, commit and run
`harness test --changed origin/main`; run the whole suite once before you push. The hook probe is
a part of `harness test`, so it needs no run of its own.

`--jobs N` runs at most N parts at once, half the CPUs by default. Each part's output is printed
whole, in the order of the part names, followed by a line `part <name>: <n> cases, <w> wrong`.
`--log FILE` writes all of it to `FILE` and prints only the `BAD` lines and the summary. A part
that crashes counts as one failed case and shows its traceback; a part that runs longer than
300 s is stopped and counts as one failed case.

At most two runs of `harness test` share a machine. A run holds one of two slots, an exclusive
`flock` lock on `slot-1.lock` or `slot-2.lock` in `research-harness-test/` below
`$XDG_RUNTIME_DIR`, else `$TMPDIR`, else `/tmp`. A third run prints that it waits, and starts when
a slot frees. The kernel releases the lock when the process that holds it ends, also after a
crash. `--list` takes no slot.

The sweep checks the contract of [the `harness` command](harness-command.md): a dry run changes
no file, a subcommand with a missing precondition exits with status 2 and prints one line, and for
the four subcommands that it applies, a dry run after `--apply` has nothing to do. Each fixture
lives in a temporary directory, so the cases need nothing from the machine's own `HOME`.

`harness test` passes wherever the checkout lies, below `/tmp/` or `$TMPDIR` too. The hook probe
loads `adapters/omp/guards.ts` and the OpenCode plugins `adapters/opencode/plugins/*.ts` under
`node`, so `node` must be on `PATH`; a missing `node` makes a test case fail. The cases of
`lib/harness/script_cases.py` run the package copies of `run-tests.jl` and the critic with
`rsync`, and `scripts/spec-gate.py` on a fixture task file; they need no Julia.

## The strict profile

The Python code of the harness follows one profile, which `pyproject.toml` sets. `ruff format`
gives the layout, at line length 110; `.git-blame-ignore-revs` names the commit that formatted
the whole tree, so `git blame --ignore-revs-file .git-blame-ignore-revs` skips it.
`ruff check` runs the rule families `E F W B BLE TRY PTH S UP SIM RET C4 PERF PL RUF ARG FBT DTZ N
TID`, bans `os.system` and `os.popen`, and ignores `S603` and `TRY003`; a file that holds test
cases also ignores `B023` and `PLR2004`. `bin/harness`, `githooks/pre-commit-wiki`,
`.githooks/pre-commit`, `.githooks/pre-push` and `launchagents/claude-autocommit` have no `.py`
suffix, and `pyproject.toml` names all five for ruff; the formatter and the `UP` family leave
`bin/harness` and `githooks/pre-commit-wiki`, whose syntax is a closed set of Python 3.0 forms,
and ruff reads `.githooks/pre-push` as Python 3.9. `basedpyright` checks `lib`, `hooks`,
`adapters`, `scripts` and `bin` in strict mode for Python 3.14; it reads only `.py` files, so it
checks none of the five.

The findings of the code that the profile met are recorded, not fixed: the table
`[tool.ruff.lint.extend-per-file-ignores]` of `pyproject.toml`, and the baseline
`.basedpyright/baseline.json`, which `basedpyright --writebaseline` writes. The lines that a
change adds or changes meet the profile with both records removed. A new module is in neither
record, and a module leaves a record when its last entry there goes. A change writes both records
again in the same commit as the fixes that shrink them: the table from `ruff check --output-format
json` with the table removed, and the baseline with `basedpyright --writebaseline`; a run of
`basedpyright` with fewer errors than the baseline writes it too.

The hooks and the guards import only the standard library: a case of `harness test`
(`lib/harness/strict.py`) parses each `.py` file below `hooks/` and the hook of the prose
repositories, `githooks/pre-commit-wiki`, and fails on an import of a module outside
`sys.stdlib_module_names`. `hooks/probe.py` may also import the harness's own package `harness`,
and the four tables in `hooks/guard/frontends/` the guard package `guard`.

The two tools are pinned in the `dev` group of `pyproject.toml` and locked in `uv.lock`, so every
machine and CI run the same versions. `harness install --apply` syncs the `dev` group into the
harness's Python environment only where `[setup]` of the profile sets `develop = true`; set it
on every machine where you commit to the harness.

## The Python rule

`rules/python-code.md` states the idioms of the strict profile for an agent, each with the tool
that enforces it, and loads on every `.py` file. This section gives the reason for each idiom.

- **One layout.** `ruff format` decides every line break, so a diff holds only changes of
  meaning, and no review argues about layout.
- **New code is strict.** The records admit the findings of the code that the profile met. A
  finding on a line that a change adds or changes is a defect that the records would hide, so the
  records only shrink.
- **A dataclass at every input boundary.** A `dict` from `json.loads` or `tomllib` has values of
  unknown type, and `basedpyright` cannot follow a key. A typed dataclass, filled where the input
  enters, turns a missing or mistyped key into one error at that place, not a `KeyError` or a
  wrong value three calls later.
- **`pathlib`.** One type for a path; `os.path` and string joins mix separators and lose the
  difference between a path and a text.
- **The form of `subprocess.run`.** Without `check=`, a failed program reads as a success unless
  the caller reads `returncode`; `check=` says which of the two the call means. `text=True` decodes
  the output once, so the code that reads it handles `str`, not `bytes`. A program outside the
  harness, such as `git`, `gh` or `node`, can wait on a prompt or the network, and a `timeout=`
  turns that wait into a failure that names it.
- **`HarnessError` for a reported failure.** The `harness` command catches it, prints its one line
  and exits 2, the status that the sweep checks for a missing precondition. A traceback tells the
  user nothing they can act on.
- **No blind `except`.** An `except Exception` also catches the bug that the code did not expect,
  and turns it into a wrong result.
- **The banned APIs, and the APIs that review keeps in their place.** `os.system` and `os.popen`
  run a command line through the shell, so its quoting decides what runs. `json.load` at each call
  site spreads the parsing of one kind of file over many functions. `shlex` splits as POSIX `sh`
  does, so a guard that decides on its tokens can allow a command that the real shell runs
  differently. A secret file that is written and then given mode `0600` is readable by others in
  between.
- **Standard-library-only hooks.** Claude Code and Antigravity run a hook on the interpreter of
  the harness's Python environment. The oh-my-pi frontend starts a hook as `python3`, and the
  OpenCode frontend by its `#!/usr/bin/env python3` line: both run it on the first `python3` of
  the `PATH`. There, a module that only the harness's environment holds does not import, and the
  hook fails each call that it guards.

## The pre-commit hook

`.githooks/pre-commit` runs the three checks of the strict profile on each commit:
`ruff format --check`, `ruff check` and `basedpyright`. It checks the commit, not the working
tree: it writes the index into a temporary directory with `git checkout-index` and runs the tools
there, so a change that is not staged neither fails nor passes a commit. The tools come from the
`bin/` of the harness's Python environment, which `bin/harness`'s own `environment_path` and
`interpreter` give, never from the `PATH`. All three run, and one that fails refuses the commit
with exit 1 and a line that names it. The formatter only checks: it names each staged file that it
would change, and the hook changes no file; run `ruff format` yourself, then stage again. An
environment without `ruff` or `basedpyright` refuses the commit with one line: set
`develop = true` in `[setup]` of the profile, then run `harness install --apply`. The cases of
`lib/harness/strict.py` run the hook in scratch repositories with stub tools.

## The pre-push hook

`.githooks/pre-push` is a Python program that imports only the standard library and runs on the
`python3` of the `PATH`. It gates a push to `main` with the leak checks and the suite. A push of any
other ref gets `harness leaks --commits` only, over the tree at the pushed commit and the commits
that the push sends (those that neither the remote SHA nor a branch of `origin` holds, so a
merge of a newer `main` sends none of its commits), so a pull request cannot bring a private
string to `main`; its gitleaks checks and its
suite run in CI. The hook tests the pushed commit, never the working tree: it clones the
repository with `git clone --shared` into a temporary directory under `$TMPDIR`, checks out the
pushed commit and runs there.

First come the two leak checks, before the suite, so a refused push costs seconds. They check
the tree at the pushed commit and every commit that the push brings to `main`
(`git rev-list <old>..<sha>`, as CI scans them; the whole history for a new `main`). So a leak
that a later commit deletes or renames still refuses the push. This is also true when a branch
on `origin` already holds the commit. `gitleaks` finds known secret patterns, such as tokens and
keys, and home paths, with `.gitleaks.toml`: gitleaks' default rules and a `home-path` rule that
allows only `/Users/me` and `/home/example`. `harness leaks --commits` finds the private strings
of the profile's `leak` list and the names of the research tree, in the files and their paths.
Both also search the message of each commit that the push sends, its subject and body:
`gitleaks git` reads no message, so the hook pipes the messages
(`git log --no-walk --format=%B`) into `gitleaks stdin`, and `harness leaks --commits` reports a
hit there as `<sha12> message:<n>`. The author and committer, a tag message and `git notes` are
not searched. Each gitleaks call passes `--redact` and `--ignore-gitleaks-allow`, so a
`gitleaks:allow` comment has no effect; a false positive is fixed in the text. The checks fail
closed. Each of these refuses the push with a one-line message: no `gitleaks` on `PATH`, a
`gitleaks` older than 8.21 or a version that it cannot read, no profile, an empty `leak` list, or
a check that fails; the hook skips none of them. **gitleaks 8.21 or later is a required local
tool** (`brew install gitleaks`); 8.19 added the `git`, `dir` and `stdin` commands, and 8.21 is
the first release with several allowlists per rule, `[[rules.allowlists]]`.

Then it runs `bin/harness test` once, with `python3`; `bin/harness` runs the suite on the
interpreter of the harness's Python environment. Then it runs the compile check
`<environment>/bin/python -m compileall -q lib hooks scripts adapters` on that interpreter, at the
path that `bin/harness` gives, then the three checks of [the strict profile](#the-strict-profile),
`ruff format --check`, `ruff check` and `basedpyright`, with the tools of that environment's
`bin/`, and `shellcheck -S warning` over the shell files. All three checks run, and one that fails
refuses the push; an environment without `ruff` or `basedpyright` refuses the push with one line
per tool that names `harness install --apply`. A push of a branch runs none of the three; CI runs
them.
Then, when `chezmoi` is on the `PATH`, it runs the kit's tests on `python3`:
`examples/dotfiles/tests/update-check.py`, `check-check.py`,
`driver-check.py`, `render-check.py` and `script-check.py`. All five run, and when one fails the
hook refuses the push with one line that names it. Without `chezmoi` it prints
`skip  chezmoi: not found; CI runs the kit's tests`.
Then it runs the Julia test files that the changed paths of the pushed range select: a change
to `scripts/mutate.jl` selects `scripts/run-tests-test.jl`, a change to `Project.toml` all nine,
and a change to `README.md` none. It prints each file's name and its usual time before it runs
it; `scripts/run-tests-test.jl` is silent for about 11 minutes. Without a `python3` of 3.14 or
later, the hook refuses the push. The hook parses as Python 3.9, so the `python3` of macOS runs
it up to that check and refuses the push with the hook's own line. A missing `shellcheck`,
`chezmoi` or `julia` prints one `skip` line, because CI runs them. A program that the hook cannot
start, such as an environment's interpreter that does not exist, prints one line and fails its
check, and the checks after it still run. A SIGTERM or a SIGHUP ends the hook and removes its
clone. Enable the hook once per checkout:

```bash
git config core.hooksPath .githooks
```

## CI

CI runs `.github/workflows/test.yml` on every push, pull request and manual dispatch:
`bin/harness test` and the compile check on Python 3.14 and the latest 3.x, the three checks of
the strict profile, `shellcheck` and `actionlint`. Its `python` job installs uv with
`astral-sh/setup-uv`, pinned by its commit SHA, and runs `uv sync --locked` into the environment
that `bin/harness` reads, on the job's Python;
the job on the latest 3.x has `continue-on-error`, so its failure warns and does not fail the
run. Its `empty-home` job runs `bin/harness test` once more on Python 3.14, with `HOME`
set to a new empty directory, so a case that needs a file of the runner's home fails there. Its
`strict` job runs `uv sync --locked` with the `dev` group into an environment of its own and runs
the three checks of the strict profile, `ruff format --check`, `ruff check` and `basedpyright`,
with that environment's tools, each as a step of its own. Its
`leaks` job runs gitleaks 8.30.1, a pinned tarball checked by its SHA256, with
`.gitleaks.toml` and `--redact`. A canary step first checks that gitleaks finds a synthetic token
and a synthetic home path, built at run time, and that the token is not in the log. Then the job
scans the pushed range (`before..sha`; for a new branch `origin/main..sha`, for a new `main`
the whole history; for a pull request `base..head`), the messages of that range through
`gitleaks stdin`, the checkout, and the templates rendered
with `examples/profile.toml`. CI has no profile, so the private strings are the hook's alone.
Its `dotfiles` job installs chezmoi 2.73.2 from its release tarball, checked by its SHA256, and
runs the five tests of the [dotfiles kit](dotfiles-command.md) in `examples/dotfiles/tests/`.
On a pull request, its `changelog` job runs
[`bin/harness changelog --check`](harness-command.md#changelog) against the pull request's base.
A branch writes its changelog entry as a fragment, `changelog.d/<branch>.md` with each `/` of the
branch name as `-`, not as an edit of `CHANGELOG.md`, so two open pull requests never change the
same lines; `changelog.d/README.md` gives the form. The job fails when the branch changes a file
below `lib/`, `hooks/`, `adapters/`, `bin/`, `scripts/`, `githooks/`, `agents/`, `skills/` or
`rules/` and adds no fragment. At a release, `harness changelog --apply` joins the fragments into
`## Unreleased`.
`.github/workflows/julia.yml` runs the nine Julia test files on Julia 1.13 when a
`.jl` file, `Project.toml`, `githooks/pre-commit`, `githooks/pre-push` or the workflow itself
changes.
`.github/workflows/docs.yml` builds the documentation site with VitePress when a file under
`docs/`, `agents/`, `skills/`, `examples/models.toml` or the workflow itself changes.
VitePress fails the build on a broken local link. On a push to `main`, the workflow also deploys
the site to the `gh-pages` branch.

## The documentation site

The site is a VitePress project in `docs/`, and its build needs Node.js, not Julia. The pages are
in `docs/src/`, and the configuration and the sidebar are in `docs/.vitepress/config.mts`.
`docs/package.json` pins the npm packages, and `docs/package-lock.json` pins their dependencies.
The home page, `docs/src/index.md`, is a landing page of its own, with VitePress's home layout;
it does not include the README. Build the site locally from `docs/`:

```bash
npm ci
npm run docs:build
npm run docs:check
```

The site is then in `docs/build/`; `npm run docs:dev` serves it with live reload. `docs/build/`
and `docs/node_modules/` are not tracked. A link from a page to a file outside `docs/src/` fails
the build; link to the file on GitHub instead. Link to a section of another page with the
heading's anchor: `[text](setup-macos.md#harness-install-apply)`. An anchor is the heading in lower
case, with each run of spaces and punctuation as one `-`. VitePress does not check an anchor, but
`npm run docs:check` does. It also checks that every page of the menu is in the sidebar, that each
page has the table rows of its source, that the home page has its two figures, the introduction
its three and the page `agentic-engineering` its four call graphs, that no edge of a figure crosses
another edge or passes through a box that is not its end, and that every colour of the figures has
a value for the dark theme. It finds the four walk-throughs by their titles, and checks each
animated figure: its SVG parses as XML, it holds no script, it loops, it stops under
`prefers-reduced-motion`, and its token and its steps keep their timing. It first runs the cases
of `docs/scripts/figures.test.mjs` and `docs/scripts/newcomer.test.mjs`. Last,
`docs/scripts/newcomer.mjs` checks the introductory pages for new readers, which it lists: the
glossary of `concepts.md` has one entry for each of its terms, the first use of a term on each of
these pages links to its entry, and none of these pages holds a `file:line`.

The figures are Vue components in `docs/.vitepress/theme/figures/`, which the build renders to
inline SVG, so a page shows them with JavaScript off. `FigCard`, `FigPanel` and `FigArrow` draw a
card with an icon, a group panel with a header band, and a right-angled arrow. The icons come
from the npm package `lucide`, and the build inlines them. Every colour, the font, the corner radii
and the line widths are custom properties in `docs/.vitepress/theme/figures.css`, with a value for
the light and the dark theme; a component names no colour itself. The overview and the flow figure
of the home page, and the two figures of the introduction, have a fixed layout in their components.

The call graphs of `agentic-engineering.md` are generated. A block with the info string
`calls <caller>`, or `calls` for every edge, holds the graph's `title:` and `desc:`, and the build
draws the graph there. `docs/.vitepress/theme/figures/calls.data.ts` reads
`docs/figures/calls.toml`, the frontmatter of `agents/` and `skills/`, and `examples/models.toml`
at build time, and `elkjs` lays out each graph. So a change of an agent's `effort:` changes the
figure with no other edit.

The four walk-throughs are animated figures of the component `WalkThrough`. Each one has one data
file `docs/figures/walkthrough-<name>.toml`: its title, its boxes on a grid, its edges with the
`file:line` that states each step, and the order of the steps. A box of an agent or a skill takes
its model and effort from the same sources as the call graphs.
`docs/.vitepress/theme/figures/walkthroughs.data.ts` lays out each walk-through at build time and
writes its animation as CSS in the figure. `harness test` checks each data file: each agent and
skill exists, and each cited line exists.

The pages in `docs/src/components/` describe each component: one page for each kind, and one
level-2 section for each component, whose heading names it in backticks. `lib/harness/docs.py`
says which files are the components of each page. Its cases in `harness test` fail when a
component has no heading, when a heading names something that is no component of its page, and
when a tool of the tables of `dependencies.md` has no heading on that page, or a heading there
names something that is no tool of the tables. So a new agent, skill, rule, hook or script needs
its section in the same change.
