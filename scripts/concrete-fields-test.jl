#!/usr/bin/env julia
#
# Checks for concrete-fields.jl:
#
#   julia --startup-file=no scripts/concrete-fields-test.jl
#
# The rule and the walk run in this process, each on a fixture module that is built once with
# `Core.eval` into a fresh `Module()` and never evaluated again: on Julia 1.12 and later a changed
# struct evaluated again into the same module is a new type. The command line runs on fixture
# packages under mktempdir(), each with a `Project.toml` and a `src/<Name>.jl` and no dependency.

using Test

const SCRIPT = joinpath(@__DIR__, "concrete-fields.jl")
const USAGE_LINE = "usage: concrete-fields.jl <package>"

include(SCRIPT)

"A package `name` under mktempdir() whose `src/<name>.jl` holds `source`."
function package(name, source)
    dir = realpath(mktempdir())
    write(joinpath(dir, "Project.toml"), "name = \"$name\"\nuuid = \"$(Base.UUID(rand(UInt128)))\"\n")
    mkpath(joinpath(dir, "src"))
    write(joinpath(dir, "src", "$name.jl"), source)
    return dir
end

# The precompile caches of the fixture packages go to a depot of their own, which is removed with
# the test's other temporary directories; the depots of this process follow it for everything else.
const DEPOT = mktempdir()

"""
Run concrete-fields.jl with `args`: the exit code, the lines of stdout and the text of stderr.
The run gets a working directory and a TMPDIR of its own, and the TMPDIR must be empty after it:
the script removes the directory of its result file, also where the load process ends by a signal.
"""
function run_cli(args...)
    out, err = IOBuffer(), IOBuffer()
    tmp, cwd = realpath(mktempdir()), realpath(mktempdir())
    julia = `$(Base.julia_cmd()) --startup-file=no $SCRIPT $(collect(args))`
    cmd = addenv(Cmd(julia; dir = cwd),
        "JULIA_DEPOT_PATH" => join([DEPOT; DEPOT_PATH], ':'), "TMPDIR" => tmp)
    proc = run(pipeline(ignorestatus(cmd); stdout = out, stderr = err))
    @test isempty(readdir(tmp))
    return proc.exitcode, filter(!isempty, split(String(take!(out)), '\n')), String(take!(err))
end

"A fresh module named `name` that holds the top-level statements of `body`."
function fixture(name::Symbol, body::Expr)
    m = Module(name)
    Core.eval(m, Expr(:toplevel, body.args...))
    return m
end

"The pairs `type => field` of the violations of `m`."
flagged(m) = [r.type => r.field for r in concrete_field_violations(m)]

