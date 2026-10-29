"""`harness wiki-lint`: the structural lint of the Markdown that carries claims and cross
references.

    harness wiki-lint                    # the four trees
    harness wiki-lint Knowledge          # one of them
    harness wiki-lint --strict           # warnings fail too
    harness wiki-lint --quiet            # the errors, the counts and the totals only

The trees are the two vaults `Knowledge/` and `Environment/` and the two reference trees `Tasks/`
and `Library/` below the research root, $RESEARCH_ROOT, else ~/Research: the `SCOPES` below.

A **vault** is a wiki: one claim per page and `[[wiki-links]]`. It gets every check. A **reference
tree** is a work queue (`Tasks/`) or a catalogue of other people's papers (`Library/`), dense in
paths into the rest of the tree; it gets the checks of paths and line citations, and `Tasks/` also
gets the schema of the task board. Every check is deterministic and reads the working tree: no
model, no index, no network.

The checks, numbered as the comments below number them:

  1     a frontmatter block that never closes, does not parse, or repeats a key: ERROR
  2-4   `verified:` that is no YYYY-MM-DD date, and each `depends_on` entry that is no mapping,
        has no `path`, names a missing path or an anchor that its file no longer holds: ERROR; a
        dependency whose file changed after `verified:` (the UTC date of its mtime): WARN
  5     a `checks:` file that does not exist: ERROR
  6     a wiki-link broken across a newline, or one from a vault into the other vault: ERROR; one
        from a reference tree into a vault: WARN; one that names no page: WARN
  7     a vault page that nothing links to: WARN
  8-9   a backticked path that does not exist: WARN; a line citation past the end of its file:
        ERROR
  10    a generated block with no generator: WARN
  13    a topic of `Knowledge/` without its `Projects/` counterpart, and the reverse: WARN
  14    the task board's schema in `Tasks/`
  scope a tree that holds no Markdown: ERROR

Each `CHANGELOG.md` is skipped; `Tasks/Archive/`, `Tasks/Evidence/` and each directory that holds
a `.lint-records` file are records, which the checks of paths, line citations and unwritten links
skip. ERROR is a claim that is certainly false with an unambiguous fix; WARN needs a person.

A frontmatter is YAML, read by PyYAML through `FrontmatterLoader`, a `SafeLoader` that keeps a
date as its text, refuses a duplicate key (an ERROR on the line of the second key), and records
each mapping value that YAML 1.1 converts where YAML 1.2 keeps the text or reads another value,
such as `no`, `on`, `0755` or `1:30` (a WARN that names the key and the converted value). Both
findings belong to the checks of the vaults' frontmatter and of the task board; the lint also
reads the frontmatter of `Library/` for its `aliases`, and reports nothing there. PyYAML is
imported when the first frontmatter is read, so an environment synced without it fails only this
subcommand.

The output is one line per finding, `<SEVERITY>  [<check>]  <file>[:<line>] — <message>`, sorted
by severity, check, file and line, then a table of the counts by check and the totals. The exit
status is 0 without an ERROR (and, under --strict, without a WARN), 1 with one, and 2 for a tree
name that is no directory and for an environment without PyYAML.

The selftest's cases (part `wikilint`) build research roots in a temporary directory: one or
more cases for each check, each decision on the edges of YAML, and the hook
`githooks/pre-commit-wiki`, committed in scratch repositories with stubs of ruff and basedpyright.
"""

import argparse
import bisect
import dataclasses
import datetime
import functools
import math
import os
import pathlib
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Callable, Hashable
from typing import TYPE_CHECKING, Any, ClassVar, cast, override
from unittest import mock

from . import REPO, HarnessError, environment, fmt, strict

if TYPE_CHECKING:
    import yaml

# Order matters only for the report. A vault gets every check, a reference tree the paths and the
# line citations.
SCOPES = [("Knowledge", "vault"), ("Environment", "vault"), ("Tasks", "refs"), ("Library", "refs")]

# A backticked span that starts with one of these is a path into the tree.
PATH_PREFIXES = (
    "~/Research/",
    "~/.claude/",
    "Knowledge/",
    "Environment/",
    "Packages/",
    "Experiments/",
    "Papers/",
    "Books/",
    "Projects/",
    "Tasks/",
    "Library/",
    "Bibliography/",
    "Latex/",
    "Talks/",
)
SKIP_DIRS = frozenset({".git", ".obsidian", ".claude", "vendor", "__pycache__"})

LINK_RE = re.compile(r"\[\[([^\]|#]+?)\]\]")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
GEN_OPEN_RE = re.compile(r"<!--\s*generated:\s*([A-Za-z0-9_-]+)\s*-->")
WHITESPACE_RE = re.compile(r"\s+")
# `file:12`, and a range `file:12-25` with a hyphen or an en dash.
CITATION_RE = re.compile(r"^(.*?):(\d+)(?:[-\N{EN DASH}](\d+))?$")
CITATION_SUFFIX_RE = re.compile(r":\d+(?:[-\N{EN DASH}]\d+)?$")
FLAG_RE = re.compile(r" --?[A-Za-z]")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# A span holding any of these is a pattern or a placeholder, not a path that must resolve. A space
# is not among them: many directories of the tree have one in their name.
NOT_A_PATH = frozenset("*?<>{}…")

# Records: a closed task and the reports a plan rests on state what was true when they were
# written, so the checks of paths, line citations and unwritten links skip them.
RECORDS = ("Tasks/Archive/", "Tasks/Evidence/")

# Two directories are ephemeral by rule: `.worktrees/` holds temporary checkouts and `.scratch/`
# logs. A page that names one that is gone describes what was done.
EPHEMERAL = ("~/Research/.worktrees/", "~/Research/.scratch/", ".worktrees/", ".scratch/")

# A backticked directory links the pages below it from this many path parts on, the vault's own
# name included.
DIRECTORY_DEPTH = 3

TASK_STATUSES = ("wip", "next", "incoming", "backlog", "done")
TASK_NOT_TASKS = ("README.md", "CLAUDE.md")

# The `stop` of a frontmatter that opens and never closes, and of one that PyYAML refuses.
UNCLOSED, REFUSED = -1, -2

TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"
BOOL_TAG, INT_TAG, FLOAT_TAG = "tag:yaml.org,2002:bool", "tag:yaml.org,2002:int", "tag:yaml.org,2002:float"
# YAML 1.2's core schema, against which a YAML 1.1 value is a conversion.
CORE_BOOL = {"true": True, "True": True, "TRUE": True, "false": False, "False": False, "FALSE": False}
# (the form of a number, its value), in the order of the core schema's resolution.
CORE_NUMBERS: list[tuple[re.Pattern[str], Callable[[str], object]]] = [
    (re.compile(r"[-+]?[0-9]+"), int),
    (re.compile(r"0o[0-7]+"), lambda t: int(t[2:], 8)),
    (re.compile(r"0x[0-9a-fA-F]+"), lambda t: int(t[2:], 16)),
    (re.compile(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?"), float),
    (re.compile(r"[-+]?\.(?:inf|Inf|INF)"), lambda t: -math.inf if t.startswith("-") else math.inf),
    (re.compile(r"\.(?:nan|NaN|NAN)"), lambda _: math.nan),
]


@dataclasses.dataclass(frozen=True)
class Finding:
    severity: str  # "error" or "warn"
    check: str
    file: str  # relative to the research root
    line: int  # 0 when the finding is about the file as a whole
    message: str


@dataclasses.dataclass(frozen=True)
class Conversion:
    """A mapping value that YAML 1.1 reads otherwise than YAML 1.2: its key, its text, the value
    that PyYAML gives, and its 0-based line in the YAML block."""

    key: str
    text: str
    value: object
    line: int


@dataclasses.dataclass(frozen=True)
class YamlRead:
    """What `yaml_reader()` makes of a YAML block: the value, or a refusal with its 0-based line in
    the block and the key that the block repeats (None for a block that does not parse)."""

    data: object
    refused: bool = False
    line: int = -1
    duplicate: str | None = None
    conversions: tuple[Conversion, ...] = ()


@dataclasses.dataclass(frozen=True)
class Front:
    """The frontmatter of a page: its mapping ({} for none, a list, a scalar or a refusal), and
    `stop`, the line of its closing `---`, 0 without a frontmatter, UNCLOSED or REFUSED. A refusal
    carries its line in the file and the repeated key, if any."""

    data: dict[object, object]
    stop: int
    line: int = 1
    duplicate: str | None = None
    conversions: tuple[Conversion, ...] = ()


def shown(value: object) -> str:
    """The text of a frontmatter value in a message: a string as it is, `true` and `false`,
    `nothing` for an empty value, `Inf` and `NaN`, a list as `Any[…]` and a mapping as
    `Dict{Any, Any}(…)`, the forms that Julia's `string` gives."""
    match value:
        case bool():
            text = "true" if value else "false"
        case None:
            text = "nothing"
        case float() if math.isnan(value) or math.isinf(value):
            text = "NaN" if math.isnan(value) else "Inf" if value > 0 else "-Inf"
        case list():
            text = "Any[" + ", ".join(quoted(x) for x in cast("list[object]", value)) + "]"
        case dict():
            pairs = cast("dict[object, object]", value).items()
            text = "Dict{Any, Any}(" + ", ".join(f"{quoted(k)} => {quoted(v)}" for k, v in pairs) + ")"
        case _:
            text = str(value)
    return text


def quoted(value: object) -> str:
    """`shown`, with a string in double quotes, as an element of a list or a mapping."""
    return f'"{value}"' if isinstance(value, str) else shown(value)


def entries(value: object) -> list[object]:
    """The items that a `for` over a frontmatter value visits: a list's items, a string's
    characters, a mapping's pairs as text, nothing for an empty value, else the value itself."""
    match value:
        case None:
            return []
        case list():
            return list(cast("list[object]", value))
        case str():
            return list(value)
        case dict():
            pairs = cast("dict[object, object]", value).items()
            return [f"{quoted(k)} => {quoted(v)}" for k, v in pairs]
        case _:
            return [value]


def core_value(text: str) -> object:
    """The value of a plain scalar under YAML 1.2's core schema for the bool, int and float forms,
    else the text itself."""
    if text in CORE_BOOL:
        return CORE_BOOL[text]
    for pattern, value in CORE_NUMBERS:
        if pattern.fullmatch(text):
            return value(text)
    return text


def same_value(a: object, b: object) -> bool:
    """Whether two scalars are one value; NaN equals NaN."""
    return a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))


