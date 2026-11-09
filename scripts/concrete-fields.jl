#!/usr/bin/env julia
#
# The fields of a package's structs whose types are not concrete up to type variables:
#
#   julia --startup-file=no concrete-fields.jl <package>
#
# A field's type passes when it is a type variable (with any bound), a non-abstract DataType whose
# type parameters all pass, or exactly Union{Nothing, X} or Union{Missing, X} where X is not a Union
# and passes. A type parameter that is not a type, such as the 2 of Array{T, 2}, passes; a Vararg
# passes when its element type passes, whatever its count. Every other field is a violation: a
# Function, an Any, an abstract type with or without parameters, a bare or partially applied
# UnionAll such as Matrix, any other Union, and a type with such a parameter, such as Vector{Real}.
#
# The structs read are those whose parentmodule is the package's root module or one of its
# submodules, recursively: not the types that the package only binds, not the generated types
# whose names start with `#`, and not the extension modules of ext/. No argument exempts a field.
#
# The package loads, by the `name` of its Project.toml, in a fresh process with
# --project=<package>; nothing is resolved or instantiated. One line per violation,
# `<Type path>.<field>::<field type>`, then the verdict:
#
#   Verdict: PASS — 0 violations                       exit 0
#   Verdict: FAIL — <n> violations                     exit 1
#   UNKNOWN: the package does not load: <error>        exit 3
#
# The UNKNOWN line also stands where the process that loads the package ends with another exit
# code or by a signal; its <error> then names both. Bad arguments print the usage line to stderr and exit 2. In process, concrete_field_violations
# takes the root module that a caller has loaded.

using TOML

"Whether the type parameter `p` passes: a value such as `2` or `:a` passes, a type is checked."
parameter_passes(p) = p isa Union{Type, TypeVar, Core.TypeofVararg} ? field_type_passes(p) : true

"Whether the field type `t` is concrete up to type variables."
function field_type_passes(t)
    t isa TypeVar && return true
    t isa Core.TypeofVararg && return field_type_passes(t.T)
    if t isa Union
        members = Base.uniontypes(t)
        length(members) == 2 || return false
        x = filter(m -> m !== Nothing && m !== Missing, members)
        return length(x) == 1 && field_type_passes(only(x))
    end
    t isa DataType || return false
    isabstracttype(t) && return false
    return all(parameter_passes, t.parameters)
end

"""
Push the struct types that `mod` and its submodules define onto `found`, each once, as
`path => type`, with `path` from `prefix`.
"""
function struct_types!(found, mod::Module, prefix::String)
    for name in names(mod; all = true)
        isdefined(mod, name) || continue
        v = getglobal(mod, name)
        if v isa Module
            # a package's root module is its own parentmodule, and every module binds its own name
            v !== mod && parentmodule(v) === mod && struct_types!(found, v, "$prefix.$(nameof(v))")
        elseif v isa Type
            u = Base.unwrap_unionall(v)
            u isa DataType && parentmodule(u) === mod || continue
            (startswith(string(nameof(u)), "#") || isabstracttype(u)) && continue
            T = u.name.wrapper
            any(p -> last(p) === T, found) || push!(found, "$prefix.$(nameof(u))" => T)
        end
    end
    return found
end

"""
    concrete_field_violations(M::Module)

The fields of the struct types of `M` and its submodules whose types are not concrete up to type
variables, as named tuples `(; type, field, fieldtype)`: `type` the path of the struct from `M`,
such as `"M.Inner.S"`, `field` the field's name, and `fieldtype` its declared type. Sorted by
`type`, then by the position of the field.
"""
function concrete_field_violations(M::Module)
    types = sort!(struct_types!(Pair{String, Type}[], M, string(nameof(M))); by = first)
    out = @NamedTuple{type::String, field::Symbol, fieldtype::Type}[]
    for (path, T) in types
        body = Base.unwrap_unionall(T)
        for (i, field) in enumerate(fieldnames(body))
            ft = fieldtype(body, i)
            field_type_passes(ft) || push!(out, (; type = path, field, fieldtype = ft))
        end
    end
    return out
end

const USAGE = "usage: concrete-fields.jl <package>"

"Print the violations of `M` and the verdict; the exit code."
function print_violations(M::Module)
    violations = concrete_field_violations(M)
    foreach(r -> println(r.type, ".", r.field, "::", sprint(show, r.fieldtype)), violations)
    n = length(violations)
    println(n == 0 ? "Verdict: PASS — 0 violations" : "Verdict: FAIL — $n violations")
    return n == 0 ? 0 : 1
end

"Load the package `name` of the active project and print its violations; the exit code."
function report(name::String)
    M = try
        Core.eval(Main, :(import $(Symbol(name))))
        Base.invokelatest(getglobal, Main, Symbol(name))
    catch e
        message = sprint(showerror, e)
        line = join(filter(!isempty, strip.(split(message, '\n'))), " ")
        println("UNKNOWN: the package does not load: ", line)
        println(stderr, message)
        return 3
    end
    # the package's bindings are newer than the world of this call
    return Base.invokelatest(print_violations, M)
end

# The program of the fresh process: ARGS are this file and the package's name.
const CHILD = "include(ARGS[1]); exit(report(ARGS[2]))"

function main(args)
    length(args) == 1 || (println(stderr, USAGE); return 2)
    pkg = abspath(expanduser(args[1]))
    project = joinpath(pkg, "Project.toml")
    toml = isfile(project) ? TOML.tryparsefile(project) : nothing
    name = toml isa Dict ? get(toml, "name", nothing) : nothing
    if !(name isa String)
        println(stderr, "concrete-fields.jl: no Project.toml with a name in $pkg")
        println(stderr, USAGE)
        return 2
    end
    cmd = `$(Base.julia_cmd()) --startup-file=no --project=$pkg -e $CHILD $(@__FILE__) $name`
    proc = run(ignorestatus(cmd))
    proc.exitcode in (0, 1, 3) && proc.termsignal == 0 && return proc.exitcode
    println("UNKNOWN: the package does not load: the process ended with exit code ",
        proc.exitcode, ", signal ", proc.termsignal)
    return 3
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
