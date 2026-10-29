- **`skills/build-part/edges.md` names three more edge classes from the P2 loop.** A signal
  handler that raises inside a wait on a child, so that `subprocess.run` kills a child that holds
  a lock; a port of a shell script where a program that cannot start raises `OSError` past every
  check, where the shell went on to the next one; and a CI stub written at the path of a program
  that the same job then runs for real. `plan-parts` writes a part's *Decided at the
  edges* from this list, so the next part of each kind decides these before its build.
