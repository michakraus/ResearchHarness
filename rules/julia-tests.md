---
paths: ["**/test/**/*.jl"]
description: The one layout of a Julia repository's tests — groups, runtests.jl, Aqua marks, compat entries — what a numerical or property test asserts, and how its check and runner are called.
---

# Test files in a Julia repository

Every repository here lays out its tests in one form. `Harness/scripts/test-layout.jl
--check <repository>` prints each violation, tagged with its rule, and exits 1 if there is any.

- **The test dependencies are in `test/Project.toml`.** `Project.toml` has no `[extras]` and no
  `[targets]`.
- **`runtests.jl` holds no test.** It holds `using SafeTestsets`,
  `const GROUPS = isempty(ARGS) ? ["core", "slow"] : ARGS` (or the platform line below), and one
  `if "<group>" in GROUPS` per group. Each `if` holds only
  `@safetestset "<label>" include("<path>")` lines.
- **The groups are `core`, `slow`, `doctests`, `metal`, `cuda` and `broken`.** Empty `ARGS` runs
  `core` and `slow`. `doctests` holds `test/quality/doctests.jl` and no other file. The CI
  Doctests job does not run this file: it runs the doctests itself, through `doctest`. A device
  group runs in its own CI workflow. No test file reads `ARGS` or `ENV` to decide what runs.
- **A repository with a `metal` group has the platform line, and only such a repository has it:**
  `const GROUPS = isempty(ARGS) ? (Sys.isapple() && Sys.ARCH === :aarch64 ? ["core", "slow", "metal"] : ["core", "slow"]) : ARGS`.
  Empty `ARGS` on Apple silicon then runs `metal` too. The check compares both lines as
  expressions, so a reordered condition is a violation. A `cuda` group keeps the plain line.
- **A `core` file runs in at most 60 s on this machine, cold, compilation included.** The time is
  the file's in `run-tests.jl <repo> core`, in the order of `runtests.jl`, in one fresh process. A
  slower file goes to `slow`. The layout check does not check this.
- **`test/<path>.jl` tests `src/<path>.jl`.** A test file at the top level of `test/` is
  `test/<name>.jl` for a `src/<name>.jl` of the same name; every other test file is in a
  directory. A test of several source files is in their deepest common directory. A test of the
  whole package is under `test/integration/`. `quality/`, `helpers/`, `integration/`,
  `verification/` and `devices/` mirror no directory of `src/`.
- **The quality files are under `test/quality/`.** `aqua.jl` is in every package. `jet.jl` is where
  the package has a hot or kernel path. `doctests.jl` is where the package has doctests, and it is
  in the group `doctests` only.
- **Every file under `test/` is listed once in `runtests.jl`**, or is a helper under
  `test/helpers/`. A helper is included by the test files that use it, and never listed.
- **A separate suite is outside the convention**: a top-level directory of `test/` with a
  `Project.toml` in its tree and no file that `runtests.jl` lists, such as the per-vendor device
  tests of a solver package in `test/gpu/`. It has its own environment and its own runner, and no
  rule here applies to its files.
- **A reached test that fails is `@test_broken`**, with its issue on the same line. A file that
  cannot load is in `broken`, with its issue on its `@safetestset` line.
- **The device skip is the one `@test_skip` that needs no issue.** It is the whole expression
  `@test_skip Metal.functional()` or `@test_skip CUDA.functional()`, in a file under
  `test/devices/`. `test/devices/metal.jl` runs its tests under `if Metal.functional()` and has
  the device skip in the `else` branch.
- **A failing Aqua check carries the same mark.** A check with a `broken` keyword, such as
  `piracies` or `persistent_tasks`, takes `(broken = true,)  # issue #NN` in `Aqua.test_all`.
  `stale_deps` has none: set `stale_deps = false`, and add
  `@test_broken isempty(Aqua.find_stale_deps(Base.PkgId(<Package>)))  # issue #NN` beside it. A
  name list, `stale_deps = (; ignore = [...])`, puts no `@test_broken` into the result. A check
  that fails only on some Julia versions is set to `false`, with its issue on the same line. A
  `broken` mark errors there as an Unexpected Pass on the versions that pass.
- **A shared dependency takes its bound from the package alone.** The `[compat]` table of
  `test/Project.toml` or `docs/Project.toml` has no entry for a dependency that `Project.toml` has
  in `[deps]` or `[weakdeps]`, whatever its value. These environments contain the package, so the
  resolver applies its bounds; an entry there can only repeat or narrow them. A test-only or
  docs-only dependency keeps its own bound.
