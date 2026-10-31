- **Every JSON read goes through `jsonio`, every merge into a file another program owns through
  `ownedjson`, every secret write through `write_private`, and every `subprocess.run` names a
  timeout.** A key twice in one object, a `NaN` or a deep nesting is now refused at each read
  with a message that names the text and the line, where `json` kept the last value, read the
  constant or raised `RecursionError`; ruff bans `json.load` and `json.loads` outside the two
  copies of `jsonio` and the dotfiles kit's tests.
  `jsonio.loads` takes `top=` for a top level that is an array, a string or any value. The merges
  of Claude Code's `settings.json`, `~/.claude.json` (`harness trust`), and Antigravity's CLI
  settings, `config.json` and `mcp_config.json` keep every byte that they do not change: a
  minified `config.json` stays minified and is no longer replaced at each install (K102), a key
  twice in `config.json` exits 2 before anything is written (K101), a number that `json` writes in
  other text no longer stops the merge, a key twice inside the Kaimon entry of `mcp_config.json`
  now exits 2, and `harness trust` writes a symlinked `~/.claude.json` through to its target. A
  file with a mode, and a backup, are written with their mode from the first byte (K94), and the
  install refuses such a target whose directory it cannot write. Each `subprocess.run` names
  60 s for a local program, 300 s for one that reaches the network, or `# no timeout: <reason>` for
  a long run; `harness` turns a program past its timeout into one line and exit 2, the bootstrap's
  `uv sync` into a refusal, and `harness test --changed` no longer waits on a `git diff` that does
  not end (K110). `lib/harness/strict.py` holds the timeouts and refuses a `chmod` to a private
  mode after a file write outside `fsutil.py`.
