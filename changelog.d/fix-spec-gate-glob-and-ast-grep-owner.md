- **`spec-gate.py` reads a glob in a part's Files as no repository, and a change under
  `ast-grep/` selects only the `docs` part of `harness test --changed`.** A path such as
  `~/Research/**/.githooks` made the part SPANS `**`, a repository that does not exist; a path
  whose repository segment is a glob now counts as the part's own. A path under `ast-grep/` had no
  owner and selected every part, although only `docs` reads those files; the rule tests run in the
  Julia workflow.
