---
paths: ["**/KNOWN_ISSUES.md"]
description: What a repository's KNOWN_ISSUES.md holds, the form of an entry, and when an entry comes and goes.
---

# The known-issues file

`KNOWN_ISSUES.md` sits at the root of a repository under `~/Research`, beside `README.md` and
`CHANGELOG.md`. It holds the current state of what is known to be wrong and not
fixed, in the present tense.

- **What goes in:** every finding with evidence that its pull request does not fix. A pure style
  remark that a formatter or a lint check fixes stays out.
- **A defect that the branch causes stays out.** A CHANGELOG line that the branch makes false is an
  example. The branch fixes it before its pull request opens. A doubt that a later run answers is
  not a defect either: its entry is deleted.
- **No empty file.** The file exists when it has an entry, so it never says "checked, nothing
  found" when nobody checked.
- **One entry per issue**, with a stable ID that is never reused. An existing ID (`A1`, `D7`, …)
  stays, because CHANGELOG entries cite it. A repository with no IDs numbers its entries `K1`,
  `K2`, …. A new entry takes `K<n+1>` in every repository, after the highest `K<n>` in the file.
- **Two entries are one issue only when one fix closes both.** Both entries stay, and the later
  one names the earlier ID in its `found` field. A partial overlap is two issues, and neither entry
  names the other: a fix of one would leave the other pointing at an ID that is gone.
- **The layout:** each entry is a `### <ID> · <problem>` heading with a bullet list of the other
  four fields. A group heading, such as `## Upstream`, stays a `##` heading above its entries, in the same order as the source.

| field | holds |
|:--|:--|
| location | `file:line`; the first `file:line` or path the text names, else `—` |
| problem | one sentence, in the present tense; for a longer entry, its bold lead sentence or its `####` heading, word for word |
| evidence | a command and its output, or a short snippet that reproduces it; the rest of a longer entry, word for word; else `—` |
| kind | defect · missing test · dead code · docs · upstream · not verified · found late |
| found | a pull-request number or a date, never a `Tasks/…` path; else the date of the commit that added the lead sentence (`git log -S`); for the later entry of one issue, also the earlier ID |

- **Prose around the entries:** each fact about one entry goes into its `found` field or its
  `problem`. A paragraph that holds a general lesson goes into the pull-request body for the user
  to place, for example in `Knowledge/`. Nothing is dropped in silence.
- **An entry believed fixed on `main`** stays unchanged, with kind `not verified`, and the pull
  request names it. A move verifies nothing.
- **An entry leaves the file when its fix merges**, and the CHANGELOG entry of the fix names its ID.
- **Every agent reads the file before it adds an entry.** A critic reads it too: a known issue
  blocks only when the part claims to fix it.
- **The loop files a GitHub issue itself only in an organisation of the user's own, as the tree
  instructions list them.** In any other repository it asks the user first,
  and files nothing until the user approves.
