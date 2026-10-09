---
paths: ["**/*.jl"]
description: Verification tiers, the formatter, Aqua, and the structural tools for Julia code in this tree.
---

# Working on Julia code here

## Define the check, then pick the cheapest runner

Turn the task into something verifiable, then loop until it verifies. Three tiers, cheapest first:

0. **`mcp__kaimon__ex` on a warm session.** Revise auto-reloads `src/` before every eval, so an
   edit is checkable in seconds with no process start. This is the default while iterating.
1. **`Harness/scripts/run-tests.jl <package> affected`**, or on named test files, once
   the edit is plausible: the test files the diff reaches, through `TestEnv`, in seconds to a
   minute per file.
2. **The full `Pkg.test()`** before pushing — seconds to a few minutes in most packages, and
   **20–100 minutes in CI in the large ones.**

Reach for tier 0 before shelling out to `julia`: a cold start pays for the process, the package
load and precompilation every time. **The exception is measurement** — a timing or allocation
figure needs a cold process, never the warm session.

**`--startup-file=no` is not optional** in any cold invocation. `~/.julia/config/startup.jl`
loads Revise only when `isinteractive()`, and a Kaimon setup that rewrites its block can drop that
guard. Revise's file watcher then sprays `EMFILE` into the output, mid-line, and eats the value you
printed. When `EMFILE` shows in a script's output, check `~/.julia/config/startup.jl` first.

**The working Julia here is 1.13. The compatibility floor is the package's own `[compat] julia`:
1.11 in most packages. Check it in `Project.toml`. All these releases exist.** A model whose priors
end before a release writes for the version it remembers and reads the version fact as a mistake to
correct. Take the version from `~/.julia/` and from each `Project.toml`, never from memory.

## Diagnosing a bug: build the loop before the theory

**No command that goes red on this bug, no hypothesis.** Name one command — a `@testset` name, a
script path, an `ex` expression — run it at least once, and show that it fails on the symptom that
was reported. Reading code to build a theory before that command exists is the failure this
prevents. Tier 0 is usually the tight loop, because Revise reloads `src/` in seconds.

**For a nondeterministic bug, aim for a higher reproduction rate, not a clean repro.** Loop the
trigger, seed the RNG, narrow the timing window. A failure that appears half the time is
debuggable; one in a hundred is not. One red run is not a reproduction, and one green run is not a
fix.

**Rank three to five falsifiable hypotheses before you test any one of them.** Each states the
prediction that would kill it. Generating one at a time anchors the whole investigation on the
first plausible idea.

**Tag every temporary probe** — `@info "[DEBUG-a4f2] …"`, one prefix per investigation — so the
cleanup is a single grep. An untagged `@show` survives the commit.

**A check that cannot fail is not a check.** A test whose expected value is recomputed the way the
code computes it passes by construction. Take the expected value from elsewhere: a closed form, a
published table, a coarser method, a conserved quantity. This is the common failure in a numerical
suite, and a green run cannot report it.

**Where no seam lets the regression test see the real failure, that absence is the finding.**
Report it. A test at the wrong seam gives false confidence.

## Traps that read as something else

**Versions.**

- **Check an inference-sensitive change on the package's floor**, with `julia +<floor>`. On 1.10, a
  closure that captures a local type (`local T = promote_type(…)` inside a `map`, `sum` or
  `mapreduce` lambda) makes the whole call infer as `Any`. Write the loop out, with an accumulator
  `local p::T = one(T)`. A `Manifest-v<major.minor>.toml` resolves for that version beside the main
  manifest; `.gitignore` covers only `Manifest.toml`, so delete it after.
- **On 1.10 and 1.11, `parentmodule` reports every module's own `eval` and `include` as owned**; on
  1.12+ it does not. Skip `:eval` and `:include` by name in a scan that decides ownership with
  `parentmodule(x) === mod`. 1.11 is the `min` job of most packages.
- **On 1.12+, an `include` of a file whose `struct`, `abstract type`, `primitive type` or `@enum`
  changed makes a new type.** Including the original again makes a third. Methods of other files
  still name the first, so calls raise `MethodError`. Run a mutant, probe or reload that changes a
  type definition in a fresh process.
- **A manifest resolved by another Julia reads as a package bug.** No repository tracks
  `Manifest.toml`, so one copy serves every version. On the wrong version, precompilation fails with
  "in a world prior to its definition world" or "The applicable method may be too new", and
  `Pkg.resolve()` does not clear it. Julia's own warning about a manifest resolved by another
  version prints first and is easy to scroll past. CI passing on both versions with the same
  dependency shows it is no package incompatibility. Before a version switch, run
  `rm -f Manifest.toml && julia +<version> --startup-file=no --project=. -e 'using Pkg; Pkg.instantiate()'`
  (about 100 s). Re-resolve for the default Julia (`juliaup status`) before a push, because
  `.githooks/pre-push` runs `Pkg.test()` with it.
