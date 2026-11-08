- **`ci-triage` takes the known failures from each repository's `KNOWN_ISSUES.md`, and the gating
  checks from the ruleset that protects `main`.** It read its expected-red set from one task file
  of the tree, which had moved and closed with the set empty, so a graded run across 37
  repositories reported a `Documentation` failure that the repository's `KNOWN_ISSUES.md` records
  as a real regression. It also counted `Documentation` as gating, which no ruleset requires. The
  ruleset is read through `rules/branches/main`, because the classic protection endpoint answers
  404 where only a ruleset protects the branch. A third trap is added: pass a batched GraphQL query
  as a file, `gh api graphql -F query=@<file>`, because the same query given inline failed on the
  sandbox in that run. The agent gains the `write` tool for that file, limited by its text to one
  scratch directory.
