- **`launchagents/claude-autocommit` and `.githooks/pre-push` are Python programs, standard library
  only, with the behaviour of the bash scripts that they replace.** The script keeps its options,
  environment variables, exit statuses, lines, lock, commit message and commit by pathspec, writes
  no temporary file, and removes its lock on a SIGTERM too. A SIGTERM goes on to the running git,
  which removes its own `index.lock`, and the run ends after that git. It now refuses a value of
  `CLAUDE_AUTOCOMMIT_QUIESCE_MIN`, `CLAUDE_AUTOCOMMIT_MAX_DELETIONS` or `CLAUDE_AUTOCOMMIT_PUSH`
  that is not an integer, and a run without git, with one `ERROR:` line and exit 1, and a git
  command that takes longer than 10 minutes gets a SIGTERM and ends the run with one `ERROR:` line
  and exit 1. A path whose name is not UTF-8 is printed as its bytes in every locale. The plist and
  the systemd unit run it on the interpreter of the harness's Python environment,
  `~/.local/share/research-harness/python/bin/python`, and CI's job `systemd` verifies the unit
  against the environment that its render makes.
  Python cases of `harness test`, in `lib/harness/autocommit.py`, replace
  `launchagents/claude-autocommit-test.jl`, with its seven cases under their titles and 36 more,
  so the script's tests run on every machine without Julia; julia.yml drops the file and its
  `launchagents/**` trigger. The pre-push hook runs its checks in the same order with the same
  lines, parses as Python 3.9, so that the `python3` of macOS refuses a push with the hook's own
  line, and refuses a push whose git, gitleaks or tool run takes longer than an hour. A program
  that it cannot start prints one line and fails its check, and a SIGTERM or a SIGHUP removes its
  clone, as the bash hook did. A push
  without any `python3` on the `PATH` now fails with git's own message, as the hook cannot start.
  ruff checks both files, and shellcheck no longer reads them.
