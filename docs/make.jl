# Build the documentation site with Documenter:
#
#   julia --project=docs -e 'using Pkg; Pkg.instantiate()'
#   julia --project=docs docs/make.jl
#
# The site is in docs/build/. On a push to main, the docs workflow deploys it to gh-pages.

using Documenter

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

makedocs(;
    sitename = "ResearchHarness",
    repo = Remotes.GitHub("michakraus/ResearchHarness"),
    format = Documenter.HTML(;
        prettyurls = get(ENV, "CI", nothing) == "true",
        edit_link = "main",
        # The harness has no version, and the inventory needs one.
        inventory_version = "main"
    ),
    pages = [
        "Home" => "index.md",
        "Setup" => ["setup-macos.md", "setup-linux.md"],
        "Use" => ["daily-use.md", "profile.md", "harness-command.md"],
        "Background" => ["security.md", "architecture.md", "tools.md"],
        "Development" => "development.md"
    ]
)

# The harness has no releases, so the site is one version at the root of gh-pages.
deploydocs(; repo = "github.com/michakraus/ResearchHarness.git", devbranch = "main", versions = nothing)
