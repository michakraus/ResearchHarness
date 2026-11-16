- **`runtests.jl` has a second form, the parallel form, in which ParallelTestRunner.jl runs each
  test file in a worker process, and the test tools read it.** The form is a fixed template with
  one literal table `TESTS` of group → label → path; `test-layout.jl` holds the template, checks a
  `runtests.jl` against it statement by statement, and judges the files of `TESTS` by the rules of
  the serial form. `run-tests.jl` lists, selects and runs the files of `TESTS` in its own driver,
  and `full --jobs <n>` runs one `Pkg.test(; test_args = ["--jobs=<n>"])` on that form.
  `verify-workflows.jl` check 6 judges `test/ci-groups.toml` against the groups of `TESTS`.
  `rules/julia-tests.md` requires the form for a suite whose serial `Pkg.test()` takes more than
  10 min, with `retries = 0`: a flaky test is a defect with an issue. ParallelTestRunner 2.10 is in
  the harness's Julia environment, for the end-to-end test of the template; run
  `harness install --apply` to install it.
