# The edge catalogue

The edges that critics found after round 1, by kind of part. `plan-parts` writes a part's *Decided
at the edges* from this list, one line per edge with its answer. The round-1 critic of
`julia-critic` probes every edge of the part's kind that the section does not decide.

**An edge that a later round finds joins this list.** After a loop, the dispatcher adds each class
of a *found late* defect that is not here yet, in one line, with the part that found it, to the
source of this file, `~/Research/Harness/skills/build-part/edges.md`; the user's `harness
install --apply` installs it.

**Contents**

- [A part that predicts what another tool reads or does](#a-part-that-predicts-what-another-tool-reads-or-does)
- [A numerical method](#a-numerical-method)
- [A type or an interface](#a-type-or-an-interface)
- [A tool that reads files or a tree](#a-tool-that-reads-files-or-a-tree)
- [A step that runs a user's script](#a-step-that-runs-a-users-script)
- [A lint cleanup](#a-lint-cleanup)
- [A migration of tests or of text](#a-migration-of-tests-or-of-text)

## A part that predicts what another tool reads or does

A guard, a renderer that passes source text through, a strict parser that stands in for another
reader: each gap between the copy and the original is a defect, and each critic round finds a
neighbour of the last one. Decide the design before the build, in *Decided at the edges*:

- **the design: fail closed or canonical re-emission, never emulation.** Refuse every input the
  code cannot read for certain, or write the value in a form whose reading is certain, such as a
  JSON string in YAML. A spec that makes the code mirror another tool's parsing is a `decision`
  part (O1 and O2, *Unify the agent configuration*; part B, *Unify the test suites*)
- the closed set of inputs the code accepts, written as a grammar or a list; everything else is
  refused with its line
- the reader the tests compare against: the other tool itself, run on the case, where it can run
- a closed grammar that fails closed but is narrower than the tool that reads the value: real
  values of that tool are refused, such as a Bedrock model ID with `:` or a Vertex one with `@`;
  list the other tool's real value forms in the grammar's cases (N3 verify 2, *Unify the agent
  configuration*)
- a probe that names the version of the tool's CLI, while the run it measures used another build:
  read the version from the run's own record, such as a transcript's `"version"` (X, *Unify the
  agent configuration*)
- a configuration key moved onto an entity that holds more roles: whatever a renderer attaches to
  the key's entity now reaches every role, such as a round-1 council preamble in the verify critic.
  Grep the renderers for the key's consumers (X, *Unify the agent configuration*)
- test fixtures of another tool's output written from memory of its format: record them from the
  tool and strip the private fields; keep synthetic ones only for shapes the tool cannot give on
  demand. A recording that starts a nested `claude -p` is the user's to run, because the auto-mode
  classifier refuses it (Q round 1, *Unify the agent configuration*)
- a filter on the tool name tested only with an event that lacks the input the filter guards: a
  `read` event with no `command` passes with or without the `shell` filter; give the other tool's
  event the guarded input (W1 round 1, *Unify the agent configuration*)
- a case meant for one guard that an earlier check stops first: `sed -i` never reaches
  `no-shell-file-write.py`; give each guard a case that only it refuses (W1 round 1, *Unify the
  agent configuration*)
- **a case meant for one guard that a *later* guard now also catches, when both raise the same error
  type:** a fix adds an `isempty` guard after a two-times guard, and a one-time input trips the new
  guard with the same `ArgumentError`, so an `isa ArgumentError` test passes whether or not the
  two-times guard is dropped, and a named mutant that the test caught survives (P25 verify 2,
  *Rewrite the reduced basis packages*). **Assert the refusing guard's own phrase, not the type
  alone.** The mirror of the entry above: there an earlier check hides the case, here a later one
  hides the mutant
- **a refusal message that names several values, tested on a case where two of them are equal:** a
  message can name the outer scale and the march's scale, and a test at `χ = 2` matches either, so a
  mutant that drops one of the two sentences survives; the equal case never separates them. Give
  each named value a different number, and assert each at its own place in the phrase. This binds a
  critic's or an advisor's prescribed case too (P38b verify 2, *Rewrite the reduced basis packages*)
- a live probe whose prompt the model refuses on its own, such as a read of a credential file in a
  subagent: no tool call runs, and the probe measures nothing; probe with a command the model has
  no reason to refuse (W1 clause 6, *Unify the agent configuration*)
- a settings change predicted to leave Claude Code's dialogs as they are: a `git -C` command runs
  sandboxed and is approved unless an `ask` or `deny` names it, so narrowing a `git -C` ask removes
  dialogs whatever `allow` holds (L, round sixty-four P2, *Unify the agent configuration*)
- a check that reads a field the tool fills from several backends, or that the host's own
  configuration reshapes: `git`'s `%G?` is `G` for a trusted OpenPGP or X.509 signature as well as
  an SSH one, and `log.showSignature = true` puts text before the format. Pin the backend and the
  options on the call (`-c gpg.openpgp.program=false`, `--no-show-signature`), and test each
  backend the host can hold (E1 round 1, *Synchronise the machines with chezmoi*)

## A numerical method

- `NaN` and `Inf` in an input, and at a trial point; a slope of `-Inf` read as descent
- a subnormal input; a result that underflows to zero; an anchor value near `floatmin`
- a scale of `1e±8`, and a scale that is **not a power of 2** — a power of 2 is exact and hides
  round-off
- the other precision: `Float32` and `Float64`; `Float16` where a type parameter admits it
- a mutant that no test can kill in one of the two precisions, because the only value of the other
  type that the test passes there converts exactly — a seed `c = Δ` in `Float64` whose only off-type
  value is `1.0f0`. Name the mutant as caught in the precision that kills it, and say why the other
  cannot (M1b verify 3, *Simplify the optimiser package and the learning package for 0.9*)
- a first trial step of `Inf`, or above the caller's ceiling; an invalid ceiling
- an empty, a one-element or a zero-width case; the edge of a grid
- a tie that round-off decides, for example a safeguard of the form `w <= wprev / 2`
- a square or a product of unscaled quantities, which overflows at extreme scales
- one scale formed as a scalar and applied to the whole gradient: `1/(‖R‖‖Y‖)` is subnormal in
  `Float32` once its product passes `1/floatmin(Float32)` and is zero at an extreme `Y` scale, where
  dividing each gradient entry by the two norms on its own leaves every entry finite. Divide per
  entry, and measure the scalar's own threshold before a comment claims it holds (M1b round 1b,
  *Simplify the optimiser package and the learning package for 0.9*)
- a counter or a budget that a relative stop cannot end, such as a bracket whose lower end is 0
- a status that hides a failure, such as *stalled* for a large increase
- a minimiser near an end of the bracket, where a safeguard on the interpolated step falls back to
  bisection (K13, round 5 of the loop benchmark)
- a near-quadratic merit, where the cubic coefficient of an interpolation is round-off and the root
  formula cancels (K7, round 5)
- a merit equal to `φ(0)` at two trials, and a merit that is not monotone, with `φ(α) = φ(0)` at a
  large step and a decrease at a smaller one: a stop on equal merits returns *stalled* where a
  decrease exists (K10, round 5; the C1 replay of l14)
- a stationary point that is a maximum, which a test of the slope's sign accepts; a test on a convex
  merit only does not show it (K12, round 5)
- a bit-for-bit comparison of a product built from `muladd`, across two compilation contexts: the
  compiler may contract the product into a fused multiply–add in one and not the other, so a
  `ComplexF32` static product differs by up to 2 ulp between a kernel and the host that evaluates
  the same expression, when every operand is bit-identical and the two Julia versions disagree about
  which context contracts (L-a verify 2 and 3, *Design the solver package*). Write every operand out
  of the kernel whole and compare those exactly, and compare the product at a stated ulp bound — a
  tolerance on the product alone hides a corruption of an operand that reaches only it.
- a solver swap that changes the quantity a tolerance bounds: the old solver tested `maximum(abs, F)`
  where the replacement tests `‖F‖₂`, so the same `abstol` is now stricter and rejects a solve the
  reference accepted (P44, *Rewrite the reduced basis packages*)
- an exception raised by the model inside the solve, which reaches the caller instead of the solver's
  own residual-and-iteration error, so the solve's failure contract does not cover it (P44, *Rewrite
  the reduced basis packages*)
- a complex element type where a norm feeds `maximum` (no `isless` on `Complex`), or where a buffer
  of the element type adds in another order than the real reduction it replaces, so a halving count
  shifts at a threshold (G8, the verifier after verify 3, and verify 4)
- a singular input to an in-place LAPACK call that ignores `info`, where the `\` it replaces raises
  `SingularException` (G8, the verifier after verify 6)
- a value check weakened from `==` to `rtol`, which leaves alive a mutant of an input such as the
  norm; keep a direct check of that quantity (G8, verify 5)
- an exact `==` between non-zero `@allocated` readings that reach `inv` or `exp`, whose allocation
  differs by 16–48 B between calls on Windows (G8, the verifier after verify 6 and verify 7)
- a `Float32` precision row whose fixture builds its scale as a `Float64` literal: the input is
  promoted, so the row measures the other precision, and every figure taken from it describes the
  promoted path — the check 3 ratios quoted in a CHANGELOG named a `Float64` input under a
  `Float32` heading. Convert the scale to `T` and assert `eltype(C) === T` in each input set
  (M4, *Simplify the optimiser package and the learning package for 0.9*)
- an untimed warm-up of a device measurement that is not synchronized, so the device's unfinished
  work lands in the first timed sample: synchronize the warm-up exactly as every timed call is
  (M4, *Simplify the optimiser package and the learning package for 0.9*)
- a docstring that states a kernel's guarantee without the domain its rows cover, such as the
  sizes and the scales: it reads as universal, while elimination overflows outside them. Name the
  tested sizes and scales in the contract, and where it fails (M4, *Simplify the optimiser
  package and the learning package for 0.9*)
- a docstring signature rewritten when the type alias it named goes away: the new spelling can be
  wider than the methods it documents, as `DataLoader(data::NamedTuple{(:q, :p)})` was for methods
  that require one array type. Compare each rewritten docstring signature with the `methods` it
  heads (B1, *Move the Hamiltonian and Lagrangian networks out of the learning package*)
- a bit-for-bit pin recorded from the parent commit whose value passes through a LAPACK
  factorisation of a seeded draw, such as the QR of a `StiefelManifold` initialisation: OpenBLAS
  0.3.29 (Julia 1.12.7) and 0.3.30 (1.13.2) give the same `randn` and different last bits of the
  orthonormalised weight, so the pin holds on the Julia that recorded it and reddens the floor
  suite. Record such a pin on both versions, and set the leaf to a fixed, exactly orthonormal
  matrix before the pinned pass (M5, *Simplify the optimiser package and the learning package for
  0.9*)

## A type or an interface

- an argument of another integer type, such as `Int32`, where the code widened `Int`
- a concrete storage type passed through `Type{<:X{T}}`, which a method may ignore
- every structured leaf of a container, such as a skew-symmetric or a triangular leaf beside the
  symmetric one
- a device array under `allowscalar(false)`
- the precision of a device: Metal has `Float32` only, and a `Float64` array or scalar raises an
  error. Query `KernelAbstractions.supports_float64(backend)`; do not hardcode a default. Metal has
  no `qr` and no `svd` on an `MtlArray` (the solver package's capability spike)
- a mutable static array offered as an iterate: `x + α * d` and `map` on an `MVector` or an
  `MMatrix` return a new mutable array, which the heap holds, so no method makes it `isbits` or
  allocation-free while the type stays (L-a round 1, *Design the solver package*). A plan that lists
  `MMatrix` among the iterates of a zero-allocation clause is naming the in-kernel storage that a
  storage spike decided; the clause belongs on the immutable form (`SVector`) alone, and a mutable
  static array that is an iterate for the call form carries no allocation promise.
- a non-`isbits` element type, such as `BigFloat`, on a path that builds an `MMatrix`: StaticArrays
  refuses `setindex!` on it, so an R1 kernel written for `Float32` and `Float64` has no `BigFloat`
  method (I round 1a, *Design the solver package*)
- the backend of a result, not only that it runs: `zero(Y)` of a device point (G5, *Simplify GO and
  GML for 0.9*)
- a deleted method of a dependency's function, whose generic fallback then answers with another
  shape, here or in the dependency's own methods (G5, `alloc_h`)
- a default accessor on a supertype that one of the package's own subtypes cannot answer (G5,
  `gradient(::BFGSState)`)
- a cotangent of the leaf's own structured type, and one of another precision, where the hook asks
  for a leaf of the same type (G7, K17 and K20)
- a pullback seeded with the other float type — `back(one(value))` with a `Float64` seed on a
  `Float32` network: one pullback hands back the seed's type at every leaf and the other converts it,
  so the two disagree where the data does not. Decide the seed's conversion per pullback and test
  each precision with a seed of the other type (M1b round 1a, *Simplify the optimiser package and
  the learning package for 0.9*)
- a device row checked only against a host twin that runs the same code, so wrong arithmetic passes
  both; and an equality over several storage blocks tested only by changing every block at once
  (G7, verify 2)
- a new call in a constructor path that allocates nothing itself but stops the caller from
  inlining, so construction allocates more (G7, K19)
- a module loaded by path as a plug-in: one that loads but lacks a required member gives a
  traceback, and one that calls `sys.exit` at import exits with its own code; check the members
  after the load and catch `SystemExit` (N2 round 1, *Unify the agent configuration*)
- a plug-in member that the loader checks for presence only, where the spec fixes its type, such
  as "one string": a list or `None` loads and prints its repr (I round 1, *Unify the agent
  configuration*)
- a stencil width whose length `(2w+1)^D` overflows `Int`: `w = typemax(Int)` on a 1×1 grid
  reported length 1; compute the length with checked arithmetic, or state a representable-width
  limit (P10, *Rewrite the reduced basis packages*)
- an index form that the signature admits and the parent refuses: a single
  `Vararg{Union{CartesianIndex, Tuple, Integer}, N}` `getindex` accepts mixed forms, which the
  `AbstractArray` fallback then rejects with its own `ArgumentError`. Uniform forms per method would
  add the ambiguities the part forbids, so decide the mixed case explicitly (P10, *Rewrite the
  reduced basis packages*)
- a function argument that a method only passes on: a method whose parameter is typed
  `rhs::Base.Callable` is not specialised on the function it is given, so its runtime dispatch costs
  bytes that an exact `@allocated` comparison against the caller's typed path sees — 16 to 800 B per
  call — and those bytes depend on what the process ran before. Type the parameter as
  `rhs::F) where {F <: Base.Callable}` (P41, *Rewrite the reduced basis packages*)
- a copy removed by preallocating the result with `similar(operand, …)`: it pins the element type of
  that operand, so a mixed input loses the type the product would have promoted — a Float32 basis with
  finite Float64 coordinates returned `±Inf Float32` instead of a finite Float64 result. Allocate with
  `T = promote_type(eltype(operand), eltype(input))` (P29, *Rewrite the reduced basis packages*)
- the scalar-indexing state restored by copying one value into both stores: `allowscalar` writes a
  task-local key and a process-wide default, and `@allowscalar` restores only the task-local key,
  so a test that captures the task-local value alone leaves the default changed for every later
  file in the process. Capture both, write neither, and assert both after the scope (M5,
  *Simplify the optimiser package and the learning package for 0.9*)
- a host array mixed into a device broadcast: a `JLArray` broadcast reads a host `Matrix`, so a
  test that compares values on the device cannot see one, and a mutant that allocates the encoding
  on `CPU()` survives. Assert the backend of what the layer produces (M5, *Simplify the optimiser
  package and the learning package for 0.9*)
- a parameter set read by position instead of by name: a forward pass that takes the head products
  by their position in a `NamedTuple` gives a different result for the same values in another
  order, where the parent read them by name. Read the fields by their names, and test a parameter
  set whose fields are reordered (M5, the learning package)
- a comment between a docstring and its definition: a `#` line after the closing `"""` detaches the
  documentation, and every `@ref` to the name turns into an unresolved reference. Put the comment
  inside the definition, and run the reference check (M5, the learning package)
