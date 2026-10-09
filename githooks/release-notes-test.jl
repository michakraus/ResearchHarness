#!/usr/bin/env julia
#
# Checks for release-notes.jl. Companion to it; run after any change to it.
#
#   julia --startup-file=no release-notes-test.jl
#
# Exits non-zero if any case fails. The cases that matter most are the two that must FAIL: a
# breaking release whose CHANGELOG section has no breaking-changes heading, and a version that was
# never closed out. Both must exit 1 with empty stdout, because the caller redirects stdout into
# notes.json — a script that emitted a partial body on failure would post it.
#
# Fixtures are built in a temporary directory. The first testset carries one changelog per version
# heading shape that package changelogs use: bare, v-prefixed, and bracketed with a date after a
# hyphen or an em-dash.

using Test

const SCRIPT = joinpath(@__DIR__, "release-notes.jl")

"Run the script on a fixture with the given version and CHANGELOG text; return (code, stdout)."
function run_on(version::AbstractString, changelog::AbstractString)
    dir = mktempdir()
    write(joinpath(dir, "Project.toml"), "name = \"Fixture\"\nversion = \"$version\"\n")
    write(joinpath(dir, "CHANGELOG.md"), changelog)
    out = IOBuffer()
    code = run(pipeline(ignorestatus(`$(Base.julia_cmd()) --startup-file=no $SCRIPT $dir`);
                        stdout = out, stderr = devnull)).exitcode
    return code, String(take!(out))
end

"A changelog with one heading shape: `heading(v)` is the heading line of version `v`."
shaped_changelog(heading, title = "Changelog") = """
    # $title

    ## [Unreleased] — targeting 9.9.9

    ### Documentation

    * Pending.

    $(heading("0.18.1"))

    ### Fixes

    * A patch.

    $(heading("0.18.0"))

    ### Breaking Changes

    * `foo` was renamed to `bar`.

    ### New Features

    * Something additive.

    $(heading("0.17.3"))

    ### Fixes

    * Something else.
    """

"The `body` field of the emitted JSON, decoded far enough to compare against source text."
function decode_body(json::AbstractString)
    m = match(r"^\{\"body\": \"(.*)\"\}\n?$"s, json)
    m === nothing && error("output is not the expected {\"body\": ...} shape")
    s = m.captures[1]
    for (esc, chr) in ("\\n" => "\n", "\\r" => "\r", "\\t" => "\t", "\\\"" => "\"", "\\\\" => "\\")
        s = replace(s, esc => chr)
    end
    return s
end

@testset "release-notes.jl" begin
    @testset "heading shapes found in the packages" begin
        bare = shaped_changelog(v -> "## $v", "Release Notes")

        # `## 0.18.0` — bare, and a breaking 0.y.0 bump.
        code, out = run_on("0.18.0", bare)
        @test code == 0
        @test occursin(r"^#{2,6}[ \t].*breaking"im, decode_body(out))

        # `## 0.18.1` — same file, a patch release, so no breaking section is required.
        code, out = run_on("0.18.1", bare)
        @test code == 0

        # `## [0.18.1] - 2026-08-10` — bracketed and dated.
        code, out = run_on("0.18.1", shaped_changelog(v -> "## [$v] - 2026-08-10"))
        @test code == 0
        @test !isempty(out)

        # `## v0.18.1` — v-prefixed.
        code, out = run_on("0.18.1", shaped_changelog(v -> "## v$v"))
        @test code == 0
        @test !isempty(out)

        # `## [0.18.1] — 2026-09-02` — bracketed and dated with an em-dash.
        code, out = run_on("0.18.1", shaped_changelog(v -> "## [$v] — 2026-09-02", "Release Notes"))
        @test code == 0
        @test !isempty(out)
    end

    @testset "a breaking release with no breaking section is refused" begin
        changelog = """
        # Release Notes

        ## 0.9.0

        ### New Features

        * Something additive.

        ## 0.8.4

        ### Fixes

        * Something else.
        """
        code, out = run_on("0.9.0", changelog)
        @test code == 1
        @test isempty(out)

        # The same notes, with the section present, are accepted.
        with_section = replace(changelog, "### New Features" => "### Breaking Changes"; count = 1)
        code, out = run_on("0.9.0", with_section)
        @test code == 0
        @test !isempty(out)
    end

    @testset "a burned version number is still breaking" begin
        # 0.17.3 → 0.18.2 skips the .0, so the version alone does not look breaking.
        changelog = """
        # Release Notes

        ## 0.18.2

        ### New Features

        * Something additive.

        ## 0.17.3

        ### Fixes

        * Something else.
        """
        code, out = run_on("0.18.2", changelog)
        @test code == 1
        @test isempty(out)
    end

    @testset "a minor bump at or above 1.0 is not breaking" begin
        changelog = "# Release Notes\n\n## 1.2.0\n\n### New Features\n\n* Additive.\n\n## 1.1.4\n\n* Fix.\n"
        code, out = run_on("1.2.0", changelog)
        @test code == 0
        @test !isempty(out)
    end

    @testset "a first release is not breaking" begin
        # No previous version heading means nothing is released for this to break, so 0.1.0 and
        # 1.0.0 — which the version-only rule would both call breaking — need no such section.
        for version in ("0.1.0", "1.0.0")
            changelog = "# Release Notes\n\n## $version\n\n### New Features\n\n* The first implementation.\n\n## Open Issues\n\n* Nothing yet.\n"
            code, out = run_on(version, changelog)
            @test code == 0
            @test !isempty(out)
            @test !occursin(r"breaking"i, decode_body(out))
        end

        # The guard: the same 0.y.0 bump with a previous version present is still refused, so this
        # is a first-release exemption rather than the breaking check being switched off.
        changelog = "# Release Notes\n\n## 0.1.0\n\n### New Features\n\n* Additive.\n\n## 0.0.5\n\n* Fix.\n"
        code, out = run_on("0.1.0", changelog)
        @test code == 1
        @test isempty(out)
    end

    @testset "a version that was never closed out is refused" begin
        changelog = "# Release Notes\n\n## [Unreleased] — targeting 0.5.0\n\n## 0.4.2\n\n* Fix.\n"
        code, out = run_on("0.5.0", changelog)
        @test code == 1
        @test isempty(out)
    end

    @testset "the body is the section, promoted, under the Registrator preamble" begin
        changelog = """
        # Release Notes

        ## 0.9.0

        ### Breaking Changes

        * `foo` was renamed to `bar`.

        #### Detail

        * A nested point.

        ## Open Issues

        * Not part of the notes.
        """
        code, out = run_on("0.9.0", changelog)
        @test code == 0
        body = decode_body(out)
        @test startswith(body, "@JuliaRegistrator register\n\nRelease notes:\n\n")
        @test occursin("## Breaking Changes", body)      # promoted from ###
        @test occursin("### Detail", body)               # promoted from ####
        @test occursin("`foo` was renamed to `bar`.", body)
        @test !occursin("Open Issues", body)             # the next ## heading terminates it
        @test !occursin("Not part of the notes", body)
        @test !endswith(body, "\n")                      # blank edges trimmed
    end

    @testset "quotes and backslashes survive JSON encoding" begin
        changelog = "# Release Notes\n\n## 0.1.1\n\n* A \"quoted\" phrase and a backslash \\\\ in prose.\n"
        code, out = run_on("0.1.1", changelog)
        @test code == 0
        @test occursin("A \"quoted\" phrase and a backslash \\\\ in prose.", decode_body(out))
    end
end
