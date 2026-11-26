- **The git write and push-deletion checks read `GIT`, a redirection before the subcommand, and a
  subcommand that the shell expands or an alias option names.** `git 2>&1 push`, `GIT push` (which
  macOS runs as git) and `git pus{h,}` passed both checks, so a lease push to `main` or a deleting
  refspec went through with no prompt. The checks now skip a redirection's target, read the
  program name in any case, and ask for a call whose subcommand they cannot know (`$`, a backtick,
  a brace or a glob in it, or a `-c alias.*` option), while a lease push to a default branch is
  still refused. K195, K196 and K197 name the forms that stay open.
