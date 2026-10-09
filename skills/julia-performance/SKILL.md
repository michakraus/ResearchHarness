---
name: julia-performance
description: "Measure Julia performance so that the number means something: allocations, type stability, timings and before/after comparisons, each in a cold process with the traps of this tree. Load it first, before reading code, for any question about the speed, memory or inference of Julia code, even a one-line question with no code attached. Typical words: allocates, allocation count, @allocated, @btime, @benchmark, BenchmarkTools, @code_warntype, @inferred, JET, runtime dispatch, inference, type instability, slower, faster, speed-up, slowdown after a merge or an update, performance regression, compare a branch with main, is the fix worth it, a failing allocation test. For a whole-package quality sweep, use julia-package-audit instead."
---

# Julia performance measurement

Every rule here exists because it was violated once and produced a confident wrong number.
The failure mode is never a crash — it is a measurement that looks fine and means nothing.

**Contents**

- [Before measuring](#before-measuring)
- [Timing](#timing)
- [Allocations](#allocations)
- [Type stability](#type-stability)
- [A/B the change, not two inputs](#ab-the-change-not-two-inputs)
- [Guarantees hold only where asserted](#guarantees-hold-only-where-asserted)
- [Report](#report)

## Before measuring

**Measure cold, in a fresh process.** A sweep inside one session measures what the previous row
compiled. Start a new `julia` for each configuration you intend to compare. Two variants timed in
one process give the first one the compilation cost. Run each variant twice in its own process, and
label the cold and warm columns. A build-cost figure is the exception and stays valid, because the
docs build runs the later blocks warm.

**Warm up before timing.** The first build or call in a process measures compilation, not the
code. Take a median over repeats, not a single reading.

**Print the resolved versions next to any cross-version measurement.** A probe environment that
silently resolved the *registered* package instead of the working tree has produced a pre-fix
figure reported as post-fix. `[sources]` is Pkg 1.11+, so on **1.10 a `[sources]` entry is
ignored** and the registry copy wins — use `Pkg.develop(path=…)` in any 1.10 probe env.

**Do not measure while a test suite is running** over any of the same packages. `Pkg.test()`'s
`--check-bounds=yes` on 1.12 and earlier diverges from your `auto`, the shared precompile images
invalidate each other, and you will be timing recompilation. Disjoint packages or matching flags
are fine.

**Pin `BLAS.set_num_threads(1)` inside the script** before you quote a ratio for a change to dense
arithmetic, and state the thread count. Multithreaded BLAS gives a large square product its loss
back by an amount set by idle cores; one script gave 2.1, 3.3 and 756 for one code. Read the cost
class off the expression, and do not fit an exponent: at reachable sizes allocation dominates the
small end and `gemm` the large end.

## Timing

**Give the timed call its own statement.** Julia compiles a whole top-level statement before it
runs it. In `println(@elapsed f(x))` the callee compiles before the timer starts, so the cold
figure comes out warm, repeatably. Write `t = @elapsed SINK[] = f(x)` with `const SINK = Ref{Any}(nothing)`.

**Check every cold figure twice.** Time a second call in the same process, and check that the two
differ by the factor compilation explains. Then compare with an independent run.

**Below ~1 µs per call, one call per sample measures the clock.** `time_ns()` on this Apple Silicon
host advances in 41–42 ns ticks. Fold calls into each sample until it lasts ≥ 20 µs, then divide.
Size the block with `c = ceil(Int, 2e-5 / @elapsed f(x))`, take the median over samples, and run
the script cold three times. At the smallest size the ratio still moves between runs, so publish a
range there, not one figure.

**Time the shape a user writes.** `foreach` over a `Vector` of closures puts every dynamic dispatch
inside the timed region.

## Allocations

**`Pkg.test()` forces `--check-bounds=yes` up to Julia 1.12.** There it inflates timings roughly
4× **and skips every guarded `@allocated` assertion**; from 1.13 it inherits the session's `auto`.
On the `[min, 1]` matrix a bound is therefore enforced on `1` and skipped on `min`, so green CI is
*not* evidence for an allocation bound on the floor. Run with `--check-bounds=auto` when allocations are the point:

```bash
julia --project --check-bounds=auto -e 'using Pkg; Pkg.test(; julia_args=["--check-bounds=auto"])'
```

**`@allocated` equality is not portable.** It drifts tens of bytes per call and ~30 % between
builds; Windows jitters in both directions. Assert a **ceiling or a spread**, never `==`.

**One `@allocated` call can be off by orders of magnitude.** A GC interaction or a buffer resize
lands in it, and the output does not show this. Sweep several sizes and read the trend. Take a
minimum over repeats, and distrust a row that breaks the trend of its neighbours. A warm-up call
removes compilation, not this noise.

**`@allocated` around a constructor measures the constructor**, not the work the caller did to
build its argument. To compare retained storage, use `Base.summarysize`.

**On Julia 1.11, keep the measuring function to one line, with all arguments as parameters.** A
function that builds the object and holds the `@allocated` gets a `Core.Box` that 1.11 does not
elide, so `@allocated` reads 16 bytes for a zero-allocation call. Build the object in the caller.

**`Profile.Allocs` gives correct counts and wrong sizes.** Use it to find which `file:line`
allocates and how often. Take every byte figure from `@allocated` on a warm call in a cold process.

**Measure the shape a consumer actually holds.** A bare `NamedTuple` benchmark reports the cheap
column and calls it the cost.

## Type stability

`@code_warntype` on the entry point, `@inferred` in tests.

**`@inferred` drops literal arguments** — it cannot test constant propagation. Wrap the call in
a closure if that is what you mean to check.

A `CacheType` that reads a value off the problem rather than constant-folding costs ~5×
allocations. If a type parameter is computed at runtime, inference has already lost.

## A/B the change, not two inputs

To claim a change did or did not affect performance, toggle **that change** with everything else
fixed. Comparing two different inputs, two different Julia versions, or two different
environments answers a different question.

"This is not a performance fix" needs the with/without toggle just as much as "this is".

The new variant is the shipped function, never a copy in the script: a copy goes stale silently
when review edits the method. Write out only the replaced variant, and have it return the same
wrapper type as the method, so the byte columns compare like with like. Reach the old one with `invoke`, or run the same script file in a
worktree at the base commit, and name the commit.

`invoke` works when the fix adds a more specific method. Copy the shadowed method's own signature,
without the function type, from its definition:

```julia
invoke(rand,
    Tuple{CPU, Random.AbstractRNG, Type{MT}, Integer, Integer} where {T, MT <: Manifold{T}},
    CPU(), Random.default_rng(), SymplecticStiefelManifold{Float64}, 6, 4)
```

When the fix edits a
method body in place, no old method is left; use the worktree, and say which route you took.

**A rare yes/no outcome needs a rate on both trees.** One run on the changed tree and none on the
baseline is not a comparison. Run enough trials on each tree and quote "n of N trials".

## Guarantees hold only where asserted

A fix lands on the code paths that have allocation tests, not on their siblings. Before saying
a class of call is now allocation-free, check whether each member is actually covered.

## Report

```
## <what was measured>

| variant | allocations | time | Julia | resolved versions |
|:--------|------------:|-----:|:------|:------------------|

Method: <fresh process? warm-up? check-bounds? repeats?>
Conclusion: <what changed, or "not reproducible">
```

**A ratio band from one run is one run.** Both terms of a ratio move with load. Quote the
direction ("less than", "an order of magnitude", "grows linearly in n") unless several runs back
the band, and say how many.

**Before you publish a figure, run `lsof -c julia -t`** to find another session's `Pkg.test()`. When
the machine was not idle, say so beside the figure.

**"Not reproducible" is a valid and useful result.** Report it plainly rather than hunting for a
configuration that shows the expected effect.
