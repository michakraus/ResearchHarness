- **The sandbox allows writes to `~/.cache/pocl`.** PoCL, the OpenCL runtime of the
  KernelAbstractions CPU backend from 0.10 on, writes each compiled kernel to that cache. A
  sandboxed run of a kernel that the cache does not hold failed with `CLError(1)`, so a `JLArray`
  test in a session failed where the same test passed outside it.
