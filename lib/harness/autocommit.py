"""The cases of `launchagents/claude-autocommit` on the system that runs them, macOS or Linux.

Each case builds a fixture HOME in a temporary directory, with a `.claude` repository on `main`
that holds one plan and one memory index, committed and pushed to a bare remote, and a
`settings.json`. It runs the script on this interpreter with HOME, TMPDIR, the git identity and
XDG_STATE_HOME set in the child's environment, and git reading no global or system
configuration, so no case reaches the real `~/.claude`. A file that a case settles gets an mtime
of 2020, outside every quiescence window.

The module has no subcommand; its cases run in `harness test`.
"""

import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Protocol

from . import REPO, HarnessError

SCRIPT = REPO / "launchagents" / "claude-autocommit"
MEMORY = pathlib.PurePosixPath("projects", "-fixture", "memory")
SETTLED = 1577836800  # 2020-01-01
TIMEOUT = 60
LINUX = sys.platform.startswith("linux")


class Case(Protocol):
    """The recorder of one case: its label and its verdict."""

    def __call__(self, label: str, *, ok: bool) -> None: ...


def git_program() -> str:
    """The git of the PATH, which the script runs too."""
    found = shutil.which("git")
    if found is None:
        raise HarnessError("the cases of claude-autocommit need git on the PATH")
    return found


