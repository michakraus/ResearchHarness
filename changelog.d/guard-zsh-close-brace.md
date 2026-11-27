- **The rm and work-tree checks read zsh's `}` at the end of a word as the end of a group (K217).**
  zsh closes a group at a `}` that ends a word or the target of a redirection, so
  `repeat 0 { true; cd .scratch/x } && rm -rf Papers`,
  `if false; then { cd .scratch/x } fi && rm -rf Papers`, `repeat 0;` and a newline before
  `{ cd .scratch/x && true } | rm -rf Papers`, and `repeat 0 { true; cd .scratch/x >/dev/null} &&
  rm -rf Papers` run no `cd` and remove `~/Research/Papers` from `~/Research`; they passed, and
  are now refused. Once a word that starts with `{` has come, no `cd` right before such a `}` is
  sure, and the `&&` list of a `cd` ends at it. zsh also opens a group at a word that starts with
  `{`, so `false && {true; cd .scratch/x || exit; }; rm -rf Papers` passed, and is now refused.
  The check matches no `{` with a `}`, since it cannot tell a quoted brace from a bare one, so
  `cd .scratch/x && { true } && rm -rf build`, `cd .scratch/x && echo {a,b} && rm -rf build` and
  `cd .scratch/x && awk '{print $1}' f && rm -rf build` passed, and are refused now.
