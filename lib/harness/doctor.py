"""The read-only subcommand `harness doctor`: one line for each check of this machine's setup.

    harness doctor [--full]

The checks, in this order:

- the machine: the system and the architecture; on Linux the two kernel settings for user
  namespaces, a sandbox of `bwrap` and `socat`;
- the tools of docs/src/dependencies.md: each found on the PATH, and at or above its minimum where
  the page states one (MINIMUMS); the Julia packages of Project.toml in the Manifest.toml of the
  Julia environment of the scripts, SKIP where the profile's `[setup]` does not choose the `julia`
  component; the Python environment of the harness, whose interpreter must start at or above the
  minimum of Python, and which is a WARN when it lags uv.lock;
- the profile: it loads, the `tree_agents` directory and OpenCode's configuration directory exist,
  the latter SKIP where `[setup]` does not choose `opencode`, and its `autocommit_branch`;
- the install: the dry run of `harness install`, and each of its warnings; and a WARN for each
  frontend that `[setup]` does not choose and whose layer is still installed or whose plan
  refuses;
- the jobs: Kaimon, its server and the update job; the autocommit job, and when it is enabled,
  `~/.claude` as the top of its own git repository with an `origin`; the Kaimon token file; on
  Linux also linger;
- with `--full`, `harness test` and `julia -e 'using Revise'`; without it, both are SKIP.

Each line is `PASS`, `WARN`, `FAIL` or `SKIP`, the name of the check and a detail. A FAIL line
also names the section of the setup pages that fixes it (FIX). The subcommand exits 1 when a check
fails, else 0; a WARN or a SKIP does not count.

It changes nothing: it reads files, and runs the version flags of the tools, the dry run of
`harness install` and the status commands of the jobs. It reads no secret: the Kaimon token only
for its existence, mode and size, and of `~/.claude`'s `origin` only whether it exists, since a
remote URL can hold a credential.

A session's sandbox, known by $SANDBOX_RUNTIME, can refuse `bwrap`, `systemctl`, `loginctl`,
`launchctl` and the version flag of a tool, and deny a file. There, such a check that does not
get its answer is SKIP with the reason; run the subcommand in a plain terminal for its real
verdict.
"""

import argparse
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
from collections.abc import Callable
from typing import Any, cast
from unittest import mock

