#!/usr/bin/env julia
#
# Checks for run-tests.jl, mutate.jl and test-census.jl. Companion to them; run after any change
# to one of them.
#
#   julia --startup-file=no run-tests-test.jl
#
# The selection is checked on a fixture in the form of the convention, with the changed paths
# given directly: a sandboxed process cannot create a `.git`, so no fixture has a history.

using Test

# the warm mode's test sets use short lists, which run cold by default; one test set unsets it
ENV["MUTATE_WARM_MIN"] = "0"

const SCRIPTS = @__DIR__
const RUNTESTS = joinpath(SCRIPTS, "run-tests.jl")
const MUTATE = joinpath(SCRIPTS, "mutate.jl")

module R
include(joinpath(@__DIR__, "run-tests.jl"))
end

module M
include(joinpath(@__DIR__, "mutate.jl"))
end

module C
include(joinpath(@__DIR__, "test-census.jl"))
end

const FIXTURE_RUNTESTS = """
using SafeTestsets

const GROUPS = isempty(ARGS) ? (Sys.isapple() && Sys.ARCH === :aarch64 ? ["core", "slow", "metal"] : ["core", "slow"]) : ARGS

if "core" in GROUPS
    @safetestset "Aqua" include("quality/aqua.jl")
    @safetestset "Options" include("base/options.jl")
    @safetestset "Base, together" include("base/common.jl")
    @safetestset "Newton" include("solvers/newton.jl")
    @safetestset "Whole package" include("integration/solve.jl")
end
if "slow" in GROUPS
    @safetestset "Convergence" include("verification/convergence.jl")
end
if "metal" in GROUPS
    @safetestset "Metal" include("devices/metal.jl")
end
"""

const PLAIN = "using Test, Fixture\n@test Fixture.f() == 1\n"

const FIXTURE = Dict(
    "Project.toml" => "name = \"Fixture\"\nuuid = \"01234567-89ab-cdef-0123-456789abcdef\"\n",
    "src/Fixture.jl" => "module Fixture\nf() = 1\ninclude(\"base/options.jl\")\ninclude(\"base/tools.jl\")\ninclude(\"solvers/newton.jl\")\nend\n",
    "src/base/options.jl" => "g() = 2\n",
    "src/base/tools.jl" => "h() = 3\n",
    "src/solvers/newton.jl" => "k() = 4\n",
    "ext/FixtureExt.jl" => "module FixtureExt end\n",
    "test/Project.toml" => "[deps]\nTest = \"8dfed614-e22c-5e08-85e1-65c5234f0b40\"\n",
    "test/runtests.jl" => FIXTURE_RUNTESTS,
    "test/quality/aqua.jl" => PLAIN,
    "test/base/options.jl" => "using Test, Fixture\ninclude(\"../helpers/utils.jl\")\n@test Fixture.g() == 2\n",
    "test/base/common.jl" => "using Test, Fixture\n@test Fixture.g() + Fixture.h() == 5\n",
    "test/solvers/newton.jl" => "using Test, Fixture\n@test Fixture.k() == 4\n",
    "test/integration/solve.jl" => PLAIN,
    "test/verification/convergence.jl" => PLAIN,
    "test/devices/metal.jl" => PLAIN,
    "test/helpers/utils.jl" => "include(\"data.jl\")\n",
    "test/helpers/data.jl" => "data() = 1\n"
)

"Write the fixture with `changes` applied (`nothing` deletes a file) and return its directory."
function fixture(changes = Dict{String, Union{String, Nothing}}())
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    for (path, text) in merge(Dict{String, Union{String, Nothing}}(FIXTURE), changes)
        text === nothing && continue
        mkpath(dirname(joinpath(dir, path)))
        write(joinpath(dir, path), text)
    end
    return dir
end

"Run a script on arguments; return (exit code, stdout and stderr)."
function script(file, args...)
    out = IOBuffer()
    code = run(pipeline(
        ignorestatus(`$(Base.julia_cmd()) --startup-file=no $file $args`);
        stdout = out, stderr = out)).exitcode
    return code, String(take!(out))
end

const DIR = fixture()

"The test files, relative to test/, that `affected` selects for the changed `paths`."
function selected(paths...)
    sel = R.affected(DIR, R.units(DIR), collect(paths))
    sel isa Symbol && return sel
    return sort([relpath(e.path, joinpath(DIR, "test")) for e in first(sel)])
end

@testset "affected selects by the mirror of D3" begin
    # the mirror, the tests of its directory that mirror no file, the whole package, quality
    @test selected("src/base/options.jl") ==
          ["base/common.jl", "base/options.jl", "integration/solve.jl", "quality/aqua.jl"]
    @test selected("src/solvers/newton.jl") ==
          ["integration/solve.jl", "quality/aqua.jl", "solvers/newton.jl"]
    # the top-level module file reaches the tests of no subdirectory
    @test selected("src/Fixture.jl") == ["integration/solve.jl", "quality/aqua.jl"]
    @test selected("ext/FixtureExt.jl") == ["integration/solve.jl", "quality/aqua.jl"]
    @test selected("test/solvers/newton.jl") == ["quality/aqua.jl", "solvers/newton.jl"]
    @test selected("README.md") == []
    # every test of the changed file's own directory, whatever its name
    @test selected("src/base/tools.jl") ==
          ["base/common.jl", "base/options.jl", "integration/solve.jl", "quality/aqua.jl"]
end

@testset "affected links a helper to its users by the resolved path" begin
    # `include("../helpers/utils.jl")`, and `data.jl` through `utils.jl`
    @test selected("test/helpers/utils.jl") == ["base/options.jl", "quality/aqua.jl"]
    @test selected("test/helpers/data.jl") == ["base/options.jl", "quality/aqua.jl"]
end

@testset "affected runs the group core" begin
    @test selected("test/verification/convergence.jl") == ["quality/aqua.jl"]
    @test selected("test/runtests.jl") == ["base/common.jl", "base/options.jl",
        "integration/solve.jl", "quality/aqua.jl", "solvers/newton.jl"]
    @test selected("Project.toml") === :full
    @test selected("test/Project.toml") === :full
end

