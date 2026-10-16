# One table of agent runs, read from the raw transcripts of three harnesses.
#
#   julia --startup-file=no -t auto transcripts.jl <out-dir> --from <iso> --to <iso>
#
# Sources:
#
#   claude    ~/.claude/projects/**/*.jsonl; a sub-agent is subagents/agent-<id>.jsonl, and its
#             .meta.json gives the agent type and the parent
#   opencode  ~/.local/share/opencode/opencode.db, read with the sqlite3 command line, read-only
#   omp       ~/.omp/agent/sessions/**/*.jsonl; a sub-agent is <session>/<name>.jsonl
#
# Only records whose timestamp lies in [from, to) count. A file with no such record is left out.
#
# Writes to <out-dir>:
#
#   runs.tsv      one row per run: a main session or a sub-agent; `loaded` lists the rules and
#                 directory CLAUDE.md files that loaded on a Read (nested_memory records), and
#                 `rewrite_after` what the run waited on before each cache rewrite, with counts
#   tools.tsv     one row per run and tool: calls, result bytes, errors
#   results.tsv   the 500 largest tool results: run, tool, bytes, what was called, markers
#   reports.jsonl prompt and report of every run of a loop agent type (LOOP_TYPES)
#
# Usage is counted once per API message: Claude Code writes one message as several records, and
# the record with the largest output count is kept. Output is complete only where the message's
# record carries a stop_reason; out_complete is that share, and output means something only near 1.
# Input cost is exact; it is priced only for the models in PRICE, and every other model's tokens
# are counted, not priced.

let env = get(
        ENV,
        "RESEARCH_HARNESS_JULIA",
        joinpath(homedir(), ".local", "share", "research-harness", "julia"),
    )
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using JSON: JSON
using Dates: DateTime, Millisecond, unix2datetime

# $/MTok: input, cache write 5 min, cache write 1 h, cache read, output; the list prices.
const PRICE = Dict(
    "claude-opus-5-5" => (4.0, 5.0, 8.0, 0.20, 20.0),
    "claude-sonnet-5-5" => (2.0, 2.5, 4.0, 0.20, 10.0),
)
const LOOP_TYPES = Set([
    "julia-builder",
    "julia-critic",
    "julia-critic-high",
    "part-builder",
    "part-critic",
    "advisor",
    "arbitrator",
    "julia-pr-shepherd",
    "julia-branch-verifier",
    "julia-test-runner",
])
const TOP = 500
const REWRITE = 100_000  # a cache write above this, after the cache expired, is a rewrite

mutable struct Run
    source::String
    run_id::String
    root::String
    parent::String
    depth::Int
    agent_type::String
    description::String
    file::String
    models::Dict{String,Int}
    requested_model::String
    efforts::Dict{String,Int}
    calls::Int
    input::Int
    w5::Int
    w1::Int
    read::Int
    output::Int
    complete::Int
    cost_in::Float64
    cost_out::Float64
    startup::Int
    max_ctx::Int
    t0::String
    t1::String
    verdict::String
    task::String
    part::String
    round::String
    prs::Set{String}
    skills::Vector{String}
    loaded::Set{String}
    compactions::Int
    rewrites::Int
    rewrite_tok::Int
    rewrite_after::Dict{String,Int}
    prompt::String
    report::String
end
Run(source, id, file) = Run(
    source,
    id,
    id,
    "",
    0,
    "main",
    "",
    file,
    Dict(),
    "",
    Dict(),
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0.0,
    0.0,
    0,
    0,
    "",
    "",
    "",
    "",
    "",
    "",
    Set(),
    String[],
    Set(),
    0,
    0,
    0,
    Dict(),
    "",
    "",
)

struct Result
    run_id::String
    tool::String
    bytes::Int
    called::String
    error::Bool
    precompile::Bool
    testsummary::Bool
    head::String
end

g(o, k) = o isa AbstractDict ? get(o, k, nothing) : nothing
g(o, k, ks...) = g(g(o, k), ks...)
str(x) = x isa AbstractString ? String(x) : ""
num(x) = x isa Number ? Int(x) : 0
clean(s) = replace(s, r"[\t\n\r]" => " ")
bump!(d, k) = (d[k] = get(d, k, 0) + 1)
top(d) = isempty(d) ? "" : first(sort(collect(d); by = last, rev = true))[1]

