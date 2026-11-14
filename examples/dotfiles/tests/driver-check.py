#!/usr/bin/env python3
"""Check the driver dot_local/bin/executable_dotfiles. Run it with Python 3.11 or later, from any
directory:

    python3 tests/driver-check.py

Each case copies the driver into a scratch bin directory under $TMPDIR beside stubs of
dotfiles-update, dotfiles-check, dotfiles-merge and dotfiles-absorb, which print their name and
arguments, and puts stubs of gh, glab and git first on the PATH. The stubs of gh and glab log their
arguments and answer with the state and source branch in $GH_ANSWER or $GLAB_ANSWER, and exit 1
when the answer is empty, as gh and glab do for a number they cannot read. Under GITLAB_TOKEN=KEY
the stub of glab answers $GLAB_TOKEN_ANSWER instead, and it logs its working directory, its
GITLAB_HOST and whether its GITLAB_TOKEN is KEY. The stub of git logs each `credential` call and
runs the real git. A scratch HOME holds a git repository at ~/.local/share/chezmoi whose origin
each case sets, with a repo-local credential helper for https://git.example.org that returns the
password in $HELPER_PASSWORD: an origin on github.com asks gh, any other host asks glab. The
driver runs in a directory outside the source, with no system or global git configuration.

The cases of the fallback to the source's git credential: glab's own login answers, so glab runs
once and no credential is read; the credential answers, so glab runs a second time with the
password as GITLAB_TOKEN, the host as GITLAB_HOST and the source as its directory, and the
password is in no output, no argument and no file; the second answer is not open; and no answer,
for each of three reasons (glab answers neither call, the helper returns no password, the origin
is an SSH address), stops with one line that names `dotfiles merge <branch>`. It also runs
`bash -n` and `shellcheck -S warning` on the driver. It exits 0 when every check passes.
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
    """A stub of gh: log the arguments, print the answer, exit 1 on an empty one."""
    return (
        f'#!/bin/bash\necho "{name} $*" >> "$HOME/{name}.log"\n'
        f'[ -n "${variable}" ] || exit 1\nprintf "%s\\n" "${variable}"\n'
    )


# A stub of glab: log the arguments to glab.log, and the working directory, GITLAB_HOST and whether
# GITLAB_TOKEN is unset or empty (none), $EXPECTED_TOKEN (match) or another value (other) to
# glab.env, so that no log holds the token. It answers $GLAB_TOKEN_ANSWER under the expected token
# and $GLAB_ANSWER otherwise, and exits 1 on an empty answer.
GLAB = """#!/bin/bash
echo "glab $*" >> "$HOME/glab.log"
if [ -z "${GITLAB_TOKEN-}" ]; then token=none
elif [ "$GITLAB_TOKEN" = "$EXPECTED_TOKEN" ]; then token=match
else token=other; fi
printf 'cwd=%s host=%s token=%s\\n' "$PWD" "${GITLAB_HOST-}" "$token" >> "$HOME/glab.env"
if [ "$token" = match ]; then answer=$GLAB_TOKEN_ANSWER; else answer=$GLAB_ANSWER; fi
[ -n "$answer" ] || exit 1
printf '%s\\n' "$answer"
"""

# A stub of git on the PATH: it logs the arguments of each `credential` call to git-credential.log
# and runs the real git.
GIT_STUB = """#!/bin/bash
case " $* " in *" credential "*) echo "git $*" >> "$HOME/git-credential.log" ;; esac
exec {git} "$@"
"""

# The source's repo-local credential helper for https://git.example.org: it writes a line to its
# stderr, logs its GCM_INTERACTIVE and GIT_TERMINAL_PROMPT to helper.env, and answers `get` with
# the password in $HELPER_PASSWORD, or with nothing when it is empty.
HELPER = """#!/bin/bash
echo "helper: asked for $1" >&2
echo "GCM_INTERACTIVE=${GCM_INTERACTIVE-} GIT_TERMINAL_PROMPT=${GIT_TERMINAL_PROMPT-}" >> "$HOME/helper.env"
[ "$1" = get ] || exit 0
cat > /dev/null
[ -z "$HELPER_PASSWORD" ] || printf 'username=me\\npassword=%s\\n' "$HELPER_PASSWORD"
"""

# The password that the helper returns and the stub of glab expects in GITLAB_TOKEN.
KEY = "test-token"


class Scratch:
    """A scratch bin directory with the driver and stubs of the three scripts it runs, stubs of gh,
    glab and git, a directory outside the source in which the driver starts, and a HOME whose
    chezmoi source is a git repository with the origin OTHER and a repo-local credential helper."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.bin_dir, self.stubs, self.home = tmp / "bin", tmp / "stubs", tmp / "home"
        self.elsewhere = tmp / "elsewhere"
        for d in (self.bin_dir, self.stubs, self.elsewhere):
            d.mkdir()
        shutil.copy(DRIVER, self.bin_dir / "dotfiles")
        (self.bin_dir / "dotfiles").chmod(0o755)
        for name in ("dotfiles-update", "dotfiles-check", "dotfiles-merge", "dotfiles-absorb"):
            executable(self.bin_dir / name, f'#!/bin/bash\necho "{name} $*"\n')
        executable(self.stubs / "glab", GLAB)
        executable(self.stubs / "gh", answering("gh", "GH_ANSWER"))
        executable(self.stubs / "git", GIT_STUB.format(git=GIT))
        executable(tmp / "helper", HELPER)
        self.source = self.home / ".local" / "share" / "chezmoi"
        self.source.mkdir(parents=True)
        subprocess.run([GIT, "init", "-q", str(self.source)], check=True, timeout=60)
        for args in (
            ["remote", "add", "origin", OTHER],
            ["config", "credential.https://git.example.org.helper", str(tmp / "helper")],
        ):
            subprocess.run([GIT, "-C", str(self.source), *args], check=True, timeout=60)

    def origin(self, url):
        subprocess.run(
            [GIT, "-C", str(self.source), "remote", "set-url", "origin", url], check=True, timeout=60
        )

    def log(self, name):
        """The text of ~/<name>, which is then removed; <name> is glab.log, gh.log, glab.env or
        git-credential.log, or a bare name, read as <name>.log."""
        path = self.home / (name if "." in name else f"{name}.log")
        text = path.read_text() if path.exists() else ""
        path.unlink(missing_ok=True)
        return text

    def holds_key(self):
        """The paths below the scratch directory whose bytes hold KEY."""
        return [p for p in self.tmp.rglob("*") if p.is_file() and KEY.encode() in p.read_bytes()]

    def run(self, *args, glab="", gh="", keyed="", helper=""):
        """The driver run in a directory outside the source, with the stubs first on the PATH, no
        system or global git configuration, and no GITLAB_TOKEN or GITLAB_HOST of the caller.
        `glab` is glab's answer under its own login, `keyed` its answer under GITLAB_TOKEN=KEY, and
        `helper` the password that the source's credential helper returns."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "GITLAB_TOKEN",
                "GITLAB_HOST",
                "GIT_ASKPASS",
                "SSH_ASKPASS",
                "GCM_INTERACTIVE",
                "GIT_TERMINAL_PROMPT",
            }
            and not k.startswith("GIT_CONFIG")
        }
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            GIT_CONFIG_NOSYSTEM="1",
            PATH=f"{self.stubs}:{os.environ['PATH']}",
            GLAB_ANSWER=glab,
            GLAB_TOKEN_ANSWER=keyed,
            EXPECTED_TOKEN=KEY,
            HELPER_PASSWORD=helper,
            GH_ANSWER=gh,
        )
        return subprocess.run(
            [str(self.bin_dir / "dotfiles"), *args],
            cwd=self.elsewhere,
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
    p = s.run("absorb")
    check(p.returncode == 0 and p.stdout == "dotfiles-absorb \n", "absorb runs dotfiles-absorb")
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


def fallback_cases(s):
    """merge with a number on another host when glab's own login cannot read the merge request:
    glab answers first, the source's git credential answers, the second answer is not open, and
    no answer, from glab, from the helper or for an SSH origin."""
    s.origin(OTHER)
    view = "mr view 31 -R https://git.example.org/me/dotfiles.git -F json --jq"
    p = s.run("merge", "31", glab="opened feature-x", keyed="opened feature-q", helper=KEY)
    glab, credential = s.log("glab"), s.log("git-credential.log")
    check(
        p.returncode == 0
        and p.stdout.endswith("dotfiles-merge feature-x\n")
        and glab.count("glab ") == 1
        and credential == "",
        "glab's own login answers: glab runs once and no git credential is read",
    )
    s.log("glab.env")

    p = s.run("merge", "31", keyed="opened feature-x", helper=KEY)
    glab, env, credential = s.log("glab"), s.log("glab.env").splitlines(), s.log("git-credential.log")
    second = dict(f.split("=", 1) for f in env[1].split()) if len(env) == 2 else {}
    check(
        p.returncode == 0
        and p.stdout.endswith("dotfiles-merge feature-x\n")
        and glab.splitlines() == [f'glab {view} .state + " " + .source_branch'] * 2
        and env[0].endswith("token=none")
        and "credential fill" in credential,
        f"the source's git credential answers: glab runs twice with the same arguments: {glab!r}",
    )
    helper_env = s.log("helper.env")
    check(
        helper_env == "GCM_INTERACTIVE=never GIT_TERMINAL_PROMPT=0\n",
        f"the credential is read with GCM_INTERACTIVE=never and GIT_TERMINAL_PROMPT=0: {helper_env!r}",
    )
    check(
        second.get("token") == "match"
        and second.get("host") == "git.example.org"
        and pathlib.Path(second.get("cwd", "/nonexistent")).resolve() == s.source.resolve(),
        f"the second glab call has GITLAB_TOKEN, GITLAB_HOST and the source as its directory: {env}",
    )
    check(
        KEY not in p.stdout + p.stderr + glab + credential and not s.holds_key(),
        f"the password is in no output, no argument of glab or git and no file: {s.holds_key()}",
    )

    hint = "dotfiles merge <branch>"
    p = s.run("merge", "32", keyed="merged feature-y", helper=KEY)
    check(
        p.returncode == 1
        and "dotfiles-merge" not in p.stdout
        and "is merged, not open" in p.stderr
        and hint not in p.stderr,
        f"a merge request that the second glab call finds not open stops before dotfiles-merge: {p.stderr!r}",
    )
    for log in ("glab", "glab.env", "git-credential.log", "helper.env"):
        s.log(log)

    for label, origin, helper, calls, read in (
        ("glab answers neither call", OTHER, KEY, 2, True),
        ("the helper returns no password", OTHER, "", 1, True),
        ("an SSH origin", "git@git.example.org:me/dotfiles.git", KEY, 1, False),
        ("an http:// origin", "http://git.example.org/me/dotfiles.git", KEY, 1, False),
    ):
        s.origin(origin)
        keyed = "" if label.startswith("glab") else "opened feature-x"
        p = s.run("merge", "33", keyed=keyed, helper=helper)
        glab, credential = s.log("glab"), s.log("git-credential.log")
        s.log("glab.env")
        s.log("helper.env")
        check(
            p.returncode == 1
            and "dotfiles-merge" not in p.stdout
            and len(p.stderr.splitlines()) == 1
            and "not found" in p.stderr
            and hint in p.stderr
            and glab.count("glab ") == calls
            and ("credential fill" in credential) == read,
            f"{label}: one stderr line with 'not found' and '{hint}', glab ran {calls} time(s), "
            f"a credential {'read' if read else 'not read'}: {p.stderr!r} {glab!r} {credential!r}",
        )
    s.origin(OTHER)


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
            p.returncode == 1
            and "dotfiles-merge" not in p.stdout
            and "not found" in p.stderr
            and ("dotfiles merge <branch>" in p.stderr) == (label == "glab"),
            f"a number that {label} cannot read stops with 'not found' before dotfiles-merge, and the "
            f"line names dotfiles merge <branch> for glab only: {p.stderr!r}",
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
    for args in ([], ["merge"], ["merge", ""], ["merge", "a", "b"], ["absorb", "x"], ["apply"]):
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
        fallback_cases(s)
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
