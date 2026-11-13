- **`test.yml` and `julia.yml` run on a push to `main` only, and on each pull request.** A push to
  a topic branch with an open pull request started each workflow twice on the same commit, once
  for `push` and once for `pull_request`, and the two runs are in different concurrency groups, so
  neither cancelled the other: of 200 recent runs, 50 were such repeats. The pull request run
  reports every required check. `julia.yml` takes `workflow_dispatch`, as `test.yml` does, so a
  branch without a pull request can still be tested by hand.
