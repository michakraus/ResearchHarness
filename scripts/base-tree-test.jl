#!/usr/bin/env julia
#
# Checks for base-tree.jl. Run after any change to it, with the default Julia:
#
#   julia --startup-file=no base-tree-test.jl
#
# The tests read the commits of this repository, and of fixture repositories under tempdir(),
# where a sandboxed process can make a `.git`.

using Test

module B
include(joinpath(@__DIR__, "base-tree.jl"))
end

const REPO = dirname(@__DIR__)
const SCRIPT = joinpath(@__DIR__, "base-tree.jl")
const GITENV = filter(((k, _),) -> !startswith(k, "GIT_"), ENV)
const HOOKS = ".githooks"

git(dir, args...) = run(setenv(`git -c user.name=fixture -c user.email=fixture@example.org $args`, GITENV; dir))

"A new git repository at `dir` with one commit that holds each of `files`."
function fixture(dir, files)
    for f in files
        mkpath(dirname(joinpath(dir, f)))
        write(joinpath(dir, f), "$f\n")
    end
    git(dir, "init", "-q", ".")
    git(dir, "add", "--all")
    git(dir, "commit", "-q", "-m", "one")
    return dir
end

"The files under `dir`, relative to it, sorted."
files(dir) = sort!([relpath(joinpath(r, f), dir) for (r, _, fs) in walkdir(dir) for f in fs])

"Whether a path under `dir`, a directory or a file, has a segment named `.githooks`."
hooks_inside(dir) = any(((r, ds, fs),) -> HOOKS in ds || HOOKS in fs, walkdir(dir))

"The error that `base_tree` throws for `paths`, or `nothing` where it throws none."
function refusal(pkg, dest, paths)
    try
        B.base_tree(pkg, "HEAD", dest, paths)
        return nothing
    catch e
        return e
    end
end

@testset "base-tree.jl" verbose = true begin
    mktempdir() do tmp
        written = ["a$HOOKS/keep", "src/a.jl", "sub/$HOOKS-notes"]
        left = ["$HOOKS/pre-commit", "src/deep/$HOOKS/y", "x/$HOOKS"]
        fix = fixture(joinpath(tmp, "fix"), [written; left])
        sub = ["pkg/Project.toml", "pkg/src/P.jl", "pkg/$HOOKS/pre-commit"]
        fixpkg = fixture(joinpath(tmp, "fixpkg"), [written; left; sub])

        @testset "the whole tree of HEAD" begin
            dest = joinpath(tmp, "whole")
            n = B.base_tree(REPO, "HEAD", dest)
            tracked = split(read(`git -C $REPO ls-tree -r --name-only HEAD`, String), '\n';
                keepempty = false)
            kept = filter(f -> !(HOOKS in splitpath(f)), tracked)
            @test length(kept) < length(tracked)
            @test n == length(kept)
            @test !hooks_inside(dest)
            @test read(joinpath(dest, "Project.toml"), String) ==
                  read(`git -C $REPO show HEAD:Project.toml`, String)
        end

        @testset "a .githooks at any depth is not written" begin
            dest = joinpath(tmp, "depth")
            @test B.base_tree(fix, "HEAD", dest) == 3
            @test files(dest) == written
            @test !hooks_inside(dest)
        end

        @testset "a package in a subdirectory" begin
            dest = joinpath(tmp, "sub")
            @test B.base_tree(joinpath(fixpkg, "pkg"), "HEAD", dest) == 2
            @test files(dest) == ["Project.toml", "src/P.jl"]
        end

        @testset "a named path inside .githooks is refused" begin
            for (k, (pkg, paths)) in enumerate(((REPO, ["$HOOKS/pre-push"]),
                (REPO, ["Project.toml", HOOKS]), (fix, ["src/deep/$HOOKS/y"]),
                (fix, ["./$HOOKS/pre-commit"]), (fix, ["src/../$HOOKS/pre-commit"])))
                dest = joinpath(tmp, "refused-$k")
                e = refusal(pkg, dest, paths)
                @test e isa ErrorException && occursin("git show", e.msg)
                @test !ispath(dest)
            end
            # the segment counts after normpath: this path names no file inside `.githooks`
            @test B.base_tree(REPO, "HEAD", joinpath(tmp, "back"), ["$HOOKS/../LICENSE"]) == 1
            dest = joinpath(tmp, "refused-cli")
            p = run(pipeline(
                ignorestatus(`$(Base.julia_cmd()) --startup-file=no $SCRIPT $REPO HEAD $dest $HOOKS/pre-push`);
                stderr = devnull))
            @test p.exitcode == 1
            @test !ispath(dest)
        end

        @testset "a name that only contains .githooks is written" begin
            dest = joinpath(tmp, "contains")
            @test B.base_tree(fix, "HEAD", dest, ["a$HOOKS/keep", "sub/$HOOKS-notes"]) == 2
            @test files(dest) == ["a$HOOKS/keep", "sub/$HOOKS-notes"]
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
