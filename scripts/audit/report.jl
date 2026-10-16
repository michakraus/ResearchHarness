# The baseline reports, from the tables of transcripts.jl.
#
#   julia --startup-file=no report.jl <data-dir>
#
# Reads <data-dir>/runs.tsv, results.tsv and, where it exists, prs.tsv. Writes parts.tsv,
# run-parts.tsv, loop-prs.txt, prs.graphql, prs.jq and calls.tsv to <data-dir>, and the reports to
# report.md:
#
#   parts     each part of a task file: tier, runs, tokens and input cost of its agents, critic
#             rounds to the first PASS, its pull requests; and the totals per tier
#   rounds    the distribution of critic rounds to PASS, per tier
#   calls     every advisor and arbitrator run: part, question (the prompt's first lines), answer
#             (the report's first lines); calls.tsv holds them for the reversal check
#   results   the 20 largest tool results and their kind
#   startup   the first-call context per agent type: median, quartiles, runs
#   escaped   per loop pull request, from prs.tsv: state, CI failures, commits after opening, review
#             threads
#   rewrites  per agent type, the calls that wrote the whole context again after a pause
#
# A run belongs to a part when its prompt names a task file and a part, or when an ancestor's does.
# A main session is the dispatcher and belongs to no part; its cost is reported apart. A part's tier
# is `reviewed` when a part-builder or part-critic ran for it, `build` when a julia-builder or a
# julia-critic did. A part is a benchmark when a run of it lies in a loop-bench worktree or its
# agent type starts with `bench-`.
#
# prs.tsv comes from the GraphQL query that this script writes to prs.graphql, with the filter it
# writes to prs.jq. `gh` reads a token that the sandbox denies to a script, so run it as a command
# of its own from <data-dir>, with the filter pasted in, and save what it prints as prs.tsv:
#   gh api graphql -F query=@prs.graphql --jq '<the content of prs.jq>'

using Statistics: median, quantile
using Printf: @sprintf

const PRS_JQ = """.data | to_entries[] | .value.pullRequest as \$p | [\$p.url, \$p.state, (\$p.mergedAt // ""), \$p.createdAt,
  \$p.commits.totalCount, ([\$p.commits.nodes[] | select(.commit.committedDate > \$p.createdAt)] | length),
  ([\$p.commits.nodes[] | select(.commit.statusCheckRollup.state == "FAILURE")] | length),
  (\$p.commits.nodes[-1].commit.statusCheckRollup.state // ""), \$p.reviews.totalCount, \$p.reviewThreads.totalCount,
  \$p.comments.totalCount, ([\$p.commits.nodes[] | select(.commit.committedDate > \$p.createdAt) |
  .commit.messageHeadline] | join(" | ")), ([\$p.last.nodes[0].commit.checkSuites.nodes[].checkRuns.nodes[].name] |
  unique | join(", "))] | @tsv"""

function readtsv(path)
    lines = readlines(path)
    head = split(lines[1], '\t')
    [Dict(zip(head, split(l, '\t'; keepempty = true))) for l in lines[2:end]]
end
i(x) = isempty(x) ? 0 : parse(Int, x)
f(x) = isempty(x) ? 0.0 : parse(Float64, x)
tokens_in(r) =
    i(r["input"]) + i(r["cache_write_5m"]) + i(r["cache_write_1h"]) + i(r["cache_read"])
ismain(r) = startswith(r["agent_type"], "main")
const CRITICS = r"critic"
verdict(r) = (
    m = match(r"^(PASS|FAIL|BLOCKED|ready|PR open|done|blocked)"i, r["verdict"]);
    m === nothing ? "" : uppercase(m[1])
)

"The critic round of a critic run: 1 for 1a/1b and round 1, n for verify n."
function critic_round(r)
    s = lowercase(r["round"] * " " * r["description"])
    m = match(r"verify\D{0,12}(\d+)", s)
    m === nothing || return parse(Int, m[1])
    m = match(r"round\s*(\d+)", s)
    m === nothing || return parse(Int, m[1])
    occursin(r"\b1[ab]\b|round 1|critic 1", s) && return 1
    0
