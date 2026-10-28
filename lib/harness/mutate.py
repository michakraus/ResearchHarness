"""`harness mutate`: named mutants of the Python code, each applied to a copy of the repository and
run against the parts of `harness test` that should kill it.

    harness mutate SPEC

SPEC is a TOML file with one table per mutant, in the order in which they run:

    [name]
    file = "lib/harness/x.py"   # a path relative to the repository
    anchor = "def f("           # a text on exactly one line of `file`
    old = "a < b"               # a text that occurs exactly once after the end of that line
    new = "a <= b"              # the text that replaces it
    tests = ["x"]               # the parts of `harness test` that should kill the mutant

The copy is a git repository below `tempfile.gettempdir()`: the repository's tracked files and its
untracked files that git does not ignore, with their working-tree bytes, in its index. It is
removed after the run, also after an error, an interrupt, a SIGTERM or a SIGHUP; nothing is
written into the repository or its `.git`.

Before any test runs, a spec that cannot be applied stops the run with exit 2 and a message that
names the mutant: an empty spec; a table without one of the five keys, with another key, or with
a value of the wrong type; a `file` that the copy does not hold; an `anchor` on no line or on more
than one; an `old` that does not occur exactly once after the anchor's line; an empty `tests`; a
part that `harness test --list` of the copy does not name. Then the copy runs `harness test` with
the union of the parts, unmutated, and a result other than `0 wrong` stops the run with exit 2 and
its first BAD line, because every mutant would then be killed by a failure that is not its own.

Each mutant is then applied alone to the unmutated file, and reverted after its run. A mutated
file that `ast.parse` refuses is `invalid` and runs no test. One line per mutant, in the order of
the spec:

    <name> killed: <the first BAD line>
    <name> killed (timeout): <the first BAD line, which is a part's timeout line>
    <name> SURVIVED
    <name> invalid: <the SyntaxError>

and last `<n> mutants, <k> killed, <s> survived, <i> invalid`. A run of `harness test` that fails
with no BAD line, such as a crash at import, kills the mutant with `exit <status> with no BAD
line: <its last line>`. The exit status is 1 when a mutant survives or is invalid, else 0.
"""

import argparse
import ast
import collections.abc
import contextlib
import dataclasses
import io
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import types
from typing import cast

from . import REPO, HarnessError, fmt

KEYS = ("file", "anchor", "old", "new", "tests")
# The BAD line that `harness test` prints for a part that it stops after its timeout.
TIMEOUT_LINE = re.compile(r"BAD  .+: runs longer than \d+ s and is stopped")
GIT_TIMEOUT = 60  # seconds for a local git command

Check = collections.abc.Callable[[bool, str], None]


@dataclasses.dataclass(frozen=True)
class Mutant:
    name: str
    file: str
    anchor: str
    old: str
    new: str
    tests: tuple[str, ...]


def load(spec: pathlib.Path) -> list[Mutant]:
    """The mutants of the TOML file `spec`, in its order; a spec that holds none, or a table that is
    not one mutant, raises."""
    try:
        data = tomllib.loads(spec.read_bytes().decode("utf-8"))
    except OSError as e:
        raise HarnessError(f"{spec}: {e.strerror}") from None
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise HarnessError(f"{spec}: {e}") from None
    if not data:
        raise HarnessError(f"{spec}: holds no mutant")
    return [mutant(name, table) for name, table in data.items()]


def mutant(name: str, table: object) -> Mutant:
    """The mutant of the table `name`; a table without one of KEYS, with another key, or with a
    value of the wrong type raises."""
    if not isinstance(table, dict):
        raise HarnessError(f"{name}: not a table")
    entries = cast("dict[str, object]", table)
    missing = [key for key in KEYS if key not in entries]
    if missing:
        raise HarnessError(f"{name}: no key {', '.join(missing)}")
    other = [key for key in entries if key not in KEYS]
    if other:
        raise HarnessError(f"{name}: the key {', '.join(other)} is none of {', '.join(KEYS)}")
    texts: dict[str, str] = {}
    for key in KEYS[:4]:
        value = entries[key]
        if not isinstance(value, str):
            raise HarnessError(f"{name}: {key} is not a string")
        texts[key] = value
    tests = entries["tests"]
    if not isinstance(tests, list):
        raise HarnessError(f"{name}: tests is not a list")
    parts = cast("list[object]", tests)
    if not parts:
        raise HarnessError(f"{name}: tests is empty")
    names = [part for part in parts if isinstance(part, str)]
    if len(names) != len(parts):
        raise HarnessError(f"{name}: tests holds a value that is not a string")
    return Mutant(name, texts["file"], texts["anchor"], texts["old"], texts["new"], tuple(names))