@testset "a unit is a group, a path or a label" begin
    names(args...) = sort([relpath(e.path, joinpath(DIR, "test"))
                           for e in R.named(R.units(DIR), collect(args))])
    @test names("core") == ["base/common.jl", "base/options.jl", "integration/solve.jl",
        "quality/aqua.jl", "solvers/newton.jl"]
    @test names("slow") == ["verification/convergence.jl"]
    @test names("metal", "slow") == ["devices/metal.jl", "verification/convergence.jl"]
    @test names("base/options.jl") == ["base/options.jl"]
    @test names("Newton") == ["solvers/newton.jl"]
    @test names("runtests.jl") == []
end

# the fixture with test/quality/doctests.jl in its own group `doctests`
const DOCTESTS_DIR = fixture(Dict{String, Union{String, Nothing}}(
    "test/runtests.jl" => replace(FIXTURE_RUNTESTS,
        "if \"metal\" in GROUPS" => "if \"doctests\" in GROUPS\n    @safetestset \"Doctests\" include(\"quality/doctests.jl\")\nend\nif \"metal\" in GROUPS"),
    "test/quality/doctests.jl" => PLAIN))

@testset "the unit doctests runs the file of the group doctests" begin
    @test [relpath(e.path, joinpath(DOCTESTS_DIR, "test"))
           for e in R.named(R.units(DOCTESTS_DIR), ["doctests"])] == ["quality/doctests.jl"]
    code, out = script(RUNTESTS, DOCTESTS_DIR, "doctests")
    @test code == 0
    @test occursin("1 of 1 test files in doctests", out)
    @test occursin("PASS", out)
end

@testset "affected never selects the group doctests" begin
    for p in ("src/Fixture.jl", "src/base/options.jl", "ext/FixtureExt.jl",
        "test/quality/doctests.jl", "test/quality/aqua.jl", "test/runtests.jl")
        sel = R.affected(DOCTESTS_DIR, R.units(DOCTESTS_DIR), [p])
        @test !isempty(first(sel))
        @test all(e -> e.group == "core", first(sel))
    end
    # the change of the doctests file alone selects the quality files of `core`
    sel = R.affected(DOCTESTS_DIR, R.units(DOCTESTS_DIR), ["test/quality/doctests.jl"])
    @test [relpath(e.path, joinpath(DOCTESTS_DIR, "test")) for e in first(sel)] ==
          ["quality/aqua.jl"]
end

@testset "a unit that names no test file stops the run" begin
    code, out = script(RUNTESTS, DIR, "runtests.jl")
    @test code == 2
    @test occursin("runtests.jl", out)
    @test !occursin("Nothing ran", out)
    # one unit that names nothing stops the run, beside one that names a file
    code, out = script(RUNTESTS, DIR, "base/options.jl", "cor")
    @test code == 2
    @test occursin("cor", out)
    @test !occursin("PASS", out)
end

@testset "mutate.jl refuses a mode of run-tests.jl as a unit" begin
    for unit in ("list", "select", "affected")
        code, out = script(MUTATE, DIR, "src/base/options.jl", "g() = 2", "g() = 3", unit)
        @test code == 2
        @test !occursin("SURVIVED", out)
    end
    # a later unit is a label, never a mode
    @test !occursin("mode of run-tests.jl",
        last(script(MUTATE, DIR, "src/base/options.jl", "g() = 2", "g() = 3", "Options",
            "list")))
end

@testset "a budget that does not parse is a failure of the script" begin
    out = IOBuffer()
    cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $DIR list`,
        "RUN_TESTS_BUDGET" => "abc")
    @test run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode == 3
end

@testset "list shows each file with its group" begin
    code, out = script(RUNTESTS, DIR, "list")
    @test code == 0
    @test occursin(r"verification/convergence.jl\s+slow\s+Convergence", out)
    @test occursin(r"base/options.jl\s+core\s+Options", out)
    code, out = script(RUNTESTS, DOCTESTS_DIR, "list")
    @test code == 0
    @test occursin(r"quality/doctests.jl\s+doctests\s+Doctests", out)
end

@testset "an old layout is refused, with the layout and the plan named" begin
    old = fixture(Dict{String, Union{String, Nothing}}(
        "test/runtests.jl" => "using Test\n@testset \"all\" begin\n    include(\"base/options.jl\")\nend\n"))
    for mode in ("list", "affected", "core", "base/options.jl")
        code, out = script(RUNTESTS, old, mode)
        @test code == 2
        @test occursin("Unify the test suites", out)
        @test occursin("[D2]", out)
    end
    # a D8 violation alone is no old layout
    extra = fixture(Dict{String, Union{String, Nothing}}("test/base/extra.jl" => PLAIN))
    @test first(script(RUNTESTS, extra, "list")) == 0
end

@testset "the parser for the other layouts is gone" begin
    src = read(RUNTESTS, String)
    @test !occursin("units!", src)
    @test !occursin("label_of", src)
    @test occursin("test-layout.jl", src)
end

@testset "a core run reports each file whose first, cold time is above the 60 s of D6" begin
    times = joinpath(mktempdir(), "times.tsv")
    write(times,
        "core\tbase/a.jl\t61.5\ncore\tbase/b.jl\t12.0\ncore\tbase/c.jl\t60.0\n" *
        "slow\tverification/d.jl\t300.0\n")
    report = R.over_budget(times)
    @test report == ["D6: test/base/a.jl runs 61.5 s cold, above the 60 s of a core file"]
end

@testset "a core run passes, and times each file" begin
    code, out = script(RUNTESTS, DIR, "core")
    @test code == 0
    @test occursin("PASS", out)
    @test occursin("5 of 5 test files in core", out)
    bad = fixture(Dict{String, Union{String, Nothing}}(
        "test/solvers/newton.jl" => "using Test, Fixture\n@test Fixture.k() == 5\n"))
    code, out = script(RUNTESTS, bad, "core")
    @test code == 1
    @test occursin("FAIL", out)
end

@testset "a core run reports a core file above the budget, end to end, and runs it once" begin
    # each run of base/common.jl adds a line to runs.txt
    counted = fixture(Dict{String, Union{String, Nothing}}(
        "test/base/common.jl" => "using Test, Fixture\n" *
                                 "open(io -> println(io, \"run\"), joinpath(dirname(dirname(@__DIR__)), \"runs.txt\"), \"a\")\n" *
                                 "@test Fixture.g() + Fixture.h() == 5\n"))
    out = IOBuffer()
    cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $counted core slow`,
        "RUN_TESTS_BUDGET" => "0")
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    s = String(take!(out))
    # the report is advice: the exit status is the tests'
    @test code == 0
    @test occursin(r"D6: test/base/options.jl runs [\d.]+ s cold, above the 0 s of a core file", s)
    @test occursin(r"D6: test/base/common.jl runs [\d.]+ s cold", s)
    @test !occursin("D6: test/verification/convergence.jl", s)
    @test readlines(joinpath(counted, "runs.txt")) == ["run"]
    @test !occursin("timed again", s)
    @test !occursin("after compilation", s)
    @test occursin(r"load average [\d.]+", s)
    # the load average comes at the start, before the verdict
    @test findfirst("load average", s).start < findfirst(r"\n(PASS|FAIL) in", s).start
    # the default budget reports nothing on this fixture
    code, s = script(RUNTESTS, DIR, "core")
    @test !occursin("D6:", s)
