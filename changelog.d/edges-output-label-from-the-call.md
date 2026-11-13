- **`edges.md` adds a cell of a comparison table that takes its label from the plan, not from the
  call it records.** A benchmark that writes each cell's method from its pairing table keeps a
  correct label when an adapter passes another solver, line search or linear solver, so the wrong
  pairing never shows in the verdicts. The new edge tells the planner to build the label from the
  objects the adapter passes, and to give each adapter a mutant that swaps one of them.
