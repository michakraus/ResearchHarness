#!/usr/bin/env julia
#
# Checks for test-layout.jl. Companion to it; run after any change to it.
#
#   julia --startup-file=no test-layout-test.jl
#
# A fixture repository in the form of the convention must pass with exit 0 and no output. Each
# mutation of it breaks one rule and must exit 1 with a line that names exactly that rule.

using Test

const SCRIPT = joinpath(@__DIR__, "test-layout.jl")

const RUNTESTS = """
using SafeTestsets

const GROUPS = isempty(ARGS) ? ["core", "slow"] : ARGS

if "core" in GROUPS
    @safetestset "Aqua" include("quality/aqua.jl")
    @safetestset "Options" include("base/options.jl")
    @safetestset "Whole package" include("integration/solve.jl")
end
if "doctests" in GROUPS
    @safetestset "Doctests" include("quality/doctests.jl")
end
if "broken" in GROUPS
    @safetestset "Old API" include("base/old_api.jl")   # issue #12
end
"""

const ROOT_PROJECT = """
name = "Fixture"
uuid = "01234567-89ab-cdef-0123-456789abcdef"

[deps]
Shared = "11111111-1111-1111-1111-111111111111"

[weakdeps]
Weak = "22222222-2222-2222-2222-222222222222"

[compat]
Shared = "1.2"
Weak = "0.3"
"""

const TEST_PROJECT = """
[deps]
SafeTestsets = "1bc83da4-3b8d-516f-aca4-4fe02f6d838f"
Shared = "11111111-1111-1111-1111-111111111111"
TestOnly = "33333333-3333-3333-3333-333333333333"
Weak = "22222222-2222-2222-2222-222222222222"

[compat]
"""

const DOCS_PROJECT = """
[deps]
Documenter = "e30172f5-a6a5-5a46-863b-614d45cd2de4"
Fixture = "01234567-89ab-cdef-0123-456789abcdef"

[compat]
Documenter = "1"
"""

const FILES = Dict(
    "Project.toml" => ROOT_PROJECT,
    "src/Fixture.jl" => "module Fixture\n\"\"\"\n```jldoctest\njulia> 1\n1\n```\n\"\"\"\nf() = 1\nend\n",
    "src/base/options.jl" => "g() = 2\n",
    "test/Project.toml" => TEST_PROJECT,
    "test/runtests.jl" => RUNTESTS,
    "test/quality/aqua.jl" => "using Aqua, Fixture\nAqua.test_all(Fixture)\n",
    "test/quality/doctests.jl" => "using Documenter, Fixture\ndoctest(Fixture; manual = false)\n",
    "test/base/options.jl" => "using Test, Random, Fixture\nRandom.seed!(1)\ninclude(\"../helpers/data.jl\")\n@test rand() < 2\n",
    "test/base/old_api.jl" => "using Test, Fixture\n@test_broken Fixture.h() == 1   # issue #12\n",
    "test/integration/solve.jl" => "using Test, Fixture\n@test Fixture.f() == 1\n",
    "test/helpers/data.jl" => "data() = 1\n"
)

const Changes = Dict{String, Union{String, Nothing}}

"Write the fixture with `changes` applied (`nothing` deletes a file) and return its directory."
function fixture(changes = Changes())
    dir = mktempdir()
    for (path, text) in merge(Changes(FILES), changes)
        text === nothing && continue
        mkpath(dirname(joinpath(dir, path)))
        write(joinpath(dir, path), text)
    end
    return dir
end

"Run `test-layout.jl --check` on a directory; return (exit code, stdout lines)."
function check(dir)
    out = IOBuffer()
    code = run(pipeline(
        ignorestatus(`$(Base.julia_cmd()) --startup-file=no $SCRIPT --check $dir`);
        stdout = out, stderr = devnull)).exitcode
    return code, filter(!isempty, split(String(take!(out)), '\n'))
end

