- **The hooks, CI and the pre-push hook run on the harness's Python environment.**
  `harness install` writes the command of each Python hook in `~/.claude/settings.json` and in
  Antigravity's `hooks.json` as the environment's interpreter, by its absolute path, then the
  hook, each one shell word, so a hook no longer runs on whatever `python3` comes first on the
  `PATH`, and a home path with a space no longer splits a command. Each hook keeps its shebang
  `#!/usr/bin/env python3` for a run by hand. Under Claude Code a guard whose environment is
  missing fails to start, and Claude Code lets the tool call go on. CI's job `python` installs
  uv 0.13.5 with a pinned `astral-sh/setup-uv`, runs `uv sync --locked --no-dev` into the
  environment that `bin/harness` reads, writes its stamp, and runs the suite and the compile check
  on it; the job on the latest 3.x only warns. The pre-push hook runs `bin/harness test` once, in
  place of a second run on `python3.14`, and the compile check on the environment's interpreter.