- a rename of a field that one type carries and another keeps: an item names one architecture, and
  a second type of the same family keeps the old field name, so the family is now named two ways.
  Grep the family for the old name, and record the one the item does not name (M5, the learning
  package)

## A tool that reads files or a tree

- a path with a trailing `/`, and `.`
- a nested file with the same name as a top-level one, both reached and not reached
- a file or a `Project.toml` that is missing
- a value read from `git` on the depth-1 checkout of `actions/checkout`, where `git log -- <path>`
  returns HEAD for every path; and the same code in a tree with no `.git` or no `git` (S, *Collect
  the TikZ figures in the figure repository*)
- a test that breaks only one of several external calls, so a mutant that silences another one
  survives (S, *Collect the TikZ figures in the figure repository*)
- a comment or a string that looks like code
- a qualified call (`Module.f`), a macro with a module prefix, and a broadcast call (`f.(x)`)
- a line number that belongs to another file than the one read
- one violation that prints two lines, and many violations that print one
- a file name that follows another pattern than the one the rule names, such as `<p>_tests.jl`
  beside `src/<p>.jl` (part B replay)
- a line the pattern should match but for indentation or a trailing comment, such as
  `function f end  # note` (part B of the base package)
- a pattern with a literal `\n` over a text file that the Windows runner checks out with CRLF
  endings: it matches nothing there, and only the `windows-latest` job goes red (M, *Collect the
  TikZ figures in the figure repository*)
