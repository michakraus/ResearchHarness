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
# Bad arguments print the usage line to stderr and exit 2. In process, concrete_field_violations
# takes the root module that a caller has loaded.

using TOML

"Whether the type parameter `p` passes: a value such as `2` or `:a` passes, a type is checked."
parameter_passes(p) = p isa Union{Type, TypeVar, Core.TypeofVararg} ? field_type_passes(p) : true

"Whether the field type `t` is concrete up to type variables."
function field_type_passes(t)
    t isa TypeVar && return true
    t isa Core.TypeofVararg && return isdefined(t, :T) && field_type_passes(t.T)
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

"The struct types of `mod` and of its submodules, each as `path => type`, with `path` from `prefix`."
function struct_types!(found, seen, mod::Module, prefix::String)
    push!(seen, mod)
    for name in names(mod; all = true)
        (isdefined(mod, name) && !Base.isdeprecated(mod, name)) || continue
        v = getglobal(mod, name)
        if v isa Module
            v in seen || parentmodule(v) !== mod || struct_types!(found, seen, v, "$prefix.$(nameof(v))")
        elseif v isa Type
            u = Base.unwrap_unionall(v)
            u isa DataType && parentmodule(u) === mod || continue
            startswith(string(nameof(u)), "#") && continue
            (isabstracttype(u) || !isstructtype(u) || fieldcount(u) == 0) && continue
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
    types = sort!(struct_types!(Pair{String, Type}[], Set{Module}(), M, string(nameof(M))); by = first)
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
