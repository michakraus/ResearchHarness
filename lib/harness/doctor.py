"""The read-only verb `harness doctor`: one line for each check of this machine's setup.

    harness doctor [--full]

The checks, in this order:

- the machine: the system and the architecture; on Linux the two kernel settings for user
  namespaces, a sandbox of `bwrap` and `socat`;
- the tools of docs/src/dependencies.md: each found on the PATH, and at or above its minimum where
  the page states one (MINIMUMS); the Julia packages of Project.toml in the Manifest.toml of the
  Julia environment of the scripts;
- the profile: it loads, the `tree_agents` directory and OpenCode's configuration directory exist,
  and its `autocommit_branch`;
- the install: the dry run of `harness install`, and each of its warnings;
- the jobs: Kaimon, its server and the update job; the autocommit job, and when it is enabled,
  `~/.claude` as the top of its own git repository with an `origin`; the Kaimon token file; on
  Linux also linger;
- with `--full`, `harness test` and `julia -e 'using Revise'`; without it, both are SKIP.

Each line is `PASS`, `WARN`, `FAIL` or `SKIP`, the name of the check and a detail. A FAIL line
also names the section of the setup page that fixes it (FIX). The verb exits 1 when a check fails,
else 0; a WARN or a SKIP does not count.

It changes nothing: it reads files, and runs the version flags of the tools, the dry run of
`harness install` and the status commands of the jobs. It reads no secret: the Kaimon token only
for its existence, mode and size, and of `~/.claude`'s `origin` only whether it exists, since a
remote URL can hold a credential.

A session's sandbox, known by $SANDBOX_RUNTIME, can refuse `bwrap`, `systemctl`, `loginctl`,
`launchctl` and the version flag of a tool, and deny a file. There, such a check that does not get its answer is SKIP with the
reason; run the verb in a plain terminal for its real verdict.
"""

import contextlib
import io
import os
import pathlib
import platform
import plistlib
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import types
from collections import namedtuple
from unittest import mock

from . import REPO, HarnessError, install
from . import profile as profile_module

# The command of the harness itself, for the dry run of `install` and for `test`.
HARNESS = [sys.executable, str(REPO / "bin" / "harness")]
# The variable that the sandbox of a session sets.
SANDBOX = "SANDBOX_RUNTIME"
KERNEL = pathlib.Path("/proc/sys/kernel")
OS_RELEASE = pathlib.Path("/etc/os-release")
ITERM = pathlib.Path("/Applications/iTerm.app")
# The seconds that one command may take: a tool's version flag or a status command, the dry run
# of the install, `harness test`, and the load of Revise.
TIMEOUT, INSTALL_TIMEOUT, TEST_TIMEOUT, REVISE_TIMEOUT = 60, 300, 3600, 600

# The minimums of docs/src/dependencies.md, {tool: versions}. A version passes at or above the
# last one, or at or above an earlier one of the same major release: Node.js 20.16 in 20.x, else
# 22.3. A case compares them with the page.
MINIMUMS = {
    "Python": ("3.11",), "gitleaks": ("8.21",), "Node.js": ("20.16", "22.3"), "actionlint": ("1.7.12",),
    "Julia": ("1.13",), "ExplicitImports": ("1.15",), "JSON": ("1.10",), "JuliaFormatter": ("2.14",),
    "JuliaSyntax": ("1.0.2",), "TestEnv": ("1.103.7",), "YAML": ("0.4.17",), "fatou": ("0.22.0",),
}
# (name in dependencies.md, command, its version arguments, what stops without it); a tool with no
# such text is required: a FAIL when it is missing, a WARN for the others.
TOOLS = [
    ("Python", "python3", ["--version"], None),
    ("git", "git", ["--version"], None),
    ("gh", "gh", ["--version"], None),
    ("Node.js", "node", ["--version"], None),
    ("shellcheck", "shellcheck", ["--version"], None),
    ("actionlint", "actionlint", ["--version"], None),
    ("timeout", "timeout", ["--version"], None),
    ("rsync", "rsync", ["--version"], None),
    ("Julia", "julia", ["--version"], None),
    ("fatou", "fatou", ["--version"], None),
    ("gitleaks", "gitleaks", ["version"], "the pre-push hook of the harness refuses a push to main"),
    ("juliaup", "juliaup", ["--version"], "the update job cannot update the Julia releases"),
    ("Claude Code", "claude", ["--version"], "nothing reads the layer in ~/.claude/"),
    ("OpenCode", "opencode", ["--version"], "nothing reads the configuration in ~/.config/opencode/"),
    ("oh-my-pi", "omp", ["--version"], "nothing reads the configuration in ~/.omp/agent/"),
    ("RTK", "rtk", ["--version"], "the OpenCode plugin passes each command unchanged"),
    ("jq", "jq", ["--version"], "the status line of Claude Code shows no values"),
]
# The section that fixes a FAIL, {topic: (on Linux, on macOS)}.
FIX = {
    "machine": ("setup-linux.md, Check the machine", None),
    "sandbox": ("setup-linux.md, The sandbox of Claude Code", None),
    "tools": ("setup-linux.md, The dependencies", "setup-macos.md, The dependencies"),
    "profile": ("setup-linux.md, The profile and the model tables", "setup-macos.md, The profile and the model tables"),
    "tree": ("setup-linux.md, The tree instructions", "setup-macos.md, The tree instructions"),
    "install": ("setup-linux.md, `harness install --apply`", "setup-macos.md, `harness install --apply`"),
    "kaimon job": ("setup-linux.md, The jobs", "components/other.md, `kaimon.plist`"),
    "update job": ("setup-linux.md, The jobs", "components/other.md, `julia-update.plist`"),
    "autocommit": ("setup-linux.md, The jobs", "components/other.md, `claude-autocommit`"),
    "token": ("setup-linux.md, The Kaimon token", "setup-linux.md, The Kaimon token"),
    "test": ("setup-linux.md, The check that it worked", "setup-macos.md, The check that it worked"),
}
# The answers of `systemctl is-active`; any other output is no answer.
STATES = {"active", "inactive", "failed", "activating", "deactivating", "reloading", "refreshing", "maintenance"}
VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
SUMMARY = re.compile(r"(\d+) cases, (\d+) wrong")
WIDTH = 24

Result = namedtuple("Result", "status name detail")


def system():
    return platform.system()


def machine():
    return platform.machine()


def sandboxed():
    """Whether the verb runs in a session's sandbox."""
    return bool(os.environ.get(SANDBOX))


