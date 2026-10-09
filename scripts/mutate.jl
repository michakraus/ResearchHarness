# Check that tests test what they claim, in a copy of the package under ~/Research/.scratch/mutants/.
# The package itself is never touched.
#
#   julia --startup-file=no mutate.jl <package> <file> <from> <to> [<unit> ...]
#       Replace the one occurrence of <from> in <file> (relative to the package) by <to>, and run
#       the units. CAUGHT: a unit fails. SURVIVED: every unit passes, so no test sees the change.
#   julia --startup-file=no mutate.jl <package> --list <mutants.toml> [--only <verdict>] [<unit> ...]
#       Run each mutant of the list, one copy each, and print one verdict line per mutant and the
#       totals. A mutant is one or more edits, each the one occurrence of `from` in `file`:
#
#           [[mutant]]
#           name = "M1: no lower safeguard"
#           file = "src/step.jl"
#           from = "clamp(αn, 0.1α, 0.5α)"
#           to = "min(αn, 0.5α)"
#
#           [[mutant]]
#           name = "M2: every exit is a success"
#           [[mutant.edit]]
#           file = "src/step.jl"
#           from = "ok ? SUCCESS : FAILED"
#           to = "SUCCESS"
#           [[mutant.edit]]
#           file = "src/other.jl"
#           from = """
#           code = classify(φα, φ₀)"""
#           to = "code = SUCCESS"
#
#       TOML strings take Unicode and several lines with no shell quoting. The run-tests.jl log of
#       each mutant is named on its verdict line. An edit may carry `at`, the byte position of
#       `from` in the file as the mutant's earlier edits leave it; then `from` may occur more than
#       once, and the edit replaces the one at `at`. mutants.jl writes every mutant with `at`.
#   julia --startup-file=no mutate.jl <package> --warm <mutants.toml> [--jobs <n>] [--only <verdict>] [<unit> ...]
#       Run the list in warm worker processes (mutate-worker.jl), one copy each: each mutant is
#       included into its module, tested with failfast, fastest unit first, and restored. The
#       baseline runs again every 20 mutants and after the last; when it fails, every verdict
#       since the last baseline that passed is UNKNOWN. A mutant that passes its time limit,
#       max(60 s, 10 × the baseline) or MUTATE_TIME_LIMIT, is UNKNOWN, and a new worker goes on.
#       Every SURVIVED runs again cold, and the cold verdict counts; so do 10 of the CAUGHT, at
#       even steps, and if one of those is not caught cold, every other warm kill is UNKNOWN. A
#       mutant of several files, of a file that defines a module, or that deletes a top-level
#       statement, runs cold, because an include cannot remove a definition; so does one that
#       changes a struct, an abstract or primitive type or an @enum, because an include of it makes
#       a new type that the other files' methods do not name. A list with 20 warm mutants or fewer
#       (MUTATE_WARM_MIN) runs every mutant cold, n at a time, after the smoke mutant; the quality files of
#       the units run only in the cold runs. `--jobs <n>` deals the mutants out to n workers and
#       runs the cold runs n at a time, each process with one thread and one BLAS thread; one
#       worker by default. First each unit runs once with `--code-coverage`: a mutant runs only
#       the units that reach its lines, and a mutant whose lines the coverage lists but no unit
#       runs is NO-COVERAGE, a finding as SURVIVED is, and does not run. A mutant whose lines the
#       coverage does not list (a method that no unit compiles, a signature, a top-level
#       statement) runs every unit. Before the mutants, one smoke mutant runs cold: an `error`
#       call at the start of each function that a mutant changes. If it is not CAUGHT, the units
#       reach none of those functions, and every mutant is UNKNOWN.
#
#   Both list modes write the verdicts to <mutants>.result.json beside the list: each mutant's
#   file, line, operator, verdict, detail and edits, the tree hash and the units its verdict holds
#   for, and the survivors (SURVIVED and NO-COVERAGE) grouped by line. It holds the last run of
#   the list, whatever its units. A later run of the list
#   keeps a CAUGHT, SURVIVED or NO-COVERAGE of a mutant with the same edits when the tree hash
#   (Project.toml, Manifest.toml, src/, ext/ and test/) and the units are the same; a change in any
#   of those runs the mutant again. `--only <verdict>` runs only the mutants whose verdict in that
#   result is <verdict>, and the ones it does not hold; every other mutant keeps its verdict.
#   julia --startup-file=no mutate.jl <package> --check <mutants.toml>
#       Check each mutant of the list, as the modes above do before they run one, and run
#       nothing: VALID, or INVALID with the reason.
#
# The branch's tests on the base's code, PINS or FAILS, are pins.jl's.
#
# A <unit> is as for run-tests.jl. Without units, the units that the diff against origin/main
# reaches in the package are run. Each run compiles the copy once; in a large package, choose the
# units, and run only the mutants that the part's acceptance items name. The copy leaves out a
# manifest that another Julia resolved, as run-tests.jl does.
#
# A mutant is INVALID, and does not run, when an edit's `from` does not occur exactly once in its
# file, when a mutated file does not parse (JuliaSyntax), or when it adds an undefined name (the
# `undefined-name` findings of `fatou lint` on the mutated file that the original file does not
# have; the rule does not follow `include`, so only the difference counts). Such a mutant would
# fail to load and read as CAUGHT. The checks need JuliaSyntax 1.0, so Julia 1.12 or later, and
# `fatou` on the PATH.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using TOML
using JSON: JSON
using SHA: SHA
using JuliaSyntax: JuliaSyntax

pkgversion(JuliaSyntax) >= v"1" ||
    error("mutate.jl needs JuliaSyntax 1.0, which this Julia ($VERSION) does not resolve; run it with ~/.juliaup/bin/julia")

const RUNTESTS = joinpath(@__DIR__, "run-tests.jl")
julia(args...) = `$(Base.julia_cmd()) --startup-file=no $args`