end

@testset "only a run of the group core reports D6" begin
    # a file that runs first in a named run pays the load and the compilation: no D6 time
    for units in (["base/common.jl"], ["Base, together"], ["Options", "Newton"])
        out = IOBuffer()
        cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $DIR $units`,
            "RUN_TESTS_BUDGET" => "0")
        code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
        s = String(take!(out))
        @test code == 0
        @test occursin("PASS", s)
        @test !occursin("D6:", s)
    end
end

"The log and the times file that a run of run-tests.jl names in its output."
function run_files(out)
    log = match(r"log: (\S+)", out).captures[1]
    return log, replace(log, r"-[a-z]+\.log$" => "-times.tsv")
end

# every core file defines K, and fails where its module has a K: one of another file
const KS = Dict{String, Union{String, Nothing}}(
    "test/quality/aqua.jl" => "using Test, Fixture\n@test !isdefined(@__MODULE__, :K)\nconst K = 1\n@test Fixture.f() == K\n",
    "test/base/options.jl" => "using Test, Fixture\n@test !isdefined(@__MODULE__, :K)\nconst K = 2.0\n@test Fixture.g() == K\n",
    "test/base/common.jl" => "using Test, Fixture\n@test !isdefined(@__MODULE__, :K)\nconst K = \"5\"\n@test string(Fixture.g() + Fixture.h()) == K\n",
    "test/solvers/newton.jl" => "using Test, Fixture\n@test !isdefined(@__MODULE__, :K)\nconst K = [4]\n@test [Fixture.k()] == K\n",
    "test/integration/solve.jl" => "using Test, Fixture\n@test !isdefined(@__MODULE__, :K)\nconst K = :one\n@test Fixture.f() == 1\n")

@testset "--jobs runs the selected files in workers, each once, in its own module" begin
    dir = fixture(KS)
    code, out = script(RUNTESTS, dir, "--jobs", "2", "core")
    @test code == 0
    @test occursin("PASS", out)
    @test occursin("5 of 5 test files in core, Julia $VERSION, in 2 workers", out)
    log, times = run_files(out)
    rows = split.(readlines(times), '\t')
    # each core file once, with its worker
    @test sort([r[2] for r in rows]) == ["base/common.jl", "base/options.jl",
        "integration/solve.jl", "quality/aqua.jl", "solvers/newton.jl"]
    @test all(r -> length(r) == 4 && r[4] in ("worker 1", "worker 2"), rows)
    @test all(r -> parse(Float64, r[3]) > 0, rows)
    text = read(log, String)
    for r in rows
        @test occursin("$(r[4]): test/$(r[2])", text)
    end
    # each file under a testset of its label, in a fresh module
    drv = R.driver(dir, R.units(dir), "times.tsv"; worker = 1, claims = "claims")
    for (label, rel) in (("Newton", "solvers/newton.jl"), ("Base, together", "base/common.jl"))
        @test occursin("@testset $(repr(label)) begin\n        t = @elapsed Base.include(fresh(), " *
                       repr(joinpath(dir, "test", rel)), drv)
    end
    # the workers' own logs, times files and claims are gone
    stem = basename(times)[1:(end - length("-times.tsv"))]
    @test isempty(filter(readdir(dirname(log))) do f
        startswith(f, stem) &&
            (endswith(f, "-claims") || occursin("worker", f) && !occursin("driver", f))
    end)
    # a named selection and a selection of more workers than files
    code, out = script(RUNTESTS, dir, "--jobs", "8", "Options", "solvers/newton.jl")
    @test code == 0
    @test occursin("2 of 5 test files in core, Julia $VERSION, in 2 workers", out)
    @test length(readlines(last(run_files(out)))) == 2
    # --jobs after the units reads the same
    code, out = script(RUNTESTS, dir, "core", "--jobs", "3")
    @test code == 0
    @test occursin("in 3 workers", out)
end

@testset "--jobs gives the verdict and the exit status of one process" begin
    for (units, n) in ((["core"], "2"), (["Options", "Newton", "Aqua"], "3"))
        bad = fixture(merge(KS, Dict{String, Union{String, Nothing}}(
            "test/solvers/newton.jl" => "using Test, Fixture\n@test Fixture.k() == 5\n")))
        one, out1 = script(RUNTESTS, bad, units...)
        code, out = script(RUNTESTS, bad, "--jobs", n, units...)
        @test one == code == 1
        @test occursin("\nFAIL in", out)
        # the failure is reported under the file's label
        @test occursin("Newton: Test Failed", out)
        # every selected file ran, the failing one included
        @test length(readlines(last(run_files(out)))) ==
              parse(Int, match(r"(\d+) of \d+ test files", out).captures[1])
    end
    # an error outside a @test fails the run too
    err = fixture(Dict{String, Union{String, Nothing}}(
        "test/base/common.jl" => "using Test, Fixture\nerror(\"boom\")\n"))
    @test first(script(RUNTESTS, err, "--jobs", "2", "core")) == 1
end

@testset "--jobs gives the workers the files in the order of runtests.jl" begin
    ents = R.units(DIR)
    sel = first(R.affected(DIR, ents, ["src/solvers/newton.jl", "src/base/options.jl"]))
    rel(e) = relpath(e.path, joinpath(DIR, "test"))
    order = [rel(e) for e in ents if e in sel]
    # affected adds the files in the order of the diff's paths
    @test [rel(e) for e in sel] != order
    @test [rel(e) for e in R.in_order(sel, ents)] == order
    drv = R.driver(DIR, R.in_order(sel, ents), "t.tsv"; worker = 1, claims = "c")
    @test [m.captures[1] for m in eachmatch(r"worker 1: test/(\S+?)\"", drv)] == order
    # main puts every selection in that order before it writes the workers' drivers
    @test occursin("jobs > 1 && (sel = in_order(sel, entries))", read(RUNTESTS, String))
end

@testset "--jobs counts a failing worker, whichever worker it is" begin
    # each file fails in one worker only; the slow first file keeps worker 1 busy, so worker 2,
    # which resolves its environment after worker 1, runs the other files
    for (bad, other) in (("worker 2", "worker 1"), ("worker 1", "worker 2"))
        body = "using Test\n@test !occursin($(repr(replace(bad, " " => "-"))), Main.TIMES.name)\n"
        dir = fixture(Dict{String, Union{String, Nothing}}(
            "test/quality/aqua.jl" => "sleep(10)\n" * body, "test/base/options.jl" => body,
            "test/base/common.jl" => body, "test/solvers/newton.jl" => body,
            "test/integration/solve.jl" => body))
        code, out = script(RUNTESTS, dir, "--jobs", "2", "core")
        workers = [split(l, '\t')[4] for l in readlines(last(run_files(out)))]
        # both workers ran a file, so the run has a passing and a failing worker
        @test bad in workers && other in workers
        @test code == 1
        @test occursin("\nFAIL in", out)
    end
end

@testset "a claim that fails for another reason than a taken file stops the worker" begin
    work = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    claims = mkpath(joinpath(work, "claims"))
    drv = joinpath(work, "driver.jl")
    write(drv, R.driver(DIR, R.units(DIR)[1:1], joinpath(work, "t.tsv"); worker = 1, claims))
    chmod(claims, 0o555)
    out = IOBuffer()
    code = run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no --project=$DIR $drv`);
        stdout = out, stderr = out)).exitcode
    chmod(claims, 0o755)
    @test code != 0
    @test occursin("permission denied", lowercase(String(take!(out))))