def environment():
    """The environment of each command: the caller's, without a `GIT_*` variable, which a git hook
    sets to the caller's repository."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run(command, timeout=None):
    """(exit status, stdout, stderr) of `command`, or None when its program is not found. A
    program that cannot be started gives 126 and the reason, and a run that outlives `timeout`,
    else TIMEOUT, gives "timeout"."""
    timeout = timeout or TIMEOUT
    try:
        p = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, env=environment())
    except FileNotFoundError:
        return None
    except OSError as e:
        return 126, "", f"cannot start {command[0]}: {e.strerror or e}"
    except subprocess.TimeoutExpired:
        return "timeout", "", f"no answer after {timeout} s"
    return p.returncode, p.stdout, p.stderr


def said(command, r):
    """What the run `r` of `command` gave, for a detail: its exit status and its first line."""
    if r is None:
        return f"{command} not found"
    return f"{command} exits {r[0]}: {first(r[1] + r[2])}" if first(r[1] + r[2]) else f"{command} exits {r[0]}, silent"


def first(text):
    """The first line of `text` that is not blank, at most 160 characters."""
    return next((line.strip() for line in text.splitlines() if line.strip()), "")[:160]


def last(text):
    """The last line of `text` that is not blank, at most 160 characters."""
    return next((line.strip() for line in reversed(text.splitlines()) if line.strip()), "")[:160]


def numbers(text):
    """The version `text` as three integers, a missing patch 0."""
    return tuple(int(n) for n in text.split(".")) + (0,) * (3 - text.count(".") - 1)


def meets(version, minimums):
    """Whether `version`, three integers, meets `minimums`: at or above the last, or at or above
    an earlier one of the same major release."""
    floors = [numbers(m) for m in minimums]
    return version >= floors[-1] or any(version[0] == f[0] and version >= f for f in floors[:-1])


class Doctor:
    """The checks of one run, each a method that returns its Results."""

    def __init__(self, args):
        self.args = args
        self.system = system()
        self.linux = self.system == "Linux"
        self.home = pathlib.Path.home()
        try:
            self.profile, self.profile_error = profile_module.load(args.profile), None
        except HarnessError as e:
            self.profile, self.profile_error = None, str(e)
        except OSError as e:
            self.profile, self.profile_error = None, f"cannot read the profile: {e.strerror or e}"

    def fix(self, topic):
        """The section of FIX for `topic`: the macOS one on macOS, else the Linux one."""
        linux, macos = FIX[topic]
        return macos if self.system == "Darwin" and macos else linux

    def fail(self, name, detail, topic):
        return Result("FAIL", name, f"{detail} (fix: {self.fix(topic)})")

    def refused(self, name, detail, topic):
        """A command or a file that gave no answer: SKIP in a session's sandbox, which can refuse
        it, else FAIL."""
        if sandboxed():
            return Result("SKIP", name, f"{detail}; the session's sandbox can refuse it: run in a plain terminal")
        return self.fail(name, detail, topic)

    # The machine.

    def machine(self):
        arch = machine()
        if self.linux:
            names = dict(re.findall(r'^([A-Z_]+)="?([^"\n]*)"?$', read(OS_RELEASE) or "", re.M))
            where = f"Linux {arch} ({names.get('PRETTY_NAME', 'no /etc/os-release')})"
            if arch in ("x86_64", "aarch64"):
                result = Result("PASS", "system", where)
            else:
                result = Result("WARN", "system", f"{where}: the setup page covers x86_64 and aarch64, and its "
                                                  "release files do not exist for this one")
            return [result] + self.namespaces() + self.sandbox()
        if self.system == "Darwin":
            return [Result("PASS", "system", f"macOS {platform.mac_ver()[0]} {arch}")]
        return [Result("WARN", "system", f"{self.system} {arch}: no setup page covers this system")]

    def namespaces(self):
        """The two kernel settings for user namespaces; a missing key sets no limit."""
        out = []
        clone = read(KERNEL / "unprivileged_userns_clone")
        if clone is not None and clone.strip() == "0":
            out.append(self.fail("userns clone", "0: the kernel refuses user namespaces to a user who is not root",
                                 "machine"))
        else:
            out.append(Result("PASS", "userns clone", clone.strip() if clone is not None else "absent: no limit"))
        armor = read(KERNEL / "apparmor_restrict_unprivileged_userns")
        if armor is not None and armor.strip() == "1":
            out.append(Result("WARN", "apparmor userns", "1: AppArmor refuses user namespaces to a program that it "
                                                         "does not allow; the sandbox check decides"))
        else:
            out.append(Result("PASS", "apparmor userns", armor.strip() if armor is not None else "absent: no limit"))
        return out

    def sandbox(self):
        """The sandbox check of setup-linux.md, and socat beside it."""
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            out = [self.fail("sandbox", "bwrap not found", "sandbox")]
        else:
            r = run([bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--unshare-user", "--unshare-pid", "true"])
            if r is not None and r[0] == 0:
                out = [Result("PASS", "sandbox", f"bwrap makes a sandbox ({bwrap})")]
            else:
                out = [self.refused("sandbox", said("bwrap", r), "sandbox")]
        socat = shutil.which("socat")
        return out + [Result("PASS", "socat", socat) if socat else self.fail("socat", "socat not found", "sandbox")]

    # The tools.

    def tools(self):
        out = [self.tool(*t) for t in TOOLS]
        if self.system == "Darwin":
            out.append(self.iterm())
        return out + self.packages()

    def tool(self, name, command, flags, without):
        """A tool of TOOLS: missing, or a version flag that exits non-zero, is a FAIL for a required
        tool (`without` None) and a WARN for an optional one; a non-zero exit is a SKIP in a
        session's sandbox, which can refuse the flag. A version below its minimum is a FAIL, and
        output with no version a WARN."""
        path = shutil.which(command)
        if path is None:
            if without is None:
                return self.fail(name, f"{command} not found", "tools")
            return Result("WARN", name, f"{command} not found: {without}")
        r = run([path, *flags])
        call = " ".join([command, *flags])
        if r is None or r[0] != 0:
            if without is None or sandboxed():
                return self.refused(name, said(call, r), "tools")
            return Result("WARN", name, f"{said(call, r)}: {without}")
        m = VERSION.search(r[1] + r[2])
        if m is None:
            return Result("WARN", name, f"cannot read a version from {call}: {first(r[1] + r[2])!r}")
        return self.minimum(name, m.group(0), f"{m.group(0)} ({path})", "tools")

    def minimum(self, name, version, detail, topic):
        floors = MINIMUMS.get(name)
        if floors and not meets(numbers_of(version), floors):
            return self.fail(name, f"{detail}, below {' or '.join(floors)}", topic)
        return Result("PASS", name, detail)

    def iterm(self):
        try:
            with open(ITERM / "Contents" / "Info.plist", "rb") as f:
                version = plistlib.load(f).get("CFBundleShortVersionString")
        except OSError:
            return Result("WARN", "iTerm2", f"{ITERM} not found: the hook cc-status does nothing")
        except (plistlib.InvalidFileException, ValueError, AttributeError) as e:
            return Result("WARN", "iTerm2", f"cannot read the version of {ITERM}: {e}")
        return Result("PASS", "iTerm2", f"{version} ({ITERM})")

    def packages(self):
        """The Julia packages of Project.toml, in the Manifest.toml of the scripts' environment."""
        names = sorted(tomllib.loads((REPO / "Project.toml").read_text())["deps"])
        manifest = install.JULIA_ENV / "Manifest.toml"
        try:
            deps = tomllib.loads(manifest.read_text()).get("deps")
        except FileNotFoundError:
            return [self.fail(n, f"no {manifest}: the environment is not instantiated", "install") for n in names]
        except PermissionError as e:
            return [self.refused(n, f"cannot read {manifest}: {e.strerror}", "install") for n in names]
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            return [Result("WARN", n, f"cannot read {manifest}: {e}") for n in names]
        if not isinstance(deps, dict):
            return [Result("WARN", n, f"cannot read {manifest}: it has no table `deps`") for n in names]
        out = []
        for name in names:
            entry = deps.get(name)
            readable = isinstance(entry, list) and entry and isinstance(entry[0], dict)
            version = entry[0].get("version") if readable else None
            if version is None:
                out.append(self.fail(name, f"not in {manifest}", "install"))
            elif not isinstance(version, str) or VERSION.fullmatch(version) is None:
                out.append(Result("WARN", name, f"cannot read the version {version!r} in {manifest}"))
            else:
                out.append(self.minimum(name, version, version, "install"))
        return out

    # The profile and the install.

    def profile_checks(self):
        where = profile_module.location(self.args.profile)
        if self.profile is None:
            skip = "the profile does not load"
            return [self.fail("profile", self.profile_error, "profile"),
                    Result("SKIP", "tree_agents", skip), self.opencode(), Result("SKIP", "autocommit_branch", skip)]
        tree = self.profile.get("tree_agents")
        if not isinstance(tree, str):
            agents = self.fail("tree_agents", "the profile has no tree_agents", "tree")
        elif os.path.isdir(tree):
            agents = Result("PASS", "tree_agents", tree)
        else:
            agents = self.fail("tree_agents", f"{tree} is not a directory", "tree")
        return [Result("PASS", "profile", f"{where} (home {self.profile['home']})"), agents, self.opencode(),
                Result("PASS", "autocommit_branch", str(self.profile["autocommit_branch"]))]

    def opencode(self):
        directory = os.environ.get("OPENCODE_CONFIG_DIR") or str(self.home / ".config" / "opencode")
        if os.path.isdir(directory):
            return Result("PASS", "OpenCode directory", directory)
        return self.fail("OpenCode directory", f"{directory} is not a directory", "install")

    def install(self):
        """The dry run of `harness install`: its count, and a WARN for each warning."""
        if self.profile is None:
            return [Result("SKIP", "install", "the profile does not load")]
        options = [o for flag, value in (("--profile", self.args.profile), ("--models", self.args.models)) if value
                   for o in (flag, value)]
        r = run(HARNESS + options + ["install"], INSTALL_TIMEOUT)
        code, out, err = r
        count = re.search(r"^(\d+) change\(s\) to make\.$", out, re.M)
        if code == 0 and count and count.group(1) == "0":
            result = Result("PASS", "install", "0 change(s) to make")
        elif code == 1 and count:
            result = self.fail("install", f"{count.group(1)} change(s) to make", "install")
        else:
            result = self.fail("install", f"the dry run exits {code}: {last(err) or last(out)}", "install")
        warnings = re.findall(r"^WARNING: (.*)$", out, re.M)
        return [result] + [Result("WARN", f"install warning {n}", w.strip()) for n, w in enumerate(warnings, 1)]

    # The jobs.

    def jobs(self):
        kaimon = self.home / ".julia" / "bin" / "kaimon"
        installed = os.path.isfile(kaimon) and os.access(kaimon, os.X_OK)
        out = [Result("PASS", "Kaimon", str(kaimon)) if installed else
               Result("WARN", "Kaimon", f"{kaimon} is not an executable file: the agents have no Julia session, and "
                                        "the update job stops")]
        if self.linux:
            out.append(self.linger())
            ask = self.systemd()
        elif self.system != "Darwin":
            return out
        elif self.profile is None:
            skip = "the profile, which names launchd_prefix, does not load"
            return out + [Result("SKIP", name, skip) for name in ("kaimon job", "julia-update job", "autocommit job",
                                                                   "~/.claude repository")] + [self.token(installed)]
        else:
            ask = self.launchd(self.profile.get("launchd_prefix"))
        for name, job, topic in (("kaimon job", "kaimon", "kaimon job"), ("julia-update job", "julia-update",
                                                                            "update job")):
            if not installed:
                out.append(Result("SKIP", name, "Kaimon is not installed"))
                continue
            answer, detail = ask(job)
            out.append(Result("PASS", name, detail) if answer == "yes" else
                       self.refused(name, detail, topic) if answer == "none" else self.fail(name, detail, topic))
        answer, detail = ask("claude-autocommit")
        if answer == "yes":
            out += [Result("PASS", "autocommit job", detail), self.repository()]
        elif answer == "no":
            out += [Result("SKIP", "autocommit job", f"{detail}: the job is not enabled"),
                    Result("SKIP", "~/.claude repository", "the autocommit job is not enabled")]
        else:
            out += [self.refused("autocommit job", detail, "autocommit") if answer == "none" else
                    self.fail("autocommit job", detail, "autocommit"),
                    Result("SKIP", "~/.claude repository", "cannot tell whether the autocommit job is enabled")]
        return out + [self.token(installed)]

    # The `ask(job)` of a service manager gives (answer, detail) for the job `kaimon`,
    # `julia-update` or `claude-autocommit`: answer "yes" when the job runs or is loaded, "no" when
    # it does not, "missing" when the manager's command is not found, and "none" when the command
    # gives no answer.

    def systemd(self):
        """The `ask` of `systemd --user`: `is-active` of kaimon.service, and the list of the timers
        for the other two jobs, which it reads once."""
        systemctl = shutil.which("systemctl")
        timers = []

        def ask(job):
            if systemctl is None:
                return "missing", "systemctl not found"
            if job == "kaimon":
                r = run([systemctl, "--user", "is-active", "kaimon.service"])
                state = first(r[1]) if r else ""
                if state in STATES:
                    return ("yes" if state == "active" else "no"), f"kaimon.service {state}"
                return "none", said("systemctl", r)
            if not timers:
                timers.append(run([systemctl, "--user", "list-timers", "--no-pager"]))
            r = timers[0]
            if r is None or r[0] != 0:
                return "none", said("systemctl", r)
            listed = {word for line in r[1].splitlines() for word in line.split()}
            unit = f"{job}.timer"
            return ("yes", f"{unit} listed") if unit in listed else ("no", f"{unit} is not listed")
        return ask

    def launchd(self, prefix):
        """The `ask` of launchd: `launchctl list` of the job's label."""
        launchctl = shutil.which("launchctl")

        def ask(job):
            label = f"{prefix}.{job}"
            if launchctl is None:
                return "missing", "launchctl not found"
            r = run([launchctl, "list", label])
            if r is not None and r[0] == 0:
                return "yes", f"{label} loaded"
            if r is not None and "Could not find service" in r[2]:
                return "no", f"{label} is not loaded"
            return "none", said("launchctl", r)
        return ask

    def linger(self):
        loginctl = shutil.which("loginctl")
        if loginctl is None:
            return self.fail("linger", "loginctl not found", "kaimon job")
        r = run([loginctl, "show-user", pwd.getpwuid(os.getuid()).pw_name, "-p", "Linger"])
        m = re.search(r"^Linger=(yes|no)$", r[1], re.M) if r else None
        if m is None:
            return self.refused("linger", said("loginctl", r), "kaimon job")
        if m.group(1) == "no":
            return self.fail("linger", "Linger=no: the jobs stop at your last logout", "kaimon job")
        return Result("PASS", "linger", "Linger=yes")

    def repository(self):
        """`~/.claude` as the top of its own git repository, with an `origin`; its URL is not
        printed."""
        claude = self.home / ".claude"
        git = shutil.which("git")
        if git is None:
            return self.fail("~/.claude repository", "git not found", "autocommit")
        r = run([git, "-C", str(claude), "rev-parse", "--show-toplevel"])
        top = r[1].strip() if r and r[0] == 0 else None
        if top is None:
            return self.fail("~/.claude repository", f"{claude} is not a git repository", "autocommit")
        if os.path.realpath(top) != os.path.realpath(claude):
            return self.fail("~/.claude repository", f"{claude} is inside the repository {top}, not the top of its own",
                             "autocommit")
        r = run([git, "-C", str(claude), "remote", "get-url", "origin"])
        if r is None or r[0] != 0:
            return self.fail("~/.claude repository", f"{claude} has no remote origin", "autocommit")
        return Result("PASS", "~/.claude repository", f"{claude}, with an origin")

    def token(self, kaimon):
        """The token file of the Kaimon entry of OpenCode and oh-my-pi: its existence, mode and size,
        never its content."""
        if not kaimon:
            return Result("SKIP", "Kaimon token", "Kaimon is not installed")
        if shutil.which("opencode") is None and shutil.which("omp") is None:
            return Result("SKIP", "Kaimon token", "neither OpenCode nor oh-my-pi is installed, and only they read it")
        path = self.home / ".config" / "kaimon" / "opencode-token"
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return self.fail("Kaimon token", f"{path} does not exist", "token")
        except PermissionError as e:
            return self.refused("Kaimon token", f"cannot read the mode of {path}: {e.strerror}", "token")
        mode = stat.S_IMODE(st.st_mode)
        if not stat.S_ISREG(st.st_mode):
            return self.fail("Kaimon token", f"{path} is not a file", "token")
        if mode != 0o600:
            return self.fail("Kaimon token", f"{path} has mode {mode:o}, not 600", "token")
        if st.st_size == 0:
            return self.fail("Kaimon token", f"{path} is empty", "token")
        return Result("PASS", "Kaimon token", f"{path}, mode 600, {st.st_size} bytes")

    # The slow checks.

    def full(self):
        if not self.args.full:
            return [Result("SKIP", "harness test", "run with --full"), Result("SKIP", "Revise", "run with --full")]
        code, out, err = run(HARNESS + ["test"], TEST_TIMEOUT)
        m = SUMMARY.fullmatch(last(out))
        if code == 0 and m and m.group(2) == "0":
            test = Result("PASS", "harness test", last(out))
        else:
            test = self.fail("harness test", f"exits {code}: {last(out) or last(err)}", "test")
        julia = shutil.which("julia")
        if julia is None:
            return [test, self.fail("Revise", "julia not found", "tools")]
        r = run([julia, "-e", "using Revise"], REVISE_TIMEOUT)
        if r is not None and r[0] == 0:
            return [test, Result("PASS", "Revise", f"julia -e 'using Revise' loads it ({julia})")]
        return [test, Result("WARN", "Revise", f"julia -e 'using Revise' exits {r[0] if r else 127}: "
                                               f"{last(r[2]) or last(r[1]) if r else ''}")]