module RunTests
include(joinpath(@__DIR__, "run-tests.jl"))
end

const copy_command = RunTests.copy_command

"A fresh copy of `pkg` under ~/Research/.scratch/mutants/, without a manifest of another Julia."
function fresh_copy(pkg)
    root = mkpath(expanduser("~/Research/.scratch/mutants"))
    copy = mktempdir(root; prefix = basename(rstrip(pkg, '/')) * "-")
    run(copy_command(pkg, copy, RunTests.foreign_manifests(pkg)))
    return copy
end

"An edit of a mutant: `from` in `file` becomes `to`, at the byte `at`, or where `from` occurs once."
const Edit = Tuple{String, String, String, Union{Int, Nothing}}

"`text` with the `from` that starts at the byte `at` replaced by `to`."
function mutated_at(text, from, to, at)
    bytes = codeunits(text)
    return String(vcat(bytes[1:(at - 1)], codeunits(to), bytes[(at + ncodeunits(from)):end]))
end

"""
The files that the edits change, as `file => mutated text`, with the edits applied in order; or
the reason an edit cannot apply: its `from` must be at its byte `at`, or occur exactly once.
"""
function mutated(pkg, edits)
    texts = Dict{String, String}()
    for (file, from, to, at) in edits
        path = joinpath(pkg, file)
        isfile(path) || return "$file does not exist"
        text = get(() -> read(path, String), texts, file)
        if at === nothing
            n = count(from, text)
            n == 1 || return "`$from` occurs $n times in $file; an edit needs exactly one, or `at`"
            texts[file] = replace(text, from => to)
        else
            stop = at + ncodeunits(from) - 1
            1 <= at && stop <= ncodeunits(text) && codeunits(text)[at:stop] == codeunits(from) ||
                return "`$from` is not at byte $at of $file"
            texts[file] = mutated_at(text, from, to, at)
        end
    end
    return texts
end

"""
The `undefined-name` findings of `fatou lint` on each of `texts`, as the names it flags, in one
call of `fatou`.
"""
function undefined_names(texts)
    isempty(texts) && return Vector{String}[]
    fatou = Sys.which("fatou")
    fatou === nothing && error("fatou is not on the PATH; mutate.jl needs it to check a mutant")
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/mutants")); prefix = "check-")
    files = [joinpath(dir, "$i.jl") for i in eachindex(texts)]
    foreach(write, files, texts)
    config = joinpath(dir, "fatou.toml")
    write(config, "[lint]\nselect = [\"undefined-name\"]\n")
    # fatou writes its findings to stderr
    buf = IOBuffer()
    run(pipeline(ignorestatus(`$fatou lint --config $config --output concise $files`);
        stdout = buf, stderr = buf))
    rm(dir; recursive = true)
    found = Dict(f => String[] for f in files)
    for m in eachmatch(r"^(.*\.jl):\d+:\d+: warning\[undefined-name\] `(.*)` is not defined$"m, String(take!(buf)))
        push!(found[m.captures[1]], m.captures[2])
    end
    return [found[f] for f in files]
end

"The elements of `new` that `old` does not account for, counted with their multiplicity."
function added(new, old)
    left = copy(old)
    return filter(new) do x
        i = findfirst(==(x), left)
        i === nothing || deleteat!(left, i)
        i === nothing
    end
end

const NAMES = Dict{String, Set{String}}()

"""
Every identifier in the `.jl` files under `src/` of `pkg`. `fatou`'s `undefined-name` flags a
name that another file defines, and an `@enum` member anywhere, so a name found here is no
undefined name.
"""
function package_names(pkg)
    get!(NAMES, pkg) do
        names = Set{String}()
        for (d, _, fs) in walkdir(joinpath(pkg, "src")), f in fs
            endswith(f, ".jl") || continue
            text = read(joinpath(d, f), String)
            tree = JuliaSyntax.parseall(JuliaSyntax.SyntaxNode, text; filename = f, ignore_errors = true)
            stack = [tree]
            while !isempty(stack)
                n = pop!(stack)
                JuliaSyntax.kind(n) == JuliaSyntax.K"Identifier" && push!(names, JuliaSyntax.sourcetext(n))
                c = JuliaSyntax.children(n)
                c === nothing || append!(stack, c)
            end
        end
        names
    end
end

"Why a mutated file does not parse, or `nothing`."
function parse_failure(file, text)
    try
        JuliaSyntax.parseall(JuliaSyntax.SyntaxNode, text; filename = file)
    catch e
        e isa JuliaSyntax.ParseError || rethrow()
        why = match(r"── (.*)", sprint(showerror, e))
        return "the mutated $file does not parse" * (why === nothing ? "" : ": $(why.captures[1])")
    end
    return nothing
end

"""
Why each mutant `(name, edits)` of `list` is INVALID, or `nothing`: every `from` is found, every
mutated file parses, and no mutated file adds a name that `fatou` finds undefined and no source
file of the package uses. `fatou` runs once for the mutated files and once for their originals.
"""
function invalid_all(pkg, list)
    why = Vector{Union{Nothing, String}}(nothing, length(list))
    todo = Tuple{Int, String, String}[]  # (mutant, file, mutated text) to lint
    for (i, (_, edits)) in enumerate(list)
        texts = mutated(pkg, edits)
        texts isa String && (why[i] = texts; continue)
        for (f, t) in texts
            why[i] = parse_failure(f, t)
            why[i] === nothing || break
        end
        why[i] === nothing && append!(todo, [(i, f, t) for (f, t) in texts])
    end
    originals = unique(f for (_, f, _) in todo)
    before = Dict(zip(originals, undefined_names([read(joinpath(pkg, f), String) for f in originals])))
    for ((i, file, _), names) in zip(todo, undefined_names([t for (_, _, t) in todo]))
        why[i] === nothing || continue
        unknown = filter(n -> !(n in package_names(pkg)), added(names, before[file]))
        isempty(unknown) ||
            (why[i] = "the mutated $file adds the undefined name " * join(("`$n`" for n in unknown), ", "))
    end
    return why
