- **`dependents.jl` is formatted in the SciML style of the packages.** A base package's
  pre-commit hook refused to commit the installed copy, because one line exceeded the margin. A
  case of `harness test githooks` checks the format of the template.
