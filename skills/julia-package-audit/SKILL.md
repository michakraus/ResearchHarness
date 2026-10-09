---
name: julia-package-audit
description: "Audit the correctness and code quality of a whole Julia package, and return one findings report in a fixed format: type piracy, type instabilities, avoidable allocations, functionality duplicated from dependencies, and stale or historical comments and docs. Load it first, before reading the source, whenever the request covers a whole package or asks about its code quality, even a one-line request. Typical words: audit, review, sweep, quality pass, clean code, concise, piracy, instability, allocations, duplication, dependencies, stale comments, present tense, historical notes, compact comments, findings report, before a release. For one measurement or a before/after comparison, use julia-performance; for a pull request, the julia-pr-reviewer agent; to fix what the report finds, julia-surgical-fix."
---

# Julia package audit

A whole-package sweep. The output is a **findings report**, not a set of edits — fix only what
the user then asks for, or what is trivially and unambiguously wrong.

**Contents**

- [The checklist](#the-checklist)
- [How to check each](#how-to-check-each)
- [Imports — the three-tool chain](#imports--the-three-tool-chain)
- [Tools](#tools)
- [Facts about this tree](#facts-about-this-tree)
- [Report format](#report-format)

## The checklist

Two variants recur. Ask which is wanted if it is not obvious; default to the full list.

**Quality pass**

1. Code correctness, code quality, clean and concise code.
2. No type piracy.
3. The package does not duplicate functionality already found in its dependencies.
4. No stale comments; all comments in the **present tense**.
5. No historical notes in comments or docs. Everything other than `CHANGELOG.md` describes the
   package **as it is**, not how it got that way.
6. Comments are reasonably self-contained — references are fine, dependence on the diff is not.
7. Comments that can be compacted without losing information.

**Performance pass** — 1, 2, plus:

3. No type instabilities.
4. No avoidable allocations.

## How to check each

| Point | Method |
|:------|:-------|
| type piracy | Aqua `test_piracies`. Then read each hit — a deliberate, documented extension is not a finding. |
| type instability | `@code_warntype` on the entry points; `@inferred` in tests. **`@inferred` drops literal arguments** and cannot see constant propagation — wrap in a closure. |
| allocations | `@allocated` under `--check-bounds=auto`. See `julia-performance` before quoting a number. |
| duplicated functionality | search the dependency's exports for the name and the behaviour, not just the name |
| **imports** | **ExplicitImports.jl** — `print_explicit_imports(M; report_non_public=true)` then `test_explicit_imports(M)`. Seven checks: implicit imports, stale explicit imports, import and qualified-access ownership and public-ness, self-qualified accesses. |
| ambiguities | `detect_ambiguities` — **a count is not a property**. Triage each pair for a witness; most are benign. With `recursive = true` the count covers every method table the process loaded, so two processes are not a before/after. Compare in one process: count, `foreach(Base.delete_method, victims)`, count again, and `setdiff` the `string(m.sig)` keys. Select victims by `String(m.file)`, never by signature text: a `const` `Union` alias prints expanded and matches nothing. Restart the session after the probe; Revise does not remove an `@eval`-added method. |
| stale deps | Aqua `stale_deps` is enabled across this tree. It compares `[deps]` and `[weakdeps]` against `Base.loaded_modules` and has no call-site analysis. A dependency that another dependency also loads passes, and a live-but-useless `using` hides a stale dependency from it. |
| dead dependency | Match each dependency's exported names against `Meta.parseall` of every file the module includes. Exclude the module file and its `export` list. A grep fails both ways: it matches docstrings, strings and commented-out code, and it misses re-exports. Count only names that a single dependency exports. Report `file:line` per dependency and read every hit before you cut. Then confirm with `isdefined(M, n)` over `names(M)` and the suite. |
| DifferentialEquations | An import of DifferentialEquations.jl is dead code to remove. Replace the call with a problem and an integrator of the integrator package. |
| transpose identities | Grep `'` and `adjoint` in a type's own file. For each site, ask whether the defining identity is a transpose (`Mᵀ = ±M`) or an adjoint. `A'` and `transpose(A)` agree on a real element type, so a real-only suite cannot see the difference. Check with a `ComplexF64` instance against the dense form. Three tells: the docstring writes `A^T` where the code writes `A'`; `getindex` rebuilds entrywise without conjugating, so every other method that rebuilds the same block must not conjugate either; one constructor of a pair is exact and its twin is not (`LowerTriangular` reads `A`, `map_to_up` reads `A'`). Not every `'` is wrong: the manifolds' `Y.A'` is right, because `‖YᴴY − I‖` is sesquilinear. The `{<:Real}` fix makes sense only where the real method shares storage. |
| element-type defaults | Unifying an element-type default that a backend argument selects on `Float64` is right on the host and a silent GPU regression. Check whether the GPU branch is the `Float32` one. Prefer deleting the backend constructor with no element type, so the caller names `T`. Convert each scalar to the array's own `T` where it enters a kernel. |

## Imports — the three-tool chain

These interlock, and the order matters:

1. **`fatou lint`** lists `unused-import` candidates cheaply and statically. Do not act on them
   alone: the rule does not follow `include`, so it flags a module file's load-bearing imports.
2. **ExplicitImports.jl** goes further: implicit imports (`using Foo` then relying on what it
   happens to export), stale explicit imports, and accesses to names a package does **not**
   declare public. Run on Julia **1.11+** — the `public`/non-public distinction does not exist
   below that, so the checks are only authoritative there.
3. **Aqua's `stale_deps`** then finally means what it claims. This is the point of the
   exercise: *a live-but-useless `using` hides a stale dependency from Aqua*, so clearing 1 and
   2 is what makes 3 trustworthy. It still passes a dependency that another dependency loads;
   the syntax-tree match in the table finds those.

Available in the shared environment (ExplicitImports v1.15), so ad-hoc analysis needs no change to
any repository. A Kaimon session's load path already carries `@v#.#`, so load it directly there.
`TestEnv.activate()` fails inside Kaimon with `can not merge projects`.

```julia
using ExplicitImports, MyPkg
print_explicit_imports(MyPkg; report_non_public = true)
test_explicit_imports(MyPkg)
```

To install it as a **test dependency** of a package, hand-edit `test/Project.toml` (or
`[extras]`/`[targets]`) rather than using `Pkg.add` — the house rule about `Pkg.develop`/`add`
eating comments and injecting `[sources]` applies. Pin a **tight** lower bound:
`ExplicitImports = "1.15"`. `test_explicit_imports` only exists from v1.15, so a looser `"1"`
lets the resolver pick an older version and the suite fails with `UndefVarError`. A tight bound
is harmless for a test-only dependency — it never constrains users.

## Tools

`Aqua` (piracy, ambiguities, stale deps, compat bounds) · `JET` (abstract interpretation;
catches inference and call errors Aqua does not — present in only 2 repositories here, worth
proposing where a package has real inference surface) · `BenchmarkTools` · `Documenter` with
`DocStringExtensions` · package extensions rather than optional hard dependencies · Holy Traits
where dispatch on a property is wanted without touching the type hierarchy.

Prefer immutable structs, and abstract rather than concrete field annotations. Short keyword
syntax `f(; max_iter)`. Test exception **types** or user-facing messages, not incidental text.

## Facts about this tree

- **`style = "sciml"`** — every `.JuliaFormatter.toml` file. There is no BlueStyle repository
  here. Format with **JuliaFormatter**, on **staged files only**; several repos (the simple solver package
  among them) are not formatted to their own config, so a whole-tree run buries the real change.
- **Never `fatou format`.** Fatou does not read `.JuliaFormatter.toml` and has no style preset;
  it would reformat ~all files into a different style. Use `fatou lint` — it is style-neutral.
- **CairoMakie, not Plots.** Plots survives only in legacy `docs/` and `scripts/`.
- **Edit `[compat]` by hand, then `Pkg.resolve()`.** `Pkg.develop` rewrites `Project.toml`,
  eats every comment, and injects a `[sources]` table that blocks registration in General.
- **The floor is the package's `[compat] julia`** — 1.11 in most packages, 1.10 in a few; CI runs
  from it to `^1.13.0-0` and nightly.
- **Doctests are not run by `Pkg.test()`** — only `docs/make.jl` executes `jldoctest` blocks.
- **Do not run a test suite concurrently with another heavy Julia job over shared packages.**
  `Pkg.test()` on Julia 1.12 and earlier uses `--check-bounds=yes` while everything else uses
  `auto`; the divergent
  `CacheFlags` invalidate shared precompile images, producing `CacheFlags`/`MethodError`
  failures that look like real bugs. Disjoint packages or matching flags are fine.

## Report format

Always this shape, most severe first:

```
## <package> — audit <date>

### Findings

| # | severity | file:line | claim | evidence |
|--:|:---------|:----------|:------|:---------|

### Checked and clean
- <point>: <how it was checked>

### Not checked
- <point>: <why>
```

Rules for the table:

- **severity** is `bug` / `correctness-risk` / `quality` / `nit` — the vocabulary of
  `julia-pr-reviewer` and `julia-branch-verifier`, without `blocker`, because no pull request
  waits on an audit. Do not inflate.
- **evidence** is a command that was run and its output, or a file:line to read. A finding
  without evidence is a guess and belongs in "Not checked" instead.
- Re-measure any figure you quote. A PR's own claimed allocation numbers have failed to
  reproduce here before.
- If CI is involved, read the **job**, not the workflow conclusion: `continue-on-error`
  misreports in both directions, and nightly is expected red.

Say what was *not* checked. An audit that silently skips a point reads as a clean bill of
health for it.
