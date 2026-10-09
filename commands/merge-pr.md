---
description: Merge a reviewed pull request on a Julia package in this tree once its required checks are green, then clean up the checkout, the worktree and the task file. Usage — /merge-pr <Package> <PR number>
argument-hint: <Package> <PR number>
disable-model-invocation: true
---

Merge pull request #$1 of the package `$0`, then clean up after it.

Get the pull request first. Each step is its own Bash call:

1. `cd ~/Research/Packages/$0`, or `cd ~/Research/Experiments/$0` if the first does not exist.
2. `gh repo view --json nameWithOwner -q .nameWithOwner` gives `<repo>`. Do not assume
   one owner: the packages here belong to several owners. Use `-R <repo>` in every command below.
3. `gh pr view $1 -R <repo> --json number,title,state,isDraft,author,headRefName,baseRefName,mergeable,reviewDecision,statusCheckRollup,url`

**This command is the user's explicit go-ahead to merge.** It does not change who may merge:

1. **This session authored the pull request** — it opened it, or it pushed commits to it → do not
   merge. Report that the PR is ready, and stop.
2. **The state is `MERGED`** → go to step 5.
3. **A required check failed, or a reviewer's requested changes are outstanding** → report which,
   and stop. Do not dismiss a review.
4. **Required checks are pending** → run `gh pr checks $1 -R <repo> --required --watch` in the
   background, and merge when it exits 0. Merge from `~/Research`, not from the package's
   checkout, so that no local branch moves: `gh pr merge $1 -R <repo> --merge --delete-branch`.
5. **Clean up.** In the package's checkout, `git fetch origin`. Fast-forward `main` only if the
   checkout is on `main` with a clean tree — another session may hold it, so otherwise say so and
   leave it. Remove every worktree under `~/Research/.worktrees/` on the PR's head branch, `cd`
   out of it first, and delete the local head branch.
6. **Update the task file** that names this pull request: find it with a search of
   `~/Research/Tasks/` for the PR number and the package. Record the merge and its merge commit,
   and keep its card true by `Tasks/CLAUDE.md`. Commit that file by name.

Report the merge commit, what was cleaned up, and what was left and why.