from . import REPO, HarnessError, frontends, fsutil, install, sources
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
    "Python": ("3.14",),
    "gitleaks": ("8.21",),
    "Node.js": ("20.16", "22.3"),
    "actionlint": ("1.7.12",),
    "Julia": ("1.13",),
    "ExplicitImports": ("1.15",),
    "JSON": ("1.10",),
    "JuliaFormatter": ("2.14",),
    "JuliaSyntax": ("1.0.2",),
    "TestEnv": ("1.103.7",),
    "YAML": ("0.4.17",),
    "fatou": ("0.22.0",),
}
# (name in dependencies.md, command, its version arguments, what stops without it); a tool with no
# such text is required: a FAIL when it is missing, a WARN for the others.
TOOLS = [
    ("Python", "python3", ["--version"], None),
    ("uv", "uv", ["--version"], "harness install cannot sync the Python environment"),
    ("git", "git", ["--version"], None),
    ("gh", "gh", ["--version"], None),
    ("Node.js", "node", ["--version"], None),
    ("shellcheck", "shellcheck", ["--version"], None),
    ("actionlint", "actionlint", ["--version"], None),
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
# The section that fixes a FAIL, {topic: (on Linux, on macOS)}: a page below docs/src/ and a
# level-2 heading of it, which `fix_cases` checks. setup-reference.md gives each step for both
# systems; the check that it worked is a section of each setup page.
FIX = {
    "machine": ("setup-reference.md, Check the machine", "setup-reference.md, Check the machine"),
    "sandbox": (
        "setup-reference.md, The sandbox of Claude Code",
        "setup-reference.md, The sandbox of Claude Code",
    ),
    "tools": ("setup-reference.md, The packages", "setup-reference.md, The packages"),
    "profile": (
        "setup-reference.md, The profile and the model tables",
        "setup-reference.md, The profile and the model tables",
    ),
    "tree": ("setup-reference.md, The tree instructions", "setup-reference.md, The tree instructions"),
    "install": (
        "setup-reference.md, `harness install --apply`",
        "setup-reference.md, `harness install --apply`",
    ),
    "kaimon job": ("setup-reference.md, The jobs", "setup-reference.md, The jobs"),
    "update job": ("setup-reference.md, The jobs", "setup-reference.md, The jobs"),
    "autocommit": ("setup-reference.md, The jobs", "setup-reference.md, The jobs"),
    "token": ("setup-reference.md, The Kaimon token", "setup-reference.md, The Kaimon token"),
    "test": ("setup-linux.md, The check that it worked", "setup-macos.md, The check that it worked"),
}
# The answers of `systemctl is-active`; any other output is no answer.
STATES = {
    "active",
    "inactive",
    "failed",
    "activating",
    "deactivating",
    "reloading",
    "refreshing",
    "maintenance",
}
VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
SUMMARY = re.compile(r"(\d+) cases, (\d+) wrong")
WIDTH = 24

Result = namedtuple("Result", "status name detail")


def system():
    return platform.system()


def machine():
    return platform.machine()


def sandboxed():
    """Whether the subcommand runs in a session's sandbox."""
    return bool(os.environ.get(SANDBOX))


def environment():
    """The environment of each command: the caller's, without a `GIT_*` variable, which a git hook
    sets to the caller's repository."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run(command, timeout=None):
    """(exit status, stdout, stderr) of `command`, or None when its program is not found. A
    program that cannot be started gives 126 and the reason, and a run longer than `timeout`
    (default TIMEOUT) gives "timeout"."""
    timeout = timeout or TIMEOUT
    try:
        p = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=environment(),
            check=False,
        )
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
    return (
        f"{command} exits {r[0]}: {first(r[1] + r[2])}"
        if first(r[1] + r[2])
        else f"{command} exits {r[0]}, silent"
    )


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

    def __init__(self, args: argparse.Namespace):
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
            return Result(
                "SKIP", name, f"{detail}; the session's sandbox can refuse it: run in a plain terminal"
            )
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
                result = Result(
                    "WARN",
                    "system",
                    f"{where}: the setup page covers x86_64 and aarch64, and its "
                    "release files do not exist for this one",
                )
            return [result] + self.namespaces() + self.sandbox()
        if self.system == "Darwin":
            return [Result("PASS", "system", f"macOS {platform.mac_ver()[0]} {arch}")]
        return [Result("WARN", "system", f"{self.system} {arch}: no setup page covers this system")]

    def namespaces(self):
        """The two kernel settings for user namespaces; a missing key sets no limit."""
        out = []
        clone = read(KERNEL / "unprivileged_userns_clone")
        if clone is not None and clone.strip() == "0":
            out.append(
                self.fail(
                    "userns clone",
                    "0: the kernel refuses user namespaces to a user who is not root",
                    "machine",
                )
            )
        else:
            out.append(
                Result("PASS", "userns clone", clone.strip() if clone is not None else "absent: no limit")
            )
        armor = read(KERNEL / "apparmor_restrict_unprivileged_userns")
        if armor is not None and armor.strip() == "1":
            out.append(
                Result(
                    "WARN",
                    "apparmor userns",
                    "1: AppArmor refuses user namespaces to a program that it "
                    "does not allow; the sandbox check decides",
                )
            )
        else:
            out.append(
                Result("PASS", "apparmor userns", armor.strip() if armor is not None else "absent: no limit")
            )
        return out

    def sandbox(self):
        """The sandbox check of setup-reference.md on Linux, and socat beside it."""
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            out = [self.fail("sandbox", "bwrap not found", "sandbox")]
        else:
            r = run(
                [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--unshare-user", "--unshare-pid", "true"]
            )
            if r is not None and r[0] == 0:
                out = [Result("PASS", "sandbox", f"bwrap makes a sandbox ({bwrap})")]
            else:
                out = [self.refused("sandbox", said("bwrap", r), "sandbox")]
        socat = shutil.which("socat")
        return out + [
            Result("PASS", "socat", socat) if socat else self.fail("socat", "socat not found", "sandbox")
        ]

    # The tools.

    def tools(self):
        out = [self.tool(*t) for t in TOOLS]
        if self.system == "Darwin":
            out.append(self.iterm())
        return out + self.packages() + [self.python_environment()]

    def tool(self, name, command, flags, without):
        """A tool of TOOLS: missing, or a version flag that exits non-zero, is a FAIL for a required
        tool (`without` None) and a WARN for an optional one; a non-zero exit is a SKIP in a
        session's sandbox, which can refuse the flag. A version below its minimum is a FAIL, and
        output with no version a WARN. uv is found as `harness install --apply` finds it, on the
        PATH or in ~/.local/bin."""
        path = install.boot().find_uv() if command == "uv" else shutil.which(command)
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
        """The Julia packages of Project.toml, in the Manifest.toml of the scripts' environment; each
        a SKIP where `[setup]` does not choose the `julia` component, whose environment `harness
        install` then does not install."""
        names = sorted(tomllib.loads((REPO / "Project.toml").read_text())["deps"])
        if self.profile is not None and "julia" not in self.profile.setup.components:
            return [Result("SKIP", n, "[setup] does not choose the julia component") for n in names]
        manifest = install.JULIA_ENV / "Manifest.toml"
        try:
            deps = tomllib.loads(manifest.read_text()).get("deps")
        except FileNotFoundError:
            return [
                self.fail(n, f"no {manifest}: the environment is not instantiated", "install") for n in names
            ]
        except PermissionError as e:
            return [self.refused(n, f"cannot read {manifest}: {e.strerror}", "install") for n in names]
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            return [Result("WARN", n, f"cannot read {manifest}: {e}") for n in names]
        if not isinstance(deps, dict):
            return [Result("WARN", n, f"cannot read {manifest}: it has no table `deps`") for n in names]
        out = []
        for name in names:
            entry = deps.get(name)
            head = cast(object, entry[0] if isinstance(entry, list) and entry else None)
            fields = cast("dict[str, object]", head) if isinstance(head, dict) else {}
            version = fields.get("version")
            if version is None:
                out.append(self.fail(name, f"not in {manifest}", "install"))
            elif not isinstance(version, str) or VERSION.fullmatch(version) is None:
                out.append(Result("WARN", name, f"cannot read the version {version!r} in {manifest}"))
            else:
                out.append(self.minimum(name, version, version, "install"))
        return out

    def python_environment(self):
        """The Python environment that bin/harness runs on: a FAIL when its interpreter does not
        start or is below the minimum of Python, a SKIP in a session's sandbox for an interpreter
        that exits non-zero, a WARN when its stamp names another uv.lock, or another group than
        the profile's `develop`, else a PASS."""
        name, boot = "Python environment", install.boot()
        try:
            environment = boot.environment_path()
        except boot.Refusal as e:
            return self.fail(name, str(e), "install")
        python = boot.interpreter(environment)
        r = run([python, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"])
        if r is None:
            return self.fail(name, f"no interpreter at {python}: the environment is not made", "install")
        if r[0] != 0:
            return self.refused(name, said(python, r), "install")
        m = VERSION.search(r[1] + r[2])
        if m is None:
            return Result("WARN", name, f"cannot read a version from {python}: {first(r[1] + r[2])!r}")
        if not meets(numbers_of(m.group(0)), MINIMUMS["Python"]):
            return self.fail(name, f"{m.group(0)} ({python}), below {MINIMUMS['Python'][-1]}", "install")
        develop = self.profile.setup.develop if self.profile is not None else False
        if not boot.synced(environment, develop):
            return Result(
                "WARN",
                name,
                f"{environment} lags uv.lock {'with' if develop else 'without'} the dev "
                f"group: run `harness install --apply`",
            )
        return Result("PASS", name, f"{m.group(0)} ({environment})")

    # The profile and the install.

    def profile_checks(self):
        where = profile_module.location(self.args.profile)
        if self.profile is None:
            skip = "the profile does not load"
            return [
                self.fail("profile", self.profile_error, "profile"),
                Result("SKIP", "tree_agents", skip),
                self.opencode(),
                Result("SKIP", "autocommit_branch", skip),
            ]
        tree = self.profile.tree_agents
        if pathlib.Path(tree).is_dir():
            agents = Result("PASS", "tree_agents", tree)
        else:
            agents = self.fail("tree_agents", f"{tree} is not a directory", "tree")
        return [
            Result("PASS", "profile", f"{where} (home {self.profile.home})"),
            agents,
            self.opencode(),
            Result("PASS", "autocommit_branch", self.profile.autocommit_branch),
        ]

    def opencode(self):
        """OpenCode's configuration directory, which its layer needs: a SKIP where `[setup]` does
        not choose `opencode`, else a FAIL without it."""
        if self.profile is not None and "opencode" not in self.profile.setup.frontends:
            return Result("SKIP", "OpenCode directory", "[setup] does not choose opencode")
        directory = os.environ.get("OPENCODE_CONFIG_DIR") or str(self.home / ".config" / "opencode")
        if os.path.isdir(directory):
            return Result("PASS", "OpenCode directory", directory)
        return self.fail("OpenCode directory", f"{directory} is not a directory", "install")

    def install(self):
        """The dry run of `harness install`: its count, and a WARN for each warning; then the
        layers of the frontends that `[setup]` does not choose (`unchosen`)."""
        if self.profile is None:
            return [Result("SKIP", "install", "the profile does not load")]
        options = [
            o
            for flag, value in (("--profile", self.args.profile), ("--models", self.args.models))
            if value
            for o in (flag, value)
        ]
        r = run(HARNESS + options + ["install"], INSTALL_TIMEOUT)
        # The program of HARNESS is this interpreter, which exists: `run` gives no None.
        code, out, err = cast("tuple[int | str, str, str]", r)
        count = re.search(r"^(\d+) change\(s\) to make\.$", out, re.M)
        if code == 0 and count and count.group(1) == "0":
            result = Result("PASS", "install", "0 change(s) to make")
        elif code == 1 and count:
            result = self.fail("install", f"{count.group(1)} change(s) to make", "install")
        else:
            result = self.fail("install", f"the dry run exits {code}: {last(err) or last(out)}", "install")
        warnings = re.findall(r"^WARNING: (.*)$", out, re.M)
        return (
            [result]
            + [Result("WARN", f"install warning {n}", w.strip()) for n, w in enumerate(warnings, 1)]
            + self.unchosen(self.profile)
        )

    def unchosen(self, profile: profile_module.Profile) -> list[Result]:
        """A WARN for each frontend that `[setup]` of `profile`, the loaded profile, does not
        choose and whose layer is on disk: one file or more that its plan would install exists at
        its destination. OpenCode, oh-my-pi and Antigravity are planned alone, as `harness install`
        plans them; the Claude Code layer's files are the Claude Code adapter's `copies`, its
        settings.json and its stamp, which need no read below ~/.claude. OpenCode without its
        directory has no layer on disk and is not planned. A plan that refuses is a WARN that names
        the frontend and the refusal. The lines of a plan are not printed, and nothing is written
        or removed."""
        args = argparse.Namespace(
            profile=self.args.profile, models=self.args.models, force=False, apply=False
        )
        out: list[Result] = []
        for name in frontends.FRONTENDS:
            if name in profile.setup.frontends:
                continue
            if name == "opencode" and not frontends.adapter(name).destination().is_dir():
                continue
            ctx = types.SimpleNamespace(
                args=args,
                profile=profile,
                models=profile_module.models_path(args),
                agents=sources.AGENTS,
                plans={},
            )
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    if name == "claude":
                        root = pathlib.Path.home() / ".claude"
                        made = cast("types.SimpleNamespace", frontends.adapter(name).copies(ctx))
                        destinations = [root / "settings.json", root / install.STAMP]
                        destinations += [f[0] for f in cast("list[tuple[pathlib.Path, ...]]", made.files)]
                    else:
                        frontends.planned(ctx, (name,))
                        plan = cast("types.SimpleNamespace", ctx.plans[name])
                        destinations = [f[0] for f in cast("list[tuple[pathlib.Path, ...]]", plan.files)]
            except HarnessError as e:
                out.append(
                    Result(
                        "WARN",
                        f"{name} layer",
                        f"[setup] does not choose {name}, and its plan refuses, so whether its layer "
                        f"is installed is not known: {e}",
                    )
                )
                continue
            found = sum(1 for dst in destinations if dst.exists())
            if found:
                out.append(
                    Result(
                        "WARN",
                        f"{name} layer",
                        f"{found} file(s) of its layer are installed, and [setup] does not choose "
                        f"{name}: harness install leaves them; remove them by hand, or choose {name}",
                    )
                )
        return out

    # The jobs.

    def jobs(self):
        kaimon = self.home / ".julia" / "bin" / "kaimon"
        installed = os.path.isfile(kaimon) and os.access(kaimon, os.X_OK)
        out = [
            Result("PASS", "Kaimon", str(kaimon))
            if installed
            else Result(
                "WARN",
                "Kaimon",
                f"{kaimon} is not an executable file: the agents have no Julia session, and "
                "the update job stops",
            )
        ]
        if self.linux:
            out.append(self.linger())
            ask = self.systemd()
        elif self.system != "Darwin":
            return out
        elif self.profile is None:
            skip = "the profile, which names launchd_prefix, does not load"
            return (
                out
                + [
                    Result("SKIP", name, skip)
                    for name in ("kaimon job", "julia-update job", "autocommit job", "~/.claude repository")
                ]
                + [self.token(installed)]
            )
        else:
            ask = self.launchd(self.profile.launchd_prefix)
        for name, job, topic in (
            ("kaimon job", "kaimon", "kaimon job"),
            ("julia-update job", "julia-update", "update job"),
        ):
            if not installed:
                out.append(Result("SKIP", name, "Kaimon is not installed"))
                continue
            answer, detail = ask(job)
            out.append(
                Result("PASS", name, detail)
                if answer == "yes"
                else self.refused(name, detail, topic)
                if answer == "none"
                else self.fail(name, detail, topic)
            )
        answer, detail = ask("claude-autocommit")
        if answer == "yes":
            out += [Result("PASS", "autocommit job", detail), self.repository()]
        elif answer == "no":
            out += [
                Result("SKIP", "autocommit job", f"{detail}: the job is not enabled"),
                Result("SKIP", "~/.claude repository", "the autocommit job is not enabled"),
            ]
        else:
            out += [
                self.refused("autocommit job", detail, "autocommit")
                if answer == "none"
                else self.fail("autocommit job", detail, "autocommit"),
                Result("SKIP", "~/.claude repository", "cannot tell whether the autocommit job is enabled"),
            ]
        return out + [self.token(installed)]

    # The `ask(job)` of a service manager gives (answer, detail) for the job `kaimon`,
    # `julia-update` or `claude-autocommit`: answer "yes" when the job runs or is loaded, "no" when
    # it does not, "missing" when the manager's command is not found, and "none" when the command
    # gives no answer.

    def systemd(self):
        """The status query of the systemd user units: `is-active` of kaimon.service, and the list
        of the timers for the other two jobs, which it reads once."""
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

    def launchd(self, prefix: str) -> Callable[[str], tuple[str, str]]:
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
            return self.fail(
                "~/.claude repository",
                f"{claude} is inside the repository {top}, not the top of its own",
                "autocommit",
            )
        r = run([git, "-C", str(claude), "remote", "get-url", "origin"])
        if r is None or r[0] != 0:
            return self.fail("~/.claude repository", f"{claude} has no remote origin", "autocommit")
        return Result("PASS", "~/.claude repository", f"{claude}, with an origin")

    def token(self, kaimon):
        """The token file of the Kaimon entry of OpenCode, oh-my-pi and Antigravity: its existence,
        mode and size, never its content. Antigravity is installed when ~/.gemini is a directory, as
        its adapter decides."""
        if not kaimon:
            return Result("SKIP", "Kaimon token", "Kaimon is not installed")
        if (
            shutil.which("opencode") is None
            and shutil.which("omp") is None
            and not (self.home / ".gemini").is_dir()
        ):
            return Result(
                "SKIP",
                "Kaimon token",
                "neither OpenCode, oh-my-pi nor Antigravity is installed, and only they read it",
            )
        path = self.home / ".config" / "kaimon" / "auth-token"
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
            return [
                Result("SKIP", "harness test", "run with --full"),
                Result("SKIP", "Revise", "run with --full"),
            ]
        # The program of HARNESS is this interpreter, which exists: `run` gives no None.
        code, out, err = cast("tuple[int | str, str, str]", run([*HARNESS, "test"], TEST_TIMEOUT))
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
        return [
            test,
            Result(
                "WARN",
                "Revise",
                f"julia -e 'using Revise' exits {r[0] if r else 127}: "
                f"{last(r[2]) or last(r[1]) if r else ''}",
            ),
        ]


def numbers_of(version: str):
    """The three integers of the first version in `version`."""
    # Each caller passes a text that VERSION has matched.
    return numbers(cast("re.Match[str]", VERSION.search(version)).group(0))


def read(path):
    """The text of `path`, or None when it does not exist or cannot be read."""
    try:
        return pathlib.Path(path).read_text()
    except OSError, UnicodeDecodeError:
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
# exit status)]}. The macOS lines are recorded from the tools on a Mac set up by the steps of
# setup-reference.md, but for actionlint, whose line is the form of its releases, and launchctl,
# whose lines are written from its known form: in a session's sandbox it gives no answer. The
# Linux versions are those of a machine with Ubuntu 26.04 set up by the steps of
# setup-reference.md, each in its tool's form: the
# lines of gh, shellcheck and rsync are the form of their upstream releases, and those of
# systemctl, loginctl and bwrap are written from their known form around the answers that the
# machine gave, such as `Linger=no` and `active`. The Linux line of uv is written: the version of
# the release that bin/harness fetches, without the build note that follows it.
SHELLCHECK = (
    "ShellCheck - shell script analysis tool\nversion: 0.11.0\nlicense: GNU General Public License, "
    "version 3\nwebsite: https://www.shellcheck.net\n"
)
SYSTEMD_TIMERS = (
    "NEXT                            LEFT LAST                              PASSED UNIT                    ACTIVATES\n"
    "Wed 2026-10-21 04:30:00 CEST      9h -                                      - julia-update.timer      "
    "julia-update.service\n"
    "Tue 2026-10-20 19:12:13 CEST 13min Tue 2026-10-20 18:57:13 CEST 1min 2s ago claude-autocommit.timer "
    "claude-autocommit.service\n\n2 timers listed.\nPass --all to see loaded but inactive timers, too.\n"
)
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
    "uv": [("--version", "uv 0.13.5\n", "", 0)],
    "gh": [
        (
            "--version",
            "gh version 2.46.0 (2024-03-01)\nhttps://github.com/cli/cli/releases/tag/v2.46.0\n",
            "",
            0,
        )
    ],
    "node": [("--version", "v22.22.1\n", "", 0)],
    "actionlint": [
        (
            "--version",
            "1.7.12\ninstalled by downloading from release page\n"
            "built with go1.26.1 compiler for linux/amd64\n",
            "",
            0,
        )
    ],
    "rsync": [("--version", "rsync  version 3.4.1  protocol version 32\n", "", 0)],
    "julia": [("--version", "julia version 1.13.1\n", "", 0), ("-e using Revise", "", "", 0)],
    "juliaup": [("--version", "Juliaup 1.22.7\n", "", 0)],
    "claude": [("--version", "2.1.304 (Claude Code)\n", "", 0)],
    "opencode": [("--version", "opencode v2.1.1\n", "", 0)],
    "jq": [("--version", "jq-1.8.1\n", "", 0)],
    "bwrap": [("--ro-bind / / --dev /dev --unshare-user --unshare-pid true", "", "", 0)],
    "socat": [("*", "", "", 0)],
    "loginctl": [("show-user * -p Linger", "Linger=yes\n", "", 0)],
    "systemctl": [
        ("--user is-active kaimon.service", "active\n", "", 0),
        ("--user list-timers --no-pager", SYSTEMD_TIMERS, "", 0),
    ],
}
LAUNCHCTL = (
    '{\n\t"LimitLoadToSessionType" = "Aqua";\n\t"Label" = "org.example.{job}";\n\t"OnDemand" = false;\n'
    '\t"LastExitStatus" = 0;\n\t"PID" = 4242;\n\t"Program" = "/Users/me/.local/bin/{job}";\n'
    '\t"ProgramArguments" = (\n\t\t"/Users/me/.local/bin/{job}";\n\t);\n};\n'
)
MACOS = COMMON | {
    "python3": [("--version", "Python 3.14.8\n", "", 0)],
    "uv": [("--version", "uv 0.13.5 (Homebrew 2026-10-22 aarch64-apple-darwin)\n", "", 0)],
    "gh": [
        (
            "--version",
            "gh version 2.102.0 (2026-09-30)\nhttps://github.com/cli/cli/releases/tag/v2.102.0\n",
            "",
            0,
        )
    ],
    "node": [("--version", "v26.12.0\n", "", 0)],
    "actionlint": [
        (
            "--version",
            "1.7.12\ninstalled by downloading from release page\n"
            "built with go1.26.1 compiler for darwin/arm64\n",
            "",
            0,
        )
    ],
    "rsync": [("--version", "rsync  version 3.5.1  protocol version 33\n", "", 0)],
    "julia": [("--version", "julia version 1.13.2\n", "", 0), ("-e using Revise", "", "", 0)],
    "fatou": [("--version", "fatou 0.23.0\n", "", 0)],
    "juliaup": [("--version", "Juliaup 1.18.9\n", "", 0)],
    "claude": [("--version", "2.1.303 (Claude Code)\n", "", 0)],
    "opencode": [("--version", "opencode v2.1.0\n", "", 0)],
    "rtk": [("--version", "rtk 1.0.1\n", "", 0)],
    "jq": [("--version", "jq-1.7.1-apple\n", "", 0)],
    "launchctl": [
        (f"list org.example.{job}", LAUNCHCTL.replace("{job}", job), "", 0)
        for job in ("kaimon", "julia-update", "claude-autocommit")
    ],
}
# The dry run of `harness install` and `harness test`, as their lines end.
INSTALL_OUT = (
    "julia/Project.toml                 already identical\n"
    "\nWARNING: ~/.config/kaimon/auth-token does not exist.\n"
    "         Create it (mode 600, the token alone).\n"
    "\n0 change(s) to make.\n"
)
HARNESS_STUB = [
    ("--profile * install", INSTALL_OUT, "", 0),
    ("test", "ok   sweep: a case\n\n1861 cases, 0 wrong\n", "", 0),
]
PACKAGES = {
    "ExplicitImports": "1.15.0",
    "JSON": "1.11.0",
    "JuliaFormatter": "2.14.0",
    "JuliaSyntax": "1.0.2",
    "TestEnv": "1.103.7",
    "YAML": "0.4.17",
}
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
GIT_VERSION = {"Linux": "git version 2.53.0\n", "Darwin": "git version 2.54.0 (Apple Git-157)\n"}


def stub(path, cases):
    """An executable shell script at `path` that answers its arguments, "$*", with the first case
    of `cases`, [(pattern, stdout, stderr, exit status)], whose pattern matches; `*` in a pattern
    matches anything, as in a shell `case`. Arguments that no case matches exit 99."""
    lines = ["#!/bin/sh", 'case "$*" in']
    for pattern, out, err, code in cases:
        glob = "*".join(shlex.quote(part) if part else "" for part in pattern.split("*"))
        lines.append(
            f"  {glob}) printf '%s' {shlex.quote(out)}; printf '%s' {shlex.quote(err)} >&2; exit {code} ;;"
        )
    lines += ['  *) echo "stub: no case for $*" >&2; exit 99 ;;', "esac", ""]
    path.write_text("\n".join(lines))
    path.chmod(0o755)


def stubs(directory, system_name):
    """The stubs of `system_name` in `directory`, and a `git` that prints its version as the
    system's git does and passes every other call to the real git."""
    for name, cases in (LINUX if system_name == "Linux" else MACOS).items():
        stub(directory / name, cases)
    version = GIT_VERSION[system_name]
    # The cases run where git is on the PATH.
    git = cast(str, shutil.which("git"))
    (directory / "git").write_text(
        f'#!/bin/sh\n[ "$*" = --version ] && {{ printf %s {shlex.quote(version)}; '
        f'exit 0; }}\nexec {shlex.quote(git)} "$@"\n'
    )
    (directory / "git").chmod(0o755)


def manifest(versions):
    """A Manifest.toml in the form of Julia 1.13, with `versions`, {package: version}."""
    head = (
        '# This file is machine-generated - editing it directly is not advised\n\njulia_version = "1.13.2"\n'
        'manifest_format = "2.1"\nproject_hash = "94acdf3174e6a47bf3ed8d1b53e835f5db8784a4"\n'
    )
    return head + "".join(
        f'\n[[deps.{name}]]\ndeps = ["Dates"]\nuuid = "00000000-0000-0000-0000-000000000000"\n'
        f'version = "{version}"\n'
        for name, version in versions.items()
    )


class Fixture:
    """A scratch HOME one level below `root`, with every step of the setup page done, and a
    directory of stub commands that print what each tool prints on `system`; `results` runs the
    checks of some sections with both."""

    # A patch that a case sets on its fixture and enters around `results`.
    patch: contextlib.AbstractContextManager[object]

    def __init__(self, root: pathlib.Path, system_name: str, claude: pathlib.Path):
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
        self.token = self.home / ".config" / "kaimon" / "auth-token"
        self.token.parent.mkdir(parents=True)
        fsutil.write_private(self.token, TOKEN.encode())
        shutil.copytree(claude, self.home / ".claude", symlinks=True)
        self.julia.mkdir()
        (self.julia / "Manifest.toml").write_text(manifest(PACKAGES))
        # The Python environment, synced without the dev group, with a stub of its interpreter.
        self.python = root / "python-env"
        (self.python / "bin").mkdir(parents=True)
        stub(self.python / "bin" / "python", [("*", "3.14.8\n", "", 0)])
        (self.python / install.boot().STAMP).write_text(install.boot().stamp_text(False))
        self.kernel.mkdir()
        (self.kernel / "unprivileged_userns_clone").write_text("1\n")
        self.os_release.write_text('PRETTY_NAME="Ubuntu 26.04.1 LTS"\nNAME="Ubuntu"\nVERSION_ID="26.04"\n')
        (self.iterm / "Contents").mkdir(parents=True)
        (self.iterm / "Contents" / "Info.plist").write_bytes(
            plistlib.dumps({"CFBundleShortVersionString": "3.7.3"})
        )
        self.bin.mkdir()
        stubs(self.bin, system_name)
        self.harness = self.bin / "harness-stub"
        stub(self.harness, HARNESS_STUB)

    @contextlib.contextmanager
    def patched(self, full=False, sandbox=False, arch=None, only=None, models=None, extra=None):
        """The arguments of a run on this fixture, inside a context with its HOME, its PATH, its
        system and its files in place of the machine's, and stdout in `self.out`; `only` names
        the tools of TOOLS that the run checks, else all, and `extra` adds variables."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in (SANDBOX, "OPENCODE_CONFIG_DIR", "RESEARCH_HARNESS_PROFILE", "RESEARCH_HARNESS_MODELS")
            and not k.startswith("GIT_")
        }
        env.update(
            GIT_ENV,
            HOME=str(self.home),
            PATH=str(self.bin),
            RESEARCH_HARNESS_PYTHON=str(self.python),
            **({SANDBOX: "1"} if sandbox else {}),
        )
        env.update(extra or {})
        self.out = io.StringIO()
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch(f"{__name__}.system", lambda: self.system),
            mock.patch(
                f"{__name__}.machine", lambda: arch or ("x86_64" if self.system == "Linux" else "arm64")
            ),
            mock.patch(f"{__name__}.KERNEL", self.kernel),
            mock.patch(f"{__name__}.OS_RELEASE", self.os_release),
            mock.patch(f"{__name__}.ITERM", self.iterm),
            mock.patch(f"{__name__}.HARNESS", [str(self.harness)]),
            mock.patch.object(install, "JULIA_ENV", self.julia),
            contextlib.redirect_stdout(self.out),
            mock.patch(f"{__name__}.TOOLS", [t for t in TOOLS if only is None or t[0] in only]),
        ):
            yield types.SimpleNamespace(profile=str(self.profile), models=models, full=full)

    def results(self, *sections: str, **options: Any) -> tuple[dict[str, Result], str]:
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
        check(
            MINIMUMS.get(tool, ()) == floors,
            f"the minimum of {tool}: {MINIMUMS.get(tool, ())} here, {floors} in dependencies.md",
        )
    check(
        set(MINIMUMS) <= set(found),
        f"every tool of MINIMUMS is a row of dependencies.md: {sorted(set(MINIMUMS) - set(found))} are not",
    )
    names = {name for name, *_ in TOOLS} | set(PACKAGES) | {"Kaimon", "iTerm2", "chezmoi", "Antigravity"}
    check(
        set(found) == names,
        f"the checks cover each tool of dependencies.md: missing {sorted(set(found) - names)}, "
        f"extra {sorted(names - set(found))}",
    )


def level_two(text: str) -> list[str]:
    """The level-2 headings of the Markdown `text`, outside code fences."""
    found: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(line[3:].strip())
    return found


def fix_problems(fix: dict[str, tuple[str, str]], pages: pathlib.Path) -> list[str]:
    """Each section of `fix`, `<page>, <heading>`, that is no level-2 heading of `pages`/<page>, a
    missing page included, as `<topic>: <section>`."""
    problems: list[str] = []
    for topic, pair in fix.items():
        for where in dict.fromkeys(pair):
            page, _, heading = where.partition(", ")
            path = pages / page
            if heading not in (level_two(path.read_text(encoding="utf-8")) if path.is_file() else []):
                problems.append(f"{topic}: {where}")
    return problems


def fix_cases(check: Callable[[bool, str], None], root: pathlib.Path) -> None:
    """The rules of `fix_problems` on a fixture in `root`, then each section of FIX against
    docs/src/."""
    check(
        level_two("## A\n```\n## B\n```\n### C\n## D \n") == ["A", "D"],
        "a heading in a code fence and a level-3 heading are no level-2 headings",
    )
    pages = root / "fix-pages"
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "p.md").write_text("# P\n\n## A\n\n```\n## B\n```\n", encoding="utf-8")
    found = fix_problems(
        {"x": ("p.md, A", "p.md, B"), "y": ("q.md, A", "p.md, A"), "z": ("p.md, C", "p.md, C")}, pages
    )
    check(
        found == ["x: p.md, B", "y: q.md, A", "z: p.md, C"],
        "a section in a code fence and a section of a missing page are problems of FIX, and a section "
        f"that both systems name is one: {found}",
    )
    problems = fix_problems(FIX, REPO / "docs" / "src")
    check(not problems, f"each section of FIX is a level-2 heading of its page: not {problems}")


def page_cases(check: Callable[[bool, str], None], root: pathlib.Path) -> None:
    """The cases that read the pages of docs/src/: the minimums and the sections of FIX."""
    minimum_cases(check)
    fix_cases(check, root)


def below(floor):
    """The last release before `floor`, as a version string."""
    a, b, c = (int(n) for n in (floor + ".0").split(".")[:3])
    return f"{a}.{b}.{c - 1}" if c else f"{a}.{b - 1}.99" if b else f"{a - 1}.99.99"


def status_cases(check, root, system_name):
    """Each status of each check on a fixture of `system_name`."""
    linux = system_name == "Linux"
    claude = root / "claude-template"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(claude)],
        check=True,
        capture_output=True,
        env=environment() | GIT_ENV,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(claude), "remote", "add", "origin", "https://user:url-secret@example.org/m.git"],
        check=True,
        capture_output=True,
        env=environment() | GIT_ENV,
        timeout=60,
    )
    n = 0

    def fixture():
        nonlocal n
        n += 1
        return Fixture(root / f"case{n}", system_name, claude)

    def expect(label, got, want, text="", darwin=not linux):
        """Each check of `want`, {name: status}, has its status in `got`; a FAIL ends with a fix of
        FIX for its system, macOS when `darwin`, and nothing prints the token or the origin's URL."""
        wrong = {
            name: (got[name].status if name in got else None)
            for name, status in want.items()
            if name not in got or got[name].status != status
        }
        sections = {pair[1] or pair[0] if darwin else pair[0] for pair in FIX.values()}
        fails = [
            r
            for r in got.values()
            if r.status == "FAIL" and not any(r.detail.endswith(f"(fix: {s})") for s in sections)
        ]
        leaked = TOKEN in text or "url-secret" in text
        check(
            not wrong and not fails and not leaked,
            f"{system_name}: {label} -> {want}"
            + (f"; got {wrong}" if wrong else "")
            + (f"; a FAIL with no fix of this system: {fails}" if fails else "")
            + ("; the output holds a secret" if leaked else ""),
        )

    def case(label, want, change=lambda f: None, sections=(), **options):
        f = fixture()
        change(f)
        got, text = f.results(*sections, **options)
        expect(label, got, want, text, darwin=f.system == "Darwin")
        return got, text

    # The whole run on a machine with every step done: no FAIL, and each line in the format.
    got, text = case(
        "every step done",
        dict.fromkeys(
            (
                "system",
                "Python",
                "Python environment",
                "Kaimon",
                "profile",
                "install",
                "kaimon job",
                "julia-update job",
                "autocommit job",
                "~/.claude repository",
                "Kaimon token",
            ),
            "PASS",
        )
        | {"install warning 1": "WARN", "harness test": "SKIP", "Revise": "SKIP"},
    )
    lines = text.splitlines()
    form = re.compile(r"(PASS|WARN|FAIL|SKIP)  \S.{%d,}  \S.*" % (WIDTH - 1))
    check(
        all(form.fullmatch(line) for line in lines) and len(lines) == len(got),
        f"{system_name}: each of the {len(lines)} lines is a status, a name and a detail: "
        f"{[line for line in lines if not form.fullmatch(line)]}",
    )
    check(
        not [r for r in got.values() if r.status == "FAIL"],
        f"{system_name}: every step done gives no FAIL -> {[r for r in got.values() if r.status == 'FAIL']}",
    )

    # The machine.
    if linux:
        case(
            "an architecture the page does not cover",
            {"system": "WARN", "sandbox": "PASS"},
            sections=("machine",),
            arch="riscv64",
        )
        case("aarch64", {"system": "PASS"}, sections=("machine",), arch="aarch64")
        case(
            "unprivileged_userns_clone = 0",
            {"userns clone": "FAIL"},
            lambda f: (f.kernel / "unprivileged_userns_clone").write_text("0\n"),
            ("machine",),
        )
        case(
            "no unprivileged_userns_clone",
            {"userns clone": "PASS"},
            lambda f: (f.kernel / "unprivileged_userns_clone").unlink(),
            ("machine",),
        )
        case(
            "apparmor_restrict_unprivileged_userns = 1",
            {"apparmor userns": "WARN"},
            lambda f: (f.kernel / "apparmor_restrict_unprivileged_userns").write_text("1\n"),
            ("machine",),
        )
        case(
            "apparmor_restrict_unprivileged_userns = 0",
            {"apparmor userns": "PASS"},
            lambda f: (f.kernel / "apparmor_restrict_unprivileged_userns").write_text("0\n"),
            ("machine",),
        )
        refused_bwrap = (
            "--ro-bind / / --dev /dev --unshare-user --unshare-pid true",
            "",
            "bwrap: setting up uid map: Permission denied\n",
            1,
        )
        case("bwrap refused", {"sandbox": "FAIL"}, lambda f: f.tool("bwrap", refused_bwrap), ("machine",))
        case(
            "bwrap refused in a session's sandbox",
            {"sandbox": "SKIP"},
            lambda f: f.tool("bwrap", refused_bwrap),
            ("machine",),
            sandbox=True,
        )
        case("no bwrap", {"sandbox": "FAIL"}, lambda f: (f.bin / "bwrap").unlink(), ("machine",))
        case("no socat", {"socat": "FAIL"}, lambda f: (f.bin / "socat").unlink(), ("machine",))
    else:
        case("macOS", {"system": "PASS"}, sections=("machine",))
        got, _ = case(
            "another system",
            {"system": "WARN"},
            sections=("machine", "jobs"),
            change=lambda f: setattr(f, "system", "FreeBSD"),
        )
        check(
            set(got) == {"system", "Kaimon"},
            f"another system has no machine-specific check and no job: {sorted(got)}",
        )

        def other(f):
            f.system = "FreeBSD"
            (f.bin / "julia").unlink()

        got, _ = case("another system without julia", {"Julia": "FAIL"}, other, ("tools",), only=("Julia",))
        detail = cast("str", got["Julia"].detail)
        check(
            detail.endswith("(fix: setup-reference.md, The packages)"),
            f"another system names the section of FIX that fixes the tools -> {detail!r}",
        )

        def other_test(f: Fixture) -> None:
            f.system = "FreeBSD"
            stub(f.harness, [("test", "BAD  a case\n\n1861 cases, 1 wrong\n", "", 1)])

        got, _ = case(
            "another system with a wrong case", {"harness test": "FAIL"}, other_test, ("full",), full=True
        )
        detail = cast("str", got["harness test"].detail)
        check(
            detail.endswith("(fix: setup-linux.md, The check that it worked)"),
            f"another system names the Linux entry of a pair of FIX that differs -> {detail!r}",
        )

    # The tools: each required one missing, each optional one missing, each minimum and the
    # release before it, and output with no version.
    stubs = LINUX if linux else MACOS
    printed = (LINUX if linux else MACOS) | {"git": [("--version", GIT_VERSION[system_name], "", 0)]}
    for name, command, flags, without in TOOLS:
        status = "FAIL" if without is None else "WARN"
        one = {"only": (name,)}
        case(f"no {command}", {name: status}, lambda f, c=command: (f.bin / c).unlink(), ("tools",), **one)
        case(
            f"{command} prints no version",
            {name: "WARN"},
            lambda f, c=command, a=flags: f.tool(
                c, (" ".join(a), "command-line tool, no number here\n", "", 0)
            ),
            ("tools",),
            **one,
        )
        # A version flag that exits non-zero: FAIL for a required tool, WARN for an optional one,
        # and SKIP in a session's sandbox, where gh prints its version, a warning and exits 1.
        exits = lambda f, c=command, a=flags: f.tool(
            c, (" ".join(a), printed[c][0][1], "warning: failed to load config\n", 1)
        )
        got, _ = case(f"{command} exits 1", {name: status}, exits, ("tools",), **one)
        check(
            f"{' '.join([command, *flags])} exits 1" in got[name].detail,
            f"{system_name}: {command} exits 1 names the exit -> {got[name].detail!r}",
        )
        got, _ = case(
            f"{command} exits 1 in a session's sandbox",
            {name: "SKIP"},
            exits,
            ("tools",),
            sandbox=True,
            **one,
        )
        check(
            "sandbox" in got[name].detail,
            f"{system_name}: the SKIP names the sandbox -> {got[name].detail!r}",
        )
        case(
            f"{command} exits 127",
            {name: status},
            lambda f, c=command, a=flags: f.tool(
                c,
                (
                    " ".join(a),
                    "",
                    "error while loading shared libraries: libfoo.so.1: cannot open shared object file\n",
                    127,
                ),
            ),
            ("tools",),
            **one,
        )
        case(
            f"{command} prints no version in a session's sandbox",
            {name: "WARN"},
            lambda f, c=command, a=flags: f.tool(
                c, (" ".join(a), "command-line tool, no number here\n", "", 0)
            ),
            ("tools",),
            sandbox=True,
            **one,
        )
        for floor in MINIMUMS.get(name, ()):
            out = printed[command][0][1]
            # The stub of each tool prints a version.
            at = cast("re.Match[str]", VERSION.search(out)).group(0)
            for version, want in ((floor, "PASS"), (below(floor), "FAIL")):
                text = out.replace(at, version, 1)
                case(
                    f"{command} at {version}, minimum {' or '.join(MINIMUMS[name])}",
                    {name: want},
                    lambda f, c=command, a=flags, t=text: f.tool(c, (" ".join(a), t, "", 0)),
                    ("tools",),
                    **one,
                )
    # A working environment runs without uv, so a missing uv is a WARN; the loop above derives
    # the status from the row, and this case states it.
    case("no uv", {"uv": "WARN"}, lambda f: (f.bin / "uv").unlink(), ("tools",), only=("uv",))

    # uv in ~/.local/bin, where the bootstrap fetches it, and not on the PATH: the lookup of the sync.
    def local_uv(f):
        (f.bin / "uv").unlink()
        (f.home / ".local" / "bin").mkdir(parents=True, exist_ok=True)
        stub(f.home / ".local" / "bin" / "uv", [("--version", "uv 0.13.5\n", "", 0)])

    got, _ = case("uv in ~/.local/bin only", {"uv": "PASS"}, local_uv, ("tools",), only=("uv",))
    check(
        ".local/bin/uv" in got["uv"].detail,
        f"{system_name}: the uv line names ~/.local/bin/uv -> {got['uv'].detail!r}",
    )
    for version, want in (("21.7.3", "FAIL"), ("20.18.0", "PASS"), ("18.20.4", "FAIL"), ("23.0.0", "PASS")):
        case(
            f"node at {version}",
            {"Node.js": want},
            lambda f, v=version: f.tool("node", ("--version", f"v{v}\n", "", 0)),
            ("tools",),
            only=("Node.js",),
        )
    case(
        "fatou 0.22 against the minimum 0.22.0",
        {"fatou": "PASS"},
        lambda f: f.tool("fatou", ("--version", "fatou 0.22\n", "", 0)),
        ("tools",),
        only=("fatou",),
    )
    case(
        "a version of gitleaks with a v",
        {"gitleaks": "FAIL"},
        lambda f: f.tool("gitleaks", ("version", "v8.16.0\n", "", 0)),
        ("tools",),
        only=("gitleaks",),
    )

    def garbage(f):
        (f.bin / "jq").write_bytes(b"\x00\x01\x02 not a program\n")

    got, _ = case("a jq that cannot start", {"jq": "WARN"}, garbage, ("tools",), only=("jq",))
    check(
        "cannot start" in got["jq"].detail,
        f"{system_name}: the line names the reason -> {got['jq'].detail!r}",
    )
    with mock.patch(f"{__name__}.TIMEOUT", 1):
        got, _ = case(
            "a jq that does not answer",
            {"jq": "WARN"},
            lambda f: (f.bin / "jq").write_text("#!/bin/sh\nexec /bin/sleep 5\n"),
            ("tools",),
            only=("jq",),
        )
    check(
        "no answer after 1 s" in got["jq"].detail,
        f"{system_name}: the line names the time -> {got['jq'].detail!r}",
    )
    # The cases below check no tool of TOOLS.
    none = {"only": ()}
    if not linux:
        case("no iTerm2", {"iTerm2": "WARN"}, lambda f: shutil.rmtree(f.iterm), ("tools",), **none)
        case(
            "an Info.plist of iTerm2 that is no plist",
            {"iTerm2": "WARN"},
            lambda f: (f.iterm / "Contents" / "Info.plist").write_text("not a plist\n"),
            ("tools",),
            **none,
        )
    else:
        got, _ = case("iTerm2 on Linux", {}, sections=("tools",), **none)
        check("iTerm2" not in got, f"Linux: no iTerm2 line -> {got.get('iTerm2')}")
    case("every Julia package", dict.fromkeys(PACKAGES, "PASS"), sections=("tools",), **none)
    for name, floor in ((n, MINIMUMS[n][0]) for n in PACKAGES):
        for version, want in ((floor, "PASS"), (below(floor), "FAIL")):
            case(
                f"{name} {version} in the manifest",
                {name: want},
                lambda f, n=name, v=version: (f.julia / "Manifest.toml").write_text(
                    manifest(PACKAGES | {n: v})
                ),
                ("tools",),
                **none,
            )
    case(
        "JSON not in the manifest",
        {"JSON": "FAIL", "YAML": "PASS"},
        lambda f: (f.julia / "Manifest.toml").write_text(
            manifest({k: v for k, v in PACKAGES.items() if k != "JSON"})
        ),
        ("tools",),
        **none,
    )
    case(
        "no manifest",
        dict.fromkeys(PACKAGES, "FAIL"),
        lambda f: (f.julia / "Manifest.toml").unlink(),
        ("tools",),
        **none,
    )
    case(
        "a manifest that is not TOML",
        dict.fromkeys(PACKAGES, "WARN"),
        lambda f: (f.julia / "Manifest.toml").write_text("[[deps.JSON\n"),
        ("tools",),
        **none,
    )
    case(
        "a version in the manifest that is no version",
        {"JSON": "WARN"},
        lambda f: (f.julia / "Manifest.toml").write_text(manifest(PACKAGES | {"JSON": "latest"})),
        ("tools",),
        **none,
    )
    case(
        "a manifest with no table deps",
        dict.fromkeys(PACKAGES, "WARN"),
        lambda f: (f.julia / "Manifest.toml").write_text('julia_version = "1.13.2"\n'),
        ("tools",),
        **none,
    )
    if os.geteuid() != 0:  # root reads a file of mode 000
        for sandbox, want in ((False, "FAIL"), (True, "SKIP")):
            case(
                f"a manifest that cannot be read, sandbox {sandbox}",
                dict.fromkeys(PACKAGES, want),
                lambda f: (f.julia / "Manifest.toml").chmod(0),
                ("tools",),
                sandbox=sandbox,
                **none,
            )

    # The Python environment: an interpreter that starts at or above the minimum and the stamp of
    # this uv.lock pass; no interpreter, one that exits non-zero, one below 3.14 and a relative path
    # fail; a stamp of another lock or group warns.
    python = lambda f: f.python / "bin" / "python"
    stamp = lambda f: f.python / install.boot().STAMP
    env_name = "Python environment"
    case("a synced Python environment", {env_name: "PASS"}, sections=("tools",), **none)
    case("no Python environment", {env_name: "FAIL"}, lambda f: shutil.rmtree(f.python), ("tools",), **none)
    case(
        "an interpreter of the environment that is a broken link",
        {env_name: "FAIL"},
        lambda f: (python(f).unlink(), python(f).symlink_to(f.python / "gone")),
        ("tools",),
        **none,
    )
    exits = lambda f: stub(python(f), [("*", "", "dyld: Library not loaded\n", 6)])
    case("an interpreter of the environment that exits 6", {env_name: "FAIL"}, exits, ("tools",), **none)
    got, _ = case(
        "an interpreter of the environment that exits 6 in a session's sandbox",
        {env_name: "SKIP"},
        exits,
        ("tools",),
        sandbox=True,
        **none,
    )
    check(
        "sandbox" in got[env_name].detail,
        f"{system_name}: the SKIP names the sandbox -> {got[env_name].detail!r}",
    )
    for version, want in (("3.13.9", "FAIL"), ("3.14.0", "PASS"), ("3.15.1", "PASS")):
        case(
            f"an interpreter of the environment at {version}",
            {env_name: want},
            lambda f, v=version: stub(python(f), [("*", f"{v}\n", "", 0)]),
            ("tools",),
            **none,
        )
    case(
        "an interpreter of the environment that prints no version",
        {env_name: "WARN"},
        lambda f: stub(python(f), [("*", "no number\n", "", 0)]),
        ("tools",),
        **none,
    )
    case(
        "a stamp of another uv.lock",
        {env_name: "WARN"},
        lambda f: stamp(f).write_text("0" * 64 + " no-dev\n"),
        ("tools",),
        **none,
    )
    case("no stamp", {env_name: "WARN"}, lambda f: stamp(f).unlink(), ("tools",), **none)
    # The profile of a fixture ends with its [setup] table, so an appended `develop` is its key.
    case(
        "develop = true and a stamp without the dev group",
        {env_name: "WARN"},
        lambda f: f.profile.write_text(f.profile.read_text() + "develop = true\n"),
        ("tools",),
        **none,
    )
    case(
        "develop = true and a stamp with the dev group",
        {env_name: "PASS"},
        lambda f: (
            f.profile.write_text(f.profile.read_text() + "develop = true\n"),
            stamp(f).write_text(install.boot().stamp_text(True)),
        ),
        ("tools",),
        **none,
    )
    got, _ = case(
        "a relative $RESEARCH_HARNESS_PYTHON",
        {env_name: "FAIL"},
        sections=("tools",),
        extra={"RESEARCH_HARNESS_PYTHON": "relative/env"},
        **none,
    )
    check(
        "relative/env" in got[env_name].detail and "not an absolute path" in got[env_name].detail,
        f"{system_name}: the line names the relative path, which is not absolute -> {got[env_name].detail!r}",
    )

    # The profile.
    for label, text in (
        ("no profile", None),
        ("a profile that is not TOML", "home = \n"),
        ("a relative home", 'home = "h"\n' + profile_module.DUMMY.read_text()),
    ):

        def change(f, text=text):
            f.profile.unlink() if text is None else f.profile.write_text(text)

        case(
            label,
            {
                "profile": "FAIL",
                "tree_agents": "SKIP",
                "OpenCode directory": "PASS",
                "autocommit_branch": "SKIP",
                "install": "SKIP",
            }
            | (
                {"kaimon job": "SKIP", "julia-update job": "SKIP", "autocommit job": "SKIP"}
                if not linux
                else {}
            ),
            change,
            ("profile_checks", "install", "jobs"),
        )
    case(
        "no tree_agents directory",
        {"tree_agents": "FAIL"},
        lambda f: shutil.rmtree(f.home / "Research" / "Environment" / "Agents"),
        ("profile_checks",),
    )
    case(
        "no tree_agents key",
        {"profile": "FAIL", "tree_agents": "SKIP"},
        lambda f: f.profile.write_text(re.sub(r"^tree_agents = .*$", "", f.profile.read_text(), flags=re.M)),
        ("profile_checks",),
    )
    with mock.patch.object(profile_module, "load", side_effect=PermissionError(1, "Operation not permitted")):
        got, _ = case(
            "a profile that cannot be read",
            {"profile": "FAIL", "install": "SKIP"},
            sections=("profile_checks", "install"),
        )
    check(
        "cannot read the profile" in got["profile"].detail,
        f"{system_name}: the line says why -> {got['profile'].detail!r}",
    )
    case(
        "no OpenCode directory",
        {"OpenCode directory": "FAIL"},
        lambda f: shutil.rmtree(f.home / ".config" / "opencode"),
        ("profile_checks",),
    )
    elsewhere = cast(pathlib.Path, root / "opencode-elsewhere")
    elsewhere.mkdir(parents=True)
    case(
        "$OPENCODE_CONFIG_DIR, and no ~/.config/opencode",
        {"OpenCode directory": "PASS"},
        lambda f: shutil.rmtree(f.home / ".config" / "opencode"),
        ("profile_checks",),
        extra={"OPENCODE_CONFIG_DIR": str(elsewhere)},
    )
    case(
        "an $OPENCODE_CONFIG_DIR that does not exist, and ~/.config/opencode",
        {"OpenCode directory": "FAIL"},
        sections=("profile_checks",),
        extra={"OPENCODE_CONFIG_DIR": str(root / "no-such-directory")},
    )

    def branch_first(f: Fixture) -> None:
        """The key goes first: the fixture's profile ends with its [setup] table."""
        f.profile.write_text('autocommit_branch = "memory/case"\n' + f.profile.read_text())

    got, _ = case(
        "autocommit_branch",
        {"autocommit_branch": "PASS"},
        branch_first,
        ("profile_checks",),
    )
    check(
        got["autocommit_branch"].detail == "memory/case",
        f"{system_name}: the autocommit_branch line prints the value -> {got['autocommit_branch'].detail!r}",
    )

    # The install.
    case(
        "an install with changes",
        {"install": "FAIL"},
        lambda f: stub(
            f.harness,
            [("*install", "julia/Project.toml                 REPLACE\n\n5 change(s) to make.\n", "", 1)],
        ),
        ("install",),
    )
    models = root / "models.toml"
    case(
        "--models",
        {"install": "PASS"},
        lambda f: stub(f.harness, [("--profile * --models * install", INSTALL_OUT, "", 0)]),
        ("install",),
        models=str(models),
    )
    case(
        "an install that exits 2",
        {"install": "FAIL"},
        lambda f: stub(f.harness, [("*install", "", "harness install: no profile at /x/profile.toml\n", 2)]),
        ("install",),
    )
    three = INSTALL_OUT.replace(
        "\n0 change",
        "\nWARNING: ~/.omp/agent/.env lacks PI_CONFIG_FILES.\n"
        "\nWARNING: the checkout ~/Research/Harness is 3 commit(s) behind its "
        "origin/main.\n         Run `git pull` there, then install again.\n"
        "\n0 change",
    )
    got, _ = case(
        "three install warnings",
        {
            "install": "PASS",
            "install warning 1": "WARN",
            "install warning 2": "WARN",
            "install warning 3": "WARN",
        },
        lambda f: stub(f.harness, [("*install", three, "", 0)]),
        ("install",),
    )
    check(
        "3 commit(s) behind" in got["install warning 3"].detail,
        f"{system_name}: an install warning's line is its first line -> {got['install warning 3'].detail!r}",
    )

    # The jobs.
    case(
        "no Kaimon",
        {
            "Kaimon": "WARN",
            "kaimon job": "SKIP",
            "julia-update job": "SKIP",
            "Kaimon token": "SKIP",
            "autocommit job": "PASS",
        },
        lambda f: f.kaimon.unlink(),
        ("jobs",),
    )
    case(
        "a Kaimon that is not executable",
        {"Kaimon": "WARN", "kaimon job": "SKIP"},
        lambda f: f.kaimon.chmod(0o644),
        ("jobs",),
    )
    case("no OpenCode", {"Kaimon token": "PASS"}, lambda f: (f.bin / "opencode").unlink(), ("jobs",))
    case("no oh-my-pi", {"Kaimon token": "PASS"}, lambda f: (f.bin / "omp").unlink(), ("jobs",))
    case(
        "neither OpenCode nor oh-my-pi",
        {"Kaimon token": "SKIP"},
        lambda f: ((f.bin / "opencode").unlink(), (f.bin / "omp").unlink()),
        ("jobs",),
    )
    # Antigravity is installed when ~/.gemini is a directory, as its adapter decides.
    case(
        "Antigravity alone",
        {"Kaimon token": "PASS"},
        lambda f: ((f.bin / "opencode").unlink(), (f.bin / "omp").unlink(), (f.home / ".gemini").mkdir()),
        ("jobs",),
    )
    case(
        "Antigravity alone, no token file",
        {"Kaimon token": "FAIL"},
        lambda f: (
            (f.bin / "opencode").unlink(),
            (f.bin / "omp").unlink(),
            (f.home / ".gemini").mkdir(),
            f.token.unlink(),
        ),
        ("jobs",),
    )
    case(
        "a ~/.gemini that is a file",
        {"Kaimon token": "SKIP"},
        lambda f: (
            (f.bin / "opencode").unlink(),
            (f.bin / "omp").unlink(),
            (f.home / ".gemini").write_text("x"),
        ),
        ("jobs",),
    )
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
        f.patch = mock.patch(
            f"{__name__}.os.stat",
            lambda p, *a, **k: (
                (_ for _ in ()).throw(PermissionError(1, "Operation not permitted"))
                if str(p).endswith("auth-token")
                else real(p, *a, **k)
            ),
        )

    for sandbox, want in ((True, "SKIP"), (False, "FAIL")):
        f = fixture()
        denied(f)
        with f.patch:
            got, text = f.results("jobs", sandbox=sandbox)
        expect(f"a token whose stat is denied, sandbox {sandbox}", got, {"Kaimon token": want}, text)
    case(
        "~/.claude not a repository",
        {"~/.claude repository": "FAIL"},
        lambda f: shutil.rmtree(f.home / ".claude" / ".git"),
        ("jobs",),
    )
    case(
        "~/.claude without an origin",
        {"~/.claude repository": "FAIL"},
        lambda f: subprocess.run(
            ["git", "-C", str(f.home / ".claude"), "remote", "remove", "origin"],
            check=True,
            env=environment() | GIT_ENV,
            timeout=60,
        ),
        ("jobs",),
    )

    def inside(f):
        """Make ~/.claude a plain directory in a repository of the home, which has an origin."""
        shutil.rmtree(f.home / ".claude" / ".git")
        for command in (
            ["init", "-q", str(f.home)],
            ["-C", str(f.home), "remote", "add", "origin", "https://example.org/h.git"],
        ):
            program = shutil.which("git") or "git"
            subprocess.run([program, *command], check=True, env=environment() | GIT_ENV, timeout=60)

    got, _ = case(
        "~/.claude inside the home's repository", {"~/.claude repository": "FAIL"}, inside, ("jobs",)
    )
    check(
        "inside the repository" in got["~/.claude repository"].detail,
        f"{system_name}: the line names the repository around ~/.claude -> {got['~/.claude repository'].detail!r}",
    )
    case("no git", {"~/.claude repository": "FAIL"}, lambda f: (f.bin / "git").unlink(), ("jobs",))
    # As inside a git hook, which exports GIT_DIR: the check still reads ~/.claude.
    case(
        "~/.claude not a repository, with GIT_DIR of another one",
        {"~/.claude repository": "FAIL"},
        lambda f: shutil.rmtree(f.home / ".claude" / ".git"),
        ("jobs",),
        extra={"GIT_DIR": str(claude / ".git")},
    )
    if linux:
        case(
            "Linger=no",
            {"linger": "FAIL"},
            lambda f: f.tool("loginctl", ("show-user * -p Linger", "Linger=no\n", "", 0)),
            ("jobs",),
        )
        no_user = (
            "show-user * -p Linger",
            "",
            "Failed to get user: User ID 1000 is not logged in or lingering\n",
            1,
        )
        case(
            "loginctl without an answer", {"linger": "FAIL"}, lambda f: f.tool("loginctl", no_user), ("jobs",)
        )
        case(
            "loginctl without an answer in a session's sandbox",
            {"linger": "SKIP"},
            lambda f: f.tool("loginctl", no_user),
            ("jobs",),
            sandbox=True,
        )
        case("no loginctl", {"linger": "FAIL"}, lambda f: (f.bin / "loginctl").unlink(), ("jobs",))
        timers = ("--user list-timers --no-pager", SYSTEMD_TIMERS, "", 0)
        for state in ("inactive", "failed"):
            case(
                f"kaimon.service {state}",
                {"kaimon job": "FAIL"},
                lambda f, s=state: f.tool(
                    "systemctl", ("--user is-active kaimon.service", f"{s}\n", "", 3), timers
                ),
                ("jobs",),
            )
        no_bus = [
            ("--user is-active kaimon.service", "", NO_BUS, 1),
            ("--user list-timers --no-pager", "", NO_BUS, 1),
        ]
        case(
            "systemctl without a bus",
            {
                "kaimon job": "FAIL",
                "julia-update job": "FAIL",
                "autocommit job": "FAIL",
                "~/.claude repository": "SKIP",
            },
            lambda f: f.tool("systemctl", *no_bus),
            ("jobs",),
        )
        case(
            "systemctl without a bus in a session's sandbox",
            {
                "kaimon job": "SKIP",
                "julia-update job": "SKIP",
                "autocommit job": "SKIP",
                "~/.claude repository": "SKIP",
            },
            lambda f: f.tool("systemctl", *no_bus),
            ("jobs",),
            sandbox=True,
        )
        only = "\n".join(line for line in SYSTEMD_TIMERS.splitlines() if "julia-update" not in line) + "\n"
        case(
            "no julia-update.timer",
            {"julia-update job": "FAIL", "autocommit job": "PASS"},
            lambda f: f.tool(
                "systemctl",
                ("--user is-active kaimon.service", "active\n", "", 0),
                ("--user list-timers --no-pager", only, "", 0),
            ),
            ("jobs",),
        )
        only = (
            "\n".join(line for line in SYSTEMD_TIMERS.splitlines() if "claude-autocommit" not in line) + "\n"
        )
        case(
            "no claude-autocommit.timer",
            {"autocommit job": "SKIP", "~/.claude repository": "SKIP", "julia-update job": "PASS"},
            lambda f: f.tool(
                "systemctl",
                ("--user is-active kaimon.service", "active\n", "", 0),
                ("--user list-timers --no-pager", only, "", 0),
            ),
            ("jobs",),
        )
        case(
            "no claude-autocommit.timer and no ~/.claude repository",
            {"~/.claude repository": "SKIP"},
            lambda f: (
                f.tool(
                    "systemctl",
                    ("--user is-active kaimon.service", "active\n", "", 0),
                    ("--user list-timers --no-pager", only, "", 0),
                ),
                shutil.rmtree(f.home / ".claude" / ".git"),
            ),
            ("jobs",),
        )
        case(
            "no systemctl",
            {"kaimon job": "FAIL", "julia-update job": "FAIL", "autocommit job": "FAIL"},
            lambda f: (f.bin / "systemctl").unlink(),
            ("jobs",),
        )
    else:

        def launchctl(*missing, error=None):
            def change(f):
                cases = []
                for job in ("kaimon", "julia-update", "claude-autocommit"):
                    if error is not None:
                        cases.append((f"list org.example.{job}", "", error, 1))
                    elif job in missing:
                        cases.append(
                            (
                                f"list org.example.{job}",
                                "",
                                f'Could not find service "org.example.{job}" in domain for port\n',
                                113,
                            )
                        )
                    else:
                        cases.append((f"list org.example.{job}", LAUNCHCTL.replace("{job}", job), "", 0))
                f.tool("launchctl", *cases)

            return change

        case(
            "kaimon not loaded",
            {"kaimon job": "FAIL", "julia-update job": "PASS"},
            launchctl("kaimon"),
            ("jobs",),
        )
        case(
            "julia-update not loaded",
            {"julia-update job": "FAIL", "kaimon job": "PASS"},
            launchctl("julia-update"),
            ("jobs",),
        )
        case(
            "claude-autocommit not loaded",
            {"autocommit job": "SKIP", "~/.claude repository": "SKIP"},
            launchctl("claude-autocommit"),
            ("jobs",),
        )
        case(
            "claude-autocommit not loaded and no ~/.claude repository",
            {"~/.claude repository": "SKIP"},
            lambda f: (launchctl("claude-autocommit")(f), shutil.rmtree(f.home / ".claude" / ".git")),
            ("jobs",),
        )
        # In a session's sandbox, `launchctl list <label>` exits 1 and prints nothing.
        case(
            "launchctl without an answer",
            {
                "kaimon job": "FAIL",
                "julia-update job": "FAIL",
                "autocommit job": "FAIL",
                "~/.claude repository": "SKIP",
            },
            launchctl(error=""),
            ("jobs",),
        )
        case(
            "launchctl without an answer in a session's sandbox",
            {
                "kaimon job": "SKIP",
                "julia-update job": "SKIP",
                "autocommit job": "SKIP",
                "~/.claude repository": "SKIP",
            },
            launchctl(error=""),
            ("jobs",),
            sandbox=True,
        )
        case(
            "no launchctl",
            {"kaimon job": "FAIL", "julia-update job": "FAIL", "autocommit job": "FAIL"},
            lambda f: (f.bin / "launchctl").unlink(),
            ("jobs",),
        )

    # The slow checks.
    case("--full", {"harness test": "PASS", "Revise": "PASS"}, sections=("full",), full=True)
    case(
        "--full with a wrong case",
        {"harness test": "FAIL"},
        lambda f: stub(f.harness, [("test", "BAD  a case\n\n1861 cases, 1 wrong\n", "", 1)]),
        ("full",),
        full=True,
    )
    case(
        "--full with no summary line",
        {"harness test": "FAIL"},
        lambda f: stub(f.harness, [("test", "", "Traceback (most recent call last):\n", 1)]),
        ("full",),
        full=True,
    )
    case(
        "--full without Revise",
        {"Revise": "WARN"},
        lambda f: f.tool(
            "julia",
            ("--version", "julia version 1.13.2\n", "", 0),
            ("-e using Revise", "", "ERROR: ArgumentError: Package Revise not found in current path.\n", 1),
        ),
        ("full",),
        full=True,
    )
    case(
        "--full without julia", {"Revise": "FAIL"}, lambda f: (f.bin / "julia").unlink(), ("full",), full=True
    )

    # Nothing on the PATH: each check reports what is missing, and none raises.
    f = fixture()
    for path in f.bin.iterdir():
        if path != f.harness:
            path.unlink()
    try:
        got, text = f.results()
        raised = None
    # The case reports what a check raised instead of stopping the suite.
    except (OSError, ValueError, LookupError, TypeError, AttributeError) as e:
        got, text, raised = {}, "", repr(e)
    missing = [name for name, command, _, without in TOOLS if without is None]
    check(
        raised is None
        and all(got[name].status == "FAIL" and "not found" in got[name].detail for name in missing),
        f"{system_name}: with nothing on the PATH, each required tool is a FAIL that names it, and no check raises "
        f"-> {raised or [got.get(n) for n in missing if got[n].status != 'FAIL']}",
    )
    setup_cases(
        cast("Callable[[bool, str], object]", check),
        cast(pathlib.Path, root) / "setup",
        cast(str, system_name),
        cast(pathlib.Path, claude),
    )


def setup_cases(
    check: Callable[[bool, str], object], root: pathlib.Path, system_name: str, claude: pathlib.Path
) -> None:
    """The checks that the profile's `[setup]` changes, each on a fixture of `system_name` below
    `root` whose ~/.claude is a copy of `claude`: the Julia packages are SKIP without the `julia`
    component, and the OpenCode directory without `opencode`; a frontend that `[setup]` does not
    choose is a WARN that names `[setup]` and the frontend where one file or more of its layer is
    on disk, also the Claude Code layer whose settings.json its plan refuses, and where its plan
    refuses a symbolic link among the sources, naming the link; and nothing where its directory
    holds no such file, where it is OpenCode without its directory, or where it is chosen. The run
    changes no file of the fixture. Without a profile that loads, the Julia packages are
    checked."""
    # A file of each layer as its plan installs it, relative to the fixture's HOME. oh-my-pi's
    # directory is $PI_CODING_AGENT_DIR, set to .omp/agent below the HOME.
    layer_files = {
        "opencode": ".config/opencode/AGENTS.md",
        "omp": ".omp/agent/AGENTS.md",
        "antigravity": ".gemini/config/GEMINI.md",
    }
    n = 0

    def checked_on(
        frontends_toml: str,
        components_toml: str,
        files: tuple[str, ...] = (),
        dirs: tuple[str, ...] = (),
        changes: tuple[Callable[[pathlib.Path], object], ...] = (),
    ) -> tuple[dict[str, str], dict[str, str], bool]:
        """The status and the detail of each Result by name, of the sections `tools`, `profile_checks`
        and `install`, on a fresh fixture whose [setup] chooses `frontends_toml` and
        `components_toml`, with each of `changes` called on its HOME, then `files` written and
        `dirs` made below it; and whether the run changed a file below the HOME."""
        nonlocal n
        n += 1
        f = Fixture(root / f"case{n}", system_name, claude)
        text = f.profile.read_text()
        f.profile.write_text(
            text[: text.index("\n[setup]\n")]
            + f"\n[setup]\nfrontends = {frontends_toml}\ncomponents = {components_toml}\n"
        )
        home = f.home
        for change in changes:
            change(home)
        for d in dirs:
            (home / d).mkdir(parents=True, exist_ok=True)
        for name in files:
            (home / name).parent.mkdir(parents=True, exist_ok=True)
            (home / name).write_text("a file of a layer\n")
        before = {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}
        results, _ = f.results(
            "tools",
            "profile_checks",
            "install",
            only=(),
            extra={"PI_CODING_AGENT_DIR": str(home / ".omp" / "agent")},
        )
        after = {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}
        statuses = {name: cast(str, r.status) for name, r in results.items()}
        details = {name: cast(str, r.detail) for name, r in results.items()}
        return statuses, details, before != after

    def layers(statuses: dict[str, str], details: dict[str, str]) -> dict[str, str]:
        """Each `<frontend> layer` Result that names `[setup]`: its frontend and its status."""
        return {
            name.removesuffix(" layer"): status
            for name, status in statuses.items()
            if name.endswith(" layer") and "[setup]" in details[name]
        }

    def no_opencode(home: pathlib.Path) -> None:
        shutil.rmtree(home / ".config" / "opencode")

    def linked(home: pathlib.Path) -> None:
        """A symbolic link among the tree instructions' agents, which every layer's plan refuses."""
        (home / "Research" / "Environment" / "Agents" / "linked.md").symlink_to(
            home / ".config" / "research-harness" / "profile.toml"
        )

    every = '["claude", "opencode", "omp", "antigravity"]'
    statuses, details, changed = checked_on(every, '["rtk"]')
    packages = {name: statuses.get(name) for name in PACKAGES}
    check(
        all(s == "SKIP" for s in packages.values())
        and all("julia" in details[name] for name in PACKAGES)
        and statuses.get("OpenCode directory") == "PASS",
        f"{system_name}: [setup] without the julia component: each Julia package is SKIP, naming julia -> "
        f"{packages}, OpenCode directory {statuses.get('OpenCode directory')}",
    )
    # No OpenCode directory: no layer, and no WARN.
    statuses, details, changed = checked_on('["claude"]', '["julia"]', changes=(no_opencode,))
    check(
        statuses.get("OpenCode directory") == "SKIP"
        and "opencode" in details.get("OpenCode directory", "")
        and all(statuses.get(name) == "PASS" for name in PACKAGES)
        and not layers(statuses, details),
        f"{system_name}: [setup] without opencode: the OpenCode directory is SKIP, and the Julia "
        f"packages pass -> {statuses.get('OpenCode directory')}, {details.get('OpenCode directory')!r}",
    )
    statuses, details, changed = checked_on('["claude"]', '["julia"]', files=tuple(layer_files.values()))
    found = layers(statuses, details)
    check(
        found == dict.fromkeys(layer_files, "WARN")
        and all(name in details[f"{name} layer"] for name in layer_files)
        and not changed,
        f"{system_name}: claude alone, and a file of each other layer on disk: one WARN each, naming "
        f"[setup] and the frontend, none for claude, and no file changed -> {found}, changed {changed}",
    )
    statuses, details, changed = checked_on('["claude"]', '["julia"]', dirs=(".omp/agent", ".gemini/config"))
    found = layers(statuses, details)
    check(
        not found and not changed,
        f"{system_name}: claude alone, and the other frontends' directories hold no file of a layer: "
        f"no WARN -> {found}",
    )
    statuses, details, changed = checked_on(every, '["julia"]', files=tuple(layer_files.values()))
    found = layers(statuses, details)
    check(
        not found and not changed,
        f"{system_name}: every frontend chosen, and a file of each layer on disk: no WARN -> {found}",
    )
    # An unchosen Claude Code layer whose settings.json is not JSON, which its plan refuses: its
    # files, the settings and the stamp among them, are found without that read, and counted. A
    # plan that refuses for another cause than OpenCode's missing directory, a symbolic link among
    # the sources that every layer copies: a WARN for each unchosen frontend that names it and the
    # refusal, whatever is on disk; none for OpenCode without its directory.
    for frontends_toml, files, changes, want, said, label in (
        (
            '["opencode"]',
            (".claude/settings.json", ".claude/CLAUDE.md"),
            (),
            ("claude",),
            "2 file(s)",
            "claude",
        ),
        (
            '["opencode"]',
            (".claude/settings.json",),
            (),
            ("claude",),
            "1 file(s)",
            "claude, only settings.json",
        ),
        (
            '["opencode"]',
            (f".claude/{install.STAMP}",),
            (),
            ("claude",),
            "1 file(s)",
            "claude, only the stamp",
        ),
        ('["claude"]', (), (linked,), tuple(layer_files), "linked.md", "a link among the sources"),
        (
            '["claude"]',
            (),
            (linked, no_opencode),
            ("omp", "antigravity"),
            "linked.md",
            "the link, no OpenCode",
        ),
    ):
        statuses, details, changed = checked_on(frontends_toml, '["julia"]', files, changes=changes)
        found = layers(statuses, details)
        check(
            found == dict.fromkeys(want, "WARN")
            and all(name in details[f"{name} layer"] and said in details[f"{name} layer"] for name in want)
            and not changed,
            f"{system_name}: {frontends_toml}, {files} on disk, {label}: a WARN for each of "
            f"{want}, naming [setup], the frontend and {said!r}, and no file changed -> {found}, "
            f"{[details.get(f'{name} layer') for name in want]}, changed {changed}",
        )
    # A profile that does not load chooses nothing to skip: the Julia packages are checked.
    f = Fixture(root / "no-profile", system_name, claude)
    f.profile.unlink()
    results, _ = f.results("tools", only=())
    packages = {name: cast(str, results[name].status) if name in results else None for name in PACKAGES}
    check(
        all(s == "PASS" for s in packages.values()),
        f"{system_name}: no profile: each Julia package is checked and passes -> {packages}",
    )


def exit_cases(check, root):
    """The exit status: 0 with PASS, WARN and SKIP lines only, 1 with a FAIL; and 2 on a usage
    error, in a process of its own."""
    claude = root / "claude-template"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(claude)],
        check=True,
        capture_output=True,
        env=environment() | GIT_ENV,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(claude), "remote", "add", "origin", "https://example.org/m.git"],
        check=True,
        capture_output=True,
        env=environment() | GIT_ENV,
        timeout=60,
    )
    this = system() if system() in ("Linux", "Darwin") else "Linux"
    for label, change, want in (
        ("only PASS, WARN and SKIP", lambda f: None, 0),
        ("one FAIL", lambda f: f.token.chmod(0o644), 1),
        (
            "one FAIL in the install",
            lambda f: stub(f.harness, [("*install", "\n1 change(s) to make.\n", "", 1)]),
            1,
        ),
    ):
        f = Fixture(root / label.replace(" ", "-").replace(",", ""), this, claude)
        change(f)
        with f.patched() as args:
            code = cmd_doctor(args)
        statuses = sorted({line[:4] for line in f.out.getvalue().splitlines()[:-2]})
        check(code == want, f"{label}: exit {code} -> {statuses}")
    for argv in (["doctor", "--bogus"], ["doctor", "extra"]):
        p = subprocess.run(HARNESS + argv, capture_output=True, text=True, check=False, timeout=60)
        check(
            p.returncode == 2 and "Traceback" not in p.stderr,
            f"harness {' '.join(argv)}: exit {p.returncode}",
        )