"The runtests.jl of the fixture with each `from => to` applied; each `from` must occur in it."
function rt(pairs...)
    for p in pairs
        occursin(first(p), RUNTESTS) || error("not in RUNTESTS: $(repr(first(p)))")
    end
    Changes("test/runtests.jl" => replace(RUNTESTS, pairs...))
end

const DOCTESTS_SLOW = "if \"slow\" in GROUPS\n    @safetestset \"Doctests\" include(\"quality/doctests.jl\")\nend\n"
const AQUA_LINE = "    @safetestset \"Aqua\" include(\"quality/aqua.jl\")\n"
const DOCTESTS_GROUP = "if \"doctests\" in GROUPS\n    @safetestset \"Doctests\" include(\"quality/doctests.jl\")\nend\n"
const OTHER_IN_DOCTESTS = "if \"doctests\" in GROUPS\n    @safetestset \"Other\" include(\"base/other.jl\")\nend\n"
# test/quality/doctests.jl in the group `core`
const DOCTESTS_IN_CORE = rt(DOCTESTS_GROUP => "",
    AQUA_LINE =>
        AQUA_LINE * "    @safetestset \"Doctests\" include(\"quality/doctests.jl\")\n")
# test/top.jl, listed in `core`
const TOP_LISTED = merge(
    rt(AQUA_LINE => AQUA_LINE * "    @safetestset \"Top\" include(\"top.jl\")\n"),
    Changes("test/top.jl" => "using Test, Fixture\n@test Fixture.f() == 1\n"))

@testset "a repository in form passes" begin
    code, lines = check(fixture())
    @test code == 0
    @test isempty(lines)
end

"test/base/options.jl of the fixture, drawing with `draw` and no seed."
function unseeded(draw)
    Changes("test/base/options.jl" => "using Test, Random, Fixture\ninclude(\"../helpers/data.jl\")\n@test length($draw) > 0\n")
end

"test/quality/aqua.jl of the fixture, with `body` as the keywords of `Aqua.test_all`."
function aqua(body)
    Changes("test/quality/aqua.jl" => "using Aqua, Fixture\nAqua.test_all(Fixture; $body)\n")
end

"The test/Project.toml of the fixture with each `from => to` applied."
tp(pairs...) = Changes("test/Project.toml" => replace(TEST_PROJECT, pairs...))

