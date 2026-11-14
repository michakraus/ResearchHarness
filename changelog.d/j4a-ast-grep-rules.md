- **Five ast-grep rules for Julia find defects that a pattern decides, with rule tests and a CI
  job.** `docstring-comment` finds a comment that detaches a docstring, `allocated-equality` two
  `@allocated` readings compared exactly, `exitcode-alone` a `p.exitcode` read without
  `termsignal` or `success`, `line-citation-comment` a comment that cites `<name>.jl:<line>`, and
  `debug-probe` an `@show` or a `[DEBUG-` string under `src/` or `ext/`. Each has the severity
  `error` and a test in `ast-grep/rule-tests/` that `research-sgconfig.yml` names. The `ast-grep`
  job of `julia.yml` installs ast-grep 0.51.2, builds the parser, and runs the tests and a scan
  that checks the files of `debug-probe`. Copy the config to `~/Research/sgconfig.yml` again, so
  that `ast-grep test` there finds the tests.
