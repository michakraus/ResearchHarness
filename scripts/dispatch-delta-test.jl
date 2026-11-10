#!/usr/bin/env julia
#
# Checks for dispatch-delta.jl. Run after any change to it, with the default Julia:
#
#   julia --startup-file=no dispatch-delta-test.jl
#
# Each fixture is a small package that uses the standard library only, in a git repository under
# tempdir() with a base commit and a head commit; the script runs on it in a process of its own,
# and loads each side in a process of its own. A sandboxed process can make a `.git` under
# tempdir() but not under ~/Research. The script keeps its run directories under
# ~/Research/.scratch/dispatch-delta/; the tests remove the ones they make.

using Test, UUIDs

# Run as a script, the file runs again inside one test set, so that it prints one summary table.
if abspath(PROGRAM_FILE) == @__FILE__() && Test.get_testset_depth() == 0
    @testset "dispatch-delta-test.jl" verbose = true include(@__FILE__)
    exit()
end

module DD
include(joinpath(@__DIR__, "dispatch-delta.jl"))
end

const SCRIPT = joinpath(@__DIR__, "dispatch-delta.jl")
const RUNS_DIR = expanduser("~/Research/.scratch/dispatch-delta")
const ROOT = mktempdir()
const MADE = String[]
const GITENV = filter(((k, _),) -> !startswith(k, "GIT_"), ENV)

git(dir, args...) = run(setenv(`git -c user.name=fixture -c user.email=fixture@example.org $args`, GITENV; dir))
git_read(dir, args...) = read(setenv(`git $args`, GITENV; dir), String)

"Write each `path => text` under `dir`."
function files!(dir, files)
    for (p, t) in files
        f = joinpath(dir, p)
        mkpath(dirname(f))
        write(f, t)
    end
end

"""
A package `name` in a new git repository under `ROOT`: a base commit with `base` and a head commit
with `head` on top. `project` goes into the base's `Project.toml` after the name, the UUID and the
version; `headproject`, where given, replaces it in the head. With `sub`, the package is in that
subdirectory of the repository.
"""
function fixture(name, base, head; project = "", headproject = project, sub = "")
    top = mkpath(joinpath(ROOT, name))
    dir = mkpath(joinpath(top, sub))
    proj(extra) = "name = \"$name\"\nuuid = \"$(uuid5(UUID("5c3e7f6a-1d2b-4c8e-9f0a-2b4c6d8e0f1a"), name))\"\nversion = \"0.1.0\"\n$extra"
    git(top, "init", "-q", ".")
    files!(dir, ["Project.toml" => proj(project), ".gitignore" => "Manifest.toml\nalive.txt\n", base...])
    git(top, "add", "--all")
    git(top, "commit", "-q", "-m", "base")
    files!(dir, ["Project.toml" => proj(headproject), head...])
    git(top, "add", "--all")
    git(top, "commit", "-q", "--allow-empty", "-m", "head")
    return dir
end

"Run the script with `args`, from `dir`; the exit code, stdout, stderr, the time and the run directory."
function dd(args...; dir = ROOT)
    out, err = IOBuffer(), IOBuffer()
    cmd = Cmd(`$(Base.julia_cmd()) --startup-file=no $SCRIPT $args`; dir)
    t = @elapsed p = run(pipeline(ignorestatus(cmd); stdout = out, stderr = err))
    o = String(take!(out))
    m = match(r"run directory (\S+)", o)
    rundir = m === nothing ? "" : String(m[1])
    isempty(rundir) || push!(MADE, rundir)
    return (; code = p.exitcode, out = o, err = String(take!(err)), secs = t, run = rundir)
end

lines(out, prefix) = [String(l) for l in split(out, '\n') if startswith(l, prefix)]
verdict(out) = only(lines(out, "Verdict: "))

"The `  other:` lines that follow the `INFO: added method:` line that contains `what`."
function others(out, what)
    ls = split(out, '\n')
    k = findfirst(l -> startswith(l, "INFO: added method: ") && occursin(what, l), ls)
    k === nothing && return nothing
    res = String[]
    for l in ls[(k + 1):end]
        startswith(l, "  other: ") || break
        push!(res, String(l))
    end
    return res
end

mod(name, body) = "module $name\n$body\nend\n"

@testset "bad arguments exit 2 and name the argument" begin
    repo = fixture("DDArgs", ["src/DDArgs.jl" => mod("DDArgs", "a(x) = x")], [])
    nogit = mkpath(joinpath(ROOT, "nogit"))
    write(joinpath(nogit, "Project.toml"), "name = \"DDNoGit\"\n")
    noproject = mkpath(joinpath(ROOT, "noproject"))
    git(noproject, "init", "-q", ".")
    noname = mkpath(joinpath(ROOT, "noname"))
    git(noname, "init", "-q", ".")
    write(joinpath(noname, "Project.toml"), "version = \"0.1.0\"\n")
    # the run directories of these packages; another run of this file may make its own meanwhile
    runs() = isdir(RUNS_DIR) ? filter(d -> startswith(d, "DDArgs-") || startswith(d, "DDNoGit-"), readdir(RUNS_DIR)) : String[]
    before = runs()
    for (args, names) in [
        (String[], "<package>"),
        ([nogit, "HEAD"], "not a git repository"),
        ([noproject, "HEAD"], "has no Project.toml"),
        ([noname, "HEAD"], "Project.toml has no name"),
        ([repo, "HEAD", "--treat-as-own", "Foo"], "unknown option --treat-as-own"),
        ([repo, "HEAD", "--timeout", "0"], "--timeout"),
        ([repo, "HEAD", "--timeout", "x"], "--timeout"),
        ([repo, "HEAD", "--timeout", "1.5"], "--timeout"),
        ([repo, "HEAD", "--timeout"], "--timeout"),
        ([repo, ""], "<base> is empty"),
        ([repo, "no-such-ref"], "no-such-ref"),
        ([repo, "-x"], "unknown option -x"),
        ([repo, "HEAD", "HEAD~1"], "one <package> and one <base>"),
    ]
        r = dd(args...)
        @test r.code == 2
        @test occursin(names, r.err)
        @test isempty(r.run)
    end
    @test runs() == before
    a = DD.arguments([repo, "HEAD", "--timeout", "1"])
    @test a isa NamedTuple && a.timeout == 1 && a.jet
    @test !DD.arguments([repo, "HEAD", "--no-jet"]).jet
    @test DD.arguments([repo, "HEAD"]).timeout == 600
    @test DD.arguments([repo, "HEAD", "--api"]).api && !DD.arguments([repo, "HEAD"]).api
    @test DD.arguments([repo, "HEAD", "--api"]).jet
end

@testset "the key renames type variables by position and keeps their bounds" begin
    @eval module K
    g(x) = x
    var"##kw#12"(x) = x
    module Sub
    s(x::Integer, y) = 1
    end
    end
    T, S = TypeVar(:T, Real), TypeVar(:S, Real)
    a = UnionAll(T, Tuple{typeof(K.g), T, Vector{T}})
    b = UnionAll(S, Tuple{typeof(K.g), S, Vector{S}})
    I = TypeVar(:T, Integer)
    c = UnionAll(I, Tuple{typeof(K.g), I, Vector{I}})
    @test DD.key(a, K) == "Tuple{typeof(g), _1, Vector{_1}} where _1<:Real"
    @test DD.key(b, K) == DD.key(a, K)
    @test DD.key(c, K) != DD.key(a, K)
    k = DD.key(Tuple{typeof(getfield(K, Symbol("##kw#12"))), Any}, K)
    @test occursin("##kw#", k) && !occursin(r"##kw#\d", k)
    # a bound that names an earlier variable is renamed with it
    U = TypeVar(:U)
    V = TypeVar(:V, AbstractVector{U})
    @test DD.key(UnionAll(U, UnionAll(V, Tuple{typeof(K.g), U, V})), K) ==
          "Tuple{typeof(g), _1, _2} where {_1, _2<:AbstractVector{_1}}"
    # a name that the root module imports keeps its key: a submodule's function names its
    # submodule, and an external function its full path
    sk = Tuple{typeof(K.Sub.s), Integer, Any}
    @test DD.key(sk, K) == "Tuple{typeof(Sub.s), Integer, Any}"
    @test DD.key(Tuple{typeof(Base.Iterators.cycle), Symbol}, K) == "Tuple{typeof(Base.Iterators.cycle), Symbol}"
    Core.eval(K, :(using .Sub: s))
    Core.eval(K, :(using Base.Iterators: cycle))
    @test DD.key(sk, K) == "Tuple{typeof(Sub.s), Integer, Any}"
    @test DD.key(Tuple{typeof(Base.Iterators.cycle), Symbol}, K) == "Tuple{typeof(Base.Iterators.cycle), Symbol}"
    # the root's name is stripped only where it starts a path
    @eval module SubMain
    module K
    t(x) = x
    end
    end
    @test DD.key(Tuple{typeof(SubMain.K.t), Any}, K) == "Tuple{typeof(Main.SubMain.K.t), Any}"
    @eval module Q
    module Main
    module K
    t(x) = x
    end
    end
    end
    @test DD.key(Tuple{typeof(Q.Main.K.t), Any}, K) == "Tuple{typeof(Main.Q.Main.K.t), Any}"
