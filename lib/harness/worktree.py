"""`harness worktree`: ask the installed worktree hook to make, remove or sweep worktrees.

    harness worktree add <name> [--apply]
    harness worktree remove <path> [--apply]
    harness worktree sweep [--apply]

OpenCode and oh-my-pi have no `WorktreeCreate` event, so an agent there runs this subcommand in
the repository instead. It runs the hook that `harness install` puts at
`~/.claude/hooks/worktree.py`, below the home that `HOME` gives, as the hook itself reads it. For
`add` and `remove` it sends the payload that Claude Code sends on stdin: `{"hook_event_name":
"WorktreeCreate", "cwd": …, "name": …}` for `add`, `{"hook_event_name": "WorktreeRemove",
"worktree_path": …}` for `remove`. For `sweep` it runs the hook's own `sweep`, with `--apply`
where it is given. The hook holds the whole logic of a worktree and of the sweep, and under
`agentbox` it asks the broker outside the sandbox; this subcommand runs no git.

The dry run of `add` and `remove` prints the request in one line and exits 1. `--apply` runs the
hook with this interpreter, in the working directory and in a session of its own, for at most
TIMEOUT seconds; it prints the hook's stdout, which is the worktree's path for `add`, passes the
hook's stderr on, and exits 0. `sweep` runs the hook in the same way also without `--apply`: the
hook's dry run lists the worktrees and exits 1, and so does `sweep`. A missing hook, a hook that
exits other than 0 (other than 1 for the dry run of `sweep`) or runs longer than TIMEOUT seconds,
a NAME or a PATH that is empty or holds a line break, and a working directory that no longer
exists are a HarnessError, so `harness` exits 2. A SIGINT, SIGTERM or SIGHUP during the hook's run,
the stop after a timeout included, goes on to the hook's process group, and `harness` then exits
128 + the signal's number, not 2.

The hook refuses a remove that it cannot finish, so run `remove --apply` and `sweep --apply` under
`agentbox` or from a terminal, not from a sandboxed call: there the hook's own git runs in the
sandbox. The nightly job `worktree-sweep` runs the hook's `sweep --apply` outside any sandbox.
"""

import argparse
import contextlib
import dataclasses
import io
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from unittest import mock

from . import REPO, HarnessError, changing, fmt, jsonio

# Seconds for the hook's run: the hook's client of the broker waits up to 420 s for an answer.
TIMEOUT = 480
# Seconds between the SIGTERM and the SIGKILL of the hook's process group after the timeout.
GRACE = 5
DRY = 1  # the exit status of a dry run
FAILED = 2  # the exit status of a HarnessError
# Seconds for each `git` that builds the sweep's fixture, and the hook's FRESH, the seconds since a
# worktree's last use within which its sweep keeps it.
GIT_TIMEOUT = 30
FRESH = 12 * 3600


def hook() -> pathlib.Path:
    """The installed worktree hook, below the home of `HOME`."""
    return pathlib.Path.home() / ".claude" / "hooks" / "worktree.py"


def here() -> pathlib.Path:
    """The working directory; a HarnessError where it no longer exists."""
    try:
        return pathlib.Path.cwd()
    except FileNotFoundError:
        raise HarnessError("the working directory does not exist") from None


def one_line(what: str, value: str) -> str:
    """`value`, which must be one line that is not empty: a line break would split the dry run's
    line, and the hook refuses a worktree name that holds one."""
    if value.splitlines() != [value]:
        raise HarnessError(f"the {what} {value!r} is empty or holds a line break")
    return value


