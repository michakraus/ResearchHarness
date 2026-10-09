#!/usr/bin/env julia
#
# Every method of a Julia name, with its signature and location, **without loading the package**.
#
#     julia --startup-file=no julia-methods.jl <package-dir> <name> [<name> …]
#     julia --startup-file=no julia-methods.jl <package-dir> --all
#
# `--startup-file=no` is not optional. Without it the startup file loads Revise, whose file watcher
# sprays EMFILE errors over stdout and can bury the report.
#
# This is the static half of the routing in `~/.claude/CLAUDE.md`, *Where grep is the wrong tool*:
#
#   * real dispatch — which method actually runs for these arguments — is Kaimon's `search_methods`
#     on a warm session, and nothing else answers it;
#   * **this** answers "what methods exist and where", for a package that may not load;
#   * callers are `julia-callers.jl` where the package loads, and grep otherwise.
#
# Why this exists rather than the code graph: the graph's node key is
# `UNIQUE(project, qualified_name)` with no signature in it, so all methods of one name in one file
# collapse to a single node and the last one parsed wins: 23 definitions of one name in one file
# become one node pointing at the last. A module-qualified definition is worse: it is filed under
# the module, so `ExampleBase.tableau` is not recorded as `tableau` at all. On a file of 60
# `ExampleBase.tableau` definitions, Fatou reports 60 and the graph reports 0.
#
# What it does not do. Fatou resolves per *file*: `documentSymbol` is exact, `workspace/symbol` is
# lossy (2 hits of 46 in one measurement), so this walks the files itself rather than asking for a
# workspace-wide answer. It therefore reports **definitions**, not uses, and it says nothing about
# which method a given call dispatches to.

include(joinpath(@__DIR__, "fatou-lsp.jl"))
using .FatouLSP

"Julia sources under `root`, `src/` first, skipping the usual generated and vendored trees."
function julia_files(root::String)
    skip = (".git", "docs/build", "docs/.CondaPkg", ".kaimon", ".claude", "legacy")
    out = String[]
    for (dir, _, files) in walkdir(root)
        any(occursin(s, dir) for s in skip) && continue
        for f in files
            endswith(f, ".jl") && push!(out, joinpath(dir, f))
        end
    end
    order(p) = (occursin("/src/", p) ? 0 : occursin("/test/", p) ? 2 : 1, p)
    return sort(out; by = order)
end

"The bare name of a symbol Fatou reported, with any `Mod.` prefix removed."
bare(name::AbstractString) = (i = findlast('.', name); i === nothing ? name : name[(i + 1):end])

# LSP `SymbolKind`, and the only kind Fatou attaches a signature to. Without this filter a struct
# **field** of the same name counts as a method: a name with 33 methods, which 16 structs also
# hold as a field, reports 49. Every symbol of kind 12 carries a `detail`. No symbol of
# any other kind carries one — kind 8 fields, kind 23 structs, kind 14 constants, kind 11 abstract
# types, kind 15 strings and kind 2 modules.
# Macro definitions are kind 12 and are reported, as they were before.
const SYMBOL_KIND_FUNCTION = 12

"""
    methods_in(root; names) -> Vector{NamedTuple}

Walk every Julia file under `root` in one LSP session and collect the **function** symbols whose
bare name is in `names`. Pass an empty `names` for everything. Fields, structs, abstract types and
constants are skipped — see `SYMBOL_KIND_FUNCTION`.
"""
function methods_in(root::String; names = String[])
    files = julia_files(root)
    isempty(files) && return NamedTuple[]
    wanted = Set(names)
    found = NamedTuple[]
    io = lsp_open()
    try
        initialize(io, root)
        id = 10
        for path in files
            for s in document_symbol(io, path; id = (id += 1))
                nm = get(s, "name", "")
                isempty(nm) && continue
                get(s, "kind", -1) == SYMBOL_KIND_FUNCTION || continue
                (isempty(wanted) || bare(nm) in wanted) || continue
                line = get(get(get(s, "range", Dict()), "start", Dict()), "line", -1)
                push!(found, (name = nm, detail = get(s, "detail", ""),
                    file = relpath(path, root), line = line + 1))
            end
        end
    finally
        # Not discarded: a false here means a leaked server, and the warning inside says how to
        # clear it. One run leaking is a nuisance; a sweep over 38 packages leaking is a gigabyte.
        lsp_close(io) || @warn "julia-methods: the fatou lsp server for $root was left running"
    end
    return found
end

function main(args)
    length(args) >= 2 || error("usage: julia-methods.jl <package-dir> <name> [<name> …]\n" *
                               "   or: julia-methods.jl <package-dir> --all")
    root = abspath(expanduser(args[1]))
    isdir(root) || error("no such directory: $root")
    names = args[2] == "--all" ? String[] : collect(args[2:end])

    t0 = time()
    found = methods_in(root; names)
    elapsed = round(time() - t0; digits = 1)

    if isempty(found)
        println("no methods found in ", relpath(root), " (", elapsed, "s)")
        println("An empty result is not a negative: Fatou reports definitions per file, and a name")
        println("defined only inside a macro or an `@eval` is invisible to any parser. Check with")
        println("`julia-callers.jl` on a loaded session, or grep.")
        return 1
    end

    for nm in sort(unique(bare.(getfield.(found, :name))))
        hits = filter(f -> bare(f.name) == nm, found)
        println("\n", nm, " — ", length(hits), " method(s)")
        for h in hits
            println("  ", rpad(string(h.file, ":", h.line), 52), h.name, h.detail)
        end
    end
    println("\n", length(found), " method(s) in ", length(unique(getfield.(found, :file))),
        " file(s), ", elapsed, "s. Definitions only — no dispatch, no callers.")
    return 0
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