end

# One run that passes: the head moves a method, adds methods, a JET report and a function, keeps
# an ambiguity of the base and removes a piracy and an ambiguity of the base.
const PASS_BASE = mod("DDPass", """
struct A end
g(x::T, y::Vector{T}) where {T<:Real} = x
p(x::Int) = 1
p(x::String) = 2
kw(x; a = 1) = x + a
amb(x::Integer, y) = 1
amb(x, y::Integer) = 2
gone(x::Integer, y) = 1
gone(x, y::Integer) = 2
Base.length(::Symbol) = 0
old(x) = gone_name_xyz(x)
kwp(x::Int; a = 1) = x""")
const PASS_HEAD = mod("DDPass", """
struct A end
include("moved.jl")
p(x::Int) = 1
p(x::String) = 2
p(x::Float64) = 3
kw(x; a = 1) = x + a
amb(x::Integer, y) = 1
amb(x, y::Integer) = 2
gone(x::Integer, y) = 1
Base.show(io::IO, ::A) = print(io, "A")
brand_new(x) = x
h(x) = undefined_name_xyz(x)
brand_kw(x; k = 1) = x + k
kwp(x::Int; a = 1) = x
kwp(x::String; a = 1) = x""")
const PASS = fixture("DDPass", ["src/DDPass.jl" => PASS_BASE],
    ["src/DDPass.jl" => PASS_HEAD, "src/moved.jl" => "\n\n# g, moved\ng(x::S, y::Vector{S}) where {S<:Real} = x\n"])
# the head's Manifest.toml, resolved by this Julia
run(`$(Base.julia_cmd()) --startup-file=no --project=$PASS -e "using Pkg; Pkg.resolve(; io = devnull)"`)
const PASS_STATUS = git_read(PASS, "status", "--porcelain", "--ignored")
const P = dd(PASS, "HEAD~1")
const HEAD_JSON = DD.JSON.parsefile(joinpath(P.run, "head.json"))
const BASE_JSON = DD.JSON.parsefile(joinpath(P.run, "base.json"))

@testset "the head's manifest goes into the base tree" begin
    @test isfile(joinpath(PASS, "Manifest.toml"))
    @test lines(P.out, "manifest: ") == ["manifest: the head's Manifest.toml goes into the base tree"]
    @test BASE_JSON["dependencies"] == HEAD_JSON["dependencies"]
    # the base tree held the head's manifest when its side began
    @test BASE_JSON["manifest"] === true && HEAD_JSON["manifest"] === true
end

@testset "the head's tree is left as it was, and the base tree is removed" begin
    @test git_read(PASS, "status", "--porcelain", "--ignored") == PASS_STATUS
    @test isfile(joinpath(P.run, "base.json")) && isfile(joinpath(P.run, "head.json"))
    @test isfile(joinpath(P.run, "head.log")) && isfile(joinpath(P.run, "base.log"))
    @test !any(startswith("DDPass-base-"), readdir(P.run))
    @test lines(P.out, "json: ") == ["json: $(joinpath(P.run, "base.json")) $(joinpath(P.run, "head.json"))"]
end

@testset "each side writes one JSON record per own method" begin
    for k in ("package", "side", "julia", "tools", "dependencies", "loaded", "methods", "ambiguities", "piracies")
        @test haskey(HEAD_JSON, k)
    end
    @test HEAD_JSON["package"] == "DDPass" && HEAD_JSON["side"] == "head"
    @test haskey(HEAD_JSON["tools"], "Aqua")
    @test "DDPass" in HEAD_JSON["loaded"] && issorted(HEAD_JSON["loaded"])
    ms = HEAD_JSON["methods"]
    for m in ms
        @test issubset(("key", "name", "module", "file", "line", "generic", "generic_package", "others"), keys(m))
        @test !startswith(m["file"], "/")
    end
    count_of(n) = count(m -> m["name"] == n, ms)
    # A(), g, p ×3, kw, amb ×2, gone, show, brand_new, h, brand_kw, kwp ×2, and the Core.kwcall
    # methods of kw, brand_kw and kwp ×2
    @test length(ms) == 19
    @test (count_of("p"), count_of("kw"), count_of("amb"), count_of("show")) == (3, 2, 2, 1)
    show = only(filter(m -> m["name"] == "show", ms))
    @test show["generic"] == "external" && show["key"] == "Tuple{typeof(show), IO, A}"
    @test show["file"] == "src/DDPass.jl" && show["line"] == 11 && show["module"] == "DDPass"
    @test show["generic_package"] == "Base"
    @test only(filter(m -> m["name"] == "brand_new", ms))["generic"] == "own"
    # a constructor is a method of an own generic; a function type that is no DataType has none
    @test only(filter(m -> m["name"] == "A", ms))["generic"] == "own"
    @test DD.generic_module(Union{typeof(sin), typeof(cos)}) === nothing
end

@testset "names that start with # are dropped, Core.kwcall methods stay" begin
    ms = HEAD_JSON["methods"]
    @test any(m -> startswith(m["key"], "Tuple{typeof(Core.kwcall)") && occursin("typeof(kw)", m["key"]), ms)
    @test !any(m -> startswith(m["name"], "#"), ms)
end

@testset "a keyword method belongs to its keyword function" begin
    ms = HEAD_JSON["methods"]
    kwcalls(f) = filter(m -> startswith(m["key"], "Tuple{typeof(Core.kwcall),") && occursin("typeof($f)", m["key"]), ms)
    @test length(kwcalls("brand_kw")) == 1 && length(kwcalls("kw")) == 1
    @test all(m -> m["generic"] == "own", [kwcalls("brand_kw"); kwcalls("kw")])
    # the other methods of a keyword method are the keyword methods of its function, and the
    # other methods of a positional method the positional ones
    kint, kstr = (only(filter(m -> occursin(t, m["key"]), kwcalls("kwp"))) for t in ("Int64", "String"))
    @test [o["key"] for o in kstr["others"]] == [kint["key"]]
    pstr = only(filter(m -> m["key"] == "Tuple{typeof(kwp), String}", ms))
    @test [o["key"] for o in pstr["others"]] == ["Tuple{typeof(kwp), Int64}"]
    @test DD.generic_of(only(kwcalls("kw"))["key"]) == "typeof(kw)"
    @test DD.generic_of(kstr["key"]) == "typeof(kwp)"
    @test only(others(P.out, kstr["key"])) == "  other: $(kint["key"]) at src/DDPass.jl:15"
end

@testset "a moved method is the same method" begin
    @test !any(l -> occursin("typeof(g)", l), lines(P.out, "INFO: added method:"))
    @test isempty(lines(P.out, "FAIL:"))
    @test P.code == 0
    g = only(filter(m -> m["name"] == "g", HEAD_JSON["methods"]))
    @test g["file"] == "src/moved.jl" && g["line"] == 4
end

@testset "an ambiguity on the base does not fail" begin
    @test !any(l -> occursin("typeof(amb)", l), [lines(P.out, "FAIL:"); lines(P.out, "INFO:")])
    @test count(a -> a["kind"] == "own-own", HEAD_JSON["ambiguities"]) == 1
    @test P.code == 0
    # Test orders a pair of one file by line; a head that swaps the two lines keeps the record
    @eval module AB1
    amb(x::Integer, y) = 1
    amb(x, y::Integer) = 2
    end
    @eval module AB2
    amb(x, y::Integer) = 2
    amb(x::Integer, y) = 1
    end
    raw(M) = [DD.key(m.sig, M) for m in only(Test.detect_ambiguities(M))]
    @test raw(AB1) == reverse(raw(AB2))
    @test DD.ambiguities([AB1], Set([AB1]), AB1) == DD.ambiguities([AB2], Set([AB2]), AB2)
end

