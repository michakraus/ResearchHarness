---
paths: ["**/docs/make.jl", "**/docs/src/**", "**/docs/Project.toml"]
description: What breaks a Documenter build in this tree, what every other check misses, how to build locally, and how to tell that the docs deployed.
---

# Documentation builds in a Julia repository

The full build is the **Documentation** workflow, `Documenter.yml`. CI's Doctests job runs only
`doctest(m)`, and it passes a broken `@ref`. `Pkg.test()` skips the docs. Only a `makedocs` run
checks docstring attachment, cross-references and `checkdocs`.

## Run the build after the last source edit

- **Keep the gap between a docstring and its definition empty.** A comment or a helper there
  detaches the docstring: the binding is undocumented and every `@ref` to it fails. The formatter,
  `fatou lint` and the suite all pass. Put a helper **above** the docstring. An edit near a
  docstring invalidates an earlier docs build.
- **A docstring above the wrong definition documents that one.** `@autodocs` renders it under the
  wrong name with no error; an explicit `@docs` block fails. Prefer explicit `@docs` blocks on a
  library page.
- `julia-branch-verifier` does not run the docs build. Run it yourself.

## What `checkdocs` and `@ref` see

- **A submodule needs its own `@docs` or `@autodocs Modules = [Package.Sub]` block.** `checkdocs`
  recurses into a submodule, and `@autodocs Modules = [Package]` does not. Without the block, the
  build fails on `:missing_docs` and on `:cross_references`.
- **`checkdocs = :exports` ignores a bare re-export**, a name with no local docstring and no local
  method. Turn it on without docstrings for re-exports, and name them in the page prose. It flags a
  generic the package extends but does not document; a two-line docstring naming the owner fixes it.
- **Importing a dependency's generic moves its docstring anchor** from `id="Package.name"` to
  `id="Dep.name"`. The build stays green and a permalink breaks. Grep `docs/build/library.html` for
  both forms.
- **An unqualified `@ref` to a name that the package and a dependency both export fails the
  build** on a page with no `CurrentModule`. Name the target:
  `` [`Newton`](@ref Example.Newton) ``. A qualified link text also works, and is the
  convention for `` [`Example.OptimizerStatus`](@ref) ``. With `CurrentModule` set and the name in an
  `@docs` block on the same page, the unqualified form resolves.

## Build locally where it can finish

- **Run `grep -n InterLinks docs/make.jl` first.** An empty result means the build can finish in
  the sandbox, so run it. Otherwise each inventory fetch from `<org>.github.io` is blocked, every
  `@extref` fails, and `makedocs` stops before rendering. An `InterLinks` entry that names a file
  under `docs/inventories/` beside its URL falls back to that file; where every entry does, the
  build can finish too.
- **Where the build cannot finish, a local exit 1 says nothing about the change.** Compare with the
  base, or push and read the **job** conclusion of the Documentation workflow. Locally, grep the log
  for `Cannot resolve @ref` and `No docstring found`. Ignore `cannot resolve external link` and the
  other local-image failures that need CI.
- **Check for the positive marker, not for the absence of errors.** A filtered log returns the
  filter's exit status, and doctests run before cross-references. A complete build prints
  `[ Info: RenderDocument: rendering document.`. Read where the log stopped before you count what
  it reported.
- **A red build that names a source file and a symbol can be a stale `docs/Manifest.toml`.** It is
  gitignored and drifts below the package's `[compat]`. Compare its versions with `[compat]`, then
  run `Pkg.update()` in the docs environment; `Pkg.instantiate()` does not fix it. After adding a
  dependency to the package, `Pkg.resolve(); Pkg.instantiate()` in the docs environment is enough.
  Back up `docs/Project.toml` before a resolve.
- **Do not `cd` into `docs/build` or a directory under `docs/src`.** The harness creates
  `.claude/.cc-writes/` in the shell's cwd. Documenter then copies or clears it and fails with
  `EPERM`, and the sandbox cannot delete it. Run `make -C docs/src/tikz` from the repository root,
  and read a built page by absolute path. A checkout that has the directory builds only from a
  clean worktree of the branch, with `docs/Manifest.toml` copied in.

## Deploy

- **`devbranch` and `edit_link` name the default branch.** A stale `"master"` deploys nothing while
  the job is green, and every edit link 404s. Check the tree with
  `grep -rn 'devbranch\s*=\|edit_link\s*=' Packages/*/docs/make.jl Experiments/*/docs/make.jl | grep -i master`.
- **A green Documentation job does not prove a deploy.** `git log -1 --format='%ci %s'
  origin/gh-pages` names the commit you pushed when it deployed. `gh api repos/<owner>/<name>/pages`
  returning 404 means no Pages site is configured.
- **A repository with its own docs workflow pins its own `julia-version`.** Raise it with
  `[compat] julia`, or every docs job fails in "Install dependencies". A pin below the floor can be
  a deliberate workaround: read `docs/src/maintenance.md` first. The Documentation check is not a
  required check, so the pull request that breaks it merges green.

Evidence and measurements: `~/Research/Environment/Notes/Tree-Wide-Gotchas.md`, § "Building the
documentation".