- a file read in text mode: Python's universal newlines turn CRLF into LF before a strict check
  sees it, so a CRLF test on a string passes and a CRLF file passes too (D1 round 1, *Unify the
  agent configuration*)
- a strict parser that replaces a YAML reader: a lone CR, NUL or another control character, a
  C1 or line-separator character, or a space or tab at the edge of a value, which YAML reads
  differently and the port accepts (D1 verify 2, verify 3 and the verifier, *Unify the agent
  configuration*)
- a malformed configuration file or one that is not UTF-8: a traceback exits 1, which the
  subcommand contract reserves for "changes to make" (D1 round 1, *Unify the agent configuration*)
- a well-formed file with a value of the wrong type, such as a list or a table where a string is
  expected: a membership test raises `TypeError`, a traceback that exits 1; check the type before
  the value (Q round 1, *Unify the agent configuration*)
- a JSON file nested deeper than the parser reads: `json.loads` raises `RecursionError`, which is
  not a `ValueError`, at a depth of about 1000 on Python 3.11 (P1 round 1, *Publish the harness
  as ResearchHarness*)
- a write check that tests only for write access: a target whose bytes stay and whose mode
  changes needs a `chmod`, which needs the owner, not write access (P1 round 1, *Publish the
  harness as ResearchHarness*)
