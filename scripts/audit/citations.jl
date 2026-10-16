# Check what the instruction files cite: paths, commands, long flags, tool names, and agent and
# skill names. Prints each citation that does not resolve, with file:line.
#
#   julia --startup-file=no citations.jl <instructions.tsv> [--kind <kind>]... [--root <dir>]... \
#       [--tools <tools.tsv>]
#
# <instructions.tsv> is the table of instructions.jl; --kind keeps only the rows of those kinds.
# A citation is the text of a code span, a command of a fenced bash or sh block (a line, with its
# continuation lines and the lines of a quoted argument), or the target of a Markdown link. The
# checks:
#
#   path      a code span with a `/` and no space, or a link target. `~/` is the home directory; a
#             relative path resolves against the file's directory, its repository's root, each
#             --root, or a directory one to three levels below a --root, outside directories
#             whose name starts with a dot (a path that every repository has, such as
#             `docs/make.jl`). A `:<line>` suffix is dropped. Not checked:
#             a pattern (`<`, `*`, `$`, `{`, `…` or `|` in it), a git ref (`origin/`, `refs/`), a
#             slash command (`/word`), a host name (a first segment with two dots), and a
#             placeholder (a segment `Example…`, `foo`, `bar`, `X`, `x`, `a` or `b`).
#   command   the first word of a code span with a flag in it, and of every command of a fenced
#             line: an executable on the PATH, a file below scripts/ or bin/ of a --root
#             or of a directory below one, or a shell builtin.
#   flag      each `--flag`. For git, gh, glab, juliaup, rtk, jq, rg and harness, the help of the
#             command and its subcommands names it: `git help <sub>`, `<command> <sub>... --help`,
#             gh and glab with an empty configuration directory. For julia, a flag before the
#             script is julia's, and a flag after it is the script's. For a script that this
#             script finds, its source names the flag. Every other flag is counted as not checked.
#   tool      a CamelCase code span of two or more words that no Julia package and no `…Error` or
#             `…Exception` type has, on a line that says tool, or an `mcp__` name: a tool of
#             <tools.tsv>. A tool that no run called is reported as such; the check cannot tell it
#             from a name that does not exist.
#   agent     a kebab-case code span on a line that says agent: an agent of the table, or a
#             built-in agent type.
#   skill     a kebab-case code span on a line that says skill: a skill of the table.

const HOME = homedir()
untilde(p) = startswith(p, "~/") ? joinpath(HOME, p[3:end]) : p == "~" ? HOME : p
tilde(p) = startswith(p, HOME) ? "~" * p[length(HOME)+1:end] : p

const BUILTIN_AGENTS = Set(["general-purpose", "Explore", "Plan", "claude-code-guide",
                            "statusline-setup", "fork"])
const BUILTINS = Set(["cd", "export", "source", "echo", "set", "test", "exit", "read", "for",
                      "while", "if", "then", "do", "done", "fi", "true", "false", "unset"])
const HELP = Set(["git", "gh", "glab", "juliaup", "rtk", "jq", "rg", "harness"])
const PATTERN = r"[<>*$`{}…|]|\.\.\."
const PLACEHOLDER = r"(^|/)(Example[\w-]*|foo|bar|X|x|a|b)(\.\w+)?(/|$)"

struct Citation
    file::String
    line::Int
    text::String
    kind::Symbol        # :span, :fence, :link
end

function citations(file)
    v = Citation[]
    fence = nothing
    buf, first = "", 0
    for (i, l) in enumerate(eachline(file))
        m = match(r"^\s*(```+|~~~+)\s*([\w-]*)", l)
        if m !== nothing && isempty(buf)
            fence = fence === nothing ? lowercase(m[2]) : nothing
            continue
        end
        if fence !== nothing
            fence in ("bash", "sh", "zsh", "shell") || continue
            isempty(buf) && (startswith(strip(l), "#") || isempty(strip(l))) && continue
            isempty(buf) && (first = i)
            buf *= (isempty(buf) ? "" : "\n") * rstrip(l, '\\')
            # A line that ends in `\`, or leaves a single quote open, goes on.
            (endswith(l, "\\") || isodd(count(==('\''), replace(buf, "'\\''" => "")))) && continue
            push!(v, Citation(file, first, strip(buf), :fence))
            buf = ""
            continue
        end
        for c in eachmatch(r"(?<!`)`([^`]+)`(?!`)", l)
            push!(v, Citation(file, i, strip(c[1]), :span))
        end
        for c in eachmatch(r"\]\(([^)\s]+)\)", l)
            occursin(r"^(https?|mailto):|^[#@]", c[1]) || push!(v, Citation(file, i, c[1], :link))
        end
    end
    v
