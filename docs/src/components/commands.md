# Commands

A command is a prompt that the user starts by typing `/<name>`, often with arguments. Each command
is one file `commands/<name>.md`. Its frontmatter holds a `description` and an `argument-hint`, and
its body is the prompt. In the body, `$0` and `$1` stand for the first and the second argument,
and `$ARGUMENTS` for all the arguments as the user typed them. `harness install` copies each
command to `~/.claude/commands/<name>.md`. Edit the source in `commands/`, not the installed copy.

A command differs from a [skill](skills.md). The agent loads a skill on its own when a request
matches the skill's description. A command runs only when the user types it: both commands here
have `disable-model-invocation: true`. A command is a fixed sequence of steps for one job, with
its inputs as arguments.

The two commands act on one pull request of a Julia package in the research tree. `review-pr`
reviews it and brings its checks to green. `merge-pr` merges it after the review and cleans up.

## `review-pr`

`review-pr` reviews a pull request of a Julia package, fixes its findings and brings the required
checks to green. With `nofix`, it only reviews. The usage is:

```
/review-pr <Package> <PR number> [nofix]
```

The agent goes to the package's checkout in `Packages/` or else in `Experiments/`. It reads the
owner and the repository with `gh repo view`, because the packages belong to several owners. Then
it reads the state of the pull request with `gh pr view`.

It delegates from that directory. With `nofix` as the last argument, the `julia-pr-reviewer` agent
reviews and posts the review, and changes nothing. Otherwise the `julia-pr-shepherd` agent reviews,
posts the review, fixes the findings, pushes, and brings the required checks to green. The agent
gets the repository, the number and the state, but nothing about the purpose of the change, so the
review is blind. The command reports the verdict and the review URL. It never merges; use
`merge-pr` for that.

## `merge-pr`

`merge-pr` merges a reviewed pull request of a Julia package once its required checks are green.
Then it cleans up the checkout, the worktree and the task file. The usage is:

```
/merge-pr <Package> <PR number>
```

The command is the user's explicit go-ahead to merge, but it does not change who may merge. The
agent reads the repository and the state of the pull request as `review-pr` does, then follows
these rules:

- When this session opened the pull request or pushed to it, the agent reports it as ready and
  stops.
- When the pull request is merged already, the agent goes to the cleanup.
- When a required check failed or a reviewer requested changes, it reports which and stops. It
  never dismisses a review.
- When required checks are pending, it watches them with `gh pr checks --required --watch` in the
  background, and merges when they pass.

The merge is `gh pr merge --merge --delete-branch`. The cleanup fetches `origin` and fast-forwards
`main` only on a clean checkout on `main`. It removes each worktree on the head branch and deletes
the local branch. Last, it records the merge commit in the task file that names the pull request,
and commits that file. The report names the merge commit, what was cleaned up, and what was left.
