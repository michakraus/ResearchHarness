#!/usr/bin/env julia
#
# Structural lint for the Markdown that carries claims and cross references: the two vaults
# `Knowledge/` and `Environment/`, and the two reference trees `Tasks/` and `Bibliography/`.
#
#     julia --startup-file=no wiki-lint.jl            # all four
#     julia --startup-file=no wiki-lint.jl Knowledge  # one of them
#     julia --startup-file=no wiki-lint.jl --strict   # warnings fail too
#     julia --startup-file=no wiki-lint.jl --quiet    # findings and totals only
#
# TWO SCOPE KINDS, BECAUSE ONE CHECK SET DOES NOT FIT BOTH
#
# A **vault** is a wiki: one claim per page, `[[wiki-links]]`, and a page nothing links to is
# worth knowing about. It gets every check.
#
# A **reference tree** is not a wiki. `Tasks/` is a work queue, `Bibliography/` is tooling around
# `.bib` files, and `Library/` is a catalogue of other people's papers; all three are dense in
# paths into `Packages/`, `Experiments/`, `Papers/`, `Books/` and `Projects/`, and that is the
# whole reason to lint them. They get the path and line-citation checks, and `Tasks/` also gets
# rule 14, the task board's schema. Running
# the wiki checks over `Tasks/` and `Bibliography/` reported 58 pages with no frontmatter, 56
# orphans and 566 dates in prose, none of which is a defect: a task file is not linked to, and its
# dates are the record `Tasks/CLAUDE.md` asks for.
#
# `Library/` is 2 400 Markdown files, 1 400 of them per-paper `description.md` stubs that hold no
# tree paths at all. Including them costs about a second and reports nothing, so they are not
# excluded: a stub that later grows a path should be checked like anything else.
#
# **`metadata.json`'s `source_ref` is deliberately not checked.** It is provenance — where a PDF
# came from at import — so a path that has since moved is an accurate record, not a decayed claim.
# Linting it would be the same error as linting a `CHANGELOG.md`.
#
# It finds what a test suite, a formatter and a docs build cannot: a sentence that is false
# because the tree moved under it. Every check is deterministic and reads the working tree. No
# model, no index, no network.
#
# EXIT STATUS
#
#   0  no ERROR (and, under --strict, no WARN either)
#   1  at least one finding at the failing severity
#   2  the lint itself could not run
#
# `harness ci-protection` reads an exit status; so does a pre-commit hook. Do not make this script
# print a verdict and exit 0.
#
# WHAT IS NOT LINTED, AND WHY
#
# `CHANGELOG.md` is skipped entirely. An entry states what was true when it was written, and a
# changelog is never corrected, so a path that has since moved is not a defect there. Linting it
# would report the history as a fault and invite exactly the rewrite the convention forbids.
#
# SEVERITIES
#
# ERROR is for a claim that is certainly false and whose fix is unambiguous: a link that resolves
# in the other vault, a link broken across a newline, a line citation past the end of its file, a
# generated block that disagrees with the disk, a declared dependency that is gone.
#
# WARN is everything that needs a person to judge it. Three classes of warning are **not**
# defects, and saying so is what keeps the error list worth reading:
#
#   * `link-unwritten` — this tree's own README calls a link to a page that does not exist yet a
#     legitimate marker of something worth writing.
#   * `path` — prose often names a path deliberately *because* it is gone: "not, as before, at
#     `~/Research/.syncignore`". A dead path is sometimes the point of the sentence.
#   * `orphan` — a page nothing links to is worth knowing about, not a fault.
#
# THREE CHECKS WERE WRITTEN AND REMOVED, EACH AFTER MEASURING THE CORPUS
#
# **`date-in-prose`** demanded that an absolute date move into `verified:`. It fired 333 times, and
# a sample showed roughly one in four was a page timestamp; the rest date a *measurement*, an
# *observation* or a *changelog entry* — `Measured 2026-09-02, by probing each of the nine declared
# entries` is this tree's own discipline, not decay. Narrowing it to lines that begin
# `Verified|Measured|Checked <date>` left 27, and most of those were still dating a probe.
#
# **`frontmatter`** warned on every page without a YAML block: 160 of them. Adding an empty block
# to all 160 would silence the warning and tell a reader nothing. Frontmatter is now **opt-in and
# earned** — a page declares `verified:` and `depends_on:` when it wants a mechanical staleness
# check — and the lint validates what is there rather than demanding that something be there.
#
# WHAT `verified:` MEANS, EXACTLY
#
# `verified: 2026-09-19` says **the declared dependencies held on that date** — the paths existed
# and the anchors matched. It does **not** say the claim was re-derived or the scripts re-run.
# That is the only reading the `stale` check can enforce, so it is the only one the key may carry.
# Re-running a check is `checks:`, and running them is phase 4 of
# `Tasks/Stop Knowledge going stale.md`, not this script.
#
# **`readme-alias`** wanted every `README.md` to declare an alias so `[[…]]` to it would resolve.
# These READMEs render on GitLab, where a YAML block shows, and Obsidian already resolves a
# vault-relative `[[Notes/reviews/README]]`. The link form was the fix, not metadata.
#
# The pattern in all three: a check written from a policy, not from the corpus. Measure what a new
# check would fire on before trusting it, and delete it when the corpus disagrees.
#
# `--strict` fails on warnings too. Do not turn it on before the backlog is cleared.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using Dates
using Unicode
using YAML

