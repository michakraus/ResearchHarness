- **`skills/build-part/edges.md` lists a comprehension or a closure that captures a variable the
  enclosing loop reassigns**, under *A type or an interface*. The variable becomes a `Core.Box`
  and its operations infer `Any` while the return type still infers, so `@inferred` misses it. The
  branch verifier found two such sites late, each after a critic PASS; the entry names the fix and
  a testset that scans the lowered code for `Core.Box`.
