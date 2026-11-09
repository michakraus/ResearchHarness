# The dispatch delta of a head against a base: what a branch adds to the method table, and the new
# ambiguities and piracies, from both trees loaded side by side.
#
#   julia --startup-file=no dispatch-delta.jl <package> <base> [--timeout <s>] [--no-jet]
#
# <package> is the package's directory: its working tree, as it is, is the head. <base> is a git ref
# of it. The base goes with base-tree.jl into <run>/<Pkg>-base-<sha7>, under the run directory
# ~/Research/.scratch/dispatch-delta/<Pkg>-<stamp>-<pid>/. The head's Manifest.toml goes into the
# base tree, so that both sides load the same versions, where it holds every package under [deps]
# of the base; else the base resolves its own. Where another minor version of Julia resolved the
# head's Manifest.toml or test/Manifest.toml, neither side gets one, and the head runs from a copy
# without them, as in run-tests.jl. Each side then loads in a fresh process group of its own, both
# at once, as run-tests.jl loads a driver: --project=<tree>, the harness environment last in
# LOAD_PATH, TestEnv.activate(). Its own modules are the package's module tree and each extension
# that loads once the side loads the [weakdeps] that its test environment provides. It writes
# <run>/<side>.json, then runs JET into <run>/<side>-jet.json; its output goes to <run>/<side>.log.
# --timeout gives each side, and then each JET step, that many seconds (600 by default); past it,
# the side's process group is killed.
#
# The lines of the output:
#
#   FAIL: new own-own ambiguity: <key> | <key>          both methods in own modules
#   FAIL: new own-external ambiguity: <own> | <other>
#   FAIL: new piracy: <key> at <file>:<line>            Aqua's piracy hunt on the module tree, not ext/
#   FAIL: the head does not load: <error>               also an extension whose triggers the test
#                                                       environment provides and that does not load
#   UNKNOWN: the base does not load: <error>
#   UNKNOWN: <side> does not resolve: <error>           TestEnv.activate() failed
#   UNKNOWN: <side> timed out after <n> s
#   UNKNOWN: <side> ended by signal <n>                 a signal that the script did not send
#   UNKNOWN: <side> gave no result, exit code <n>       no JSON and no error file
#   UNKNOWN: jet: <side> timed out after <n> s          leaves the exit code to the other analyses,
#   UNKNOWN: jet: <side> ended with <signal or code>    as does a JET step that ends the side
#   INFO: added method: <key> at <file>:<line>          a new method of a generic that the base has,
#     other: <key> at <file>:<line>                     with every other method of an own generic and
#                                                       the intersecting ones of an external generic;
#                                                       the generic of a Core.kwcall method is its
#                                                       keyword function, and an external generic
#                                                       counts where the base loaded its package
#   INFO: new JET report: <type>: <message> in <key>
#   INFO: gone piracy | gone own-own ambiguity | gone own-external ambiguity | gone JET report: ...
#   INFO: dependency drift: <name> <base version> -> <head version>
#   Verdict: <PASS|FAIL|UNKNOWN> — <f> FAIL, <u> UNKNOWN, <i> INFO
#
# The key of a method is its signature with the full path of each name that Base and Core do not
# export, less the path of the package's root module, so that a `using` in the root module changes
# no key, with its type variables renamed _1, _2, … by position and the digits of gensym names
# stripped. A head that only reorders the `where` list of a method therefore changes its key: a
# finding of that method reads as new, and its old key as gone.
#
# Exit 0: PASS. 1: a FAIL line. 2: bad arguments. 3: no verdict — a base that does not load, a side
# that does not resolve or that timed out — and no FAIL line.

module BaseTree
include(joinpath(@__DIR__, "base-tree.jl"))
end

# run-tests.jl puts the harness's Julia environment first in LOAD_PATH, where JSON is; a side
# appends it instead.
module RunTests
include(joinpath(@__DIR__, "run-tests.jl"))
end

using JSON: JSON
using Dates: Dates
using Pkg: Pkg
using Test: Test
using TOML: TOML

const SCRIPT = @__FILE__
const HARNESS_ENV = RunTests.HARNESS_ENV
const USAGE = "usage: dispatch-delta.jl <package> <base> [--timeout <s>] [--no-jet]"

"""
The arguments as `(; pkg, base, name, timeout, jet)`, or the message that names a bad one. Every
argument that starts with `-` is an option.
"""
function arguments(args)
    pos, timeout, jet = String[], 600, true
    rest = collect(String, args)
    while !isempty(rest)
        a = popfirst!(rest)
        if a == "--no-jet"
            jet = false
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
    return (; pkg, base, name, timeout, jet)
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

