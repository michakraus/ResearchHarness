- **The CI test step runs with `check_bounds: auto`, not the `julia-runtest` default of `yes`.**
  A bounds check defeats `@inbounds`, so the local `MMatrix` and `MVector` of a static kernel
  escape to the heap, and a kernel that a compiled backend runs cannot allocate: under `yes`, every
  such testset throws `KernelException` on a host backend that compiles kernels, which is
  `KernelAbstractions` 0.10's `CPU()`. The pre-commit probes already run with `auto`. A package
  that must keep the forced checks can still guard the affected testsets with
  `Base.JLOptions().check_bounds != 1`, and the reason the files give for their allocation
  assertions covers that case.
