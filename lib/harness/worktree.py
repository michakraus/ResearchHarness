"""`harness worktree`: ask the installed worktree hook to make or remove a worktree.

    harness worktree add <name> [--apply]
    harness worktree remove <path> [--apply]

OpenCode and oh-my-pi have no `WorktreeCreate` hook, so an agent there runs this subcommand in
the repository instead. It runs the hook that `harness install` puts at
`~/.claude/hooks/worktree.py`, below the home that `HOME` gives, as the hook itself reads it, with
the payload that Claude Code sends it on stdin: `{"hook_event_name": "WorktreeCreate", "cwd": …,
"name": …}` for `add`, `{"hook_event_name": "WorktreeRemove", "worktree_path": …}` for `remove`.
The hook holds the whole logic of a worktree, and under `agentbox` it asks the broker outside the
sandbox; this subcommand runs no git of its own.

The dry run prints the request in one line and exits 1. `--apply` runs the hook with this
interpreter, in the working directory, for at most TIMEOUT seconds; it prints the hook's stdout,
which is the worktree's path for `add`, passes the hook's stderr on, and exits 0. A missing hook
and a hook that exits other than 0 are a HarnessError, so `harness` exits 2.
"""

import argparse
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Callable
from unittest import mock

from . import REPO, HarnessError, changing, fmt, jsonio

# Seconds for the hook's run: the hook's client of the broker waits up to 420 s for an answer.
TIMEOUT = 480
DRY = 1  # the exit status of a dry run
FAILED = 2  # the exit status of a HarnessError


def hook() -> pathlib.Path:
    """The installed worktree hook, below the home of `HOME`."""
    return pathlib.Path.home() / ".claude" / "hooks" / "worktree.py"


