- **`gh pr create` in an own organisation and `gh api graphql` with a query in a file no longer
  ask.** The new guard check `gh_pr_create.py` reads every `-R` and `--repo` of a `gh pr create`
  or its alias `gh pr new` in every frontend: it lets a call through when each names an own organisation, asks for any
  other repository, and refuses a call with none, with the reason to add `--repo <owner>/<repo>`.
  oh-my-pi's final `prompt` pattern `gh pr create*` is gone, so under oh-my-pi an own-organisation
  call runs also inside a pipe or after `&&`, where the pattern had asked, and a sub-agent, which
  has no prompt, had to hand the command to its caller. The settings template allows
  `gh pr create * -R <org>/*` and `* --repo <org>/*` in place of the two `ask` rules for a
  repository flag after the first argument. The `gh api` check reads the query of
  `-F query=@<file>` and of `--input <file>.json` and decides it as an inline query; it asked for
  each before, 25 prompts in four weeks for read-only queries and review-thread replies. A query
  that it cannot read still asks, and so does a query file whose name another part of the same
  command holds, which could write the file before `gh` reads it.
