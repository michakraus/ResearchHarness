- **`harness` runs on a Python environment of its own, made by uv from a committed `uv.lock`,
  and needs Python 3.14.** `bin/harness` refuses a Python below 3.14 with one line. Its first run
  outside a session runs `uv sync --locked --no-dev` into
  `~/.local/share/research-harness/python/` (`$RESEARCH_HARNESS_PYTHON`), and every command then
  runs on that environment's interpreter: `bin/harness` starts itself there with the same
  arguments. uv comes from the `PATH`; on Linux without it, `bin/harness` fetches the pinned uv
  0.13.5 into `~/.local/bin` and checks its sha256. A session never runs uv: without the
  environment it runs the command on the current interpreter and prints one line that names
  `harness install --apply`. `harness install` plans the environment as one line, `python
  environment`, and `--apply` syncs it, with the `dev` group of ruff and basedpyright where the new
  profile key `develop = true` is set. `harness doctor` checks the environment and uv, and its
  minimum of Python is 3.14. CI and the pre-push hook run `bin/harness` on 3.14 in place of 3.11.
