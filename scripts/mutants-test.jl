#!/usr/bin/env julia
#
# Checks for mutants.jl. Run after any change to it, with the default Julia:
#
#   julia --startup-file=no mutants-test.jl
#
# A sandboxed process cannot create a `.git`, so the diff is given as text and the added lines
# directly; the command line is not run here.

using Test

module G
include(joinpath(@__DIR__, "mutants.jl"))
end

module M
include(joinpath(@__DIR__, "mutate.jl"))
end

const DIFF = """
diff --git a/src/a.jl b/src/a.jl
index 1111111..2222222 100644
--- a/src/a.jl
+++ b/src/a.jl
@@ -3,0 +4,2 @@ f(x) = 1
+g(x) = x < 1
+h(x) = x > 2
@@ -10 +12 @@ end
-k() = 0
+k() = 1
diff --git a/src/gone.jl b/src/gone.jl
deleted file mode 100644
--- a/src/gone.jl
+++ /dev/null
@@ -1,2 +0,0 @@
-x = 1
-y = 2
diff --git a/src/new.jl b/src/new.jl
new file mode 100644
--- /dev/null
+++ b/src/new.jl
@@ -0,0 +1,3 @@
+a = 1
+b = 2
+c = 3
"""

@testset "the added lines come from a zero-context diff" begin
    lines = G.added_lines(DIFF)
    @test lines["src/a.jl"] == Set([4, 5, 12])
    @test lines["src/new.jl"] == Set([1, 2, 3])
    @test !haskey(lines, "src/gone.jl")
end

const SOURCE = """
@enum Code::UInt8 OK SLOW BAD

function f(x, a)
    if x == a
        return OK
    end
    y = x < a && a >= 0 ? min(x, a) : clamp(x, zero(a), one(a))
    x > 0 || return BAD
    return y + 1
end
"""

"The mutants of `SOURCE` on `lines`, as (operator, from, to) triples."
triples(lines) = sort([(m.operator, m.from, m.to) for m in G.mutants(SOURCE, "src/f.jl", Set(lines),
    G.enum_members(SOURCE))])

@testset "one mutant per operator node on an added line" begin
    t = triples(1:11)
    for want in [
        ("comparison", "==", "!="), ("comparison", "<", "<="), ("comparison", ">=", ">"),
        ("comparison", ">", ">="), ("and-or", "&&", "||"), ("and-or", "||", "&&"),
        ("min-max", "min", "max"), ("clamp", "clamp(x, zero(a), one(a))", "x"),
        ("zero-one", "zero", "one"), ("zero-one", "one", "zero"),
        ("negate", "x == a", "!(x == a)"), ("negate", "x < a && a >= 0", "!(x < a && a >= 0)"),
        ("return-code", "OK", "SLOW"), ("return-code", "BAD", "OK"),
        ("literal", "0", "1"), ("literal", "1", "0")]
        @test want in t
    end
    # the @enum line itself is no mutation site of a return code
    @test count(x -> x[1] == "return-code", t) == 2
    # each statement of a block with more than one is deleted: the guard, the assignment, the if
    deleted = [x[2] for x in t if x[1] == "delete"]
    @test "x > 0 || return BAD" in deleted
    @test "y = x < a && a >= 0 ? min(x, a) : clamp(x, zero(a), one(a))" in deleted
    @test any(startswith("if x == a"), deleted)
    # the body of the `if` holds one statement, so its `return OK` is not deleted
    @test !("return OK" in deleted)
    @test all(x -> x[3] == "", filter(x -> x[1] == "delete", t))
    # a statement of the file itself is deleted too
    @test "@enum Code::UInt8 OK SLOW BAD" in deleted
    # an operand, a branch, a term: each replaces its node, in parentheses
    for want in [("drop-operand", "y + 1", "(y)"), ("drop-operand", "y + 1", "(1)"),
        ("ternary-branch", "x < a && a >= 0 ? min(x, a) : clamp(x, zero(a), one(a))", "(min(x, a))"),
        ("ternary-branch", "x < a && a >= 0 ? min(x, a) : clamp(x, zero(a), one(a))",
            "(clamp(x, zero(a), one(a)))"),
        ("drop-term", "x < a && a >= 0", "(x < a)"), ("drop-term", "x < a && a >= 0", "(a >= 0)"),
        ("drop-term", "x > 0 || return BAD", "(x > 0)")]
        @test want in t
    end
end

@testset "a power keeps its base, and abs its argument" begin
    src = "f(x) = abs(x)^2\n"
    t = sort([(m.operator, m.from, m.to) for m in G.mutants(src, "f.jl", Set([1]), Vector{String}[])])
    @test ("drop-operand", "abs(x)^2", "(abs(x))") in t
    @test ("drop-operand", "abs(x)", "(x)") in t
    @test !(("drop-operand", "abs(x)^2", "(2)") in t)
end

@testset "only the added lines are mutated" begin
    t = triples([8])
    @test ("and-or", "||", "&&") in t
    @test ("comparison", ">", ">=") in t
    @test ("return-code", "BAD", "OK") in t
    @test !(("comparison", "==", "!=") in t)
    @test isempty(triples(Int[]))
end

@testset "every mutant applies at its byte position and parses" begin
    ms = G.mutants(SOURCE, "src/f.jl", Set(1:11), G.enum_members(SOURCE))
    @test length(ms) == length(unique((m.at, m.to) for m in ms))
    for m in ms
        @test String(codeunits(SOURCE)[m.at:(m.at + ncodeunits(m.from) - 1)]) == m.from
        text = M.mutated_at(SOURCE, m.from, m.to, m.at)
        @test text != SOURCE
        @test G.JuliaSyntax.parseall(G.JuliaSyntax.SyntaxNode, text; filename = "f.jl") isa
              G.JuliaSyntax.SyntaxNode
    end
end

@testset "a written list is valid for mutate.jl" begin
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/mutants-test")))
    mkpath(joinpath(dir, "src"))
    write(joinpath(dir, "src", "f.jl"), SOURCE)
    ms = G.mutants(SOURCE, "src/f.jl", Set(1:11), G.enum_members(SOURCE))
    list = joinpath(dir, "mutants.toml")
    G.write_list(list, ms)
    read = M.read_list(list)
    @test read isa Vector
    @test length(read) == length(ms)
    # the names are unique and carry the file and the line
    @test length(unique(first.(read))) == length(read)
    @test all(n -> occursin("src/f.jl:", n), first.(read))
    # the literal `0` occurs twice in the file; its mutant names its position, so it is valid
    @test all(isnothing, M.invalid_all(dir, read))
end
