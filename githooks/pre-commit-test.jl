#!/usr/bin/env julia
#
# Checks for the shared pre-commit hook, on the system it runs on. Run after any change to it:
#
#   julia --startup-file=no githooks/pre-commit-test.jl
#
# The hook lives byte-identical in every package repository, so this test never edits it: each
# case builds a fixture package repository under mktempdir(), stages files in it and runs the
# hook as it stands, from the fixture's root. The formatting stage loads JuliaFormatter from the
# harness environment, $RESEARCH_HARNESS_JULIA, as the hook does. HOME and the git identity are set
# in each subprocess, and git reads no global or system configuration.

using Test

const HOOK = joinpath(@__DIR__, "pre-commit")

const FORMATTED = """
    module Fixture

    export double

    double(x) = 2x

    end
    """

const MISFORMATTED = """
    module Fixture

    export double

    double( x )=2*x

    end
    """

# Formatted, and fails at load: the name is undefined.
const DOES_NOT_LOAD = """
    module Fixture

    const VALUE = undefined_name + 1

    end
    """

function environment(home)
    env = Dict("HOME" => home, "PATH" => ENV["PATH"], "TMPDIR" => tempdir(),
               "GIT_CONFIG_GLOBAL" => "/dev/null", "GIT_CONFIG_NOSYSTEM" => "1",
               "GIT_AUTHOR_NAME" => "Fixture", "GIT_AUTHOR_EMAIL" => "fixture@example.org",
               "GIT_COMMITTER_NAME" => "Fixture", "GIT_COMMITTER_EMAIL" => "fixture@example.org",
               "RESEARCH_HARNESS_JULIA" => get(ENV, "RESEARCH_HARNESS_JULIA",
                                               joinpath(homedir(), ".local", "share",
                                                        "research-harness", "julia")))
    # The Julia that runs this test, so the hook's `julia` is the same release. A fixture depot
    # comes first, so the fixture package's cache goes there; this process's depots follow, for
    # JuliaFormatter.
    env["PATH"] = Sys.BINDIR * ":" * env["PATH"]
    env["JULIA_DEPOT_PATH"] = join([joinpath(home, ".julia"); DEPOT_PATH], ":")
    return env
end

"""
A fixture package repository with `src/Fixture.jl` holding `source` and staged, and the files
of `extra` (path => text) staged with it. Returns the hook's exit code and output.
"""
function run_hook(source; extra = Pair{String,String}[])
    root = realpath(mktempdir())
    home = joinpath(root, "home")
    repo = joinpath(root, "Fixture")
    mkpath(home)
    mkpath(joinpath(repo, "src"))
    env = environment(home)
    run(setenv(`git init -q -b main $repo`, env))
    write(joinpath(repo, "Project.toml"), """
        name = "Fixture"
        uuid = "8c1f2a4e-6b0d-4f3a-9e57-2d8c4b1a0f61"
        version = "0.1.0"
        """)
    write(joinpath(repo, ".JuliaFormatter.toml"), "style = \"sciml\"\n")
    files = ["Project.toml", ".JuliaFormatter.toml"]
    if source !== nothing
        write(joinpath(repo, "src", "Fixture.jl"), source)
        push!(files, joinpath("src", "Fixture.jl"))
    end
    for (path, text) in extra
        mkpath(dirname(joinpath(repo, path)))
        write(joinpath(repo, path), text)
        push!(files, path)
    end
    run(setenv(`git -C $repo add $files`, env))
    out = IOBuffer()
    cmd = setenv(`bash $HOOK`, env; dir = repo)
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    return code, String(take!(out))
end

@testset "pre-commit" begin
    @testset "a formatted file that loads passes" begin
        code, out = run_hook(FORMATTED)
        @test code == 0
        @test occursin("formatting: ok", out)
        @test occursin("loads: ok", out)
    end

    @testset "a misformatted file is refused" begin
        code, out = run_hook(MISFORMATTED)
        @test code == 1
        @test occursin("formatting: FAILED", out)
    end

    @testset "a formatted file that does not load is refused" begin
        code, out = run_hook(DOES_NOT_LOAD)
        @test code == 1
        @test occursin("formatting: ok", out)
        @test occursin("loads: FAILED", out)
    end

    # No .jl file staged: the hook ends early, on the test-layout stage's verdict.
    @testset "a commit that touches test/ without .githooks/test-layout.jl is refused" begin
        code, out = run_hook(nothing; extra = ["test/data.txt" => "data\n"])
        @test code == 1
        @test occursin("test-layout.jl is missing", out)
    end
end