@testset "a finding that went away is information" begin
    @test only(lines(P.out, "INFO: gone piracy: ")) == "INFO: gone piracy: Tuple{typeof(length), Symbol} at src/DDPass.jl:11"
    @test only(lines(P.out, "INFO: gone own-own ambiguity: ")) ==
          "INFO: gone own-own ambiguity: Tuple{typeof(gone), Any, Integer} | Tuple{typeof(gone), Integer, Any}"
    l = only(lines(P.out, "INFO: gone JET report: "))
    @test occursin("gone_name_xyz", l) && endswith(l, " in Tuple{typeof(old), Any}")
    @test isempty(lines(P.out, "FAIL:")) && P.code == 0
end

@testset "a new JET report is information" begin
    l = only(lines(P.out, "INFO: new JET report: "))
    @test startswith(l, "INFO: new JET report: UndefVarErrorReport: ") && occursin("undefined_name_xyz", l)
    @test endswith(l, " in Tuple{typeof(h), Any}")
    @test isfile(joinpath(P.run, "head-jet.json")) && isfile(joinpath(P.run, "base-jet.json"))
    @test P.code == 0 && startswith(verdict(P.out), "Verdict: PASS — 0 FAIL, 0 UNKNOWN, ")
end

@testset "a method added to an own generic prints with every other method" begin
    o = others(P.out, "Tuple{typeof(p), Float64}")
    @test o == ["  other: Tuple{typeof(p), Int64} at src/DDPass.jl:4", "  other: Tuple{typeof(p), String} at src/DDPass.jl:5"]
    @test only(lines(P.out, "INFO: added method: Tuple{typeof(p)")) == "INFO: added method: Tuple{typeof(p), Float64} at src/DDPass.jl:6"
    # the generic of a key is its first type parameter, commas inside it included
    @test DD.generic_of("Tuple{typeof(p), Float64}") == "typeof(p)"
    @test DD.generic_of("Tuple{Type{Pair{Int64, Int64}}, Any}") == "Type{Pair{Int64, Int64}}"
    @test DD.generic_of("Tuple{typeof(f)} where _1") == "typeof(f)"
end

@testset "a method added to an external generic prints with the intersecting methods only" begin
    o = others(P.out, "Tuple{typeof(show), IO, A}")
    @test o !== nothing
    @test any(startswith("  other: Tuple{typeof(show), IO, Any} at "), o)
    @test !any(l -> occursin("Signed", l), o)
end

@testset "a method of a new function is not an added method" begin
    @test !any(l -> occursin("brand_new", l) || occursin("typeof(h)", l), lines(P.out, "INFO: added method:"))
    # nor is a keyword method of a new function
    @test !any(l -> occursin("brand_kw", l), lines(P.out, "INFO: added method:"))
end

# One run that fails, without JET: new ambiguities in the root module, in a submodule and in an
# extension, an own-external ambiguity, a piracy in a submodule and one in the extension.
const FAIL_PROJECT = """

[weakdeps]
LinearAlgebra = "37e2e46d-f89d-539d-b4ee-838fcccc9c8e"

[extensions]
DDFailLinearAlgebraExt = "LinearAlgebra"

[extras]
LinearAlgebra = "37e2e46d-f89d-539d-b4ee-838fcccc9c8e"

[targets]
test = ["LinearAlgebra"]
"""
const FAIL_HEAD = mod("DDFail", """
struct A end
f(x::Integer, y) = 1
f(x, y::Integer) = 2
Base.:(==)(::Any, ::A) = true
function q end
h(x) = undefined_name_xyz(x)
module Sub
s(x::Integer, y) = 1
s(x, y::Integer) = 2
Base.length(::Symbol) = 0
end""")
const FAIL = fixture("DDFail",
    ["src/DDFail.jl" => mod("DDFail", "struct A end\nf(x::Integer, y) = 1\nfunction q end\nmodule Sub\ns(x::Integer, y) = 1\nend"),
     "ext/DDFailLinearAlgebraExt.jl" => mod("DDFailLinearAlgebraExt", "using DDFail, LinearAlgebra\nDDFail.q(x::Integer, y) = 1\nconst LA = LinearAlgebra")],
    ["src/DDFail.jl" => FAIL_HEAD,
     "ext/DDFailLinearAlgebraExt.jl" => mod("DDFailLinearAlgebraExt",
        "using DDFail, LinearAlgebra\nDDFail.q(x::Integer, y) = 1\nDDFail.q(x, y::Integer) = 2\nBase.length(::Char) = 1\nconst LA = LinearAlgebra")];
    project = FAIL_PROJECT)
const F = dd(FAIL, "HEAD~1", "--no-jet")
const FAIL_JSON = DD.JSON.parsefile(joinpath(F.run, "head.json"))

@testset "a new own-own ambiguity fails" begin
    @test "FAIL: new own-own ambiguity: Tuple{typeof(f), Any, Integer} | Tuple{typeof(f), Integer, Any}" in lines(F.out, "FAIL: ")
    @test F.code == 1 && startswith(verdict(F.out), "Verdict: FAIL — ")
end

@testset "a new own-external ambiguity fails" begin
    ext = lines(F.out, "FAIL: new own-external ambiguity: ")
    @test !isempty(ext) && all(startswith("FAIL: new own-external ambiguity: Tuple{typeof(==), Any, A} | "), ext)
    @test any(l -> occursin("Missing", l), ext)
    @test !any(l -> occursin("typeof(==)", l), lines(F.out, "FAIL: new own-own ambiguity: "))
    @test F.code == 1
    # each recorded ambiguity names an own method first
    own = Set(m["key"] for m in FAIL_JSON["methods"])
    @test all(a -> a["keys"][1] in own, FAIL_JSON["ambiguities"])
    # Test orders a pair by file; a method of a file that sorts before the own file comes first,
    # and the own key still comes first in the record
    @eval module OE
    using LinearAlgebra
    struct M <: AbstractMatrix{Float64} end
    Base.:*(::AbstractMatrix, ::M) = 1
    end
    raw = filter(p -> count(m -> parentmodule(m) === OE, p) == 1, collect(Test.detect_ambiguities(OE; recursive = true)))
    @test any(p -> parentmodule(p[1]) !== OE, raw)
    as = DD.ambiguities([OE], Set([OE]), OE)
    @test !isempty(as) && all(a -> a["kind"] == "own-external" && a["keys"][1] == "Tuple{typeof(*), AbstractMatrix, M}", as)
end

@testset "an ambiguity found through two own modules prints once" begin
    @test length(filter(l -> occursin("Sub.s)", l), lines(F.out, "FAIL: new own-own ambiguity: "))) == 1
    @test allunique(FAIL_JSON["ambiguities"])
end

@testset "a new piracy in a submodule fails" begin
    @test lines(F.out, "FAIL: new piracy: ") == ["FAIL: new piracy: Tuple{typeof(length), Symbol} at src/DDFail.jl:11"]
    @test F.code == 1
end

@testset "an extension's methods are own, its piracy is not scanned" begin
    @test "FAIL: new own-own ambiguity: Tuple{typeof(q), Any, Integer} | Tuple{typeof(q), Integer, Any}" in lines(F.out, "FAIL: ")
    @test !any(l -> occursin("Char", l), lines(F.out, "FAIL: new piracy: "))
    ms = FAIL_JSON["methods"]
    @test any(m -> m["module"] == "DDFailLinearAlgebraExt" && m["file"] == "ext/DDFailLinearAlgebraExt.jl", ms)
    # a module that an extension binds to a name of its own is no own module
    @test all(m -> startswith(m["module"], "DDFail"), ms)
end

@testset "--no-jet skips the JET step" begin
    @test lines(F.out, "INFO: jet: ") == ["INFO: jet: not run (--no-jet)"]
    @test isempty(lines(F.out, "INFO: new JET report:"))
    @test !any(endswith("-jet.json"), readdir(F.run))
end

# The comparison on given JSON files, for what a fixture cannot make on demand.
function sides(base, head; jet = Dict("base" => [], "head" => []))
    rundir = mktempdir(ROOT)
    for (s, d) in (("base", base), ("head", head))
        DD.write_json(joinpath(rundir, "$s.json"), d)
        haskey(jet, s) && DD.write_json(joinpath(rundir, "$s-jet.json"), Dict("reports" => jet[s]))
    end
    return rundir
end
side(s; deps = Dict("Foo" => "1.0.0")) = Dict("package" => "Fx", "side" => s, "julia" => "1.13.3",
    "tools" => Dict("Aqua" => "0.8.18"), "dependencies" => deps, "loaded" => [], "methods" => [], "ambiguities" => [],
    "piracies" => [], "fields" => [])
const DONE = DD.End(0, 0, false)

