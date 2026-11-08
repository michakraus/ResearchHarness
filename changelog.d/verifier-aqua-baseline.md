- **`julia-branch-verifier` reads the piracy baseline from the package's own Aqua call.** It said
  that most repositories name no Aqua in a `Project.toml`, so that a piracy check had no baseline.
  Every package of the tree it serves names Aqua in its `test/Project.toml`, and the tests of all
  but one run the piracy check. The verifier now says so: a package whose tests run the check has a
  base that passes it, and only a package with no Aqua, or with the check turned off, has no
  baseline.
