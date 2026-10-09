# Drift check for the shared GitHub workflows. Companion to harness workflows.
#
#   julia verify-workflows.jl            # report
#   julia verify-workflows.jl --quiet    # only deviations and the summary
#
# Exits non-zero if any repository deviates. Run it before touching CI, after any install, and
# before harness ci-protection --apply, which refuses to run if this fails.
#
# WHAT IT CHECKS, AND WHY EACH CHECK IS HERE.
#
#   1. CI.yml, dependabot.yml, TagBot.yml and codecov.yml are byte-identical to the templates in
#      workflows/. They are installed by copy and are not parameterised, so anything other than
#      equality is drift. This is the check that makes the required-status-check list static.
#      TagBot.yml is the one asymmetric case: byte-identical under Packages/, and asserted
#      ABSENT under Experiments/, none of which is registered in General.
#   1b. The same set on the DEFAULT branch, but only for a repository whose working tree is
#      checked out somewhere else. The working-tree pass is primary — it is what a push would
#      carry, and it catches an uncommitted hand edit. But a repository parked on a topic branch
#      that predates a workflow change reports as drifted when nothing has drifted, and the
#      obvious remedy for that report (harness workflows --apply) would overwrite the branch's
#      files. So both questions are asked and reported apart. The default branch is the invariant
#      harness ci-protection depends on; the working tree is what you are about to push.
#   2. The two canonical CI jobs parse, and their job names are exactly the strings that
#      harness ci-protection requires. A rename here silently invalidates branch protection in every
#      repository, so it is asserted against a literal rather than derived.
#   3. No Register.yml, no register.yml, no Documentation.yml, no Documentation.yaml, no
#      CompatHelper.yml, in the working tree and on the default branch. Register.yml is removed on
#      purpose (see Packages/CLAUDE.md - dispatching it burns a version number); the Documentation
#      spellings are the old names of Documenter.yml; CompatHelper.yml would open every [compat]
#      bump a second time beside dependabot.yml.
#   4. Every `uses:` in every workflow is pinned to the expected major. An action left a major
#      behind is the failure mode dependabot.yml does not cover: it updates Julia only.
#   5. Which repositories the doctest job will skip - those with no docs/Project.toml. The job is
#      byte-identical everywhere and skips itself, so this is reported rather than treated as an
#      error, but a silent skip is worse than a loud one.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end
using TOML
using YAML

const ROOT = get(ENV, "RESEARCH_ROOT", joinpath(homedir(), "Research"))
const TEMPLATES = joinpath(@__DIR__, "workflows")
const PROFILE = TOML.parsefile(
    get(ENV, "RESEARCH_HARNESS_PROFILE", joinpath(homedir(), ".config", "research-harness", "profile.toml")),
)

const QUIET = "--quiet" in ARGS

# Job names. These are the required status checks, modulo the matrix expansion below.
const TEST_JOB_NAME = "Julia \${{ matrix.version }} - \${{ matrix.os }} - \${{ matrix.arch }}"
const DOCTEST_JOB_NAME = "Doctests - \${{ matrix.os }}"

const VERSIONS = ["min", "1"]
const OSES = ["ubuntu-latest", "macOS-latest", "windows-latest"]

required_checks() = vcat(
    ["Julia $v - $o - default" for v in VERSIONS for o in OSES],
    ["Doctests - ubuntu-latest"],
)

# Expected major version of every action used anywhere in the tree. Queried from GitHub on
# 2026-08-31; julia-actions/julia-processcoverage publishes no GitHub release, but its `v1` tag
# tracks v1.2.2.
const ACTION_MAJORS = Dict(
    "actions/checkout" => "v7",
    "actions/upload-artifact" => "v7",
    "actions/download-artifact" => "v8",
    "actions/cache" => "v6",
    "codecov/codecov-action" => "v7",
    "julia-actions/setup-julia" => "v3",
    "julia-actions/cache" => "v3",
    "julia-actions/julia-buildpkg" => "v1",
    "julia-actions/julia-runtest" => "v1",
    "julia-actions/julia-processcoverage" => "v1",
    "julia-actions/julia-docdeploy" => "v1",
    "julia-actions/julia-downgrade-compat" => "v2",
    "JuliaRegistries/TagBot" => "v1",
    "peter-evans/create-pull-request" => "v8",
)

