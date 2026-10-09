#!/usr/bin/env julia
#
# Run JuliaFormatter over every *tracked* .jl file in Packages/ and Experiments/.
#
#   julia format-tree.jl            # report only, changes nothing
#   julia format-tree.jl --apply    # rewrite files in place
#
# Tracked files only. The tree carries a lot of untracked scratch work -- prototyping/,
# obsolete/, stray test scripts -- and reformatting that would create noise in files nobody
# has committed and nobody is reviewing.
#
# Each repo is formatted from inside its own directory so JuliaFormatter picks up that repo's
# .JuliaFormatter.toml. A repo with no config is SKIPPED rather than formatted with the
# built-in default: imposing a style on a repo that declares none is a decision for a person,
# not for this script. The skip is reported at the end of the run.
#
# One file at a time, printing before it starts and flushing. A whole-tree run is not safe to
# assume terminates -- one died inside SciML's `nest!` after 62 minutes of CPU -- and the point
# of the per-file line is that the log then names the file it died on.

#
# CRASH RESILIENCE. JuliaFormatter can hard-crash the process on a pathological file -- not an
# exception that `try` can catch, but a stack blow-up that takes the runtime with it.
# A generated file of 6 lines and 4.7 kB can reach 3.4 billion allocations before dying. So:
#
#   * before each file, the path is written to MARKER (overwritten each time);
#   * files listed in SKIPLIST are not attempted;
#   * `harness format` reruns this script, moving the marker into the skiplist after each crash,
#     until it exits cleanly. The skiplist is then the list of files JuliaFormatter cannot
#     handle, which is worth having on its own.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using JuliaFormatter

const ROOT = get(ENV, "RESEARCH_ROOT", joinpath(homedir(), "Research"))
const APPLY = "--apply" in ARGS
const MARKER = get(ENV, "FMT_MARKER", tempname())
const SKIPLIST = get(ENV, "FMT_SKIPLIST", "")

const SKIP = isempty(SKIPLIST) || !isfile(SKIPLIST) ? Set{String}() :
             Set(filter(!isempty, strip.(readlines(SKIPLIST))))

function repos()
    out = String[]
    for tree in ("Packages", "Experiments")
        d = joinpath(ROOT, tree)
        isdir(d) || continue
        for name in sort(readdir(d))
            p = joinpath(d, name)
            isdir(joinpath(p, ".git")) && push!(out, p)
        end
    end
    out
end

"""
Directories excluded wholesale. `prototyping/`, `legacy/` and `obsolete/` hold work that is
either superseded or never was source in the first place, such as ModelingToolkit code
generation: six-line files whose longest line is 893 818 characters. Reformatting those is
meaningless, and some of them hard-crash JuliaFormatter outright.
"""
const EXCLUDED_DIRS = ("prototyping", "legacy", "obsolete")

excluded(path) = any(d -> d in split(path, '/'), EXCLUDED_DIRS)

tracked(repo) = filter(f -> !isempty(f) && !excluded(f),
    split(read(`git -C $repo ls-files "*.jl"`, String), '\n'))

function main()
    APPLY || println("REPORT ONLY -- no file will be written. Pass --apply to format.\n")
    total = changed = skipped_files = 0
    skipped_repos = String[]
    changed_files = String[]

    for repo in repos()
        name = basename(repo)
        if !isfile(joinpath(repo, ".JuliaFormatter.toml"))
            push!(skipped_repos, name)
            println("== $name  SKIPPED: no .JuliaFormatter.toml"); flush(stdout)
            continue
        end
        files = tracked(repo)
        println("== $name  ($(length(files)) tracked .jl)"); flush(stdout)

        cd(repo) do
            for f in files
                isfile(f) || continue
                key = "$name/$f"
                if key in SKIP
                    println("   $f  SKIPPED (known to crash JuliaFormatter)"); flush(stdout)
                    skipped_files += 1
                    continue
                end
                total += 1
                write(MARKER, key)              # so the wrapper knows what died
                print("   $f "); flush(stdout)
                before = read(f, String)
                t = @elapsed try
                    format(f; overwrite = APPLY)
                catch e
                    println("ERROR ", sprint(showerror, e)[1:min(end, 120)]); flush(stdout)
                    skipped_files += 1
                    continue
                end
                after = read(f, String)
                if APPLY
                    if after != before
                        changed += 1; push!(changed_files, "$name/$f")
                        println("CHANGED  ", round(t; digits = 1), "s")
                    else
                        println("ok  ", round(t; digits = 1), "s")
                    end
                else
                    # overwrite=false: `format` returns true when already formatted
                    ok = format(f; overwrite = false)
                    ok || (changed += 1; push!(changed_files, "$name/$f"))
                    println(ok ? "ok" : "would change", "  ", round(t; digits = 1), "s")
                end
                flush(stdout)
            end
        end
    end

    isempty(MARKER) || (isfile(MARKER) && rm(MARKER; force = true))   # clean finish
    println("\n", "="^60)
    println(APPLY ? "reformatted" : "would reformat", ": $changed of $total tracked files")
    isempty(skipped_repos) || println("skipped repos (no .JuliaFormatter.toml): ",
                                      join(skipped_repos, ", "))
    skipped_files == 0 || println("skipped or errored files: $skipped_files")
    println("="^60)
end

main()
