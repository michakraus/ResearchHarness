"""The coverage of the component pages of the documentation site.

Each page of `docs/src/components/` describes one kind of component. After the title and the
introduction, the page has one level-2 section per component, and the heading names it in
backticks: "## `advisor`", or "## `gate.jl` and `gate-test.jl`" for a script and its test. KINDS
says which tracked files are the components of each page and how each is named. `harness test`
checks both directions: every component has a heading on its page, and every name in backticks
in a level-2 heading is a component of that page, so a removed component leaves no stale section.
It also checks `docs/src/dependencies.md`: its three tables, under the level-2 headings of
TABLES, with the columns `tool`, `minimum` and `used for`, and below them one level-3 heading per
description, which names its tools, "Python" or "JSON, YAML and TestEnv". Every tool of the
tables is named by a heading, and every name in a heading is a tool of the tables.

The call graphs of `docs/src/agents-at-work.md` are drawn from `docs/figures/calls.toml`, one
`[[call]]` entry per spawn: `caller`, `callee`, `at` (the `file:line` of the instruction that
spawns), and optionally `effort`, where the caller sets one other than the callee's own, and
`label`, the text on the edge. `harness test` checks that every caller and callee is an agent of
`agents/` or a skill of `skills/`, that `at` is a line of the caller's own source that names the
callee, and that every source with the tool `agent`, and each skill of SPAWNING_SKILLS, is the
caller of at least one entry.

Each animated walk-through of the site is drawn from one file `docs/figures/walkthrough-<name>.toml`:
its `title`, `subtitle` and `steps` (the edges in the order in which the token runs along them, as
"from -> to"), its `[[box]]` and `[[group]]` entries, and its `[[edge]]` entries, each with `at`,
the `file:line` that states the step. `harness test` checks that each box of the kind `agent` or
`skill` shows an agent of `agents/` or a skill of `skills/`, that each `at` is a line of a file of
the repository, and that the edges and the steps name boxes and edges of the file.
"""

import re
import subprocess
import tomllib

from . import REPO
from .frontmatter import parse_file

PAGES = REPO / "docs" / "src" / "components"
DEPENDENCIES = REPO / "docs" / "src" / "dependencies.md"
CALLS = REPO / "docs" / "figures" / "calls.toml"
# The data of each animated walk-through, and the kinds of its boxes: you, a skill, an agent, a
# step with no agent, an outcome.
WALKTHROUGH = "docs/figures/walkthrough-*.toml"
BOX_KINDS = ("you", "skill", "agent", "step", "outcome")

# The keys of a `[[call]]` entry, the ones it must have, and the values of `effort`.
CALL_KEYS = {"caller", "callee", "at", "effort", "label"}
CALL_REQUIRED = ("caller", "callee", "at")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# The skills that spawn agents from the main session, which has the tool `agent` without a
# `tools:` line.
SPAWNING_SKILLS = ("build-part", "build-reviewed")
# The tables of the dependencies page, in this order, each under a level-2 heading of this text,
# and the header row of each.
TABLES = ("Generic tools", "Julia and its packages", "Optional")
TABLE_HEADER = "| tool | minimum | used for |"

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


def dependency_problems(text):
    """What is wrong with the dependencies page `text`, one phrase each: the tables under the
    level-2 headings, in the order of TABLES, with the header TABLE_HEADER; and the level-3
    headings, whose names, split at ", " and " and ", are the tools of the tables, each once."""
    tables, section, fenced = {}, None, False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif fenced:
            continue
        elif line.startswith("## "):
            section = line[3:]
        elif section is not None and line.startswith("|"):
            tables.setdefault(section, []).append(line)
    problems = []
    if tuple(tables) != TABLES:
        problems.append(f"the tables are under {list(tables)}, not {list(TABLES)}")
    tools = []
    for section, lines in tables.items():
        if lines[0] != TABLE_HEADER:
            problems.append(f"the table of {section!r} has the header {lines[0]!r}")
        tools += [line.split("|")[1].strip() for line in lines[2:]]
    names = [n for h in headings(text, 3) for n in re.split(r", | and ", h)]
    for tool in sorted({t for t in tools if tools.count(t) > 1}):
        problems.append(f"{tool!r} is a row of the tables more than once")
    for tool in sorted(set(tools) - set(names)):
        problems.append(f"{tool!r} is a row of the tables and no heading names it")
    for name in sorted(set(names) - set(tools)):
        problems.append(f"{name!r} is named by a heading and is no row of the tables")
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"{name!r} is named by more than one heading")
    return problems


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