# rule tag => the mutation that breaks that rule alone, sorted by rule tag
const MUTATIONS = [
    "D1" => Changes("test/Project.toml" => nothing),
    "D1" => Changes("Project.toml" =>
        FILES["Project.toml"] * "\n[targets]\ntest = [\"Test\"]\n"),
    "D1" => Changes("Project.toml" =>
        FILES["Project.toml"] * "\n  [targets]\n  test = [\"Test\"]\n"),
    "D1" => Changes("Project.toml" =>
        FILES["Project.toml"] *
        "\n[extras]\nTest = \"8dfed614-e22c-5e08-85e1-65c5234f0b40\"\n"),
    "D1" => Changes("Project.toml" => nothing),
    "D2" => rt("using SafeTestsets\n" => "using SafeTestsets, Test\n@test 1 == 1\n"),
    "D2" =>
        rt("    @safetestset \"Options\" include(\"base/options.jl\")" => "    @testset \"Options\" begin include(\"base/options.jl\") end"),
    "D2" => rt("using SafeTestsets\n" => ""),
    "D2" =>
        rt("    @safetestset \"Whole package\" include(\"integration/solve.jl\")" => "    include(\"integration/solve.jl\")"),
    "D2" => merge(
        rt("    @safetestset \"Whole package\" include(\"integration/solve.jl\")" => "    @safetestset \"Whole package\" include(\"integration/runtests.jl\")"),
        Changes("test/integration/solve.jl" => nothing,
            "test/integration/runtests.jl" => "using Test, Fixture\n@test Fixture.f() == 1\n")),
    "D2" => rt("end\nif \"doctests\" in GROUPS" => "else\nend\nif \"doctests\" in GROUPS"),
    "D2" =>
        rt("if \"broken\" in GROUPS" => "if \"core\" in GROUPS\nend\nif \"broken\" in GROUPS"),
    "D2" => rt("using SafeTestsets\n" => "using SafeTestsets\nusing SafeTestsets\n"),
    "D3" => merge(
        Changes("test/base/options.jl" => nothing,
            "test/solvers/options.jl" => FILES["test/base/options.jl"]),
        rt("base/options.jl" => "solvers/options.jl")),
    # a listed file at the top level of test/ with no src/<name>.jl
    "D3" => TOP_LISTED,
    "D4" => merge(Changes("test/quality/aqua.jl" => nothing), rt(AQUA_LINE => "")),
    "D5" => rt("\"core\", \"slow\"]" => "\"core\"]"),
    "D5" => rt("if \"broken\" in GROUPS" => "if \"extra\" in GROUPS"),
    "D5" =>
        Changes("test/integration/solve.jl" => "using Test, Fixture\nif haskey(ENV, \"CI\")\n    @test Fixture.f() == 1\nend\n"),
    "D5" => rt("const GROUPS = isempty(ARGS) ? [\"core\", \"slow\"] : ARGS\n" => ""),
    "D5" =>
        rt("const GROUPS = isempty(ARGS) ? [\"core\", \"slow\"] : ARGS\n" => "const GROUPS = isempty(ARGS) ? [\"core\", \"slow\"] : ARGS\nconst GROUPS = isempty(ARGS) ? [\"core\", \"slow\"] : ARGS\n"),
    "D5" =>
        Changes("test/integration/solve.jl" => "using Test, Fixture\nfor g in ARGS\n    @test Fixture.f() == 1\nend\n"),
    "D5" =>
        Changes("test/integration/solve.jl" => "using Test, Fixture\n@test Fixture.f() == 1 skip = haskey(ENV, \"CI\")   # issue #3\n"),
    "D7" =>
        Changes("test/base/old_api.jl" => "using Test, Fixture\n@test_broken Fixture.h() == 1\n"),
    "D7" =>
        Changes("test/base/old_api.jl" => "using Test, Fixture\nTest.@test_broken Fixture.h() == 1\n"),
    "D7" =>
        Changes("test/base/old_api.jl" => "using Test, Fixture\n@test Fixture.h() == 1 broken = true\n"),
    "D7" =>
        Changes("test/base/old_api.jl" => "using Test, Fixture\n@test Fixture.h() == 1 skip = true\n"),
    "D7" =>
        Changes("test/base/old_api.jl" => "using Test, Fixture\n@test_skip Fixture.h() == 1\n"),
    "D7" => aqua("deps_compat = (; broken = true)"),
    "D7" => aqua("piracies = (broken = true,)"),
    "D7" =>
        aqua("\n    ambiguities = false,   # issue #3\n    piracies = (; broken = true)"),
    "D8" => Changes("test/base/unlisted.jl" => "using Test\n@test true\n"),
    "D8" =>
        rt("    @safetestset \"Whole package\"" => "    @safetestset \"Again\" include(\"base/options.jl\")\n    @safetestset \"Whole package\""),
    "D8" =>
        rt("    @safetestset \"Whole package\"" => "    @safetestset \"Missing\" include(\"base/missing.jl\")\n    @safetestset \"Whole package\""),
    "D8" =>
        rt("    @safetestset \"Whole package\"" => "    @safetestset \"Helper\" include(\"helpers/data.jl\")\n    @safetestset \"Whole package\""),
    "D8" => Changes("test/base/runtests.jl" => "using Test\n@test true\n"),
    "D9" => merge(Changes("test/quality/doctests.jl" => nothing), rt(DOCTESTS_GROUP => "")),
    "D9" => DOCTESTS_IN_CORE,
    # test/quality/doctests.jl in the group `slow`
    "D9" => rt(DOCTESTS_GROUP => DOCTESTS_SLOW),
    "D9" => merge(
        Changes("test/quality/doctests.jl" => nothing,
            "src/Fixture.jl" => "module Fixture\nf() = 1\nend\n",
            "docs/src/index.md" => "```jldoctest\njulia> 1\n1\n```\n"),
        rt(DOCTESTS_GROUP => "")),
    # the group `doctests` holds test/quality/doctests.jl and no other file
    "D9" => merge(rt(DOCTESTS_GROUP => DOCTESTS_SLOW * OTHER_IN_DOCTESTS),
        Changes("test/base/other.jl" => "using Test, Fixture\n@test Fixture.f() == 1\n")),
    "D9" => merge(
        rt(DOCTESTS_GROUP => replace(DOCTESTS_GROUP,
            "end\n" => "    @safetestset \"Other\" include(\"base/other.jl\")\nend\n")),
        Changes("test/base/other.jl" => "using Test, Fixture\n@test Fixture.f() == 1\n")),
    "D10" => rt("   # issue #12" => ""),
    "compat" => tp("[compat]\n" => "[compat]\nShared = \"1.2\"\n"),
    "compat" => tp("[compat]\n" => "[compat]\nShared = \"1.3\"\n"),
    "compat" => tp("[compat]\n" => "[compat]\nWeak = \"0.3\"\n"),
    "compat" => tp("Shared = \"11111111-1111-1111-1111-111111111111\"\n" => "",
        "[compat]\n" => "[compat]\nShared = \"1.2\"\n"),
    "compat" => Changes("docs/Project.toml" =>
        replace(DOCS_PROJECT, "[compat]\n" => "[compat]\nShared = \"1.2\"\n")),
    "label" => rt("\"Whole package\"" => "\"Options\""),
    "label" => rt("\"Whole package\"" => "\"Whole \$(1) package\""),
    "seed" =>
        Changes("test/base/options.jl" => "using Test, Fixture\ninclude(\"../helpers/data.jl\")\n@test rand() < 2\n"),
    "seed" =>
        Changes("test/base/options.jl" => "using Test, Random, Fixture\ninclude(\"../helpers/data.jl\")\n@test Random.rand() < 2\n"),
    "seed" =>
        Changes("test/base/options.jl" => "using Test, Random, Fixture\n# Random.seed!(1) is not called\ninclude(\"../helpers/data.jl\")\n@test rand() < 2\n"),
    "seed" => unseeded("rand.(1:3)"),
    "seed" => unseeded("Random.rand.(1:3)"),
    "seed" => unseeded("bitrand(3)"),
    "seed" => unseeded("sprand(3, 3, 0.5)"),
    "seed" => unseeded("randstring(3)"),
    "using" => Changes("test/integration/solve.jl" => "@test 1 == 1\n")
]

