#!/usr/bin/env julia
#
# Checks for julia-methods.jl, against the real `fatou` on the PATH, which CI installs:
#
#   julia --startup-file=no scripts/julia-methods-test.jl
#
# Each fixture is one source file of a package under mktempdir(); the package never loads, because
# julia-methods.jl reads its files through `fatou lsp`. Where no `fatou` is on the PATH, the
# testsets that run the script print one line and are skipped.

using Test

const SCRIPT = joinpath(@__DIR__, "julia-methods.jl")
const ROOT = dirname(@__DIR__)
const MARK = "more than one qualified spelling"

"A package directory under mktempdir() whose `src/P.jl` holds `body` inside `module P`."
function fixture(body)
    dir = realpath(mktempdir())
    mkpath(joinpath(dir, "src"))
    write(joinpath(dir, "src", "P.jl"), "module P\n" * body * "end\n")
    return dir
end

"Run julia-methods.jl on `dir` with `args`: the exit code and the lines of stdout."
function run_methods(dir, args...)
    out = IOBuffer()
    cmd = `$(Base.julia_cmd()) --startup-file=no $SCRIPT $dir $(collect(args))`
    proc = run(pipeline(ignorestatus(cmd); stdout = out, stderr = devnull))
    return proc.exitcode, split(String(take!(out)), '\n')
end

"The index of the summary line, which closes the listing."
summary_index(lines) = findfirst(l -> occursin(r"method\(s\) in \d+ file\(s\)", l), lines)

"The non-empty lines after the summary line."
after_summary(lines) = filter(!isempty, lines[(summary_index(lines) + 1):end])

"The lines that carry the mark."
marked(lines) = filter(l -> occursin(MARK, l), lines)

"The body of the level-2 section of Markdown `text` whose heading contains `name`."
function section(text, name)
    lines = split(text, '\n')
    start = findfirst(l -> startswith(l, "## ") && occursin(name, l), lines)
    stop = findnext(l -> startswith(l, "## "), lines, start + 1)
    return join(lines[start:(stop === nothing ? end : stop - 1)], '\n')
end

const NUMBERS = Dict("nine" => 9, "ten" => 10, "eleven" => 11, "twelve" => 12, "thirteen" => 13)

@testset "julia-methods.jl" verbose = true begin
    if Sys.which("fatou") === nothing
        println("skip  julia-methods.jl against the real fatou: no fatou on the PATH")
    else
        two = fixture("f(x) = 1\nM.f(x::Int) = 2\nh(x) = 1\nh(x, y) = 2\n")

        @testset "f(x) and M.f(x::Int): exit 3, the listing, one line after the summary" begin
            code, lines = run_methods(two, "f")
            @test code == 3
            @test "f — 2 method(s)" in lines
            @test any(l -> occursin("src/P.jl:2", l) && endswith(l, "f(x)"), lines)
            @test any(l -> occursin("src/P.jl:3", l) && endswith(l, "M.f(x::Int)"), lines)
            @test summary_index(lines) !== nothing
            after = after_summary(lines)
            @test length(after) == 1
            line = only(after)
            @test startswith(line, "f: ")
            @test occursin("(f, M.f)", line)
            @test occursin("search_methods", line)
            @test occursin("julia-callers.jl", line)
            @test occursin(MARK, line)
        end

        @testset "A.g(x) and B.g(x): exit 3, the line names A.g, B.g" begin
            dir = fixture("A.g(x) = 1\nB.g(x) = 2\n")
            code, lines = run_methods(dir, "g")
            @test code == 3
            line = only(after_summary(lines))
            @test startswith(line, "g: ")
            @test occursin("(A.g, B.g)", line)
        end

        @testset "one spelling: exit 0, no line" begin
            code, lines = run_methods(two, "h")
            @test code == 0
            @test any(l -> startswith(l, "h — 2 method(s)"), lines)
            @test isempty(marked(lines))
            @test isempty(after_summary(lines))

            dir = fixture("M.k(x) = 1\nM.k(x, y) = 2\n")
            code, lines = run_methods(dir, "k")
            @test code == 0
            @test any(l -> startswith(l, "k — 2 method(s)"), lines)
            @test isempty(marked(lines))
            @test isempty(after_summary(lines))
        end

        @testset "two names: one line per name with two spellings" begin
            code, lines = run_methods(two, "f", "h")
            @test code == 3
            after = after_summary(lines)
            @test length(after) == 1
            @test startswith(only(after), "f: ")

            dir = fixture("f(x) = 1\nM.f(x::Int) = 2\nA.g(x) = 1\nB.g(x) = 2\n")
            code, lines = run_methods(dir, "f", "g")
            @test code == 3
            after = after_summary(lines)
            @test length(after) == 2
            @test startswith(after[1], "f: ") && occursin("f, M.f", after[1])
            @test startswith(after[2], "g: ") && occursin("A.g, B.g", after[2])
        end

        @testset "no definition: exit 1; beside a name with two spellings: exit 3" begin
            code, lines = run_methods(two, "nothere")
            @test code == 1
            @test any(l -> startswith(l, "no methods found"), lines)

            code, lines = run_methods(two, "nothere", "f")
            @test code == 3
            @test startswith(only(after_summary(lines)), "f: ")
        end

        @testset "--all: exit 0, the heading of f carries the mark, that of h does not" begin
            code, lines = run_methods(two, "--all")
            @test code == 0
            heading_f = only(filter(l -> startswith(l, "f — "), lines))
            heading_h = only(filter(l -> startswith(l, "h — "), lines))
            @test occursin(MARK, heading_f)
            @test !occursin(MARK, heading_h)
            @test isempty(after_summary(lines))
        end
    end

    @testset "CI runs this file, and development.md counts the matrix" begin
        workflow = read(joinpath(ROOT, ".github", "workflows", "julia.yml"), String)
        lines = split(workflow, '\n')
        start = findfirst(l -> strip(l) == "file:", lines)
        stop = findnext(l -> strip(l) == "steps:", lines, start)
        files = [strip(l)[3:end] for l in lines[(start + 1):(stop - 1)] if startswith(strip(l), "- ")]
        @test "scripts/julia-methods-test.jl" in files
        development = read(joinpath(ROOT, "docs", "src", "development.md"), String)
        m = match(r"`\.github/workflows/julia\.yml` runs the (\w+) Julia test files", development)
        @test m !== nothing
        @test get(NUMBERS, m[1], -1) == length(files)
    end

    @testset "the docs, the header and the skill state exit 3 and the mark" begin
        header = join(filter(l -> startswith(l, "#"), split(read(SCRIPT, String), '\n')), '\n')
        page = section(read(joinpath(ROOT, "docs", "src", "components", "scripts.md"), String),
            "`julia-methods.jl`")
        for text in (header, page)
            @test occursin("status 3", text)
            @test occursin(MARK, text)
            @test occursin("--all", text)
        end
        skill = read(joinpath(ROOT, "skills", "julia-structure", "SKILL.md"), String)
        start = findfirst("### `julia-methods.jl`", skill)
        stop = findnext("\n### ", skill, last(start))
        part = skill[first(start):first(stop)]
        @test occursin("status 3", part)
        @test occursin("search_methods", part)
    end
end
