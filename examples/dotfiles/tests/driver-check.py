#!/usr/bin/env python3
"""Check the driver dot_local/bin/executable_dotfiles. Run it with Python 3.11 or later, from any
directory:

    python3 tests/driver-check.py

Each case copies the driver into a scratch bin directory under $TMPDIR beside stubs of
dotfiles-update, dotfiles-check and dotfiles-merge, which print their name and arguments, and puts
stubs of gh and glab first on the PATH. Each stub logs its arguments and answers with the state
and source branch in $GH_ANSWER or $GLAB_ANSWER, and exits 1 when its answer is empty, as gh and
glab do for a number they cannot read. A scratch HOME holds a git repository at
~/.local/share/chezmoi whose origin each case sets: an origin on github.com asks gh, any other
host asks glab. It also runs `bash -n` and `shellcheck -S warning` on the driver. It exits 0 when
every check passes.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent.parent
DRIVER = SOURCE / "dot_local" / "bin" / "executable_dotfiles"
OTHER = "https://git.example.org/me/dotfiles.git"
GIT = shutil.which("git") or "git"
BASH = shutil.which("bash") or "bash"

failures = []


def check(ok, label):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        failures.append(label)


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


def answering(name, variable):
    """A stub of gh or glab: log the arguments, print the answer, exit 1 on an empty one."""
    return (
        f'#!/bin/bash\necho "{name} $*" >> "$HOME/{name}.log"\n'
        f'[ -n "${variable}" ] || exit 1\nprintf "%s\\n" "${variable}"\n'
    )


class Scratch:
    """A scratch bin directory with the driver and stubs of the three scripts it runs, stubs of gh
    and glab, and a HOME whose chezmoi source is a git repository with the origin OTHER."""

    def __init__(self, tmp):
        self.bin_dir, self.stubs, self.home = tmp / "bin", tmp / "stubs", tmp / "home"
        for d in (self.bin_dir, self.stubs):
            d.mkdir()
        shutil.copy(DRIVER, self.bin_dir / "dotfiles")
        (self.bin_dir / "dotfiles").chmod(0o755)
        for name in ("dotfiles-update", "dotfiles-check", "dotfiles-merge"):
            executable(self.bin_dir / name, f'#!/bin/bash\necho "{name} $*"\n')
        executable(self.stubs / "glab", answering("glab", "GLAB_ANSWER"))
        executable(self.stubs / "gh", answering("gh", "GH_ANSWER"))
        self.source = self.home / ".local" / "share" / "chezmoi"
        self.source.mkdir(parents=True)
        subprocess.run([GIT, "init", "-q", str(self.source)], check=True, timeout=60)
        subprocess.run(
            ["git", "-C", str(self.source), "remote", "add", "origin", OTHER],  # noqa: S607 -- git runs from PATH
            check=True,
            timeout=60,
        )

    def origin(self, url):
        subprocess.run(
            ["git", "-C", str(self.source), "remote", "set-url", "origin", url],  # noqa: S607 -- git runs from PATH
            check=True,
            timeout=60,
        )

    def log(self, name):
        path = self.home / f"{name}.log"
        text = path.read_text() if path.exists() else ""
        path.unlink(missing_ok=True)
        return text

    def run(self, *args, glab="", gh=""):
        env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=f"{self.stubs}:{os.environ['PATH']}",
            GLAB_ANSWER=glab,
            GH_ANSWER=gh,
        )
        return subprocess.run(
            [str(self.bin_dir / "dotfiles"), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )


def subcommand_cases(s):
    """update, check and merge with a branch name, and merge with a number on another host."""
    p = s.run("update")
    check(p.returncode == 0 and p.stdout == "dotfiles-update \n", "update runs dotfiles-update")
    p = s.run("check", "--full")
    check(p.stdout == "dotfiles-check --full\n", "check passes its arguments to dotfiles-check")
    p = s.run("merge", "topic-branch")
    check(
        p.stdout == "dotfiles-merge topic-branch\n" and s.log("glab") == "" and s.log("gh") == "",
        "a branch name goes to dotfiles-merge and asks neither glab nor gh",
    )

    p = s.run("merge", "12", glab="opened feature-x")
    glab, gh = s.log("glab"), s.log("gh")
    check(
        p.returncode == 0
        and p.stdout.endswith("dotfiles-merge feature-x\n")
        and "mr view 12 -R https://git.example.org/me/dotfiles.git" in glab
        and gh == "",
        "a number on another host is a merge request that glab names, merged by its source branch",
    )
    p = s.run("merge", "13", glab="merged feature-y")
    check(
        p.returncode == 1 and "dotfiles-merge" not in p.stdout and "not open" in p.stderr,
        "a merge request that is not open stops before dotfiles-merge",
    )
    s.log("glab")


def github_cases(s):
    """merge with a number on github.com, under each form of its origin, and one gh cannot read."""
    # As `harness repos status` reads an origin: the host in any case and without its port,
    # the path without the slashes around it and without .git.
    for url in (
        "https://github.com/owner/dotfiles.git",
        "git@github.com:owner/dotfiles.git",
        "ssh://git@github.com/owner/dotfiles",
        "ssh://git@github.com:22/owner/dotfiles.git",
        "https://github.com:443/owner/dotfiles.git",
        "https://GitHub.com/owner/dotfiles.git",
        "git@GitHub.com:owner/dotfiles.git",
        "https://github.com/owner/dotfiles/",
        "https://github.com/owner/dotfiles.git/",
        "git@github.com:/owner/dotfiles.git",
    ):
        s.origin(url)
        p = s.run("merge", "21", gh="OPEN feature-z")
        glab, gh = s.log("glab"), s.log("gh")
        check(
            p.returncode == 0
            and p.stdout.endswith("dotfiles-merge feature-z\n")
            and "pr view 21 -R github.com/owner/dotfiles " in gh
            and glab == "",
            f"a number on github.com ({url}) is a pull request that gh names, and glab is not asked",
        )
    p = s.run("merge", "22", gh="MERGED feature-w")
    check(
        p.returncode == 1 and "dotfiles-merge" not in p.stdout and "not open" in p.stderr,
        "a pull request that is not open stops before dotfiles-merge",
    )
    s.log("gh")

    for url, label in ((OTHER, "glab"), ("https://github.com/owner/dotfiles.git", "gh")):
        s.origin(url)
        p = s.run("merge", "14")
        check(
            p.returncode == 1 and "dotfiles-merge" not in p.stdout and "not found" in p.stderr,
            f"a number that {label} cannot read stops with 'not found' before dotfiles-merge",
        )
    s.log("glab")
    s.log("gh")


def usage_cases(s):
    """--help, the usage errors, and a host without dotfiles-merge."""
    p = s.run("--help")
    lines = p.stdout.splitlines()
    check(
        p.returncode == 0
        and lines[0].startswith("dotfiles <subcommand>")
        and lines[-1] == "Any other argument is a branch name.",
        "--help prints the whole comment at the head of the driver, and nothing more",
    )
    for args in ([], ["merge"], ["merge", ""], ["merge", "a", "b"], ["apply"]):
        p = s.run(*args)
        check(
            p.returncode == 2 and p.stderr.startswith("usage:"),
            f"{args or 'no argument'} is a usage error",
        )
    (s.bin_dir / "dotfiles-merge").unlink()
    p = s.run("merge", "topic-branch")
    check(p.returncode == 1 and "only the template host" in p.stderr, "a host without dotfiles-merge stops")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        s = Scratch(pathlib.Path(tmp))
        subcommand_cases(s)
        github_cases(s)
        usage_cases(s)

    p = subprocess.run([BASH, "-n", str(DRIVER)], check=False, timeout=60)
    check(p.returncode == 0, "bash -n")
    if shutil.which("shellcheck"):
        p = subprocess.run(
            ["shellcheck", "-S", "warning", "-s", "bash", str(DRIVER)],  # noqa: S607 -- shellcheck runs from PATH
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        check(p.returncode == 0, "shellcheck -S warning" + (f": {p.stdout.strip()}" if p.returncode else ""))
    else:
        check(ok=False, label="shellcheck is on the PATH")
    print(f"driver-check: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