def process_cases(check: Callable[[object, str], object], root: pathlib.Path):
    """`harness doctor` in a process of its own on the contract sweep's fixture, with the stubs of
    this system on the PATH and the real dry run of `harness install`: it exits 0 or 1, prints no
    traceback and changes no file below the fixture."""
    from . import sweep

    if system() not in ("Linux", "Darwin"):
        return
    home = root / "home"
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in sweep.UNSET and k != SANDBOX and not k.startswith("GIT_")
    }
    env.update(
        sweep.GIT,
        HOME=str(home),
        RESEARCH_ROOT=str(home / "Research"),
        RESEARCH_HARNESS_JULIA=str(root / "julia-env"),
    )
    sweep.make_fixture(home, env)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    stubs(bin_dir, system())
    env["PATH"] = str(bin_dir)
    before = sweep.digest(root)
    p = subprocess.run(
        [*HARNESS, "doctor"], capture_output=True, text=True, env=env, cwd=root, timeout=300, check=False
    )
    changed = sweep.digest(root) != before
    install_line = next(
        (line for line in p.stdout.splitlines() if line.startswith(("PASS  install ", "FAIL  install "))),
        None,
    )
    check(
        p.returncode in (0, 1)
        and "Traceback" not in p.stdout + p.stderr
        and not changed
        and install_line is not None
        and "change(s) to make" in install_line,
        f"harness doctor on the sweep's fixture: exit {p.returncode}, a file changed {changed}, the install line "
        f"{install_line!r}" + (f": {p.stderr.strip()[-300:]!r}" if p.returncode not in (0, 1) else ""),
    )


