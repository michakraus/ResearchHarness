# Census of the test layout of every package and experiment repository, as a Markdown table.
#
#   julia --startup-file=no test-census.jl [<root> ...]    (default: ~/Research/Packages ~/Research/Experiments)
#
# Per repository: how runtests.jl reaches its files (`@safetestset`, `@testset` around an
# `include`, a bare `include`, a nested runtests.jl), the gates on ARGS or ENV, where the test
# dependencies live, whether Aqua and JET run, the test files that runtests.jl does not reach, and
# the share of test files whose path mirrors a file under src/. The layout comes from the parser
# of test-layout.jl, the same one that `test-layout.jl --check` reads.

include(joinpath(@__DIR__, "test-layout.jl"))

function census(repo)
    L = layout(repo)
    t = L.test
    files = filter(f -> basename(f) != "runtests.jl", L.files)  # the census counts no runtests.jl
    # an `include("../src/…")` reaches no test file
    reached = Set(e.path for e in L.entries if startswith(e.path, normpath(t) * "/"))
    n(kind) = count(e -> e.kind === kind, L.entries)
    src = Set{String}()
    isdir(joinpath(repo, "src")) && for (d, _, fs) in walkdir(joinpath(repo, "src")), f in fs
        push!(src, replace(relpath(joinpath(d, f), joinpath(repo, "src")), r"\.jl$" => ""))
    end
    stem(f) = replace(relpath(f, t), r"(_tests?|_test)?\.jl$" => "")
    mirrored = count(f -> stem(f) in src, collect(reached))
    proj = read(joinpath(repo, "Project.toml"), String)
    deps = isfile(joinpath(t, "Project.toml")) ? "test/Project.toml" : has_section(proj, "targets") ? "[targets]" : "none"
    alltext = join((read(f, String) for f in files if isfile(f)), "\n")
    return (name = basename(repo), safe = n(:safetestset), testset = n(:testset),
            bare = n(:bare), nested = length(L.nested), gates = L.gates, deps = deps,
            aqua = occursin("Aqua", alltext), jet = occursin("JET", alltext),
            files = length(files), reached = length(reached),
            unreached = length(setdiff(Set(files), reached)), mirrored = mirrored,
            parse_error = !isempty(L.parse_errors))
end

if abspath(PROGRAM_FILE) == @__FILE__
    roots = isempty(ARGS) ? expanduser.(["~/Research/Packages", "~/Research/Experiments"]) : ARGS
    rows = [census(joinpath(r, d)) for r in roots for d in sort(readdir(r))
            if isfile(joinpath(r, d, "Project.toml")) && isdir(joinpath(r, d, ".git"))]
    println("| repository | files | reached | not reached | `@safetestset` | `@testset` include | bare include | nested runtests | gates | test deps | Aqua | JET | mirrors src |")
    println("|:--|--:|--:|--:|--:|--:|--:|--:|--:|:--|:-:|:-:|--:|")
    for r in rows
        println("| $(r.name)$(r.parse_error ? " (parse error)" : "") | $(r.files) | $(r.reached) | $(r.unreached) | $(r.safe) | $(r.testset) | $(r.bare) | $(r.nested) | $(r.gates) | $(r.deps) | $(r.aqua ? "yes" : "—") | $(r.jet ? "yes" : "—") | $(r.mirrored) of $(r.reached) |")
    end
end
