- **The canonical `CI.yml` runs its matrix in tiers, and the downgrade job moves to a workflow of
  its own, `Downgrade.yml`.** A pull request and a push to a branch run Ubuntu on Julia `min` and
  `1`, then macOS and Windows on `1` only once every Ubuntu job has passed; the new weekly run
  (Monday 03:17 UTC), a tag and a run by hand add `min` on macOS and Windows. The `groups` job
  writes those versions from the event, and gives every other event, such as `merge_group`, the
  full matrix. `pre` and `nightly` run on every event in the advisory job `prerelease`, which no job
  waits for. The concurrency group holds the event, so the weekly run and a push to `main` do not
  replace each other's pending run. `Downgrade.yml` runs the downgrade job that `CI.yml` held, with
  the same steps, on a pull request and a push that change `Project.toml` or `test/Project.toml`, on
  every tag, weekly and by hand. `harness workflows` installs it wherever it installs `CI.yml`, and
  `verify-workflows.jl` compares it byte for byte; the `workflows` of a `test/ci-groups.toml` may
  not name it, as they may not name `CI.yml`. `REQUIRED_CHECKS` drops `Julia min` on macOS
  and Windows, so a repository without test groups requires five checks, and a case derives that
  set from the template. Every repository needs `harness workflows --apply`, then `harness
  ci-protection --apply`: until then the old ruleset requires two checks that a pull request no
  longer reports.
