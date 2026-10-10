#!/usr/bin/env julia
#
# Checks for julia-update.jl on the system it runs on, macOS or Linux. Run after any change to it:
#
#   julia --startup-file=no scripts/julia-update-test.jl
#
# Each case runs the script in a subprocess on a fixture HOME under mktempdir(), with an
# environment of its own and a PATH that holds only a stub directory. The fixture HOME has a stub
# juliaup and a stub julia launcher in ~/.juliaup/bin, a juliaup.json with two `X.Y` channels, the
# Kaimon app's Project.toml and a profile. The stub directory has lsof, ps, both service managers
# (launchctl, systemctl) and both notifiers (osascript, notify-send). Every stub appends its name
# and arguments to a call log, so no case can reach the real ~/.juliaup or the real Kaimon server.
#
# The server is a real process: a copy of `sleep` named `julia`, which the test starts, then
# deletes, rewrites or leaves alone, and whose pid the lsof stub prints. On Linux the script reads
# its binary from /proc/<pid>/exe; on macOS from `ps`, whose stub prints the copy's path while the
# process lives.

using Test

const SCRIPT = joinpath(@__DIR__, "julia-update.jl")
const LINUX = Sys.islinux()
Sys.isapple() || LINUX || error("julia-update-test.jl runs on macOS and Linux, not on $(Sys.KERNEL)")

const PREFIX = "org.example"
# The restart call of this system as the stub logs it, and the service manager of the other one.
const RESTART = LINUX ? "systemctl --user restart kaimon.service" :
                "launchctl kickstart -k gui/$(Libc.getuid())/$PREFIX.kaimon"
const OTHER = LINUX ? "launchctl" : "systemctl"
const NOTIFIER = LINUX ? "notify-send" : "osascript"
# The command that the "RESTART DUE" line names, and the log that the failure alert names.
const RESTART_HINT = LINUX ? "systemctl --user restart kaimon.service" :
                     "launchctl kickstart -k gui/\$(id -u)/$PREFIX.kaimon"
const LOG_HINT = LINUX ? "journalctl --user -u julia-update.service" : "~/Library/Logs/julia-update/"

"Write an executable `/bin/sh` script."
function stub(path, body)
    write(path, "#!/bin/sh\n" * body)
    chmod(path, 0o755)
    return path
end

# Each stub logs `<name> <arguments>`. `${0##*/}` is the shell's own basename: the PATH has no
# `basename`.
const LOG_LINE = raw"""printf '%s %s\n' "${0##*/}" "$*" >> "$STUB_LOG"
"""

struct Fixture
    root::String
    home::String
    stubs::String
    log::String
    bindir::String   # the server's "release": its binary is bindir/julia
    harness::String  # the harness environment, RESEARCH_HARNESS_JULIA
end

