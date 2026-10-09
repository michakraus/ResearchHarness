# The gate of a head: the checks that a script can run before a critic, in one short report.
#
#   julia --startup-file=no gate.jl <package> <out-dir> [--base <ref>] [--named <list>]... [--jobs <n>] [--no-sweep]
#
# In this order, each with its full output in a log under <out-dir>:
#
#   tests      run-tests.jl <package> affected: the test files the diff reaches, and test/quality/,
#              so also the doctests where test/quality/doctests.jl exists
#   named      mutate.jl --warm on a copy of each <list>: the totals, and each mutant that is not CAUGHT
#   generated  mutants.jl against <base>, then mutate.jl --warm --jobs <n> (4 by default): the totals,
#              and the survivors grouped by line; information for the critic, not a failure
#   format     JuliaFormatter, with the package's .JuliaFormatter.toml, on the .jl files that the
#              diff against <base> adds or changes
#
# and writes <out-dir>/gate.md. The mutant steps run with mutate.jl's default units: those that the
# diff against origin/main reaches. A list is copied into <out-dir> first, so that its result file
# is the gate's, and no earlier run's verdict is kept.
#
# Exit 0: every step that can fail passes. 1: one fails. 2: bad arguments. 3: a step gave no
# verdict, and no other failed.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using JSON: JSON
using JuliaFormatter: JuliaFormatter

const SCRIPTS = @__DIR__
julia_cmd(script, args...) = `$(Base.julia_cmd()) --startup-file=no $(joinpath(SCRIPTS, script)) $args`

"One step of the gate: its name, verdict (PASS, FAIL, UNKNOWN or INFO), numbers, detail lines, time and log."
struct Step
    name::String
    verdict::String
    numbers::String
    detail::Vector{String}
    secs::Float64
    log::String
end

"Run `cmd` with its output into `log`; return the exit code, the output and the time."
function logged(cmd, log)
    t = @elapsed p = open(io -> run(pipeline(ignorestatus(cmd); stdout = io, stderr = io)), log, "w")
    return p.exitcode, read(log, String), t
end

"The verdict of a `run-tests.jl` output with its exit code: the PASS or FAIL line, and the summary after it."
function tests_step(code, out, secs, log)
    lines = split(out, '\n')
    k = findfirst(l -> occursin(r"^(PASS|FAIL) in \d+ s", l), lines)
    code in (0, 1) && k !== nothing ||
        return Step("tests", "UNKNOWN", "run-tests.jl exited $code", String.(last(lines, min(10, length(lines)))), secs, log)
    head = something(findfirst(l -> occursin(r"test files in", l), lines), k)
    summary = [String(l) for l in lines[(k + 1):end] if !isempty(strip(l))]
    return Step("tests", code == 0 ? "PASS" : "FAIL", strip(lines[head]), first(summary, 40), secs, log)
end

"The totals line of a `mutate.jl` output, or `nothing`."
totals(out) = (m = match(r"^(\d+ CAUGHT, .* of \d+ mutants)$"m, out); m === nothing ? nothing : m[1])

"""
The verdict of the named mutants, from `mutate.jl`'s exit code and output: PASS when every mutant
is CAUGHT, FAIL when one is SURVIVED or NO-COVERAGE, UNKNOWN when one has no verdict.
"""
function named_step(code, out, secs, log)
    t = totals(out)
    smoke = [String(l) for l in split(out, '\n') if startswith(l, "smoke:")]
    t === nothing && return Step("named", "UNKNOWN", "mutate.jl exited $code", smoke, secs, log)
    bad = [String(l) for l in split(out, '\n') if occursin(r"^(SURVIVED|NO-COVERAGE|UNKNOWN|INVALID): ", l)]
    verdict = any(l -> occursin(r"^(UNKNOWN|INVALID)", l), bad) ? "UNKNOWN" : isempty(bad) ? "PASS" : "FAIL"
    return Step("named", verdict, t, [smoke; bad], secs, log)
end

"""
The survivors of a mutate.jl result, one line per source line: `file:line`, and each mutant's
`from` → `to` there.
"""
function survivor_lines(result)
    r = JSON.parsefile(result)
    byname = Dict(m["name"] => m for m in r["mutants"])
    map(r["survivors_by_line"]) do s
        what = map(s["mutants"]) do n
            e = first(byname[n]["edits"])
            "`$(first(split(e["from"], '\n')))` → `$(first(split(e["to"], '\n')))`" *
            (byname[n]["verdict"] == "NO-COVERAGE" ? " (no unit runs it)" : "")
        end
        "$(s["file"]):$(s["line"]): " * join(what, "; ")
    end
end

"The generated sweep's step: information only, with the survivors by line."
function generated_step(code, out, secs, log, result)
    t = totals(out)
    (t === nothing || !isfile(result)) && return Step("generated", "UNKNOWN", "mutate.jl exited $code", String[], secs, log)
    smoke = [String(l) for l in split(out, '\n') if startswith(l, "smoke:")]
    return Step("generated", "INFO", t, [smoke; survivor_lines(result)], secs, log)