end

"Why the mutant `edits` of `pkg` is INVALID, or `nothing`."
invalid(pkg, edits) = only(invalid_all(pkg, [("", edits)]))

"Write the mutated files into the copy. The mutant is checked, so every edit applies."
function apply!(copy, edits)
    for (file, text) in mutated(copy, edits)
        write(joinpath(copy, file), text)
    end
end

describe(edits) = join(("$file: `$from` → `$to`" for (file, from, to, _) in edits), "; ")

"The mutants of a list file, as (name, edits), or a String that says why the list is not valid."
function read_list(file)
    isfile(file) || return "$file does not exist"
    toml = try
        TOML.parsefile(file)
    catch e
        e isa TOML.ParserError || rethrow()
        return "$file is no valid TOML: " * first(split(sprint(showerror, e), '\n'))
    end
    list = get(toml, "mutant", nothing)
    list isa Vector && !isempty(list) || return "$file holds no [[mutant]] table"
    out = Tuple{String, Vector{Edit}}[]
    for (i, m) in enumerate(list)
        name = string(get(m, "name", "mutant $i"))
        edits = get(m, "edit", [m])
        for e in edits
            all(k -> get(e, k, nothing) isa String, ("file", "from", "to")) ||
                return "$name: each edit needs the strings file, from and to"
            get(e, "at", 0) isa Integer || return "$name: `at` is a byte position, an integer"
        end
        push!(out, (name, Edit[(e["file"], e["from"], e["to"], get(e, "at", nothing)) for e in edits]))
    end
    return out
end

"The default units: those that the diff against origin/main reaches, as run-tests.jl selects them."
function default_units(pkg)
    listing = read(julia(RUNTESTS, pkg, "select"), String)
    return [m.captures[1] for m in eachmatch(r"^  test/(\S+) — "m, listing)]
end

"Run the units on the copy, then remove it. Return the exit code of run-tests.jl and its output."
function run_units(copy, units; quiet = false)
    out = IOBuffer()
    p = run(pipeline(ignorestatus(julia(RUNTESTS, copy, units...));
        stdout = quiet ? out : stdout, stderr = quiet ? out : stderr))
    rm(copy; recursive = true)
    return p.exitcode, String(take!(out))
end

"Run a checked mutant cold, in a copy and a new process of its own: its verdict and the detail."
function cold(pkg, edits, units)
    copy = fresh_copy(pkg)
    apply!(copy, edits)
    code, out = run_units(copy, units; quiet = true)
    log = match(r"log: (\S+)", out)
    detail = describe(edits) * (log === nothing ? "" : " — log: $(log.captures[1])")
    code in (0, 1) || return "UNKNOWN", "run-tests.jl exited $code; " * detail
    return code == 0 ? "SURVIVED" : "CAUGHT", detail
end

"Print the verdicts in the order of the list, and the totals; return the exit status."
function report(list, verdicts)
    counts = Dict("CAUGHT" => 0, "SURVIVED" => 0, "NO-COVERAGE" => 0, "UNKNOWN" => 0, "INVALID" => 0)
    for ((name, _), (verdict, detail)) in zip(list, verdicts)
        counts[verdict] += 1
        println("$verdict: $name — $detail")
    end
    # NO-COVERAGE, a finding as SURVIVED is, comes only from the warm mode, and only when there is one
    uncovered = counts["NO-COVERAGE"] == 0 ? "" : " $(counts["NO-COVERAGE"]) NO-COVERAGE,"
    println("\n$(counts["CAUGHT"]) CAUGHT, $(counts["SURVIVED"]) SURVIVED,$uncovered $(counts["UNKNOWN"]) UNKNOWN, $(counts["INVALID"]) INVALID, of $(length(list)) mutants")
    return counts["UNKNOWN"] + counts["INVALID"] == 0 ? 0 : 3
end

"The result file of a mutant list: beside it, with the extension `.result.json`."
result_path(list) = splitext(abspath(list))[1] * ".result.json"

"""
The hash of what a verdict depends on: `Project.toml`, `Manifest.toml` and every file under
`src/`, `ext/` and `test/`, with its path.
"""
function tree_hash(pkg)
    files = [f for f in ("Project.toml", "Manifest.toml") if isfile(joinpath(pkg, f))]
    for dir in ("src", "ext", "test")
        isdir(joinpath(pkg, dir)) || continue
        for (d, _, fs) in walkdir(joinpath(pkg, dir)), f in fs
            push!(files, relpath(joinpath(d, f), pkg))
        end
    end
    ctx = SHA.SHA256_CTX()
    for f in sort(files)
        SHA.update!(ctx, codeunits(f * "\0"))
        SHA.update!(ctx, read(joinpath(pkg, f)))
    end
    return bytes2hex(SHA.digest!(ctx))
end

"The line of the package's file where a mutant's first edit starts, or `nothing` where it does not apply."
function mutant_line(pkg, edits)
    file, from, _, at = first(edits)
    isfile(joinpath(pkg, file)) || return nothing
    text = read(joinpath(pkg, file), String)
    if at === nothing
        r = findfirst(from, text)
        r === nothing && return nothing
        at = first(r)
    end
    return count(==(UInt8('\n')), view(codeunits(text), 1:min(at - 1, ncodeunits(text)))) + 1
end

"What a printed detail adds to a verdict kept from the last result; the result holds the detail without it."
const KEPT = " — kept from the last result"