- **Every test file is self-contained.** It has its own `using`, and a fixed seed where it draws
  random numbers.
- **The label of a `@safetestset` is a plain string**, unique in `runtests.jl`.
- **A floating-point difference of one or a few ULPs (at least up to `8 ulp`, `8 * eps(real(T))`)
  is acceptable and never blocks.** Assert floating-point identities and directional derivatives
  with `isapprox(a, b; rtol = 8 * eps(real(T)))` rather than `==`, because FMA contraction and
  summation order differ by a few ULPs across architectures, Julia versions and compilation
  contexts.
- **A rounding-path assertion asserts a rate across a sweep**, not the outcome at one parameter
  value. `--check-bounds` changes summation order, and `Pkg.test()` forces `yes` on 1.12 but
  inherits the session's setting on 1.13. Beside a `check_bounds == 0` guard, write "skipped where
  a run forces `--check-bounds=yes`", never "`Pkg.test()` skips this". Where a single-point
  assertion is unavoidable, reproduce it under `--check-bounds=yes` before you believe it.
- **An allocation assertion between two sizes is a difference under a stated tolerance**, never an
  exact equality: Windows quantises the figures by 16 bytes, in both directions. Pick the sizes so
  the tolerance sits orders of magnitude below what it must catch. A ceiling on the absolute figure
  sits above the residue and can hide an `N×2n` temporary.
- **Assert that the iterate changes after one step.** A test that checks only types or convergence
  flags misses an iterate that never moves.
- **A property of a search states what its status claims, against a reference the test computes
  itself.** A `SUCCESS` of a minimising search is a minimum, not only a decrease: a stationary
  point with a decrease below the anchor can be a maximum. A `STALLED` or a failure is checked
  against a decrease that a fine grid or a closed form finds, so a status that hides a reachable
  decrease fails the test. A property that accepts every non-error status checks nothing.
- **A property test reports one counterexample per check.** Supposition shrinks the first failure
  it finds, so a dismissed counterexample hides every other failure of the same check. After you
  judge a counterexample a false alarm, filter its class out of the generator, or out of the
  property, and run the check again; only a clean rerun clears the property.
- **Every branch, keyword value, component and stated property has a test** that fails when that
  path breaks. Assert each component of a result, not one component and a length. Run every
  combination of a keyword grid with `Iterators.product`, not a list picked by hand. A mutant of
  each branch fails a test; a guarded branch that no test reaches is a finding.
- **A tolerance comes from the error source of the computed value.** Derive it from the rounding
  and the truncation error, in the metric of the evidence, such as `rtol = 10 * (δ + eps(T) / δ)`
  for a difference with the step `δ`. It sits below what a mutant gives: test one input inside the
  bound and one outside, and give a "must fail" threshold the pass bound of the same `T`. A bound
  tuned until the test passes checks nothing.
- **A fixture gives each factor a value other than 1** and each component a value of its own.
  Equal weights, a symmetric, separable, linear or time-independent case, and a start at the exact
  answer hide a wrong term. Test each factor at two values, such as `ω in (0.7, 3.0)`, on a
  non-linear, time-dependent case, and run the mutant that drops the factor or the component.
- **`@test_throws` matches a phrase that only the guard writes**, with an anchored pattern:
  `@test_throws r"^ArgumentError: <the guard's phrase>" f(x)`. A library error or another guard of
  the same type then does not pass it. Take the exception and the message from one call. Remove the
  guard once: the test must fail, not error.
- **A reference value comes from a method that can be right where the code is wrong**: an
  independent or a more accurate method, in wider precision, from a converged run only. Record
  with it the flags and the versions that made it, such as `Base.JLOptions().check_bounds` and
  `VERSION`. The reference's own error is far below the smallest error that it measures.
- **Reproduce a 1.12 `min` failure with `julia +1.12`**: run `julia +1.12 --startup-file=no
  run-tests.jl <worktree> <test file>` or `julia +1.12 --project=. <test file>`.

Run one file, a group, or the files a diff reaches, with `run-tests.jl <repository> <path>`,
`run-tests.jl <repository> core` or `run-tests.jl <repository> affected`. `affected` never runs
the group `doctests`, so a doctest change runs `run-tests.jl <repository> doctests`.
`--jobs <n>` before the selection runs its files in n worker processes, each file once; with
`full`, the files of `Pkg.test()`. A `core` run with `--jobs` gives no D6 verdict, because a file's
time in a worker is not its cold time in the order of `runtests.jl`. The shared `pre-commit` hook
runs `test-layout.jl --check` on a commit that touches `test/`.
