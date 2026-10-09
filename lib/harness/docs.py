"""The coverage of the component pages of the documentation site.

Each page of `docs/src/components/` describes one kind of component. After the title and the
introduction, the page has one level-2 section per component, and the heading names it in
backticks: "## `advisor`", or "## `gate.jl` and `gate-test.jl`" for a script and its test. KINDS
says which tracked files are the components of each page and how each is named. `harness test`
checks both directions: every component has a heading on its page, and every name in backticks
in a level-2 heading is a component of that page, so a removed component leaves no stale section.
It also checks that every tool of the README's dependency tables has a heading in
`docs/src/tools.md` that names it as a whole word.

The call graphs of `docs/src/agents-at-work.md` are drawn from `docs/figures/calls.toml`, one
`[[call]]` entry per spawn: `caller`, `callee`, `at` (the `file:line` of the instruction that
spawns), and optionally `effort`, where the caller sets one other than the callee's own, and
`label`, the text on the edge. `harness test` checks that every caller and callee is an agent of
`agents/` or a skill of `skills/`, that `at` is a line of the caller's own source that names the
callee, and that every source with the tool `agent`, and each skill of SPAWNING_SKILLS, is the
caller of at least one entry.
"""

import re
import subprocess
import tomllib

from . import REPO
from .frontmatter import parse_file

PAGES = REPO / "docs" / "src" / "components"
TOOLS = REPO / "docs" / "src" / "tools.md"
CALLS = REPO / "docs" / "figures" / "calls.toml"

# The keys of a `[[call]]` entry, the ones it must have, and the values of `effort`.
CALL_KEYS = {"caller", "callee", "at", "effort", "label"}
CALL_REQUIRED = ("caller", "callee", "at")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# The skills that spawn agents from the main session, which has the tool `agent` without a
# `tools:` line.
SPAWNING_SKILLS = ("build-part", "build-reviewed")

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


def call_sources(paths):
    """{name: source path} of each agent of `agents/` and each skill of `skills/` in `paths`."""
    found = {stem(p): p for p in paths if matches("agents/*.md", p)}
    found.update({parent(p): p for p in paths if matches("skills/*/SKILL.md", p)})
    return found


def call_problems(call, sources, meta, lines):
    """What is wrong with one `[[call]]` entry, one phrase each. `sources` maps a name to its
    source path, `meta` maps a name to its frontmatter, and `lines(path)` gives a file's lines."""
    if not isinstance(call, dict):
        return ["is not a table"]
    problems = [f"has the unknown key {key!r}" for key in sorted(set(call) - CALL_KEYS)]
    problems += [f"has no {key!r}" for key in CALL_REQUIRED if key not in call]
    caller, callee, at = (call.get(key) for key in CALL_REQUIRED)
    for role, name in (("caller", caller), ("callee", callee)):
        if role in call and not (isinstance(name, str) and name in sources):
            problems.append(f"{role} {name!r} is no agent of agents/ and no skill of skills/")
    if "at" in call and isinstance(caller, str) and caller in sources:
        place = re.fullmatch(r"(.+):([1-9][0-9]*)", at) if isinstance(at, str) else None
        if not place or place[1] != sources[caller]:
            problems.append(f"at {at!r} is no line of the caller's source {sources[caller]}")
        else:
            text = lines(place[1])
            if int(place[2]) > len(text):
                problems.append(f"at {at!r} is past the end of the file")
            elif isinstance(callee, str) and callee in sources and not word(callee, text[int(place[2]) - 1]):
                problems.append(f"the line {at} does not name {callee!r}")
    if "effort" in call:
        effort = call["effort"]
        if effort not in EFFORTS:
            problems.append(f"effort {effort!r} is none of {', '.join(EFFORTS)}")
        elif isinstance(callee, str) and meta.get(callee, {}).get("effort") == effort:
            problems.append(f"effort {effort!r} is the callee's own")
    if "label" in call and not isinstance(call["label"], str):
        problems.append("label is not a string")
    return problems


def spawners(meta):
    """The sources that spawn agents: each with the tool `agent`, and each of SPAWNING_SKILLS."""
    return sorted({name for name, m in meta.items() if "agent" in m.get("tools", [])} | set(SPAWNING_SKILLS))


