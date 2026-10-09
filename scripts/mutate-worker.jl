# The warm worker of `mutate.jl --warm`. mutate.jl starts it; it is not run by hand.
#
#   julia --startup-file=no [--check-bounds=yes] --project=<copy> mutate-worker.jl <job.toml> <first>
#
# It loads the package of the copy and its test environment once, runs the units once as the
# baseline, and orders them fastest first. Then, for each mutant of the job from position <first>
# on, it writes the mutated file into the copy, includes it into its module, runs the units with
# failfast, writes the original back and includes it again. Every `every` mutants, and after the
# last one, the baseline runs again; if it fails, the worker stops with exit 4. It writes one line
# per event to the job's results file, so the tests' own output cannot garble the verdicts:
#
#   BASELINE <seconds>            the first baseline passed, in that time
#   BASELINE FAIL <why>           a baseline failed; the worker stops
#   BASELINE FINAL <seconds>      the baseline after the last mutant passed
#   PEAK <bytes>                  the worker's peak resident memory
#   RESULT <i> <seconds> <verdict>
#   TIMES <i> apply <s> test <s> restore <s> baseline <s>   where the seconds of the mutant went
#   DONE

using TOML

const JOB = TOML.parsefile(ARGS[1])
const FIRST = parse(Int, ARGS[2])
say(line) = open(io -> (println(io, replace(line, '\n' => ' ')); flush(io)), JOB["results"], "a")

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml. Last in LOAD_PATH: the package under test comes first, so its own dependencies
# win, as they did over the shared default environment.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || push!(LOAD_PATH, env)
end
using TestEnv
TestEnv.activate()
using Test

const PKG = Symbol(JOB["package"])
Core.eval(Main, :(using $PKG))
const ROOT = getfield(Main, PKG)

fresh() = Core.eval(Main, :(module $(gensym(:Unit)) using Test end))
quiet(f) = redirect_stdio(f; stdout = devnull, stderr = devnull)

"True when every unit passes; stop at the first failing unit and at its first failing test."
function passes(units)
    for u in units
        ok = try
            quiet(() -> @testset failfast = true "mutant" Base.include(fresh(), u))
            true
        catch
            false
        end
        ok || return false
    end
    return true
end

function baseline(units)
    for u in units
        passes([u]) || return u
    end
    return nothing
end

units = JOB["units"]
times = Float64[]
for u in units
    t = @elapsed ok = passes([u])
    ok || (say("BASELINE FAIL $u fails on the unmutated copy"); exit(4))
    push!(times, t)
end
const ORDER = units[sortperm(times)]
say("BASELINE $(round(sum(times); digits = 2))")

r2(t) = round(t; digits = 2)

for (n, m) in enumerate(JOB["mutant"][FIRST:end])
    path = m["path"]
    mod = foldl(getfield, Symbol.(m["module"][2:end]); init = ROOT)
    orig = read(path, String)
    write(path, read(m["text"], String))
    t0 = time()
    t_apply = t0
    verdict = try
        quiet(() -> Base.include(mod, path))
        t_apply = time()
        # with "units", only the units that reach the mutant's lines, in the baseline's order
        passes(haskey(m, "units") ? filter(in(Set(m["units"])), ORDER) : ORDER) ? "SURVIVED" : "CAUGHT"
    catch e
        "UNKNOWN the mutated file does not load: " * first(sprint(showerror, e), 120)
    end
    t_test = time()
    write(path, orig)
    quiet(() -> Base.include(mod, path))
    t_restore = time()
    say("RESULT $(m["i"]) $(r2(t_test - t0)) $verdict")
    t_base = 0.0
    if n % JOB["every"] == 0
        t_base = @elapsed bad = baseline(ORDER)
        bad === nothing || (say("BASELINE FAIL $bad fails after the mutant $(m["i"]) was restored"); exit(4))
    end
    say("TIMES $(m["i"]) apply $(r2(t_apply - t0)) test $(r2(t_test - t_apply)) restore $(r2(t_restore - t_test)) baseline $(r2(t_base))")
end
if (length(JOB["mutant"]) - FIRST + 1) % JOB["every"] != 0
    t = @elapsed bad = baseline(ORDER)
    bad === nothing || (say("BASELINE FAIL $bad fails after the last mutant was restored"); exit(4))
    say("BASELINE FINAL $(r2(t))")
end
say("PEAK $(Sys.maxrss())")
say("DONE")
