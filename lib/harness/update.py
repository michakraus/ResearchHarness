"""Bring the harness checkout up to origin/main, and install it.

    harness update [--apply]

It works on the checkout that runs it, and only when its branch is `main` with the upstream
`origin/main`: a development checkout. A checkout at a detached HEAD is pinned to a commit, as on
a machine whose dotfiles name the commit to install; only a reviewed change of the pin moves it,
so the subcommand stops there and moves nothing.

The dry run fetches, prints the new commits and the files they change, and exits 1 when there is
a new commit. `--apply` also shows the whole diff, through git's pager in a terminal, and asks
y/N; on `y` it merges `--ff-only` and runs `harness install --apply`. It needs a terminal for the
question, and it stops when a tracked file has changes or the branch has commits that
`origin/main` lacks.
"""

import argparse
import contextlib
import io
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Protocol
from unittest import mock

from . import REPO, HarnessError, changing
from .githooks import git
from .sweep import GIT


class Subcommands(Protocol):
    """The `sub` that `register` receives: what `add_subparsers` returns."""

    def add_parser(self, name: str, *, help: str, description: str) -> argparse.ArgumentParser: ...


def plan(repo: pathlib.Path) -> int:
    """Fetch, then the number of commits of `origin/main` that `HEAD` lacks; a checkout that
    cannot be fast-forwarded is a `HarnessError`."""
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if not branch:
        head = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
        raise HarnessError(
            f"{repo} is pinned at {head} (detached HEAD); move the pin where it is set, "
            "such as in your dotfiles, not here"
        )
    if branch != "main":
        raise HarnessError(f"{repo} is on {branch}, not main; switch to main first")
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
    if upstream != "origin/main":
        raise HarnessError(f"main of {repo} tracks {upstream or 'nothing'}, not origin/main")
    p = git(repo, "fetch", "--quiet", "origin", timeout=300)
    if p.returncode:
        raise HarnessError(f"git fetch failed: {(p.stderr.strip().splitlines() or [''])[-1]}")
    counts = git(repo, "rev-list", "--left-right", "--count", "HEAD...origin/main").stdout.split()
    ahead, behind = int(counts[0]), int(counts[1])
    if ahead:
        raise HarnessError(f"main has {ahead} commit(s) that origin/main lacks; push or rebase them first")
    return behind


def confirm(question: str) -> bool:
    """True only for the answer y or Y; an empty line and the end of input mean no."""
    try:
        return input(f"{question} [y/N] ").strip() in ("y", "Y")
    except EOFError:
        return False


def show_diff(repo: pathlib.Path) -> None:
    """The whole diff, through git's pager when the output is a terminal. Its exit status is not
    read: the diff only informs the question that follows, which still decides."""
    git_program = shutil.which("git") or "git"
    subprocess.run(  # no timeout: git's pager waits for the user to read the diff
        [git_program, "-C", str(repo), "diff", "HEAD", "origin/main"], check=False
    )


def install(args: argparse.Namespace) -> int:
    """`harness install --apply` from the merged checkout, in a process of its own."""
    options = [
        o
        for flag, value in (("--profile", args.profile), ("--models", args.models))
        if value
        for o in (flag, value)
    ]
    return subprocess.run(  # no timeout: the install instantiates the Julia environment, a long run
        [sys.executable, str(REPO / "bin" / "harness"), *options, "install", "--apply"], check=False
    ).returncode


def update(args: argparse.Namespace, repo: pathlib.Path) -> int:
    if args.apply and not sys.stdin.isatty():
        raise HarnessError("--apply asks on the terminal; run it yourself, in a terminal")
    behind = plan(repo)
    if behind == 0:
        print(
            f"up to date: main is origin/main at {git(repo, 'rev-parse', '--short', 'HEAD').stdout.strip()}"
        )
        return 0
    print(git(repo, "log", "--oneline", "HEAD..origin/main").stdout.rstrip())
    print(git(repo, "diff", "--stat", "HEAD", "origin/main").stdout.rstrip())
    if not args.apply:
        print(f"\n{behind} new commit(s). harness update --apply shows the diff and asks before the merge.")
        return 1
    if git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise HarnessError(f"{repo} has changes to tracked files; commit or set them aside first")
    show_diff(repo)
    if not confirm(
        f"harness update: merge {behind} commit(s) of origin/main and run harness install --apply?"
    ):
        print("harness update: nothing merged, nothing installed.")
        return 0
    p = git(repo, "merge", "--ff-only", "--quiet", "origin/main")
    if p.returncode:
        raise HarnessError(f"git merge --ff-only failed: {(p.stderr.strip().splitlines() or [''])[-1]}")
    if install(args):
        raise HarnessError("harness install --apply failed; main is merged")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    return update(args, REPO)