@functools.cache
def yaml_reader() -> Callable[[str], YamlRead]:
    """The reader of a YAML block, on PyYAML: imported here, so that an environment without PyYAML
    fails only `harness wiki-lint`, with one line."""
    try:
        import yaml  # noqa: PLC0415 -- a stale environment fails only this subcommand
    except ImportError as e:
        raise HarnessError(
            "PyYAML is not in the harness's Python environment; run harness install --apply"
        ) from e

    class FrontmatterLoader(yaml.SafeLoader):
        """A SafeLoader that keeps a date as its text, refuses a duplicate key and records each
        mapping value that YAML 1.1 converts."""

        yaml_implicit_resolvers: ClassVar = {
            first: [(tag, regexp) for tag, regexp in resolvers if tag != TIMESTAMP_TAG]
            for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
        }

        def __init__(self, stream: str) -> None:
            super().__init__(stream)
            self.duplicate: str | None = None
            self.conversions: list[Conversion] = []

        @override
        def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
            converted: dict[str, Callable[[yaml.ScalarNode], object]] = {
                BOOL_TAG: self.construct_yaml_bool,
                INT_TAG: self.construct_yaml_int,
                FLOAT_TAG: self.construct_yaml_float,
            }
            seen: set[tuple[str, str]] = set()
            for key_node, value_node in node.value:
                if not isinstance(key_node, yaml.ScalarNode):
                    continue
                key = cast("str", key_node.value)
                if (key_node.tag, key) in seen:
                    self.duplicate = key
                    raise yaml.constructor.ConstructorError(
                        None, None, f"duplicate key `{key}`", key_node.start_mark
                    )
                seen.add((key_node.tag, key))
                # A plain scalar that the resolver of YAML 1.1 makes a bool, an int or a float.
                if (
                    isinstance(value_node, yaml.ScalarNode)
                    and value_node.style is None
                    and value_node.tag in converted
                ):
                    text = cast("str", value_node.value)
                    value = converted[value_node.tag](value_node)
                    if not same_value(core_value(text), value):
                        self.conversions.append(Conversion(key, text, value, value_node.start_mark.line))
            return super().construct_mapping(node, deep=deep)

    def read(body: str) -> YamlRead:
        loader = FrontmatterLoader(body)
        try:
            data: object = loader.get_single_data()
        except yaml.MarkedYAMLError as e:
            mark = e.problem_mark or e.context_mark
            return YamlRead(None, refused=True, line=mark.line if mark else -1, duplicate=loader.duplicate)
        except yaml.YAMLError:
            return YamlRead(None, refused=True)
        return YamlRead(data, conversions=tuple(loader.conversions))

    return read


def frontmatter(text: str) -> Front:
    """The YAML block delimited by `---` on the first line and the next line that is `---`."""
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return Front({}, 0)
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        return Front({}, UNCLOSED)
    got = yaml_reader()("\n".join(lines[1:close]))
    if got.refused:
        # The block starts on line 2 of the file; a refusal without a mark is on line 1.
        line = got.line + 2 if got.line >= 0 else 1
        return Front({}, REFUSED, line, got.duplicate)
    data = cast("dict[object, object]", got.data) if isinstance(got.data, dict) else {}
    return Front(data, close + 1, conversions=got.conversions)


# ---------------------------------------------------------------------------------------------
# Paths


def file_mode(path: str) -> int | None:
    """The mode of `path`, following links, or None when it does not exist. A path that ends in
    `/` exists only as a directory."""
    try:
        mode = pathlib.Path(path).stat().st_mode
    except OSError, ValueError:
        return None
    return mode if not path.endswith("/") or stat.S_ISDIR(mode) else None


def exists(path: str) -> bool:
    """Whether `path` exists, by `access(F_OK)`: a path whose metadata a sandbox refuses to read
    still exists, and `file/` does not."""
    try:
        return os.access(path, os.F_OK)
    except ValueError:  # a NUL in the path
        return False


def is_file(path: str) -> bool:
    mode = file_mode(path)
    return mode is not None and stat.S_ISREG(mode)


def is_dir(path: str) -> bool:
    mode = file_mode(path)
    return mode is not None and stat.S_ISDIR(mode)


def countlines(path: str) -> int:
    """The lines of a file, a last line without a newline included."""
    data = pathlib.Path(path).read_bytes()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


@dataclasses.dataclass(frozen=True)
class Root:
    """The research root, as text without a trailing `/`."""

    path: str

    def resolve(self, p: str) -> str:
        """An absolute path for a tree-relative or `~`-relative path spelt in prose."""
        if p.startswith("~/"):
            return f"{pathlib.Path.home()}/{p[2:]}"
        return p if p.startswith("/") else f"{self.path}/{p}"

    def relative(self, path: str) -> str | None:
        """`path` relative to the root, after `..` and `.` are folded; None outside the root."""
        normed = posixpath.normpath(path)
        base = posixpath.normpath(self.path)
        return normed[len(base) + 1 :] if normed.startswith(base + "/") else None

    def walk(self, scope: str) -> list[tuple[str, list[str]]]:
        """(directory relative to the root, its files) of each directory below `scope`, without
        SKIP_DIRS; a link to a directory is not entered."""
        out: list[tuple[str, list[str]]] = []
        base = f"{self.path}/{scope}"
        for directory, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            out.append((posixpath.normpath(scope + directory[len(base) :]), files))
        return out


def markdown_files(root: Root, scope: str) -> list[str]:
    """Every `.md` file below `scope` except each `CHANGELOG.md`, relative to the root, sorted."""
    return sorted(
        f"{d}/{f}"
        for d, files in root.walk(scope)
        for f in files
        if f.endswith(".md") and f != "CHANGELOG.md"
    )


def records_dirs(root: Root, scope: str) -> list[str]:
    """Every directory below `scope` that holds a `.lint-records` file, relative to the root."""
    return [f"{d}/" for d, files in root.walk(scope) if ".lint-records" in files]


# ---------------------------------------------------------------------------------------------
# Extraction


def blank_code(text: str) -> str:
    """`text` with the content of every backticked span replaced by spaces, so that a `[[…]]` in
    code is no link and the offsets stay."""
    return BACKTICK_RE.sub(lambda m: "`" + " " * (len(m[0]) - 2) + "`", text)


def wiki_links(text: str) -> list[tuple[int, str, bool]]:
    """(line, target, wrapped) of every `[[target]]`; `wrapped` says it spans a newline."""
    src = blank_code(text)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    out: list[tuple[int, str, bool]] = []
    for m in LINK_RE.finditer(src):
        raw = m[1]
        target = nfc(WHITESPACE_RE.sub(" ", raw.strip()))
        if target:
            out.append((bisect.bisect_right(starts, m.start()), target, "\n" in raw))
    return out


