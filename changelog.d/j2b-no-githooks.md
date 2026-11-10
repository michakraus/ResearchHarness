- **`base-tree.jl` and the copy of `run-tests.jl` (`copy_command`) leave out every `.githooks`,
  at any depth, and `base-tree.jl` refuses a named path inside one.** The sandbox denies the write
  of a `.githooks` under `~/Research`, and every package tracks one, so in a sandboxed session the
  base tree, `dispatch-delta.jl`, `mutate.jl`, `pins.jl` and a run beside a foreign manifest failed
  on every package. The refusal names `git show <ref>:<path>`, which prints such a file.
