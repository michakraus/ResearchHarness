- **The profile and `models.toml` load into frozen dataclasses, and a broken file stops the
  subcommand with one line that names the file, the key and the type.** An unknown key, a
  `[setup]` table among them, a missing required key, a value of the wrong type and an empty
  required list exit 2 before any other file is read; before, `harness get` accepted each of
  them, and a mistyped key read as missing. The required keys are `memory_project`, `tree_agents`,
  `org`, `repository_roots` and `leak`; every other key is optional with a default, and `harness`
  defaults to the running checkout. The loader refuses the retired keys `extra_domain`,
  `opencode_providers` and `omp_providers` for every subcommand that reads the profile.
  `harness install` checks the whole of `models.toml` before it plans any frontend: a table that
  no frontend reads, a key of `[claude]` or `[antigravity]` that is no tier, a `[claude]` without
  a tier and a value of the wrong type exit 2; each table is optional. `doctor` reports a profile
  without `tree_agents` as a FAIL of its `profile` check. `lib/harness/profile.py` passes
  basedpyright in strict mode and leaves the baseline; the readers in `lib/` and `adapters/` read
  attributes. `harness get develop` prints `true` or `false`; before, it ended in a traceback for
  `develop = true`. A profile that `harness get` loaded before can now stop with exit 2: run
  `harness get org` once after the update, and remove or rename each key that it names.