def prose_paths(text: str) -> list[tuple[int, str]]:
    """(line, span) of the backticked spans that name a path into the tree and could resolve."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(text.split("\n"), 1):
        for m in BACKTICK_RE.finditer(line):
            s = m[1].strip()
            if (
                s.startswith(PATH_PREFIXES)
                and not any(c in NOT_A_PATH for c in s)
                and not s.startswith(EPHEMERAL)
                and not s.endswith("...")
            ):
                out.append((i, s))
    return out


def command_head(s: str) -> str:
    """The path a command span starts with: `s` up to its first flag."""
    return FLAG_RE.split(s, maxsplit=1)[0].strip().rstrip("/")


# ---------------------------------------------------------------------------------------------
# The checks


@dataclasses.dataclass
class Tree:
    """A tree of the run: its name, kind, files, texts and the frontmatter of each file, read once."""

    name: str
    kind: str
    files: list[str]
    texts: dict[str, str]
    fronts: dict[str, Front] = dataclasses.field(default_factory=dict[str, Front])

    def front(self, f: str) -> Front:
        if f not in self.fronts:
            self.fronts[f] = frontmatter(self.texts[f])
        return self.fronts[f]

    def names(self) -> dict[str, str]:
        """Every string that resolves to a page of this tree: its basename, its path within the
        tree, and each alias of its frontmatter."""
        names: dict[str, str] = {}
        for f in self.files:
            names[nfc(posixpath.splitext(posixpath.basename(f))[0])] = f
            names[nfc(posixpath.splitext(f.removeprefix(self.name.rstrip("/") + "/"))[0])] = f
            for a in entries(self.front(f).data.get("aliases")):
                names[nfc(shown(a))] = f
        return names


def front_findings(f: str, front: Front, check: str, refusal: str, findings: list[Finding]) -> bool:
    """The finding of a block that does not close, does not parse or repeats a key, which ends the
    checks of the page (True), else one finding per YAML 1.1 conversion. `check` names the check
    of the refusal, and `refusal` its message for a block that does not close or does not parse."""
    if front.stop in {UNCLOSED, REFUSED}:
        if front.duplicate is not None:
            findings.append(
                Finding("error", check, f, front.line, f"YAML block repeats the key `{front.duplicate}`")
            )
        else:
            findings.append(Finding("error", check, f, front.line, refusal))
        return True
    findings.extend(
        Finding(
            "warn",
            "frontmatter",
            f,
            c.line + 2,
            f"`{c.key}: {c.text}` is {shown(c.value)} in YAML 1.1; quote it to keep the text",
        )
        for c in front.conversions
    )
    return False


def verified_date(fm: dict[object, object]) -> str | None:
    """The `verified:` date as YYYY-MM-DD text, or None when it is absent or no such date."""
    text = shown(fm["verified"])
    if not DATE_RE.fullmatch(text):
        return None
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return None
    return text


def check_frontmatter(root: Root, f: str, front: Front, findings: list[Finding]) -> None:
    """Checks 1-5 on one page of a vault."""
    if front.stop == UNCLOSED:
        findings.append(Finding("error", "frontmatter", f, 1, "opens `---` and never closes it"))
        return
    if front_findings(f, front, "frontmatter", "YAML block does not parse", findings):
        return
    fm = front.data

    # --- 2, 3, 4: declared dependencies
    page_time = verified_date(fm) if "verified" in fm else None
    if "verified" in fm and page_time is None:
        findings.append(
            Finding(
                "error", "frontmatter", f, 0, f"`verified: {shown(fm['verified'])}` is not a YYYY-MM-DD date"
            )
        )
    for dep in entries(fm.get("depends_on", [])):
        if not isinstance(dep, dict):
            findings.append(
                Finding("error", "depends-on", f, 0, f"`depends_on` entry is not a mapping: {shown(dep)}")
            )
            continue
        entry = cast("dict[object, object]", dep)
        p = entry.get("path")
        if p is None:
            findings.append(Finding("error", "depends-on", f, 0, "`depends_on` entry has no `path`"))
            continue
        target = root.resolve(shown(p))
        if not exists(target):
            findings.append(Finding("error", "depends-on", f, 0, f"`{shown(p)}` does not exist"))
            continue
        anchor = entry.get("anchor")
        if (
            anchor is not None
            and is_file(target)
            and shown(anchor).encode() not in pathlib.Path(target).read_bytes()
        ):
            findings.append(
                Finding("error", "anchor", f, 0, f'`{shown(p)}` no longer contains "{shown(anchor)}"')
            )
        if page_time is not None and is_file(target):
            changed = datetime.datetime.fromtimestamp(pathlib.Path(target).stat().st_mtime, tz=datetime.UTC)
            if changed.date().isoformat() > page_time:
                findings.append(
                    Finding("warn", "stale", f, 0, f"`{shown(p)}` changed after `verified: {page_time}`")
                )

    # --- 5: cited checks
    findings.extend(
        Finding("error", "checks", f, 0, f"`{shown(c)}` does not exist")
        for c in entries(fm.get("checks", []))
        if not is_file(root.resolve(shown(c)))
    )


def lint_scope(
    root: Root, tree: Tree, names: dict[str, str], elsewhere: dict[str, str], findings: list[Finding]
) -> None:
    """Checks 1-10 on one tree, in the order of their numbers, which is the order of two findings
    with the same severity, check, file and line in the report."""
    if not tree.files:
        findings.append(Finding("error", "scope", tree.name, 0, "holds no Markdown"))
        return
    if tree.kind == "vault":
        for f in tree.files:
            check_frontmatter(root, f, tree.front(f), findings)
    records = (*RECORDS, *records_dirs(root, tree.name))
    inbound = link_findings(tree, names, elsewhere, records, findings)
    if tree.kind == "vault":
        orphan_findings(root, tree, inbound, findings)
    path_findings(root, tree, records, findings)
    for f in tree.files:
        findings.extend(
            Finding("warn", "generated", f, i, f"generated block `{m[1]}` has no generator yet")
            for i, line in enumerate(tree.texts[f].split("\n"), 1)
            if (m := GEN_OPEN_RE.search(line))
        )


def link_findings(
    tree: Tree,
    names: dict[str, str],
    elsewhere: dict[str, str],
    records: tuple[str, ...],
    findings: list[Finding],
) -> dict[str, int]:
    """6: wiki-links resolve; the number of links to each page of the tree from its other pages. A
    link to a page that does not exist yet is a marker of something worth writing; a link into the
    other vault is an error inside a vault and a warning from a reference tree; a link broken
    across a newline is an error. A record keeps its unwritten links."""
    vault = tree.kind == "vault"
    inbound = dict.fromkeys(tree.files, 0)
    for f in tree.files:
        for ln, target, wrapped in wiki_links(tree.texts[f]):
            here = names.get(target)
            if wrapped:
                findings.append(
                    Finding(
                        "error",
                        "link-wrapped",
                        f,
                        ln,
                        f"[[{target}]] is broken across a newline, so it resolves to nothing"
                        + ("" if here is None else " — the page exists"),
                    )
                )
                if here is not None and here != f:
                    inbound[here] += 1
            elif here is not None:
                if here != f:
                    inbound[here] += 1
            elif target in elsewhere:
                findings.append(
                    Finding(
                        "error" if vault else "warn",
                        "link-crossvault",
                        f,
                        ln,
                        f"[[{target}]] is in another vault, at `{elsewhere[target]}`"
                        + ("" if vault else " — Obsidian will not follow it from here"),
                    )
                )
            elif not f.startswith(records):
                findings.append(
                    Finding(
                        "warn", "link-unwritten", f, ln, f"[[{target}]] names no page — a marker, or a typo"
                    )
                )
    return inbound


def orphan_findings(root: Root, tree: Tree, inbound: dict[str, int], findings: list[Finding]) -> None:
    """7: the pages of a vault that nothing links to. A backticked path to a page links it, and so
    does one to a directory above it at DIRECTORY_DEPTH or deeper: a top-level directory is a
    section of the wiki, and one mention of it would link every page there."""
    fileset = set(tree.files)
    for f in tree.files:
        for m in BACKTICK_RE.finditer(tree.texts[f]):
            s = CITATION_SUFFIX_RE.sub("", m[1].strip()).rstrip("/")
            if not s or any(c in NOT_A_PATH for c in s):
                continue
            target = (
                root.resolve(s)
                if s.startswith(PATH_PREFIXES)
                else str(pathlib.Path(root.path, posixpath.dirname(f), s))
            )
            rel = root.relative(target)
            if rel is None:
                continue
            if rel in fileset:
                if rel != f:
                    inbound[rel] += 1
            elif (
                rel.startswith(tree.name + "/") and len(rel.split("/")) >= DIRECTORY_DEPTH and is_dir(target)
            ):
                for g in tree.files:
                    if g.startswith(rel + "/") and g != f:
                        inbound[g] += 1
    findings.extend(
        Finding("warn", "orphan", f, 0, "no inbound link")
        for f in tree.files
        if posixpath.basename(f) != "README.md" and inbound[f] == 0
    )


def path_findings(root: Root, tree: Tree, records: tuple[str, ...], findings: list[Finding]) -> None:
    """8, 9: the paths and the line citations in prose, outside the records."""
    for f in tree.files:
        if f.startswith(records):
            continue
        for ln, raw in prose_paths(tree.texts[f]):
            p = raw.rstrip("/")
            m = CITATION_RE.match(p)
            if m:
                target = root.resolve(m[1])
                n = int(m[3] or m[2])
                if not is_file(target):
                    findings.append(Finding("warn", "path", f, ln, f"`{m[1]}` does not exist"))
                else:
                    total = countlines(target)
                    if total < n:
                        findings.append(
                            Finding(
                                "error", "line-citation", f, ln, f"`{p}` names line {n}; the file has {total}"
                            )
                        )
            elif not exists(root.resolve(p)) and not exists(root.resolve(command_head(p))):
                findings.append(Finding("warn", "path", f, ln, f"`{raw}` does not exist"))


def lint_mirror(root: Root, findings: list[Finding]) -> None:
    """13: each topic directory of `Knowledge/` and of `Projects/` has its counterpart."""
    k, p = f"{root.path}/Knowledge", f"{root.path}/Projects"
    if not (is_dir(k) and is_dir(p)):
        return

    def topics(d: str) -> set[str]:
        # A dot-directory is never a topic.
        return {
            nfc(x.name)
            for x in pathlib.Path(d).iterdir()
            if is_dir(f"{d}/{x.name}") and not x.name.startswith(".") and x.name not in SKIP_DIRS
        }

    kt, pt = topics(k), topics(p)
    findings.extend(
        Finding("warn", "mirror", f"Knowledge/{t}", 0, "no `Projects/` counterpart") for t in sorted(kt - pt)
    )
    findings.extend(
        Finding("warn", "mirror", f"Projects/{t}", 0, "no `Knowledge/` counterpart") for t in sorted(pt - kt)
    )


def lint_tasks(tree: Tree, findings: list[Finding]) -> None:
    """14: the task board's schema. `Tasks/Board.base` groups the task files by `status`, so a typo
    there makes a phantom column. An unknown value and a file in the wrong folder for its status
    are errors; the rest are warnings. `Tasks/Evidence/` holds no task files."""
    for f in tree.files:
        parts = f.split("/")[1:]
        if posixpath.basename(f) in TASK_NOT_TASKS or parts[0] == "Evidence":
            continue
        archived = parts[:-1] == ["Archive"]
        if not (len(parts) == 1 or archived):
            findings.append(
                Finding("error", "task-status", f, 0, "task files live in `Tasks/` or `Tasks/Archive/` only")
            )
            continue
        front = tree.front(f)
        if front_findings(f, front, "task-status", "frontmatter does not close or does not parse", findings):
            continue
        fm = front.data
        if "created" not in fm:
            findings.append(Finding("warn", "task-status", f, 0, "no `created:`"))
        if fm.get("status") is None:
            findings.append(Finding("warn", "task-status", f, 0, "no `status:`"))
            continue
        status = shown(fm["status"])
        if status not in TASK_STATUSES:
            findings.append(
                Finding(
                    "error",
                    "task-status",
                    f,
                    0,
                    f"`status: {status}` is not one of {' | '.join(TASK_STATUSES)}",
                )
            )
            continue
        if archived != (status == "done"):
            findings.append(
                Finding(
                    "error",
                    "task-status",
                    f,
                    0,
                    f"is in `Archive/` but `status: {status}`"
                    if archived
                    else "`status: done` belongs in `Archive/`",
                )
            )
        if status == "wip" and "started" not in fm:
            findings.append(Finding("warn", "task-status", f, 0, "`status: wip` without `started:`"))


def research_root() -> Root:
    return Root(
        str(pathlib.Path(os.environ.get("RESEARCH_ROOT") or pathlib.Path.home() / "Research")).rstrip("/")
        or "/"
    )


def lint(root: Root, named: list[str]) -> tuple[list[Finding], list[str]]:
    """The sorted findings over the trees `named`, every tree of SCOPES when there is none, and
    the trees. A name that is no directory below the root raises."""
    vaults = named or [name for name, _ in SCOPES]
    for v in vaults:
        if not is_dir(f"{root.path}/{v}"):
            raise HarnessError(f"no such vault: {v}")
    kinds = dict(SCOPES)
    trees: dict[str, Tree] = {}
    for v in vaults:
        files = markdown_files(root, v)
        texts = {f: pathlib.Path(root.path, f).read_bytes().decode("utf-8", "replace") for f in files}
        trees[v] = Tree(v, kinds.get(v, "refs"), files, texts)
    names = {v: trees[v].names() for v in vaults}

    findings: list[Finding] = []
    for v in vaults:
        # A link resolves against every vault but this one; a reference tree holds no pages to
        # link to.
        elsewhere: dict[str, str] = {}
        for w in vaults:
            if w != v and kinds.get(w) == "vault":
                elsewhere.update(names[w])
        lint_scope(root, trees[v], names[v], elsewhere, findings)
    if "Knowledge" in vaults:
        lint_mirror(root, findings)
    if "Tasks" in vaults:
        lint_tasks(trees["Tasks"], findings)
    findings.sort(key=lambda f: (0 if f.severity == "error" else 1, f.check, f.file, f.line))
    return findings, vaults


def report(findings: list[Finding], vaults: list[str], *, strict: bool, quiet: bool) -> tuple[str, int]:
    """The text of the report, and the exit status."""
    errors = sum(f.severity == "error" for f in findings)
    out: list[str] = []
    if not quiet or errors > 0:
        for f in findings:
            if f.severity == "warn" and quiet:
                continue
            where = f.file if f.line == 0 else f"{f.file}:{f.line}"
            out.append(f"{f.severity.upper()}  [{f.check}]  {where} — {f.message}")
        if findings:
            out.append("")
    by_check: dict[tuple[str, str], int] = {}
    for f in findings:
        by_check[f.severity, f.check] = by_check.get((f.severity, f.check), 0) + 1
    out.append("by check:")
    # The most first, then by check. The table is filled from the sorted findings, so where one
    # check has as many ERRORs as WARNs, the stable sort keeps the ERRORs first.
    for (severity, check), n in sorted(by_check.items(), key=lambda x: (-x[1], x[0][1])):
        out.append(f"  {check:<16} {severity:<6} {n}")
    out.extend(["", f"{errors} error(s), {len(findings) - errors} warning(s) over {', '.join(vaults)}."])
    failing = len(findings) if strict else errors
    return "\n".join(out) + "\n", 0 if failing == 0 else 1


def cmd_wiki_lint(args: argparse.Namespace, root: Root | None = None) -> int:
    findings, vaults = lint(root or research_root(), cast("list[str]", args.trees))
    text, code = report(findings, vaults, strict=cast("bool", args.strict), quiet=cast("bool", args.quiet))
    sys.stdout.write(text)
    return code


def register(sub: fmt.Subcommands) -> None:
    p = sub.add_parser(
        "wiki-lint",
        help="lint the Markdown of the prose trees: links, paths, line citations, frontmatter",
        description="Check the vaults Knowledge and Environment and the reference trees Tasks and "
        "Library below $RESEARCH_ROOT (else ~/Research), or the TREEs named. Prints one line per "
        "finding, ERROR or WARN, then the counts by check and the totals. Exits 0 without an ERROR "
        "(and, with --strict, without a WARN), 1 with one, 2 for a TREE that is no directory.",
    )
    p.add_argument(
        "trees", nargs="*", metavar="TREE", help="a tree below the research root; all four without one"
    )
    p.add_argument("--strict", action="store_true", help="fail on a WARN too")
    p.add_argument(
        "--quiet", action="store_true", help="print no WARN line, and the ERROR lines only when there is one"
    )
    p.set_defaults(run=cmd_wiki_lint)


# ---------------------------------------------------------------------------------------------
# The selftest

HOOK = REPO / "githooks" / "pre-commit-wiki"
TIMEOUT = 120  # seconds for each git commit of the hook cases

# The research root of the rule cases. A.md's frontmatter takes lines 1-16 and its heading line 17,
# so its links start on line 18. p.jl has five lines and no final newline; even.jl has three.
RULES = {
    "Knowledge/README.md": (
        "# K\n\n[[A]] [[Pages]] [[Cafe\N{COMBINING ACUTE ACCENT}]] [[Dup]] [[Bad]] [[Conv]]"
        " [[Dates]] [[Dates2]] [[Dates3]] [[Dates4]] [[Unclosed]] [[Near]] [[Quoted]]\n"
    ),
    "Knowledge/Notes/A.md": (
        "---\naliases: [Alpha]\nverified: 2026-01-01\ndepends_on:\n  - path: Packages/P/p.jl\n"
        '    anchor: "function p"\n  - path: Packages/P/p.jl\n    anchor: absent\n'
        "  - path: Packages/P/gone.jl\n  - anchor: x\n  - plain\n  - [a, b]\nchecks:\n"
        "  - Packages/P/p.jl\n  - Packages/P/none.jl\n---\n# A\n"
        "Links: [[B]], [[Alpha]], [[Env Page]], [[Nowhere]], [[Wr\n"
        "apped]] and [[Two\n"
        "Words]] and `[[Code]]`.\n"
        "Paths: `Packages/P/p.jl:5`, `Packages/P/p.jl:2-6`, `Packages/P/even.jl:3`, `Packages/P/even.jl:4`.\n"
        "`Packages/P/missing.jl:4`, `Packages/P/run.jl --apply`, `Packages/P/nothing/`, `Packages/P/`.\n"
        "`Packages/*/x`, `Packages/<n>/x`, `~/Research/.scratch/x`, `.worktrees/y`, `Packages/x...`.\n"
        "<!-- generated: table-one -->\n"
    ),
    "Knowledge/Notes/B.md": (
        "# B\n\n[[A]], the directory `Knowledge/Notes/Deep/` and `Rel.md`.\n"
        "The section `Knowledge/Notes/` and [[Good]], a task file.\n"
    ),
    "Knowledge/Notes/Two Words.md": "# Two Words\n",
    "Knowledge/Notes/Café.md": "# Café\n",
    "Knowledge/Notes/Rel.md": "# Rel\n",
    "Knowledge/Notes/Deep/Sub/L.md": "# L\n",
    "Knowledge/Notes/Orphan.md": "# Orphan\n\nOnly `Orphan.md` names me.\n",
    "Knowledge/Notes/Self/S/Only.md": "# Only\n\n`Knowledge/Notes/Self/` holds me alone.\n",
    "Knowledge/Notes/Pages.md": "---\ntitle: Pages\n---\n# Pages\n",
    "Knowledge/Notes/Dup.md": "---\ntitle: a\ntitle: b\n---\n# Dup\n",
    "Knowledge/Notes/Bad.md": "---\ntitle: a\nbad: value: other\n---\n# Bad\n",
    "Knowledge/Notes/Conv.md": (
        "---\ndraft: no\nflag: on\nmode: 0755\ntime: 1:30\nbig: 1_000\nhex: 0x1F\nyes12: true\nn: 12\n"
        'q: "no"\nf: 1.5\nd: 2026-01-01\ndeps:\n  - anchor: off\n---\n# Conv\n'
    ),
    "Knowledge/Notes/Dates.md": "---\nverified: 2026-9-1\n---\n",
    "Knowledge/Notes/Dates2.md": "---\nverified: 2026-02-30\n---\n",
    "Knowledge/Notes/Dates3.md": "---\nverified: soon\n---\n",
    "Knowledge/Notes/Dates4.md": "---\nverified: 20260101\n---\n",
    "Knowledge/Notes/Unclosed.md": "---\ntitle: open\n\n# Unclosed\n",
    "Knowledge/Notes/Near.md": (
        "---\nverified: 2026-01-01\ndepends_on:\n  - path: Packages/P/late.jl\n"
        "  - path: Packages/P/next.jl\n---\n"
    ),
    "Knowledge/Notes/Quoted.md": (
        '---\nverified: "2026-02-03"\ndepends_on:\n  - path: Packages/P/even.jl\n---\n'
    ),
    "Knowledge/Records/.lint-records": "",
    "Knowledge/Records/R.md": "# Record\n\n[[Nowhere3]] and `Packages/none.jl:4`.\n",
    "Knowledge/CHANGELOG.md": "# Changelog\n\n[[Nowhere2]] and `Packages/gone.jl:1`.\n",
    "Knowledge/.obsidian/x.md": "[[Nowhere4]]\n",
    "Environment/README.md": "# E\n",
    "Environment/Env Page.md": "# Env\n\n`Environment/README.md:1` and `Environment/README.md:2`.\n",
    "Tasks/README.md": "[[B]]\n",
    "Tasks/CLAUDE.md": "# Rules\n",
    "Tasks/Good.md": "---\nstatus: wip\ncreated: 2026-01-01\nstarted: 2026-01-02\n---\nx\n",
    "Tasks/NoStatus.md": "---\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/NoCreated.md": "---\nstatus: next\n---\nx\n",
    "Tasks/BadStatus.md": "---\nstatus: wipp\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/DoneHere.md": "---\nstatus: done\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/WipNoStart.md": "---\nstatus: wip\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/NoFrontmatter.md": "# No frontmatter\n",
    "Tasks/Unclosed.md": "---\nstatus: wip\n",
    "Tasks/BadYaml.md": "---\nstatus: wip\nbad: value: other\n---\nx\n",
    "Tasks/DupStatus.md": "---\nstatus: wip\ncreated: 2026-01-01\nstatus: next\n---\nx\n",
    "Tasks/Conv.md": "---\nstatus: next\ncreated: 2026-01-01\ndraft: no\n---\nx\n",
    "Tasks/Sub/Deep.md": "---\nstatus: next\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/Archive/Old.md": "---\nstatus: next\ncreated: 2026-01-01\n---\n`Packages/gone.jl:3`\n",
    "Tasks/Archive/Fine.md": "---\nstatus: done\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/Archive/Sub/Deeper.md": "---\nstatus: done\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/NullStatus.md": "---\nstatus:\ncreated: 2026-01-01\n---\nx\n",
    "Tasks/Evidence/E/x.md": "---\na: 1\na: 2\n---\n[[Nowhere5]] and `Packages/none.jl:4`\n",
    "Library/README.md": "`Library/README.md:1` and `Library/none.md`.\n",
    "Library/papers/X/notes.md": "---\npages: 045202\ntitle: a\ntitle: b\n---\n# X\n",
    "Projects/Notes/p.md": "x\n",
    "Projects/Other/p.md": "x\n",
    "Packages/P/p.jl": "function p()\n    1\nend\n\n# end",
    "Packages/P/even.jl": "a\nb\nc\n",
    "Packages/P/run.jl": "x\n",
    "Packages/P/late.jl": "x\n",
    "Packages/P/next.jl": "x\n",
    "Empty/notes.txt": "no Markdown\n",
}
# The modification times of the rule cases, as UTC: p.jl changed after `verified: 2026-01-01`,
# late.jl on that UTC date and next.jl on the next, half an hour either side of midnight.
STAMPS = {
    "Packages/P/p.jl": "2026-06-01T12:00:00",
    "Packages/P/late.jl": "2026-01-01T23:30:00",
    "Packages/P/next.jl": "2026-01-02T00:30:00",
}
CLEAN = {
    "Knowledge/README.md": "# K\n\n[[A]]\n",
    "Knowledge/Notes/A.md": "# A\n",
    "Knowledge/Notes/B.md": "# B, an orphan\n",
    "Environment/README.md": "# E\n",
    "Tasks/T.md": "---\nstatus: next\ncreated: 2026-01-01\n---\nx\n",
    "Library/README.md": "# L\n",
    "Projects/Notes/p.md": "x\n",
}

A, CONV = "Knowledge/Notes/A.md", "Knowledge/Notes/Conv.md"
QUOTE = "quote it to keep the text"
# The lines that the run of the four trees gives on RULES, one or more per check.
RULE_LINES = [
    f'ERROR  [anchor]  {A} — `Packages/P/p.jl` no longer contains "absent"',
    f"ERROR  [checks]  {A} — `Packages/P/none.jl` does not exist",
    f"ERROR  [depends-on]  {A} — `Packages/P/gone.jl` does not exist",
    f"ERROR  [depends-on]  {A} — `depends_on` entry has no `path`",
    f"ERROR  [depends-on]  {A} — `depends_on` entry is not a mapping: plain",
    f'ERROR  [depends-on]  {A} — `depends_on` entry is not a mapping: Any["a", "b"]',
    "ERROR  [frontmatter]  Knowledge/Notes/Dates.md — `verified: 2026-9-1` is not a YYYY-MM-DD date",
    "ERROR  [frontmatter]  Knowledge/Notes/Dates2.md — `verified: 2026-02-30` is not a YYYY-MM-DD date",
    "ERROR  [frontmatter]  Knowledge/Notes/Dates4.md — `verified: 20260101` is not a YYYY-MM-DD date",
    "ERROR  [frontmatter]  Knowledge/Notes/Dates3.md — `verified: soon` is not a YYYY-MM-DD date",
    "ERROR  [frontmatter]  Knowledge/Notes/Unclosed.md:1 — opens `---` and never closes it",
    "ERROR  [frontmatter]  Knowledge/Notes/Dup.md:3 — YAML block repeats the key `title`",
    "ERROR  [frontmatter]  Knowledge/Notes/Bad.md:3 — YAML block does not parse",
    "ERROR  [line-citation]  Environment/Env Page.md:3 — `Environment/README.md:2` names line 2;"
    " the file has 1",
    f"ERROR  [line-citation]  {A}:21 — `Packages/P/p.jl:2-6` names line 6; the file has 5",
    f"ERROR  [line-citation]  {A}:21 — `Packages/P/even.jl:4` names line 4; the file has 3",
    f"ERROR  [link-crossvault]  {A}:18 — [[Env Page]] is in another vault, at `Environment/Env Page.md`",
    f"ERROR  [link-wrapped]  {A}:18 — [[Wr apped]] is broken across a newline, so it resolves to nothing",
    f"ERROR  [link-wrapped]  {A}:19 — [[Two Words]] is broken across a newline, so it resolves to nothing"
    " — the page exists",
    "ERROR  [task-status]  Tasks/Archive/Old.md — is in `Archive/` but `status: next`",
    "ERROR  [task-status]  Tasks/BadStatus.md — `status: wipp` is not one of"
    " wip | next | incoming | backlog | done",
    "ERROR  [task-status]  Tasks/DoneHere.md — `status: done` belongs in `Archive/`",
    "ERROR  [task-status]  Tasks/Sub/Deep.md — task files live in `Tasks/` or `Tasks/Archive/` only",
    "ERROR  [task-status]  Tasks/Archive/Sub/Deeper.md — task files live in `Tasks/` or"
    " `Tasks/Archive/` only",
    "ERROR  [task-status]  Tasks/Unclosed.md:1 — frontmatter does not close or does not parse",
    "ERROR  [task-status]  Tasks/BadYaml.md:3 — frontmatter does not close or does not parse",
    "ERROR  [task-status]  Tasks/DupStatus.md:4 — YAML block repeats the key `status`",
    f"WARN  [frontmatter]  {CONV}:2 — `draft: no` is false in YAML 1.1; {QUOTE}",
    f"WARN  [frontmatter]  {CONV}:3 — `flag: on` is true in YAML 1.1; {QUOTE}",
    f"WARN  [frontmatter]  {CONV}:4 — `mode: 0755` is 493 in YAML 1.1; {QUOTE}",
    f"WARN  [frontmatter]  {CONV}:5 — `time: 1:30` is 90 in YAML 1.1; {QUOTE}",
    f"WARN  [frontmatter]  {CONV}:6 — `big: 1_000` is 1000 in YAML 1.1; {QUOTE}",
    f"WARN  [frontmatter]  {CONV}:14 — `anchor: off` is false in YAML 1.1; {QUOTE}",
    f"WARN  [frontmatter]  Tasks/Conv.md:4 — `draft: no` is false in YAML 1.1; {QUOTE}",
    f"WARN  [generated]  {A}:24 — generated block `table-one` has no generator yet",
    "WARN  [link-crossvault]  Tasks/README.md:1 — [[B]] is in another vault, at `Knowledge/Notes/B.md`"
    " — Obsidian will not follow it from here",
    f"WARN  [link-unwritten]  {A}:18 — [[Nowhere]] names no page — a marker, or a typo",
    "WARN  [mirror]  Knowledge/Records — no `Projects/` counterpart",
    "WARN  [mirror]  Projects/Other — no `Knowledge/` counterpart",
    "WARN  [orphan]  Environment/Env Page.md — no inbound link",
    "WARN  [orphan]  Knowledge/Notes/Orphan.md — no inbound link",
    "WARN  [orphan]  Knowledge/Notes/Self/S/Only.md — no inbound link",
    "WARN  [link-unwritten]  Knowledge/Notes/B.md:4 — [[Good]] names no page — a marker, or a typo",
    "WARN  [task-status]  Tasks/NullStatus.md — no `status:`",
    "WARN  [orphan]  Knowledge/Records/R.md — no inbound link",
    f"WARN  [path]  {A}:22 — `Packages/P/missing.jl` does not exist",
    f"WARN  [path]  {A}:22 — `Packages/P/nothing/` does not exist",
    "WARN  [path]  Library/README.md:1 — `Library/none.md` does not exist",
    f"WARN  [stale]  {A} — `Packages/P/p.jl` changed after `verified: 2026-01-01`",
    "WARN  [stale]  Knowledge/Notes/Near.md — `Packages/P/next.jl` changed after `verified: 2026-01-01`",
    "WARN  [task-status]  Tasks/NoCreated.md — no `created:`",
    "WARN  [task-status]  Tasks/NoFrontmatter.md — no `created:`",
    "WARN  [task-status]  Tasks/NoFrontmatter.md — no `status:`",
    "WARN  [task-status]  Tasks/NoStatus.md — no `status:`",
    "WARN  [task-status]  Tasks/WipNoStart.md — `status: wip` without `started:`",
]
# Texts that no line of that run may hold: each is a page, a span or a link that the lint skips,
# resolves or accepts.
ABSENT = [
    "[[Code]]",
    "[[Alpha]]",
    "[[B]] names",
    "Nowhere2",
    "Nowhere3",
    "Nowhere4",
    "Nowhere5",
    "Packages/none.jl",
    "Packages/gone.jl:",
    "run.jl",
    "`Packages/P/` does",
    "Packages/*",
    "<n>",
    ".scratch",
    ".worktrees",
    "Packages/x...",
    "p.jl:5`",
    "even.jl:3`",
    "late.jl",
    "Quoted.md",
    "Café",
    "Two Words.md —",
    "Rel.md",
    "Deep/Sub/L.md",
    "Library/papers",
    "Tasks/Evidence",
    "Tasks/Good.md",
    "Tasks/Archive/Fine.md",
    "Pages.md",
    "hex",
    "yes12",
    "`n: 12`",
    "`q:",
    "`f:",
    "`d:",
    "README.md —",
]


def write_tree(
    base: pathlib.Path, files: dict[str, str], stamps: dict[str, str] | None = None
) -> pathlib.Path:
    """A research root below `base` with `files`, each with an mtime of 2025-01-01 or the UTC time
    of `stamps`."""
    root = pathlib.Path(tempfile.mkdtemp(dir=base))
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        when = datetime.datetime.fromisoformat((stamps or {}).get(rel, "2025-01-01T12:00:00"))
        t = when.replace(tzinfo=datetime.UTC).timestamp()
        os.utime(path, (t, t))
    return root


def output(
    root: pathlib.Path, trees: list[str], *, strict: bool = False, quiet: bool = False
) -> tuple[list[str], int]:
    """The lines of the report over `trees` of `root`, and the exit status."""
    findings, vaults = lint(Root(str(root)), trees)
    text, code = report(findings, vaults, strict=strict, quiet=quiet)
    return text.split("\n")[:-1], code


def raised(f: Callable[[], object]) -> str | None:
    """The message of the HarnessError that `f()` raises, or None."""
    try:
        f()
    except HarnessError as e:
        return str(e)
    return None


def rule_cases(check: Callable[[bool, str], None], tmp: pathlib.Path) -> None:
    """One case or more for each check, on RULES."""
    root = write_tree(tmp, RULES, STAMPS)
    home = tmp / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    with mock.patch.dict(os.environ, {"HOME": str(home)}):
        lines, code = output(root, [])
    findings = [line for line in lines if line.startswith(("ERROR  [", "WARN  ["))]
    for want in RULE_LINES:
        check(want in lines, f"the four trees give {want!r}")
    check(
        len(findings) == len(RULE_LINES) + 1 and code == 1,
        f"the four trees give these {len(RULE_LINES)} lines, the stale dependency twice, and exit 1 -> "
        f"{len(findings)} lines, exit {code}: {sorted(set(findings) - set(RULE_LINES))}",
    )
    for text in ABSENT:
        hits = [line for line in findings if text in line]
        check(hits == [], f"no finding names {text!r} -> {hits}")
    errors = 27
    check(
        findings[0].startswith("ERROR  [anchor]")
        and all(line.startswith("ERROR") for line in findings[:errors])
        and all(line.startswith("WARN") for line in findings[errors:]),
        f"the errors come first, by check: {findings[:1]}, {findings[-1:]}",
    )
    depends = [line for line in findings if line.startswith(f"ERROR  [depends-on]  {A}")]
    check(
        [line.rpartition(" — ")[2] for line in depends]
        == [
            "`Packages/P/gone.jl` does not exist",
            "`depends_on` entry has no `path`",
            "`depends_on` entry is not a mapping: plain",
            '`depends_on` entry is not a mapping: Any["a", "b"]',
        ],
        f"findings of one check, file and line keep the order of the entries: {depends}",
    )
    tail = lines[len(findings) :]
    check(
        tail
        == [
            "",
            "by check:",
            "  task-status      error  8",
            "  frontmatter      error  7",
            "  frontmatter      warn   7",
            "  task-status      warn   6",
            "  depends-on       error  4",
            "  orphan           warn   4",
            "  line-citation    error  3",
            "  path             warn   3",
            "  stale            warn   3",
            "  link-unwritten   warn   2",
            "  link-wrapped     error  2",
            "  mirror           warn   2",
            "  anchor           error  1",
            "  checks           error  1",
            "  generated        warn   1",
            "  link-crossvault  error  1",
            "  link-crossvault  warn   1",
            "",
            "27 error(s), 29 warning(s) over Knowledge, Environment, Tasks, Library.",
        ],
        f"a blank line, the counts by check, the most first, then by check, an ERROR before a WARN of one "
        f"check and count, and the totals follow the findings: {tail}",
    )
    target = f"{root}/Packages/P/even.jl"
    check(
        (is_file(target), is_file(target + "/"), exists(target + "/"), is_dir(f"{root}/Packages/P/"))
        == (True, False, False, True),
        "a path that ends in / names a directory only",
    )

    lines, code = output(root, ["Knowledge"])
    check(
        f"WARN  [link-unwritten]  {A}:18 — [[Env Page]] names no page — a marker, or a typo" in lines
        and not any("Tasks/" in line for line in lines)
        and lines[-1] == "17 error(s), 20 warning(s) over Knowledge."
        and code == 1,
        f"Knowledge alone: a link into Environment names no page, and no other tree is read -> {lines[-1:]}",
    )
    lines, code = output(root, ["Tasks", "Library"])
    check(
        "WARN  [link-unwritten]  Tasks/README.md:1 — [[B]] names no page — a marker, or a typo" in lines
        and "WARN  [path]  Library/README.md:1 — `Library/none.md` does not exist" in lines
        and not any("[mirror]" in line for line in lines)
        and code == 1,
        f"Tasks and Library: a link into a vault that is not linted names no page, and no mirror -> "
        f"{lines[-1:]}",
    )
    lines, code = output(root, ["Empty"])
    check(
        lines[0] == "ERROR  [scope]  Empty — holds no Markdown" and code == 1,
        f"a tree without Markdown is an ERROR -> {lines[:1]}, exit {code}",
    )
    message = raised(lambda: output(root, ["Knowledge", "Nosuch"]))
    check(message == "no such vault: Nosuch", f"a tree that is no directory raises -> {message!r}")


def report_cases(check: Callable[[bool, str], None], tmp: pathlib.Path) -> None:
    """The exit status and the lines of --strict and --quiet, on a root with one WARN and none."""
    root = write_tree(tmp, CLEAN)
    orphan = "WARN  [orphan]  Knowledge/Notes/B.md — no inbound link"
    totals = "0 error(s), 1 warning(s) over Knowledge, Environment, Tasks, Library."
    lines, code = output(root, [])
    check(
        lines == [orphan, "", "by check:", "  orphan           warn   1", "", totals] and code == 0,
        f"a WARN alone: printed, exit 0 -> {lines}, exit {code}",
    )
    lines, code = output(root, [], quiet=True)
    check(
        lines == ["by check:", "  orphan           warn   1", "", totals] and code == 0,
        f"--quiet: no WARN line, the counts and the totals, exit 0 -> {lines}, exit {code}",
    )
    lines, code = output(root, [], strict=True)
    check(lines[0] == orphan and code == 1, f"--strict: a WARN fails -> exit {code}")
    (root / "Knowledge" / "Notes" / "B.md").unlink()
    lines, code = output(root, [], strict=True)
    check(
        lines == ["by check:", "", "0 error(s), 0 warning(s) over Knowledge, Environment, Tasks, Library."]
        and code == 0,
        f"no finding: no blank line before the counts, exit 0 under --strict -> {lines}, exit {code}",
    )
    (root / "Knowledge" / "Notes" / "C.md").write_text("[[Wr\nap]]\n", encoding="utf-8")
    lines, code = output(root, [], quiet=True)
    check(
        lines[0]
        == "ERROR  [link-wrapped]  Knowledge/Notes/C.md:1 — [[Wr ap]] is broken across a newline, so it"
        " resolves to nothing"
        and not any(line.startswith("WARN") for line in lines)
        and code == 1,
        f"--quiet with an ERROR: the ERROR lines and no WARN line, exit 1 -> {lines}, exit {code}",
    )
    message = raised(
        lambda: cmd_wiki_lint(
            argparse.Namespace(trees=["Nosuch"], strict=False, quiet=False), Root(str(root))
        )
    )
    check(
        message == "no such vault: Nosuch",
        f"the subcommand raises for a tree that is no directory -> {message!r}",
    )
    p = subprocess.run(
        [sys.executable, str(REPO / "bin" / "harness"), "wiki-lint", "Nosuch"],
        env={**os.environ, "RESEARCH_ROOT": str(root)},
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    check(
        (p.returncode, p.stderr, p.stdout) == (2, "harness wiki-lint: no such vault: Nosuch\n", ""),
        f"harness wiki-lint Nosuch exits 2 with one line -> {p.returncode}, {p.stderr!r}",
    )
    p = subprocess.run(
        [sys.executable, str(REPO / "bin" / "harness"), "wiki-lint", "--quiet"],
        env={**os.environ, "RESEARCH_ROOT": str(root)},
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    check(
        p.returncode == 1 and p.stdout.startswith("ERROR  [link-wrapped]  Knowledge/Notes/C.md:1 — "),
        f"harness wiki-lint reads $RESEARCH_ROOT and exits 1 on an ERROR -> {p.returncode}, "
        f"{p.stdout[:80]!r}",
    )


def yaml_cases(check: Callable[[bool, str], None]) -> None:
    """The reader of a YAML block, and a stale environment."""
    read = yaml_reader()
    got = read("a: 1\nb: 2\na: 3\n")
    check(
        (got.refused, got.duplicate, got.line) == (True, "a", 2),
        f"a duplicate key refuses the block, on the line of the second key -> {got}",
    )
    got = read("deps:\n  - path: x\n    path: y\n")
    check(
        (got.refused, got.duplicate, got.line) == (True, "path", 2),
        f"a duplicate key in a nested mapping -> {got}",
    )
    got = read("a: [x\n")
    check(got.refused and got.duplicate is None, f"a block that does not parse is refused -> {got}")
    got = read("a: !!python/name:os.system\n")
    check(got.refused, f"a Python tag is refused, as a SafeLoader does -> {got}")
    got = read("d: 2026-01-01\nt: 2026-01-01 10:00:00\n")
    check(
        got.data == {"d": "2026-01-01", "t": "2026-01-01 10:00:00"} and not got.conversions,
        f"a date and a time keep their text -> {got}",
    )
    got = read("")
    check(not got.refused and got.data is None, f"an empty block is no mapping -> {got}")
    got = read("- a\n- b\n")
    check(not got.refused and got.data == ["a", "b"], f"a list is read -> {got}")
    check(
        frontmatter("---\n- a\n---\n") == Front({}, 3) and frontmatter("# x\n---\n") == Front({}, 0),
        "a block that is no mapping gives none, and a page that does not start with --- has none",
    )
    front = frontmatter("---\na: 1\nb: c: d\n---\n")
    check(
        (front.stop, front.line, front.duplicate) == (REFUSED, 3, None),
        f"a refused block's line is PyYAML's mark in the file -> {front}",
    )
    front = frontmatter("---\nb: c: d\n---\n")
    check(
        (front.stop, front.line) == (REFUSED, 2),
        f"a refusal on the block's first line is on line 2 of the file -> {front}",
    )
    front = frontmatter("---  \nverified: x\n--- \n")
    check(
        front == Front({"verified": "x"}, 3),
        f"a delimiter with spaces after its dashes opens and closes a block -> {front}",
    )
    got = read('k: !!bool "yes"\n')
    check(got.conversions == (), f"a quoted value with an explicit tag is no conversion -> {got.conversions}")
    for text, want in [
        ("no", False),
        ("off", False),
        ("Yes", True),
        ("0755", 493),
        ("1:30", 90),
        ("1_0.5", 10.5),
    ]:
        got = read(f"k: {text}\n")
        check(
            [(c.key, c.text, c.value, c.line) for c in got.conversions] == [("k", text, want, 0)],
            f"`k: {text}` is a conversion to {want!r} -> {got.conversions}",
        )
    for text in [
        "true",
        "False",
        "12",
        "-3",
        "0x1F",
        "0o17",
        "1.5",
        "1e3",
        ".inf",
        ".nan",
        '"no"',
        "'0755'",
        "x",
        "~",
    ]:
        got = read(f"k: {text}\n")
        check(got.conversions == (), f"`k: {text}` is no conversion -> {got.conversions}")
    got = read("- no\n- [on]\n")
    check(got.conversions == (), f"an item of a list is no mapping value -> {got.conversions}")
    check(
        [shown(v) for v in (True, None, 1.5, math.inf, math.nan, ["a", 1], {"a": True})]
        == ["true", "nothing", "1.5", "Inf", "NaN", 'Any["a", 1]', 'Dict{Any, Any}("a" => true)'],
        "a value's text in a message",
    )
    check(
        [entries(v) for v in (None, "ab", 5, ["x"], {"a": 1})] == [[], ["a", "b"], [5], ["x"], ['"a" => 1']],
        "the items of a frontmatter value",
    )

    # A module that is None in sys.modules raises ImportError at its import.
    yaml_reader.cache_clear()
    try:
        with mock.patch.dict(sys.modules, {"yaml": None}):
            message = raised(lambda: frontmatter("---\na: 1\n---\n"))
    finally:
        yaml_reader.cache_clear()
    check(
        message == "PyYAML is not in the harness's Python environment; run harness install --apply",
        f"an environment without PyYAML: one line that names harness install --apply -> {message!r}",
    )
    check(frontmatter("# no block\n") == Front({}, 0), "a page without a frontmatter needs no PyYAML")


class Commit:
    """One `git commit` through the hook in a scratch repository `Tasks/` of a research root."""

    def __init__(self, code: int | None, out: str, log: list[str], *, committed: bool) -> None:
        self.code, self.out, self.log, self.committed = code, out, log, committed

    def tools(self) -> list[str]:
        return [line.partition(" | ")[0] for line in self.log]


def commit(
    tmp: pathlib.Path,
    trees: dict[str, str],
    staged: dict[str, str],
    *,
    unstaged: dict[str, str] | None = None,
    tools: tuple[str, ...] = strict.TOOLS,
) -> Commit:
    """Stage `staged` in a repository `Tasks/` of a research root with `trees`, whose `Harness` is a
    link to this checkout unless `trees` writes a directory there, and commit through the hook,
    with stubs of `tools` in the environment's `bin/`."""
    base = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    root = write_tree(base, trees)
    if not (root / "Harness").exists():
        (root / "Harness").symlink_to(REPO)
    repo, env_dir, path, log = root / "Tasks", base / "env", base / "path", base / "log"
    for d in (repo / ".githooks", env_dir / "bin", path):
        d.mkdir(parents=True, exist_ok=True)
    hook = repo / ".githooks" / "pre-commit"
    shutil.copyfile(HOOK, hook)
    hook.chmod(0o755)
    for tool in tools:
        (env_dir / "bin" / tool).write_text(strict.STUB.format(python=sys.executable, log=str(log)))
        (env_dir / "bin" / tool).chmod(0o755)
    git_program = shutil.which("git")
    if git_program is None:
        return Commit(None, "no git on the PATH", [], committed=False)
    (path / "git").symlink_to(git_program)
    (path / "python3").symlink_to(sys.executable)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "RESEARCH_HARNESS_"))}
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="case",
        GIT_AUTHOR_EMAIL="case@example.org",
        GIT_COMMITTER_NAME="case",
        GIT_COMMITTER_EMAIL="case@example.org",
        HOME=str(base),
        PATH=f"{path}:/usr/bin:/bin",
        RESEARCH_ROOT=str(root),
        RESEARCH_HARNESS_PYTHON=str(env_dir),
        RESEARCH_HARNESS_INTERPRETER=sys.executable,
        TMPDIR=str(base),
    )

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [git_program, *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )

    git("init", "-q", "-b", "main")
    git("config", "core.hooksPath", ".githooks")
    for name, text in staged.items():
        (repo / name).write_text(text)
    git("add", "--", *staged)
    for name, text in (unstaged or {}).items():
        (repo / name).write_text(text)
    try:
        p = git("commit", "-q", "-m", "case")
        code, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        code, out = None, "TIMEOUT"
    committed = git("rev-parse", "-q", "--verify", "HEAD").returncode == 0
    return Commit(code, out, log.read_text().splitlines() if log.exists() else [], committed=committed)


