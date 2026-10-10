#!/usr/bin/env julia
#
# Checks for claude-autocommit on the system it runs on, macOS or Linux. Run after any change to it:
#
#   julia --startup-file=no launchagents/claude-autocommit-test.jl
#
# Each case builds a fixture ~/.claude repository under mktempdir(), with a bare remote as its
# origin, and runs the script under /bin/bash, which is bash 3.2 on macOS. HOME, the git identity
# and XDG_STATE_HOME are set in the environment of each subprocess, and git reads no global or
# system configuration, so nothing reaches the real ~/.claude.

using Test

const SCRIPT = joinpath(@__DIR__, "claude-autocommit")
const LINUX = Sys.islinux()
Sys.isapple() || LINUX || error("claude-autocommit-test.jl runs on macOS and Linux, not on $(Sys.KERNEL)")

const MEMORY = joinpath("projects", "-fixture", "memory")

"The environment of every subprocess: a fixture HOME, a fixed git identity, no git config."
function environment(home; extra...)
    env = Dict("HOME" => home, "PATH" => ENV["PATH"], "TMPDIR" => tempdir(),
               "GIT_CONFIG_GLOBAL" => "/dev/null", "GIT_CONFIG_NOSYSTEM" => "1",
               "GIT_AUTHOR_NAME" => "Fixture", "GIT_AUTHOR_EMAIL" => "fixture@example.org",
               "GIT_COMMITTER_NAME" => "Fixture", "GIT_COMMITTER_EMAIL" => "fixture@example.org")
    for (k, v) in extra
        env[string(k)] = v
    end
    return env
end

git(repo, env, args...) = readchomp(setenv(`git -C $repo $args`, env))

"Settle a file: give it an mtime well outside the quiescence window."
settle(path) = run(`touch -t 202001010000 $path`)

"""
A fixture: HOME, and in it a `.claude` repository on `main` with one plan and one memory index
committed and pushed to a bare remote. Returns (home, repo, remote, env).
"""
function fixture(; extra...)
    home = realpath(mktempdir())
    repo = joinpath(home, ".claude")
    remote = joinpath(home, "remote.git")
    env = environment(home; extra...)
    run(setenv(`git init -q --bare -b main $remote`, env))
    run(setenv(`git init -q -b main $repo`, env))
    mkpath(joinpath(repo, "plans"))
    mkpath(joinpath(repo, MEMORY))
    write(joinpath(repo, "plans", "first.md"), "a plan\n")
    write(joinpath(repo, MEMORY, "MEMORY.md"), "- [one](one.md)\n")
    write(joinpath(repo, "settings.json"), "{}\n")
    git(repo, env, "add", "plans", MEMORY, "settings.json")
    git(repo, env, "commit", "-q", "-m", "initial")
    git(repo, env, "remote", "add", "origin", remote)
    git(repo, env, "push", "-q", "origin", "main")
    return home, repo, remote, env
end

"Run the script under /bin/bash; return the exit code and its output."
function run_script(repo, env, args...)
    out = IOBuffer()
    cmd = setenv(`/bin/bash $SCRIPT $args`, merge(env, Dict("CLAUDE_AUTOCOMMIT_REPO" => repo)))
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    return code, String(take!(out))
end

"The lock's directory on this system for a HOME and an XDG_STATE_HOME (`nothing`: unset)."
function lock_dir(home, xdg)
    LINUX || return joinpath(home, "Library", "Logs", "claude-autocommit")
    state = (xdg === nothing || isempty(xdg)) ? joinpath(home, ".local", "state") : xdg
    return joinpath(state, "claude-autocommit")
end

@testset "claude-autocommit on $(LINUX ? "Linux" : "macOS")" begin
    @testset "a settled memory is committed and pushed; a staged file outside stays staged" begin
        home, repo, remote, env = fixture()
        memory = joinpath(repo, MEMORY, "one.md")
        write(memory, "one fact\n")
        settle(memory)
        write(joinpath(repo, "settings.json"), "{\"changed\": true}\n")
        git(repo, env, "add", "settings.json")

        code, out = run_script(repo, env)
        @test code == 0
        @test occursin("committed 0 plan(s), 1 memory file(s)", out)
        @test split(git(repo, env, "show", "--name-only", "--format=", "HEAD")) == [joinpath(MEMORY, "one.md")]
        @test git(remote, env, "rev-parse", "main") == git(repo, env, "rev-parse", "HEAD")
        @test git(repo, env, "diff", "--cached", "--name-only") == "settings.json"
    end

    @testset "the lock lands at this system's path (XDG_STATE_HOME $label)" for (label, xdg) in
                                                                                 (("unset", nothing),
                                                                                  ("empty", ""),
                                                                                  ("set", "state"))
        home, repo, remote, env = fixture()
        xdg === nothing || (env["XDG_STATE_HOME"] = isempty(xdg) ? "" : joinpath(home, xdg))
        expected = lock_dir(home, get(env, "XDG_STATE_HOME", nothing))
        memory = joinpath(repo, MEMORY, "one.md")
        write(memory, "one fact\n")
        settle(memory)

        code, out = run_script(repo, env, "--no-push")
        @test code == 0
        # The script removes the lock on exit and leaves the directory that holds it.
        @test isdir(expected)
        @test !ispath(joinpath(expected, "lock"))
        for other in (joinpath(home, "Library"), joinpath(home, ".local", "state"),
                      joinpath(home, "state"))
            startswith(expected, other) || @test !ispath(other)
        end
    end

    @testset "a held lock defers the run" begin
        home, repo, remote, env = fixture()
        mkpath(joinpath(lock_dir(home, nothing), "lock"))
        memory = joinpath(repo, MEMORY, "one.md")
        write(memory, "one fact\n")
        settle(memory)
        head = git(repo, env, "rev-parse", "HEAD")

        code, out = run_script(repo, env)
        @test code == 0
        @test git(repo, env, "rev-parse", "HEAD") == head
    end
end
