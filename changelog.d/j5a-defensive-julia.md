- **`build-part/defensive-julia.md` is a catalogue of defensive Julia, D1 to D38, which a builder
  reads before it writes `src/` code.** Each entry gives a rule, the code that fails and the code
  that holds, the check that a test makes, and the `edges.md` entry that it answers; the entries
  come from the review findings and `KNOWN_ISSUES.md` entries of the packages since 2026-10-01,
  after a read of each class's members. The test side of D3, D11, D12, D22 and D23 is five new
  bullets of `rules/julia-tests.md`. `julia-builder` and `part-builder` name the file in their
  step that writes the code, the `build-part` section of the components page names it, and the
  entries of `edges.md` on `similar` and on the stencil length link to D2 and D33 in place of
  their own how-to sentence.
