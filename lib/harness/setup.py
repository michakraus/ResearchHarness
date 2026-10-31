"""`harness setup`: the tools, the frontends and the harness's own steps of a machine, in one run.

    harness setup              # ask in a terminal, show the plan, run it after y/N
    harness setup --yes        # read [setup] of the profile, ask nothing, run the plan
    harness setup --dry-run    # print every command of the plan, change nothing
    harness test setup         # the cases below

A machine needs Python 3.14, uv, git, the clone and, on macOS, Homebrew before it. In a terminal,
`setup` creates the profile from examples/profile.toml when there is none, asking only for the
keys of REQUIRED, the keys with no default, with the example's value as the answer to an empty
line; it asks for the frontends and the components from numbered lists, and for `develop`, y/N.
It then shows the plan and runs it after y/N; the first step of that plan writes the answers into
`[setup]` of the profile (`with_setup`), `develop` only where it is true. `--yes` reads `[setup]`,
or the defaults of a profile without it, asks nothing and never writes the profile; without a
profile it exits 2. Without a terminal on stdin and without `--yes` it exits 2 and names
`--yes`. `--dry-run`, alone or with `--yes`, prints the plan and changes nothing. Missing model
tables are copied from examples/models.toml. `with_setup` writes only a table under its own
header line, and checks its edit with tomllib: a `setup` of the profile that it cannot write in
place, such as an inline table or dotted keys, exits 2 and names the table to write.

The plan (`plan`), in this order: the directories that `harness install` needs (the tree
instructions, each `repository_roots` entry, and the OpenCode directory with `opencode`); the
packages; the pinned releases; the vendor installers; then `harness install --apply`,
`git config core.hooksPath .githooks` in the clone, `harness trust --apply`, the jobs with the
`jobs` component, the Kaimon token with the `julia` component, and `harness doctor`. A tool of
TOOLS belongs to every machine or to one component or frontend. A tool that is installed and meets
its minimum is skipped; a tool with no minimum is met by any version, and one whose version cannot
be read counts as below its minimum. On macOS a missing tool that Homebrew has goes into one
`brew install` line, and so does one below its minimum that Homebrew does not list as installed
(`brew list`); one that it lists goes into one `brew upgrade` line, and iTerm2 into
`brew install --cask`. On Ubuntu each package whose apt candidate meets the tool's minimum goes
into one `sudo apt-get install -y` line; an apt-cache that fails exits 2. Without sudo, or with
`sudo -n true` refused, that step prints the line for an administrator and the run stops there. A
tool that apt does not meet installs from its pinned release of setup/tools.toml (`load_pins`)
into ~/.local/bin, after a check of the archive's sha256; a mismatch installs nothing. Otherwise
the vendor's installer runs, where one runs unattended: the OpenCode installer only when
`opencode` is not on the PATH, with `--no-modify-path`, and the juliaup installer only when
`juliaup` is not on the PATH. Julia below its minimum runs `juliaup update`. After a Homebrew line
or `juliaup update` for a tool below its minimum, the tool's version is read again
(`rechecked`): one still below it fails the step, with the fix for Julia, the default channel of
juliaup, and otherwise with the path of the copy that comes first on the PATH. What runs no
installer is a line under "by hand". An unknown system, a Linux that is not Ubuntu and an unknown
architecture exit 2 and name it.

The run goes step by step. A failed step prints its output and exits 2; a second run plans again
and starts from the first step, and each step skips what is already done. After the last step
come the lines by hand, then `harness doctor`: its report ends the run, and the run exits with its
status, 1 when it reports a FAIL; any other status of doctor is a failed step. Every lookup and
every child process uses the PATH of the machine with the directories of EXTRA_PATH first, so that
a tool that a step installs there is found by the next step.
"""

import argparse
import contextlib
import dataclasses
import hashlib
import http.client
import http.server
import io
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Callable, Generator, Mapping, Sequence
from typing import IO, cast, override

from . import REPO, HarnessError, fmt, frontends, jsonio
from . import profile as profile_module
from .fsutil import Case, write_private

PINS = REPO / "setup" / "tools.toml"
MODELS = REPO / "examples" / "models.toml"
# Seconds: a version query, an apt-cache query and a download; and every command of a step.
TIMEOUT, INSTALL_TIMEOUT = 60, 3600
# The architectures of each system, as `platform.machine()` names them.
SYSTEMS = {"Darwin": ("arm64", "x86_64"), "Linux": ("x86_64", "aarch64")}
MACOS, LINUX = ("Darwin",), ("Linux",)
# The directories below the home directory where an installer puts its program.
EXTRA_PATH = (".local/bin", ".juliaup/bin", ".julia/bin", ".opencode/bin")
VERSION = re.compile(r"\d+(?:\.\d+)+")
CANDIDATE = re.compile(r"^\s*Candidate:\s*(\S+)", re.MULTILINE)
SHA256 = re.compile(r"[0-9a-f]{64}")
# The header of the `[setup]` table, and a key of it, bare or quoted.
HEADER = re.compile(r"""\s*\[\s*(["']?)setup\1\s*\]\s*(?:#.*)?""")
KEY = re.compile(r"""\s*(["']?)(frontends|components|develop)\1\s*=""")
# The one redirect that a download of a pinned release follows, as bin/harness's download does.
REDIRECT = ("https", "release-assets.githubusercontent.com")
DOCTOR = "harness doctor"
JOBS = ("kaimon", "julia-update", "claude-autocommit")
UNITS = (
    "kaimon.service",
    "julia-update.service",
    "julia-update.timer",
    "claude-autocommit.service",
    "claude-autocommit.timer",
)
ENABLED = ("kaimon.service", "julia-update.timer", "claude-autocommit.timer")

JULIAUP = "curl -fsSL https://install.julialang.org | sh -s -- --yes"
CLAUDE = "curl -fsSL https://claude.ai/install.sh | bash"
OPENCODE = "curl -fsSL https://opencode.ai/v2/install | bash -s -- --no-modify-path"
OMP = "curl -fsSL https://omp.sh/install | sh -s -- --binary"
FATOU = "curl --proto '=https' --tlsv1.2 -sSf https://fatou.dev/install | sh"
KAIMON = """julia -e 'using Pkg; Pkg.Apps.add("Kaimon")'"""

type Ask = Callable[[str], str]
# A step's action: None when it succeeds, else the text that says why it failed.
type Action = Callable[[], str | None]
# The action of `harness doctor`: its status, 0 or 1, or the text that says why the step failed.
type Doctor = Callable[[], int | str]


@dataclasses.dataclass(frozen=True, slots=True)
class Tool:
    """A tool that `setup` installs: `name` as dependencies.md and setup/tools.toml name it,
    `command` on the PATH (or `app` in the applications directory, or `marker` below the home
    directory), `need` the component or frontend that needs it ("" for every machine), `version`
    the arguments that print its version (none where any version meets it), the Homebrew `brew`
    formula or `cask`, the Ubuntu `apt` packages (the first one's candidate counts), the vendor's
    `installer` and the `upgrade` line below its minimum, the line that names the fix (`stuck`)
    when the tool is still below its minimum after that line, the tool whose installer brings it
    (`comes_with`), the `systems` it runs on, and the line that `by_hand` prints where nothing
    installs it."""

    name: str
    command: str = ""
    need: str = ""
    version: tuple[str, ...] = ()
    brew: str = ""
    cask: str = ""
    apt: tuple[str, ...] = ()
    installer: str = ""
    upgrade: str = ""
    stuck: str = ""
    comes_with: str = ""
    app: str = ""
    marker: str = ""
    systems: tuple[str, ...] = ("Darwin", "Linux")
    by_hand: str = ""


TOOLS = (
    Tool("git", "git", brew="git", apt=("git",)),
    Tool("gh", "gh", brew="gh", apt=("gh",)),
    Tool("Node.js", "node", version=("--version",), brew="node", apt=("nodejs", "npm")),
    Tool("shellcheck", "shellcheck", brew="shellcheck", apt=("shellcheck",)),
    Tool("actionlint", "actionlint", version=("--version",), brew="actionlint", apt=("actionlint",)),
    Tool("rsync", "rsync", brew="rsync", apt=("rsync",)),
    Tool("gitleaks", "gitleaks", version=("version",), brew="gitleaks", apt=("gitleaks",)),
    Tool("curl", "curl", apt=("curl",), systems=LINUX),
    Tool("bubblewrap", "bwrap", apt=("bubblewrap",), systems=LINUX),
    Tool("socat", "socat", apt=("socat",), systems=LINUX),
    Tool("lsof", "lsof", apt=("lsof",), systems=LINUX),
    Tool("juliaup", "juliaup", need="julia", installer=JULIAUP),
    Tool(
        "Julia",
        "julia",
        need="julia",
        version=("--version",),
        installer="juliaup add release",
        upgrade="juliaup update",
        stuck="juliaup update keeps the default channel of juliaup: run "
        "`juliaup add release && juliaup default release`, then harness setup again",
        comes_with="juliaup",
    ),
    Tool("fatou", "fatou", need="julia", version=("--version",), brew="jolars/tap/fatou", installer=FATOU),
    Tool("Kaimon", "kaimon", need="julia", installer=KAIMON),
    Tool("RTK", "rtk", need="rtk", brew="rtk"),
    Tool("jq", "jq", need="jq", brew="jq", apt=("jq",)),
    Tool(
        "iTerm2",
        need="iterm",
        cask="iterm2",
        app="iTerm.app",
        systems=MACOS,
        by_hand="iTerm2 runs on macOS only: nothing is installed for the component iterm",
    ),
    Tool("chezmoi", "chezmoi", need="dotfiles", brew="chezmoi", apt=("chezmoi",)),
    Tool("Claude Code", "claude", need="claude", installer=CLAUDE),
    Tool("OpenCode", "opencode", need="opencode", brew="anomalyco/tap/opencode-v2", installer=OPENCODE),
    Tool("oh-my-pi", "omp", need="omp", brew="can1357/tap/omp", installer=OMP),
    Tool(
        "Antigravity",
        need="antigravity",
        marker=".gemini",
        by_hand="install the Antigravity desktop app from https://antigravity.google/ and start it once",
    ),
)


@dataclasses.dataclass(frozen=True, slots=True)
class Release:
    """A pinned release of setup/tools.toml: the archive at `url`, with its `sha256`."""

    version: str
    url: str
    sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class Pins:
    """setup/tools.toml: the minimum of each tool, and its releases by `<system>-<architecture>`."""

    minimum: Mapping[str, tuple[str, ...]]
    releases: Mapping[str, Mapping[str, Release]]


@dataclasses.dataclass(frozen=True, slots=True)
class Machine:
    """The machine that `setup` plans for: `system` and `arch` as `platform` names them, the
    `distro` of /etc/os-release on Linux, the `home` directory, the environment `env` of every
    child process (its PATH that of every lookup), the harness `clone`, the command that runs
    `harness`, and the applications directory `apps`."""

    system: str
    arch: str
    distro: str
    home: pathlib.Path
    env: Mapping[str, str]
    clone: pathlib.Path
    harness: tuple[str, ...]
    apps: pathlib.Path

    def which(self, command: str) -> str | None:
        return shutil.which(command, path=self.env.get("PATH", ""))


@dataclasses.dataclass(frozen=True, slots=True)
class Options:
    """The options of one run: `yes`, `dry_run`, and the profile and model tables it uses."""

    yes: bool
    dry_run: bool
    profile: pathlib.Path
    models: pathlib.Path


@dataclasses.dataclass(frozen=True, slots=True)
class Step:
    """One step of the plan: the command line that it shows, and its action."""

    show: str
    action: Action


@dataclasses.dataclass(slots=True)
class Plan:
    """The steps in their order, the lines that the user does by hand, and `harness doctor`,
    which comes after both."""

    doctor: Doctor
    steps: list[Step] = dataclasses.field(default_factory=list[Step])
    by_hand: list[str] = dataclasses.field(default_factory=list[str])


# --------------------------------------------------------------------- the pinned releases ----


