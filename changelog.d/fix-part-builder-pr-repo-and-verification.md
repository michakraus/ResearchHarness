- **`part-builder`'s finish names the repository in `gh pr create` and `gh pr edit`, and puts the
  verifier's `## Pre-PR verification` block in the pull-request body.** Without `-R`, the guard
  refused the finish's `gh pr create`, and `gh pr edit` took the repository from the checkout,
  which is the wrong one after a `cd` that failed. The body listed the critic's table but not the
  verifier's block, so a reviewer did not see what the verifier fixed and left. The finish also
  says where to write the body file, keeps the `--title` free of backticks and `$(`, and puts the
  critic's table under `## Critic` and the known issues under `## Known issues added`. All of it
  matches `python-builder`'s finish.
