---
name: latex-revision
description: "Run a revision pass over a LaTeX manuscript with colour-marked changes. Triggers on: revise this paper, do a revision pass, mark the changes, \\fixed, \\added, \\rev, markchanges, address the referee report, respond to the reviewers, which changes are still unreviewed, strip the change markings, typeset it clean. Covers the marking macros, the colour lifecycle, and the scripts/ verification convention."
---

# LaTeX revision passes

Changes to a manuscript are **colour-marked**, and the markings are a **review queue**: a
marked passage is one the author has not yet accepted. Removing the colour asserts it was
reviewed. That is the whole point of the mechanism, and the reason a "tidy up the markup" pass
is destructive.

## The preamble block

```latex
% Verification pass <date>: corrections and additions are colour-marked.
% Set \markchangesfalse to typeset the document clean.
\newif\ifmarkchanges  \markchangestrue
\definecolor{fixcolor}{rgb}{0.70,0.10,0.10}   % corrected existing material
\definecolor{addcolor}{rgb}{0.10,0.25,0.70}   % newly added material
\newcommand{\fixed}[1]{\ifmarkchanges\textcolor{fixcolor}{#1}\else#1\fi}
\newcommand{\added}[1]{\ifmarkchanges\textcolor{addcolor}{#1}\else#1\fi}
\newenvironment{addedblock}{\ifmarkchanges\color{addcolor}\fi}{}
\newcommand{\fixmath}{\ifmarkchanges\color{fixcolor}\fi}
\newcommand{\addmath}{\ifmarkchanges\color{addcolor}\fi}
```

A later pass adds a **third colour**, so that round is distinguishable from material already
accepted:

```latex
\definecolor{revcolor}{rgb}{0.05,0.45,0.20}   % this pass
\newcommand{\rev}[1]{\ifmarkchanges\textcolor{revcolor}{#1}\else#1\fi}
\newenvironment{revblock}{\ifmarkchanges\color{revcolor}\fi}{}
\newcommand{\revmath}{\ifmarkchanges\color{revcolor}\fi}
```

Note the environment is **not** called `newblock`: `\newblock` is a LaTeX bibliography command
and `plainnat` uses it.

## Lifecycle

| state | meaning |
|:------|:--------|
| wrapped in this pass's colour | new, awaiting review |
| wrapped in an older colour | from an earlier pass, still unaccepted |
| unwrapped | **accepted** |

Rules:

- **Never strip a marker you did not resolve.** Stripping is the accept action.
- A new pass gets a **new colour**. Reusing the previous one destroys the distinction between
  what has been reviewed and what has not.
- Use `\fixed` for corrected existing material and `\added` for genuinely new material — the
  two colours answer different questions during review.
- Inside displayed maths use `\fixmath` / `\addmath` / `\revmath`; `\textcolor` does not survive
  every maths context.
- `\markchangesfalse` typesets clean. Do **not** delete the macros to produce a clean build.

## Every claim gets a script

```latex
\newcommand{\us}{\_\allowbreak}         % underscore that permits a line break
\newcommand{\script}[1]{\texttt{#1}}
```

A derivation, identity, constant or convergence statement is checked by a script in `scripts/`
and cited with `\script{}`. Julia, per the global rule — `SymPyPythonCall.jl` only where Julia
has no equivalent, harness in Julia.

**A control that cannot fail proves nothing.** The recorded case: `so(3)` used as a Jacobi
control satisfies the identity because it is Bianchi class A, a reason unrelated to the
property under test. It passed for everything, including what it was meant to exclude, and an
erratum followed. State what would make each check fail, and run that case too.

## The author reorganises deliberately

Moved, reordered or rewritten text is an authorial decision, not drift. Fix only what the move
broke — a dangling `\ref`, a duplicated sentence, a now-unused macro. Do not restore the
previous order and do not rewrite prose you were not asked about.

## Frozen snapshots

`arXiv_v1` and its siblings are what was submitted. They do not change — not the `.tex`, not the
`.bib`, not during a bibliography consolidation.

## Report

List, per pass: what was marked and in which colour, what was stripped (i.e. accepted) and on
whose instruction, which claims got a new `scripts/` check, and what was left marked for the
author. Never strip on your own initiative.
