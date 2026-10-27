- **`build-part` runs the spec checks of a spec-delta part with `--out` below `$TMPDIR`.** The
  sandbox refuses a `.claude` directory below `~/Research/.scratch`, so a check that runs a
  scratch `harness install` failed there with `Operation not permitted`, and the gate reported a
  failure that was not the part's. The same checks pass with the output below `$TMPDIR`.
