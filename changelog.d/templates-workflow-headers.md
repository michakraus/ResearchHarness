- **The headers of the workflow templates name no local directory.** `CI.yml`, `TagBot.yml`,
  `dependabot.yml` and `codecov.yml` said that the installer copies them into the repositories
  "under Packages/ and Experiments/", which are directories of one checkout, and each template said
  "edit this file", which an installed copy also reads. Each header, and those of `Documenter.yml`,
  `Dependents.yml` and `dependents.jl`, now names the template's path in the ResearchHarness and
  says never to edit an installed copy. `CI.yml` no longer lists the compat floors of one tree, and
  its line of 104 characters is rewrapped at 100. Comments only, but the templates are copied byte
  for byte, so `harness workflows --apply` rewrites them in every repository, and
  `verify-workflows.jl` reports drift until it does.
