- **`spec-validate.py` runs its `git archive` and `git status` without the global git
  configuration.** In a process that may not read a file that `~/.gitconfig` includes, as in a
  Kaimon session, where every check that needs Metal runs, git exits 128 before it reads the
  repository: the copy of the base failed with a rule-9 error, and `git status --porcelain` of the
  head returned no answer, so the check that a command left the head unchanged was skipped without
  a word. Both calls now set `GIT_CONFIG_GLOBAL=/dev/null`; neither needs a user setting. A case
  of `harness test` builds such a home and fails without the setting.
