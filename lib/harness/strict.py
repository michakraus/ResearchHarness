"""The cases of the strict profile of the Python code: the hooks and the guards import only the
standard library, every `subprocess.run` names a timeout, no secret file is written before its
mode is set, `harness` turns a program that runs past its timeout into exit 2, and
`.githooks/pre-commit` refuses a commit that fails `ruff format --check`, `ruff check` or
`basedpyright`.

The import cases parse each `.py` file below `hooks/` and `githooks/pre-commit-wiki` with `ast`,
in this repository and in scratch trees. The timeout and chmod cases parse each file that ruff
reads with `ast`, in this repository and in scratch trees: a call of `subprocess.run` names a
`timeout=` or carries `# no timeout: <reason>` on the line where it starts (`untimed_runs`), and a
chmod to a private mode after a file write in one function, outside `fsutil`, carries
`# not private: <reason>` (`chmods_after_writes`); `write_private` writes a secret file. The
handler case runs `harness` with a subcommand whose program sleeps past its timeout. The hook cases
commit in a scratch repository whose `core.hooksPath` is this checkout's `.githooks/`, with
$RESEARCH_HARNESS_PYTHON set to a scratch
environment whose `bin/` holds stubs of `ruff` and `basedpyright`. A stub logs its arguments and
its working directory, and fails on a marker in a `.py` file of that directory: BADFORMAT for
`ruff format --check`, BADLINT for `ruff check`, BADTYPE for `basedpyright`. `ruff format`
without `--check` rewrites each file with BADFORMAT, as the formatter does. A second pair of
stubs on the PATH logs that it ran and passes. The real hook cases run the hook with the real tools
of the harness's environment, where it holds basedpyright and pyyaml, and a `python3` on the PATH
that lacks yaml: a fixed baselined error with its old baseline refuses the commit, and with the
baseline written again commits. Where the environment lacks either, one `skip` line stands for
them. The skip cases check that line on an environment without basedpyright, one whose
interpreter lacks yaml, and one that does not exist.
"""

import argparse
import ast
import contextlib
import importlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import types
from collections.abc import Callable
from typing import Protocol
from unittest import mock

from . import REPO, install

HOOK = REPO / ".githooks" / "pre-commit"
TOOLS = ("ruff", "basedpyright")
TIMEOUT = 60
# The directories whose files ruff does not read here.
SKIPPED = frozenset({".git", ".venv", "node_modules", "__pycache__", ".claude"})
# The comment that exempts a call of `subprocess.run` from a timeout, on the line where it starts,
# and the one that exempts a chmod whose mode is never private, on its line; each with a reason.
NO_TIMEOUT = re.compile(r"# no timeout: *\S")
NOT_PRIVATE = re.compile(r"# not private: *\S")


class Subparsers(Protocol):
    """The `sub` that a module's `register` receives: what `add_subparsers` returns."""

    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


# The modules beyond the standard library that a file may import: the hook probe loads the
# harness's own package, the guard's tables of its four frontends import the guard package by its
# name `guard`, whose parent directory the guard's `__main__` puts on `sys.path`, and the seven hooks
# that read JSON import the guard's `jsonio` from `guard/`, which lies beside them wherever they
# are installed; `kaimon-note.py` also imports its `shell` and `kaimon_session`, and
# `registry-copies.py` its `shell`.
OWN = {
    "hooks/probe.py": frozenset({"harness"}),
    "hooks/context-handoff.py": frozenset({"guard"}),
    "hooks/edit-scope.py": frozenset({"guard"}),
    "hooks/install-drift.py": frozenset({"guard"}),
    "hooks/kaimon-note.py": frozenset({"guard"}),
    "hooks/prompt-log.py": frozenset({"guard"}),
    "hooks/registry-copies.py": frozenset({"guard"}),
    "hooks/worktree.py": frozenset({"guard"}),
    "hooks/guard/frontends/claude.py": frozenset({"guard"}),
    "hooks/guard/frontends/antigravity.py": frozenset({"guard"}),
    "hooks/guard/frontends/opencode.py": frozenset({"guard"}),
    "hooks/guard/frontends/omp.py": frozenset({"guard"}),
}
# The three commands of `githooks/pre-commit-wiki`, as the stubs log them; the cases of
# lib/harness/wikilint.py read them.
COMMANDS = ["ruff format --check --no-cache .", "ruff check --no-cache .", "basedpyright"]
# The three commands of `.githooks/pre-commit`, as the stubs log them; {python} is the interpreter
# of the environment whose bin/ holds the tools.
HOOK_COMMANDS = [
    "ruff format --check --no-cache .",
    "ruff check --no-cache .",
    "basedpyright --pythonpath {python} --baselinemode=lock",
]
# The baseline of basedpyright, and the line that the real pre-commit case prints where the
# harness's environment lacks basedpyright or pyyaml.
BASELINE = ".basedpyright/baseline.json"
REAL_SKIP = "skip  strict: the real pre-commit case needs basedpyright and pyyaml in "
# The fixture of the real pre-commit case: a strict project, a file that imports yaml, and a file
# with one error that the baseline holds, in TYPED, and with the error fixed, in FIXED.
REAL_FILES = {
    "pyproject.toml": '[tool.basedpyright]\ntypeCheckingMode = "strict"\n',
    "reader.py": 'import yaml\n\nprint(yaml.safe_load("a: 1"))\n',
}
TYPED = {**REAL_FILES, "typed.py": 'x: int = "one"\n'}
FIXED = {**REAL_FILES, "typed.py": "x: int = 1\n"}

