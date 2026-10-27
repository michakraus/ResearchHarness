- **`skills/build-part/edges.md` names the edge of a value read out of a live cache.** A value
  that a step reads out of its cache and stores beside the solution aliases the cache, so every
  stored entry ends up equal to the last one, and a test whose fixture gives each step the same
  value cannot see it. `plan-parts` writes a part's *Decided at the edges* from this list, so the
  next numerical part decides the copy and a step-dependent fixture before its build.
