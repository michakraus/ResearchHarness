- **`harness ci-protection` also protects the Harness itself, with the jobs of its `test.yml` as
  required checks.** After the packages and experiments, it plans and, with `--apply`, writes the
  ruleset `main` of the Harness checkout that runs it, in the packages' form, and `--remove-classic`
  treats it the same way. The Harness requires its own list, `HARNESS_CHECKS`: the jobs of
  `.github/workflows/test.yml` that report on every pull request and are not warnings, so not
  `Python 3.x`, and nothing of `julia.yml` or `docs.yml`, whose path filters would leave a pull
  request pending. `ruleset_problem` judges a ruleset against the list of its repository. A case
  reads `test.yml` with PyYAML and fails when `HARNESS_CHECKS` differs from it, so a renamed or an
  added job fails `harness test` rather than leave every pull request pending.
