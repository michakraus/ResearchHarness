#!/usr/bin/env julia
#
# Checks for the shared pre-commit and pre-push hooks, on the system they run on. Run after any
# change to either launcher or either program:
#
#   julia --startup-file=no githooks/pre-commit-test.jl
#
# The hooks live byte-identical in every package repository, so this test never edits them: each
# case builds a fixture package repository under mktempdir(), stages files in it and runs a hook
# as it stands, from the fixture's root. The formatting stage loads JuliaFormatter from the
# harness environment, $RESEARCH_HARNESS_JULIA, as the hook does. HOME and the git identity are set
# in each subprocess, and git reads no global or system configuration.

using Test

const HOOK = joinpath(@__DIR__, "pre-commit")
const PROGRAM = joinpath(@__DIR__, "pre-commit.jl")
const PREPUSH = joinpath(@__DIR__, "pre-push")
const LAYOUT = joinpath(dirname(@__DIR__), "scripts", "test-layout.jl")

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

# Formatted and loads, with an `e` and a combining acute accent in a comment: NFD, not NFC.
const NOT_NFC = """
    module Fixture

    # café

    double(x) = 2x

    end
    """

# A test directory in the layout of the test convention.
const LAYOUT_FILES = [
    "test/Project.toml" => """
        [deps]
        Aqua = "4c88cf16-eb10-579e-8560-4a9242c79595"
        SafeTestsets = "1bc83da4-3b8d-516f-aca4-4fe02f6d838f"
        Test = "8dfed614-e22c-5e08-85e1-65c5234f0b40"
        """,
    "test/runtests.jl" => """
        using SafeTestsets

        const GROUPS = isempty(ARGS) ? ["core", "slow"] : ARGS

        if "core" in GROUPS
            @safetestset "Aqua" include("quality/aqua.jl")
            @safetestset "Double" include("integration/double.jl")
        end
        """,
    "test/quality/aqua.jl" => "using Aqua, Fixture\n\nAqua.test_all(Fixture)\n",
    "test/integration/double.jl" => "using Test, Fixture\n\n@test double(2) == 4\n",
]

const PROJECT = """
    name = "Fixture"
    uuid = "8c1f2a4e-6b0d-4f3a-9e57-2d8c4b1a0f61"
    version = "0.1.0"
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
A fixture package repository with `src/Fixture.jl` holding `source`, and the files of `extra`
(path => text). With `stage`, each file is staged. Returns the repository and its environment.
"""
function fixture(source; extra = Pair{String,String}[], project = PROJECT, stage = true)
    root = realpath(mktempdir())
    home = joinpath(root, "home")
    repo = joinpath(root, "Fixture")
    mkpath(home)
    mkpath(joinpath(repo, "src"))
    env = environment(home)
    run(setenv(`git init -q -b main $repo`, env))
    write(joinpath(repo, "Project.toml"), project)
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
    stage && run(setenv(`git -C $repo add $files`, env))
    return repo, env
end

"Run `cmd` in `repo` with `env` and `input` on stdin; return the exit code, stdout and stderr."
function capture(cmd, repo, env; input = "")
    out, err = IOBuffer(), IOBuffer()
    p = run(pipeline(ignorestatus(setenv(cmd, env; dir = repo)); stdin = IOBuffer(input),
                     stdout = out, stderr = err))
    return p.exitcode, String(take!(out)), String(take!(err))
end

"""
Run the pre-commit hook on a fixture made by `fixture(source; extra)`, with `path` as its `PATH`
where one is given. Returns the hook's exit code and its stdout and stderr in one string.
"""
function run_hook(source; extra = Pair{String,String}[], path = nothing)
    repo, env = fixture(source; extra)
    path === nothing || (env["PATH"] = path)
    code, out, err = capture(`bash $HOOK`, repo, env)
    return code, out * err
end

"A directory with one executable `name` that holds `script`."
function bindir(name, script)
    d = mktempdir()
    write(joinpath(d, name), script)
    chmod(joinpath(d, name), 0o755)
    return d
end

"The test's `PATH` with `Sys.BINDIR` first, minus each directory that holds a `name`."
without(name) = join(filter(d -> !isfile(joinpath(d, name)), [Sys.BINDIR; split(ENV["PATH"], ":")]), ":")

