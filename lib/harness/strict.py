"""The cases of the strict profile of the Python code: the hooks and the guards import only the
standard library, and `.githooks/pre-commit` refuses a commit that fails `ruff format --check`,
`ruff check` or `basedpyright`.

The import cases parse each `.py` file below `hooks/` and `githooks/pre-commit-wiki` with `ast`,
in this repository and in scratch trees. The hook cases
commit in a scratch repository whose `core.hooksPath` is this checkout's `.githooks/`, with
$RESEARCH_HARNESS_PYTHON set to a scratch
environment whose `bin/` holds stubs of `ruff` and `basedpyright`. A stub logs its arguments and
its working directory, and fails on a marker in a `.py` file of that directory: BADFORMAT for
`ruff format --check`, BADLINT for `ruff check`, BADTYPE for `basedpyright`. `ruff format`
without `--check` rewrites each file with BADFORMAT, as the formatter does. A second pair of
stubs on the PATH logs that it ran and passes.
"""

import ast
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable

from . import REPO

HOOK = REPO / ".githooks" / "pre-commit"
TOOLS = ("ruff", "basedpyright")
TIMEOUT = 60
# The modules beyond the standard library that a file may import: the hook probe loads the
# harness's own package, and the guard's tables of Claude Code and Antigravity import the guard
# package by its name `guard`, whose parent directory the guard's `__main__` puts on `sys.path`.
OWN = {
    "hooks/probe.py": frozenset({"harness"}),
    "hooks/guard/frontends/claude.py": frozenset({"guard"}),
    "hooks/guard/frontends/antigravity.py": frozenset({"guard"}),
}
# The three commands of the hook, as the stubs log them.
COMMANDS = ["ruff format --check --no-cache .", "ruff check --no-cache .", "basedpyright"]

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
) -> Run:
    """Stage the files `staged` in a new scratch repository below `tmp`, write `unstaged` into the
    work tree after that, and run `git commit` with the hook, with the stubs of `tools` in the
    environment's `bin/` and stubs of both tools on the PATH."""
    base = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    repo, environment, path, log = base / "repo", base / "env", base / "path", base / "log"
    for d in (repo, environment / "bin", path):
        d.mkdir(parents=True)
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
    (path / "python3").symlink_to(sys.executable)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "RESEARCH_HARNESS_"))}
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

    run = commit(tmp, clean)
    places = {line.partition(" | ")[2] for line in run.log}
    case(
        lambda: run.code == 0 and run.committed and commands(run) == COMMANDS,
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
            and commands(run) == COMMANDS
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
        hook_cases(case, pathlib.Path(tmp))
    return total, wrong