function text_of(content)
    content isa AbstractString && return String(content)
    content isa AbstractVector || return ""
    join((str(g(c, "text")) for c in content if c isa AbstractDict), "")
end

"What a run waits on during a tool call: `gh` with its subcommand, another command's program, an agent type, or the tool."
function waited_on(name, input)
    if name == "Bash"
        words = split(str(g(input, "command")))
        isempty(words) && return "Bash"
        words[1] == "gh" && return join(words[1:min(3, end)], " ")
        return "Bash " * replace(basename(words[1]), r"[^\w.+-]" => "")
    end
    name == "Agent" && return "Agent " * str(g(input, "subagent_type"))
    name
end

"What a tool call names: the command, the path, the pattern or the agent type."
function called(name, input)
    for k in (
        "command",
        "file_path",
        "path",
        "pattern",
        "query",
        "subagent_type",
        "skill",
        "e",
        "url",
    )
        v = str(g(input, k))
        isempty(v) || return first(clean(v), 200)
    end
    ""
end

const RE_TASK = [
    r"Task file:\s*`?(?:[^\n`]*/)?Tasks/([^\n`]+?\.md)",
    r"task file\s+`(?:[^`]*/)?Tasks/([^`]+?\.md)`",
    r"Tasks/([^\n`*]+?\.md)",
]
const RE_PART = [
    r"(?m)^\s*Part:\s*`?([A-Za-z]*[0-9][A-Za-z0-9.\-]*|[A-Z][A-Za-z0-9.\-]*)",
    r"\b[Pp]art\s+`?([A-Z][A-Za-z0-9.\-]*)`?\s+of\b",
]
const RE_ROUND = r"(?m)^\s*Round:\s*([^\n]+)"
const RE_VERDICT = r"(?m)^\W*Verdict\W*:?\W*\s*([A-Za-z][A-Za-z \-—]*)"
const RE_PR = r"https://github\.com/[\w.\-]+/[\w.\-]+/pull/\d+"

function firstmatch(res, s)
    for re in res
        m = match(re, s)
        m === nothing || return String(m[1])
    end
    ""
end

"Task file, part and round named by a prompt."
function label!(r::Run)
    p = r.prompt
    r.task = firstmatch(RE_TASK, p)
    r.part = firstmatch(RE_PART, p)
    m = match(RE_ROUND, p)
    r.round = m === nothing ? "" : first(strip(m[1]), 60)
    m = match(RE_VERDICT, r.report)
    r.verdict = m === nothing ? "" : first(strip(m[1]), 40)
    for m in eachmatch(RE_PR, r.report)
        push!(r.prs, m.match)
    end
end

function account!(r::Run, model, u, has_stop)
    i, w = num(g(u, "input_tokens")), num(g(u, "cache_creation_input_tokens"))
    w1 = num(g(u, "cache_creation", "ephemeral_1h_input_tokens"))
    w5, rd, o = w - w1, num(g(u, "cache_read_input_tokens")), num(g(u, "output_tokens"))
    r.calls += 1
    r.input += i
    r.w5 += w5
    r.w1 += w1
    r.read += rd
    r.output += o
    r.complete += has_stop
    ctx = i + w + rd
    r.calls == 1 && (r.startup = ctx)
    r.max_ctx = max(r.max_ctx, ctx)
    p = get(PRICE, model, nothing)
    if p !== nothing
        r.cost_in += (p[1] * i + p[2] * w5 + p[3] * w1 + p[4] * rd) / 1e6
        r.cost_out += p[5] * o / 1e6
    end
end

inwindow(ts, from, to) = !isempty(ts) && from <= ts < to

