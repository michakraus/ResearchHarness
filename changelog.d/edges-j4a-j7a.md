- **`skills/build-part/edges.md` names four more edge classes from two reviewed parts.** A
  short-form Julia definition with a return type or a `where` clause, whose head is not a call; an
  order that a test sees only because a hash set happens to hold it; a second read of state that
  the first read already holds; and a CI step that pipes its check into `tee` without pipefail, so
  a failed check passes the job. `plan-parts` writes a part's *Decided at the edges* from this
  list, so the next part of each kind decides these before its build.
