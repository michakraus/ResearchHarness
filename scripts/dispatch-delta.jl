# The dispatch delta of a head against a base: what a branch adds to the method table, and the new
# ambiguities, piracies, abstract fields and stale explicit imports, from both trees loaded side by
# side.
#
#   julia --startup-file=no dispatch-delta.jl <package> <base> [--timeout <s>] [--no-jet] [--api]
#
# <package> is the package's directory: its working tree, as it is, is the head. <base> is a git ref
# of it. The base goes with base-tree.jl into <run>/<Pkg>-base-<sha7>, under the run directory
# ~/Research/.scratch/dispatch-delta/<Pkg>-<stamp>-<pid>/. The head's Manifest.toml goes into the
# base tree, so that both sides load the same versions, where it holds every package under [deps]
# of the base; else the base resolves its own. Where another minor version of Julia resolved the
# head's Manifest.toml or test/Manifest.toml, neither side gets one, and the head runs from a copy
# without them, as in run-tests.jl. Each side then loads in a fresh process group of its own, both
# at once (with --api, one after the other), as run-tests.jl loads a driver: --project=<tree>,
# the harness environment last in LOAD_PATH, TestEnv.activate(). Its own modules are the
# package's module tree and each extension that loads once the side loads the [weakdeps] that its
# test environment provides. It writes <run>/<side>.json, then runs JET into
# <run>/<side>-jet.json; its output goes to <run>/<side>.log.
# --timeout gives each side, and then each JET step, that many seconds (600 by default); past it,
# the side's process group is killed.
#
# The lines of the output:
#
#   FAIL: new own-own ambiguity: <key> | <key>          both methods in own modules
#   FAIL: new own-external ambiguity: <own> | <other>
#   FAIL: new piracy: <key> at <file>:<line>            Aqua's piracy hunt on the module tree, not ext/
#   FAIL: new abstract field: <type>.<field>::<field type>
#                                                       a field of the module tree, not ext/, whose
#                                                       type is not concrete up to type variables
#   FAIL: new stale import: <module>: <name> at <file>:<line>
#                                                       no file of test/, docs/, scripts/ or ext/
#                                                       names <module>.<name>
#   FAIL: the head does not load: <error>               also an extension whose triggers the test
#                                                       environment provides and that does not load
#   UNKNOWN: the base does not load: <error>
#   UNKNOWN: <side> does not resolve: <error>           TestEnv.activate() failed
#   UNKNOWN: <side> timed out after <n> s
#   UNKNOWN: <side> ended by signal <n>                 a signal that the script did not send
#   UNKNOWN: <side> gave no result, exit code <n>       no JSON and no error file
#   UNKNOWN: jet: <side> timed out after <n> s          leaves the exit code to the other analyses,
#   UNKNOWN: jet: <side> ended with <signal or code>    as does a JET step that ends the side
#   UNKNOWN: stale imports: <module>: <reason>          ExplicitImports cannot analyse the module or
#                                                       raised on it, on either side; leaves the exit
#                                                       code to the other analyses
#   UNKNOWN: stale imports: ExplicitImports does not load: <error>
#   INFO: added method: <key> at <file>:<line>          a new method of a generic that the base has,
#     other: <key> at <file>:<line>                     with every other method of an own generic and
#                                                       the intersecting ones of an external generic;
#                                                       the generic of a Core.kwcall method is its
#                                                       keyword function, and an external generic
#                                                       counts where the base loaded its package
#   INFO: new JET report: <type>: <message> in <key>
#   INFO: gone piracy | gone own-own ambiguity | gone own-external ambiguity | gone JET report: ...
#   INFO: gone abstract field: <type>.<field>::<field type>
#   INFO: new stale import, used in <dirs>: <module>: <name>
#                                                       a file of those directories names
#                                                       <module>.<name>
#   INFO: gone stale import: <module>: <name>
#   INFO: dependency drift: <name> <base version> -> <head version>
#   Verdict: <PASS|FAIL|UNKNOWN> — <f> FAIL, <u> UNKNOWN, <i> INFO
#
# Each side also records its public names: those with Base.ispublic that are defined in the root
# module and in each submodule that is a public name of its parent, recursively. A method is API
# where its generic is the value of a public name of those modules (a function, a callable object,
# or a type's constructor), or an external generic; its record holds its keyword names. --api
# compares the API of the head with that of the base, typically the last release tag: the base side
# runs first, then the head side, which reads base.json and writes into head.json its cover of each
# base public name and of each base API method whose key it lacks. A base API method is covered
# where an own method of the head takes its signature (`sig <: m.sig`); its key is evaluated in
# the head's root module, with each leading qualifier that the root does not bind and that names a
# loaded package replaced by that package. --api runs no JET, records no stale import, and prints
# these lines in place of the comparison lines above; the lines of a side that gives no records
# stay:
#
#   FAIL: gone public name: <module.>name            the head does not define it in that module
#   FAIL: no longer public: <module.>name            the head defines it there, not public
#   FAIL: removed method: <key> at <file>:<line>     no own head method covers it; also a key that
#                                                    names an own name that the head lacks
#   FAIL: removed keyword: <function> <name>         no head method of the function takes it; a
#                                                    keyword slurp `kw...` takes every name
#   UNKNOWN: key: <key>: <error>                     the key does not parse or evaluate in the head,
#                                                    also where it names a gensym name
#   INFO: covered: <base key> by <head key>
#   INFO: new public name: <module.>name
#
# --api compares no structure of a public type, its fields, type parameters and supertype, and a
# name that the head declares `public` in place of `export` stays public.
#
# The key of a method is its signature with the full path of each name that Base and Core do not
# export, less the path of the package's root module, so that a `using` in the root module changes
# no key, with its type variables renamed _1, _2, … by position and the digits of gensym names
# stripped. A head that only reorders the `where` list of a method therefore changes its key: a
# finding of that method reads as new, and its old key as gone.
#
# Each side also records each field of the struct types of the root module and its submodules whose
# type is not concrete up to type variables, by concrete_field_violations of concrete-fields.jl; the
# extension modules are not read. The record of a field is the path of its struct from the root
# module, such as <Pkg>.Sub.S, its name, and its type printed by `show`, and all three are its key:
# a field whose abstract type changes, or whose struct moves to another module or renames a type
# variable, reads as new, and its old record as gone.
#
# Each side also records the stale explicit imports of its own modules: the rows with `stale` of
# ExplicitImports' improper_explicit_imports(<root>; strict = false), whose result for the root
# module holds the modules below it and below each loaded extension. A module for which
# `strict = true` returns `nothing`, as ExplicitImports cannot read part of it, gets no records. The
# key of a stale import is its module and its name, so an import that moves to another line is not
# new. A new one that a file of test/, docs/, scripts/ or ext/ of the side's tree names as
# <module>.<name>, word bounded, in a .jl or .md file, is information: such a caller reaches the name
# through the import, and the caller is what changes.
#
# Exit 0: PASS. 1: a FAIL line. 2: bad arguments. 3: no verdict — a base that does not load, a side
# that does not resolve or that timed out, an `UNKNOWN: key` line, or a missing ExplicitImports —
# and no FAIL line.