end

function reporoot(dir)
    d = dir
    while d != dirname(d)
        ispath(joinpath(d, ".git")) && return d
        d = dirname(d)
    end
    nothing
end

const CHILDREN = Dict{String,Vector{String}}()
children(d) = get!(CHILDREN, d) do
    isdir(d) || return String[]
    # A directory that the sandbox denies has no children here.
    es = try
        readdir(d)
    catch e
        e isa Base.IOError || rethrow()
        String[]
    end
    [joinpath(d, e) for e in es
     if !startswith(e, ".") && e != "node_modules" && isdir(joinpath(d, e)) && !islink(joinpath(d, e))]
end

# The directories one to `n` levels below a root.
below(r, n) = n == 0 ? String[] : (c = children(r); [c; [x for d in c for x in below(d, n - 1)]])
const BELOW = Dict{String,Vector{String}}()

function resolves(p, file, roots)
    p = replace(p, r":\d+([-–,]\d+)*$" => "", r"#.*$" => "")
    p = rstrip(p, ['.', ',', ';', ':'])
    isempty(p) && return true
    (startswith(p, "~") || startswith(p, "/")) && return ispath(untilde(p))
    bases = [dirname(file); something(reporoot(dirname(file)), String[]); roots]
    any(b -> ispath(joinpath(b, p)), bases) && return true
    any(r -> any(d -> ispath(joinpath(d, p)), get!(() -> below(r, 3), BELOW, r)), roots)
end

ispathlike(t) =
    !occursin(r"\s", t) && occursin('/', t) && !occursin(r"^[a-z]+://", t) &&
    !occursin(r"^[\w.-]+/[\w.-]+#\d+$", t) &&       # owner/repo#NN
    !occursin(r"^--?\w", t) && !occursin('=', t) && !occursin(r"[()\[\]]", t)

notchecked(t) =
    occursin(PATTERN, t) || occursin(r"^(origin|upstream|refs)/", t) ||
    occursin(r"^/[\w-]+$", t) || occursin(r"^[\w-]+\.[\w-]+\.[\w.-]+/", t) ||
    occursin(PLACEHOLDER, t)

# The commands of a citation: a fenced command splits at `&&`, `||`, `;` and `|`, outside quotes.
function commands(c::Citation)
    t = replace(c.text, r"^\$\s+" => "")
    t = replace(t, r"'[^']*'"s => "''", r"\"[^\"]*\""s => "\"\"")
    t = replace(t, r"(^|\s)#[^\n]*" => "")
    parts = c.kind == :fence ? split(t, r"&&|\|\||;|\||\n") : [t]
    v = Vector{Vector{String}}()
    for p in parts
        w = String.(split(strip(p)))
        while !isempty(w) && occursin(r"^\w+=", w[1])     # an environment assignment
            popfirst!(w)
        end
        isempty(w) || push!(v, w)
    end
    v
end

const FOUND = Dict{String,Union{String,Nothing}}()
# The file of a script name or path below scripts/ or bin/ of a root or of a directory below one.
function script(w, roots)
    get!(FOUND, w) do
        if startswith(w, "~") || startswith(w, "/")
            f = untilde(w)
            return isfile(f) && any(r -> startswith(f, r * "/"), roots) ? f : nothing
        end
        n = basename(w)
        for r in roots, d in [r; children(r)], s in ("scripts", "bin", "")
            f = joinpath(d, s, w)
            isfile(f) && return f
            f = joinpath(d, s, n)
            !isempty(s) && isfile(f) && return f
        end
        nothing
    end
