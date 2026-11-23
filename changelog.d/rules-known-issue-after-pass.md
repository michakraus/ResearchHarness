- **The arbitrator's `known issue` move no longer records a code defect that the branch causes.**
  After a PASS, `known-issues.md` kept a branch-caused defect out of `KNOWN_ISSUES.md`, while
  the arbitrator's move recorded any code finding that was not a wrong result on an input of a
  clause. The move now covers a finding that the branch does not cause, and a limit of a form
  that the plan decided; `known-issues.md` names that limit as an entry whose `found` field names
  the clause. A code finding that the branch causes takes `continue`, or `test round` when only a
  test changes.
