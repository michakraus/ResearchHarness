# One table of the instruction files: tokens, when each loads, how many runs loaded it in the
# window, and which failure classes cite it.
#
#   julia --startup-file=no -t auto instructions.jl <data-dir> <lines-dir> --from <iso> --to <iso> \
#       --harness <checkout> [--tree <dir>] [--claude-md <root>]... [--notes <dir>] \
#       [--exclude <dir>]... [--projects <dir>]
#
# <data-dir> holds the runs.tsv of transcripts.jl, and <lines-dir> the failure lines that
# taxonomy.jl reads. The instruction files are:
#
#   --harness    adapters/claude/*.md, instructions/, rules/, skills/, agents/, commands/,
#                adapters/opencode/agents/ and the OpenCode and oh-my-pi delta files
#   --tree       the tree instructions: instructions/ and rules/, installed beside the harness's
#   --claude-md  every CLAUDE.md and AGENTS.md at most three levels below the root, outside
#                directories whose name starts with a dot
#   --notes      every *.md below the directory but CHANGELOG.md, except below an --exclude
#                directory
#   memory       every <projects>/*/memory/*.md; <projects> is ~/.claude/projects by default
#
# A run loaded a file when one of these records names it, inside [from, to):
#
#   an agent definition   runs.tsv agent_type is its name, or its name and a suffix such as `-high`
#   a skill               runs.tsv skills names it
#   a rule                runs.tsv loaded names its installed copy
#   a CLAUDE.md           runs.tsv loaded names it, or a Claude Code `instructions` record does
#   the global files      a Claude Code `instructions` record names the installed copy
#   a command             a Claude Code user message holds `<command-name>/<name>`
#   any other file        a Claude Code Read of its path; for a skill's other files, the installed path
#   a delta file          the runs.tsv rows of OpenCode or oh-my-pi; an upper bound
#
# The `instructions` records and the Reads come from the Claude Code transcripts in <projects>, so
# a count of those kinds covers Claude Code only. Tokens are characters / 3.5. A failure line cites
# a file when its seventh field names it as agents/, skills/, rules/, instructions/ or commands/
# path outside parentheses; the class is its sixth field. Prints the table as Markdown, then the
# files that no run loaded and the files that no failure line cites; writes instructions.tsv into
# <data-dir>.

let env = get(
        ENV,
        "RESEARCH_HARNESS_JULIA",
        joinpath(homedir(), ".local", "share", "research-harness", "julia"),
    )
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using JSON: JSON

const HOME = homedir()
const INSTALLED = joinpath(HOME, ".claude")

tilde(p) = startswith(p, HOME) ? "~" * p[length(HOME)+1:end] : p

mutable struct File
    path::String
    kind::String
    loads::String
    cite::String                          # the path a failure line uses, or ""
    keys::Vector{Pair{Symbol,String}}     # the records that count as a load
    runs::Set{String}
    classes::Dict{String,Int}
end

File(path, kind, loads, cite, keys) =
    File(path, kind, loads, cite, keys, Set{String}(), Dict{String,Int}())

function option(args, name)
    v = String[]
    i = findfirst(==(name), args)
    while i !== nothing
        push!(v, args[i+1])
        i = findnext(==(name), args, i + 2)
    end
    v
end

mdfiles(dir) = isdir(dir) ? sort([joinpath(dir, f) for f in readdir(dir) if endswith(f, ".md")]) : String[]

function paths_of(file)
    m = match(r"^paths:\s*(.*)$"m, read(file, String))
    m === nothing ? "always" : "on a Read of " * replace(m[1], r"[\[\]\"]" => "")
end

function description_note(file)
    occursin(r"^omitClaudeMd:\s*true"m, read(file, String)) ? "; no CLAUDE.md" : ""
end

