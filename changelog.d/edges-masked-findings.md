- **`skills/build-part/edges.md` names the edge of new code under a generated suppression
  record.** A per-file ignore table or a type-checker baseline that a branch writes suppresses by
  file and code, so the branch's own new lines in a covered module pass with findings that the rule
  for new code forbids. A critic checks the added lines with the generated record removed.