const ROOT = get(ENV, "RESEARCH_ROOT", joinpath(homedir(), "Research"))

# Order matters only for the report. `:vault` gets every check, `:refs` gets paths and line
# citations. Adding a tree here is the whole cost of extending the lint to it.
const SCOPES = ["Knowledge" => :vault, "Environment" => :vault,
    "Tasks" => :refs, "Bibliography" => :refs, "Library" => :refs]

kind_of(name) = something(findfirst(p -> p.first == name, SCOPES), 0) == 0 ? :refs :
                SCOPES[findfirst(p -> p.first == name, SCOPES)].second

# Backticked spans starting with one of these are treated as paths into the tree.
const PATH_PREFIXES = ["~/Research/", "~/.claude/", "Knowledge/", "Environment/", "Packages/",
    "Experiments/", "Papers/", "Books/", "Projects/", "Tasks/", "Library/", "Bibliography/",
    "Latex/", "Talks/"]

const SKIP_DIRS = Set([".git", ".obsidian", ".claude", "vendor", "__pycache__"])

nfc(s) = Unicode.normalize(String(s), :NFC)

struct Finding
    severity::Symbol      # :error or :warn
    check::String
    file::String          # relative to ROOT
    line::Int             # 0 when the finding is about the file as a whole
    message::String
end

# ---------------------------------------------------------------------------------------------
# Collecting the vault

"""
    markdown_files(vault) -> Vector{String}

Every `.md` file under `ROOT/vault`, as paths relative to `ROOT`, excluding `SKIP_DIRS` and
every `CHANGELOG.md`. Sorted, so the report is stable between runs.
"""
function markdown_files(vault::AbstractString)
    out = String[]
    base = joinpath(ROOT, vault)
    for (dir, dirs, files) in walkdir(base)
        filter!(d -> !(d in SKIP_DIRS), dirs)
        for f in files
            endswith(f, ".md") || continue
            f == "CHANGELOG.md" && continue
            push!(out, relpath(joinpath(dir, f), ROOT))
        end
    end
    return sort(out)
end

"""
    frontmatter(text) -> (Dict, Int)

The YAML block delimited by `---` on the first line, and the number of lines it occupies
(0 when there is none). A block that does not parse yields an empty dict and its own finding,
raised by the caller.
"""
function frontmatter(text::AbstractString)
    lines = split(text, '\n')
    (isempty(lines) || strip(lines[1]) != "---") && return (Dict{Any,Any}(), 0)
    close = findfirst(i -> strip(lines[i]) == "---", 2:length(lines))
    close === nothing && return (Dict{Any,Any}(), -1)      # -1 signals "opened, never closed"
    stop = close + 1
    body = join(lines[2:(stop - 1)], '\n')
    try
        parsed = YAML.load(body)
        return (parsed isa Dict ? parsed : Dict{Any,Any}(), stop)
    catch
        return (Dict{Any,Any}(), -2)                        # -2 signals "does not parse"
    end
