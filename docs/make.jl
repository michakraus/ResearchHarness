# Build the documentation site with Documenter and DocumenterVitepress:
#
#   julia --project=docs -e 'using Pkg; Pkg.instantiate()'
#   julia --project=docs docs/make.jl
#
# The build runs npm, which fetches VitePress from the npm registry into docs/node_modules/. The
# site is in docs/build/1/. On a push to main, the docs workflow deploys it to gh-pages.

using Documenter
using DocumenterVitepress

# The figures are drawn first, into docs/src/assets/figures/, from docs/figures/.
include(joinpath(@__DIR__, "figures", "figures.jl"))
make_figures()

# The home page is the README, so its text has one source. Its links into docs/src/ become links
# between pages, and the edit link of the page points at the README.
readme = read(joinpath(@__DIR__, "..", "README.md"), String)
# GitHub's anchor of a heading is in lower case; Documenter's keeps the case of the heading.
for m in eachmatch(r"^#+ (.+)$"m, readme)
    anchor = replace(m[1], " " => "-")
    global readme = replace(readme, "](#$(lowercase(anchor)))" => "](#$(anchor))")
end
write(
    joinpath(@__DIR__, "src", "index.md"),
    "```@meta\nEditURL = \"../../README.md\"\n```\n\n" *
    replace(readme, "](docs/src/" => "](")
)

# Only the docs workflow deploys. A local build decides "no deploy" here, so that Documenter does
# not look for a CI system and print a warning that it found none.
on_ci = get(ENV, "GITHUB_ACTIONS", nothing) == "true"

makedocs(;
    sitename = "ResearchHarness",
    repo = Remotes.GitHub("michakraus/ResearchHarness"),
    format = DocumenterVitepress.MarkdownVitepress(;
        repo = "github.com/michakraus/ResearchHarness",
        devbranch = "main",
        devurl = "dev",
        deploy_decision = on_ci ? nothing : Documenter.DeployDecision(; all_ok = false),
        # The site has one version, so search engines may index it.
        noindex_non_stable = false,
        # The harness has no version, and the inventory needs one.
        inventory_version = "main"
    ),
    pages = [
        "Home" => "index.md",
        "Tutorial" => "tutorial.md",
        "Setup" => ["setup-macos.md", "setup-linux.md"],
        "Use" => ["daily-use.md", "profile.md", "harness-command.md"],
        "Background" => ["agents-at-work.md", "security.md", "architecture.md", "tools.md"],
        "Components" => [
            "components/agents.md",
            "components/skills.md",
            "components/commands.md",
            "components/rules.md",
            "components/hooks.md",
            "components/githooks.md",
            "components/scripts.md",
            "components/adapters.md",
            "components/harness.md",
            "components/other.md"
        ],
        "Development" => "development.md"
    ]
)

# The harness has no releases, so the site is one version. DocumenterVitepress deploys it to dev/
# on gh-pages, and the root of gh-pages redirects to dev/.
if on_ci
    DocumenterVitepress.deploydocs(;
        repo = "github.com/michakraus/ResearchHarness.git",
        target = joinpath(@__DIR__, "build"),
        devbranch = "main"
    )
end