"""
The verdict that each mutant of `list` keeps from the result of `file`, with the tree it was
found on, or `nothing` where the mutant runs. Without `only`, a mutant with the same edits keeps a
CAUGHT, SURVIVED or NO-COVERAGE found on the same tree with the same units. With `only`, a mutant
runs if its verdict there is `only` or the result does not hold it; every other keeps its verdict.
"""
function kept_verdicts(file, list, units, tree, only)
    out = Vector{Union{Nothing, Tuple{Tuple{String, String}, String}}}(nothing, length(list))
    path = result_path(file)
    isfile(path) || return out
    earlier = Dict(Edit[(e["file"], e["from"], e["to"], e["at"]) for e in m["edits"]] => m
                   for m in JSON.parsefile(path)["mutants"])
    for (i, (_, edits)) in enumerate(list)
        m = get(earlier, edits, nothing)
        m === nothing && continue
        keep = only === nothing ?
               m["verdict"] in ("CAUGHT", "SURVIVED", "NO-COVERAGE") && m["tree"] == tree && m["units"] == units :
               m["verdict"] != only
        keep && (out[i] = ((m["verdict"], m["detail"] * KEPT), m["tree"]))
    end
    return out
end

"""
Write the verdicts of `list`, read from `file`, into its result file, and return the path: each
mutant's file, line, operator, verdict, detail and edits, with the tree and the units its verdict
holds for; and the survivors, SURVIVED and NO-COVERAGE, grouped by line.
"""
function write_result(pkg, file, list, verdicts, trees, units, tree)
    ops = [get(m, "operator", "") for m in TOML.parsefile(file)["mutant"]]
    ms = map(enumerate(zip(list, verdicts, trees))) do (i, ((name, edits), (verdict, detail), t))
        Dict("name" => name, "file" => first(edits)[1], "line" => mutant_line(pkg, edits),
            "operator" => ops[i], "verdict" => verdict, "detail" => chopsuffix(detail, KEPT),
            "tree" => t, "units" => units,
            "edits" => [Dict("file" => f, "from" => a, "to" => b, "at" => at) for (f, a, b, at) in edits])
    end
    groups = Dict{Tuple{String, Int}, Vector{String}}()
    for m in ms
        m["verdict"] in ("SURVIVED", "NO-COVERAGE") &&
            push!(get!(Vector{String}, groups, (m["file"], something(m["line"], 0))), m["name"])
    end
    survivors = [Dict("file" => f, "line" => l, "mutants" => names) for ((f, l), names) in sort(collect(groups))]
    path = result_path(file)
    write(path, JSON.json(Dict("package" => pkg, "list" => abspath(file), "units" => units, "tree" => tree,
            "mutants" => ms, "survivors_by_line" => survivors); pretty = 2))
    return path
end

function run_list(pkg, file, units; only = nothing)
    list = read_list(file)
    list isa String && (println(stderr, list); return 2)
    tree = tree_hash(pkg)
    kept = kept_verdicts(file, list, sort(units), tree, only)
    verdicts = map(zip(list, invalid_all(pkg, list), kept)) do ((_, edits), why, k)
        why !== nothing ? ("INVALID", why) : k !== nothing ? first(k) : cold(pkg, edits, units)
    end
    status = report(list, verdicts)
    trees = [k === nothing ? tree : last(k) for k in kept]
    println("result: ", write_result(pkg, file, list, verdicts, trees, sort(units), tree))
    return status
end

"""
The module of each file under `src/` that the package's module file includes, as the path of
module names from the package down; a file that defines a module itself is not in it.
"""
function include_modules(pkg)
    name = TOML.parsefile(joinpath(pkg, "Project.toml"))["name"]
    out = Dict{String, Vector{String}}()
    function scan(rel, path)
        tree = JuliaSyntax.parseall(JuliaSyntax.SyntaxNode, read(joinpath(pkg, rel), String); filename = rel)
        defines_module = false
        function walk(n, path)
            k = JuliaSyntax.kind(n)
            c = JuliaSyntax.children(n)
            if k == JuliaSyntax.K"module"
                defines_module = true
                path = [path; JuliaSyntax.sourcetext(c[1])]
            elseif k == JuliaSyntax.K"call" && c !== nothing && length(c) == 2 &&
                   JuliaSyntax.sourcetext(c[1]) == "include" && JuliaSyntax.kind(c[2]) == JuliaSyntax.K"string"
                s = JuliaSyntax.children(c[2])
                if s !== nothing && length(s) == 1 && JuliaSyntax.kind(s[1]) == JuliaSyntax.K"String"
                    inc = normpath(joinpath(dirname(rel), JuliaSyntax.sourcetext(s[1])))
                    isfile(joinpath(pkg, inc)) && scan(inc, path)
                end
            end
            c === nothing || foreach(x -> walk(x, path), c)
        end
        walk(tree, path)
        defines_module || (out[rel] = path)
    end
    scan(joinpath("src", "$name.jl"), String[])
    # the module file itself defines the package's module; `scan` enters it from outside
    return Dict(f => p for (f, p) in out if !isempty(p))
end

const WORKER = joinpath(@__DIR__, "mutate-worker.jl")

"How many warm kills run again cold. Gremlins.jl, whose warm path once gave 2 false kills in 6, samples 10."
const COLD_SAMPLE = 10

"""
The most warm mutants that run cold instead: 20, or MUTATE_WARM_MIN. On the round-1 heads of the
loop benchmark, 4–9 named mutants took 386–553 s warm, of which the warm phase took about 30 s and
the coverage runs about 240 s; cold they take about 16 s each.
"""
warm_min() = parse(Int, get(ENV, "MUTATE_WARM_MIN", "20"))

"""
The number of top-level statements of a file. An `include` of a mutated file cannot remove a
definition that the original made, so a mutant with fewer statements runs cold: in the check on
l13 of the loop benchmark, all 38 wrong warm verdicts were such deletions.
"""
function statements(text)
    c = JuliaSyntax.children(JuliaSyntax.parseall(JuliaSyntax.SyntaxNode, text; ignore_errors = true))
    return c === nothing ? 0 : length(c)