- a rule over a directory named by an environment variable, compared as written: a path below
  its real location (`/private/tmp/…` for a `TMPDIR` under `/tmp` on macOS) passes; compare the
  resolved path too (P4 round 1, *Publish the harness as ResearchHarness*)
- a fix that changes how a file is read: it can remove a rejection that the old read gave for
  free, such as a lone CR read as a line break (D1 verify 2, *Unify the agent configuration*)
- a path the sandbox denies: `Path.is_file()` raises on Python 3.11 and returns `False` on 3.12
  and later, so an `except OSError` around it never runs there; check with `stat()` and test
  with `stat` patched (D1b round 1, *Unify the agent configuration*)
- a file mode that the code sets explicitly, tested under the default umask: 022 already gives
  0644, so a case for "a new file is 0644" passes with the explicit mode deleted; run the case
  under a umask of 077 (M round 1, *Unify the agent configuration*)
- a finish that quotes a critic's reproducer: the critics' probes live under the home directory,
  so the quoted path is a home path that the leak gate refuses; quote the probe by its file name
  (M finish, *Unify the agent configuration*)
- a bound tested only on its refusing side: a case for "nine is refused" and none for "eight is
  accepted" lets a mutant that refuses eight survive (D1b round 1, *Unify the agent
  configuration*)