"The rule tags in their order: D1 to D10 by number, then the named rules by name."
tagkey(t) = startswith(t, "D") ? (0, parse(Int, t[2:end]), "") : (1, 0, t)

@testset "MUTATIONS is sorted by rule tag" begin
    @test issorted(first.(MUTATIONS); by = tagkey)
end

@testset "what is no violation" for change in (
# a test-only dependency with no bound, and one with a bound (M5/M1 keep those)
    tp("[compat]\n" => "[compat]\nTestOnly = \"2\"\n"),
# a docs-only dependency with a bound
    Changes("docs/Project.toml" => DOCS_PROJECT),
# a shared dependency that test/Project.toml does not list
    tp("Weak = \"22222222-2222-2222-2222-222222222222\"\n" => ""),
# a listed file at the top level of test/ that mirrors src/<name>.jl (D3)
    merge(TOP_LISTED, Changes("src/top.jl" => "t() = 1\n")),
# a listed file at the top level of test/ in a repository with no src/ (D3)
    merge(TOP_LISTED,
    Changes("src/Fixture.jl" => nothing, "src/base/options.jl" => nothing)),
# a `broken` mark with its issue on its line
    Changes("test/base/old_api.jl" => "using Test, Fixture\n@test Fixture.h() == 1 broken = true   # issue #12\n@test_skip Fixture.h() == 1   # issue #12\n"),
    aqua("\n    piracies = (; broken = true),   # issue #3\n    ambiguities = false"),
    aqua("piracies = (; broken = false)"),
# `broken = false` beside a marked line
    aqua("\n    piracies = (; broken = true),   # issue #3\n    ambiguities = (; broken = false)"),
# a seeded draw by broadcast
    Changes("test/base/options.jl" => "using Test, Random, Fixture\nRandom.seed!(1)\ninclude(\"../helpers/data.jl\")\n@test length(rand.(1:3)) == 3\n"),
# a separate suite: an environment below its top directory, and a runner that reads ARGS, that
# mirrors no source directory, that no runtests.jl lists, and that has no issue on a `@test_skip`
    Changes("test/gpu/metal/Project.toml" => "[deps]\n",
        "test/gpu/runtests.jl" => "using Test\nfor b in ARGS\n    @test_skip b == \"metal\"\nend\n"),
# an environment for a workflow, with no test file (`test/symbolic/`)
    Changes("test/symbolic/Project.toml" => "[deps]\n"))
    code, lines = check(fixture(change))
    @test code == 0
    @test isempty(lines)
