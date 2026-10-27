- **`wiki-lint.jl` checks backticked paths that contain spaces, skips records, and counts a
  backticked path as a link.** A space no longer excludes a span from the path check, because most
  directories under `Projects/`, `Papers/`, `Books/` and `Talks/` have spaces in their names; the
  exclusion hid a line citation past the end of its file. A span that does not resolve whole is
  checked again up to its first flag (` -x` or ` --x`), so `script.jl --apply` names
  `script.jl`, while a file name such as `latexmk -C deletes the built PDF.md` still resolves
  whole. The path and line-citation checks skip `Tasks/Archive/`, `Tasks/Evidence/` and every
  directory that holds a `.lint-records` file, for the reason they skip a `CHANGELOG.md`. The
  orphan check counts a backticked path to a page, or to a directory at least two levels below the
  vault root, as an inbound link, so the files of an evidence directory that a note names are no
  longer reported. On the corpus, with three marked directories and the pointers fixed, the
  warnings fall from 896 to 246.