function parse_claude(path, root, from, to)
    sub = occursin("/subagents/", path)
    id =
        sub ? replace(basename(path), r"^agent-|\.jsonl$" => "") :
        replace(basename(path), ".jsonl" => "")
    r = Run("claude", id, relpath(path, root))
    tools = Dict{String,Vector{Int}}()  # tool -> [calls, bytes, errors]
    results = Result[]
    uses = Dict{String,Tuple{String,String}}()
    msgs = Dict{String,Tuple{String,Any,Bool,Int,Int}}()  # message id -> (model, usage, stop, output, order)
    msg_ts = Dict{String,String}()  # message id -> timestamp of its first record
    waited = Dict{String,String}()  # message id -> what the run waited on before it
    last_wait = "start"
    handback = ""
    lasttext = ""
    any_in = false
    for line in eachline(path)
        rec = try
            JSON.parse(line)
        catch
            continue
        end
        rec isa AbstractDict || continue
        typ = str(g(rec, "type"))
        if typ == "pr-link"
            u = str(g(rec, "prUrl"))
            isempty(u) || push!(r.prs, u)
            continue
        end
        ts = str(g(rec, "timestamp"))
        inwindow(ts, from, to) || continue
        !sub && g(rec, "isSidechain") === true && continue
        any_in = true
        isempty(r.t0) && (r.t0 = ts)
        r.t1 = max(r.t1, ts)
        sid = str(g(rec, "sessionId"))
        isempty(sid) || (r.root = sid)
        ep = str(g(rec, "entrypoint"))
        !sub && r.agent_type == "main" && !isempty(ep) && (r.agent_type = "main:" * ep)
        typ == "system" &&
            str(g(rec, "subtype")) == "compact_boundary" &&
            (r.compactions += 1)
        # A rule or a directory CLAUDE.md that loads on a Read.
        if typ == "attachment" && str(g(rec, "attachment", "type")) == "nested_memory"
            push!(r.loaded, replace(str(g(rec, "attachment", "path")), homedir() => "~"))
        end
        msg = g(rec, "message")
        content = g(msg, "content")
        if typ == "user" && isempty(r.prompt) && g(rec, "toolUseResult") === nothing
            t = text_of(content)
            isempty(t) || startswith(t, "<") || (r.prompt = t)
        end
        if typ == "assistant"
            e = str(g(rec, "effort"))
            isempty(e) || bump!(r.efforts, e)
            model = str(g(msg, "model"))
            mid = str(g(msg, "id"))
            u = g(msg, "usage")
            if u !== nothing && !isempty(mid) && model != "<synthetic>"
                o = num(g(u, "output_tokens"))
                stop = g(msg, "stop_reason") !== nothing
                old = get(msgs, mid, nothing)
                get!(msg_ts, mid, ts)
                get!(waited, mid, last_wait)
                if old === nothing || o > old[4] || (stop && !old[3])
                    msgs[mid] = (
                        model,
                        u,
                        stop || (old !== nothing && old[3]),
                        o,
                        old === nothing ? length(msgs) : old[5],
                    )
                end
            end
            for b in (content isa AbstractVector ? content : [])
                bt = str(g(b, "type"))
                if bt == "tool_use"
                    name = str(g(b, "name"))
                    inp = g(b, "input")
                    uses[str(g(b, "id"))] = (name, called(name, inp))
                    get!(tools, name, [0, 0, 0])[1] += 1
                    last_wait = waited_on(name, inp)
                    name == "Skill" && push!(r.skills, str(g(inp, "skill")))
                    name == "SubagentHandback" && (handback = str(g(inp, "message")))
                elseif bt == "text"
                    t = str(g(b, "text"))
                    isempty(strip(t)) || (lasttext = t)
                end
            end
        elseif typ == "user" && content isa AbstractVector
            for b in content
                str(g(b, "type")) == "tool_result" || continue
                name, what = get(uses, str(g(b, "tool_use_id")), ("?", ""))
                t = text_of(g(b, "content"))
                err = g(b, "is_error") === true
                v = get!(tools, name, [0, 0, 0])
                v[2] += sizeof(t)
                v[3] += err
                push!(
                    results,
                    Result(
                        id,
                        name,
                        sizeof(t),
                        what,
                        err,
                        occursin("Precompiling", t),
                        occursin("Test Summary", t),
                        first(clean(t), 160),
                    ),
                )
            end
        elseif typ == "user" &&
               content isa AbstractString &&
               g(rec, "toolUseResult") === nothing
            last_wait = "message from caller"
        end
    end
    any_in || return nothing
    prev = ""
    for (mid, (model, u, stop, _, _)) in sort(collect(msgs); by = x -> x[2][5])
        bump!(r.models, model)
        account!(r, model, u, stop)
        # A pause past the cache's life writes the whole context again: 5 minutes for a sub-agent,
        # 1 hour for a main session.
        w = num(g(u, "cache_creation_input_tokens"))
        if !isempty(prev) && w > REWRITE && minutes(prev, msg_ts[mid]) > (sub ? 5 : 60)
            r.rewrites += 1
            r.rewrite_tok += w
            bump!(r.rewrite_after, get(waited, mid, "?"))
        end
        prev = msg_ts[mid]
    end
    if sub
        r.agent_type = "workflow"
        meta = replace(path, r"\.jsonl$" => ".meta.json")
        if isfile(meta)
            m = JSON.parse(read(meta, String))
            r.agent_type = something(str(g(m, "agentType")), "?")
            r.description = clean(str(g(m, "description")))
            r.requested_model = str(g(m, "model"))
            e = str(g(m, "effort"))
            isempty(e) || (r.efforts = Dict(e => 1))
            r.parent =
                isempty(str(g(m, "parentAgentId"))) ? r.root : str(g(m, "parentAgentId"))
            r.depth = num(g(m, "spawnDepth"))
        else
            r.parent = r.root
        end
        r.report = isempty(handback) ? lasttext : handback
    end
    label!(r)
    sort!(results; by = x -> -x.bytes)
    r, tools, results[1:min(end, TOP)]
