---
description: Review a pull request on a Julia package in this tree, fix its findings and bring CI to green; with `nofix`, only review. Usage — /review-pr <Package> <PR number> [nofix]
argument-hint: <Package> <PR number> [nofix]
disable-model-invocation: true
---

Review pull request #$1 of the package `$0`. The arguments as typed: `$ARGUMENTS`.

Each step is its own Bash call:

1. `cd ~/Research/Packages/$0`, or `cd ~/Research/Experiments/$0` if the first does not exist. The
   agent below makes its worktree from the repository you stand in.
2. `gh repo view --json nameWithOwner -q .nameWithOwner` gives `<owner>/<repo>`. Do not assume
   one owner: the packages here belong to several owners.
3. `gh pr view $1 -R <owner>/<repo> --json number,title,state,isDraft,author,headRefName,baseRefName,mergeable,reviewDecision,statusCheckRollup,url`

Then delegate, from that directory:

- **The last argument is `nofix` or `[nofix]`** → `julia-pr-reviewer`: review and post the
  review. It changes nothing.
- **Otherwise** → `julia-pr-shepherd`: review, post the review, fix the findings, push, and bring
  the required checks to green. It stops at green and never merges.

Give the agent `<owner>/<repo>`, the PR number and the state from step 3, and nothing about what
the change is meant to do: the reviewer reviews blind. Report its verdict and the review URL.
