# The §V and §L sections of a plan

Write both sections into the plan, after the collision map. Replace each `<…>`, and delete a line
that does not apply. `julia-builder` and `julia-critic` find these sections by their headings.

The generic rules are not repeated here: the build steps are in `julia-builder`, the judging rules
in `julia-critic`, the evidence table and its rules in `~/.claude/skills/build-part/evidence.md`,
and the loop in the `build-part` skill. A rule in this plan's §V adds to them; where it differs,
the plan's rule holds for this plan.

---

## §V · Plan rules for building and verifying

- **The benchmark of a part is** <its *Done when* | the `verification` cell of each of its
  T-numbers and the numbered checks of its §5V subsection>. <The house checks of §<n> are clauses
  of every part.>
- **Precisions:** <every numeric test runs in `Float32` and `Float64` and asserts the element type
  of its result>.
- **Backends:** <`Array`, `JLArray` under `allowscalar(false)` and KA `CPU()`, wherever the code
  runs on them (`test/backends.jl`)>.
- **Devices:** <Metal through Kaimon; CUDA and ROCm by hand on the user's machines>.
- <Any other rule of this plan, one sentence each.>

## §L · The loop for this plan

Every part runs through the builder-critic loop of the `build-part` skill.

- **The builder also reads:** <sections, or "nothing more">.
- **The critic also reads:** <the preamble of §<n>, the traps section, or "nothing more">.
- **This plan changes the loop:** <a draft pull request in place of a pull request, for example,
  or "not at all">.
- **Generated mutants:** <"none" | "a sweep of the diff before round 1", for a part whose tests are
  its main deliverable. It adds about 20 minutes per 800 mutants in a package with a one-minute
  suite, and a fix round for its survivors (`~/.claude/skills/build-part/evidence.md`, *Which
  mutants run*)>.