end

function parse_omp(path, root, from, to)
    dir, name = dirname(path), replace(basename(path), ".jsonl" => "")
    sub = isfile(dir * ".jsonl")  # <session>/<name>.jsonl next to <session>.jsonl
    r = Run("omp", sub ? basename(dir) * "/" * name : name, relpath(path, root))
    sub &&
        (r.root = basename(dir); r.parent = basename(dir); r.agent_type = name; r.depth = 1)
    tools = Dict{String,Vector{Int}}()
    results = Result[]
    uses = Dict{String,Tuple{String,String}}()
    any_in = false
    lasttext = ""
    for line in eachline(path)
        rec = try
            JSON.parse(line)
        catch
            continue
        end
        ts = str(g(rec, "timestamp"))
        typ = str(g(rec, "type"))
        typ == "thinking_level_change" && bump!(r.efforts, str(g(rec, "thinkingLevel")))
        (typ == "message" && inwindow(ts, from, to)) || continue
        any_in = true
        isempty(r.t0) && (r.t0 = ts)
        r.t1 = max(r.t1, ts)
        msg = g(rec, "message")
        role = str(g(msg, "role"))
        content = g(msg, "content")
        if role == "user" && isempty(r.prompt)
            r.prompt = text_of(content)
        elseif role == "assistant"
            u = g(msg, "usage")
            model = str(g(msg, "model"))
            if u !== nothing
                bump!(r.models, model)
                i, rd, w, o = num(g(u, "input")),
                num(g(u, "cacheRead")),
                num(g(u, "cacheWrite")),
                num(g(u, "output"))
                r.calls += 1
                r.input += i
                r.read += rd
                r.w5 += w
                r.output += o
                r.complete += 1
                r.calls == 1 && (r.startup = i + rd + w)
                r.max_ctx = max(r.max_ctx, i + rd + w)
                c = g(u, "cost", "total")
                c isa Number && (r.cost_in += c)  # omp reports one cost; it is kept whole in cost_in
            end
            for b in (content isa AbstractVector ? content : [])
                if str(g(b, "type")) == "toolCall"
                    nm = str(g(b, "name"))
                    uses[str(g(b, "id"))] = (nm, called(nm, g(b, "arguments")))
                    get!(tools, nm, [0, 0, 0])[1] += 1
                elseif str(g(b, "type")) == "text" && !isempty(strip(str(g(b, "text"))))
                    lasttext = str(g(b, "text"))
                end
            end
        elseif role == "toolResult"
            nm, what = get(uses, str(g(msg, "toolCallId")), (str(g(msg, "toolName")), ""))
            t = text_of(content)
            err = g(msg, "isError") === true
            v = get!(tools, nm, [0, 0, 0])
            v[2] += sizeof(t)
            v[3] += err
            push!(
                results,
                Result(
                    r.run_id,
                    nm,
                    sizeof(t),
                    what,
                    err,
                    occursin("Precompiling", t),
                    occursin("Test Summary", t),
                    first(clean(t), 160),
                ),
            )
        end
    end
    any_in || return nothing
    r.report = lasttext
    label!(r)
    sort!(results; by = x -> -x.bytes)
    r, tools, results[1:min(end, TOP)]
end

sqlite(db, q) = JSON.parse(
    read(`sqlite3 -readonly -json $db $q`, String) |> s -> isempty(strip(s)) ? "[]" : s,
)

