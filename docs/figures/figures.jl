# The figures of the documentation site, drawn with Graphviz's `dot` from Graphviz_jll.
#
# `make_figures()` writes one SVG file for each figure into docs/src/assets/figures/. docs/make.jl
# calls it before `makedocs`, and the files are committed, so that GitHub shows them too. The docs
# workflow fails when a build changes a committed figure.
#
# The call graphs come from docs/figures/calls.toml: one entry for each spawn. The kind of each
# node comes from where its source is, its tier and its effort from the source's frontmatter, and
# its model from the [claude] table of examples/models.toml. `harness test` checks calls.toml.

using Graphviz_jll
using TOML

const ROOT = normpath(joinpath(@__DIR__, "..", ".."))
const FIGURES = joinpath(ROOT, "docs", "src", "assets", "figures")

# The call graphs: the file name, and the caller whose spawns the figure follows, or `nothing` for
# every edge of calls.toml.
const CALL_GRAPHS = [
    "build-part" => "build-part",
    "build-reviewed" => "build-reviewed",
    "julia-pr-shepherd" => "julia-pr-shepherd",
    "calls" => nothing,
]

"""The `key: value` lines of the frontmatter of the Markdown file `path`, with the quotes of a
quoted value removed. A key with a block list has no entry."""
function frontmatter(path)
    lines = readlines(path)
    first(lines) == "---" || error("$path has no frontmatter")
    meta = Dict{String,String}()
    for line in lines[2:(findnext(==("---"), lines, 2) - 1)]
        m = match(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.*?)\s*$", line)
        (m === nothing || isempty(m[2])) && continue
        meta[m[1]] = startswith(m[2], '"') ? unescape_string(m[2][2:(end - 1)]) : m[2]
    end
    return meta
end

"""The name, kind, model and effort of the agent or skill `name`."""
function node(name, models)
    agent = joinpath(ROOT, "agents", name * ".md")
    skill = joinpath(ROOT, "skills", name, "SKILL.md")
    kind, path = isfile(agent) ? ("agent", agent) : isfile(skill) ? ("skill", skill) :
                 error("calls.toml names $name, which is no agent and no skill")
    meta = frontmatter(path)
    model = haskey(meta, "model") ? models[meta["model"]] : "the caller's model"
    effort = get(meta, "effort", "the session's effort")
    return (; name, kind, model, effort)
end

"""Text for a Graphviz HTML-like label."""
html(text) = replace(text, "&" => "&amp;", "<" => "&lt;", ">" => "&gt;")

const FILL = Dict("agent" => "#dbe8f7", "skill" => "#f7ecc8")

function node_dot(n)
    small = html("$(n.kind) on $(n.model)") * "<br/>" * html("effort: $(n.effort)")
    return """  "$(n.name)" [fillcolor="$(FILL[n.kind])", label=<<b>$(html(n.name))</b><br/><font point-size="10">$small</font>>];\n"""
end

function edge_dot(call)
    text = get(call, "label", "")
    haskey(call, "effort") && (text *= (isempty(text) ? "" : ", ") * "at $(call["effort"]) effort")
    label = isempty(text) ? "" :
            """ [label=<<table border="0" cellborder="0" cellpadding="2" bgcolor="#f2f2f2"><tr><td>$(html(text))</td></tr></table>>]"""
    return """  "$(call["caller"])" -> "$(call["callee"])"$label;\n"""
end

"""The entries of `calls` that `root` reaches: its own spawns, then their callees' spawns."""
function reached(calls, root)
    root === nothing && return calls
    seen, frontier = Set([root]), [root]
    while !isempty(frontier)
        caller = popfirst!(frontier)
        for c in calls
            c["caller"] == caller && c["callee"] ∉ seen && (push!(seen, c["callee"]); push!(frontier, c["callee"]))
        end
    end
    return filter(c -> c["caller"] in seen, calls)
end

"""The `dot` source of the call graph of `calls`, top to bottom, or left to right with `across`."""
function call_graph(name, calls, models; across = false)
    names = unique(vcat([[c["caller"], c["callee"]] for c in calls]...))
    io = IOBuffer()
    print(io, "digraph \"$name\" {\n",
          "  graph [bgcolor=\"transparent\", fontname=\"Helvetica\", nodesep=0.3, ranksep=0.5",
          across ? ", rankdir=LR" : "", "];\n",
          "  node [shape=box, style=\"rounded,filled\", fontname=\"Helvetica\", fontsize=13, ",
          "fontcolor=\"#1a1a1a\", color=\"#5a5a5a\", margin=\"0.15,0.06\"];\n",
          "  edge [color=\"#8c8c8c\", penwidth=1.4, fontname=\"Helvetica\", fontsize=10, fontcolor=\"#1a1a1a\"];\n")
    foreach(n -> print(io, node_dot(node(n, models))), names)
    foreach(c -> print(io, edge_dot(c)), calls)
    print(io, "}\n")
    return String(take!(io))
end

"""A `dot` command that loads only Graphviz's core and dot-layout plugins, from a directory of its
own. Without the Pango plugin, `dot` sizes text with its own font metrics, not with the fonts of
the machine, so that each machine draws the same figure."""
function dot_command()
    dot = Graphviz_jll.dot()
    lib = joinpath(dirname(dirname(dot.exec[1])), "lib", "graphviz")
    dir = mktempdir()
    for f in readdir(lib)
        startswith(f, r"libgvplugin_(core|dot_layout)\.") && symlink(joinpath(lib, f), joinpath(dir, f))
    end
    cmd = addenv(dot, "GVBINDIR" => dir)
    run(`$cmd -c`)
    return cmd
end

"""The SVG of the `dot` source `source`, without the comment that names the Graphviz version.
Anything `dot` prints on stderr is an error."""
function svg(cmd, source)
    out, err = IOBuffer(), IOBuffer()
    run(pipeline(`$cmd -Tsvg`; stdin = IOBuffer(source), stdout = out, stderr = err))
    message = String(take!(err))
    isempty(message) || error("dot: $message")
    return replace(String(take!(out)), r"<!-- Generated by graphviz version .*?-->\n"s => "")
end

"""Write every figure into FIGURES."""
function make_figures()
    calls = TOML.parsefile(joinpath(@__DIR__, "calls.toml"))["call"]
    models = TOML.parsefile(joinpath(ROOT, "examples", "models.toml"))["claude"]
    cmd = dot_command()
    mkpath(FIGURES)
    for (file, root) in CALL_GRAPHS
        source = call_graph(file, reached(calls, root), models; across = root === nothing)
        write(joinpath(FIGURES, "$file.svg"), svg(cmd, source))
    end
    return nothing
end
