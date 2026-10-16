# Lint instruction files for the words that date a text or narrate its history.
#
#   julia --startup-file=no tense-lint.jl <instructions.tsv> [--kind <kind>]...
#   julia --startup-file=no tense-lint.jl <file.md>...
#
# <instructions.tsv> is the table of instructions.jl; --kind keeps only the rows of those kinds.
# A CHANGELOG.md is skipped. The words: now, currently, recently, as of, originally, previously,
# used to (not after a form of "be" or "get": "is used to build" is present tense), no longer,
# has been changed to, going forward, from now on, and since <date>. A word inside a code span,
# a fenced block, a quotation ("…" or “…”), an emphasis that holds only the word (*now*), or an
# emphasis that holds two or more of the words (a list of them) is a mention, not a use, and does
# not count. Prints one line per hit, file:line, the word and the
# line, then the hits per file. Exit 1 when a hit exists.

const HOME = homedir()
untilde(p) = startswith(p, "~/") ? joinpath(HOME, p[3:end]) : p
tilde(p) = startswith(p, HOME) ? "~" * p[length(HOME)+1:end] : p

const MONTH = "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
const WORDS = [
    "from now on" => r"\bfrom now on\b"i,
    "now" => r"\bnow\b"i,
    "currently" => r"\bcurrently\b"i,
    "recently" => r"\brecently\b"i,
    "as of" => r"\bas of\b"i,
    "originally" => r"\boriginally\b"i,
    "previously" => r"\bpreviously\b"i,
    "used to" => r"(?<!\bis )(?<!\bare )(?<!\bbe )(?<!\bbeen )(?<!\bbeing )(?<!\bwas )(?<!\bwere )(?<!\bget )(?<!\bgets )\bused to\b"i,
    "no longer" => r"\bno longer\b"i,
    "has been changed to" => r"\bha(?:s|ve) been changed to\b"i,
    "going forward" => r"\bgoing forward\b"i,
    "since <date>" => Regex("\\bsince (?:\\d{4}(?:-\\d{2}){0,2}\\b|$MONTH|\\d{1,2} $MONTH)", "i"),
]

# The text of a line with its mentions blanked: code spans, quotations, an emphasis that holds
# only a linted word, and an emphasis that holds two or more (a list of the words).
function prose(l)
    l = replace(l, r"`[^`]*`" => " ", r"\"[^\"]*\"" => " ", r"“[^”]*”" => " ")
    for (_, re) in WORDS
        l = replace(l, Regex("\\*{1,2}_?(?:" * re.pattern * ")_?\\*{1,2}", "i") => " ")
    end
    list(s) = count(w -> occursin(w[2], s), WORDS) >= 2 ? " " : s
    replace(replace(l, r"\*\*[^*]+\*\*" => list), r"(?<!\*)\*[^*]+\*(?!\*)" => list)
end

function lint(file)
    hits = Tuple{Int,String,String}[]
    fence = false
    for (i, l) in enumerate(eachline(file))
        if occursin(r"^\s*(```|~~~)", l)
            fence = !fence
            continue
        end
        fence && continue
        p = prose(l)
        for (w, re) in WORDS
            occursin(re, p) || continue
            push!(hits, (i, w, strip(l)))
            p = replace(p, re => " ")        # `from now on` is not also `now`
        end
    end
    hits
end

function main(args)
    files = String[]
    if endswith(args[1], ".tsv")
        kinds = [args[i+1] for i in 2:length(args)-1 if args[i] == "--kind"]
        for r in readlines(args[1])[2:end]
            v = split(r, '\t')
            (isempty(kinds) || v[2] in kinds) && push!(files, untilde(String(v[1])))
        end
    else
        files = args
    end
    filter!(f -> basename(f) != "CHANGELOG.md", files)
    total = 0
    perfile = Pair{String,Int}[]
    for f in files
        h = lint(f)
        isempty(h) && continue
        for (i, w, l) in h
            println("- `$(tilde(f)):$i` *$w*: ", replace(first(l, 160), '|' => "\\|"))
        end
        total += length(h)
        push!(perfile, tilde(f) => length(h))
    end
    println("\n$total hits in $(length(perfile)) of $(length(files)) files.")
    isempty(perfile) || println("\n| file | hits |\n|:--|--:|")
    for (f, n) in sort(perfile; by = x -> -x[2])
        println("| `$f` | $n |")
    end
    exit(total == 0 ? 0 : 1)
end

main(ARGS)