function parse_opencode(db, from, to)
    ms(t) = string(round(Int, (DateTime(t[1:19]) - DateTime(1970)).value))
    lo, hi = ms(from), ms(to)
    iso(x) = string(unix2datetime(x / 1000)) * "Z"
    out = Tuple{Run,Dict{String,Vector{Int}},Vector{Result}}[]
    sessions = sqlite(
        db,
        """select id, parent_id, agent, model, title, tokens_input, tokens_output, tokens_cache_read,
           tokens_cache_write, cost, time_created, time_updated from session
           where time_created >= $lo and time_created < $hi""",
    )
    calls = Dict(
        str(x["session_id"]) => num(x["n"]) for x in sqlite(
            db,
            """select session_id, count(*) n from message where json_extract(data,'\$.role')='assistant'
               and time_created >= $lo and time_created < $hi group by 1""",
        )
    )
    tools = Dict{String,Dict{String,Vector{Int}}}()
    for x in sqlite(
        db,
        """select session_id, json_extract(data,'\$.tool') tool, count(*) n,
           sum(length(coalesce(json_extract(data,'\$.state.output'),''))) bytes,
           sum(json_extract(data,'\$.state.status')='error') errors from part
           where json_extract(data,'\$.type')='tool' and time_created >= $lo and time_created < $hi
           group by 1, 2""",
    )
        get!(tools, str(x["session_id"]), Dict())[str(x["tool"])] =
            [num(x["n"]), num(x["bytes"]), num(x["errors"])]
    end
    for s in sessions
        id = str(s["id"])
        r = Run("opencode", id, "opencode.db")
        r.parent = str(s["parent_id"])
        r.root = isempty(r.parent) ? id : r.parent
        r.depth = isempty(r.parent) ? 0 : 1
        r.agent_type = isempty(r.parent) ? "main:" * str(s["agent"]) : str(s["agent"])
        r.description = clean(str(s["title"]))
        m = try
            JSON.parse(str(s["model"]))
        catch
            nothing
        end
        model = str(g(m, "providerID")) * "/" * str(g(m, "id"))
        r.models[model] = 1
        isempty(str(g(m, "variant"))) || (r.efforts[str(g(m, "variant"))] = 1)
        r.input, r.output = num(s["tokens_input"]), num(s["tokens_output"])
        r.read, r.w5 = num(s["tokens_cache_read"]), num(s["tokens_cache_write"])
        r.cost_in = s["cost"] isa Number ? s["cost"] : 0.0
        r.calls = get(calls, id, 0)
        r.complete = r.calls
        r.t0, r.t1 = iso(num(s["time_created"])), iso(num(s["time_updated"]))
        push!(out, (r, get(tools, id, Dict()), Result[]))
    end
    out
end

function minutes(a, b)
    (isempty(a) || isempty(b)) && return 0.0
    (DateTime(b[1:23]) - DateTime(a[1:23])).value / 60_000
end

const RUN_COLS = [
    "source",
    "run_id",
    "root",
    "parent",
    "depth",
    "agent_type",
    "description",
    "model",
    "requested_model",
    "effort",
    "calls",
    "input",
    "cache_write_5m",
    "cache_write_1h",
    "cache_read",
    "output",
    "out_complete",
    "cost_input_usd",
    "cost_output_usd",
    "startup_ctx",
    "max_ctx",
    "tool_calls",
    "tool_result_bytes",
    "tool_errors",
    "t_start",
    "t_end",
    "wall_min",
    "compactions",
    "rewrites",
    "rewrite_tokens",
    "verdict",
    "task",
    "part",
    "round",
    "prs",
    "skills",
    "loaded",
    "rewrite_after",
    "file",
]