function fixture()
    root = realpath(mktempdir())
    home = joinpath(root, "home")
    stubs = joinpath(root, "stubs")
    bindir = joinpath(root, "release", "bin")
    harness = joinpath(root, "harness-env")
    jbin = joinpath(home, ".juliaup", "bin")
    app = joinpath(home, ".julia", "environments", "apps", "Kaimon")
    config = joinpath(home, ".config", "research-harness")
    juliaup = joinpath(home, ".julia", "juliaup")
    foreach(mkpath, (stubs, bindir, harness, jbin, app, config, juliaup))
    log = joinpath(root, "calls.log")
    touch(log)

    # The launcher prints a BINDIR when asked for one, and fails a call that names $STUB_FAIL.
    stub(joinpath(jbin, "julia"), LOG_LINE * raw"""
        case "$*" in *Sys.BINDIR*) printf '%s' "$STUB_BINDIR" ;; esac
        if [ -n "$STUB_FAIL" ]; then
            case "$*" in *"$STUB_FAIL"*) exit 1 ;; esac
        fi
        exit 0
        """)
    stub(joinpath(jbin, "juliaup"), LOG_LINE * "exit 0\n")
    # Real lsof prints nothing and exits 1 when no process listens.
    stub(joinpath(stubs, "lsof"), LOG_LINE * raw"""
        [ -n "$STUB_PID" ] || exit 1
        printf '%s\n' "$STUB_PID"
        """)
    for manager in ("launchctl", "systemctl")
        stub(joinpath(stubs, manager), LOG_LINE * raw"""
            if [ -n "$STUB_RESTART_FAILS" ]; then
                echo "stub: no user manager" >&2
                exit 1
            fi
            exit 0
            """)
    end
    stub(joinpath(stubs, "osascript"), LOG_LINE * "exit 0\n")
    stub(joinpath(stubs, "notify-send"), LOG_LINE * "exit 0\n")
    # `ps -o comm= -p <pid>` prints a live process's full path on macOS, its 15-character name on
    # Linux, and nothing for an ended one. The real `ps` and `kill -0` are refused inside the agent
    # sandbox, so this stub stands for it: it prints $STUB_COMM, which `comm` sets for this system,
    # for the server's pid and nothing for any other.
    stub(joinpath(stubs, "ps"), LOG_LINE * raw"""
        [ -n "$STUB_COMM" ] && [ "$4" = "$STUB_PID" ] || exit 1
        printf '%s\n' "$STUB_COMM"
        """)

    write(joinpath(juliaup, "juliaup.json"), """
        {"Default": "release",
         "InstalledChannels": {
           "release": {"Version": "1.13.1"},
           "1.12": {"Version": "1.12.6"},
           "1.13": {"Version": "1.13.1"},
           "1.12.6": {"Version": "1.12.6"}},
         "InstalledVersions": {"1.13.1+0.aarch64.apple.darwin14": {"Path": "x"}}}
        """)
    write(joinpath(app, "Project.toml"), "name = \"Kaimon\"\nversion = \"1.0.0\"\n")
    write(joinpath(harness, "Project.toml"), "[deps]\n")
    # On Linux the profile has no launchd_prefix, so a script that read it would fail.
    write(joinpath(config, "profile.toml"), LINUX ? "leak = []\n" : "launchd_prefix = \"$PREFIX\"\n")
    return Fixture(root, home, stubs, log, bindir, harness)
end

"Start the server: a copy of `sleep` at `bindir/julia`. Returns the process and its binary."
function start_server(fx::Fixture)
    binary = joinpath(fx.bindir, "julia")
    cp(Sys.which("sleep"), binary)
    chmod(binary, 0o755)
    return run(`$binary 600`; wait = false), binary
end

"Run the script; return the exit code, its output and the call log's lines."
function run_script(fx::Fixture, extra::Pair...)
    env = Dict("HOME" => fx.home, "PATH" => fx.stubs, "STUB_LOG" => fx.log,
               "STUB_BINDIR" => fx.bindir, "RESEARCH_HARNESS_JULIA" => fx.harness)
    for (k, v) in extra
        env[k] = v
    end
    out = IOBuffer()
    cmd = setenv(`$(Base.julia_cmd()) --startup-file=no $SCRIPT`, env)
    code = run(pipeline(ignorestatus(cmd); stdout = out, stderr = out)).exitcode
    return code, String(take!(out)), readlines(fx.log)
end

"""
What `ps -o comm=` prints for a process run from `binary`: the full path on macOS, and only the
first 15 characters of the file name on Linux. So a script that read `ps` on Linux would test
the name `julia`, never the server's path.
"""
comm(binary) = LINUX ? first(basename(binary), 15) : binary

"Run the script against a live server; `prepare(binary)` acts on its binary first."
function with_server(prepare, fx::Fixture, extra::Pair...)
    proc, binary = start_server(fx)
    try
        prepare(binary)
        return run_script(fx, "STUB_PID" => string(getpid(proc)), "STUB_COMM" => comm(binary), extra...)
    finally
        kill(proc)
        wait(proc)
    end
end

restarts(calls) = count(==(RESTART), calls)
others(calls) = count(l -> startswith(l, OTHER * " "), calls)
alerts(calls) = filter(l -> startswith(l, NOTIFIER * " "), calls)

function rewrite(binary)
    rm(binary)
    cp(Sys.which("sleep"), binary)
    chmod(binary, 0o755)
end

