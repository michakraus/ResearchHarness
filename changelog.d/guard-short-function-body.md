- **The rm and work-tree checks end the body of zsh's short function definition where zsh ends
  it.** After `function f;`, `function f` and a newline, or `function f()`, zsh makes the whole
  next `&&` or `||` list the body, so `function f; true && cd .scratch/x || exit; rm -rf Papers`
  runs no `cd` and removes `~/Research/Papers` from `~/Research`; it passed, and is now refused,
  as are `function f; (true; true) && cd …`, `function f; g() true && cd …` and
  `f() repeat 1 true && cd …`. After a name and `()` without `function`, the body is one command,
  so zsh runs the `cd` of `f() X=1; cd .scratch/x && rm -rf build`; it was refused, and now
  passes. A body that holds a compound command or a backtick is read to the end of the command
  or of its parenthesis. K215 records that a `cd` in the list body of zsh's short `repeat`, as in
  `repeat 0 true && cd x || exit`, is still read as one that runs.
