- **The guard asks before a `git push` whose refspec deletes a remote ref, in place of two `ask`
  rules.** The rules `git push * :**` and `git -C * push * :**` made Claude Code print a warning
  at each start, because a `:*` stands before the end of each; the guard check
  `git_push_delete.py` asks on `:<ref>`, `+:<ref>` and a lone `:` in every frontend, with `-C`,
  after another part and inside `sh -c`.