end

mtok(x) = @sprintf("%.1f", x / 1e6)
usd(x) = @sprintf("%.2f", x)

function main(dir)
    runs = filter(r -> r["source"] == "claude", readtsv(joinpath(dir, "runs.tsv")))
    byid = Dict(r["run_id"] => r for r in runs)
    key(r) =
        isempty(r["task"]) || isempty(r["part"]) ? "" :
        replace(r["task"], r"\.md$" => "") * " · " * r["part"]
    function partof(r)
        seen = Set{String}()
        while !ismain(r) && !(r["run_id"] in seen)
            push!(seen, r["run_id"])
            k = key(r)
            isempty(k) || return k
            p = get(byid, r["parent"], nothing)
            p === nothing && return ""
            r = p
        end
        ""
    end
    parts = Dict{String,Vector{Dict}}()
    open(joinpath(dir, "run-parts.tsv"), "w") do io
        println(io, "run_id\tpart")
        for r in runs
            ismain(r) && continue
            k = partof(r)
            isempty(k) && continue
            push!(get!(parts, k, Dict[]), r)
            println(io, r["run_id"], '\t', k)
        end
    end

    # parts
    rows = []
    for (k, rs) in parts
        types = Set(r["agent_type"] for r in rs)
        tier =
            any(t -> t in ("part-builder", "part-critic"), types) ? "reviewed" :
            any(t -> t == "julia-builder" || occursin(CRITICS, t), types) ? "build" :
            "other"
        bench = any(
            r ->
                occursin("loop-bench", r["file"]) || startswith(r["agent_type"], "bench-"),
            rs,
        )
        critics = sort(
            filter(r -> occursin(CRITICS, r["agent_type"]), rs);
            by = r -> r["t_start"],
        )
        rounds = [r["agent_type"] == "part-critic" ? 0 : critic_round(r) for r in critics]
        # A part-critic run is its own round; the build tier numbers its rounds in the prompt.
        if tier == "reviewed"
            rounds = collect(1:length(critics))
        end
        # A round passes when every critic of it passes.
        byround = Dict{Int,Vector{String}}()
        for (c, n) in zip(critics, rounds)
            push!(get!(byround, n, String[]), verdict(c))
        end
        passed = sort([n for (n, v) in byround if n > 0 && all(==("PASS"), v)])
        to_pass = isempty(passed) ? "" : string(first(passed))
        fails = count(r -> verdict(r) == "FAIL", critics)
        prs = sort(unique(vcat((split(r["prs"]) for r in rs if !isempty(r["prs"]))...)))
        complete = all(r -> f(r["out_complete"]) >= 0.9 || i(r["calls"]) == 0, rs)
        push!(
            rows,
            (;
                key = k,
                tier,
                bench,
                runs = length(rs),
                builders = count(r -> occursin("builder", r["agent_type"]), rs),
                critics = length(critics),
                fails,
                to_pass,
                max_round = maximum(rounds; init = 0),
                unnumbered = count(==(0), rounds),
                advisors = count(r -> r["agent_type"] == "advisor", rs),
                arbitrators = count(r -> r["agent_type"] == "arbitrator", rs),
                tok = sum(tokens_in, rs),
                out = complete ? sum(r -> i(r["output"]), rs) : -1,
                cost = sum(r -> f(r["cost_input_usd"]), rs),
                t0 = minimum(r -> r["t_start"], rs),
                dispatchers = join(sort(unique(r["root"][1:8] for r in rs)), " "),
                prs = join(prs, " "),
            ),
        )
    end
    sort!(rows; by = x -> (x.tier, x.t0))
    open(joinpath(dir, "parts.tsv"), "w") do io
        println(io, join(fieldnames(typeof(rows[1])), '\t'))
        for x in rows
            println(io, join(values(x), '\t'))
        end
    end
    loop_prs =
        sort(unique(vcat((split(x.prs) for x in rows if x.tier != "other" && !x.bench)...)))
    write(joinpath(dir, "loop-prs.txt"), join(loop_prs, '\n') * '\n')
    write(joinpath(dir, "prs.jq"), PRS_JQ)
    open(joinpath(dir, "prs.graphql"), "w") do io
        println(io, "{")
        for (n, u) in enumerate(loop_prs)
            m = match(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", u)
            println(
                io,
                "  p$n: repository(owner: \"$(m[1])\", name: \"$(m[2])\") { pullRequest(number: $(m[3])) { url state mergedAt createdAt",
                " commits(first: 100) { totalCount nodes { commit { committedDate messageHeadline statusCheckRollup { state } } } }",
                " reviews { totalCount } reviewThreads { totalCount } comments { totalCount }",
                " last: commits(last: 1) { nodes { commit { checkSuites(first: 30) { nodes { checkRuns(first: 50,",
                " filterBy: {conclusions: [FAILURE]}) { nodes { name } } } } } } } } }",
            )
        end
        println(io, "}")
    end
    # GitHub answers with the current URL, so a renamed repository (`X` to `X.jl`) is matched
    # without the suffix.
    prkey(u) = lowercase(replace(u, r"\.jl/pull/" => "/pull/"))
    merged = Set{String}()
    prinfo = Dict{String,Vector{SubString{String}}}()
    if isfile(joinpath(dir, "prs.tsv"))
        for l in readlines(joinpath(dir, "prs.tsv"))
            v = split(l, '\t'; keepempty = true)
            append!(v, fill(SubString(""), 13 - length(v)))  # an empty last field may lose its tab
            prinfo[prkey(v[1])] = v
            v[2] == "MERGED" && push!(merged, prkey(v[1]))
        end
    end

    println("## 1. Tokens per part, per tier and per merged PR\n")
    println(
        "Agents only; the dispatcher sessions are listed apart. Input cost at list price for Opus and Sonnet; ",
        "Haiku tokens are counted, not priced. Output in Mtok where every run of the part has complete output.\n",
    )
    println(
        "| tier | parts | benchmark | with a merged PR | runs | input Mtok | input \$ | median input \$ per part | input \$ per merged PR |",
    )
    println("|:--|--:|--:|--:|--:|--:|--:|--:|--:|")
    for t in ("build", "reviewed", "other")
        xs = filter(x -> x.tier == t && !x.bench, rows)
        isempty(xs) && continue
        b = count(x -> x.tier == t && x.bench, rows)
        m = filter(x -> any(u -> prkey(u) in merged, split(x.prs)), xs)
        nm = length(
            unique(vcat((filter(u -> prkey(u) in merged, split(x.prs)) for x in m)...)),
        )
        println(
            "| $t | $(length(xs)) | $b | $(length(m)) | $(sum(x -> x.runs, xs)) | $(mtok(sum(x -> x.tok, xs))) | ",
            "$(usd(sum(x -> x.cost, xs))) | $(usd(median([x.cost for x in xs]))) | ",
            nm == 0 ? "—" : usd(sum(x -> x.cost, m) / nm),
            " |",
        )
    end
    # A headless sdk-cli session is a skill-trigger test, never a dispatcher.
    dispatch = filter(
        r ->
            r["agent_type"] in ("main:claude-desktop", "main:cli") &&
            any(s -> s in ("build-part", "build-reviewed"), split(r["skills"], ';')),
        runs,
    )
    println(
        "\nDispatcher sessions (a desktop or CLI session that invoked build-part or build-reviewed): $(length(dispatch)), ",
        "input \$$(usd(sum(r -> f(r["cost_input_usd"]), dispatch; init=0.0))), ",
        "$(mtok(sum(tokens_in, dispatch; init=0))) Mtok. Models: ",
        join(
            (
                "$m $(count(r -> r["model"] == m, dispatch))" for
                m in unique(r["model"] for r in dispatch)
            ),
            ", ",
        ),
        ".\n",
    )
    println("All parts, newest last, in parts.tsv. The ten most expensive:\n")
    println("| part | tier | runs | critics | FAILs | rounds to PASS | input \$ | PRs |")
    println("|:--|:--|--:|--:|--:|--:|--:|:--|")
    for x in first(sort(filter(x -> !x.bench, rows); by = x -> -x.cost), 10)
        println(
            "| $(x.key) | $(x.tier) | $(x.runs) | $(x.critics) | $(x.fails) | $(isempty(x.to_pass) ? "no PASS" : x.to_pass) | ",
            "$(usd(x.cost)) | $(join((replace(p, r"https://github.com/[^/]+/" => "") for p in split(x.prs)), " ")) |",
        )
    end

    println("\n## 2. Critic rounds to PASS\n")
    println(
        "| tier | parts with a critic | PASS in round 1 | 2 | 3 | 4+ | no PASS | median critic runs |",
    )
    println("|:--|--:|--:|--:|--:|--:|--:|--:|")
    for t in ("build", "reviewed")
        xs = filter(x -> x.tier == t && !x.bench && x.critics > 0, rows)
        c(n) = count(x -> x.to_pass == string(n), xs)
        println(
            "| $t | $(length(xs)) | $(c(1)) | $(c(2)) | $(c(3)) | $(count(x -> !isempty(x.to_pass) && parse(Int, x.to_pass) >= 4, xs)) | ",
            "$(count(x -> isempty(x.to_pass), xs)) | $(median([x.critics for x in xs])) |",
        )
    end

    println("\n## 3. Advisor and arbitrator calls\n")
    calls = sort(
        filter(r -> r["agent_type"] in ("advisor", "arbitrator"), runs);
        by = r -> r["t_start"],
    )
    open(joinpath(dir, "calls.tsv"), "w") do io
        println(io, "run_id\tagent_type\tt_start\tpart\tdescription\tinput_usd")
        for r in calls
            println(
                io,
                join(
                    (
                        r["run_id"],
                        r["agent_type"],
                        r["t_start"],
                        partof(r),
                        r["description"],
                        r["cost_input_usd"],
                    ),
                    '\t',
                ),
            )
        end
    end
    println(
        "$(count(r -> r["agent_type"] == "advisor", calls)) advisor runs, ",
        "$(count(r -> r["agent_type"] == "arbitrator", calls)) arbitrator runs; input \$",
        usd(sum(r -> f(r["cost_input_usd"]), calls; init = 0.0)),
        ". One row each in calls.tsv.\n",
    )

    println("## 4. The 20 largest tool results\n")
    results = readtsv(joinpath(dir, "results.tsv"))
    function kind(x)
        c, t = lowercase(x["called"]), x["tool"]
        t == "Read" || occursin(r"^(cat|sed|head|tail|less) ", c) ? "file read" :
        x["test_summary"] == "true" || occursin(r"run-tests|pkg\.test|runtests", c) ?
        "test output" :
        x["precompile"] == "true" ? "precompilation" :
        t in ("Grep", "Glob") ||
        occursin(r"grep|search|find |rg ", lowercase(t * " " * c)) ? "search" :
        occursin(r"^gh |^git ", c) ? "git/gh" : occursin(r"julia", c) ? "julia" : "other"
    end
    println("| # | bytes | tool | kind | agent type | called |")
    println("|--:|--:|:--|:--|:--|:--|")
    for (n, x) in enumerate(first(results, 20))
        a = get(byid, x["run_id"], nothing)
        println(
            "| $n | $(x["bytes"]) | $(x["tool"]) | $(kind(x)) | $(a === nothing ? "?" : a["agent_type"]) | `",
            replace(first(x["called"], 70), "|" => "\\|", "`" => "'"),
            "` |",
        )
    end
    kinds = Dict{String,Vector{Int}}()
    for x in results
        v = get!(kinds, kind(x), [0, 0])
        v[1] += 1
        v[2] += i(x["bytes"])
    end
    println(
        "\nKinds over the $(length(results)) largest results: ",
        join(
            (
                "$k $(v[1]) ($(round(v[2] / 1e6; digits=1)) MB)" for
                (k, v) in sort(collect(kinds); by = x -> -x[2][2])
            ),
            ", ",
        ),
        ".\n",
    )

    println("## 5. Startup tokens per agent type\n")
    println(
        "First-call context (input + cache write + cache read), which includes the delegation prompt.\n",
    )
    println("| agent type | runs | median | p25 | p75 |")
    println("|:--|--:|--:|--:|--:|")
    types = Dict{String,Vector{Int}}()
    for r in runs
        i(r["startup_ctx"]) > 0 &&
            push!(get!(types, r["agent_type"], Int[]), i(r["startup_ctx"]))
    end
    for (t, v) in sort(collect(types); by = x -> -length(x[2]))
        length(v) >= 3 || continue
        q = quantile(v, [0.25, 0.5, 0.75])
        println(
            "| $t | $(length(v)) | $(round(Int, q[2])) | $(round(Int, q[1])) | $(round(Int, q[3])) |",
        )
    end

    println("\n## 7. Cache rewrites after a pause\n")
    println(
        "A call that writes more than 100k tokens to the cache after the cache expired: a gap of over 5 ",
        "minutes in a sub-agent, over 60 minutes in a main session. Priced at the model's 5-minute write for a ",
        "sub-agent and its 1-hour write for a main session.\n",
    )
    println("| agent type | runs | rewrites | Mtok | \$ | share of the type's input \$ |")
    println("|:--|--:|--:|--:|--:|--:|")
    wprice = Dict("claude-opus-5-5" => (5.0, 8.0), "claude-sonnet-5-5" => (2.5, 4.0))
    rw = Dict{String,Vector{Float64}}()
    for r in runs
        v = get!(rw, r["agent_type"], zeros(5))
        p = get(wprice, r["model"], (0.0, 0.0))
        v[1] += 1
        v[2] += i(r["rewrites"])
        v[3] += i(r["rewrite_tokens"])
        v[4] += i(r["rewrite_tokens"]) * (ismain(r) ? p[2] : p[1]) / 1e6
        v[5] += f(r["cost_input_usd"])
    end
    for (t, v) in sort(collect(rw); by = x -> -x[2][4])
        v[2] > 0 || continue
        println(
            "| $t | $(Int(v[1])) | $(Int(v[2])) | $(mtok(v[3])) | $(usd(v[4])) | ",
            v[5] > 0 ? "$(round(Int, 100 * v[4] / v[5])) %" : "—",
            " |",
        )
    end

    isempty(prinfo) && return
    println("\n## 6. Escaped defects on loop PRs\n")
    # The checks that fail on almost every pull request of a repository: Downgrade and codecov.
    routine = r"^(Downgrade - ubuntu-latest|codecov/project)$"
    other_red(v) =
        filter(c -> !occursin(routine, c), strip.(split(v[13], ","; keepempty = false)))
    vs = [prinfo[prkey(u)] for u in loop_prs if haskey(prinfo, prkey(u))]
    after = filter(
        v ->
            v[6] != "0" && !all(h -> startswith(strip(h), "Merge "), split(v[12], " | ")),
        vs,
    )
    println(
        "$(length(vs)) loop PRs, $(count(v -> v[2] == "MERGED", vs)) merged. With a commit after opening that is ",
        "not a merge of main: $(length(after)). With a failing check at the last commit other than ",
        "Downgrade or codecov: $(count(v -> !isempty(other_red(v)), vs)).\n",
    )
    println(
        "| PR | commits | after opening | last CI | other failing checks at the last commit | reviews | threads |",
    )
    println("|:--|--:|--:|:--|:--|--:|--:|")
    for v in vs
        o = other_red(v)
        println(
            "| $(replace(v[1], r"https://github.com/[^/]+/" => "")) | $(v[5]) | $(v[6]) | $(v[8]) | ",
            length(o) > 3 ? "$(length(o)) jobs" : join(o, ", "),
            " | $(v[9]) | $(v[10]) |",
        )
    end
end

open(joinpath(ARGS[1], "report.md"), "w") do io
    redirect_stdout(() -> main(ARGS[1]), io)
end