@testset "dependency drift is information" begin
    rd = sides(side("base"), side("head"; deps = Dict("Foo" => "1.1.0")))
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DONE); timeout = 600, jet = true)
    @test "INFO: dependency drift: Foo 1.0.0 -> 1.1.0" in ls
    @test status == 0 && last(ls) == "Verdict: PASS — 0 FAIL, 0 UNKNOWN, 1 INFO"
end

@testset "a JET step past its time is UNKNOWN alone" begin
    rd = sides(side("base"), side("head"); jet = Dict("base" => []))
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DD.End(9, 0, true)); timeout = 7, jet = true)
    @test "UNKNOWN: jet: head timed out after 7 s" in ls
    @test status == 0 && last(ls) == "Verdict: PASS — 0 FAIL, 1 UNKNOWN, 0 INFO"
    # without its JSON, the same end is a side past its limit
    rm(joinpath(rd, "head.json"))
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DD.End(9, 0, true)); timeout = 7, jet = true)
    @test "UNKNOWN: head timed out after 7 s" in ls && status == 3
    # a side that fails or gets a signal after its JSON exists loses its JET step alone
    rd = sides(side("base"), side("head"); jet = Dict("base" => []))
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DD.End(0, 1, false)); timeout = 7, jet = true)
    @test lines(join(ls, '\n'), "UNKNOWN: ") == ["UNKNOWN: jet: head ended with exit code 1"] && status == 0
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DD.End(15, 0, false)); timeout = 7, jet = true)
    @test "UNKNOWN: jet: head ended with signal 15" in ls && status == 0
    # without JET, the same ends give no verdict
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DD.End(15, 0, false)); timeout = 7, jet = false)
    @test "UNKNOWN: head ended by signal 15" in ls && status == 3
    # a real run: the head's JET step hangs in a macro that sleeps once JET is loaded; the step
    # gets its own limit, counted from the moment the head's JSON exists
    slow = "macro slow()\n    any(m -> nameof(m) === :JET, values(Base.loaded_modules)) && sleep(120)\n    nothing\nend\n@slow\na(x) = x"
    dir = fixture("DDJet", ["src/DDJet.jl" => mod("DDJet", "a(x) = x")], ["src/DDJet.jl" => mod("DDJet", slow)])
    # 40 s leaves the side time to load on a busy machine
    r = dd(dir, "HEAD~1", "--timeout", "40")
    @test lines(r.out, "UNKNOWN: ") == ["UNKNOWN: jet: head timed out after 40 s"]
    @test r.code == 0 && startswith(verdict(r.out), "Verdict: PASS — 0 FAIL, 1 UNKNOWN, ")
    @test time() - mtime(joinpath(r.run, "head.json")) >= 39
end

# an extension on a weak dependency that no environment provides and on one that the standard
# library provides: it is no own module, and its side loads
const CLEAN = fixture("DDClean",
    ["src/DDClean.jl" => mod("DDClean", "# a comment\nc(x) = x"),
     "ext/DDCleanNoSuchExt.jl" => mod("DDCleanNoSuchExt", "using DDClean, DDNoSuchPackage\nDDClean.c(x::Int) = x")],
    ["src/DDClean.jl" => mod("DDClean", "# another comment\nc(x) = x")];
    project = """

    [weakdeps]
    DDNoSuchPackage = "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f"
    LinearAlgebra = "37e2e46d-f89d-539d-b4ee-838fcccc9c8e"

    [extensions]
    DDCleanNoSuchExt = ["DDNoSuchPackage", "LinearAlgebra"]
    """)
const C = dd(CLEAN, "HEAD~1", "--no-jet")

@testset "a clean head passes" begin
    @test C.code == 0
    @test startswith(verdict(C.out), "Verdict: PASS — 0 FAIL, 0 UNKNOWN, ")
    @test isempty(lines(C.out, "INFO: added method:"))
    @test [m["name"] for m in DD.JSON.parsefile(joinpath(C.run, "head.json"))["methods"]] == ["c"]
end

@testset "the package path with a trailing slash or as ." begin
    for r in (dd(CLEAN * "/", "HEAD~1", "--no-jet"), dd(".", "HEAD~1", "--no-jet"; dir = CLEAN))
        @test r.code == C.code && verdict(r.out) == verdict(C.out)
        @test startswith(r.out, "DDClean: ")
    end
end

# One run without JET and one with --api of a package whose head adds abstract fields in the root
# module, in a submodule and in an extension, keeps one of the base, makes one concrete and changes
# the type of one.
const FIELDS_BASE = mod("DDFields", """
struct Old
    x::Any
end
struct Fixed
    x::Any
end
struct Narrowed
    x::Any
end""")
const FIELDS_HEAD = mod("DDFields", """
struct Old
    x::Any
end
struct Fixed
    x::Int
end
struct Narrowed
    x::Real
end
struct New
    y::Real
end
module Sub
struct Deep{T}
    v::AbstractVector{T}
end
end""")
const FIELDS = fixture("DDFields",
    ["src/DDFields.jl" => FIELDS_BASE,
     "ext/DDFieldsLinearAlgebraExt.jl" => mod("DDFieldsLinearAlgebraExt", "using DDFields, LinearAlgebra")],
    ["src/DDFields.jl" => FIELDS_HEAD,
     "ext/DDFieldsLinearAlgebraExt.jl" => mod("DDFieldsLinearAlgebraExt", "using DDFields, LinearAlgebra\nstruct ExtBad\n    x::Real\nend")];
    project = replace(FAIL_PROJECT, "DDFailLinearAlgebraExt" => "DDFieldsLinearAlgebraExt"))
const FD = dd(FIELDS, "HEAD~1", "--no-jet")
const FIELDS_JSON = DD.JSON.parsefile(joinpath(FD.run, "head.json"))
const FA = dd(FIELDS, "HEAD~1", "--api")

@testset "each side records its abstract fields" begin
    fb = DD.JSON.parsefile(joinpath(FD.run, "base.json"))
    for d in (fb, FIELDS_JSON)
        @test haskey(d, "fields") && all(r -> sort!(collect(keys(r))) == ["field", "fieldtype", "type"], d["fields"])
    end
    rec(d) = [(r["type"], r["field"], r["fieldtype"]) for r in d["fields"]]
    @test rec(fb) == [("DDFields.Fixed", "x", "Any"), ("DDFields.Narrowed", "x", "Any"), ("DDFields.Old", "x", "Any")]
    @test rec(FIELDS_JSON) == [("DDFields.Narrowed", "x", "Real"), ("DDFields.New", "y", "Real"), ("DDFields.Old", "x", "Any"),
        ("DDFields.Sub.Deep", "v", "AbstractArray{T, 1}")]
    @test DD.JSON.parsefile(joinpath(C.run, "head.json"))["fields"] == []
    # the API mode writes the record too
    @test rec(DD.JSON.parsefile(joinpath(FA.run, "head.json"))) == rec(FIELDS_JSON)
end

@testset "a new abstract field fails" begin
    @test lines(FD.out, "FAIL: ") == ["FAIL: new abstract field: DDFields.Narrowed.x::Real",
        "FAIL: new abstract field: DDFields.New.y::Real", "FAIL: new abstract field: DDFields.Sub.Deep.v::AbstractArray{T, 1}"]
    @test FD.code == 1 && startswith(verdict(FD.out), "Verdict: FAIL — 3 FAIL, 0 UNKNOWN, ")
end

@testset "an abstract field of the base does not fail" begin
    @test !any(l -> occursin("Old", l), lines(FD.out, "FAIL:"))
    @test !any(l -> occursin("Old", l), lines(FD.out, "INFO:"))
end

@testset "an abstract field that went away is information" begin
    @test "INFO: gone abstract field: DDFields.Fixed.x::Any" in lines(FD.out, "INFO: ")
    @test !any(l -> occursin("Fixed", l), lines(FD.out, "FAIL:"))
    @test lines(FD.out, "INFO: gone abstract field: ") ==
          ["INFO: gone abstract field: DDFields.Fixed.x::Any", "INFO: gone abstract field: DDFields.Narrowed.x::Any"]
    # the lines of each kind are sorted, whatever the order of the records
    rf(t) = Dict("type" => t, "field" => "x", "fieldtype" => "Any")
    ts = ["M.$c" for c in 'a':'z']
    ls = join(DD.compare(merge(side("base"), Dict("fields" => rf.(reverse(ts)))), side("head")), '\n')
    @test lines(ls, "INFO: gone abstract field: ") == ["INFO: gone abstract field: $t.x::Any" for t in ts]
    ls = join(DD.compare(side("base"), merge(side("head"), Dict("fields" => rf.(reverse(ts))))), '\n')
    @test lines(ls, "FAIL: new abstract field: ") == ["FAIL: new abstract field: $t.x::Any" for t in ts]
