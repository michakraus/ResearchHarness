#!/usr/bin/env julia
#
# Checks for base-tree.jl. Run after any change to it, with the default Julia:
#
#   julia --startup-file=no base-tree-test.jl
#
# A sandboxed process cannot create a `.git`, so the tests read the commits of this repository.

using Test

module B
include(joinpath(@__DIR__, "base-tree.jl"))
end

const REPO = dirname(@__DIR__)
const SCRIPT = joinpath(@__DIR__, "base-tree.jl")

@testset "base-tree.jl" begin
    mktempdir() do tmp
        @testset "the whole tree of HEAD" begin
            dest = joinpath(tmp, "whole")
            n = B.base_tree(REPO, "HEAD", dest)
            tracked = split(read(`git -C $REPO ls-tree -r --name-only HEAD`, String), '\n';
                keepempty = false)
            @test n == length(tracked)
            @test read(joinpath(dest, "Project.toml"), String) ==
                  read(`git -C $REPO show HEAD:Project.toml`, String)
        end

        @testset "only the named paths" begin
            dest = joinpath(tmp, "paths")
            @test B.base_tree(REPO, "HEAD", dest, ["Project.toml", "LICENSE"]) == 2
            @test sort(readdir(dest)) == ["LICENSE", "Project.toml"]
        end

        @testset "a non-empty destination is refused" begin
            dest = joinpath(tmp, "full")
            mkpath(dest)
            write(joinpath(dest, "stale.jl"), "")
            @test_throws ErrorException B.base_tree(REPO, "HEAD", dest)
            @test readdir(dest) == ["stale.jl"]
        end

        @testset "an unknown ref fails" begin
            @test_throws ProcessFailedException B.base_tree(REPO, "no-such-ref", joinpath(tmp, "bad"))
        end

        @testset "the command line" begin
            dest = joinpath(tmp, "cli")
            out = read(`$(Base.julia_cmd()) --startup-file=no $SCRIPT $REPO HEAD $dest LICENSE`,
                String)
            sha = chomp(read(`git -C $REPO rev-parse --short HEAD`, String))
            @test out == "$dest: 1 files of HEAD at $sha\n"
            usage = run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $SCRIPT $REPO`);
                stderr = devnull))
            @test usage.exitcode == 2
        end
    end
end