# Workflow file names that must not exist. Register.yml is removed on purpose; the Documentation
# spellings are the old name of Documenter.yml; CompatHelper.yml duplicates dependabot.yml.
const FORBIDDEN =
    ["Register.yml", "register.yml", "Documentation.yml", "Documentation.yaml", "CompatHelper.yml"]

# Repositories whose documentation workflow is a multi-job pipeline rather than a single build: the
# profile's `docs_exceptions`. The template does not describe them, so no comparison against it
# means anything.
const DOCS_PIPELINES = Vector{String}(PROFILE["docs_exceptions"])

# Repositories that keep the canonical documentation workflow and only *add* to it, such as the TeX
# toolchain that docs/make.jl needs to compile TikZ figures before Documenter checks links: the
# profile's `docs_additions`. The installer does not overwrite them, so the byte comparison never
# sees them — but the canonical body must still survive inside each, which is what
# `documenter_additions_intact` asserts. Without that, nothing would report a template change to it.
const DOCS_ADDITIONS = Vector{String}(PROFILE["docs_additions"])

# Every repository whose Documenter.yml the installer skips, as `harness workflows` does.
const DOCS_EXCEPTIONS = vcat(DOCS_PIPELINES, DOCS_ADDITIONS)

struct Finding
    repo::String
    what::String
end

"""
An off-branch repository: one whose working tree is not on its default branch. `deviations` holds
what the **default branch** says, which is the invariant `harness ci-protection` depends on — the
required-status-check list is built on job names being identical across the tree, and those checks
run against the default branch and PR merge commits, never against a local checkout.

Reported separately from `Finding` because the two answer different questions, and conflating them
is actively misleading: a working-tree deviation on a topic branch that predates a workflow change
is not drift, and the obvious remedy for it — `harness workflows --apply` — would write template
bytes over that branch's files.
"""
struct OffBranch
    repo::String
    branch::String
    default::String
    deviations::Vector{String}
end

repos() = sort!(
    [
        d for group in ("Packages", "Experiments") for
        d in readdir(joinpath(ROOT, group); join = true) if
        isdir(joinpath(d, ".git")) && isfile(joinpath(d, "Project.toml"))
    ];
    by = basename,
)

"""
    tracked(dir, path)

Whether `path` is tracked by git in `dir`. Not `isfile`: a runner checks out tracked files only, so
an untracked `docs/make.jl` sitting in a working tree is not documentation that CI can build, such
as an untracked stale copy of another package's `docs/`. Mirrors the same test in
`harness workflows`.
"""
function tracked(dir::String, path::String)
    return try
        cmd = Cmd(`git -C $dir ls-files -- $path`; ignorestatus = true)
        !isempty(readchomp(pipeline(cmd; stderr = devnull)))
    catch
        false
    end
end

"""
    describe_difference(template_text, actual_text)

Byte comparison of two strings, normalising only the trailing newline. Returns `nothing` when equal
and a short description of the first difference otherwise. Shared by the working-tree comparison and
the default-branch one, so the two cannot report the same drift differently.
"""
function describe_difference(template_text::AbstractString, actual_text::AbstractString)
    a = rstrip(template_text, '\n')
    b = rstrip(actual_text, '\n')
    a == b && return nothing
    la, lb = split(a, '\n'), split(b, '\n')
    for i in 1:min(length(la), length(lb))
        la[i] == lb[i] && continue
        return "differs from the template at line $i: $(strip(lb[i]))"
    end
    return "differs from the template in length ($(length(lb)) lines, expected $(length(la)))"
end

"""
    identical(template, installed)

As `describe_difference`, reading `installed` from the working tree.
"""
function identical(template::String, installed::String)
    isfile(installed) || return "missing"
    return describe_difference(read(template, String), read(installed, String))
end

"""
    content_at_ref(dir, rel, ref)

The bytes of `rel` as committed at `ref`, or `nothing` when the path does not exist there. Uses
`git show`, so it reads the commit rather than the working tree — which is the whole point of the
default-branch pass below.

**`nothing` means "not readable", not specifically "absent":** a missing path and a nonexistent
`ref` are indistinguishable here, both being a non-zero `git show`. That matters for the
TagBot-absence assertion, where `nothing` is the *passing* answer — a bad ref would read as a pass.
It is safe only because the caller passes a ref that `default_branch` has just found with
`git branch --list`, so the ref exists by construction. Do not reuse this with an unvalidated ref
to prove an absence.
"""
function content_at_ref(dir::String, rel::String, ref::String)
    out = IOBuffer()
    cmd = Cmd(`git -C $dir show $(ref * ":" * rel)`; ignorestatus = true)
    p = run(pipeline(cmd; stdout = out, stderr = devnull))
    return success(p) ? String(take!(out)) : nothing
