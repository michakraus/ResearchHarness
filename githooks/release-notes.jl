#!/usr/bin/env julia
#
# Build the `@JuliaRegistrator` comment body from a package's CHANGELOG, and refuse to build one
# for a breaking release whose notes have no breaking-changes section.
#
#   julia --startup-file=no release-notes.jl [package-dir] > notes.json
#   gh api repos/<owner>/<repo>/commits/<SHA>/comments --input notes.json
#
# package-dir defaults to the working directory. JSON goes to stdout; every failure goes to stderr
# with exit 1 and *nothing* on stdout, so a failed run cannot leave a half-built notes.json behind.
#
# WHY THIS EXISTS.
#
#   1. RegistryCI's guideline_breaking_explanation matches the registry PR body's
#      <!-- BEGIN RELEASE NOTES --> block against /breaking|changelog/i. A breaking release
#      registered without notes is blocked by AutoMerge, and by then the PR body is already
#      written — the notes have to be right in the first comment. This script is the check.
#   2. `gh api -F body=@file` mangles multi-line bodies, so the JSON has to be assembled anyway.
#      Assembling it by hand each release is what let the notes be forgotten.
#
# The version comes from Project.toml rather than an argument: the release commit is what defines
# the release. That also catches a close-out that was never done — if the CHANGELOG has no section
# for that version, there are no notes to post, and the script says so.

const VERSION_HEADING = r"^##[ \t]+\[?v?(\d+)\.(\d+)\.(\d+)\]?[ \t]*(?:[-–—].*)?$"
# `m` is load-bearing: this one is tested with `occursin` against the whole section, and without
# it `^` anchors to the start of that string rather than to each line. The check then passes only
# when the breaking heading is the section's very first line — which the house shape in
# `Packages/CLAUDE.md` never produces, since it puts `### New Features` first.
const BREAKING_HEADING = r"^#{2,6}[ \t].*breaking"im

fail(msg::AbstractString) = (println(stderr, "release-notes: ", msg); exit(1))

"Version from Project.toml, as (major, minor, patch) and the string it was written as."
function project_version(dir::AbstractString)
    path = joinpath(dir, "Project.toml")
    isfile(path) || fail("no Project.toml in $dir")
    for line in eachline(path)
        m = match(r"^[ \t]*version[ \t]*=[ \t]*\"([^\"]+)\"", line)
        m === nothing && continue
        v = m.captures[1]
        n = match(r"^(\d+)\.(\d+)\.(\d+)$", v)
        n === nothing && fail("version \"$v\" in $path is not X.Y.Z")
        return (parse.(Int, n.captures)...,), v
    end
    fail("no version entry in $path")
end

"""
Lines of the section for `version`, plus the version heading that follows it, if any.

The section runs to the next `## ` heading of any kind, so `## Open Issues` terminates it the same
way the previous release does.
"""
function changelog_section(dir::AbstractString, version::AbstractString)
    path = joinpath(dir, "CHANGELOG.md")
    isfile(path) || fail("no CHANGELOG.md in $dir")
    lines = readlines(path)

    start = findfirst(lines) do line
        m = match(VERSION_HEADING, line)
        m !== nothing && join(m.captures, ".") == version
    end
    start === nothing && fail("""
        CHANGELOG.md has no section for $version.
        Close out `## [Unreleased]` into `## $version` before registering — the notes in that
        section are the notes the Registrator comment carries.""")

    stop = findnext(line -> startswith(line, "## "), lines, start + 1)
    body = lines[(start + 1):(stop === nothing ? length(lines) : stop - 1)]

    previous = nothing
    if stop !== nothing
        i = findnext(line -> match(VERSION_HEADING, line) !== nothing, lines, stop)
        i === nothing || (previous = (parse.(Int, match(VERSION_HEADING, lines[i]).captures)...,))
    end
    return body, previous
end

"""
Whether registering this version is a breaking change, in the sense Registrator labels BREAKING.

A release with no previous version in the CHANGELOG is a first registration: there is nothing
released for it to break, so it is never breaking — 0.1.0 and 1.0.0 as a package's first version
are the common cases, and the version-only rule below would otherwise call both of them breaking.

Otherwise, from the version alone: every 0.0.z release, a 0.y.0 minor bump, and an x.0.0 major
bump. The previous heading then widens that verdict when a version number was burned and the bump
skipped the .0 — a 0.17.3 → 0.18.2 jump is breaking even though the patch is not zero.

The first-registration test is "no older version heading in this CHANGELOG", which a seeded
CHANGELOG whose earlier releases are an unwritten gap also satisfies. Such a package gets notes
with no breaking section and AutoMerge blocks the registry PR, which is the loud failure — write
the gap's versions in as headings, or add the section by hand, rather than working around it.
"""
function breaking(version::NTuple{3,Int}, previous::Union{Nothing,NTuple{3,Int}})
    previous === nothing && return false
    major, minor, patch = version
    base = major == 0 ? (minor == 0 || patch == 0) : (minor == 0 && patch == 0)
    base && return true
    return major == 0 ? (previous[1], previous[2]) != (major, minor) : previous[1] != major
end

"Section text as release notes: subsection headings rise one level, blank edges trimmed."
function notes(body::Vector{String})
    promoted = map(line -> replace(line, r"^#(#{2,})" => s"\1"), body)
    from = findfirst(!isempty ∘ strip, promoted)
    from === nothing && return ""
    to = findlast(!isempty ∘ strip, promoted)
    return join(promoted[from:to], "\n")
end

function json_string(s::AbstractString)
    io = IOBuffer()
    print(io, '"')
    for c in s
        if c == '"'
            print(io, "\\\"")
        elseif c == '\\'
            print(io, "\\\\")
        elseif c == '\n'
            print(io, "\\n")
        elseif c == '\r'
            print(io, "\\r")
        elseif c == '\t'
            print(io, "\\t")
        elseif c < '\x20'
            print(io, "\\u", string(UInt16(c); base = 16, pad = 4))
        else
            print(io, c)
        end
    end
    print(io, '"')
    return String(take!(io))
end

function main(args)
    length(args) <= 1 || fail("usage: release-notes.jl [package-dir]")
    dir = isempty(args) ? pwd() : args[1]
    isdir(dir) || fail("not a directory: $dir")

    version, written = project_version(dir)
    body, previous = changelog_section(dir, written)
    text = notes(body)
    isempty(text) && fail("the `## $written` section in CHANGELOG.md is empty — nothing to post")

    if breaking(version, previous)
        occursin(BREAKING_HEADING, text) || fail("""
            $written is a breaking release and its CHANGELOG section has no breaking-changes
            heading. Add a `### Breaking Changes` subsection saying what broke and what a caller
            should do about it, then run this again.
            Without it Registrator labels the registry PR BREAKING, RegistryCI's
            guideline_breaking_explanation finds no match for /breaking|changelog/i, and AutoMerge
            blocks the release.""")
        println(stderr, "release-notes: $written is breaking; breaking-changes section present.")
    else
        println(stderr, "release-notes: $written is not a breaking release.")
    end

    println(stdout, "{\"body\": ", json_string("@JuliaRegistrator register\n\nRelease notes:\n\n" * text), "}")
end

main(ARGS)
