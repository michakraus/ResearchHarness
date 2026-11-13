- **`Dependents.yml` tests the default branch of the base in a second checkout of the
  dependent.** The run against the head wrote a `Manifest.toml` into the first checkout, and
  `Pkg.develop` keeps the versions it can, so a dependency that only the head forced could carry
  over and turn a regression into *known red*.