RUFF = '[project]\nname = "x"\n\n[tool.ruff]\nline-length = 110\n'
LINT_ONLY = '[project]\nname = "x"\n\n[tool.ruff.lint]\nselect = ["F"]\n'
PLAIN = '[project]\nname = "x"\n'


def hook_cases(check: Callable[[bool, str], None], tmp: pathlib.Path) -> None:
    """The hook `githooks/pre-commit-wiki`, installed as `.githooks/pre-commit` of a scratch
    repository."""
    text = HOOK.read_text(encoding="utf-8")
    # The checker of bin/harness's closed set of forms; its module carries no types.
    outside_syntax = cast("Callable[[str], list[str]]", vars(environment)["outside_syntax"])
    found = outside_syntax(text)
    check(found == [], f"the hook uses only the closed set of Python 3.0 forms of bin/harness: {found}")
    check(
        HOOK in strict.guarded_files(REPO)
        and not [f for f in strict.third_party_imports(REPO) if "pre-commit-wiki" in f],
        "the hook is a guarded file, and imports only the standard library",
    )
    check("julia" not in text and "harness wiki-lint" in text, "the hook runs harness wiki-lint and no Julia")
    errors = {**CLEAN, "Knowledge/Notes/Bad.md": "[[Wr\nap]]\n"}

    run = commit(tmp, CLEAN, {"note.md": "# Note\n"})
    check(
        run.code == 0 and run.committed and run.log == [],
        f"a Markdown file over trees without an ERROR: the commit happens, no Python check runs -> exit "
        f"{run.code}, {run.tools()}, {run.out[-300:]!r}",
    )
    run = commit(tmp, errors, {"note.md": "# Note\n"})
    check(
        run.code == 1
        and not run.committed
        and "ERROR  [link-wrapped]  Knowledge/Notes/Bad.md:1" in run.out
        and "pre-commit: refused, harness wiki-lint failed" in run.out,
        f"an ERROR in a tree: the hook prints it and refuses the commit -> exit {run.code}, "
        f"{run.out[-300:]!r}",
    )
    run = commit(tmp, CLEAN, {"pyproject.toml": RUFF, "x.py": "x = 1\n"})
    places = {line.partition(" | ")[2] for line in run.log}
    check(
        run.code == 0 and run.committed and run.tools() == strict.COMMANDS,
        f"a [tool.ruff] table and a clean file: the three checks run and the commit happens -> exit "
        f"{run.code}, {run.tools()}, {run.out[-300:]!r}",
    )
    check(
        len(places) == 1 and not any(place.endswith("/Tasks") for place in places),
        f"the checks run in one directory outside the work tree -> {places}",
    )
    for marker, name in (
        ("BADFORMAT", "ruff format --check"),
        ("BADLINT", "ruff check"),
        ("BADTYPE", "basedpyright"),
    ):
        run = commit(tmp, CLEAN, {"pyproject.toml": RUFF, "x.py": f"x = 1  # {marker}\n"})
        check(
            run.code == 1 and not run.committed and f"pre-commit: refused, {name} failed" in run.out,
            f"a [tool.ruff] table and a file that {name} refuses: no commit -> exit {run.code}, "
            f"{run.out[-200:]!r}",
        )
    run = commit(tmp, errors, {"pyproject.toml": RUFF, "x.py": "x = 1  # BADLINT\n"})
    check(
        run.code == 1
        and run.tools() == strict.COMMANDS
        and "refused, harness wiki-lint and ruff check failed" in run.out,
        f"an ERROR and a lint finding: every check runs and the refusal names both -> {run.tools()}, "
        f"{run.out[-200:]!r}",
    )
    run = commit(tmp, CLEAN, {"pyproject.toml": PLAIN, "x.py": "x = 1  # BADLINT\n"})
    check(
        run.code == 0 and run.committed and run.log == [],
        f"a pyproject.toml without [tool.ruff]: no Python check runs, the commit happens -> exit {run.code}, "
        f"{run.tools()}",
    )
    run = commit(tmp, CLEAN, {"x.py": "x = 1  # BADLINT\n"})
    check(
        run.code == 0 and run.log == [],
        f"no pyproject.toml: no Python check runs -> exit {run.code}, {run.tools()}",
    )
    run = commit(tmp, CLEAN, {"x.py": "x = 1  # BADLINT\n"}, unstaged={"pyproject.toml": RUFF})
    check(
        run.code == 0 and run.log == [],
        f"a [tool.ruff] table that is not staged: no Python check runs -> exit {run.code}, {run.tools()}",
    )
    run = commit(tmp, CLEAN, {"pyproject.toml": LINT_ONLY, "x.py": "x = 1  # BADLINT\n"})
    check(
        run.code == 1 and run.tools() == strict.COMMANDS,
        f"a [tool.ruff.lint] table alone is a [tool.ruff] table -> exit {run.code}, {run.tools()}",
    )
    run = commit(tmp, CLEAN, {"pyproject.toml": "[tool.ruff\n", "x.py": "x = 1\n"})
    check(
        run.code == 1
        and not run.committed
        and "the staged pyproject.toml does not parse" in run.out
        and run.log == [],
        f"a pyproject.toml that does not parse refuses the commit -> exit {run.code}, {run.out[-200:]!r}",
    )
    run = commit(
        tmp, CLEAN, {"pyproject.toml": 'tool = 1\n\n[project]\nname = "x"\n', "x.py": "x = 1  # BADLINT\n"}
    )
    check(
        run.code == 0 and run.log == [],
        f"a pyproject.toml whose `tool` is no table: no Python check runs -> exit {run.code}, "
        f"{run.out[-200:]!r}",
    )
    root = write_tree(tmp, {})
    (root / "Harness").symlink_to(REPO)
    alone = {**os.environ, "RESEARCH_ROOT": str(root)}
    old = (
        "import runpy, sys; sys.version_info = (3, 10, 4, 'final', 0); "
        "runpy.run_path(sys.argv[1], run_name='__main__')"
    )
    p = subprocess.run(
        [sys.executable, "-c", old, str(HOOK)],
        cwd=root,
        env=alone,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    check(
        (p.returncode, p.stderr) == (2, "harness: Python 3.10 found, 3.14 or later needed\n"),
        f"an interpreter that reports 3.10 gets bin/harness's refusal of its version -> {p.returncode}, "
        f"{p.stderr[-200:]!r}",
    )
    p = subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=root,
        env={**alone, "RESEARCH_HARNESS_PYTHON": "relative/env"},
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    check(
        (p.returncode, p.stderr)
        == (1, "pre-commit: refused, $RESEARCH_HARNESS_PYTHON is 'relative/env', not an absolute path\n"),
        f"a relative $RESEARCH_HARNESS_PYTHON: one line, exit 1 -> {p.returncode}, {p.stderr[-200:]!r}",
    )
    run = commit(tmp, {**CLEAN, "Harness/README.txt": "no harness here\n"}, {"note.md": "# Note\n"})
    check(
        run.code == 1 and not run.committed and "pre-commit: refused, no harness at " in run.out,
        f"a research root without the harness: the hook refuses the commit with one line -> exit {run.code}, "
        f"{run.out[-200:]!r}",
    )
    for tools in [("basedpyright",), ()]:
        run = commit(tmp, CLEAN, {"pyproject.toml": RUFF, "x.py": "x = 1\n"}, tools=tools)
        lacking = " and ".join(t for t in strict.TOOLS if t not in tools)
        check(
            run.code == 1
            and not run.committed
            and run.log == []
            and f"pre-commit: {lacking} not in " in run.out
            and "harness install --apply" in run.out,
            f"an environment without {lacking}: one line that names harness install --apply, no tool "
            f"runs, no commit -> exit {run.code}, {run.out[-300:]!r}",
        )


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok: bool, label: str) -> None:  # noqa: FBT001 -- the form of every selftest's check
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  wikilint: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-wikilint-") as tmp:
        base = pathlib.Path(tmp)
        rule_cases(check, base)
        report_cases(check, base)
        yaml_cases(check)
        hook_cases(check, base)
    return total, wrong