def load_pins(path: pathlib.Path = PINS) -> Pins:
    """setup/tools.toml at `path`. A file that is not TOML, a minimum that is not a list of
    versions, and a release without its version, an https `url` and a sha256 of 64 lowercase
    hexadecimal digits exit 2, naming the file and the key."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise HarnessError(f"{path} cannot be read: {e}") from None
    minimum: dict[str, tuple[str, ...]] = {}
    for name, value in table(data.get("minimum", {}), path, "minimum").items():
        items = cast("list[object]", value) if isinstance(value, list) else []
        versions = tuple(v for v in items if isinstance(v, str) and VERSION.fullmatch(v))
        if not versions or len(versions) != len(items):
            raise HarnessError(f"{path}: minimum.{name} is {value!r}, not a list of versions")
        minimum[name] = versions
    releases: dict[str, dict[str, Release]] = {}
    for name, value in table(data.get("release", {}), path, "release").items():
        tool = table(value, path, f"release.{name}")
        version = tool.get("version")
        if not isinstance(version, str):
            raise HarnessError(f"{path}: release.{name} has no version")
        releases[name] = {}
        for key, entry in tool.items():
            if key == "version":
                continue
            where = f"release.{name}.{key}"
            fields = table(entry, path, where)
            url, digest = fields.get("url"), fields.get("sha256")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise HarnessError(f"{path}: {where} has no https url")
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                raise HarnessError(f"{path}: {where} has no sha256 of 64 lowercase hexadecimal digits")
            releases[name][key] = Release(version, url, digest)
    return Pins(minimum, releases)


def table(value: object, path: pathlib.Path, where: str) -> dict[str, object]:
    """`value`, the TOML table `where` of the file at `path`; anything else exits 2."""
    if not isinstance(value, dict):
        raise HarnessError(f"{path}: {where} is not a table")
    return cast("dict[str, object]", value)


# ------------------------------------------------------------------------- the versions ----


def numbers(version: str) -> tuple[int, ...]:
    """The dotted `version` as integers, padded with zeros to three."""
    parts = tuple(int(n) for n in version.split("."))
    return parts + (0,) * (3 - len(parts))


def meets(version: str, minimums: Sequence[str]) -> bool:
    """Whether `version` is at or above the last of `minimums`, or at or above an earlier one of
    the same major release; with no minimums, any version meets them."""
    if not minimums:
        return True
    have, floors = numbers(version), [numbers(m) for m in minimums]
    return have >= floors[-1] or any(have[0] == f[0] and have >= f for f in floors[:-1])


def installed_version(machine: Machine, program: str, arguments: tuple[str, ...]) -> str | None:
    """The first dotted version in the output of `program arguments`, or None."""
    try:
        p = subprocess.run(
            [program, *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(machine.env),
            timeout=TIMEOUT,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    m = VERSION.search(p.stdout + p.stderr)
    return m.group(0) if m else None


def candidate(machine: Machine, package: str) -> str | None:
    """The version of the apt candidate of `package`, without its epoch and revision, or None
    when apt-cache knows no candidate. An apt-cache that is missing, cannot start, takes too long
    or exits non-zero exits 2, naming it and its error."""
    program = machine.which("apt-cache")
    if program is None:
        raise HarnessError("apt-cache is not on the PATH; Ubuntu has it in the package apt")
    try:
        p = subprocess.run(
            [program, "policy", package],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(machine.env),
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HarnessError(f"cannot run apt-cache policy {package}: {e}") from None
    if p.returncode != 0:
        error = "; ".join(line.strip() for line in p.stderr.splitlines() if line.strip())
        raise HarnessError(f"apt-cache policy {package} exits {p.returncode}: {error}")
    m = CANDIDATE.search(p.stdout)
    if not m:
        return None
    # The first dotted number: `(none)` has none, an epoch, `1:`, has no dot, and the revision
    # follows a `-`.
    version = VERSION.search(m.group(1))
    return version.group(0) if version else None


def state(machine: Machine, tool: Tool, minimum: Sequence[str]) -> str:
    """`ok` when `tool` is installed and meets `minimum`, `below` when it is installed below it,
    `missing` otherwise."""
    if tool.app:
        return "ok" if (machine.apps / tool.app).exists() else "missing"
    if tool.marker:
        return "ok" if (machine.home / tool.marker).exists() else "missing"
    program = machine.which(tool.command)
    if program is None:
        return "missing"
    if not tool.version or not minimum:
        return "ok"
    version = installed_version(machine, program, tool.version)
    return "ok" if version is not None and meets(version, minimum) else "below"


# ---------------------------------------------------------------------------- the plan ----


def checked_machine(machine: Machine) -> None:
    """Exit 2, naming it, on a system other than macOS and Ubuntu, or an unknown architecture."""
    if machine.system not in SYSTEMS:
        raise HarnessError(f"the system {machine.system!r} is not macOS or Ubuntu; nothing is installed")
    if machine.system == "Linux" and machine.distro != "ubuntu":
        raise HarnessError(f"the Linux {machine.distro!r} is not Ubuntu; nothing is installed")
    if machine.arch not in SYSTEMS[machine.system]:
        raise HarnessError(
            f"the architecture {machine.arch!r} is not one of {', '.join(SYSTEMS[machine.system])} "
            f"on {machine.system}; nothing is installed"
        )


def chosen(choice: profile_module.Setup, system: str) -> list[Tool]:
    """The tools that `choice` needs, in the order of TOOLS, that run on `system`."""
    names = {"", *choice.frontends, *choice.components}
    return [t for t in TOOLS if t.need in names and system in t.systems]


def plan(
    machine: Machine,
    choice: profile_module.Setup,
    loaded: profile_module.Profile,
    options: Options,
    pins: Pins,
) -> Plan:
    """The plan of `setup` for `choice` on `machine`, with the profile `loaded`; see the module."""
    checked_machine(machine)
    env = {
        **machine.env,
        "RESEARCH_HARNESS_PROFILE": str(options.profile),
        "RESEARCH_HARNESS_MODELS": str(options.models),
    }
    result = Plan(doctor(machine, env))
    for tool in TOOLS:
        if tool.need in {*choice.components, *choice.frontends} and machine.system not in tool.systems:
            result.by_hand.append(tool.by_hand)
    directories_step(machine, choice, loaded, result)
    tools = [(t, state(machine, t, pins.minimum.get(t.name, ()))) for t in chosen(choice, machine.system)]
    needed = [(t, s) for t, s in tools if s != "ok"]
    if machine.system == "Darwin":
        installers = homebrew_steps(machine, needed, pins, result)
    else:
        installers = ubuntu_steps(machine, needed, pins, result)
    installing = {t.name for t, s in installers if s == "missing"}
    for tool, s in installers:
        if s == "missing" and tool.comes_with in installing:
            continue
        if s == "below" and tool.upgrade:
            action = rechecked(machine, shell(machine, tool.upgrade), [tool], pins)
            result.steps.append(Step(tool.upgrade, action))
        else:
            result.steps.append(Step(tool.installer, shell(machine, tool.installer)))
        # Only Linux runs the OpenCode installer; Homebrew installs it on macOS.
        if tool.name == "OpenCode":
            result.by_hand.append('add to your shell startup file: export PATH="$HOME/.opencode/bin:$PATH"')
    harness_steps(machine, choice, loaded, env, result)
    return result


def directories_step(
    machine: Machine, choice: profile_module.Setup, loaded: profile_module.Profile, result: Plan
) -> None:
    """One step that creates the directories that `harness install` needs and that are missing."""
    wanted = [pathlib.Path(loaded.tree_agents), *(pathlib.Path(r) for r in loaded.repository_roots)]
    if "opencode" in choice.frontends:
        wanted.append(
            pathlib.Path(machine.env.get("OPENCODE_CONFIG_DIR") or machine.home / ".config" / "opencode")
        )
    missing = [d for d in wanted if not d.is_dir()]
    if missing:

        def make() -> str | None:
            try:
                for d in missing:
                    d.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return f"cannot create {e.filename}: {e.strerror}"
            return None

        result.steps.append(Step("mkdir -p " + " ".join(str(d) for d in missing), make))


def homebrew_steps(
    machine: Machine, needed: list[tuple[Tool, str]], pins: Pins, result: Plan
) -> list[tuple[Tool, str]]:
    """The Homebrew steps of the tools `needed` on macOS; the tools left for their installers. A
    tool below its minimum upgrades through Homebrew when Homebrew lists its formula as installed,
    and is installed by Homebrew otherwise; after either line its version is read again."""
    formulas = [(t, s) for t, s in needed if t.brew]
    casks = [t.cask for t, _ in needed if t.cask]
    if formulas or casks:
        brew = machine.which("brew")
        if brew is None:
            raise HarnessError("brew is not on the PATH: install Homebrew first, from https://brew.sh")
        below = [t for t, s in formulas if s == "below"]
        upgrade = [t for t in below if listed(machine, brew, t.brew)]
        install = [t for t, _ in formulas if t not in upgrade]
        for verb, tools in (("install", install), ("upgrade", upgrade)):
            if tools:
                names = [t.brew for t in tools]
                action = rechecked(
                    machine, command(machine, [brew, verb, *names]), [t for t in tools if t in below], pins
                )
                result.steps.append(Step(f"brew {verb} {' '.join(names)}", action))
        if casks:
            argv = [brew, "install", "--cask", *casks]
            result.steps.append(Step(f"brew install --cask {' '.join(casks)}", command(machine, argv)))
    rest = [(t, s) for t, s in needed if not t.brew and not t.cask]
    return route_rest(rest, result)


def listed(machine: Machine, brew: str, formula: str) -> bool:
    """Whether Homebrew lists `formula` as installed: `brew list <formula>` exits 0."""
    try:
        p = subprocess.run(
            [brew, "list", formula],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(machine.env),
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HarnessError(f"cannot run brew list {formula}: {e}") from None
    return p.returncode == 0


def rechecked(machine: Machine, action: Action, tools: Sequence[Tool], pins: Pins) -> Action:
    """`action`, then the version of each of `tools` read again: a tool that is still below its
    minimum fails the step, with its `stuck` line, or else with the path of the copy that comes
    first on the PATH."""

    def run() -> str | None:
        if (failure := action()) is not None:
            return failure
        lines = [
            tool.stuck
            or f"{tool.name} at {machine.which(tool.command)} is still below its minimum "
            f"{' or '.join(pins.minimum.get(tool.name, ()))}: this copy comes first on the PATH; remove it, "
            "or put the Homebrew copy before it, then run harness setup again"
            for tool in tools
            if state(machine, tool, pins.minimum.get(tool.name, ())) == "below"
        ]
        return "\n".join(lines) or None

    return run


def ubuntu_steps(
    machine: Machine, needed: list[tuple[Tool, str]], pins: Pins, result: Plan
) -> list[tuple[Tool, str]]:
    """The apt line and the pinned releases of the tools `needed` on Ubuntu; the tools left for
    their installers."""
    packages: list[str] = []
    releases: list[Step] = []
    rest: list[tuple[Tool, str]] = []
    key = f"linux-{machine.arch}"
    for tool, s in needed:
        version = candidate(machine, tool.apt[0]) if tool.apt else None
        release = pins.releases.get(tool.name, {}).get(key)
        if version is not None and meets(version, pins.minimum.get(tool.name, ())):
            packages.extend(tool.apt)
        elif release is not None:
            releases.append(
                Step(
                    f"install {tool.command} {release.version} from {release.url} into ~/.local/bin, "
                    f"if its sha256 is {release.sha256}",
                    lambda program=tool.command, r=release: install_release(machine, program, r),
                )
            )
        else:
            rest.append((tool, s))
    # The apt line comes first, so that a stop for sudo comes before any other install.
    if packages:
        line = "sudo apt-get install -y " + " ".join(packages)
        result.steps.append(Step(line, apt(machine, packages, line)))
    result.steps.extend(releases)
    return route_rest(rest, result)


def route_rest(rest: list[tuple[Tool, str]], result: Plan) -> list[tuple[Tool, str]]:
    """The tools of `rest` that an installer installs; each other one is a line by hand."""
    installers: list[tuple[Tool, str]] = []
    for tool, s in rest:
        if tool.installer:
            installers.append((tool, s))
        else:
            result.by_hand.append(tool.by_hand or f"install {tool.name}: no package, release or installer")
    return installers


def harness_steps(
    machine: Machine,
    choice: profile_module.Setup,
    loaded: profile_module.Profile,
    env: Mapping[str, str],
    result: Plan,
) -> None:
    """The steps after the installs, in their order, up to `harness doctor`, which the plan holds
    apart; each harness step runs with `env`."""
    steps = result.steps
    steps.append(
        Step("harness install --apply", command(machine, [*machine.harness, "install", "--apply"], env))
    )
    git = machine.which("git") or "git"
    steps.append(
        Step(
            f"git -C {machine.clone} config core.hooksPath .githooks",
            command(machine, [git, "-C", str(machine.clone), "config", "core.hooksPath", ".githooks"]),
        )
    )
    steps.append(Step("harness trust --apply", command(machine, [*machine.harness, "trust", "--apply"], env)))
    if "jobs" in choice.components:
        job_steps(machine, loaded, env, result)
    if "julia" in choice.components:
        steps.append(
            Step(
                "write ~/.config/kaimon/auth-token, mode 600, from the first key of "
                "~/.config/kaimon/config.json, when that file exists and the token does not",
                lambda: kaimon_token(machine.home),
            )
        )


def job_steps(machine: Machine, loaded: profile_module.Profile, env: Mapping[str, str], result: Plan) -> None:
    """The jobs, as the dotfiles kit's services step does them: the two copies in ~/.local/bin,
    then the launch agents or the systemd user units, rendered and loaded."""
    local = machine.home / ".local" / "bin"
    for source, mode in (("launchagents/claude-autocommit", 0o755), ("scripts/julia-update.jl", 0o644)):
        target = local / pathlib.PurePath(source).name
        result.steps.append(
            Step(
                f"install -m {mode:o} {machine.clone / source} {target}",
                lambda s=machine.clone / source, t=target, m=mode: copy(s, t, m),
            )
        )
    if machine.system == "Darwin":
        if not loaded.launchd_prefix:
            raise HarnessError(
                "the profile has no launchd_prefix, which the labels of the launch agents need"
            )
        agents = machine.home / "Library" / "LaunchAgents"
        for job in JOBS:
            label = f"{loaded.launchd_prefix}.{job}"
            plist = agents / f"{label}.plist"
            result.steps.append(
                Step(
                    f"harness render launchagents/{job}.plist > {plist}",
                    lambda j=job, p=plist: render(machine, f"launchagents/{j}.plist", p, env),
                )
            )
            result.steps.append(
                Step(
                    f"launchctl bootout gui/{os.getuid()}/{label}, when loaded; "
                    f"launchctl bootstrap gui/{os.getuid()} {plist}",
                    lambda j=job, lab=label, p=plist: load_agent(machine, j, lab, p),
                )
            )
        return
    units = machine.home / ".config" / "systemd" / "user"
    for unit in UNITS:
        result.steps.append(
            Step(
                f"harness render systemd/{unit} > {units / unit}",
                lambda u=unit: render(machine, f"systemd/{u}", units / u, env),
            )
        )
    systemctl = machine.which("systemctl") or "systemctl"
    for words in (["daemon-reload"], ["enable", "--now", *ENABLED], ["restart", *ENABLED]):
        result.steps.append(
            Step(f"systemctl --user {' '.join(words)}", command(machine, [systemctl, "--user", *words]))
        )
    result.by_hand.append('keep the jobs running after logout: sudo loginctl enable-linger "$USER"')


# --------------------------------------------------------------------------- the actions ----


def command(machine: Machine, argv: Sequence[str], env: Mapping[str, str] | None = None) -> Action:
    """The action that runs `argv` with `env`, the machine's by default."""

    def run() -> str | None:
        try:
            p = subprocess.run(
                list(argv),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env=dict(env if env is not None else machine.env),
                timeout=INSTALL_TIMEOUT,
                check=False,
            )
        except OSError as e:
            return f"cannot start {argv[0]}: {e.strerror or e}"
        except subprocess.TimeoutExpired:
            return f"no end after {INSTALL_TIMEOUT} s"
        if p.returncode != 0:
            return f"{p.stdout}{p.stderr}exit {p.returncode}"
        return None

    return run