class Fixture:
    """A fixture HOME with its `.claude` repository, the bare remote and the environment."""

    def __init__(self, home: pathlib.Path) -> None:
        self.home = home
        self.repo = home / ".claude"
        self.remote = home / "remote.git"
        (home / "tmp").mkdir(parents=True)
        self.env = {
            "HOME": str(home),
            "PATH": os.environ.get("PATH", ""),
            "TMPDIR": str(home / "tmp"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.org",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.org",
        }
        self.git_in(home, "init", "-q", "--bare", "-b", "main", str(self.remote))
        self.git_in(home, "init", "-q", "-b", "main", str(self.repo))
        self.write("plans/first.md", "a plan\n")
        self.write(f"{MEMORY}/MEMORY.md", "- [one](one.md)\n")
        (self.repo / "settings.json").write_text("{}\n", encoding="utf-8")
        self.git("add", "plans", str(MEMORY), "settings.json")
        self.git("commit", "-q", "-m", "initial")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "origin", "main")

    def git_in(self, directory: pathlib.Path, *args: str) -> str:
        return subprocess.run(
            [git_program(), *args],
            cwd=directory,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
            timeout=TIMEOUT,
        ).stdout.strip()

    def git(self, *args: str) -> str:
        return self.git_in(self.repo, *args)

    def remote_git(self, *args: str) -> str:
        return self.git_in(self.remote, *args)

    def write(self, name: str, text: str, *, settled: bool = True) -> pathlib.Path:
        """Write the file `name` of the repository; a settled file gets an mtime of 2020."""
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if settled:
            os.utime(path, (SETTLED, SETTLED))
        return path

    def run(self, *args: str, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        """The script on this interpreter, on the fixture's repository."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env={**self.env, "CLAUDE_AUTOCOMMIT_REPO": str(self.repo), **(extra or {})},
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT,
        )


def lock_dir(home: pathlib.Path, xdg: str | None) -> pathlib.Path:
    """The lock's directory on this system for a HOME and an XDG_STATE_HOME (None: unset)."""
    if not LINUX:
        return home / "Library" / "Logs" / "claude-autocommit"
    return (pathlib.Path(xdg) if xdg else home / ".local" / "state") / "claude-autocommit"


def julia_cases(case: Case, tmp: pathlib.Path) -> None:
    """The seven cases of the Julia test that the script had as a bash script, with its titles."""
    f = Fixture(tmp / "settled")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    (f.repo / "settings.json").write_text('{"changed": true}\n', encoding="utf-8")
    f.git("add", "settings.json")
    p = f.run()
    case(
        "a settled memory is committed and pushed; a staged file outside stays staged",
        ok=p.returncode == 0
        and "committed 0 plan(s), 1 memory file(s)" in p.stdout
        and f.git("show", "--name-only", "--format=", "HEAD").split() == [f"{MEMORY}/one.md"]
        and f.remote_git("rev-parse", "main") == f.git("rev-parse", "HEAD")
        and f.git("diff", "--cached", "--name-only") == "settings.json",
    )

    for label, branch in (("unset", None), ("memory/test", "memory/test")):
        f = Fixture(tmp / f"branch-{label.replace('/', '-')}")
        before = f.remote_git("rev-parse", "main")
        f.write(f"{MEMORY}/one.md", "one fact\n")
        p = f.run(extra={} if branch is None else {"CLAUDE_AUTOCOMMIT_BRANCH": branch})
        head = f.git("rev-parse", "HEAD")
        branches = sorted(f.remote_git("for-each-ref", "--format=%(refname:short)", "refs/heads").split())
        if branch is None:
            pushed = branches == ["main"] and f.remote_git("rev-parse", "main") == head
        else:
            pushed = (
                branches == sorted(["main", branch])
                and f.remote_git("rev-parse", branch) == head
                and f.remote_git("rev-parse", "main") == before
            )
        case(
            f"the push goes to CLAUDE_AUTOCOMMIT_BRANCH ({label})",
            ok=p.returncode == 0 and head != before and pushed,
        )

    for label, xdg in (("unset", None), ("empty", ""), ("set", "state")):
        f = Fixture(tmp / f"xdg-{label}")
        extra = {} if xdg is None else {"XDG_STATE_HOME": str(f.home / xdg) if xdg else ""}
        expected = lock_dir(f.home, extra.get("XDG_STATE_HOME"))
        f.write(f"{MEMORY}/one.md", "one fact\n")
        p = f.run("--no-push", extra=extra)
        # The script removes the lock on exit and leaves the directory that holds it.
        others = [
            o
            for o in (f.home / "Library", f.home / ".local" / "state", f.home / "state")
            if not expected.is_relative_to(o) and o.exists()
        ]
        case(
            f"the lock lands at this system's path (XDG_STATE_HOME {label})",
            ok=p.returncode == 0 and expected.is_dir() and not (expected / "lock").exists() and not others,
        )

    f = Fixture(tmp / "held-lock")
    (lock_dir(f.home, None) / "lock").mkdir(parents=True)
    f.write(f"{MEMORY}/one.md", "one fact\n")
    head = f.git("rev-parse", "HEAD")
    p = f.run()
    case("a held lock defers the run", ok=p.returncode == 0 and f.git("rev-parse", "HEAD") == head)


def more_cases(case: Case, tmp: pathlib.Path) -> None:
    """The cases beyond the Julia test's: the classes of change, the refusals, the dry run, the
    locks and the push."""
    f = Fixture(tmp / "untracked-plan")
    f.write("plans/second.md", "a second plan\n")
    p = f.run("--no-push")
    message = f.git("log", "-1", "--format=%B").splitlines()
    case(
        "an untracked plan is committed, and the commit message names its path",
        ok=p.returncode == 0
        and f.git("show", "--name-status", "--format=", "HEAD").split() == ["A", "plans/second.md"]
        and message[0].startswith("chore(auto): 1 plan(s), 0 memory file(s) — ")
        and message[-1] == "plans/second.md",
    )

    f = Fixture(tmp / "deferred")
    f.write(f"{MEMORY}/one.md", "one fact\n", settled=False)
    f.write(f"{MEMORY}/MEMORY.md", "- [one](one.md)\n- [two](two.md)\n")
    f.write("plans/first.md", "a plan, changed\n")
    p = f.run("--no-push")
    case(
        "a memory that is still settling defers itself and its directory's MEMORY.md; the plan is committed",
        ok=p.returncode == 0
        and f"deferring {MEMORY}/MEMORY.md — a memory in the same directory is still settling" in p.stdout
        and "committed 1 plan(s), 0 memory file(s), 2 deferred" in p.stdout
        and f.git("show", "--name-only", "--format=", "HEAD").split() == ["plans/first.md"],
    )

    f = Fixture(tmp / "dry-run")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    head = f.git("rev-parse", "HEAD")
    p = f.run("--dry-run", extra={"CLAUDE_AUTOCOMMIT_BRANCH": "memory/test"})
    case(
        "the dry run names what it would commit and push, takes no lock and writes nothing",
        ok=p.returncode == 0
        and "would commit 0 plan(s) and 1 memory file(s); 0 deferred, 0 deletion(s)" in p.stdout
        and f"  {MEMORY}/one.md" in p.stdout.splitlines()
        and "would then: git push origin main:refs/heads/memory/test" in p.stdout
        and f.git("rev-parse", "HEAD") == head
        and not lock_dir(f.home, None).exists()
        and not any((f.home / "tmp").iterdir()),
    )

    f = Fixture(tmp / "rename")
    f.git("mv", "plans/first.md", "plans/renamed.md")
    p = f.run()
    case(
        "a rename exits 1 with one ERROR line and commits nothing",
        ok=p.returncode == 1
        and p.stderr.splitlines()[-1].endswith(
            "ERROR: rename under plans/ or memory/ (plans/renamed.md) — commit it by hand"
        )
        and len(p.stderr.splitlines()) == 1
        and f.git("rev-list", "--count", "HEAD") == "1",
    )

    for cap, code in (("1", 0), ("0", 1)):
        f = Fixture(tmp / f"deletion-{cap}")
        (f.repo / "plans" / "first.md").unlink()
        p = f.run("--no-push", extra={"CLAUDE_AUTOCOMMIT_MAX_DELETIONS": cap})
        case(
            f"one deletion with a cap of {cap} exits {code}",
            ok=p.returncode == code
            and (f.git("rev-list", "--count", "HEAD") == "2") == (code == 0)
            and (
                code == 0
                or "ERROR: 1 deletions under plans/ or memory/ exceeds the cap of 0 — commit by hand"
                in p.stderr
            ),
        )

    f = Fixture(tmp / "arguments")
    bogus, helped = f.run("--bogus"), f.run("--help")
    case(
        "an unknown argument exits 1 with the usage on stderr; --help prints it on stdout and exits 0",
        ok=bogus.returncode == 1
        and bogus.stdout == ""
        and bogus.stderr.startswith("unknown argument: --bogus\nusage: claude-autocommit [--dry-run]")
        and helped.returncode == 0
        and helped.stderr == ""
        and helped.stdout == bogus.stderr.partition("\n")[2]
        and f.run("-h").stdout == helped.stdout,
    )

    f = Fixture(tmp / "push-fails")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    f.git("remote", "set-url", "origin", str(f.home / "missing.git"))
    p = f.run()
    case(
        "a failed push leaves the commit local, warns on stderr and exits 0",
        ok=p.returncode == 0
        and "push failed (rc=128), commit is local — leaving it" in p.stderr
        and f.git("rev-list", "--count", "HEAD") == "2",
    )

    f = Fixture(tmp / "index-lock")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    (f.repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    p = f.run()
    case(
        "a locked index defers the run with one line and exit 0",
        ok=p.returncode == 0
        and "index locked by another process — retrying next interval" in p.stdout
        and f.git("rev-list", "--count", "HEAD") == "1",
    )


def repository_cases(case: Case, tmp: pathlib.Path) -> None:
    """The refusals of a repository: one whose pathspec matches no tracked file, bare or not, a
    missing directory and a plain one."""
    f = Fixture(tmp / "no-tracked")
    other = f.home / "other"
    f.git_in(f.home, "init", "-q", "-b", "main", str(other))
    (other / "README").write_text("x\n", encoding="utf-8")
    f.git_in(other, "add", "README")
    f.git_in(other, "commit", "-q", "-m", "x")
    for label, repo in (("a repository", other), ("a bare repository", f.remote)):
        p = f.run(extra={"CLAUDE_AUTOCOMMIT_REPO": str(repo)})
        case(
            f"{label} whose pathspec matches no tracked file exits 1",
            ok=p.returncode == 1
            and p.stderr.endswith(
                "ERROR: pathspec matches no tracked file — refusing to run (git behaviour changed, or "
                "this is a fresh repository with no plans and no memories yet)\n"
            ),
        )
    for label, directory in (
        ("a missing directory", f.home / "missing"),
        ("a plain directory", f.home / "tmp"),
    ):
        p = f.run(extra={"CLAUDE_AUTOCOMMIT_REPO": str(directory)})
        want = "no such directory" if label == "a missing directory" else "not a git repository"
        case(
            f"{label} exits 1 with one ERROR line",
            ok=p.returncode == 1
            and p.stderr.splitlines() == [p.stderr.strip()]
            and f"ERROR: {want}: " in p.stderr,
        )


def edge_cases(case: Case, tmp: pathlib.Path) -> None:
    """Nothing to commit, a new project's memory directory, the settings that are no integers, a
    PATH without git, the failures of git that a git on the PATH fakes (a status, an add and a
    commit that fail, a commit with nothing to commit and one on a locked index), a lock directory
    that cannot be made, and a run without a push."""
    f = Fixture(tmp / "nothing")
    quiet, dry = f.run(), f.run("--dry-run")
    case(
        "with nothing to commit a run prints nothing and the dry run says so; both exit 0",
        ok=quiet.returncode == 0
        and quiet.stdout == quiet.stderr == ""
        and dry.returncode == 0
        and dry.stdout.endswith(" claude-autocommit: nothing to commit (0 deferred)\n"),
    )

    # The memory directory of a new project is untracked, and git names the project's directory.
    f = Fixture(tmp / "new-project")
    f.write("projects/-other/memory/a.md", "a fact\n")
    p = f.run("--no-push")
    case(
        "the settled memory of a new project is committed, although its directory is new",
        ok=p.returncode == 0
        and f.git("show", "--name-only", "--format=", "HEAD") == "projects/-other/memory/a.md",
    )

    for name in (
        "CLAUDE_AUTOCOMMIT_QUIESCE_MIN",
        "CLAUDE_AUTOCOMMIT_MAX_DELETIONS",
        "CLAUDE_AUTOCOMMIT_PUSH",
    ):
        p = f.run(extra={name: "five"})
        case(
            f"{name}=five exits 1 with one ERROR line",
            ok=p.returncode == 1 and p.stderr.endswith(f"ERROR: {name} is not an integer: 'five'\n"),
        )

    f = Fixture(tmp / "no-git")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    p = f.run(extra={"PATH": str(f.home / "tmp")})
    case(
        "a PATH without git exits 1 with one ERROR line and leaves no lock",
        ok=p.returncode == 1
        and p.stderr.endswith("ERROR: no git on the PATH\n")
        and not (lock_dir(f.home, None) / "lock").exists(),
    )

    locked = "index locked by another process — retrying next interval"
    for n, (command, output, code, want) in enumerate(
        (
            (
                "ls-files",
                "fatal: no ls-files",
                1,
                "ERROR: pathspec matches no tracked file — refusing to run (git behaviour changed, or "
                "this is a fresh repository with no plans and no memories yet)",
            ),
            ("status", "fatal: no status", 1, "ERROR: git status failed (rc=128): fatal: no status"),
            ("add", "fatal: no add", 1, f"ERROR: git add failed for {MEMORY}/one.md (rc=128): fatal: no add"),
            ("commit", "fatal: no commit", 1, "ERROR: git commit failed (rc=128): fatal: no commit"),
            ("commit", "nothing to commit, working tree clean", 0, ""),
            ("commit", "no changes added to commit", 0, ""),
            ("commit", "fatal: Unable to create 'x/index.lock': File exists.", 0, locked),
        )
    ):
        f = Fixture(tmp / f"failing-{n}")
        f.write(f"{MEMORY}/one.md", "one fact\n")
        stub = f.home / "stub"
        stub.mkdir()
        (stub / "git").write_text(
            f'#!/bin/sh\n[ "$1" = {command} ] && {{ echo "{output}" >&2; exit 128; }}\n'
            f'exec "{git_program()}" "$@"\n',
            encoding="utf-8",
        )
        (stub / "git").chmod(0o755)
        p = f.run(extra={"PATH": f"{stub}{os.pathsep}{f.env['PATH']}"})
        said = p.stderr if code else p.stdout
        case(
            f"a git {command} that fails with {output!r} exits {code}"
            + (f" with {want!r}" if want else " and prints nothing"),
            ok=p.returncode == code
            and (said.endswith(f"{want}\n") if want else p.stdout == p.stderr == "")
            and f.git("rev-list", "--count", "HEAD") == "1",
        )

    # A lock directory whose parent cannot be made: a file stands where a directory must be.
    f = Fixture(tmp / "lock-parent")
    blocked = lock_dir(f.home, None).parent
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("", encoding="utf-8")
    p = f.run()
    case(
        "a lock directory that cannot be made exits 1 with one ERROR line",
        ok=p.returncode == 1 and p.stderr.endswith(f"ERROR: cannot create {lock_dir(f.home, None)}\n"),
    )

    f = Fixture(tmp / "no-push")
    for label, args, extra in (
        ("--no-push", ("--no-push",), {}),
        ("CLAUDE_AUTOCOMMIT_PUSH=0", (), {"CLAUDE_AUTOCOMMIT_PUSH": "0"}),
    ):
        before = f.remote_git("rev-parse", "main")
        f.write(f"plans/{label}.md", "a plan\n")
        p = f.run(*args, extra=extra)
        case(
            f"{label} commits and does not push",
            ok=p.returncode == 0
            and f.git("show", "--name-only", "--format=", "HEAD") == f"plans/{label}.md"
            and f.remote_git("rev-parse", "main") == before,
        )


def lock_cases(case: Case, tmp: pathlib.Path) -> None:
    """A lock older than 30 minutes is taken over; a SIGTERM during a run removes the lock."""
    f = Fixture(tmp / "stale-lock")
    lock = lock_dir(f.home, None) / "lock"
    lock.mkdir(parents=True)
    os.utime(lock, (time.time() - 31 * 60, time.time() - 31 * 60))
    f.write(f"{MEMORY}/one.md", "one fact\n")
    p = f.run("--no-push")
    case(
        "a lock older than 30 minutes is taken over, and the run commits",
        ok=p.returncode == 0
        and "lock older than 30m — taking it over" in p.stdout
        and f.git("rev-list", "--count", "HEAD") == "2"
        and not lock.exists(),
    )
    f = Fixture(tmp / "fresh-lock")
    lock = lock_dir(f.home, None) / "lock"
    lock.mkdir(parents=True)
    os.utime(lock, (time.time() - 29 * 60, time.time() - 29 * 60))
    f.write(f"{MEMORY}/one.md", "one fact\n")
    p = f.run("--no-push")
    case(
        "a lock 29 minutes old is held: the run exits 0 and commits nothing",
        ok=p.returncode == 0
        and p.stdout == ""
        and f.git("rev-list", "--count", "HEAD") == "1"
        and lock.is_dir(),
    )

    # A git on the PATH that waits, so the run holds its lock when the SIGTERM comes.
    f = Fixture(tmp / "sigterm")
    stub = f.home / "stub"
    stub.mkdir()
    (stub / "git").write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    (stub / "git").chmod(0o755)
    lock = lock_dir(f.home, None) / "lock"
    child = subprocess.Popen(
        [sys.executable, str(SCRIPT)],
        env={**f.env, "CLAUDE_AUTOCOMMIT_REPO": str(f.repo), "PATH": f"{stub}{os.pathsep}{f.env['PATH']}"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + TIMEOUT
    while not lock.is_dir() and time.monotonic() < deadline:
        time.sleep(0.05)
    held = lock.is_dir()
    child.send_signal(signal.SIGTERM)
    try:
        code = child.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        code = None
    finally:
        child.kill()
    case(
        "a SIGTERM during a run removes the lock",
        ok=held and code not in (None, 0) and not lock.exists() and lock.parent.is_dir(),
    )


def commit_sigterm_case(case: Case, tmp: pathlib.Path) -> None:
    """A SIGTERM while `git commit` holds the index lock: git ends on the SIGTERM that the run
    sends on, before it commits, and removes its own lock, so the next run commits. A pre-commit
    hook that waits holds `git commit` when the SIGTERM comes."""
    f = Fixture(tmp / "sigterm-commit")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    # The hook marks that `git commit` runs; `git add` takes the index lock too, but briefly.
    hook, marker = f.repo / ".git" / "hooks" / "pre-commit", f.home / "committing"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nsleep 5\n", encoding="utf-8")
    hook.chmod(0o755)
    index_lock = f.repo / ".git" / "index.lock"
    child = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--no-push"],
        env={**f.env, "CLAUDE_AUTOCOMMIT_REPO": str(f.repo)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + TIMEOUT
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    held = index_lock.exists()
    child.send_signal(signal.SIGTERM)
    try:
        code = child.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        code = None
    finally:
        child.kill()
    left = index_lock.exists()
    count = f.git("rev-list", "--count", "HEAD")
    hook.unlink()
    p = f.run("--no-push")
    case(
        "a SIGTERM during `git commit` stops that git and exits 143, and leaves no index.lock and no "
        "lock, and the next run commits",
        ok=held
        and code == 128 + signal.SIGTERM
        and not left
        and count == "1"
        and not (lock_dir(f.home, None) / "lock").exists()
        and p.returncode == 0
        and f.git("rev-list", "--count", "HEAD") == "2",
    )


def undecodable_case(case: Case, tmp: pathlib.Path) -> None:
    """A path whose name is not UTF-8, which a git on the PATH reports in `git status`, under
    LC_ALL=en_US.UTF-8, a locale in which Python's stdout and stderr refuse such a name by
    default: the dry run prints its bytes and exits 0, and a rename to it exits 1 with an ERROR
    line that holds its bytes. A file system that refuses such a name, as APFS does, cannot hold
    it, so the git of the case fakes the status."""
    f = Fixture(tmp / "undecodable")
    stub = f.home / "stub"
    stub.mkdir()
    (stub / "git").write_text(
        '#!/bin/sh\n[ "$1" = status ] && { printf "$STUB_STATUS"; exit 0; }\n'
        f'exec "{git_program()}" "$@"\n',
        encoding="utf-8",
    )
    (stub / "git").chmod(0o755)
    runs = [
        subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            env={
                **f.env,
                "CLAUDE_AUTOCOMMIT_REPO": str(f.repo),
                "PATH": f"{stub}{os.pathsep}{f.env['PATH']}",
                "LC_ALL": "en_US.UTF-8",
                "STUB_STATUS": status,
            },
            capture_output=True,
            check=False,
            timeout=TIMEOUT,
        )
        for status in ("?? plans/\\377.md\\0", "R  plans/\\377.md\\0plans/first.md\\0")
    ]
    case(
        "a path that is not UTF-8 is printed as its bytes by the dry run, which exits 0",
        ok=runs[0].returncode == 0 and b"\n  plans/\xff.md\n" in runs[0].stdout and runs[0].stderr == b"",
    )
    case(
        "a rename to a path that is not UTF-8 exits 1 with an ERROR line that holds its bytes",
        ok=runs[1].returncode == 1
        and runs[1].stderr.endswith(
            b"ERROR: rename under plans/ or memory/ (plans/\xff.md) " + "— commit it by hand\n".encode()
        ),
    )


def commit_timeout_case(case: Case, tmp: pathlib.Path) -> None:
    """A `git commit` that outlasts the timeout, in a copy of the script whose GIT_TIMEOUT is 1 s:
    git ends on the SIGTERM that the run sends and removes its own index.lock, and the run exits 1
    with one ERROR line that names the command, and leaves no lock."""
    f = Fixture(tmp / "timeout-commit")
    f.write(f"{MEMORY}/one.md", "one fact\n")
    hook = f.repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    hook.chmod(0o755)
    text = SCRIPT.read_text(encoding="utf-8")
    script = f.home / "claude-autocommit"
    script.write_text(text.replace("\nGIT_TIMEOUT = 600\n", "\nGIT_TIMEOUT = 1\n"), encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(script), "--no-push"],
        env={**f.env, "CLAUDE_AUTOCOMMIT_REPO": str(f.repo)},
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT,
    )
    case(
        "a `git commit` that outlasts the timeout ends on a SIGTERM: exit 1 with one ERROR line, and "
        "no index.lock and no lock is left",
        ok="\nGIT_TIMEOUT = 600\n" in text
        and p.returncode == 1
        and p.stderr.endswith(f"ERROR: git did not finish within 1 s: git commit -F - -- {MEMORY}/one.md\n")
        and not (f.repo / ".git" / "index.lock").exists()
        and not (lock_dir(f.home, None) / "lock").exists()
        and f.git("rev-list", "--count", "HEAD") == "1",
    )


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  autocommit: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-autocommit-") as tmp:
        root = pathlib.Path(tmp).resolve()
        julia_cases(case, root)
        more_cases(case, root)
        repository_cases(case, root)
        edge_cases(case, root)
        lock_cases(case, root)
        commit_sigterm_case(case, root)
        commit_timeout_case(case, root)
        undecodable_case(case, root)
    return total, wrong