function row(r::Run, tools)
    tc = sum((v[1] for v in values(tools)); init = 0)
    tb = sum((v[2] for v in values(tools)); init = 0)
    te = sum((v[3] for v in values(tools)); init = 0)
    vals = (
        r.source,
        r.run_id,
        r.root,
        r.parent,
        r.depth,
        r.agent_type,
        r.description,
        top(r.models),
        r.requested_model,
        top(r.efforts),
        r.calls,
        r.input,
        r.w5,
        r.w1,
        r.read,
        r.output,
        r.calls == 0 ? 0.0 : round(r.complete / r.calls; digits = 3),
        round(r.cost_in; digits = 4),
        round(r.cost_out; digits = 4),
        r.startup,
        r.max_ctx,
        tc,
        tb,
        te,
        r.t0,
        r.t1,
        round(minutes(r.t0, r.t1); digits = 1),
        r.compactions,
        r.rewrites,
        r.rewrite_tok,
        r.verdict,
        r.task,
        r.part,
        r.round,
        join(sort(collect(r.prs)), " "),
        join(r.skills, ";"),
        join(sort(collect(r.loaded)), ";"),
        join(("$k:$n" for (k, n) in sort(collect(r.rewrite_after); by = x -> -x[2])), ";"),
        r.file,
    )
    join((clean(string(v)) for v in vals), '\t')
end

function main(args)
    length(args) == 5 && args[2] == "--from" && args[4] == "--to" ||
        error("usage: transcripts.jl <out-dir> --from <iso> --to <iso>")
    out, from, to = args[1], args[3], args[5]
    mkpath(out)
    home = homedir()
    claude_root = joinpath(home, ".claude", "projects")
    omp_root = joinpath(home, ".omp", "agent", "sessions")
    files = String[]
    for (root, _, fs) in walkdir(claude_root), f in fs
        endswith(f, ".jsonl") && push!(files, joinpath(root, f))
    end
    omp = String[]
    for (root, _, fs) in walkdir(omp_root), f in fs
        endswith(f, ".jsonl") && push!(omp, joinpath(root, f))
    end
    # A file last written before the window holds no record in it.
    cut = DateTime(from[1:19])
    keep(f) = unix2datetime(mtime(f)) >= cut
    filter!(keep, files)
    filter!(keep, omp)
    jobs = vcat([(:claude, f) for f in files], [(:omp, f) for f in omp])
    parsed = Vector{Any}(nothing, length(jobs))
    Threads.@threads for k in eachindex(jobs)
        kind, f = jobs[k]
        parsed[k] =
            kind == :claude ? parse_claude(f, claude_root, from, to) :
            parse_omp(f, omp_root, from, to)
    end
    all = Any[p for p in parsed if p !== nothing]
    append!(
        all,
        parse_opencode(
            joinpath(home, ".local", "share", "opencode", "opencode.db"),
            from,
            to,
        ),
    )
    open(joinpath(out, "runs.tsv"), "w") do io
        println(io, join(RUN_COLS, '\t'))
        for (r, t, _) in all
            println(io, row(r, t))
        end
    end
    open(joinpath(out, "tools.tsv"), "w") do io
        println(io, "source\trun_id\ttool\tcalls\tresult_bytes\terrors")
        for (r, t, _) in all, (name, v) in sort(collect(t))
            println(io, join((r.source, r.run_id, clean(name), v...), '\t'))
        end
    end
    results = sort!(reduce(vcat, (x[3] for x in all); init = Result[]); by = x -> -x.bytes)
    open(joinpath(out, "results.tsv"), "w") do io
        println(io, "run_id\ttool\tbytes\tis_error\tprecompile\ttest_summary\tcalled\thead")
        for x in results[1:min(end, TOP)]
            println(
                io,
                join(
                    (
                        x.run_id,
                        x.tool,
                        x.bytes,
                        x.error,
                        x.precompile,
                        x.testsummary,
                        x.called,
                        x.head,
                    ),
                    '\t',
                ),
            )
        end
    end
    open(joinpath(out, "reports.jsonl"), "w") do io
        for (r, _, _) in all
            r.agent_type in LOOP_TYPES || continue
            JSON.json(
                io,
                Dict(
                    "run_id" => r.run_id,
                    "root" => r.root,
                    "parent" => r.parent,
                    "agent_type" => r.agent_type,
                    "task" => r.task,
                    "part" => r.part,
                    "round" => r.round,
                    "verdict" => r.verdict,
                    "t_start" => r.t0,
                    "description" => r.description,
                    "prompt" => r.prompt,
                    "report" => r.report,
                ),
            )
            println(io)
        end
    end
    n = length(all)
    println(
        "runs: $n (claude $(count(x -> x[1].source == "claude", all)), omp $(count(x -> x[1].source == "omp", all)), ",
        "opencode $(count(x -> x[1].source == "opencode", all))); window [$from, $to)",
    )
end

main(ARGS)
