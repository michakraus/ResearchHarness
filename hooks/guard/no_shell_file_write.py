"""Refuse a shell command that writes a file inside a git working tree.

The check reads the command and denies a segment that writes a file that belongs to the internal
edit tools:

  * a **redirection**: `>`, `>>`, `>|`, `&>`, `>&`, which can follow any command at all, and
    `tee`, which writes without one;
  * an **in-place flag cluster**: `sed -Ei`, `perl -ni`, the `git add -nA` shape;
  * a **Python one-off**: `python3 -c`, `python3 - <<'EOF'`, whose code calls `open(p, 'w')` or
    `Path(p).write_text` on a path it can read: a literal, or a name bound once to one.

A quoted `>` is text and never a redirection. A heredoc body is cut out before the command is
read, so its lines are not segments.

A target is resolved against the call's working directory, every `cd` before it in the command,
and a leading variable that an earlier segment set on its own (`S=/x; cd $S`). A relative target
that only the call's working directory resolves is denied when the call names none. A scratch
root passes first, whatever is below it: `$TMPDIR`, `/tmp/`, `/private/tmp/`, `/var/folders/`,
`/dev/`, and `~/Research/.scratch/`. Then a target in a git working tree (a `.git` at or above it)
is refused unless `git check-ignore` says git ignores it. A target outside one, or relative after
a `cd` whose directory is unknown, is refused when it has a source suffix.

Out of its reach: a computed target (`> $OUT`, `open(f"{d}/x.jl", 'w')`, a name bound twice), a
Julia one-off, any other writer inside a string argument, and a `cd` inside a subshell, which is
taken to persist after the `)`.
"""

import ast
import functools
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .contract import PASS, Call, Verdict, needs_cwd
from .paths import Place, place
from .shell import SEGMENT, Tokens, lex

# The redirection at the end of an operator run; what comes before it is a separator: `)>` closes
# a subshell and redirects it. `<` forms read, and are kept only to find the heredoc placeholder
# and to skip their target.
REDIRECT = re.compile(r"(&>>?|>>?[|&]?|<<<|<<-?|<>|<&?)$")