module BaseTree
include(joinpath(@__DIR__, "base-tree.jl"))
end

# run-tests.jl puts the harness's Julia environment first in LOAD_PATH, where JSON is; a side
# appends it instead.
module RunTests
include(joinpath(@__DIR__, "run-tests.jl"))
end

# concrete-fields.jl defines a `USAGE` and a `main` of its own
module ConcreteFields
include(joinpath(@__DIR__, "concrete-fields.jl"))
end

using JSON: JSON
using Dates: Dates
using Pkg: Pkg
using Test: Test
using TOML: TOML

const SCRIPT = @__FILE__
const HARNESS_ENV = RunTests.HARNESS_ENV
const USAGE = "usage: dispatch-delta.jl <package> <base> [--timeout <s>] [--no-jet] [--api]"

"""
The arguments as `(; pkg, base, name, timeout, jet, api)`, or the message that names a bad one.
Every argument that starts with `-` is an option.
"""
function arguments(args)
    pos, timeout, jet, api = String[], 600, true, false
    rest = collect(String, args)
    while !isempty(rest)
        a = popfirst!(rest)
        if a == "--no-jet"
            jet = false
        elseif a == "--api"
            api = true
        elseif a == "--timeout"
            t = isempty(rest) ? nothing : tryparse(Int, popfirst!(rest))
            (t === nothing || t < 1) && return "`--timeout` needs a whole number of seconds, 1 or more"
            timeout = t
        elseif startswith(a, "-")
            return "unknown option $a"
        else
            push!(pos, a)
        end
    end
    isempty(pos) && return "missing <package>"
    length(pos) == 1 && return "missing <base>"
    length(pos) > 2 && return "one <package> and one <base>, not $(join(pos, ", "))"
    pkg, base = rstrip(normpath(abspath(expanduser(pos[1]))), '/'), pos[2]
    isempty(base) && return "<base> is empty"
    success(pipeline(`git -C $pkg rev-parse --is-inside-work-tree`; stdout = devnull, stderr = devnull)) ||
        return "$pkg is not a git repository"
    project = joinpath(pkg, "Project.toml")
    isfile(project) || return "$pkg has no Project.toml"
    name = get(TOML.parsefile(project), "name", nothing)
    name isa String || return "$project has no name"
    success(pipeline(`git -C $pkg rev-parse --quiet --verify $(base * "^{commit}")`; stdout = devnull, stderr = devnull)) ||
        return "<base> $base is no commit of $pkg"
    return (; pkg, base, name, timeout, jet, api)
end

"""
The type of `sig` with each type variable of its `UnionAll` chain renamed `_1`, `_2`, … by its
position, and its bounds kept, with the earlier variables renamed in them.
"""
function renamed(sig)
    vars, body = TypeVar[], sig
    while body isa UnionAll
        push!(vars, body.var)
        body = body.body
    end
    isempty(vars) && return sig
    new = TypeVar[]
    inst(t) = foldl((t, (v, n)) -> Base.has_typevar(t, v) ? UnionAll(v, t){n} : t, zip(vars, new); init = t)
    for (k, v) in enumerate(vars)
        push!(new, TypeVar(Symbol("_", k), inst(v.lb), inst(v.ub)))
    end
    return foldr(UnionAll, new; init = sig{new...})
end

"""
An empty module: in its context a signature names each function and type by its full path, except
the names that Base and Core export.
"""
module KeyContext end

"""
The key of a method signature: `sig` renamed, printed in `KeyContext`, without the path of the
package's root module `root`, and with no gensym digits. A `using` in `root` therefore
changes no key: a function of `root` prints as `typeof(f)`, one of its submodule as `typeof(Sub.f)`.
"""
function key(sig, root)
    s = sprint(show, renamed(sig); context = :module => KeyContext)
    s = replace(s, Regex("(?<![\\w.!])\\Q$(root).\\E") => "")
    return replace(s, r"(?<=#)\d+" => "")
end

"""
The generic of a key: the text of its first type parameter, such as `typeof(f)`, and of its third
for a `Core.kwcall` method, whose generic is its keyword function.
"""
function generic_of(k)
    s, depth, from, ps = chopprefix(k, "Tuple{"), 0, 1, String[]
    for (i, c) in pairs(s)
        if depth == 0 && c in ",}"
            push!(ps, strip(s[from:prevind(s, i)]))
            c == '}' && break
            from = nextind(s, i)
        end
        depth += c in "{(" ? 1 : c in "})" ? -1 : 0
    end
    return ps[1] == "typeof(Core.kwcall)" ? ps[3] : ps[1]
end

"`file` relative to the root of `tree` where it is under it, else as it is."
function relfile(file, tree)
    f = string(file)
    for t in unique((tree, realpath(tree)))
        startswith(f, t * "/") && return f[(length(t) + 2):end]
    end
    return f
