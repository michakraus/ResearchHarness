- **The `downgrade` job of `CI.yml` resolves `Project.toml` and `test/Project.toml` together
  (`projects: ., test`), and checks the lower bounds of both.** A resolve of the root alone took
  each indirect dependency at its newest version, and the test run, which keeps that manifest, then
  could not add a test-only dependency that caps it: DocStringExtensions 0.10.2 against Documenter
  1.19, and CEnum 1.0.0 against CairoMakie and Metal. Such a package failed the job whatever its
  floors. With both projects in one resolve, a package with Documenter and CairoMakie in its tests
  passed the floor check and its suite on Julia 1.12.7, once two test floors that could not be
  reached were raised. The floors in `test/Project.toml` are now tested too, so a false one turns
  the advisory job red.
