- **A pull request on a base package tests the `core` group of each direct dependent, in the new
  workflow `Dependents.yml`.** The new profile key `dependents_bases` lists the bases. `harness
  workflows` installs `Dependents.yml` and its script `dependents.jl` into each base and removes
  them from every other repository, and the new `harness dependents --apply` writes the list of a
  base's direct dependents, the packages below `Packages/` with the base's UUID in `[deps]`, into
  `.github/dependents.toml`. A job develops the head into the dependent and runs its `core` tests;
  a red dependent runs again against the base's default branch, so of the four results only a
  regression of the pull request fails the job, and a head that the dependent's `[compat]` excludes is reported
  as excluded and not tested. The workflow is advisory. `verify-workflows.jl` checks both files in
  each base, their absence elsewhere, and `dependents.toml` in each base. The new cases of
  `harness test` in `githooks_cases.py` run both subcommands, the script and `verify-workflows.jl`
  on fixture research roots.
