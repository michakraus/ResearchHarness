# Git safety

`git` and `gh` run outside the sandbox, because a sandboxed `git` cannot write `.git` and a
sandboxed `gh` fails its TLS check. So the sandbox does not limit them, and the checks of this page
do the work: the permission lists, the guard hooks, the worktrees, and the hooks and rulesets of
the repositories. Several sessions can work in one tree at the same time, so most of the checks
protect the work of one session from another. This page describes each check by the step of the
work that it guards.

## Why git needs its own checks

A git command can lose work that no file system limit sees: a reset drops commits, a sweep commits
another session's files under your message, a forced push replaces a branch on the remote. Most of
these commands are fine in one state of the repository and wrong in another. A permission rule
reads only the text, so the harness splits the work:

- **A permission rule** refuses or asks for a form that is wrong in every state, such as
  `git reset --hard` or `git push --force` ([Permissions](permissions.md#deny)).
- **A guard hook** runs code, and reads the state that the text does not show: the working
  directory, the branch, whether a worktree holds commits that no branch has
  ([Guard hooks](guard-hooks.md#the-git-write-check)).
- **A hook or a ruleset in the repository** checks what arrives, whatever the session did:
  the pre-push hook and the branch protection.

## Staging

**A commit takes the whole index.** A sweep stages every change of the tree, including the work of
another session in the same checkout. So the staging rules are:

- Stage the paths that you changed, by name. `git add -A`, `git add .`, `git add -u`,
  `git commit -a` and `git commit --amend` are denied; the [staging
  check](guard-hooks.md#the-staging-check) also refuses the sweeping forms that a pattern does not
  catch, such as a flag cluster.
- Read `git status --short` and `git diff --cached --name-only` before a commit, and leave alone
  what you did not write.
- `git stash` acts on everything that changed, and the stash list is shared by every worktree, so
  its sweeping forms are denied.

The guard catches the common spellings. The rest of the rule is an instruction:
**known issue (K116)**, the staging check finds no `git add` behind a prefix word or inside a
compound command, and misses some spellings of `.`.

## Worktrees

A worktree is a second checkout of a repository on its own branch. Each part of a plan, each
review and each new feature works in one, so the main checkout stays on `main` and two sessions do
not write the same files.

- **One place.** The `WorktreeCreate` hook, [`worktree.py`](guard-hooks.md#worktree-py), makes each
  worktree at `~/Research/.worktrees/<Repository>-<slug>`, from `origin/HEAD`, not from a local
  `main` that can lag. A worktree of a sub-agent gets the slug `agent-<hex>`, detached at
  `origin/HEAD`, and the agent makes its own branch.
- **No forced removal.** The `WorktreeRemove` hook removes a worktree without `--force`, so a
  worktree with changes stays. A forced `git worktree remove` that would lose commits or tracked
  changes asks you ([the git write check](guard-hooks.md#the-git-write-check)).
- **No move out of the tree.** The directory check refuses a move of the session out of the
  research tree, and asks before a worktree is removed.

A worktree goes when its branch merges: `git worktree remove <path>` from the main checkout, then
`git branch -d`. [The research tree](../research-tree.md#temporary-work) names the place.

## Writes that depend on the state

[The git write check](guard-hooks.md#the-git-write-check) answers the forms that are right in one
state and wrong in another:

| command | the check |
|:--|:--|
| `git worktree remove --force` | asks when the worktree holds commits that no other branch has, or tracked changes; passes otherwise |
| `git cherry-pick` | asks outside a worktree or a checkout of your own organisations |
| `git push --force-with-lease` | refuses a lease push to the default branch, or one that names no branch; asks for a push to another organisation; passes a lease push of a topic branch of your own organisation |

Other guards of git and `gh`:

- [The rm check](guard-hooks.md#the-rm-check) asks for a `git rm` outside a worktree, and for a
  `git merge` outside one.
- [The `gh pr create` check](guard-hooks.md#the-gh-pr-create-check) refuses a pull request that
  names no repository with `-R`, and asks for one outside your own organisations.
- [The `gh api` check](guard-hooks.md#the-gh-api-check) refuses a DELETE, passes a review or a
  comment in your own organisations, and asks for the other writes, such as a `PATCH` of a ref.
- [The archive check](guard-hooks.md#the-archive-check) asks for a `git archive` that writes its
  file with `-o`.
- [The sandbox check](guard-hooks.md#the-sandbox-check) refuses the forms that fail in the sandbox
  with a misleading error: a `git` write nested in `$(…)` or after a `cd`, a `$?`, a path argument
  to `git init`, `git clone` or `git worktree add`, and a `git init` inside a working tree.

## Pushes

A push is the step where a local mistake becomes public. The checks:

- **The permission lists** allow `git push origin <branch>`, deny a forced push, a mirror push and
  a lease push to `main` or `master`, and ask for a deletion on the remote.
- **The pre-push hook of a package** runs the full test suite on a push to `main` or `master`, and
  passes a push of another branch, which CI tests
  ([`pre-push`](../components/githooks.md#pre-push-and-pre-push-jl)). **Known issue (K133):** it
  tests the working tree, not the commit that it pushes.
- **The pre-push hook of the harness** runs the [leak checks](leaks.md) first, then the suite, on a
  `git clone --shared` of the pushed commit, so it tests what it pushes. A branch other than `main`
  gets only `harness leaks --commits`.
- **The ruleset of a repository.** [`harness ci-protection`](../harness-command.md#ci-protection)
  sets a ruleset on the default branch: no deletion, no non-fast-forward push, and the required
  checks, strict. You, as the admin, can bypass it. It has no review rule, because a required
  review by the only author is a review by oneself. It refuses to run while `verify-workflows.jl`
  fails.

## Merges

A merge is an `ask` rule, so it always shows you a prompt. The rule of who merges is in
[Review and pull requests](../agentic/review.md#who-merges): no agent merges a pull request that
its own session opened or pushed to, and `/merge-pr` refuses such a pull request too.

## The limits

- The checks read the command text with its quotes and the scripts of `sh -c`, `bash -c` and
  `eval`. A `git` whose subcommand a variable names, or that a script on standard input runs,
  passes them.
- The staging rules beyond the staging check, such as reading the index before a commit, are
  instructions only.
- The ruleset lets you, the admin, bypass it, so it does not stop a push that you make yourself.