def signal_group(proc: subprocess.Popen[str], signum: int) -> None:
    """Send `signum` to the hook's process group. A group that is gone raises ProcessLookupError,
    and on macOS a group that holds only the unreaped hook raises PermissionError; neither has a
    program left to stop."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signum)


def stop(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """Stop the hook's process group, which holds the programs that it started: SIGTERM, so that
    git removes its lock files, then SIGKILL after GRACE seconds. Return the hook's stdout and
    stderr, or nothing where a program outside the group still holds the pipes."""
    for signum in (signal.SIGTERM, signal.SIGKILL):
        signal_group(proc, signum)
        with contextlib.suppress(subprocess.TimeoutExpired):
            return proc.communicate(timeout=GRACE)
    return "", ""


@dataclasses.dataclass(frozen=True)
class Ran:
    """The hook's run: its exit status, None where it did not end; its stdout and stderr; and the
    first SIGINT, SIGTERM or SIGHUP that arrived while it ran, or None."""

    status: int | None
    out: str
    err: str
    signum: int | None


def run_hook(script: pathlib.Path, payload: dict[str, str] | None, argv: tuple[str, ...] = ()) -> Ran:
    """Run the hook with the arguments `argv` and `payload` on its stdin, an empty stdin for None,
    in the working directory and in a session of its own; its output is decoded with replacement
    characters. A SIGINT, SIGTERM or SIGHUP meanwhile
    goes on to the hook's process group: one that arrives before the hook's process starts goes
    on right after the start. A hook that runs longer than TIMEOUT seconds is stopped, and is a
    HarnessError where no signal arrived."""
    cwd = here()
    received: list[int] = []
    missed: list[int] = []
    procs: list[subprocess.Popen[str]] = []

    def forward(signum: int, _frame: object) -> None:
        received.append(signum)
        if not procs:
            missed.append(signum)
        for proc in procs:
            signal_group(proc, signum)

    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {s: signal.signal(s, forward) for s in signals}
    try:
        proc = subprocess.Popen(  # the timeout is on `communicate`
            [sys.executable, str(script), *argv],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        procs.append(proc)
        # A signal before the line above went to no process group; one after it goes on in `forward`.
        if missed:
            signal_group(proc, missed[0])
        try:
            out, err = proc.communicate("" if payload is None else json.dumps(payload), timeout=TIMEOUT)
            timed_out = False
        except subprocess.TimeoutExpired:
            out, err = stop(proc)
            timed_out = True
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
    signum = received[0] if received else None
    if timed_out and signum is None:
        sys.stdout.write(out)
        sys.stderr.write(err)
        raise HarnessError(f"{script} takes more than {TIMEOUT} s and is stopped")
    return Ran(proc.returncode, out, err, signum)


def request(payload: dict[str, str], plan: str, *, apply: bool) -> int:
    """With `apply`, send `payload` to the hook on its stdin (`run`); without it, print `plan`, the
    request in words, and return 1."""
    if not apply:
        print(f"would ask {hook()} {plan}")
        return DRY
    return run(payload)


def run(payload: dict[str, str] | None, argv: tuple[str, ...] = (), *, dry: bool = False) -> int:
    """Run the hook with `argv` and `payload` on its stdin, and return 0, 1 where `dry` says that the
    hook runs its dry run and it exits 1, or 128 + n where the signal n arrived while the hook ran.
    The hook's stdout goes to stdout and its stderr to stderr; the last line of its stderr is the
    reason of the HarnessError when it exits with another status and no signal arrived."""
    script = hook()
    if not script.is_file():
        raise HarnessError(f"{script} does not exist; `harness install --apply` installs it")
    ran = run_hook(script, payload, argv)
    sys.stdout.write(ran.out)
    sys.stderr.write(ran.err)
    if ran.signum is not None:
        return 128 + ran.signum
    if dry and ran.status == DRY:
        return DRY
    if ran.status != 0:
        lines = ran.err.strip().splitlines()
        raise HarnessError(lines[-1] if lines else f"{script} exited {ran.status}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    name = one_line("name", str(args.name))
    cwd = str(here())
    payload = {"hook_event_name": "WorktreeCreate", "cwd": cwd, "name": name}
    return request(payload, f"to make the worktree {name} of the repository at {cwd}", apply=args.apply)


def cmd_remove(args: argparse.Namespace) -> int:
    given = pathlib.Path(one_line("path", str(args.path)))
    path = str(given if given.is_absolute() else here() / given)
    payload = {"hook_event_name": "WorktreeRemove", "worktree_path": path}
    return request(payload, f"to remove the worktree {path}", apply=args.apply)


def cmd_sweep(args: argparse.Namespace) -> int:
    if args.apply:
        return run(None, ("sweep", "--apply"))
    return run(None, ("sweep",), dry=True)


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
    sweep = changing(
        actions.add_parser(
            "sweep",
            help="list the worktrees, and remove the clean ones that origin/HEAD holds",
            description="List each directory below ~/Research/.worktrees as removable (clean, its "
            "HEAD in origin/HEAD, unused for 12 hours), kept, or orphan (no record of git). With "
            "--apply, ask the hook to remove each removable one. An orphan is never touched.",
        )
    )
    sweep.set_defaults(run=cmd_sweep)


# A stub of the hook: it writes its stdin, its working directory and its arguments to LOG, writes
# its bytes to stderr and its answer to stdout, and exits with its status.
STUB = """import json, os, sys
with open({log!r}, "w") as f:
    json.dump({{"stdin": sys.stdin.read(), "cwd": os.getcwd(), "argv": sys.argv[1:]}}, f)