def doctor(machine: Machine, env: Mapping[str, str]) -> Doctor:
    """The action that runs `harness doctor` with `env` and prints its report: doctor's status
    when it is 0 or 1 (a FAIL); any other status, or a doctor that cannot start, fails the step."""

    def run() -> int | str:
        try:
            p = subprocess.run(
                [*machine.harness, "doctor"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env=dict(env),
                timeout=INSTALL_TIMEOUT,
                check=False,
            )
        except OSError as e:
            return f"cannot start harness doctor: {e.strerror or e}"
        except subprocess.TimeoutExpired:
            return f"no end after {INSTALL_TIMEOUT} s"
        print(p.stdout + p.stderr, end="")
        return p.returncode if p.returncode in {0, 1} else f"exit {p.returncode}"

    return run


def shell(machine: Machine, line: str) -> Action:
    """The action that runs the shell line `line`."""
    return command(machine, ["/bin/sh", "-c", line])


def apt(machine: Machine, packages: Sequence[str], line: str) -> Action:
    """The action of the apt line: without sudo, or with `sudo -n true` refused, it prints the line
    for an administrator and fails."""

    def run() -> str | None:
        sudo = machine.which("sudo")
        refused = sudo is None or command(machine, [sudo, "-n", "true"])() is not None
        if sudo is None or refused:
            return (
                "sudo cannot run here without a password. Run `sudo -v` first, or ask an administrator "
                f"to run this line, then run harness setup again:\n  {line}\n"
            )
        return command(machine, [sudo, "-n", "apt-get", "install", "-y", *packages])()

    return run


def install_release(
    machine: Machine, program: str, release: Release, *, redirect: tuple[str, str] = REDIRECT
) -> str | None:
    """Download `release`, following one redirect to `redirect`, a scheme and a host, and no other,
    check its sha256, and install its `program` into ~/.local/bin."""
    try:
        with urllib.request.build_opener(Redirects(redirect)).open(release.url, timeout=TIMEOUT) as response:
            data = cast("bytes", response.read())
    except (OSError, ValueError, http.client.HTTPException, HarnessError) as e:
        return f"cannot download {release.url}: {e}"
    got = hashlib.sha256(data).hexdigest()
    if got != release.sha256:
        return f"{release.url} has sha256 {got}, not the pinned {release.sha256}; nothing is installed"
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            member = tar.extractfile(program)
            body = member.read() if member else b""
    except (KeyError, OSError, tarfile.TarError) as e:
        return f"cannot read {program} from {release.url}: {e}"
    if not body:
        return f"{release.url} holds no file {program}"
    target = machine.home / ".local" / "bin" / program
    try:
        replaced(target, body, 0o755)
    except OSError as e:
        return f"cannot write {target}: {e.strerror}"
    return None


class Redirects(urllib.request.HTTPRedirectHandler):
    """A redirect handler that follows one redirect to `allowed`, a scheme and a host, and refuses
    every other one."""

    def __init__(self, allowed: tuple[str, str] = REDIRECT) -> None:
        super().__init__()
        self.allowed = allowed
        self.followed = 0

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = urllib.parse.urlsplit(newurl)
        if self.followed or (target.scheme, target.hostname) != self.allowed:
            raise HarnessError(
                f"the download redirects to {newurl}; only one redirect to "
                f"{self.allowed[0]}://{self.allowed[1]} is followed"
            )
        self.followed += 1
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def replaced(target: pathlib.Path, data: bytes, mode: int) -> None:
    """`target` holding `data` with the permission bits `mode`, whole or not at all: the bytes go
    to a `.part` file beside it, which then replaces it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    part.chmod(mode)
    part.replace(target)


def copy(source: pathlib.Path, target: pathlib.Path, mode: int) -> str | None:
    """Copy `source` to `target` with the permission bits `mode`."""
    try:
        replaced(target, source.read_bytes(), mode)
    except OSError as e:
        return f"cannot copy {source} to {target}: {e.strerror}"
    return None


def render(machine: Machine, template: str, target: pathlib.Path, env: Mapping[str, str]) -> str | None:
    """`harness render` of the clone's `template` into `target`, whole or not at all."""
    try:
        p = subprocess.run(
            [*machine.harness, "render", str(machine.clone / template)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=INSTALL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"cannot run harness render: {e}"
    if p.returncode != 0:
        return f"{p.stdout}{p.stderr}exit {p.returncode}"
    try:
        replaced(target, p.stdout.encode(), 0o644)
    except OSError as e:
        return f"cannot write {target}: {e.strerror}"
    return None


def load_agent(machine: Machine, job: str, label: str, plist: pathlib.Path) -> str | None:
    """Boot the launch agent `label` out when launchd has it, wait up to 10 s until it is gone,
    then bootstrap it from `plist`, once more after 1 s when that fails."""
    launchctl = machine.which("launchctl") or "launchctl"
    domain = f"gui/{os.getuid()}"
    logs = machine.home / "Library" / "Logs" / job
    try:
        logs.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"cannot create {logs}: {e.strerror}"

    def loaded() -> bool:
        return command(machine, [launchctl, "print", f"{domain}/{label}"])() is None

    if loaded():
        if failed := command(machine, [launchctl, "bootout", f"{domain}/{label}"])():
            return failed
        for _ in range(100):
            if not loaded():
                break
            time.sleep(0.1)
    bootstrap = command(machine, [launchctl, "bootstrap", domain, str(plist)])
    if bootstrap() is None:
        return None
    time.sleep(1)
    return bootstrap()


def kaimon_token(home: pathlib.Path) -> str | None:
    """Write ~/.config/kaimon/auth-token, mode 600, from the first key of Kaimon's config.json,
    when that file exists and the token does not; otherwise print the step."""
    directory = home / ".config" / "kaimon"
    token, config = directory / "auth-token", directory / "config.json"
    if token.exists():
        print(f"{token} exists; it is kept")
        return None
    key: object = None
    if config.is_file():
        try:
            keys = jsonio.load(config).get("api_keys")
        except HarnessError as e:
            return str(e)
        key = cast("list[object]", keys)[0] if isinstance(keys, list) and keys else None
    if not isinstance(key, str) or not key:
        print(
            f"{config} holds no key yet: once the Kaimon server has started, write its first key of "
            f"api_keys into {token}, mode 600, or run harness setup again"
        )
        return None
    try:
        write_private(token, key.encode())
    except HarnessError as e:
        return str(e)
    return None


# ---------------------------------------------------------------------- the questions ----


def ask_line(ask: Ask, question: str) -> str:
    """The answer to `question`; the end of the input, and an answer that is not valid UTF-8, exit 2.

    A standard input that decodes strictly, as under a UTF-8 locale, raises while it reads such an
    answer; one that decodes with `surrogateescape`, as under the C locale, returns it with a
    surrogate, which does not encode."""
    not_utf8 = "an answer that is not valid UTF-8 to: " + question.strip()
    try:
        answer = ask(question).strip()
    except EOFError:
        raise HarnessError("the input ended before the answer to: " + question.strip()) from None
    except UnicodeDecodeError:
        raise HarnessError(not_utf8) from None
    try:
        answer.encode("utf-8")
    except UnicodeEncodeError:
        raise HarnessError(not_utf8) from None
    return answer


def pick(what: str, names: Sequence[str], current: Sequence[str], ask: Ask) -> tuple[str, ...]:
    """The names of `names` that the user picks by their numbers; an empty line keeps `current`."""
    print(f"The {what}:")
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}")
    keep = " ".join(str(names.index(n) + 1) for n in current) or "none"
    while True:
        answer = ask_line(ask, f"The {what} to set up, numbers separated by spaces, or none [{keep}]: ")
        if not answer:
            return tuple(current)
        if answer == "none":
            return ()
        words = answer.replace(",", " ").split()
        if all(w.isdigit() and 1 <= int(w) <= len(names) for w in words):
            return tuple(dict.fromkeys(names[int(w) - 1] for w in words))
        print(f"  Give numbers from 1 to {len(names)}, or none.")


def confirm(ask: Ask, question: str, *, default: bool = False) -> bool:
    """y or n to `question`; an empty line gives `default`."""
    answer = ask_line(ask, f"{question} [{'Y/n' if default else 'y/N'}] ").lower()
    return default if not answer else answer in ("y", "yes")


def choose(current: profile_module.Setup, ask: Ask) -> profile_module.Setup:
    """The `[setup]` that the user chooses, with `current` as the answer to each empty line."""
    return profile_module.Setup(
        frontends=pick("frontends", frontends.FRONTENDS, current.frontends, ask),
        components=pick("components", profile_module.COMPONENTS, current.components, ask),
        develop=confirm(ask, "Develop the harness, with the dev group of uv.lock?", default=current.develop),
    )


def toml_value(value: str | Sequence[str]) -> str:
    """`value` as a TOML string or list of strings: a JSON string is a TOML basic string once
    U+007F, which JSON leaves as it is and TOML refuses, is escaped."""

    def basic(s: str) -> str:
        return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")

    if isinstance(value, str):
        return basic(value)
    return "[" + ", ".join(basic(v) for v in value) + "]"


def new_profile(example: str, ask: Ask) -> str:
    """The text of `example` with each key of REQUIRED set to the user's answer, the example's own
    value for an empty line. A list is given as items separated by commas; an empty item is
    dropped."""
    text = example
    for key, kind in profile_module.REQUIRED.items():
        line = re.search(rf"^{key} = (.*)$", text, re.MULTILINE)
        if line is None:
            raise HarnessError(f"examples/profile.toml has no line `{key} = …`")
        answer = ask_line(ask, f"{key}, {kind} [{line.group(1)}]: ")
        if answer:
            value = toml_value(
                answer
                if kind == profile_module.STRING
                else [a.strip() for a in answer.split(",") if a.strip()]
            )
            text = text[: line.start(1)] + value + text[line.end(1) :]
    return text


def with_setup(text: str, choice: profile_module.Setup) -> str:
    """The profile `text`, which is TOML, with its `[setup]` table holding `choice`: each key's
    line replaced in place, a missing one added after the table's header, `develop` only where it
    is true. Without a header line, a table is added at the end. A line scan finds the header and
    the keys, and `checked_setup` holds the edit to what tomllib reads: any layout that the scan
    does not edit right exits 2, naming the form to write."""
    values = setup_values(choice)
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if HEADER.fullmatch(line.rstrip("\r\n"))), None)
    if start is None:
        body = "".join(f"{k} = {v}\n" for k, v in values.items())
        new = text + ("" if text.endswith("\n") or not text else "\n") + "\n[setup]\n" + body
        return checked_setup(text, new, choice)
    out, i, written = lines[: start + 1], start + 1, set[str]()
    while i < len(lines) and not lines[i].lstrip().startswith("["):
        m = KEY.match(lines[i])
        if m is None:
            out.append(lines[i])
            i += 1
            continue
        # A value of several lines goes on to the first line at which it is whole TOML.
        end = i
        while end < len(lines) - 1 and not is_toml("".join(lines[i : end + 1])):
            end += 1
        if m.group(2) in values:
            out.append(f"{m.group(2)} = {values[m.group(2)]}\n")
            written.add(m.group(2))
        i = end + 1
    missing = "".join(f"{k} = {v}\n" for k, v in values.items() if k not in written)
    out.insert(start + 1, missing)
    return checked_setup(text, "".join(out + lines[i:]), choice)


def setup_values(choice: profile_module.Setup) -> dict[str, str]:
    """The keys of `[setup]` that hold `choice`, each with its value as TOML: `develop` only where
    it is true."""
    values = {"frontends": toml_value(choice.frontends), "components": toml_value(choice.components)}
    if choice.develop:
        values["develop"] = "true"
    return values


# The start of the line with which `with_setup` refuses an edit.
REFUSED = "cannot write [setup] into the profile in place"


