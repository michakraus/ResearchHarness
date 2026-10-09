#!/usr/bin/env julia
#
# Checks for gate.jl. Run after any change to it, with the default Julia:
#
#   julia --startup-file=no gate-test.jl
#
# A sandboxed process cannot create a `.git`, so the steps are checked on the outputs of the
# scripts they run, given as text; the whole gate runs on a real head, not here.

using Test

module Gate
include(joinpath(@__DIR__, "gate.jl"))
end

const GATE = joinpath(@__DIR__, "gate.jl")
const DIR = mktempdir(mkpath(expanduser("~/Research/.scratch/gate-test")))

@testset "the tests step reads the verdict and the summary of run-tests.jl" begin
    out = "Pkg: 13 of 21 test files in core, Julia 1.13.1\n  the diff\n\nPASS in 26 s — log: /x.log\nTest Summary: | Pass  Total\nselected      |  10     10\n"
    s = Gate.tests_step(0, out, 26.0, "/x.log")
    @test s.verdict == "PASS" && s.numbers == "Pkg: 13 of 21 test files in core, Julia 1.13.1"
    @test s.detail == ["Test Summary: | Pass  Total", "selected      |  10     10"]
    @test Gate.tests_step(1, replace(out, "PASS" => "FAIL"), 26.0, "/x.log").verdict == "FAIL"
    # a layout that run-tests.jl refuses is no verdict on the tests
    s = Gate.tests_step(2, "Pkg: the tests are not in the layout of the test convention\n", 1.0, "/x.log")
    @test s.verdict == "UNKNOWN" && s.numbers == "run-tests.jl exited 2"
end

@testset "the named step fails on a survivor and gives no verdict on an UNKNOWN" begin
    ok = "smoke: CAUGHT — x\nCAUGHT: N1 — a\nCAUGHT: N2 — b\n\n2 CAUGHT, 0 SURVIVED, 0 UNKNOWN, 0 INVALID, of 2 mutants\n"
    s = Gate.named_step(0, ok, 9.0, "/n.log")
    @test s.verdict == "PASS" && s.numbers == "2 CAUGHT, 0 SURVIVED, 0 UNKNOWN, 0 INVALID, of 2 mutants"
    @test s.detail == ["smoke: CAUGHT — x"]
    bad = replace(ok, "CAUGHT: N2" => "SURVIVED: N2", "2 CAUGHT, 0 SURVIVED" => "1 CAUGHT, 1 SURVIVED")
    s = Gate.named_step(0, bad, 9.0, "/n.log")
    @test s.verdict == "FAIL" && "SURVIVED: N2 — b" in s.detail
    @test Gate.named_step(3, replace(ok, "CAUGHT: N2" => "UNKNOWN: N2"), 9.0, "/n.log").verdict == "UNKNOWN"
    @test Gate.named_step(2, "a.toml holds no [[mutant]] table\n", 1.0, "/n.log").verdict == "UNKNOWN"
end

@testset "the generated step lists the survivors by line, as information" begin
    result = joinpath(DIR, "generated.result.json")
    write(result, """
    {"mutants": [
      {"name": "G1", "verdict": "SURVIVED", "edits": [{"file": "src/a.jl", "from": "x < 1", "to": "x <= 1", "at": 5}]},
      {"name": "G2", "verdict": "NO-COVERAGE", "edits": [{"file": "src/a.jl", "from": "y", "to": "(z)", "at": 9}]},
      {"name": "G3", "verdict": "CAUGHT", "edits": [{"file": "src/b.jl", "from": "a", "to": "b", "at": 1}]}],
     "survivors_by_line": [{"file": "src/a.jl", "line": 3, "mutants": ["G1", "G2"]}]}
    """)
    @test Gate.survivor_lines(result) == ["src/a.jl:3: `x < 1` → `x <= 1`; `y` → `(z)` (no unit runs it)"]
    out = "smoke: CAUGHT — x\n\n1 CAUGHT, 1 SURVIVED, 1 NO-COVERAGE, 0 UNKNOWN, 0 INVALID, of 3 mutants\n"
    s = Gate.generated_step(0, out, 60.0, "/g.log", result)
    @test s.verdict == "INFO" && length(s.detail) == 2
    # no totals, or no result, is no verdict
    @test Gate.generated_step(2, "", 1.0, "/g.log", result).verdict == "UNKNOWN"
    @test Gate.generated_step(0, out, 1.0, "/g.log", joinpath(DIR, "none.json")).verdict == "UNKNOWN"
end

@testset "the format step names each file that the formatter would change" begin
    pkg = mktempdir(DIR)
    mkpath(joinpath(pkg, "src"))
    write(joinpath(pkg, "src", "good.jl"), "f(x) = x + 1\n")
    write(joinpath(pkg, "src", "bad.jl"), "f( x )=x+1\n")
    s = Gate.format_step(pkg, ["src/good.jl", "src/bad.jl"])
    @test s.verdict == "FAIL" && s.detail == ["src/bad.jl"] && s.numbers == "1 of 2 files not formatted"
    @test read(joinpath(pkg, "src", "bad.jl"), String) == "f( x )=x+1\n"
    @test Gate.format_step(pkg, ["src/good.jl"]).verdict == "PASS"
end

@testset "the verdict and the report" begin
    S(n, v) = Gate.Step(n, v, "numbers of $n", v == "PASS" ? String[] : ["detail of $n"], 1.4, "/$n.log")
    @test Gate.verdict([S("a", "PASS"), S("b", "INFO")]) == ("PASS", 0)
    @test Gate.verdict([S("a", "UNKNOWN"), S("b", "PASS")]) == ("UNKNOWN", 3)
    @test Gate.verdict([S("a", "UNKNOWN"), S("b", "FAIL")]) == ("FAIL", 1)
    r = Gate.render("Pkg at abc1234, base origin/main", [S("tests", "PASS"), S("named", "FAIL"), S("generated", "INFO")])
    @test startswith(r, "# Gate — Pkg at abc1234, base origin/main\n\nVerdict: FAIL — named\n")
    @test occursin("| named | FAIL | numbers of named | 1 s | `/named.log` |", r)
    @test occursin("## named\n\n- detail of named", r) && occursin("## generated", r) && !occursin("## tests", r)
end

@testset "gate.jl refuses bad arguments" begin
    run_gate(args...) = run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $GATE $args`);
        stdout = devnull, stderr = devnull)).exitcode
    @test run_gate(DIR) == 2
    @test run_gate(DIR, DIR, "--jobs", "0") == 2
    @test run_gate(DIR, DIR, "--named", joinpath(DIR, "none.toml")) == 2
    @test run_gate(DIR, DIR, "--colour") == 2
end