end

"""
    identical_at_ref(template, dir, rel, ref)

As `identical`, against the committed content at `ref` instead of the working tree.
"""
function identical_at_ref(template::String, dir::String, rel::String, ref::String)
    text = content_at_ref(dir, rel, ref)
    text === nothing && return "missing"
    return describe_difference(read(template, String), text)
end

"""
    current_branch(dir)

The checked-out branch, or `""` for a detached HEAD or on error.
"""
function current_branch(dir::String)
    return try
        cmd = Cmd(`git -C $dir rev-parse --abbrev-ref HEAD`; ignorestatus = true)
        b = readchomp(pipeline(cmd; stderr = devnull))
        b == "HEAD" ? "" : b
    catch
        ""
    end
end

"""
    default_branch(dir)

`"main"` if the repository has one, else `"master"`, else `""`.

**Deliberately does not consult `origin/HEAD`.** After a branch rename, `origin/HEAD` can still
point at `origin/master` while the remote carries only `main` — a dangling symbolic ref. A checker
that trusted it would compare against a branch that does not exist. Local branch names are the thing actually being checked, so
they are what this asks about.
"""
function default_branch(dir::String)
    # The format string is interpolated rather than written literally: Julia's backtick syntax
    # rejects unquoted parentheses.
    fmt = "--format=%(refname:short)"
    out = try
        cmd = Cmd(`git -C $dir branch $fmt --list main master`; ignorestatus = true)
        readchomp(pipeline(cmd; stderr = devnull))
    catch
        ""
    end
    names = split(out, '\n'; keepempty = false)
    "main" in names && return "main"
    "master" in names && return "master"
    return ""
end

"""
    workflow_files(dir, name, isexperiment)

The `(template, repository-relative path)` pairs whose bytes must match in this repository. One
list, consumed by both the working-tree pass and the default-branch pass, so a file can never be
checked in one and forgotten in the other. Paths use `/` because `git show` needs them that way.

`TagBot.yml` is absent from the list for an experiment; its absence is asserted separately.
"""
function workflow_files(dir::String, name::String, isexperiment::Bool)
    files = [
        ("CI.yml", ".github/workflows/CI.yml"),
        ("dependabot.yml", ".github/dependabot.yml"),
        ("codecov.yml", "codecov.yml"),
    ]
    isexperiment || push!(files, ("TagBot.yml", ".github/workflows/TagBot.yml"))
    if !(name in DOCS_EXCEPTIONS) && tracked(dir, "docs/make.jl")
        push!(files, ("Documenter.yml", ".github/workflows/Documenter.yml"))
    end
    return files
end

"""
    workflow_body(path) -> Vector{String}

The lines of a workflow that carry behaviour: comments and blank lines dropped, trailing whitespace
removed. A `DOCS_ADDITIONS` repository rewrites the header comment of its copy on purpose — that is
where it says why it differs — so the comments are exactly the part a comparison must ignore.
"""
function workflow_body(path::String)
    body = String[]
    for line in eachline(path)
        stripped = strip(line)
        (isempty(stripped) || startswith(stripped, "#")) && continue
        push!(body, rstrip(line))
    end
    return body
end

"""
    documenter_additions_intact(template, path) -> Union{Nothing, String}

`nothing` when every behavioural line of `template` appears in `path` in the same order, otherwise
the first canonical line that does not. A `DOCS_ADDITIONS` copy adds steps and changes nothing else,
so the canonical body must survive inside it as a subsequence. Extra lines are the point and are
allowed; a canonical line that has moved, changed or gone is what this reports.
"""
function documenter_additions_intact(template::String, path::String)
    canonical = workflow_body(template)
    got = workflow_body(path)
    at = 1
    for want in canonical
        hit = findnext(==(want), got, at)
        hit === nothing && return want
        at = hit + 1
    end
    return nothing
end

