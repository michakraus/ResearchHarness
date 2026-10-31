---
paths: ["**/*.py"]
description: The idioms of the strict Python profile, each with the tool that enforces it.
---

# Working on Python code here

The Harness sets the strict profile in its `pyproject.toml`, and its pre-commit hook runs the
three checks on every commit: `ruff format --check`, `ruff check` and `basedpyright`. A repository
that sets the same profile follows the same idioms. Each idiom below names the tool that enforces
it; "review" means that the critic checks it and no tool does.

## The checks

- **One layout: `ruff format`.** Run it before you stage; the hook only checks. Never format by
  hand against it.
- **`ruff check`** runs the rule families of `pyproject.toml`. Fix a finding; do not add a
  `# noqa` or a per-file ignore for a line that you write.
- **Strict typing: `basedpyright`** in strict mode. New code is strict from its first commit: the
  lines that you add or change meet the profile with the generated records removed, the ruff
  per-file table and `.basedpyright/baseline.json`. A new module is in neither record. Write the
  records again with the fix that shrinks them, never to admit a new finding.

## The idioms

- **A dataclass at every input boundary** (review; `basedpyright` flags each value of unknown
  type that its absence leaves). Parse JSON, TOML, a hook payload or a
  command line once, where it enters, into a frozen `dataclass` with typed fields; the code behind
  it reads fields, never `dict` keys of unknown type.
- **`pathlib` for paths** (`ruff check`, `PTH`). No `os.path`, and no string joins of paths.
- **`subprocess.run` names `check=`** (`ruff check`, `PLW1510`), sets `text=True` where it reads
  text, and sets a `timeout=`, or carries `# no timeout: <reason>` on the line where it starts
  (`harness test`, the `untimed_runs` case of `lib/harness/strict.py` in the Harness). Pass a list
  of arguments, never `shell=True` (`ruff check`, `S`).
- **A failure that the user must read raises `HarnessError`** (review), with one line that names
  the cause; the command's entry point catches it and exits 2. No `sys.exit` deep in a module, and
  no traceback as a message to the user.
- **No blind `except`** (`ruff check`, `BLE001`). Catch the exception that you expect, at the call
  that raises it, and let every other one propagate.
- **Banned APIs** (`ruff check`, `TID251`, the `banned-api` table of `pyproject.toml`): `os.system`
  and `os.popen`, which run a shell; run a program with `subprocess.run`. `json.load` and
  `json.loads`, which keep the last value of a key held twice, read `NaN`, and raise
  `RecursionError` on a deep nesting.
- **JSON enters through one reader** (`ruff check`, `TID251`): `harness.jsonio`, and
  `guard.jsonio` in a hook, refuse each of these with a `HarnessError`. One loader per kind of file
  returns the dataclass (review), not a call in each function that needs a value.
- **No decision of a guard rests on `shlex`** (review): it splits as POSIX `sh` does, not as the
  shell that runs the command, so a split that passes can still run something else.
- **A secret file is written by one helper** that creates it with mode `0600`, `write_private`
  where the repository has it; never `write_text` followed by `chmod`, which leaves the file
  readable in between (`harness test`, the `chmods_after_writes` case of `lib/harness/strict.py`
  in the Harness).
- **Hooks and guards import only the standard library** (`harness test`, a case of
  `lib/harness/strict.py` in the Harness).

## Tests

- **A test is a case of `harness test`** in the Harness: a selftest of the module, run in a process
  of its own. Run the parts that your change reaches while you edit, and the full suite once before
  you report.
- **A named mutant runs with `harness mutate <spec>`**, which applies it to a copy and runs the
  parts that must kill it. A mutant that survives shows a test that does not test what it claims.

`docs/src/development.md` of the Harness gives the reason for each idiom.
