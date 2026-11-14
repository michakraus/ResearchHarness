- **The edge catalogue names the order of git's credential helpers.** A helper that a repository
  adds runs after the system and global helpers, and git stops once a helper gives a username and
  a password, so an empty `helper` line goes first.