end

# ---------------------------------------------------------------------------------------------
# Extraction

const LINK_RE = r"\[\[([^\]\|#]+?)\]\]"s
const BACKTICK_RE = r"`([^`\n]+)`"
const DATE_RE = r"\b(19|20)\d\d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b"
const GEN_OPEN_RE = r"<!--\s*generated:\s*([A-Za-z0-9_-]+)\s*-->"

# A span holding any of these is a pattern or a placeholder, not a path that must resolve.
const NOT_A_PATH = ['*', '?', '<', '>', '{', '}', '…', ' ', '\t']

# Two directories are ephemeral by rule: `.worktrees/` holds temporary checkouts, removed when
# the branch merges, and `.scratch/` holds logs and throw-away environments. A page naming one
# that is gone is describing what was done, not making a claim that has decayed.
const EPHEMERAL = ["~/Research/.worktrees/", "~/Research/.scratch/",
    ".worktrees/", ".scratch/"]

"""
    blank_code(text) -> String

`text` with the contents of every backticked span replaced by spaces, so that byte offsets are
unchanged and a `[[…]]` written as an example — `[[wiki-links]]` in a README — is not read as a
link. Fenced blocks are left alone; a link inside one is still a link Obsidian resolves.
"""
blank_code(text::AbstractString) =
    replace(text, BACKTICK_RE => m -> '`' * ' '^(length(m) - 2) * '`')

"1-based line number of byte offset `i`, from a precomputed vector of line-start offsets."
line_of(starts::Vector{Int}, i::Int) = searchsortedlast(starts, i)

line_starts(text::AbstractString) =
    vcat(1, [i + 1 for i in eachindex(text) if text[i] == '\n'])

"""
    wiki_links(text) -> Vector{(line, target, wrapped)}

Every `[[target]]`, including one broken across lines. `wrapped` says the source spanned a
newline, which Obsidian does **not** resolve however well the target reads.
"""
function wiki_links(text::AbstractString)
    src = blank_code(text)
    starts = line_starts(src)
    out = Tuple{Int,String,Bool}[]
    for m in eachmatch(LINK_RE, src)
        raw = m.captures[1]
        wrapped = occursin('\n', raw)
        target = nfc(replace(strip(raw), r"\s+" => " "))
        isempty(target) && continue
        push!(out, (line_of(starts, m.offset), target, wrapped))
    end
    return out
end

"""
    prose_paths(text) -> Vector{(line, span)}

Backticked spans that name a path into the tree and could resolve. A span holding a glob, a
`<placeholder>`, an ellipsis or whitespace is skipped: it is a pattern or a shape, and reporting
it as a dead path buries the real findings. That exclusion is why this check is an ERROR.
"""
function prose_paths(text::AbstractString)
    out = Tuple{Int,String}[]
    for (i, line) in enumerate(split(text, '\n'))
        for m in eachmatch(BACKTICK_RE, line)
            s = strip(m.captures[1])
            any(p -> startswith(s, p), PATH_PREFIXES) || continue
            any(c -> c in NOT_A_PATH, s) && continue
            any(p -> startswith(s, p), EPHEMERAL) && continue
            endswith(s, "...") && continue
            push!(out, (i, String(s)))
        end
    end
    return out
end

"""
    resolve(p) -> String

An absolute path for a tree-relative or `~`-relative path spelt in prose. Trailing separators
and a `:NN` suffix are removed by the caller, not here.
"""
function resolve(p::AbstractString)
    startswith(p, "~/") && return joinpath(homedir(), p[3:end])
    return joinpath(ROOT, p)
end

# ---------------------------------------------------------------------------------------------
# The checks

