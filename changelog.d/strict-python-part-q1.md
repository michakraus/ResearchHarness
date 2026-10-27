- **The Python code follows a strict profile, which a new pre-commit hook, the pre-push hook and
  CI enforce.** `pyproject.toml` configures ruff at line length 110 with the rule families
  `E F W B BLE TRY PTH S UP SIM RET C4 PERF PL RUF ARG FBT DTZ N TID`, a ban of `os.system` and
  `os.popen`, and basedpyright in strict mode for Python 3.14. One commit formats the whole tree
  with `ruff format`, and `.git-blame-ignore-revs` names it. The safe fixes of `ruff check --fix`
  are applied; the remaining findings are recorded per file in `pyproject.toml`, and the strict
  errors in `.basedpyright/baseline.json`, so the checks pass and a module leaves the records when
  a change touches it. `.githooks/pre-commit` runs `ruff format --check`, `ruff check` and
  `basedpyright` on the staged files, with the tools of the harness's Python environment, and
  refuses a commit that fails one, or that it cannot check because the environment lacks a tool:
  set `develop = true` in the profile and run `harness install --apply`. The pre-push hook runs
  the same three checks on a push to `main`, and CI's new job `strict` runs them on every push and
  pull request. A case of `harness test` fails when a hook or a guard imports a module outside
  the standard library.