def mutated(m: Mutant, text: str) -> str:
    """`text` with the one `old` after the anchor's line replaced by `new`; an anchor on no line or on
    more than one, and an `old` that does not occur exactly once after that line, raise."""
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if m.anchor in line]
    if len(hits) != 1:
        where = "no line" if not hits else f"{len(hits)} lines"
        raise HarnessError(f"{m.name}: the anchor {m.anchor!r} is on {where} of {m.file}")
    start = sum(len(line) for line in lines[: hits[0] + 1])
    after = text[start:]
    count = after.count(m.old)
    if count != 1:
        raise HarnessError(f"{m.name}: {m.old!r} occurs {count} times after the anchor's line of {m.file}")
    return text[:start] + after.replace(m.old, m.new, 1)


def source(m: Mutant, copy: pathlib.Path) -> tuple[pathlib.Path, bytes, str]:
    """The path of the mutant's file in `copy`, its bytes now, and its mutated text; a file that the
    copy does not hold, or that is not UTF-8, raises."""
    path = copy / m.file
    if not path.resolve().is_relative_to(copy.resolve()) or not path.is_file():
        raise HarnessError(f"{m.name}: {m.file} is no file of the repository")
    original = path.read_bytes()
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError:
        raise HarnessError(f"{m.name}: {m.file} is not UTF-8") from None
    return path, original, mutated(m, text)


def clean(env: collections.abc.Mapping[str, str]) -> dict[str, str]:
    """`env` without the GIT_* variables, which would send a git command to another repository."""
    return {k: v for k, v in env.items() if not k.startswith("GIT_")}


def git(args: list[str], cwd: pathlib.Path, env: dict[str, str], stdin: str = "") -> str:
    """The output of one local git command; a failure raises."""
    p = subprocess.run(
        ["git", *args],  # noqa: S607 -- git from the PATH, as every git command of the harness
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=GIT_TIMEOUT,
    )
    if p.returncode != 0:
        raise HarnessError(f"git {args[0]} in {cwd}: {p.stderr.strip()}")
    return p.stdout


def copy(root: pathlib.Path, dest: pathlib.Path, env: collections.abc.Mapping[str, str]) -> list[str]:
    """Copy the tracked files of `root` and its untracked files that git does not ignore, with their
    working-tree bytes, into `dest`, which becomes a git repository whose index holds them; returns
    their paths. A tracked file that the working tree has deleted is not copied, nor a directory
    such as a submodule's."""
    names = git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], root, clean(env))
    copied: list[str] = []
    for name in dict.fromkeys(filter(None, names.split("\0"))):
        src, dst = root / name, dest / name
        if not (src.is_symlink() or src.is_file()):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            dst.symlink_to(src.readlink())
        else:
            shutil.copy2(src, dst)
        copied.append(name)
    # The copy reads no configuration of the caller, so no filter or hook of theirs runs on it.
    quiet = clean(env) | {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_LITERAL_PATHSPECS": "1",
    }
    git(["init", "-q", "-b", "main"], dest, quiet)
    git(["add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"], dest, quiet, "\0".join(copied))
    return copied