end

@testset "two --jobs runs of packages of one name, started together, keep their workers apart" begin
    slow = fixture(Dict{String, Union{String, Nothing}}(
        "test/quality/aqua.jl" => "using Test\nsleep(8)\n@test true\n"))
    twin = joinpath(mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test"))), basename(slow))
    cp(slow, twin)
    outs = [IOBuffer(), IOBuffer()]
    ps = [run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $d --jobs 2 core`);
              stdout = o, stderr = o); wait = false) for (d, o) in zip((slow, twin), outs)]
    foreach(wait, ps)
    for (p, o) in zip(ps, outs)
        s = String(take!(o))
        @test p.exitcode == 0
        @test occursin("\nPASS in", s)
    end
end

@testset "--jobs refuses a count that is not a whole number of 1 or more" begin
    for bad in (["--jobs", "0"], ["--jobs", "-1"], ["--jobs", "abc"], ["--jobs", "1.5"], ["core", "--jobs"])
        code, out = script(RUNTESTS, DIR, bad..., "core")
        @test code == 2
        @test occursin("`--jobs` needs a whole number of workers, 1 or more", out)
        @test !occursin("PASS", out) && !occursin("FAIL", out)
    end
end

@testset "--jobs 1 runs as a run without --jobs" begin
    out = IOBuffer()
    cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $DIR --jobs 1 core`,
        "RUN_TESTS_BUDGET" => "0")
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    s = String(take!(out))
    @test code == 0
    @test occursin("5 of 5 test files in core, Julia $VERSION\n", s)
    @test !occursin("worker", s)
    @test occursin(r"D6: test/base/options.jl runs [\d.]+ s cold", s)
    @test all(l -> length(split(l, '\t')) == 3, readlines(last(run_files(s))))
    @test !occursin("worker", read(first(run_files(s)), String))
end

@testset "a core run with --jobs prints no D6 verdict, and says why in one line" begin
    why = "No D6 verdict: with --jobs 2, a file's time in a worker is not its cold time in the order of runtests.jl."
    out = IOBuffer()
    cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $DIR --jobs 2 core slow`,
        "RUN_TESTS_BUDGET" => "0")
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    s = String(take!(out))
    @test code == 0
    @test !occursin("D6:", s)
    @test count(why, s) == 1
    # a named run with --jobs reads no D6 either, and has nothing to explain
    out = IOBuffer()
    cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $RUNTESTS $DIR --jobs 2 Options Newton`,
        "RUN_TESTS_BUDGET" => "0")
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    s = String(take!(out))
    @test code == 0
    @test !occursin("D6", s)
end

@testset "full with --jobs runs the files of Pkg.test() in workers" begin
    code, out = script(RUNTESTS, DIR, "--jobs", "2", "full")
    @test code == 0
    @test occursin("PASS", out)
    @test !occursin("full suite, Pkg.test()", out)
    @test occursin("in 2 workers", out)
    # empty ARGS: core and slow, and metal on Apple silicon
    apple = Sys.isapple() && Sys.ARCH === :aarch64
    @test occursin(apple ? "7 of 7 test files in core, slow, metal" : "6 of 6 test files in core, slow", out)
    rels = sort([split(l, '\t')[2] for l in readlines(last(run_files(out)))])
    @test ("devices/metal.jl" in rels) == apple
    @test "verification/convergence.jl" in rels
    # a doctests group is not in Pkg.test()'s list
    code, out = script(RUNTESTS, DOCTESTS_DIR, "--jobs", "2", "full")
    @test code == 0
    @test !occursin("doctests", out)
    # a layout outside the convention has no file list: full with --jobs is refused there
    old = fixture(Dict{String, Union{String, Nothing}}(
        "test/runtests.jl" => "using Test\n@testset \"all\" begin\n    include(\"base/options.jl\")\nend\n"))
    code, out = script(RUNTESTS, old, "--jobs", "2", "full")
    @test code == 2
    @test occursin("[D2]", out)
end

@testset "mutate.jl reports UNKNOWN when run-tests.jl ran nothing" begin
    code, out = script(MUTATE, fixture(), "src/base/options.jl", "g() = 2", "g() = 3",
        "runtests.jl")
    @test occursin("UNKNOWN", out)
    @test !occursin("SURVIVED", out)
end

