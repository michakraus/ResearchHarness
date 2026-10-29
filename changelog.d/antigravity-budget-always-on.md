- **Antigravity's size check counts only the global file and the always-on rules against the
  80,000-byte budget.** A rule with `paths` loads only for a matching file, so it is not in the
  budget that Antigravity's always-on and global rules share; it still keeps the 24,000-byte cap
  and the include check. Before, `harness install` refused a tree whose rules together passed
  80,000 bytes, and installed nothing, although its always-on texts were far below the budget.
