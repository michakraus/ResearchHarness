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


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        bin_dir, stubs, home = tmp / "bin", tmp / "stubs", tmp / "home"
        for d in (bin_dir, stubs):
            d.mkdir()
        shutil.copy(DRIVER, bin_dir / "dotfiles")
        (bin_dir / "dotfiles").chmod(0o755)
        for name in ("dotfiles-update", "dotfiles-check", "dotfiles-merge"):
            executable(bin_dir / name, f'#!/bin/bash\necho "{name} $*"\n')
        executable(stubs / "glab", answering("glab", "GLAB_ANSWER"))
        executable(stubs / "gh", answering("gh", "GH_ANSWER"))
        source = home / ".local" / "share" / "chezmoi"
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "remote", "add", "origin", OTHER], check=True)

        def origin(url):
            subprocess.run(["git", "-C", str(source), "remote", "set-url", "origin", url], check=True)

        def log(name):
            path = home / f"{name}.log"
            text = path.read_text() if path.exists() else ""
            path.unlink(missing_ok=True)
            return text

        def run(*args, glab="", gh=""):
            env = dict(
                os.environ,
                HOME=str(home),
                PATH=f"{stubs}:{os.environ['PATH']}",
                GLAB_ANSWER=glab,
                GH_ANSWER=gh,
            )
            return subprocess.run([str(bin_dir / "dotfiles"), *args], env=env, capture_output=True, text=True)

        p = run("update")
        check(p.returncode == 0 and p.stdout == "dotfiles-update \n", "update runs dotfiles-update")
        p = run("check", "--full")
        check(p.stdout == "dotfiles-check --full\n", "check passes its arguments to dotfiles-check")
        p = run("merge", "topic-branch")
        check(
            p.stdout == "dotfiles-merge topic-branch\n" and log("glab") == "" and log("gh") == "",
            "a branch name goes to dotfiles-merge and asks neither glab nor gh",
        )

        p = run("merge", "12", glab="opened feature-x")
        glab, gh = log("glab"), log("gh")
        check(
            p.returncode == 0
            and p.stdout.endswith("dotfiles-merge feature-x\n")
            and "mr view 12 -R https://git.example.org/me/dotfiles.git" in glab
            and gh == "",
            "a number on another host is a merge request that glab names, merged by its source branch",
        )
        p = run("merge", "13", glab="merged feature-y")
        check(
            p.returncode == 1 and "dotfiles-merge" not in p.stdout and "not open" in p.stderr,
            "a merge request that is not open stops before dotfiles-merge",
        )
        log("glab")

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
            origin(url)
            p = run("merge", "21", gh="OPEN feature-z")
            glab, gh = log("glab"), log("gh")
            check(
                p.returncode == 0
                and p.stdout.endswith("dotfiles-merge feature-z\n")
                and "pr view 21 -R github.com/owner/dotfiles " in gh
                and glab == "",
                f"a number on github.com ({url}) is a pull request that gh names, and glab is not asked",
            )
        p = run("merge", "22", gh="MERGED feature-w")
        check(
            p.returncode == 1 and "dotfiles-merge" not in p.stdout and "not open" in p.stderr,
            "a pull request that is not open stops before dotfiles-merge",
        )
        log("gh")

        for url, label in ((OTHER, "glab"), ("https://github.com/owner/dotfiles.git", "gh")):
            origin(url)
            p = run("merge", "14")
            check(
                p.returncode == 1 and "dotfiles-merge" not in p.stdout and "not found" in p.stderr,
                f"a number that {label} cannot read stops with 'not found' before dotfiles-merge",
            )
        log("glab")
        log("gh")

        p = run("--help")
        lines = p.stdout.splitlines()
        check(
            p.returncode == 0
            and lines[0].startswith("dotfiles <subcommand>")
            and lines[-1] == "Any other argument is a branch name.",
            "--help prints the whole comment at the head of the driver, and nothing more",
        )
        for args in ([], ["merge"], ["merge", ""], ["merge", "a", "b"], ["apply"]):
            p = run(*args)
            check(
                p.returncode == 2 and p.stderr.startswith("usage:"),
                f"{args or 'no argument'} is a usage error",
            )
        (bin_dir / "dotfiles-merge").unlink()
        p = run("merge", "topic-branch")
        check(
            p.returncode == 1 and "only the template host" in p.stderr, "a host without dotfiles-merge stops"
        )

    check(subprocess.run(["bash", "-n", str(DRIVER)]).returncode == 0, "bash -n")
    if shutil.which("shellcheck"):
        p = subprocess.run(
            ["shellcheck", "-S", "warning", "-s", "bash", str(DRIVER)], capture_output=True, text=True
        )
        check(p.returncode == 0, "shellcheck -S warning" + (f": {p.stdout.strip()}" if p.returncode else ""))
    else:
        check(False, "shellcheck is on the PATH")
    print(f"driver-check: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