"""
One record per own method: every method of `Core.methodtable` whose module is own, except the
methods of a function whose name starts with `#`. `others` holds the other methods of the generic:
all of them for an own generic, the intersecting ones for an external generic. The generic of a
`Core.kwcall` method is its keyword function, and its other methods are that function's
`Core.kwcall` methods. `generic_package` names the package of the generic's module.
"""
function method_records(ownset, root, tree)
    ms = Method[]
    Base.visit(Core.methodtable) do x
        parentmodule(x) in ownset && !startswith(string(x.name), "#") && push!(ms, x)
    end
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

"Write `d` as JSON into `path` at once, so that a reader never sees part of it."
function write_json(path, d)
    write(path * ".part", JSON.json(d))
    mv(path * ".part", path; force = true)
end

"""
The records of a side, written into `<rundir>/<side>.json`. Beside the keys that a reader of the
two files uses, `manifest` says whether the side's tree held a `Manifest.toml` when the side began.
`loaded` names each package that the side has loaded when it writes the file.
"""
function record(s, rundir, tree, name, root, tree_mods, own, aqua, manifest)
    ownset = Set(own)
    piracies = [where_is(m, root, tree) for mod in tree_mods for m in aqua.Piracy.hunt(mod)]
    write_json(joinpath(rundir, "$s.json"), Dict(
        "package" => name, "side" => s, "julia" => string(VERSION), "manifest" => manifest,
        "tools" => Dict("Aqua" => string(pkgversion(aqua))),
        "dependencies" => Dict(i.name => (i.version === nothing ? nothing : string(i.version)) for i in values(Pkg.dependencies())),
        "loaded" => sort!([p.name for p in keys(Base.loaded_modules)]),
        "methods" => method_records(ownset, root, tree),
        "ambiguities" => ambiguities(own, ownset, root),
        "piracies" => piracies))
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
whether the tree held a `Manifest.toml` before the activation. Returns the process's exit code; a
failed load writes `<side>.error`.
"""
function side(s, rundir, tree, name, jet, manifest)
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
    tree_mods, own = Base.invokelatest() do
        t, exts = module_tree(root), Module[]
        for x in keys(get(project, "extensions", Dict()))
            m = Base.get_extension(root, Symbol(x))
            m === nothing || module_tree(m, exts)
        end
        t, [t; exts]
    end
    Base.invokelatest(record, s, rundir, tree, name, root, tree_mods, own, aqua, manifest)
    jet || return 0
    j = Base.require(Main, :JET)
    reports = Base.invokelatest(jet_reports, j, root, own, tree)
    write_json(joinpath(rundir, "$s-jet.json"), Dict("JET" => string(pkgversion(j)), "reports" => reports))
    return 0
end

"The driver of a side: the harness environment last in LOAD_PATH, `TestEnv.activate()`, then `side`."
driver(s, rundir, tree, name, jet) = """
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
    exit(DispatchDelta.side($(repr(s)), $(repr(rundir)), $(repr(tree)), $(repr(name)), $jet, manifest))
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
Run both sides at once and wait for them. Each side is a process group of its own. A side gets
`timeout` seconds to write its JSON, and with JET `timeout` seconds more from that moment; past its
limit its process group is killed, as is each group still running when the script stops.
"""
function run_sides(rundir, trees, name, timeout, jet)
    logs = Dict(s => open(joinpath(rundir, "$s.log"), "w") for s in keys(trees))
    procs = Dict(map(collect(trees)) do (s, tree)
        drv = joinpath(rundir, "$s-driver.jl")
        write(drv, driver(s, rundir, tree, name, jet))
        cmd = Cmd(`$(Base.julia_cmd()) --startup-file=no --project=$tree $drv`; detach = true)
        s => run(pipeline(ignorestatus(cmd); stdout = logs[s], stderr = logs[s]); wait = false)
    end)
    t0, json_at, ends = time(), Dict{String, Float64}(), Dict{String, End}()
    try
        while length(ends) < length(procs)
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
            length(ends) < length(procs) && sleep(0.2)
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
a clean exit after that is the JET step's alone.
"""
function analyse(rundir, ends; timeout, jet)
    out, data, decisive = String[], Dict{String, Any}(), false
    jet_lost = Set{String}()
    for s in ("base", "head")
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
        append!(out, compare(data["base"], data["head"]))
        jet && isempty(jet_lost) && append!(out,
            compare_jet((JSON.parsefile(joinpath(rundir, "$s-jet.json")) for s in ("base", "head"))...))
    end
    jet || push!(out, "INFO: jet: not run (--no-jet)")
    f, u, i = (count(startswith(p), out) for p in ("FAIL: ", "UNKNOWN: ", "INFO: "))
    status = f > 0 ? 1 : decisive ? 3 : 0
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
    (; pkg, base, name, timeout, jet) = a
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
        ends = run_sides(rundir, Dict("base" => basetree, "head" => head), name, timeout, jet)
        out, status = analyse(rundir, ends; timeout, jet)
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
