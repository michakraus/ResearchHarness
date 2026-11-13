- **A pull request on a base package tests the `core` group of each direct dependent.** The new
  workflow `Dependents.yml` runs these tests. The new profile key `dependents_bases` lists the
  bases. `harness workflows` installs `Dependents.yml` and its script `dependents.jl` into each
  base. It removes them from every other repository. The new `harness dependents --apply` writes
  the direct dependents of a base into `.github/dependents.toml`. A direct dependent is a package
  below `Packages/` with the base's UUID in `[deps]`. A job develops the head into the dependent
  and runs its `core` tests. When the dependent fails, the job runs the tests again against the
  base's default branch. Of the four results, only a regression of the pull request fails the job.
  The job does not test a head that the dependent's `[compat]` excludes, and reports it as
  excluded. The workflow is advisory. `verify-workflows.jl` checks both files in each base, their
  absence elsewhere, and `dependents.toml` in each base. It reads a profile without
  `docs_exceptions` or `docs_additions` as two empty lists. New cases of `harness test` in
  `githooks_cases.py` run the two subcommands, the script and `verify-workflows.jl` on fixture
  research roots. After the full suite, the CI job `python` installs Julia and the harness's
  Julia environment. Then it runs the part `githooks` again, so the cases of the script and of
  `verify-workflows.jl` run in CI. That step fails when the part still skips these cases. The CI
  job `lint` runs `actionlint` on `Dependents.yml` too.