- a rule over a directory tree tested at one depth: a case for `rules/a/x.md` and none for
  `rules/a/b/x.md` lets a mutant that refuses only one level survive (O2 verify 4, *Unify the
  agent configuration*)
- a test fixture `HOME` placed directly in the temporary directory: with `TMPDIR` unset, as on a
  Linux CI runner, its parent is `/tmp`, and a rule keyed on the parent of `HOME` changes; put
  `HOME` one level down (E1a round 1, *Publish the harness as ResearchHarness*)
- a stub of a system tool that prints the same on every system: a script that branches on the
  system then passes its other system's form too. Make the stub print what that system's tool
  prints, such as the 15-character name of Linux `ps -o comm=` (C1 round 1, *Synchronise the
  machines with chezmoi*)
- a test fixture that runs `git` with the caller's environment: inside a git hook, `GIT_DIR`
  names the caller's repository, so the fixture's `init`, `add` and `commit` land there; drop every
  inherited `GIT_*` (E1a round 1, *Publish the harness as ResearchHarness*)
- a test of a git hook that links its tools from the PATH: inside a real hook git puts its exec
  path first, and Apple's `git` started from a link to that copy cannot find `git-upload-pack`.
  The test passes in CI and in the suite and fails inside the push; run it once with
  `git --exec-path` first on the PATH (P7, after the merge, *Publish the harness as
  ResearchHarness*)
- a guard that turns a reader's failure into a warning: a pre-parse of its own accepts what the
  reader rejects (a UTF-8 BOM), and a list of exception types misses one the reader raises
  (`TypeError` from a list placeholder); wrap the reader's own call, and test each input class
  that reaches it (D2 verify 2 and verify 3, *Unify the agent configuration*)
- a guard that matches a command word with one literal space (`startsWith('rtk ')`): a tab or
  several spaces after the word, or white space before it, hides the rest of the command; match
  `\s+` and test a tab (P7 round 1, *Publish the harness as ResearchHarness*)
- a new value in a column of fixed width: a name as long as the width runs into the next column,
  and a test that lists only the old, shorter values cannot see it (G1 round 1, *Faster test
  suites for the learning package and the optimiser package*)
- a `HOME` before the first install, where a directory that the install creates does not exist
  yet: a dry run that reads it exits before it prints its warnings (N2 round 1, *Unify the agent
  configuration*)
- a check over commits that reads only their content: a file name that holds a leak, added by one
  commit and renamed by the next, passes; check the paths a commit adds too (E2 round 1, *Publish
  the harness as ResearchHarness*)
- a flag added to a `git` call for one input class (`-m` for a merge, `--root` for the root
  commit), with no case of that class: removing the flag survives (E2 verify 2, *Publish the
  harness as ResearchHarness*)
- a base fixture changed under an older mutation case: the case now breaks two rules, so it no
  longer isolates the check it names, and only another case still covers that check. After a
  fixture change, read each mutation case's output for the one line it expects (G4, *Faster test
  suites for the learning package and the optimiser package*)
