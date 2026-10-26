- **`wiki-lint.jl` checks backticked paths that contain spaces, skips closed records, and counts a
  backticked path as a link.** A space no longer excludes a span from the path check, because most
  directories under `Projects/`, `Papers/`, `Books/` and `Talks/` have spaces in their names; the
  exclusion hid a line citation past the end of its file. A span that continues with ` -` is a
  command, and only the path before the first flag is checked. The path and line-citation checks
  skip `Tasks/Archive/` and `Tasks/Evidence/`, for the reason they skip a `CHANGELOG.md`. The
  orphan check counts a backticked path to a page, or to a directory at least two levels below
  the vault root, as an inbound link, so the files of an evidence directory that a note names are
  no longer reported. On the corpus the warnings fall from 896 to 388, and one error appears.
