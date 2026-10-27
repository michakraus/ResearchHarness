- **`wiki-lint.jl` does not report an unwritten link inside a record.** `link-unwritten` skips
  `Tasks/Archive/`, `Tasks/Evidence/` and every directory with a `.lint-records` file, as the path
  and line-citation checks do: a record is never edited to write the page its marker named. The
  other link checks still read records. On the corpus, the 13 warnings in the three marked
  directories go to 0, and no other count changes (244 to 231 warnings).