end

"`m` and each module below it."
function module_tree(m, acc = Module[])
    push!(acc, m)
    for n in names(m; all = true)
        isdefined(m, n) || continue
        x = getglobal(m, n)
        # a package's root module is its own parent
        x isa Module && x !== m && parentmodule(x) === m && module_tree(x, acc)
    end
    return acc
end

ftype(m::Method) = Base.unwrap_unionall(m.sig).parameters[1]

"The function type of the generic of `m`: the keyword function's, the third parameter, for a `Core.kwcall` method."
function gtype(m::Method)
    ps = Base.unwrap_unionall(m.sig).parameters
    return ps[1] === typeof(Core.kwcall) ? ps[3] : ps[1]
end

"The module that owns the generic of a function type: the type's own for `Type{T}`."
function generic_module(ft)
    ft isa DataType || return nothing
    ft.name === Type.body.name && ft.parameters[1] isa Type && return parentmodule(ft.parameters[1])
    return parentmodule(ft)
end

where_is(m, root, tree) = Dict("key" => key(m.sig, root), "file" => relfile(m.file, tree), "line" => Int(m.line))

"Every method of `Core.methodtable` whose module is in `ownset`, except the methods of a function whose name starts with `#`."
function own_methods(ownset)
    ms = Method[]
    Base.visit(Core.methodtable) do x
        parentmodule(x) in ownset && !startswith(string(x.name), "#") && push!(ms, x)
    end
    return ms
end

"""
Each public name of `root`, and of each submodule that is itself a public name of its parent,
recursively, as `(path, module, name)`: `path` is the path of the module below `root`, `""` for
`root` itself. A public name is one with `Base.ispublic` that the module defines; a module's own
name is left out.
"""
function public_bindings(root)
    acc = Tuple{String, Module, Symbol}[]
    function walk(m, path)
        for n in sort!(names(m; all = true, imported = true))
            (n === nameof(m) || !Base.ispublic(m, n) || !isdefined(m, n)) && continue
            push!(acc, (path, m, n))
            x = getglobal(m, n)
            x isa Module && x !== m && parentmodule(x) === m && walk(x, isempty(path) ? string(n) : "$path.$n")
        end
    end
    walk(root, "")
    return acc
end

"The kind of the binding `n` of `m`: `module`, `type`, `function`, or `other`."
function kind(m, n)
    x = getglobal(m, n)
    return x isa Module ? "module" : x isa Type ? "type" : x isa Function ? "function" : "other"
end

"""
Whether the function type `ft` of a generic is that of the value of a public name among the
bindings `pub` of `public_bindings`: a function, a callable object, or a type's constructor.
"""
function public_generic(ft, pub)
    ft = Base.unwrap_unionall(ft)
    ft isa DataType || return false
    for (_, m, n) in pub
        x = getglobal(m, n)
        typeof(x).name === ft.name && return true
        if x isa Type && ft.name === Type.body.name
            t, u = Base.unwrap_unionall(ft.parameters[1]), Base.unwrap_unionall(x)
            t isa DataType && u isa DataType && t.name === u.name && return true
        end
    end
    return false
end

"""
One record per own method of `own_methods`. `others` holds the other methods of the generic:
all of them for an own generic, the intersecting ones for an external generic. The generic of a
`Core.kwcall` method is its keyword function, and its other methods are that function's
`Core.kwcall` methods. `generic_package` names the package of the generic's module. `api` says
whether the generic is external or that of the value of a public name among `pub`, and `kwargs`
holds the method's keyword names, a slurp as `name...`.
"""
function method_records(ownset, root, tree, pub)
    ms = own_methods(ownset)
    group(x) = (ftype(x), gtype(x))
    gs = Set{Any}(group(x) for x in ms)
    bygen = Dict{Any, Vector{Method}}()
    Base.visit(Core.methodtable) do x
        g = group(x)
        g in gs && push!(get!(bygen, g, Method[]), x)
    end
    map(ms) do x
        gm = generic_module(gtype(x))
        own = gm in ownset
        others = filter(y -> y !== x && (own || typeintersect(y.sig, x.sig) !== Union{}), bygen[group(x)])
        merge(where_is(x, root, tree),
            Dict("name" => string(x.name), "module" => string(parentmodule(x)),
                "generic" => own ? "own" : "external",
                "generic_package" => gm === nothing ? nothing : string(nameof(Base.moduleroot(gm))),
                "api" => !own || public_generic(gtype(x), pub), "kwargs" => string.(Base.kwarg_decl(x)),
                "others" => sort!([where_is(y, root, tree) for y in others]; by = o -> (o["file"], o["line"], o["key"]))))
    end
end

"""
Each ambiguity of the own modules: own-own with its keys in order, own-external with the own key
first. `detect_ambiguities` returns only pairs that hold a method of the modules it gets.
"""
function ambiguities(own, ownset, root)
    map(Test.detect_ambiguities(own...; recursive = true)) do (a, b)
        oa, ob = parentmodule(a) in ownset, parentmodule(b) in ownset
        ka, kb = key(a.sig, root), key(b.sig, root)
        oa && ob ? Dict("kind" => "own-own", "keys" => sort!([ka, kb])) :
        Dict("kind" => "own-external", "keys" => oa ? [ka, kb] : [kb, ka])
    end
end

const TYPE_HEADS = (:curly, :where, :tuple, :braces, :<:, :>:)

"""
Whether `ex` holds only the parts of a printed type: names, dotted names, literals, `{}`, `where`,
bounds, a lower and an upper bound together (`A<:T<:B`), `typeof(…)`, and the fields `a = …` of a
named tuple.
"""
function type_expr(ex)
    ex isa Expr || return true
    h, a = ex.head, ex.args
    h === :tuple && return all(x -> x isa Expr && x.head === :(=) && length(x.args) == 2 && x.args[1] isa Symbol ?
                                    type_expr(x.args[2]) : type_expr(x), a)
    return (h in TYPE_HEADS || h === :. && length(a) == 2 && a[2] isa QuoteNode ||
            h === :call && length(a) == 2 && a[1] === :typeof ||
            h === :comparison && length(a) == 5 && a[2] === a[4] && a[2] in (:<:, :>:)) && all(type_expr, a)
