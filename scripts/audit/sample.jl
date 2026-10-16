# A seeded sample of loop parts, and one dossier per part for the failure taxonomy.
#
#   julia --startup-file=no sample.jl <data-dir> <seed> <n>
#
# Reads parts.tsv, run-parts.tsv, runs.tsv, reports.jsonl and prs.tsv of transcripts.jl and
# report.jl. Draws <n> parts of tier build or reviewed that are no benchmark: the parts sorted by
# the SHA-256 of "<seed>:<part>", the first <n>. The order does not depend on the Julia version.
# Adds every other part with an arbitrator run. Writes sample.tsv and dossiers/<NN>.md: the part's
# pull requests and, per run in time order, its numbers, the files that loaded, its prompt and its
# report.

let env = get(
        ENV,
        "RESEARCH_HARNESS_JULIA",
        joinpath(homedir(), ".local", "share", "research-harness", "julia"),
    )
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using JSON: JSON
using SHA: sha256

function readtsv(path)
    lines = readlines(path)
    head = split(lines[1], '\t')
    [Dict(zip(head, split(l, '\t'; keepempty = true))) for l in lines[2:end]]
end

"The first `n` characters, or the last `n` when `tail`."
cut(s, n; tail = false) =
    length(s) <= n ? s :
    tail ? "[… $(length(s) - n) characters cut]\n" * last(s, n) :
    first(s, n) * "\n[… $(length(s) - n) characters cut]"

function main(dir, seed, n)
    parts = readtsv(joinpath(dir, "parts.tsv"))
    runs = Dict(
        r["run_id"] => r for
        r in readtsv(joinpath(dir, "runs.tsv")) if r["source"] == "claude"
    )
    runpart =
        Dict(r["run_id"] => r["part"] for r in readtsv(joinpath(dir, "run-parts.tsv")))
    reports = Dict{String,Any}()
    for l in eachline(joinpath(dir, "reports.jsonl"))
        x = JSON.parse(l)
        reports[x["run_id"]] = x
    end
    prs = Dict{String,Vector{SubString{String}}}()
    for l in readlines(joinpath(dir, "prs.tsv"))
        v = split(l, '\t'; keepempty = true)
        append!(v, fill(SubString(""), 13 - length(v)))
        prs[v[1]] = v
    end

    eligible =
        filter(p -> p["tier"] in ("build", "reviewed") && p["bench"] == "false", parts)
    order = sort(eligible; by = p -> bytes2hex(sha256("$seed:$(p["key"])")))
    chosen = [(p, "sample") for p in first(order, n)]
    for p in parts
        p["arbitrators"] != "0" &&
            !any(c -> c[1]["key"] == p["key"], chosen) &&
            push!(chosen, (p, "arbitrator"))
    end

    out = joinpath(dir, "dossiers")
    mkpath(out)
    open(joinpath(dir, "sample.tsv"), "w") do io
        println(io, "n\tpart\ttier\treason\tseed")
        for (k, (p, why)) in enumerate(chosen)
            println(io, join((k, p["key"], p["tier"], why, seed), '\t'))
        end
    end
    for (k, (p, why)) in enumerate(chosen)
        rs = sort(
            [runs[id] for (id, q) in runpart if q == p["key"] && haskey(runs, id)];
            by = r -> r["t_start"],
        )
        open(joinpath(out, string(lpad(k, 2, '0'), ".md")), "w") do io
            println(io, "# ", p["key"], "\n")
            println(
                io,
                "Tier $(p["tier"]); in the sample as: $why (seed $seed). Runs $(p["runs"]), critics $(p["critics"]), ",
                "critic FAILs $(p["fails"]), first round in which every critic passed: ",
                isempty(p["to_pass"]) ? "none" : p["to_pass"],
                ", agent input \$$(round(parse(Float64, p["cost"]); digits=2)).\n",
            )
            println(io, "## Pull requests\n")
            for u in split(p["prs"])
                v = get(prs, u, nothing)
                v === nothing && (println(io, "- $u: not queried"); continue)
                println(
                    io,
                    "- $u: $(v[2]); $(v[5]) commits, $(v[6]) after opening",
                    isempty(v[12]) ? "" : " ($(v[12]))",
                    "; failing checks at the last commit: ",
                    isempty(v[13]) ? "none" : v[13],
                )
            end
            println(io, "\n## Runs, in time order\n")
            for r in rs
                x = get(reports, r["run_id"], nothing)
                println(
                    io,
                    "### $(r["t_start"][1:16]) · $(r["agent_type"]) · $(r["run_id"])\n",
                )
                println(
                    io,
                    "$(r["description"]). Verdict: $(isempty(r["verdict"]) ? "—" : r["verdict"]); round: ",
                    isempty(r["round"]) ? "—" : r["round"],
                    "; calls $(r["calls"]), tool errors $(r["tool_errors"]), ",
                    "$(r["wall_min"]) min, input \$$(r["cost_input_usd"]), effort $(r["effort"]), model $(r["model"]).",
                )
                println(
                    io,
                    "Loaded on a Read: ",
                    isempty(r["loaded"]) ? "none" : r["loaded"],
                    ". Skills: ",
                    isempty(r["skills"]) ? "none" : r["skills"],
                    ".\n",
                )
                x === nothing && continue
                t = r["agent_type"]
                judge = t in (
                    "julia-critic",
                    "julia-critic-high",
                    "part-critic",
                    "advisor",
                    "arbitrator",
                )
                println(
                    io,
                    "Prompt:\n\n```text\n",
                    cut(x["prompt"], judge ? 4000 : 1500),
                    "\n```\n",
                )
                println(
                    io,
                    "Report:\n\n```text\n",
                    judge ? cut(x["report"], 14000) :
                    cut(x["report"], 4000; tail = occursin("builder", t)),
                    "\n```\n",
                )
            end
        end
    end
    println(
        "$(length(chosen)) dossiers: $(count(c -> c[2] == "sample", chosen)) sampled with seed $seed, ",
        "$(count(c -> c[2] == "arbitrator", chosen)) added for an arbitrator run",
    )
end

main(ARGS[1], ARGS[2], parse(Int, ARGS[3]))
