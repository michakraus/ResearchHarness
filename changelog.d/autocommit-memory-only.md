- **`claude-autocommit` commits `projects/*/memory/` only, and no longer `plans/`.** A plan-mode
  file is one session's by-product, and a plan worth keeping belongs in a task file; the subject
  of an automatic commit now reads `chore(auto): N memory file(s) — <date>`.
