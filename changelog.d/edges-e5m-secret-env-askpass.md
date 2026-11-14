- **The edge catalogue names two classes of secret handling in a shell script.** A secret in a
  shell variable that a caller exported reaches every child of the script, and
  `GIT_TERMINAL_PROMPT=0` leaves git's askpass routes and a credential helper's dialog open.
