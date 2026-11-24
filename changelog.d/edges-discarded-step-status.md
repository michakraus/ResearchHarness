- **`skills/build-part/edges.md` names the edge of a return that substitutes an earlier iterate
  and carries that iterate's whole status.** A least-squares solve that kept its step start in
  place of the step's result dropped the solve-wide counters the discarded step added, and three
  critic rounds missed it. The new edge tells the planner to take the iterate's own fields from
  the iterate returned and the solve-wide counters from the status after the discarded step, and
  to test each counter on that return.
