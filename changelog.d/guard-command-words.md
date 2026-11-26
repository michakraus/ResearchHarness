- **The guard's shell checks find a program behind a prefix word, inside a compound command or a
  substitution, after a redirection, and in any case.** `env git add -A`, `sudo rm -rf …`,
  `rtk gh api -X DELETE …`, `if true; then git add -A; fi`, `echo $(rm -rf …)`,
  `2>&1 julia -e 'using Metal'`, `GIT add -A` and `RM -rf …` passed the staging, rm, `gh api`,
  `gh pr create`, watcher, archive, write and GPU checks, each of which looked for its program as
  the first word of a part. One reader, `shell.commands`, now gives every check each simple
  command from its command word on: past reserved words, assignments and wrappers such as `env`,
  `sudo`, `xargs`, `time` and `rtk`, with `( … )`, `$( … )`, backticks and the string of `env -S`
  read as commands of their own. The rm and work-tree checks move their directory only for the
  shell's own `cd`, also after an assignment, `command`, `builtin` or `time`; `CD`, `env cd`,
  `sudo cd` and `nohup cd` run `/usr/bin/cd` in a child. The staging check also refuses `./.` and `.//`, the rm check
  reads `--r` as `--recursive`, the write check reads `<>` as a write, and the work-tree check of
  the other frontends reads `g''it init`, `GIT init` and `env git init`. This closes K114, K116,
  K117, K118, K122, K150, K194 and K195.
- **The git write and push-deletion checks read an alias of the git configuration and of a
  `GIT_CONFIG_*` variable.** `git p --force-with-lease origin main` with `alias.p = push` in the
  repository's config, and the same push after `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p
  GIT_CONFIG_VALUE_0=push`, passed with no prompt. The checks now look up a subcommand that is no
  builtin with `git config` in the repository of the call's part, follow it through at most four
  aliases, and read it as unknown when it can run a write; `git lg` with `lg = log --oneline`
  still passes. A command that the checks cannot read asks also for a lease option after `git`,
  and for an expanded subcommand after global options or a redirection, as in
  `git -C . pus{h,}`, while `git -C $dir log` in a Julia heredoc passes. This closes K196 and
  K197; K198 and K199 name the forms that stay open.
- **A quote in a heredoc body no longer hides the lines after the heredoc from the shell checks.**
  In `cat <<EOF`, a body `it's`, `EOF`, `git push --force-with-lease origin main` and `echo '`,
  the quote of `it's` closed at the last line, so the push passed. `shell.readings` now also reads
  the command without its heredoc bodies, with an open quote closed at its end, so the push is
  refused, and the sandbox check refuses a `git` write behind such a heredoc.
