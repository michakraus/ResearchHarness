---
paths: ["**/CHANGELOG.md"]
description: How an entry is written in this tree, why a changelog is never corrected, and what does not belong in one at all.
---

# Writing a CHANGELOG entry

Every repository under `~/Research` carries a `CHANGELOG.md`. If one does not, create it rather
than working without. This is the one place history belongs: comments and prose describe the
current state, the changelog records how it got there.

- **Add the entry in the same change that earns it**, not in a sweep afterwards.
- Write **what changed and why it matters to someone using this**, not which files were touched.
- **Name the gaps.** An honest "these versions were never written up" beats a silently incomplete
  record.

Each tree's `CLAUDE.md` gives the shape for that kind of work — they differ, because a manuscript
has no releases. The **`changelog-scribe`** agent writes the entry in the right convention.

## Traps

**Write the entry from the artefact, not from the plan.** A claim of absence — "this is not
included" — is exactly what a passing test suite cannot contradict. Grep the module before you
write it down. In an entry a sub-agent drafted, `ls` or grep every path, name and count.

**An entry reads as one release, not one commit.** Something true per commit can be false per
branch, and false again per merge. A file count is the case that catches people out: re-derive it
against the merge result, with `git merge-tree --write-tree origin/main <head>` and then
`git ls-tree -r --name-only <tree> -- <dir>`. When the count is wrong, merge `main` into the topic
branch, with no force-push, and re-run the affected gate: the merged combination never ran in CI.
Before you open the PR, re-read every entry the branch adds against `git diff --stat <base>...HEAD`.
Prefer entries that describe the end state.

**"Each new test fails before the fix" is a per-test claim.** Run each test against `origin/main`,
never against a mid-session draft of the fix. Otherwise name which tests reproduce the defect and
which are regression guards.

**In an open `[Unreleased]` section, a before/after column names the base commit**, not the last
tag. The base already carries that release's earlier work. Say which half of the script produced
the baseline column, and why the shipped script cannot produce it whole.

## A changelog is never corrected

An entry states what was true when it was written. Rewriting it to match the present makes it
false. When a path moves or a fact is superseded, add a new entry saying so; leave the old one
alone. The same holds for any sentence elsewhere that describes a past move or a past measurement.

The rule starts at the release. An entry that is not released yet, in an open pull request or in
the `[Unreleased]` section, is not history: correct it until it is true for its release.

## An open question is not an entry

A changelog records what changed. A known defect, a deferred fix and a decision still to take are
statements about the present. A known defect and a deferred fix go to the repository's
`KNOWN_ISSUES.md`, in every repository under `~/Research`, not to its issue tracker. A body of work
goes to a `Tasks/` file. Anything else goes to the issue tracker of a repository on GitHub. A
repository on GitLab gets no issue: a single decision for it goes to `Tasks/Decisions pending.md`.

The two rules compound where a standing note sits in a changelog anyway. The rule above then
applies to text that is not history: the next measurement lands as a correction stacked under the
sentence it corrects, and the section grows a paragraph on every visit. Move such a note out and
write it once. A standing note such as a `> [!NOTE]` is deleted or made true; it never stays as it
is.