end

@testset "a directory is a separate suite only with an environment and no listed file" begin
    runner = "using Test\nfor b in ARGS\n    @test b == \"metal\"\nend\n"
    # without its environment, the device runner is a file of the suite, and breaks three rules
    code, lines = check(fixture(Changes("test/gpu/runtests.jl" => runner)))
    @test code == 1
    @test sort([match(r"\[(\w+)\]", l).captures[1] for l in lines]) == ["D3", "D5", "D8"]
    # a listed file keeps its directory under every rule, whatever environment it holds
    dir = fixture(merge(
        rt(AQUA_LINE => AQUA_LINE * "    @safetestset \"Symbolic\" include(\"symbolic/x.jl\")\n"),
        Changes("test/symbolic/Project.toml" => "[deps]\n",
            "test/symbolic/x.jl" => "using Test, Fixture\nif haskey(ENV, \"CI\")\n    @test Fixture.f() == 1\nend\n")))
    code, lines = check(dir)
    @test code == 1
    @test any(l -> occursin("[D5] symbolic/x.jl", l), lines)
    @test any(l -> occursin("[D3] symbolic/x.jl", l), lines)
end

@testset "`broken` in a nested runtests.jl reads the issue from that file" begin
    nested(issue) = "using SafeTestsets\n" * "\n"^40 *
                    "if \"broken\" in GROUPS\n    @safetestset \"N\" include(\"x.jl\")$issue\nend\n"
    for (issue, expected) in (("   # issue #3", 0), ("", 1))
        dir = fixture(merge(
            rt("    @safetestset \"Whole package\" include(\"integration/solve.jl\")" => "    @safetestset \"Whole package\" include(\"integration/runtests.jl\")"),
            Changes("test/integration/solve.jl" => nothing,
                "test/integration/runtests.jl" => nested(issue),
                "test/integration/x.jl" => "using Test\n@test true\n")))
        code, lines = check(dir)
        @test code == 1                 # the nested runtests.jl is a D2 violation
        @test count(l -> occursin("[D10]", l), lines) == expected
    end
end

# The example of the convention itself, verbatim, with its files
const EXAMPLE = """
using SafeTestsets

const GROUPS = isempty(ARGS) ? (Sys.isapple() && Sys.ARCH === :aarch64 ? ["core", "slow", "metal"] : ["core", "slow"]) : ARGS

if "core" in GROUPS
    @safetestset "Aqua" include("quality/aqua.jl")
    @safetestset "JET" include("quality/jet.jl")
    @safetestset "Options" include("base/options.jl")          # tests src/base/options.jl
    @safetestset "Line searches" include("globalization/linesearch.jl")
end
if "slow" in GROUPS
    @safetestset "Convergence of the RK methods" include("verification/rk_convergence.jl")
end
if "doctests" in GROUPS
    @safetestset "Doctests" include("quality/doctests.jl")
end
if "metal" in GROUPS
    @safetestset "Metal" include("devices/metal.jl")
end
if "broken" in GROUPS
    @safetestset "Old multisymplectic API" include("integrators/old_api.jl")   # issue #NN
end
"""

