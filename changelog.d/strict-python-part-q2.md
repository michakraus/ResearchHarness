- **The type errors of standard mode, the `subprocess.run` calls without `check=` and the blind
  `except`s are fixed outside the guard files, and both records of the strict profile shrink.**
  Every `subprocess.run` names `check=`: `check=False` where the code reads the exit status or
  tolerates a failure, `check=True` where it relies on success. Each `except Exception` outside a
  test case's `case` helper names the exceptions it handles. `hooks/install-drift.py`,
  `hooks/prompt-log.py`, `lib/harness/fmt.py`, `lib/harness/frontends.py`,
  `lib/harness/script_cases.py`, `lib/harness/update.py` and the five tests of
  `examples/dotfiles/tests/` meet the whole profile and leave both records; the baseline goes from
  12,195 to 10,682 entries. `hooks/prompt-log.py` logs to a `LOG` with no directory part, such as
  `LOG=p.jsonl`, in the working directory, where it logged nothing before. The records rule in
  `pyproject.toml` and the development page is now the line rule: the lines that a change adds or
  changes meet the profile with both records removed, a new module is in neither, and a module
  leaves a record when its last entry there goes.