- **A new worktree carries the main checkout's manifest, stale or not.** Julia does not check
  `[compat]` at `using`, so an old manifest loads old dependency versions. The pre-commit load test
  runs only when a `.jl` file is staged, so the failure appears on a later commit and reads as broken
  source ("exported function … does not exist"). When a load test names a missing function of a
  dependency, compare the manifest's `version` with `[compat]`, delete the worktree's
  `Manifest.toml`, run `Pkg.instantiate()`, and check `git diff Project.toml`.
- **A numerical difference between versions can be round-off on a gate.** A stop that depends on a
  noise-level value lands on either side of a tolerance by chance. Before you blame or raise a
  compat floor, run the probe on every version in between and read the last iterations for a cycle.

**Revise keeps a deleted method**, and it can leave some methods of a file stale. Before a number,
a type or a pass/fail goes into a CHANGELOG, a PR body or a task file, call
`manage_repl(command = "restart")` and measure again; `Revise.revise()` does not resync a
half-reloaded session. Confirm the reload with `isdefined` on a name
the branch adds and on one it deletes.

**Dispatch.** A narrowed `Base` method does not raise a `MethodError` for the excluded types: they
fall through to the generic method, which usually exists. Call it on an excluded type before you
say what happens: write `@test_throws MethodError` first, and if it fails, measure what happened
rather than relax the assertion. After you add an operator method, call every combination. With
`*(::T{a}, ::AbstractMatrix)` and `*(::AbstractMatrix, ::T{b})`, `T{a} * T{b}` is ambiguous, and one
`*(::T, ::T)` does not fix it, because specificity is per argument slot: write each concrete pair. A
new `*(::AbstractMatrix, ::Owned)` makes `v' * X` and `transpose(v) * X` ambiguous with
`LinearAlgebra`'s row-vector methods; `detect_ambiguities` counts that pair as own-versus-external,
and a matrix-only probe reports clean. Probe both products on both trees, and add the tie-breakers
`Base.:*(x::Adjoint{<:Any, <:AbstractVector}, X::Owned)` and its `Transpose` twin. Check whether an
ambiguity exists on `main` before you attribute it to the diff.

**Write `transpose`, not `'`, where the type's defining identity is a transpose one** (`Mᵀ = -M`,
`Mᵀ = M`, a `-Bᵀ` block). The two agree on real element types, so a real-only suite cannot see the
error. Build a `ComplexF64` instance and compare every operation with its dense form: a real error
is `0.0`, a complex one is `O(1)`. `(A' * B')'` is a true adjoint identity and stays. The other fix
binds the method to `{<:Real}`, so `LinearAlgebra`'s lazy `Adjoint` takes the complex case.
`transpose` in place of `'` changes the return type from `Adjoint` to `Transpose`.

**In a `Float16` kernel, accumulate every `O(n)` reduction in `Float32`**, and keep storage and
results in `Float16`. A `Float16` dot product stops near `32 · eps(Float16)`, which is coarser than
`sqrt(eps(Float16))`, so a relative threshold on it means nothing. `ldexp(one(T), -exponent(m) - 1)`
overflows to `Inf` for a subnormal `m`: cap the exponent at `exponent(floatmax(T))`. A per-pair
relative convergence test never ends on a rank-deficient matrix: test against the largest column,
as LAPACK's `gesvj` does. Both fail silently.

**An edit that changes a file's line count falsifies every `file:line` citation of it.** Run
`grep -rn 'name\.jl:' CHANGELOG.md test/ Tasks/` and re-measure each hit in the same commit. In a
new comment, name the function, not the line.

**Kaimon.** `ex` takes the session as `ses = …` and shows its return value only with `q = false`;
`manage_repl` takes `session = …`. `ex` drops an unknown parameter silently and answers
`No session matched ''`. A bare "The operation timed out." from `start_session` is the client at
about 60–70 s, and the session keeps starting: call `ping`, and do not retry, because a retry spawns
a duplicate.

## Look before you write a name

Before writing anything longer than a one-liner, run `julia-methods.jl <package-dir> <name>` for
the name you were about to invent, and for the helper you are assuming is missing. Multiple
dispatch is what makes this necessary rather than merely tidy: a method added to an existing
generic is not a new name, so grep finds your own call site and says nothing about the definitions
already in the tree. A **qualified** definition — `ExampleBase.nsamples(x) = …` — does not look
like a definition to any text search, and a fifth of this tree is written that way.

