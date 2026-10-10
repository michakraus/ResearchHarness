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
- a live probe whose prompt the model refuses on its own, such as a read of a credential file in a
  subagent: no tool call runs, and the probe measures nothing; probe with a command the model has
  no reason to refuse (W1 clause 6, *Unify the agent configuration*)
- a settings change predicted to leave Claude Code's dialogs as they are: a `git -C` command runs
  sandboxed and is approved unless an `ask` or `deny` names it, so narrowing a `git -C` ask removes
  dialogs whatever `allow` holds (L, round sixty-four P2, *Unify the agent configuration*)

## A numerical method

- `NaN` and `Inf` in an input, and at a trial point; a slope of `-Inf` read as descent
- a subnormal input; a result that underflows to zero; an anchor value near `floatmin`
- a scale of `1e±8`, and a scale that is **not a power of 2** — a power of 2 is exact and hides
  round-off
- the other precision: `Float32` and `Float64`; `Float16` where a type parameter admits it
- a first trial step of `Inf`, or above the caller's ceiling; an invalid ceiling
- an empty, a one-element or a zero-width case; the edge of a grid
- a tie that round-off decides, for example a safeguard of the form `w <= wprev / 2`
- a square or a product of unscaled quantities, which overflows at extreme scales
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

## A type or an interface

- an argument of another integer type, such as `Int32`, where the code widened `Int`
- a concrete storage type passed through `Type{<:X{T}}`, which a method may ignore
- every structured leaf of a container, such as a skew-symmetric or a triangular leaf beside the
  symmetric one
- a device array under `allowscalar(false)`
- the precision of a device: Metal has `Float32` only, and a `Float64` array or scalar raises an
  error. Query `KernelAbstractions.supports_float64(backend)`; do not hardcode a default. Metal has
  no `qr` and no `svd` on an `MtlArray` (the solver package's capability spike)
- the backend of a result, not only that it runs: `zero(Y)` of a device point (G5, *Simplify GO and
  GML for 0.9*)
- a deleted method of a dependency's function, whose generic fallback then answers with another
  shape, here or in the dependency's own methods (G5, `alloc_h`)
- a default accessor on a supertype that one of the package's own subtypes cannot answer (G5,
  `gradient(::BFGSState)`)
- a cotangent of the leaf's own structured type, and one of another precision, where the hook asks
  for a leaf of the same type (G7, K17 and K20)
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
- a malformed configuration file or one that is not UTF-8: a traceback exits 1, which the verb
  contract reserves for "changes to make" (D1 round 1, *Unify the agent configuration*)
- a well-formed file with a value of the wrong type, such as a list or a table where a string is
  expected: a membership test raises `TypeError`, a traceback that exits 1; check the type before
  the value (Q round 1, *Unify the agent configuration*)
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
- a test fixture that runs `git` with the caller's environment: inside a git hook, `GIT_DIR`
  names the caller's repository, so the fixture's `init`, `add` and `commit` land there; drop every
  inherited `GIT_*` (E1a round 1, *Publish the harness as ResearchHarness*)
- a guard that turns a reader's failure into a warning: a pre-parse of its own accepts what the
  reader rejects (a UTF-8 BOM), and a list of exception types misses one the reader raises
  (`TypeError` from a list placeholder); wrap the reader's own call, and test each input class
  that reaches it (D2 verify 2 and verify 3, *Unify the agent configuration*)
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
- a new `test/Project.toml` that makes `Pkg.test()` write a `test/Manifest.toml` the
  `.gitignore` does not name
- a renamed file whose old name stays in a comment under `src/`, `ext/` or `scripts/`
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
  a verb that reads the example profile and the other rows do not: trace what each verb reads,
  per source, and compare every row (F3, *Publish the harness as ResearchHarness*)
- a page that says what a verb does from its name, not its code: the skip conditions, the extra
  files it writes and the files it deletes are missing. Read the verb's body, not its help line
  (F3, *Publish the harness as ResearchHarness*)
- a security page that says a mechanism stops a write, while a command outside the sandbox, an
  excluded command, bypasses every list of the sandbox; and a rule for "outside the sandbox"
  that leaves out a condition, such as no redirection to a file (F3, *Publish the harness as
  ResearchHarness*)
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