end

executable(w, roots) =
    w in BUILTINS || Sys.which(w) !== nothing || script(w, roots) !== nothing || isfile(untilde(w))

const EMPTY = mktempdir()
const HELPTEXT = Dict{Vector{String},Union{String,Nothing}}()
function helptext(cmd)
    get!(HELPTEXT, cmd) do
        c = cmd[1] == "git" ? `git help $(length(cmd) > 1 ? cmd[2] : "git")` : `$cmd --help`
        c = addenv(c, "MANPAGER" => "cat", "PAGER" => "cat", "GH_CONFIG_DIR" => EMPTY,
                   "GLAB_CONFIG_DIR" => EMPTY, "GLAB_CHECK_UPDATE" => "false")
        out = IOBuffer()
        run(pipeline(ignorestatus(c); stdout = out, stderr = out))
        s = replace(String(take!(out)), r".\x08" => "")
        occursin(r"is not a git command|No manual entry|unknown command|invalid choice|unrecognized subcommand"i, s) &&
            return nothing
        replace(s, r"--\[no-\]([\w-]+)" => s"--\1 --no-\1")
    end
end

# The subcommand words come after git's global options and before the first other flag or argument.
function subcommand(w)
    n = w[1] in ("gh", "glab") ? 2 : w[1] in ("git", "rtk", "harness", "juliaup") ? 1 : 0
    s = String[w[1]]
    i = 2
    if w[1] == "git"
        while i <= length(w) && startswith(w[i], "-")
            i += w[i] in ("-C", "-c") ? 2 : 1
        end
    end
    for x in w[i:end]
        length(s) > n && break
        occursin(r"^[a-z][a-z-]*$", x) || break
        push!(s, x)
    end
    s
end

longflags(w) = unique(replace(x, r"=.*$" => "") for x in w if occursin(r"^--[a-z][\w-]*", x))
hasflag(text, fl) = occursin(Regex("(?<![\\w-])" * fl * "(?![\\w-])"), text)

