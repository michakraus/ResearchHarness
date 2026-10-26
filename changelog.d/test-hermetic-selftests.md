- **The selftests read `skills/` and `rules/` of the repository by the install's own rule, and CI
  runs the suite once more with an empty `HOME`.** Two Antigravity cases listed `skills/` with
  `iterdir()`, so a hidden directory there that `.gitignore` ignores, such as the `.claude/` that
  Claude Code leaves in a checkout, counted as a skill that the install skips, and the two cases
  failed on that checkout and passed in CI. The new helpers `skill_names` and `rule_names` of
  `lib/harness/install_cases.py` read a directory through `install.source_files`, which skips
  hidden names, and the Antigravity and oh-my-pi cases use them. The new `empty-home` job of CI
  runs `bin/harness test` on Python 3.11 with `HOME` set to a new empty directory.