end

"Whether `ex` is the expression of a key: a type expression of a `Tuple{…}`, with or without `where`."
function key_expr(ex)
    type_expr(ex) || return false
    while ex isa Expr && ex.head === :where
        ex = ex.args[1]
    end
    return ex isa Expr && ex.head === :curly && ex.args[1] === :Tuple
end

"""
The first symbol of each dotted name in `ex`: `X` of `X.T`, and of `X.Y.T`, whose inner node is
`X.Y`.
"""
function qualifiers(ex, acc = Set{Symbol}())
    ex isa Expr || return acc
    ex.head === :. && ex.args[1] isa Symbol && push!(acc, ex.args[1])
    foreach(a -> qualifiers(a, acc), ex.args)
    return acc
end

"The loaded package named `s`, where exactly one is loaded, else `nothing`."
function loaded_package(s)
    ps = [m for (k, m) in Base.loaded_modules if k.name == string(s)]
    return length(ps) == 1 ? only(ps) : nothing
end

"""
`ex` with each leading qualifier that `root` does not bind and that names a loaded package replaced
by that package, and each `typeof(:op)`, the key of an operator of `root`, read as `typeof(op)`.
"""
function requalified(ex, root)
    ex isa Expr || return ex
    ex.head === :call && ex.args[1] === :typeof && ex.args[2] isa QuoteNode && return Expr(:call, :typeof, ex.args[2].value)
    if ex.head === :. && ex.args[1] isa Symbol && !isdefined(root, ex.args[1])
        p = loaded_package(ex.args[1])
        p === nothing || return Expr(:., p, ex.args[2])
    end
    return Expr(ex.head, (requalified(a, root) for a in ex.args)...)
end

"""
The head's verdict on the base key `k`, among the own methods `ms` of the head: `covered`, with the
key of an own method whose signature takes the key's (`sig <: m.sig`), else `removed`. A key that
does not evaluate in `root` is `unknown`, with the first line of its error, except an
`UndefVarError` in an own module of a name that is no leading qualifier of the key and holds no
`#`, which is `removed`: an own name is gone. A gensym name, which holds `#`, stays `unknown`. A key
that is no type expression is not evaluated.
"""
function method_cover(k, root, ownset, ms)
    unknown(msg) = Dict("status" => "unknown", "error" => String(first(split(msg, '\n'))))
    ex = try
        Meta.parse(k)
    catch e
        return unknown(sprint(showerror, e))
    end
    key_expr(ex) || return unknown("not a type expression")
    sig = try
        Core.eval(root, requalified(ex, root))
    catch e
        e isa UndefVarError && !occursin('#', string(e.var)) && e.scope in ownset && !(e.var in qualifiers(ex)) &&
            return Dict("status" => "removed")
        return unknown(sprint(showerror, e))
    end
    by = sort!([key(m.sig, root) for m in ms if sig <: m.sig])
    return isempty(by) ? Dict("status" => "removed") : Dict("status" => "covered", "by" => first(by))
end

"The module at `path` below `root`, `\"\"` for `root`, where each step is a submodule; else `nothing`."
function submodule(root, path)
    m = root
    for p in (isempty(path) ? String[] : split(path, '.'))
        s = Symbol(p)
        isdefined(m, s) || return nothing
        x = getglobal(m, s)
        x isa Module && x !== m && parentmodule(x) === m || return nothing
        m = x
    end
    return m
end

"""
The head's cover of the base's records `b`: for each base public name, `public`, `demoted` where
the head defines it in the same module and does not declare it public, or `gone`; and for each base
API method whose key the own methods `ms` of the head lack, the verdict of `method_cover`, with the
base's file and line.
"""
function cover(b, root, ownset, ms)
    ns = map(b["public"]) do r
        m, n = submodule(root, r["module"]), Symbol(r["name"])
        status = m === nothing || !isdefined(m, n) ? "gone" : Base.ispublic(m, n) ? "public" : "demoted"
        Dict("module" => r["module"], "name" => r["name"], "status" => status)
    end
    hkeys = Set(key(m.sig, root) for m in ms)
    mcs = [merge(Dict("key" => r["key"], "file" => r["file"], "line" => r["line"]), method_cover(r["key"], root, ownset, ms))
           for r in b["methods"] if r["api"] && !(r["key"] in hkeys)]
    return Dict("names" => ns, "methods" => mcs)
end

"The reason of the `UNKNOWN: stale imports:` line where ExplicitImports does not load; such a line gives no verdict."
const NO_EXPLICIT_IMPORTS = "ExplicitImports does not load"

"The directories of a tree where a name that a module imports can be reached as `<module>.<name>`."
const REACH_DIRS = ("test", "docs", "scripts", "ext")

"""
The directories of `REACH_DIRS` under `tree` where a `.jl` or `.md` file holds the text `q`, word
bounded: no letter, digit, `_` or `.` before it, and no letter, digit, `_` or `!` after it.
"""
function reached_in(tree, q)
    re = Regex("(?<![\\w.])\\Q$q\\E(?![\\w!])")
    filter(REACH_DIRS) do d
        dir = joinpath(tree, d)
        isdir(dir) || return false
        any(walkdir(dir)) do (path, _, files)
            any(files) do f
                p = joinpath(path, f)
                # a dangling link names no file
                (endswith(f, ".jl") || endswith(f, ".md")) && isfile(p) && occursin(re, read(p, String))
            end
        end
    end
end

"The modules of `own` that are the root of their tree, in their order: the package's root module and each extension."
root_modules(own) = filter(m -> Base.moduleroot(m) === m, own)

