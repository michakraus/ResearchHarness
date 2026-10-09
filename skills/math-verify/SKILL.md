---
name: math-verify
description: "Check one mathematical statement in Julia, analytically, symbolically or numerically, together with a case that should make the check fail, and keep the check as a script in scripts/. Load it first, before answering from memory or reading a paper, whenever the request asks whether a formula, an identity, a scheme or a property holds, even a one-line question. Typical words: derivation, identity, proof, prove, lemma, symplectic, symplecticity, energy, invariant, conserved quantity, Jacobi identity, Poisson bracket, order of convergence, consistency, exactness, holds, numerical confirmation, Symbolics. For every claim of a whole .tex manuscript, use the latex-verifier agent; for timings or allocations, julia-performance."
---

# Verifying a mathematical statement

## Julia, always

Every analytic, symbolic or numerical check is written in **Julia**. `SymPyPythonCall.jl` is
acceptable where Julia has no equivalent, but the surrounding script is Julia.

The bracket package is the model: SymPy appears **only inside `scripts/`**. Prefer `Symbolics.jl` where it suffices.

Known symbolic traps in this tree:

- `simplify` **harms code generation**. `simplify=false` is the default of the Euler–Lagrange package; leave
  it alone.
- `simplify` and `substitute` on a shared expression are writes, even when the result is
  discarded: later fields generate their terms in a different order. Prove a code-generation change
  harmless by A/B against a pristine worktree of the same head, with `--check-bounds=yes`. Compare
  the rebuilt functions and their values; an invariant such as orthonormality cannot show it.
- `==` between two separately generated functions passes or fails by platform rounding. Split it
  into `.f ===` (same function), `.p ==` (same parameters) and the values at `rtol = 1e-12`. A
  local run on this `apple-m4` host proves nothing about the CI runners.
- An unsubstituted `Differential(t)` can survive codegen, producing a function that throws only
  when evaluated — and if nothing evaluates it, silently.
- Anything to be symbolically differentiated must branch with `max`/`min`, not `?:`.

## Design the check before running it

**State what would make it fail, and run that case too.**

The recorded failure: `so(3)` was used as a control for the Jacobi identity. It satisfies Jacobi
because it is **Bianchi class A** — a reason unrelated to the property under test — so it passed
for every case, including the ones it was meant to exclude. An erratum in the papers followed.

A control that cannot fail is not evidence. Before trusting a green result, ask:

1. What input should make this check report failure?
2. Does it?
3. Is the property I measured the property I claimed, or a weaker one that happens to coincide?

For a structure-preservation claim, that third question is where the mistakes live.
`SLRK` is **constraint-preserving but not symplectic**; the manuscript's proof had a hole, and
the checks that "confirmed" symplecticity were measuring constraint preservation.

## Numerical checks

- Compare against a **tolerance derived from the method**, not a round number. A test that
  passes at `1e-8` because nothing was computed passes just as well.
- Distinguish "the invariant is preserved to order h^p" from "the invariant is preserved". Fit
  the rate; do not assert a single residual.
- A finite result is not a converged one. Check the convergence flag, not just the return value.
- Gauge- and parametrisation-dependence is a real effect here: DVRK's order depends on the gauge
  of ϑ, and Poincaré invariants are gauge-blind by construction. Know which before writing a
  test that "detects" it.

## Archive the script

The script goes into the relevant repository's `scripts/` directory and is cited from wherever
the claim is written down — `\script{}` in a manuscript, a link in a `Knowledge/` page.

**A claim whose script was thrown away is an unverified claim**, however convincing the run was
at the time. `/tmp` is not an archive.

## Report

```
## <statement being checked>

Verdict: holds / fails / holds under <conditions> / inconclusive
Method:  <analytic | symbolic | numerical>, <what was computed>
Control: <the case expected to fail, and whether it did>
Script:  <repo>/scripts/<file>
```

If the answer is "holds only under conditions the statement did not mention", that is the
finding — say so rather than reporting a pass. And record a **negative** result as carefully as
a positive one; a disproved conjecture that is not written down gets re-attempted.