def register(sub: Subcommands) -> None:
    changing(
        sub.add_parser(
            "update",
            help="bring the harness checkout up to origin/main and install it",
            description="Fetch the harness checkout and show the commits of origin/main that it "
            "lacks; exit 1 when there is one. --apply shows the diff, asks y/N in a "
            "terminal, merges --ff-only and runs harness install --apply. A pinned "
            "checkout, at a detached HEAD, is not moved.",
        ),
        help="show the diff, ask, merge and install",
    ).set_defaults(run=cmd_update)


def selftest():
    """`plan` and `update` on a scratch remote and its clone: a pinned and a diverged checkout
    stop, the dry run lists a new commit, and `--apply` merges and installs only after `y`."""
    results: list[object] = []

    def check(ok: object, label: str) -> None:
        results.append(ok)
        print(f"{'ok ' if ok else 'BAD'}  update: {label}")

    def run(*command: str, cwd: pathlib.Path) -> None:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, timeout=60)

    def attempt(
        repo: pathlib.Path, *, apply: bool = False, answer: str = "n", tty: bool = True
    ) -> tuple[int | str, bool]:
        """(exit status or the error text, whether install ran)."""
        installed: list[argparse.Namespace] = []

        def ask(_question: str) -> str:
            return answer

        def install_stub(a: argparse.Namespace) -> int:
            installed.append(a)
            return 0

        def show_diff_stub(_repo: pathlib.Path) -> None:
            return None

        with (
            mock.patch.object(sys.stdin, "isatty", lambda: tty),
            mock.patch("builtins.input", ask),
            mock.patch(f"{__name__}.install", install_stub),
            mock.patch(f"{__name__}.show_diff", show_diff_stub),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code: int | str
            try:
                code = update(argparse.Namespace(apply=apply, profile=None, models=None), repo)
            except HarnessError as e:
                code = str(e)
        return code, bool(installed)

    with tempfile.TemporaryDirectory() as name, mock.patch.dict("os.environ", GIT):
        tmp = pathlib.Path(name)
        run("git", "init", "-q", "--bare", "-b", "main", "origin.git", cwd=tmp)
        run("git", "clone", "-q", "origin.git", "author", cwd=tmp)
        author, local = tmp / "author", tmp / "local"

        def commit(repo: pathlib.Path, text: str) -> None:
            (repo / "file").write_text(text)
            run("git", "add", "file", cwd=repo)
            run("git", "commit", "-q", "-m", text, cwd=repo)
            run("git", "push", "-q", "origin", "HEAD:main", cwd=repo)

        commit(author, "one")
        run("git", "clone", "-q", "origin.git", "local", cwd=tmp)
        check(attempt(local)[0] == 0, "an up-to-date checkout exits 0")
        commit(author, "two")
        check(attempt(local)[0] == 1, "the dry run exits 1 for a new commit")
        check("terminal" in str(attempt(local, apply=True, tty=False)[0]), "--apply without a terminal stops")
        head = git(local, "rev-parse", "HEAD").stdout
        code, installed = attempt(local, apply=True, answer="")
        check(
            code == 0 and not installed and git(local, "rev-parse", "HEAD").stdout == head,
            "the answer no merges and installs nothing",
        )
        code, installed = attempt(local, apply=True, answer="y")
        check(
            code == 0
            and installed
            and git(local, "rev-list", "--count", "HEAD..origin/main").stdout.strip() == "0",
            "the answer y merges and installs",
        )
        run("git", "checkout", "-q", "--detach", "HEAD", cwd=local)
        check("pinned" in str(attempt(local)[0]), "a pinned checkout stops")
        run("git", "switch", "-q", "main", cwd=local)
        commit(author, "three")
        (local / "other").write_text("x")
        run("git", "add", "other", cwd=local)
        run("git", "commit", "-q", "-m", "local", cwd=local)
        check("lacks" in str(attempt(local)[0]), "a checkout ahead of origin/main stops")
    return len(results), results.count(False)
