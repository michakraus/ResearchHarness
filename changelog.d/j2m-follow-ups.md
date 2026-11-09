- **`.githooks/pre-push` runs `scripts/dispatch-delta-test.jl` and `scripts/julia-methods-test.jl`
  when their scripts change, and with all others on a change to `Project.toml`.** The hook's list
  matches the CI matrix of `julia.yml` again. The Julia rule and the agents that run
  `julia-methods.jl` say that its exit status 3 is a complete listing, not a failure, and the
  script's header points to the routing in `rules/julia-code.md`.