def checked_setup(old: str, new: str, choice: profile_module.Setup) -> str:
    """`new`, the profile `old` with `[setup]` edited, when tomllib reads both and finds in `new`
    the keys of SETUP_KEYS of `setup` equal to `choice`, `develop` only where it is true, and every
    other key, inside and outside `setup`, as in `old`. Otherwise it exits 2 with one line that
    names the form of `[setup]` to write."""
    form = "; ".join(f"{k} = {v}" for k, v in setup_values(choice).items())
    refused = HarnessError(
        f"{REFUSED}; write it as a table under a line [setup] that holds the lines {form}, then run "
        "harness setup again"
    )
    try:
        before, after = tomllib.loads(old), tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        raise refused from None
    old_setup: object = before.pop("setup", {})
    new_setup: object = after.pop("setup", None)
    if not isinstance(old_setup, dict) or not isinstance(new_setup, dict):
        raise refused
    old_table, new_table = cast("dict[str, object]", old_setup), cast("dict[str, object]", new_setup)
    want: dict[str, object] = {"frontends": list(choice.frontends), "components": list(choice.components)}
    if choice.develop:
        want["develop"] = True
    keys = profile_module.SETUP_KEYS
    if (
        {k: v for k, v in new_table.items() if k in keys} != want
        or {k: v for k, v in new_table.items() if k not in keys}
        != {k: v for k, v in old_table.items() if k not in keys}
        or after != before
    ):
        raise refused
    return new


def is_toml(text: str) -> bool:
    """Whether `text` is a whole TOML document."""
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False
    return True


# ------------------------------------------------------------------------------- the run ----


def loaded_from(text: str, home: pathlib.Path) -> profile_module.Profile:
    """The profile that `text` holds, checked as `profile.load` checks a file."""
    with tempfile.TemporaryDirectory(prefix="harness-setup-") as tmp:
        path = pathlib.Path(tmp) / "profile.toml"
        path.write_text(text, encoding="utf-8")
        try:
            return profile_module.load(path, home=str(home))
        except HarnessError as e:
            raise HarnessError(str(e).replace(str(path), "the new profile")) from None


def setup(machine: Machine, options: Options, ask: Ask, *, terminal: bool, pins: Pins) -> int:
    """One run of `harness setup`; see the module. After the plan ran, the status of
    `harness doctor`, 0 or 1; 0 after the dry run, or when the answer to the plan is no."""
    if not options.yes and not terminal:
        raise HarnessError(
            "no terminal on stdin to ask the questions; `harness setup --yes` reads [setup] of the "
            "profile and asks nothing"
        )
    checked_machine(machine)
    before: list[Step] = []
    if options.yes:
        if not options.profile.is_file():
            raise HarnessError(
                f"no profile at {options.profile}; --yes asks nothing, so run `harness setup` in a "
                "terminal, or copy examples/profile.toml there and fill it in"
            )
        loaded = profile_module.load(options.profile, home=str(machine.home))
        choice = loaded.setup
    else:
        exists = options.profile.is_file()
        text = (
            options.profile.read_text(encoding="utf-8")
            if exists
            else new_profile(profile_module.DUMMY.read_text(encoding="utf-8"), ask)
        )
        choice = choose(loaded_from(text, machine.home).setup, ask)
        text = with_setup(text, choice)
        loaded = loaded_from(text, machine.home)
        if not exists or text != options.profile.read_text(encoding="utf-8"):
            before.append(
                Step(
                    f"write [setup] into {options.profile}" if exists else f"write {options.profile}",
                    lambda: written(options.profile, text),
                )
            )
    if not options.models.is_file():
        before.append(
            Step(
                f"cp {MODELS} {options.models}",
                lambda: copy(MODELS, options.models, 0o644),
            )
        )
    the_plan = plan(machine, choice, loaded, options, pins)
    the_plan.steps[:0] = before
    show(machine, choice, the_plan)
    if options.dry_run:
        print("\nharness setup: the dry run changes nothing.")
        return 0
    if not options.yes and not confirm(ask, "Run the plan?"):
        print("harness setup: nothing is changed.")
        return 0
    return run(the_plan)


def written(path: pathlib.Path, text: str) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        return f"cannot write {path}: {e.strerror}"
    return None


def show(machine: Machine, choice: profile_module.Setup, the_plan: Plan) -> None:
    print(
        f"harness setup on {machine.system} {machine.arch}: frontends "
        f"{', '.join(choice.frontends) or 'none'}; components {', '.join(choice.components) or 'none'}"
    )
    print("\nThe plan, in this order:")
    for i, step in enumerate(the_plan.steps, 1):
        print(f"  {i}. {step.show}")
    print(f"  {len(the_plan.steps) + 1}. {DOCTOR}")
    by_hand(the_plan)


def by_hand(the_plan: Plan) -> None:
    if the_plan.by_hand:
        print("\nBy hand:")
        for line in the_plan.by_hand:
            print(f"  - {line}")


def run(the_plan: Plan) -> int:
    """Each step in order, then the lines by hand, then `harness doctor`, whose status of 0 or 1
    is the run's. A failed step prints its output and exits 2."""
    n = len(the_plan.steps) + 1

    def failed(i: int, show: str, failure: str) -> HarnessError:
        print(failure.rstrip(), file=sys.stderr)
        return HarnessError(f"step {i} of {n} failed: {show}; harness setup starts again from the first step")

    for i, step in enumerate(the_plan.steps, 1):
        print(f"\n[{i}/{n}] {step.show}", flush=True)
        failure = step.action()
        if failure is not None:
            raise failed(i, step.show, failure)
    by_hand(the_plan)
    print(f"\n[{n}/{n}] {DOCTOR}", flush=True)
    status = the_plan.doctor()
    if isinstance(status, str):
        raise failed(n, DOCTOR, status)
    print(
        "\nharness setup: done." if status == 0 else "\nharness setup: done; harness doctor reports a FAIL."
    )
    return status


