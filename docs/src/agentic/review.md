# Review and pull requests

A change ends in a pull request, and a pull request ends in a merge. Between the two, the change
gets a last check of its diff, a review by a context that did not write it, CI on its head, and
your decision. This page describes the steps from a finished branch to a merged pull request, the
agents of each step, and the rule of who merges.

## Before the pull request

A builder that has a PASS does not open the pull request at once. It first runs
[`julia-branch-verifier`](../components/agents.md#julia-branch-verifier) on the branch. The
verifier finds the diff against the merge base and runs a pass of seven points on the diff only,
for example correctness, type piracy and ambiguities with the
[dispatch delta](static-checks.md#what-a-change-adds-to-the-method-table), type instability,
avoidable allocations, stale comments, and history outside the `CHANGELOG.md`. It fixes what it can, and returns three things:

- a verdict;
- the exact paths to stage, so that the builder commits nothing that it did not change;
- a block for the body of the pull request, with what the verifier checked.

A finding counts against the branch only when its source is in the changed lines, or when the
branch made it wrong. A finding that the branch does not cause is reported, not fixed, so the diff
holds the change and nothing else. A finding that the branch causes and the verifier cannot fix
stops the pull request until it is fixed and the verifier has run again.

The verifier does not run the suite: the loop ran it beside the critic. For a missing changelog
entry it names [`changelog-scribe`](../components/agents.md#changelog-scribe), which writes the
entry in the convention of the repository.

## The text of a pull request

A pull request is read on GitHub, by a reader who does not have your machine. So its text:

- holds no local path, such as a path in your home directory or a task file;
- names an issue with "relates to", never with a word that closes it on the merge, such as
  "fixes" or "closes", unless the pull request is to close it;
- holds the verifier's block, and the evidence of each clause.

`gh pr create` needs `-R <owner>/<repo>`: the [guard](../safeguards/guard-hooks.md#the-gh-pr-create-check)
refuses one that names no repository, and asks for one outside your own organisations.

## The review

A pull request that the loop opened has passed a blind critic already. A pull request from
elsewhere, or one that you want reviewed again, goes to the review agents:

| agent or command | does |
|:--|:--|
| [`julia-pr-reviewer`](../components/agents.md#julia-pr-reviewer) | reviews the pull request in a worktree at its head, measures each figure that it claims again, reads the CI jobs, and posts the review. It edits no code |
| [`julia-pr-shepherd`](../components/agents.md#julia-pr-shepherd) | has `julia-pr-reviewer` review, fixes the findings of severity `blocker`, `bug` and `correctness-risk`, pushes, and answers each finding in one comment. It makes one fix round and never merges |
| [`/review-pr`](../components/commands.md#review-pr) | starts the shepherd, or with `nofix` the reviewer, and waits for the CI runs of the push |

The review is blind in the same sense as the critic: the reviewer treats the author's description
of the change as a claim to check, not as a fact. The shepherd does not wait for CI. Its report
names the runs of its push, and its caller waits for them, because a sub-agent that waits for
minutes must write its whole context to the cache again.

### Comments of a review bot

Where a review bot such as CodeRabbit reviews the pull request, `build-part` answers each of its
comments before the merge. A comment that names a defect goes to a fix round, like a critic's
blocking defect. A comment that is wrong, or a matter of taste, is rejected with the reason. Each
answer goes into the comment's thread: `fixed in <sha>` or `rejected: <reason>`.

## Who merges

**No agent merges a pull request that its own session opened or pushed to.** A session that
writes a change, opens its pull request and merges it is a direct push to `main` with extra steps:
no second context has said yes. The line is authorship, not time: a sub-agent that the authoring
session spawned is on the author's side.

The harness holds the line in three places:

- **The permission settings** put `gh pr merge` on the `ask` list, so every merge by an agent
  shows you a prompt ([Permissions](../safeguards/permissions.md)).
- **The agents** of the loop and of the review never merge: the builders, the critics, the
  verifier, the reviewer and the shepherd.
- **[`/merge-pr`](../components/commands.md#merge-pr)** is your explicit go-ahead to merge, and it
  still refuses a pull request that its session opened or pushed to. Otherwise it waits for the
  required checks, merges with `gh pr merge --merge --delete-branch`, removes the worktree and the
  local branch, and records the merge commit in the task file.

A session that only reviewed a pull request may merge it, once its required checks are green and
you have said so in that session. In most cases you merge yourself, on GitHub.

## After the merge

The worktree of the part goes, with `git worktree remove` from the main checkout, and the local
branch with `git branch -d`. The task file records the merge, and the part's state becomes
`merged`. A part that waits on this one merges `main` into its own branch before its pull request
opens ([The builder-critic loop](loop.md#several-parts-at-once)).