"Whether the process `pid` exists: `kill` with signal 0 sends nothing and checks."
alive(pid) = ccall(:kill, Cint, (Cint, Cint), pid, 0) == 0

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
        # The cause is kept, and the backtrace frames are dropped.
        @test occursin("undefined_name", out)
        @test !occursin(r"^\s*\[\d+\]\s"m, out)
    end

    # No .jl file staged: the hook ends early, on the test-layout stage's verdict.
    @testset "a commit that touches test/ without .githooks/test-layout.jl is refused" begin
        code, out = run_hook(nothing; extra = ["test/data.txt" => "data\n"])
        @test code == 1
        @test occursin("test-layout.jl is missing", out)
    end

    @testset "a commit that touches test/ out of the layout is refused" begin
        code, out = run_hook(nothing; extra = [".githooks/test-layout.jl" => read(LAYOUT, String),
                                               "test/data.txt" => "data\n"])
        @test code == 1
        @test occursin("test layout: FAILED", out)
        @test occursin("    Fixture: [D2] test/runtests.jl does not exist", out)
    end

    @testset "a commit that touches test/ in the layout passes" begin
        code, out = run_hook(FORMATTED;
                             extra = [".githooks/test-layout.jl" => read(LAYOUT, String);
                                      LAYOUT_FILES])
        @test code == 0
        @test occursin("test layout: ok", out)
    end

    @testset "a file that is not NFC is refused" begin
        code, out = run_hook(NOT_NFC)
        @test code == 1
        @test occursin("unicode: 1 file(s) not NFC", out)
        @test occursin("    src/Fixture.jl", out)
        @test occursin("formatting: ok", out)
    end

    @testset "a commit with no staged file passes with no stage" begin
        repo, env = fixture(FORMATTED; stage = false)
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test !occursin("formatting", out * err)
    end

    @testset "without julia on the PATH, the launcher refuses" begin
        repo, env = fixture(FORMATTED)
        env["PATH"] = without("julia")
        @test Sys.which("julia") !== nothing  # the test's own PATH has one
        code, out, err = capture(`$(Sys.which("bash")) $HOOK`, repo, env)
        @test code == 1
        @test err == "pre-commit: julia is not on the PATH.\n"
        @test out == ""
    end

    @testset "without fatou on the PATH, the lint stage is skipped with one line" begin
        code, out = run_hook(FORMATTED; path = without("fatou"))
        @test code == 0
        @test occursin("fatou lint: skipped — fatou is not on the PATH", out)
        @test count("fatou lint", out) == 1
    end

    @testset "fatou findings warn and do not block" begin
        fatou = bindir("fatou", "#!/bin/sh\necho 'src/Fixture.jl:1:1 one' >&2\necho 'src/Fixture.jl:2:1 two' >&2\nexit 1\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("fatou lint: 2 finding(s) — advisory, not blocking", out)
        @test occursin("    src/Fixture.jl:2:1 two", out)
    end

    @testset "fatou with no finding reports clean" begin
        fatou = bindir("fatou", "#!/bin/sh\nexit 0\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("fatou lint: clean", out)
    end

    # The wrapper comes before Sys.BINDIR and starts the real julia by its absolute path, so it
    # counts the starts by the name `julia` and not itself. A child that the program starts with
    # Base.julia_cmd(), and its precompile workers, start by an absolute path and are not counted.
    @testset "a commit of one .jl file starts julia once" begin
        count_file = joinpath(mktempdir(), "starts")
        wrapper = bindir("julia",
                         "#!/bin/sh\necho start >> '$count_file'\nexec '$(joinpath(Sys.BINDIR, "julia"))' \"\$@\"\n")
        code, out = run_hook(FORMATTED; path = wrapper * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("loads: ok", out)
        @test readlines(count_file) == ["start"]
    end
end

# The time box of the lint stage, called in this process: the program runs its stages only as a
# program file, so an include defines its functions and runs nothing.
@testset "the lint time box" begin
    hook = Module(:PreCommitProgram)
    Base.include(hook, PROGRAM)
    run_boxed(cmd, seconds) = Base.invokelatest(hook.run_boxed, cmd, seconds)

    @testset "the lint time box keeps the exit status and both streams" begin
        code, out = run_boxed(`sh -c 'echo out; echo err >&2; exit 3'`, 30)
        @test code == 3
        @test sort(split(chomp(out), '\n')) == ["err", "out"]
    end

    @testset "the lint time box stops a program that runs too long" begin
        t = @elapsed code, _ = run_boxed(`sleep 60`, 1)
        @test code === nothing
        @test t < 5
    end

    @testset "the lint time box kills a program that ignores the stop signal" begin
        t = @elapsed code, _ = run_boxed(`sh -c 'trap "" TERM; sleep 60 >/dev/null 2>&1 & wait'`, 1)
        @test code === nothing
        @test 5 <= t < 20
    end
end

@testset "pre-push" begin
    topic = "refs/heads/topic 1111111111111111111111111111111111111111 refs/heads/topic 0000000000000000000000000000000000000000\n"
    main = "refs/heads/main 1111111111111111111111111111111111111111 refs/heads/main 0000000000000000000000000000000000000000\n"

    # The suite fails unless it runs with the default bounds checks: Pkg.test passes
    # --check-bounds=yes to the test process unless julia_args says otherwise.
    passing = "Base.JLOptions().check_bounds == 0 || error(\"check-bounds is not auto\")\n"

    @testset "pre-push: a push of a topic branch skips the suite" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => "error(\"the suite ran\")\n"])
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = topic)
        @test code == 0
        @test occursin("not main/master — skipping the suite", out)
        @test !occursin("the suite ran", out * err)
    end

    @testset "pre-push: a push to main with a passing suite passes" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing])
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = topic * main)
        @test code == 0
        @test occursin("running the full suite for Fixture", out)
        @test occursin("Suite passed.", out)
    end

    @testset "pre-push: a push to master with a passing suite passes" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing])
        code, out, _ = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                               input = replace(main, "main" => "master"))
        @test code == 0
        @test occursin("Suite passed.", out)
    end

    @testset "pre-push: a push to main with a failing suite is refused" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => "error(\"the suite failed\")\n"])
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = main)
        @test code == 1
        @test occursin("tests must pass before pushing to main", out)
        @test occursin("the suite failed", out * err)
    end

    @testset "pre-push: a repository without a name runs test/runtests.jl" begin
        repo, env = fixture(nothing; project = "[deps]\n",
                            extra = ["test/runtests.jl" => "println(\"runtests ran\"); " * passing])
        code, out, _ = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                               input = main)
        @test code == 0
        @test occursin("running the full suite for Fixture", out)
        @test occursin("runtests ran", out)
        @test occursin("Suite passed.", out)
    end

    @testset "pre-push: a repository without a name or a test/runtests.jl runs nothing" begin
        repo, env = fixture(nothing; project = "[deps]\n")
        code, out, _ = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                               input = main)
        @test code == 0
        @test occursin("no package name and no test/runtests.jl — nothing to run.", out)
    end

    @testset "without julia on the PATH, the pre-push launcher refuses" begin
        repo, env = fixture(FORMATTED)
        env["PATH"] = without("julia")
        code, out, err = capture(`$(Sys.which("bash")) $PREPUSH origin x`, repo, env; input = main)
        @test code == 1
        @test err == "pre-push: julia is not on the PATH.\n"
        @test out == ""
    end

    # The suite writes its process id and waits; the test interrupts the hook. The hook passes
    # the interrupt on and waits, so the suite has ended when the hook has.
    @testset "pre-push: an interrupted hook stops its suite" begin
        repo, env = fixture(nothing; project = "[deps]\n",
                            extra = ["test/runtests.jl" => "write(\"suite.pid\", string(getpid())); sleep(120)\n"])
        pidfile = joinpath(repo, "suite.pid")
        p = run(pipeline(ignorestatus(setenv(`bash $PREPUSH origin x`, env; dir = repo));
                         stdin = IOBuffer(main), stdout = devnull, stderr = devnull); wait = false)
        deadline = time() + 120
        while !(isfile(pidfile) && !isempty(read(pidfile, String))) && time() < deadline &&
                  process_running(p)
            sleep(0.2)
        end
        @test isfile(pidfile)
        suite = parse(Int, read(pidfile, String))
        kill(p, Base.SIGINT)
        wait(p)
        @test p.exitcode == 130
        @test !alive(suite)
        alive(suite) && ccall(:kill, Cint, (Cint, Cint), suite, 9)
    end
end
