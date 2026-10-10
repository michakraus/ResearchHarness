# Git hooks and workflows

A git hook is a program that git runs at a fixed point, for example before a commit or before a
push. When the hook exits with a status other than 0, git refuses the commit or the push. A
GitHub Actions workflow is a file that tells GitHub which jobs to run on a push or a pull
request.

The files of this page are in `githooks/` and `githooks/workflows/`. They are templates for the
Julia repositories of the research tree, and a few scripts beside them. Two verbs of the
`harness` command install the templates into every repository below `Packages/` and
`Experiments/` (see
[The verbs for the whole research tree](../daily-use.md#the-verbs-for-the-whole-research-tree)):

- `harness githooks --apply` copies `pre-commit`, `pre-push` and `scripts/test-layout.jl` into
  `.githooks/` of each repository, and sets `core.hooksPath` there.
- `harness workflows --apply` copies the files of `githooks/workflows/` into each repository that
  has a `Project.toml`.

`harness wiki-lint-hook --apply` installs `pre-commit-wiki` into the prose repositories. Each copy
is byte-identical to its template and is a tracked file in the repository. Edit the template,
then install again; never edit a copy. The other scripts of this page run from the checkout.
This repository has a pre-push hook of its own, `.githooks/pre-push`; it is not a template, and
[Development](../development.md) describes it.

## `pre-commit`

`pre-commit` is the shared pre-commit hook of the Julia repositories. It runs these stages:

| stage | what it checks | on a failure |
|:--|:--|:--|
| 0 | `test-layout.jl --check`, on a commit that touches `test/` | blocks |
| 1 | JuliaFormatter, with the `.JuliaFormatter.toml` of the repository | blocks |
| 2 | `fatou lint`, with a limit of 60 s where `timeout` exists | warns only |
| 2.5 | each file is in Unicode NFC | blocks |
| 3 | `using <package>` loads, for a repository with a package name | blocks |

Stages 1 to 3 run on the staged `.jl` files only. Stage 0 reads `.githooks/test-layout.jl`, which
`harness githooks` installs beside the hook; a missing copy blocks the commit. Stage 0 checks the
working tree, not the index. The lint only warns, because `fatou lint` gives false findings. The
NFC stage does not change a file; run `nfc.jl --apply` to fix one. A commit with no
staged `.jl` file and no change below `test/` passes with no check. `git commit --no-verify` skips
the hook.

## `pre-push`

`pre-push` is the shared pre-push hook of the Julia repositories. It runs the full test suite,
but only on a push to `main` or `master`. A push to another branch passes at once, and CI tests
it.

For a package, the hook runs `Pkg.test("<package>")` with `--check-bounds=auto`. For a repository
with no package name, it runs `test/runtests.jl`. With neither, it runs nothing and passes. A
failure refuses the push.

The suite takes 10 to 30 minutes and prints nothing until it ends. That is not a hang. When you
stop the hook, stop its Julia process too. `harness push-all` runs this hook in each repository.

## `pre-commit-wiki`

`pre-commit-wiki` is the pre-commit hook of the five prose repositories: `Knowledge`,
`Environment`, `Tasks`, `Bibliography` and `Library`. `harness wiki-lint-hook --apply` installs it
into each as `.githooks/pre-commit`, and sets `core.hooksPath`.

The hook runs `scripts/wiki-lint.jl --quiet` from `$RESEARCH_ROOT/Harness`, else
`~/Research/Harness`, over all five trees. An ERROR in any tree blocks the commit, also an ERROR
in another repository: the trees link to each other, so an edit here can break a link there. A
warning does not block. A missing lint script, or no `julia` on the `PATH`, blocks too. The run
takes about three seconds. No Julia repository uses this hook; it uses `pre-commit`.

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
valid UTF-8. Exit 0 when each checked file is NFC; 1 when one is not, or when a named file is
not valid UTF-8. With `--apply`, exit 0 after the rewrite.

Normalisation can change a string literal. Before `--apply`, check what reads such a literal, for
example a doctest. The `pre-commit` hook has its own copy of the check, and names this script for
the fix. The rule `generated-hooks-and-workflows` and the agent `julia-pr-shepherd` tell an agent
to run it.

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
file. Run it on Julia 1.11 or later, because only there are the ownership checks authoritative.
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

It sets a threshold of 1 % on both the project status and the patch status. Without it, Codecov
fails a pull request for any decrease of the coverage. So a real regression still fails, and a
small drift does not. The coverage comes from one entry of the matrix of `CI.yml`.

## `workflows/dependabot.yml`

`workflows/dependabot.yml` is the Dependabot configuration. `harness workflows` copies it to
`.github/dependabot.yml` of each repository.

Dependabot proposes, each week, a raise of the `[compat]` entries of the root `Project.toml`. It
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
reports the repositories whose `doctest` job skips itself. Exit 1 when a repository deviates. It
reads the profile for `docs_exceptions` and `docs_additions`.

Run it after `harness workflows --apply`, and before a change to CI. `harness ci-protection
--apply` refuses to run when it fails. The rule `generated-hooks-and-workflows` and the agent
`ci-triage` name it.
