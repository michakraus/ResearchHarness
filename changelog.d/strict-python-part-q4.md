- **`harness mutate SPEC` runs named mutants of the Python code.** The spec is a TOML file with
  one table per mutant: `file`, an `anchor` text on one line of it, an `old` text that occurs once
  after that line, its `new` text, and the `tests` parts of `harness test` that should kill it.
  Each mutant is applied alone to a scratch copy of the checkout, which is a git repository, runs
  `harness test` with its parts and is reverted; the command prints `killed`,
  `killed (timeout)`, `SURVIVED` or `invalid` (a mutated file that `ast.parse` refuses) per
  mutant, and exits 1 when one survives or is invalid. A spec that cannot be applied, or a copy
  that fails the spec's parts unmutated, stops the run with exit 2 before any mutant runs. The
  checkout and its `.git` stay as they are. A named mutant no longer has to be applied and
  reverted by hand.
