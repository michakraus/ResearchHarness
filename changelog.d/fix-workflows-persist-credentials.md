- **No checkout of a workflow template keeps the token.** `actions/checkout` writes the token
  into the git configuration by default, where every later step of the job can read it, and the
  package's build, tests and docs build run third-party code. Each checkout of `CI.yml` and
  `Documenter.yml` now sets `persist-credentials: false`, as those of `Dependents.yml` already
  did. The docs deploy pushes from a new repository of its own, with `DOCUMENTER_KEY` or
  `GITHUB_TOKEN`. A private repository needs `devbranch` in its `deploydocs` call: without it,
  Documenter reads the default branch with `git remote show origin`, which needs the token there,
  and falls back to `master`. A case of `harness test githooks` checks every checkout of every
  template. The repositories get the change at the next `harness workflows --apply`.