"""
    action_uses(path)

Every `uses: owner/repo@ref` in one workflow file, as `(owner/repo, ref, line)`. A regex rather
than the parsed YAML, because `uses:` appears at several nesting depths and the line number is what
makes a finding actionable.
"""
function action_uses(path::String)
    out = Tuple{String, String, Int}[]
    for (i, line) in enumerate(eachline(path))
        m = match(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([A-Za-z0-9_.-]+)", line)
        m === nothing && continue
        push!(out, (m.captures[1], m.captures[2], i))
    end
    return out
end

function check_repo(
        dir::String,
        findings::Vector{Finding},
        skips::Vector{String},
        offbranch::Vector{OffBranch},
)
    name = basename(dir)
    wf = joinpath(dir, ".github", "workflows")
    isexperiment = occursin(joinpath("", "Experiments", ""), dir * Base.Filesystem.path_separator)

    fail(what) = push!(findings, Finding(name, what))

    files = workflow_files(dir, name, isexperiment)

    # 1. the byte-identical set, in the working tree
    for (template, rel) in files
        d = identical(joinpath(TEMPLATES, template), joinpath(dir, rel))
        d === nothing || fail("$template $d")
    end
    # TagBot is asserted in both directions: byte-identical under Packages/, absent under
    # Experiments/. Nothing under Experiments/ is registered in General, so there is nothing to
    # tag, and harness workflows installs the file into Packages/ only.
    #
    # The absence is asserted rather than skipped because install_file only ever copies: nothing
    # removes a file the template set no longer covers, so a hand-reintroduced copy is invisible
    # to the installer and would be invisible here too.
    if isexperiment
        isfile(joinpath(wf, "TagBot.yml")) &&
            fail("TagBot.yml is present, but nothing under Experiments/ is registered in General")
    end

    # 1a. the repositories that add steps to the canonical documentation workflow. The installer
    # skips their Documenter.yml, so the byte comparison above never covers it, and until this check
    # existed nothing reported a template change to them at all — not a new step, not a renamed job.
    # The action majors in check 4 did cover the version bumps, and only those.
    if name in DOCS_ADDITIONS
        doc = joinpath(wf, "Documenter.yml")
        if !isfile(doc)
            fail("Documenter.yml is missing, but this repository is listed in DOCS_ADDITIONS")
        else
            gone = documenter_additions_intact(joinpath(TEMPLATES, "Documenter.yml"), doc)
            gone === nothing || fail(
                "Documenter.yml has drifted from the template: the canonical line " *
                "`$(gone)` is missing from it or out of order",
            )
        end
    end

    # 1b. the same set on the default branch, when the working tree is somewhere else.
    #
    # The working-tree pass above is what a push would carry and it catches an uncommitted hand
    # edit, so it stays primary. But a repository parked on a topic branch that predates a workflow
    # change reports as drifted when nothing has drifted: its main is byte-identical while its
    # checkout sits on an older branch. Both questions are worth answering, so both are asked and
    # reported apart.
    branch = current_branch(dir)
    default = default_branch(dir)
    if !isempty(default) && branch != default
        devs = String[]
        for (template, rel) in files
            d = identical_at_ref(joinpath(TEMPLATES, template), dir, rel, default)
            d === nothing || push!(devs, "$template $d")
        end
        if isexperiment &&
           content_at_ref(dir, ".github/workflows/TagBot.yml", default) !== nothing
            push!(devs,
                "TagBot.yml is present, but nothing under Experiments/ is registered in General")
        end
        for f in FORBIDDEN
            content_at_ref(dir, ".github/workflows/$f", default) === nothing ||
                push!(devs, "$f still exists")
        end
        push!(offbranch, OffBranch(name, isempty(branch) ? "(detached HEAD)" : branch, default, devs))
    end

    # 2. the canonical job names, from the parsed YAML
    ci = joinpath(wf, "CI.yml")
    if isfile(ci)
        y = try
            YAML.load_file(ci)
        catch e
            fail("CI.yml does not parse as YAML: $(sprint(showerror, e))")
            nothing
        end
        if y !== nothing
            get(y, "name", nothing) == "CI" ||
                fail("CI.yml workflow name is $(repr(get(y, "name", nothing))), expected \"CI\"")
            jobs = get(y, "jobs", Dict())
            haskey(jobs, "test") || fail("CI.yml has no `test` job")
            haskey(jobs, "doctest") || fail("CI.yml has no `doctest` job")
            if haskey(jobs, "test")
                got = get(jobs["test"], "name", nothing)
                got == TEST_JOB_NAME ||
                    fail("CI.yml test job name is $(repr(got)), expected $(repr(TEST_JOB_NAME))")
            end
            if haskey(jobs, "doctest")
                got = get(jobs["doctest"], "name", nothing)
                got == DOCTEST_JOB_NAME || fail(
                    "CI.yml doctest job name is $(repr(got)), expected $(repr(DOCTEST_JOB_NAME))",
                )
            end
        end
    end

    # 3. names that must not exist. `readdir` rather than `isfile`, because APFS is
    # case-insensitive: isfile(".../register.yml") is true when only Register.yml exists, which
    # would report both spellings for every repository that has either.
    if isdir(wf)
        present = readdir(wf)
        for f in FORBIDDEN
            f in present && fail("$f still exists")
        end
    end

    # 4. action majors, across every workflow in the repository
    if isdir(wf)
        for f in sort(readdir(wf))
            endswith(f, ".yml") || endswith(f, ".yaml") || continue
            path = joinpath(wf, f)
            # every workflow must at least parse
            try
                YAML.load_file(path)
            catch e
                fail("$f does not parse as YAML: $(sprint(showerror, e))")
            end
            for (action, ref, line) in action_uses(path)
                want = get(ACTION_MAJORS, action, nothing)
                if want === nothing
                    fail("$f:$line uses unknown action $action@$ref")
                elseif ref != want
                    fail("$f:$line has $action@$ref, expected @$want")
                end
            end
        end
    end

    # 5. doctest coverage - reported, not failed. The doctest job is byte-identical everywhere and
    # skips itself where there is no documentation environment, but a silent skip is worse than a
    # loud one.
    tracked(dir, "docs/Project.toml") || push!(skips, name)
    return nothing
end

function main()
    all = repos()
    isempty(all) && (println("no repositories found under $ROOT"); return 1)

    findings = Finding[]
    skips = String[]
    offbranch = OffBranch[]
    for dir in all
        check_repo(dir, findings, skips, offbranch)
    end

    if !QUIET
        println("Required status checks (identical in every repository):")
        for c in required_checks()
            println("    ", c)
        end
        println()
    end

    if !isempty(skips)
        println("Doctest job will skip itself (no docs/Project.toml) in $(length(skips)) repo(s):")
        println("    ", join(skips, ", "))
        println()
    end

    byrepo = Dict{String, Vector{String}}()
    for f in findings
        push!(get!(byrepo, f.repo, String[]), f.what)
    end

    # Off-branch repositories, before the findings, because this section is what tells the reader
    # whether a finding below is drift or a stale checkout.
    offbranch_bad = filter(o -> !isempty(o.deviations), offbranch)
    if !isempty(offbranch)
        println("$(length(offbranch)) repositor$(length(offbranch) == 1 ? "y is" : "ies are") not on the default branch:")
        for o in sort(offbranch; by = o -> o.repo)
            if isempty(o.deviations)
                println("    $(o.repo): on $(o.branch); $(o.default) is canonical")
            else
                println("    $(o.repo): on $(o.branch); $(o.default) DEVIATES:")
                for d in o.deviations
                    println("        ", d)
                end
            end
        end
        println()
        println("    A working-tree finding below for one of these may be the branch, not drift.")
        println("    Do NOT run harness workflows --apply in a repository listed here as")
        println("    canonical on its default branch: it would write template bytes over the")
        println("    checked-out branch's files. Switch to the default branch first.")
        println()
    end

    if isempty(findings) && isempty(offbranch_bad)
        println("$(length(all)) repositories checked - all canonical.")
        return 0
    end

    if !isempty(findings)
        println("$(length(byrepo)) of $(length(all)) repositories deviate in the working tree:")
        for repo in sort(collect(keys(byrepo)))
            println("\n  ", repo)
            for what in byrepo[repo]
                println("      ", what)
            end
        end
        println("\n$(length(findings)) finding(s). Re-run harness workflows --apply, or fix by hand.")
    end
    if !isempty(offbranch_bad)
        println()
        println("$(length(offbranch_bad)) repositor$(length(offbranch_bad) == 1 ? "y" : "ies") deviate on the DEFAULT branch, which is the invariant that matters:")
        println("    ", join(sort([o.repo for o in offbranch_bad]), ", "))
        println("Fix these on the default branch itself, not in the current checkout.")
    end
    return 1
end

exit(main())