@testset "the example of the convention passes" begin
    plain = "using Test, Fixture\n@test Fixture.f() == 1\n"
    code, lines = check(fixture(Changes(
        "test/runtests.jl" => replace(EXAMPLE, "#NN" => "#12"),
        "test/base/old_api.jl" => nothing, "test/integration/solve.jl" => nothing,
        "src/globalization/linesearch.jl" => "l() = 1\n", "src/integrators/old.jl" => "o() = 1\n",
        "test/quality/jet.jl" => plain, "test/globalization/linesearch.jl" => plain,
        "test/verification/rk_convergence.jl" => plain, "test/devices/metal.jl" => plain,
        "test/integrators/old_api.jl" => plain)))
    @test code == 0
    @test isempty(lines)
end

@testset "`@test_broken` in a comment is no violation" begin
    code,
    lines = check(fixture(Changes("test/integration/solve.jl" => "using Test, Fixture\n# @test_broken is not used here\n@test Fixture.f() == 1\n")))
    @test code == 0
    @test isempty(lines)
end

@testset "a statement outside the convention is named by its line, not its path" begin
    code,
    lines = check(fixture(rt("using SafeTestsets\n" => "using SafeTestsets\n@testset \"inline\" begin end\n")))
    @test code == 1
    @test length(lines) == 1
    @test occursin("runtests.jl:2: @testset", lines[1])
    @test !occursin("#=", lines[1])
end

@testset "a path with a trailing slash keeps the repository name" begin
    dir = fixture(Changes("test/Project.toml" => nothing))
    code, lines = check(dir * "/")
    @test code == 1
    @test lines == ["$(basename(dir)): [D1] test/Project.toml does not exist"]
end

@testset "a `@testset` in a group gives one line, not two" begin
    code,
    lines = check(fixture(rt("    @safetestset \"Options\" include(\"base/options.jl\")" => "    @testset \"Options\" include(\"base/options.jl\")")))
    @test code == 1
    @test length(lines) == 1
end

@testset "each nested runtests.jl gives its own line" begin
    code, lines = check(fixture(merge(
        rt("    @safetestset \"Whole package\" include(\"integration/solve.jl\")" => "    @safetestset \"A\" include(\"integration/runtests.jl\")\n    @safetestset \"B\" include(\"base/runtests.jl\")"),
        Changes("test/integration/solve.jl" => nothing,
            "test/integration/runtests.jl" => "using Test\n",
            "test/base/runtests.jl" => "using Test\n"))))
    @test code == 1
    @test count(l -> occursin("nested runtests.jl", l), lines) == 2
end

@testset "an `include` of a path that is not a literal" begin
    code,
    lines = check(fixture(rt("include(\"integration/solve.jl\")" => "include(joinpath(\"integration\", \"solve.jl\"))")))
    @test code == 1
    @test any(
        l -> occursin("[D2] runtests.jl:8: `include` of a path that is not a literal", l),
        lines)
    # the file it names is then not reached, which D8 reports
    @test all(l -> occursin("[D2]", l) || occursin("[D8] integration/solve.jl", l), lines)
end

@testset "each non-literal `include` gives its own line, with its file and line" begin
    code, lines = check(fixture(merge(
        rt("include(\"integration/solve.jl\")" => "include(\"integration/runtests.jl\")"),
        Changes("test/integration/solve.jl" => nothing,
            "test/integration/runtests.jl" => "using Test\ninclude(joinpath(@__DIR__, \"a.jl\"))\n\ninclude(string(\"b\", \".jl\"))\n"))))
    @test code == 1
    nonliteral = filter(l -> occursin("not a literal", l), lines)
    @test length(nonliteral) == 2
    @test any(l -> occursin("[D2] integration/runtests.jl:2: `include`", l), nonliteral)
    @test any(l -> occursin("[D2] integration/runtests.jl:4: `include`", l), nonliteral)
end

