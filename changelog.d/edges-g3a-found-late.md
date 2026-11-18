- **The edge catalogue names five more classes of a process outside a sandbox that serves or reads
  for the sandboxed side.** A socket read bounded per `recv` and not as a whole, a client that drops
  the reply it read when a reset follows, a `git` that reads the config of a repository the
  sandboxed side can write, a `git` that finds another repository than the one checked, and a check
  of a path that the sandboxed side can rename before the reader opens it.
