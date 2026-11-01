- **A `fatou` that cannot start no longer blocks a commit in the Julia packages.** When `fatou` is
  on the `PATH` but the system cannot start it, such as a script whose interpreter is missing, the
  lint stage threw an uncaught error: the commit was refused, and the NFC and load stages never
  ran. The stage now prints `fatou lint: could not start — stage skipped, not a failure` with the
  error, and the commit goes on to the later stages, as a missing `fatou` does.