# The groups of cases, each a function of `check` and a scratch directory; `harness test` runs each
# group as the part `doctor:<group>`.
GROUPS = {
    "minimum": page_cases,
    "linux": lambda check, root: status_cases(check, root / "Linux", "Linux"),
    "darwin": lambda check, root: status_cases(check, root / "Darwin", "Darwin"),
    "exit": lambda check, root: exit_cases(check, root / "exit"),
    "process": lambda check, root: process_cases(check, root / "process"),
}


def selftest(groups):
    """The cases of the groups `groups` of GROUPS: the minimums against dependencies.md and the
    sections of FIX against the setup pages, each status of each check on a fixture of Linux and
    of macOS, the exit status, and a run in a process of its own: (number of cases, number
    wrong)."""
    total = wrong = 0

    def check(ok: object, label: str) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  doctor: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-doctor-") as tmp:
        for name in groups:
            GROUPS[name](check, pathlib.Path(tmp))
    return total, wrong


def register(sub):
    p = sub.add_parser(
        "doctor",
        help="check the setup of this machine, read-only; a session's sandbox makes some checks "
        "SKIP, so run it in a plain terminal",
        description="Check this machine's setup, read-only: one line per check, PASS, WARN, FAIL or "
        "SKIP; exit 1 when one fails. A session's sandbox refuses some of the commands, "
        "and those checks are SKIP: run it in a plain terminal for the real verdict.",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="also run `harness test` and `julia -e 'using Revise'`, which take minutes",
    )
    p.set_defaults(run=cmd_doctor)