"""
    vault_names(vault, files, texts) -> Dict(target => file)

Every string that resolves to a page in this vault: its basename, its vault-relative path, and
every alias its frontmatter declares. Obsidian accepts all three.
"""
function vault_names(vault, files, texts)
    names = Dict{String,String}()
    for f in files
        names[nfc(splitext(basename(f))[1])] = f
        names[nfc(splitext(relpath(f, vault))[1])] = f
        fm, _ = frontmatter(texts[f])
        for a in get(fm, "aliases", String[])
            names[nfc(string(a))] = f
        end
    end
    return names
end

function lint_scope(vault::AbstractString, kind::Symbol, files, texts, names,
                    elsewhere::Dict{String,String}, findings::Vector{Finding})
    isempty(files) && (push!(findings, Finding(:error, "scope", vault, 0, "holds no Markdown"));
                       return)

    # --- 1, 12: frontmatter, and a README that declares an alias -----------------------------
    for f in (kind == :vault ? files : String[])
        fm, stop = frontmatter(texts[f])
        if stop == -1
            push!(findings, Finding(:error, "frontmatter", f, 1, "opens `---` and never closes it"))
            continue
        elseif stop == -2
            push!(findings, Finding(:error, "frontmatter", f, 1, "YAML block does not parse"))
            continue
        end

        # --- 2, 3, 4: declared dependencies --------------------------------------------------
        page_time = haskey(fm, "verified") ? tryparse(Date, string(fm["verified"])) : nothing
        if haskey(fm, "verified") && page_time === nothing
            push!(findings, Finding(:error, "frontmatter", f, 0,
                "`verified: $(fm["verified"])` is not a YYYY-MM-DD date"))
        end

        for dep in get(fm, "depends_on", [])
            dep isa Dict || (push!(findings, Finding(:error, "depends-on", f, 0,
                "`depends_on` entry is not a mapping: $dep")); continue)
            p = get(dep, "path", nothing)
            p === nothing && (push!(findings, Finding(:error, "depends-on", f, 0,
                "`depends_on` entry has no `path`")); continue)
            abs = resolve(string(p))
            if !ispath(abs)
                push!(findings, Finding(:error, "depends-on", f, 0, "`$p` does not exist"))
                continue
            end
            anchor = get(dep, "anchor", nothing)
            if anchor !== nothing && isfile(abs)
                occursin(string(anchor), read(abs, String)) ||
                    push!(findings, Finding(:error, "anchor", f, 0,
                        "`$p` no longer contains \"$anchor\""))
            end
            if page_time !== nothing && isfile(abs)
                Date(unix2datetime(mtime(abs))) > page_time &&
                    push!(findings, Finding(:warn, "stale", f, 0,
                        "`$p` changed after `verified: $page_time`"))
            end
        end

        # --- 5: cited checks -----------------------------------------------------------------
        for c in get(fm, "checks", [])
            isfile(resolve(string(c))) ||
                push!(findings, Finding(:error, "checks", f, 0, "`$c` does not exist"))
        end
    end

    # --- 6: wiki-links resolve ---------------------------------------------------------------
    #
    # Three outcomes, and only two of them are defects. This vault's own README says a link to a
    # page that does not exist yet is a **legitimate marker of something worth writing**, so that
    # case is a warning and never fails a commit. A link that resolves in the *other* vault is an
    # error: the page moved and the link did not. A link broken across a newline is an error too,
    # however well it reads — Obsidian does not join the lines.
    # A cross-vault link means different things on each side. Inside a vault it is an error: the
    # page moved and the link did not. From `Tasks/` or `Bibliography/` it is the normal way to
    # point at a claim, so it is only a warning — Obsidian will not follow it across vaults, and
    # that is worth saying once, not failing a commit over.
    inbound = Dict(f => 0 for f in files)
    for f in files, (ln, target, wrapped) in wiki_links(texts[f])
        here = get(names, target, nothing)
        if wrapped
            push!(findings, Finding(:error, "link-wrapped", f, ln,
                "[[$target]] is broken across a newline, so it resolves to nothing" *
                (here === nothing ? "" : " — the page exists")))
            here === nothing || here == f || (inbound[here] += 1)
        elseif here !== nothing
            here == f || (inbound[here] += 1)
        elseif haskey(elsewhere, target)
            push!(findings, Finding(kind == :vault ? :error : :warn, "link-crossvault", f, ln,
                "[[$target]] is in another vault, at `$(elsewhere[target])`" *
                (kind == :vault ? "" : " — Obsidian will not follow it from here")))
        else
            push!(findings, Finding(:warn, "link-unwritten", f, ln,
                "[[$target]] names no page — a marker, or a typo"))
        end
    end

    # --- 7: orphans --------------------------------------------------------------------------
    # Only in a vault. Nothing links to a task file, and that is not a defect.
    for f in (kind == :vault ? files : String[])
        basename(f) in ("README.md",) && continue
        inbound[f] == 0 && push!(findings, Finding(:warn, "orphan", f, 0, "no inbound link"))
    end

    # --- 8, 9: paths and line citations in prose ---------------------------------------------
    for f in files
        for (ln, raw) in prose_paths(texts[f])
            p = rstrip(raw, '/')
            m = match(r"^(.*?):(\d+)(?:[-–](\d+))?$", p)     # `file:12` and `file:12-25`
            if m !== nothing
                target = resolve(m.captures[1])
                n = parse(Int, something(m.captures[3], m.captures[2]))
                if !isfile(target)
                    push!(findings, Finding(:warn, "path", f, ln,
                        "`$(m.captures[1])` does not exist"))
                else
                    total = countlines(target)
                    total < n && push!(findings, Finding(:error, "line-citation", f, ln,
                        "`$p` names line $n; the file has $total"))
                end
            else
                ispath(resolve(p)) ||
                    push!(findings, Finding(:warn, "path", f, ln, "`$raw` does not exist"))
            end
        end
    end

    # --- 10: generated blocks ----------------------------------------------------------------
    for f in files, (i, line) in enumerate(split(texts[f], '\n'))
        m = match(GEN_OPEN_RE, line)
        m === nothing && continue
        push!(findings, Finding(:warn, "generated", f, i,
            "generated block `$(m.captures[1])` has no generator yet"))
    end

