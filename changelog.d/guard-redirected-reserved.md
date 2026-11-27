- **The rm and work-tree checks read a reserved word after a redirection in its part also as
  bash does: as a program, which opens and closes nothing (K222).** bash reads a reserved word
  only where a command word can stand, so `false && { true; >/dev/null }; cd .scratch/x || exit;
  }; rm -rf Papers` skips the whole group, whose `}` is a command and not its end, and runs the
  `rm` in `~/Research`; the checks read the `}` as the end of the group and the `cd` as sure, so
  the command passed, and is now refused. The same holds for `2>&1 }`, `<<<x }`,
  `>/dev/null time }`, `>/dev/null fi`, `>/dev/null done` and `>/dev/null case x in a | rm -rf
  Papers`. zsh runs the redirection as a command of its own and reads the word after it as
  reserved, so the checks keep that reading too and answer the stronger decision of both.
  `{ true; } >/dev/null; cd .scratch/x || exit; rm -rf build` still passes.
