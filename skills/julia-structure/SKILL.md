---
name: julia-structure
description: "Answer a structural question about Julia code with tools that read it as Julia, not with grep: julia-methods.jl, Kaimon's live session and julia-callers.jl give the methods of a name and where they are, the method that dispatch picks, the callers of a function, what a signature change breaks, and whether code is dead. Load it first, before searching files, whenever the request asks where something is defined, what calls it, what runs, or how a package is laid out, even a one-line question. Typical words: callers, call sites, methods, method table, dispatch, defined, definition, signature, impact, unused, dead code, refactor safely, module layout, architecture, codebase tour. For a claim that nothing uses something, delegate to the exhaustive-auditor agent; for a whole-package quality sweep, use julia-package-audit."
---

# Structural questions about Julia code

**There is no code graph in this tree.** The tools below answer these questions. The measurements
behind that choice are in `Environment/Notes/Helpers-and-MCPs.md`.

**Contents**

- [Why grep is not enough, and why a static index is not the answer](#why-grep-is-not-enough-and-why-a-static-index-is-not-the-answer)
- [Route by what you have](#route-by-what-you-have)
  - [`julia-methods.jl` — static, exact, no Julia session](#julia-methodsjl--static-exact-no-julia-session)
  - [Kaimon — the live session, for anything semantic](#kaimon--the-live-session-for-anything-semantic)
  - [`julia-callers.jl` — callers, from lowered IR](#julia-callersjl--callers-from-lowered-ir)
  - [Kaimon `grep_code` — the cross-repository search, no session needed](#kaimon-grep_code--the-cross-repository-search-no-session-needed)
- [The rule that matters more than the routing](#the-rule-that-matters-more-than-the-routing)

## Why grep is not enough, and why a static index is not the answer

Julia is multiple-dispatch. A method added to an existing generic is **not a new name**, so grep
finds your own call site and says nothing about the definitions already there. Worse, the normal
idiom for implementing an interface is a **module-qualified definition**:

```julia
ExampleBase.nsamples(ge::EnsembleProblem) = length(initial_conditions(ge))
```

That is a definition of `nsamples`, and no text search recognises it as one. About a fifth of this
tree is written that way — 1 668 such definitions in `Packages/*/src` against 5 938 plain
`function` forms.

A static index keyed by qualified name, with no signature, fails on exactly this: every method of
one name in one file collapses into one node.

## Route by what you have

| the question | the tool |
|:--|:--|
| what methods exist, and where — **without loading the package** | `julia-methods.jl` |
| which method **actually runs** for these arguments | Kaimon `search_methods` |
| who calls this; is it dead — **where the package loads** | `julia-callers.jl` |
| anything spanning all the repositories | Kaimon `grep_code` with an absolute `path`, then `grep` |

### `julia-methods.jl` — static, exact, no Julia session

```bash
julia --startup-file=no ~/Research/Harness/scripts/julia-methods.jl <package-dir> <name>
```

**`--startup-file=no` is not optional.** Without it the startup file loads Revise, whose file
watcher sprays EMFILE errors over stdout and can bury the report entirely.

Drives Fatou's language server over its `documentSymbol` request, which resolves **per method** and
keeps the qualified name and the signature. Walks the package's files itself, because Fatou's
`workspace/symbol` is lossy while `documentSymbol` is exact.

Use it first for "what is there". It needs no session and no manifest, so it is **the only tool
that works on a package that does not load**. Its grading against source is in
`Environment/Notes/Helpers-and-MCPs.md`.

It reports **definitions only** — no dispatch, no callers, and nothing built by `@eval`.

### Kaimon — the live session, for anything semantic

`search_methods` answers real dispatch on real argument types. It is the only tool that does, and
it is also the only one that sees methods generated at load time: `for name in (…) @eval` in
`src/integrators/dgvi/integrators_dgvi_common.jl:183` of the integrator package creates five types and
ten constructors that no parser can see.

Two costs, both easy to forget (the measurements are in `Environment/Notes/Helpers-and-MCPs.md`):

- **It answers about the manifest-resolved copy in `~/.julia/packages/`, not your working tree.**
  A dependency there can be a minor version behind. "Who calls this before I change its signature"
  is a question about the tree you are about to edit.
- **It sees one dependency cone** — the packages that one session loads, at hundreds of MB
  resident. Covering the tree is impossible, not merely expensive: some packages are mutually
  unsatisfiable.

### `julia-callers.jl` — callers, from lowered IR

```julia
include("~/Research/Harness/scripts/julia-callers.jl")
callers(ExampleBase.nsamples, [Example, ExampleTools])
dead(Example.compute_difference, [Example])
```

Enumerates every method whose **defining** module is one of the targets, then scans each method's
lowered IR for a `GlobalRef`. The defining module is not where the generic lives, which is why it
finds callers hiding behind `Base.length`, `Base.iterate` and `ExampleBase.eachsample`. A whole
package stack takes seconds.

It is also right where text search is wrong: it excludes a file that is `include`d nowhere.
`src/simulations/parallel_simulation.jl` of the integrator package is commented out at
`src/Simulations.jl:15`, and grep reports its call sites as live.

### Kaimon `grep_code` — the cross-repository search, no session needed

```
grep_code(pattern = "ExampleBase\\.nsamples",
          path    = "/Users/me/Research/Packages")
```

A real regex over the **live working tree**, so no index can go stale, and it needs only the
server — not a session, and not a package that loads. Each hit carries its **enclosing function or
struct**, which is what a bare grep cannot give. One call covers every repository under `path`, and
it reports the qualified definitions together with any in an `obsolete/` directory — which is dead
source, so read the paths rather than the count.

Three limits. It respects `.gitignore` unless `no_ignore = true`. It caps the body and prints the
true total in its header, so **read the header before concluding anything about completeness**.
And it resolves nothing: a hit is text, so it cannot tell a definition from a call, nor see a
method built by `@eval`.

## The rule that matters more than the routing

**An empty result is UNKNOWN, never a negative.** Each tool is blind in its own way:

| tool | blind to |
|:--|:--|
| `julia-methods.jl` | uses, dispatch, anything generated by a macro; `references` on a qualified name returns 0 |
| Kaimon | anything not loaded — unloadable packages, tests, unloaded extensions — and your working tree |
| `julia-callers.jl` | the same, plus calls built by `eval` or string interpolation |
| grep | qualified definitions as definitions; and it counts shadowing locals as uses |

So **say which tool produced the answer**, and when two disagree, say which you believe and why.
Never reconcile them silently.

Only the `exhaustive-auditor` agent may publish an all/none claim, and its basis is the text
sweep, not any index.