end

# --- 13: the Knowledge <-> Projects mirror ---------------------------------------------------

function lint_mirror(findings::Vector{Finding})
    k, p = joinpath(ROOT, "Knowledge"), joinpath(ROOT, "Projects")
    (isdir(k) && isdir(p)) || return
    # A dot-directory is never a topic: `.githooks`, `.obsidian`, `.claude` and friends.
    topics(d) = Set(nfc(x) for x in readdir(d)
                    if isdir(joinpath(d, x)) && !startswith(x, '.') && !(x in SKIP_DIRS))
    kt, pt = topics(k), topics(p)
    for t in sort(collect(setdiff(kt, pt)))
        push!(findings, Finding(:warn, "mirror", "Knowledge/$t", 0, "no `Projects/` counterpart"))
    end
    for t in sort(collect(setdiff(pt, kt)))
        push!(findings, Finding(:warn, "mirror", "Projects/$t", 0, "no `Knowledge/` counterpart"))
    end
end

# --- 14: the task board's schema -------------------------------------------------------------
#
# `Tasks/Board.base` groups task files by `status`. Obsidian has no enum property type, so a typo
# in `status` silently makes a phantom column, and this check is the only constraint on it. An
# unknown value and a file in the wrong folder for its status are errors; the rest are warnings,
# because the hook blocks on an error and a half-finished retrofit must not block a commit.
#
# `Tasks/Evidence/` holds the reports a plan rests on, one folder per plan. They are not task
# files, so this rule skips them; the path and line-citation checks still read them.

const TASK_STATUSES = ("wip", "next", "incoming", "backlog", "done")
const TASK_NOT_TASKS = ("README.md", "CLAUDE.md")

