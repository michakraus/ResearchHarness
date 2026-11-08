- **A `gh` watcher polls at most every 30 seconds.** The new guard check `gh_watch_interval.py`
  refuses a `gh run watch`, and a `gh pr checks --watch`, whose `-i` or `--interval` is missing
  or below 30 seconds, in every frontend, with the reason to add `--interval 60`. At `gh`'s
  default refresh of 3 seconds (`gh run watch`) and 10 seconds (`gh pr checks --watch`), two
  watchers on half-hour docs runs tripped GitHub's secondary rate limit; the REST Actions
  endpoints then answered 403 for every session of the account for more than 15 minutes, while
  `gh api rate_limit` still showed most of the core quota left. Every waiting command in
  `CLAUDE.md`, `julia-pr-shepherd`, `/review-pr`, `/merge-pr`, `build-part` and `build-reviewed`
  carries `--interval 60`, and `CLAUDE.md` and `ci-triage` say how to read a branch or a deploy
  with `git` while the limit holds.