def numbers_of(version):
    """The three integers of the first version in `version`."""
    return numbers(VERSION.search(version).group(0))


def read(path):
    """The text of `path`, or None when it does not exist or cannot be read."""
    try:
        return pathlib.Path(path).read_text()
    except (OSError, UnicodeDecodeError):
        return None


# The sections of a run, in order.
SECTIONS = ["machine", "tools", "profile_checks", "install", "jobs", "full"]


def run_checks(args, sections=SECTIONS):
    """Print one line for each check of `sections`, as it finishes; the Results."""
    doctor = Doctor(args)
    results = []
    for section in sections:
        for r in getattr(doctor, section)():
            print(f"{r.status:<4}  {r.name:<{WIDTH}}  {r.detail}", flush=True)
            results.append(r)
    return results


def cmd_doctor(args):
    results = run_checks(args)
    counts = {s: sum(r.status == s for r in results) for s in ("PASS", "WARN", "FAIL", "SKIP")}
    print("\n" + ", ".join(f"{n} {s}" for s, n in counts.items()))
    return 1 if counts["FAIL"] else 0


# The cases.

# A token whose value must never reach the output.
TOKEN = "kaimon_" + "5e" * 20
# What each tool prints on each system, {command: [(pattern of its arguments, stdout, stderr,
# exit status)]}. The macOS lines are recorded from the tools on a Mac with the setup page done,
# but for actionlint, whose line is the form of its releases, and launchctl, whose lines are
# written from its known form: in a session's sandbox it gives no answer. The Linux versions are
# those of a machine with Ubuntu 26.04 set up with setup-linux.md, each in its tool's form: the
# lines of gh, shellcheck, timeout and rsync are the form of their upstream releases, and those of
# systemctl, loginctl and bwrap are written from their known form around the answers that the
# machine gave, such as `Linger=no` and `active`.
SHELLCHECK = ("ShellCheck - shell script analysis tool\nversion: 0.11.0\nlicense: GNU General Public License, "
              "version 3\nwebsite: https://www.shellcheck.net\n")
