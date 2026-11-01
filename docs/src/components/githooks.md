# Git hooks and workflows

A git hook is a program that git runs at a fixed point, for example before a commit or before a
push. When the hook exits with a status other than 0, git refuses the commit or the push. A
GitHub Actions workflow is a file that tells GitHub which jobs to run on a push or a pull
request.

The files of this page are in `githooks/` and `githooks/workflows/`. Most of them are templates
for the Julia repositories of the research tree; the others are scripts beside them. Two
subcommands of the `harness` command install the templates into every repository below
`Packages/` and `Experiments/` (see
[Clone, sync and trust](../research-tree.md#clone-sync-and-trust)):

- `harness githooks --apply` copies `pre-commit`, `pre-commit.jl`, `pre-push`, `pre-push.jl`
  and `scripts/test-layout.jl` into `.githooks/` of each repository, and sets `core.hooksPath`
  there.
- `harness workflows --apply` copies the files of `githooks/workflows/` into each repository that
  has a `Project.toml`.

`harness wiki-lint-hook --apply` installs `pre-commit-wiki` into the prose repositories. Each copy
is byte-identical to its template and is a tracked file in the repository. Edit the template,
then install again; never edit a copy. The other scripts of this page run from the checkout.
This repository has a pre-commit and a pre-push hook of its own, `.githooks/pre-commit` and
`.githooks/pre-push`; they are not templates, and [Development](../development.md) describes them.

## `pre-commit`, `pre-commit.jl` and `pre-commit-test.jl`

`pre-commit` is the shared pre-commit hook of the Julia repositories. It is a short bash
launcher that starts `pre-commit.jl` beside it, in one Julia process. A commit with no staged
`.jl` path, a deletion included, and no change below `test/` passes without starting `julia`.
Without `julia` on the `PATH`, any other commit is refused with
`pre-commit: julia is not on the PATH.` The program runs these stages:

| stage | what it checks | on a failure |
|:--|:--|:--|
| 0 | the `violations` of `test-layout.jl`, on a commit that touches `test/` | blocks |
| 1 | JuliaFormatter 2.14 or later, with the `.JuliaFormatter.toml` of the repository | blocks |
| 2 | `fatou lint`, with a limit of 60 s | warns only |
| 2.5 | each file is in Unicode NFC | blocks |
| 3 | `using <package>` loads, with a limit of 600 s, for a repository with a package name | blocks |

Stages 1 to 2.5 run on the staged `.jl` files only, a renamed file under its new name and a file
that became a symlink too; a path with non-ASCII characters is read as it is, not in git's quoted
form. A staged `.jl` path that is not a file, such as a symlink to a missing file or to a
directory, is refused with one line that names it, before any stage runs. Stage 3 runs when a
`.jl` file is staged, and also when only the deletion of one is: a deletion can break an
`include`. Stage 1 checks each file on its own: a file that does not parse fails stage 1, with
the first line of its error on stderr, and the other files are still checked. Stage 1 loads
JuliaFormatter from the harness's Julia environment, which pins 2.14, and refuses an older
release with one line that names its version, marking every staged file; JuliaFormatter 2.14
supports Julia 1.10 and later. Stage 1 has no time limit (K130 of `KNOWN_ISSUES.md`). Stage 0 reads
`.githooks/test-layout.jl`, which `harness githooks` installs beside the hook; a missing copy
blocks the commit. Every stage reads the working tree, not the index (K128). The lint only
warns, because `fatou lint` reports false positives; without `fatou` on the `PATH`, or with a
`fatou` that cannot start, the stage prints one line and is skipped. The NFC stage does not
change a file; run `nfc.jl --apply` to fix one. Stage 3 loads the package in a child process, in
the environment of the repository, so that the versions of JuliaFormatter's dependencies in the
hook's own process do not change what the package loads. The package name comes from
`Project.toml`, read as TOML; a `Project.toml` that does not parse refuses the commit with one
line. The lint stage and the load test run in a process group of their own: when the limit runs
out, the hook sends the group SIGTERM, and SIGKILL 5 s later, and does not wait for the output
of a process that left the group. When you interrupt the hook, it kills that group on its way
out. A commit with no staged `.jl` path and no change below `test/` passes with no check.
`git commit --no-verify` skips the hook.

`pre-commit-test.jl` runs both hooks, unchanged, in fixture package repositories
(`julia --startup-file=no pre-commit-test.jl`). For `pre-commit`: a formatted file, also under a
non-ASCII name, passes, and a misformatted file, a renamed misformatted file, a file that does not
parse, a file that does not load, a file that is not NFC and a change below `test/` without
`test-layout.jl` or out of its layout are refused, and so is a JuliaFormatter older than 2.14; a
file that does not parse beside a formatted one is listed alone; a staged symlink to a missing
file or to a directory is refused with one line; a `Project.toml` with an indented, single-quoted
name runs the load test, and one that does not parse is refused; a commit that only deletes a
`.jl` file runs the load test; without `julia`, or with a `julia` that cannot start, a commit with
no `.jl` file and no `test/` path passes; without `julia`, any other commit, a `.jl` file that
became a symlink too, is refused; a missing `fatou`, a `fatou` that cannot start, and the findings
of `fatou`, give their lines; a commit of one `.jl` file starts `julia` from the `PATH` once; an
interrupted commit stops its load test. It checks the time limits of the lint stage and the load
test, also for a child that holds the output and for a process that leaves the group, and that
`pre-commit.jl` and `pre-push.jl` are in SciML style. For `pre-push` it checks each case of the
gate and the suite. CI runs it on Linux.

## `pre-push` and `pre-push.jl`

`pre-push` is the shared pre-push hook of the Julia repositories. Like `pre-commit`, it is a bash
launcher that starts `pre-push.jl` beside it, and passes it git's ref lines on stdin. A push
that updates no `main` or `master` passes without starting `julia`. Without `julia` on the
`PATH`, a push of either is refused with `pre-push: julia is not on the PATH.` The program runs
the full test suite, but only on a push to `main` or `master`. A push to another branch passes at
once, and CI tests it.

For a package, the hook runs `Pkg.test("<package>")` with `--check-bounds=auto`, and passes the
flag to the test process through `julia_args`: up to Julia 1.12, `Pkg.test` gives the test
process `--check-bounds=yes` whatever the calling process uses. For a repository
with no package name, it runs `test/runtests.jl`. With neither, it runs nothing and passes. The
package name comes from `Project.toml`, read as TOML; a `Project.toml` that does not parse
refuses the push. A failure of the suite refuses the push with
`ERROR — tests must pass before pushing to main or master.`

The suite takes 10 to 30 minutes and prints nothing until it ends. That is not a hang. The suite
runs in a process group of its own. When you interrupt the hook with Ctrl-C or `SIGINT`, it sends
the interrupt to that group, waits for the suite to stop, and exits with status 130. When the
suite still runs 30 s after the interrupt, the hook sends SIGKILL to the group. A second
interrupt does not end the wait.
`harness repos push` runs this hook in each repository.

## `pre-commit-wiki`

`pre-commit-wiki` is the pre-commit hook of the four prose repositories: `Knowledge`,
`Environment`, `Tasks` and `Library`. `harness wiki-lint-hook --apply` installs it
into each as `.githooks/pre-commit`, and sets `core.hooksPath`.

The hook is a Python script that imports only the standard library, in the closed set of Python
3.0 forms of `bin/harness`, so an old `python3` prints the version refusal of `bin/harness`
instead of a syntax error. It runs `harness wiki-lint --quiet` with `bin/harness` of
`$RESEARCH_ROOT/Harness`, or of `~/Research/Harness` if `RESEARCH_ROOT` is not set, over all four
trees. An ERROR in any tree blocks the commit, even an ERROR in another repository: the trees
link to each other, so an edit here can break a link there. A warning does not block. A missing
`bin/harness` blocks too. The lint takes about a second.

In a repository whose staged `pyproject.toml` holds a `[tool.ruff]` table, the hook also runs
`ruff format --check`, `ruff check` and `basedpyright` on the staged Python files and the tools'
configuration, which it writes into a temporary directory. The tools come from the `bin/` of the
harness's Python environment; where the environment lacks one, the hook refuses the commit with
one line that names `harness install --apply`. Every check runs, and the hook refuses the commit
when one fails. No Julia repository uses this hook; it uses `pre-commit`.

## `nfc.jl`

`nfc.jl` reports or applies Unicode NFC normalisation. In NFC, a letter such as `ẋ` is one code
point, not a base letter and a combining mark. Julia reads both forms as the same name, but a
byte search for one form does not find the other.

```bash
julia --startup-file=no nfc.jl                     # check every tracked source file here
julia --startup-file=no nfc.jl --apply             # rewrite them
julia --startup-file=no nfc.jl a.jl b.md           # check just these paths
julia --startup-file=no nfc.jl --apply src/x.jl    # rewrite just this one
```

With no path, it checks every tracked file of the repository in the current directory that is
valid UTF-8. The exit status is 0 when each checked file is NFC, and 1 when one is not or when a
named file is not valid UTF-8. With `--apply`, the exit status is 0 after the rewrite.

Normalisation can change a string literal. Before `--apply`, check what reads such a literal, for
example a doctest. The `pre-commit` hook has its own copy of the check, in `pre-commit.jl`, and
names this script for the fix. The rule `generated-hooks-and-workflows` and the agent
`julia-pr-shepherd` tell an agent to run it.

## `explicit-imports.jl`

`explicit-imports.jl` runs ExplicitImports.jl on a package and prints what it finds. It loads the
package, so it sees the real bindings. `fatou lint` cannot do this, because its `unused-import`
rule does not follow `include`.

```bash
julia --project=<pkg> explicit-imports.jl <PkgName>
```

It prints the implicit imports, the names that a `using` brings in without a name list. Then it
runs four checks and prints `ok` or `FAIL` for each: stale explicit imports, explicit imports
through their owner, self-qualified access, and qualified access through the owner. It changes no
file. Run it on Julia 1.11 or later, because the ownership checks are reliable only on that
version.
No hook, skill or agent calls it.

## `format-tree.jl`

`format-tree.jl` runs JuliaFormatter over every tracked `.jl` file of the repositories below
`Packages/` and `Experiments/`.

```bash
julia format-tree.jl            # report only, changes nothing
julia format-tree.jl --apply    # rewrite files in place
```

It formats each repository with its own `.JuliaFormatter.toml`, and skips a repository with no
such file. It skips the directories `prototyping/`, `legacy/` and `obsolete/`. It works on one
file at a time, and writes the name of each file to a marker file before it starts.

`harness format` runs this script. When JuliaFormatter crashes the process on a file, `harness
format` moves that file to a skip list and runs the script again, until it ends cleanly. Use
`harness format`, not the script, for a run over the tree. For the files of one change, run
JuliaFormatter on those files only.

## `release-notes.jl` and `release-notes-test.jl`

`release-notes.jl` builds the body of the `@JuliaRegistrator` comment from the `CHANGELOG.md` of
a package. It refuses a breaking release whose notes have no breaking-changes section, because
the registry then blocks the release.

```bash
julia --startup-file=no release-notes.jl [package-dir] > notes.json
gh api repos/<owner>/<repo>/commits/<SHA>/comments --input notes.json
```

The version comes from `Project.toml`. The notes are the `CHANGELOG.md` section of that version.
The JSON goes to stdout. On a failure, the script writes the reason to stderr, nothing to stdout,
and exits 1. It fails when the section is missing or empty, or when a breaking release has no
heading that contains "breaking". The first version of a package is never breaking. The skill
`julia-release` runs it.

`release-notes-test.jl` checks the script on fixtures, among them the two cases that must fail
with an empty stdout.

```bash
julia --startup-file=no release-notes-test.jl
```

## `workflows/CI.yml`

`workflows/CI.yml` is the CI workflow. `harness workflows` copies it to
`.github/workflows/CI.yml` of each repository. It runs on a push to `main` or `master`, on a tag,
on a pull request and by hand. It reads the package name from `Project.toml` at run time, so one
file fits every repository.

| job | what it runs |
|:--|:--|
| `test` | the tests on Julia `min` and `1`, on Ubuntu, macOS and Windows; `pre` and `nightly` on Ubuntu, as information only |
| `downgrade` | the tests with each direct dependency at the lower bound of its `[compat]` entry, on Julia `min`; information only |
| `doctest` | `doctest` of the package on Julia `1` on Ubuntu, where `docs/Project.toml` exists |

The matrix names Julia versions by alias, `min` and `1`, so the names of the checks stay the same
in every repository. Branch protection needs those fixed names. Only the entry of Julia `1` on
Ubuntu measures coverage and sends it to Codecov. A repository that needs another job gets its
own extra workflow file, not an edit of this one.

## `workflows/Documenter.yml`

`workflows/Documenter.yml` is the documentation workflow. It builds the documentation with
`docs/make.jl` and deploys it. `harness workflows` copies it to `.github/workflows/Documenter.yml`
of each repository that has a tracked `docs/make.jl`.

It does not go into a repository that the profile key `docs_exceptions` or `docs_additions`
names. Such a repository keeps its own file: its documentation is a pipeline of several jobs, or
it needs an extra step. The doctests do not run here; the `doctest` job of `CI.yml` runs them. It
runs on the same events as `CI.yml`, on Ubuntu with Julia `1`.

## `workflows/TagBot.yml`

`workflows/TagBot.yml` runs the action `JuliaRegistries/TagBot` for a registered package.
`harness workflows` copies it to `.github/workflows/TagBot.yml` of each package below
`Packages/`, and not into an experiment.

It runs on a comment that the registry posts as `JuliaTagBot`, and by hand, with the input
`lookback`. An `if:`
condition stops it on every other issue comment.

## `workflows/codecov.yml`

`workflows/codecov.yml` is the Codecov configuration. `harness workflows` copies it to
`codecov.yml` at the root of each repository.

It sets a threshold of 1 % on both the project status and the patch status. Without the
threshold, Codecov fails a pull request for any decrease of the coverage. With it, a real
regression still fails, but a small drift does not. The coverage comes from one entry of the
matrix of `CI.yml`.

## `workflows/dependabot.yml`

`workflows/dependabot.yml` is the Dependabot configuration. `harness workflows` copies it to
`.github/dependabot.yml` of each repository.

Each week, Dependabot proposes to raise the `[compat]` bounds of the root `Project.toml`. It
does not update `test/Project.toml`, `docs/Project.toml` or the GitHub actions. Change the version
of an action in the templates, so that the copies stay identical. The configuration ignores the
standard libraries, whose bound stays at "1".

## `verify-workflows.jl`

`verify-workflows.jl` checks that the workflows of every repository below `Packages/` and
`Experiments/` match the templates.

```bash
julia verify-workflows.jl            # report
julia verify-workflows.jl --quiet    # only deviations and the summary
```

It checks these points:

1. `CI.yml`, `dependabot.yml`, `TagBot.yml` and `codecov.yml` are byte-identical to the
   templates, in the working tree. `TagBot.yml` must be absent in an experiment.
2. The same files on the default branch, for a repository that is on another branch.
3. The job names of `CI.yml` are the names of the required checks.
4. No `Register.yml`, `Documentation.yml`, `CompatHelper.yml` or other forbidden file exists.
5. Each `uses:` names the expected major version of its action.

It also checks that a repository of `docs_additions` keeps the body of `Documenter.yml`. It
reports the repositories whose `doctest` job skips itself. It exits with status 1 when a
repository deviates. It
reads the profile for `docs_exceptions` and `docs_additions`.

Run it after `harness workflows --apply`, and before a change to CI. `harness ci-protection
--apply` refuses to run when it fails. The rule `generated-hooks-and-workflows` and the agent
`ci-triage` name it.
