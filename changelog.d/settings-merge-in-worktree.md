- **A `git merge` in a worktree runs without a prompt.** `rm-scope.py` asks for a `git merge`
  only outside `~/Research/.worktrees/<name>/` or aimed at another repository, and there not for a
  plain `--ff-only` or `--no-edit` merge. The settings template allows `git merge *` in place of
  its three merge grants and drops the eight `ask` rules of `--no-ff`, `--squash`, `--no-commit`
  and `-m`; `--abort` and the `git -C` forms keep theirs. The merge of `origin/main` into a pull
  request's branch asked 11 times in 23 days of the prompt log, and is local and undone by
  `git reset --hard ORIG_HEAD`. A broken `rm-scope` fails open: a named merge in a main checkout
  then runs unasked.