def call_cases(calls, sources, meta, lines, check):
    """The cases of `calls`, the entries of calls.toml, through `check(ok, label)`."""
    for number, call in enumerate(calls, 1):
        problems = call_problems(call, sources, meta, lines)
        name = f"{call.get('caller')} -> {call.get('callee')}" if isinstance(call, dict) else repr(call)
        check(not problems, f"calls.toml entry {number}, {name}" + (": " + "; ".join(problems) if problems else ""))
    keys = [tuple(repr(c.get(k)) for k in ("caller", "callee", "effort")) for c in calls if isinstance(c, dict)]
    for key in sorted({k for k in keys if keys.count(k) > 1}):
        check(False, f"calls.toml has {key[0]} -> {key[1]} at effort {key[2]} more than once")
    callers = {c.get("caller") for c in calls if isinstance(c, dict) and isinstance(c.get("caller"), str)}
    for name in spawners(meta):
        check(name in callers, f"calls.toml has an entry with the caller {name!r}, which spawns")


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

    # The rules of calls.toml on fixed inputs: each wrong entry gives one problem.
    sources = call_sources(["agents/a.md", "agents/b.md", "skills/s/SKILL.md", "skills/s/edges.md"])
    meta = {"a": {"tools": ["read"]}, "b": {"tools": ["agent"], "effort": "medium"}, "s": {}}
    files = {"agents/b.md": ["---", "Spawn `a` here.", "Spawn the s skill."], "skills/s/SKILL.md": ["Spawn `b`."]}
    good = {"caller": "b", "callee": "a", "at": "agents/b.md:2"}
    check(sources == {"a": "agents/a.md", "b": "agents/b.md", "s": "skills/s/SKILL.md"}, "call_sources reads agents/*.md and skills/*/SKILL.md only")
    check(call_problems(good, sources, meta, files.get) == [], "a true entry of calls.toml has no problem")
    for change, phrase in [
        ({"callee": "nonexistent"}, "callee 'nonexistent' is no agent"),
        ({"caller": "nonexistent"}, "caller 'nonexistent' is no agent"),
        ({"at": "agents/b.md:3"}, "does not name 'a'"),
        ({"at": "skills/s/SKILL.md:1"}, "no line of the caller's source"),
        ({"at": "agents/b.md:9"}, "past the end"),
        ({"at": "agents/b.md"}, "no line of the caller's source"),
        ({"effort": "huge"}, "effort 'huge' is none of"),
        ({"model": "large"}, "unknown key 'model'"),
        ({"label": 1}, "label is not a string"),
    ]:
        found = call_problems(good | change, sources, meta, files.get)
        check(len(found) == 1 and phrase in found[0], f"calls.toml entry with {change} gives {phrase!r}: {found}")
    check(call_problems({"caller": "s", "callee": "b", "at": "skills/s/SKILL.md:1", "effort": "medium"}, sources, meta, files.get)
          == ["effort 'medium' is the callee's own"], "an effort that is the callee's own is a problem")
    check(call_problems({"caller": "b", "callee": "a"}, sources, meta, files.get) == ["has no 'at'"], "an entry without 'at' is a problem")
    check(spawners(meta) == ["b", *SPAWNING_SKILLS], "spawners: the sources with the tool agent, and SPAWNING_SKILLS")
    found = []
    call_cases([good, good, {"caller": "s", "callee": "b", "at": "skills/s/SKILL.md:1"}], sources, meta, files.get,
               lambda ok, label: found.append((ok, label)))
    check([label for ok, label in found if not ok] == [
        "calls.toml has 'b' -> 'a' at effort None more than once",
        "calls.toml has an entry with the caller 'build-part', which spawns",
        "calls.toml has an entry with the caller 'build-reviewed', which spawns",
    ], f"call_cases names a duplicate and each spawner without an entry: {found}")

    # calls.toml of this checkout.
    sources = call_sources(tracked())
    meta = {name: parse_file(REPO / path).meta for name, path in sources.items()}
    calls = tomllib.loads(CALLS.read_text()).get("call", []) if CALLS.is_file() else []
    check(CALLS.is_file() and bool(calls), "docs/figures/calls.toml exists and has [[call]] entries")
    call_cases(calls, sources, meta, lambda path: (REPO / path).read_text().splitlines(), check)
    return total, wrong
