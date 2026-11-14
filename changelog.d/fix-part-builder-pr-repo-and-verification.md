- **`part-builder`'s finish names the repository in `gh pr create` and `gh pr edit`, and puts the
  verifier's `## Pre-PR verification` block in the pull-request body.** Without `-R`, `gh` picks
  the repository from the working directory, which is wrong after a `cd` that failed. The body
  listed the critic's table but not the verifier's block, so a reviewer did not see what the
  verifier fixed and left. Both match `python-builder`'s finish.
