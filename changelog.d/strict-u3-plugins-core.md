- **OpenCode's guard plugin and oh-my-pi's guard extension run the guard package, `hooks/guard/`,
  in place of their own path guards and the seven guard scripts.** Each plugin, now about 60 lines,
  sends each tool call to `<python> <its directory>/../hooks/guard --from opencode` or
  `--from omp`, with the interpreter that `harness install` writes under `python` into the
  `guard-paths.json` beside it, and applies the answer; a list without `python`, a guard that cannot
  start, exits non-zero, prints no valid answer or does not answer within 10 s refuses the call,
  and `python3` from the `PATH` is no longer run. The tables `frontends/opencode.py` and
  `frontends/omp.py` hold what the plugins checked: the path lists, OpenCode's list in
  `$OPENCODE_CONFIG_DIR`, its in-place edit refusal and its `rtk` form, oh-my-pi's own directory,
  hashline and patch headers and a sub-agent's write to `agent://`, which reads `Call.caller`
  (K120). The seven scripts (`no-blind-stage.py`, `no-shell-file-write.py`, `gh-api-writes.py`,
  `rm-scope.py`, `git-archive-output.py`, `sandbox-semantics.py`, `kaimon-session.py`) are
  removed, and `harness install` installs the package into both frontends; it deletes no file, so
  old copies of the scripts stay in their `hooks/` and nothing runs them. The decisions tighten in
  a few places, each a record of `tests/guard/corpus.jsonl` with its reason, and the forms of K14
  with a redirection, an assignment or `time` before a `cd` are refused. The Bash rules of the
  path list meet only the word lists that hold all their needed texts, so a crafted command of
  1 MiB costs 484 matcher calls where it cost 36,438,620.