end

@testset "a changed abstract field type reads as new" begin
    @test "FAIL: new abstract field: DDFields.Narrowed.x::Real" in lines(FD.out, "FAIL: ")
    @test "INFO: gone abstract field: DDFields.Narrowed.x::Any" in lines(FD.out, "INFO: ")
end

@testset "an extension's abstract field is not read" begin
    @test !occursin("ExtBad", FD.out)
    @test !any(r -> occursin("ExtBad", r["type"]), FIELDS_JSON["fields"])
    # the extension has loaded on the head: its constructors are own methods
    @test any(m -> m["module"] == "DDFieldsLinearAlgebraExt" && m["name"] == "ExtBad", FIELDS_JSON["methods"])
end

@testset "the API mode gives no abstract field line" begin
    @test !occursin("abstract field", FA.out)
    @test FA.code == 0 && startswith(verdict(FA.out), "Verdict: PASS — 0 FAIL, 0 UNKNOWN, ")
end

# One run, without JET, of a package in a subdirectory of its repository, whose base holds an
# own-own ambiguity in a submodule and a piracy of a function of Base.Iterators; the head imports
# both functions into the root module, and extends a function of Statistics, which it adds.
const VIS_BASE = """
struct A end
module Sub
s(x::Integer, y) = 1
s(x, y::Integer) = 2
end
Base.Iterators.cycle(::Symbol) = 0"""
const VIS_HEAD = """
using Statistics
struct A end
module Sub
s(x::Integer, y) = 1
s(x, y::Integer) = 2
end
using .Sub: s
using Base.Iterators: cycle
Base.Iterators.cycle(::Symbol) = 0
Statistics.mean(::A) = 0"""
const VIS = fixture("DDVis", ["src/DDVis.jl" => mod("DDVis", VIS_BASE)], ["src/DDVis.jl" => mod("DDVis", VIS_HEAD)];
    headproject = "\n[deps]\nStatistics = \"10745b16-79ce-11e8-11f9-7d13ad32a3b2\"\n", sub = "lib/DDVis")
const V = dd(VIS, "HEAD~1", "--no-jet")
# One run, without JET, whose base has the dependency LinearAlgebra and whose head drops it and is
# resolved.
const DROP = fixture("DDDrop", ["src/DDDrop.jl" => mod("DDDrop", "using LinearAlgebra\na(x) = norm(x)")],
    ["src/DDDrop.jl" => mod("DDDrop", "a(x) = sqrt(sum(abs2, x))")];
    project = "\n[deps]\nLinearAlgebra = \"37e2e46d-f89d-539d-b4ee-838fcccc9c8e\"\n", headproject = "")
run(`$(Base.julia_cmd()) --startup-file=no --project=$DROP -e "using Pkg; Pkg.resolve(; io = devnull)"`)
const D = dd(DROP, "HEAD~1", "--no-jet")

@testset "a package in a subdirectory of its repository" begin
    @test startswith(V.out, "DDVis: ") && V.code == 0
    @test isfile(joinpath(V.run, "base.json")) && isfile(joinpath(V.run, "head.json"))
end

@testset "a name that the root module imports changes no finding" begin
    @test isempty(lines(V.out, "FAIL:")) && isempty(lines(V.out, "INFO: gone"))
    @test isempty(lines(V.out, "INFO: added method:"))
    @test startswith(verdict(V.out), "Verdict: PASS — 0 FAIL, 0 UNKNOWN, ")
end

@testset "a method on a generic of a package that the base did not load is not an added method" begin
    vb, vh = (DD.JSON.parsefile(joinpath(V.run, "$s.json")) for s in ("base", "head"))
    @test "Statistics" ∉ vb["loaded"] && "Statistics" ∈ vh["loaded"]
    mean = only(filter(m -> m["name"] == "mean", vh["methods"]))
    @test mean["generic"] == "external" && mean["generic_package"] == "Statistics"
    @test !any(l -> occursin("mean", l), lines(V.out, "INFO: added method:"))
    # the package of a generic is the root of its module
    @test only(filter(m -> m["name"] == "cycle", vh["methods"]))["generic_package"] == "Base"
    # a generic with no module, as of a function type that is no DataType, counts as on the base
    ext(p) = Dict("key" => "Tuple{F, Any} where F", "file" => "src/X.jl", "line" => 1, "generic" => "external",
        "generic_package" => p, "others" => [])
    added(p) = lines(join(DD.compare(side("base"), merge(side("head"), Dict("methods" => [ext(p)]))), '\n'), "INFO: added method:")
    @test length(added(nothing)) == 1 && isempty(added("Statistics"))
end

@testset "a head's manifest that lacks a dependency of the base stays out of the base tree" begin
    @test lines(D.out, "manifest: ") ==
          ["manifest: the head's Manifest.toml lacks LinearAlgebra of the base's [deps], so the base resolves its own"]
    @test isfile(joinpath(D.run, "base.json")) && isfile(joinpath(D.run, "head.json"))
    @test isempty(lines(D.out, "UNKNOWN:")) && D.code == 0
    @test DD.JSON.parsefile(joinpath(D.run, "base.json"))["manifest"] === false
end

@testset "a head that does not load fails with its error" begin
    dir = fixture("DDHeadBroken", ["src/DDHeadBroken.jl" => mod("DDHeadBroken", "a(x) = x")],
        ["src/DDHeadBroken.jl" => mod("DDHeadBroken", "error(\"broken head\")")])
    r = dd(dir, "HEAD~1", "--no-jet")
    l = only(lines(r.out, "FAIL: the head does not load: "))
    @test occursin("broken head", l)
    @test lines(r.out, "log: ") == ["log: $(joinpath(r.run, "head.log"))"]
    @test r.code == 1
end

@testset "a base that does not load gives no verdict" begin
    dir = fixture("DDBaseBroken", ["src/DDBaseBroken.jl" => mod("DDBaseBroken", "error(\"broken base\")")],
        ["src/DDBaseBroken.jl" => mod("DDBaseBroken", "a(x) = x")])
    r = dd(dir, "HEAD~1", "--no-jet")
    l = only(lines(r.out, "UNKNOWN: the base does not load: "))
    @test occursin("broken base", l)
    @test r.code == 3 && startswith(verdict(r.out), "Verdict: UNKNOWN — 0 FAIL, ")
end

@testset "an extension that does not load is a failed load of its side" begin
    # a package `name` whose extension on LinearAlgebra raises on the base or on the head
    function broken(name; on)
        x = "$(name)LinearAlgebraExt"
        ext(body) = mod(x, "using $name, LinearAlgebra\n$name.q(x::Integer, y) = 1\n$body")
        good, bad = ext(""), ext("$name.q(x, y::Integer) = 2\nerror(\"broken ext\")")
        base, head = on == "head" ? (good, bad) : (bad, good)
        dir = fixture(name, ["src/$name.jl" => mod(name, "function q end"), "ext/$x.jl" => base], ["ext/$x.jl" => head];
            project = replace(FAIL_PROJECT, "DDFailLinearAlgebraExt" => x))
        return dd(dir, "HEAD~1", "--no-jet")
    end
    head = broken("DDExtHead"; on = "head")
    l = only(lines(head.out, "FAIL: the head does not load: "))
    @test occursin("broken ext", l)
    @test lines(head.out, "log: ") == ["log: $(joinpath(head.run, "head.log"))"]
    @test head.code == 1
    base = broken("DDExtBase"; on = "base")
    @test occursin("broken ext", only(lines(base.out, "UNKNOWN: the base does not load: ")))
    @test base.code == 3 && isempty(lines(base.out, "FAIL:"))
end

@testset "a resolve error gives no verdict" begin
    dir = fixture("DDResolve", ["src/DDResolve.jl" => mod("DDResolve", "a(x) = x")], [];
        project = "", headproject = "\n[compat]\njulia = \"0.7\"\n")
    r = dd(dir, "HEAD~1", "--no-jet")
    @test length(lines(r.out, "UNKNOWN: head does not resolve: ")) == 1
    @test r.code == 3
end