SYSTEMD_TIMERS = (
    "NEXT                            LEFT LAST                              PASSED UNIT                    ACTIVATES\n"
    "Wed 2026-10-21 04:30:00 CEST      9h -                                      - julia-update.timer      "
    "julia-update.service\n"
    "Tue 2026-10-20 19:12:13 CEST 13min Tue 2026-10-20 18:57:13 CEST 1min 2s ago claude-autocommit.timer "
    "claude-autocommit.service\n\n2 timers listed.\nPass --all to see loaded but inactive timers, too.\n")
NO_BUS = "Failed to connect to user scope bus via local transport: No such file or directory\n"
COMMON = {
    "fatou": [("--version", "fatou 0.24.0\n", "", 0)],
    "gitleaks": [("version", "8.30.1\n", "", 0)],
    "rtk": [("--version", "rtk 1.0.1\n", "", 0)],
    "omp": [("--version", "omp/18.12.3\n", "", 0)],
    "shellcheck": [("--version", SHELLCHECK, "", 0)],
}
LINUX = COMMON | {
    "python3": [("--version", "Python 3.14.4\n", "", 0)],
    "gh": [("--version", "gh version 2.46.0 (2024-03-01)\nhttps://github.com/cli/cli/releases/tag/v2.46.0\n", "", 0)],
    "node": [("--version", "v22.22.1\n", "", 0)],
    "actionlint": [("--version", "1.7.12\ninstalled by downloading from release page\n"
                                 "built with go1.26.1 compiler for linux/amd64\n", "", 0)],
    "timeout": [("--version", "timeout (GNU coreutils) 9.7\nCopyright (C) 2025 Free Software Foundation, Inc.\n", "",
                 0)],
    "rsync": [("--version", "rsync  version 3.4.1  protocol version 32\n", "", 0)],
    "julia": [("--version", "julia version 1.13.1\n", "", 0), ("-e using Revise", "", "", 0)],
    "juliaup": [("--version", "Juliaup 1.22.7\n", "", 0)],
    "claude": [("--version", "2.1.304 (Claude Code)\n", "", 0)],
    "opencode": [("--version", "opencode v2.1.1\n", "", 0)],
    "jq": [("--version", "jq-1.8.1\n", "", 0)],
    "bwrap": [("--ro-bind / / --dev /dev --unshare-user --unshare-pid true", "", "", 0)],
    "socat": [("*", "", "", 0)],
    "loginctl": [("show-user * -p Linger", "Linger=yes\n", "", 0)],
    "systemctl": [("--user is-active kaimon.service", "active\n", "", 0),
                  ("--user list-timers --no-pager", SYSTEMD_TIMERS, "", 0)],
}
LAUNCHCTL = ('{\n\t"LimitLoadToSessionType" = "Aqua";\n\t"Label" = "org.example.{job}";\n\t"OnDemand" = false;\n'
             '\t"LastExitStatus" = 0;\n\t"PID" = 4242;\n\t"Program" = "/Users/me/.local/bin/{job}";\n'
             '\t"ProgramArguments" = (\n\t\t"/Users/me/.local/bin/{job}";\n\t);\n};\n')
MACOS = COMMON | {
    "python3": [("--version", "Python 3.14.8\n", "", 0)],
    "gh": [("--version", "gh version 2.102.0 (2026-09-30)\nhttps://github.com/cli/cli/releases/tag/v2.102.0\n", "", 0)],
    "node": [("--version", "v26.12.0\n", "", 0)],
    "actionlint": [("--version", "1.7.12\ninstalled by downloading from release page\n"
                                 "built with go1.26.1 compiler for darwin/arm64\n", "", 0)],
    "timeout": [("--version", "timeout (GNU coreutils) 9.12\nCopyright (C) 2026 Free Software Foundation, Inc.\n", "",
                 0)],
    "rsync": [("--version", "rsync  version 3.5.1  protocol version 33\n", "", 0)],
    "julia": [("--version", "julia version 1.13.2\n", "", 0), ("-e using Revise", "", "", 0)],
    "fatou": [("--version", "fatou 0.23.0\n", "", 0)],
    "juliaup": [("--version", "Juliaup 1.18.9\n", "", 0)],
    "claude": [("--version", "2.1.303 (Claude Code)\n", "", 0)],
    "opencode": [("--version", "opencode v2.1.0\n", "", 0)],
    "rtk": [("--version", "rtk 1.0.1\n", "", 0)],
    "jq": [("--version", "jq-1.7.1-apple\n", "", 0)],
    "launchctl": [(f"list org.example.{job}", LAUNCHCTL.replace("{job}", job), "", 0)
                  for job in ("kaimon", "julia-update", "claude-autocommit")],
}
# The dry run of `harness install` and `harness test`, as their lines end.
INSTALL_OUT = ("julia/Project.toml                 already identical\n"
               "\nWARNING: ~/.config/kaimon/opencode-token does not exist.\n"
               "         Create it (mode 600, the token alone).\n"
               "\n0 change(s) to make.\n")
HARNESS_STUB = [("--profile * install", INSTALL_OUT, "", 0),
                ("test", "ok   sweep: a case\n\n1861 cases, 0 wrong\n", "", 0)]
PACKAGES = {"ExplicitImports": "1.15.0", "JSON": "1.11.0", "JuliaFormatter": "2.14.0", "JuliaSyntax": "1.0.2",
            "TestEnv": "1.103.7", "YAML": "0.4.17"}
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
GIT_VERSION = {"Linux": "git version 2.53.0\n", "Darwin": "git version 2.54.0 (Apple Git-157)\n"}


def stub(path, cases):
    """An executable shell script at `path` that answers its arguments, "$*", with the first case
    of `cases`, [(pattern, stdout, stderr, exit status)], whose pattern matches; `*` in a pattern
    matches anything, as in a shell `case`. Arguments that no case matches exit 99."""
    lines = ["#!/bin/sh", 'case "$*" in']
    for pattern, out, err, code in cases:
        glob = "*".join(shlex.quote(part) if part else "" for part in pattern.split("*"))
        lines.append(f"  {glob}) printf '%s' {shlex.quote(out)}; printf '%s' {shlex.quote(err)} >&2; exit {code} ;;")
    lines += ['  *) echo "stub: no case for $*" >&2; exit 99 ;;', "esac", ""]
    path.write_text("\n".join(lines))
    path.chmod(0o755)


def stubs(directory, system_name):
    """The stubs of `system_name` in `directory`, and a `git` that prints its version as the
    system's git does and passes every other call to the real git."""
    for name, cases in (LINUX if system_name == "Linux" else MACOS).items():
        stub(directory / name, cases)
    version = GIT_VERSION[system_name]
    (directory / "git").write_text(f'#!/bin/sh\n[ "$*" = --version ] && {{ printf %s {shlex.quote(version)}; '
                                   f'exit 0; }}\nexec {shlex.quote(shutil.which("git"))} "$@"\n')
    (directory / "git").chmod(0o755)


def manifest(versions):
    """A Manifest.toml in the form of Julia 1.13, with `versions`, {package: version}."""
    head = '# This file is machine-generated - editing it directly is not advised\n\njulia_version = "1.13.2"\n' \
           'manifest_format = "2.1"\nproject_hash = "94acdf3174e6a47bf3ed8d1b53e835f5db8784a4"\n'
    return head + "".join(f'\n[[deps.{name}]]\ndeps = ["Dates"]\nuuid = "00000000-0000-0000-0000-000000000000"\n'
                          f'version = "{version}"\n' for name, version in versions.items())


