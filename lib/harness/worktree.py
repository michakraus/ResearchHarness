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
interpreter, in the working directory and in a session of its own, for at most TIMEOUT seconds;
it prints the hook's stdout, which is the worktree's path for `add`, passes the hook's stderr on,
and exits 0. A missing hook, a hook that exits other than 0 or runs longer than TIMEOUT seconds,
a NAME or a PATH that is empty or holds a line break, and a working directory that no longer
exists are a HarnessError, so `harness` exits 2. A SIGINT, SIGTERM or SIGHUP during the hook's run
goes on to the hook's process group, and `harness` then exits 128 + the signal's number.
"""

import argparse
import contextlib
import io
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from unittest import mock

from . import REPO, HarnessError, changing, fmt, jsonio

# Seconds for the hook's run: the hook's client of the broker waits up to 420 s for an answer.
TIMEOUT = 480
# Seconds between the SIGTERM and the SIGKILL of the hook's process group after the timeout.
GRACE = 5
DRY = 1  # the exit status of a dry run
FAILED = 2  # the exit status of a HarnessError


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
    line and reach the hook's patterns, whose `$` matches before a final newline."""
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


def run_hook(script: pathlib.Path, payload: dict[str, str]) -> tuple[int, str, str]:
    """Run the hook with `payload` on its stdin, in the working directory and in a session of its
    own: (its exit status, its stdout, its stderr), decoded with replacement characters. A
    SIGINT, SIGTERM or SIGHUP meanwhile goes on to the hook's process group, and then ends this
    process with status 128 + its number; a hook that runs longer than TIMEOUT seconds is stopped
    and is a HarnessError."""
    cwd = here()
    received: list[int] = []
    procs: list[subprocess.Popen[str]] = []

    def forward(signum: int, _frame: object) -> None:
        received.append(signum)
        for proc in procs:
            signal_group(proc, signum)

    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {s: signal.signal(s, forward) for s in signals}
    try:
        proc = subprocess.Popen(  # the timeout is on `communicate`
            [sys.executable, str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        procs.append(proc)
        try:
            out, err = proc.communicate(json.dumps(payload), timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            out, err = stop(proc)
            sys.stdout.write(out)
            sys.stderr.write(err)
            raise HarnessError(f"{script} takes more than {TIMEOUT} s and is stopped") from None
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
    if received:
        sys.stdout.write(out)
        sys.stderr.write(err)
        raise SystemExit(128 + received[0])
    return proc.returncode, out, err


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
    status, out, err = run_hook(script, payload)
    sys.stdout.write(out)
    sys.stderr.write(err)
    if status != 0:
        lines = err.strip().splitlines()
        raise HarnessError(lines[-1] if lines else f"{script} exited {status}")
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

    def run(self, *argv: str, gone: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
        """`harness worktree <argv>` in the working directory, with HOME the fixture home and the
        rest of the environment kept; with `gone`, in that directory, removed before the start."""
        self.log.unlink(missing_ok=True)
        command = [*HARNESS, "worktree", *argv]
        if gone is not None:
            gone.mkdir()
            command = [sys.executable, "-c", GONE, str(gone), *command]
        return subprocess.run(
            command,
            cwd=self.work,
            env=dict(os.environ, HOME=str(self.home)),
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
