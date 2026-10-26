- **A branch adds its changelog entry as a fragment in `changelog.d/`, not as an edit of
  `CHANGELOG.md`.** Two open pull requests that each added an entry at the top of `## Unreleased`
  conflicted there, and each merge forced a rebase of the other branch. A fragment is a file of its
  own, `changelog.d/<branch name with / as ->.md`, so two branches no longer touch the same lines;
  `changelog.d/README.md` gives the form. `harness changelog` prints the `## Unreleased` block that
  the fragments make, newest first by the date of the commit that added each, and exits 1 when
  there is one; `harness changelog --apply` writes the block at the top of `## Unreleased` and
  deletes the fragments, at a release. An empty fragment, one of whitespace, one with a carriage
  return or one that is not UTF-8 stops both with exit 2. On a pull request, the new `changelog`
  job of CI runs `harness changelog --check` against the base: it fails when the branch changes a
  file below `lib/`, `hooks/`, `adapters/`, `bin/`, `scripts/`, `githooks/`, `agents/`, `skills/`
  or `rules/` and adds no fragment. `rules/changelog.md` says that a repository with a
  `changelog.d/` takes a fragment.
