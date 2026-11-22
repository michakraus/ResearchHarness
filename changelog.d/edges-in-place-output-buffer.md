- **`edges.md` names the in-place function whose tests read only its return value.** A test of
  `f!(out, args...)` that compares the returned array passes a version that returns a correct fresh
  array and leaves `out` wrong; the line asks for `=== out` and a comparison of `out` itself.
