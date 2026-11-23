- **`edges.md` names a shell mutant whose symptom the spec reasons from another shell.** zsh does
  not split an unquoted `$*`, so the mutant that writes `$*` for `"$@"` keeps `a b` whole and drops
  only an empty argument; the line asks the builder to run each shell mutant in the shell that reads
  the code, and to give the case an empty argument.