def walkthroughs(paths):
    """The walk-throughs among the tracked `paths`: docs/figures/walkthrough-*.toml."""
    return sorted(p for p in paths if matches(WALKTHROUGH, p))


def walkthrough_problems(data, sources, lines):
    """What is wrong with one walk-through, the TOML table `data`, one phrase each. `sources` maps
    the name of each agent and skill to its source path, and `lines(path)` gives the lines of a file
    of the repository, or None for a path that is none."""
    problems = [f"has no {key!r}" for key in ("title", "subtitle", "steps", "box", "edge") if key not in data]
    boxes, groups = data.get("box", []), data.get("group", [])
    ids = [b.get("id") for b in boxes + groups]
    for name in sorted({i for i in ids if ids.count(i) > 1}, key=str):
        problems.append(f"the id {name!r} is used twice")
    group_ids = {g.get("id") for g in groups}
    for b in boxes:
        name, kind, shows = b.get("id"), b.get("kind"), b.get("shows")
        if kind not in BOX_KINDS:
            problems.append(f"box {name!r} has the kind {kind!r}, none of {', '.join(BOX_KINDS)}")
        elif kind in ("agent", "skill"):
            source = sources.get(shows) if isinstance(shows, str) else None
            if source is None or not source.startswith("agents/" if kind == "agent" else "skills/"):
                problems.append(f"box {name!r} shows {shows!r}, which is no {kind} of {kind}s/")
        if "cell" not in b and b.get("in") not in group_ids:
            problems.append(f"box {name!r} has neither a cell nor a group")
    edges = set()
    for e in data.get("edge", []):
        edge = f"{e.get('from')} -> {e.get('to')}"
        edges.add(edge)
        for end in (e.get("from"), e.get("to")):
            if end not in ids:
                problems.append(f"the edge {edge} names no box {end!r}")
        at = e.get("at")
        place = re.fullmatch(r"(.+):([1-9][0-9]*)", at) if isinstance(at, str) else None
        text = lines(place[1]) if place else None
        if not place:
            problems.append(f"at {at!r} is no file:line")
        elif text is None:
            problems.append(f"at {at!r} names no file of the repository")
        elif int(place[2]) > len(text):
            problems.append(f"at {at!r} is past the end of the file")
    for step in data.get("steps", []):
        if step not in edges:
            problems.append(f"the step {step!r} names no edge")
    return problems


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

    # The rules of the dependencies page on fixed inputs, then the page of this checkout.
    def page(generic="| A | 1 | a |\n| B | 2 | b |\n", heads="### A\n### B and C\n### D, E\n", header=TABLE_HEADER,
             order=TABLES):
        bodies = {"Generic tools": generic, "Julia and its packages": "| C | 3 | c |\n", "Optional": "| D | 4 | d |\n| E | 5 | e |\n"}
        tables = "".join(f"## {t}\n\n{header}\n|:--|:--|:--|\n{bodies[t]}\n" for t in order)
        return f"# Dependencies\n\n{tables}## What each tool does\n\n```\n### Z\n```\n{heads}"
    check(dependency_problems(page()) == [], "a true dependencies page has no problem")
    for label, text, phrase in [
        ("a row removed, its heading kept", page(generic="| A | 1 | a |\n"), "'B' is named by a heading and is no row"),
        ("a heading removed, its row kept", page(heads="### A\n### B and C\n### E\n"), "'D' is a row of the tables and no heading"),
        ("a row twice", page(generic="| A | 1 | a |\n| B | 2 | b |\n| A | 1 | a |\n"), "'A' is a row of the tables more than once"),
        ("a tool in two headings", page(heads="### A\n### B and C\n### D, E\n### A\n"), "'A' is named by more than one heading"),
        ("the tables out of order", page(order=(TABLES[1], TABLES[0], TABLES[2])), "the tables are under"),
        ("another header", page(header="| tool | minimum | needed by |"), "has the header"),
    ]:
        found = dependency_problems(text)
        check(len(found) == (3 if "header" in phrase else 1) and phrase in found[0], f"a dependencies page with {label} gives {phrase!r}: {found}")
    problems = dependency_problems(DEPENDENCIES.read_text()) if DEPENDENCIES.is_file() else ["the page does not exist"]
    check(not problems, "docs/src/dependencies.md: " + ("; ".join(problems) if problems else "its tables and their headings agree"))

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
    paths = tracked()
    sources = call_sources(paths)
    meta = {name: parse_file(REPO / path).meta for name, path in sources.items()}
    calls = tomllib.loads(CALLS.read_text()).get("call", []) if CALLS.is_file() else []
    check(CALLS.is_file() and bool(calls), "docs/figures/calls.toml exists and has [[call]] entries")
    call_cases(calls, sources, meta, lambda path: (REPO / path).read_text().splitlines(), check)

    # The rules of a walk-through on fixed inputs: each wrong entry gives one problem.
    files = {"skills/s/SKILL.md": ["---", "Spawn `a`."], "agents/a.md": ["---"]}
    good = {
        "title": "T", "subtitle": "S", "steps": ["you -> s", "s -> g"],
        "box": [{"id": "you", "cell": [0, 0], "kind": "you", "name": "You"},
                {"id": "s", "cell": [1, 0], "kind": "skill", "shows": "s"},
                {"id": "a", "in": "g", "kind": "agent", "shows": "a"}],
        "group": [{"id": "g", "cell": [2, 0], "name": "G"}],
        "edge": [{"from": "you", "to": "s", "route": ["right", "left"], "at": "skills/s/SKILL.md:2"},
                 {"from": "s", "to": "g", "route": ["right", "left"], "at": "skills/s/SKILL.md:2", "label": "l"}],
    }
    sources = call_sources(["agents/a.md", "skills/s/SKILL.md"])
    check(walkthrough_problems(good, sources, files.get) == [], "a true walk-through has no problem")
    for label, change, phrase in [
        ("an agent renamed", ("box", 2, {"shows": "nonexistent"}), "box 'a' shows 'nonexistent', which is no agent of agents/"),
        ("a skill renamed", ("box", 1, {"shows": "nonexistent"}), "box 's' shows 'nonexistent', which is no skill of skills/"),
        ("a skill as an agent", ("box", 1, {"kind": "agent"}), "box 's' shows 's', which is no agent of agents/"),
        ("an unknown kind", ("box", 0, {"kind": "person"}), "box 'you' has the kind 'person'"),
        ("a cited line past the end", ("edge", 0, {"at": "skills/s/SKILL.md:3"}), "at 'skills/s/SKILL.md:3' is past the end of the file"),
        ("a cited file that does not exist", ("edge", 0, {"at": "skills/t/SKILL.md:1"}), "at 'skills/t/SKILL.md:1' names no file of the repository"),
        ("a citation with no line", ("edge", 0, {"at": "skills/s/SKILL.md"}), "at 'skills/s/SKILL.md' is no file:line"),
        ("an edge to no box", ("edge", 1, {"to": "z"}), "the edge s -> z names no box 'z'"),
        ("a box with no cell", ("box", 1, {"cell": None}), "box 's' has neither a cell nor a group"),
    ]:
        data = {**good, change[0]: [dict(e) for e in good[change[0]]]}
        data[change[0]][change[1]].update(change[2])
        data[change[0]][change[1]] = {k: v for k, v in data[change[0]][change[1]].items() if v is not None}
        found = walkthrough_problems(data, sources, files.get)
        if label == "an edge to no box":
            found = [p for p in found if "names no edge" not in p]
        check(len(found) == 1 and phrase in found[0], f"a walk-through with {label} gives {phrase!r}: {found}")
    found = walkthrough_problems({**good, "steps": ["you -> s", "a -> you"]}, sources, files.get)
    check(found == ["the step 'a -> you' names no edge"], f"a step that names no edge is a problem: {found}")
    found = walkthrough_problems({k: v for k, v in good.items() if k != "title"}, sources, files.get)
    check(found == ["has no 'title'"], f"a walk-through with no title is a problem: {found}")

    # The walk-throughs of this checkout.
    walks = walkthroughs(paths)
    check(len(walks) >= 4, f"docs/figures/ has at least four walk-throughs: {walks}")
    known = set(paths)
    lines = lambda path: (REPO / path).read_text().splitlines() if path in known else None
    for path in walks:
        problems = walkthrough_problems(tomllib.loads((REPO / path).read_text()), call_sources(paths), lines)
        check(not problems, f"{path}" + (": " + "; ".join(problems) if problems else ": its boxes and cited lines exist"))
    return total, wrong