def tested(copy: pathlib.Path, parts: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """`harness test` of `copy` with `parts`: (its exit status, its stdout, its stderr). An error or
    an interrupt stops it, and it stops its own parts."""
    p = subprocess.Popen(
        [sys.executable, str(copy / "bin" / "harness"), "test", *parts],
        cwd=copy,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # No timeout: `harness test` stops each of its parts after its own timeout of 300 s.
        out, err = p.communicate()
    except BaseException:
        p.terminate()
        try:
            p.wait(timeout=GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        raise
    return p.returncode, out, err


def verdict(status: int, out: str, err: str) -> tuple[str, str] | None:
    """The kill of one run of `harness test`: ("killed" or "killed (timeout)", its first BAD line, or
    its exit status and last line when it fails with none); None when it passes."""
    bad = next((line for line in out.splitlines() if line.startswith("BAD")), None)
    if bad is not None:
        return ("killed (timeout)" if TIMEOUT_LINE.fullmatch(bad) else "killed", bad)
    if status != 0:
        last = next((line for line in reversed((out + "\n" + err).splitlines()) if line.strip()), "")
        return ("killed", f"exit {status} with no BAD line: {last}")
    return None


def leave(signum: int, _frame: types.FrameType | None) -> None:
    """The handler of SIGTERM and SIGHUP during a run: end it through an exception, so that the child
    stops and the copy is removed."""
    raise SystemExit(128 + signum)


def run(
    spec: pathlib.Path,
    root: pathlib.Path = REPO,
    env: collections.abc.Mapping[str, str] = os.environ,
    scratch: pathlib.Path | None = None,
) -> int:
    """Run the mutants of `spec` on a copy of `root`, below `scratch` or the temporary directory, and
    print one line per mutant and the summary: 1 when a mutant survives or is invalid, else 0. A
    spec that cannot be applied raises before any test runs."""
    mutants = load(spec)
    child = clean(env) | {"PYTHONDONTWRITEBYTECODE": "1"}
    previous = {s: signal.signal(s, leave) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        with tempfile.TemporaryDirectory(prefix="harness-mutate-", dir=scratch) as tmp:
            dest = pathlib.Path(tmp) / "repository"
            dest.mkdir()
            copy(root, dest, env)
            for m in mutants:
                source(m, dest)
            listed = subprocess.run(
                [sys.executable, str(dest / "bin" / "harness"), "test", "--list"],
                cwd=dest,
                env=child,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_TIMEOUT,
            )
            if listed.returncode != 0:
                raise HarnessError(f"harness test --list of the copy exits {listed.returncode}")
            known = set(listed.stdout.splitlines())
            for m in mutants:
                unknown = [part for part in m.tests if part not in known]
                if unknown:
                    raise HarnessError(f"{m.name}: no part {', '.join(unknown)} in harness test --list")
            union = list(dict.fromkeys(part for m in mutants for part in m.tests))
            failure = verdict(*tested(dest, union, child))
            if failure is not None:
                raise HarnessError(f"the unmutated copy fails harness test {' '.join(union)}: {failure[1]}")
            return each(mutants, dest, child)
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def each(mutants: list[Mutant], dest: pathlib.Path, child: dict[str, str]) -> int:
    """Apply each mutant to its file of the copy `dest` as the file is then, run its parts, revert
    it, and print its line and the summary: 1 when a mutant survives or is invalid, else 0."""
    killed = survived = invalid = 0
    for m in mutants:
        path, original, text = source(m, dest)
        try:
            ast.parse(text, filename=m.file)
        except SyntaxError as e:
            print(f"{m.name} invalid: {type(e).__name__}: {e}", flush=True)
            invalid += 1
            continue
        path.write_bytes(text.encode("utf-8"))
        try:
            kill = verdict(*tested(dest, list(m.tests), child))
        finally:
            path.write_bytes(original)
        if kill is None:
            print(f"{m.name} SURVIVED", flush=True)
            survived += 1
        else:
            print(f"{m.name} {kill[0]}: {kill[1]}", flush=True)
            killed += 1
    print(f"{len(mutants)} mutants, {killed} killed, {survived} survived, {invalid} invalid")
    return 1 if survived or invalid else 0


def cmd_mutate(args: argparse.Namespace) -> int:
    return run(pathlib.Path(cast("str", args.spec)).resolve())


def register(sub: fmt.Subcommands) -> None:
    p = sub.add_parser(
        "mutate",
        help="run named mutants of the Python code against the parts of harness test that should kill them",
        description="Apply each mutant of SPEC, a TOML file, to a copy of the repository, one at a "
        "time, and run harness test of the copy with the mutant's parts. Prints one line per "
        "mutant: killed, SURVIVED or invalid. Exits 1 when a mutant survives or is invalid, 2 "
        "when the spec cannot be applied or the unmutated copy fails its parts.",
    )
    p.add_argument("spec", metavar="SPEC", help="the TOML file of the mutants")
    p.set_defaults(run=cmd_mutate)


# The stub `bin/harness` of the selftest's fixture: `test --list` prints its parts, and `test NAME…`
# runs NAME… with docs and sweep on the fixture's m.py and prints `ok`/`BAD` lines and, last,
# `<n> cases, <w> wrong`, as `harness test` does. Its `docs` part fails where `git ls-files` fails
# in its root, as the real one does, and its `sweep` part where PYTHONDONTWRITEBYTECODE is not 1.
# Each call appends its arguments to $STUB_LOG and its root to $STUB_ROOTS; `test --list` exits
# $STUB_LIST_EXIT where it is set.
STUB = """\
import os, pathlib, subprocess, sys, time
root = pathlib.Path(__file__).resolve().parent.parent
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
with open(os.environ["STUB_ROOTS"], "a") as roots:
    roots.write(str(root) + "\\n")
PARTS = ["a", "broken", "docs", "hang", "slow", "sweep"]
if args == ["test", "--list"]:
    print("\\n".join(PARTS))
    sys.exit(int(os.environ.get("STUB_LIST_EXIT", "0")))
text = (root / "m.py").read_text()
if "CRASH" in text:
    sys.exit("crashed at import")
env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
env["GIT_CEILING_DIRECTORIES"] = str(root.parent)
lines = []
for name in sorted({*args[1:], "docs", "sweep"}):
    if name == "a":
        ok, label = "X = 1\\n" in text, "a: X is 1"
    elif name == "broken":
        ok, label = False, "broken: fails on any tree"
    elif name == "docs":
        p = subprocess.run(["git", "ls-files"], cwd=root, env=env, capture_output=True, text=True)
        ok, label = p.returncode == 0 and "m.py" in p.stdout.split(), "docs: git ls-files lists m.py"
    elif name == "hang":
        with open(os.environ["STUB_LOG"], "a") as log:
            log.write("pid %d\\n" % os.getpid())
        time.sleep(60)
        ok, label = True, "hang"
    elif name == "slow":
        if "Z = 3" not in text:
            lines.append("BAD  slow: runs longer than 300 s and is stopped")
            continue
        ok, label = True, "slow: Z is 3"
    else:
        ok, label = os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "sweep: no bytecode is written"
    lines.append(("ok   " if ok else "BAD  ") + label)
wrong = sum(line.startswith("BAD") for line in lines)
print("\\n".join(lines))
print()
print("%d cases, %d wrong" % (len(lines), wrong))
sys.exit(1 if wrong else 0)
"""
FIXTURE = "# fixture\nX = 1\nY = 2\nZ = 3\n"


def spec_cases(check: Check, base: pathlib.Path) -> None:
    """The cases of the spec file, without a repository."""
    path = base / "spec.toml"

    def refused(text: str | bytes) -> str:
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        try:
            load(path)
        except HarnessError as e:
            return str(e)
        return ""

    t = "[m]\nfile = 'f'\nanchor = 'a'\nold = 'o'\nnew = 'n'\ntests = ['x']\n"
    path.write_text(t + t.replace("[m]", "[k]"))
    check(
        load(path) == [Mutant("m", "f", "a", "o", "n", ("x",)), Mutant("k", "f", "a", "o", "n", ("x",))],
        "a spec gives its mutants in its order",
    )
    for label, text, start in [
        ("an empty spec", "", f"{path}: holds no mutant"),
        ("a spec of comments only", "# nothing\n", f"{path}: holds no mutant"),
        ("a spec that is not TOML", "[m\n", f"{path}: "),
        ("a spec that is not UTF-8", b"[m]\nfile = '\xff'\n", f"{path}: "),
        ("a key that is no table", "m = 1\n", "m: not a table"),
        ("a table with another key", t + "extra = 1\n", "m: the key extra is none of"),
        ("a nested table", t + "[m.sub]\n", "m: the key sub is none of"),
        ("a file that is no string", t.replace("'f'", "1"), "m: file is not a string"),
        ("an anchor that is no string", t.replace("'a'", "[]"), "m: anchor is not a string"),
        ("an old that is no string", t.replace("'o'", "true"), "m: old is not a string"),
        ("a new that is no string", t.replace("'n'", "2"), "m: new is not a string"),
        ("tests that is no list", t.replace("['x']", "'x'"), "m: tests is not a list"),
        ("an empty tests", t.replace("['x']", "[]"), "m: tests is empty"),
        ("a test that is no string", t.replace("['x']", "['x', 1]"), "m: tests holds a value"),
    ]:
        message = refused(text)
        check(message.startswith(start), f"{label} is refused, named -> {message!r}")
    for key in KEYS:
        message = refused("".join(line for line in t.splitlines(keepends=True) if not line.startswith(key)))
        check(message == f"m: no key {key}", f"a table without {key} is refused -> {message!r}")
    path.unlink()
    try:
        load(path)
        message = ""
    except HarnessError as e:
        message = str(e)
    check(message.startswith(f"{path}: "), f"a spec that does not exist is refused -> {message!r}")


def mutation_cases(check: Check) -> None:
    """The cases of the anchor and of `old`, without a repository."""

    def apply(anchor: str, old: str, text: str) -> str:
        try:
            return mutated(Mutant("m", "f.py", anchor, old, "N", ("x",)), text)
        except HarnessError as e:
            return f"refused: {e}"

    text = "a = 1\nb = a\nc = a\n"
    for label, anchor, old, src, expected in [
        ("old once after the anchor's line is replaced", "b =", "a", text, "a = 1\nb = a\nc = N\n"),
        ("old on the anchor's own line does not count", "b = a", "a", "a = 1\nb = a\nc = 1\n", "refused"),
        (
            "old on the anchor's line and once after it",
            "b =",
            "1",
            "a = 1\nb = 1\nc = 1\n",
            "a = 1\nb = 1\nc = N\n",
        ),
        ("old that spans lines", "a = 1", "a\nc", text, "a = 1\nb = N = a\n"),
        ("the anchor on the last line", "c =", "a", text, "refused"),
        ("an anchor on no line", "zzz", "a", text, "refused: m: the anchor 'zzz' is on no line of f.py"),
        ("an anchor on two lines", "= a", "a", text, "refused: m: the anchor '= a' is on 2 lines of f.py"),
        ("an anchor that spans lines", "1\nb", "a", text, "refused: m: the anchor '1\\nb' is on no line"),
        (
            "old twice after the anchor",
            "a = 1",
            "a",
            text,
            "refused: m: 'a' occurs 2 times after the anchor's line",
        ),
        (
            "old only before the anchor",
            "c =",
            "1",
            text,
            "refused: m: '1' occurs 0 times after the anchor's line",
        ),
        ("a carriage return stays", "b =", "a", "a = 1\r\nb = a\r\nc = a\r\n", "a = 1\r\nb = a\r\nc = N\r\n"),
    ]:
        got = apply(anchor, old, src)
        check(
            got.startswith(expected) if expected.startswith("refused") else got == expected,
            f"{label} -> {got!r}",
        )


def verdict_cases(check: Check) -> None:
    """The cases of the line of one run of `harness test`, without a repository."""
    timeout = "BAD  slow: runs longer than 300 s and is stopped"
    colon = "BAD  probe:omp: runs longer than 300 s and is stopped"
    for label, args, expected in [
        ("a pass", (0, "ok   a\n\n1 cases, 0 wrong\n", ""), None),
        ("the first BAD line kills", (1, "ok   a\nBAD  a: x\nBAD  b: y\n", ""), ("killed", "BAD  a: x")),
        (
            "a first timeout line kills by timeout",
            (1, f"{timeout}\nBAD  b: y\n", ""),
            ("killed (timeout)", timeout),
        ),
        (
            "a timeout line after another BAD line",
            (1, f"BAD  a: x\n{timeout}\n", ""),
            ("killed", "BAD  a: x"),
        ),
        ("the timeout line of a part with a colon", (1, f"{colon}\n", ""), ("killed (timeout)", colon)),
        ("a timeout line with more text", (1, f"{timeout} now\n", ""), ("killed", f"{timeout} now")),
        ("a BAD line with exit 0", (0, "BAD  a: x\n", ""), ("killed", "BAD  a: x")),
        (
            "a failure with no BAD line",
            (1, "ok   a\n", "Traceback\nNameError: x\n\n"),
            ("killed", "exit 1 with no BAD line: NameError: x"),
        ),
    ]:
        got = verdict(*args)
        check(got == expected, f"verdict: {label} -> {got!r}")


def run_cases(check: Check, base: pathlib.Path) -> None:  # noqa: PLR0915 -- one case after the other
    """The cases of the copy and of whole runs, on a fixture git repository with a stub `bin/harness`."""
    log, scratch, root = base / "stub.log", base / "scratch", base / "repository"
    scratch.mkdir()
    # Without the caller's PYTHONDONTWRITEBYTECODE, so that the stub sees the one that `run` sets.
    env = {k: v for k, v in clean(os.environ).items() if k != "PYTHONDONTWRITEBYTECODE"} | {
        "STUB_LOG": str(log),
        "STUB_ROOTS": str(base / "roots"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "mutate",
        "GIT_AUTHOR_EMAIL": "mutate@example.org",
        "GIT_COMMITTER_NAME": "mutate",
        "GIT_COMMITTER_EMAIL": "mutate@example.org",
        "GIT_CEILING_DIRECTORIES": str(base),
    }
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "harness").write_text(STUB)
    (root / "m.py").write_text(FIXTURE)
    (root / ".gitignore").write_text("*.log\n")
    (root / "gone.py").write_text("gone\n")
    (root / "kept.log").write_text("tracked, and ignored by .gitignore\n")
    (root / "link.py").symlink_to("m.py")
    # A name that is pathspec magic, which excludes m.py and matches nothing.
    (root / ":(exclude)m.py").write_text("MAGIC = 1\n")
    git(["init", "-q", "-b", "main"], root, env)
    git(["add", "."], root, env)
    git(["add", "-f", "kept.log"], root, env)
    git(["commit", "-q", "-m", "fixture"], root, env)
    (root / "gone.py").unlink()
    (root / "ignored.log").write_text("ignored\n")

    # The copy; a GIT_DIR of the caller does not send it to another repository, and a filter of the
    # caller's global configuration, which refuses every file, does not run on it.
    (root / "new.py").write_text("NEW = 1\n")
    (root / "m.py").write_text(FIXTURE + "# changed\n")
    (root / ".gitattributes").write_text("m.py filter=refuse\n")
    home = base / "home"
    home.mkdir()
    (home / ".gitconfig").write_text('[filter "refuse"]\n\tclean = false\n\trequired = true\n')
    dest = base / "copy"
    dest.mkdir()
    caller = {"GIT_DIR": str(base / "nowhere"), "GIT_INDEX_FILE": str(base / "no"), "HOME": str(home)}
    names = copy(root, dest, env | caller)
    listed = git(["ls-files"], dest, env).split()
    (root / ".gitattributes").unlink()
    files = [".gitattributes", ".gitignore", ":(exclude)m.py", "bin/harness", "kept.log", "link.py"]
    check(
        sorted(names) == listed == [*files, "m.py", "new.py"]
        and (dest / "m.py").read_text() == FIXTURE + "# changed\n"
        and (dest / "link.py").is_symlink()
        and (dest / "link.py").readlink() == pathlib.Path("m.py")
        and not (dest / "ignored.log").exists(),
        "the copy holds the tracked files, an ignored one too, and the untracked files that git does "
        "not ignore, with their working-tree bytes, a symlink as a symlink, a name that is pathspec "
        "magic as itself, and no deleted file, and git ls-files lists them; no GIT_DIR or global "
        f"filter of the caller acts on it -> {listed}",
    )
    (root / "new.py").unlink()
    (root / "m.py").write_text(FIXTURE)
    elsewhere = base / "not-a-repository"
    elsewhere.mkdir()
    try:
        copy(elsewhere, base / "copy2", env)
        message = ""
    except HarnessError as e:
        message = str(e)
    check(
        message.startswith(f"git ls-files in {elsewhere}: "),
        f"a root that is no git repository stops the copy -> {message!r}",
    )

    def state() -> list[tuple[str, bytes]]:
        return sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob("*") if p.is_file())

    specs = iter(range(1000))

    def go(*tables: str) -> tuple[int | str, list[str], list[str]]:
        """A run of the spec of `tables` on the fixture: (its exit status or the message that stops
        it, its lines, the stub's calls)."""
        path = base / f"spec{next(specs)}.toml"
        path.write_text("".join(tables))
        log.write_text("")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                status: int | str = run(path, root, env, scratch)
            except HarnessError as e:
                status = str(e)
        return status, out.getvalue().splitlines(), log.read_text().splitlines()

    def table(name: str, old: str, new: str, tests: str = "['a']", file: str = "m.py") -> str:
        return (
            f"[{name}]\nfile = '{file}'\nanchor = '# fixture'\n"
            f"old = '''{old}'''\nnew = '''{new}'''\ntests = {tests}\n"
        )

    m1 = table("M1", "X = 1", "X = 9")
    m2 = table("M2", "Y = 2", "Y = 3")
    m3 = table("M3", "Y = 2", "Y = (")
    before = state()
    status, lines, calls = go(m1, m2, m3)
    check(
        (status, lines[:2], lines[3:])
        == (1, ["M1 killed: BAD  a: X is 1", "M2 SURVIVED"], ["3 mutants, 1 killed, 1 survived, 1 invalid"])
        and lines[2].startswith("M3 invalid: SyntaxError: ")
        and "m.py" in lines[2],
        "a kill, a survivor and an invalid mutant, in the order of the spec, exit 1; the copy is a git "
        "repository, where the stub's docs part, which fails without git ls-files, passes "
        f"-> {status}, {lines}",
    )
    check(
        calls == ["test --list", "test a", "test a", "test a"],
        "the unmutated run and each valid mutant run harness test with their parts, the second mutant on "
        f"the reverted file; the invalid one runs none -> {calls}",
    )
    status, lines, calls = go(m2)
    check(
        (status, lines) == (1, ["M2 SURVIVED", "1 mutants, 0 killed, 1 survived, 0 invalid"]),
        f"a survivor alone exits 1 -> {status}, {lines}",
    )
    status, lines, calls = go(m3)
    check(
        status == 1
        and lines[1:] == ["1 mutants, 0 killed, 0 survived, 1 invalid"]
        and calls == ["test --list", "test a"],
        f"an invalid mutant alone exits 1 and runs only the unmutated test -> {status}, {lines}, {calls}",
    )
    status, lines, calls = go(
        table("M4", "Z = 3", "Z = 4", "['slow']"),
        table("M5", "X = 1\nY = 2\nZ = 3", "", "['slow', 'a']"),
        table("M6", "Y = 2", "CRASH = 1"),
    )
    check(
        (status, lines)
        == (
            0,
            [
                "M4 killed (timeout): BAD  slow: runs longer than 300 s and is stopped",
                "M5 killed: BAD  a: X is 1",
                "M6 killed: exit 1 with no BAD line: crashed at import",
                "3 mutants, 3 killed, 0 survived, 0 invalid",
            ],
        ),
        "a first timeout line is killed (timeout), one after another BAD line a plain kill, a crash a "
        f"kill; all killed exits 0 -> {status}, {lines}",
    )
    check(
        calls == ["test --list", "test slow a", "test slow", "test slow a", "test a"],
        f"the unmutated run takes the union of the parts, in the order of the spec -> {calls}",
    )
    check(state() == before, "the runs leave every file of the repository and of its .git as it was")
    roots = {pathlib.Path(line) for line in (base / "roots").read_text().splitlines()}
    copies = 4  # one per run above
    check(
        len(roots) == copies
        and all(r.is_relative_to(scratch.resolve()) and not r.exists() for r in roots)
        and not any(scratch.iterdir()),
        f"each run makes its copy below the scratch directory and removes it -> {sorted(roots)}",
    )

    for label, tables, expected, runs in [
        ("an empty spec", [""], "holds no mutant", []),
        (
            "an anchor on no line",
            [m1, m2.replace("# fixture", "nowhere")],
            "M2: the anchor 'nowhere' is on no line",
            [],
        ),
        ("an anchor on two lines", [m2.replace("# fixture", "=")], "M2: the anchor '=' is on 3 lines", []),
        ("old twice after the anchor", [m2.replace("'''Y = 2'''", "' = '")], "M2: ' = ' occurs 3 times", []),
        ("old not after the anchor", [m2.replace("'''Y = 2'''", "'W'")], "M2: 'W' occurs 0 times", []),
        (
            "a file that does not exist",
            [table("M7", "a", "b", file="no.py")],
            "M7: no.py is no file of the repository",
            [],
        ),
        ("an ignored file", [table("M7", "a", "b", file="ignored.log")], "M7: ignored.log is no file", []),
        (
            "a file outside the copy, which exists",
            [table("M7", "X = 1", "X = 9", file=str(root / "m.py"))],
            f"M7: {root / 'm.py'} is no file of the repository",
            [],
        ),
        ("a directory", [table("M7", "a", "b", file="bin")], "M7: bin is no file", []),
        ("an empty tests", [m1.replace("['a']", "[]")], "M1: tests is empty", []),
        (
            "an unknown part",
            [m1, m2.replace("['a']", "['a', 'nosuchpart']")],
            "M2: no part nosuchpart",
            ["test --list"],
        ),
        (
            "an unmutated copy that fails its parts",
            [m1.replace("['a']", "['broken']")],
            "the unmutated copy fails harness test broken: BAD  broken: fails on any tree",
            ["test --list", "test broken"],
        ),
    ]:
        status, lines, calls = go(*tables)
        check(
            isinstance(status, str) and expected in status and not lines and calls == runs,
            f"{label} stops the run before any mutant's test, named -> {status!r}, {calls}",
        )
    env["STUB_LIST_EXIT"] = "3"
    status, lines, calls = go(m1)
    del env["STUB_LIST_EXIT"]
    check(
        status == "harness test --list of the copy exits 3" and not lines and calls == ["test --list"],
        f"a harness test --list that fails stops the run before any test -> {status!r}, {calls}",
    )
    (root / "latin.py").write_bytes(b"# fixture\nX = '\xff'\n")
    status, _, calls = go(table("M8", "X", "x", file="latin.py"))
    (root / "latin.py").unlink()
    check(
        status == "M8: latin.py is not UTF-8" and calls == [],
        f"a file that is not UTF-8 is refused -> {status!r}",
    )
    check(
        state() == before and not any(scratch.iterdir()),
        "a refused run leaves the repository as it was and removes its copy",
    )

    # SIGTERM, SIGHUP and an interrupt during the unmutated run: the run ends, the stub stops and
    # the copy goes.
    path = base / "hang.toml"
    path.write_text(table("M9", "X = 1", "X = 9", "['hang']"))
    lib = pathlib.Path(__file__).resolve().parent.parent
    code = (
        "import pathlib, signal, sys; signal.signal(signal.SIGINT, signal.default_int_handler); "
        "sys.path.insert(0, sys.argv[1]); from harness import mutate; "
        "a = [pathlib.Path(x) for x in sys.argv[2:]]; "
        "sys.exit(mutate.run(a[0], a[1], scratch=a[2]))"
    )
    for sig, expected in [
        (signal.SIGTERM, 128 + signal.SIGTERM),
        (signal.SIGHUP, 128 + signal.SIGHUP),
        (signal.SIGINT, -signal.SIGINT),
    ]:
        log.write_text("")
        p = subprocess.Popen(
            [sys.executable, "-c", code, str(lib), str(path), str(root), str(scratch)],
            env=env | {"PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while "pid " not in log.read_text() and time.monotonic() < deadline and p.poll() is None:
            time.sleep(0.05)
        p.send_signal(sig)
        try:
            status = p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            status = p.wait()
        pids = [int(line[4:]) for line in log.read_text().splitlines() if line.startswith("pid ")]
        check(
            status == expected and len(pids) == 1 and not alive(pids[0]) and not any(scratch.iterdir()),
            f"{sig.name} during a run ends it with {expected}, stops the stub and removes the copy "
            f"-> {status}",
        )


def alive(pid: int) -> bool:
    """Whether the process `pid` runs."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def selftest() -> tuple[int, int]:
    """The cases of the spec, the mutation, the verdicts, the copy and whole runs, the last on a
    fixture git repository with a stub `bin/harness`; the real suite never runs here: (number of
    cases, number wrong)."""
    total = wrong = 0

    def check(ok: bool, label: str) -> None:  # noqa: FBT001 -- the form of every selftest's check
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  mutate: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-mutate-selftest-") as tmp:
        base = pathlib.Path(tmp)
        spec_cases(check, base)
        mutation_cases(check)
        verdict_cases(check)
        run_cases(check, base)
    return total, wrong