@testset "a repository without Project.toml does not stop the next one" begin
    out = IOBuffer()
    a, b = fixture(Changes("Project.toml" => nothing)), fixture()
    code = run(pipeline(
        ignorestatus(`$(Base.julia_cmd()) --startup-file=no $SCRIPT --check $a $b`);
        stdout = out, stderr = devnull)).exitcode
    lines = filter(!isempty, split(String(take!(out)), '\n'))
    @test code == 1
    @test length(lines) == 1 && occursin("[D1] Project.toml does not exist", lines[1])
end

const PLAIN = "const GROUPS = isempty(ARGS) ? [\"core\", \"slow\"] : ARGS\n"
const PLATFORM = "const GROUPS = isempty(ARGS) ? (Sys.isapple() && Sys.ARCH === :aarch64 ? [\"core\", \"slow\", \"metal\"] : [\"core\", \"slow\"]) : ARGS\n"
const DEVICE_TEST = "using Test, Fixture\n@test Fixture.f() == 1\n"
# test/devices/metal.jl in the form of the convention: the device skip, with no issue
const DEVICE_SKIP = "using Test, Metal, Fixture\nif Metal.functional()\n    @test Fixture.f() == 1\nelse\n    @test_skip Metal.functional()\nend\n"

"The fixture with the GROUPS line `groups`, a group `g` and its file `test/devices/<g>.jl`."
function device(groups, file = DEVICE_TEST; g = "metal")
    group = "if \"$g\" in GROUPS\n    @safetestset \"Device\" include(\"devices/$g.jl\")\nend\n"
    merge(
        rt(PLAIN => groups, "if \"broken\" in GROUPS" => group * "if \"broken\" in GROUPS"),
        Changes("test/devices/$g.jl" => file))
end

const NOT_PLATFORM = "[D5] GROUPS is not the platform form"
const NO_METAL = "[D5] GROUPS has the platform form, and the repository has no `metal` group"
const SKIP_NO_ISSUE = "has `@test_skip` with no issue on its line"

# (what, change, the text of its one violation, or nothing for no violation)
const DEVICE_CASES = [
    ("(a) a `metal` group and the platform line", device(PLATFORM), nothing),
    ("(b) a `metal` group and the plain line", device(PLAIN), NOT_PLATFORM),
    ("(c) no `metal` group and the platform line", rt(PLAIN => PLATFORM), NO_METAL),
    ("(d) no `metal` group and the plain line", Changes(), nothing),
    ("(e) the device skip in test/devices/metal.jl with no issue",
        device(PLATFORM, DEVICE_SKIP), nothing),
    ("(f) `@test_skip Metal.functional()` with no issue outside test/devices/",
        Changes("test/integration/solve.jl" => "using Test, Fixture\n@test_skip Metal.functional()\n"),
        "[D7] integration/solve.jl:2 $SKIP_NO_ISSUE"),
    ("(g) `@test_skip other()` with no issue in test/devices/metal.jl",
        device(PLATFORM, "using Test, Fixture\n@test_skip other()\n"),
        "[D7] devices/metal.jl:2 $SKIP_NO_ISSUE"),
    ("a reordered condition of the platform line",
        device(replace(PLATFORM,
            "Sys.isapple() && Sys.ARCH === :aarch64" => "Sys.ARCH === :aarch64 && Sys.isapple()")),
        NOT_PLATFORM),
    ("a `cuda` group and the plain line", device(PLAIN; g = "cuda"), nothing),
    ("a `cuda` group and the platform line", device(PLATFORM; g = "cuda"), NO_METAL),
    ("the device skip of CUDA in test/devices/cuda.jl with no issue",
        device(PLAIN, replace(DEVICE_SKIP, "Metal" => "CUDA"); g = "cuda"), nothing),
    ("the device skip inside a larger expression, with no issue",
        device(PLATFORM, "using Test, Metal\n@test_skip Metal.functional() == true\n"),
        "[D7] devices/metal.jl:2 $SKIP_NO_ISSUE"),
    ("`@test_skip` of another module's `functional()` in test/devices/, with no issue",
        device(PLATFORM, "using Test, Fixture\n@test_skip Fixture.functional()\n"),
        "[D7] devices/metal.jl:2 $SKIP_NO_ISSUE"),
    ("`@test_skip CUDA.functional(true)` in test/devices/cuda.jl, with no issue",
        device(PLAIN, "using Test, CUDA\n@test_skip CUDA.functional(true)\n"; g = "cuda"),
        "[D7] devices/cuda.jl:2 $SKIP_NO_ISSUE"),
    ("the device skip with a keyword in test/devices/metal.jl, with no issue",
        device(PLATFORM, "using Test, Metal\n@test_skip Metal.functional() skip = true\n"),
        "[D7] devices/metal.jl:2 $SKIP_NO_ISSUE"),
    ("the device skip in test/devices.jl, outside test/devices/, with no issue",
        merge(
            rt(AQUA_LINE =>
                AQUA_LINE * "    @safetestset \"Devices\" include(\"devices.jl\")\n"),
            Changes(
                "test/devices.jl" => "using Test, Metal\n@test_skip Metal.functional()\n",
                "src/devices.jl" => "d() = 1\n")),
        "[D7] devices.jl:2 $SKIP_NO_ISSUE")
]