| the question | the tool |
|:--|:--|
| what methods exist, and where — in a package that may not load | `Harness/scripts/julia-methods.jl <package-dir> <name>`. The first argument is a **path** |
| which method actually **runs** for these arguments | Kaimon `search_methods` on a warm session. Nothing else answers this |
| who calls this, and is it dead — where the package loads | `julia-callers.jl` on that session. It sees through qualified definitions |
| anything spanning all the repositories | Kaimon `grep_code`, with `path` set to an absolute directory. It is the cross-repository tool and **needs no session**, only the server; each hit carries its enclosing function or struct |

**An empty result from any of them is UNKNOWN, never a negative.** Say which tool produced the
answer. The `julia-structure` skill has the full routing.

## Judge code quality critically

When the task is to write, port, modernise or review Julia code, judge the quality of that code
critically, and look for the radical simplification: fewer lines, fewer types, fewer special
cases, and a dependency's function instead of a local copy. Three limits bound it. A
simplification that costs any of them is wrong:

- **Readability** — a reader follows the code without the diff beside it.
- **Comprehensibility** — the design stays visible in the code.
- **Performance** — measure the hot path before and after the change, and keep the version that
  is not slower. The `julia-performance` skill says how to measure.

Start every accumulator from `zero(T)` or `one(T)`, never from a literal such as `0.0`. A literal
promotes `Float32` to `Float64`, and a `Float32` test then passes on the promoted value.

The stance covers the code the task names. It does not widen the task: the scope rule of
`~/.claude/CLAUDE.md` still decides which files change.

## Formatting — one engine, two entry points

`style = "sciml"`, from each repository's `.JuliaFormatter.toml`. Run it over **only the files you
changed**, never a whole tree: several repositories are not formatted to their own config, so a
whole-tree run buries the actual change.

Warm session, no process start — and the final expression is the answer, because `ex` removes the
print calls of the code you send:

```julia
using JuliaFormatter
bad = filter(f -> !format(f; overwrite = false), ["a.jl", "b.jl"])
isempty(bad) ? "formatted" : "not formatted:\n" * join(bad, "\n")
```

Cold, as `.githooks/pre-commit` does it, and as a sub-agent without Kaimon must:

```bash
julia --startup-file=no -e '
    pushfirst!(LOAD_PATH, joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    using JuliaFormatter
    bad = filter(f -> !format(f; overwrite = false), ARGS)
    isempty(bad) || @error "not formatted:\n" * join(bad, "\n")
    exit(isempty(bad) ? 0 : 1)
' file1.jl file2.jl
```

`overwrite = false` checks and returns a `Bool` per file. Drop it to rewrite.

**Never run `fatou format`** — it reads only `fatou.toml`, has no SciML preset, and reformats
damagingly.

## Aqua — wrap it, or a pass and a failure look the same

Run Aqua through Kaimon's `ex`, never through `lint_package`. A call that holds a `using` returns
its value but not the printed output of the functions it calls, so a bare `Aqua.test_all` beside
`using Aqua` returns nothing whatever it found. `Aqua.test_all` also **aborts after its first
failing check** and adds no enclosing testset, so a bare call hides both passes and failures:

```julia
using Aqua, Test
try
    @testset "Aqua" begin
        Aqua.test_all(ThePackage)
    end
    "Aqua: all checks passed"
catch e
    join(string.(e.errors_and_fails), "\n\n")
end
```

`e.errors_and_fails` carries the failing expression and its location. `sprint(showerror, e)` gives
only the counts.

## Disabled Kaimon tools, and why

`format_code`, `lint_package`, `code_typed`, `code_lowered` and `profile_code` are off in
`~/Research/.kaimon/tools.json`. `format_code` and `lint_package` resolve their package in the
**server's** own `Main`, a derived artefact that every `Pkg.Apps.update` regenerates. `code_typed`
and `code_lowered` build a call that matches no method, and return `Any[]` for every function.
`profile_code` returns no profile, because its wrapper holds `using Profile`. A session is the
durable path, because its load path carries `@v#.#`. Ask the same question through `ex`.

## Verification is written in Julia

Every analytic, symbolic or numerical check is Julia. `SymPyPythonCall.jl` is acceptable where
Julia has no equivalent, but the surrounding script is Julia. This governs **verification code**,
not tooling; Python-based tools are fine.

A script that verifies an algorithm or a mathematical statement is **archived into the
repository's `scripts/`**, not left in `/tmp`. A claim whose check has been thrown away is an
unverified claim.

Measurements and the trials behind all of this: `Environment/Notes/Helpers-and-MCPs.md`.