- a case for "the checks count this result as wrong" that restates the accepted values in the
  test: a check that starts to accept the result survives; pass the result through the checks'
  own code (P3 round 1, *Publish the harness as ResearchHarness*)
- a refusal of one directory compared by path, even resolved: a case variant on a file system
  that ignores case, and the macOS firmlink below `/System/Volumes/Data`, name the same directory
  and pass; compare by device and inode (C round 1, *Ship the dotfiles kit in the harness*)
- a write to a path that holds something other than a regular file or a link: `write_bytes` on a
  FIFO blocks for ever, and a file that cannot be read raises `PermissionError`, a traceback that
  exits 1; check the kind before the open, and turn each `OSError` into the contract's exit 2
  (C round 1, *Ship the dotfiles kit in the harness*)

## A step that runs a user's script

- a `Module()` built to run the script, which has no `include` and no `eval`: a script that includes
  a helper beside it, or uses `@eval`, fails (E1, *Collect the TikZ figures in the figure repository*)
- an exception from a nested `include`, which arrives in one `LoadError` per level: an unwrap of
  one level turns an `InterruptException` into the step's own error (E1, verify 2)
- a keyword that no caller passes, with a layout tuned for its default only (M, *Collect the TikZ
  figures in the figure repository*)
- a test that matches the captured output of a `Base.julia_cmd()` subprocess: on CI the command
  carries `--color=yes`, so ANSI codes split the text the pattern expects, while a local run with no
  TTY passes. Run the test with `--color=yes` too (C1 fix 2, *Collect the TikZ figures in
  the figure repository*)
- a selection handed to parallel workers in the order that one input path builds it: the stated
  order holds for a named selection and a group, but `affected` adds the files in the order of the
  diff. Put every path's result in the stated order before the hand-off (I1, *Faster test suites
  for the learning and optimiser packages*)
- a scratch name keyed on the clock alone, such as a stamp to the second: two runs started
  together share it, and one run removes the other's files. Give each run a `mktempdir` (I1)

## A lint cleanup

- a deleted unused binding whose right side was the only reader of a value computed further up,
  which is then computed and never read (N6, `FIELDS` in *Clear the remaining fatou findings*)
- a family of near-identical blocks that the task names by a count, while the section's `Files` glob
  matches fewer members than the count: the block outside the glob keeps its copy, and the branch's
  CHANGELOG then claims the whole family went. Find the family by its interface — `<: Cache{`,
  `function Cache(` — not by the glob (P43, *Rewrite the reduced basis packages*)

## A migration of tests or of text

- doctests in the manual pages, not only in the docstrings
- a tolerance or an API that answers on the session's Julia and not on the `[compat]` floor:
  `eps(::Type{ComplexF32})` returns a value on 1.13 and raises a `MethodError` on 1.11, so a device
  test that uses it errors in CI's `min` job while every local run is green (J round 1 and verify 2,
  *Design the solver package*). Run the floor once per part, and write `eps(real(T))` wherever `T`
  may be complex.
- a new `test/Project.toml` that makes `Pkg.test()` write a `test/Manifest.toml` the
  `.gitignore` does not name
- a renamed file whose old name stays in a comment under `src/`, `ext/` or `scripts/`
- a removal of every citation of a directory, checked by its path only: a citation by the bare
  file name (`Loop-Benchmark.md`) or of a page in a subdirectory (`settings/settings.json.md`)
  survives; grep for the file name of every page below the directory (P6, *Publish the harness as
  ResearchHarness*)
- a CHANGELOG entry that states more than the change, or rewrites an old entry
- an entry that the source already marks closed or withdrawn (planning, *Move the open issues*)
- an entry longer than the one-sentence field of the target form (planning, *Move the open issues*)
- a generated copy of the source that `.gitignore` names, such as `docs/src/releasenotes.md`
  (planning, *Move the open issues*)
- a stale copy of the source under `.worktrees/` or `.claude/worktrees/` (planning, *Move the open
  issues*)
- a local path, such as `Tasks/…`, inside the moved prose (planning, *Move the open issues*)
- a value on `origin/main` that a plan-wide rule would rewrite, such as an existing `[compat]`
  bound in `test/Project.toml`. The default answer: the rule reaches only what the part adds or
  moves. In a `[workspace]` the test bound also holds the versions that the tests resolve, so a
  wider bound changes what CI runs (M5 and M1, *Unify the test suites*)
- a removed `test/` or `docs/` bound that was narrower than the root's: the tests now take what
  the root admits, a newer release or the root's floor. Only a fresh resolve with no
  `Manifest.toml` shows it, because a worktree's ignored manifest pins the old versions; pin the
  root's floor as well (R16 and A4, *Unify the test suites*)
