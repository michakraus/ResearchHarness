# Write the operator mutants of a branch's diff as a mutant list for mutate.jl.
#
#   julia --startup-file=no mutants.jl <package> <out.toml> [<base>]
#
# It reads the lines of `src/` that the working tree adds against <base> (default origin/main),
# parses each changed file with JuliaSyntax, and writes one mutant per operator node that starts on
# an added line:
#
#   delete       a statement of a block or of the file that holds more than one: a guard, an
#                update, a branch, a method
#   drop-term    `A && B` or `A || B` → `(A)` or `(B)`
#   ternary-branch  `c ? a : b` → `(a)` or `(b)`
#   drop-operand `a op b` → `(a)` or `(b)` for `+ - * /`; `a^b` → `(a)`; `abs(x)` → `(x)`
#   comparison   `<` ↔ `<=`, `>` ↔ `>=`, `≤` ↔ `<`, `≥` ↔ `>`, `==` ↔ `!=`, `===` ↔ `!==`
#   and-or       `&&` ↔ `||`
#   min-max      `min` ↔ `max`
#   clamp        `clamp(x, lo, hi)` → `x`
#   negate       the condition of an `if`, `elseif`, `while` or `?` → `!(…)`, or a leading `!` removed
#   return-code  a member of an `@enum` of the package → the next member
#   zero-one     `zero(…)` ↔ `one(…)`
#   literal      the integer `0` ↔ `1`
#
# A replacement by a part of the node goes in parentheses, so that no operator precedence changes
# what the mutant means. Each mutant carries its byte position `at`, so it matches by
# construction, and its line and operator. The named mutants of a part and the semantic ones that no operator gives are written by
# hand, beside this list. Check a hand-written list with `mutate.jl --check` before you run it.
# The script needs JuliaSyntax 1.0, so Julia 1.12 or later.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using JuliaSyntax: JuliaSyntax, SyntaxNode, parseall, kind, children, sourcetext, @K_str
using TOML

pkgversion(JuliaSyntax) >= v"1" ||
    error("mutants.jl needs JuliaSyntax 1.0, which this Julia ($VERSION) does not resolve; run it with ~/.juliaup/bin/julia")

"One mutant: `from` at the byte `at` of `file`, on line `line`, becomes `to`."
struct Mutant
    file::String
    line::Int
    at::Int
    from::String
    to::String
    operator::String
end