function lint_tasks(files, texts, findings::Vector{Finding})
    for f in files
        parts = splitpath(relpath(f, "Tasks"))
        basename(f) in TASK_NOT_TASKS && continue
        parts[1] == "Evidence" && continue
        archived = length(parts) == 2 && parts[1] == "Archive"
        (length(parts) == 1 || archived) ||
            (push!(findings, Finding(:error, "task-status", f, 0,
                 "task files live in `Tasks/` or `Tasks/Archive/` only")); continue)
        fm, stop = frontmatter(texts[f])
        stop < 0 && (push!(findings, Finding(:error, "task-status", f, 1,
                         "frontmatter does not close or does not parse")); continue)
        status = get(fm, "status", nothing)
        haskey(fm, "created") ||
            push!(findings, Finding(:warn, "task-status", f, 0, "no `created:`"))
        if status === nothing
            push!(findings, Finding(:warn, "task-status", f, 0, "no `status:`"))
            continue
        end
        status = string(status)
        if !(status in TASK_STATUSES)
            push!(findings, Finding(:error, "task-status", f, 0,
                "`status: $status` is not one of $(join(TASK_STATUSES, " | "))"))
            continue
        end
        archived == (status == "done") ||
            push!(findings, Finding(:error, "task-status", f, 0,
                archived ? "is in `Archive/` but `status: $status`" :
                "`status: done` belongs in `Archive/`"))
        status == "wip" && !haskey(fm, "started") &&
            push!(findings, Finding(:warn, "task-status", f, 0, "`status: wip` without `started:`"))
    end
end

# ---------------------------------------------------------------------------------------------

function main()
    strict = "--strict" in ARGS
    quiet = "--quiet" in ARGS
    named = filter(a -> !startswith(a, "--"), ARGS)
    vaults = isempty(named) ? [p.first for p in SCOPES] : named

    for v in vaults
        isdir(joinpath(ROOT, v)) || (println(stderr, "no such vault: $v"); exit(2))
    end

    files = Dict(v => markdown_files(v) for v in vaults)
    texts = Dict(v => Dict(f => read(joinpath(ROOT, f), String) for f in files[v]) for v in vaults)
    names = Dict(v => vault_names(v, files[v], texts[v]) for v in vaults)

    findings = Finding[]
    for v in vaults
        # A link is resolved against every *vault* but this one. A reference tree holds no pages
        # to link to, so including its names would make a stray `[[…]]` resolve to a task file.
        elsewhere = Dict{String,String}()
        for w in vaults
            (w == v || kind_of(w) != :vault) && continue
            merge!(elsewhere, names[w])
        end
        lint_scope(v, kind_of(v), files[v], texts[v], names[v], elsewhere, findings)
    end
    ("Knowledge" in vaults) && lint_mirror(findings)
    ("Tasks" in vaults) && lint_tasks(files["Tasks"], texts["Tasks"], findings)

    sort!(findings, by = f -> (f.severity == :error ? 0 : 1, f.check, f.file, f.line))

    errors = count(f -> f.severity == :error, findings)
    warns = length(findings) - errors

    by_check = Dict{Tuple{Symbol,String},Int}()
    for f in findings
        by_check[(f.severity, f.check)] = get(by_check, (f.severity, f.check), 0) + 1
    end

    if !quiet || errors > 0
        for f in findings
            f.severity == :warn && quiet && continue
            where = f.line == 0 ? f.file : "$(f.file):$(f.line)"
            println("$(uppercase(string(f.severity)))  [$(f.check)]  $where — $(f.message)")
        end
        isempty(findings) || println()
    end

    println("by check:")
    for ((sev, check), n) in sort(collect(by_check), by = x -> (-x[2], x[1][2]))
        println("  $(rpad(check, 16)) $(rpad(string(sev), 6)) $n")
    end
    println()
    println("$errors error(s), $warns warning(s) over $(join(vaults, ", ")).")

    failing = strict ? length(findings) : errors
    exit(failing == 0 ? 0 : 1)
end

main()
