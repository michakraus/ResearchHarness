- **The rm and work-tree checks read no `cd` of zsh's short function definition as sure, and
  read a `case` pattern as no command.** In zsh, `f() cd .scratch/x && rm -rf Papers`,
  `f() cd .scratch/x || exit; rm -rf Papers`, `f() ; cd …`, `function f; cd …` and
  `env() cd …` define a function and run no `cd`, so the `rm` removes `~/Research/Papers` from
  `~/Research`; each passed. The checks now read the commands after such a `cd` in the directory
  before it too, so each is refused; an anonymous `() cd x`, which zsh runs at once, stays sure.
  This closes K213. A pattern of a `case`, as in `b)` or `(b|c)`, now runs nothing and opens and
  closes no parenthesis: the `)` of `b)` ended the scope of a sure `cd` before it, so
  `cd .scratch/x && case a in b) rm -rf c;; esac` was refused and now passes.