"The lines that a zero-context diff adds, per file of its new side."
function added_lines(diff)
    out = Dict{String, Set{Int}}()
    file = nothing
    for l in split(diff, '\n')
        if startswith(l, "+++ ")
            p = l[5:end]
            file = p == "/dev/null" ? nothing : (startswith(p, "b/") ? p[3:end] : p)
        elseif startswith(l, "@@ ") && file !== nothing
            m = match(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", l)
            start, n = parse(Int, m[1]), m[2] === nothing ? 1 : parse(Int, m[2])
            n > 0 && union!(get!(Set{Int}, out, file), start:(start + n - 1))
        end
    end
    return out
end

"The members of each `@enum` in `text`, in order."
function enum_members(text)
    out = Vector{Vector{String}}()
    visit(parseall(SyntaxNode, text; filename = "enum.jl")) do n
        kind(n) == K"macrocall" || return
        c = children(n)
        kind(c[1]) == K"MacroName" && sourcetext(c[1]) == "enum" || return
        members = [sourcetext(x) for x in c[3:end] if kind(x) == K"Identifier"]
        isempty(members) || push!(out, members)
    end
    return out
end

"Call `f` on `n` and every node below it."
function visit(f, n)
    f(n)
    c = children(n)
    c === nothing || foreach(x -> visit(f, x), c)
end

const SWAP = Dict("<" => "<=", "<=" => "<", ">" => ">=", ">=" => ">", "≤" => "<", "≥" => ">",
    "==" => "!=", "!=" => "==", "===" => "!==", "!==" => "===",
    "&&" => "||", "||" => "&&", "min" => "max", "max" => "min", "zero" => "one", "one" => "zero",
    "0" => "1", "1" => "0")

"""
The mutants of `text`, the source of `file`, that start on one of `lines`. `enums` are the members
of the package's `@enum`s, as `enum_members` gives them.
"""
function mutants(text, file, lines, enums)
    bytes = codeunits(text)
    # the first byte of each line, to find the line of a byte
    starts = [1; findall(==(UInt8('\n')), bytes) .+ 1]
    line(at) = searchsortedlast(starts, at)
    # a node's range can start with whitespace; its text starts at the first other byte
    function span(n)
        r = JuliaSyntax.byte_range(n)
        a = first(r)
        while a <= last(r) && bytes[a] in (UInt8(' '), UInt8('\t'), UInt8('\n'))
            a += 1
        end
        return a:last(r)
    end
    source(r) = String(bytes[r])
    next_member = Dict{String, String}()
    for e in enums, (i, m) in enumerate(e)
        next_member[m] = e[mod1(i + 1, length(e))]
    end
    out = Mutant[]
    add(r, to, op) = line(first(r)) in lines &&
                     push!(out, Mutant(file, line(first(r)), first(r), source(r), to, op))
    negate(c) = begin
        r = span(c)
        cc = children(c)
        if kind(c) == K"call" && cc !== nothing && length(cc) == 2 && sourcetext(cc[1]) == "!"
            add(r, source(span(cc[2])), "negate")
        else
            add(r, "!(" * source(r) * ")", "negate")
        end
    end
    function walk(n, in_enum)
        k = kind(n)
        c = children(n)
        part(x) = "(" * source(span(x)) * ")"
        if k in (K"block", K"toplevel") && c !== nothing && length(c) > 1
            foreach(x -> add(span(x), "", "delete"), c)
        end
        if k in (K"&&", K"||")
            add(span(n), part(c[1]), "drop-term")
            add(span(n), part(c[2]), "drop-term")
        elseif k == K"?"
            add(span(n), part(c[2]), "ternary-branch")
            add(span(n), part(c[3]), "ternary-branch")
        end
        if k == K"macrocall" && sourcetext(c[1]) == "enum"
            in_enum = true
        elseif k == K"call" && JuliaSyntax.is_infix_op_call(n) && length(c) == 3
            op = source(span(c[2]))
            op in ("<", "<=", ">", ">=", "≤", "≥", "==", "!=", "===", "!==") &&
                add(span(c[2]), SWAP[op], "comparison")
            if op in ("+", "-", "*", "/", "^")
                add(span(n), part(c[1]), "drop-operand")
                op == "^" || add(span(n), part(c[3]), "drop-operand")
            end
        elseif k == K"comparison"
            for x in c[2:2:end]
                op = source(span(x))
                haskey(SWAP, op) && add(span(x), SWAP[op], "comparison")
            end
        elseif k in (K"&&", K"||")
            # the operator is no node: it is the token between the two operands
            gap = (last(span(c[1])) + 1):(first(span(c[2])) - 1)
            tok = k == K"&&" ? "&&" : "||"
            i = findfirst(tok, source(gap))
            i === nothing || add((first(gap) + first(i) - 1):(first(gap) + last(i) - 1), SWAP[tok], "and-or")
        elseif k == K"call" && c !== nothing && kind(c[1]) == K"Identifier"
            head = sourcetext(c[1])
            head in ("min", "max") && add(span(c[1]), SWAP[head], "min-max")
            head in ("zero", "one") && add(span(c[1]), SWAP[head], "zero-one")
            head == "clamp" && length(c) == 4 && add(span(n), source(span(c[2])), "clamp")
            head == "abs" && length(c) == 2 && add(span(n), part(c[2]), "drop-operand")
        elseif k in (K"if", K"elseif", K"while", K"?")
            negate(c[1])
        elseif k == K"Identifier" && !in_enum && haskey(next_member, sourcetext(n))
            add(span(n), next_member[sourcetext(n)], "return-code")
        elseif k == K"Integer" && source(span(n)) in ("0", "1")
            add(span(n), SWAP[source(span(n))], "literal")
        end
        c === nothing || foreach(x -> walk(x, in_enum), c)
    end
    walk(parseall(SyntaxNode, text; filename = file), false)
    return unique(m -> (m.at, m.to), out)
end

"Write `ms` as a mutant list that mutate.jl reads."
function write_list(path, ms)
    tables = map(enumerate(ms)) do (i, m)
        from = first(split(m.from, '\n'))
        Dict("name" => "G$i $(m.operator): $(m.file):$(m.line) `$from` → `$(first(split(m.to, '\n')))`",
            "file" => m.file, "from" => m.from, "to" => m.to, "at" => m.at, "line" => m.line,
            "operator" => m.operator)
    end
    open(io -> TOML.print(io, Dict("mutant" => tables)), path, "w")
end

function main(args)
    length(args) in (2, 3) || (println(stderr, "usage: mutants.jl <package> <out.toml> [<base>]"); return 2)
    pkg, out = abspath(expanduser(args[1])), abspath(expanduser(args[2]))
    base = length(args) == 3 ? args[3] : "origin/main"
    diff = read(`git -C $pkg diff -U0 $base -- src`, String)
    lines = filter(kv -> endswith(first(kv), ".jl"), added_lines(diff))
    src = joinpath(pkg, "src")
    enums = reduce(vcat, (enum_members(read(joinpath(d, f), String))
                          for (d, _, fs) in walkdir(src) for f in fs if endswith(f, ".jl")); init = Vector{String}[])
    ms = Mutant[]
    for file in sort(collect(keys(lines)))
        append!(ms, mutants(read(joinpath(pkg, file), String), file, lines[file], enums))
    end
    write_list(out, ms)
    for file in sort(unique(m.file for m in ms))
        ops = [m.operator for m in ms if m.file == file]
        println(rpad(file, 40), length(ops), " mutants: ",
            join(("$(count(==(o), ops)) $o" for o in sort(unique(ops))), ", "))
    end
    println("\n$(length(ms)) mutants on $(sum(length, values(lines); init = 0)) added lines of $(length(lines)) files — $out")
    return 0
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