@testset "concrete-fields.jl" verbose = true begin
    @testset "a type variable field passes" begin
        m = fixture(:TypeVars, quote
            struct S1{T}
                x::T
            end
            struct S1b{T <: AbstractArray}
                x::T
            end
        end)
        @test isempty(concrete_field_violations(m))
    end

    @testset "a Union with Nothing or Missing passes where the other member passes" begin
        m = fixture(:GoodUnions, quote
            struct S2{T}
                x::Union{Nothing, Vector{T}}
            end
            struct S2b
                x::Union{Missing, Int}
            end
            struct S2c{T}
                x::Union{Nothing, T}
            end
            struct S2d
                x::Union{Nothing, Missing}
            end
        end)
        @test isempty(concrete_field_violations(m))
    end

    @testset "every other Union is flagged" begin
        m = fixture(:BadUnions, quote
            struct U1
                x::Union{Int, Float64, String}
            end
            struct U2
                x::Union{Nothing, Matrix}
            end
            struct U3
                x::Union{Nothing, Missing, Int}
            end
            struct U4
                x::Union{Nothing, Union{Int, Float64}}
            end
            struct U5
                x::Union{Int, Float64}
            end
        end)
        @test flagged(m) == ["BadUnions.U$i" => :x for i in 1:5]
    end

    @testset "an abstract field type is flagged" begin
        m = fixture(:Abstracts, quote
            struct A1
                x::Function
            end
            struct A2
                x::Any
            end
            struct A3
                x::Real
            end
            struct A4
                x::Ref{Int}
            end
            struct A5{T}
                x::AbstractVector{T}
            end
            struct A6{T}
                x::Ref{T}
            end
            struct A7{K, V}
                x::AbstractDict{K, V}
            end
        end)
        @test flagged(m) == ["Abstracts.A$i" => :x for i in 1:7]
    end

    @testset "a UnionAll field is flagged" begin
        m = fixture(:UnionAlls, quote
            struct SomeWrapper{T, K, I, N, G}
                x::Int
            end
            struct W1
                x::Matrix
            end
            struct W2{T}
                x::Array{T}
            end
            struct W3{RT}
                forw_plan::SomeWrapper{RT, -1, false, 2}
            end
        end)
        @test flagged(m) ==
              ["UnionAlls.W1" => :x, "UnionAlls.W2" => :x, "UnionAlls.W3" => :forw_plan]
    end

    @testset "the check recurses into type parameters" begin
        m = fixture(:Parameters, quote
            struct P1
                x::Vector{Real}
            end
            struct P2
                x::Dict{Symbol, Any}
            end
            struct P3
                x::Vector{Function}
            end
            struct P4
                x::Vector{Float64}
            end
            struct P5{T}
                x::Dict{Symbol, Vector{T}}
            end
        end)
        @test flagged(m) == ["Parameters.P$i" => :x for i in 1:3]
    end

    @testset "a Vararg and a value parameter pass" begin
        m = fixture(:Values, quote
            struct V1{D, T}
                x::NTuple{D, T}
            end
            struct V2
                x::NTuple{3, Int}
            end
            struct V3{T}
                x::Array{T, 2}
            end
            struct V4
                x::Val{3}
            end
            struct V5
                x::Val{:a}
            end
            struct V6{D}
                x::NTuple{D, Real}
            end
        end)
        @test flagged(m) == ["Values.V6" => :x]
    end

    @testset "a Vararg with no count is flagged" begin
        m = fixture(:Unbounded, quote
            struct T1
                x::Tuple{Vararg{Int}}
            end
            struct T2{T}
                x::Tuple{Vararg{T}}
            end
            struct T3
                x::Tuple{Int, Vararg{Int}}
            end
        end)
        @test flagged(m) == ["Unbounded.T$i" => :x for i in 1:3]
    end

    @testset "only the module's own struct types are walked" begin
        sibling = fixture(:B, quote
            struct Bad
                x::Real
            end
        end)
        m = fixture(:A, quote
            struct ThatStruct
                x::Real
                y::Int
            end
            const Alias = ThatStruct
            mutable struct Mut
                n::Int
                x::AbstractVector
            end
            g(v) = () -> v
            const C = typeof(g(Any[1]))
            struct var"#Hidden"
                x::Any
            end
            abstract type Shape end
            struct Empty end
            const Imported = $(sibling).Bad
        end)
        @test fieldtypes(m.C) == (Vector{Any},)
        @test parentmodule(m.Imported) === sibling
        @test flagged(m) == ["A.Mut" => :x, "A.ThatStruct" => :x]
    end

    @testset "an instance alias, a Union alias, a primitive type and an unset global add nothing" begin
        m = fixture(:Aliases, quote
            struct P{T}
                x::T
                y::Real
            end
            const PInt = P{Int}
            const U = Union{Int, P{Int}}
            primitive type Prim 8 end
            global declared_only
        end)
        @test :declared_only in names(m; all = true)
        @test flagged(m) == ["Aliases.P" => :y]
    end

    @testset "a submodule is walked and its type is named with its path" begin
        m = fixture(:Outer, quote
            module Inner
            struct Deep
                x::Real
            end
            end
        end)
        r = concrete_field_violations(m)
        @test length(r) == 1
        @test string(only(r).type) == "Outer.Inner.Deep"
        @test only(r).field === :x
        @test only(r).fieldtype === Real
    end

    @testset "the violations are sorted and the function takes no keyword" begin
        m = fixture(:Sorted, quote
            struct Zed
                b::Real
                a::Any
            end
            # names(m; all = true) lists Alias before Alpha, so the walk finds Zed first
            const Alias = Zed
            struct Alpha{T}
                z::Vector{Any}
                ok::T
                y::Function
            end
        end)
        r1 = concrete_field_violations(m)
        r2 = concrete_field_violations(m)
        @test r1 == r2
        @test r1 isa Vector
        @test all(r -> keys(r) == (:type, :field, :fieldtype), r1)
        @test [(r.type, r.field) for r in r1] ==
              [("Sorted.Alpha", :z), ("Sorted.Alpha", :y), ("Sorted.Zed", :b), ("Sorted.Zed", :a)]
        @test [r.fieldtype for r in r1] == [Vector{Any}, Function, Real, Any]
        @test length(methods(concrete_field_violations)) == 1
        @test hasmethod(concrete_field_violations, Tuple{Module})
        @test !hasmethod(concrete_field_violations, Tuple{Module}, (:allow,))
    end

    @testset "the CLI prints the violations and exits 1" begin
        dir = package("CfBad", """
            module CfBad
            struct A
                x::Real
                n::Int
            end
            module Inner
            import ..A
            struct B{T}
                y::Ref{A}
                z::T
            end
            end
            struct C
                n::Int
            end
            end
            """)
        code, lines, err = run_cli(dir)
        @test code == 1
        @test lines ==
              ["CfBad.A.x::Real", "CfBad.Inner.B.y::Ref{CfBad.A}", "Verdict: FAIL — 2 violations"]
        @test !occursin("world", err)
    end

    @testset "a line prints the field type with the package's own show" begin
        dir = package("CfShow", """
            module CfShow
            abstract type Shape end
            Base.show(io::IO, ::Type{Shape}) = print(io, "a Shape")
            struct A
                s::Shape
            end
            end
            """)
        code, lines, _ = run_cli(dir)
        @test code == 1
        @test lines == ["CfShow.A.s::a Shape", "Verdict: FAIL — 1 violations"]
    end

    @testset "one violation fails too" begin
        dir = package("CfOne", "module CfOne\nstruct A\n    f::Function\nend\nend\n")
        code, lines, _ = run_cli(dir)
        @test code == 1
        @test lines == ["CfOne.A.f::Function", "Verdict: FAIL — 1 violations"]
    end

    @testset "the CLI passes a clean package" begin
        clean = package("CfClean", """
            module CfClean
            struct A{T}
                x::T
                v::Vector{Float64}
                u::Union{Nothing, Int}
            end
            end
            """)
        empty = package("CfNoStruct", "module CfNoStruct\nf(x) = x\nend\n")
        for dir in (clean, empty)
            code, lines, _ = run_cli(dir)
            @test code == 0
            @test lines == ["Verdict: PASS — 0 violations"]
        end
    end

    @testset "a package that does not load gives exit 3" begin
        dir = package("CfBroken", "module CfBroken\nf(x = \nend\n")
        code, lines, _ = run_cli(dir)
        @test code == 3
        @test length(lines) == 1
        @test startswith(only(lines), "UNKNOWN: the package does not load: ")
    end

    @testset "a load process that ends with another exit code or a signal gives exit 3" begin
        dir = package("CfExit", "module CfExit\n__init__() = exit(5)\nend\n")
        code, lines, _ = run_cli(dir)
        @test code == 3
        @test lines ==
              ["UNKNOWN: the package does not load: the process ended with exit code 5, signal 0"]
        # the exit codes of a verdict, from a process that printed none
        for (i, n) in enumerate((0, 1, 3))
            dir = package("CfExit$i", "module CfExit$i\n__init__() = exit($n)\nend\n")
            code, lines, _ = run_cli(dir)
            @test code == 3
            @test lines == [
                "UNKNOWN: the package does not load: the process ended with exit code $n, signal 0",
            ]
        end
        dir = package("CfKill",
            "module CfKill\n__init__() = ccall(:kill, Cint, (Cint, Cint), getpid(), 9)\nend\n")
        code, lines, _ = run_cli(dir)
        @test code == 3
        @test length(lines) == 1
        @test startswith(only(lines), "UNKNOWN: the package does not load: the process ended with")
        @test endswith(only(lines), "signal 9")
        # the exit codes 10, 11 and 13, which carry no verdict, from a package with a violation
        for n in (10, 11, 13)
            dir = package("CfVerdict$n",
                "module CfVerdict$n\nstruct A\n    x::Real\nend\n__init__() = exit($n)\nend\n")
            code, lines, _ = run_cli(dir)
            @test code == 3
            @test length(lines) == 1
            @test startswith(only(lines), "UNKNOWN: the package does not load: ")
        end
        # a result file that does not hold 0, 1 or 3, written by the package's own code
        for (i, s) in enumerate(("7", "", "0\n"))
            dir = package("CfFile$i",
                "module CfFile$i\n__init__() = (write(ARGS[end], $(repr(s))); exit(0))\nend\n")
            code, lines, _ = run_cli(dir)
            @test code == 3
            @test lines == [
                "UNKNOWN: the package does not load: the process ended with exit code 0, signal 0",
            ]
        end
    end

    @testset "bad arguments exit 2" begin
        dir = package("CfArgs", "module CfArgs\nend\n")
        noname, numbername, badtoml = realpath(mktempdir()), realpath(mktempdir()),
        realpath(mktempdir())
        write(joinpath(noname, "Project.toml"), "uuid = \"$(Base.UUID(rand(UInt128)))\"\n")
        write(joinpath(numbername, "Project.toml"), "name = 5\n")
        write(joinpath(badtoml, "Project.toml"), "name = \n")
        for args in ((), (dir, dir), (realpath(mktempdir()),), (noname,), (numbername,), (badtoml,))
            code, lines, err = run_cli(args...)
            @test code == 2
            @test isempty(lines)
            @test occursin(USAGE_LINE, err)
        end
    end
end
