- **`scripts/dispatch-delta.jl` compares the method tables of a base and a head, loaded side by
  side, and the gate and `julia-branch-verifier` run it.** It loads both trees in two fresh
  processes through `TestEnv`, writes one JSON record per own method for each side, and fails on a
  new own-own or own-external ambiguity and on a new piracy in the package's module tree; added
  methods, new JET reports, findings that went away and dependency drift are information.
  `gate.jl` runs it as the step `dispatch` before `format`, and the verifier runs it for point 3 on
  every branch, in place of Aqua `test_piracies` in a session and the sibling-package exemption.
  The rule `julia-code` names it for the ambiguities that a branch adds. `Project.toml` adds Aqua,
  pinned to 0.8.18 because the piracy hunt is internal API, and JET 0.13.
