- **The edge catalogue names a class for a plan that allows a shared `CHANGELOG.md` "added lines
  only" while the part's move makes earlier `[Unreleased]` sentences false.** The plan row and the
  changelog rule then contradict each other, so the spec decides it: in-place corrections inside
  the base's `[Unreleased]` section only, with a list of the stale phrases and a range guard over
  the `git diff -U0` hunk headers.