# The sandbox refuses a new `.claude` directory, so no fixture can hold one; the command is checked.
@testset "mutate.jl copies no .claude directory" begin
    cmd = M.copy_command("/a/pkg", "/b/copy")
    @test "--exclude=.claude" in cmd.exec
    @test "--exclude=.git" in cmd.exec
    dst = mktempdir()
    run(M.copy_command(DIR, dst))
    @test isfile(joinpath(dst, "src", "Fixture.jl"))
end

@testset "a manifest of another Julia is foreign" begin
    own = "julia_version = \"$VERSION\"\nmanifest_format = \"2.0\"\n"
    other = "julia_version = \"1.0.5\"\nmanifest_format = \"2.0\"\n"
    @test R.foreign_manifests(fixture()) == []
    @test R.foreign_manifests(fixture(Dict{String, Union{String, Nothing}}(
        "Manifest.toml" => own))) == []
    @test R.foreign_manifests(fixture(Dict{String, Union{String, Nothing}}(
        "Manifest.toml" => other, "test/Manifest.toml" => other))) ==
          ["Manifest.toml", "test/Manifest.toml"]
    # a manifest that names no Julia is foreign too
    @test R.foreign_manifests(fixture(Dict{String, Union{String, Nothing}}(
        "Manifest.toml" => "manifest_format = \"2.0\"\n"))) == ["Manifest.toml"]
    dst = mktempdir()
    run(M.copy_command(fixture(Dict{String, Union{String, Nothing}}("Manifest.toml" => other)),
        dst, ["Manifest.toml"]))
    @test isfile(joinpath(dst, "src", "Fixture.jl"))
    @test !isfile(joinpath(dst, "Manifest.toml"))
end

@testset "a run beside a foreign manifest goes to a copy, and leaves the manifest" begin
    other = "julia_version = \"1.0.5\"\nmanifest_format = \"2.0\"\n"
    dir = fixture(Dict{String, Union{String, Nothing}}("Manifest.toml" => other))
    code, out = script(RUNTESTS, dir, "core")
    @test code == 0
    @test occursin("uses a copy without it", out)
    @test occursin("PASS", out)
    @test read(joinpath(dir, "Manifest.toml"), String) == other
    # a failing test in the package fails the copy's run
    bad = fixture(Dict{String, Union{String, Nothing}}("Manifest.toml" => other,
        "test/solvers/newton.jl" => "using Test, Fixture\n@test Fixture.k() == 5\n"))
    @test first(script(RUNTESTS, bad, "core")) == 1
end

@testset "mutate.jl runs a list of mutants, each with one or more edits" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "g is wrong"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 3"

    [[mutant]]
    name = "h is not tested by the unit"
    file = "src/base/tools.jl"
    from = "h() = 3"
    to = "h() = 4"

    [[mutant]]
    name = "two files, one of several lines"
    [[mutant.edit]]
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 2 # unchanged"
    [[mutant.edit]]
    file = "src/Fixture.jl"
    from = \"\"\"
    module Fixture
    f() = 1\"\"\"
    to = \"\"\"
    module Fixture
    f() = 2\"\"\"

    [[mutant]]
    name = "a text that is not there"
    file = "src/base/options.jl"
    from = "φ() = 7"
    to = "φ() = 8"
    """)
    code, out = script(MUTATE, fixture(), "--list", list, "base/options.jl", "quality/aqua.jl")
    @test code == 3
    @test occursin("CAUGHT: g is wrong", out)
    @test occursin("SURVIVED: h is not tested by the unit", out)
    @test occursin("CAUGHT: two files, one of several lines", out)
    @test occursin("INVALID: a text that is not there — `φ() = 7` occurs 0 times", out)
    @test occursin("2 CAUGHT, 1 SURVIVED, 0 UNKNOWN, 1 INVALID, of 4 mutants", out)
    # without the mutant that cannot apply, every verdict is known
    write(list, replace(read(list, String), r"\[\[mutant\]\]\nname = \"a text.*"s => ""))
    @test first(script(MUTATE, fixture(), "--list", list, "base/options.jl")) == 0
    # an edit without `to` is a bad list
    write(list, "[[mutant]]\nfile = \"src/base/options.jl\"\nfrom = \"g() = 2\"\n")
    code, out = script(MUTATE, fixture(), "--list", list, "base/options.jl")
    @test code == 2
    @test occursin("file, from and to", out)
    # so is a file that is no TOML
    write(list, "[[mutant]]\nfrom = \"a\nb\"\n")
    code, out = script(MUTATE, fixture(), "--list", list, "base/options.jl")
    @test code == 2
    @test occursin("is no valid TOML", out)
end

const BROKEN = """
[[mutant]]
name = "does not parse"
file = "src/base/options.jl"
from = "g() = 2"
to = "g() = (2"

[[mutant]]
name = "an undefined name"
file = "src/base/options.jl"
from = "g() = 2"
to = "g() = two"

