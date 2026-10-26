# Changelog fragments

Each branch adds its changelog entry here, as a file of its own, not as an edit of
`CHANGELOG.md`. The file name is the branch name with each `/` as `-` and `.md` added: the branch
`topic/part-a` writes `changelog.d/topic-part-a.md`.

The file holds one entry in the form of `CHANGELOG.md`: one bullet that opens with a bold lead
sentence.

    - **What changed, in one sentence.** Why it matters to someone who uses it.

`harness changelog` prints the `## Unreleased` block that the fragments make, newest first, and
`harness changelog --apply` writes it into `CHANGELOG.md` at a release and deletes the fragments.
On a pull request, CI runs `harness changelog --check`: a branch that changes code adds a fragment.