function main(args)
    rows = readlines(args[1])
    kinds = String[]
    roots = String[]
    toolsfile = nothing
    i = 2
    while i <= length(args)
        a, x = args[i], args[i+1]
        a == "--kind" ? push!(kinds, x) : a == "--root" ? push!(roots, abspath(untilde(x))) :
        a == "--tools" ? (toolsfile = x) : error("unknown option $a")
        i += 2
    end
    files = String[]
    agents, skills = Set{String}(), Set{String}()
    for r in rows[2:end]
        v = split(r, '\t')
        (isempty(kinds) || v[2] in kinds) && push!(files, untilde(String(v[1])))
        v[2] == "agent" && push!(agents, replace(basename(v[1]), ".md" => ""))
        v[2] == "skill" && push!(skills, basename(dirname(v[1])))
    end
    tools = Set{String}()
    if toolsfile !== nothing
        for r in readlines(toolsfile)[2:end]
            t = split(r, '\t')[3]
            push!(tools, t)
            m = match(r"^mcp__\w+?__(\w+)$", t)
            m === nothing || push!(tools, m[1])
        end
    end
    packages = Set{String}(readdir(joinpath(HOME, ".julia", "packages")))

    bad = Dict{Symbol,Vector{Tuple{Citation,String}}}()
    n = Dict{Symbol,Int}()
    note(k, c, why) = push!(get!(bad, k, Tuple{Citation,String}[]), (c, why))
    seen(k, m = 1) = (n[k] = get(n, k, 0) + m)

    for f in files, c in citations(f)
        t = c.text
        l = lowercase(read_line(c))
        if c.kind == :link || (c.kind == :span && ispathlike(t))
            if notchecked(t)
                seen(:pattern)
            else
                seen(:path)
                resolves(t, f, roots) || note(:path, c, "does not exist")
            end
            continue
        end
        if c.kind == :span && occursin(r"^(mcp__\w+|[A-Z][a-z]+(?:[A-Z][a-z]+)+)$", t)
            (toolsfile === nothing || t in packages || occursin(r"(Error|Exception)$", t)) && continue
            if t in tools
                seen(:tool)
            elseif startswith(t, "mcp__") || occursin(r"\btools?\b", l)
                seen(:tool)
                note(:tool, c, "no run called it")
            end
            continue
        end
        if c.kind == :span && occursin(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$", t)
            if occursin(r"\bagents?\b|subagent", l) && !(t in skills)
                seen(:agent)
                t in agents || t in BUILTIN_AGENTS || note(:agent, c, "no such agent")
                continue
            elseif occursin(r"\bskills?\b", l) && !(t in agents)
                seen(:skill)
                t in skills || note(:skill, c, "no such skill")
                continue
            end
        end
        for w in commands(c)
            c.kind == :span && !any(x -> occursin(r"^--?[A-Za-z]", x), w[2:end]) && continue
            occursin(r"^[A-Za-z0-9_~/.][A-Za-z0-9_.+/~-]*$", w[1]) || continue
            length(w) > 1 && w[2] == "=" && continue       # an assignment, not a command
            occursin(PATTERN, w[1]) && continue
            seen(:command)
            if !executable(w[1], roots)
                note(:command, c, "`$(w[1])` is no executable")
                continue
            end
            check_flags(w, c, roots, note, seen)
        end
    end

    println("| check | citations | not resolved |")
    println("|:--|--:|--:|")
    for k in (:path, :command, :flag, :tool, :agent, :skill)
        println("| $k | $(get(n, k, 0)) | $(length(get(bad, k, []))) |")
    end
    println("| path not checked: pattern, ref, slash command, host, placeholder | $(get(n, :pattern, 0)) | — |")
    println("| flag not checked | $(get(n, :unchecked, 0)) | — |")
    for k in (:path, :command, :flag, :tool, :agent, :skill)
        haskey(bad, k) || continue
        println("\n### $k\n")
        for (c, why) in bad[k]
            println("- `$(tilde(c.file)):$(c.line)` `$(replace(first(c.text, 120), r"[`\n]" => " "))`: $why")
        end
    end
end

function check_flags(w, c, roots, note, seen)
    if w[1] == "julia"
        k = findfirst(x -> !startswith(x, "-"), w[2:end])
        k === nothing && return seen(:unchecked, length(longflags(w)))
        own, rest = w[1:k], w[k+1:end]
        h = helptext(["julia"])
        for fl in longflags(own)
            seen(:flag)
            hasflag(h, fl) || note(:flag, c, "`julia` has no `$fl`")
        end
        s = endswith(rest[1], ".jl") ? script(rest[1], roots) : nothing
        flags = longflags(rest[2:end])
        s === nothing && return seen(:unchecked, length(flags))
        src = read(s, String)
        for fl in flags
            seen(:flag)
            hasflag(src, fl) || note(:flag, c, "`$(rest[1])` has no `$fl`")
        end
        return
    end
    flags = longflags(w)
    isempty(flags) && return
    if w[1] in HELP
        sub = subcommand(w)
        help = helptext(sub)
        if help === nothing
            note(:command, c, "`$(join(sub, ' '))`: no such subcommand")
            return
        end
        if w[1] == "git" && length(sub) > 1    # the flags before the subcommand are git's own
            k = findfirst(==(sub[2]), w)
            for fl in longflags(w[2:k-1])
                seen(:flag)
                hasflag(helptext(["git"]), fl) || note(:flag, c, "`git` has no `$fl`")
            end
            flags = longflags(w[k+1:end])
        end
        for fl in flags
            seen(:flag)
            hasflag(help, fl) || note(:flag, c, "`$(join(sub, ' '))` has no `$fl`")
        end
    elseif (s = script(w[1], roots)) !== nothing
        src = read(s, String)
        for fl in flags
            seen(:flag)
            hasflag(src, fl) || note(:flag, c, "`$(w[1])` has no `$fl`")
        end
    else
        seen(:unchecked, length(flags))
    end
end

const LINES = Dict{String,Vector{String}}()
read_line(c) = get!(() -> readlines(c.file), LINES, c.file)[c.line]

main(ARGS)