[[mutant]]
name = "a valid mutant"
file = "src/base/options.jl"
from = "g() = 2"
to = "g() = 3"
"""

@testset "mutate.jl calls a mutant INVALID that does not parse or adds an undefined name" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, BROKEN)
    code, out = script(MUTATE, fixture(), "--list", list, "base/options.jl")
    @test code == 3
    @test occursin("INVALID: does not parse — the mutated src/base/options.jl does not parse", out)
    @test occursin("INVALID: an undefined name — the mutated src/base/options.jl adds the undefined name `two`", out)
    @test occursin("CAUGHT: a valid mutant", out)
    @test occursin("1 CAUGHT, 0 SURVIVED, 0 UNKNOWN, 2 INVALID, of 3 mutants", out)
    # an INVALID mutant never runs, so its line names no log
    @test !occursin(r"INVALID: does not parse[^\n]*log:", out)
    # the name that other files define is no finding: only the mutant's own name is reported
    @test !occursin("undefined name `g`", out)
    # a name that another file of the package defines is no undefined name
    write(list, "[[mutant]]\nname = \"calls h of tools.jl\"\nfile = \"src/base/options.jl\"\n" *
                "from = \"g() = 2\"\nto = \"g() = h()\"\n")
    @test occursin("VALID: calls h of tools.jl", last(script(MUTATE, fixture(), "--check", list)))
end

@testset "mutate.jl --check checks a list and runs nothing" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, BROKEN)
    code, out = script(MUTATE, fixture(), "--check", list)
    @test code == 3
    @test occursin("INVALID: does not parse", out)
    @test occursin("INVALID: an undefined name", out)
    @test occursin("VALID: a valid mutant", out)
    @test occursin("1 VALID, 2 INVALID, of 3 mutants", out)
    @test !occursin("CAUGHT", out) && !occursin("log:", out)
    write(list, "[[mutant]]\nname = \"a valid mutant\"\nfile = \"src/base/options.jl\"\n" *
                "from = \"g() = 2\"\nto = \"g() = 3\"\n")
    code, out = script(MUTATE, fixture(), "--check", list)
    @test code == 0
    @test occursin("1 VALID, 0 INVALID, of 1 mutants", out)
end

@testset "an edit with `at` replaces `from` at that byte, where `from` occurs more than once" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    pkg = fixture(Dict{String, Union{String, Nothing}}(
        "src/base/options.jl" => "g() = 2\nq() = 2\n"))
    at = ncodeunits("g() = 2\nq() = ") + 1
    write(list, "[[mutant]]\nname = \"q is wrong\"\nfile = \"src/base/options.jl\"\n" *
                "from = \"2\"\nto = \"3\"\nat = $at\n\n" *
                "[[mutant]]\nname = \"at points elsewhere\"\nfile = \"src/base/options.jl\"\n" *
                "from = \"2\"\nto = \"3\"\nat = 1\n")
    code, out = script(MUTATE, pkg, "--check", list)
    @test occursin("VALID: q is wrong", out)
    @test occursin("INVALID: at points elsewhere — `2` is not at byte 1 of src/base/options.jl", out)
    @test M.mutated_at("g() = 2\nq() = 2\n", "2", "3", at) == "g() = 2\nq() = 3\n"
    # without `at`, the same `from` occurs twice and is INVALID
    write(list, "[[mutant]]\nname = \"ambiguous\"\nfile = \"src/base/options.jl\"\n" *
                "from = \"2\"\nto = \"3\"\n")
    @test occursin("occurs 2 times", last(script(MUTATE, pkg, "--check", list)))
end

@testset "the warm mode gives the cold verdicts, in one process" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "g is wrong"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 3"

    [[mutant]]
    name = "h is not tested by the unit"
    file = "src/base/tools.jl"
    from = "h() = 3"
    to = "h() = 4"

    [[mutant]]
    name = "g is wrong again"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 5"

    [[mutant]]
    name = "f of the module file"
    file = "src/Fixture.jl"
    from = "f() = 1"
    to = "f() = 2"

    [[mutant]]
    name = "g is gone"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = ""
    """)
    pkg = fixture()
    code, out = script(MUTATE, pkg, "--warm", list, "base/options.jl", "quality/aqua.jl")
    @test code == 0
    @test occursin("CAUGHT: g is wrong —", out)
    @test occursin("CAUGHT: g is wrong again —", out)
    # a survivor is run again cold, and the cold verdict is reported
    @test occursin("SURVIVED: h is not tested by the unit — ", out)
    @test occursin("cold again", out)
    # a file that defines a module cannot be included into it: that mutant runs cold, with every
    # unit, and the fixture's quality/aqua.jl tests f
    @test occursin(r"CAUGHT: f of the module file — [^\n]*runs cold: src/Fixture.jl defines a module", out)
    # an include cannot remove a definition, so a mutant that deletes one runs cold
    @test occursin(r"CAUGHT: g is gone — [^\n]*runs cold: it deletes a top-level statement", out)
    @test occursin("4 CAUGHT, 1 SURVIVED, 0 UNKNOWN, 0 INVALID, of 5 mutants", out)
    # the smoke mutant ran first, and the units reach a changed function
    @test occursin("smoke: CAUGHT — `error(\"mutate.jl smoke\")` at the start of 3 functions", out)
    # the quality files do not run in the warm process
    @test occursin("leaves out quality/aqua.jl", out)
    # the totals line says where the worker's time went
    @test occursin(r"warm: 3 mutants in \d+ s, one worker \(apply \d+ s, test \d+ s, restore \d+ s, baseline \d+ s, peak [\d.]+ GiB per worker\)", out)
    # the warm verdicts of the two options mutants equal the cold ones
    _, cold = script(MUTATE, pkg, "--list", list, "base/options.jl")
    for name in ("g is wrong", "g is wrong again", "h is not tested by the unit")
        @test match(Regex("(\\w+): $name —"), out)[1] == match(Regex("(\\w+): $name —"), cold)[1]
    end
    # two workers give the same verdicts; without the result, every mutant runs again
    rm(M.result_path(list))
    code2, out2 = script(MUTATE, pkg, "--warm", list, "--jobs", "2", "base/options.jl", "quality/aqua.jl")
    @test code2 == 0
    @test occursin("warm: 3 mutants in", out2) && occursin("2 workers", out2)
    for name in ("g is wrong", "g is wrong again", "h is not tested by the unit", "f of the module file", "g is gone")
        @test match(Regex("(\\w+): $name —"), out2)[1] == match(Regex("(\\w+): $name —"), out)[1]
    end
    @test script(MUTATE, pkg, "--warm", list, "--jobs", "0", "base/options.jl")[1] == 2
    @test script(MUTATE, pkg, "--list", list, "--jobs", "2", "base/options.jl")[1] == 2
    # the package is as it was
    @test read(joinpath(pkg, "src/base/options.jl"), String) == "g() = 2\n"
end

