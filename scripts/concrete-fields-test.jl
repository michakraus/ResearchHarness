#!/usr/bin/env julia
#
# Checks for concrete-fields.jl:
#
#   julia --startup-file=no scripts/concrete-fields-test.jl
#
# The rule and the walk run in this process, each on a fixture module that is built once with
# `@eval` into a fresh `Module()` and never evaluated again: on Julia 1.12 and later a changed
# struct evaluated again into the same module is a new type.

using Test

include(joinpath(@__DIR__, "concrete-fields.jl"))

"A fresh module named `name` that holds the top-level statements of `body`."
function fixture(name::Symbol, body::Expr)
    m = Module(name)
    Core.eval(m, Expr(:toplevel, body.args...))
    return m
end

"The pairs `type => field` of the violations of `m`."
flagged(m) = [r.type => r.field for r in concrete_field_violations(m)]

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
    end)
    @test flagged(m) == ["BadUnions.U$i" => :x for i in 1:4]
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
    end)
    @test flagged(m) == ["Abstracts.A$i" => :x for i in 1:5]
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
    @test flagged(m) == ["UnionAlls.W1" => :x, "UnionAlls.W2" => :x, "UnionAlls.W3" => :forw_plan]
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
        abstract type Shape end
        struct Empty end
        const Imported = $(sibling).Bad
    end)
    @test fieldtypes(m.C) == (Vector{Any},)
    @test parentmodule(m.Imported) === sibling
    @test flagged(m) == ["A.Mut" => :x, "A.ThatStruct" => :x]
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