function harness_files(h)
    v = File[]
    for f in mdfiles(joinpath(h, "adapters", "claude"))
        r = relpath(f, joinpath(h, "adapters", "claude"))
        push!(v, File(f, "global", "always, as ~/.claude/$r, but in an agent without CLAUDE.md", "",
                      [:start => joinpath(INSTALLED, r)]))
    end
    for f in mdfiles(joinpath(h, "instructions"))
        r = relpath(f, h)
        push!(v, File(f, "global", "always, as ~/.claude/$r, but in an agent without CLAUDE.md", r,
                      [:start => joinpath(INSTALLED, r)]))
    end
    for f in mdfiles(joinpath(h, "rules"))
        r = relpath(f, h)
        push!(v, File(f, "rule", paths_of(f), r, [:nested => "~/.claude/" * r]))
    end
    for d in sort(readdir(joinpath(h, "skills")))
        dir = joinpath(h, "skills", d)
        isdir(dir) || continue
        for f in mdfiles(dir)
            r = relpath(f, h)
            if basename(f) == "SKILL.md"
                push!(v, File(f, "skill", "on a Skill call of `$d`; its description always", r,
                              [:skill => d]))
            else
                push!(v, File(f, "skill file", "on a Read, when `$d` sends one", r,
                              [:read => joinpath(INSTALLED, "skills", d, basename(f))]))
            end
        end
    end
    for f in [mdfiles(joinpath(h, "agents")); mdfiles(joinpath(h, "adapters", "opencode", "agents"))]
        n = replace(basename(f), ".md" => "")
        push!(v, File(f, "agent", "per run of `$n`; its description always" * description_note(f),
                      relpath(f, h), [:agent => n]))
    end
    for f in mdfiles(joinpath(h, "commands"))
        n = replace(basename(f), ".md" => "")
        push!(v, File(f, "command", "on /$n", relpath(f, h), [:command => n]))
    end
    for (src, file, loads) in (
        ("opencode", "OPENCODE-DELTA.md", "always under OpenCode, as its AGENTS.md"),
        ("omp", "OMP-DELTA.md", "always under oh-my-pi, as its AGENTS.md"),
        ("omp", "UNDER-OMP.md", "rendered into every oh-my-pi agent"),
    )
        f = joinpath(h, "adapters", src, file)
        isfile(f) && push!(v, File(f, "delta", loads, "", [:source => src]))
    end
    v
end

function tree_files(t)
    v = File[]
    for f in mdfiles(joinpath(t, "instructions"))
        r = relpath(f, t)
        push!(v, File(f, "global", "always, as ~/.claude/$r, but in an agent without CLAUDE.md", r,
                      [:start => joinpath(INSTALLED, r)]))
    end
    for f in mdfiles(joinpath(t, "rules"))
        r = relpath(f, t)
        push!(v, File(f, "rule", paths_of(f), r, [:nested => "~/.claude/" * r]))
    end
    v
end

function claude_md(root, depth = 3)
    v = String[]
    function walk(dir, d)
        for e in readdir(dir)
            p = joinpath(dir, e)
            if isdir(p) && !islink(p)
                d < depth && !startswith(e, ".") && e != "node_modules" && walk(p, d + 1)
            elseif e in ("CLAUDE.md", "AGENTS.md")
                push!(v, p)
            end
        end
    end
    walk(root, 1)
    [File(f, "CLAUDE.md", "at the start below $(tilde(dirname(f)))/, or on a Read below it", "",
          [:start => f, :nested => tilde(f)]) for f in sort(v)]
end

function notes(dir, exclude)
    v = File[]
    for (d, _, fs) in walkdir(dir)
        any(x -> d == x || startswith(d, x * "/"), exclude) && continue
        for f in sort(fs)
            endswith(f, ".md") && f != "CHANGELOG.md" || continue
            p = joinpath(d, f)
            push!(v, File(p, "note", "on a Read", "", [:read => p]))
        end
    end
    sort!(v; by = f -> f.path)
end

function memory(projects)
    v = File[]
    for p in sort(readdir(projects))
        dir = joinpath(projects, p, "memory")
        for f in mdfiles(dir)
            if basename(f) == "MEMORY.md"
                push!(v, File(f, "memory", "always, in a run below its project; first 200 lines", "",
                              [:start => f]))
            else
                push!(v, File(f, "memory", "on a Read", "", [:read => f]))
            end
        end
    end
    v