STUB = """#!{python}
import pathlib, sys
tool, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with open({log!r}, "a") as f:
    f.write(" ".join([tool, *args]) + " | " + str(pathlib.Path.cwd()) + "\\n")


def marked(word):
    return sorted(str(p) for p in pathlib.Path(".").rglob("*.py") if word in p.read_text())


if tool == "basedpyright":
    found = marked("BADTYPE")
elif args[0] == "check":
    found = marked("BADLINT")
elif "--check" in args:
    found = marked("BADFORMAT")
    print(*("Would reformat: " + p for p in found), sep="\\n")
    sys.exit(1 if found else 0)
else:
    for p in marked("BADFORMAT"):
        path = pathlib.Path(p)
        path.write_text(path.read_text().replace("BADFORMAT", "formatted"))
    found = []
print(*(p + ":1:1: a finding" for p in found), sep="\\n")
sys.exit(1 if found else 0)
"""


def guarded_files(root: pathlib.Path) -> list[pathlib.Path]:
    """The files that may import only the standard library: each `.py` file below `hooks/`, and the
    hook of the prose repositories, `githooks/pre-commit-wiki`."""
    return sorted(root.glob("hooks/**/*.py")) + sorted(root.glob("githooks/pre-commit-wiki"))


def third_party_imports(root: pathlib.Path) -> list[str]:
    """Each import of a file of `guarded_files(root)` whose top-level module is neither in the
    standard library nor in OWN for that file, as `<path>:<line>: <module>`. A relative import
    names a module of the repository and passes."""
    found: list[str] = []
    for path in guarded_files(root):
        rel = path.relative_to(root).as_posix()
        allowed = sys.stdlib_module_names | OWN.get(rel, frozenset())
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), rel)):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            found += [f"{rel}:{node.lineno}: {n}" for n in names if n.partition(".")[0] not in allowed]
    return found


def ruff_files(root: pathlib.Path) -> list[pathlib.Path]:
    """The files that ruff reads below `root`: each `*.py` file outside SKIPPED directories, and each
    file of `extend-include` in `[tool.ruff]` of `root`'s pyproject.toml that exists."""
    found = sorted(p for p in root.rglob("*.py") if not SKIPPED & set(p.relative_to(root).parts))
    project = root / "pyproject.toml"
    if project.is_file():
        ruff = tomllib.loads(project.read_text(encoding="utf-8")).get("tool", {}).get("ruff", {})
        found += [root / name for name in ruff.get("extend-include", []) if (root / name).is_file()]
    return found


def calls(path: pathlib.Path) -> list[ast.Call]:
    """The calls of the Python file at `path`."""
    return [
        n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))) if isinstance(n, ast.Call)
    ]


def attribute_of(call: ast.Call, owner: str) -> str | None:
    """The attribute that `call` calls on the name `owner`, as `run` in `subprocess.run(…)`, or None."""
    f = call.func
    return (
        f.attr
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == owner
        else None
    )