"""
The stale explicit imports of the own modules, from the rows with `stale` of ExplicitImports'
`improper_explicit_imports(first(roots); strict = false)`, as `(; imports, unknown)`. `roots` are
the package's root module and then each loaded extension; the result for the root module holds the
modules below it and below each loaded extension. `ei` is the loaded ExplicitImports, or the error
text of its load. A record of `imports` holds the module, the name, the file relative to `tree` and
the line of the import, and `used`, the directories of `REACH_DIRS` where `<module>.<name>` occurs.
A record of `unknown` holds a module and the reason that it has no records: a module for which
`strict = true` returns `nothing`, as ExplicitImports cannot read part of it and a used name may
read as stale; each module of `roots` where the call raises; and the empty module, which stands
for every module, where ExplicitImports does not load.
"""
function stale_imports(ei, roots, tree)
    imports, unknown = Dict{String, Any}[], Dict{String, String}[]
    if ei isa String
        push!(unknown, Dict("module" => "", "reason" => "$NO_EXPLICIT_IMPORTS: $(first(split(ei, '\n')))"))
        return (; imports, unknown)
    end
    lax, strict = try
        ei.improper_explicit_imports(first(roots); strict = false), Dict(ei.improper_explicit_imports(first(roots); strict = true))
    catch e
        reason = "ExplicitImports raised: $(first(split(sprint(showerror, e), '\n')))"
        append!(unknown, [Dict("module" => string(r), "reason" => reason) for r in roots])
        return (; imports, unknown)
    end
    for (m, rows) in lax
        if rows === nothing || get(strict, m, nothing) === nothing
            push!(unknown, Dict("module" => string(m), "reason" => "ExplicitImports cannot analyse it"))
            continue
        end
        for x in rows
            x.stale || continue
            file, line = rsplit(x.location, ':'; limit = 3)
            push!(imports, Dict("module" => string(m), "name" => string(x.name), "file" => relfile(file, tree),
                "line" => parse(Int, line), "used" => collect(String, reached_in(tree, "$m.$(x.name)"))))
        end
    end
    return (; imports, unknown)
end

"Write `d` as JSON into `path` at once, so that a reader never sees part of it."
function write_json(path, d)
    write(path * ".part", JSON.json(d))
    mv(path * ".part", path; force = true)
end

"""
The records of a side, written into `<rundir>/<side>.json`. Beside the keys that a reader of the
two files uses, `manifest` says whether the side's tree held a `Manifest.toml` when the side began.
`loaded` names each package that the side has loaded when it writes the file. `public` holds one
record per public name of `public_bindings`. `fields` holds one record per field of the root
module's tree whose type is not concrete up to type variables, by `concrete_field_violations` of
concrete-fields.jl, with its type printed by `show`. With `basejson`, the path of the base's
records, the file also holds the head's `cover` of them. Where `ei`, the loaded ExplicitImports or
the error text of its load, is no `nothing`, `stale` holds the `stale_imports` of the root module
and of each extension.
"""
function record(s, rundir, tree, name, root, tree_mods, own, aqua, manifest, basejson, ei)
    ownset = Set(own)
    pub = public_bindings(root)
    piracies = [where_is(m, root, tree) for mod in tree_mods for m in aqua.Piracy.hunt(mod)]
    d = Dict(
        "package" => name, "side" => s, "julia" => string(VERSION), "manifest" => manifest,
        "tools" => Dict("Aqua" => string(pkgversion(aqua))),
        "dependencies" => Dict(i.name => (i.version === nothing ? nothing : string(i.version)) for i in values(Pkg.dependencies())),
        "loaded" => sort!([p.name for p in keys(Base.loaded_modules)]),
        "public" => [Dict("module" => p, "name" => string(n), "kind" => kind(m, n)) for (p, m, n) in pub],
        "methods" => method_records(ownset, root, tree, pub),
        "ambiguities" => ambiguities(own, ownset, root),
        "piracies" => piracies,
        "fields" => [Dict("type" => r.type, "field" => string(r.field), "fieldtype" => sprint(show, r.fieldtype))
                     for r in ConcreteFields.concrete_field_violations(root)])
    basejson === nothing || (d["cover"] = cover(JSON.parsefile(basejson), root, ownset, own_methods(ownset)))
    if ei !== nothing
        st = stale_imports(ei, root_modules(own), tree)
        d["stale"] = Dict("imports" => st.imports, "unknown" => st.unknown)
    end
    write_json(joinpath(rundir, "$s.json"), d)
end

"""
JET's reports on the own modules, each with its type, the key of its innermost frame and its
message. `target_modules` keeps only the reports whose error point is in an own module, so the
innermost frame is a method of one.
"""
function jet_reports(jet, root, own, tree)
    reps = jet.get_reports(jet.report_package(root; target_modules = Tuple(own), toplevel_logger = nothing))
    map(reps) do r
        frame = last(r.vst)
        msg = replace(sprint(jet.print_report_message, r), r"\S+\.jl:\d+" => "", r"(?<=#)\d+" => "", r"\s+" => " ")
        Dict("type" => string(nameof(typeof(r))), "message" => strip(msg), "frame" => key(frame.linfo.def.sig, root),
            "file" => relfile(frame.file, tree), "line" => Int(frame.line))
    end
end

