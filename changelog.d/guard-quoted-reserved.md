- **The rm and work-tree checks read a quoted or escaped reserved word as the shells do: as a
  program, which opens and closes nothing (K220).** `false && { true; "}"; cd .scratch/x || exit;
  }; rm -rf Papers` skips the whole group, whose `"}"` is a command and not its end, and runs the
  `rm` in `~/Research`; the checks read the `"}"` as the end of the group and the `cd` as sure,
  so the command passed, and is now refused. The same holds for `! "}" || cd .scratch/x && rm -rf
  Papers`, for `\}`, `''}`, `"fi"`, `\fi`, `"done"` and `d\one`, and for a quoted `"time"` before
  a reserved word. A backslash-newline quotes nothing, so `{ true; \` and a newline before `}`
  still closes the group. A quoted word reads as the same text everywhere else, as a path or the
  name of a program: `"cd" .scratch/x && rm -rf build` still passes and `'rm' -rf Papers` is still
  refused. `"time" fi; cd .scratch/x || exit; rm -rf build`, where both shells run the `cd` and
  the `rm` in `.scratch/x`, was refused and now passes.