def distro(path: pathlib.Path = pathlib.Path("/etc/os-release")) -> str:
    """`ubuntu` when the os-release file at `path` names Ubuntu in ID or ID_LIKE, else its ID, and
    "" without the file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    fields = {
        m.group(1): m.group(3)
        for m in re.finditer(r"""^(ID|ID_LIKE)=(["']?)([^"'\n]*)\2\s*$""", text, re.MULTILINE)
    }
    if "ubuntu" in fields.get("ID", "").split() + fields.get("ID_LIKE", "").split():
        return "ubuntu"
    return fields.get("ID", "")


def extended(home: pathlib.Path, path: str) -> str:
    """`path` with the directories of EXTRA_PATH below `home` first, each once."""
    extra = [str(home / d) for d in EXTRA_PATH]
    return os.pathsep.join([*extra, *(p for p in path.split(os.pathsep) if p and p not in extra)])


def cmd_setup(args: argparse.Namespace) -> int:
    home = pathlib.Path.home()
    env = {**os.environ, "PATH": extended(home, os.environ.get("PATH", ""))}
    system = platform.system()
    machine = Machine(
        system=system,
        arch=platform.machine(),
        distro=distro() if system == "Linux" else "",
        home=home,
        env=env,
        clone=REPO,
        harness=(sys.executable, str(REPO / "bin" / "harness")),
        apps=pathlib.Path("/Applications"),
    )
    options = Options(
        yes=bool(args.yes),
        dry_run=bool(args.dry_run),
        profile=profile_module.location(cast("str | None", args.profile)),
        models=profile_module.models_path(args),
    )
    return setup(machine, options, input, terminal=sys.stdin.isatty(), pins=load_pins())


def register(sub: fmt.Subcommands) -> None:
    p = sub.add_parser(
        "setup",
        help="install the tools and frontends of [setup], then run install, trust, the jobs and doctor",
        description="Ask for the frontends and components in a terminal, write them into [setup] "
        "of the profile, show the plan and run it after y/N: the packages, the pinned releases, the "
        "vendor installers, harness install --apply, core.hooksPath, harness trust --apply, the "
        "jobs, the Kaimon token and harness doctor. A failed step exits 2; a FAIL of harness doctor "
        "exits 1.",
    )
    p.add_argument("--yes", action="store_true", help="read [setup] of the profile and ask nothing")
    p.add_argument(
        "--dry-run", action="store_true", help="print every command of the plan and change nothing"
    )
    p.set_defaults(run=cmd_setup)


# ------------------------------------------------------------------------------ the cases ----

# The fake programs of a case: each appends `<name> <arguments>` to the log, then runs its body.
MACOS_FAKES = {
    "brew": "exit 0",
    "curl": "exit 0",
    "launchctl": '[ "$1" = print ] && exit 1; exit 0',
    "julia": 'echo "julia version 1.13.0"',
    "harness": 'echo "$1 $RESEARCH_HARNESS_PROFILE $RESEARCH_HARNESS_MODELS" >> "$0.env"\n'
    '[ "$1" = render ] && echo "rendered $2"\n'
    '[ "$1" = doctor ] && echo "doctor: all PASS"\nexit 0',
}
LINUX_FAKES = {
    "apt-cache": 'echo "  Candidate: 9.9.9-1"',
    "apt-get": "exit 0",
    "sudo": "exit 0",
    "curl": "exit 0",
    "systemctl": "exit 0",
    "julia": 'echo "julia version 1.13.0"',
    "harness": '[ "$1" = render ] && echo "rendered $2"; exit 0',
}
CHANGING = (
    "brew install",
    "brew upgrade",
    "apt-get",
    "sudo",
    "curl",
    "launchctl boot",
    "systemctl",
    "harness",
)


@dataclasses.dataclass(frozen=True, slots=True)
class Scratch:
    """A case's scratch machine: the home directory, the directory of fake programs, the log of
    their calls, a scratch clone, and the profile and model tables in the home directory."""

    root: pathlib.Path
    home: pathlib.Path
    bin: pathlib.Path
    log: pathlib.Path
    clone: pathlib.Path
    profile: pathlib.Path
    models: pathlib.Path

    def fake(self, name: str, body: str) -> None:
        f = self.bin / name
        f.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.log}"\n{body}\n', encoding="utf-8")
        f.chmod(0o755)

    def machine(self, system: str = "Darwin", arch: str = "", distro: str = "") -> Machine:
        return Machine(
            system=system,
            arch=arch or SYSTEMS.get(system, ("",))[0],
            distro=distro or ("ubuntu" if system == "Linux" else ""),
            home=self.home,
            env={"PATH": extended(self.home, str(self.bin)), "HOME": str(self.home)},
            clone=self.clone,
            harness=(str(self.bin / "harness"),),
            apps=self.root / "Applications",
        )

    def options(self, *, yes: bool = True, dry_run: bool = False) -> Options:
        return Options(yes=yes, dry_run=dry_run, profile=self.profile, models=self.models)

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def envs(self) -> list[str]:
        """The lines of the fake harness of MACOS_FAKES: its subcommand, then the profile and
        model tables of its environment."""
        env = self.bin / "harness.env"
        return env.read_text(encoding="utf-8").splitlines() if env.exists() else []

    def files(self) -> list[tuple[str, int, int]]:
        return sorted(
            (str(p.relative_to(self.home)), p.stat().st_size, p.stat().st_mtime_ns)
            for p in self.home.rglob("*")
            if p.is_file() and not p.is_symlink()
        )

    def hooks(self) -> str:
        return subprocess.run(
            [shutil.which("git") or "git", "-C", str(self.clone), "config", "--local", "core.hooksPath"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        ).stdout.strip()


def scratch(tmp: pathlib.Path, name: str, fakes: Mapping[str, str]) -> Scratch:
    """A new Scratch below `tmp`, with the fake programs `fakes`, the real sh, bash and git, and
    the example profile and model tables."""
    root = tmp / name
    s = Scratch(
        root=root,
        home=root / "home",
        bin=root / "bin",
        log=root / "calls.log",
        clone=root / "clone",
        profile=root / "home" / ".config" / "research-harness" / "profile.toml",
        models=root / "home" / ".config" / "research-harness" / "models.toml",
    )
    s.bin.mkdir(parents=True)
    s.profile.parent.mkdir(parents=True)
    shutil.copyfile(profile_module.DUMMY, s.profile)
    shutil.copyfile(MODELS, s.models)
    for program, body in fakes.items():
        s.fake(program, body)
    for program in ("sh", "bash", "git"):
        real = shutil.which(program)
        if real:
            (s.bin / program).symlink_to(real)
    (s.clone / "launchagents").mkdir(parents=True)
    (s.clone / "scripts").mkdir()
    (s.clone / "launchagents" / "claude-autocommit").write_text("#!/bin/sh\n", encoding="utf-8")
    (s.clone / "scripts" / "julia-update.jl").write_text("# update\n", encoding="utf-8")
    subprocess.run(
        [shutil.which("git") or "git", "init", "-q", str(s.clone)],
        capture_output=True,
        timeout=TIMEOUT,
        check=True,
    )
    return s


class Asker:
    """The answers of a case, in order; it records each question, and the end of its answers is the
    end of the input."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.questions: list[str] = []

    def __call__(self, question: str) -> str:
        self.questions.append(question)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def attempt(
    machine: Machine, options: Options, ask: Ask | None = None, *, terminal: bool = False, pins: Pins
) -> tuple[str, str]:
    """`setup`, with its output: (`0`, or `exit 2: <message>`, the output)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = str(setup(machine, options, ask or Asker(), terminal=terminal, pins=pins))
        except HarnessError as e:
            code = f"exit 2: {e}"
    return code, out.getvalue()


def shows(machine: Machine, choice: profile_module.Setup, options: Options, pins: Pins) -> list[str]:
    """The command lines of the plan of `choice`, or the refusal."""
    loaded = profile_module.load(options.profile, home=str(machine.home))
    try:
        return [step.show for step in plan(machine, choice, loaded, options, pins).steps] + [DOCTOR]
    except HarnessError as e:
        return [f"exit 2: {e}"]


def pins_cases(case: Case, tmp: pathlib.Path) -> None:
    """setup/tools.toml: its releases, and its minimums against dependencies.md."""
    pins = load_pins()
    keys = {key for releases in pins.releases.values() for key in releases}
    case(
        f"setup/tools.toml has releases for linux-x86_64 and linux-aarch64: {sorted(keys)}",
        ok=keys
        >= {
            "linux-x86_64",
            "linux-aarch64",
        },
    )
    names = {t.name for t in TOOLS}
    unknown = sorted((set(pins.minimum) | set(pins.releases)) - names)
    case(f"each tool of setup/tools.toml is a tool of TOOLS: {unknown} are not", ok=not unknown)
    page = (REPO / "docs" / "src" / "dependencies.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| ([^|]+?) \| ([^|]+?) \| [^|]+\|$", page, re.MULTILINE)
    found = {tool: tuple(re.findall(r"≥ (\d+(?:\.\d+)*)", cell)) for tool, cell in rows}
    # The rows of the tools of TOOLS; Python is a prerequisite, and the Julia packages come with
    # the Julia environment of `harness install`.
    floors = {tool: f for tool, f in found.items() if f and tool in names}
    case(
        f"the minimums of setup/tools.toml are the ≥ cells of dependencies.md: {dict(pins.minimum)} "
        f"against {floors}",
        ok=dict(pins.minimum) == floors,
    )
    for name, text, want in (
        ("http", 'url = "http://example.invalid/a.tar.gz"\nsha256 = "' + "0" * 64 + '"', "https url"),
        ("short", 'url = "https://example.invalid/a.tar.gz"\nsha256 = "abc"', "sha256"),
        ("upper", 'url = "https://example.invalid/a.tar.gz"\nsha256 = "' + "A" * 64 + '"', "sha256"),
    ):
        path = tmp / f"{name}.toml"
        path.write_text(f'[release.x]\nversion = "1"\n[release.x.linux-x86_64]\n{text}\n', encoding="utf-8")
        try:
            load_pins(path)
            got = "loaded"
        except HarnessError as e:
            got = str(e)
        case(f"a release with a {name} url or sha256 exits 2 naming it: {got}", ok=want in got)


def version_cases(case: Case) -> None:
    """`meets` on the minimums of setup/tools.toml."""
    for version, minimum, want in (
        ("8.21", ("8.21",), True),
        ("8.21.0", ("8.21",), True),
        ("8.20.9", ("8.21",), False),
        ("8.30.1", ("8.21",), True),
        ("20.16.0", ("20.16", "22.3"), True),
        ("20.15.9", ("20.16", "22.3"), False),
        ("21.7.0", ("20.16", "22.3"), False),
        ("22.3.0", ("20.16", "22.3"), True),
        ("24.0.0", ("20.16", "22.3"), True),
        ("0.1", (), True),
        ("8.21", ("8.21.0",), True),
    ):
        case(f"{version} meets {minimum}: {want}", ok=meets(version, minimum) is want)


def refusal_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """No terminal and no --yes; --yes without a profile; an unknown system, Linux or architecture."""
    s = scratch(tmp, "noterm", MACOS_FAKES)
    before, profile_bytes = s.files(), s.profile.read_bytes()
    for dry_run in (False, True):
        code, out = attempt(s.machine(), s.options(yes=False, dry_run=dry_run), pins=pins)
        case(
            f"without a terminal and without --yes (dry run {dry_run}), setup exits 2 naming --yes and "
            f"changes nothing: {code} {out!r} {s.calls()}",
            ok=code.startswith("exit 2")
            and "--yes" in code
            and not s.calls()
            and s.files() == before
            and s.profile.read_bytes() == profile_bytes,
        )
    s.profile.unlink()
    code, _ = attempt(s.machine(), s.options(), pins=pins)
    case(
        f"--yes without a profile exits 2 naming the profile and writes none: {code}",
        ok=code.startswith("exit 2") and str(s.profile) in code and not s.profile.exists(),
    )
    s = scratch(tmp, "unknown", LINUX_FAKES)
    for machine, name in (
        (s.machine("Linux", "riscv64"), "riscv64"),
        (s.machine("Darwin", "ppc"), "ppc"),
        (s.machine("FreeBSD", "amd64"), "FreeBSD"),
        (s.machine("Linux", "x86_64", "fedora"), "fedora"),
    ):
        for dry_run in (True, False):
            code, _ = attempt(machine, s.options(dry_run=dry_run), pins=pins)
            case(
                f"{machine.system} {machine.distro} {machine.arch}, dry run {dry_run}: exit 2 naming "
                f"{name}, and nothing runs: {code} {s.calls()}",
                ok=code.startswith("exit 2") and name in code and not s.calls(),
            )


def macos_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The whole plan on macOS with --yes: Homebrew, the installers, the harness steps, the jobs and
    the token; then a failed step and the run after it."""
    s = scratch(tmp, "macos", MACOS_FAKES)
    kaimon = s.home / ".config" / "kaimon"
    kaimon.mkdir(parents=True)
    (kaimon / "config.json").write_text('{"api_keys": ["kaimon_key", "second_key"]}\n', encoding="utf-8")
    profile_bytes = s.profile.read_bytes()
    asker = Asker("y", "y", "y")
    code, out = attempt(s.machine(), s.options(), asker, terminal=True, pins=pins)
    calls = s.calls()
    case(f"--yes asks nothing, in a terminal too: {asker.questions}", ok=not asker.questions)
    case(f"--yes runs the plan and exits 0: {code} {out[-300:]!r}", ok=code == "0")
    case("--yes never writes the profile", ok=s.profile.read_bytes() == profile_bytes)
    brew = [c for c in calls if c.startswith("brew install ") and "--cask" not in c]
    wanted = ("gh", "node", "actionlint", "gitleaks", "jolars/tap/fatou", "rtk", "jq", "chezmoi")
    case(
        f"one brew install line holds each missing tool, and not git, which is on the PATH: {brew}",
        ok=len(brew) == 1
        and all(w in brew[0].split() for w in (*wanted, "anomalyco/tap/opencode-v2", "can1357/tap/omp"))
        and "git" not in brew[0].split(),
    )
    case("iTerm2 installs as a cask", ok="brew install --cask iterm2" in calls)
    curls = [c for c in calls if c.startswith("curl ")]
    case(
        f"the juliaup and the Claude Code installer run, and no OpenCode or oh-my-pi installer: {curls}",
        ok=any("install.julialang.org" in c for c in curls)
        and any("claude.ai/install.sh" in c for c in curls)
        and not any("opencode.ai" in c or "omp.sh" in c for c in curls),
    )
    case("Kaimon installs as a Julia app", ok=any('Pkg.Apps.add("Kaimon")' in c for c in calls))
    harness = [c for c in calls if c.startswith("harness ")]
    order = [c.split()[1] for c in harness]
    case(
        f"the harness steps run in their order: {order}",
        ok=order == ["install", "trust", "render", "render", "render", "doctor"]
        and harness[0] == "harness install --apply"
        and harness[1] == "harness trust --apply",
    )
    case(
        f"each harness step gets the run's profile and model tables: {s.envs()}",
        ok=len(s.envs()) == len(harness)
        and all(e.split()[1:] == [str(s.profile), str(s.models)] for e in s.envs()),
    )
    case(f"core.hooksPath of the clone is .githooks: {s.hooks()!r}", ok=s.hooks() == ".githooks")
    plists = sorted(p.name for p in (s.home / "Library" / "LaunchAgents").glob("*.plist"))
    case(
        f"each launch agent is rendered under its label: {plists}",
        ok=plists == sorted(f"org.example.{j}.plist" for j in JOBS)
        and all((s.home / "Library" / "Logs" / j).is_dir() for j in JOBS),
    )
    boots = [c for c in calls if c.startswith("launchctl bootstrap")]
    case(f"each launch agent is bootstrapped: {boots}", ok=len(boots) == len(JOBS))
    local = s.home / ".local" / "bin"
    modes = [oct((local / n).stat().st_mode & 0o777) for n in ("claude-autocommit", "julia-update.jl")]
    case(f"the two copies are in ~/.local/bin, modes 755 and 644: {modes}", ok=modes == ["0o755", "0o644"])
    token = kaimon / "auth-token"
    got = (oct(token.stat().st_mode & 0o777), token.read_text()) if token.exists() else None
    case(f"the Kaimon token is the first key, mode 600: {got}", ok=got == ("0o600", "kaimon_key"))
    case("the output names the steps that the user does by hand", ok="antigravity.google" in out)
    case("the output of harness doctor is printed", ok="doctor: all PASS" in out)

    s.fake("brew", '[ "$1" = install ] && { echo "brew: boom"; exit 1; }; exit 0')
    s.log.unlink()
    code, out = attempt(s.machine(), s.options(), pins=pins)
    case(
        f"a failed step prints its output and exits 2, and no later step runs: {code} {s.calls()}",
        ok=code.startswith("exit 2")
        and "brew: boom" in out
        and not any(c.startswith("harness") for c in s.calls()),
    )
    s.fake("brew", "exit 0")
    code, _ = attempt(s.machine(), s.options(), pins=pins)
    brews = [c for c in s.calls() if c.startswith("brew install ") and "--cask" not in c]
    runs = 2
    case(
        f"the next run starts again from the first step and runs to the end: {code} {brews}",
        ok=code == "0" and len(brews) == runs and "harness doctor" in s.calls(),
    )
    s.fake("gitleaks", 'echo "8.21.0"')
    s.fake("node", 'echo "v20.16.0"')
    s.fake("actionlint", 'echo "1.7.11"')
    lines = shows(s.machine(), profile_module.Setup(), s.options(), pins)
    case(
        f"on macOS, a tool at its minimum is skipped, and one below it upgrades with brew: {lines[:4]}",
        ok="brew upgrade actionlint" in lines
        and not any(" gitleaks" in line or " node" in line for line in lines if line.startswith("brew ")),
    )


def yes_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The order of the jobs and the token; --yes on a profile whose [setup] chooses one frontend
    and no component."""
    s = scratch(tmp, "macos-order", MACOS_FAKES)
    lines = shows(s.machine(), profile_module.Setup(), s.options(), pins)
    at = next((i for i, line in enumerate(lines) if "auth-token" in line), -1)
    agents = [i for i, line in enumerate(lines) if line.startswith("launchctl ")]
    case(
        f"the Kaimon token step comes after the jobs and before harness doctor: {lines[-6:]}",
        ok=bool(agents) and max(agents) < at < len(lines) - 1 and lines[-1] == "harness doctor",
    )
    s = scratch(tmp, "macos-opencode", MACOS_FAKES)
    chosen_profile(s, profile_module.Setup(frontends=("opencode",), components=()))
    code, out = attempt(s.machine(), s.options(), pins=pins)
    calls = s.calls()
    brew = [c for c in calls if c.startswith("brew install ")]
    case(
        f"--yes plans the [setup] of the profile: OpenCode, and no other frontend or component: "
        f"{code} {brew}",
        ok=code == "0"
        and len(brew) == 1
        and "anomalyco/tap/opencode-v2" in brew[0].split()
        and not any(
            w in brew[0].split() for w in ("jq", "rtk", "chezmoi", "jolars/tap/fatou", "can1357/tap/omp")
        )
        and not any(c.startswith(("curl", "launchctl", "harness render")) for c in calls)
        and "auth-token" not in out,
    )


def offline_pins(pins: Pins) -> Pins:
    """`pins` with each release at a local port that refuses: a case's run that reaches a release
    never reaches the network."""
    return Pins(
        pins.minimum,
        {
            name: {
                key: Release(r.version, f"http://127.0.0.1:9/{name}", r.sha256) for key, r in by_key.items()
            }
            for name, by_key in pins.releases.items()
        },
    )


def linux_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The plan on Ubuntu: the apt line against the minimums, the skips, sudo and the installers."""
    s = scratch(tmp, "linux", LINUX_FAKES)
    s.fake(
        "apt-cache",
        'case "$2" in gitleaks) echo "  Candidate: 8.16.0-2";; nodejs) echo "  Candidate: 22.22.0+dfsg-1";; '
        'actionlint|chezmoi) echo "  Candidate: (none)";; *) echo "  Candidate: 1:2.5-1";; esac',
    )
    machine, everything = s.machine("Linux"), profile_module.Setup()
    lines = shows(machine, everything, s.options(), pins)
    apt_lines = [line for line in lines if line.startswith("sudo apt-get install -y ")]
    words = apt_lines[0].split() if apt_lines else []
    case(
        f"one apt line holds each package whose candidate meets the minimum, and not gitleaks (8.16 < "
        f"8.21) or actionlint (no candidate): {apt_lines}",
        ok=len(apt_lines) == 1
        and all(p in words for p in ("nodejs", "npm", "gh", "jq", "bubblewrap", "socat", "lsof"))
        and "gitleaks" not in words
        and "actionlint" not in words,
    )
    releases = [line.split()[1] for line in lines if line.startswith("install ") and "sha256" in line]
    case(
        f"gitleaks, actionlint and RTK install from their pinned releases: {releases}",
        ok=releases == ["actionlint", "gitleaks", "rtk"],
    )
    case(
        f"the apt line comes before the releases: {lines[:3]}",
        ok=bool(apt_lines)
        and lines.index(apt_lines[0])
        < min(
            (i for i, line in enumerate(lines) if line.startswith("install ") and "sha256" in line),
            default=-1,
        ),
    )
    installers = (
        "curl -fsSL https://claude.ai/install.sh | bash",
        "curl -fsSL https://opencode.ai/v2/install | bash -s -- --no-modify-path",
        "curl -fsSL https://omp.sh/install | sh -s -- --binary",
        "curl -fsSL https://install.julialang.org | sh -s -- --yes",
        "curl --proto '=https' --tlsv1.2 -sSf https://fatou.dev/install | sh",
    )
    case(
        f"the installers of Claude Code, OpenCode with --no-modify-path, oh-my-pi, juliaup with --yes "
        f"and fatou run, as these lines: {[line for line in lines if line.startswith('curl')]}",
        ok=all(line in lines for line in installers),
    )
    page = (REPO / "docs" / "src" / "setup-linux.md").read_text(encoding="utf-8").splitlines()
    case(
        "the installers of Claude Code, oh-my-pi and juliaup are the lines of setup-linux.md",
        ok=all(line in page for line in (installers[0], installers[2], installers[3])),
    )
    s.fake("gitleaks", 'echo "8.21"')
    s.fake("node", 'echo "v20.16.0"')
    s.fake("actionlint", 'echo "1.7.12"')
    lines = shows(machine, everything, s.options(), pins)
    planned = " ".join(lines)
    case(
        f"a tool at its minimum is skipped: gitleaks 8.21, Node.js 20.16.0, actionlint 1.7.12: {lines[:3]}",
        ok="gitleaks" not in planned and "nodejs" not in planned and "actionlint" not in planned,
    )
    s.fake("gitleaks", 'echo "8.20.9"')
    s.fake(
        "apt-cache",
        'case "$2" in gitleaks) echo "  Candidate: 8.30.0-1";; *) echo "  Candidate: 9.9-1";; esac',
    )
    lines = shows(machine, everything, s.options(), pins)
    case(
        f"gitleaks below its minimum upgrades through apt, whose candidate meets it: {lines[:2]}",
        ok=any(line.startswith("sudo apt-get") and "gitleaks" in line.split() for line in lines),
    )

    # sudo: missing, then refused; each stops the run at the apt line.
    for name, body in (("no sudo", None), ("sudo -n true refused", "exit 1")):
        s.log.unlink(missing_ok=True)
        (s.bin / "sudo").unlink(missing_ok=True)
        if body is not None:
            s.fake("sudo", body)
        code, out = attempt(machine, s.options(), pins=pins)
        calls = s.calls()
        case(
            f"{name}: the apt line is printed for an administrator, and the run stops before every "
            f"later step: {code} {calls}",
            ok=code.startswith("exit 2")
            and "sudo apt-get install -y " in out
            and not any(c.startswith(("apt-get", "curl", "harness", "systemctl")) for c in calls)
            and all(c == "sudo -n true" for c in calls if c.startswith("sudo")),
        )
    s.fake("sudo", "exit 0")

    # The installers of OpenCode and juliaup only where the program is not on the PATH.
    opencode = profile_module.Setup(frontends=("opencode",), components=())
    lines = shows(machine, opencode, s.options(), pins)
    case(
        f"without opencode on the PATH, its installer runs with --no-modify-path: {lines}",
        ok=any(line.startswith("curl") and line.endswith("| bash -s -- --no-modify-path") for line in lines),
    )
    s.fake("opencode", "exit 0")
    lines = shows(machine, opencode, s.options(), pins)
    case(
        f"with opencode on the PATH, its installer does not run: {lines}",
        ok=not any("opencode.ai" in x for x in lines),
    )
    julia = profile_module.Setup(frontends=(), components=("julia",))
    (s.bin / "julia").unlink()
    lines = shows(machine, julia, s.options(), pins)
    case(
        f"without juliaup, its installer runs, and brings Julia: {lines}",
        ok="curl -fsSL https://install.julialang.org | sh -s -- --yes" in lines
        and "juliaup add release" not in lines,
    )
    s.fake("juliaup", "exit 0")
    lines = shows(machine, julia, s.options(), pins)
    case(
        f"with juliaup on the PATH, its installer does not run, and Julia comes from it: {lines}",
        ok=not any("install.julialang.org" in x for x in lines) and "juliaup add release" in lines,
    )
    s.fake("julia", 'echo "julia version 1.12.6"')
    lines = shows(machine, julia, s.options(), pins)
    case(f"Julia below 1.13 updates through juliaup: {lines}", ok="juliaup update" in lines)


def linux_jobs_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """A whole run of the jobs on Ubuntu, with sudo."""
    s = scratch(tmp, "linux-jobs", LINUX_FAKES)
    machine = s.machine("Linux")
    jobs = profile_module.Setup(frontends=(), components=("jobs",))
    loaded = profile_module.load(s.profile, home=str(s.home))
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = str(run(plan(machine, jobs, loaded, s.options(), pins)))
        except HarnessError as e:
            code = f"exit 2: {e}"
    calls = s.calls()
    case(
        f"with sudo, the apt line runs through sudo -n: {code} {[c for c in calls if c.startswith('sudo')]}",
        ok=code == "0" and any(c.startswith("sudo -n apt-get install -y ") for c in calls),
    )
    units = sorted(p.name for p in (s.home / ".config" / "systemd" / "user").glob("*"))
    case(f"the five units are rendered into ~/.config/systemd/user: {units}", ok=units == sorted(UNITS))
    systemctl = [c for c in calls if c.startswith("systemctl")]
    case(
        f"the units are reloaded, enabled and restarted: {systemctl}",
        ok=systemctl
        == [
            "systemctl --user daemon-reload",
            "systemctl --user enable --now " + " ".join(ENABLED),
            "systemctl --user restart " + " ".join(ENABLED),
        ],
    )
    case("the linger line is printed by hand", ok="loginctl enable-linger" in out.getvalue())


def plan_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """What the choices, the installed programs and the profile put into the plan."""
    s = scratch(tmp, "plan", MACOS_FAKES)
    s.fake("apt-cache", 'echo "  Candidate: 9.9-1"')
    mac, linux, options = s.machine(), s.machine("Linux"), s.options()
    loaded = profile_module.load(s.profile, home=str(s.home))
    opencode = profile_module.Setup(frontends=("opencode",), components=())
    the_plan = plan(mac, opencode, loaded, options, pins)
    lines = [step.show for step in the_plan.steps]
    case(
        f"only the chosen frontend's tools are planned, with no jobs and no token: {lines}",
        ok=any(
            line.startswith("brew install ") and "anomalyco/tap/opencode-v2" in line.split() for line in lines
        )
        and not any(
            x in " ".join(lines) for x in ("claude.ai", "julialang", "fatou", "render", "kaimon", "rtk")
        )
        and any(line.startswith("mkdir -p ") and ".config/opencode" in line for line in lines),
    )
    none = plan(mac, profile_module.Setup(frontends=(), components=()), loaded, options, pins)
    case(
        "without opencode, the OpenCode directory is not made",
        ok=not any(".config/opencode" in step.show for step in none.steps),
    )
    (s.root / "Applications" / "iTerm.app").mkdir(parents=True)
    (s.home / ".gemini").mkdir(parents=True)
    the_plan = plan(mac, profile_module.Setup(), loaded, options, pins)
    case(
        f"iTerm2 in the applications and ~/.gemini count as installed, and no tool of Linux is a line "
        f"by hand on macOS: {the_plan.by_hand}",
        ok=not any("--cask" in step.show for step in the_plan.steps) and the_plan.by_hand == [],
    )
    for d in (loaded.tree_agents, *loaded.repository_roots, s.home / ".config" / "opencode"):
        pathlib.Path(d).mkdir(parents=True, exist_ok=True)
    lines = shows(mac, profile_module.Setup(), options, pins)
    case(f"with every directory there, no mkdir step: {lines[:2]}", ok=not any("mkdir" in x for x in lines))
    linux_plan = plan(linux, profile_module.Setup(), loaded, options, pins)
    case(
        f"on Linux, iTerm2 is a line by hand: {linux_plan.by_hand}",
        ok=any("macOS only" in line for line in linux_plan.by_hand),
    )
    s.fake(
        "apt-cache", 'case "$2" in chezmoi) echo "  Candidate: (none)";; *) echo "  Candidate: 9.9-1";; esac'
    )
    linux_plan = plan(linux, profile_module.Setup(), loaded, options, pins)
    case(
        f"chezmoi without an apt candidate is a line by hand: {linux_plan.by_hand}",
        ok=any(line.startswith("install chezmoi") for line in linux_plan.by_hand),
    )
    linux_plan = plan(linux, opencode, loaded, options, pins)
    case(
        f"the OpenCode installer comes with its PATH line by hand: {linux_plan.by_hand}",
        ok=any(".opencode/bin" in line for line in linux_plan.by_hand),
    )
    s.fake("gitleaks", 'echo "no version here"')
    lines = shows(mac, profile_module.Setup(), options, pins)
    case(
        f"a tool whose version cannot be read is upgraded: {lines[:3]}",
        ok=any(line.startswith("brew upgrade") and "gitleaks" in line.split() for line in lines),
    )
    (s.bin / "brew").unlink()
    lines = shows(mac, profile_module.Setup(), options, pins)
    case(f"on macOS without brew, setup exits 2 naming Homebrew: {lines}", ok="Homebrew" in lines[0])
    s.fake("brew", "exit 0")
    s.profile.write_text(
        s.profile.read_text(encoding="utf-8").replace('launchd_prefix = "org.example"', ""), encoding="utf-8"
    )
    lines = shows(mac, profile_module.Setup(), options, pins)
    case(
        f"the jobs on macOS without launchd_prefix exit 2 naming it: {lines}", ok="launchd_prefix" in lines[0]
    )
    s.models.write_text("# mine\n", encoding="utf-8")
    shutil.copyfile(profile_module.DUMMY, s.profile)
    attempt(mac, options, pins=pins)
    case("an existing models.toml is kept", ok=s.models.read_text(encoding="utf-8") == "# mine\n")
    code, out = attempt(mac, s.options(yes=False, dry_run=True), Asker(*[""] * 3), terminal=True, pins=pins)
    case(
        f"in a terminal, unchanged answers on a profile write nothing: {code}",
        ok=code == "0" and str(s.profile) not in out,
    )


def step_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The load of a launch agent, an apt line with nothing to install, and a failed render."""
    s = scratch(tmp, "steps", MACOS_FAKES)
    mac, linux, options = s.machine(), s.machine("Linux"), s.options()
    s.fake(
        "launchctl",
        'case "$1" in print) [ -e "$0.out" ] && exit 1; exit 0;; bootout) : > "$0.out";; '
        'bootstrap) [ -e "$0.once" ] && exit 0; : > "$0.once"; exit 1;; esac',
    )
    s.log.unlink(missing_ok=True)
    failure = load_agent(mac, "kaimon", "org.example.kaimon", s.home / "a.plist")
    verbs = [c.split()[1] for c in s.calls()]
    case(
        f"a loaded agent is booted out and waited for, and a failed bootstrap is tried once more: "
        f"{failure} {verbs}",
        ok=failure is None and verbs == ["print", "bootout", "print", "bootstrap", "bootstrap"],
    )
    for program, body in (
        *((p, "exit 0") for p in ("gh", "shellcheck", "rsync", "bwrap", "socat", "lsof")),
        ("node", 'echo "v22.3.0"'),
        ("actionlint", 'echo "1.7.12"'),
        ("gitleaks", 'echo "8.21.0"'),
    ):
        s.fake(program, body)
    lines = shows(linux, profile_module.Setup(frontends=(), components=()), options, pins)
    case(f"on Ubuntu with every tool there, no apt line: {lines}", ok=not any("apt-get" in x for x in lines))
    s.fake("harness", 'echo "render: no such template" >&2; exit 2')
    target = s.home / "rendered.plist"
    failure = render(mac, "launchagents/kaimon.plist", target, dict(mac.env))
    case(
        f"a failed render is a failed step, and writes no file: {failure!r}",
        ok=failure is not None and "no such template" in failure and not target.exists(),
    )


def helper_cases(case: Case, tmp: pathlib.Path) -> None:
    """The os-release file, the PATH, the y/N, a numbered list, an archive without its program, and
    the types of setup/tools.toml."""
    release = tmp / "os-release"
    for text, want in (
        ('ID=ubuntu\nVERSION_ID="26.04"\n', "ubuntu"),
        ('ID=pop\nID_LIKE="ubuntu debian"\n', "ubuntu"),
        ("ID=fedora\n", "fedora"),
    ):
        release.write_text(text, encoding="utf-8")
        case(f"os-release {text!r} is {want!r}: {distro(release)!r}", ok=distro(release) == want)
    case("without os-release, the distribution is empty", ok=distro(tmp / "none") == "")
    home = pathlib.Path("/h")
    got = extended(home, f"/h/.local/bin{os.pathsep}{os.pathsep}/usr/bin")
    case(
        f"the PATH holds the directories of EXTRA_PATH first, each once, and no empty entry: {got}",
        ok=got.split(os.pathsep) == [*(str(home / d) for d in EXTRA_PATH), "/usr/bin"],
    )
    for answer, default, want in (
        ("", True, True),
        ("", False, False),
        ("y", False, True),
        ("no", True, False),
    ):
        with contextlib.redirect_stdout(io.StringIO()):
            got_answer = confirm(Asker(answer), "?", default=default)
        case(f"y/N: {answer!r} with the default {default} is {want}", ok=got_answer is want)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        picked = pick("frontends", frontends.FRONTENDS, ("claude",), Asker("9", "x", "4 2 4"))
        nothing = pick("frontends", frontends.FRONTENDS, ("claude",), Asker("none"))
        kept = pick("frontends", frontends.FRONTENDS, ("claude",), Asker(""))
    case(
        f"a numbered list asks again on a wrong answer, takes each name once, `none` and Enter: "
        f"{picked} {nothing} {kept}",
        ok=picked == ("antigravity", "opencode") and nothing == () and kept == ("claude",),
    )
    for name, kind in (("other", tarfile.REGTYPE), ("gitleaks", tarfile.DIRTYPE)):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            info = tarfile.TarInfo(name)
            info.type = kind
            tar.addfile(info, io.BytesIO(b""))
        data = archive.getvalue()
        with release_server({"/a.tar.gz": data}) as url:
            machine = Machine("Linux", "x86_64", "ubuntu", tmp / "h", {}, tmp, (), tmp)
            failure = install_release(
                machine, "gitleaks", Release("1", f"{url}/a.tar.gz", hashlib.sha256(data).hexdigest())
            )
        case(
            f"an archive whose gitleaks is no file ({name}) installs nothing: {failure}",
            ok=failure is not None and "gitleaks" in failure and not (tmp / "h" / ".local").exists(),
        )
    for name, text, want in (
        ("a string", '[minimum]\ngitleaks = "8.21"\n', "minimum.gitleaks"),
        ("a list with a number", '[minimum]\ngitleaks = ["8.21", 9]\n', "minimum.gitleaks"),
        ("a release without its version", '[release.x.linux-x86_64]\nurl = "https://a"\n', "no version"),
    ):
        path = tmp / "pins.toml"
        path.write_text(text, encoding="utf-8")
        try:
            load_pins(path)
            got = "loaded"
        except HarnessError as e:
            got = str(e)
        case(f"{name} in setup/tools.toml exits 2 naming it: {got}", ok=want in got)


def dry_run_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The dry run prints every step in order and runs no command that changes the machine."""
    for system in ("Darwin", "Linux"):
        s = scratch(tmp, f"dry-{system}", MACOS_FAKES if system == "Darwin" else LINUX_FAKES)
        before, hooks = s.files(), s.hooks()
        code, out = attempt(s.machine(system), s.options(dry_run=True), pins=pins)
        changing = [c for c in s.calls() if c.startswith(CHANGING)]
        steps = (
            "harness install --apply",
            "core.hooksPath .githooks",
            "harness trust --apply",
            "harness doctor",
        )
        at = [out.find(step) for step in steps]
        case(
            f"{system}: the dry run exits 0, names the four harness steps in order, and runs nothing "
            f"that changes the machine: {code} {at} {changing}",
            ok=code == "0" and -1 not in at and at == sorted(at) and not changing,
        )
        case(
            f"{system}: the dry run changes no file of the home and not core.hooksPath",
            ok=s.files() == before and s.hooks() == hooks,
        )


def release_cases(case: Case, tmp: pathlib.Path) -> None:
    """A pinned release from a local file server: installed when its sha256 matches, refused when
    it differs, in a whole run too."""
    body = b"#!/bin/sh\necho 8.30.1\n"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        info = tarfile.TarInfo("gitleaks")
        info.size, info.mode = len(body), 0o755
        tar.addfile(info, io.BytesIO(body))
    data = archive.getvalue()
    with release_server({"/gitleaks.tar.gz": data}) as url:
        good = Release("8.30.1", f"{url}/gitleaks.tar.gz", hashlib.sha256(data).hexdigest())
        bad = Release("8.30.1", good.url, hashlib.sha256(data + b"x").hexdigest())
        s = scratch(tmp, "release", LINUX_FAKES)
        target = s.home / ".local" / "bin" / "gitleaks"
        failure = install_release(s.machine("Linux"), "gitleaks", bad)
        case(
            f"a release whose bytes differ from its sha256 is refused, and nothing is installed: {failure}",
            ok=failure is not None and bad.sha256 in failure and not target.exists(),
        )
        s.fake(
            "apt-cache",
            'case "$2" in gitleaks) echo "  Candidate: 8.16.0-2";; *) echo "  Candidate: 9.9-1";; esac',
        )
        pins = Pins(load_pins().minimum, {"gitleaks": {"linux-x86_64": bad}})
        code, _ = attempt(s.machine("Linux"), s.options(), pins=pins)
        case(
            f"in a whole run, the mismatch exits 2 before the harness steps: {code}",
            ok=code.startswith("exit 2")
            and not target.exists()
            and not any(c.startswith("harness") for c in s.calls()),
        )
        failure = install_release(s.machine("Linux"), "gitleaks", good)
        mode = oct(target.stat().st_mode & 0o777) if target.exists() else None
        case(
            f"a release whose sha256 matches installs its program into ~/.local/bin, mode 755: "
            f"{failure} {mode}",
            ok=failure is None and mode == "0o755" and target.read_bytes() == body,
        )


@contextlib.contextmanager
def release_server(files: Mapping[str, bytes], moved: Mapping[str, str] | None = None) -> Generator[str]:
    """The URL of a local file server that serves `files` by path, and redirects each path of
    `moved` to its path on the same server."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if moved and self.path in moved:
                self.send_response(302)
                self.send_header("Location", moved[self.path])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = files.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @override
        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def interactive_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """In a terminal: a new profile from the example, the choices, [setup] written, the y/N."""
    s = scratch(tmp, "ask", MACOS_FAKES)
    s.profile.unlink()
    s.models.unlink()
    answers = ("", "", "me, my-org", "", "", "1 3", "2", "y")
    code, _ = attempt(s.machine(), s.options(yes=False), Asker(*answers, "n"), terminal=True, pins=pins)
    case(
        f"the answer n to the plan changes nothing: {code} {s.calls()}",
        ok=code == "0"
        and not s.profile.exists()
        and not s.models.exists()
        and not any(c.startswith(CHANGING) for c in s.calls()),
    )
    asker = Asker(*answers, "y")
    code, _ = attempt(s.machine(), s.options(yes=False), asker, terminal=True, pins=pins)
    asked = [q.split(",")[0].split(" [")[0] for q in asker.questions]
    case(
        f"setup asks for the five keys with no default, the frontends, the components, develop and the "
        f"plan: {asked}",
        ok=len(asker.questions) == len(profile_module.REQUIRED) + 4
        and asked[: len(profile_module.REQUIRED)] == list(profile_module.REQUIRED),
    )
    try:
        loaded = profile_module.load(s.profile, home=str(s.home))
        got: object = (loaded.org, loaded.setup, loaded.memory_project)
    except HarnessError as e:
        got = str(e)
    case(
        f"the new profile holds the answers, the example's values for the empty ones, and [setup]: "
        f"{code} {got}",
        ok=code == "0"
        and got
        == (
            ("me", "my-org"),
            profile_module.Setup(frontends=("claude", "omp"), components=("rtk",), develop=True),
            "-home-example-Research",
        ),
    )
    case("models.toml is copied from the example", ok=s.models.read_bytes() == MODELS.read_bytes())
    case("the plan ran: harness install --apply", ok="harness install --apply" in s.calls())

    text = 'a = 1\n\n[setup]\n# kept\nfrontends = [\n  "claude",\n]\ncomponents = []\ndevelop = true\n'
    new = with_setup(text, profile_module.Setup(frontends=("omp",), components=("jq",)))
    case(
        f"with_setup replaces each key in place, a list of several lines whole, and drops a false "
        f"develop: {new!r}",
        ok=new == 'a = 1\n\n[setup]\n# kept\nfrontends = ["omp"]\ncomponents = ["jq"]\n',
    )
    new = with_setup("a = 1\n", profile_module.Setup(frontends=(), components=(), develop=True))
    case(
        f"with_setup adds a table where there is none: {new!r}",
        ok=new == "a = 1\n\n[setup]\nfrontends = []\ncomponents = []\ndevelop = true\n",
    )


def token_cases(case: Case, tmp: pathlib.Path) -> None:
    """The Kaimon token: no config, no key, an existing token."""
    home = tmp / "token"
    directory = home / ".config" / "kaimon"
    directory.mkdir(parents=True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        failure = kaimon_token(home)
    case(
        f"without config.json, the token step prints the step and writes nothing: {out.getvalue()!r}",
        ok=failure is None and "api_keys" in out.getvalue() and not (directory / "auth-token").exists(),
    )
    for keys in ("[]", '[""]', "[7]"):
        (directory / "config.json").write_text(f'{{"api_keys": {keys}}}\n', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            failure = kaimon_token(home)
        case(
            f"with api_keys {keys}, the token step writes nothing",
            ok=failure is None and not (directory / "auth-token").exists(),
        )
    (directory / "auth-token").write_text("mine", encoding="utf-8")
    (directory / "config.json").write_text('{"api_keys": ["other"]}\n', encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        failure = kaimon_token(home)
    case("an existing token is kept", ok=(directory / "auth-token").read_text() == "mine")


def chosen_profile(s: Scratch, choice: profile_module.Setup) -> None:
    """Write `choice` into `[setup]` of the scratch profile."""
    s.profile.write_text(with_setup(s.profile.read_text(encoding="utf-8"), choice), encoding="utf-8")


def header_cases(case: Case) -> None:
    """`with_setup` on each form of a `[setup]` table that TOML allows."""
    choice = profile_module.Setup(frontends=("omp",), components=("jq",))
    want = {"frontends": ["omp"], "components": ["jq"]}
    for name, text in (
        (
            "a header with a comment",
            'a = 1\n[setup]  # this machine\nfrontends = ["claude"]\ncomponents = []\n',
        ),
        ("a header with spaces", 'a = 1\n[ setup ]\nfrontends = ["claude"]\ncomponents = []\n'),
        (
            "a list whose first line holds a comment with ]",
            'a = 1\n[setup]\nfrontends = [ # the ] frontends\n  "claude",\n]\ncomponents = []\n',
        ),
        (
            "a list whose items hold comments with ]",
            'a = 1\n[setup]\nfrontends = [\n  "claude", # one ]\n  "omp", # two ]\n]\ncomponents = []\n',
        ),
        ("quoted keys", 'a = 1\n[setup]\n"frontends" = ["claude"]\n\'components\' = []\n'),
        ("a header in double quotes", 'a = 1\n["setup"]\nfrontends = ["claude"]\ncomponents = []\n'),
        ("a header in single quotes", "a = 1\n['setup']\nfrontends = [\"claude\"]\ncomponents = []\n"),
        (
            "a quoted header with spaces and a comment",
            'a = 1\n[ "setup" ]  # this machine\nfrontends = ["claude"]\ncomponents = []\n',
        ),
    ):
        try:
            new = with_setup(text, choice)
            got: object = cast("dict[str, object]", tomllib.loads(new)).get("setup")
            kept = new.splitlines()[:2] == text.splitlines()[:2] and new.count("setup") == 1
        except (HarnessError, tomllib.TOMLDecodeError) as e:
            got, kept = str(e), False
        case(f"with_setup writes [setup] in place on {name}: {got}", ok=got == want and kept)
    for name, text in (
        ("an inline table", 'a = 1\nsetup = { frontends = ["claude"], components = [] }\n'),
        ("dotted keys", 'a = 1\nsetup.frontends = ["claude"]\nsetup.components = []\n'),
    ):
        try:
            got = with_setup(text, choice)
        except HarnessError as e:
            got = str(e)
        case(
            f"with_setup refuses [setup] as {name}, naming the form: {got!r}",
            ok=REFUSED in got and 'frontends = ["omp"]' in got,
        )
    old = 'a = 1\n[setup]\nfrontends = ["claude"]\ncomponents = []\n'
    for name, new in (
        ("a wrong setup", 'a = 1\n[setup]\nfrontends = ["claude"]\ncomponents = ["jq"]\n'),
        (
            "a setup with develop = false",
            'a = 1\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\ndevelop = false\n',
        ),
    ):
        try:
            got = checked_setup(old, new, choice)
        except HarnessError as e:
            got = str(e)
        case(f"the check of with_setup refuses {name} beside an equal rest: {got!r}", ok=REFUSED in got)
    new = 'a = 1\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\n'
    try:
        got = checked_setup(old, new, choice)
    except HarnessError as e:
        got = str(e)
    case(f"the check of with_setup passes the chosen setup beside an equal rest: {got!r}", ok=got == new)
    for name, before, new in (
        ("another key changed", old, 'a = 2\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\n'),
        ("a key added", old, 'a = 1\nb = 1\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\n'),
        ("invalid TOML", old, 'a = 1\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\n[setup]\n'),
        (
            "another key of setup dropped",
            'a = 1\n[setup]\nfrontends = ["claude"]\ncomponents = []\nx = 1\n',
            'a = 1\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\n',
        ),
        (
            "an old setup that is no table",
            "a = 1\nsetup = 1\n",
            'a = 1\n[setup]\nfrontends = ["omp"]\ncomponents = ["jq"]\n',
        ),
    ):
        try:
            got = checked_setup(before, new, choice)
        except HarnessError as e:
            got = str(e)
        case(f"the check of with_setup refuses {name}: {got!r}", ok=REFUSED in got)


def string_header_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """A line `[setup]` inside a multi-line string before the table, and an answer that is not
    valid UTF-8: each exits 2 with one line and changes nothing."""
    for name, answers in (
        ("a new choice", ("1", "3", "n")),
        ("the choice the profile holds", ("", "", "")),
    ):
        s = scratch(tmp, f"string-header-{answers[0] or 'same'}", MACOS_FAKES)
        text = s.profile.read_text(encoding="utf-8").replace(
            'launchd_prefix = "org.example"', 'launchd_prefix = """\n[setup]\n"""'
        )
        s.profile.write_text(text, encoding="utf-8")
        before = s.profile.read_bytes()
        loads = profile_module.load(s.profile, home=str(s.home)).setup == profile_module.Setup()
        code, _ = attempt(s.machine(), s.options(yes=False), Asker(*answers), terminal=True, pins=pins)
        case(
            f"a line [setup] in a multi-line string before the table, with {name}, exits 2 naming the "
            f"form and leaves the profile byte for byte: {code!r}",
            ok=loads and code.startswith("exit 2") and REFUSED in code and s.profile.read_bytes() == before,
        )
    # The real `input` reads the answers through a standard input of each decoding: `strict`, as
    # under a UTF-8 locale, raises while it reads; `surrogateescape`, as under the C locale,
    # returns the byte as a surrogate.
    for errors in ("strict", "surrogateescape"):
        s = scratch(tmp, f"not-utf-8-{errors}", MACOS_FAKES)
        s.profile.unlink()
        stdin = io.TextIOWrapper(io.BytesIO(b"x\xff\n" + b"\n" * 12), encoding="utf-8", errors=errors)
        real, sys.stdin = sys.stdin, stdin
        try:
            code, out = attempt(s.machine(), s.options(yes=False), input, terminal=True, pins=pins)
            code.encode()
        except UnicodeError as e:
            code, out = f"raised {type(e).__name__}: {e}", ""
        finally:
            sys.stdin = real
        case(
            f"an answer that is not valid UTF-8, read with errors={errors}, exits 2 with one line and "
            f"no traceback: {code!r}",
            ok=code.startswith("exit 2")
            and "is not valid UTF-8" in code
            and "\n" not in code
            and "Traceback" not in out
            and not s.profile.exists(),
        )


def edge_cases(case: Case, tmp: pathlib.Path) -> None:
    """An os-release value in single quotes, an answer with U+007F or empty list items, a
    sha256 of 65 digits, and a log directory that cannot be made."""
    release = tmp / "os-release-quoted"
    release.write_text("ID='pop'\nID_LIKE='ubuntu debian'\n", encoding="utf-8")
    case(f"os-release in single quotes names Ubuntu: {distro(release)!r}", ok=distro(release) == "ubuntu")
    value = "a\x7fb"
    try:
        parsed: object = tomllib.loads(f"x = {toml_value(value)}\ny = {toml_value([value])}\n")
    except tomllib.TOMLDecodeError as e:
        parsed = str(e)
    case(f"toml_value escapes U+007F: {parsed!r}", ok=parsed == {"x": value, "y": [value]})
    example = profile_module.DUMMY.read_text(encoding="utf-8")
    answers = [""] * len(profile_module.REQUIRED)
    answers[list(profile_module.REQUIRED).index("org")] = "me,, "
    with contextlib.redirect_stdout(io.StringIO()):
        text = new_profile(example, Asker(*answers))
    org = cast("dict[str, object]", tomllib.loads(text)).get("org")
    case(f"a list answer drops its empty items: {org}", ok=org == ["me"])
    path = tmp / "long.toml"
    path.write_text(
        '[release.x]\nversion = "1"\n[release.x.linux-x86_64]\nurl = "https://example.invalid/a.tar.gz"\n'
        f'sha256 = "{"0" * 65}"\n',
        encoding="utf-8",
    )
    try:
        load_pins(path)
        got = "loaded"
    except HarnessError as e:
        got = str(e)
    case(f"a sha256 of 65 digits exits 2 naming it: {got}", ok="sha256" in got)
    s = scratch(tmp, "logs", MACOS_FAKES)
    (s.home / "Library").mkdir(parents=True)
    (s.home / "Library" / "Logs").write_text("in the way\n", encoding="utf-8")
    try:
        failure = load_agent(s.machine(), "kaimon", "org.example.kaimon", s.home / "a.plist")
    except OSError as e:
        failure = f"raised {e!r}"
    case(
        f"a log directory that cannot be made fails the step, naming it: {failure}",
        ok=failure is not None and not failure.startswith("raised") and "Logs" in failure,
    )


def redirect_cases(case: Case, tmp: pathlib.Path) -> None:
    """A release that redirects: to another host, once to the allowed host, twice, and once to the
    allowed host by another scheme."""
    body = b"#!/bin/sh\n"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        info = tarfile.TarInfo("gitleaks")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    data = archive.getvalue()
    with release_server({"/b.tar.gz": data}, {"/a.tar.gz": "/b.tar.gz"}) as url:
        home = tmp / "redirect"
        machine = Machine("Linux", "x86_64", "ubuntu", home, {}, tmp, (), tmp)
        failure = install_release(
            machine, "gitleaks", Release("1", f"{url}/a.tar.gz", hashlib.sha256(data).hexdigest())
        )
    case(
        f"a release that redirects to another host installs nothing: {failure}",
        ok=failure is not None and "redirect" in failure and not (home / ".local").exists(),
    )
    moved = {"/a.tar.gz": "/b.tar.gz", "/c.tar.gz": "/a.tar.gz"}
    with release_server({"/b.tar.gz": data}, moved) as url:
        for name, path, scheme, installs in (
            ("one redirect to the allowed host", "a", "http", True),
            ("two redirects to the allowed host", "c", "http", False),
            ("one redirect to the allowed host by http, where https is allowed", "a", "https", False),
        ):
            home = tmp / f"redirect-{path}-{scheme}"
            machine = Machine("Linux", "x86_64", "ubuntu", home, {}, tmp, (), tmp)
            failure = install_release(
                machine,
                "gitleaks",
                Release("1", f"{url}/{path}.tar.gz", hashlib.sha256(data).hexdigest()),
                redirect=(scheme, "127.0.0.1"),
            )
            target = home / ".local" / "bin" / "gitleaks"
            case(
                f"{name}: {'installs' if installs else 'refused, installs nothing'}: {failure}",
                ok=(failure is None and target.is_file() and target.read_bytes() == body)
                if installs
                else (failure is not None and "redirect" in failure and not (home / ".local").exists()),
            )


def apt_cache_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """apt-cache that fails, is missing, or knows no package."""
    s = scratch(tmp, "apt-cache", LINUX_FAKES)
    machine, nothing = s.machine("Linux"), profile_module.Setup(frontends=(), components=())
    s.fake("apt-cache", 'echo "E: The package lists could not be parsed" >&2; exit 100')
    lines = shows(machine, nothing, s.options(), pins)
    case(
        f"apt-cache that exits 100 exits 2, naming apt-cache and its error: {lines[:1]}",
        ok=lines[0].startswith("exit 2") and "apt-cache" in lines[0] and "could not be parsed" in lines[0],
    )
    (s.bin / "apt-cache").unlink()
    lines = shows(machine, nothing, s.options(), pins)
    case(
        f"Ubuntu without apt-cache exits 2 naming it: {lines[:1]}",
        ok=lines[0].startswith("exit 2") and "apt-cache" in lines[0],
    )
    s.fake("apt-cache", 'case "$2" in gh) exit 0;; *) echo "  Candidate: 9.9-1";; esac')
    lines = shows(machine, nothing, s.options(), pins)
    case(
        f"a package that apt-cache does not know is no candidate, and no error: {lines[:2]}",
        ok=not lines[0].startswith("exit 2") and not any("gh" in line.split() for line in lines),
    )


def recheck_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """A tool below its minimum after its upgrade: Julia on its default channel, and a copy that
    Homebrew did not install."""
    s = scratch(tmp, "julia-below", LINUX_FAKES)
    chosen_profile(s, profile_module.Setup(frontends=(), components=("julia",)))
    s.fake("julia", 'echo "julia version 1.12.6"')
    s.fake("juliaup", "exit 0")
    code, out = attempt(s.machine("Linux"), s.options(), pins=pins)
    calls = s.calls()
    case(
        f"juliaup update that leaves Julia below 1.13 fails the run at that step, naming juliaup "
        f"default, and no later step runs: {code} {calls[-3:]}",
        ok=code.startswith("exit 2")
        and "juliaup update" in code
        and "juliaup default release" in out
        and not any(c.startswith(("harness", "fatou")) or "Kaimon" in c for c in calls),
    )
    s.fake(
        "juliaup",
        f'[ "$1" = update ] && printf \'#!/bin/sh\\necho "julia version 1.13.0"\\n\' > "{s.bin / "julia"}"; '
        "exit 0",
    )
    s.log.unlink()
    code, out = attempt(s.machine("Linux"), s.options(), pins=pins)
    case(
        f"juliaup update that raises Julia to 1.13.0 passes: {code} {out[-200:]!r}",
        ok=code == "0" and "juliaup update" in s.calls(),
    )

    s = scratch(tmp, "node-below", MACOS_FAKES)
    chosen_profile(s, profile_module.Setup(frontends=(), components=()))
    s.fake("node", 'echo "v18.0.0"')
    s.fake("brew", '[ "$1" = list ] && exit 1; exit 0')
    lines = shows(s.machine(), profile_module.Setup(frontends=(), components=()), s.options(), pins)
    case(
        f"a Node.js below its minimum that Homebrew did not install gets brew install: {lines[:3]}",
        ok=any(line.startswith("brew install ") and "node" in line.split() for line in lines)
        and not any(line.startswith("brew upgrade") for line in lines),
    )
    code, out = attempt(s.machine(), s.options(), pins=pins)
    case(
        f"when another copy below the minimum comes first after brew install, the step fails naming "
        f"its path: {code}",
        ok=code.startswith("exit 2")
        and "brew install" in code
        and str(s.bin / "node") in out
        and not any(c.startswith("harness") for c in s.calls()),
    )
    s.fake("brew", '[ "$1" = list ] && [ "$2" = node ] && exit 0; exit 0')
    lines = shows(s.machine(), profile_module.Setup(frontends=(), components=()), s.options(), pins)
    case(
        f"a Node.js below its minimum that Homebrew lists gets brew upgrade: {lines[:3]}",
        ok="brew upgrade node" in lines,
    )
    s.fake(
        "brew",
        f'[ "$1" = upgrade ] && printf \'#!/bin/sh\\necho v22.3.0\\n\' > "{s.bin / "node"}"; exit 0',
    )
    s.log.unlink()
    code, _ = attempt(s.machine(), s.options(), pins=pins)
    case(f"brew upgrade that raises Node.js passes: {code}", ok=code == "0")


def doctor_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The status of `harness doctor` at the end of the run."""
    for status, want in (("1", "1"), ("2", "exit 2: step")):
        s = scratch(tmp, f"doctor-{status}", MACOS_FAKES)
        s.fake("harness", f'[ "$1" = doctor ] && {{ echo "doctor: FAIL here"; exit {status}; }}; exit 0')
        code, out = attempt(s.machine(), s.options(), pins=pins)
        calls = [c.split()[1] for c in s.calls() if c.startswith("harness ")]
        case(
            f"a harness doctor that exits {status} gives {want}, after every earlier step: {code} {calls}",
            ok=code.startswith(want)
            and calls == ["install", "trust", "render", "render", "render", "doctor"],
        )
        if status == "1":
            case(
                f"doctor's output comes once, after the lines by hand: {out[-400:]!r}",
                ok=out.count("doctor: FAIL here") == 1
                and out.rfind("antigravity.google") < out.find("doctor: FAIL here"),
            )


def selftest() -> tuple[int, int]:
    """The cases of the functions above: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  setup: {label}")

    # No case reaches the network, a mutated one neither: each release is at a port that refuses.
    pins = offline_pins(load_pins())
    with tempfile.TemporaryDirectory(prefix="harness-setup-") as tmp:
        root = pathlib.Path(tmp).resolve()
        pins_cases(case, root)
        version_cases(case)
        refusal_cases(case, root, pins)
        macos_cases(case, root, pins)
        linux_cases(case, root, pins)
        linux_jobs_cases(case, root, pins)
        plan_cases(case, root, pins)
        step_cases(case, root, pins)
        helper_cases(case, root)
        dry_run_cases(case, root, pins)
        release_cases(case, root)
        interactive_cases(case, root, pins)
        token_cases(case, root)
        yes_cases(case, root, pins)
        header_cases(case)
        string_header_cases(case, root, pins)
        edge_cases(case, root)
        redirect_cases(case, root)
        apt_cache_cases(case, root, pins)
        recheck_cases(case, root, pins)
        doctor_cases(case, root, pins)
    return total, wrong
