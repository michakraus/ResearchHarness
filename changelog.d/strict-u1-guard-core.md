- **Claude Code runs one guard program, `hooks/guard/`, in place of the eight guard scripts.** On
  the `Bash` matcher, the directory and worktree tools and the Kaimon tools, the settings template
  runs `<python> ~/.claude/hooks/guard --from claude || exit 2`; the `Bash` group keeps
  `rtk hook claude` first, and the Edit matcher keeps `edit-scope.py`. The guard turns the payload
  into a neutral call, runs one module per check, and answers the first of `deny`, `ask`, `allow`
  and `pass` with the reason of the check that gave it, so a payload where one check asks and
  another refuses is refused. It fails closed where the scripts failed open: it refuses a payload
  that is not UTF-8 or not a JSON object, one without a `tool_name` or a readable `tool_input`, a
  command of more than 1 MiB, a command whose check must resolve a path against a working
  directory that the payload does not name (a relative write target, a recursive `rm` of a
  relative path, a `git rm` or `git merge`, a `git init` or `git clone`), and a call on which it
  raises; a guard that cannot start refuses the call through `|| exit 2`. It reads a command
  without `shlex`: a `#` inside a word and a backslash-newline are read as the shell reads them. It
  decides a command of 1 MiB within the hook's 5 s timeout, a chain of `cd` and many `rm` operands
  among them, and stops at the first check that refuses. `tests/guard/corpus.jsonl` holds 429
  payloads, each case of the scripts' probe among them, and the probe's `commands` group runs them
  through the guard; each payload that the guard decides otherwise than the scripts names its
  reason there, and none is decided more loosely. `hooks/directory-scope.py` is removed; the seven
  scripts that oh-my-pi, OpenCode and Antigravity run stay as they are.