end

# --- Claude Code transcripts: `instructions` records, Reads and slash commands per run ---

g(x, k) = x isa AbstractDict ? get(x, k, nothing) : nothing
str(x) = x isa AbstractString ? String(x) : ""
inwindow(ts, from, to) = !isempty(ts) && from <= ts < to

function scan(path, from, to)
    sub = occursin("/subagents/", path)
    id = "claude:" * replace(basename(path), r"^agent-|\.jsonl$" => "")
    seen = Pair{Symbol,String}[]
    for line in eachline(path)
        (occursin("\"instructions\"", line) || occursin("\"Read\"", line) ||
         occursin("<command-name>/", line)) || continue
        rec = try
            JSON.parse(line)
        catch
            continue
        end
        rec isa AbstractDict || continue
        inwindow(str(g(rec, "timestamp")), from, to) || continue
        !sub && g(rec, "isSidechain") === true && continue
        typ = str(g(rec, "type"))
        a = g(rec, "attachment")
        if typ == "attachment" && str(g(a, "type")) == "instructions"
            for f in something(g(a, "files"), [])
                push!(seen, :start => str(g(f, "path")))
            end
        end
        content = g(g(rec, "message"), "content")
        if typ == "assistant" && content isa AbstractVector
            for b in content
                str(g(b, "type")) == "tool_use" && str(g(b, "name")) == "Read" || continue
                push!(seen, :read => str(g(g(b, "input"), "file_path")))
            end
        elseif typ == "user"
            t = content isa AbstractString ? content :
                join((str(g(b, "text")) for b in (content isa AbstractVector ? content : [])), "\n")
            for m in eachmatch(r"<command-name>/([\w:-]+)</command-name>", t)
                push!(seen, :command => String(m[1]))
            end
        end
    end
    id => unique(seen)
end

function transcripts(projects, from, to)
    files = String[]
    for (d, _, fs) in walkdir(projects)
        for f in fs
            endswith(f, ".jsonl") && push!(files, joinpath(d, f))
        end
    end
    out = Vector{Pair{String,Vector{Pair{Symbol,String}}}}(undef, length(files))
    Threads.@threads for i in eachindex(files)
        out[i] = scan(files[i], from, to)
    end
    out
end

# --- runs.tsv ---

function runs_tsv(data, from, to)
    rows = readlines(joinpath(data, "runs.tsv"))
    h = split(rows[1], '\t')
    col(n) = findfirst(==(n), h)
    s, id, at, sk, ld, t0 = col("source"), col("run_id"), col("agent_type"), col("skills"),
                            col("loaded"), col("t_start")
    out = Pair{String,Vector{Pair{Symbol,String}}}[]
    for r in rows[2:end]
        v = split(r, '\t')
        seen = Pair{Symbol,String}[:source => v[s], :agent => v[at]]
        append!(seen, (:skill => String(x) for x in split(v[sk], ';') if !isempty(x)))
        append!(seen, (:nested => String(x) for x in split(v[ld], ';') if !isempty(x)))
        push!(out, "$(v[s]):$(v[id])" => seen)
    end
    out
end

# An agent type counts for the definition whose name it is, or whose name and a suffix it is:
# `julia-critic-high` is a run of `julia-critic`.
function agent_of(t, names)
    t in names && return t
    best = ""
    for n in names
        startswith(t, n * "-") && length(n) > length(best) && (best = n)
    end
    best
end

# --- failure lines ---

function cite!(files, dir)
    bycite = Dict(f.cite => f for f in files if !isempty(f.cite))
    unknown = Dict{String,Int}()
    for f in sort(readdir(dir; join = true))
        endswith(f, ".md") || continue
        for l in eachline(f)
            occursin(r"^\d\d \| ", l) || continue
            v = String.(strip.(split(l, " | ")))
            length(v) == 9 || error("$(basename(f)): $(length(v)) fields in: $(first(l, 80))")
            class = strip(replace(v[6], r"\(.*$" => ""))
            (isempty(class) || class == "—") && continue
            text = replace(v[7], r"\([^)]*\)" => "")
            for m in unique(m.match for m in eachmatch(
                r"(?:agents|skills|rules|instructions|commands)/[\w./-]+?\.md", text))
                x = get(bycite, m, nothing)
                if x === nothing
                    unknown[m] = get(unknown, m, 0) + 1
                else
                    x.classes[class] = get(x.classes, class, 0) + 1
                end
            end
        end
    end
    unknown