@testset "the warm mode stops a mutant at the time limit, and goes on" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "g never returns"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = (while true end; 2)"

    [[mutant]]
    name = "g is wrong"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 3"
    """)
    out = IOBuffer()
    cmd = addenv(`$(Base.julia_cmd()) --startup-file=no $MUTATE $(fixture()) --warm $list base/options.jl`,
        "MUTATE_TIME_LIMIT" => "20")
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    s = String(take!(out))
    @test code == 3
    @test occursin(r"UNKNOWN: g never returns — [^\n]* — the time limit of 20 s", s)
    @test occursin("CAUGHT: g is wrong", s)
end

@testset "a failing final baseline makes every verdict since the last good one UNKNOWN" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    # the first mutant redefines h of tools.jl, which the restore of options.jl does not undo,
    # so the second mutant reads as caught in a wrong process
    write(list, """
    [[mutant]]
    name = "h changed from another file"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 2\\nh() = 4"

    [[mutant]]
    name = "g the same"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 1 + 1"
    """)
    code, out = script(MUTATE, fixture(), "--warm", list, "base/common.jl")
    @test code == 3
    # the detail holds the mutant's `to`, which spans two lines
    @test occursin(r"UNKNOWN: h changed from another file — .*?fails after the last mutant was restored"s, out)
    @test occursin(r"UNKNOWN: g the same — [^\n]*fails after the last mutant was restored", out)
    @test occursin("0 CAUGHT, 0 SURVIVED, 2 UNKNOWN", out)
end

@testset "a warm kill that a cold run does not repeat stops the warm kills from counting" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "g a float"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 2.0"

    [[mutant]]
    name = "g is wrong"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 3"
    """)
    # the unit fails on `g() = 2.0` only in the warm worker, whose Main holds JOB: a seeded
    # false kill, which the baseline (g() === 2) does not see
    pkg = fixture(Dict("test/base/options.jl" =>
        "using Test, Fixture\n@test Fixture.g() == 2\n@test !(isdefined(Main, :JOB) && Fixture.g() === 2.0)\n"))
    code, out = script(MUTATE, pkg, "--warm", list, "base/options.jl")
    @test code == 3
    @test occursin(r"SURVIVED: g a float — [^\n]*CAUGHT warm, [^\n]*cold again: SURVIVED", out)
    @test occursin(r"CAUGHT: g is wrong — [^\n]*CAUGHT warm, [^\n]*cold again: CAUGHT", out)
    @test occursin("The warm kills are not trusted: not caught cold: g a float", out)
    @test occursin("0 survivors and 2 kills run again cold", out)
end

@testset "the warm mode runs only the units that reach a mutant, and none for an unreached line" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "the branch that no test takes"
    file = "src/base/options.jl"
    from = "return 3"
    to = "return 4"

    [[mutant]]
    name = "the condition"
    file = "src/base/options.jl"
    from = "x > 0"
    to = "x < 0"

    [[mutant]]
    name = "h, which only common.jl calls"
    file = "src/base/tools.jl"
    from = "h(x = 3) = x"
    to = "h(x = 3) = x + 1"
    """)
    # line 5 of g runs in no unit; h runs only in common.jl. Each method takes an argument: a
    # method without one, such as `h() = 3`, is folded to its value and leaves no coverage line
    pkg = fixture(Dict("src/base/options.jl" => "function g(x = 1)\n    if x > 0\n        return 2\n    end\n    return 3\nend\n",
        "src/base/tools.jl" => "h(x = 3) = x\n"))
    code, out = script(MUTATE, pkg, "--warm", list, "base/options.jl", "base/common.jl")
    @test code == 0
    @test occursin(r"NO-COVERAGE: the branch that no test takes — [^\n]*no unit runs line 5", out)
    @test occursin(r"CAUGHT: the condition — [^\n]*warm, [\d.]+ s, 2 of 2 units", out)
    @test occursin(r"CAUGHT: h, which only common.jl calls — [^\n]*warm, [\d.]+ s, 1 of 2 units", out)
    @test occursin("2 CAUGHT, 0 SURVIVED, 1 NO-COVERAGE, 0 UNKNOWN, 0 INVALID, of 3 mutants", out)
    @test occursin(r"coverage: 2 units in \d+ s; 1 mutants NO-COVERAGE, 2 of 2 run only the units that reach them", out)
end

@testset "a short list runs cold in the warm mode, after the smoke mutant" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "g is wrong"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 3"

    [[mutant]]
    name = "h is not tested by the unit"
    file = "src/base/tools.jl"
    from = "h() = 3"
    to = "h() = 4"
    """)
    code, out = withenv(() -> script(MUTATE, fixture(), "--warm", list, "base/options.jl"), "MUTATE_WARM_MIN" => nothing)
    @test code == 0
    @test occursin("smoke: CAUGHT", out)
    @test occursin(r"CAUGHT: g is wrong — [^\n]*runs cold: 2 warm mutants, 20 or fewer", out)
    @test occursin(r"SURVIVED: h is not tested by the unit — [^\n]*runs cold: 2 warm mutants", out)
    @test occursin("warm: 0 mutants", out) && !occursin("coverage:", out)
end