- a floor raise whose `test/` or `docs/` environment needs a package that releases in a later
  gate: the environment cannot resolve, and a required check such as `Doctests` that
  instantiates it goes red. Read the required checks and each environment's deps before the
  gate order is fixed; two packages that need each other's release form a cycle that only a
  bypass merge or a temporary `[sources]` pin breaks (W2, *Make the base package's stubs public*)
- a floor raise that moves the CI `min` job onto a Julia where a timing check goes red, such as
  Aqua's 30 s persistent-tasks limit while a Makie extension precompiles on 1.11: run the quality
  tests on the new floor itself, not only on the newest Julia (W3, *Make the base package's stubs
  public*)
- a floor raise that moves the CI `min` job onto a Julia whose LLVM crashes on an architecture the
  local machine lacks, such as LLVM 16 on x86_64 aborting on a vectorised `BFloat16` conversion on
  1.11 while every aarch64 run passes: a local suite on the floor cannot show it, so the PR's `min`
  job on each runner architecture is the check, and a red `min` after a PASS is read before the
  part is called done (X, *Make the base package's stubs public*)
- a floor raise under an `[Unreleased]` heading that holds an earlier bullet naming the old floor
  value: the new bullet makes the old one false. Read the whole unreleased section, not only the
  added bullet (W3 of the integrators' base package, *Make the base package's stubs public*)
- a shrunk exception list whose members are still described away from the list: a printed
  message that gives one reason for every member, or a template header that counts or names
  them. Grep the tool's output strings and the installed templates, not only the comments beside
  the list (W, *Collect the TikZ figures in the figure repository*)
- a `main` that changes a file the branch moves: on a rebase, rename detection carries main's new
  hunk into the moved copy, where its relative `include` no longer resolves, and main's new
  comments name the old path. Read `git diff <base> origin/main` for each moved file before the
  finish round (E, *Faster test suites for the learning package and the optimiser package*)
- an earlier `[Unreleased]` bullet that quotes a time or a count the change supersedes, such as
  "takes 218 s" for a sweep the part cuts (D, *Faster test suites for the learning package and
  the optimiser package*)
- a name that a case-sensitive search misses, such as an organisation in lower case inside a
  host name: search the names with `-i` (D3, *Unify the agent configuration*)
- a rewritten line that removes the only introduction of a term, while a later line that no
  search finds still uses it, or still states the fact the rewrite moved (D3, *Unify the agent
  configuration*)
- a removed message that told the user to do something, such as a warning to export a variable:
  the same instruction lives on in a note of another repository, which the part's grep does not
  reach (I round 1, *Unify the agent configuration*)
- a sister page of the one the part fixes, with the same instruction: grep every page in the
  *Files* domain for the old path, not only the page the plan names (D3, *Unify the agent
  configuration*)
- a claim about another tool's history, such as "the first release with X", written from memory
  or copied from older prose: the floor can be right while the reason is wrong. Read the release
  notes, and cite them beside the claim (F1, *Publish the harness as ResearchHarness*)
- a CHANGELOG entry for moved text that says "only" some sentences changed, while the move also
  adds headings or a linking sentence: a reverse pass of the oracle, which looks up each block of
  the new pages in the old text, lists every new block (F2, *Publish the harness as
  ResearchHarness*)
- a table column whose cells follow two rules, such as a *read by* column where one row counts
  a subcommand that reads the example profile and the other rows do not: trace what each
  subcommand reads, per source, and compare every row (F3, *Publish the harness as
  ResearchHarness*)
- a page that says what a subcommand does from its name, not its code: the skip conditions, the
  extra files it writes and the files it deletes are missing. Read the subcommand's body, not its
  help line
  (F3, *Publish the harness as ResearchHarness*)
- a security page that says a mechanism stops a write, while a command outside the sandbox, an
  excluded command, bypasses every list of the sandbox; and a rule for "outside the sandbox"
  that leaves out a condition, such as no redirection to a file (F3, *Publish the harness as
  ResearchHarness*)
- a command block of a setup page that calls a subcommand with a relative path, such as `harness
  render systemd/<unit>`: it works only from the checkout, and with a redirect it writes an empty file
  from any other directory. Follow the page from its top and run each block in the directory that
  the steps before it leave (F4, *Synchronise the machines with chezmoi*)
- a clause that expects a framework feature, such as an edit link, on a layout that drops it,
  such as VitePress's home layout: build the page and grep the output for the feature (J2b,
  *Publish the harness as ResearchHarness*)
- a check that reads its input from a container, such as `<main>`, that one page lacks: the check
  then skips that page in silence. Fail on an empty container (J2b, *Publish the harness as
  ResearchHarness*)
- a page that maps components to the places they serve, written from each component's main use:
  a component whose source names a second place is missing there. Derive the map from every
  place that each source names, by script (J5, *Publish the harness as ResearchHarness*)
- a clause that sets a size bound which a layout library cannot meet for the largest input:
  measure the largest graph with the library while writing the spec (J2c, *Publish the harness
  as ResearchHarness*)
- a graph whose edge labels a layout library places in a band beside the edges: a label nearer
  another edge than its own reads as that edge's. Check that each label's own edge passes
  through it (J2c, *Publish the harness as ResearchHarness*)
- a reworded error message in an upstream package: a consumer's `@test_throws` matches the old
  text by substring, so the consumer's suite goes red while every upstream test passes. In a part
  that must not change a value, keep the message and record the wording in `KNOWN_ISSUES.md`; grep
  each consumer's tests for the old substring before a rewording (N2b, *Simplify the optimiser
  package and the learning package for 0.9*)
