- **The guard's shell checks find a program behind a prefix word, inside a compound command or a
  substitution, after a redirection, and in any case.** `env git add -A`, `sudo rm -rf …`,
  `rtk gh api -X DELETE …`, `if true; then git add -A; fi`, `echo $(rm -rf …)`,
  `2>&1 julia -e 'using Metal'`, `GIT add -A` and `RM -rf …` passed the staging, rm, `gh api`,
  `gh pr create`, watcher, archive, write and GPU checks, each of which looked for its program as
  the first word of a part. One reader, `shell.commands`, now gives every check each simple
  command from its command word on: past reserved words, assignments and wrappers such as `env`,
  `sudo`, `xargs`, `time` and `rtk`, with `( … )`, `$( … )`, backticks and the string of `env -S`
  read as commands of their own. The staging check also refuses `./.` and `.//`, the rm check
  reads `--r` as `--recursive`, the write check reads `<>` as a write, and the work-tree check of
  the other frontends reads `g''it init`, `GIT init` and `env git init`. This closes K114, K116,
  K117, K118, K122, K150, K194 and K195.
