- **The rm and work-tree checks read a `cd` that can fail, or that a shell runs in a child, in
  both directories.** `cd ~/Research/.scratch/missing; rm -rf Papers` from `~/Research` passed,
  and removes `~/Research/Papers` when the `cd` fails; so did `cd x | true; rm -rf …` and
  `command cd .scratch/x && rm -rf Papers`, which zsh runs in a child. The checks now read the
  commands after a `cd` that `&&` does not join to the next command, and after `command cd` or
  `time cd`, in the directory before it and after it; a `cd` that `|| exit` follows stays
  sure, and a `popd` returns to the directory before its `pushd`. A recursive `rm`
  of a relative path after a `cd` to a directory that the check cannot know, such as `cd $X`,
  asks, and the work-tree check follows `pushd`. This closes K200, K201 and K202.
- **The git write and push-deletion checks read an alias in a command that they cannot read, and
  after a `cd` to a directory that they cannot know.** `git sh`, with `alias.sh = !git push`,
  passed after a heredoc whose body holds an open quote, and `cd $D && git p --force-with-lease
  origin feature` passed when `$D` defines `alias.p = push`. The checks now look the alias up in
  the call's working directory for such a command, and read a name that is no builtin as unknown
  after a `cd` to an unknown directory. This closes K198 and K199.
- **The rm and work-tree checks read a sure `cd` only up to the end of its scope.** `cd
  ~/Research/.scratch/x && true; rm -rf Papers`, `(cd … && true); rm -rf Papers`,
  `cd … && true & rm -rf Papers`, `true || cd … && rm -rf Papers` and `echo | cd … && rm -rf
  Papers` passed from `~/Research`, and each can remove `~/Research/Papers`. A `cd` is now sure
  for the rest of its `&&` list, for every command after `cd x || exit`, and for the `then` of
  `if cd x`; after that, and after `||` or a pipe before the `cd`, the checks read the directory
  before it too. `if cd x; then rm -rf y; fi` now passes. The checks follow a `cd` behind zsh's
  `noglob`, `nocorrect` and `-`, and read a `pushd` with no operand as a swap of the top two
  directories. This closes K203 and K205 to K210; K211 records that a `{ … }` group ends the
  `&&` list early, which errs toward a refusal.
- **The guard reads a command once for all its checks.** The readings of a command and its
  simple commands are kept for the checks after the first, and the path list splits a command
  once for its two rule lists. The 1 MiB `[mib-rules]` case of `probe:antigravity` took more than
  10 s on the CI runners; on a local machine it takes 3.0 s, against 4.1 s on `main`.
