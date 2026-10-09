# Run a branch's tests on the base's code: a test that passes there PINS behaviour, and a test that
# fails there reproduces the defect it names.
#
#   julia --startup-file=no pins.jl <package> <base> [<unit> ...]
#
# <base> is a git ref of <package>, such as origin/main, or a directory that holds the base's
# `src/` and `ext/`. The run is on a copy under ~/Research/.scratch/mutants/: the branch's tree with
# `src/` and `ext/` of the base. The package itself is never touched. A <unit> is as for
# run-tests.jl; without units, the units that the diff against origin/main reaches are run. The
# verdict is one for all units: PINS when every unit passes, FAILS when one fails. For a verdict
# per test file, run one unit per call.

module Mutate
include(joinpath(@__DIR__, "mutate.jl"))
end

"Put `src/` and `ext/` of `base`, a ref of `pkg` or a directory, into `copy`, in place of its own."
function put_base!(copy, pkg, base)
    if isdir(base)
        dirs = filter(d -> isdir(joinpath(base, d)), ["src", "ext"])
        foreach(d -> rm(joinpath(copy, d); recursive = true, force = true), dirs)
        foreach(d -> cp(joinpath(base, d), joinpath(copy, d)), dirs)
    else
        present = split(read(`git -C $pkg ls-tree --name-only $base`, String))
        dirs = filter(d -> d in present, ["src", "ext"])
        foreach(d -> rm(joinpath(copy, d); recursive = true, force = true), dirs)
        run(pipeline(`git -C $pkg archive $base $dirs`, `tar -x -C $copy`))
    end
    return dirs
end

function main(args)
    length(args) >= 2 || (println(stderr, "usage: pins.jl <package> <base> [<unit> ...]"); return 2)
    pkg, base = abspath(expanduser(args[1])), args[2]
    units = args[3:end]
    # run-tests.jl reads a first unit `list`, `select` or `affected` as a mode, whose exit status is
    # no verdict; `full` runs the suite, and a later unit is a label
    !isempty(units) && units[1] in ("list", "select", "affected") &&
        (println(stderr, "`$(units[1])` is a mode of run-tests.jl, not a unit."); return 2)
    isempty(units) && (units = Mutate.default_units(pkg))
    isempty(units) && (println("No unit to run."); return 2)
    copy = Mutate.fresh_copy(pkg)
    dirs = put_base!(copy, pkg, base)
    what = "$(join(dirs, " and ")) of $base under the branch's tests"
    code, _ = Mutate.run_units(copy, units)
    code in (0, 1) || (println("\nUNKNOWN — run-tests.jl exited $code, so no verdict: $what"); return 3)
    println("\n", code == 0 ? "PINS — every unit passes on $base" : "FAILS on $base", ": $what")
    return 0
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
