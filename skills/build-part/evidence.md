# The evidence table of a part

**Contents**

- [Rules for a row](#rules-for-a-row)
- [The tools](#the-tools)
- [Which mutants run](#which-mutants-run)
- [A warm session for probes](#a-warm-session-for-probes)
- [Hostile inputs](#hostile-inputs)
- [Allocation assertions](#allocation-assertions)

`julia-builder` writes this table before it changes code, `julia-critic` writes its own before it
reads the diff, and `plan-parts` writes each *Done when* so that the table can be filled. The
builder's table goes into its report and into the pull-request body.

**A part is done when every clause has a row, and every row says PASS.** A clause with no row is
not done. A row without a command and its output is not evidence.

**The clauses** are the part's *Done when*, split into statements that one command can show false,
and the clauses of the plan's §V. Where the plan keeps its benchmark somewhere else — a
`verification` cell, a numbered check list — the plan's §V says where.

**Each clause has a domain**: the finite set of inputs it names — "each repository of §1.1", the
decided edges, the named mutants, an example the section gives. A clause with *every*, *each* or
*one … per* that names no set has the domain of the part's own tests and the inputs its section
describes. A failure inside the domain fails the clause; a failure outside it is *found late*,
recorded and not blocking.

| clause | test or command | on the unmodified tree | on the branch | verdict |
|:--|:--|:--|:--|:--|

## Rules for a row

- **A test that reproduces a defect FAILS on the unmodified tree.** One that passes there PINS
  behaviour, and the row says so. `pins.jl <worktree> origin/main <unit>` gives the column for a
  whole test file. Where the part names a mutant, the row quotes `mutate.jl`'s
  verdict on it: CAUGHT, or the clause is not met.
- **The unmodified tree is `origin/main`**, never a draft of the fix from this session. "Each new
  test fails before the fix" is a claim about each test: name the tests that reproduce a defect
  and the tests that pin behaviour as regression guards.
- **Where the fix adds a more specific method**, `invoke` with the old method's signature gives
  the pre-fix value in the same process. Where the fix edits a method body, use `pins.jl`.
- **A tolerance is a number with a reason**: `√eps(T)`, a multiple of `eps · κ`, the order of the
  method, or a measured noise floor. "To tolerance" is not a tolerance until the row states the
  number.
- **A measurement names its method**: a cold process, the number of BLAS threads, the number of
  runs, the machine and the package versions.
- **"The suite is green" is evidence only for a clause that the suite covers.** Name the test file
  or the testset.
- **A device clause names its run.** A Metal run goes through Kaimon. A CUDA or ROCm run is done by
  hand on the user's machine: the builder writes the script and the exact command, and the row
  quotes the machine, the versions and the output. The critic does not repeat a device run; it
  judges the recorded output and marks the row *by hand, not re-run*. A device row with no output
  is a FAIL.
- **A clause that the part cannot meet stops the part.** The report says `Met: no`, with the
  reason. Do not weaken the clause, and do not widen a tolerance until a test passes.

## The tools

Each prints a short verdict and exits with the tests' status, so no command needs `$?`.
They run under `~/Research/Harness/scripts/`:

| to | run |
|:--|:--|
| run the `core` test files the diff can reach by the mirror of `src/`, and the files under `test/quality/`; where a `Project.toml` changed, the full `Pkg.test()` | `julia --startup-file=no run-tests.jl <worktree> affected` |
| run a group, and report each `core` file above its 60 s, cold | `julia --startup-file=no run-tests.jl <worktree> core` |
| see that selection without running it | `julia --startup-file=no run-tests.jl <worktree> select` |
| run named test files, by path under `test/` or by testset label | `julia --startup-file=no run-tests.jl <worktree> <unit> ...` |
| run the whole suite, `Pkg.test()` | `julia --startup-file=no run-tests.jl <worktree> full` |
| check that a test catches a mutant | `julia --startup-file=no mutate.jl <worktree> <file> '<from>' '<to>' <unit> ...` |
| run a list of mutants, each with one or more edits, one verdict line each | `julia --startup-file=no mutate.jl <worktree> --list <mutants.toml> <unit> ...` |
| run a list of mutants in one warm process; each survivor runs again cold | `julia --startup-file=no mutate.jl <worktree> --warm <mutants.toml> <unit> ...` |
| run again only the survivors of a list's last run, after a new test | `julia --startup-file=no mutate.jl <worktree> --warm <mutants.toml> --only SURVIVED <unit> ...` |
| check a list of mutants without running it | `julia --startup-file=no mutate.jl <worktree> --check <mutants.toml>` |
| write the operator mutants of the diff against the base as a list | `julia --startup-file=no mutants.jl <worktree> <mutants.toml>` |
| run the branch's tests on the base's `src/` | `julia --startup-file=no pins.jl <worktree> origin/main <unit> ...` |
| run a probe script with the package and its test dependencies | `julia --startup-file=no --project=<worktree> -e 'using TestEnv; TestEnv.activate(); include("<probe>.jl")'` |

The header of `mutate.jl` gives the form of a mutant list. Its TOML strings take Unicode and
several lines, with no shell quoting. A mutant whose `from` does not occur exactly once, whose
mutated file does not parse, or that adds an undefined name is INVALID and does not run: it would
fail to load and read as CAUGHT. Fix the list; run `--check` on a new list before you run it.
`--warm` runs a list of more than 20 mutants in warm processes and each survivor again cold; a
list of 20 or fewer, as a named list is, it runs cold, one copy per mutant, about 15 s each,
because the warm mode's coverage runs and its cold sample of the kills cost more than they save
there (`MUTATE_WARM_MIN` sets the 20).
`--warm` first runs one smoke mutant, an `error` call in each function that the list changes:
when no unit reaches one of them, every verdict is UNKNOWN, and the units are the wrong ones.
Each run writes `<mutants>.result.json` beside the list, with every verdict and the survivors
grouped by line. A run of the same list on the same tree, with the same units, keeps each
verdict and runs nothing; any change under `src/`, `ext/` or `test/` runs every mutant again.

## Which mutants run

| kind | written by | run by | a survivor |
|:--|:--|:--|:--|
| **named**: each mutant of the part's *Tests catch* | `plan-parts` | the builder, once, with `--warm`; each round 1 critic again | fails its clause, and blocks |
| **doubted**: a mutant for a clause whose test a critic doubts | the critic | the critic, in the same list as the named ones | blocks when it is in a clause's domain |
| **generated**: every operator mutant of the diff, from `mutants.jl` | the script | the dispatcher's runner, before round 1, only where the plan's §L asks for it | goes to the builder, which adds a test or shows that the mutant changes no behaviour, then runs the list again with `--only SURVIVED` |

**A mutant's verdict holds only for the shapes and seeds that its units run.** One shape and one
seed can land among the cases a mutant passes. Run the test file's own loop of shapes, with many
seeds, and quote "fails n of N". Try more than one mutant. Where the code runs only on real element
types, add a mutant that spells `adjoint` as `transpose`: only a complex element type separates the
two. Report which mutant each assertion catches, not a claim about "the suite".

No agent sweeps the whole diff on its own. A sweep's output enters the context that each later
call reads again, and its survivors are a search with no end. Where the plan's §L asks for a
generated sweep, the builder writes these two commands under *Left for the dispatcher*:

```
julia --startup-file=no mutants.jl <worktree> <worktree>/.claude/scratch/generated.toml
julia --startup-file=no mutate.jl <worktree> --warm <worktree>/.claude/scratch/generated.toml --jobs 4 <unit> ...
```

The units are the test files that reach the changed source files. On part K of the solver package,
794 generated mutants took 17 minutes with 4 workers, about 3 GiB each, and left 73 survivors.

`run-tests.jl` and `mutate.jl` run with the `--check-bounds` of `Pkg.test()` on the same Julia —
`yes` up to 1.12, the session's `auto` from 1.13 — so that they can run beside a suite without
breaking its precompile images. Never pass another `--check-bounds` while a suite runs. A run on a
Julia before 1.13 skips every allocation assertion guarded by the flag, so an allocation row needs
a cold process of its own. An unguarded assertion runs there, and can fail (*Allocation
assertions*).

**Another Julia is one command.** `julia +1.11 --startup-file=no run-tests.jl <worktree> full`
runs the suite on the 1.11 floor. Where another minor version resolved the manifest, `run-tests.jl`
and `mutate.jl` run in a copy without it, and the worktree's manifest stays as it is. Make no copy
of your own.

**The floor runs once.** A second Julia doubles the suite time, and the CI `min` job runs the floor
on every pull request. Leave `julia +<floor> … run-tests.jl <worktree> full` for the dispatcher in
round 1, and again only for a fix diff that changes an `@allocated`, `@inferred` or JET assertion
or a `VERSION` branch. The floor is the lower bound of `julia` in `[compat]`.

`TestEnv` builds the test environment outside the worktree. Never run `Pkg.develop`, `Pkg.add` or
`Pkg.instantiate` with `--project=<worktree>/test` or in the worktree: it changes the tracked
`test/Project.toml`, or writes a `test/Manifest.toml` that every later `Pkg.test()` resolves
against. Write a probe file with the Write tool, not with a heredoc. A critic writes under
`~/Research/.scratch/critic/<Repository>-<part>/round-<N>/`, and never into an earlier round's
directory: those probes are the reproducers that the next verify round runs again. The builder
writes under `<worktree>/.claude/scratch/`. In a worktree-isolated agent the Write tool refuses
every path under `~/Research` outside its worktree, `~/Research/.scratch/` included. `.claude/` is
ignored by the global git rules, `mutate.jl` does not copy it, and it goes with the worktree.
`$TMPDIR` is no place for it: every session on this machine shares it.

## A warm session for probes

A probe in a fresh process pays for the process start, the package load and the compilation:
4–30 s in a small package, minutes in a large one. The same call in a warm Kaimon session takes
well under a second after its first run. **Probe in the session; write a file only for what must
last.**

1. **Start one session for your tree**: `start_session(project_path = <tree>)`. The builder's tree
   is its worktree, where Revise reloads `src/` before each call. A critic's tree is a copy,
   `rsync -a --exclude=.git --exclude=.claude <worktree>/ <round directory>/tree/`: two critics
   judge one worktree at once, and one path has one session.
2. **Load the test environment in a call of its own.** `TestEnv.activate()` alone fails in a
   session, because the package's project is active:

   ```julia
   import Pkg, TestEnv
   Pkg.activate(; temp = true, io = devnull)
   Pkg.develop(path = "<tree>"; io = devnull)
   TestEnv.activate("<Package>")
   ```

   Then `using <Package>, Test` and the test dependencies, in a call of their own. A call that
   holds a `using` returns its value, but not the output of the functions it calls.
3. **Send each probe as `ex(e = …, q = false, ses = <key>)`.** The value of the last expression is
   the answer. The `print`, `println`, `@show` and logging calls of the code you send are removed;
   the output of a function you call comes back. A test file runs as
   `@testset "probe" Base.include(Core.eval(Main, :(module $(gensym(:Probe)) end)), "<file>")`, a
   fresh module each time, as `run-tests.jl` does. `Module()` does not serve: its module has no
   `include`, so a test file that includes a helper fails. A call that runs longer than 30 s becomes a
   job; collect it with `check_eval`, at most once a minute.
4. **Keep what must last as a file.** A probe that shows a defect becomes the critic's reproducer,
   and a probe that pins a clause becomes the builder's test. Run the file once in a fresh process
   before you cite it.
5. **Shut the session down before you return**: `manage_repl(command = "shutdown", session =
   <key>)`. Nothing else closes it. A builder that is resumed starts a new one.

Four things stay out of the session: a measurement (`@allocated`, a timing), which needs a cold
process; a run on another Julia; the evidence row of a test, which is `run-tests.jl`'s; and any
call after a change of `Project.toml`, because Revise reloads `src/` and no dependency — restart
with `manage_repl(command = "restart")`. Nothing in the session writes into the worktree: no
`Pkg` call on it, no file write.

**Ask the session instead of writing a probe:**

| question | tool |
|:--|:--|
| which method runs for these arguments | `search_methods`, or `ex` with `@which f(x)` |
| the fields and parameters of a type | `type_info`, with a concrete type such as `Foo{Float64}` |
| the names a module defines | `list_names` |
| what a macro expands to | `macro_expand` |
| the locals of a failing call | `debug_exfiltrate` on code that holds `@exfiltrate`, then `debug_safehouse`. Never `@infiltrate`: without the Kaimon TUI the session stays paused until a restart |
| type stability | `ex`: `using JET` in its own call, then `JET.report_call(f, (T,))`, or `sprint(io -> code_warntype(io, f, (T,)))` |

## Hostile inputs

Probe a numeric argument on this set, in each precision the part claims (`Float32`, `Float64`, and
`BigFloat` where the code is generic): `zero(T)`, `-zero(T)`, `nextfloat(zero(T))`,
`floatmin(T)`, `eps(T)`, `one(T)`, `floatmax(T) / 2`, `floatmax(T)`, `T(Inf)`, `-T(Inf)`,
`T(NaN)`, and the scale family `s * x` for `s = 10.0^k`, `k = -8:4:8`. An argument of another
float type than the working type (a `Float64` bound for a `Float32` method) is a case of its own.
Check each result against the part's contracts, not only for the absence of an error: a finite
result where the contract promises one, a return code that matches what the code measured, and a
cost that does not depend on the scale.

## Allocation assertions

**An `@allocated … == 0` assertion measures through a function barrier**, whose arguments have
concrete types and which calls the function once before it measures:

```julia
allocations(f::F, a::A) where {F, A} = (f(a); @allocated f(a))
```

Julia 1.11 boxes a closure over a loop variable, a captured type parameter and an unspecialised
varargs splat, where 1.12 and 1.13 do not. An assertion at testset scope, or through such a helper,
then fails the CI `min` job although the code allocates nothing. Where no barrier can hold the
call, guard the assertion with `Base.JLOptions().check_bounds != 1` and say in the row that the
floor does not check it. A control, `@test allocations(collect, a) > 0`, shows that the helper sees
an allocation.
