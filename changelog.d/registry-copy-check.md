- **A new `PostToolUse` hook, `registry-copies.py`, warns after a Bash call that runs Julia when
  the depot holds a stale copy of the General registry, and `julia-release` checks a registration
  through Pkg.** Pkg of Julia 1.10 to 1.12 writes `General.tar.gz`, Pkg of Julia 1.13 writes
  `General.tar.zst`, and neither removes the other's file; `General.toml` names the one that Pkg
  reads. The warning names each copy, its modification time and the remedy. The skill no longer
  reads a tarball by a fixed name, which could disagree with what Pkg resolves.
