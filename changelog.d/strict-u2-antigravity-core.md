- **Antigravity runs the guard package, `hooks/guard/`, in place of its own guard hook.** Its
  `hooks.json` runs `<python> ~/.gemini/config/hooks/guard --from antigravity` on every tool call,
  and `harness install` copies the Claude Code layer's guard package to
  `~/.gemini/config/hooks/guard/`; it no longer installs `config/hooks/guard.py` or the seven guard
  scripts there, and deletes neither: `harness install` lists the old copies as extra files, and
  nothing runs them. A table `frontends/antigravity.py` maps each tool onto a neutral action; the
  path list `guard-paths.json` is a check of the package, `path_list.py`, which reads a command
  without `shlex`; and the sandbox lift is the check `sandbox_lift.py`, which lifts a command only
  where the whole line matches a closed grammar and Claude Code's sandbox rule lifts it. The guard
  answers as before, `deny`, `force_ask` for an ask and `ask` for a pass, and a `run_command` that
  it does not deny carries the `BypassSandbox` of the lift. It spawns no guard script, so a command
  of 1 MiB is decided within the 15 s of `hooks.json` with no program spawned but `git`. Its
  decisions tighten in a few places, each a record of `tests/guard/corpus.jsonl` with its reason:
  `multi_replace_file_content` meets the `edit` and `ask` lists (K87, and that half of K103); a
  `#` inside a word, a backslash-newline inside a word and a comment that ends in one are read as
  the shell reads them (K89, K90, K91); a command of more than 1 MiB, or one that holds a lone
  surrogate, is refused; and a call with no workspace path has no working directory, so a relative
  path of it, a relative word of a command among them, is refused. A record of
  `rm -rf '/\<newline>'` covers the backslash-newline inside single quotes (K93).
