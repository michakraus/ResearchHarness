- **Worktrees work under `agentbox`: a broker outside `srt` runs the worktree hook's `git`.**
  `srt` denies writes to every `.githooks`, so `git worktree add` failed inside it, and no
  `isolation: "worktree"` agent and no `EnterWorktree` worked. `agentbox` now starts
  `worktree.py --serve` outside `srt`, with its socket in `~/.local/state/research-harness/broker`,
  and exports the socket as `AGENTBOX_BROKER`; each frontend's `srt` settings allow a connection
  there in `network.allowUnixSockets`. With `AGENTBOX` set, the hook sends its payload to the
  broker and runs no `git`, and it fails closed without a broker. Either way the hook now finds the
  repository by reading files, below `~/Research` only, refuses a `.git` link, a linked worktree
  whose admin files are not git's, and a worktree path that is a link, and gives every `git`
  `-c core.hooksPath=/dev/null -c core.fsmonitor=false`, so no hook of the repository runs. A
  `git pull`, `switch` or `rebase` that changes `.githooks/` still fails under `agentbox`.