end

"""
The source text of each type definition of a file: `struct`, `abstract type`, `primitive type` and
`@enum`. Since Julia 1.12 an `include` that changes one makes a new type, and the restore another,
so the methods of the other files, whose signatures name the first type, no longer apply: on l14
of the loop benchmark, one deleted field made the next baseline fail in three workers.
"""
function type_definitions(text)
    out = String[]
    function walk(n)
        k = JuliaSyntax.kind(n)
        c = JuliaSyntax.children(n)
        if k in (JuliaSyntax.K"struct", JuliaSyntax.K"abstract", JuliaSyntax.K"primitive") ||
           k == JuliaSyntax.K"macrocall" && c !== nothing && JuliaSyntax.sourcetext(c[1]) in ("enum", "@enum")
            push!(out, JuliaSyntax.sourcetext(n))
        elseif c !== nothing
            foreach(walk, c)
        end
    end
    walk(JuliaSyntax.parseall(JuliaSyntax.SyntaxNode, text; ignore_errors = true))
    return out
end

"The lines of `orig` that `text` changes: those between the common prefix and the common suffix."
function changed_lines(orig, text)
    a, b = codeunits(orig), codeunits(text)
    p = 0
    while p < min(length(a), length(b)) && a[p + 1] == b[p + 1]
        p += 1
    end
    s = 0
    while s < min(length(a), length(b)) - p && a[end - s] == b[end - s]
        s += 1
    end
    line(byte) = count(==(UInt8('\n')), view(a, 1:(byte - 1))) + 1
    start = min(p + 1, length(a))
    return line(start):line(max(start, length(a) - s))
end

"The line counts of the files under `copy`'s `src/` in an LCOV file, as `relpath => line => count`."
function read_lcov(info, copy)
    out = Dict{String, Dict{Int, Int}}()
    file = nothing
    for l in eachline(info)
        if startswith(l, "SF:")
            path = l[4:end]
            file = startswith(path, joinpath(copy, "src")) ? relpath(path, copy) : nothing
        elseif startswith(l, "DA:") && file !== nothing
            line, n = parse.(Int, split(l[4:end], ',')[1:2])
            counts = get!(Dict{Int, Int}, out, file)
            counts[line] = max(get(counts, line, 0), n)
        end
    end
    return out
end

