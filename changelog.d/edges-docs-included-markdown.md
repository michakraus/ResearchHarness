- **`skills/build-part/edges.md` names a Markdown fragment below `docs/src/` as an edge class.**
  By default Documenter builds every `.md` file there as a page, whether or not `pages` names it,
  so a table that a page reads in also ships as a page of its own that no menu reaches.
  `plan-parts` writes a part's *Decided at the edges* from this list, so the next docs part keeps
  such a fragment out of `docs/src/` or gives it another extension.