- a fixture a nested `@testset begin` block assigns inside an enclosing `@testset for`: it assigns
  the *outer* variable, so every later testset reads the new value, and an expected value built from
  it can turn vacuous — a Lorentz acceleration whose field a preceding testset has already set to
  zero reads `[0, 0, 0]` and the assertion holds whatever the code does. Bind the nested block's
  field to its own name, or with `local`, and assert that the expected value is not itself zero
  (P13 verify 2, *Rewrite the reduced basis packages*)
- a new entry that copies the form of the file's older entries instead of the house rule: where a
  `KNOWN_ISSUES.md` uses `## KI-<n> · kind · problem` with prose, a new entry still takes
  `### K<n> · <problem>` and the four bullets, and takes the next `K<n>` after the highest in the
  file, never the older scheme (P10 and P29, *Rewrite the reduced basis packages*)
- a fix that rewrites a comment about dispatch from a critic's sentence, not from the methods: a
  subtype such as `Manifold <: AbstractMatrix` makes "an array" false. Write the comment from the
  method table (G10 verify 2, *Simplify the optimiser package and the learning package for 0.9*)
- a rewritten comment whose *other* clause still states the old behaviour: the round removed the
  history phrases and left "whose two element types are free" beside a bound of
  `T1 <: Union{T, Integer}`, which the fix's own grep for history phrases cannot see. Write every
  clause of a rewritten comment from the method table, and grep the claim's own words as well as the
  history (M2 verify 2, *Simplify the optimiser package and the learning package for 0.9*)
- a comment that says nothing calls a function, in the file that the part now makes its caller: the
  header claimed "nothing in the package, the tests or the scripts called it", and the finder's grep
  over `src/` and `ext/` never reaches a `test/` header. Read the header of a test file the part
  gives its first caller, or of the file whose prose the part rewrites (M2 verify 2, *Simplify the
  optimiser package and the learning package for 0.9*)
- a moved table marked with the version of the commit that first wrote its cells, while a later
  commit measured them again on a newer dependency: name the last measurement. `git log -S` on a
  cell finds the last change of the value, not the last run that reproduced it (G10 round 1b,
  *Simplify the optimiser package and the learning package for 0.9*)
- a moved block whose own directional reference — "the table above", "the section below" — points
  at the neighbours it had before the move: the verbatim-move rule keeps the words and makes the
  direction false, and a byte-comparison of the moved block calls that move correct. Read the
  directions a moved block carries, and re-point the phrase with the plan's leave (P18 round 1c,
  *Rewrite the reduced basis packages*)
- a decided convention that the part must state in prose, such as a quantity's relation to the
  figure a reader knows it from: a docstring clause is a clause, and a fix builder that reads the
  `Done when` checks as the only deliverable skips it while every code check passes. Grep the
  decided block's own words in the files that *Files* names, and assert them from a test, so the
  verdict does not rest on reading the docstring (P38a verify 2, *Rewrite the reduced basis
  packages*)
- a mutant whose `from` calls a local that the mutant's own `to` defines later, or never: the
  harness reports VALID and CAUGHT, but the kill is the `UndefVarError`, not the defect the mutant
  names. Read the failed assertion's message, and spell the mutant so its only change is the
  defect (M5, *Simplify the optimiser package and the learning package for 0.9*)
- a round-off tolerance given as a constant relative factor with no derivation (`1e-9·n`): it
  accepts a real fraction at the domain's own scale (a stride of 100) and a whole step at 10⁹.
  Derive the bound from the roundings of the computed value, and test one input inside the bound
  and one outside (P38b verify 2, *Rewrite the reduced basis packages*)