end

"The .jl files that the diff of `pkg` against `base` adds or changes."
changed_jl(pkg, base) =
    filter(f -> endswith(f, ".jl") && isfile(joinpath(pkg, f)),
        split(read(`git -C $pkg diff --name-only --diff-filter=AM $base`, String)))

"The format step: each changed file that JuliaFormatter would change."
function format_step(pkg, files)
    t = @elapsed bad = filter(f -> !JuliaFormatter.format(joinpath(pkg, f); overwrite = false), files)
    return Step("format", isempty(bad) ? "PASS" : "FAIL", "$(length(bad)) of $(length(files)) files not formatted",
        String.(bad), t, "")
end

"The gate's verdict over its steps: FAIL before UNKNOWN before PASS; INFO counts as PASS."
function verdict(steps)
    vs = [s.verdict for s in steps]
    "FAIL" in vs && return "FAIL", 1
    "UNKNOWN" in vs && return "UNKNOWN", 3
    return "PASS", 0
end

"The report: a table of the steps, then the detail of each step that has one."
function render(title, steps)
    v, _ = verdict(steps)
    io = IOBuffer()
    println(io, "# Gate — $title\n")
    bad = [s.name for s in steps if s.verdict in ("FAIL", "UNKNOWN")]
    println(io, "Verdict: $v", isempty(bad) ? "" : " — " * join(bad, ", "), "\n")
    println(io, "| step | verdict | numbers | time | log |\n|:--|:--|:--|--:|:--|")
    for s in steps
        println(io, "| $(s.name) | $(s.verdict) | $(s.numbers) | $(round(Int, s.secs)) s | $(isempty(s.log) ? "—" : "`$(s.log)`") |")
    end
    for s in steps
        isempty(s.detail) && continue
        println(io, "\n## $(s.name)\n")
        foreach(l -> println(io, "- ", l), s.detail)
    end
    return String(take!(io))
end

function main(args)
    usage = "usage: gate.jl <package> <out-dir> [--base <ref>] [--named <list>]... [--jobs <n>] [--no-sweep]"
    length(args) >= 2 || (println(stderr, usage); return 2)
    pkg, out = abspath(expanduser(args[1])), abspath(expanduser(args[2]))
    base, named, jobs, sweep = "origin/main", String[], 4, true
    rest = args[3:end]
    while !isempty(rest)
        a = popfirst!(rest)
        if a == "--no-sweep"
            sweep = false
        elseif a in ("--base", "--named", "--jobs") && !isempty(rest)
            v = popfirst!(rest)
            a == "--base" ? (base = v) : a == "--named" ? push!(named, abspath(expanduser(v))) :
            (jobs = something(tryparse(Int, v), 0))
        else
            println(stderr, usage)
            return 2
        end
    end
    jobs >= 1 || (println(stderr, "`--jobs` needs a whole number of workers, 1 or more."); return 2)
    for l in named
        isfile(l) || (println(stderr, "$l does not exist"); return 2)
    end
    mkpath(out)
    head = strip(read(`git -C $pkg rev-parse --short HEAD`, String))
    steps = Step[]
    log = joinpath(out, "tests.log")
    push!(steps, tests_step(logged(julia_cmd("run-tests.jl", pkg, "affected"), log)..., log))
    isfile(joinpath(pkg, "test", "quality", "doctests.jl")) ||
        push!(steps, Step("doctests", "INFO", "no test/quality/doctests.jl, so no doctest ran", String[], 0.0, ""))
    for (k, l) in enumerate(named)
        list = joinpath(out, "named-$k.toml")
        cp(l, list; force = true)
        log = joinpath(out, "named-$k.log")
        s = named_step(logged(julia_cmd("mutate.jl", pkg, "--warm", list), log)..., log)
        push!(steps, Step("named $(basename(l))", s.verdict, s.numbers, s.detail, s.secs, s.log))
    end
    if sweep
        list = joinpath(out, "generated.toml")
        log1, log = joinpath(out, "mutants.log"), joinpath(out, "generated.log")
        code, _, t1 = logged(julia_cmd("mutants.jl", pkg, list, base), log1)
        if code == 0
            code, o, t2 = logged(julia_cmd("mutate.jl", pkg, "--warm", list, "--jobs", string(jobs)), log)
            push!(steps, generated_step(code, o, t1 + t2, log, joinpath(out, "generated.result.json")))
        else
            push!(steps, Step("generated", "UNKNOWN", "mutants.jl exited $code", String[], t1, log1))
        end
    end
    push!(steps, format_step(pkg, changed_jl(pkg, base)))
    report = joinpath(out, "gate.md")
    write(report, render("$(basename(pkg)) at $head, base $base", steps))
    v, status = verdict(steps)
    println("Gate: $v — $report")
    return status
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
