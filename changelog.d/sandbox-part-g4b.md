- **`harness install` writes the Claude Code settings for `claudex` too.** `claudex` runs Claude
  Code with `CLAUDE_CONFIG_DIR=~/.config/claudex`, where Claude Code reads its own
  `settings.json`. The install now merges the settings template into
  `~/.config/claudex/settings.json` as into `~/.claude/settings.json`, right after it and before
  the other files of the layer, so that the same hooks, permissions and sandbox hold there. In
  both files, each deny rule on a path below `~/.claude/` or on `~/.claude.json` gets a twin below
  `~/.config/claudex/`, which also covers the two rules on `**/.claude/settings*.json`, and the
  sandbox's read denies of `~/.claude.json`, `~/.claude/backups` and
  `~/.claude/.credentials.json` get theirs: the denies hold for the second name of each file. Run
  `harness install --apply` to write the new file.