"""
The line coverage of each unit of `warm_units`, as `unit => relpath => line => count`: each unit
runs once, in a worker with no mutant and `--code-coverage`, `n` at a time, on one copy.
`nothing` when a coverage run fails.
"""
function unit_coverage(pkg, warm_units, n, dir)
    copy = fresh_copy(pkg)
    name = TOML.parsefile(joinpath(pkg, "Project.toml"))["name"]
    log = joinpath(dir, "coverage.log")
    maps = asyncmap(collect(enumerate(warm_units)); ntasks = n) do (k, u)
        job, info = joinpath(dir, "coverage-$k.toml"), joinpath(dir, "coverage-$k.info")
        open(io -> TOML.print(io, Dict("package" => name, "units" => [joinpath(copy, "test", u)],
                "every" => 20, "results" => joinpath(dir, "coverage-$k.txt"), "mutant" => Dict{String, Any}[])), job, "w")
        p = run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $(RunTests.CHECKBOUNDS) --code-coverage=user --code-coverage=$info --project=$copy $WORKER $job 1`);
            stdout = log, stderr = log, append = true))
        p.exitcode == 0 && isfile(info) ? read_lcov(info, copy) : nothing
    end
    rm(copy; recursive = true, force = true)
    any(isnothing, maps) && return nothing
    return Dict(zip(warm_units, maps))
end

"""
The units of `warm_units` that reach a line of `lines` in `file`, by `cov`; `:none` when the
coverage lists one of those lines and no unit runs it; `nothing` when the coverage lists none of
them, as for a method that no unit compiles, a signature or a top-level statement, so that every
unit must run.
"""
function reaching(cov, warm_units, file, lines)
    counts(u) = get(cov[u], file, Dict{Int, Int}())
    any(u -> any(l -> haskey(counts(u), l), lines), warm_units) || return nothing
    reach = [u for u in warm_units if any(l -> get(counts(u), l, 0) > 0, lines)]
    return isempty(reach) ? :none : reach
end

"The call that the smoke mutant puts at the start of a function."
const SMOKE = "error(\"mutate.jl smoke\")"

"""
The edits of the smoke mutant of the mutants `idx` of `list`: `SMOKE` at the start of the body of
each outermost function that holds the first edit of one of them. A unit that reaches a changed
function fails on it, so a smoke mutant that survives shows that the units reach none of them.
`nothing` where no such edit lies inside a function with a body.
"""
function smoke_edits(pkg, list, idx)
    spots = Dict{String, Vector{Int}}()
    for i in idx
        file, from, _, at = first(list[i][2])
        text = read(joinpath(pkg, file), String)
        push!(get!(Vector{Int}, spots, file), at === nothing ? first(findfirst(from, text)) : at)
    end
    edits = Edit[]
    for (file, ats) in spots
        found = Edit[]
        function walk(n)
            c = JuliaSyntax.children(n)
            if JuliaSyntax.kind(n) == JuliaSyntax.K"function" && c !== nothing && length(c) == 2 &&
               any(in(JuliaSyntax.byte_range(n)), ats)
                body = c[2]
                stmts = JuliaSyntax.children(body)
                if JuliaSyntax.kind(body) != JuliaSyntax.K"block"
                    # a short-form body is one expression
                    r = JuliaSyntax.byte_range(body)
                    push!(found, (file, "", ")", last(r) + 1), (file, "", "($SMOKE; ", first(r)))
                elseif stmts !== nothing && !isempty(stmts)
                    push!(found, (file, "", "$SMOKE; ", first(JuliaSyntax.byte_range(stmts[1]))))
                end
                return
            end
            c === nothing || foreach(walk, c)
        end
        walk(JuliaSyntax.parseall(JuliaSyntax.SyntaxNode, read(joinpath(pkg, file), String); filename = file))
        # from the end of the file to its start, so that each `at` holds after the edits before it
        append!(edits, sort(found; by = e -> e[4], rev = true))
    end
    return isempty(edits) ? nothing : edits
end

"""
Run `jobs` in one warm worker process on a copy of its own, in `dir`; write each verdict into
`verdicts` and add the worker's times to `spent`.
"""
function drive_worker(pkg, jobs, warm_units, dir, verdicts, spent)
    mkpath(dir)
    copy = fresh_copy(pkg)
    for j in jobs
        j["path"] = joinpath(copy, j["file"])
        haskey(j, "reach") && (j["units"] = [joinpath(copy, "test", u) for u in j["reach"]])
    end
    results = joinpath(dir, "results.txt")
    log = joinpath(dir, "worker.log")
    job = joinpath(dir, "job.toml")
    open(io -> TOML.print(io, Dict("package" => TOML.parsefile(joinpath(pkg, "Project.toml"))["name"],
            "units" => [joinpath(copy, "test", u) for u in warm_units], "every" => 20,
            "results" => results, "mutant" => jobs)), job, "w")
    limit_env = get(ENV, "MUTATE_TIME_LIMIT", nothing)
    seen, pos, limit = 0, 1, 600.0
    # the jobs up to `confirmed` ran before a baseline that passed; a failing baseline makes the
    # verdicts after it UNKNOWN, because the process may have been wrong since then
    confirmed = 0
    lines() = isfile(results) ? readlines(results) : String[]
    # SIGKILL: a worker that gets SIGTERM inside a test run can hang in its exit hooks
    stop(proc) = process_exited(proc) || (kill(proc, Base.SIGKILL); wait(proc))
    done = isempty(jobs)
    while !done
        proc = run(pipeline(`$(Base.julia_cmd()) --startup-file=no $(RunTests.CHECKBOUNDS) --project=$copy $WORKER $job $pos`;
            stdout = log, stderr = log, append = true); wait = false)
        waited = time()
        # read the worker's lines until it writes DONE or a failing baseline, or stops, or hangs;
        # after the last result it still runs the final baseline
        while !done
            new = lines()[(seen + 1):end]
            if isempty(new)
                why = process_exited(proc) ? "the worker stopped; log: $log" :
                      time() - waited > limit ? "the time limit of $(round(Int, limit)) s" : nothing
                if why === nothing
                    sleep(0.1)
                    continue
                end
                stop(proc)
                if pos <= length(jobs)
                    # no result for the mutant at `pos`; a new worker goes on after it
                    j = jobs[pos]
                    verdicts[j["i"]] = ("UNKNOWN", j["detail"] * " — " * why)
                    write(j["path"], read(joinpath(pkg, relpath(j["path"], copy)), String))
                    pos += 1
                    done = pos > length(jobs)
                else
                    # every result is in, but the final baseline did not report
                    for j in jobs[(confirmed + 1):end]
                        verdicts[j["i"]] = ("UNKNOWN", j["detail"] * " — the final baseline did not end: " * why)
                    end
                    done = true
                end
                break
            end
            for l in new
                seen += 1
                waited = time()
                if l == "DONE"
                    done = true
                elseif startswith(l, "PEAK ")
                    spent["peak"] = max(get(spent, "peak", 0.0), parse(Float64, l[6:end]))
                elseif startswith(l, "BASELINE FAIL")
                    for j in jobs[(confirmed + 1):end]
                        verdicts[j["i"]] = ("UNKNOWN", j["detail"] * " — " * lowercase(l[10:end]) * "; log: $log")
                    end
                    done = true
                elseif startswith(l, "BASELINE FINAL")
                    spent["baseline"] += parse(Float64, l[16:end])
                    confirmed = length(jobs)
                elseif startswith(l, "BASELINE ")
                    b = parse(Float64, l[10:end])
                    limit = limit_env === nothing ? max(60.0, 10b) : parse(Float64, limit_env)
                elseif startswith(l, "TIMES ")
                    w = split(l)
                    for k in ("apply", "test", "restore", "baseline")
                        spent[k] += parse(Float64, w[findfirst(==(k), w) + 1])
                    end
                    w[end] == "0.0" || (confirmed = pos - 1)
                elseif startswith(l, "RESULT ")
                    _, i, secs, verdict = split(l, ' '; limit = 4)
                    j = jobs[pos]
                    v = first(split(verdict))
                    units_s = haskey(j, "reach") ? ", $(length(j["reach"])) of $(length(warm_units)) units" : ""
                    j["warm"] = "warm, $secs s$units_s"
                    verdicts[j["i"]] = (v, j["detail"] * " — " * j["warm"] *
                                           (v == "UNKNOWN" ? ": " * verdict[9:end] : ""))
                    pos += 1
                end
            end
        end
        stop(proc)
    end
    rm(copy; recursive = true, force = true)
end

"""
Run the mutants of `file` in `n` warm worker processes, each on a copy of its own, and every
survivor and a sample of the kills again cold, `n` at a time. A mutant of several files, of a
file that defines a module, or that deletes a top-level statement or changes a type definition
runs cold. The quality files of
`units` do not run in the workers, because the methods that the tests define stay in a process.
"""
function run_warm(pkg, file, units; n = 1, only = nothing)
    list = read_list(file)
    list isa String && (println(stderr, list); return 2)
    # n processes at once: each runs one Julia thread and one BLAS thread
    n > 1 && (ENV["JULIA_NUM_THREADS"] = "1"; ENV["OPENBLAS_NUM_THREADS"] = "1")
    why = invalid_all(pkg, list)
    tree = tree_hash(pkg)
    kept = kept_verdicts(file, list, sort(units), tree, only)
    trees = [k === nothing ? tree : last(k) for k in kept]
    finish(verdicts) = (status = report(list, verdicts);
        println("result: ", write_result(pkg, file, list, verdicts, trees, sort(units), tree)); status)
    test = joinpath(pkg, "test")
    entries = RunTests.named(RunTests.units(pkg), units)
    quality = [relpath(e.path, test) for e in entries if startswith(relpath(e.path, test), "quality/")]
    isempty(quality) || println("The warm mode leaves out $(join(quality, ", ")): a quality check sees the methods the tests leave.")
    warm_units = [relpath(e.path, test) for e in entries if !(relpath(e.path, test) in quality)]
    mods = include_modules(pkg)
    verdicts = Vector{Tuple{String, String}}(undef, length(list))
    # kept after the run: the detail of an UNKNOWN names the worker's log in it
    dir = mktempdir(mkpath(expanduser("~/Research/.scratch/mutants")); prefix = "warm-", cleanup = false)
    jobs = Dict{String, Any}[]
    # each cold run: (list index, what the detail adds, whether a cold CAUGHT confirms a warm kill)
    colds = Tuple{Int, String, Bool}[]
    for (i, ((_, edits), w)) in enumerate(zip(list, why))
        if w !== nothing
            verdicts[i] = ("INVALID", w)
            continue
        elseif kept[i] !== nothing
            verdicts[i] = first(kept[i])
            continue
        end
        texts = mutated(pkg, edits)
        f = first(keys(texts))
        orig = read(joinpath(pkg, f), String)
        if length(texts) > 1 || !haskey(mods, f) || isempty(warm_units) ||
           statements(texts[f]) < statements(orig) || type_definitions(texts[f]) != type_definitions(orig)
            reason = length(texts) > 1 ? "it changes several files" :
                     isempty(warm_units) ? "no unit runs warm" :
                     !haskey(mods, f) ? "$f defines a module" :
                     statements(texts[f]) < statements(orig) ? "it deletes a top-level statement" :
                     "it changes a type definition"
            push!(colds, (i, "runs cold: $reason", false))
            continue
        end
        text = joinpath(dir, "$i.jl")
        write(text, texts[f])
        push!(jobs, Dict{String, Any}("i" => i, "file" => f, "module" => mods[f], "text" => text,
            "detail" => describe(edits), "lines" => changed_lines(read(joinpath(pkg, f), String), texts[f])))
    end
    # a short list runs cold: the coverage runs and the cold kill sample cost more than the warm
    # phase saves
    if 0 < length(jobs) <= warm_min()
        append!(colds, [(j["i"], "runs cold: $(length(jobs)) warm mutants, $(warm_min()) or fewer", false) for j in jobs])
        empty!(jobs)
    end
    nkept = count(!isnothing, kept)
    nkept == 0 || println("kept: $nkept verdicts from $(result_path(file))")
    # the smoke mutant: if the units reach no function that a mutant changes, no verdict means anything
    torun = [[j["i"] for j in jobs]; [c[1] for c in colds]]
    smoke = isempty(torun) ? nothing : smoke_edits(pkg, list, torun)
    if !isempty(torun) && smoke === nothing
        println("smoke: none, because no mutant lies inside a function with a body")
    elseif smoke !== nothing
        nf = count(e -> occursin(SMOKE, e[3]), smoke)
        bad = invalid(pkg, smoke)
        sv, sd = bad === nothing ? cold(pkg, smoke, units) : ("INVALID", bad)
        println("smoke: $sv — `$SMOKE` at the start of $nf functions that the mutants change")
        if sv != "CAUGHT"
            # the cause and the log, without the smoke mutant's edits
            log = match(r"log: (\S+)", sd)
            cause = sv == "INVALID" ? sd : first(split(sd, "; "))
            reason = (sv == "SURVIVED" ?
                      "the smoke mutant survived: the units reach none of the $nf functions that the mutants change" :
                      "the smoke mutant is $sv: $cause") * (log === nothing ? "" : "; log: $(log.captures[1])")
            for i in torun
                verdicts[i] = ("UNKNOWN", describe(list[i][2]) * " — " * reason)
            end
            finish(verdicts)
            return 3
        end
    end
    # one coverage run per unit: a mutant runs only the units that reach its lines, and one on a
    # line that the coverage lists but no unit runs is NO-COVERAGE, and does not run
    t_cov = @elapsed cov = isempty(jobs) ? nothing : unit_coverage(pkg, warm_units, n, dir)
    cov === nothing && !isempty(jobs) && println("The coverage runs failed, so every mutant runs every unit; log: $(joinpath(dir, "coverage.log"))")
    uncovered = Set{Int}()
    if cov !== nothing
        for j in jobs
            r = reaching(cov, warm_units, j["file"], j["lines"])
            if r === :none
                verdicts[j["i"]] = ("NO-COVERAGE", j["detail"] * " — no unit runs line $(first(j["lines"]))" *
                                                   (length(j["lines"]) > 1 ? "–$(last(j["lines"]))" : ""))
                push!(uncovered, j["i"])
            elseif r !== nothing
                j["reach"] = r
            end
        end
        filter!(j -> !(j["i"] in uncovered), jobs)
    end
    for j in jobs
        delete!(j, "lines")
    end
    spent = Dict("apply" => 0.0, "test" => 0.0, "restore" => 0.0, "baseline" => 0.0)
    # the mutants are dealt out in turn, so that each worker gets every file's mutants
    shares = filter(!isempty, [jobs[k:n:end] for k in 1:n])
    t_warm = @elapsed @sync for (k, share) in enumerate(shares)
        @async drive_worker(pkg, share, warm_units, joinpath(dir, "worker-$k"), verdicts, spent)
    end
    # every survivor runs again cold, and the cold verdict counts; so does a sample of the warm
    # kills, at even steps through the list: one that is not caught cold means a worker can invent
    # kills, so no unchecked warm kill counts
    survivors = [j for j in jobs if verdicts[j["i"]][1] == "SURVIVED"]
    kills = [j for j in jobs if verdicts[j["i"]][1] == "CAUGHT"]
    sample = kills[unique(round.(Int, range(1, length(kills); length = min(COLD_SAMPLE, length(kills)))))]
    append!(colds, [(j["i"], "SURVIVED $(j["warm"]), cold again", false) for j in survivors])
    append!(colds, [(j["i"], "CAUGHT $(j["warm"]), cold again", true) for j in sample])
    wrong = String[]
    asyncmap(colds; ntasks = n) do (i, note, was_kill)
        cv, cd = cold(pkg, list[i][2], units)
        verdicts[i] = (cv, cd * " — $note" * (startswith(note, "runs") ? "" : ": $cv"))
        was_kill && cv != "CAUGHT" && push!(wrong, list[i][1])
    end
    again = length(survivors)
    if !isempty(wrong)
        for j in setdiff(kills, sample)
            verdicts[j["i"]] = ("UNKNOWN", j["detail"] * " — CAUGHT warm, but a sampled warm kill was not caught cold")
        end
    end
    status = finish(verdicts)
    isempty(wrong) || println("The warm kills are not trusted: not caught cold: $(join(wrong, "; "))")
    split_s = join(("$k $(round(Int, spent[k])) s" for k in ("apply", "test", "restore", "baseline")), ", ")
    workers = length(shares) == 1 ? "one worker" : "$(length(shares)) workers"
    peak = haskey(spent, "peak") ? ", peak $(round(spent["peak"] / 2^30; digits = 1)) GiB per worker" : ""
    println("warm: $(length(jobs)) mutants in $(round(Int, t_warm)) s, $workers ($split_s$peak); $again survivors and $(length(sample)) kills run again cold")
    cov === nothing ||
        println("coverage: $(length(warm_units)) units in $(round(Int, t_cov)) s; $(length(uncovered)) mutants NO-COVERAGE, $(count(j -> haskey(j, "reach"), jobs)) of $(length(jobs)) run only the units that reach them")
    return isempty(wrong) ? status : 3
end

function check_list(pkg, file)
    list = read_list(file)
    list isa String && (println(stderr, list); return 2)
    bad = 0
    for ((name, _), why) in zip(list, invalid_all(pkg, list))
        why === nothing ? println("VALID: $name") : (bad += 1; println("INVALID: $name — $why"))
    end
    println("\n$(length(list) - bad) VALID, $bad INVALID, of $(length(list)) mutants")
    return bad == 0 ? 0 : 3
end

function main(args)
    length(args) >= 3 || (println(stderr, "usage: mutate.jl <package> (<file> <from> <to> | --list <mutants.toml> [--only <verdict>] | --warm <mutants.toml> [--jobs <n>] [--only <verdict>] | --check <mutants.toml>) [<unit> ...]"); return 2)
    pkg = abspath(expanduser(args[1]))
    args[2] == "--base" &&
        (println(stderr, "`--base` is pins.jl now: julia --startup-file=no pins.jl <package> <ref> [<unit> ...]"); return 2)
    args[2] == "--check" && return check_list(pkg, args[3])
    mode = args[2] in ("--list", "--warm") ? args[2] : "edit"
    units = mode == "edit" ? args[5:end] : args[4:end]
    n = 1
    k = findfirst(==("--jobs"), units)
    if k !== nothing
        mode == "--warm" || (println(stderr, "`--jobs` is for `--warm` only."); return 2)
        m = k < length(units) ? tryparse(Int, units[k + 1]) : nothing
        m isa Int && m >= 1 || (println(stderr, "`--jobs` needs a whole number of workers, 1 or more."); return 2)
        n = m
        deleteat!(units, k:(k + 1))
    end
    only = nothing
    k = findfirst(==("--only"), units)
    if k !== nothing
        mode in ("--list", "--warm") || (println(stderr, "`--only` is for `--list` and `--warm`."); return 2)
        v = k < length(units) ? units[k + 1] : ""
        v in ("CAUGHT", "SURVIVED", "NO-COVERAGE", "UNKNOWN") ||
            (println(stderr, "`--only` needs a verdict: CAUGHT, SURVIVED, NO-COVERAGE or UNKNOWN."); return 2)
        isfile(result_path(args[3])) ||
            (println(stderr, "`--only` reads $(result_path(args[3])), which does not exist: run the list once first."); return 2)
        only = v
        deleteat!(units, k:(k + 1))
    end
    # run-tests.jl reads a first unit `list`, `select` or `affected` as a mode, whose exit status is
    # no verdict on the mutant; `full` runs the suite, and a later unit is a label
    !isempty(units) && units[1] in ("list", "select", "affected") &&
        (println(stderr, "`$(units[1])` is a mode of run-tests.jl, not a unit."); return 2)
    mode == "edit" && length(args) < 4 && (println(stderr, "a mutant needs <file> <from> <to>"); return 2)
    isempty(units) && (units = default_units(pkg))
    isempty(units) && (println("No unit to run."); return 2)
    mode == "--list" && return run_list(pkg, args[3], units; only)
    mode == "--warm" && return run_warm(pkg, args[3], units; n, only)
    edits = Edit[(args[2], args[3], args[4], nothing)]
    why = invalid(pkg, edits)
    why === nothing || (println("\nINVALID — $why"); return 3)
    copy = fresh_copy(pkg)
    apply!(copy, edits)
    what = describe(edits)
    code, _ = run_units(copy, units)
    code in (0, 1) || (println("\nUNKNOWN — run-tests.jl exited $code, so no verdict: $what"); return 3)
    println("\n", code == 0 ? "SURVIVED — no unit sees the mutant" : "CAUGHT", ": $what")
    return 0
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
