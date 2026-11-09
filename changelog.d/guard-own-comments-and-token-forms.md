- **The `gh api` check passes a review or a comment only in an own organisation, and a new token
  check refuses a call that holds a token of a known form.** A `gh api` review, inline comment,
  reply, or comment on a pull request, an issue or a commit now asks unless its endpoint is
  `repos/<owner>/<repo>/…` with an owner of the profile's `org` list and the call names no
  `--hostname`; a `{owner}` placeholder, an encoded or dotted owner and a missing profile ask too.
  GraphQL review mutations pass as before. `hooks/guard/token_forms.py` refuses a shell command, a
  web call or a Kaimon call that holds a GitHub (`gh[pousr]_`, `github_pat_`), GitLab (`glpat-`) or
  `sk-` token, as it is or percent-decoded, on every frontend. Both checks prevent an accident: an
  agent could post a secret in a comment on any public repository with no prompt, and a pasted
  token left the machine with the call. Neither is a boundary against a session that sends a
  secret out.
