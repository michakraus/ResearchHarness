- **The wiki lint is `harness wiki-lint`, in Python, and the prose repositories' hook is Python
  too.** `lib/harness/wikilint.py` replaces `scripts/wiki-lint.jl` with the same checks, messages,
  line format, totals and exit statuses; over the four prose trees it prints the same output and
  runs in about a second, where the Julia program took about 3.6 s. It reads the
  frontmatter with PyYAML, the harness's first runtime dependency, through a `SafeLoader` that
  refuses a duplicate key (an ERROR on the key's line) and warns on a value that YAML 1.1 converts,
  such as `draft: no`; a block that does not parse is an ERROR on PyYAML's line, and `verified:`
  is a `YYYY-MM-DD` text, so `2026-9-1` is an ERROR. `githooks/pre-commit-wiki` runs
  `harness wiki-lint --quiet`, and in a repository whose staged `pyproject.toml` holds
  `[tool.ruff]` also `ruff format --check`, `ruff check` and `basedpyright`. Run
  `harness install --apply` to add PyYAML to the environment, then `harness wiki-lint-hook --apply`
  to install the hook.
