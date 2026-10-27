- **The pre-push leak check of a branch skips the commits that a branch of origin holds.** A
  branch that merged a newer `main` sent `main`'s own commits through `harness leaks`, and GitHub's
  merge messages ("Merge pull request #N from <owner>/…") refused the push although the tree had
  no hit. The range is the local commits that neither the remote SHA nor `refs/remotes/origin/*`
  holds; a commit there is on the remote already. Two new cases of the branch checks: an existing
  branch that merges `origin/main` passes, and one whose own new commits add the leak string is
  refused.
