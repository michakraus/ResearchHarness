- **The rm and work-tree checks end the body of zsh's short function definition where zsh ends
  it.** After `function f;`, `function f` and a newline, or `function f()`, zsh makes the whole
  next `&&` or `||` list the body, so `function f; true && cd .scratch/x || exit; rm -rf Papers`
  runs no `cd` and removes `~/Research/Papers` from `~/Research`; it passed, and is now refused,
  as are `function f; (true; true) && cd …`, `function f; g() true && cd …` and
  `f() repeat 1 true && cd …`. After a name and `()` without `function`, the body is one command,
  so zsh runs the `cd` of `f() X=1; cd .scratch/x && rm -rf build`; it was refused, and now
  passes. A body that holds a `{ … }` group, an `if` or a `do … done` ends after its closing
  word, so `f() { true; }; cd .scratch/x && rm -rf build` still passes; a body that holds
  another compound command or a backtick is read to the end of its parenthesis. No `cd` in a
  group or an `if` of a body is sure either: zsh closes
  `f() { cd .scratch/x && true } && rm -rf Papers` without a `;` and runs the `rm` in
  `~/Research`, which passed; it is refused now, and so is `f() { cd x && rm -rf y; }`. zsh's
  short `repeat` runs the whole list after its count as its body, also never, so
  `repeat 0 true && cd .scratch/x || exit; rm -rf Papers` runs the `rm` in `~/Research`; it
  passed, and is now refused, and so is
  `repeat 0 >/dev/null && cd .scratch/x || exit; rm -rf Papers`, whose body starts with the
  redirection. The checks read the command after a `repeat` and its count:
  `repeat 1 rm -rf Papers` from `~/Research` and `repeat 1 cd ../..; rm -rf Papers` from a
  directory two levels below it passed, and are refused now; `repeat 0 do true; done; cd x ||
  exit; rm -rf build` was refused, and passes now. After `;` and newlines, zsh's short `repeat`
  takes the next list as its body, unless it starts with `do` or `{`: `repeat 0;` and a newline
  before `true && cd .scratch/x || exit; rm -rf Papers` passed, and is now refused, while
  `repeat 0; do true; done; cd x || exit; rm -rf build` still passes. The checks read the
  command after `time` and after a nested `repeat`, and a `case` after a `repeat` and its count:
  `time repeat 1 rm -rf Papers`, `repeat 1 repeat 1 rm -rf Papers` and
  `repeat 0 case a in a) true;; esac && cd .scratch/x || exit; rm -rf Papers` passed, and are
  refused now.