sys.stderr.buffer.write({err!r})
sys.stdout.buffer.write({out!r} + b"\\n")
sys.exit({code})
"""
# A stub that starts a child which keeps the hook's pipes open for {seconds} s, in a session of its
# own with {escape}, writes a line to stderr, then hangs; with {ignore} it ignores SIGTERM.
HANG = """import signal, subprocess, sys, time
sys.stdin.read()
if {ignore}:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
subprocess.Popen(["sleep", "{seconds}"], start_new_session={escape})
sys.stderr.write("worktree hook: fetching\\n")
sys.stderr.flush()
time.sleep(60)
"""
# A stub that sends its caller the signal {signum}, then sleeps and prints "done".
SIGNAL = """import os, sys, time
sys.stdin.read()
sys.stderr.write("worktree hook: started\\n")
sys.stderr.flush()
os.kill(os.getppid(), {signum})
time.sleep(20)
print("done")
"""
# Runs argv[2:] in the directory argv[1], which it removes first.
GONE = "import os, sys; os.chdir(sys.argv[1]); os.rmdir(sys.argv[1]); os.execv(sys.argv[2], sys.argv[2:])"
HARNESS = [sys.executable, str(REPO / "bin" / "harness")]
DELTAS = (REPO / "adapters" / "opencode" / "OPENCODE-DELTA.md", REPO / "adapters" / "omp" / "OMP-DELTA.md")


class Fixture:
    """A fixture home whose hook is a stub, and a working directory beside it, below `tmp`."""

    def __init__(self, tmp: pathlib.Path) -> None:
        self.home, self.work, self.log = tmp / "home", tmp / "work", tmp / "log.json"
        self.stub = self.home / ".claude" / "hooks" / "worktree.py"
        self.work.mkdir(parents=True)

    def install(self, out: bytes = b"/fixture/worktree", err: bytes = b"", code: int = 0) -> None:
        """Put a stub that prints `out`, writes `err` to stderr and exits `code` in place of the
        hook."""
        self.write(STUB.format(log=str(self.log), out=out, err=err, code=code))

    def write(self, text: str) -> None:
        """Put the script `text` in place of the hook."""
        self.stub.parent.mkdir(parents=True, exist_ok=True)
        self.stub.write_text(text)

    def install_hook(self) -> None:
        """Put the repository's worktree hook and its guard package in place of the hook."""
        self.stub.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / "hooks" / "worktree.py", self.stub)
        shutil.rmtree(self.stub.parent / "guard", ignore_errors=True)
        shutil.copytree(
            REPO / "hooks" / "guard", self.stub.parent / "guard", ignore=shutil.ignore_patterns("__pycache__")
        )

    def raw(self) -> tuple[str, jsonio.JsonValue] | None:
        """The stub's stdin, as text, and its arguments; None when no stub ran."""
        if not self.log.exists():
            return None
        entry = jsonio.loads(self.log.read_text(), where=str(self.log))
        return str(entry["stdin"]), entry["argv"]

    def run(self, *argv: str, gone: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
        """`harness worktree <argv>` in the working directory, with HOME the fixture home and the
        rest of the environment kept but its GIT_* variables, which would reach the hook's git; with
        `gone`, in that directory, removed before the start."""
        self.log.unlink(missing_ok=True)
        command = [*HARNESS, "worktree", *argv]
        if gone is not None:
            gone.mkdir()
            command = [sys.executable, "-c", GONE, str(gone), *command]
        return subprocess.run(
            command,
            cwd=self.work,
            env={**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, "HOME": str(self.home)},
            capture_output=True,
            text=True,
            errors="replace",
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
    p = f.run("add", "g3b-dry-name")
    check(
        p.returncode == DRY
        and p.stdout == f"would ask {f.stub} to make the worktree g3b-dry-name of the repository at {work}\n"
        and f.logged() is None,
        "the dry run of add names the worktree and the working directory in one line, exits 1, "
        f"runs no hook: {p.returncode} {p.stdout!r}",
    )
    p = f.run("remove", "rel")
    check(
        p.returncode == DRY
        and p.stdout == f"would ask {f.stub} to remove the worktree {f.work / 'rel'}\n"
        and f.logged() is None,
        f"the dry run of remove names the absolute path in one line, exits 1, runs no hook: {p.stdout!r}",
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
    f.install(err=b"worktree hook: first line\nworktree hook: the last line\n\n", code=1)
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
    f.install(err=b"worktree hook: fetched\n")
    p = f.run("add", "x", "--apply")
    check(
        p.returncode == 0 and p.stderr == "worktree hook: fetched\n",
        f"the stderr of a hook that succeeds reaches stderr: {p.stderr!r}",
    )
    f.install(out=b"/fixture/\xffworktree", err=b"worktree hook: no \xfe UTF-8\n", code=1)
    p = f.run("add", "x", "--apply")
    replaced = chr(0xFFFD)
    check(
        p.returncode == FAILED
        and p.stdout == f"/fixture/{replaced}worktree\n"
        and p.stderr.endswith(f"harness worktree: worktree hook: no {replaced} UTF-8\n"),
        "a hook's output that is not UTF-8 reaches the caller with replacement characters: "
        f"{p.returncode} {p.stdout!r} {p.stderr!r}",
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


def argument_cases(check: Callable[[object, str], None], f: Fixture) -> None:
    """A NAME or a PATH that is empty or holds a line break, and a working directory that no
    longer exists, are a HarnessError before the hook runs."""
    f.install()
    for value in ("", "a\nb", "agent-ab\n", "a\rb", f"a{chr(0x2028)}b"):
        for action in ("add", "remove"):
            for apply in ((), ("--apply",)):
                p = f.run(action, value, *apply)
                check(
                    p.returncode == FAILED
                    and p.stdout == ""
                    and p.stderr.startswith("harness worktree: ")
                    and "line break" in p.stderr
                    and f.logged() is None,
                    f"`{action} {value!r} {' '.join(apply)}` is refused before the hook runs: "
                    f"{p.returncode} {p.stdout!r} {p.stderr!r}",
                )
    p = f.run("add", "a b", "--apply")
    logged = f.logged()
    check(
        p.returncode == 0 and logged is not None and logged[0]["name"] == "a b",
        f"a NAME with a space reaches the hook, which judges it: {p.returncode} {logged}",
    )
    gone = f.work.parent / "gone"
    for argv in (
        ("add", "x"),
        ("add", "x", "--apply"),
        ("remove", "rel"),
        ("remove", str(f.work), "--apply"),
    ):
        p = f.run(*argv, gone=gone)
        check(
            p.returncode == FAILED
            and p.stderr == "harness worktree: the working directory does not exist\n"
            and f.logged() is None,
            f"`{' '.join(argv)}` in a removed working directory exits 2 with one line: "
            f"{p.returncode} {p.stderr!r}",
        )
    p = f.run("remove", str(f.work), gone=gone)
    check(
        p.returncode == DRY and p.stdout == f"would ask {f.stub} to remove the worktree {f.work}\n",
        "the dry run of remove with an absolute path needs no working directory: "
        f"{p.returncode} {p.stdout!r}",
    )


def signal_cases(check: Callable[[object, str], None], f: Fixture) -> None:
    """A SIGINT, SIGTERM or SIGHUP of `harness worktree` reaches the hook's process group, and
    `harness worktree` then exits 128 + the signal's number."""
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        f.write(SIGNAL.format(signum=int(signum)))
        p = f.run("add", "x", "--apply")
        check(
            p.returncode == 128 + signum
            and "worktree hook: started\n" in p.stderr
            and "done" not in p.stdout,
            f"a {signum.name} of `harness worktree` stops the hook and exits {128 + signum}: "
            f"{p.returncode} {p.stdout!r} {p.stderr!r}",
        )


def timeout_cases(check: Callable[[object, str], None], f: Fixture) -> None:
    """The hook runs with this interpreter, in a session of its own, for at most 480 s; a hook
    that runs longer is stopped with its process group, and its stderr up to then is passed on."""
    runs: list[dict[str, object]] = []

    class Fake:
        def __init__(self, command: list[str], **kwargs: object) -> None:
            runs.append({"command": command, **kwargs})
            self.pid, self.returncode = 0, 0

        def communicate(self, payload: str | None = None, timeout: float | None = None) -> tuple[str, str]:
            runs.append({"payload": payload, "timeout": timeout})
            return "", ""

    f.install()
    payload: dict[str, str] = {"hook_event_name": "WorktreeRemove", "worktree_path": "/x"}
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    before = [signal.getsignal(s) for s in signals]
    with (
        mock.patch.dict(os.environ, {"HOME": str(f.home)}),
        mock.patch.object(subprocess, "Popen", Fake),
        contextlib.chdir(f.work),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        request(payload, "", apply=True)
    check(
        [(r.get("command"), r.get("start_new_session"), r.get("cwd"), r.get("timeout")) for r in runs]
        == [([sys.executable, str(f.stub)], True, f.work, None), (None, None, None, 480)],
        f"the hook runs with this interpreter, in a session of its own, with a timeout of 480 s: {runs}",
    )
    after = [signal.getsignal(s) for s in signals]
    check(after == before, f"the handlers of SIGINT, SIGTERM and SIGHUP are restored after the run: {after}")
    module = sys.modules[__name__]
    for ignore, escape, expected in (
        (False, False, "worktree hook: fetching\n"),
        (True, False, "worktree hook: fetching\n"),
        (False, True, ""),
    ):
        f.write(HANG.format(ignore=ignore, escape=escape, seconds=5 if escape else 60))
        err = io.StringIO()
        message = None
        with (
            mock.patch.dict(os.environ, {"HOME": str(f.home)}),
            mock.patch.object(module, "TIMEOUT", 1),
            mock.patch.object(module, "GRACE", 1),
            contextlib.chdir(f.work),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(err),
        ):
            try:
                request(payload, "", apply=True)
            except HarnessError as e:
                message = str(e)
        what = " and ignores SIGTERM" if ignore else " and whose child left its session" if escape else ""
        check(
            message == f"{f.stub} takes more than 1 s and is stopped" and err.getvalue() == expected,
            f"a hook that runs too long{what} is stopped with the children of its session, and its "
            f"stderr is passed on where no other program holds it: {message!r} {err.getvalue()!r}",
        )


def window_cases(check: Callable[[object, str], None], f: Fixture) -> None:
    """A signal that arrives before the hook's process joins the list of processes, or while a
    timeout stops the hook, reaches the hook's process group and makes `request` return 128 + its
    number; a timeout without a signal is a HarnessError. Each signal goes through
    the installed handler in this process, and `signal_group` is a recorder, so that no signal
    reaches the test runner."""
    module = sys.modules[__name__]
    payload: dict[str, str] = {"hook_event_name": "WorktreeRemove", "worktree_path": "/x"}
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    real = subprocess.Popen
    sent: list[tuple[object, int]] = []
    started: list[object] = []

    def record(proc: object, signum: int) -> None:
        sent.append((proc, signum))

    def deliver(signum: int) -> None:
        handler = signal.getsignal(signum)
        if callable(handler):
            handler(signum, None)

    def starting(*signums: int) -> Callable[..., subprocess.Popen[str]]:
        def early(command: list[str], **_kwargs: object) -> subprocess.Popen[str]:
            for signum in signums:
                deliver(signum)
            proc = real(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=f.work,
                text=True,
                start_new_session=True,
            )
            started.append(proc)
            return proc

        return early

    class Late:
        def __init__(self, command: list[str], **_kwargs: object) -> None:
            self.command, self.pid, self.returncode = command, 0, None
            started.append(self)

        def communicate(self, _payload: str | None = None, timeout: float | None = None) -> tuple[str, str]:
            raise subprocess.TimeoutExpired(self.command, timeout or 0)

    def stopping(*signums: int) -> Callable[[object], tuple[str, str]]:
        def stop_(_proc: object) -> tuple[str, str]:
            for signum in signums:
                deliver(signum)
            return "", "worktree hook: stopped\n"

        return stop_

    def run(popen: object, stopper: object, what: str) -> tuple[int | None, str | None, str]:
        """`request` with `popen` and `stopper` in place of Popen and `stop`: its return value or
        None, the HarnessError's message or None, and the stderr; checks the handlers after it."""
        sent.clear()
        started.clear()
        before = [signal.getsignal(s) for s in signals]
        err = io.StringIO()
        status = message = None
        with (
            mock.patch.dict(os.environ, {"HOME": str(f.home)}),
            mock.patch.object(subprocess, "Popen", popen),
            mock.patch.object(module, "signal_group", record),
            mock.patch.object(module, "stop", stopper),
            contextlib.chdir(f.work),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(err),
        ):
            try:
                status = request(payload, "", apply=True)
            except HarnessError as e:
                message = str(e)
        after = [signal.getsignal(s) for s in signals]
        check(after == before, f"after {what}, the three signals have their earlier handlers: {after}")
        return status, message, err.getvalue()

    f.install()
    what = "a SIGTERM before the hook's process joins the list"
    status, message, _ = run(starting(signal.SIGTERM), stop, what)
    check(
        status == 128 + signal.SIGTERM and message is None and sent == [(started[0], signal.SIGTERM)],
        f"{what} goes on to the hook's process group after the join, and request returns 143: "
        f"{status} {message!r} {sent} {started}",
    )
    what = "a SIGINT and then a SIGTERM before the hook's process joins the list"
    status, message, _ = run(starting(signal.SIGINT, signal.SIGTERM), stop, what)
    check(
        status == 128 + signal.SIGINT and message is None and sent == [(started[0], signal.SIGINT)],
        f"of {what}, the first goes on to the hook's process group after the join, and request "
        f"returns 130: {status} {message!r} {sent} {started}",
    )
    what = "a SIGTERM and then a SIGHUP while a timeout stops the hook"
    status, message, err = run(Late, stopping(signal.SIGTERM, signal.SIGHUP), what)
    check(
        status == 128 + signal.SIGTERM
        and message is None
        and sent == [(started[0], signal.SIGTERM), (started[0], signal.SIGHUP)]
        and err == "worktree hook: stopped\n",
        f"{what} go on to the hook's process group, the hook's stderr is passed on, and request "
        f"returns 143 for the first and raises no HarnessError: {status} {message!r} {sent} {err!r}",
    )
    what = "a timeout without a signal"
    status, message, err = run(Late, stopping(), what)
    check(
        status is None
        and message == f"{f.stub} takes more than {TIMEOUT} s and is stopped"
        and not sent
        and err == "worktree hook: stopped\n",
        f"{what} is the HarnessError of the timeout, and the hook's stderr is passed on: "
        f"{status} {message!r} {sent} {err!r}",
    )


def fixture_git(directory: pathlib.Path, *arguments: str) -> str:
    """git in `directory` with a fixed author and no configuration of the caller; its stdout."""
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "probe",
        "GIT_AUTHOR_EMAIL": "probe@example.org",
        "GIT_COMMITTER_NAME": "probe",
        "GIT_COMMITTER_EMAIL": "probe@example.org",
    }
    return subprocess.run(
        [shutil.which("git") or "git", "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=GIT_TIMEOUT,
        env=env,
    ).stdout


def sweep_fixture(f: Fixture) -> dict[str, pathlib.Path]:
    """A repository `Repo` below the fixture home's `Research`, whose `origin/HEAD` names its first
    commit, and below `Research/.worktrees` a worktree of each kind, by name: `old` clean at
    `origin/HEAD` and unused for two FRESH spans, `fresh` the same but new, `dirty` old with an
    untracked file, `ahead` old with a commit of its own, `lost` whose record is gone and `bare`
    with no `.git`; and a `.claude` directory, which is no worktree."""
    repo = f.home / "Research" / "Repo"
    root = f.home / "Research" / ".worktrees"
    root.mkdir(parents=True)
    repo.mkdir(parents=True)
    fixture_git(repo, "init", "--quiet", "--initial-branch=main")
    (repo / "a").write_text("a\n")
    fixture_git(repo, "add", "a")
    fixture_git(repo, "commit", "--quiet", "-m", "a")
    fixture_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    fixture_git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    trees = {name: root / f"Repo-{name}" for name in ("old", "fresh", "dirty", "ahead", "lost", "bare")}
    for name in ("old", "fresh", "dirty", "ahead", "lost"):
        fixture_git(repo, "worktree", "add", "--quiet", "--detach", str(trees[name]), "origin/main")
    (trees["dirty"] / "b").write_text("b\n")
    (trees["ahead"] / "a").write_text("c\n")
    fixture_git(trees["ahead"], "commit", "--quiet", "-am", "c")
    shutil.rmtree(repo / ".git" / "worktrees" / "Repo-lost")
    trees["bare"].mkdir()
    (root / ".claude").mkdir()
    for name in ("old", "dirty", "ahead"):
        aged(repo, trees[name])
    return trees


def aged(repo: pathlib.Path, tree: pathlib.Path) -> None:
    """Date the record of the worktree `tree` of `repo` two FRESH spans back."""
    old = time.time() - 2 * FRESH
    record = repo / ".git" / "worktrees" / tree.name
    for path in (record, record / "HEAD", record / "index", record / "logs" / "HEAD"):
        if path.exists():
            os.utime(path, (old, old))


def sweep_cases(check: Callable[[object, str], None], f: Fixture) -> None:
    """`harness worktree sweep` against a stub: the hook runs as `sweep` and `sweep --apply` with an
    empty stdin, its dry run's exit 1 is the dry run's, and any other failure exits 2 with the
    hook's last line; a SIGTERM during the run exits 143. Then through the repository's hook on a
    worktree of each kind: the dry run lists each with its kind, and not the hidden `.claude`,
    removes nothing and exits 1; `--apply` removes the one removable worktree alone; a removal that
    the hook refuses makes the sweep exit 2 and name the worktree."""
    for argv, code, want in (
        (("sweep",), 1, DRY),
        (("sweep", "--apply"), 0, 0),
        (("sweep",), 2, FAILED),
        (("sweep", "--apply"), 1, FAILED),
    ):
        f.install(out=b"listed", err=b"worktree hook: the last line\n" if code else b"", code=code)
        p = f.run(*argv)
        raw = f.raw()
        check(
            p.returncode == want
            and raw == ("", list(argv))
            and p.stdout == "listed\n"
            and (not code or "worktree hook: the last line" in p.stderr)
            and (want != FAILED or p.stderr.endswith("harness worktree: worktree hook: the last line\n")),
            f"`harness worktree {' '.join(argv)}` runs the hook as `{' '.join(argv)}` with an empty "
            f"stdin, and a hook that exits {code} gives {want}: "
            f"{p.returncode} {raw} {p.stdout!r} {p.stderr!r}",
        )
    f.write(SIGNAL.format(signum=int(signal.SIGTERM)))
    p = f.run("sweep", "--apply")
    check(
        p.returncode == 128 + signal.SIGTERM and "done" not in p.stdout,
        "a SIGTERM of `harness worktree sweep --apply` stops the hook and exits 143: "
        f"{p.returncode} {p.stdout!r}",
    )
    trees = sweep_fixture(f)
    kinds = {
        "old": "removable",
        "fresh": "kept",
        "dirty": "kept",
        "ahead": "kept",
        "lost": "orphan",
        "bare": "orphan",
    }
    f.install_hook()
    p = f.run("sweep")
    listed = {words[1]: words[0] for words in (line.split() for line in p.stdout.splitlines()[:-1])}
    check(
        p.returncode == DRY
        and listed == {str(trees[name]): kind for name, kind in kinds.items()}
        and p.stdout.endswith("would remove 1 worktrees\n")
        and trees["old"].is_dir(),
        f"the dry run of sweep lists each worktree with its kind, removes none and exits 1: "
        f"{p.returncode} {p.stdout!r} {p.stderr!r}",
    )
    p = f.run("sweep", "--apply")
    check(
        p.returncode == 0
        and not trees["old"].exists()
        and all(trees[name].is_dir() for name in kinds if name != "old"),
        f"sweep --apply removes the removable worktree alone: {p.returncode} {p.stdout!r} {p.stderr!r}",
    )
    repo = f.home / "Research" / "Repo"
    second = trees["old"].with_name("Repo-old2")
    fixture_git(repo, "worktree", "add", "--quiet", "--detach", str(second), "origin/main")
    aged(repo, second)
    shielded = second / ".githooks"
    shielded.mkdir()
    shielded.chmod(0o500)
    try:
        p = f.run("sweep", "--apply")
    finally:
        shielded.chmod(0o700)
    check(
        p.returncode == FAILED
        and "harness worktree: worktree hook: 1 of 1 removals failed: Repo-old2: this process cannot write"
        in p.stderr
        and second.is_dir(),
        f"a removal that the hook refuses makes sweep --apply exit 2 and name the worktree: "
        f"{p.returncode} {p.stderr!r}",
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
        argument_cases(check, Fixture(tmp / "argument"))
        signal_cases(check, Fixture(tmp / "signal"))
        timeout_cases(check, Fixture(tmp / "timeout"))
        window_cases(check, Fixture(tmp / "window"))
        sweep_cases(check, Fixture(tmp / "sweep"))
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