class Fixture:
    """A scratch HOME one level below `root`, with every step of the setup page done, and a
    directory of stub commands that print what each tool prints on `system`; `results` runs the
    checks of some sections with both."""

    def __init__(self, root, system_name, claude):
        self.system = system_name
        self.home, self.bin, self.kernel = root / "home", root / "bin", root / "kernel"
        self.julia, self.os_release, self.iterm = root / "julia-env", root / "os-release", root / "iTerm.app"
        config = self.home / ".config" / "research-harness"
        config.mkdir(parents=True)
        self.profile = config / "profile.toml"
        self.profile.write_bytes(profile_module.DUMMY.read_bytes())
        (config / "models.toml").write_bytes((REPO / "examples" / "models.toml").read_bytes())
        (self.home / "Research" / "Environment" / "Agents").mkdir(parents=True)
        (self.home / ".config" / "opencode").mkdir(parents=True)
        self.kaimon = self.home / ".julia" / "bin" / "kaimon"
        self.kaimon.parent.mkdir(parents=True)
        self.kaimon.write_text("#!/bin/sh\n")
        self.kaimon.chmod(0o755)
        self.token = self.home / ".config" / "kaimon" / "opencode-token"
        self.token.parent.mkdir(parents=True)
        self.token.write_text(TOKEN)
        self.token.chmod(0o600)
        shutil.copytree(claude, self.home / ".claude", symlinks=True)
        self.julia.mkdir()
        (self.julia / "Manifest.toml").write_text(manifest(PACKAGES))
        self.kernel.mkdir()
        (self.kernel / "unprivileged_userns_clone").write_text("1\n")
        self.os_release.write_text('PRETTY_NAME="Ubuntu 26.04.1 LTS"\nNAME="Ubuntu"\nVERSION_ID="26.04"\n')
        (self.iterm / "Contents").mkdir(parents=True)
        (self.iterm / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "3.7.3"}))
        self.bin.mkdir()
        stubs(self.bin, system_name)
        self.harness = self.bin / "harness-stub"
        stub(self.harness, HARNESS_STUB)

    @contextlib.contextmanager
    def patched(self, full=False, sandbox=False, arch=None, only=None, models=None, extra=None):
        """The arguments of a run on this fixture, inside a context with its HOME, its PATH, its
        system and its files in place of the machine's, and stdout in `self.out`; `only` names
        the tools of TOOLS that the run checks, else all, and `extra` adds variables."""
        env = {k: v for k, v in os.environ.items()
               if k not in (SANDBOX, "OPENCODE_CONFIG_DIR", "RESEARCH_HARNESS_PROFILE", "RESEARCH_HARNESS_MODELS")
               and not k.startswith("GIT_")}
        env.update(GIT_ENV, HOME=str(self.home), PATH=str(self.bin), **({SANDBOX: "1"} if sandbox else {}),
                   **(extra or {}))
        self.out = io.StringIO()
        with (mock.patch.dict(os.environ, env, clear=True), mock.patch(f"{__name__}.system", lambda: self.system),
              mock.patch(f"{__name__}.machine", lambda: arch or ("x86_64" if self.system == "Linux" else "arm64")),
              mock.patch(f"{__name__}.KERNEL", self.kernel), mock.patch(f"{__name__}.OS_RELEASE", self.os_release),
              mock.patch(f"{__name__}.ITERM", self.iterm), mock.patch(f"{__name__}.HARNESS", [str(self.harness)]),
              mock.patch.object(install, "JULIA_ENV", self.julia), contextlib.redirect_stdout(self.out),
              mock.patch(f"{__name__}.TOOLS", [t for t in TOOLS if only is None or t[0] in only])):
            yield types.SimpleNamespace(profile=str(self.profile), models=models, full=full)

    def results(self, *sections, **options):
        """(the Results by name, the printed text) of `sections`, else of every section, on this
        fixture; `options` as `patched` takes them."""
        with self.patched(**options) as args:
            results = run_checks(args, sections or SECTIONS)
        return {r.name: r for r in results}, self.out.getvalue()

    def tool(self, name, *cases):
        """Replace the stub `name` with one that answers `cases`."""
        stub(self.bin / name, list(cases))


def minimum_cases(check):
    """MINIMUMS against the tables of docs/src/dependencies.md: a tool with a `≥` in its minimum
    cell has exactly those versions, and a tool with none has no minimum here."""
    page = (REPO / "docs" / "src" / "dependencies.md").read_text()
    rows = re.findall(r"^\| ([^|]+?) \| ([^|]+?) \| [^|]+\|$", page, re.M)
    found = {tool: tuple(re.findall(r"≥ (\d+(?:\.\d+)*)", cell)) for tool, cell in rows if tool != "tool"}
    check(len(found) >= 20, f"dependencies.md has {len(found)} rows of tools")
    for tool, floors in found.items():
        check(MINIMUMS.get(tool, ()) == floors, f"the minimum of {tool}: {MINIMUMS.get(tool, ())} here, {floors} "
                                                f"in dependencies.md")
    check(set(MINIMUMS) <= set(found), f"every tool of MINIMUMS is a row of dependencies.md: "
                                       f"{sorted(set(MINIMUMS) - set(found))} are not")
    names = {name for name, *_ in TOOLS} | set(PACKAGES) | {"Kaimon", "iTerm2"}
    check(set(found) == names, f"the checks cover each tool of dependencies.md: missing {sorted(set(found) - names)}, "
                               f"extra {sorted(names - set(found))}")


def below(floor):
    """The last release before `floor`, as a version string."""
    a, b, c = (int(n) for n in (floor + ".0").split(".")[:3])
    return f"{a}.{b}.{c - 1}" if c else f"{a}.{b - 1}.99" if b else f"{a - 1}.99.99"