def request(payload: dict[str, str], plan: str, *, apply: bool) -> int:
    """With `apply`, send `payload` to the hook on its stdin and return 0; without it, print
    `plan`, the request in words, and return 1. The hook's stderr goes to stderr; its last line
    is the reason of the HarnessError when the hook exits other than 0."""
    script = hook()
    if not apply:
        print(f"would ask {script} {plan}")
        return DRY
    if not script.is_file():
        raise HarnessError(f"{script} does not exist; `harness install --apply` installs it")
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        cwd=pathlib.Path.cwd(),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        lines = proc.stderr.strip().splitlines()
        raise HarnessError(lines[-1] if lines else f"{script} exited {proc.returncode}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    name = str(args.name)
    cwd = str(pathlib.Path.cwd())
    payload = {"hook_event_name": "WorktreeCreate", "cwd": cwd, "name": name}
    return request(payload, f"to make the worktree {name} of the repository at {cwd}", apply=args.apply)


def cmd_remove(args: argparse.Namespace) -> int:
    path = str(pathlib.Path(str(args.path)).absolute())
    payload = {"hook_event_name": "WorktreeRemove", "worktree_path": path}
    return request(payload, f"to remove the worktree {path}", apply=args.apply)


def register(sub: fmt.Subcommands) -> None:
    parser = sub.add_parser(
        "worktree",
        help="make or remove a worktree through the installed worktree hook",
        description="Run the installed worktree hook, ~/.claude/hooks/worktree.py, with the "
        "payload of a WorktreeCreate or WorktreeRemove event, for a frontend that has no "
        "worktree hook. Without --apply it prints the request and exits 1; --apply runs the "
        "hook in the working directory and prints its output, the worktree's path for add.",
    )
    actions = parser.add_subparsers(dest="action", metavar="<action>", required=True)
    add = changing(
        actions.add_parser(
            "add",
            help="make a worktree of the repository that holds the working directory",
            description="Ask the hook for the worktree NAME of the repository that holds the "
            "working directory: a branch NAME, or a detached worktree for agent-<hex>. It "
            "prints the worktree's path.",
        )
    )
    add.add_argument("name", metavar="NAME", help="the branch, or agent-<hex> for a detached worktree")
    add.set_defaults(run=cmd_add)
    remove = changing(
        actions.add_parser(
            "remove",
            help="remove a worktree",
            description="Ask the hook to remove the worktree at PATH, without --force.",
        )
    )
    remove.add_argument("path", metavar="PATH", help="the worktree, absolute or relative")
    remove.set_defaults(run=cmd_remove)


# A stub of the hook: it writes its stdin, its working directory and its arguments to LOG, prints
# its answer on stdout, writes its stderr and exits with its status.
STUB = """import json, os, sys
with open({log!r}, "w") as f:
    json.dump({{"stdin": sys.stdin.read(), "cwd": os.getcwd(), "argv": sys.argv[1:]}}, f)
sys.stderr.write({err!r})
print({out!r})
sys.exit({code})
"""
HARNESS = [sys.executable, str(REPO / "bin" / "harness")]
DELTAS = (REPO / "adapters" / "opencode" / "OPENCODE-DELTA.md", REPO / "adapters" / "omp" / "OMP-DELTA.md")


class Fixture:
    """A fixture home whose hook is a stub, and a working directory beside it, below `tmp`."""

    def __init__(self, tmp: pathlib.Path) -> None:
        self.home, self.work, self.log = tmp / "home", tmp / "work", tmp / "log.json"
        self.stub = self.home / ".claude" / "hooks" / "worktree.py"
        self.work.mkdir(parents=True)

    def install(self, out: str = "/fixture/worktree", err: str = "", code: int = 0) -> None:
        """Put a stub that prints `out`, writes `err` to stderr and exits `code` in place of the
        hook."""
        self.stub.parent.mkdir(parents=True, exist_ok=True)
        self.stub.write_text(STUB.format(log=str(self.log), out=out, err=err, code=code))

    def run(self, *argv: str) -> subprocess.CompletedProcess[str]:
        """`harness worktree <argv>` in the working directory, with HOME the fixture home and the
        rest of the environment kept."""
        self.log.unlink(missing_ok=True)
        return subprocess.run(
            [*HARNESS, "worktree", *argv],
            cwd=self.work,
            env=dict(os.environ, HOME=str(self.home)),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def logged(self) -> tuple[dict[str, jsonio.JsonValue], str, jsonio.JsonValue] | None:
        """The stub's payload, working directory and arguments; None when no stub ran."""
        if not self.log.exists():
            return None
        entry = jsonio.loads(self.log.read_text(), where=str(self.log))
        return jsonio.loads(str(entry["stdin"]), where="the payload"), str(entry["cwd"]), entry["argv"]


def command_cases(check: Callable[[object, str], None], f: Fixture) -> None:
    """`harness worktree` against the stub: the dry runs, the payloads, the exits and the
    output."""
    work = str(f.work)
    f.install()
    p = f.run("add", "x")
    check(
        p.returncode == DRY and "x" in p.stdout and work in p.stdout and f.logged() is None,
        "the dry run of add names the worktree and the working directory, exits 1, runs no hook",
    )
    p = f.run("remove", "rel")
    check(
        p.returncode == DRY and str(f.work / "rel") in p.stdout and f.logged() is None,
        "the dry run of remove names the absolute path, exits 1, runs no hook",
    )
    p = f.run("add", "x", "--apply")
    logged = f.logged()
    check(
        logged == ({"hook_event_name": "WorktreeCreate", "cwd": work, "name": "x"}, work, []),
        "add --apply runs the hook below the home of HOME, in the working directory, with no "
        f"argument, and sends the WorktreeCreate payload of the working directory: {logged}",
    )
    check(
        p.returncode == 0 and p.stdout == "/fixture/worktree\n",
        f"add --apply prints the hook's stdout and exits 0: {p.returncode} {p.stdout!r}",
    )
    p = f.run("remove", "rel", "--apply")
    logged = f.logged()
    check(
        logged is not None
        and logged[0] == {"hook_event_name": "WorktreeRemove", "worktree_path": str(f.work / "rel")},
        f"remove --apply sends the WorktreeRemove payload with the absolute path: {logged}",
    )
    check(p.returncode == 0, f"remove --apply exits 0: {p.returncode}")
    f.install(err="worktree hook: first line\nworktree hook: the last line\n\n", code=1)
    p = f.run("add", "x", "--apply")
    check(
        p.returncode == FAILED
        and p.stderr.endswith("harness worktree: worktree hook: the last line\n")
        and "worktree hook: first line\n" in p.stderr,
        f"a failing hook exits 2 with its last line, and its stderr reaches stderr: {p.stderr!r}",
    )
    f.install(code=3)
    p = f.run("add", "x", "--apply")
    check(
        p.returncode == FAILED and p.stderr == f"harness worktree: {f.stub} exited 3\n",
        f"a hook that fails with no stderr exits 2 and names its status: {p.stderr!r}",
    )
    p = f.run()
    check(
        p.returncode == FAILED and "<action>" in p.stderr and f.logged() is None,
        f"`harness worktree` with no action is a usage error: {p.returncode} {p.stderr!r}",
    )
    f.install(err="worktree hook: fetched\n")
    p = f.run("add", "x", "--apply")
    check(
        p.returncode == 0 and p.stderr == "worktree hook: fetched\n",
        f"the stderr of a hook that succeeds reaches stderr: {p.stderr!r}",
    )
    f.stub.unlink()
    p = f.run("add", "x", "--apply")
    check(
        p.returncode == FAILED
        and p.stderr.startswith("harness worktree: ")
        and "harness install --apply" in p.stderr
        and f.logged() is None,
        f"a missing hook exits 2 and names `harness install --apply`: {p.stderr!r}",
    )


def timeout_case(check: Callable[[object, str], None], f: Fixture) -> None:
    """The hook runs with this interpreter and a timeout of 480 s, read from the call."""
    runs: list[dict[str, object]] = []

    def fake(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        runs.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, "", "")

    f.install()
    with (
        mock.patch.dict(os.environ, {"HOME": str(f.home)}),
        mock.patch.object(subprocess, "run", fake),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        request({"hook_event_name": "WorktreeRemove", "worktree_path": "/x"}, "", apply=True)
    check(
        [(r["command"], r.get("timeout")) for r in runs] == [([sys.executable, str(f.stub)], 480)],
        f"the hook runs with this interpreter and a timeout of 480 s: {runs}",
    )


def selftest() -> tuple[int, int]:
    """`harness worktree` in a fixture home whose hook is a stub, and the deltas of the two
    frontends that use it: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok: object, label: str) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  worktree: {label}")

    with tempfile.TemporaryDirectory() as name:
        tmp = pathlib.Path(name).resolve()
        command_cases(check, Fixture(tmp / "command"))
        timeout_case(check, Fixture(tmp / "timeout"))
    for delta in DELTAS:
        text = delta.read_text()
        check(
            "## Worktrees: ask for them" in text
            and "harness worktree add <branch> --apply" in text
            and "harness worktree remove <path> --apply" in text
            and "git worktree add" not in text,
            f"{delta.name} sends the agent to `harness worktree` and not to `git worktree add`",
        )
    return total, wrong