end

function main(args)
    data, lines = args[1], args[2]
    from, to = only(option(args, "--from")), only(option(args, "--to"))
    projects = something(tryfirst(option(args, "--projects")), joinpath(HOME, ".claude", "projects"))
    exclude = [rstrip(abspath(x), '/') for x in option(args, "--exclude")]

    files = File[]
    for h in option(args, "--harness")
        append!(files, harness_files(abspath(h)))
    end
    for t in option(args, "--tree")
        append!(files, tree_files(abspath(t)))
    end
    for r in option(args, "--claude-md"), f in claude_md(abspath(r))
        any(x -> x.path == f.path, files) || push!(files, f)
    end
    for n in option(args, "--notes")
        append!(files, notes(abspath(n), exclude))
    end
    append!(files, memory(projects))

    index = Dict{Pair{Symbol,String},Vector{File}}()
    for f in files, k in f.keys
        push!(get!(index, k, File[]), f)
    end
    agents = Set(last(k) for f in files for k in f.keys if first(k) == :agent)
    for (id, seen) in [runs_tsv(data, from, to); transcripts(projects, from, to)]
        for k in seen
            if first(k) == :agent
                k = :agent => agent_of(last(k), agents)
            end
            for f in get(index, k, File[])
                push!(f.runs, id)
            end
        end
    end
    unknown = cite!(files, lines)

    open(joinpath(data, "instructions.tsv"), "w") do io
        println(io, "path\tkind\ttokens\tloads\truns\tclasses")
        for f in files
            println(io, join((tilde(f.path), f.kind, tokens(f), f.loads, length(f.runs),
                              classes(f)), '\t'))
        end
    end

    println("| file | kind | tokens | loads | runs | failure classes that cite it |")
    println("|:--|:--|--:|:--|--:|:--|")
    for f in files
        println("| `$(tilde(f.path))` | $(f.kind) | $(tokens(f)) | $(f.loads) | $(length(f.runs)) | ",
                isempty(f.classes) ? "—" : classes(f), " |")
    end

    println("\n| kind | files | tokens | no run loaded it | no failure line cites it |")
    println("|:--|--:|--:|--:|--:|")
    for k in unique(f.kind for f in files)
        v = filter(f -> f.kind == k, files)
        println("| $k | $(length(v)) | $(sum(tokens, v)) | $(count(f -> isempty(f.runs), v)) | ",
                count(f -> isempty(f.classes), v), " |")
    end
    println("| all | $(length(files)) | $(sum(tokens, files)) | $(count(f -> isempty(f.runs), files)) | ",
            count(f -> isempty(f.classes), files), " |")

    println("\nNo run loaded these files:\n")
    for f in files
        isempty(f.runs) && println("- `$(tilde(f.path))` ($(f.kind))")
    end
    println("\nThese harness files loaded, and no failure line cites them:\n")
    for f in files
        !isempty(f.cite) && !isempty(f.runs) && isempty(f.classes) &&
            println("- `$(f.cite)` ($(f.kind), $(length(f.runs)) runs)")
    end
    if !isempty(unknown)
        println("\nFailure lines cite these paths, which are no instruction file:\n")
        for (k, n) in sort(collect(unknown))
            println("- `$k` ($n lines)")
        end
    end
end

tokens(f) = round(Int, length(read(f.path, String)) / 3.5)
classes(f) = join(("$k $n" for (k, n) in sort(collect(f.classes); by = x -> (-x[2], x[1]))), "; ")
tryfirst(v) = isempty(v) ? nothing : v[1]

main(ARGS)
