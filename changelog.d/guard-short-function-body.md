- **The rm and work-tree checks end the body of zsh's short function definition where zsh ends
  it.** After `function f;`, `function f` and a newline, or `function f()`, zsh makes the whole
  next `&&` or `||` list the body, so `function f; true && cd .scratch/x || exit; rm -rf Papers`
  runs no `cd` and removes `~/Research/Papers` from `~/Research`; it passed, and is now refused.
  After a name and `()` without `function`, the body is one simple command, so zsh runs the `cd`
  of `f() X=1; cd .scratch/x && rm -rf build`; it was refused, and now passes.