"""
The work of one side, in its own process after `TestEnv.activate()`: load the package and the weak
dependencies that its test environment provides, write the records, then run JET. `manifest` says
whether the tree held a `Manifest.toml` before the activation; `basejson`, where it is no
`nothing`, is the path of the base's records, which the head covers. With `stale`, the records hold
the stale explicit imports; a failed load of ExplicitImports leaves them one `unknown` record, with
its error, for every module. Returns the process's exit code; a failed load of the package writes
`<side>.error`.
"""
function side(s, rundir, tree, name, jet, manifest, basejson = nothing, stale = true)
    root = try
        Base.require(Main, Symbol(name))
    catch e
        write(joinpath(rundir, "$s.error"), "load\n", sprint(showerror, e))
        return 11
    end
    project = TOML.parsefile(joinpath(tree, "Project.toml"))
    for w in keys(get(project, "weakdeps", Dict()))
        Base.identify_package(w) === nothing || Base.require(Main, Symbol(w))
    end
    # an extension whose triggers the test environment provides, and that is missing, failed to load
    for (x, t) in get(project, "extensions", Dict())
        all(w -> Base.identify_package(w) !== nothing, t isa String ? [t] : t) || continue
        if Base.get_extension(root, Symbol(x)) === nothing
            write(joinpath(rundir, "$s.error"), "load\nextension $x did not load")
            return 11
        end
    end
    aqua = Base.require(Main, :Aqua)
    ei = !stale ? nothing : try
        Base.require(Main, :ExplicitImports)
    catch e
        sprint(showerror, e)
    end
    tree_mods, own = Base.invokelatest() do
        t, exts = module_tree(root), Module[]
        for x in keys(get(project, "extensions", Dict()))
            m = Base.get_extension(root, Symbol(x))
            m === nothing || module_tree(m, exts)
        end
        t, [t; exts]
    end
    Base.invokelatest(record, s, rundir, tree, name, root, tree_mods, own, aqua, manifest, basejson, ei)
    jet || return 0
    j = Base.require(Main, :JET)
    reports = Base.invokelatest(jet_reports, j, root, own, tree)
    write_json(joinpath(rundir, "$s-jet.json"), Dict("JET" => string(pkgversion(j)), "reports" => reports))
    return 0
end

"""
The driver of a side: the harness environment last in LOAD_PATH, `TestEnv.activate()`, then
`side`, with `basejson` for the head in `--api` mode, and with `stale` outside it.
"""
driver(s, rundir, tree, name, jet, basejson = nothing, stale = true) = """
    $(repr(HARNESS_ENV)) in LOAD_PATH || push!(LOAD_PATH, $(repr(HARNESS_ENV)))
    manifest = isfile($(repr(joinpath(tree, "Manifest.toml"))))
    using TestEnv
    try
        TestEnv.activate()
    catch e
        write($(repr(joinpath(rundir, "$s.error"))), "resolve\\n", sprint(showerror, e))
        exit(10)
    end
    module DispatchDelta
    include($(repr(SCRIPT)))
    end
    exit(DispatchDelta.side($(repr(s)), $(repr(rundir)), $(repr(tree)), $(repr(name)), $jet, manifest, $(repr(basejson)), $stale))
    """

"How a side's process ended: its signal, its exit code, and whether the script killed it."
struct End
    signal::Int
    code::Int
    killed::Bool
end

"Kill the process group of `p`, and so each process that `p` started, such as a precompilation."
killgroup(p) = ccall(:kill, Cint, (Cint, Cint), -getpid(p), Base.SIGKILL)

"""
Wait for the processes `procs` of the sides, from now, and add how each ended to `ends`. A side
gets `timeout` seconds to write its JSON, and with JET `timeout` seconds more from that moment;
past its limit its process group is killed.
"""
function wait_sides!(ends, procs, rundir, timeout, jet)
    t0, json_at = time(), Dict{String, Float64}()
    while !all(s -> haskey(ends, s), keys(procs))
        for (s, p) in procs
            haskey(ends, s) && continue
            running = process_running(p)
            if running
                jet && !haskey(json_at, s) && isfile(joinpath(rundir, "$s.json")) && (json_at[s] = time())
                time() > get(json_at, s, t0) + timeout || continue
                killgroup(p)
            end
            wait(p)
            ends[s] = End(p.termsignal, p.exitcode, running)
        end
        all(s -> haskey(ends, s), keys(procs)) || sleep(0.2)
    end
    return ends
end

"""
Run the sides and wait for them, each in a process group of its own; each group still running when
the script stops is killed. Both sides start at once; with `api`, the head starts once the base
has ended, with the path of `base.json`, and does not start where the base wrote none.
"""
function run_sides(rundir, trees, name, timeout, jet; api = false)
    logs = Dict(s => open(joinpath(rundir, "$s.log"), "w") for s in keys(trees))
    procs, ends = Dict{String, Base.Process}(), Dict{String, End}()
    function start(s, basejson = nothing)
        drv = joinpath(rundir, "$s-driver.jl")
        write(drv, driver(s, rundir, trees[s], name, jet, basejson, !api))
        cmd = Cmd(`$(Base.julia_cmd()) --startup-file=no --project=$(trees[s]) $drv`; detach = true)
        procs[s] = run(pipeline(ignorestatus(cmd); stdout = logs[s], stderr = logs[s]); wait = false)
    end
    try
        if api
            start("base")
            wait_sides!(ends, procs, rundir, timeout, jet)
            basejson = joinpath(rundir, "base.json")
            if isfile(basejson)
                start("head", basejson)
                wait_sides!(ends, procs, rundir, timeout, jet)
            end
        else
            foreach(start, keys(trees))
            wait_sides!(ends, procs, rundir, timeout, jet)
        end
    finally
        foreach(p -> process_running(p) && killgroup(p), values(procs))
        foreach(close, values(logs))
    end
    return ends
end

"The first `ERROR:` line of a side's log, which holds the error of a failed precompilation, else the first line of `msg`."
function error_line(log, msg)
    m = isfile(log) ? match(r"^ERROR: (.+)$"m, read(log, String)) : nothing
    return m === nothing ? first(split(msg, '\n')) : String(m[1])
end

