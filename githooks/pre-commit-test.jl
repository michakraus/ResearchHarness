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

    # caf$('e' * Char(0x301))

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

# Formatted and loads; `CLEAN` has no ast-grep hit, and `PROBE` holds `@show x` on line 4, a hit
# of the rule `debug-probe`.
const CLEAN = """
    module Fixture

    function double(x)
        return 2x
    end

    end
    """

const PROBE = """
    module Fixture

    function double(x)
        @show x
        return 2x
    end

    end
    """

# The ast-grep rules of the tree under test, and the parser that ast-grep/build-julia.sh builds:
# beside the rules where CI builds it, else in the Harness checkout of the research tree.
const RULES = joinpath(dirname(@__DIR__), "ast-grep", "rules")
const PARSER = let built = joinpath(dirname(@__DIR__), "ast-grep", "julia.dylib")
    isfile(built) ? built :
    joinpath(get(ENV, "RESEARCH_ROOT", joinpath(homedir(), "Research")), "Harness", "ast-grep",
             "julia.dylib")
end

# A fixture lies under mktempdir(), where no sgconfig.yml of the research tree is above it, so a
# fixture that the ast-grep stage checks holds this one at its root, with absolute paths.
const SGCONFIG = "sgconfig.yml" => """
    ruleDirs: [$(repr(RULES))]
    customLanguages:
      julia:
        libraryPath: $(repr(PARSER))
        extensions: [jl]
        expandoChar: µ
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
A fixture package repository with `src/Fixture.jl` holding `source`, `Project.toml` holding
`project` unless that is `nothing`, and the files of `extra` (path => text). With `stage`, each
file is staged. Returns the repository and its environment.
"""
function fixture(source; extra = Pair{String,String}[], project = PROJECT, stage = true)
    root = realpath(mktempdir())
    home = joinpath(root, "home")
    repo = joinpath(root, "Fixture")
    mkpath(home)
    mkpath(joinpath(repo, "src"))
    env = environment(home)
    run(setenv(`git init -q -b main $repo`, env))
    write(joinpath(repo, ".JuliaFormatter.toml"), "style = \"sciml\"\n")
    files = [".JuliaFormatter.toml"]
    if project !== nothing
        write(joinpath(repo, "Project.toml"), project)
        push!(files, "Project.toml")
    end
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
Run the pre-commit hook on a fixture made by `fixture(source; extra, project)`, with `path` as its
`PATH` where one is given, and the variables of `vars` set. Returns the hook's exit code and its
stdout and stderr in one string.
"""
function run_hook(source; extra = Pair{String,String}[], path = nothing, project = PROJECT,
                  vars = Dict{String,String}())
    repo, env = fixture(source; extra, project)
    path === nothing || (env["PATH"] = path)
    merge!(env, vars)
    code, out, err = capture(`bash $HOOK`, repo, env)
    return code, out * err
end

"""
Run the pre-commit hook on the second commit of a fixture: the first commit holds
`src/Fixture.jl` with `before` and the files of `extra`, and the second stages `src/Fixture.jl`
with `after`. Returns the hook's exit code and its stdout and stderr in one string.
"""
function second_commit(before, after; extra = [SGCONFIG])
    repo, env = fixture(before; extra)
    run(setenv(`git -C $repo commit -q -m base`, env))
    write(joinpath(repo, "src", "Fixture.jl"), after)
    run(setenv(`git -C $repo add src/Fixture.jl`, env))
    code, out, err = capture(`bash $HOOK`, repo, env)
    return code, out * err
end

"""
A fixture whose staged change adds the lines 4 and 8 of `src/Fixture.jl`, around an old `@show x`
on line 6 that the first commit holds. Returns the repository and its environment.
"""
function two_hunks()
    before = replace(CLEAN, "    return" => "    a = 1\n    @show x\n    b = 2\n    return")
    after = replace(before, "    a = 1\n" => "    c = 3\n    a = 1\n",
                    "    b = 2\n" => "    b = 2\n    d = 4\n")
    repo, env = fixture(before; extra = [SGCONFIG])
    run(setenv(`git -C $repo commit -q -m base`, env))
    write(joinpath(repo, "src", "Fixture.jl"), after)
    run(setenv(`git -C $repo add src/Fixture.jl`, env))
    return repo, env
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

"A parse error whose `showerror` is its message, for the cases of the `headline` rule."
struct ParseError <: Exception
    msg::String
end
Base.showerror(io::IO, e::ParseError) = print(io, e.msg)

"""
The cases of the `headline` rule, the same in both programs, for the function `headline` of one
of them.
"""
function headline_cases(headline)
    wide = try
        Meta.parse("a bcdef"; filename = "a.jl")
    catch e
        e
    end
    @test headline(wide) == "ParseError: — # Error @ a.jl:1:2 — extra tokens after end of expression"
    @test headline(ErrorException("one\ntwo\nthree")) == "one — two"
    @test headline(ParseError("P:\n# @ 1\n# └ ── first\n# @ 2\n# └ ── a ── b")) == "P: — # @ 1 — a ── b"
    @test headline(ParseError("P:\n# └ ── x")) == "P: — # └ ── x"
    @test headline(ErrorException("P:\n# @ 1\n# └ ── x")) == "P: — # @ 1"
end

"Whether the process `pid` exists: `kill` with signal 0 sends nothing and checks."
alive(pid) = ccall(:kill, Cint, (Cint, Cint), pid, 0) == 0

"""
Start a julia process that includes pre-push.jl and calls its `run_suite` on `sh -c suite`, with
the keywords of `kwargs` (source text), with interrupts caught as the hook's `main` catches them.
The script goes into `dir`, and the process's stdout goes to `out` and its stderr to `err`.
Returns the process.
"""
function suite_driver(suite, dir; kwargs = "", out = devnull, err = devnull)
    script = joinpath(dir, "driver.jl")
    write(script, """
        include($(repr(joinpath(@__DIR__, "pre-push.jl"))))
        Base.exit_on_sigint(false)
        run_suite(`sh -c \$(ARGS[1])`$kwargs)
        """)
    return run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $script $suite`);
                        stdout = out, stderr = err); wait = false)
end

# One testset holds the four below, so a failure in one of them does not stop the file before
# the others run: the outer one reports every failure, and throws, at the end of the file. The
# four keep the indentation of top-level testsets. `verbose` lists the testsets inside a testset
# in the summary, one level deep, so a log of a passing run names each testset of pre-commit.jl.
@testset "the hooks" verbose = true begin
@testset "pre-commit" verbose = true begin
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
        @test !occursin("WARNING", out)
    end

    # harness githooks copies the programs into each package's .githooks/, and the package then
    # commits them through this hook, under its own style = "sciml".
    @testset "a commit of the installed programs passes the formatting stage" begin
        code, out = run_hook(nothing; project = nothing,
                             extra = [".githooks/pre-commit.jl" => read(PROGRAM, String),
                                      ".githooks/pre-push.jl" => read(joinpath(@__DIR__, "pre-push.jl"), String),
                                      ".githooks/test-layout.jl" => read(LAYOUT, String)])
        @test occursin("formatting: ok", out)
        @test code == 0
    end

    @testset "a file that is not NFC is refused" begin
        code, out = run_hook(NOT_NFC)
        @test code == 1
        @test occursin("unicode: 1 file(s) not NFC", out)
        @test occursin("    src/Fixture.jl", out)
        @test occursin("formatting: ok", out)
    end

    @testset "a test-layout.jl that throws is refused" begin
        code, out = run_hook(nothing;
                             extra = [".githooks/test-layout.jl" => "violations(repo) = error(\"broken script\")\n",
                                      "test/data.txt" => "data\n"])
        @test code == 1
        @test occursin("test layout: FAILED", out)
        @test occursin("broken script", out)
    end

    @testset "without JuliaFormatter, the formatting stage refuses" begin
        code, out = run_hook(FORMATTED;
                             vars = Dict("RESEARCH_HARNESS_JULIA" => mktempdir(),
                                         "JULIA_LOAD_PATH" => "@stdlib"))
        @test code == 1
        @test occursin("JuliaFormatter is in no environment of the load path", out)
        @test occursin("formatting: FAILED", out)
    end

    # A stub of an older release that reports every file formatted and takes any keyword, so
    # only the version check can refuse it.
    @testset "a JuliaFormatter older than 2.14 is refused, naming its version" begin
        root = mktempdir()
        uuid = "98e50ef6-434e-11e9-1051-2b60c6c9e899"
        pkg = joinpath(root, "JuliaFormatter")
        mkpath(joinpath(pkg, "src"))
        write(joinpath(pkg, "Project.toml"),
              "name = \"JuliaFormatter\"\nuuid = \"$uuid\"\nversion = \"2.4.0\"\n")
        write(joinpath(pkg, "src", "JuliaFormatter.jl"),
              "module JuliaFormatter\nformat(f; kw...) = true\nend\n")
        env = joinpath(root, "env")
        mkpath(env)
        write(joinpath(env, "Project.toml"), "[deps]\nJuliaFormatter = \"$uuid\"\n")
        write(joinpath(env, "Manifest.toml"),
              "manifest_format = \"2.0\"\n\n[[deps.JuliaFormatter]]\npath = \"$pkg\"\n" *
              "uuid = \"$uuid\"\nversion = \"2.4.0\"\n")
        code, out = run_hook(FORMATTED;
                             vars = Dict("RESEARCH_HARNESS_JULIA" => env,
                                         "JULIA_LOAD_PATH" => "@stdlib"))
        @test code == 1
        @test occursin("JuliaFormatter 2.4.0 is older than 2.14", out)
        @test occursin("formatting: FAILED", out)
    end

    @testset "a file that is not valid UTF-8 is no NFC finding" begin
        code, out = run_hook("module Fixture\n# \xff\nend\n")
        @test occursin("unicode: NFC", out)
    end

    @testset "a repository without Project.toml has no load test" begin
        code, out = run_hook(FORMATTED; project = nothing)
        @test code == 0
        @test occursin("unicode: NFC", out)
        @test !occursin("loads:", out)
    end

    @testset "the load failure shows its first 20 lines" begin
        code, out = run_hook("""
            module Fixture

            foreach(i -> println(stderr, "load line ", i), 1:30)

            const VALUE = undefined_name + 1

            end
            """)
        @test code == 1
        @test !occursin("load line 30", out)
    end

    # The load prints 25 lines before its error, so the first 20 lines of its output hold no error.
    @testset "a failed load report starts at its ERROR: line" begin
        code, out = run_hook("""
            module Fixture

            foreach(i -> println(stderr, "load line ", i), 1:25)

            const VALUE = undefined_name + 1

            end
            """)
        @test code == 1
        @test occursin(r"^    ERROR: .*undefined_name"m, out)
        # `__init__` runs at the load, not at the precompilation, and ends it with no ERROR: line,
        # so the report starts at the first line and shows 20.
        code, out = run_hook("""
            module Fixture

            function __init__()
                foreach(i -> println(stderr, "init line ", i), 1:30)
                exit(3)
            end

            end
            """)
        @test code == 1
        @test occursin("loads: FAILED", out)
        @test occursin("    init line 1\n", out)
        @test occursin("    init line 20\n", out)
        @test !occursin("init line 21", out)
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

    @testset "without julia on the PATH, a commit with no .jl file and no test/ path passes" begin
        repo, env = fixture(nothing; extra = ["README.md" => "# Fixture\n"])
        env["PATH"] = without("julia")
        code, out, err = capture(`$(Sys.which("bash")) $HOOK`, repo, env)
        @test code == 0
        @test out * err == ""
    end

    @testset "without julia on the PATH, a commit that touches test/ is refused" begin
        repo, env = fixture(nothing; extra = ["test/data.txt" => "1\n"])
        env["PATH"] = without("julia")
        code, _, err = capture(`$(Sys.which("bash")) $HOOK`, repo, env)
        @test code == 1
        @test err == "pre-commit: julia is not on the PATH.\n"
    end

    @testset "without julia on the PATH, a .jl file that becomes a symlink is refused" begin
        repo, env = fixture(FORMATTED; extra = ["README.md" => "# Fixture\n"])
        run(setenv(`git -C $repo commit -q -m base`, env))
        rm(joinpath(repo, "src", "Fixture.jl"))
        symlink("../README.md", joinpath(repo, "src", "Fixture.jl"))
        run(setenv(`git -C $repo add src/Fixture.jl`, env))
        env["PATH"] = without("julia")
        code, _, err = capture(`$(Sys.which("bash")) $HOOK`, repo, env)
        @test code == 1
        @test err == "pre-commit: julia is not on the PATH.\n"
    end

    @testset "a renamed .jl file is checked under its new name" begin
        repo, env = fixture(MISFORMATTED)
        run(setenv(`git -C $repo commit -q -m base`, env))
        run(setenv(`git -C $repo mv src/Fixture.jl src/Moved.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin("src/Moved.jl", out * err)
    end

    @testset "a staged .jl file with a non-ASCII name is checked under that name" begin
        code, out = run_hook(FORMATTED; extra = ["src/Größe.jl" => "size2(x) = 2x\n"])
        @test code == 0
        @test occursin("formatting: ok", out)
        @test !occursin("\\303", out)
    end

    @testset "a staged .jl file that does not parse fails the formatting stage" begin
        code, out = run_hook(FORMATTED; extra = ["scripts/broken.jl" => "function f(x\n    x +\nend\n"])
        @test code == 1
        @test occursin("scripts/broken.jl", out)
    end

    @testset "without fatou on the PATH, the lint stage is skipped with one line" begin
        code, out = run_hook(FORMATTED; path = without("fatou"))
        @test code == 0
        @test occursin("fatou lint: skipped — fatou is not on the PATH", out)
        @test count("fatou lint", out) == 1
    end

    @testset "fatou findings warn and do not block" begin
        fatou = bindir("fatou", "#!/bin/sh\necho 'src/Fixture.jl:1:1: warning[w] one' >&2\necho 'src/Fixture.jl:2:1: warning[w] two' >&2\nexit 1\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("fatou lint: 2 finding(s) — advisory, not blocking", out)
        @test occursin("    src/Fixture.jl:2:1: warning[w] two", out)
    end

    @testset "fatou with no finding reports clean" begin
        fatou = bindir("fatou", "#!/bin/sh\nexit 0\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("fatou lint: clean", out)
    end

    # The stub writes each of its arguments on a line of its own.
    @testset "the staged paths reach fatou after --" begin
        args = joinpath(mktempdir(), "args")
        fatou = bindir("fatou", "#!/bin/sh\nprintf '%s\\n' \"\$@\" > '$args'\nexit 0\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test readlines(args) == ["lint", "--force-exclude", "--output", "concise", "--", "src/Fixture.jl"]
    end

    # fatou exits 2 for an unknown option, and prints no line of the form <path>:<line>:<col>: .
    @testset "a fatou error is reported as a failure of fatou, not as findings" begin
        fatou = bindir("fatou", "#!/bin/sh\necho 'error: unexpected argument' >&2\nexit 2\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("fatou lint: fatou failed with exit status 2 — stage skipped, not a failure", out)
        @test occursin("    error: unexpected argument", out)
        @test !occursin("finding(s)", out)
        @test occursin("loads: ok", out)
        # A location without the `: ` after its column is no finding either.
        fatou = bindir("fatou", "#!/bin/sh\necho 'src/Fixture.jl:1:1 one' >&2\nexit 1\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("fatou lint: fatou failed with exit status 1 — stage skipped, not a failure", out)
    end

    # No other fatou on the PATH: execvp would start the next one when this one cannot start.
    @testset "a fatou that cannot start skips the lint stage, and the later stages run" begin
        fatou = bindir("fatou", "#!/nonexistent/interpreter\n")
        code, out = run_hook(FORMATTED; path = fatou * ":" * without("fatou"))
        @test code == 0
        @test occursin("fatou lint: could not start — stage skipped, not a failure", out)
        @test occursin("loads: ok", out)
    end

    @testset "a new file with an ast-grep hit is refused" begin
        code, out = run_hook(PROBE; extra = [SGCONFIG])
        @test code == 1
        @test occursin("ast-grep: FAILED", out)
        @test occursin("    src/Fixture.jl:4: debug-probe: a debug probe", out)
        @test occursin("formatting: ok", out)
        @test occursin("loads: ok", out)
    end

    @testset "a line that adds a hit is refused" begin
        code, out = second_commit(CLEAN, PROBE)
        @test code == 1
        @test occursin("ast-grep: FAILED", out)
        @test occursin("    src/Fixture.jl:4: debug-probe: ", out)
    end

    @testset "a hit on a line the commit does not add warns" begin
        code, out = second_commit(PROBE, replace(PROBE, r"end\n$" => "triple(x) = 3x\n\nend\n"))
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out)
        @test occursin("    src/Fixture.jl:4: debug-probe: ", out)
        @test !occursin("ast-grep: FAILED", out)
    end

    # The commit adds lines 4 to 6, and the hit is on line 6.
    @testset "a hit on the last line of a hunk is refused" begin
        code, out = second_commit(CLEAN, replace(CLEAN, "    return" => "    y = x\n    z = y\n    @show z\n    return"))
        @test code == 1
        @test occursin("ast-grep: FAILED", out)
        @test occursin("    src/Fixture.jl:6: debug-probe: ", out)
    end

    # The hit spans lines 4 to 6, and the commit changes line 5 only.
    @testset "a hit whose range holds an added line is refused" begin
        wide = replace(CLEAN, "    return" => "    @show begin\n        x\n    end\n    return")
        code, out = second_commit(wide, replace(wide, "        x\n" => "        2x\n"))
        @test code == 1
        @test occursin("    src/Fixture.jl:4: debug-probe: ", out)
    end

    # The hunk of a deletion, `+c,0`, adds no line, and its `c` is the line of the old hit.
    @testset "a commit that deletes the line below an old hit passes" begin
        before = replace(PROBE, "    return" => "    y = x\n    return")
        code, out = second_commit(before, PROBE)
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out)
    end

    # Each setting makes `git diff` print no hunk header for the file, or other lines than the
    # staged ones, so a new hit would read as advisory.
    @testset "a diff.external, a textconv driver or a -diff attribute does not hide an added hit" begin
        conv = bindir("conv", "#!/bin/sh\necho converted\n")
        external = bindir("external", "#!/bin/sh\necho changed\n")
        for (config, attributes) in ((["diff.external", joinpath(external, "external")], nothing),
                                     (["diff.jl.textconv", joinpath(conv, "conv")], "*.jl diff=jl\n"),
                                     (nothing, "*.jl -diff\n"))
            extra = attributes === nothing ? [SGCONFIG] : [SGCONFIG, ".gitattributes" => attributes]
            repo, env = fixture(PROBE; extra)
            config === nothing || run(setenv(`git -C $repo config $config`, env))
            code, out, err = capture(`bash $HOOK`, repo, env)
            @test code == 1
            @test occursin("ast-grep: FAILED", out * err)
            @test occursin("    src/Fixture.jl:4: debug-probe: ", out * err)
        end
    end

    # The commit adds lines 4 and 8; the old hit lies on line 6, between the two hunks.
    @testset "diff.interHunkContext does not join two hunks around an old hit" begin
        before = replace(CLEAN, "    return" => "    a = 1\n    @show x\n    b = 2\n    return")
        after = replace(before, "    a = 1\n" => "    c = 3\n    a = 1\n",
                        "    b = 2\n" => "    b = 2\n    d = 4\n")
        repo, env = fixture(before; extra = [SGCONFIG])
        run(setenv(`git -C $repo config diff.interHunkContext 5`, env))
        run(setenv(`git -C $repo commit -q -m base`, env))
        write(joinpath(repo, "src", "Fixture.jl"), after)
        run(setenv(`git -C $repo add src/Fixture.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out * err)
        @test occursin("    src/Fixture.jl:6: debug-probe: ", out * err)
    end

    # The variable sets the context of every hunk, which -U0 alone does not override.
    @testset "GIT_DIFF_OPTS does not join two hunks around an old hit" begin
        repo, env = two_hunks()
        env["GIT_DIFF_OPTS"] = "--unified=3"
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out * err)
        @test occursin("    src/Fixture.jl:6: debug-probe: ", out * err)
        @test !occursin("ast-grep: FAILED", out * err)
    end

    # git refuses --literal-pathspecs beside any other global pathspec setting.
    @testset "GIT_ICASE_PATHSPECS does not stop the stage" begin
        repo, env = two_hunks()
        env["GIT_ICASE_PATHSPECS"] = "1"
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out * err)
        @test occursin("    src/Fixture.jl:6: debug-probe: ", out * err)
        @test !occursin("ProcessFailedException", out * err)
    end

    # As a glob, the path src/a[b].jl also matches src/ab.jl, whose second line the commit adds.
    @testset "the added lines of a path with glob characters are its own" begin
        old = "function f(x)\n    @show x\n    return x\nend\n"
        repo, env = fixture(CLEAN; extra = [SGCONFIG, "src/a[b].jl" => old, "src/ab.jl" => "g(x) = x\n"])
        run(setenv(`git -C $repo commit -q -m base`, env))
        write(joinpath(repo, "src", "a[b].jl"), old * "\nh(x) = x\n")
        write(joinpath(repo, "src", "ab.jl"), "y = 1\nz = 2\ng(x) = x\n")
        run(setenv(`git -C $repo add -- src/a\[b\].jl src/ab.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out * err)
        @test occursin("    src/a[b].jl:2: debug-probe: ", out * err)
    end

    # tree-sitter-julia marks the adjoint of a float literal with an exponent ERROR, which the rule
    # `parse-error` reports at severity info; Julia parses it.
    @testset "a parse-error hit is not printed" begin
        source = "module Fixture\n\nconst SCALE = 1e-3'\n\nend\n"
        repo, env = fixture(source; extra = [SGCONFIG])
        # `read` gives the scan no stdin: ast-grep ends at once, and a write to its stdin, as
        # `capture` makes, can then fail with a broken pipe.
        scan = read(ignorestatus(setenv(`ast-grep scan --custom-languages allow --json=stream -- src/Fixture.jl`, env; dir = repo)), String)
        @test occursin("\"ruleId\":\"parse-error\"", scan)
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("ast-grep: clean", out * err)
        @test !occursin("parse-error", out * err)
        @test occursin("loads: ok", out * err)
    end

    # A rule with no `severity` key gives hits of severity hint.
    @testset "a hit of severity warning or hint is advisory on any line" begin
        rules = ["fixture-rules/warning.yml" => """
                     id: fixture-warning
                     language: julia
                     severity: warning
                     message: a warn_me call
                     rule:
                       pattern: warn_me(\$A)
                     """,
                 "fixture-rules/hint.yml" => """
                     id: fixture-hint
                     language: julia
                     message: a hint_me call
                     rule:
                       pattern: hint_me(\$A)
                     """]
        config = "sgconfig.yml" => replace(last(SGCONFIG), "ruleDirs: [$(repr(RULES))]" =>
                                                               "ruleDirs: [$(repr(RULES)), fixture-rules]")
        source = replace(CLEAN, "    return" => "    warn_me(x)\n    hint_me(x)\n    return")
        code, out = run_hook(source; extra = [config; rules])
        @test code == 0
        @test occursin("ast-grep: 2 hit(s) of severity warning or hint — advisory", out)
        @test occursin("    src/Fixture.jl:4: fixture-warning: a warn_me call", out)
        @test occursin("    src/Fixture.jl:5: fixture-hint: a hint_me call", out)
        @test !occursin("ast-grep: FAILED", out)
        @test !occursin("ast-grep: clean", out)
    end

    @testset "a silenced hit passes" begin
        for silenced in ("    @show x  # ast-grep-ignore: debug-probe",
                         "    # ast-grep-ignore: debug-probe\n    @show x")
            code, out = run_hook(replace(PROBE, "    @show x" => silenced); extra = [SGCONFIG])
            @test code == 0
            @test occursin("ast-grep: clean", out)
        end
    end

    @testset "without ast-grep on the PATH, the stage is skipped with one line" begin
        code, out = run_hook(CLEAN; extra = [SGCONFIG], path = without("ast-grep"))
        @test code == 0
        @test count("ast-grep: skipped — ast-grep is not on the PATH", out) == 1
        @test count(l -> occursin("ast-grep", l), split(out, '\n')) == 1
    end

    @testset "an ast-grep that fails is skipped with its exit code" begin
        stub = bindir("ast-grep", "#!/bin/sh\necho boom >&2\nexit 2\n")
        code, out = run_hook(CLEAN; extra = [SGCONFIG], path = stub * ":" * Sys.BINDIR * ":" * ENV["PATH"])
        @test code == 0
        @test occursin("ast-grep: skipped — ast-grep exited with status 2: boom", out)
        @test count("ast-grep:", out) == 1
    end

    # ast-grep looks for sgconfig.yml in each parent directory, so one above the fixture would
    # answer in its place.
    @testset "without an sgconfig.yml, the stage is skipped with one line" begin
        repo, env = fixture(PROBE)
        dirs = [repo]
        while dirname(last(dirs)) != last(dirs)
            push!(dirs, dirname(last(dirs)))
        end
        @test !any(d -> isfile(joinpath(d, "sgconfig.yml")), dirs)
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test count("ast-grep: skipped — ", out * err) == 1
        @test occursin("ast-grep: skipped — no sgconfig.yml", out * err)
    end

    # With diff.renames off, only the stage's own -M finds the rename. The file with the hit is
    # not the package's module file, so the load test passes.
    @testset "a renamed file with an old hit passes" begin
        repo, env = fixture(CLEAN; extra = [SGCONFIG, "src/probe.jl" => "function probe(x)\n    @show x\n    return x\nend\n"])
        run(setenv(`git -C $repo config diff.renames false`, env))
        run(setenv(`git -C $repo commit -q -m base`, env))
        run(setenv(`git -C $repo mv src/probe.jl src/moved.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("ast-grep: 1 hit(s) on lines this commit does not add — advisory", out * err)
        @test occursin("    src/moved.jl:2: debug-probe: ", out * err)
    end

    # git lists the changed file and the renamed one by status; only the rename has an old path.
    @testset "a renamed file beside a changed file passes" begin
        repo, env = fixture(CLEAN; extra = [SGCONFIG, "src/probe.jl" => "function probe(x)\n    @show x\n    return x\nend\n"])
        run(setenv(`git -C $repo commit -q -m base`, env))
        write(joinpath(repo, "src", "Fixture.jl"), replace(CLEAN, r"end\n$" => "triple(x) = 3x\n\nend\n"))
        run(setenv(`git -C $repo add src/Fixture.jl`, env))
        run(setenv(`git -C $repo mv src/probe.jl src/moved.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test occursin("    src/moved.jl:2: debug-probe: ", out * err)
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

    @testset "a formatted file beside one that does not parse: only the unparsable one is listed" begin
        repo, env = fixture(FORMATTED; extra = ["scripts/broken.jl" => "function f(x\n    x +\nend\n"])
        code, _, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin("not formatted:\nscripts/broken.jl\n", err)
        @test !occursin("src/Fixture.jl", err)
        @test occursin(r"^scripts/broken.jl: \S"m, err)
    end

    @testset "a file that does not parse is listed with the error's location" begin
        repo, env = fixture(FORMATTED; extra = ["scripts/broken.jl" => "function f(x\n    x +\nend\n"])
        code, _, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin(r"^scripts/broken.jl: .*# Error @ line \d+:\d+"m, err)
    end

    # JuliaSyntax prints the reason after `──` on a line below the location.
    @testset "a file that does not parse is refused with the parser's reason" begin
        repo, env = fixture(FORMATTED; extra = ["scripts/broken.jl" => "function f(x\n    x +\nend\n"])
        code, _, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin(r"^scripts/broken.jl: .*# Error @ line \d+:\d+ — Expected `\)` or `,`$"m, err)
    end

    @testset "a staged .jl symlink to a missing file is refused with one line" begin
        repo, env = fixture(FORMATTED)
        symlink("missing.jl", joinpath(repo, "src", "Link.jl"))
        run(setenv(`git -C $repo add src/Link.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test count(l -> occursin("src/Link.jl", l), split(out * err, '\n')) == 1
        @test occursin("src/Link.jl is not a file", out * err)
        @test !occursin("Stacktrace", out * err)
        @test !occursin("formatting", out * err)
    end

    @testset "a staged .jl symlink to a directory is refused with one line" begin
        repo, env = fixture(FORMATTED)
        mkpath(joinpath(repo, "docs"))
        symlink("../docs", joinpath(repo, "src", "Dir.jl"))
        run(setenv(`git -C $repo add src/Dir.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test count(l -> occursin("src/Dir.jl", l), split(out * err, '\n')) == 1
        @test occursin("src/Dir.jl is not a file", out * err)
        @test !occursin("Stacktrace", out * err)
    end

    # The stages read the files on disk, so a file with an unstaged edit is refused before any
    # stage runs.
    @testset "a partly staged .jl file is refused with its name" begin
        repo, env = fixture(FORMATTED)
        write(joinpath(repo, "src", "Fixture.jl"), MISFORMATTED)
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin("pre-commit: src/Fixture.jl has changes that are not staged", out * err)
        @test occursin("Stage the rest of", out * err)
        @test !occursin("formatting", out * err)
    end

    @testset "a fully staged change of a .jl file passes" begin
        code, out = second_commit(FORMATTED, replace(FORMATTED, r"end\n$" => "triple(x) = 3x\n\nend\n"); extra = [])
        @test code == 0
        @test !occursin("not staged", out)
        @test occursin("loads: ok", out)
    end

    @testset "an unstaged change of another .jl file passes" begin
        repo, env = fixture(FORMATTED; extra = ["src/other.jl" => "f(x) = x\n"])
        run(setenv(`git -C $repo commit -q -m base`, env))
        write(joinpath(repo, "src", "Fixture.jl"), replace(FORMATTED, r"end\n$" => "triple(x) = 3x\n\nend\n"))
        run(setenv(`git -C $repo add src/Fixture.jl`, env))
        write(joinpath(repo, "src", "other.jl"), "f(x) = 2x\n")
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test !occursin("not staged", out * err)
    end

    # As a glob, the path src/a[b].jl also matches src/ab.jl, which has an unstaged change.
    @testset "a fully staged path with glob characters passes beside an unstaged path it matches as a glob" begin
        repo, env = fixture(FORMATTED; extra = ["src/a[b].jl" => "f(x) = x\n", "src/ab.jl" => "g(x) = x\n"])
        run(setenv(`git -C $repo commit -q -m base`, env))
        write(joinpath(repo, "src", "a[b].jl"), "f(x) = 2x\n")
        run(setenv(`git -C $repo add -- src/a\[b\].jl`, env))
        write(joinpath(repo, "src", "ab.jl"), "g(x) = 2x\n")
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 0
        @test !occursin("not staged", out * err)
    end

    # Under the variable, `*.jl` lists the staged files of the root only, so the file is there.
    @testset "GIT_GLOB_PATHSPECS does not stop the refusal of a partly staged file" begin
        repo, env = fixture(FORMATTED; extra = ["top.jl" => "t(x) = x\n"])
        write(joinpath(repo, "top.jl"), "t(x) = 2x\n")
        env["GIT_GLOB_PATHSPECS"] = "1"
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin("pre-commit: top.jl has changes that are not staged", out * err)
    end

    @testset "an indented, single-quoted name runs the load test" begin
        code, out = run_hook(FORMATTED; project = replace(PROJECT, "name = \"Fixture\"" => "  name = 'Fixture'"))
        @test code == 0
        @test occursin("loads: ok", out)
    end

    @testset "a Project.toml that does not parse is refused" begin
        code, out = run_hook(FORMATTED; project = replace(PROJECT, "\"Fixture\"" => "\"Fixture"))
        @test code == 1
        @test count(l -> occursin("Project.toml", l), split(out, '\n')) == 1
        @test occursin("Project.toml: does not parse", out)
        @test !occursin("Stacktrace", out)
    end

    # TOML.parsefile names the file: <path>:<line>:<col> error: …, where the column can be -1.
    @testset "a Project.toml that does not parse is refused with the error's location" begin
        code, out = run_hook(FORMATTED; project = replace(PROJECT, "\"Fixture\"" => "\"Fixture"))
        @test code == 1
        @test occursin(r"Project\.toml:\d+:-?\d+ error: ", out)
    end

    # Put into `using <name>`, the first name writes `ran` and loads. The second is no string.
    @testset "a package name that is not an identifier is refused" begin
        repo, env = fixture(FORMATTED;
                            project = replace(PROJECT, "name = \"Fixture\"" => "name = 'Base; write(\"ran\", \"1\")'"))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test !isfile(joinpath(repo, "ran"))
        @test occursin("is not a Julia identifier", out)
        @test count(l -> occursin("Project.toml", l), split(out * err, '\n')) == 1
        @test !occursin("loads:", out)
        code, out = run_hook(FORMATTED; project = replace(PROJECT, "name = \"Fixture\"" => "name = 1"))
        @test code == 1
        @test occursin("is not a Julia identifier", out)
        @test !occursin("loads:", out)
    end

    # Base.isidentifier accepts `end`; the parser does not read it as a name.
    @testset "a package name that is a keyword is refused" begin
        code, out = run_hook(FORMATTED; project = replace(PROJECT, "name = \"Fixture\"" => "name = \"end\""))
        @test code == 1
        @test occursin("is not a Julia identifier", out)
        @test count(l -> occursin("Project.toml", l), split(out, '\n')) == 1
        @test !occursin("loads:", out)
    end

    # The parser reads U+00B5 MICRO SIGN as U+03BC GREEK SMALL LETTER MU.
    @testset "a package name that the parser reads as another name is refused" begin
        code, out = run_hook(FORMATTED; project = replace(PROJECT, "name = \"Fixture\"" => "name = \"µ\""))
        @test code == 1
        @test occursin("is not a Julia identifier", out)
        @test count(l -> occursin("Project.toml", l), split(out, '\n')) == 1
        @test !occursin("loads:", out)
    end

    @testset "a Project.toml with a name and no uuid runs no load test" begin
        code, out = run_hook(FORMATTED; project = "name = \"Fixture\"\n")
        @test code == 0
        @test occursin("unicode: NFC", out)
        @test !occursin(r"loads: (ok|FAILED)", out)
    end

    @testset "a Project.toml without a name says nothing of the load test" begin
        code, out = run_hook(FORMATTED; project = "[deps]\n")
        @test code == 0
        @test occursin("unicode: NFC", out)
        @test !occursin("loads:", out)
    end

    @testset "a Project.toml with a name and no uuid says that no load test runs" begin
        code, out = run_hook(FORMATTED; project = "name = \"Fixture\"\n")
        @test code == 0
        @test count(l -> occursin("loads:", l), split(out, '\n')) == 1
        @test occursin(r"loads: skipped.* no `uuid`", out)
        @test !occursin("pre-commit failed", out)
    end

    @testset "a commit that only deletes a .jl file runs the load test" begin
        repo, env = fixture("module Fixture\n\ninclude(\"extra.jl\")\n\nend\n";
                            extra = ["src/extra.jl" => "double(x) = 2x\n"])
        run(setenv(`git -C $repo commit -q -m base`, env))
        run(setenv(`git -C $repo rm -q src/extra.jl`, env))
        code, out, err = capture(`bash $HOOK`, repo, env)
        @test code == 1
        @test occursin("loads: FAILED", out)
        @test !occursin("formatting", out * err)
        @test !occursin("fatou lint", out * err)
        @test !occursin("unicode", out * err)
    end

    # bash's `exec` does not try a second julia on the PATH, so this one fails to start.
    @testset "a julia that cannot start: a commit with no .jl file and no test/ path passes" begin
        repo, env = fixture(nothing; extra = ["README.md" => "# Fixture\n"])
        env["PATH"] = bindir("julia", "#!/nonexistent/interpreter\n") * ":" * without("julia")
        code, out, err = capture(`$(Sys.which("bash")) $HOOK`, repo, env)
        @test code == 0
        @test out * err == ""
    end

    # The load writes its process id and sleeps; the test interrupts the hook during the load.
    @testset "an interrupted commit stops its load test" begin
        repo, env = fixture("""
            module Fixture

            write(joinpath(@__DIR__, "..", "load.pid"), string(getpid()))
            sleep(120)

            end
            """)
        pidfile = joinpath(repo, "load.pid")
        p = run(pipeline(ignorestatus(setenv(`bash $HOOK`, env; dir = repo)); stdout = devnull,
                         stderr = devnull); wait = false)
        timedwait(() -> filesize(pidfile) > 0 || !process_running(p), 300.0)
        @test filesize(pidfile) > 0
        if filesize(pidfile) > 0
            child = parse(Int, read(pidfile, String))
            kill(p, Base.SIGINT)
            @test timedwait(() -> !process_running(p), 30.0) === :ok
            @test timedwait(() -> !alive(child), 5.0) === :ok
            alive(child) && ccall(:kill, Cint, (Cint, Cint), child, 9)
        end
        process_running(p) && kill(p, Base.SIGKILL)
    end
end

# Functions of the programs, called in this process: each program runs only as a program file,
# so an include defines its functions and runs nothing.
@testset "functions of pre-commit.jl" verbose = true begin
    hook = Module(:PreCommitProgram)
    Base.include(hook, PROGRAM)
    run_boxed(cmd, seconds) = Base.invokelatest(hook.run_boxed, cmd, seconds)

    @testset "a git that fails lists no staged file" begin
        @test cd(() -> Base.invokelatest(hook.staged, "--", "*.jl"), mktempdir()) === nothing
    end

    @testset "the headline of a parse error adds the reason of its last line that holds ` ── `" begin
        headline_cases(e -> Base.invokelatest(hook.headline, e))
    end

    @testset "the lint time box keeps the exit status and both streams" begin
        code, out = run_boxed(`sh -c 'echo out; echo err >&2; exit 3'`, 30)
        @test code == 3
        @test sort(split(chomp(out), '\n')) == ["err", "out"]
    end

    # A box that reads the PID after a yield throws ESRCH for a program reaped by then: about 2
    # runs in 300 on macOS, and more on a Linux runner.
    @testset "the lint time box runs a program that ends at once" begin
        @test all(run_boxed(`true`, 60) == (0, "") for _ in 1:1000)
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

    # The child of `sh` keeps the output open after `sh` ends. The case waits at most 30 s for
    # the box, so a box that waits for the pipe fails here rather than hangs.
    @testset "the lint time box returns when a child of the program holds the output" begin
        pidfile = joinpath(mktempdir(), "child.pid")
        task = @async run_boxed(`sh -c "sleep 120 & echo \$! > '$pidfile'; wait"`, 1)
        t = @elapsed done = timedwait(() -> istaskdone(task), 30.0)
        @test done === :ok
        @test t < 1 + 5 + 3
        child = parse(Int, read(pidfile, String))
        @test istaskdone(task) && fetch(task)[1] === nothing
        @test timedwait(() -> !alive(child), 5.0) === :ok
        alive(child) && ccall(:kill, Cint, (Cint, Cint), child, 9)
    end

    @testset "the lint time box returns when the program ends and its child holds the output" begin
        pidfile = joinpath(mktempdir(), "child.pid")
        task = @async run_boxed(`sh -c "sleep 120 & echo \$! > '$pidfile'"`, 1)
        @test timedwait(() -> istaskdone(task), 30.0) === :ok
        child = parse(Int, read(pidfile, String))
        @test istaskdone(task) && fetch(task)[1] === nothing
        @test timedwait(() -> !alive(child), 5.0) === :ok
        alive(child) && ccall(:kill, Cint, (Cint, Cint), child, 9)
    end

    # `sh` ends on the SIGTERM; the `sleep` that ignores it holds the output until the SIGKILL.
    @testset "the lint time box kills a child that ignores the stop signal" begin
        pidfile = joinpath(mktempdir(), "child.pid")
        t = @elapsed code, _ = run_boxed(`sh -c "(trap '' TERM; exec sleep 120) & echo \$! > '$pidfile'; wait"`, 1)
        child = parse(Int, read(pidfile, String))
        @test code === nothing
        @test 5 <= t < 20
        @test timedwait(() -> !alive(child), 5.0) === :ok
        alive(child) && ccall(:kill, Cint, (Cint, Cint), child, 9)
    end

    # A module of its own whose `signal_group` records each signal with its time. `sleep` ends
    # on the SIGTERM, so the box returns at once; the SIGKILL timer would fire 5 s after the
    # SIGTERM. After the return, a signal is recorded and not sent.
    @testset "the lint time box closes its kill timer when it returns" begin
        box = Module(:PreCommitSignals)
        Base.include(box, PROGRAM)
        sent = Tuple{Int, Float64}[]
        returned = Ref(false)
        function record(group, signal)
            push!(sent, (signal, time()))
            return returned[] ? Cint(-1) : ccall(:kill, Cint, (Cint, Cint), -group, signal)
        end
        Core.eval(box, :(signal_group(group, signal) = $record(group, signal)))
        code, _ = Base.invokelatest(box.run_boxed, `sleep 60`, 1)
        returned[] = true
        at = time()
        sleep(6)
        @test code === nothing
        @test any(s == Base.SIGTERM for (s, _) in sent)
        @test !any(s == Base.SIGKILL && t >= at for (s, t) in sent)
    end

    # The program's child forks a process that ends at once, then leaves the group with `setsid`
    # and keeps the output open without reaping that process: the group keeps a zombie, and the
    # stream stays open.
    @testset "the lint time box returns when a process that left the group holds the output" begin
        pidfile = joinpath(mktempdir(), "perl.pid")
        perl = """
            use POSIX;
            if (fork() == 0) {
                exit 0 if fork() == 0;
                POSIX::setsid();
                open(my \$f, '>', \$ARGV[0]); print \$f \$\$; close(\$f);
                sleep 120;
                exit 0;
            }
            wait();
            """
        task = @async run_boxed(`perl -e $perl $pidfile`, 1)
        t = @elapsed done = timedwait(() -> istaskdone(task), 30.0)
        @test done === :ok
        @test t < 1 + 6 + 3
        @test istaskdone(task) && fetch(task)[1] === nothing
        isfile(pidfile) && ccall(:kill, Cint, (Cint, Cint), parse(Int, read(pidfile, String)), 9)
    end

    @testset "the lint time box reports a program that a signal ends as failed" begin
        code, _ = run_boxed(`sh -c 'kill -SEGV $$'`, 30)
        @test code == 128 + 11
    end

    @testset "the load test stops a load that runs past its limit" begin
        repo, env = fixture("""
            module Fixture

            write(joinpath(@__DIR__, "..", "load.pid"), string(getpid()))
            sleep(120)

            end
            """)
        printed = mktemp() do path, io
            withenv("JULIA_DEPOT_PATH" => env["JULIA_DEPOT_PATH"]) do
                cd(repo) do
                    t = @elapsed ok = redirect_stdout(io) do
                        Base.invokelatest(hook.load, "Fixture"; seconds = 3)
                    end
                    @test ok == false
                    @test t < 3 + 5 + 3
                end
            end
            flush(io)
            read(path, String)
        end
        @test occursin(r"^\e\[0;31mloads: FAILED\e\[0m — `using Fixture` timed out after 3s"m, printed)
        pidfile = joinpath(repo, "load.pid")
        @test isfile(pidfile)
        if isfile(pidfile)
            child = parse(Int, read(pidfile, String))
            @test timedwait(() -> !alive(child), 5.0) === :ok
            alive(child) && ccall(:kill, Cint, (Cint, Cint), child, 9)
        end
    end

    # Runs the ast-grep stage in this process with `path` as the PATH, and returns its verdict and
    # what it printed. A stub that must give a run that checked a file prints `applied`, the
    # `--inspect entity` line of a file that one rule checks.
    function ast_grep(files; path = ENV["PATH"], kwargs...)
        mktemp() do file, io
            ok = withenv("PATH" => path) do
                redirect_stdout(() -> Base.invokelatest(hook.ast_grep, files; kwargs...), io)
            end
            flush(io)
            ok, read(file, String)
        end
    end
    stubbed(script) = bindir("ast-grep", "#!/bin/sh\n" * script) * ":" * ENV["PATH"]
    applied = "echo 'sg: entity|file|x.jl: language=julia,appliedRuleCount=1' >&2\n"

    # No environment of the load path holds JSON.
    @testset "the ast-grep stage skips a run whose output JSON cannot read" begin
        saved = copy(LOAD_PATH)
        ok, out = try
            empty!(LOAD_PATH)
            push!(LOAD_PATH, "@stdlib")
            withenv("RESEARCH_HARNESS_JULIA" => mktempdir()) do
                ast_grep(["x.jl"]; path = stubbed(applied * "echo '{}'\nexit 1\n"))
            end
        finally
            append!(empty!(LOAD_PATH), saved)
        end
        @test ok
        @test occursin("ast-grep: skipped — JSON does not load: ", out)
        @test count('\n', out) == 1
        # A run with no hit needs no JSON.
        ok, out = try
            empty!(LOAD_PATH)
            push!(LOAD_PATH, "@stdlib")
            withenv("RESEARCH_HARNESS_JULIA" => mktempdir()) do
                ast_grep(["x.jl"]; path = stubbed(applied * "exit 0\n"))
            end
        finally
            append!(empty!(LOAD_PATH), saved)
        end
        @test ok
        @test out == "\e[0;32mast-grep: clean\e[0m\n"
    end

    # A program of its own, whose `harness_package` this test replaces.
    @testset "the ast-grep stage passes on an interrupt while JSON loads" begin
        box = Module(:InterruptedProgram)
        Base.include(box, PROGRAM)
        Core.eval(box, :(harness_package(name) = throw(InterruptException())))
        @test_throws InterruptException withenv("PATH" => stubbed(applied * "echo '{}'\nexit 1\n")) do
            redirect_stdout(() -> Base.invokelatest(box.ast_grep, ["x.jl"]), devnull)
        end
    end

    # The child holds the stderr after `sh` ends, and not the stdout.
    @testset "the time box with apart streams returns when a child holds the stderr" begin
        task = @async Base.invokelatest(hook.run_boxed, `sh -c "sleep 120 >/dev/null & echo out"`, 1;
                                        apart = true)
        @test timedwait(() -> istaskdone(task), 30.0) === :ok
        @test istaskdone(task) && fetch(task) == (nothing, "", "")
    end

    @testset "the time box with apart streams keeps them apart" begin
        @test Base.invokelatest(hook.run_boxed, `sh -c 'echo out; echo err >&2; exit 3'`, 30;
                                apart = true) == (3, "out\n", "err\n")
    end

    # ast-grep prints its --inspect lines before the error, which the skip line names.
    @testset "the ast-grep stage names the error of a rule that does not parse" begin
        dir = mktempdir()
        mkpath(joinpath(dir, "rules"))
        write(joinpath(dir, "rules", "bad.yml"), "id: bad\nlanguage: nolanguage\nrule:\n  kind: x\n")
        write(joinpath(dir, "sgconfig.yml"), "ruleDirs: [rules]\n")
        write(joinpath(dir, "x.jl"), "x = 1\n")
        ok, out = cd(() -> ast_grep(["x.jl"]), dir)
        @test ok
        @test occursin(r"ast-grep: skipped — ast-grep exited with status \d+: Error: Cannot parse rule", out)
    end

    @testset "the ast-grep stage skips a run that times out" begin
        ok, out = ast_grep(["x.jl"]; path = stubbed("sleep 30\n"), seconds = 1)
        @test ok
        @test out == "\e[0;33mast-grep: skipped — ast-grep timed out after 1s\e[0m\n"
    end

    @testset "the ast-grep stage skips an ast-grep that cannot start" begin
        stub = bindir("ast-grep", "#!/nonexistent/interpreter\n")
        ok, out = ast_grep(["x.jl"]; path = stub * ":" * without("ast-grep"))
        @test ok
        @test out == "\e[0;33mast-grep: skipped — ast-grep could not start\e[0m\n"
    end

    @testset "the ast-grep stage skips a failure with no message on its exit code alone" begin
        ok, out = ast_grep(["x.jl"]; path = stubbed("exit 5\n"))
        @test ok
        @test out == "\e[0;33mast-grep: skipped — ast-grep exited with status 5\e[0m\n"
    end

    @testset "the ast-grep stage skips an output that is not one JSON object per line" begin
        for line in ("not json", "[1]", "{\"file\":\"x.jl\"}")
            ok, out = ast_grep(["x.jl"]; path = stubbed(applied * "echo '$line'\nexit 1\n"))
            @test ok
            @test out == "\e[0;33mast-grep: skipped — its output is not one JSON object per line\e[0m\n"
        end
    end

    # A config whose rule directory is empty, and one whose only rule is for Python: ast-grep
    # exits 0 with no hit for both, as for a clean file. So does a run that prints nothing.
    @testset "the ast-grep stage skips a run that applies no rule" begin
        python = "id: py-print\nlanguage: python\nseverity: error\nmessage: print\nrule:\n  pattern: print(\$A)\n"
        for (config, rules) in (("customLanguages:\n  julia:\n    libraryPath: $(repr(PARSER))\n    extensions: [jl]\n", []),
                                ("", ["print.yml" => python]))
            dir = mktempdir()
            mkpath(joinpath(dir, "rules"))
            for (name, text) in rules
                write(joinpath(dir, "rules", name), text)
            end
            write(joinpath(dir, "sgconfig.yml"), "ruleDirs: [rules]\n" * config)
            write(joinpath(dir, "x.jl"), "@show x\n")
            ok, out = cd(() -> ast_grep(["x.jl"]), dir)
            @test ok
            @test occursin("ast-grep: skipped — ast-grep applied no rule to the staged files", out)
        end
        ok, out = ast_grep(["x.jl"]; path = stubbed("exit 0\n"))
        @test ok
        @test occursin("ast-grep: skipped — ast-grep applied no rule to the staged files", out)
    end

    # Under this variable the hook's list of staged `*.jl` files holds no file below src/, so
    # only a direct call reaches `added_lines` with it.
    @testset "added_lines ignores GIT_GLOB_PATHSPECS" begin
        repo, env = two_hunks()
        lines = withenv(env..., "GIT_GLOB_PATHSPECS" => "1") do
            cd(() -> Base.invokelatest(hook.added_lines, "src/Fixture.jl", nothing), repo)
        end
        @test lines == [4:4, 8:8]
    end

    # As for `added_lines`, only a direct call reaches a file below src/ with the variable set.
    @testset "unstaged ignores GIT_GLOB_PATHSPECS" begin
        repo, env = fixture(FORMATTED)
        write(joinpath(repo, "src", "Fixture.jl"), MISFORMATTED)
        files = withenv(env..., "GIT_GLOB_PATHSPECS" => "1") do
            cd(() -> Base.invokelatest(hook.unstaged, ["src/Fixture.jl"]), repo)
        end
        @test files == ["src/Fixture.jl"]
    end

    # `format` with no style uses JuliaFormatter's default style: githooks/ has no
    # .JuliaFormatter.toml, so the style is named.
    @testset "the hook programs are in SciML style" begin
        pushfirst!(LOAD_PATH, get(ENV, "RESEARCH_HARNESS_JULIA",
                                  joinpath(homedir(), ".local", "share", "research-harness", "julia")))
        formatter = try
            Base.require(Base.identify_package("JuliaFormatter"))
        finally
            popfirst!(LOAD_PATH)
        end
        style = Base.invokelatest(() -> formatter.SciMLStyle())
        for program in (PROGRAM, joinpath(@__DIR__, "pre-push.jl"))
            @test Base.invokelatest(formatter.format, program, style; overwrite = false)
        end
    end
end

@testset "pre-push" begin
    topic = "refs/heads/topic 1111111111111111111111111111111111111111 refs/heads/topic 0000000000000000000000000000000000000000\n"
    main = "refs/heads/main 1111111111111111111111111111111111111111 refs/heads/main 0000000000000000000000000000000000000000\n"

    # The suite fails unless it runs with the default bounds checks: up to Julia 1.12, Pkg.test
    # passes --check-bounds=yes to the test process unless julia_args says otherwise. The
    # command itself is checked in "the suite of pre-push", for the Julia releases after 1.12.
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

    @testset "pre-push: a repository without Project.toml or test/runtests.jl runs nothing" begin
        repo, env = fixture(nothing; project = nothing)
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

    @testset "without julia on the PATH, a push of a topic branch passes" begin
        repo, env = fixture(FORMATTED)
        env["PATH"] = without("julia")
        code, out, err = capture(`$(Sys.which("bash")) $PREPUSH origin x`, repo, env; input = topic)
        @test code == 0
        @test occursin("not main/master — skipping the suite", out)
        @test err == ""
    end

    @testset "without julia on the PATH, a push of main beside a topic branch is refused" begin
        repo, env = fixture(FORMATTED)
        env["PATH"] = without("julia")
        code, _, err = capture(`$(Sys.which("bash")) $PREPUSH origin x`, repo, env;
                               input = topic * main)
        @test code == 1
        @test err == "pre-push: julia is not on the PATH.\n"
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
        t = @elapsed done = timedwait(() -> !process_running(p), 30.0)
        @test done === :ok
        @test t < 30
        process_running(p) && kill(p, Base.SIGKILL)
        wait(p)
        @test p.exitcode == 130
        @test timedwait(() -> !alive(suite), 5.0) === :ok
        alive(suite) && ccall(:kill, Cint, (Cint, Cint), suite, 9)
    end

    @testset "pre-push: a last ref line without a newline is read" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing])
        code, out, _ = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                               input = topic * chomp(main))
        @test code == 0
        @test occursin("Suite passed.", out)
    end

    @testset "pre-push: a refused push to master says main or master" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => "error(\"the suite failed\")\n"])
        code, out, _ = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                               input = replace(main, "main" => "master"))
        @test code == 1
        @test occursin("tests must pass before pushing to main or master.", out)
    end

    # bash's `exec` does not try a second julia on the PATH, so this one fails to start.
    @testset "a julia that cannot start: a push of a topic branch passes" begin
        repo, env = fixture(FORMATTED)
        env["PATH"] = bindir("julia", "#!/nonexistent/interpreter\n") * ":" * without("julia")
        code, out, err = capture(`$(Sys.which("bash")) $PREPUSH origin x`, repo, env; input = topic)
        @test code == 0
        @test occursin("not main/master — skipping the suite", out)
        @test err == ""
    end

    # Pkg.test prints "Testing Fixture tests passed"; a run of test/runtests.jl does not.
    @testset "pre-push: an indented, single-quoted name runs Pkg.test" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing],
                            project = replace(PROJECT, "name = \"Fixture\"" => "  name = 'Fixture'"))
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = main)
        @test code == 0
        @test occursin("Testing Fixture tests passed", out * err)
    end

    @testset "pre-push: a Project.toml that does not parse is refused" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing],
                            project = replace(PROJECT, "\"Fixture\"" => "\"Fixture"))
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = main)
        @test code == 1
        @test occursin("pre-push: Project.toml does not parse", out)
        @test !occursin("Suite passed.", out)
        @test !occursin("Stacktrace", out * err)
    end

    @testset "pre-push: a Project.toml that does not parse is refused with the error's location" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing],
                            project = replace(PROJECT, "\"Fixture\"" => "\"Fixture"))
        code, out, _ = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                               input = main)
        @test code == 1
        @test occursin(r"Project\.toml:\d+:-?\d+ error: ", out)
    end

    # Put into `Pkg.test("<name>")`, the name writes `ran`.
    @testset "pre-push: a package name that is not an identifier is refused" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing],
                            project = replace(PROJECT, "name = \"Fixture\"" => "name = '\$(write(\"ran\", \"1\"))'"))
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = main)
        @test code == 1
        @test !isfile(joinpath(repo, "ran"))
        @test occursin("is not a Julia identifier", out)
        @test count(l -> occursin("Project.toml", l), split(out * err, '\n')) == 1
        @test !occursin("running the full suite", out)
    end

    # Base.isidentifier accepts `end`; the parser does not read it as a name.
    @testset "pre-push: a package name that is a keyword is refused" begin
        repo, env = fixture(FORMATTED; extra = ["test/runtests.jl" => passing],
                            project = replace(PROJECT, "name = \"Fixture\"" => "name = \"end\""))
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = main)
        @test code == 1
        @test occursin("is not a Julia identifier", out)
        @test count(l -> occursin("Project.toml", l), split(out * err, '\n')) == 1
        @test !occursin("running the full suite", out)
    end

    # Pkg.test prints "Testing Fixture"; a run of test/runtests.jl does not.
    @testset "pre-push: a Project.toml with a name and no uuid runs test/runtests.jl" begin
        repo, env = fixture(nothing; project = "name = \"Fixture\"\n",
                            extra = ["test/runtests.jl" => "println(\"runtests ran\"); " * passing])
        code, out, err = capture(`bash $PREPUSH origin https://example.org/x.git`, repo, env;
                                 input = main)
        @test code == 0
        @test occursin("runtests ran", out)
        @test !occursin("Testing Fixture", out * err)
        @test occursin("Suite passed.", out)
    end

    # The suite ignores SIGINT, and so does the `sleep` that it becomes.
    @testset "pre-push: a suite that ignores the interrupt is killed after the grace time" begin
        dir = mktempdir()
        pidfile = joinpath(dir, "suite.pid")
        p = suite_driver("trap '' INT; echo \$\$ > '$pidfile'; exec sleep 120", dir;
                         kwargs = "; grace = 2")
        timedwait(() -> filesize(pidfile) > 0 || !process_running(p), 120.0)
        @test filesize(pidfile) > 0
        if filesize(pidfile) > 0
            suite = parse(Int, read(pidfile, String))
            kill(p, Base.SIGINT)
            t = @elapsed done = timedwait(() -> !process_running(p), 30.0)
            @test done === :ok
            @test 2 <= t < 15
            @test timedwait(() -> !alive(suite), 5.0) === :ok
            alive(suite) && ccall(:kill, Cint, (Cint, Cint), suite, 9)
        end
        process_running(p) && kill(p, Base.SIGKILL)
        wait(p)
        @test p.exitcode == 130
    end

    # The leader `sh` ends at once on the interrupt; its background `sleep`, in the same group,
    # ignores it.
    @testset "pre-push: a group member that ignores the interrupt after the leader ends is killed at the grace time" begin
        dir = mktempdir()
        pidfile = joinpath(dir, "member.pid")
        p = suite_driver("(trap '' INT; exec sleep 120) & echo \$! > '$pidfile'; trap 'exit 0' INT; wait",
                         dir; kwargs = "; grace = 2")
        timedwait(() -> filesize(pidfile) > 0 || !process_running(p), 120.0)
        @test filesize(pidfile) > 0
        if filesize(pidfile) > 0
            member = parse(Int, read(pidfile, String))
            kill(p, Base.SIGINT)
            t = @elapsed done = timedwait(() -> !process_running(p), 30.0)
            @test done === :ok
            @test 2 <= t < 15
            @test timedwait(() -> !alive(member), 5.0) === :ok
            alive(member) && ccall(:kill, Cint, (Cint, Cint), member, 9)
        end
        process_running(p) && kill(p, Base.SIGKILL)
        wait(p)
        @test p.exitcode == 130
    end

    # The suite ignores SIGINT and ends at the SIGKILL; the group check says the group stays, as
    # it does for a member that SIGKILL cannot end.
    @testset "pre-push: a suite group that outlives its SIGKILL ends the hook after the linger time" begin
        dir = mktempdir()
        pidfile = joinpath(dir, "suite.pid")
        outfile = joinpath(dir, "out.txt")
        p = suite_driver("trap '' INT; echo \$\$ > '$pidfile'; exec sleep 120", dir;
                         kwargs = "; grace = 1, linger = 2, group_alive = _ -> true", out = outfile)
        timedwait(() -> filesize(pidfile) > 0 || !process_running(p), 120.0)
        @test filesize(pidfile) > 0
        if filesize(pidfile) > 0
            suite = parse(Int, read(pidfile, String))
            kill(p, Base.SIGINT)
            t = @elapsed done = timedwait(() -> !process_running(p), 30.0)
            @test done === :ok
            @test 3 <= t < 15
            @test timedwait(() -> !alive(suite), 5.0) === :ok
            alive(suite) && ccall(:kill, Cint, (Cint, Cint), suite, 9)
            out = read(outfile, String)
            @test count(l -> occursin("pre-push:", l), split(out, '\n')) == 1
            @test occursin("processes of the suite are left in process group $suite", out)
        end
        process_running(p) && kill(p, Base.SIGKILL)
        wait(p)
        @test p.exitcode == 130
    end

    # The suite takes 3 s to stop after the interrupt; a second interrupt reaches the hook 1 s in.
    # The hook prints the one line of an interrupt, and no error.
    @testset "pre-push: a second interrupt during the wait still stops the suite" begin
        dir = mktempdir()
        pidfile = joinpath(dir, "suite.pid")
        outfile = joinpath(dir, "out.txt")
        errfile = joinpath(dir, "err.txt")
        p = suite_driver("trap 'sleep 3; exit 7' INT; echo \$\$ > '$pidfile'; while :; do sleep 0.1; done",
                         dir; out = outfile, err = errfile)
        timedwait(() -> filesize(pidfile) > 0 || !process_running(p), 120.0)
        @test filesize(pidfile) > 0
        if filesize(pidfile) > 0
            suite = parse(Int, read(pidfile, String))
            kill(p, Base.SIGINT)
            sleep(1)
            kill(p, Base.SIGINT)
            @test timedwait(() -> !process_running(p), 30.0) === :ok
            @test timedwait(() -> !alive(suite), 5.0) === :ok
            alive(suite) && ccall(:kill, Cint, (Cint, Cint), suite, 9)
        end
        process_running(p) && kill(p, Base.SIGKILL)
        wait(p)
        @test p.exitcode == 130
        @test occursin("pre-push: interrupted; the suite has stopped.", read(outfile, String))
        @test read(errfile, String) == ""
    end

    # The suite ends at the interrupt; the group check runs for 1 s without yielding, so the
    # second interrupt, 0.5 s after the first, comes while the hook runs rather than waits.
    @testset "pre-push: an interrupt while the hook checks the group prints no error" begin
        dir = mktempdir()
        pidfile = joinpath(dir, "suite.pid")
        outfile = joinpath(dir, "out.txt")
        errfile = joinpath(dir, "err.txt")
        busy = "_ -> (t = time_ns(); while time_ns() - t < 1e9 end; true)"
        p = suite_driver("trap 'exit 0' INT; echo \$\$ > '$pidfile'; while :; do sleep 0.1; done", dir;
                         kwargs = "; grace = 1, linger = 2, group_alive = $busy", out = outfile,
                         err = errfile)
        timedwait(() -> filesize(pidfile) > 0 || !process_running(p), 120.0)
        @test filesize(pidfile) > 0
        if filesize(pidfile) > 0
            suite = parse(Int, read(pidfile, String))
            kill(p, Base.SIGINT)
            sleep(0.5)
            kill(p, Base.SIGINT)
            @test timedwait(() -> !process_running(p), 30.0) === :ok
            @test timedwait(() -> !alive(suite), 5.0) === :ok
            alive(suite) && ccall(:kill, Cint, (Cint, Cint), suite, 9)
        end
        process_running(p) && kill(p, Base.SIGKILL)
        wait(p)
        @test p.exitcode == 130
        @test occursin("processes of the suite are left", read(outfile, String))
        @test read(errfile, String) == ""
    end
end

@testset "the gate of pre-push" begin
    prepush = Module(:PrePushProgram)
    Base.include(prepush, joinpath(@__DIR__, "pre-push.jl"))
    gated(line) = Base.invokelatest(prepush.gated, line)
    @test gated("refs/heads/x 1 refs/heads/main 0")
    @test gated("refs/heads/x 1 refs/heads/master 0")
    @test !gated("refs/heads/main 1 refs/heads/topic 0")
    @test !gated("refs/heads/x 1 refs/heads/mainline 0")
    @test !gated("refs/heads/main 1")
    @test !gated("")
end

@testset "the suite of pre-push" begin
    prepush = Module(:PrePushSuite)
    Base.include(prepush, joinpath(@__DIR__, "pre-push.jl"))
    cmd = Base.invokelatest(prepush.suite, "Fixture")
    @test cmd.exec[1] == joinpath(Sys.BINDIR, Base.julia_exename())
    @test "--check-bounds=auto" in cmd.exec
    @test "--project=." in cmd.exec
    @test cmd.exec[end] == "using Pkg; Pkg.test(\"Fixture\"; julia_args = `--check-bounds=auto`)"
end

@testset "the headline of pre-push" begin
    prepush = Module(:PrePushHeadline)
    Base.include(prepush, joinpath(@__DIR__, "pre-push.jl"))
    headline(e) = Base.invokelatest(prepush.headline, e)
    parse_error = try
        Meta.parse("a b"; filename = "a.jl")
    catch e
        e
    end
    @test headline(parse_error) == "ParseError: — # Error @ a.jl:1:2 — extra tokens after end of expression"
    headline_cases(headline)
end
end