# `<<'EOF'`, `<<-EOF`, `<< "EOF"`; not `<<<`, a here-string.
HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
PLACEHOLDER = "__heredoc_{}__"

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
LEADING_VARIABLE = re.compile(r"^\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

# The file kinds this tree edits with Read/Edit/Write: the rule outside a git working tree, and
# for a relative target whose directory is unknown.
SOURCE_SUFFIXES = (
    ".jl",
    ".md",
    ".toml",
    ".tex",
    ".bib",
    ".sty",
    ".cls",
    ".yml",
    ".yaml",
    ".json",
    ".py",
    ".sh",
    ".ipynb",
)

HOME = str(Path.home())
TMPDIR = os.environ.get("TMPDIR") or "/tmp"  # noqa: S108 -- the shell's default of $TMPDIR

# Writing under a scratch root is not editing the tree. `$TMPDIR/x` is recognised as the literal
# text it is. `~/Research/.scratch/` holds probe scripts and environments and no checkout, so it is
# a scratch root in each spelling, and a probe `git init` below it does not make it a work tree.
SCRATCH_PREFIXES = (
    "$TMPDIR",
    "${TMPDIR}",
    "/tmp/",  # noqa: S108 -- a scratch root
    "/private/tmp/",
    "/var/folders/",
    "/dev/",
    "~/Research/.scratch/",
    "$HOME/Research/.scratch/",
    "${HOME}/Research/.scratch/",
    HOME + "/Research/.scratch/",
    TMPDIR.rstrip("/") + "/",
)
# The absolute scratch roots, as names, for a path that the check has resolved.
SCRATCH_ROOTS = tuple(PurePosixPath(prefix).parts for prefix in SCRATCH_PREFIXES if prefix.startswith("/"))

# In-place editing is a flag on these, and the flag is what this check reads.
INPLACE_TOOLS = frozenset({"sed", "gsed", "perl", "awk", "gawk"})

# Letters that consume the rest of their cluster as an argument. `perl -Ilib` holds an `i` that is
# not the in-place flag, and stopping at `I` keeps it from refusing.
TAKES_ATTACHED = {
    "sed": frozenset("efl"),
    "gsed": frozenset("efl"),
    "perl": frozenset("IeEMmFD"),
    "awk": frozenset("fvF"),
    "gawk": frozenset("fvF"),
}

PYTHON = re.compile(r"^python(3(\.[0-9]+)?)?$")

MESSAGE = """Refused: {segment}

`{detail}` writes a file in a git working tree through the shell. A shell rewrite reports
success whether or not it matched anything, and BSD `sed` differs from GNU in ways that
corrupt silently on macOS.

Use the internal edit tools instead:

    Edit    one file, one region
    Write   a new file, or a full replacement you have read first

For a mechanical change over many files, use Kaimon's `rename_symbol` or `edit_code`:
both abort the whole batch untouched on one failure and return the diff.

A scratch file is not this rule: write it under `$TMPDIR` or `~/Research/.scratch/` and it
passes. A log redirect there, `> ~/Research/.scratch/<task>/run.log 2>&1`, passes too.
"""


class Missing:
    """The working directory of a call that names none: a relative path cannot be resolved."""


MISSING = Missing()
type Cwd = Place | Missing | None  # None: a `cd` went to a directory that cannot be known


class NeedsCwdError(Exception):
    """A relative path that only the call's missing working directory resolves."""


type Segment = tuple[list[str], list[str], list[int]]


def cut_heredocs(command: str) -> tuple[str, list[str]]:
    """The command with each heredoc body removed, and the bodies in order."""
    kept: list[str] = []
    bodies: list[list[str]] = []
    pending: list[tuple[bool, str]] = []
    for line in command.split("\n"):
        if pending:
            tabs, delimiter = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            else:
                bodies[len(bodies) - len(pending)].append(line)
            continue

        def mark(match: re.Match[str]) -> str:
            pending.append((match.group(1) == "-", match.group(3)))
            bodies.append([])
            return "<< " + PLACEHOLDER.format(len(bodies) - 1)

        kept.append(HEREDOC.sub(mark, line))
    return "\n".join(kept), ["\n".join(body) for body in bodies]


def split(tokens: Tokens, placeholders: dict[str, int]) -> list[Segment]:
    """Group tokens into segments: (words, write targets, heredoc body indices)."""
    segments: list[Segment] = []
    words: list[str] = []
    writes: list[str] = []
    docs: list[int] = []
    index = 0
    while index < len(tokens):
        kind, text = tokens[index]
        index += 1
        if kind == "word":
            words.append(text)
            continue
        match = REDIRECT.search(text)
        separator = text[: match.start()] if match else text
        if separator:
            segments.append((words, writes, docs))
            words, writes, docs = [], [], []
        if not match:
            continue
        operator = match.group(1)
        if index >= len(tokens) or tokens[index][0] != "word":
            continue
        target = tokens[index][1]
        index += 1
        if operator.startswith("<"):
            if target in placeholders:
                docs.append(placeholders[target])
        elif not (operator.endswith("&") and (target.isdigit() or target == "-")):
            writes.append(target)
    segments.append((words, writes, docs))
    return [segment for segment in segments if any(segment)]


def expand(path: str, variables: dict[str, str | None]) -> str | None:
    """The path with a leading `~` or a leading variable the command set expanded; None when
    anything is left that the shell computes."""
    if path == "~" or path.startswith("~/"):
        path = HOME + path[1:]
    match = LEADING_VARIABLE.match(path)
    if match:
        value = variables.get(match.group(1) or match.group(2))
        if value is not None:
            path = value + path[match.end() :]
    if any(char in path for char in "$*?`"):
        return None
    return path


def scratch(path: Place) -> bool:
    """True when the path is a scratch root or lies below one."""
    return any(path.starts(root) for root in SCRATCH_ROOTS)


@functools.cache
def root(start: Place) -> Place | None:
    """The nearest directory at or above `start` that holds a `.git`, or None; asked once per
    directory, so the writes of one directory read its `.git` and those above it once."""
    directory: Place | None = start
    while directory is not None:
        if Path(directory.text(), ".git").exists():
            return directory
        directory = directory.up
    return None


@dataclass(frozen=True, slots=True)
class Target:
    """A write target, resolved: `root`, the work tree that holds it, or None; `text`, its path, and
    `below`, its path relative to `root`, both empty without a root; `refused`, whether a write to
    it outside a work tree is refused: it lies under no scratch root and its name has a source
    suffix."""

    root: str | None
    text: str
    below: str
    refused: bool


@functools.cache
def target_of(start: Place | None, path: str) -> Target:
    """The write target `path` from the working directory `start`, or from `/` when `start` is
    None, resolved once, so that both readings of a command take it from here. Its work tree is
    the nearest directory at or above the target's directory that holds a `.git`; only a
    directory that exists can hold one. The verdict reads only the directories above the target,
    so the target's last name is joined, not read."""
    pure = PurePosixPath(path)
    if pure.name in ("", ".."):
        found = place(path, "plain") if start is None else start.go(path, "plain")
    else:
        directory = str(pure.parent)
        above = place(directory, "plain") if start is None else start.go(directory, "plain")
        found = above.joined(pure.name)
    if scratch(found):
        return Target(root=None, text="", below="", refused=False)
    tree = root(found.parent().existing())
    if tree is None:
        return Target(root=None, text="", below="", refused=found.name.lower().endswith(SOURCE_SUFFIXES))
    return Target(
        root=tree.text(),
        text=found.text(),
        below=str(PurePosixPath(*found.names()[tree.size :])),
        refused=False,
    )


def ignored_alone(root: str, path: str) -> bool:
    """True when git ignores the path: a log under `runs/`, not a source file."""
    git = shutil.which("git")
    if git is None:
        return False
    try:
        result = subprocess.run(
            [git, "-C", root, "check-ignore", "-q", path], capture_output=True, timeout=2, check=False
        )
    except OSError, subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def ignored_together(root: str, paths: dict[str, str]) -> dict[str, bool]:
    """Whether git ignores each path of `paths` in the work tree `root`, asked in one `git
    check-ignore`. Each path goes to git as its path relative to `root`, the value in `paths`,
    which git reads many times faster than an absolute path. A path with a NUL, which git cannot
    read from its input, is not ignored. A path that the answer leaves open, after git stops on a
    path outside the work tree, is left out."""
    asked: dict[str, bytes] = {}
    unreadable: dict[str, bool] = {}
    for path, below in paths.items():
        encoded = os.fsencode(below)
        if b"\0" in encoded:
            unreadable[path] = False
        else:
            asked[path] = encoded
    return unreadable | asked_together(root, asked)


def asked_together(root: str, asked: dict[str, bytes]) -> dict[str, bool]:
    """Whether git ignores each path of `asked`, given with its bytes, in one `git check-ignore`."""
    git = shutil.which("git")
    if git is None:
        return dict.fromkeys(asked, False)
    try:
        result = subprocess.run(
            [git, "-C", root, "check-ignore", "--stdin", "-z"],
            input=b"".join(encoded + b"\0" for encoded in asked.values()),
            capture_output=True,
            timeout=3,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return {}
    found = set(result.stdout.split(b"\0"))
    complete = result.returncode in (0, 1)
    return {path: encoded in found for path, encoded in asked.items() if complete or encoded in found}


class Ignores:
    """The paths of a command that git ignores, asked once per work tree.

    A first reading of the command collects each path that it asks about and takes it as ignored;
    `ask` then runs one `git check-ignore` per work tree for all of them, and the second reading
    finds each answer here, so a command that writes many files spawns git once per work tree. A
    path that the answer leaves open is asked alone."""

    def __init__(self) -> None:
        self.collecting = True
        self.pending: dict[str, dict[str, str]] = {}
        self.known: dict[str, bool] = {}

    def ignored(self, root: str, path: str, below: str) -> bool:
        """Whether git ignores `path`, whose path relative to the work tree `root` is `below`."""
        if self.collecting:
            self.pending.setdefault(root, {})[path] = below
            return True
        found = self.known.get(path)
        return ignored_alone(root, path) if found is None else found

    def ask(self) -> None:
        self.collecting = False
        for root, paths in self.pending.items():
            self.known.update(ignored_together(root, paths))


def tree_write(target: str, cwd: Cwd, variables: dict[str, str | None], ignores: Ignores) -> bool:
    """True when writing the target writes a file inside a git working tree."""
    if not target or target.startswith(SCRATCH_PREFIXES):
        return False
    path = expand(target, variables)
    if path is None:
        return False
    if not PurePosixPath(path).is_absolute():
        if isinstance(cwd, Missing):
            raise NeedsCwdError
        if cwd is None:
            return path.lower().endswith(SOURCE_SUFFIXES)
        written = target_of(cwd, path)
    else:
        written = target_of(None, path)
    if written.root is not None:
        return not ignores.ignored(written.root, written.text, written.below)
    return written.refused


def scratch_file(target: str, cwd: Cwd, variables: dict[str, str | None]) -> bool:
    """True when the target is known to lie under a scratch root."""
    if target.startswith(SCRATCH_PREFIXES):
        return True
    path = expand(target, variables)
    if path is None:
        return False
    if not PurePosixPath(path).is_absolute():
        if isinstance(cwd, Missing):
            raise NeedsCwdError
        if cwd is None:
            return False
    return scratch((cwd if isinstance(cwd, Place) else Place.anchor()).go(path, "plain"))


@functools.cache
def home() -> Place:
    """The home directory, where a `cd` with no operand goes."""
    return place(HOME, "plain")


def change_directory(words: list[str], cwd: Cwd, variables: dict[str, str | None]) -> Cwd:
    """The directory after `cd`: None when it cannot be known, MISSING when it is relative to the
    call's missing working directory."""
    if len(words) == 1:
        return home()
    target = expand(words[1], variables)
    if target is None or target == "-":
        return None
    if PurePosixPath(target).is_absolute():
        return place(target, "plain")
    if cwd is None or isinstance(cwd, Missing):
        return cwd
    return cwd.go(target, "plain")


def inplace(tool: str, arguments: list[str]) -> str | None:
    """The in-place flag among the leading options, or None."""
    attached = TAKES_ATTACHED[tool]
    for flag in arguments:
        if not flag.startswith("-") or flag == "-":
            return None
        if flag.startswith("--"):
            if flag.startswith("--in-place"):
                return flag
            continue
        for letter in flag[1:]:
            if letter == "i":
                return flag
            if letter in attached:
                break
    return None


def python_code(words: list[str], bodies: list[str]) -> str | None:
    """The code a `python3` segment runs from its command line, or None."""
    if "-c" in words:
        index = words.index("-c")
        return words[index + 1] if index + 1 < len(words) else None
    scripts = [word for word in words[1:] if not word.startswith("-")]
    if bodies and not scripts:
        return bodies[0]
    return None


def bindings(tree: ast.AST) -> dict[str, str]:
    """The names bound exactly once, by a plain assignment, to a string literal."""
    bound: dict[str, str] = {}
    seen: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr]
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.Delete):
            targets = node.targets
        elif isinstance(
            node, (ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor, ast.NamedExpr, ast.comprehension)
        ):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in seen or not isinstance(node, ast.Assign):
                bound.pop(target.id, None)
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                bound[target.id] = value.value
            seen.add(target.id)
    return bound


