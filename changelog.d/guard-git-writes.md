- **A new guard check allows three `git` writes when nothing is lost, and asks otherwise.** A
  `git worktree remove --force` (or `-f`) of a worktree below `~/Research/.worktrees/` runs with
  no prompt when a remote-tracking ref contains its HEAD and no tracked file is modified or staged;
  otherwise the prompt names the commit or the files that would go. A `git cherry-pick` runs with
  no prompt in such a worktree or in a checkout whose `origin` is in an own organisation. A
  `git push --force-with-lease origin <branch>`, or with `HEAD:refs/heads/<branch>`, runs with no
  prompt to an own organisation when the lease names no ref or the pushed branch, `origin` has no
  `remote.origin.push` refspec, and in the `<branch>` form the branch is a local one. A lease push
  to `main`, `master` or the branch of `origin/HEAD` is refused in every form, also inside a
  command of several parts, and a plain `--force` stays refused.
  The settings template drops the `ask` rules on `git cherry-pick *` and on a forced
  `git worktree remove`, and the `deny` rule on `git push --force-with-lease *`, because a matching
  rule overrides a hook's `allow`. Any other form of these writes asks, in every frontend.
