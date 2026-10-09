#!/usr/bin/env julia
#
# Run ExplicitImports.jl over the core packages and report what it finds.
#
#   julia --project=<pkg> explicit-imports.jl <PkgName>
#
# ExplicitImports lives in the harness's Julia environment, and the package under analysis lives
# in its own. Both have to be loadable at once, so the script appends the harness environment to
# LOAD_PATH, after the package's: adding ExplicitImports as a real dependency of every package
# just to measure it would be worse.
#
# Why this exists: `fatou lint` reported 243 unused-import findings across these packages, but
# its rule does not follow `include`, so in a Julia package it flags the module file's
# load-bearing imports. Those findings cannot be acted on. ExplicitImports loads the module and
# analyses actual bindings, so it answers the question fatou only approximates -- and the answer
# is what makes Aqua's stale_deps check mean anything, since a live-but-useless `using` hides a
# stale dependency from it.
#
# Run on Julia 1.11+: the public/non-public distinction does not exist below that, so the
# ownership checks are only authoritative there.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml. Last in LOAD_PATH: the package under analysis comes first, so its own
# dependencies win.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || push!(LOAD_PATH, env)
end
using ExplicitImports

const PKG = Symbol(ARGS[1])

# `using` must happen at top level, not inside `main`: a module loaded inside a compiled
# function is not visible to that same function's world age.
@eval using $PKG

function main(m::Module)
    println("="^70)
    println(PKG)
    println("="^70)

    for (label, f) in (("implicit imports (using X, relying on what it exports)",
                        () -> print_explicit_imports(m; report_non_public = true)),)
        println("\n--- ", label, " ---")
        try
            f()
        catch e
            println("ERROR: ", sprint(showerror, e)[1:min(end, 300)])
        end
    end

    println("\n--- checks ---")
    for (name, check) in (
        ("stale explicit imports", () -> check_no_stale_explicit_imports(m)),
        ("all explicit imports via owner", () -> check_all_explicit_imports_via_owners(m)),
        ("no self-qualified accesses", () -> check_no_self_qualified_accesses(m)),
        ("all qualified accesses via owner", () -> check_all_qualified_accesses_via_owners(m)),
    )
        try
            check()
            println("  ok      $name")
        catch e
            msg = sprint(showerror, e)
            println("  FAIL    $name")
            println("          ", replace(strip(msg), '\n' => "\n          ")[1:min(end, 1200)])
        end
    end
end

main(getfield(Main, PKG))
