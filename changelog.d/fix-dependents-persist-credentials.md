- **No checkout of `Dependents.yml` keeps the token.** `actions/checkout` writes the token into a
  credential file by default, and the tests of the dependents run code of other repositories. Each
  checkout now sets `persist-credentials: false`, and a case of `harness test githooks` checks it.