@testset "julia-update.jl on $(LINUX ? "Linux" : "macOS")" begin
    @testset "a deleted server binary: the updates, then exactly one restart" begin
        fx = fixture()
        code, out, calls = with_server(rm, fx)
        @test code == 0
        @test "juliaup update" in calls
        update(c) = any(l -> startswith(l, "julia +$c ") && occursin("Pkg.update()", l), calls)
        @test update("1.12")
        @test update("1.13")
        @test !update("release") && !update("1.12.6")
        @test any(l -> occursin("--project=$(fx.harness)", l) && occursin("Pkg.update()", l), calls)
        @test restarts(calls) == 1
        @test others(calls) == 0
        @test occursin("RESTARTED", out)
        @test isempty(alerts(calls))
    end

    @testset "a server whose binary exists: no restart" begin
        fx = fixture()
        code, out, calls = with_server(identity, fx)
        @test code == 0
        @test restarts(calls) == 0 && others(calls) == 0
        @test occursin("No restart due", out)
        @test isempty(alerts(calls))
    end

    @testset "a binary deleted and written again at the same path: no restart" begin
        fx = fixture()
        code, out, calls = with_server(rewrite, fx)
        @test code == 0
        @test restarts(calls) == 0 && others(calls) == 0
        @test occursin("No restart due", out)
    end

    @testset "a restart due names this system's command" begin
        fx = fixture()
        code, out, calls = with_server(identity, fx, "STUB_BINDIR" => joinpath(fx.root, "other"))
        @test code == 0
        @test restarts(calls) == 0 && others(calls) == 0
        @test occursin("RESTART DUE", out)
        @test occursin("Run: $RESTART_HINT", out)
        @test length(alerts(calls)) == 1
    end

    @testset "no process listens: no restart" begin
        fx = fixture()
        code, out, calls = run_script(fx)
        @test code == 0
        @test restarts(calls) == 0 && others(calls) == 0
        @test occursin("No process listens", out)
    end

    @testset "the process ended before its binary was read: no restart, not a failure" begin
        fx = fixture()
        ended = run(`$(Sys.which("sleep")) 0`; wait = false)
        pid = getpid(ended)
        wait(ended)
        code, out, calls = run_script(fx, "STUB_PID" => string(pid))
        @test code == 0
        @test restarts(calls) == 0 && others(calls) == 0
        @test occursin("ended before", out)
        @test isempty(alerts(calls))
    end

    @testset "a failing step exits 1 and calls the notifier with this system's log" begin
        fx = fixture()
        code, out, calls = with_server(identity, fx, "STUB_FAIL" => "+1.12")
        @test code == 1
        @test occursin("FAILED: Pkg.update() in @v1.12", out)
        @test length(alerts(calls)) == 1
        @test occursin(LOG_HINT, only(alerts(calls)))
    end

    @testset "a missing lsof is a failure, never \"no server\"" begin
        fx = fixture()
        rm(joinpath(fx.stubs, "lsof"))
        code, out, calls = with_server(rm, fx)
        @test code == 1
        @test occursin("cannot read the server", out)
        @test !occursin("No process listens", out)
        @test restarts(calls) == 0 && others(calls) == 0
        @test length(alerts(calls)) == 1
    end

    @testset "a failing restart is a failure with its output in the log" begin
        fx = fixture()
        code, out, calls = with_server(rm, fx, "STUB_RESTART_FAILS" => "1")
        @test code == 1
        @test restarts(calls) == 1
        @test occursin("stub: no user manager", out)
        @test length(alerts(calls)) == 1
    end

    # Only macOS reads the binary with `ps`.
    LINUX || @testset "no ps on the PATH (macOS): a failure, never \"no server\"" begin
        fx = fixture()
        rm(joinpath(fx.stubs, "ps"))
        code, out, calls = with_server(rm, fx)
        @test code == 1
        @test occursin("cannot read the server, because no ps", out)
        @test restarts(calls) == 0 && others(calls) == 0
        @test length(alerts(calls)) == 1
        @test !occursin("Stacktrace", out)
    end

    @testset "no service manager on the PATH: a failure and an alert, no stack trace" begin
        fx = fixture()
        rm(joinpath(fx.stubs, LINUX ? "systemctl" : "launchctl"))
        code, out, calls = with_server(rm, fx)
        @test code == 1
        @test occursin("FAILED: cannot restart the server", out)
        @test length(alerts(calls)) == 1
        @test !occursin("Stacktrace", out)
    end

    @testset "no notifier on the PATH: the log line only, no error" begin
        fx = fixture()
        rm(joinpath(fx.stubs, NOTIFIER))
        code, out, calls = with_server(identity, fx, "STUB_FAIL" => "+1.12")
        @test code == 1
        @test occursin("No $NOTIFIER on the PATH", out)
        @test occursin("FAILED: Pkg.update() in @v1.12", out)
        @test !occursin("ERROR", out)
    end
end
