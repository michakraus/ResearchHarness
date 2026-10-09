# Run a package's tests — the whole suite, a group, or only the test files a diff can reach — and
# print a short verdict. The exit status is the tests' status, so a caller never needs `$?`.
#
#   julia --startup-file=no run-tests.jl <package> [--jobs <n>] [affected [<base>] | select [<base>] | full | list | <unit> ...]
#
# The package's tests are in the layout of the test convention, which `test-layout.jl` checks and
# parses; this script reads the layout through the same parser. A repository in another layout
# is refused, with the violations that make it one, and only `full` runs there.
#
# `affected` (the default, base `origin/main`) selects the `core` test files that the diff against
# the base and the uncommitted changes can reach, by the mirror of the convention: `src/<path>.jl`
# selects `test/<path>.jl`, every test file of its directory, the test files of the directories
# above it that mirror no source file, and every file under `test/integration/` and `test/verification/`. A
# change under `ext/` selects the last two. A changed test file selects itself, a changed helper
# the test files that include it, and a changed `runtests.jl` the whole group. The quality files
# run with any selection. A changed `Project.toml` or `test/Project.toml` runs `full`.
# `select` prints what `affected` would run, and runs nothing. `full` runs `Pkg.test()`. `list`
# prints the test files, their groups and their labels.
# A `<unit>` is a group (`core`, `slow`, `doctests`, `metal`, `cuda`, `broken`), a test path
# relative to `test/`, or a substring of a testset label. A unit that names no test file is an
# error. `affected` selects from `core` alone, so it never runs `doctests`.
#
# A selection runs in one fresh process through `TestEnv`, which builds the test environment
# outside the package directory, each file in its own module under a `@testset` of its label, and
# each file timed once. A file's time is cold, compilation included, in the order of
# `runtests.jl`. A run of the group `core` reports each `core` file above the 60 s of the convention
# (D6); a named or `affected` run reports none, because its first file pays the compilation that
# the files before it pay in a `core` run. The report is advice: the exit status stays the tests'.
# The run prints the load average at its start.
# It runs with the `--check-bounds` that `Pkg.test()` of the same Julia uses — `yes` up to 1.12, the
# calling session's `auto` from 1.13 — so a selection and a suite beside it share the precompile
# images; a job with other flags would invalidate them. The log goes to ~/Research/.scratch/tests/.
#
# `--jobs <n>` runs the selection in n worker processes, or one per file where there are fewer,
# with the same flags and the same precompile images. Each worker takes the next file that no
# worker has taken, in the order of `runtests.jl`, so each file runs once, in its own module under
# a `@testset` of its label. The run passes where every worker passes. The log holds each worker's
# output under a line that names it, and the times file names each file's worker; a file's time
# is cold in its worker. A `core` run with `--jobs` gives no D6 verdict, because a file's time in
# a worker is not its cold time in the order of `runtests.jl`. `full` with `--jobs` runs the files
# of `Pkg.test()`, those of the groups of an empty `ARGS`, the same way, so it needs the layout of
# the convention. `--jobs 1` is the run without it.
#
# Where another minor version of Julia resolved `Manifest.toml` or `test/Manifest.toml` — a run of
# `julia +1.11 run-tests.jl` on a worktree that 1.13 resolved — the run goes to a copy without that
# manifest under ~/Research/.scratch/tests/copies/, removed after the run. Pkg would otherwise
# resolve the manifest again and write it into the package. The selection comes from the package.