def untimed_runs(root: pathlib.Path) -> list[str]:
    """Each call of `subprocess.run` in `ruff_files(root)` that names no `timeout=`, passes no
    `**` mapping and carries no `# no timeout: <reason>` on the line where it starts, as
    `<path>:<line>`."""
    found: list[str] = []
    for path in ruff_files(root):
        lines = path.read_text(encoding="utf-8").splitlines()
        for call in calls(path):
            keyed = any(k.arg in ("timeout", None) for k in call.keywords)
            if (
                attribute_of(call, "subprocess") == "run"
                and not keyed
                and not NO_TIMEOUT.search(lines[call.lineno - 1])
            ):
                found.append(f"{path.relative_to(root).as_posix()}:{call.lineno}")
    return found


def written(call: ast.Call) -> bool:
    """Whether `call` writes a file: `write_bytes`, `write_text`, `json.dump`, `os.write`,
    `shutil.copy`, `copyfile` or `copy2`, or `open` with a mode that holds `w`, `a` or `x`."""
    f = call.func
    if isinstance(f, ast.Attribute):
        if f.attr in ("write_bytes", "write_text", "copy", "copyfile", "copy2"):
            return True
        return attribute_of(call, "json") == "dump" or attribute_of(call, "os") == "write"
    if isinstance(f, ast.Name) and f.id == "open":
        mode = (
            call.args[1]
            if len(call.args) > 1
            else next((k.value for k in call.keywords if k.arg == "mode"), None)
        )
        return (
            isinstance(mode, ast.Constant)
            and isinstance(mode.value, str)
            and bool(set(mode.value) & set("wax"))
        )
    return False


def private_mode(call: ast.Call) -> bool:
    """Whether `call` is a chmod, `os.chmod(path, mode)` or `path.chmod(mode)`, to a private mode: a
    literal that the owner can read and no group or other can, or a name or an attribute, whose
    value no reading of the text gives."""
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "chmod":
        return False
    args = call.args[1:] if attribute_of(call, "os") == "chmod" else call.args
    if not args:
        return False
    mode = args[0]
    if isinstance(mode, ast.Constant) and isinstance(mode.value, int):
        return mode.value & 0o077 == 0 and mode.value & 0o400 != 0
    return isinstance(mode, (ast.Name, ast.Attribute))


def chmods_after_writes(root: pathlib.Path) -> list[str]:
    """Each chmod to a private mode in `ruff_files(root)`, outside lib/harness/fsutil.py, on a line
    after the first file write of its function and without `# not private: <reason>` on its line,
    as `<path>:<line>`: a secret file that `write_private` does not write."""
    found: set[str] = set()
    for path in ruff_files(root):
        rel = path.relative_to(root).as_posix()
        if rel == "lib/harness/fsutil.py":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        tree = ast.parse("\n".join(lines), rel)
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inside = [n for n in ast.walk(function) if isinstance(n, ast.Call)]
            first = min((n.lineno for n in inside if written(n)), default=None)
            found |= {
                f"{rel}:{n.lineno}"
                for n in inside
                if first is not None
                and n.lineno > first
                and private_mode(n)
                and not NOT_PRIVATE.search(lines[n.lineno - 1])
            }
    return sorted(found, key=lambda site: (site.rpartition(":")[0], int(site.rpartition(":")[2])))


