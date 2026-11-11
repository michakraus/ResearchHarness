- **The new docs page *Planned work* lists each planned and work-in-progress feature, and each
  mark of another page links its row.** Sixteen rows in four tables, for the sandboxes and the
  safeguards, the static checks, the tests and CI, and the edge catalogue, give each feature, its
  state with its condition, and the section that describes it. `npm run docs:check` runs the new
  `docs/scripts/planned.mjs` and its cases: it fails on a link to a row that the page does not
  hold, on a row that no other page links, and on a mark such as `(planned)`, `**Planned:**` or
  "on Linux planned" without a link to its row. The page *Static checks* gives the ast-grep rules
  no mark: it describes stage 2.7 of the pre-commit hook, which runs them on every commit. The
  sidebar group *Background* holds *Development* and *Planned work* after *Research memory*;
  *Development* keeps its URL `/development`.
