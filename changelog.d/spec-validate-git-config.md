- **`spec-validate.py` runs its `git archive` and `git status` once more without the global git
  configuration when git cannot read a file that it includes.** In a process that may not read a
  file that `~/.gitconfig` includes, as in a Kaimon session, where every check that needs Metal
  runs, git exits 128 with `unable to access` before it reads the repository: the copy of the base
  failed with a rule-9 error, and `git status --porcelain` of the head returned no answer, so the
  check that a command left the head unchanged was skipped without a word. Both calls now repeat
  with `GIT_CONFIG_GLOBAL=/dev/null` on that error only. The first run keeps the user's
  configuration, because `git archive` applies its smudge filters (Git LFS); in the repeated run
  they do not apply. A case of `harness test` builds such a home and checks both runs.
