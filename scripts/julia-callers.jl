#!/usr/bin/env julia
#
# Who calls this function, answered from the running system rather than from a text search.
#
# This is the check behind the claim in `Environment/Notes/Helpers-and-MCPs.md` that a live Julia
# session answers the caller question exactly, including through module-qualified method
# definitions — the idiom a static index of this tree cannot see at all.
#
# It works by enumerating every method whose *defining* module is one of the targets, then
# scanning each method's lowered IR for a `GlobalRef` to the function. The defining module of a
# method is not where its generic lives: `Base.length(p::Problem) = nsamples(p)`, written in
# module `Example`, is a method of `Base.length` whose `m.module` is `Example`. Enumerating
# `names(M)` alone therefore misses it, which is the same class of miss that the static graph
# makes for a different reason.
#
# Usage, inside a session that has already loaded the packages of interest:
#
#     include(".../julia-callers.jl")
#     callers(ExampleBase.nsamples, [Example, Other])
#     dead(Example.compute_difference, [Example])
#
# What it cannot do, and these are not incidental:
#   * it sees only what is **loaded**. A package that does not load is invisible, and one
#     session sees only its own dependency cone.
#   * it sees the **manifest-resolved** copy in `~/.julia/packages/`, not the working tree. Line
#     numbers and even method sets can differ from the code you are about to edit.
#   * test files and unloaded package extensions are not part of the running system, so their
#     call sites do not appear. Neither does a file that is `include`d nowhere — which is a
#     feature: for a file whose `include` is commented out, both grep and the static graph report
#     its call sites as live.
#
# So a `dead` verdict from this script means "nothing loaded calls it", never "nothing calls it".
# For the second claim, sweep the text of all 38 repositories as well.

"""
    methods_defined_in(targets) -> Vector{Method}

Every method whose defining module is one of `targets`, found by walking the module tree from
`Main` and taking the method tables of every function reachable from it.
"""
function methods_defined_in(targets)
    seen = Set{Method}()
    out = Method[]
    stack = Module[Main]
    visited = Set{Module}()
    while !isempty(stack)
        M = pop!(stack)
        M in visited && continue
        push!(visited, M)
        for nm in names(M; all = true, imported = true)
            isdefined(M, nm) || continue
            v = try
                getfield(M, nm)
            catch
                continue
            end
            v isa Module && push!(stack, v)
            v isa Function || continue
            for m in methods(v)
                if m.module in targets && !(m in seen)
                    push!(seen, m)
                    push!(out, m)
                end
            end
        end
    end
    return out
end

"""
    globalrefs(statement) -> Vector{GlobalRef}

Every `GlobalRef` in one lowered-IR statement, including those nested inside an `Expr`.
"""
function globalrefs(st)
    found = GlobalRef[]
    walk(x) = x isa GlobalRef ? push!(found, x) :
              x isa Expr ? foreach(walk, x.args) : nothing
    walk(st)
    return found
end

"""
    callers(target::Function, targets) -> Vector{String}

Every method defined in `targets` whose lowered IR references `target`, as
`module.name @ file:line`. Matching is on the `GlobalRef`, not on the printed form of the
statement, so a variable that merely shares the name does not match.
"""
function callers(target::Function, targets)
    name = nameof(target)
    owner = parentmodule(target)
    out = String[]
    for m in methods_defined_in(targets)
        ir = try
            Base.uncompressed_ir(m)
        catch
            continue
        end
        for st in ir.code, g in globalrefs(st)
            g.name === name || continue
            resolves = g.mod === owner ||
                       (isdefined(g.mod, name) && getfield(g.mod, name) === target)
            if resolves
                push!(out, string(m.module, ".", m.name, " @ ",
                    basename(string(m.file)), ":", m.line))
                break
            end
        end
    end
    return sort(unique(out))
end

"""
    dead(target::Function, targets) -> Bool

`true` when nothing loaded calls `target`. Read the caveats in this file's header before
reporting that as dead code: it is a statement about the running system, not about the tree.
"""
dead(target::Function, targets) = isempty(callers(target, targets))
