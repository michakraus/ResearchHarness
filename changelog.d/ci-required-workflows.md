- **A group file can name the repository's device workflow, `workflows = ["Metal.yml"]`, and
  `harness ci-protection` then requires that workflow's jobs.** With test groups, each CI job
  runs its group alone, so the `metal` group left the required macOS jobs; this keeps the Metal
  tests required, through the stricter `Metal.yml`, which fails when Metal is not functional.
  `test-layout.jl` and `verify-workflows.jl` check that each named workflow exists and is not an
  installed one, and `harness ci-protection` refuses one that does not run on every pull request. `run-tests.jl affected` selects from every group of the group file except
  `slow`, so a file that a repository moves out of `core` keeps its quick check.
