- **`dotfiles absorb` takes a host's live edits of managed files back into the chezmoi source, on a
  new branch for review.** It re-adds each file edited live and unchanged in the source since the
  last apply, lists each template and each file changed on both sides with its hunk and the
  `chezmoi merge` command, commits on `absorb/<host>-<time>`, pushes that branch and prints the
  `gh pr create` or `glab mr create` command; it never applies, never merges and never moves
  `main`.
