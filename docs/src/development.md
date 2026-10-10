# Development

## Tests

`harness test` runs three sets of cases and prints one summary line; it exits 1 when any case
is wrong. First each module's own cases; then the hook probe, `hooks/probe.py`, which runs every
Python hook with the same interpreter on a fixture `HOME`; then the contract sweep,
`lib/harness/sweep.py`, which runs the dry run of every verb except `format`, `ci-protection` and
`skill-triggers` on a fixture `HOME` and research root; the cases of `skill-triggers` run its
dry run and its `--apply` on a fake `claude`. The sweep checks the contract of
[the `harness` command](harness-command.md): a dry run changes no
file, a missing precondition exits 2 with one line, and for the five verbs it applies, a dry run
after `--apply` has nothing to do. Each fixture lives in a temporary directory, so the cases need
nothing from the machine's own `HOME`.

`harness test` runs the Python cases: each module's own cases, the hook probe and the contract
sweep, as described above. It needs nothing from the machine's own `HOME`, and it passes wherever
the checkout lies, below `/tmp/` or `$TMPDIR` too. The hook probe loads `adapters/omp/guards.ts`
and the OpenCode plugins `adapters/opencode/plugins/*.ts` under `node`, so `node` must be on
`PATH`; a missing `node` is a wrong case.

## The pre-push hook

`.githooks/pre-push` gates a push to `main`; a push to any other branch runs nothing and goes to
CI. The hook tests the pushed commit, never the working tree: it clones the repository with
`git clone --shared` into a temporary directory under `$TMPDIR`, checks out the pushed commit
and runs there.

First come the two leak checks, before the suite, so a refused push costs seconds. They check
the tree at the pushed commit and every commit that the push sends (`git rev-list <sha> --not
--remotes=origin`), so a leak that a later commit removes or renames away still refuses the
push. `gitleaks` finds the public shapes, tokens, keys and home paths, with `.gitleaks.toml`:
gitleaks' default rules and a `home-path` rule that allows only `/Users/me` and `/home/example`.
`harness leaks --commits` finds the private strings of the profile's `leak` list and the names
of the research tree, in the files and their paths. Both also search the message of each commit
that the push sends, its subject and body: `gitleaks git` reads no message, so the hook pipes
the messages (`git log --no-walk --format=%B`) into `gitleaks stdin`, and `harness leaks
--commits` reports a hit there as `<sha12> message:<n>`. The author and committer, a tag message
and `git notes` are not searched. Each gitleaks call passes `--redact` and
`--ignore-gitleaks-allow`, so a `gitleaks:allow` comment has no effect; a false positive is
fixed in the text. The checks fail closed: no `gitleaks` on `PATH`, a `gitleaks` older than 8.21
or a version it cannot read, no profile, an empty `leak` list, or a check that fails each refuse
the push with one line. None is a skip. **gitleaks 8.21 or later is a required local tool**
(`brew install gitleaks`); 8.19 added the `git`, `dir` and `stdin` commands, and 8.21 is the
first release with several allowlists per rule, `[[rules.allowlists]]`.

Then it runs `bin/harness test` on `python3` and on `python3.11`, the compile check
`python3.11 -m compileall -q lib hooks scripts adapters`, and `shellcheck -S warning` over the
shell files.
Then it runs the Julia test files that the changed paths of the pushed range select: a change
to `scripts/mutate.jl` selects `scripts/run-tests-test.jl`, a change to `Project.toml` all five,
and a change to `README.md` none. It prints each file's name and its usual time before it runs
it; `scripts/run-tests-test.jl` is silent for about 11 minutes. No `python3` of 3.11 or later
refuses the push. A missing `python3.11`, `shellcheck` or `julia` prints one `skip` line, because
CI runs them. Enable the hook once per checkout:

```bash
git config core.hooksPath .githooks
```

## CI

CI runs `.github/workflows/test.yml` on every push, pull request and manual dispatch:
`bin/harness test` and the compile check on Python 3.11 and the latest 3.x, `shellcheck` and
`actionlint`. Its `leaks` job runs gitleaks 8.30.1, a pinned tarball checked by its SHA256, with
`.gitleaks.toml` and `--redact`. A canary step first checks that gitleaks finds a synthetic token
and a synthetic home path, built at run time, and that the token is not in the log. Then the job
scans the pushed range (`before..sha`; for a new branch `origin/main..sha`, for a new `main`
the whole history; for a pull request `base..head`), the messages of that range through
`gitleaks stdin`, the checkout, and the templates rendered
with `examples/profile.toml`. CI has no profile, so the private strings are the hook's alone.
`.github/workflows/julia.yml` runs the five Julia test files on Julia 1.13 when a
`.jl` file, `Project.toml` or the workflow itself changes.
`.github/workflows/docs.yml` builds the documentation site with VitePress when the README, a file
under `docs/`, `agents/`, `skills/`, `examples/models.toml` or the workflow itself changes.
VitePress fails the build on a broken local link. On a push to `main`, the workflow also deploys
the site to the `gh-pages` branch.

## The documentation site

The site is a VitePress project in `docs/`, and its build needs Node.js, not Julia. The pages are
in `docs/src/`, and the configuration and the sidebar are in `docs/.vitepress/config.mts`.
`docs/package.json` pins the npm packages, and `docs/package-lock.json` pins their dependencies.
The home page, `docs/src/index.md`, includes the README, and the build changes the README's links
into `docs/src/` to work between pages. Build the site locally from `docs/`:

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
page has the table rows of its source, and that the page `agents-at-work` has its four call graphs.

The call graphs of `agents-at-work.md` are Mermaid diagrams. A block with the info string
`calls <caller>`, or `calls` for every edge, holds the graph's `accTitle:` and `accDescr:`, and
`docs/.vitepress/calls.mjs` adds the nodes and the edges at build time, from
`docs/figures/calls.toml`, the frontmatter of `agents/` and `skills/`, and
`examples/models.toml`. So a change of an agent's `effort:` changes the figure with no other edit.
The graphs follow the light and dark theme of the site.

The pages in `docs/src/components/` describe each component: one page for each kind, and one
level-2 section for each component, whose heading names it in backticks. `lib/harness/docs.py`
says which files are the components of each page. Its cases in `harness test` fail when a
component has no heading, when a heading names something that is no component of its page, and
when a tool of the README's dependency tables has no heading in `tools.md`. So a new agent,
skill, rule, hook or script needs its section in the same change.