@testset "the platform GROUPS line and the device skip" begin
    @testset "$what" for (what, change, text) in DEVICE_CASES
        code, lines = check(fixture(change))
        if text === nothing
            @test code == 0
            @test isempty(lines)
        else
            @test code == 1
            @test length(lines) == 1
            @test occursin(text, only(lines))
        end
    end
end

@testset "a nested runtests.jl is not checked for the platform line" begin
    nested(groups) = merge(
        rt("include(\"integration/solve.jl\")" => "include(\"integration/runtests.jl\")"),
        Changes("test/integration/solve.jl" => nothing,
            "test/integration/runtests.jl" => "using SafeTestsets\n" * groups))
    _, plain = check(fixture(nested(PLAIN)))
    _, platform = check(fixture(nested(PLATFORM)))
    @test !isempty(plain)
    # the lines name the fixture's directory, which differs between the two
    strip_repo(ls) = sort([replace(l, r"^[^:]*: " => "") for l in ls])
    @test strip_repo(plain) == strip_repo(platform)
end

@testset "D9 names the group of test/quality/doctests.jl, which is not doctests" begin
    cases = ("slow" => rt(DOCTESTS_GROUP => DOCTESTS_SLOW), "core" => DOCTESTS_IN_CORE)
    for (g, change) in cases
        code, lines = check(fixture(change))
        @test code == 1
        @test length(lines) == 1
        @test endswith(only(lines),
            ": [D9] test/quality/doctests.jl is in group \"$g\", not \"doctests\"")
    end
end

@testset "D3 reports a top-level test file with no src/<name>.jl of that exact name" begin
    message = ": [D3] top.jl is at the top level of test/ and mirrors no src/top.jl"
    code, lines = check(fixture(TOP_LISTED))
    @test code == 1
    @test length(lines) == 1
    @test endswith(only(lines), message)
    # an unlisted top-level file is a D8 violation and a D3 violation
    code, lines = check(fixture(Changes("test/top.jl" => "using Test\n@test true\n")))
    @test code == 1
    @test length(lines) == 2
    @test any(l -> endswith(l, ": [D8] top.jl is not listed in runtests.jl"), lines)
    @test any(l -> endswith(l, message), lines)
    # the name of the source file differs in case only
    code, lines = check(fixture(merge(
        rt(AQUA_LINE => AQUA_LINE * "    @safetestset \"Lower\" include(\"fixture.jl\")\n"),
        Changes("test/fixture.jl" => "using Test, Fixture\n@test Fixture.f() == 1\n"))))
    @test code == 1
    @test length(lines) == 1
    @test endswith(only(lines),
        ": [D3] fixture.jl is at the top level of test/ and mirrors no src/fixture.jl")
end

@testset "one violation of rule $rule" for (rule, change) in MUTATIONS
    code, lines = check(fixture(change))
    @test code == 1
    @test !isempty(lines)
    @test all(l -> occursin("[$rule]", l), lines)
end
