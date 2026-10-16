# Count the failure lines of the taxonomy readers by class, stage, preventing file and reason.
#
#   julia --startup-file=no taxonomy.jl <lines-dir>
#
# Reads every *.md in <lines-dir>. A failure line starts with a two-digit dossier number and has
# nine fields separated by " | ":
#
#   dossier | run | stage | failure | evidence | class | preventing file | loaded | why
#
# A field's text in parentheses is a note and does not count. A line whose class is `—` records
# that a dossier has no failure. Prints Markdown tables: lines per class with the reasons, lines per
# stage, the three most cited preventing files per class, and the preventing files that ten or more
# lines cite. A preventing file under `Tasks/`, or
# written as "the part's spec" or "the plan's", counts as the part's spec.

function field(s)
    s = strip(replace(s, r"\(.*$" => ""))
    isempty(s) ? "—" : s
end

function why(s)
    s = lowercase(s)
    for w in ("not loaded", "absent", "ignored", "wrong", "unknown")
        occursin(w, s) && return w
    end
    "—"
end

function preventing(s)
    s = strip(s)
    (startswith(s, "none") || s == "—" || isempty(s)) && return "none"
    (startswith(s, "Tasks/") || startswith(s, "the part") || startswith(s, "the plan")) &&
        return "the part's spec"
    m = match(r"^((?:agents|skills|rules|instructions)/[\w./-]+?\.md)", s)
    m === nothing ? "other: " * first(s, 40) : String(m[1])
end

function main(dir)
    lines = Vector{Vector{String}}()
    for f in sort(readdir(dir; join = true))
        endswith(f, ".md") || continue
        for l in eachline(f)
            occursin(r"^\d\d \| ", l) || continue
            v = String.(strip.(split(l, " | ")))
            length(v) == 9 ||
                error("$(basename(f)): $(length(v)) fields in: $(first(l, 80))")
            field(v[6]) == "—" && continue
            push!(lines, v)
        end
    end
    n = length(lines)
    dossiers = length(unique(v[1] for v in lines))
    println("$n failure lines from $dossiers dossiers.\n")

    whys = ("absent", "not loaded", "ignored", "wrong", "unknown")
    classes = Dict{String,Vector{Int}}()
    for v in lines
        c = get!(classes, field(v[6]), zeros(Int, 7))
        c[1] += 1
        k = findfirst(==(why(v[9])), whys)
        k === nothing || (c[k+1] += 1)
        c[7] = length(unique(w[1] for w in lines if field(w[6]) == field(v[6])))
    end
    println(
        "| class | lines | dossiers | absent | not loaded | ignored | wrong | unknown |",
    )
    println("|:--|--:|--:|--:|--:|--:|--:|--:|")
    for (k, c) in sort(collect(classes); by = x -> -x[2][1])
        println(
            "| $k | $(c[1]) | $(c[7]) | $(c[2]) | $(c[3]) | $(c[4]) | $(c[5]) | $(c[6]) |",
        )
    end
    t = [count(v -> why(v[9]) == w, lines) for w in whys]
    println("| all | $n | $dossiers | ", join(t, " | "), " |\n")

    stages = Dict{String,Int}()
    for v in lines
        s = field(split(v[3], "/")[1])
        stages[s] = get(stages, s, 0) + 1
    end
    println("| stage | lines |")
    println("|:--|--:|")
    for (k, c) in sort(collect(stages); by = x -> -x[2])
        println("| $k | $c |")
    end

    println("\n| class | most cited preventing files |")
    println("|:--|:--|")
    for (k, _) in sort(collect(classes); by = x -> -x[2][1])
        cited = Dict{String,Int}()
        for v in lines
            field(v[6]) == k || continue
            p = preventing(v[7])
            cited[p] = get(cited, p, 0) + 1
        end
        top = first(sort(collect(cited); by = x -> -x[2]), 3)
        println("| $k | ", join(("$p $c" for (p, c) in top), "; "), " |")
    end

    files = Dict{String,Vector{Int}}()
    for v in lines
        c = get!(files, preventing(v[7]), zeros(Int, 6))
        c[1] += 1
        k = findfirst(==(why(v[9])), whys)
        k === nothing || (c[k+1] += 1)
    end
    println(
        "\n| preventing file | lines | absent | not loaded | ignored | wrong | unknown |",
    )
    println("|:--|--:|--:|--:|--:|--:|--:|")
    for (k, c) in sort(collect(files); by = x -> -x[2][1])
        c[1] >= 10 || continue
        println("| $k | ", join(c, " | "), " |")
    end
end

main(ARGS[1])
