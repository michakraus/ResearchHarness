- **The Julia packages' pre-commit hook needs JuliaFormatter 2.14 or later, and checks a `.jl`
  file that becomes a symlink.** The formatting stage passes `throw_on_error = true`, which
  JuliaFormatter has from 2.14 on; an older release, such as 1.0.62 or 2.4.0 from a coauthor's own
  environment, made every staged file read as unformatted. The stage now refuses such a release
  with one line that names its version and the minimum. JuliaFormatter 2.14 supports Julia 1.10
  and later, so every package's Julia floor of 1.12 can use it, and the harness's Julia
  environment pins `JuliaFormatter = "2.14"`. The staged-file filter of the launcher and of
  `pre-commit.jl` includes a type change (`T`), so a `.jl` file replaced by a symlink no longer
  skips the stages.