"The lines that compare the records of the two sides."
function compare(b, h)
    out = String[]
    for field in ("dependencies", "tools"), n in sort!(collect(union(keys(b[field]), keys(h[field]))))
        bv, hv = get(b[field], n, nothing), get(h[field], n, nothing)
        bv == hv || push!(out, "INFO: dependency drift: $n $(something(bv, "none")) -> $(something(hv, "none"))")
    end
    amb(d) = Set((a["kind"], a["keys"][1], a["keys"][2]) for a in d["ambiguities"])
    for (kind, k1, k2) in sort!(collect(setdiff(amb(h), amb(b))))
        push!(out, "FAIL: new $kind ambiguity: $k1 | $k2")
    end
    for (kind, k1, k2) in sort!(collect(setdiff(amb(b), amb(h))))
        push!(out, "INFO: gone $kind ambiguity: $k1 | $k2")
    end
    pir(d) = Dict(p["key"] => p for p in d["piracies"])
    bp, hp = pir(b), pir(h)
    for k in sort!(collect(setdiff(keys(hp), keys(bp))))
        push!(out, "FAIL: new piracy: $k at $(hp[k]["file"]):$(hp[k]["line"])")
    end
    for k in sort!(collect(setdiff(keys(bp), keys(hp))))
        push!(out, "INFO: gone piracy: $k at $(bp[k]["file"]):$(bp[k]["line"])")
    end
    fld(d) = Set((r["type"], r["field"], r["fieldtype"]) for r in d["fields"])
    for (t, f, ft) in sort!(collect(setdiff(fld(h), fld(b))))
        push!(out, "FAIL: new abstract field: $t.$f::$ft")
    end
    for (t, f, ft) in sort!(collect(setdiff(fld(b), fld(h))))
        push!(out, "INFO: gone abstract field: $t.$f::$ft")
    end
    bkeys = Set(m["key"] for m in b["methods"])
    bgen = Set(generic_of(m["key"]) for m in b["methods"])
    bloaded = Set(b["loaded"])
    # an external generic has a method on the base where the base loaded its package
    has_base(m) = m["generic"] == "external" ? m["generic_package"] === nothing || m["generic_package"] in bloaded :
                  generic_of(m["key"]) in bgen
    for m in sort(h["methods"]; by = m -> m["key"])
        m["key"] in bkeys && continue
        has_base(m) || continue
        push!(out, "INFO: added method: $(m["key"]) at $(m["file"]):$(m["line"])")
        foreach(o -> push!(out, "  other: $(o["key"]) at $(o["file"]):$(o["line"])"), m["others"])
    end
    return append!(out, compare_stale(b["stale"], h["stale"]))
end

"""
The lines that compare the stale explicit imports of the two sides, keyed by module and name: one
`UNKNOWN` line per module that either side could not analyse, and no other line for it or for a
module below it; the empty module stands for every module.
"""
function compare_stale(b, h)
    unk = sort!(unique([(u["module"], u["reason"]) for d in (b, h) for u in d["unknown"]]))
    out = [isempty(m) ? "UNKNOWN: stale imports: $r" : "UNKNOWN: stale imports: $m: $r" for (m, r) in unk]
    known(m) = !any(((u, _),) -> isempty(u) || m == u || startswith(m, u * "."), unk)
    imp(d) = Dict((r["module"], r["name"]) => r for r in d["imports"] if known(r["module"]))
    bi, hi = imp(b), imp(h)
    for (k, r) in sort!([k => hi[k] for k in setdiff(keys(hi), keys(bi))]; by = first)
        push!(out, isempty(r["used"]) ? "FAIL: new stale import: $(k[1]): $(k[2]) at $(r["file"]):$(r["line"])" :
                   "INFO: new stale import, used in $(join(r["used"], ", ")): $(k[1]): $(k[2])")
    end
    append!(out, ["INFO: gone stale import: $m: $n" for (m, n) in sort!(collect(setdiff(keys(bi), keys(hi))))])
    return out
end

"""
The lines that compare the API of the two sides: the head's cover of the base's public names and
API methods, the new public names, and the keyword names that the generic of each base API method
takes on the base, from its API methods, and on the head, from all its methods.
"""
function compare_api(b, h)
    out = String[]
    qual(r) = isempty(r["module"]) ? r["name"] : "$(r["module"]).$(r["name"])"
    for r in sort(h["cover"]["names"]; by = qual)
        r["status"] == "gone" && push!(out, "FAIL: gone public name: $(qual(r))")
        r["status"] == "demoted" && push!(out, "FAIL: no longer public: $(qual(r))")
    end
    bpub = Set(qual(r) for r in b["public"])
    append!(out, ["INFO: new public name: $n" for n in sort!([qual(r) for r in h["public"] if !(qual(r) in bpub)])])
    for r in sort(h["cover"]["methods"]; by = r -> r["key"])
        push!(out, r["status"] == "removed" ? "FAIL: removed method: $(r["key"]) at $(r["file"]):$(r["line"])" :
                   r["status"] == "covered" ? "INFO: covered: $(r["key"]) by $(r["by"])" :
                   "UNKNOWN: key: $(r["key"]): $(r["error"])")
    end
    function keywords(d, api)
        kw = Dict{String, Set{String}}()
        for m in d["methods"]
            (api && !m["api"]) || union!(get!(kw, generic_of(m["key"]), Set{String}()), m["kwargs"])
        end
        return kw
    end
    bk, hk = keywords(b, true), keywords(h, false)
    for g in sort!(collect(keys(bk))), n in sort!(collect(bk[g]))
        hs = get(hk, g, Set{String}())
        n in hs || any(endswith("..."), hs) ||
            push!(out, "FAIL: removed keyword: $(replace(g, r"^typeof\((.*)\)$" => s"\1")) $n")
    end
    return out
end

"The lines that compare the JET reports of the two sides."
function compare_jet(b, h)
    rep(d) = Dict((r["type"], r["message"], r["frame"]) => r for r in d["reports"])
    br, hr = rep(b), rep(h)
    out = ["INFO: new JET report: $t: $m in $f" for (t, m, f) in sort!(collect(setdiff(keys(hr), keys(br))))]
    append!(out, ["INFO: gone JET report: $t: $m in $f" for (t, m, f) in sort!(collect(setdiff(keys(br), keys(hr))))])
    return out
end