def tree_of(tmp: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A scratch tree below `tmp` that holds `files`, {path: text}."""
    root = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


RUN = "import subprocess\n\n\ndef f(**kw):\n"


def timeout_cases(case: Callable[[Callable[[], bool], str], None], tmp: pathlib.Path) -> None:
    """The timeout rule on this repository and on scratch trees."""
    found = untimed_runs(REPO)
    case(
        lambda: found == [] and len(ruff_files(REPO)) > 0,
        f"each subprocess.run of the {len(ruff_files(REPO))} files that ruff reads names a timeout: {found}",
    )
    for label, files, want in [
        ("no timeout", {"a.py": RUN + "    subprocess.run(['x'], check=False)\n"}, ["a.py:5"]),
        ("timeout=5", {"a.py": RUN + "    subprocess.run(['x'], check=False, timeout=5)\n"}, []),
        ("a ** mapping", {"a.py": RUN + "    subprocess.run(['x'], **kw)\n"}, []),
        (
            "the comment on the line of the call",
            {
                "a.py": RUN
                + "    subprocess.run(  # no timeout: a long run\n        ['x'], check=False\n    )\n"
            },
            [],
        ),
        (
            "the comment on the next line",
            {
                "a.py": RUN
                + "    subprocess.run(\n        ['x'], check=False  # no timeout: a long run\n    )\n"
            },
            ["a.py:5"],
        ),
        (
            "the comment with no reason",
            {"a.py": RUN + "    subprocess.run(['x'], check=False)  # no timeout:\n"},
            ["a.py:5"],
        ),
        ("subprocess.Popen", {"a.py": RUN + "    subprocess.Popen(['x'])\n"}, []),
        (
            "a file of extend-include",
            {
                "pyproject.toml": '[tool.ruff]\nextend-include = ["bin/tool"]\n',
                "bin/tool": RUN + "    subprocess.run(['x'])\n",
            },
            ["bin/tool:5"],
        ),
        ("a file below .venv", {".venv/a.py": RUN + "    subprocess.run(['x'])\n"}, []),
    ]:
        got = untimed_runs(tree_of(tmp, files))
        case(lambda: got == want, f"subprocess.run with {label} -> {got}, want {want}")


WRITE = "import json, os, shutil\n\n\ndef f(p, mode):\n"


def chmod_cases(case: Callable[[Callable[[], bool], str], None], tmp: pathlib.Path) -> None:
    """The rule of a chmod to a private mode after a file write, on this repository and on scratch
    trees."""
    found = chmods_after_writes(REPO)
    case(lambda: found == [], f"no chmod to a private mode follows a file write outside fsutil.py: {found}")
    for label, body, want in [
        ("write_text, then chmod(0o600)", '    p.write_text("x")\n    p.chmod(0o600)\n', ["a.py:6"]),
        ("write_text, then chmod(0o755)", '    p.write_text("x")\n    p.chmod(0o755)\n', []),
        ("write_bytes, then chmod(0o400)", '    p.write_bytes(b"x")\n    p.chmod(0o400)\n', ["a.py:6"]),
        ("write_bytes, then chmod(0o700)", '    p.write_bytes(b"x")\n    p.chmod(0o700)\n', ["a.py:6"]),
        ("write_bytes, then chmod(0o640)", '    p.write_bytes(b"x")\n    p.chmod(0o640)\n', []),
        ("write_bytes, then chmod(0o200)", '    p.write_bytes(b"x")\n    p.chmod(0o200)\n', []),
        ("write_bytes, then chmod(0o620)", '    p.write_bytes(b"x")\n    p.chmod(0o620)\n', []),
        ("write_text and chmod(0o600) on one line", '    p.write_text("x"); p.chmod(0o600)\n', []),
        ("write_bytes, then chmod(0)", '    p.write_bytes(b"x")\n    p.chmod(0)\n', []),
        ("write_bytes, then chmod(mode)", '    p.write_bytes(b"x")\n    p.chmod(mode)\n', ["a.py:6"]),
        ("write_bytes, then chmod(os.mode)", '    p.write_bytes(b"x")\n    p.chmod(os.mode)\n', ["a.py:6"]),
        ("write_bytes, then chmod(mode | 1)", '    p.write_bytes(b"x")\n    p.chmod(mode | 1)\n', []),
        (
            "write_bytes, then chmod(mode) that says it is not private",
            '    p.write_bytes(b"x")\n    p.chmod(mode)  # not private: an executable bit\n',
            [],
        ),
        ("chmod(0o600), then write_text", '    p.chmod(0o600)\n    p.write_text("x")\n', []),
        ("open(p, 'w'), then os.chmod(p, 0o600)", '    open(p, "w")\n    os.chmod(p, 0o600)\n', ["a.py:6"]),
        (
            "open(p, mode='a'), then os.chmod(p, 0o600)",
            '    open(p, mode="a")\n    os.chmod(p, 0o600)\n',
            ["a.py:6"],
        ),
        ("open(p, 'x'), then os.chmod(p, 0o600)", '    open(p, "x")\n    os.chmod(p, 0o600)\n', ["a.py:6"]),
        ("open(p), then os.chmod(p, 0o600)", "    open(p)\n    os.chmod(p, 0o600)\n", []),
        ("open(p, 'r'), then os.chmod(p, 0o600)", '    open(p, "r")\n    os.chmod(p, 0o600)\n', []),
        ("json.dump, then chmod(0o600)", "    json.dump({}, p)\n    p.chmod(0o600)\n", ["a.py:6"]),
        ("pickle.dump, then chmod(0o600)", "    pickle.dump({}, p)\n    p.chmod(0o600)\n", []),
        ("write_text, then os.chmod(p, 0o755)", '    p.write_text("x")\n    os.chmod(p, 0o755)\n', []),
        ("os.write, then chmod(0o600)", "    os.write(3, b'x')\n    p.chmod(0o600)\n", ["a.py:6"]),
        ("f.write, then chmod(0o600)", "    p.write(b'x')\n    p.chmod(0o600)\n", []),
        ("shutil.copy, then chmod(0o600)", "    shutil.copy(p, p)\n    p.chmod(0o600)\n", ["a.py:6"]),
        ("shutil.copyfile, then chmod(0o600)", "    shutil.copyfile(p, p)\n    p.chmod(0o600)\n", ["a.py:6"]),
        ("shutil.copy2, then chmod(0o600)", "    shutil.copy2(p, p)\n    p.chmod(0o600)\n", ["a.py:6"]),
        ("os.chmod with no mode", '    p.write_text("x")\n    os.chmod(p)\n', []),
        (
            "a write in another function",
            '    p.write_text("x")\n\n\ndef g(p):\n    p.chmod(0o600)\n',
            [],
        ),
    ]:
        got = chmods_after_writes(tree_of(tmp, {"a.py": WRITE + body}))
        case(lambda: got == want, f"{label} -> {got}, want {want}")
    got = chmods_after_writes(
        tree_of(tmp, {"lib/harness/fsutil.py": WRITE + '    p.write_text("x")\n    p.chmod(0o600)\n'})
    )
    case(lambda: got == [], f"write_text, then chmod(0o600) in lib/harness/fsutil.py -> {got}, want []")


def handler_cases(case: Callable[[Callable[[], bool], str], None]) -> None:
    """`harness` exits 2 with one line that names the command of a program that runs past its
    timeout: a fixture program that sleeps 30 s under a timeout of 1 s."""
    cli = importlib.import_module("harness.cli")
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]

    def run(_: argparse.Namespace) -> int:
        return subprocess.run(sleeper, check=False, timeout=1).returncode

    def register(sub: Subparsers) -> None:
        sub.add_parser("sleeper").set_defaults(run=run)

    fixture = types.SimpleNamespace(register=register)
    err = io.StringIO()
    start = time.monotonic()
    with (
        mock.patch.object(cli, "modules", lambda: [fixture]),
        mock.patch.object(cli, "MODULES", [fixture]),
        contextlib.redirect_stderr(err),
    ):
        try:
            code: object = cli.main(["sleeper"])
        except subprocess.TimeoutExpired as e:
            code = f"TimeoutExpired: {e}"
    seconds = time.monotonic() - start
    lines = err.getvalue().splitlines()
    case(
        lambda: (
            code == 2
            and len(lines) == 1
            and " ".join(sleeper) in lines[0]
            and "1 s" in lines[0]
            and seconds < 20
        ),
        f"a program past its timeout: exit 2 and one line that names its command -> {code!r}, {lines}, "
        f"{seconds:.1f} s",
    )


def import_cases(case: Callable[[Callable[[], bool], str], None], tmp: pathlib.Path) -> None:
    """The ban of imports beyond the standard library, on this repository and on scratch trees."""
    found = third_party_imports(REPO)
    case(
        lambda: found == [] and len(guarded_files(REPO)) > 0,
        f"the {len(guarded_files(REPO))} hooks and guards import only the standard library: {found}",
    )
    for rel, text, want in [
        ("hooks/x.py", "import json\nimport yaml\n", ["hooks/x.py:2: yaml"]),
        ("hooks/x.py", "from yaml.loader import SafeLoader\n", ["hooks/x.py:1: yaml.loader"]),
        ("hooks/x.py", "def f():\n    import requests\n", ["hooks/x.py:2: requests"]),
        ("hooks/x.py", "import harness\n", ["hooks/x.py:1: harness"]),
        ("hooks/probe.py", "import harness\nfrom harness import install\n", []),
        ("hooks/sub/x.py", "import os.path, yaml\n", ["hooks/sub/x.py:1: yaml"]),
        ("hooks/guard/frontends/antigravity.py", "from guard import path_list\n", []),
        ("hooks/guard/x.py", "from guard import path_list\n", ["hooks/guard/x.py:1: guard"]),
        ("adapters/a/adapter.py", "import yaml\n", []),
        ("hooks/x.py", "from . import y\n", []),
        ("hooks/x.py", "from .yaml import y\n", []),
    ]:
        root = pathlib.Path(tempfile.mkdtemp(dir=tmp))
        (root / rel).parent.mkdir(parents=True)
        (root / rel).write_text(text)
        got = third_party_imports(root)
        case(lambda: got == want, f"{rel} with {text!r} -> {got}, want {want}")


class Run:
    """One `git commit` in a scratch repository with the hook, and what it left."""

    def __init__(
        self, repo: pathlib.Path, code: int | None, out: str, log: list[str], *, committed: bool
    ) -> None:
        self.repo, self.code, self.out, self.log, self.committed = repo, code, out, log, committed
        self.lines = out.splitlines()


def commit(
    tmp: pathlib.Path,
    staged: dict[str, str],
    unstaged: dict[str, str] | None = None,
    tools: tuple[str, ...] = TOOLS,
    environment: pathlib.Path | None = None,
) -> Run:
    """Stage the files `staged` in a new scratch repository below `tmp`, write `unstaged` into the
    work tree after that, and run `git commit` with the hook, with the stubs of `tools` in the
    environment's `bin/` and stubs of both tools on the PATH. With `environment`, a real Python
    environment, the hook runs that environment's tools, no stub is written, and the `python3` and
    `python` of the PATH start this interpreter without its site-packages, as an interpreter
    without `yaml`. $CI is unset, so that basedpyright's baseline mode is the hook's own."""
    base = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    repo, path, log = base / "repo", base / "path", base / "log"
    stubs = environment is None
    environment = base / "env" if environment is None else environment
    for d in (repo, path):
        d.mkdir(parents=True)
    if stubs:
        (environment / "bin").mkdir(parents=True)
        for tool in tools:
            (environment / "bin" / tool).write_text(STUB.format(python=sys.executable, log=str(log)))
            (environment / "bin" / tool).chmod(0o755)
        for tool in TOOLS:
            (path / tool).write_text(f"#!/bin/sh\necho \"PATH {tool} $*\" >> '{log}'\nexit 0\n")
            (path / tool).chmod(0o755)
    git_program = shutil.which("git")
    if git_program is None:
        return Run(repo, None, "no git on the PATH", [], committed=False)
    (path / "git").symlink_to(git_program)
    if stubs:
        (path / "python3").symlink_to(sys.executable)
    else:
        for name in ("python3", "python"):
            (path / name).write_text(f"#!/bin/sh\nexec '{sys.executable}' -S \"$@\"\n")
            (path / name).chmod(0o755)
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "RESEARCH_HARNESS_")) and k != "CI"
    }
    env.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="case",
        GIT_AUTHOR_EMAIL="case@example.org",
        GIT_COMMITTER_NAME="case",
        GIT_COMMITTER_EMAIL="case@example.org",
        PATH=f"{path}:/usr/bin:/bin",
        RESEARCH_HARNESS_PYTHON=str(environment),
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
    git("config", "core.hooksPath", str(HOOK.parent))
    for name, text in staged.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
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
    lines = log.read_text().splitlines() if log.exists() else []
    return Run(repo, code, out, lines, committed=committed)


def staged_bytes(repo: pathlib.Path, name: str) -> bytes:
    """The bytes of `name` in the index of `repo`."""
    git_program = shutil.which("git") or "git"
    return subprocess.run(
        [git_program, "show", f":{name}"], cwd=repo, capture_output=True, timeout=TIMEOUT, check=False
    ).stdout


def hook_cases(case: Callable[[Callable[[], bool], str], None], tmp: pathlib.Path) -> None:
    """The cases of `.githooks/pre-commit`."""
    clean = {"a.py": "x = 1\n"}

    def commands(run: Run) -> list[str]:
        return [line.partition(" | ")[0] for line in run.log]

    def expected(run: Run) -> list[str]:
        # `commit` puts the stubs' environment beside the scratch repository.
        return [
            command.format(python=run.repo.parent / "env" / "bin" / "python") for command in HOOK_COMMANDS
        ]

    run = commit(tmp, clean)
    places = {line.partition(" | ")[2] for line in run.log}
    case(
        lambda: run.code == 0 and run.committed and commands(run) == expected(run),
        f"a clean staged file: the three checks run from the environment and the commit happens -> exit "
        f"{run.code}, committed {run.committed}, {commands(run)}, {run.lines[-3:]}",
    )
    case(
        lambda: len(places) == 1 and not any(place.endswith("/repo") for place in places),
        f"the checks run in one directory outside the work tree, the index's copy -> {places}",
    )
    run = commit(tmp, {"a.py": "x = 1  # BADLINT\n"})
    case(
        lambda: run.code == 1 and not run.committed and "pre-commit: refused, ruff check failed" in run.lines,
        f"a staged file that ruff check refuses: no commit -> exit {run.code}, committed {run.committed}, "
        f"{run.lines[-3:]}",
    )
    run = commit(tmp, {"a.py": "x = 1  # BADTYPE\n"})
    case(
        lambda: (
            run.code == 1 and not run.committed and "pre-commit: refused, basedpyright failed" in run.lines
        ),
        f"a staged file that basedpyright refuses: no commit -> exit {run.code}, committed {run.committed}, "
        f"{run.lines[-3:]}",
    )
    run = commit(tmp, {"a.py": "x = 1  # BADLINT BADTYPE\n"})
    case(
        lambda: (
            run.code == 1
            and commands(run) == expected(run)
            and "pre-commit: refused, ruff check and basedpyright failed" in run.lines
        ),
        f"a file that two checks refuse: all three run and the refusal names both -> {commands(run)}, "
        f"{run.lines[-1:]}",
    )
    bad = "x = 1  # BADFORMAT\n"
    run = commit(tmp, {"b.py": bad})
    on_disk = (run.repo / "b.py").read_bytes()
    in_index = staged_bytes(run.repo, "b.py")
    case(
        lambda: (
            run.code == 1
            and not run.committed
            and "Would reformat: b.py" in run.lines
            and "pre-commit: refused, ruff format --check failed" in run.lines
            and on_disk == bad.encode()
            and in_index == bad.encode()
        ),
        f"a staged file that the formatter would change: the hook names it, refuses the commit and leaves "
        f"the file in the work tree and the index -> exit {run.code}, committed {run.committed}, "
        f"{run.lines[-3:]}, work tree {on_disk!r}, index {in_index!r}",
    )
    run = commit(tmp, clean, unstaged={"a.py": "x = 1  # BADLINT\n"})
    case(
        lambda: run.code == 0 and run.committed,
        f"a violation in the work tree that is not staged: the commit happens -> exit {run.code}, "
        f"{run.lines[-3:]}",
    )
    for tools in [("basedpyright",), ("ruff",), ()]:
        run = commit(tmp, clean, tools=tools)
        lacking = [t for t in TOOLS if t not in tools]
        case(
            lambda: (
                run.code == 1
                and not run.committed
                and run.log == []
                and len(run.lines) == 1
                and run.lines[0].startswith(f"pre-commit: refused, {' and '.join(lacking)} not in ")
                and "harness install --apply" in run.lines[0]
            ),
            f"an environment without {' and '.join(lacking)}, with both tools on the PATH: one line that "
            f"names harness install --apply, no tool runs, no commit -> exit {run.code}, {run.log}, "
            f"{run.lines}",
        )


def baseline_of(tmp: pathlib.Path, environment: pathlib.Path, files: dict[str, str]) -> str:
    """The baseline that the basedpyright of `environment`, on its own interpreter, writes for a
    tree of `files` below `tmp`; "" where it writes none."""
    root = tree_of(tmp, files)
    bin_ = environment / "bin"
    subprocess.run(
        [str(bin_ / "basedpyright"), "--pythonpath", str(bin_ / "python"), "--writebaseline"],
        cwd=root,
        capture_output=True,
        check=False,
        timeout=TIMEOUT,
    )
    written = root / BASELINE
    return written.read_text() if written.is_file() else ""


def real_hook_cases(case: Callable[[Callable[[], bool], str], None], tmp: pathlib.Path) -> None:
    """The real `.githooks/pre-commit` with the real tools of the harness's environment, where that
    environment holds basedpyright and pyyaml, on a fixture of a strict project with a file that
    imports yaml and a file with one baselined error; the `python3` of the PATH lacks yaml. With the
    error fixed and the baseline unchanged, the hook refuses the commit and says `went down`; with
    the baseline written again, it commits. Otherwise one line, REAL_SKIP."""
    environment = install.python_env()
    python = environment / "bin" / "python"
    has_yaml = (
        python.is_file()
        and subprocess.run(
            [str(python), "-c", "import yaml"], capture_output=True, check=False, timeout=TIMEOUT
        ).returncode
        == 0
    )
    if not ((environment / "bin" / "basedpyright").is_file() and has_yaml):
        print(f"{REAL_SKIP}{environment}")
        return
    typed = baseline_of(tmp, environment, TYPED)
    # basedpyright writes a baseline without errors only over an existing one.
    fixed = baseline_of(tmp, environment, {**FIXED, BASELINE: typed})
    run = commit(tmp, {**TYPED, BASELINE: typed}, environment=environment)
    case(
        lambda: '"reportAssignmentType"' in typed and run.code == 0 and run.committed,
        f"the real hook: a baselined error and its baseline: the commit happens -> exit {run.code}, "
        f"committed {run.committed}, {run.lines[-3:]}",
    )
    run = commit(tmp, {**FIXED, BASELINE: typed}, environment=environment)
    case(
        lambda: (
            run.code == 1
            and not run.committed
            and "went down" in run.out
            and "pre-commit: refused, basedpyright failed" in run.lines
        ),
        f"the real hook: the baselined error fixed and the baseline unchanged: no commit, and the "
        f"output says went down -> exit {run.code}, committed {run.committed}, {run.lines[-3:]}",
    )
    run = commit(tmp, {**FIXED, BASELINE: fixed}, environment=environment)
    case(
        lambda: fixed not in ("", typed) and run.code == 0 and run.committed,
        f"the real hook: the baselined error fixed and the baseline written again: the commit happens "
        f"-> exit {run.code}, committed {run.committed}, {run.lines[-3:]}",
    )


def skip_cases(case: Callable[[Callable[[], bool], str], None], tmp: pathlib.Path) -> None:
    """`real_hook_cases` on an environment without basedpyright, one whose interpreter lacks yaml,
    and one that does not exist: one line, REAL_SKIP, and no case."""
    base = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    no_tool, no_yaml = base / "no-tool", base / "no-yaml"
    for environment in (no_tool, no_yaml):
        (environment / "bin").mkdir(parents=True)
    # The interpreter of no-tool is this one, which imports yaml under `harness test`; that of
    # no-yaml starts without its site-packages, so `import yaml` fails there.
    (no_tool / "bin" / "python").write_text(f"#!/bin/sh\nexec '{sys.executable}' \"$@\"\n")
    (no_yaml / "bin" / "python").write_text(f"#!/bin/sh\nexec '{sys.executable}' -S \"$@\"\n")
    (no_yaml / "bin" / "basedpyright").write_text("#!/bin/sh\nexit 0\n")
    for tool in (no_tool / "bin" / "python", no_yaml / "bin" / "python", no_yaml / "bin" / "basedpyright"):
        tool.chmod(0o755)
    for label, environment in [
        ("without basedpyright", no_tool),
        ("whose interpreter lacks yaml", no_yaml),
        ("that does not exist", base / "missing"),
    ]:
        out, seen = io.StringIO(), list[str]()
        with (
            mock.patch.object(install, "python_env", lambda e=environment: e),
            contextlib.redirect_stdout(out),
        ):
            real_hook_cases(lambda _ok, text: seen.append(text), tmp)
        lines = out.getvalue().splitlines()
        case(
            lambda: lines == [f"{REAL_SKIP}{environment}"] and seen == [],
            f"the real hook case on an environment {label}: one skip line and no case -> {lines}, {seen}",
        )


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(ok: Callable[[], bool], label: str) -> None:
        nonlocal total, wrong
        try:
            passed = ok()
        except Exception as e:  # noqa: BLE001 -- a case that crashes is BAD, and the next case still runs
            passed, label = False, f"{label}; raised {type(e).__name__}: {e}"
        total, wrong = total + 1, wrong + (not passed)
        print(f"{'ok ' if passed else 'BAD'}  strict: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-strict-") as tmp:
        import_cases(case, pathlib.Path(tmp))
        timeout_cases(case, pathlib.Path(tmp))
        chmod_cases(case, pathlib.Path(tmp))
        handler_cases(case)
        hook_cases(case, pathlib.Path(tmp))
        real_hook_cases(case, pathlib.Path(tmp))
        skip_cases(case, pathlib.Path(tmp))
    return total, wrong
