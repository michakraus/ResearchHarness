"""The coverage of the component pages of the documentation site.

Each page of `docs/src/components/` describes one kind of component. After the title and the
introduction, the page has one level-2 section per component, and the heading names it in
backticks: "## `advisor`", or "## `gate.jl` and `gate-test.jl`" for a script and its test. KINDS
says which tracked files are the components of each page and how each is named. `harness test`
checks both directions: every component has a heading on its page, and every name in backticks
in a level-2 heading is a component of that page, so a removed component leaves no stale section.
It also checks that every tool of the README's dependency tables has a heading in
`docs/src/tools.md` that names it as a whole word.
"""

import re
import subprocess

from . import REPO

PAGES = REPO / "docs" / "src" / "components"
TOOLS = REPO / "docs" / "src" / "tools.md"

def stem(path):
    """The file name without `.md`: the name of an agent, a rule or a command."""
    return path.rsplit("/", 1)[-1].removesuffix(".md")


def parent(path):
    """The name of the directory that holds the file: the name of a skill."""
    return path.split("/")[-2]


def base(path):
    """The file name."""
    return path.rsplit("/", 1)[-1]


def under(root):
    """The path relative to `root`, for a page whose file names repeat across directories."""
    return lambda path: path.removeprefix(root + "/")


def whole(name):
    """One name for every file of a component that spans several files."""
    return lambda path: name


# (page, pattern, name): the tracked files that match the pattern are the components of the page,
# and `name` turns a matching path into the component's name. In a pattern, `*` matches within one
# path segment.
KINDS = [
    ("agents.md", "agents/*.md", stem),
    ("agents.md", "adapters/opencode/agents/*.md", stem),
    ("skills.md", "skills/*/SKILL.md", parent),
    ("commands.md", "commands/*.md", stem),
    ("rules.md", "rules/*.md", stem),
    ("rules.md", "instructions/*.md", stem),
    ("hooks.md", "hooks/*", base),
    ("githooks.md", "githooks/*", base),
    ("githooks.md", "githooks/workflows/*", under("githooks")),
    ("scripts.md", "scripts/*", base),
    ("adapters.md", "adapters/*/*", under("adapters")),
    ("adapters.md", "adapters/opencode/plugins/*", under("adapters")),
    ("harness.md", "bin/harness", base),
    ("harness.md", "lib/harness/*.py", base),
    ("other.md", "launchagents/*", base),
    ("other.md", "agent-workflows/*.js", base),
    ("other.md", "ast-grep/*.*", under("ast-grep")),
    ("other.md", "ast-grep/rules/*", under("ast-grep")),
    ("other.md", "settings/*", base),
    ("other.md", "examples/*", base),
    ("other.md", "fatou.toml", base),
    ("other.md", ".gitleaks.toml", base),
    ("other.md", "Project.toml", base),
    ("other.md", "tests/skill-triggers/*.toml", whole("tests/skill-triggers")),
]

# A file of a matching pattern that is no component of its own: a directory's ignore file.
SKIP = {"ast-grep/.gitignore"}


def matches(pattern, path):
    """Whether `path` matches `pattern`, where `*` matches within one path segment."""
    return re.fullmatch(re.escape(pattern).replace(r"\*", "[^/]*"), path) is not None


def components(tracked):
    """{page: the set of component names} for the tracked paths."""
    pages = {}
    for page, pattern, name in KINDS:
        names = pages.setdefault(page, set())
        names.update(name(p) for p in tracked if matches(pattern, p) and p not in SKIP)
    return pages


def headings(text, level):
    """The text of each heading of exactly `level` in Markdown `text`, outside code fences."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#" * level + " "):
            found.append(line[level + 1 :])
    return found


def named(text):
    """The names in backticks in a heading."""
    return set(re.findall(r"`([^`]+)`", text))


def word(name, text):
    """Whether `name` is in `text` as a whole word: not inside a longer name or path."""
    return re.search(rf"(?<![\w./-]){re.escape(name)}(?![\w./-])", text) is not None


def readme_tools(readme):
    """The first cell of each row of the README's dependency tables."""
    tools, inside = [], False
    for line in readme.splitlines():
        if line.startswith("## "):
            inside = line == "## Dependencies"
        elif inside and line.startswith("| ") and not line.startswith("| tool |"):
            tools.append(line.split("|")[1].strip())
    return tools


def tracked():
    """The paths that git tracks in the repository."""
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def selftest():
    """The matching rules on fixed inputs, then the pages of this checkout."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  docs: {label}")

    for pattern, path, expected in [
        ("hooks/*", "hooks/probe.py", True),
        ("hooks/*", "hooks/sub/probe.py", False),
        ("adapters/*/*", "adapters/opencode/plugins/rtk.ts", False),
        ("ast-grep/*.*", "ast-grep/rules/parse-error.yml", False),
    ]:
        check(matches(pattern, path) == expected, f"{path!r} matches {pattern!r}: {expected}")
    for name, text, expected in [
        ("gate.jl", "`gate.jl` and `gate-test.jl`", True),
        ("gate.jl", "`gate-test.jl`", False),
        ("pre-commit", "`pre-commit-wiki`", False),
        ("CLAUDE.md", "`claude/CLAUDE.md`", False),
        ("JSON", "ExplicitImports, JSON, JuliaFormatter", True),
        ("git", "gitleaks", False),
    ]:
        check(word(name, text) == expected, f"{name!r} is a word of {text!r}: {expected}")
    check(headings("# T\n## `a`\n```\n## `b`\n```\n### `c`\n", 2) == ["`a`"], "headings skip code fences and other levels")
    check(named("`a` and `b`") == {"a", "b"}, "named reads each name in backticks")

    for page, names in sorted(components(tracked()).items()):
        f = PAGES / page
        if not f.is_file():
            check(False, f"components/{page} exists")
            continue
        heads = headings(f.read_text(), 2)
        inside = set().union(*map(named, heads)) if heads else set()
        for name in sorted(names):
            check(name in inside, f"components/{page} has a heading for {name!r}")
        for name in sorted(inside - names):
            check(False, f"components/{page}: {name!r} in a heading is no component of the page")
    tool_heads = headings(TOOLS.read_text(), 2)
    for tool in readme_tools((REPO / "README.md").read_text()):
        check(any(word(tool, h) for h in tool_heads), f"tools.md has a heading for {tool!r}")
    return total, wrong
