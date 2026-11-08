- **`build-part` gives each critic the base.** A round-1 critic got six inputs, and the base was
  not among them, but `part-critic` requires it and stops without it. The skill passes seven, so a
  critic of a part of another pair judges the right range at its first spawn.
- **`skills/build-part/edges.md` names two more edge classes that the loops found late.** An exit
  status read from a Julia `Process` as `exitcode` alone, which is 0 for a child that a signal
  ends; and a mutant reproducer that never runs the tests on the unmutated tree, so a test file
  that fails there for another reason reads as every mutant killed.