@testset "a mutant that changes a type definition runs cold" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "P loses a field"
    file = "src/base/options.jl"
    from = "b::Int"
    to = ""

    [[mutant]]
    name = "g the same"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 1 + 1"
    """)
    # h's signature names P of options.jl: a warm include of a changed P would make a new type,
    # and h would not apply to it after the restore
    pkg = fixture(Dict{String, Union{String, Nothing}}(
        "src/base/options.jl" => "struct P\n    a::Int\n    b::Int\nend\ng() = 2\n",
        "src/base/tools.jl" => "h(p::P = P(3, 0)) = p.a\n"))
    code, out = script(MUTATE, pkg, "--warm", list, "base/common.jl")
    @test code == 0
    @test occursin(r"CAUGHT: P loses a field — [^\n]*runs cold: it changes a type definition", out)
    @test occursin(r"SURVIVED: g the same — [^\n]*warm, ", out)
    @test M.type_definitions("struct P\n    a::Int\nend\n@enum C x y\nabstract type A end\nf() = 1\n") ==
          ["struct P\n    a::Int\nend", "@enum C x y", "abstract type A end"]
end

@testset "a second run on an unchanged tree runs no mutant, and --only runs one verdict again" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, """
    [[mutant]]
    name = "g is wrong"
    file = "src/base/options.jl"
    from = "g() = 2"
    to = "g() = 3"
    operator = "literal"

    [[mutant]]
    name = "h is not tested by the unit"
    file = "src/base/tools.jl"
    from = "h() = 3"
    to = "h() = 4"
    """)
    pkg = fixture()
    code, out = script(MUTATE, pkg, "--warm", list, "base/options.jl")
    @test code == 0
    @test occursin("1 CAUGHT, 1 SURVIVED", out)
    result = M.result_path(list)
    @test result == joinpath(dir, "mutants.result.json")
    @test occursin("result: $result", out)
    r = M.JSON.parsefile(result)
    ms = Dict(m["name"] => m for m in r["mutants"])
    @test ms["g is wrong"]["verdict"] == "CAUGHT" && ms["g is wrong"]["operator"] == "literal"
    h = ms["h is not tested by the unit"]
    @test h["verdict"] == "SURVIVED" && h["file"] == "src/base/tools.jl" && h["line"] == 1
    @test h["tree"] == r["tree"] == M.tree_hash(pkg) && h["units"] == ["base/options.jl"]
    s = only(r["survivors_by_line"])
    @test s["file"] == "src/base/tools.jl" && s["line"] == 1 && s["mutants"] == ["h is not tested by the unit"]
    # the same tree and units: no mutant runs, and no smoke mutant
    code, out = script(MUTATE, pkg, "--warm", list, "base/options.jl")
    @test code == 0
    @test occursin("kept: 2 verdicts", out) && occursin("warm: 0 mutants", out) && !occursin("smoke:", out)
    @test count("kept from the last result", out) == 2
    @test occursin("1 CAUGHT, 1 SURVIVED", out)
    # a test of h changes the tree: --only SURVIVED runs h again, and g keeps its verdict
    write(joinpath(pkg, "test/base/options.jl"), "using Test, Fixture\n@test Fixture.g() == 2\n@test Fixture.h() == 3\n")
    code, out = script(MUTATE, pkg, "--warm", list, "--only", "SURVIVED", "base/options.jl")
    @test code == 0
    @test occursin("kept: 1 verdicts", out)
    @test occursin(r"CAUGHT: h is not tested by the unit — [^\n]*warm, ", out)
    @test occursin("2 CAUGHT, 0 SURVIVED", out)
    # g's verdict holds for the old tree, so a plain run runs g again and keeps h
    code, out = script(MUTATE, pkg, "--warm", list, "base/options.jl")
    @test occursin("kept: 1 verdicts", out)
    @test occursin(r"CAUGHT: g is wrong — [^\n]*warm, ", out)
    # other units are another key
    @test !occursin("kept:", last(script(MUTATE, pkg, "--warm", list, "base/common.jl")))
    # the cold mode keeps verdicts too
    rm(result)
    script(MUTATE, pkg, "--list", list, "base/options.jl")
    @test count("kept from the last result", last(script(MUTATE, pkg, "--list", list, "base/options.jl"))) == 2
    # --only needs a result and a verdict
    rm(result)
    @test first(script(MUTATE, pkg, "--warm", list, "--only", "SURVIVED", "base/options.jl")) == 2
    @test first(script(MUTATE, pkg, "--warm", list, "--only", "INVALID", "base/options.jl")) == 2
end

@testset "a sweep whose units reach no changed function stops at the smoke mutant" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/run-tests-test")))
    list = joinpath(dir, "mutants.toml")
    write(list, "[[mutant]]\nname = \"h changed\"\nfile = \"src/base/tools.jl\"\nfrom = \"h() = 3\"\nto = \"h() = 4\"\n")
    code, out = script(MUTATE, fixture(), "--warm", list, "base/options.jl")
    @test code == 3
    @test occursin("smoke: SURVIVED", out)
    @test occursin(r"UNKNOWN: h changed — [^\n]*the smoke mutant survived: the units reach none of the 1 functions", out)
    @test occursin("0 CAUGHT, 0 SURVIVED, 1 UNKNOWN, 0 INVALID, of 1 mutants", out)
    @test !occursin("warm: ", out)
    # a unit that calls h catches the smoke mutant, and the sweep runs
    code, out = script(MUTATE, fixture(), "--warm", list, "base/common.jl")
    @test code == 0
    @test occursin("smoke: CAUGHT", out) && occursin("1 CAUGHT, 0 SURVIVED", out)
    # a short-form body goes in parentheses; a long-form body gets the call before its first statement
    tools = M.smoke_edits(fixture(), [("m", M.Edit[("src/base/tools.jl", "h() = 3", "h() = 4", nothing)])], [1])
    @test M.mutated(fixture(), tools)["src/base/tools.jl"] == "h() = (error(\"mutate.jl smoke\"); 3)\n"
    long = fixture(Dict{String, Union{String, Nothing}}(
        "src/base/options.jl" => "function g(x = 1)\n    y = x\n    return y\nend\n"))
    edits = M.smoke_edits(long, [("m", M.Edit[("src/base/options.jl", "return y", "return 0", nothing)])], [1])
    @test M.mutated(long, edits)["src/base/options.jl"] ==
          "function g(x = 1)\n    error(\"mutate.jl smoke\"); y = x\n    return y\nend\n"
    # a mutant outside every function gives no smoke mutant
    flat = fixture(Dict{String, Union{String, Nothing}}("src/base/tools.jl" => "const C = 3\n"))
    @test M.smoke_edits(flat, [("m", M.Edit[("src/base/tools.jl", "3", "4", nothing)])], [1]) === nothing
end

const PINS = joinpath(SCRIPTS, "pins.jl")

@testset "pins.jl runs the branch's tests on the base's code" begin
    branch = fixture()
    # the base: the same package, where g returns 3
    base = fixture(Dict{String, Union{String, Nothing}}("src/base/options.jl" => "g() = 3\n"))
    code, out = script(PINS, branch, base, "base/options.jl")
    @test code == 0
    @test occursin("FAILS on $base: src and ext of $base under the branch's tests", out)
    # a test that does not reach g passes on the base, so it pins
    code, out = script(PINS, branch, base, "solvers/newton.jl")
    @test code == 0
    @test occursin("PINS — every unit passes on $base", out)
    # the package keeps its own code
    @test read(joinpath(branch, "src/base/options.jl"), String) == "g() = 2\n"
    # a mode of run-tests.jl is no unit
    @test first(script(PINS, branch, base, "affected")) == 2
    # mutate.jl's old --base names the new command
    code, out = script(MUTATE, branch, "--base", "origin/main", "base/options.jl")
    @test code == 2
    @test occursin("pins.jl", out)
end

@testset "mutate.jl checks a single edit before it runs it" begin
    code, out = script(MUTATE, fixture(), "src/base/options.jl", "g() = 2", "g() = (2",
        "base/options.jl")
    @test code == 3
    @test occursin("INVALID", out) && occursin("does not parse", out)
    @test !occursin("CAUGHT", out)
end

@testset "the census does not count a file outside test/ as reached" begin
    dir = fixture(Dict{String, Union{String, Nothing}}("test/runtests.jl" => replace(
        FIXTURE_RUNTESTS,
        "if \"slow\"" => "if \"broken\" in GROUPS\n    @safetestset \"Source\" include(\"../src/base/tools.jl\")\nend\nif \"slow\"")))
    row = C.census(dir)
    @test row.reached == 7
    # a path that is not normalised counts the same
    @test C.census(joinpath(dir, ".")).reached == 7
end