include(joinpath(@__DIR__, "test-layout.jl"))

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`. The driver below appends it.
const HARNESS_ENV = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
HARNESS_ENV in LOAD_PATH || pushfirst!(LOAD_PATH, HARNESS_ENV)

using Dates

# Pkg 1.10–1.12 start the test process with --check-bounds=yes; Pkg 1.13 passes the session's own.
const CHECKBOUNDS = VERSION < v"1.13" ? `--check-bounds=yes` : ``

# D6: what a `core` file may cost cold, compilation included, in seconds. RUN_TESTS_BUDGET sets
# another, for the tests of this script; `main` reads it.
const BUDGET = 60.0

const PLAN = "Unify the test suites"

"""
The manifests of `pkg` that another minor version of Julia resolved, relative to `pkg`. Pkg
resolves such a manifest again and writes it back, so a run on this Julia goes to a copy without it.
"""
function foreign_manifests(pkg)
    own = "$(VERSION.major).$(VERSION.minor)."
    filter(["Manifest.toml", "test/Manifest.toml"]) do m
        f = joinpath(pkg, m)
        isfile(f) && !startswith(string(get(TOML.parsefile(f), "julia_version", "")), own)
    end
end

# `.claude/` holds the harness-made `.cc-writes`, whose `mkdir` the sandbox refuses in a copy.
copy_command(pkg, copy, leave_out = String[]) =
    `rsync -a --exclude=.git --exclude=.claude $(["--exclude=/$f" for f in leave_out]) $(pkg)/ $(copy)/`

"The test files that `runtests.jl` lists, as `Entry` values of `test-layout.jl`."
units(pkg) = layout(pkg).entries

"""
The violations that make the test layout of `pkg` another layout than the convention's: those of
D1 and D2, and those of D5 about `runtests.jl`. Empty where the layout is the convention's.
"""
function refusal(pkg)
    filter(violations(pkg)) do l
        tag = match(r"\[(\w+)\]", l).captures[1]
        tag in ("D1", "D2") || (tag == "D5" && !occursin("reads ARGS or ENV", l))
    end
end

"The files that `file` includes, directly or through another include, as absolute paths."
function reach(file, seen = Set{String}())
    ast = isfile(file) ? parsefile(file) : nothing
    ast === nothing && return seen
    for ex in collect_exprs(ex -> ex.head === :call && ex.args[1] === :include, ast)
        length(ex.args) == 2 && ex.args[2] isa String || continue
        p = normpath(joinpath(dirname(file), ex.args[2]))
        p in seen || (push!(seen, p); reach(p, seen))
    end
    return seen
end

gitlines(pkg, args...) = filter(!isempty, split(read(`git -C $pkg $args`, String), '\n'))

function changed(pkg, base)
    committed = gitlines(pkg, "diff", "--name-only", "$base...HEAD")
    worktree = [strip(l[4:end]) for l in gitlines(pkg, "status", "--porcelain", "--untracked-files=all")]
    return unique(vcat(committed, [split(p, " -> ")[end] for p in worktree]))
end

"""
The test files of `group` that a change of `paths`, relative to `pkg`, can reach, and why each
is chosen; or `:full` where a `Project.toml` changed.
"""
function affected(pkg, entries, paths; group = "core")
    any(p -> p in ("Project.toml", "test/Project.toml"), paths) && return :full
    t, src = joinpath(pkg, "test"), joinpath(pkg, "src")
    runnable = filter(e -> e.group == group, entries)
    rel(e) = relpath(e.path, t)
    top(e) = first(splitpath(rel(e)))
    pick, why = Entry[], String[]
    add(e, r) = e in pick || (push!(pick, e); push!(why, "test/$(rel(e)) — $r"))
    whole(p) = foreach(e -> top(e) in ("integration", "verification") &&
                           add(e, "tests the whole package, $p changed"), runnable)
    for p in paths
        endswith(p, ".jl") || continue
        if p == "test/runtests.jl"
            foreach(e -> add(e, "runtests.jl changed"), runnable)
        elseif startswith(p, "test/")
            abs = normpath(joinpath(pkg, p))
            foreach(e -> e.path == abs && add(e, "changed"), runnable)
            foreach(e -> abs in reach(e.path) && add(e, "includes $p"), runnable)
        elseif startswith(p, "src/")
            r = relpath(joinpath(pkg, p), src)
            d = dirname(r)
            for e in runnable
                de = dirname(rel(e))
                if rel(e) == r
                    add(e, "mirrors $p")
                elseif top(e) in OWN_DIRS
                    continue
                elseif de == d
                    add(e, "tests the files of src/$(isempty(de) ? "" : de * "/"), $p changed")
                elseif !isfile(joinpath(src, rel(e))) &&
                       (isempty(de) || startswith(d, de * "/"))
                    add(e, "tests the files of src/$(isempty(de) ? "" : de * "/"), $p changed")
                end
            end
            whole(p)
        elseif startswith(p, "ext/")
            whole(p)
        end
    end
    if any(p -> endswith(p, ".jl"), paths)
        foreach(e -> top(e) == "quality" && add(e, "quality check"), runnable)
    end
    return pick, why
end

"The test files that the units name: a group, a path relative to `test/`, or part of a label."
function named(entries, args)
    filter(entries) do e
        any(args) do a
            a in GROUP_NAMES ? e.group == a :
            normpath(joinpath(dirname(e.file), a)) == e.path || occursin(a, string(e.label))
        end
    end
end

"""
The script that runs `entries` in one process. As worker `worker` of a `--jobs` run, it runs each
file whose claim, a directory under `claims`, it makes first, and names itself in the log and in
each line of `times`. The workers resolve the test environment one at a time, under a lock beside
`claims`.
"""
function driver(pkg, entries, times; worker = nothing, claims = nothing)
    t = joinpath(pkg, "test")
    io = IOBuffer()
    # TestEnv from the harness environment, last in LOAD_PATH: the package under test comes
    # first, so its own dependencies win.
    println(io, "$(repr(HARNESS_ENV)) in LOAD_PATH || push!(LOAD_PATH, $(repr(HARNESS_ENV)))")
    if worker === nothing
        println(io, "using TestEnv; TestEnv.activate(); using Test")
    else
        # one worker at a time resolves the test environment, which may write the package's manifest
        println(io, "using TestEnv, FileWatching.Pidfile")
        println(io, "mkpidlock(TestEnv.activate, $(repr(joinpath(dirname(claims), "activate.pid"))); stale_age = 600)")
        println(io, "using Test")
    end
    println(io, "const TIMES = open($(repr(times)), \"w\")")
    println(io, "fresh() = Core.eval(Main, :(module \$(gensym(:Unit)) using Test end))")
    # `mkdir` fails with EEXIST where the directory exists, so exactly one worker claims each
    # file; any other failure stops the worker
    worker === nothing ||
        println(io, "claim(i) = try mkdir(joinpath($(repr(claims)), string(i))); true catch e; e isa Base.IOError && e.code == Base.UV_EEXIST || rethrow(); false end")
    println(io, "@testset $(repr(worker === nothing ? "selected" : "selected, worker $worker")) begin")
    for (i, e) in enumerate(entries)
        label, path, rel = string(e.label), e.path, relpath(e.path, t)
        tail = worker === nothing ? "" : ", '\\t', \"worker $worker\""
        worker === nothing ||
            println(io, "    if claim($i)\n    println($(repr("worker $worker: test/$rel"))); flush(stdout)")
        println(io, "    @testset $(repr(label)) begin")
        println(io, "        t = @elapsed Base.include(fresh(), $(repr(path)))")
        println(io, "        println(TIMES, $(repr(something(e.group, ""))), '\\t', $(repr(rel)), '\\t', t$tail)")
        println(io, "        flush(TIMES)")
        println(io, "    end")
        worker === nothing || println(io, "    end")
    end
    println(io, "end")
    return String(take!(io))
end

"""
The test files that `Pkg.test()` runs: those of the groups of an empty `ARGS`, `core` and `slow`,
and `metal` on Apple silicon, as D5 writes `GROUPS`.
"""
function suite(entries)
    groups = Sys.isapple() && Sys.ARCH === :aarch64 ? ("core", "slow", "metal") : ("core", "slow")
    filter(e -> e.group in groups, entries)
end

"The entries of `sel` in the order of `entries`, the order of `runtests.jl`."
in_order(sel, entries) = filter(in(sel), entries)

"""
Run `cmds` side by side, worker `k`'s output into `worker-<k>.log` in `work`; then write `log`,
each worker's output under a line that names it. True where every worker passed.
"""
function run_workers(cmds, log, work)
    logs = [joinpath(work, "worker-$k.log") for k in eachindex(cmds)]
    ios = [open(l, "w") for l in logs]
    ps = [run(pipeline(ignorestatus(c); stdout = io, stderr = io); wait = false)
          for (c, io) in zip(cmds, ios)]
    foreach(wait, ps)
    foreach(close, ios)
    open(log, "w") do io
        for (k, l) in enumerate(logs)
            println(io, "\n── worker $k, exit $(ps[k].exitcode) ──")
            write(io, read(l))
        end
    end
    return all(p -> p.exitcode == 0, ps)
end

"The `core` files of a times file whose time, cold, is above the budget."
function over_budget(times; budget = BUDGET)
    out = String[]
    isfile(times) || return out
    for l in readlines(times)
        group, rel, t = split(l, '\t')
        group == "core" && parse(Float64, t) > budget &&
            push!(out, "D6: test/$rel runs $(round(parse(Float64, t); digits = 1)) s cold, above the $(round(Int, budget)) s of a core file")
    end
    return out
end

noise(l) = occursin(r"EMFILE|FolderMonitor|Revise|^\s*\[\d+\]|^\s*@ |UNHANDLED TASK ERROR", l)

function summarise(log)
    lines = filter(!noise, readlines(log))
    out, i = String[], 1
    while i <= length(lines)
        l = lines[i]
        if startswith(l, "Test Summary:")
            j = i
            while j <= length(lines) && !isempty(strip(lines[j])) && !startswith(lines[j], "ERROR")
                j - i < 25 ? push!(out, lines[j]) : j - i == 25 && push!(out, "  ⋮ (the log has the rest)")
                j += 1
            end
            i = j
        elseif occursin(r"(Test Failed|Error During Test) at", l) && count(x -> occursin(r"(Test Failed|Error During Test) at", x), out) < 10
            append!(out, lines[i:min(i + 11, end)]); push!(out, "  ⋮")
            i += 12
        else
            occursin(r"^ERROR:|tests passed|errored during testing", l) && push!(out, l)
            i += 1
        end
    end
    return out
end

function main(args)
    isempty(args) && (println(stderr, "usage: run-tests.jl <package> [--jobs <n>] [affected [<base>] | select [<base>] | full | list | <unit> ...]"); return 2)
    pkg = abspath(expanduser(args[1]))
    rest = collect(args[2:end])
    jobs = 1
    k = findfirst(==("--jobs"), rest)
    if k !== nothing
        n = k < length(rest) ? tryparse(Int, rest[k + 1]) : nothing
        n isa Int && n >= 1 || (println(stderr, "`--jobs` needs a whole number of workers, 1 or more."); return 2)
        jobs = n
        deleteat!(rest, k:(k + 1))
    end
    mode = isempty(rest) ? "affected" : rest[1]
    name = basename(rstrip(pkg, '/'))
    budget = parse(Float64, get(ENV, "RUN_TESTS_BUDGET", string(BUDGET)))
    # `full` with workers runs the convention's file list, which only its layout has
    if mode != "full" || jobs > 1
        stop = refusal(pkg)
        if !isempty(stop)
            println(stderr, "$name: the tests are not in the layout of the test convention (the plan \"$PLAN\"), ",
                "and run-tests.jl reads no other. `test-layout.jl --check` reports:")
            foreach(l -> println(stderr, "  ", l), stop)
            println(stderr, "Only `run-tests.jl $(args[1]) full`, Pkg.test(), runs on this layout.")
            return 2
        end
    end
    entries = mode == "full" && jobs == 1 ? Entry[] : units(pkg)
    t = joinpath(pkg, "test")
    if mode == "list"
        for e in entries
            println(rpad(relpath(e.path, t), 50), rpad(something(e.group, "none"), 9), e.label)
        end
        return 0
    end
    sel, why = if mode == "full"
        :full, ["requested"]
    elseif mode in ("affected", "select")
        a = affected(pkg, entries, changed(pkg, length(rest) >= 2 ? rest[2] : "origin/main"))
        a === :full ? (:full, ["Project.toml changed"]) : a
    else
        none = filter(a -> isempty(named(entries, [a])), rest)
        if !isempty(none)
            println(stderr, "$name: no test file is the group, the path or the label of ",
                join(none, ", "), ". `run-tests.jl $(args[1]) list` shows them.")
            return 2
        end
        pick = named(entries, rest)
        pick, ["named"]
    end
    # workers run the files of Pkg.test() through TestEnv, as they run any selection
    sel === :full && jobs > 1 && (sel = suite(entries); why = [why; "the files of Pkg.test()"])
    # `affected` adds files in the order of the diff's paths; the workers take them in this order
    jobs > 1 && (sel = in_order(sel, entries))
    dir = expanduser("~/Research/.scratch/tests")
    mkpath(dir)
    stamp = Dates.format(now(), "yyyymmdd-HHMMSS")
    log = joinpath(dir, "$name-$stamp-$(mode in ("full", "affected", "select") ? mode : "named").log")
    times = joinpath(dir, "$name-$stamp-times.tsv")
    runs = mode != "select" && (sel === :full || !isempty(sel))
    foreign = runs ? foreign_manifests(pkg) : String[]
    root = pkg
    if !isempty(foreign)
        root = mktempdir(mkpath(joinpath(dir, "copies")); prefix = name * "-")
        run(copy_command(pkg, root, foreign))
        println("$name: ", join(foreign, " and "), " is resolved by another Julia than $VERSION, ",
            "so the run uses a copy without it")
        into = p -> joinpath(root, relpath(p, pkg))
        sel === :full || (sel = [Entry(into(e.path), e.kind, e.label, e.group, into(e.file), e.line)
                                 for e in sel])
    end
    if sel === :full
        cmd = `$(Base.julia_cmd()) --startup-file=no --project=$root -e "using Pkg; Pkg.test()"`
        println("$name: full suite, Pkg.test() — ", join(why, "; "))
    elseif isempty(sel)
        println("$name: no test file is reachable from the diff. Nothing ran.")
        return 0
    else
        if Base.identify_package("TestEnv") === nothing
            println(stderr, "TestEnv is not installed for Julia $VERSION, so no selection can run; `full` can. ",
                    "Install the harness environment with: harness install --apply")
            return 3
        end
        workers = min(jobs, length(sel))
        command(drv) = `$(Base.julia_cmd()) --startup-file=no $CHECKBOUNDS --project=$root $drv`
        if jobs == 1
            drv = joinpath(dir, "$name-$stamp-driver.jl")
            write(drv, driver(root, sel, times))
            cmd = command(drv)
        elseif mode != "select"
            # the run's own directory, so two runs started in one second share no worker's file
            work = mktempdir(dir; prefix = "$name-$stamp-workers-", cleanup = false)
            claims = mkpath(joinpath(work, "claims"))
            wtimes = [joinpath(work, "times-worker-$k.tsv") for k in 1:workers]
            cmds = map(1:workers) do k
                drv = joinpath(work, "driver-worker-$k.jl")
                write(drv, driver(root, sel, wtimes[k]; worker = k, claims))
                command(drv)
            end
        end
        groups = unique(something(e.group, "none") for e in sel)
        println("$name: $(length(sel)) of $(count(e -> something(e.group, "none") in groups, entries)) test files in ",
            join(groups, ", "), ", Julia $VERSION", jobs == 1 ? "" : ", in $workers workers")
        foreach(w -> println("  ", w), why)
    end
    mode == "select" && return 0
    println("load average ", join(round.(Sys.loadavg(); digits = 2), " "), " at the start")
    t0 = time()
    ok = if jobs == 1
        p = open(io -> run(pipeline(ignorestatus(cmd); stdout = io, stderr = io)), log, "w")
        p.exitcode == 0
    else
        passed = run_workers(cmds, log, work)
        # one times file, worker by worker
        write(times, join(read.(filter(isfile, wtimes), String)))
        rm(work; recursive = true)
        passed
    end
    root == pkg || rm(root; recursive = true, force = true)
    println("\n", ok ? "PASS" : "FAIL", " in ", round(Int, time() - t0), " s — log: ", log)
    foreach(println, summarise(log))
    # the cold time is D6's measure only in a run of the group `core`, in one process
    if mode ∉ ("affected", "select") && "core" in rest
        jobs == 1 ? foreach(println, over_budget(times; budget)) :
        println("No D6 verdict: with --jobs $jobs, a file's time in a worker is not its cold time in the order of runtests.jl.")
    end
    return ok ? 0 : 1
end

# Exit 0: the tests pass. 1: a test fails or errors. 2: bad arguments, a unit that names no test
# file, or a layout that is not the convention's. 3: this script failed, and nothing is known
# about the tests.
if abspath(PROGRAM_FILE) == @__FILE__
    exit(try
        main(ARGS)
    catch e
        showerror(stderr, e, catch_backtrace())
        3
    end)
end