def status_cases(check, root, system_name):
    """Each status of each check on a fixture of `system_name`."""
    linux = system_name == "Linux"
    claude = root / "claude-template"
    subprocess.run(["git", "init", "-q", "-b", "main", str(claude)], check=True, capture_output=True,
                   env=environment() | GIT_ENV)
    subprocess.run(["git", "-C", str(claude), "remote", "add", "origin", "https://user:url-secret@example.org/m.git"],
                   check=True, capture_output=True, env=environment() | GIT_ENV)
    n = 0

    def fixture():
        nonlocal n
        n += 1
        return Fixture(root / f"case{n}", system_name, claude)

    def expect(label, got, want, text="", darwin=not linux):
        """Each check of `want`, {name: status}, has its status in `got`; a FAIL ends with a fix of
        FIX for its system, macOS when `darwin`, and nothing prints the token or the origin's URL."""
        wrong = {name: (got[name].status if name in got else None) for name, status in want.items()
                 if name not in got or got[name].status != status}
        sections = {pair[1] or pair[0] if darwin else pair[0] for pair in FIX.values()}
        fails = [r for r in got.values() if r.status == "FAIL"
                 and not any(r.detail.endswith(f"(fix: {s})") for s in sections)]
        leaked = TOKEN in text or "url-secret" in text
        check(not wrong and not fails and not leaked,
              f"{system_name}: {label} -> {want}" + (f"; got {wrong}" if wrong else "")
              + (f"; a FAIL with no fix of this system: {fails}" if fails else "")
              + ("; the output holds a secret" if leaked else ""))

    def case(label, want, change=lambda f: None, sections=(), **options):
        f = fixture()
        change(f)
        got, text = f.results(*sections, **options)
        expect(label, got, want, text, darwin=f.system == "Darwin")
        return got, text

    # The whole run on a machine with every step done: no FAIL, and each line in the format.
    got, text = case("every step done", {name: "PASS" for name in ("system", "Python", "Kaimon", "profile",
                                                                     "install", "kaimon job", "julia-update job",
                                                                     "autocommit job", "~/.claude repository",
                                                                     "Kaimon token")} | {"install warning 1": "WARN",
                                                                                         "harness test": "SKIP",
                                                                                         "Revise": "SKIP"})
    lines = text.splitlines()
    form = re.compile(r"(PASS|WARN|FAIL|SKIP)  \S.{%d,}  \S.*" % (WIDTH - 1))
    check(all(form.fullmatch(line) for line in lines) and len(lines) == len(got),
          f"{system_name}: each of the {len(lines)} lines is a status, a name and a detail: "
          f"{[line for line in lines if not form.fullmatch(line)]}")
    check(not [r for r in got.values() if r.status == "FAIL"], f"{system_name}: every step done gives no FAIL -> "
                                                                f"{[r for r in got.values() if r.status == 'FAIL']}")

    # The machine.
    if linux:
        case("an architecture the page does not cover", {"system": "WARN", "sandbox": "PASS"}, sections=("machine",),
             arch="riscv64")
        case("aarch64", {"system": "PASS"}, sections=("machine",), arch="aarch64")
        case("unprivileged_userns_clone = 0", {"userns clone": "FAIL"},
             lambda f: (f.kernel / "unprivileged_userns_clone").write_text("0\n"), ("machine",))
        case("no unprivileged_userns_clone", {"userns clone": "PASS"},
             lambda f: (f.kernel / "unprivileged_userns_clone").unlink(), ("machine",))
        case("apparmor_restrict_unprivileged_userns = 1", {"apparmor userns": "WARN"},
             lambda f: (f.kernel / "apparmor_restrict_unprivileged_userns").write_text("1\n"), ("machine",))
        case("apparmor_restrict_unprivileged_userns = 0", {"apparmor userns": "PASS"},
             lambda f: (f.kernel / "apparmor_restrict_unprivileged_userns").write_text("0\n"), ("machine",))
        refused_bwrap = ("--ro-bind / / --dev /dev --unshare-user --unshare-pid true", "",
                         "bwrap: setting up uid map: Permission denied\n", 1)
        case("bwrap refused", {"sandbox": "FAIL"}, lambda f: f.tool("bwrap", refused_bwrap), ("machine",))
        case("bwrap refused in a session's sandbox", {"sandbox": "SKIP"}, lambda f: f.tool("bwrap", refused_bwrap),
             ("machine",), sandbox=True)
        case("no bwrap", {"sandbox": "FAIL"}, lambda f: (f.bin / "bwrap").unlink(), ("machine",))
        case("no socat", {"socat": "FAIL"}, lambda f: (f.bin / "socat").unlink(), ("machine",))
    else:
        case("macOS", {"system": "PASS"}, sections=("machine",))
        got, _ = case("another system", {"system": "WARN"}, sections=("machine", "jobs"),
                      change=lambda f: setattr(f, "system", "FreeBSD"))
        check(set(got) == {"system", "Kaimon"},
              f"another system has no machine-specific check and no job: {sorted(got)}")

        def other(f):
            f.system = "FreeBSD"
            (f.bin / "julia").unlink()
        got, _ = case("another system without julia", {"Julia": "FAIL"}, other, ("tools",), only=("Julia",))
        check(got["Julia"].detail.endswith("(fix: setup-linux.md, The dependencies)"),
              f"another system names the Linux page -> {got['Julia'].detail!r}")

    # The tools: each required one missing, each optional one missing, each minimum and the
    # release before it, and output with no version.
    stubs = LINUX if linux else MACOS
    printed = (LINUX if linux else MACOS) | {"git": [("--version", GIT_VERSION[system_name], "", 0)]}
    for name, command, flags, without in TOOLS:
        status = "FAIL" if without is None else "WARN"
        one = {"only": (name,)}
        case(f"no {command}", {name: status}, lambda f, c=command: (f.bin / c).unlink(), ("tools",), **one)
        case(f"{command} prints no version", {name: "WARN"},
             lambda f, c=command, a=flags: f.tool(c, (" ".join(a), "command-line tool, no number here\n", "", 0)),
             ("tools",), **one)
        # A version flag that exits non-zero: FAIL for a required tool, WARN for an optional one,
        # and SKIP in a session's sandbox, where gh prints its version, a warning and exits 1.
        exits = lambda f, c=command, a=flags: f.tool(c, (" ".join(a), printed[c][0][1],
                                                         "warning: failed to load config\n", 1))
        got, _ = case(f"{command} exits 1", {name: status}, exits, ("tools",), **one)
        check(f"{' '.join([command, *flags])} exits 1" in got[name].detail,
              f"{system_name}: {command} exits 1 names the exit -> {got[name].detail!r}")
        got, _ = case(f"{command} exits 1 in a session's sandbox", {name: "SKIP"}, exits, ("tools",), sandbox=True,
                      **one)
        check("sandbox" in got[name].detail, f"{system_name}: the SKIP names the sandbox -> {got[name].detail!r}")
        case(f"{command} exits 127", {name: status},
             lambda f, c=command, a=flags: f.tool(c, (" ".join(a), "", "error while loading shared libraries: "
                                                      "libfoo.so.1: cannot open shared object file\n", 127)),
             ("tools",), **one)
        case(f"{command} prints no version in a session's sandbox", {name: "WARN"},
             lambda f, c=command, a=flags: f.tool(c, (" ".join(a), "command-line tool, no number here\n", "", 0)),
             ("tools",), sandbox=True, **one)
        for floor in MINIMUMS.get(name, ()):
            out = printed[command][0][1]
            at = VERSION.search(out).group(0)
            for version, want in ((floor, "PASS"), (below(floor), "FAIL")):
                text = out.replace(at, version, 1)
                case(f"{command} at {version}, minimum {' or '.join(MINIMUMS[name])}", {name: want},
                     lambda f, c=command, a=flags, t=text: f.tool(c, (" ".join(a), t, "", 0)), ("tools",), **one)
    for version, want in (("21.7.3", "FAIL"), ("20.18.0", "PASS"), ("18.20.4", "FAIL"), ("23.0.0", "PASS")):
        case(f"node at {version}", {"Node.js": want},
             lambda f, v=version: f.tool("node", ("--version", f"v{v}\n", "", 0)), ("tools",), only=("Node.js",))
    case("fatou 0.22 against the minimum 0.22.0", {"fatou": "PASS"},
         lambda f: f.tool("fatou", ("--version", "fatou 0.22\n", "", 0)), ("tools",), only=("fatou",))
    case("a version of gitleaks with a v", {"gitleaks": "FAIL"},
         lambda f: f.tool("gitleaks", ("version", "v8.16.0\n", "", 0)), ("tools",), only=("gitleaks",))

    def garbage(f):
        (f.bin / "jq").write_bytes(b"\x00\x01\x02 not a program\n")
    got, _ = case("a jq that cannot start", {"jq": "WARN"}, garbage, ("tools",), only=("jq",))
    check("cannot start" in got["jq"].detail, f"{system_name}: the line names the reason -> {got['jq'].detail!r}")
    with mock.patch(f"{__name__}.TIMEOUT", 1):
        got, _ = case("a jq that does not answer", {"jq": "WARN"},
                      lambda f: (f.bin / "jq").write_text("#!/bin/sh\nexec /bin/sleep 5\n"), ("tools",), only=("jq",))
    check("no answer after 1 s" in got["jq"].detail, f"{system_name}: the line names the time -> {got['jq'].detail!r}")
    # The cases below check no tool of TOOLS.
    none = {"only": ()}
    if not linux:
        case("no iTerm2", {"iTerm2": "WARN"}, lambda f: shutil.rmtree(f.iterm), ("tools",), **none)
        case("an Info.plist of iTerm2 that is no plist", {"iTerm2": "WARN"},
             lambda f: (f.iterm / "Contents" / "Info.plist").write_text("not a plist\n"), ("tools",), **none)
    else:
        got, _ = case("iTerm2 on Linux", {}, sections=("tools",), **none)
        check("iTerm2" not in got, f"Linux: no iTerm2 line -> {got.get('iTerm2')}")
    case("every Julia package", {name: "PASS" for name in PACKAGES}, sections=("tools",), **none)
    for name, floor in ((n, MINIMUMS[n][0]) for n in PACKAGES):
        for version, want in ((floor, "PASS"), (below(floor), "FAIL")):
            case(f"{name} {version} in the manifest", {name: want},
                 lambda f, n=name, v=version: (f.julia / "Manifest.toml").write_text(manifest(PACKAGES | {n: v})),
                 ("tools",), **none)
    case("JSON not in the manifest", {"JSON": "FAIL", "YAML": "PASS"},
         lambda f: (f.julia / "Manifest.toml").write_text(manifest({k: v for k, v in PACKAGES.items() if k != "JSON"})),
         ("tools",), **none)
    case("no manifest", {name: "FAIL" for name in PACKAGES}, lambda f: (f.julia / "Manifest.toml").unlink(), ("tools",),
         **none)
    case("a manifest that is not TOML", {name: "WARN" for name in PACKAGES},
         lambda f: (f.julia / "Manifest.toml").write_text("[[deps.JSON\n"), ("tools",), **none)
    case("a version in the manifest that is no version", {"JSON": "WARN"},
         lambda f: (f.julia / "Manifest.toml").write_text(manifest(PACKAGES | {"JSON": "latest"})), ("tools",), **none)
    case("a manifest with no table deps", {name: "WARN" for name in PACKAGES},
         lambda f: (f.julia / "Manifest.toml").write_text('julia_version = "1.13.2"\n'), ("tools",), **none)
    if os.geteuid() != 0:  # root reads a file of mode 000
        for sandbox, want in ((False, "FAIL"), (True, "SKIP")):
            case(f"a manifest that cannot be read, sandbox {sandbox}", {name: want for name in PACKAGES},
                 lambda f: (f.julia / "Manifest.toml").chmod(0), ("tools",), sandbox=sandbox, **none)

    # The profile.
    for label, text in (("no profile", None), ("a profile that is not TOML", "home = \n"),
                        ("a relative home", 'home = "h"\n')):
        def change(f, text=text):
            f.profile.unlink() if text is None else f.profile.write_text(text)
        case(label, {"profile": "FAIL", "tree_agents": "SKIP", "OpenCode directory": "PASS",
                     "autocommit_branch": "SKIP", "install": "SKIP"}
             | ({"kaimon job": "SKIP", "julia-update job": "SKIP", "autocommit job": "SKIP"} if not linux else {}),
             change, ("profile_checks", "install", "jobs"))
    case("no tree_agents directory", {"tree_agents": "FAIL"},
         lambda f: shutil.rmtree(f.home / "Research" / "Environment" / "Agents"), ("profile_checks",))
    case("no tree_agents key", {"tree_agents": "FAIL"},
         lambda f: f.profile.write_text(re.sub(r"^tree_agents = .*$", "", f.profile.read_text(), flags=re.M)),
         ("profile_checks",))
    with mock.patch.object(profile_module, "load", side_effect=PermissionError(1, "Operation not permitted")):
        got, _ = case("a profile that cannot be read", {"profile": "FAIL", "install": "SKIP"},
                      sections=("profile_checks", "install"))
    check("cannot read the profile" in got["profile"].detail,
          f"{system_name}: the line says why -> {got['profile'].detail!r}")
    case("no OpenCode directory", {"OpenCode directory": "FAIL"},
         lambda f: shutil.rmtree(f.home / ".config" / "opencode"), ("profile_checks",))
    other = root / "opencode-elsewhere"
    other.mkdir(parents=True)
    case("$OPENCODE_CONFIG_DIR, and no ~/.config/opencode", {"OpenCode directory": "PASS"},
         lambda f: shutil.rmtree(f.home / ".config" / "opencode"), ("profile_checks",),
         extra={"OPENCODE_CONFIG_DIR": str(other)})
    case("an $OPENCODE_CONFIG_DIR that does not exist, and ~/.config/opencode", {"OpenCode directory": "FAIL"},
         sections=("profile_checks",), extra={"OPENCODE_CONFIG_DIR": str(root / "no-such-directory")})
    got, _ = case("autocommit_branch", {"autocommit_branch": "PASS"},
                  lambda f: f.profile.write_text(f.profile.read_text() + 'autocommit_branch = "memory/case"\n'),
                  ("profile_checks",))
    check(got["autocommit_branch"].detail == "memory/case",
          f"{system_name}: the autocommit_branch line prints the value -> {got['autocommit_branch'].detail!r}")

    # The install.
    case("an install with changes", {"install": "FAIL"},
         lambda f: stub(f.harness, [("*install", "julia/Project.toml                 REPLACE\n\n5 change(s) to make.\n",
                                     "", 1)]), ("install",))
    models = root / "models.toml"
    case("--models", {"install": "PASS"},
         lambda f: stub(f.harness, [("--profile * --models * install", INSTALL_OUT, "", 0)]), ("install",),
         models=str(models))
    case("an install that exits 2", {"install": "FAIL"},
         lambda f: stub(f.harness, [("*install", "", "harness install: no profile at /x/profile.toml\n", 2)]),
         ("install",))
    three = INSTALL_OUT.replace("\n0 change", "\nWARNING: ~/.omp/agent/.env lacks PI_CONFIG_FILES.\n"
                                              "\nWARNING: the checkout ~/Research/Harness is 3 commit(s) behind its "
                                              "origin/main.\n         Run `git pull` there, then install again.\n"
                                              "\n0 change")
    got, _ = case("three install warnings", {"install": "PASS", "install warning 1": "WARN",
                                             "install warning 2": "WARN", "install warning 3": "WARN"},
                  lambda f: stub(f.harness, [("*install", three, "", 0)]), ("install",))
    check("3 commit(s) behind" in got["install warning 3"].detail,
          f"{system_name}: an install warning's line is its first line -> {got['install warning 3'].detail!r}")

    # The jobs.
    case("no Kaimon", {"Kaimon": "WARN", "kaimon job": "SKIP", "julia-update job": "SKIP", "Kaimon token": "SKIP",
                       "autocommit job": "PASS"}, lambda f: f.kaimon.unlink(), ("jobs",))
    case("a Kaimon that is not executable", {"Kaimon": "WARN", "kaimon job": "SKIP"}, lambda f: f.kaimon.chmod(0o644),
         ("jobs",))
    case("no OpenCode", {"Kaimon token": "PASS"}, lambda f: (f.bin / "opencode").unlink(), ("jobs",))
    case("no oh-my-pi", {"Kaimon token": "PASS"}, lambda f: (f.bin / "omp").unlink(), ("jobs",))
    case("neither OpenCode nor oh-my-pi", {"Kaimon token": "SKIP"},
         lambda f: ((f.bin / "opencode").unlink(), (f.bin / "omp").unlink()), ("jobs",))
    case("no token file", {"Kaimon token": "FAIL"}, lambda f: f.token.unlink(), ("jobs",))
    case("a token of mode 644", {"Kaimon token": "FAIL"}, lambda f: f.token.chmod(0o644), ("jobs",))
    case("an empty token", {"Kaimon token": "FAIL"}, lambda f: f.token.write_text(""), ("jobs",))

    def directory(f):
        f.token.unlink()
        f.token.mkdir(mode=0o600)
    case("a token that is a directory of mode 600", {"Kaimon token": "FAIL"}, directory, ("jobs",))

    def denied(f):
        """A stat of the token that the sandbox denies."""
        real = os.stat
        f.patch = mock.patch(f"{__name__}.os.stat", lambda p, *a, **k: (_ for _ in ()).throw(
            PermissionError(1, "Operation not permitted")) if str(p).endswith("opencode-token") else real(p, *a, **k))
    for sandbox, want in ((True, "SKIP"), (False, "FAIL")):
        f = fixture()
        denied(f)
        with f.patch:
            got, text = f.results("jobs", sandbox=sandbox)
        expect(f"a token whose stat is denied, sandbox {sandbox}", got, {"Kaimon token": want}, text)
    case("~/.claude not a repository", {"~/.claude repository": "FAIL"},
         lambda f: shutil.rmtree(f.home / ".claude" / ".git"), ("jobs",))
    case("~/.claude without an origin", {"~/.claude repository": "FAIL"},
         lambda f: subprocess.run(["git", "-C", str(f.home / ".claude"), "remote", "remove", "origin"], check=True,
                                  env=environment() | GIT_ENV), ("jobs",))

    def inside(f):
        """~/.claude a plain directory in a repository of the home, which has an origin."""
        shutil.rmtree(f.home / ".claude" / ".git")
        for command in (["init", "-q", str(f.home)],
                        ["-C", str(f.home), "remote", "add", "origin", "https://example.org/h.git"]):
            subprocess.run(["git", *command], check=True, env=environment() | GIT_ENV)
    got, _ = case("~/.claude inside the home's repository", {"~/.claude repository": "FAIL"}, inside, ("jobs",))
    check("inside the repository" in got["~/.claude repository"].detail,
          f"{system_name}: the line names the repository around ~/.claude -> {got['~/.claude repository'].detail!r}")
    case("no git", {"~/.claude repository": "FAIL"}, lambda f: (f.bin / "git").unlink(), ("jobs",))
    # As inside a git hook, which exports GIT_DIR: the check still reads ~/.claude.
    case("~/.claude not a repository, with GIT_DIR of another one", {"~/.claude repository": "FAIL"},
         lambda f: shutil.rmtree(f.home / ".claude" / ".git"), ("jobs",), extra={"GIT_DIR": str(claude / ".git")})
    if linux:
        case("Linger=no", {"linger": "FAIL"},
             lambda f: f.tool("loginctl", ("show-user * -p Linger", "Linger=no\n", "", 0)), ("jobs",))
        no_user = ("show-user * -p Linger", "", "Failed to get user: User ID 1000 is not logged in or lingering\n", 1)
        case("loginctl without an answer", {"linger": "FAIL"}, lambda f: f.tool("loginctl", no_user), ("jobs",))
        case("loginctl without an answer in a session's sandbox", {"linger": "SKIP"},
             lambda f: f.tool("loginctl", no_user), ("jobs",), sandbox=True)
        case("no loginctl", {"linger": "FAIL"}, lambda f: (f.bin / "loginctl").unlink(), ("jobs",))
        timers = ("--user list-timers --no-pager", SYSTEMD_TIMERS, "", 0)
        for state in ("inactive", "failed"):
            case(f"kaimon.service {state}", {"kaimon job": "FAIL"},
                 lambda f, s=state: f.tool("systemctl", ("--user is-active kaimon.service", f"{s}\n", "", 3), timers),
                 ("jobs",))
        no_bus = [("--user is-active kaimon.service", "", NO_BUS, 1), ("--user list-timers --no-pager", "", NO_BUS, 1)]
        case("systemctl without a bus", {"kaimon job": "FAIL", "julia-update job": "FAIL", "autocommit job": "FAIL",
                                         "~/.claude repository": "SKIP"},
             lambda f: f.tool("systemctl", *no_bus), ("jobs",))
        case("systemctl without a bus in a session's sandbox",
             {"kaimon job": "SKIP", "julia-update job": "SKIP", "autocommit job": "SKIP",
              "~/.claude repository": "SKIP"}, lambda f: f.tool("systemctl", *no_bus), ("jobs",), sandbox=True)
        only = "\n".join(line for line in SYSTEMD_TIMERS.splitlines() if "julia-update" not in line) + "\n"
        case("no julia-update.timer", {"julia-update job": "FAIL", "autocommit job": "PASS"},
             lambda f: f.tool("systemctl", ("--user is-active kaimon.service", "active\n", "", 0),
                              ("--user list-timers --no-pager", only, "", 0)), ("jobs",))
        only = "\n".join(line for line in SYSTEMD_TIMERS.splitlines() if "claude-autocommit" not in line) + "\n"
        case("no claude-autocommit.timer", {"autocommit job": "SKIP", "~/.claude repository": "SKIP",
                                            "julia-update job": "PASS"},
             lambda f: f.tool("systemctl", ("--user is-active kaimon.service", "active\n", "", 0),
                              ("--user list-timers --no-pager", only, "", 0)), ("jobs",))
        case("no claude-autocommit.timer and no ~/.claude repository", {"~/.claude repository": "SKIP"},
             lambda f: (f.tool("systemctl", ("--user is-active kaimon.service", "active\n", "", 0),
                               ("--user list-timers --no-pager", only, "", 0)),
                        shutil.rmtree(f.home / ".claude" / ".git")), ("jobs",))
        case("no systemctl", {"kaimon job": "FAIL", "julia-update job": "FAIL", "autocommit job": "FAIL"},
             lambda f: (f.bin / "systemctl").unlink(), ("jobs",))
    else:
        def launchctl(*missing, error=None):
            def change(f):
                cases = []
                for job in ("kaimon", "julia-update", "claude-autocommit"):
                    if error is not None:
                        cases.append((f"list org.example.{job}", "", error, 1))
                    elif job in missing:
                        cases.append((f"list org.example.{job}", "",
                                      f'Could not find service "org.example.{job}" in domain for port\n', 113))
                    else:
                        cases.append((f"list org.example.{job}", LAUNCHCTL.replace("{job}", job), "", 0))
                f.tool("launchctl", *cases)
            return change
        case("kaimon not loaded", {"kaimon job": "FAIL", "julia-update job": "PASS"}, launchctl("kaimon"), ("jobs",))
        case("julia-update not loaded", {"julia-update job": "FAIL", "kaimon job": "PASS"}, launchctl("julia-update"),
             ("jobs",))
        case("claude-autocommit not loaded", {"autocommit job": "SKIP", "~/.claude repository": "SKIP"},
             launchctl("claude-autocommit"), ("jobs",))
        case("claude-autocommit not loaded and no ~/.claude repository", {"~/.claude repository": "SKIP"},
             lambda f: (launchctl("claude-autocommit")(f), shutil.rmtree(f.home / ".claude" / ".git")), ("jobs",))
        # In a session's sandbox, `launchctl list <label>` exits 1 and prints nothing.
        case("launchctl without an answer", {"kaimon job": "FAIL", "julia-update job": "FAIL", "autocommit job": "FAIL",
                                             "~/.claude repository": "SKIP"}, launchctl(error=""), ("jobs",))
        case("launchctl without an answer in a session's sandbox",
             {"kaimon job": "SKIP", "julia-update job": "SKIP", "autocommit job": "SKIP",
              "~/.claude repository": "SKIP"}, launchctl(error=""), ("jobs",), sandbox=True)
        case("no launchctl", {"kaimon job": "FAIL", "julia-update job": "FAIL", "autocommit job": "FAIL"},
             lambda f: (f.bin / "launchctl").unlink(), ("jobs",))

    # The slow checks.
    case("--full", {"harness test": "PASS", "Revise": "PASS"}, sections=("full",), full=True)
    case("--full with a wrong case", {"harness test": "FAIL"},
         lambda f: stub(f.harness, [("test", "BAD  a case\n\n1861 cases, 1 wrong\n", "", 1)]), ("full",), full=True)
    case("--full with no summary line", {"harness test": "FAIL"},
         lambda f: stub(f.harness, [("test", "", "Traceback (most recent call last):\n", 1)]), ("full",), full=True)
    case("--full without Revise", {"Revise": "WARN"},
         lambda f: f.tool("julia", ("--version", "julia version 1.13.2\n", "", 0),
                          ("-e using Revise", "", "ERROR: ArgumentError: Package Revise not found in current path.\n",
                           1)), ("full",), full=True)
    case("--full without julia", {"Revise": "FAIL"}, lambda f: (f.bin / "julia").unlink(), ("full",), full=True)

    # Nothing on the PATH: each check reports what is missing, and none raises.
    f = fixture()
    for path in f.bin.iterdir():
        if path != f.harness:
            path.unlink()
    try:
        got, text = f.results()
        raised = None
    except Exception as e:  # the case reports what a check raised instead of stopping the suite
        got, text, raised = {}, "", repr(e)
    missing = [name for name, command, _, without in TOOLS if without is None]
    check(raised is None and all(got[name].status == "FAIL" and "not found" in got[name].detail for name in missing),
          f"{system_name}: with nothing on the PATH, each required tool is a FAIL that names it, and no check raises "
          f"-> {raised or [got.get(n) for n in missing if got[n].status != 'FAIL']}")


