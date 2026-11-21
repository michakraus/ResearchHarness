- **The worktree broker of `agentbox` runs every `git` inside `srt`, through a staging directory.**
  A program in the box could rename a repository's `.git` away and put another in its place
  between the config check and the read of `git` itself, so a config that the box chose ran
  outside `srt` in the broker's `git fetch`, `git worktree add` or `git worktree remove` (K177).
  `agentbox` now starts the broker with `--settings` and the frontend's own `srt` settings file.
  The broker makes `~/.local/state/research-harness/worktree-stage/<pid>` with mode 700 and the
  profile `<pid>.json` with mode 600, that settings file with the staging directory added to its
  writes, and starts each child as `worktree.py --boxed <profile>`, which runs every `git` as
  `~/.local/bin/srt --settings <profile> -- git …`. A create adds the worktree in the staging
  directory, renames it into `~/Research/.worktrees` without `git`, and repairs it; a remove
  renames it into the staging directory, repairs and removes it there, and puts it back where `git`
  refuses. The staging directory and `~/Research/.worktrees` must lie on one device, and nothing is
  copied. A failed step removes only what the child made and prunes the worktree. A
  `WorktreeRemove` whose `worktree_path` is no string now gets a one-line refusal.
