- **The CI test step runs with `check_bounds: auto`, not the `julia-runtest` default of `yes`.**
  A bounds check defeats `@inbounds`, so the local `MMatrix` and `MVector` of a static kernel
  escape to the heap, and a kernel that a compiled backend runs cannot allocate: under `yes`, every
  such testset throws `KernelException` on a host backend that compiles kernels, which is
  `KernelAbstractions` 0.10's `CPU()`. `pre-push` and the pre-commit probes already run with
  `auto`. The cost: no CI run checks bounds inside `@inbounds` code, and the allocation assertions
  that a `Base.JLOptions().check_bounds != 1` guard skips under `yes` run in CI on every platform.
  A run that still forces `yes` — `Pkg.test()` and `run-tests.jl` on Julia 1.12 and earlier —
  needs that guard on a kernel testset too.