def exit_cases(check, root):
    """The exit status: 0 with PASS, WARN and SKIP lines only, 1 with a FAIL; and 2 on a usage
    error, in a process of its own."""
    claude = root / "claude-template"
    subprocess.run(["git", "init", "-q", "-b", "main", str(claude)], check=True, capture_output=True,
                   env=environment() | GIT_ENV)
    subprocess.run(["git", "-C", str(claude), "remote", "add", "origin", "https://example.org/m.git"],
                   check=True, capture_output=True, env=environment() | GIT_ENV)
    this = system() if system() in ("Linux", "Darwin") else "Linux"
    for label, change, want in (
            ("only PASS, WARN and SKIP", lambda f: None, 0),
            ("one FAIL", lambda f: f.token.chmod(0o644), 1),
            ("one FAIL in the install",
             lambda f: stub(f.harness, [("*install", "\n1 change(s) to make.\n", "", 1)]), 1)):
        f = Fixture(root / label.replace(" ", "-").replace(",", ""), this, claude)
        change(f)
        with f.patched() as args:
            code = cmd_doctor(args)
        statuses = sorted({line[:4] for line in f.out.getvalue().splitlines()[:-2]})
        check(code == want, f"{label}: exit {code} -> {statuses}")
    for argv in (["doctor", "--bogus"], ["doctor", "extra"]):
        p = subprocess.run(HARNESS + argv, capture_output=True, text=True)
        check(p.returncode == 2 and "Traceback" not in p.stderr, f"harness {' '.join(argv)}: exit {p.returncode}")


