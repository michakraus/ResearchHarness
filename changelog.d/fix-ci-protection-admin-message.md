- **`harness ci-protection` says why a call was refused.** When GitHub answers a call with
  `Resource not accessible by personal access token`, the final error counts those repositories,
  names the missing repository permission *Administration: write*, and names the token that made
  the call: the sealed secret `github`, or the token that `gh` from the `PATH` chose (the wrapper's
  organisation token, `GH_TOKEN`, `GITHUB_TOKEN` or the login of `gh`). It read only
  `<n> repositories failed`.