@testset "a side past its time gives no verdict" begin
    # the head writes a counter every 0.1 s for at least 240 s while it loads; the module is
    # precompiled, so a process that the side starts runs the loop. The name, and so the UUID,
    # carries the pid of this test process, so that two runs at the same time share no precompile
    # lock; the killed precompilations leave temporary files in the fixture's compiled cache, which
    # the end of the file removes
    slow = "DDSlow$(getpid())"
    push!(MADE, joinpath(DEPOT_PATH[1], "compiled", "v$(VERSION.major).$(VERSION.minor)", slow))
    body = "for i in 1:2400\n    sleep(0.1)\n    write(joinpath(@__DIR__, \"..\", \"alive.txt\"), string(i))\nend"
    dir = fixture(slow, ["src/$slow.jl" => mod(slow, "a(x) = x")], ["src/$slow.jl" => mod(slow, body)])
    r = dd(dir, "HEAD~1", "--no-jet", "--timeout", "5")
    @test "UNKNOWN: head timed out after 5 s" in lines(r.out, "UNKNOWN: ")
    @test r.code == 3 && r.secs < 60
    alive = joinpath(dir, "alive.txt")
    n = isfile(alive) ? read(alive, String) : ""
    sleep(1.0)
    @test (isfile(alive) ? read(alive, String) : "") == n
    # a limit by which the precompilation has started: the kill reaches it; a loaded machine can
    # start the loop after 40 s, so a second run gets 150 s
    for t in ("40", "150")
        rm(alive; force = true)
        r = dd(dir, "HEAD~1", "--no-jet", "--timeout", t)
        @test "UNKNOWN: head timed out after $t s" in lines(r.out, "UNKNOWN: ")
        isfile(alive) && break
    end
    @test isfile(alive)
    n = isfile(alive) ? read(alive, String) : ""
    sleep(1.0)
    @test (isfile(alive) ? read(alive, String) : "") == n
    # an interrupt of the script kills the sides too
    rm(alive; force = true)
    buf = IOBuffer()
    p = run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $SCRIPT $dir "HEAD~1" --no-jet`); stdout = buf, stderr = devnull);
        wait = false)
    t0 = time()
    while !isfile(alive) && time() - t0 < 180
        sleep(0.2)
    end
    @test isfile(alive)
    kill(p, Base.SIGINT)
    wait(p)
    m = match(r"run directory (\S+)", String(take!(buf)))
    m === nothing || push!(MADE, m[1])
    n = isfile(alive) ? read(alive, String) : ""
    sleep(1.0)
    @test (isfile(alive) ? read(alive, String) : "") == n
    # a signal that the script did not send
    sig = fixture("DDSignal", ["src/DDSignal.jl" => mod("DDSignal", "a(x) = x")],
        ["src/DDSignal.jl" => mod("DDSignal", "__precompile__(false)\nccall(:kill, Cint, (Cint, Cint), getpid(), 9)")])
    r = dd(sig, "HEAD~1", "--no-jet")
    @test "UNKNOWN: head ended by signal 9" in lines(r.out, "UNKNOWN: ") && r.code == 3
    # a signal that the script did not send, and an exit with no result, give no verdict either
    rd = mktempdir(ROOT)
    ls, status = DD.analyse(rd, Dict("base" => DD.End(15, 0, false), "head" => DD.End(0, 1, false)); timeout = 5, jet = false)
    @test "UNKNOWN: base ended by signal 15" in ls && "UNKNOWN: head gave no result, exit code 1" in ls
    @test status == 3
end

@testset "a manifest of another Julia: neither side gets one" begin
    dir = fixture("DDForeign", ["src/DDForeign.jl" => mod("DDForeign", "a(x) = x")], [])
    manifest = "# This file is machine-generated - editing it directly is not advised\n\njulia_version = \"1.11.9\"\nmanifest_format = \"2.0\"\nproject_hash = \"da39a3ee5e6b4b0d3255bfef95601890afd80709\"\n\n[deps]\n"
    write(joinpath(dir, "Manifest.toml"), manifest)
    r = dd(dir, "HEAD~1", "--no-jet")
    @test lines(r.out, "manifest: ") ==
          ["manifest: Manifest.toml is resolved by another Julia than $VERSION, so neither side gets one, and the head runs from a copy without it"]
    @test read(joinpath(dir, "Manifest.toml"), String) == manifest
    @test r.code == 0
    for s in ("base", "head")
        @test DD.JSON.parsefile(joinpath(r.run, "$s.json"))["manifest"] === false
    end
    @test !any(startswith("DDForeign-"), readdir(r.run))
end

# The base tree and the head's copy both leave out `.githooks`, whose write the sandbox denies under
# ~/Research, where the run directory is; the foreign manifest makes the run write the copy.
@testset "a package with .githooks gets a verdict" begin
    dir = fixture("DDHooks", [".githooks/pre-commit" => "#!/bin/sh\nexit 0\n",
            "src/DDHooks.jl" => mod("DDHooks", "a(x) = x")], [])
    write(joinpath(dir, "Manifest.toml"),
        "julia_version = \"1.11.9\"\nmanifest_format = \"2.0\"\nproject_hash = \"da39a3ee5e6b4b0d3255bfef95601890afd80709\"\n\n[deps]\n")
    r = dd(dir, "HEAD~1", "--no-jet")
    @test r.code == 0
    @test startswith(verdict(r.out), "Verdict: PASS — ")
    @test only(lines(r.out, "manifest: ")) ==
          "manifest: Manifest.toml is resolved by another Julia than $VERSION, so neither side gets one, and the head runs from a copy without it"
end

# The API mode. One run of a package whose head keeps its API, with a public submodule, a submodule
# that is not public, a widened method and operator, a method on a type of LinearAlgebra and a
# deprecated name; one run of a package whose head removes public names, methods and a keyword;
# one run of a package whose head changes only a comment.
const API_KEEP_BASE = mod("DDApiKeep", """
using LinearAlgebra: Diagonal
export f, Sub, w, e, old, ⊕
public g
module Sub
export s
s(x) = x
end
module Hidden
export h
h(x) = x
end
f(x; a = 1) = x
g(x) = x
w(x::Int) = x
e(x::Diagonal{Int}) = x
old(x) = x
⊕(a::Int, b::Int) = a""")
const API_KEEP_HEAD = mod("DDApiKeep", """
using LinearAlgebra: Diagonal
export f, Sub, w, e, ⊕
public g
module Sub
export s
s(x) = x
end
module Hidden
export h
h(x) = x
end
f(x; a = 1) = x
g(x) = x
w(x::Integer) = x
e(x::Diagonal) = x
new(x) = x
@deprecate old(x) new(x)
⊕(a::Integer, b::Integer) = a""")
const LA_DEPS = "\n[deps]\nLinearAlgebra = \"37e2e46d-f89d-539d-b4ee-838fcccc9c8e\"\n"
const API_KEEP = fixture("DDApiKeep", ["src/DDApiKeep.jl" => API_KEEP_BASE], ["src/DDApiKeep.jl" => API_KEEP_HEAD];
    project = LA_DEPS)
const AK = dd(API_KEEP, "HEAD~1", "--api")
const AK_BASE = DD.JSON.parsefile(joinpath(AK.run, "base.json"))

const API_DROP = fixture("DDApiDrop",
    ["src/DDApiDrop.jl" => mod("DDApiDrop", """
    export a, b, c, Sub, k, n, V, p, q, r
    a(x) = x
    b(x) = x
    c(x) = x
    module Sub
    export s
    s(x) = x
    end
    k(x) = x
    n(x::Integer) = x
    n(x::String) = x
    struct V <: AbstractVector{Int} end
    Base.size(::V) = (1,)
    Base.getindex(::V, ::Int) = 1
    Base.length(::V) = 1
    struct Old end
    p(x::Old) = x
    q(x; tol = 1, maxit = 2) = x
    r(x; a = 1) = x
    export e
    const e = 1""")],
    ["src/DDApiDrop.jl" => mod("DDApiDrop", """
    export c, Sub, k, n, V, q, r, d, e
    b(x) = x
    c(x) = x
    d(x) = x
    module Sub
    t(x) = x
    end
    const k = 3
    n(x::Int) = x
    struct V <: AbstractVector{Int} end
    Base.size(::V) = (1,)
    Base.getindex(::V, ::Int) = 1
    q(x; tol = 1) = x
    r(x; kw...) = x""")])
const AD = dd(API_DROP, "HEAD~1", "--api")
# the lines that the API comparison prints
api_lines(out) = [l for l in split(out, '\n') if any(p -> startswith(l, p), ("FAIL: ", "UNKNOWN: ", "INFO: "))]

# an exported name that neither side defines is no public name
const API_SAME_BASE = replace(API_KEEP_BASE, "DDApiKeep" => "DDApiSame", "old, ⊕" => "old, ⊕, notyet")
const API_SAME = fixture("DDApiSame", ["src/DDApiSame.jl" => API_SAME_BASE],
    ["src/DDApiSame.jl" => replace(API_SAME_BASE, "g(x) = x" => "# unchanged\ng(x) = x")]; project = LA_DEPS)
const AS = dd(API_SAME, "HEAD~1", "--api")

@testset "the API mode runs the head after the base" begin
    for r in (AK, AD, AS)
        h = DD.JSON.parsefile(joinpath(r.run, "head.json"))
        @test haskey(h, "cover") && issubset(("names", "methods"), keys(h["cover"]))
    end
    dir = fixture("DDApiBaseBroken", ["src/DDApiBaseBroken.jl" => mod("DDApiBaseBroken", "error(\"broken base\")")],
        ["src/DDApiBaseBroken.jl" => mod("DDApiBaseBroken", "a(x) = x")])
    r = dd(dir, "HEAD~1", "--api")
    @test occursin("broken base", only(lines(r.out, "UNKNOWN: the base does not load: ")))
    @test !isfile(joinpath(r.run, "head.json")) && !isfile(joinpath(r.run, "head.error"))
    @test r.code == 3 && startswith(verdict(r.out), "Verdict: UNKNOWN — 0 FAIL, ")
    @test length(lines(r.out, "UNKNOWN: ")) == 1 && !isfile(joinpath(r.run, "head-driver.jl"))
end

@testset "the records hold the public names and the API methods" begin
    pub = Set((p["module"], p["name"], p["kind"]) for p in AK_BASE["public"])
    @test pub == Set([("", "f", "function"), ("", "g", "function"), ("", "Sub", "module"), ("", "w", "function"),
        ("", "e", "function"), ("", "old", "function"), ("", "⊕", "function"), ("Sub", "s", "function")])
    ms = AK_BASE["methods"]
    api(n) = only(unique(m["api"] for m in ms if m["name"] == n))
    @test api("f") === true && api("s") === true && api("h") === false
    @test only(m["kwargs"] for m in ms if m["key"] == "Tuple{typeof(f), Any}") == ["a"]
    @test all(m -> m["kwargs"] isa Vector, ms)
    # a default run writes the same fields, and no cover
    @test haskey(BASE_JSON, "public") && all(m -> haskey(m, "api") && haskey(m, "kwargs"), BASE_JSON["methods"])
    @test !haskey(HEAD_JSON, "cover")
    # an own method on an external generic is API, and so is a method of a public type
    vs = DD.JSON.parsefile(joinpath(AD.run, "base.json"))["methods"]
    @test only(m["api"] for m in vs if m["key"] == "Tuple{typeof(length), V}") === true
    @test only(m["api"] for m in vs if m["key"] == "Tuple{Type{V}}") === true
    @test only(m["api"] for m in vs if m["key"] == "Tuple{Type{Old}}") === false
    # the kinds of the public names; a module that the package binds is not scanned, nor is a
    # module's own name a public name of it
    @eval module PB
    using LinearAlgebra: LinearAlgebra
    export T, c, undefined_name, LinearAlgebra, S
    public X
    struct T end
    const c = 1
    module S
    export s
    s(x) = x
    end
    module X
    export x
    x(y) = y
    end
    end
    pb = Set((p, string(n), DD.kind(m, n)) for (p, m, n) in DD.public_bindings(PB))
    @test pb == Set([("", "T", "type"), ("", "c", "other"), ("", "LinearAlgebra", "module"),
        ("", "S", "module"), ("S", "s", "function"), ("", "X", "module"), ("X", "x", "function")])
    # a method is API where its generic is the type of the value of a public name: a function, a
    # callable object, or a type's constructor, also one whose signature has a type variable
    @eval module PC
    export fun, pf, P
    struct Fun end
    (::Fun)(x) = x
    const fun = Fun()
    struct PF{T} end
    (::PF{T})(x) where {T} = x
    const pf = PF{Int}()
    struct Hid end
    (::Hid)(x) = x
    const hid = Hid()
    struct P{T}
        x::T
    end
    end
    pcpub = DD.public_bindings(PC)
    pcapi(f) = [DD.public_generic(DD.gtype(m), pcpub) for m in methods(f)]
    @test pcapi(PC.fun) == [true] && pcapi(PC.pf) == [true] && pcapi(PC.hid) == [false]
    pctors = [m for m in DD.own_methods(Set([PC])) if occursin(r"^Tuple\{Type\{P[{}]", DD.key(m.sig, PC))]
    @test length(pctors) == 2 && any(m -> DD.gtype(m) isa UnionAll, pctors) &&
          all(m -> DD.public_generic(DD.gtype(m), pcpub), pctors)
end

@testset "the API mode gives only API lines" begin
    r = dd(FAIL, "HEAD~1", "--api")
    @test isempty(lines(r.out, "FAIL:"))
    @test !any(l -> occursin("ambiguity", l) || occursin("piracy", l) || occursin(r"jet"i, l) ||
                    occursin("dependency drift", l) || occursin("added method", l), api_lines(r.out))
    @test r.code == 0 && startswith(verdict(r.out), "Verdict: PASS")
    # the same fixture without --api fails on the new ambiguity and the new piracy
    @test "FAIL: new own-own ambiguity: Tuple{typeof(f), Any, Integer} | Tuple{typeof(f), Integer, Any}" in lines(F.out, "FAIL: ")
    @test !isempty(lines(F.out, "FAIL: new piracy: ")) && F.code == 1
end

@testset "a public name gone or demoted fails" begin
    ls = api_lines(AD.out)
    @test "FAIL: gone public name: a" in ls && "FAIL: gone public name: p" in ls
    @test "FAIL: no longer public: b" in ls
    # a name that the head still exports and no longer defines is gone
    @test "FAIL: gone public name: e" in ls
    @test lines(AD.out, "INFO: new public name: ") == ["INFO: new public name: d"]
    @test !any(l -> occursin(r"(: |typeof\()c\b", l), ls)
    @test AD.code == 1 && startswith(verdict(AD.out), "Verdict: FAIL — ")
    # the cover of the names: a name in a module that the head lacks, or that is no submodule, is gone
    @eval module NC
    using LinearAlgebra: LinearAlgebra
    export a
    a(x) = x
    b(x) = x
    const m = (x = 1,)
    module Sub
    export s
    s(x) = x
    end
    end
    pub(m, n) = Dict("module" => m, "name" => n)
    b = Dict("public" => [pub("", "a"), pub("", "b"), pub("", "z"), pub("Sub", "s"), pub("Gone", "x"), pub("m", "x"),
            pub("LinearAlgebra", "norm")], "methods" => [])
    st = [n["status"] for n in DD.cover(b, NC, Set([NC, NC.Sub]), DD.own_methods(Set([NC, NC.Sub])))["names"]]
    @test st == ["public", "demoted", "gone", "public", "gone", "gone", "gone"]
end

@testset "a public name of a public submodule" begin
    @test "FAIL: gone public name: Sub.s" in lines(AD.out, "FAIL: ")
    @test !any(l -> occursin("Sub.t", l), api_lines(AD.out))
    @test AD.code == 1
end

@testset "a name that changes kind loses its methods" begin
    @test !any(l -> endswith(l, ": k"), api_lines(AD.out))
    @test "FAIL: removed method: Tuple{typeof(k), Any} at src/DDApiDrop.jl:10" in lines(AD.out, "FAIL: ")
    @test AD.code == 1
end

@testset "a widened method is covered" begin
    @test "INFO: covered: Tuple{typeof(w), Int64} by Tuple{typeof(w), Integer}" in lines(AK.out, "INFO: ")
    # an operator of the root module, whose key prints its name quoted
    @test "INFO: covered: Tuple{typeof(:⊕), Int64, Int64} by Tuple{typeof(:⊕), Integer, Integer}" in lines(AK.out, "INFO: ")
    @test isempty(lines(AK.out, "FAIL:")) && AK.code == 0
end

@testset "a key that names a type of another package" begin
    c = only(lines(AK.out, "INFO: covered: Tuple{typeof(e), "))
    @test occursin("LinearAlgebra.Diagonal{Int64", c)
    @test isempty(lines(AK.out, "UNKNOWN:")) && isempty(lines(AK.out, "FAIL:"))
    @test AK.code == 0 && startswith(verdict(AK.out), "Verdict: PASS — 0 FAIL, 0 UNKNOWN, ")
end

@testset "a narrowed or deleted method is removed" begin
    fs = lines(AD.out, "FAIL: removed method: ")
    @test "FAIL: removed method: Tuple{typeof(n), Integer} at src/DDApiDrop.jl:11" in fs
    @test "FAIL: removed method: Tuple{typeof(n), String} at src/DDApiDrop.jl:12" in fs
    @test "FAIL: removed method: Tuple{typeof(a), Any} at src/DDApiDrop.jl:3" in fs
    @test AD.code == 1
end

@testset "an external generic needs an own cover" begin
    @test "FAIL: removed method: Tuple{typeof(length), V} at src/DDApiDrop.jl:16" in lines(AD.out, "FAIL: ")
    @test !any(l -> occursin("typeof(size)", l) || occursin("typeof(getindex)", l), api_lines(AD.out))
    @test AD.code == 1
end

@testset "a method of a deleted own type is removed" begin
    @test "FAIL: removed method: Tuple{typeof(p), Old} at src/DDApiDrop.jl:18" in lines(AD.out, "FAIL: ")
    @test isempty(lines(AD.out, "UNKNOWN:"))
    # the constructor of the internal type is no API
    @test !any(l -> occursin("Type{Old}", l), api_lines(AD.out))
    @test AD.code == 1
end

@testset "a key that does not evaluate gives no verdict" begin
    @eval module CV
    module Sub
    t(x) = x
    cv(x) = x
    end
    # an own submodule with the name of a loaded package
    module Test
    t(x) = x
    end
    cv(x) = x
    ⊕(a::Integer, b::Integer) = a
    # a function whose type has a gensym name, and a function that counts its calls
    const g = x -> x
    wg(x::typeof(g)) = x
    const HITS = Ref(0)
    hit(x) = (HITS[] += 1; Int)
    end
    own = Set([CV, CV.Sub, CV.Test])
    ms = DD.own_methods(own)
    cover(k) = DD.method_cover(k, CV, own, ms)
    c = cover("Tuple{typeof(cv), NoSuchPackage.T}")
    @test c["status"] == "unknown" && occursin("NoSuchPackage", c["error"]) && !occursin('\n', c["error"])
    @test cover("Tuple{typeof(cv), Int64}") == Dict("status" => "covered", "by" => "Tuple{typeof(cv), Any}")
    # an own name that is gone is a removal, a gone submodule that qualifies the key is not
    @test cover("Tuple{typeof(cv), Gone}")["status"] == "removed"
    @test cover("Tuple{typeof(Sub.gone), Any}")["status"] == "removed"
    @test cover("Tuple{typeof(GoneSub.t), Any}")["status"] == "unknown"
    @test cover("Tuple{typeof(GoneSub.Inner.t), Any}")["status"] == "unknown"
    @test cover("Tuple{typeof(Test.t), Int64}") == Dict("status" => "covered", "by" => "Tuple{typeof(Test.t), Any}")
    covered = Dict("status" => "covered", "by" => "Tuple{typeof(cv), Any}")
    @test cover("Tuple{typeof(cv), _1} where _1<:Real") == covered
    # a lower bound, in both directions, and a named tuple as a type parameter
    @test cover("Tuple{typeof(cv), _1} where Int64<:_1<:Real") == covered
    @test cover("Tuple{typeof(cv), _1} where Real>:_1>:Int64") == covered
    @test cover("Tuple{typeof(cv), Val{(a = 1, b = :c)}}") == covered
    # an operator of the root module, whose key quotes its name
    @test cover("Tuple{typeof(:⊕), Int64, Int64}") == Dict("status" => "covered", "by" => "Tuple{typeof(:⊕), Integer, Integer}")
    @test cover("Tuple{typeof(:⊖), Int64, Int64}")["status"] == "removed"
    # a gensym name, also in the key of a submodule's function, gives no verdict
    gk = DD.key(only(methods(CV.wg)).sig, CV)
    @test occursin("var\"#", gk) && cover(gk)["status"] == "unknown"
    for k in ("Tuple{typeof(cv), var\"##\"}", "Tuple{typeof(Sub.cv), var\"##\"}")
        gc = cover(k)
        @test gc["status"] == "unknown" && occursin("##", gc["error"]) && !occursin('\n', gc["error"])
    end
    @test cover("Vector{Int64}")["status"] == "unknown"
    # an error of another kind, and a key that is no type expression, which is not evaluated
    @test cover("Tuple{typeof(cv), Base.NoSuchName}")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), Any")["status"] == "unknown"
    @test cover("Tuple{typeof(cv) Any}")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), begin global HIT = 1; Int end}")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), identity(Int)}")["status"] == "unknown"
    @test cover("typeof(cv)")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), hit.(1)}")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), _1} where hit(1)<:_1<:Real")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), Val{(a = hit(1),)}}")["status"] == "unknown"
    @test cover("Tuple{typeof(cv), Val{(HIT = 1)}}")["error"] == "not a type expression"
    @test cover("Tuple{typeof(cv), Val{(HITS[] = 1,)}}")["error"] == "not a type expression"
    @test cover("Tuple{typeof(cv), _1} where Int64 == _1 == Real")["error"] == "not a type expression"
    @test cover("Tuple{typeof(cv), _1} where Int64<:_1>:Real")["error"] == "not a type expression"
    @test CV.HITS[] == 0 && !isdefined(CV, :HIT)
    # a type of another package is no cover
    @test cover("Tuple{typeof(sin), Float64}")["status"] == "removed"
    # analyse prints the unknown key, and gives no verdict without a FAIL line
    apiside(s, cover) = merge(side(s), Dict("public" => [], "methods" => []), cover === nothing ? Dict() : Dict("cover" => cover))
    m = Dict("key" => "Tuple{typeof(cv), NoSuchPackage.T}", "file" => "src/CV.jl", "line" => 3, "status" => "unknown",
        "error" => c["error"])
    rd = sides(apiside("base", nothing), apiside("head", Dict("names" => [], "methods" => [m])))
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DONE); timeout = 600, jet = false, api = true)
    @test "UNKNOWN: key: Tuple{typeof(cv), NoSuchPackage.T}: $(c["error"])" in ls
    @test status == 3 && startswith(last(ls), "Verdict: UNKNOWN — 0 FAIL, 1 UNKNOWN, ")
    # a FAIL line beside it gives the FAIL
    gone = Dict("module" => "", "name" => "cv", "status" => "gone")
    rd = sides(apiside("base", nothing), apiside("head", Dict("names" => [gone], "methods" => [m])))
    ls, status = DD.analyse(rd, Dict("base" => DONE, "head" => DONE); timeout = 600, jet = false, api = true)
    @test "FAIL: gone public name: cv" in ls && status == 1
end

@testset "a deprecated name passes" begin
    @test !any(l -> occursin("old", l), [lines(AK.out, "FAIL:"); lines(AK.out, "UNKNOWN:")])
    @test AK.code == 0
end

@testset "a removed keyword fails and a slurp covers" begin
    @test lines(AD.out, "FAIL: removed keyword: ") == ["FAIL: removed keyword: q maxit"]
    @test !any(l -> occursin(r"\br\b", l), lines(AD.out, "FAIL: removed keyword: "))
    @test AD.code == 1
    # a slurp of the base is a keyword name that only a slurp keeps
    kws(n, kw) = Dict("key" => "Tuple{typeof($n), Any}", "api" => true, "kwargs" => kw)
    # the keywords of a base method that is no API do not count; those of each head method do
    internal(n, kw) = merge(kws(n, kw), Dict("api" => false))
    b = merge(side("base"),
        Dict("public" => [], "methods" => [kws("u", ["kw..."]), kws("v", ["x"]), internal("i", ["x"]), kws("w", ["x"])]))
    h = merge(side("head"), Dict("public" => [], "methods" => [kws("u", ["a"]), kws("v", ["y...", "z"]), internal("w", ["x"])],
        "cover" => Dict("names" => [], "methods" => [])))
    @test lines(join(DD.compare_api(b, h), '\n'), "FAIL: removed keyword: ") == ["FAIL: removed keyword: u kw..."]
end

@testset "an unchanged package passes the API mode" begin
    @test isempty(lines(AS.out, "FAIL:")) && isempty(lines(AS.out, "UNKNOWN:"))
    @test startswith(verdict(AS.out), "Verdict: PASS — 0 FAIL, 0 UNKNOWN, ")
    @test AS.code == 0
    h = DD.JSON.parsefile(joinpath(AS.run, "head.json"))
    @test isempty(h["cover"]["methods"]) && all(n -> n["status"] == "public", h["cover"]["names"])
    @test length(h["cover"]["names"]) == 8 && !any(n -> n["name"] == "notyet", h["cover"]["names"])
end

foreach(d -> rm(d; recursive = true, force = true), MADE)