def process_cases(check, root):
    """`harness doctor` in a process of its own on the contract sweep's fixture, with the stubs of
    this system on the PATH and the real dry run of `harness install`: it exits 0 or 1, prints no
    traceback and changes no file below the fixture."""
    from . import sweep

    if system() not in ("Linux", "Darwin"):
        return
    home = root / "home"
    env = {k: v for k, v in os.environ.items()
           if k not in sweep.UNSET and k != SANDBOX and not k.startswith("GIT_")}
    env.update(sweep.GIT, HOME=str(home), RESEARCH_ROOT=str(home / "Research"),
               RESEARCH_HARNESS_JULIA=str(root / "julia-env"))
    sweep.make_fixture(home, env)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    stubs(bin_dir, system())
    env["PATH"] = str(bin_dir)
    before = sweep.digest(root)
    p = subprocess.run(HARNESS + ["doctor"], capture_output=True, text=True, env=env, cwd=root, timeout=300)
    changed = sweep.digest(root) != before
    install_line = next((line for line in p.stdout.splitlines()
                         if line.startswith(("PASS  install ", "FAIL  install "))), None)
    check(p.returncode in (0, 1) and "Traceback" not in p.stdout + p.stderr and not changed
          and install_line is not None and "change(s) to make" in install_line,
          f"harness doctor on the sweep's fixture: exit {p.returncode}, a file changed {changed}, the install line "
          f"{install_line!r}" + (f": {p.stderr.strip()[-300:]!r}" if p.returncode not in (0, 1) else ""))


def selftest():
    """The minimums against dependencies.md, each status of each check on a fixture of Linux and
    of macOS, the exit status, and a run in a process of its own: (number of cases, number
    wrong)."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  doctor: {label}")

    minimum_cases(check)
    with tempfile.TemporaryDirectory(prefix="harness-doctor-") as tmp:
        root = pathlib.Path(tmp)
        for system_name in ("Linux", "Darwin"):
            status_cases(check, root / system_name, system_name)
        exit_cases(check, root / "exit")
        process_cases(check, root / "process")
    return total, wrong


def register(sub):
    p = sub.add_parser("doctor", help="check this machine's setup, read-only; a session's sandbox makes some checks "
                                      "SKIP, so run it in a plain terminal",
                       description="Check this machine's setup, read-only: one line per check, PASS, WARN, FAIL or "
                                   "SKIP; exit 1 when one fails. A session's sandbox refuses some of the commands, "
                                   "and those checks are SKIP: run it in a plain terminal for the real verdict.")
    p.add_argument("--full", action="store_true", help="also run `harness test` and `julia -e 'using Revise'`, which "
                                                       "take minutes")
    p.set_defaults(run=cmd_doctor)
