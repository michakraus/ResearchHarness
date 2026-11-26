- **The rm and work-tree checks read a `cd` that can fail, or that a shell runs in a child, in
  both directories.** `cd ~/Research/.scratch/missing; rm -rf Papers` from `~/Research` passed,
  and removes `~/Research/Papers` when the `cd` fails; so did `cd x | true; rm -rf …` and
  `command cd .scratch/x && rm -rf Papers`, which zsh runs in a child. The checks now read the
  commands after a `cd` that `&&` does not join to the next command, and after `command cd` or
  `time cd`, in the directory before it and after it; a `cd` that `|| exit` or `|| return`
  follows stays sure, and a `popd` returns to the directory before its `pushd`. A recursive `rm`
  of a relative path after a `cd` to a directory that the check cannot know, such as `cd $X`,
  asks, and the work-tree check follows `pushd`. This closes K200, K201 and K202.
- **The git write and push-deletion checks read an alias in a command that they cannot read, and
  after a `cd` to a directory that they cannot know.** `git sh`, with `alias.sh = !git push`,
  passed after a heredoc whose body holds an open quote, and `cd $D && git p --force-with-lease
  origin feature` passed when `$D` defines `alias.p = push`. The checks now look the alias up in
  the call's working directory for such a command, and read a name that is no builtin as unknown
  after a `cd` to an unknown directory. This closes K198 and K199.
