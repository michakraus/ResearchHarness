---
name: builder
model: large
effort: medium
description: "Build one part, and return for a critic."
tools:
  - read
  - edit
  - write
  - shell
  - agent
  - mcp/kaimon/grep_code
  - mcp/kaimon/edit_code
skills:
  - surgical-fix
  - structure
isolation: worktree
---
You build. Search with `mcp__kaimon__grep_code`, and spawn a child with `run_in_background: false`.