"""
The lines of a run from what its sides left in `rundir` and how they ended, with the `Verdict:`
line last, and the exit code. A side whose JSON exists has its records; with JET, an end other than
a clean exit after that is the JET step's alone. With `api`, the lines compare the API alone, and a
side that `ends` lacks did not start.
"""
function analyse(rundir, ends; timeout, jet, api = false)
    out, data, decisive = String[], Dict{String, Any}(), false
    jet_lost = Set{String}()
    for s in ("base", "head")
        haskey(ends, s) || continue
        e, json, err, log = ends[s], joinpath(rundir, "$s.json"), joinpath(rundir, "$s.error"), joinpath(rundir, "$s.log")
        if jet && isfile(json) && (e.signal != 0 || e.code != 0)
            push!(out, e.killed ? "UNKNOWN: jet: $s timed out after $timeout s" :
                       "UNKNOWN: jet: $s ended with " * (e.signal != 0 ? "signal $(e.signal)" : "exit code $(e.code)"))
            push!(jet_lost, s)
            data[s] = JSON.parsefile(json)
        elseif e.signal != 0
            push!(out, e.killed ? "UNKNOWN: $s timed out after $timeout s" : "UNKNOWN: $s ended by signal $(e.signal)", "log: $log")
            decisive = true
        elseif isfile(err)
            stage, msg = split(read(err, String), '\n'; limit = 2)
            if stage == "resolve"
                push!(out, "UNKNOWN: $s does not resolve: $(first(split(msg, '\n')))", "log: $log")
                decisive = true
            elseif s == "head"
                push!(out, "FAIL: the head does not load: $(error_line(log, msg))", "log: $log")
            else
                push!(out, "UNKNOWN: the base does not load: $(error_line(log, msg))", "log: $log")
                decisive = true
            end
        elseif !isfile(json)
            push!(out, "UNKNOWN: $s gave no result, exit code $(e.code)", "log: $log")
            decisive = true
        else
            data[s] = JSON.parsefile(json)
        end
    end
    if haskey(data, "base") && haskey(data, "head")
        pushfirst!(out, "json: $(joinpath(rundir, "base.json")) $(joinpath(rundir, "head.json"))")
        append!(out, api ? compare_api(data["base"], data["head"]) : compare(data["base"], data["head"]))
        jet && isempty(jet_lost) && append!(out,
            compare_jet((JSON.parsefile(joinpath(rundir, "$s-jet.json")) for s in ("base", "head"))...))
    end
    jet || api || push!(out, "INFO: jet: not run (--no-jet)")
    f, u, i = (count(startswith(p), out) for p in ("FAIL: ", "UNKNOWN: ", "INFO: "))
    status = f > 0 ? 1 :
             decisive || any(l -> startswith(l, "UNKNOWN: key: ") || startswith(l, "UNKNOWN: stale imports: $NO_EXPLICIT_IMPORTS: "),
                             out) ? 3 : 0
    push!(out, "Verdict: $(status == 0 ? "PASS" : status == 1 ? "FAIL" : "UNKNOWN") — $f FAIL, $u UNKNOWN, $i INFO")
    return out, status
end

"The names under `[deps]` of `project` whose UUID is the `uuid` of no entry of `manifest`, sorted."
function lacking(manifest, project)
    have = Set(e["uuid"] for es in values(get(TOML.parsefile(manifest), "deps", Dict())) for e in es)
    return sort!([n for (n, u) in get(TOML.parsefile(project), "deps", Dict()) if !(u in have)])
end

function main(args)
    a = arguments(args)
    if a isa String
        println(stderr, "dispatch-delta.jl: ", a)
        println(stderr, USAGE)
        return 2
    end
    (; pkg, base, name, timeout, api) = a
    jet = a.jet && !api
    sha = readchomp(`git -C $pkg rev-parse --short $(base * "^{commit}")`)
    stamp = Dates.format(Dates.now(), "yyyymmdd-HHMMSS")
    rundir = mkpath(joinpath(expanduser("~/Research/.scratch/dispatch-delta"), "$name-$stamp-$(getpid())"))
    println("$name: $pkg against $base at $sha, Julia $VERSION, run directory $rundir")
    basetree, headcopy = joinpath(rundir, "$name-base-$sha"), joinpath(rundir, "$name-head")
    try
        BaseTree.base_tree(pkg, base, basetree)
        head = pkg
        foreign = RunTests.foreign_manifests(pkg)
        manifests = filter(m -> isfile(joinpath(pkg, m)), ["Manifest.toml", "test/Manifest.toml"])
        if !isempty(foreign)
            run(RunTests.copy_command(pkg, headcopy, manifests))
            foreach(m -> rm(joinpath(basetree, m); force = true), manifests)
            head = headcopy
            println("manifest: ", join(foreign, " and "), " is resolved by another Julia than $VERSION, ",
                "so neither side gets one, and the head runs from a copy without it")
        elseif "Manifest.toml" in manifests
            lack = lacking(joinpath(pkg, "Manifest.toml"), joinpath(basetree, "Project.toml"))
            if isempty(lack)
                cp(joinpath(pkg, "Manifest.toml"), joinpath(basetree, "Manifest.toml"); force = true)
                println("manifest: the head's Manifest.toml goes into the base tree")
            else
                println("manifest: the head's Manifest.toml lacks ", join(lack, ", "),
                    " of the base's [deps], so the base resolves its own")
            end
        else
            println("manifest: the head has no Manifest.toml, so each side resolves its own")
        end
        ends = run_sides(rundir, Dict("base" => basetree, "head" => head), name, timeout, jet; api)
        out, status = analyse(rundir, ends; timeout, jet, api)
        foreach(println, out)
        return status
    finally
        rm(basetree; recursive = true, force = true)
        rm(headcopy; recursive = true, force = true)
    end
end

if abspath(PROGRAM_FILE) == @__FILE__
    # an interrupt throws, so that the sides' process groups are killed on the way out
    Base.exit_on_sigint(false)
    exit(main(ARGS))
end
