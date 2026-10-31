- **`skills/build-part/edges.md` names two more edge classes from a part's first critic round.**
  A written output series whose test checks only its length or type, so a mutant that writes zeros
  or another series survives; and a constant factor of a formula that the one test fixture sets to
  1, so dropping the factor survives. `plan-parts` writes a part's *Decided at the edges* from this
  list, so the next part of each kind decides these before its build.