def python_writes(code: str) -> list[tuple[str, str]]:
    """(path, detail) for each file the code opens for writing by a readable path."""
    try:
        tree = ast.parse(code)
    except SyntaxError, ValueError:
        return []
    bound = bindings(tree)

    def literal(node: ast.expr | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return bound.get(node.id)
        return None

    def name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if name(node.func) == "open" and node.args:
            given = (
                node.args[1]
                if len(node.args) > 1
                else next((keyword.value for keyword in node.keywords if keyword.arg == "mode"), None)
            )
            mode = literal(given) if given is not None else "r"
            path = literal(node.args[0])
            if path and mode and set(mode) & set("wax+"):
                found.append((path, f"open({path!r}, {mode!r})"))
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in ("write_text", "write_bytes")
            and isinstance(node.func.value, ast.Call)
            and name(node.func.value.func) == "Path"
            and node.func.value.args
        ):
            path = literal(node.func.value.args[0])
            if path:
                found.append((path, f"Path({path!r}).{node.func.attr}"))
    return found


def offence(
    segment: Segment, bodies: list[str], cwd: Cwd, variables: dict[str, str | None], ignores: Ignores
) -> str | None:
    """The text that makes this segment a shell file write, or None."""
    words, writes, docs = segment
    for target in writes:
        if tree_write(target, cwd, variables, ignores):
            return "> " + target
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words:
        return None
    head = words[0].rsplit("/", 1)[-1]
    if head in INPLACE_TOOLS:
        flag = inplace(head, words[1:])
        if flag and not scratch_file(words[-1], cwd, variables):
            return flag
    if head == "tee":
        for word in words[1:]:
            if not word.startswith("-") and tree_write(word, cwd, variables, ignores):
                return "tee " + word
    if PYTHON.match(head):
        code = python_code(words, [bodies[i] for i in docs])
        for path, detail in python_writes(code) if code else []:
            if tree_write(path, cwd, {}, ignores):
                return detail
    return None


