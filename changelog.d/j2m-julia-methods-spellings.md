- **`scripts/julia-methods.jl` exits with status 3 when a name given on the command line has
  definitions with more than one qualified spelling, such as `f` and `M.f`, or `A.f` and `B.f`.**
  After the full listing, one line per such name names its spellings and points to
  `search_methods` and `julia-callers.jl`, because the definitions alone do not tell whether the
  methods extend one function. With `--all`, the heading of such a name carries the mark
  `more than one qualified spelling`, and the status stays 0 or 1. The new
  `scripts/julia-methods-test.jl` checks this against the real `fatou`, and CI runs it.