def segments_of(text: str, placeholders: dict[str, int]) -> list[Segment]:
    """The segments of the command without its heredoc bodies; a text whose quotes do not balance is
    split on the separators first."""
    tokens = lex(text)
    if tokens is not None:
        return split(tokens, placeholders)
    found: list[Segment] = []
    for raw in SEGMENT.split(text):
        part = lex(raw)
        if part is not None:
            found.extend(split(part, placeholders))
    return found


def check(call: Call) -> Verdict:
    """Deny a shell write to a file in a git working tree."""
    command = call.command
    # A cheap reject for the commands this check can never refuse. `-i` is not the test: `sed -Ei`
    # holds no `-i` substring, which is the whole reason the cluster case needs a parser.
    if not (
        ">" in command or "tee" in command or "python" in command or any(t in command for t in INPLACE_TOOLS)
    ):
        return PASS
    cwd: Cwd = MISSING if call.cwd is None else place(call.cwd, "plain")
    text, bodies = cut_heredocs(command)
    segments = segments_of(text, {PLACEHOLDER.format(i): i for i in range(len(bodies))})
    ignores = Ignores()
    try:
        verdict = scan(segments, bodies, cwd, ignores)
        if ignores.pending:
            ignores.ask()
            verdict = scan(segments, bodies, cwd, ignores)
    except NeedsCwdError:
        return needs_cwd("shell-write", command)
    return verdict


def scan(segments: list[Segment], bodies: list[str], cwd: Cwd, ignores: Ignores) -> Verdict:
    """The verdict on the segments of a command, read in order from the working directory `cwd`."""
    # A variable set by a segment of its own persists; `$TMPDIR` is a scratch root.
    variables: dict[str, str | None] = {"HOME": HOME, "TMPDIR": TMPDIR}
    for segment in segments:
        words = segment[0]
        detail = offence(segment, bodies, cwd, variables, ignores)
        if detail:
            shown = " ".join(words + [">" + target for target in segment[1]])
            return Verdict("deny", MESSAGE.format(segment=shown, detail=detail))
        if words and words[0] == "cd":
            cwd = change_directory(words, cwd, variables)
        elif words and all(ASSIGNMENT.match(word) for word in words):
            for word in words:
                key, value = word.split("=", 1)
                variables[key] = expand(value, variables)
    return PASS
