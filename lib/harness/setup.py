"""`harness setup`: the tools, the frontends and the harness's own steps of a machine, in one run.

    harness setup              # ask in a terminal, show the plan, run it after y/N
    harness setup --yes        # read [setup] of the profile, ask nothing, run the plan
    harness setup --dry-run    # print every command of the plan, change nothing
    harness test setup         # the cases below

A machine needs Python 3.14, uv, git, the clone and, on macOS, Homebrew before it. In a terminal,
`setup` creates the profile from examples/profile.toml when there is none, asking only for the
keys of REQUIRED, the keys with no default, with the example's value as the answer to an empty
line; a list is items separated by commas or a TOML list (`list_answer`). It asks for the
frontends and the components from numbered lists, and for `develop`, y/N. With the component
`jobs` and a profile without `claude_remote`, it then asks for that URL (`ask_remote`), an empty
line for none. Before each question it prints the question's explanation of EXPLAINED.
It then shows the plan and runs it after y/N; a step of that plan, after the clone of ~/.claude
alone, writes the answers into
`[setup]` of the profile (`with_setup`), `develop` only where it is true, and a `claude_remote`
answer as the profile's first line (`with_remote`). `--yes` reads `[setup]`,
or the defaults of a profile without it, asks nothing and never writes the profile; without a
profile it exits 2. Without a terminal on stdin and without `--yes` it exits 2 and names
`--yes`. `--dry-run`, alone or with `--yes`, prints the plan and changes nothing. Missing model
tables are copied from examples/models.toml. `with_setup` writes only a table under its own
header line, and checks its edit with tomllib: a `setup` of the profile that it cannot write in
place, such as an inline table or dotted keys, exits 2 and names the table to write.

The plan (`plan`), in this order: with the `jobs` component and a `claude_remote`, `git clone` of
it into a ~/.claude that holds no `.git` (`cloned`), before any step that may write below
~/.claude; the writes of the profile and the model tables; the directories that
`harness install` needs (the tree instructions, each `repository_roots` entry, and the OpenCode
directory with `opencode`); the packages; the pinned releases; the vendor installers; with any
frontend, srt from the lockfile of sandbox/srt/ (`srt_step`, `install_srt`);
`harness install --apply`, `git config core.hooksPath .githooks` in the clone,
`harness trust --apply` with the `claude` frontend once Claude Code has written `~/.claude.json`
(before that, the step by hand), the jobs with the `jobs` component, without the autocommit job
where the profile has no `claude_remote`, and on macOS with the Seatbelt profile of the Kaimon and
julia-update jobs written into ~/.config/research-harness/sandbox/ before each one's plist
(`jobsandbox.py`), and the `ps` shim of the Kaimon job into its `shims/` before Kaimon's plist,
the Kaimon token with the `julia` component, which with
the jobs waits up to TOKEN_READS s for the key of the server that they start, and
`harness doctor`. A tool of
TOOLS belongs to every machine or to one component or frontend. A tool that is installed and meets
its minimum is skipped; a tool with no minimum is met by any version, and one whose version cannot
be read counts as below its minimum. On macOS a missing tool that Homebrew has goes into one
`brew install` line, and so does one below its minimum that Homebrew does not list as installed
(`brew list`); one that it lists goes into one `brew upgrade` line. On Ubuntu each package whose
apt candidate meets the tool's minimum goes into one `sudo apt-get install -y` line; an apt-cache
that fails exits 2. Without sudo, or with `sudo -n true` refused, that step prints the line for an
administrator and the run stops there. A tool that apt does not meet installs from its pinned
release of setup/tools.toml (`load_pins`) into ~/.local/bin, after a check of the archive's
sha256; a mismatch installs nothing. The release of Node.js is a whole tree (TREES): it unpacks
into ~/.local/share/research-harness/node/<version>/, and node, npm and npx in ~/.local/bin link
into it (`install_tree`). Otherwise the vendor's installer runs, where one runs
unattended: the OpenCode installer only when `opencode` is not on the PATH, with
`--no-modify-path`, and the juliaup installer only when `juliaup` is not on the PATH. Julia below
its minimum runs `juliaup update`. After a Homebrew line or `juliaup update` for a tool below its
minimum, the tool's version is read again (`rechecked`): one still below it fails the step, with
the fix for Julia, the default channel of juliaup, and otherwise with the path of the copy that
comes first on the PATH. What runs no installer is a line under "by hand", and so is, with the
jobs on Linux, the line that turns on lingering, unless `loginctl show-user` reads `Linger=yes`
(`lingers`), and the one `export PATH=…` line of the directories of EXTRA_PATH that the choice
puts programs into and that the PATH that `setup` started with lacks (`missing_path`). In a
terminal, without `--yes`, with zsh as the login shell and a ~/.zshrc that is no symlink, `setup`
asks y/N to append that line to ~/.zshrc, after the comment PATH_COMMENT; a yes makes it a step of
the plan, which appends nothing where ~/.zshrc holds the line already. srt runs `npm ci
--ignore-scripts` on a copy of sandbox/srt/ and moves the tree into
~/.local/share/research-harness/srt/<version>/, linked as ~/.local/bin/srt, with a node of
SRT_NODE or later; the plan skips it where that tree holds the shipped lockfile and is linked. An
unknown system, a Linux that is not Ubuntu and an unknown architecture exit 2 and name it.

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
import plistlib
import pwd
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
from unittest import mock

from . import REPO, HarnessError, fmt, frontends, jobsandbox, jsonio
from . import doctor as doctor_module
from . import profile as profile_module
from .fsutil import Case, write_private

PINS = REPO / "setup" / "tools.toml"
MODELS = REPO / "examples" / "models.toml"
# Seconds: a version query, an apt-cache query, a loginctl query and a download; and every command
# of a step.
TIMEOUT, INSTALL_TIMEOUT = 60, 3600
# The architectures of each system, as `platform.machine()` names them.
SYSTEMS = {"Darwin": ("arm64", "x86_64"), "Linux": ("x86_64", "aarch64")}
LINUX = ("Linux",)
# The directories below the home directory where an installer puts its program.
EXTRA_PATH = (".local/bin", ".juliaup/bin", ".julia/bin", ".opencode/bin")
# The start of the line by hand that holds the `export PATH=…` line of `missing_path`.
PATH_BY_HAND = "add to your shell startup file: "
# The comment line above the `export PATH=…` line that `setup` appends to ~/.zshrc.
PATH_COMMENT = "# The directories of the tools that harness setup installs"
# The most reads of Kaimon's config.json, one second apart, while the token step waits for its key.
TOKEN_READS = 60
VERSION = re.compile(r"\d+(?:\.\d+)+")
CANDIDATE = re.compile(r"^\s*Candidate:\s*(\S+)", re.MULTILINE)
SHA256 = re.compile(r"[0-9a-f]{64}")
# The header of the `[setup]` table, and a key of it, bare or quoted.
HEADER = re.compile(r"""\s*\[\s*(["']?)setup\1\s*\]\s*(?:#.*)?""")
KEY = re.compile(r"""\s*(["']?)(frontends|components|develop)\1\s*=""")
# The one redirect that a download of a pinned release follows, as bin/harness's download does.
REDIRECT = ("https", "release-assets.githubusercontent.com")
# The tools whose pinned release is a whole tree, a .tar.xz: {name: the programs of the tree's bin/
# that ~/.local/bin links}. npm runs from the tree, beside the binary.
TREES = {"Node.js": ("node", "npm", "npx")}
# The directory below the home directory that holds each tree, in `<command>/<version>/`.
TREE_ROOT = pathlib.PurePath(".local", "share", "research-harness")
# The npm package of the sandbox runtime srt, for the settings files of the frontends: the directory
# of its package.json and package-lock.json, the package, the arguments of npm, and the Node.js that
# the package's `engines.node` asks for, since `npm ci` only warns below it.
SRT = REPO / "sandbox" / "srt"
SRT_FILES = ("package.json", "package-lock.json")
SRT_PACKAGE = "@anthropic-ai/sandbox-runtime"
NPM_CI = ("ci", "--ignore-scripts", "--no-audit", "--no-fund")
SRT_NODE = "22.12.0"
# The prefix of npm's error lines, the key words of the lines that npm writes before the summary of
# an error, and the start of the last line, which names npm's log file.
NPM_ERROR = "npm error"
NPM_KEYS = ("code ", "syscall ", "errno ", "file ", "path ", "dest ")
NPM_LOG = "A complete log of this run can be found in:"
DOCTOR = "harness doctor"
JOBS = ("kaimon", "julia-update", "claude-autocommit")
# The directory below the home directory of the Seatbelt profiles of the jobs of jobsandbox.JOBS,
# which the plists name; no session can write below ~/.config.
SANDBOX = ".config/research-harness/sandbox"
# The directory below the home directory that kaimon's plist puts first on the job's PATH, and the
# shim that the run installs there, as a path of the clone.
SHIMS = jobsandbox.SHIMS.removeprefix("~/")
PS_SHIM = jobsandbox.PS_SHIM.relative_to(REPO)
# The directory below the home directory that POCL_CACHE_DIR of kaimon's plist and unit names:
# Kaimon's profile lets the job write below ~/.cache/kaimon and not PoCL's default ~/.cache/pocl.
POCL_CACHE = ".cache/kaimon/pocl"
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
    `command` on the PATH (or `marker` below the home directory), `need` the component or frontend
    that needs it ("" for every machine), `version` the arguments that print its version (none
    where any version meets it), the Homebrew `brew` formula, the Ubuntu `apt` packages (the first
    one's candidate counts), the vendor's `installer` and the `upgrade` line below its minimum, the
    line that names the fix (`stuck`) when the tool is still below its minimum after that line, the
    tool whose installer brings it (`comes_with`), the `systems` it runs on, and the line that
    `by_hand` prints where nothing installs it."""

    name: str
    command: str = ""
    need: str = ""
    version: tuple[str, ...] = ()
    brew: str = ""
    apt: tuple[str, ...] = ()
    installer: str = ""
    upgrade: str = ""
    stuck: str = ""
    comes_with: str = ""
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
    Tool("chezmoi", "chezmoi", need="dotfiles", brew="chezmoi", apt=("chezmoi",)),
    Tool("Claude Code", "claude", need="claude", installer=CLAUDE),
    Tool("OpenCode", "opencode", need="opencode", brew="anomalyco/tap/opencode-v2", installer=OPENCODE),
    Tool("oh-my-pi", "omp", need="omp", brew="can1357/tap/omp", installer=OMP),
    Tool(
        "Antigravity",
        need="antigravity",
        marker=".gemini",
        by_hand="install the Antigravity desktop app from https://antigravity.google/ and start it once, "
        "then run harness install --apply",
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
    `harness`, the `path` that `setup` started with, before the directories of EXTRA_PATH, the
    user's `login_shell`, and the `sleep` of the token step's wait."""

    system: str
    arch: str
    distro: str
    home: pathlib.Path
    env: Mapping[str, str]
    clone: pathlib.Path
    harness: tuple[str, ...]
    path: str = ""
    login_shell: str = ""
    sleep: Callable[[float], None] = time.sleep

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
    """The steps in their order, the lines that the user does by hand, `harness doctor`, which
    comes after both, and the `export PATH=…` line of the directories that the PATH lacks, "" when
    it lacks none. `head` counts the steps before which `setup` puts the writes of the profile and
    the model tables: the clone of ~/.claude, or none."""

    doctor: Doctor
    steps: list[Step] = dataclasses.field(default_factory=list[Step])
    by_hand: list[str] = dataclasses.field(default_factory=list[str])
    path_line: str = ""
    head: int = 0


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
    # The clone runs first, while a clean ~/.claude is still missing or empty: a later step, such
    # as a vendor installer, may write below it.
    claude = machine.home / ".claude"
    url = loaded.claude_remote
    if "jobs" in choice.components and url and not (claude / ".git").exists():
        result.steps.append(Step(f"git clone {url} {claude}", lambda: cloned(machine, url, claude)))
    result.head = len(result.steps)
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
    if missing := missing_path(machine, choice):
        result.path_line = 'export PATH="' + "".join(f"$HOME/{d}:" for d in missing) + '$PATH"'
        result.by_hand.append(PATH_BY_HAND + result.path_line)
    srt_step(machine, choice, result)
    harness_steps(machine, choice, loaded, env, result)
    return result


def missing_path(machine: Machine, choice: profile_module.Setup) -> list[str]:
    """The directories of EXTRA_PATH, in their order, that `choice` puts programs into and that
    the PATH that `setup` started with (`machine.path`) lacks: ~/.local/bin on every machine,
    ~/.juliaup/bin and ~/.julia/bin with `julia`, and ~/.opencode/bin with `opencode` on Linux,
    where the OpenCode installer runs; Homebrew installs OpenCode on macOS."""
    used = {
        ".local/bin": True,
        ".juliaup/bin": "julia" in choice.components,
        ".julia/bin": "julia" in choice.components,
        ".opencode/bin": "opencode" in choice.frontends and machine.system == "Linux",
    }
    have = {p.rstrip("/") for p in machine.path.split(os.pathsep) if p}
    return [d for d in EXTRA_PATH if used[d] and str(machine.home / d) not in have]


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
    if formulas:
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
    rest = [(t, s) for t, s in needed if not t.brew]
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
        elif release is not None and tool.name in TREES:
            programs = TREES[tool.name]
            releases.append(
                Step(
                    f"install {tool.command} {release.version} from {release.url} into "
                    f"~/{TREE_ROOT / tool.command / release.version}, linked as "
                    f"{', '.join(programs)} in ~/.local/bin, if its sha256 is {release.sha256}",
                    lambda program=tool.command, p=programs, r=release: install_tree(machine, program, p, r),
                )
            )
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


def srt_step(machine: Machine, choice: profile_module.Setup, result: Plan) -> None:
    """With any frontend chosen, the step that installs srt from the package and lockfile of SRT
    (`install_srt`), unless the tree of that lockfile is in place (`srt_installed`). It finds npm
    and node when it runs, so that a Node.js that an earlier step installs serves it."""
    if not any(f in frontends.FRONTENDS for f in choice.frontends):
        return
    version = srt_version()
    if srt_installed(machine.home, version):
        return
    result.steps.append(
        Step(
            f"npm {' '.join(NPM_CI)} with {SRT / 'package-lock.json'} into "
            f"~/{TREE_ROOT / 'srt' / version}, linked as srt in ~/.local/bin, "
            f"with Node.js {SRT_NODE} or later",
            lambda: install_srt(machine, version),
        )
    )


def srt_version(source: pathlib.Path = SRT) -> str:
    """The version of srt that the package.json of `source` names, an exact version; anything else
    exits 2, naming the file and the value."""
    path = source / "package.json"
    dependencies = jsonio.load(path).get("dependencies")
    value = (
        cast("dict[str, object]", dependencies).get(SRT_PACKAGE) if isinstance(dependencies, dict) else None
    )
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise HarnessError(f"{path}: dependencies.{SRT_PACKAGE} is {value!r}, not an exact version")
    return value


def srt_installed(home: pathlib.Path, version: str) -> bool:
    """Whether srt/<version>/ below the tree root holds the bytes of the lockfile of SRT and
    node_modules/.bin/srt, and ~/.local/bin/srt is a link to that program."""
    target = home / TREE_ROOT / "srt" / version
    program = target / "node_modules" / ".bin" / "srt"
    link = home / ".local" / "bin" / "srt"
    try:
        same = (target / "package-lock.json").read_bytes() == (SRT / "package-lock.json").read_bytes()
        return same and program.exists() and link.is_symlink() and link.readlink() == program
    except OSError:
        return False


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
    jobs = "jobs" in choice.components
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
    if "claude" in choice.frontends:
        steps.append(Step("harness trust --apply", trust(machine, env)))
    if jobs:
        job_steps(machine, loaded, env, result)
    if "julia" in choice.components:
        # With the jobs, the job steps start the Kaimon server, which writes its key a moment later.
        reads = TOKEN_READS if jobs else 1
        wait = f", reading it once a second for up to {TOKEN_READS} s until it holds a key" if jobs else ""
        steps.append(
            Step(
                "write ~/.config/kaimon/auth-token, mode 600, from the first key of "
                f"~/.config/kaimon/config.json, when that file exists and the token does not{wait}",
                lambda: kaimon_token(machine.home, reads, machine.sleep),
            )
        )


def trust(machine: Machine, env: Mapping[str, str]) -> Action:
    """`harness trust --apply`, once Claude Code has written ~/.claude.json at its first start;
    before that, the step by hand. The harness never writes a state file that Claude Code has not
    made, and an untrusted root costs a dialog, not a refusal."""
    run = command(machine, [*machine.harness, "trust", "--apply"], env)

    def act() -> str | None:
        state = machine.home / ".claude.json"
        if not state.exists():
            print(f"{state} does not exist yet: start claude once, then run harness trust --apply")
            return None
        return run()

    return act


def job_steps(machine: Machine, loaded: profile_module.Profile, env: Mapping[str, str], result: Plan) -> None:
    """The jobs, as the dotfiles kit's services step does them: the two copies in ~/.local/bin,
    then the launch agents or the systemd user units, rendered and loaded; on macOS each job of
    jobsandbox.JOBS has its Seatbelt profile rendered into SANDBOX before its plist, and the Kaimon
    job has the `ps` shim installed into SHIMS, mode 755, before its profile. On both systems one
    step creates POCL_CACHE, the directory of POCL_CACHE_DIR in Kaimon's plist and unit, before
    the Kaimon job is loaded. Without a `claude_remote`, no launch agent or unit of the autocommit
    job is rendered or loaded, because launchd loads every plist of ~/Library/LaunchAgents at the
    next login; a line by hand names the key."""
    autocommit = bool(loaded.claude_remote)
    if not autocommit:
        result.by_hand.append(
            "the autocommit job of ~/.claude: set claude_remote in the profile to the URL of your "
            "~/.claude repository, then run harness setup again"
        )
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
        for job in (j for j in JOBS if autocommit or j != "claude-autocommit"):
            label = f"{loaded.launchd_prefix}.{job}"
            plist = agents / f"{label}.plist"
            if job == "kaimon":
                result.steps.append(pocl_step(machine))
                # The `ps` of the directory that kaimon's plist puts first on the job's PATH, in
                # place before the load.
                shim = machine.home / SHIMS / PS_SHIM.name
                result.steps.append(
                    Step(
                        f"install -m 755 {machine.clone / PS_SHIM} {shim}",
                        lambda t=shim: copy(machine.clone / PS_SHIM, t, 0o755),
                    )
                )
            if job in jobsandbox.JOBS:
                # The plist starts the job under this profile, so it is in place before the load.
                sb = machine.home / SANDBOX / f"{job}.sb"
                result.steps.append(
                    Step(
                        f"harness render sandbox/{job}.sb > {sb}",
                        lambda j=job, t=sb: render(machine, f"sandbox/{j}.sb", t, env),
                    )
                )
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
    for unit in (u for u in UNITS if autocommit or not u.startswith("claude-autocommit.")):
        result.steps.append(
            Step(
                f"harness render systemd/{unit} > {units / unit}",
                lambda u=unit: render(machine, f"systemd/{u}", units / u, env),
            )
        )
    result.steps.append(pocl_step(machine))
    systemctl = machine.which("systemctl") or "systemctl"
    enabled = [u for u in ENABLED if autocommit or not u.startswith("claude-autocommit.")]
    for words in (["daemon-reload"], ["enable", "--now", *enabled], ["restart", *enabled]):
        result.steps.append(
            Step(f"systemctl --user {' '.join(words)}", command(machine, [systemctl, "--user", *words]))
        )
    if not lingers(machine):
        result.by_hand.append('keep the jobs running after logout: sudo loginctl enable-linger "$USER"')


def pocl_step(machine: Machine) -> Step:
    """The step that creates POCL_CACHE below the home directory, one directory at a time, each
    directory that it creates with mode 700 and each that exists as it is."""
    target = machine.home / POCL_CACHE

    def make() -> str | None:
        d = machine.home
        try:
            for part in pathlib.PurePath(POCL_CACHE).parts:
                d /= part
                d.mkdir(mode=0o700, exist_ok=True)
        except OSError as e:
            return f"cannot create {e.filename}: {e.strerror}"
        return None

    return Step(f"mkdir -p {target}, each new directory mode 700", make)


def lingers(machine: Machine) -> bool:
    """Whether `loginctl show-user <user> -p Linger` exits 0 and prints the line `Linger=yes`. A
    loginctl that is missing, fails, runs out of time or prints no `Linger=` line counts as no, so
    that the plan prints the lingering line; so does a uid with no user name, as in a container
    whose uid has no `passwd` entry."""
    loginctl = machine.which("loginctl")
    if loginctl is None:
        return False
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return False
    try:
        p = subprocess.run(
            [loginctl, "show-user", user, "-p", "Linger"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(machine.env),
            timeout=TIMEOUT,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return False
    return p.returncode == 0 and re.search(r"^Linger=yes$", p.stdout, re.MULTILINE) is not None


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
    data = checked_download(release, redirect)
    if isinstance(data, str):
        return data
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


def checked_download(release: Release, redirect: tuple[str, str]) -> bytes | str:
    """The bytes of `release`, downloaded with one redirect to `redirect` and no other, when their
    sha256 is the pinned one; else the text that says why the step fails."""
    try:
        with urllib.request.build_opener(Redirects(redirect)).open(release.url, timeout=TIMEOUT) as response:
            data = cast("bytes", response.read())
    except (OSError, ValueError, http.client.HTTPException, HarnessError) as e:
        return f"cannot download {release.url}: {e}"
    got = hashlib.sha256(data).hexdigest()
    if got != release.sha256:
        return f"{release.url} has sha256 {got}, not the pinned {release.sha256}; nothing is installed"
    return data


def install_tree(
    machine: Machine,
    command: str,
    programs: Sequence[str],
    release: Release,
    *,
    redirect: tuple[str, str] = REDIRECT,
) -> str | None:
    """Download `release`, a .tar.xz with one top-level directory, check its sha256, unpack it whole
    with tarfile's `data` filter into ~/.local/share/research-harness/<command>/<version>/, link
    each of `programs` in ~/.local/bin to the tree's bin/, and remove the trees of other versions.
    The archive unpacks into a scratch directory beside <command>/ first: a download that fails, a
    sha256 that differs, an absolute member, a member that the filter refuses, a link that leaves
    the tree, a directory in ~/.local/bin of a program's name or a link that cannot be made writes
    nothing below <command>/ and nothing in ~/.local/bin. A link replaces a file of its name in
    ~/.local/bin, as `install_release` replaces its program."""
    data = checked_download(release, redirect)
    if isinstance(data, str):
        return data
    root = machine.home / TREE_ROOT
    base, target = root / command, root / command / release.version
    try:
        root.mkdir(parents=True, exist_ok=True)
        scratch = pathlib.Path(tempfile.mkdtemp(prefix=f".{command}-unpack-", dir=root))
    except OSError as e:
        return f"cannot create a directory below {root}: {e.strerror}"
    links = [machine.home / ".local" / "bin" / program for program in programs]
    parts = [link.with_name(link.name + ".part") for link in links]
    made: list[pathlib.Path] = []
    try:
        tree = unpacked_tree(data, release.url, scratch, programs)
        if isinstance(tree, str):
            return tree
        failure = made_links(links, parts, [target / "bin" / program for program in programs], made)
        if failure is not None:
            return failure
        try:
            base.mkdir(exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            tree.rename(target)
            for part, link in zip(parts, links, strict=True):
                part.replace(link)
            for other in base.iterdir():
                if other.name != release.version:
                    shutil.rmtree(other)
        except OSError as e:
            return f"cannot install the tree of {release.url} into {target}: {e.strerror or e}"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        for part in made:
            if part.is_symlink():
                part.unlink()
    return None


def unpacked_tree(
    data: bytes, url: str, scratch: pathlib.Path, programs: Sequence[str]
) -> pathlib.Path | str:
    """The one top-level directory of the .tar.xz `data` from `url`, unpacked with tarfile's `data`
    filter into `scratch`, when it holds bin/<program> for each of `programs` and no link in it
    leaves it; else the line that says why nothing is installed."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tar:
            # On POSIX the data filter strips the leading / of an absolute member and unpacks it
            # inside the scratch directory, so the name check refuses it first.
            absolute = [info.name for info in tar.getmembers() if info.name.startswith("/")]
            if absolute:
                return f"{url} holds the absolute member {absolute[0]}; nothing is installed"
            tar.extractall(scratch, filter="data")
    except (OSError, tarfile.TarError) as e:
        return f"cannot unpack {url}: {e}; nothing is installed"
    tops = list(scratch.iterdir())
    tree = tops[0] if len(tops) == 1 else scratch
    missing = [p for p in programs if not (tree / "bin" / p).is_file()]
    if len(tops) != 1 or missing:
        wanted = ", ".join(f"bin/{p}" for p in programs)
        return f"{url} holds no top-level directory with {wanted}; nothing is installed"
    # The data filter keeps each link inside the scratch directory, the parent of the tree, and
    # writes its target in normal form, with `..` only at its start. A link stays inside the tree
    # after the tree moves to its version when its leading `..` climb no higher than the link's own
    # directory; the rule reads the target as written, so a target that climbs out and comes back
    # by the tree's top-level name is refused too.
    for path in tree.rglob("*"):
        if path.is_symlink():
            target = path.readlink().parts
            ups = next((i for i, part in enumerate(target) if part != ".."), len(target))
            if ups > len(path.relative_to(tree).parts) - 1:
                name = path.relative_to(scratch)
                return f"{url} holds the link {name}, which leaves the tree; nothing is installed"
    return tree


def made_links(
    links: Sequence[pathlib.Path],
    parts: Sequence[pathlib.Path],
    targets: Sequence[pathlib.Path],
    made: list[pathlib.Path],
) -> str | None:
    """Make each of `parts` a symbolic link to its entry of `targets`, beside its entry of `links`,
    which it replaces later, and append each link made to `made`; None, or the line that says why
    nothing is installed: a directory at a link, or a link that cannot be made. The links come
    before the tree moves, so that a failure here leaves the tree as it was, and the caller removes
    the links of `made`."""
    taken = [link for link in links if link.is_dir() and not link.is_symlink()]
    if taken:
        return f"{taken[0]} is a directory, not a link; nothing is installed"
    for part, target in zip(parts, targets, strict=True):
        try:
            part.parent.mkdir(parents=True, exist_ok=True)
            part.unlink(missing_ok=True)
            part.symlink_to(target)
            made.append(part)
        except OSError as e:
            return f"cannot make the link {part}: {e.strerror or e}; nothing is installed"
    return None


def install_srt(machine: Machine, version: str) -> str | None:
    """Install srt `version` from the package.json and package-lock.json of SRT: copy both into a
    scratch directory beside srt/ below the tree root, run `npm ci --ignore-scripts --no-audit
    --no-fund` there with the npm of the PATH, then move the directory to srt/<version>/, link
    ~/.local/bin/srt to its node_modules/.bin/srt, and remove the directories of other versions and
    the links below srt/, keeping any other file there. No npm, a node below SRT_NODE or without a
    version, an npm that fails or makes no program, and a directory at ~/.local/bin/srt write
    nothing below srt/ and leave ~/.local/bin as it was; the scratch directory goes in every case.
    A file at the link is replaced, as `install_tree` does."""
    npm = machine.which("npm")
    if npm is None:
        return (
            f"npm is not on the PATH: srt needs Node.js {SRT_NODE} or later with its npm; "
            "nothing is installed"
        )
    node = machine.which("node")
    found = installed_version(machine, node, ("--version",)) if node else None
    if found is None or not meets(found, (SRT_NODE,)):
        return (
            f"srt {version} needs Node.js {SRT_NODE} or later, and the node of the PATH is "
            f"{found or 'missing or prints no version'}; nothing is installed"
        )
    root = machine.home / TREE_ROOT
    base, target = root / "srt", root / "srt" / version
    try:
        root.mkdir(parents=True, exist_ok=True)
        scratch = pathlib.Path(tempfile.mkdtemp(prefix=".srt-install-", dir=root))
    except OSError as e:
        return f"cannot create a directory below {root}: {e.strerror}"
    link = machine.home / ".local" / "bin" / "srt"
    part = link.with_name("srt.part")
    made: list[pathlib.Path] = []
    try:
        # The links come after npm: a failed npm leaves ~/.local/bin as it was.
        failure = npm_ci(machine, npm, SRT, scratch) or made_links(
            [link], [part], [target / "node_modules" / ".bin" / "srt"], made
        )
        if failure is not None:
            return failure
        try:
            base.mkdir(exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            scratch.rename(target)
            part.replace(link)
            remove_others(base, version)
        except OSError as e:
            return f"cannot install srt {version} into {target}: {e.strerror or e}"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        for p in made:
            if p.is_symlink():
                p.unlink()
    return None


def remove_others(base: pathlib.Path, version: str) -> None:
    """Remove each link and each directory in `base` but `version`; a file there, such as the
    .DS_Store that Finder writes, stays."""
    for other in base.iterdir():
        if other.is_symlink():
            other.unlink()
        elif other.is_dir() and other.name != version:
            shutil.rmtree(other)


def npm_ci(machine: Machine, npm: str, source: pathlib.Path, scratch: pathlib.Path) -> str | None:
    """Copy the package files of `source` into `scratch` and run `npm ci` of NPM_CI there; None when
    npm exits 0 and made node_modules/.bin/srt, else the line that says why nothing is installed,
    with the cause that `npm_cause` reads from npm's stderr."""
    for name in SRT_FILES:
        try:
            shutil.copyfile(source / name, scratch / name)
        except OSError as e:
            return f"cannot copy {source / name} into {scratch}: {e.strerror or e}; nothing is installed"
    try:
        p = subprocess.run(
            [npm, *NPM_CI],
            cwd=scratch,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            env=dict(machine.env),
            timeout=INSTALL_TIMEOUT,
            check=False,
        )
    except OSError as e:
        return f"cannot run npm {' '.join(NPM_CI)} in {scratch}: {e.strerror or e}; nothing is installed"
    except subprocess.TimeoutExpired:
        return f"npm {' '.join(NPM_CI)} has no end after {INSTALL_TIMEOUT} s; nothing is installed"
    if p.returncode != 0:
        cause = npm_cause(p.stderr)
        said = f": {cause}" if cause else " with an empty stderr"
        return f"npm {' '.join(NPM_CI)} exits {p.returncode}{said}; nothing is installed"
    if not (scratch / "node_modules" / ".bin" / "srt").exists():
        return f"npm {' '.join(NPM_CI)} made no node_modules/.bin/srt; nothing is installed"
    return None


def npm_cause(stderr: str) -> str:
    """The cause of a failed npm in its stderr: the text of the `npm error code` line and the first
    `npm error` line of other text, joined with `; `. A bare `npm error` line, whose text is empty,
    is not read, and a line whose text starts with a key word of NPM_KEYS or is the log path is no
    such line; nor is an `npm warn` or `npm notice` line. With neither line, the last line of any
    kind that is not the log path, else the log path; "" for an empty stderr. npm writes its key
    lines first, then a summary and its detail, and the log path last."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    errors = [line.removeprefix(NPM_ERROR).strip() for line in lines if line.startswith(f"{NPM_ERROR} ")]
    code = next((text for text in errors if text.startswith("code ")), "")
    summary = next((text for text in errors if not text.startswith((*NPM_KEYS, NPM_LOG))), "")
    if code or summary:
        return "; ".join(text for text in (code, summary) if text)
    rest = [line for line in lines if not line.removeprefix(NPM_ERROR).strip().startswith(NPM_LOG)]
    return (rest or lines or [""])[-1]


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
    part.chmod(mode)  # not private: each caller gives 0755 or 0644
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


def kaimon_token(
    home: pathlib.Path, reads: int = 1, sleep: Callable[[float], None] = time.sleep
) -> str | None:
    """Write ~/.config/kaimon/auth-token, mode 600, from the first key of Kaimon's config.json,
    when that file exists and the token does not; otherwise print the step. The file is read up to
    `reads` times, with `sleep(1)` between two reads, until it holds a key: the Kaimon server
    writes its key a moment after it starts. A config.json that is no JSON fails the step with one
    read, and counts as no key with more."""
    directory = home / ".config" / "kaimon"
    token, config = directory / "auth-token", directory / "config.json"
    if token.exists():
        print(f"{token} exists; it is kept")
        return None
    key: str | None = None
    for n in range(reads):
        if n:
            sleep(1)
        try:
            key = first_key(config)
        except HarnessError as e:
            if reads == 1:
                return str(e)
            continue
        if key:
            break
    if not key:
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


def first_key(config: pathlib.Path) -> str | None:
    """The first item of `api_keys` of Kaimon's `config`, when it is a string that is not empty;
    None without the file. A file that is no JSON raises HarnessError."""
    if not config.is_file():
        return None
    keys = jsonio.load(config).get("api_keys")
    key = cast("list[object]", keys)[0] if isinstance(keys, list) and keys else None
    return key if isinstance(key, str) and key else None


def cloned(machine: Machine, url: str, target: pathlib.Path) -> str | None:
    """`git clone url target`, where `target` is missing or an empty directory. A `target` that
    holds files fails the step with the lines that move it aside and clone. A clone that fails
    leaves nothing below `target` and fails the step with the last line of git's stderr."""
    existed = target.is_dir()
    if target.exists() and (not existed or any(target.iterdir())):
        return (
            f"{target} holds files and is no git repository. Move it aside and clone it, then run "
            f"harness setup again:\n  mv {target} {target}.setup\n  git clone {url} {target}\n"
        )
    git = machine.which("git") or "git"
    try:
        p = subprocess.run(
            [git, "clone", url, str(target)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(machine.env),
            timeout=INSTALL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        failure = f"cannot run git clone: {e}"
    else:
        if p.returncode == 0:
            return None
        lines = [line for line in p.stderr.splitlines() if line.strip()]
        failure = lines[-1] if lines else f"git clone exits {p.returncode}"
    try:
        if existed:
            for child in target.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        elif target.exists():
            shutil.rmtree(target)
    except OSError as e:
        failure += f"\ncannot remove the partial clone at {e.filename}: {e.strerror}"
    return failure


# ---------------------------------------------------------------------- the questions ----

# The lines that `setup` prints before a question, the one place of their text: for each key of
# REQUIRED, what it holds and whether its answer is the same on every machine that shares the
# tree, in three lines at most; for the lists of frontends and components, what they are; for
# each frontend and each component, its description in the list; for `develop`, which machine it
# is for; and for `claude_remote`, what the URL is for. The explanations name no repository,
# organisation or person.
EXPLAINED: dict[str, tuple[str, ...]] = {
    "memory_project": (
        "A label, not a path: Claude Code keeps the tree's memory in ~/.claude/projects/<label>/memory.",
        "The same on every machine that shares one memory pool; usually the tree's path on the first",
        "machine with each / replaced by -.",
    ),
    "tree_agents": (
        "The directory of the tree instructions, which `harness install` copies into ~/.claude/.",
        "The same on every machine when written with ~; an absolute path differs with the home directory.",
    ),
    "org": (
        "The GitHub accounts and organisations, your own included, where a session may open and comment",
        "on pull requests and issues without a prompt: GitHub names, letters, digits and hyphens.",
        "The same on every machine.",
    ),
    "repository_roots": (
        "The directories that hold the tree's repositories; `harness leaks` searches the harness for the",
        "name of each directory below them. The same on every machine when written with ~.",
    ),
    "leak": (
        "The strings that must never appear in the harness repository, such as user names and host",
        "names; the item ~ stands for the path of the home directory.",
        "Mostly the same on every machine; add the user and host names of each machine.",
    ),
    "frontends": ("The agent programs whose configuration `harness install` writes; chosen per machine.",),
    "components": ("What `harness setup` installs and starts beside the frontends; chosen per machine.",),
    "develop": (
        "Only for a machine that changes the harness's own code: it adds the dev group of uv.lock, the",
        "tools that check the harness's Python code, such as ruff and basedpyright. Chosen per machine.",
    ),
    "claude": ("Claude Code, Anthropic's agent in the terminal",),
    "opencode": ("OpenCode, an open-source agent in the terminal",),
    "omp": ("oh-my-pi, an agent in the terminal",),
    "antigravity": ("Antigravity, Google's agent in a desktop app",),
    "julia": ("juliaup, Julia, fatou, Kaimon and the Julia environment of the harness's scripts",),
    "rtk": ("RTK, a proxy that shortens the output of shell commands",),
    "jq": ("jq, the command-line JSON processor",),
    "jobs": ("Kaimon, the Julia update and the autocommit of ~/.claude, as background jobs",),
    "dotfiles": ("chezmoi, which applies a repository of dotfiles",),
    "claude_remote": (
        "The URL of the git repository of ~/.claude, starting with https:// or git@: harness setup clones",
        "it into ~/.claude, and the autocommit job pushes to it. An empty answer: no autocommit job.",
        "The same on every machine.",
    ),
}
# The most lines that the explanation of a key of REQUIRED has.
EXPLAINED_LINES = 3


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
    """The names of `names` that the user picks by their numbers; an empty line keeps `current`.
    The list gives the explanation of `what` and the description of each name (EXPLAINED)."""
    print(f"The {what}:")
    for line in EXPLAINED[what]:
        print(line)
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}: {EXPLAINED[name][0]}")
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
    """The `[setup]` that the user chooses, with `current` as the answer to each empty line; the
    explanation of `develop` (EXPLAINED) comes before its question."""
    chosen_frontends = pick("frontends", frontends.FRONTENDS, current.frontends, ask)
    components = pick("components", profile_module.COMPONENTS, current.components, ask)
    for line in EXPLAINED["develop"]:
        print(line)
    return profile_module.Setup(
        frontends=chosen_frontends,
        components=components,
        develop=confirm(ask, "Develop the harness, with the dev group of uv.lock?", default=current.develop),
    )


def ask_remote(ask: Ask) -> str:
    """The URL of the ~/.claude repository, after the explanation of `claude_remote` (EXPLAINED),
    or "" for an empty line. An answer that starts with neither of `profile.REMOTE_STARTS` prints
    one line and is asked again."""
    for line in EXPLAINED["claude_remote"]:
        print(line)
    starts = " or ".join(profile_module.REMOTE_STARTS)
    while answer := ask_line(ask, f"claude_remote, a URL that starts with {starts}, or empty for none []: "):
        if answer.startswith(profile_module.REMOTE_STARTS):
            return answer
        print(f"  {answer!r} starts with neither {starts}; give such a URL, or an empty line")
    return ""


def with_remote(text: str, url: str) -> str:
    """The profile `text` with the line `claude_remote = <url>` first, where every key is a key
    of the top-level table."""
    return f"claude_remote = {toml_value(url)}\n{text}"


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
    value for an empty line. Before each question, the key's explanation (EXPLAINED). A list is
    read by `list_answer`, and an `org` item must be a GitHub account name (GITHUB_NAME); an
    answer that either refuses prints one line and is asked again."""
    text = example
    for key, kind in profile_module.REQUIRED.items():
        line = re.search(rf"^{key} = (.*)$", text, re.MULTILINE)
        if line is None:
            raise HarnessError(f"examples/profile.toml has no line `{key} = …`")
        for row in EXPLAINED[key]:
            print(row)
        if kind == profile_module.STRING:
            answer = ask_line(ask, f"{key}, {kind} [{line.group(1)}]: ")
            value = toml_value(answer) if answer else None
        else:
            value = None
            while answer := ask_line(
                ask,
                f"{key}, {kind}, separated by commas or as a TOML list; the answer replaces the example "
                f"list [{line.group(1)}]: ",
            ):
                items = list_answer(answer, nonempty=kind == profile_module.NONEMPTY)
                if (
                    key == "org"
                    and isinstance(items, tuple)
                    and (bad := [i for i in items if not profile_module.GITHUB_NAME.fullmatch(i)])
                ):
                    items = f"the item {bad[0]!r} is no GitHub account name; give the account names"
                if isinstance(items, tuple):
                    value = toml_value(items)
                    break
                print(f"  {items}")
        if value is not None:
            text = text[: line.start(1)] + value + text[line.end(1) :]
    return text


def list_answer(answer: str, *, nonempty: bool) -> tuple[str, ...] | str:
    """The items of the answer `answer` to a list question, or the line that refuses it. An answer
    that starts with `[` is a TOML list of strings, read as the value of a key, and refused when an
    item is empty; any other answer is items separated by commas, each with its spaces trimmed,
    and an empty item dropped. An item that holds a bracket or a quote is refused, naming it, and
    so is an answer with no item when `nonempty`."""
    if answer.startswith("["):
        try:
            value = cast("dict[str, object]", tomllib.loads("v = " + answer))["v"]
        except tomllib.TOMLDecodeError:
            value = None
        if not isinstance(value, list) or not all(isinstance(v, str) for v in cast("list[object]", value)):
            return f"{answer!r} is no TOML list of strings; give one, or items separated by commas"
        items = tuple(cast("list[str]", value))
        if "" in items:
            return f"{answer!r} holds an empty item; give the items without it"
    else:
        items = tuple(a.strip() for a in answer.split(",") if a.strip())
    if bad := [item for item in items if any(c in item for c in "[]\"'")]:
        return f"the item {bad[0]!r} holds a bracket or a quote; give the items without them"
    if nonempty and not items:
        return f"{answer!r} holds no item; give one item or more"
    return items


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
        if (
            "jobs" in choice.components
            and not loaded_from(text, machine.home).claude_remote
            and (url := ask_remote(ask))
        ):
            text = with_remote(text, url)
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
    the_plan.steps[the_plan.head : the_plan.head] = before
    zshrc = machine.home / ".zshrc"
    if (
        the_plan.path_line
        and not options.yes
        and pathlib.PurePath(machine.login_shell).name == "zsh"
        and not zshrc.is_symlink()
        and confirm(ask, f"Append the line {the_plan.path_line} to {zshrc}?")
    ):
        the_plan.by_hand.remove(PATH_BY_HAND + the_plan.path_line)
        line = the_plan.path_line
        the_plan.steps.append(
            Step(f"append to {zshrc}: {PATH_COMMENT}, {line}", lambda: appended(zshrc, line))
        )
    show(machine, choice, the_plan)
    if options.dry_run:
        print("\nharness setup: the dry run changes nothing.")
        return 0
    if not options.yes and not confirm(ask, "Run the plan?"):
        print("harness setup: nothing is changed.")
        return 0
    return run(the_plan)


def appended(zshrc: pathlib.Path, line: str) -> str | None:
    """Append PATH_COMMENT and `line` to `zshrc`, after an empty line where it holds text; nothing
    where a line of `zshrc` is `line` already, so that a second run appends no second block."""
    try:
        held = zshrc.read_text(encoding="utf-8", errors="replace") if zshrc.is_file() else ""
        if line in (x.strip() for x in held.splitlines()):
            return None
        gap = "\n" if zshrc.is_file() and zshrc.stat().st_size else ""
        with zshrc.open("a", encoding="utf-8") as f:
            f.write(f"{gap}{PATH_COMMENT}\n{line}\n")
    except OSError as e:
        return f"cannot append to {zshrc}: {e.strerror}"
    return None


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


def passwd_shell() -> str:
    """The login shell of the running user, as the passwd entry names it; "" for a uid with no
    entry."""
    try:
        return pwd.getpwuid(os.getuid()).pw_shell
    except KeyError:
        return ""


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
        path=os.environ.get("PATH", ""),
        login_shell=passwd_shell(),
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
        "vendor installers, the clone of claude_remote into ~/.claude (with jobs), harness install "
        "--apply, core.hooksPath, harness trust --apply (with claude), the jobs, the Kaimon token and "
        "harness doctor. A failed step exits 2; a FAIL of harness doctor exits 1.",
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
# Each apt candidate of the fake apt-cache meets its tool's minimum, so a run installs no pinned
# release unless a case changes the fake.
LINUX_FAKES = {
    "apt-cache": 'case "$2" in nodejs) echo "  Candidate: 22.22.0+dfsg-1";; '
    '*) echo "  Candidate: 9.9.9-1";; esac',
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
        """The scratch machine: it started with the PATH of the fake programs alone, has no login
        shell, and its token step does not sleep."""
        return Machine(
            system=system,
            arch=arch or SYSTEMS.get(system, ("",))[0],
            distro=distro or ("ubuntu" if system == "Linux" else ""),
            home=self.home,
            env={"PATH": extended(self.home, str(self.bin)), "HOME": str(self.home)},
            clone=self.clone,
            harness=(str(self.bin / "harness"),),
            path=str(self.bin),
            sleep=lambda _: None,
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


def scratch(tmp: pathlib.Path, name: str, fakes: Mapping[str, str], *, srt: bool = True) -> Scratch:
    """A new Scratch below `tmp`, with the fake programs `fakes`, the real sh, bash and git, the
    example profile and model tables, and with `srt` the tree of the shipped srt lockfile linked
    (`installed_srt`), so that a plan with a frontend holds no srt step and a run calls no npm."""
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
    (s.home / ".claude.json").write_text("{}\n", encoding="utf-8")
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
    (s.clone / PS_SHIM).parent.mkdir(parents=True)
    (s.clone / PS_SHIM).write_text("#!/bin/sh\n# ps\n", encoding="utf-8")
    subprocess.run(
        [shutil.which("git") or "git", "init", "-q", str(s.clone)],
        capture_output=True,
        timeout=TIMEOUT,
        check=True,
    )
    if srt:
        installed_srt(s.home, srt_version())
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
    chezmoi = {
        key: (r.version, r.url.rsplit("/", 1)[-1], r.sha256) for key, r in pins.releases["chezmoi"].items()
    }
    case(
        f"setup/tools.toml pins chezmoi 2.73.2 for both Linux architectures: {chezmoi}",
        ok=chezmoi
        == {
            "linux-x86_64": (
                "2.73.2",
                "chezmoi_2.73.2_linux_amd64.tar.gz",
                "4d7bd8072f15373d5f5c801209bac218527452c8e54f9ae46ba6c5bd4a6eca41",
            ),
            "linux-aarch64": (
                "2.73.2",
                "chezmoi_2.73.2_linux_arm64.tar.gz",
                "db92b343a32cade0b1d4ff5e30da54c5156f7a580349281e583a5402c57c7bcf",
            ),
        },
    )
    node = pins.releases.get("Node.js", {})
    versions = {r.version for r in node.values()}
    version = next(iter(versions), "")
    arches = {"linux-x86_64": "x64", "linux-aarch64": "arm64"}
    case(
        "setup/tools.toml pins one Node.js 24 release for both Linux architectures, the .tar.xz of "
        f"nodejs.org/dist/: { {key: r.url for key, r in node.items()} }",
        ok=set(node) == set(arches)
        and len(versions) == 1
        and version.startswith("24.")
        and all(
            r.url == f"https://nodejs.org/dist/v{version}/node-v{version}-linux-{arches[key]}.tar.xz"
            for key, r in node.items()
        ),
    )
    shasums = f"https://nodejs.org/dist/v{version}/SHASUMS256.txt"
    case(
        f"setup/tools.toml names {shasums}, the file that the Node.js sha256s come from",
        ok=bool(version) and shasums in PINS.read_text(encoding="utf-8"),
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
    s = claude_repository(scratch(tmp, "macos", MACOS_FAKES))
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
    brew = [c for c in calls if c.startswith("brew install ")]
    wanted = ("gh", "node", "actionlint", "gitleaks", "jolars/tap/fatou", "rtk", "jq", "chezmoi")
    case(
        f"one brew install line holds each missing tool, and not git, which is on the PATH: {brew}",
        ok=len(brew) == 1
        and all(w in brew[0].split() for w in (*wanted, "anomalyco/tap/opencode-v2", "can1357/tap/omp"))
        and "git" not in brew[0].split(),
    )
    case("no cask is installed", ok=not any("--cask" in c for c in calls))
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
        ok=order == ["install", "trust", *["render"] * 5, "doctor"]
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
    case(
        "the output names the steps that the user does by hand, and the Antigravity line says to run "
        "harness install --apply after the app's first start",
        ok="https://antigravity.google/ and start it once, then run harness install --apply" in out,
    )
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
    brews = [c for c in s.calls() if c.startswith("brew install ")]
    runs = 2
    case(
        f"the next run starts again from the first step and runs to the end: {code} {brews}",
        ok=code == "0" and len(brews) == runs and "harness doctor" in s.calls(),
    )
    s.fake("gitleaks", 'echo "8.21.0"')
    s.fake("node", 'echo "v22.12.0"')
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
        f"gitleaks, actionlint, RTK and chezmoi install from their pinned releases: {releases}",
        ok=releases == ["actionlint", "gitleaks", "rtk", "chezmoi"],
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
    page = (REPO / "docs" / "src" / "setup-reference.md").read_text(encoding="utf-8").splitlines()
    case(
        "the installers of Claude Code, oh-my-pi and juliaup are the lines of setup-reference.md",
        ok=all(line in page for line in (installers[0], installers[2], installers[3])),
    )
    s.fake("gitleaks", 'echo "8.21"')
    s.fake("node", 'echo "v22.12.0"')
    s.fake("actionlint", 'echo "1.7.12"')
    lines = shows(machine, everything, s.options(), pins)
    planned = " ".join(lines)
    case(
        f"a tool at its minimum is skipped: gitleaks 8.21, Node.js 22.12.0, actionlint 1.7.12: {lines[:3]}",
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
    s = claude_repository(scratch(tmp, "linux-jobs", LINUX_FAKES))
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
    case(
        "without loginctl, the linger line is printed by hand", ok="loginctl enable-linger" in out.getvalue()
    )
    user = pwd.getpwuid(os.getuid()).pw_name
    for label, body, printed in (
        ("Linger=no", 'echo "Linger=no"', True),
        ("Linger=yes", 'echo "Linger=yes"', False),
        ("Linger=yes and exit 1", 'echo "Linger=yes"; exit 1', True),
        ("no Linger= line", 'echo "Name=someone"', True),
        ("Linger=yes inside a longer line", 'echo "XLinger=yes"; echo "Linger=yesterday"', True),
    ):
        s.fake("loginctl", body)
        s.log.unlink(missing_ok=True)
        by_hand = plan(machine, jobs, loaded, s.options(), pins).by_hand
        asked = [c for c in s.calls() if c.startswith("loginctl")]
        case(
            f"a loginctl that prints {label}: the linger line is "
            f"{'printed' if printed else 'not printed'} by hand: {by_hand} {asked}",
            ok=any("loginctl enable-linger" in line for line in by_hand) == printed
            and asked == [f"loginctl show-user {user} -p Linger"],
        )
    # A loginctl that cannot start: its interpreter does not exist.
    (s.bin / "loginctl").write_text(f"#!{s.root / 'no-such-shell'}\necho Linger=yes\n", encoding="utf-8")
    by_hand = plan(machine, jobs, loaded, s.options(), pins).by_hand
    case(
        f"a loginctl that cannot start: the linger line is printed by hand: {by_hand}",
        ok=any("loginctl enable-linger" in line for line in by_hand),
    )
    # A uid with no user name, as in a container whose uid has no passwd entry: loginctl reads
    # Linger=yes, but it is not asked, and the line is printed.
    s.fake("loginctl", 'echo "Linger=yes"')
    s.log.unlink(missing_ok=True)
    try:
        with mock.patch.object(pwd, "getpwuid", side_effect=KeyError("getpwuid(): uid not found")):
            by_hand = plan(machine, jobs, loaded, s.options(), pins).by_hand
    except KeyError as e:
        by_hand = [f"KeyError: {e}"]
    asked = [c for c in s.calls() if c.startswith("loginctl")]
    case(
        f"a uid with no user name: loginctl is not asked, the linger line is printed by hand: "
        f"{by_hand} {asked}",
        ok=any("loginctl enable-linger" in line for line in by_hand) and not asked,
    )


def node_plan_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """Node.js below its minimum in apt, on each Linux architecture: the step of its pinned release,
    and no line by hand."""
    s = scratch(tmp, "node-plan", LINUX_FAKES)
    s.fake(
        "apt-cache",
        'case "$2" in nodejs) echo "  Candidate: 18.19.1+dfsg-6";; *) echo "  Candidate: 9.9-1";; esac',
    )
    loaded = profile_module.load(s.profile, home=str(s.home))
    for arch in ("x86_64", "aarch64"):
        node_plan = plan(s.machine("Linux", arch), profile_module.Setup(), loaded, s.options(), pins)
        node = [x.show for x in node_plan.steps if x.show.startswith("install node ")]
        version = pins.releases["Node.js"][f"linux-{arch}"].version
        case(
            f"{arch}: Node.js below its minimum in apt installs its pinned release, and is no line by hand: "
            f"{node}",
            ok=len(node) == 1
            and node[0].startswith(f"install node {version} ")
            and not any("Node.js" in line for line in node_plan.by_hand),
        )


def plan_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """What the choices, the installed programs and the profile put into the plan."""
    # On macOS, with every tool of the choice installed, the plan needs no Homebrew.
    s = scratch(tmp, "plan-no-brew", {k: v for k, v in MACOS_FAKES.items() if k != "brew"})
    for program in ("gh", "shellcheck", "rsync"):
        s.fake(program, "exit 0")
    for program in ("node", "actionlint", "gitleaks"):
        s.fake(program, 'echo "99.0.0"')
    lines = shows(s.machine(), profile_module.Setup(frontends=(), components=()), s.options(), pins)
    case(
        f"on macOS without brew, a choice whose tools are all installed plans no Homebrew step: {lines}",
        ok=not any(line.startswith(("exit 2", "brew ")) for line in lines),
    )
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
    (s.home / ".gemini").mkdir(parents=True)
    the_plan = plan(mac, profile_module.Setup(), loaded, options, pins)
    tools = [line for line in the_plan.by_hand if not line.startswith((PATH_BY_HAND, "the autocommit job"))]
    case(
        f"~/.gemini counts as installed, and no tool of Linux is a line by hand on macOS: {the_plan.by_hand}",
        ok=tools == [],
    )
    for d in (loaded.tree_agents, *loaded.repository_roots, s.home / ".config" / "opencode"):
        pathlib.Path(d).mkdir(parents=True, exist_ok=True)
    lines = shows(mac, profile_module.Setup(), options, pins)
    case(
        f"with every directory there, no mkdir step but Kaimon's PoCL cache: {lines[:2]}",
        ok=not any("mkdir" in x and POCL_CACHE not in x for x in lines),
    )
    s.fake(
        "apt-cache", 'case "$2" in chezmoi) echo "  Candidate: (none)";; *) echo "  Candidate: 9.9-1";; esac'
    )
    linux_plan = plan(linux, profile_module.Setup(), loaded, options, pins)
    release = pins.releases["chezmoi"]["linux-x86_64"]
    chezmoi = [step.show for step in linux_plan.steps if "chezmoi" in step.show]
    case(
        f"chezmoi without an apt candidate installs its pinned release into ~/.local/bin, and is no "
        f"line by hand: {chezmoi} {linux_plan.by_hand}",
        ok=any(
            step.show.startswith(f"install chezmoi {release.version} from {release.url} into ~/.local/bin")
            for step in linux_plan.steps
        )
        and release.version == "2.73.2"
        and not any("chezmoi" in line for line in linux_plan.by_hand),
    )
    aarch64 = [
        x.show
        for x in plan(s.machine("Linux", "aarch64"), profile_module.Setup(), loaded, options, pins).steps
    ]
    case(
        f"chezmoi has a pinned release on linux-aarch64 too: {[x for x in aarch64 if 'chezmoi' in x]}",
        ok=any(x.startswith("install chezmoi 2.73.2 ") for x in aarch64),
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
    code, out = attempt(mac, s.options(yes=False, dry_run=True), Asker(*[""] * 4), terminal=True, pins=pins)
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
        ("node", 'echo "v22.12.0"'),
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
            machine = Machine("Linux", "x86_64", "ubuntu", tmp / "h", {}, tmp, ())
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
    # A component that `[setup]` cannot choose, such as `iterm`, stops the run before its plan.
    s = scratch(tmp, "dry-unknown-component", MACOS_FAKES)
    text = s.profile.read_text(encoding="utf-8")
    s.profile.write_text(
        text.replace('components = ["julia"', 'components = ["iterm", "julia"', 1), encoding="utf-8"
    )
    code, out = attempt(s.machine(), s.options(dry_run=True), pins=pins)
    case(
        f"--yes --dry-run on a profile whose [setup] names iterm exits 2 with one line that names iterm "
        f"and the profile, and runs nothing: {code!r} {s.calls()}",
        ok='"iterm"' in s.profile.read_text(encoding="utf-8")
        and code.startswith("exit 2: ")
        and "\n" not in code
        and "'iterm'" in code
        and str(s.profile) in code
        and not s.calls(),
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


NODE = TREES["Node.js"]


def node_tree(version: str, extra: Sequence[tarfile.TarInfo] = ()) -> bytes:
    """A .tar.xz in the form of a nodejs.org release: one top-level directory that holds bin/node,
    a script that prints `v<version>`, the tree lib/node_modules/npm/, and bin/npm and bin/npx as
    links into it; then the members `extra`, each a file of `x` bytes or a link."""
    top = f"node-v{version}-linux-x64"
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:xz") as tar:
        for directory in (
            "",
            "/bin",
            "/lib",
            "/lib/node_modules",
            "/lib/node_modules/npm",
            "/lib/node_modules/npm/bin",
        ):
            info = tarfile.TarInfo(top + directory)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            tar.addfile(info)
        for member, body in (
            ("bin/node", f"#!/bin/sh\necho v{version}\n"),
            ("lib/node_modules/npm/bin/npm-cli.js", "#!/bin/sh\necho 11.6.2\n"),
            ("lib/node_modules/npm/bin/npx-cli.js", "#!/bin/sh\necho 11.6.2\n"),
        ):
            info = tarfile.TarInfo(f"{top}/{member}")
            info.size, info.mode = len(body), 0o755
            tar.addfile(info, io.BytesIO(body.encode()))
        for program in ("npm", "npx"):
            info = tarfile.TarInfo(f"{top}/bin/{program}")
            info.type, info.linkname = tarfile.SYMTYPE, f"../lib/node_modules/npm/bin/{program}-cli.js"
            tar.addfile(info)
        for info in extra:
            tar.addfile(info, io.BytesIO(b"x" * info.size) if info.isfile() else None)
    return data.getvalue()


def flat_tree() -> bytes:
    """A .tar.xz that holds bin/node, bin/npm and bin/npx and a lib/ directory at its top, with no
    top-level directory."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:xz") as tar:
        tar.addfile(member("lib/README"), io.BytesIO(b"x"))
        for program in NODE:
            info = member(f"bin/{program}")
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(b"x"))
    return data.getvalue()


def member(name: str, link: str = "") -> tarfile.TarInfo:
    """A tar member `name`: a file of one byte, or a symbolic link to `link`."""
    info = tarfile.TarInfo(name)
    if link:
        info.type, info.linkname = tarfile.SYMTYPE, link
    else:
        info.size = 1
    return info


def tree_cases(case: Case, tmp: pathlib.Path) -> None:
    """The Node.js release, a whole tree: unpacked below ~/.local/share/research-harness/node/
    <version>/ and linked into ~/.local/bin; a mismatch, an HTTP error and a second redirect write
    nothing below ~/.local; a second version replaces the first; a deep link that stays inside the
    tree installs."""
    good, newer = node_tree("24.11.1"), node_tree("24.12.0")
    deep = node_tree(
        "24.11.1", [member("node-v24.11.1-linux-x64/lib/node_modules/npm/bin/deep", "../../../../bin/node")]
    )
    files = {"/good.tar.xz": good, "/newer.tar.xz": newer, "/deep.tar.xz": deep}
    moved = {"/a.tar.xz": "/good.tar.xz", "/c.tar.xz": "/a.tar.xz"}
    with release_server(files, moved) as url:

        def release(path: str, data: bytes, version: str = "24.11.1") -> Release:
            return Release(version, f"{url}/{path}", hashlib.sha256(data).hexdigest())

        n = 0

        def machine() -> Machine:
            nonlocal n
            n += 1
            home = tmp / f"tree{n}"
            return Machine("Linux", "x86_64", "ubuntu", home, {}, tmp, ())

        m = machine()
        failure = install_tree(m, "node", NODE, release("good.tar.xz", good))
        tree = m.home / ".local" / "share" / "research-harness" / "node" / "24.11.1"
        links = [m.home / ".local" / "bin" / p for p in NODE]
        resolved = [link.resolve() for link in links]
        case(
            "the Node.js release unpacks its whole tree into ~/.local/share/research-harness/node/24.11.1/: "
            f"{failure}",
            ok=failure is None and (tree / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js").is_file(),
        )
        case(
            f"node, npm and npx in ~/.local/bin are links into the tree's bin/, and resolve: {resolved}",
            ok=all(link.is_symlink() for link in links)
            and all(link.readlink() == tree / "bin" / p for link, p in zip(links, NODE, strict=True))
            and resolved[1] == (tree / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js").resolve()
            and all(r.is_file() for r in resolved),
        )
        answer = subprocess.run(
            [str(links[0]), "--version"], capture_output=True, text=True, timeout=TIMEOUT, check=False
        ).stdout
        case(f"node --version through the link answers v24.11.1: {answer!r}", ok=answer == "v24.11.1\n")
        failure = install_tree(m, "node", NODE, release("newer.tar.xz", newer, "24.12.0"))
        versions = sorted(p.name for p in tree.parent.iterdir())
        case(
            f"a tree of another version replaces the first, and the links point at it: {failure} {versions}",
            ok=failure is None
            and versions == ["24.12.0"]
            and all(
                link.readlink() == tree.parent / "24.12.0" / "bin" / p
                for link, p in zip(links, NODE, strict=True)
            )
            and subprocess.run(
                [str(links[0]), "--version"], capture_output=True, text=True, timeout=TIMEOUT, check=False
            ).stdout
            == "v24.12.0\n",
        )

        failure = install_tree(m, "node", NODE, release("newer.tar.xz", newer, "24.12.0"))
        case(
            f"the tree of the same version again replaces itself: {failure}",
            ok=failure is None and (tree.parent / "24.12.0" / "bin" / "node").is_file(),
        )

        m = machine()
        failure = install_tree(m, "node", NODE, release("deep.tar.xz", deep))
        tree = m.home / ".local" / "share" / "research-harness" / "node" / "24.11.1"
        link = tree / "lib" / "node_modules" / "npm" / "bin" / "deep"
        case(
            f"a link four levels deep to ../../../../bin/node stays inside the tree and installs: {failure}",
            ok=failure is None and link.is_symlink() and link.resolve() == (tree / "bin" / "node").resolve(),
        )

        m = machine()
        (m.home / ".local" / "bin").mkdir(parents=True)
        (m.home / ".local" / "bin" / "node").write_text("#!/bin/sh\necho v18.19.1\n", encoding="utf-8")
        (m.home / ".local" / "bin" / "npm.part").write_text("left by a run that stopped\n", encoding="utf-8")
        failure = install_tree(m, "node", NODE, release("good.tar.xz", good))
        link = m.home / ".local" / "bin" / "node"
        case(
            f"a node file in ~/.local/bin is replaced by the link, as a release replaces its program, and a "
            f"left .part file is no obstacle: {failure}",
            ok=failure is None and link.is_symlink() and (m.home / ".local" / "bin" / "npm").is_symlink(),
        )

        bad = Release("24.11.1", f"{url}/good.tar.xz", hashlib.sha256(good + b"x").hexdigest())
        for label, the_release, redirect in (
            ("a sha256 that differs", bad, REDIRECT),
            ("an HTTP error", release("missing.tar.xz", good), REDIRECT),
            ("a second redirect", release("c.tar.xz", good), ("http", "127.0.0.1")),
            ("a redirect to another host", release("a.tar.xz", good), REDIRECT),
        ):
            m = machine()
            failure = install_tree(m, "node", NODE, the_release, redirect=redirect)
            case(
                f"{label}: the step fails and writes nothing below ~/.local: {failure}",
                ok=failure is not None and not (m.home / ".local").exists(),
            )
        m = machine()
        failure = install_tree(m, "node", NODE, release("a.tar.xz", good), redirect=("http", "127.0.0.1"))
        case(f"one redirect to the allowed host installs the tree: {failure}", ok=failure is None)


def tree_refusal_cases(case: Case, tmp: pathlib.Path) -> None:
    """The Node.js installs that fail: no top-level directory, a top-level directory that lacks a
    program, a directory in ~/.local/bin of a program's name, a link that cannot be made, and each
    member that escapes the tree. Each writes no tree below ~/.local/share/research-harness/node/
    and no link in ~/.local/bin, and a <program>.part link that the step does not make keeps its
    target. A link of a program's name to a directory is no such obstacle: the step replaces it."""
    good = node_tree("24.11.1")
    outside = tmp / "tree-outside"
    top = "node-v24.11.1-linux-x64"
    leaves = "which leaves the tree; nothing is installed"
    # Each archive, and the text that the line of its failure holds ("" where any line will do).
    escapes = {
        "an absolute member": (node_tree("24.11.1", [member(str(outside / "absolute"))]), ""),
        "an absolute member /<top>/bin/planted, named in the line": (
            node_tree("24.11.1", [member(f"/{top}/bin/planted")]),
            f"/{top}/bin/planted",
        ),
        "a link to ../.., the directory of the versions": (
            node_tree("24.11.1", [member(f"{top}/bin/up", "../..")]),
            f"bin/up, {leaves}",
        ),
        "a link into a tree of another version": (
            node_tree("24.11.1", [member(f"{top}/bin/side", "../../24.0.0/bin/node")]),
            f"bin/side, {leaves}",
        ),
        "a link that leaves the tree and comes back by its top-level name": (
            node_tree("24.11.1", [member(f"{top}/bin/back", f"../../{top}/bin/node")]),
            f"bin/back, {leaves}",
        ),
        "a link x/../../.., in normal form ../..": (
            node_tree("24.11.1", [member(f"{top}/bin/k", "x/../../..")]),
            f"bin/k, {leaves}",
        ),
        "a member with ..": (node_tree("24.11.1", [member(f"{top}/../../escaped")]), ""),
        "a link out of the tree": (
            node_tree("24.11.1", [member(f"{top}/bin/evil", "../../../../../../../../../etc/passwd")]),
            "",
        ),
        "an absolute link": (node_tree("24.11.1", [member(f"{top}/bin/evil", "/etc/passwd")]), ""),
    }
    flat = flat_tree()
    lacking = io.BytesIO()
    with tarfile.open(fileobj=lacking, mode="w:xz") as tar:
        tar.addfile(member(f"{top}/bin/node"), io.BytesIO(b"x"))
        tar.addfile(member(f"{top}/bin/npm"), io.BytesIO(b"x"))
    files = {"/good.tar.xz": good, "/flat.tar.xz": flat, "/lacking.tar.xz": lacking.getvalue()} | {
        f"/escape{i}.tar.xz": data for i, (data, _) in enumerate(escapes.values())
    }
    with release_server(files) as url:

        def release(path: str, data: bytes) -> Release:
            return Release("24.11.1", f"{url}/{path}", hashlib.sha256(data).hexdigest())

        n = 0

        def machine() -> Machine:
            nonlocal n
            n += 1
            home = tmp / f"refused{n}"
            return Machine("Linux", "x86_64", "ubuntu", home, {}, tmp, ())

        m = machine()
        failure = install_tree(m, "node", NODE, release("flat.tar.xz", flat))
        case(
            f"an archive with bin/ and lib/ at its top, and no top-level directory, is refused: {failure}",
            ok=failure is not None
            and not (m.home / ".local" / "bin").exists()
            and not (m.home / ".local" / "share" / "research-harness" / "node").exists(),
        )

        m = machine()
        failure = install_tree(m, "node", NODE, release("lacking.tar.xz", lacking.getvalue()))
        case(
            f"an archive with one top-level directory that lacks bin/npx is refused: {failure}",
            ok=failure is not None
            and not (m.home / ".local" / "bin").exists()
            and not (m.home / ".local" / "share" / "research-harness" / "node").exists(),
        )

        m = machine()
        (m.home / ".local" / "bin" / "npm").mkdir(parents=True)
        (m.home / "kept").write_text("x\n", encoding="utf-8")
        (m.home / ".local" / "bin" / "node.part").symlink_to(m.home / "kept")
        failure = install_tree(m, "node", NODE, release("good.tar.xz", good))
        left = sorted(p.name for p in (m.home / ".local" / "bin").iterdir())
        case(
            f"a directory npm in ~/.local/bin fails the step before anything is installed, and a node.part "
            f"link that the step does not reach keeps its target: {failure} {left}",
            ok=failure is not None
            and left == ["node.part", "npm"]
            and (m.home / ".local" / "bin" / "node.part").readlink() == m.home / "kept"
            and (m.home / ".local" / "bin" / "npm").is_dir()
            and not (m.home / ".local" / "bin" / "npm").is_symlink()
            and not (m.home / ".local" / "share" / "research-harness" / "node").exists(),
        )

        m = machine()
        (m.home / ".local" / "bin" / "npx.part").mkdir(parents=True)
        failure = install_tree(m, "node", NODE, release("good.tar.xz", good))
        left = sorted(p.name for p in (m.home / ".local" / "bin").iterdir())
        case(
            f"a link that cannot be made fails the step and removes the links made before: {failure} {left}",
            ok=failure is not None
            and left == ["npx.part"]
            and not (m.home / ".local" / "share" / "research-harness" / "node").exists(),
        )

        m = machine()
        (m.home / "elsewhere").mkdir(parents=True)
        (m.home / ".local" / "bin").mkdir(parents=True)
        (m.home / ".local" / "bin" / "npm").symlink_to(m.home / "elsewhere")
        failure = install_tree(m, "node", NODE, release("good.tar.xz", good))
        case(
            f"a link npm to a directory is replaced by the link into the tree: {failure}",
            ok=failure is None and (m.home / ".local" / "bin" / "npm").resolve().is_file(),
        )

        for i, (label, (_, named)) in enumerate(escapes.items()):
            m = machine()
            failure = install_tree(m, "node", NODE, release(f"escape{i}.tar.xz", escapes[label][0]))
            stray = ("planted", "up", "side", "back", "k", "evil")
            strays = [str(p) for p in m.home.rglob("*") if p.name in stray]
            case(
                f"{label}: the step fails before anything is linked, and leaves no tree: {failure} {strays}",
                ok=failure is not None
                and failure.endswith("nothing is installed")
                and named in failure
                and not strays
                and not (m.home / ".local" / "bin").exists()
                and not (m.home / ".local" / "share" / "research-harness" / "node").exists()
                and not outside.exists()
                and not (m.home / ".local" / "share" / "escaped").exists()
                and not (m.home / ".local" / "share" / "research-harness" / "escaped").exists(),
            )


# The lockfile format that npm 7 and later read, and the integrity of the srt tarball that the
# supply-chain review read from the registry.
SRT_LOCKFILE_VERSION = 3
SRT_INTEGRITY = (
    "sha512-bjHDu87gjIR7+Oxy9jPiK3v8CvSELCzfpXa3fjqfSKdvlZET2iF51xcXILWPayTpowB3xtZeQVf2JR916nVW/w=="
)
# A stub npm: it records its arguments and its working directory beside itself, then writes the
# program that `npm ci` links from the package's `bin` entry.
SRT_NPM = (
    'echo "$*" > "$0.args"; pwd -P > "$0.cwd"\n'
    '/bin/mkdir -p node_modules/.bin && printf "#!/bin/sh\\n" > node_modules/.bin/srt '
    "&& /bin/chmod 755 node_modules/.bin/srt"
)
# The stderr of three failures of `npm ci` that npm 11.20.0 wrote, line for line, with the log path
# as `{log}`: the registry out of reach, a tarball whose sha512 differs from the lockfile's, and a
# package.json out of step with its lockfile, whose usage block keeps its first and last lines.
NPM_ENOTFOUND = """npm error code ENOTFOUND
npm error syscall getaddrinfo
npm error errno ENOTFOUND
npm error network request to https://registry.npmjs.org/zod/-/zod-3.25.76.tgz failed, reason: \
getaddrinfo ENOTFOUND registry.npmjs.org
npm error network This is a problem related to network connectivity.
npm error network In most cases you are behind a proxy or have bad network settings.
npm error network
npm error network If you are behind a proxy, please make sure that the 'proxy' config is set properly.  \
See: 'npm help config'
npm error A complete log of this run can be found in: {log}
"""
NPM_SHA = "sha512-" + "A" * 86 + "=="
NPM_EINTEGRITY = f"""npm warn tarball tarball data for zod@https://registry.npmjs.org/zod/-/zod-3.25.76.tgz \
({NPM_SHA}) seems to be corrupted. Trying again.
npm warn tarball tarball data for zod@https://registry.npmjs.org/zod/-/zod-3.25.76.tgz \
({NPM_SHA}) seems to be corrupted. Trying again.
npm error code EINTEGRITY
npm error {NPM_SHA} integrity checksum failed when using sha512: wanted {NPM_SHA} but got \
sha512-gzUt/qt81nXsFGKIFcC3YnfEAx5NkunCfnDlvuBSSFS02bcXu4Lmea0AFIUwbLWxWPx3d9p8S5QoaujKcNQxcQ==. \
(583600 bytes)
npm notice
npm notice New major version of npm available! 11.20.0 -> 12.2.2
npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.2
npm notice To update run: npm install -g npm@12.2.2
npm notice
npm error A complete log of this run can be found in: {{log}}
"""
NPM_EUSAGE = """npm error code EUSAGE
npm error
npm error `npm ci` can only install packages when your package.json and package-lock.json or \
npm-shrinkwrap.json are in sync. Please update your lock file with `npm install` before continuing.
npm error
npm error Invalid: lock file's @anthropic-ai/sandbox-runtime@0.0.81 does not satisfy \
@anthropic-ai/sandbox-runtime@0.0.80
npm error
npm error Clean install a project
npm error Run "npm help ci" for more info
npm error A complete log of this run can be found in: {log}
"""


def installed_srt(home: pathlib.Path, version: str) -> pathlib.Path:
    """The tree of srt `version` below `home` as `install_srt` leaves it: the shipped package and
    lockfile, a stub program, and ~/.local/bin/srt linked to the program, which it returns."""
    target = home / TREE_ROOT / "srt" / version
    (target / "node_modules" / ".bin").mkdir(parents=True)
    for name in SRT_FILES:
        shutil.copyfile(SRT / name, target / name)
    program = target / "node_modules" / ".bin" / "srt"
    program.write_text("#!/bin/sh\n", encoding="utf-8")
    link = home / ".local" / "bin" / "srt"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(program)
    return program


def srt_file_cases(case: Case, tmp: pathlib.Path) -> None:
    """sandbox/srt/: the package that pins srt and overrides node-forge, its lockfile, and the
    version that the step reads from it."""
    version = srt_version()
    package = jsonio.load(SRT / "package.json")
    case(
        f"sandbox/srt/package.json is private, pins srt 0.0.81 alone and overrides node-forge to 1.4.1: "
        f"{version} {package}",
        ok=version == "0.0.81"
        and package.get("private") is True
        and package.get("dependencies") == {SRT_PACKAGE: "0.0.81"}
        and package.get("overrides") == {"node-forge": "1.4.1"},
    )
    lock = jsonio.load(SRT / "package-lock.json")
    raw = lock.get("packages")
    packages = cast("dict[str, dict[str, object]]", raw if isinstance(raw, dict) else {})
    locked = {name.removeprefix("node_modules/"): entry for name, entry in packages.items() if name}
    srt = locked.get(SRT_PACKAGE, {})
    case(
        f"the lockfile, version 3, holds srt 0.0.81 with the review's integrity, node-forge 1.4.1 and "
        f"three more packages: {sorted(locked)}",
        ok=lock.get("lockfileVersion") == SRT_LOCKFILE_VERSION
        and set(locked) == {SRT_PACKAGE, "node-forge", "zod", "commander", "@pondwader/socks5-server"}
        and srt.get("version") == "0.0.81"
        and srt.get("integrity") == SRT_INTEGRITY
        and locked["node-forge"].get("version") == "1.4.1",
    )
    case(
        "each package of the lockfile comes from registry.npmjs.org with a sha512 integrity and has no "
        "install script",
        ok=bool(locked)
        and all(
            str(entry.get("resolved", "")).startswith("https://registry.npmjs.org/")
            and str(entry.get("integrity", "")).startswith("sha512-")
            and not entry.get("hasInstallScript")
            for entry in locked.values()
        ),
    )
    for name, value in (("a range", "^0.0.81"), ("a tag", "latest")):
        source = tmp / f"srt-{name.replace(' ', '-')}"
        source.mkdir()
        (source / "package.json").write_text(
            json.dumps({"private": True, "dependencies": {SRT_PACKAGE: value}}), encoding="utf-8"
        )
        try:
            got = srt_version(source)
        except HarnessError as e:
            got = str(e)
        case(f"a package.json that pins srt to {name} exits 2 naming it: {got}", ok=repr(value) in got)


def srt_plan_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The srt step in the plan: after the installers and before the harness steps with each
    frontend, none with no frontend, and none with the tree of the shipped lockfile in place; a
    whole run installs it."""
    version = srt_version()
    root = TREE_ROOT / "srt" / version

    def srt_lines(lines: Sequence[str]) -> list[str]:
        return [line for line in lines if line.startswith("npm ci --ignore-scripts")]

    s = scratch(tmp, "srt-plan", MACOS_FAKES, srt=False)
    s.fake("apt-cache", 'echo "  Candidate: 9.9-1"')
    claude = profile_module.Setup(frontends=("claude",), components=())
    for system in ("Darwin", "Linux"):
        lines = shows(s.machine(system), claude, s.options(), pins)
        at = next((i for i, line in enumerate(lines) if line.startswith("npm ci --ignore-scripts")), -1)
        installer = next((i for i, line in enumerate(lines) if "claude.ai/install.sh" in line), -1)
        case(
            f"{system}: one srt step names npm ci --ignore-scripts and ~/{root}, after the installers and "
            f"before harness install: {lines}",
            ok=len(srt_lines(lines)) == 1
            and f"~/{root}" in lines[at]
            and -1 < installer < at < lines.index("harness install --apply"),
        )
    for frontend in frontends.FRONTENDS:
        lines = shows(
            s.machine(), profile_module.Setup(frontends=(frontend,), components=()), s.options(), pins
        )
        case(f"{frontend} alone plans the srt step: {srt_lines(lines)}", ok=len(srt_lines(lines)) == 1)
    lines = shows(s.machine(), profile_module.Setup(frontends=(), components=("julia",)), s.options(), pins)
    case(f"no frontend plans no srt step: {srt_lines(lines)}", ok=not srt_lines(lines))

    program = installed_srt(s.home, version)
    lines = shows(s.machine(), profile_module.Setup(), s.options(), pins)
    case(f"with the shipped lockfile's tree linked, no srt step: {srt_lines(lines)}", ok=not srt_lines(lines))
    code, out = attempt(s.machine(), s.options(dry_run=True), pins=pins)
    case(f"and the dry run shows none: {code}", ok=code == "0" and "npm ci" not in out)
    lock = program.parents[2] / "package-lock.json"
    lock.write_bytes(lock.read_bytes() + b"\n")
    lines = shows(s.machine(), profile_module.Setup(), s.options(), pins)
    case(
        f"an installed lockfile of other bytes plans the step: {srt_lines(lines)}",
        ok=len(srt_lines(lines)) == 1,
    )
    shutil.copyfile(SRT / "package-lock.json", lock)
    link = s.home / ".local" / "bin" / "srt"
    link.unlink()
    link.symlink_to(s.home / "elsewhere")
    lines = shows(s.machine(), profile_module.Setup(), s.options(), pins)
    case(f"a link to another target plans the step: {srt_lines(lines)}", ok=len(srt_lines(lines)) == 1)
    link.unlink()
    link.symlink_to(program)
    program.unlink()
    lines = shows(s.machine(), profile_module.Setup(), s.options(), pins)
    case(f"a tree without its program plans the step: {srt_lines(lines)}", ok=len(srt_lines(lines)) == 1)

    s = scratch(tmp, "srt-run", MACOS_FAKES, srt=False)
    s.fake("node", 'echo "v22.12.0"')
    s.fake("npm", SRT_NPM)
    chosen_profile(s, claude)
    code, out = attempt(s.machine(), s.options(), pins=pins)
    link = s.home / ".local" / "bin" / "srt"
    case(
        f"a whole run with a stub npm installs srt and links it: {code} {out[-300:]!r}",
        ok=code == "0"
        and link.is_symlink()
        and link.readlink() == s.home / root / "node_modules" / ".bin" / "srt",
    )
    lines = shows(s.machine(), claude, s.options(), pins)
    case(f"the plan after that run has no srt step: {srt_lines(lines)}", ok=not srt_lines(lines))


def srt_scratch(tmp: pathlib.Path, name: str, node: str = "v22.12.0", npm: str = SRT_NPM) -> Scratch:
    """A Scratch without srt, whose stub node prints `node` and whose stub npm runs `npm`."""
    s = scratch(tmp, f"srt-{name}", MACOS_FAKES, srt=False)
    s.fake("node", f'echo "{node}"')
    s.fake("npm", npm)
    return s


def listing(directory: pathlib.Path) -> list[str]:
    """The sorted names in `directory`; none where it is no directory."""
    return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []


def srt_target(s: Scratch, version: str) -> pathlib.Path:
    """The directory of srt `version` in the home of `s`."""
    return s.home / TREE_ROOT / "srt" / version


def srt_linked(s: Scratch) -> str:
    """The target of ~/.local/bin/srt in the home of `s`; "" where it is no link."""
    link = s.home / ".local" / "bin" / "srt"
    return str(link.readlink()) if link.is_symlink() else ""


def srt_install_cases(case: Case, tmp: pathlib.Path) -> None:
    """`install_srt` with a stub npm and node: a fresh install, an upgrade, a file at the link, and a
    tree of the same version with another lockfile."""
    version = srt_version()
    s = srt_scratch(tmp, "fresh")
    failure = install_srt(s.machine(), version)
    args = (s.bin / "npm.args").read_text(encoding="utf-8").strip() if (s.bin / "npm.args").exists() else ""
    cwd = pathlib.Path((s.bin / "npm.cwd").read_text(encoding="utf-8").strip()) if args else pathlib.Path()
    case(
        f"npm runs as npm ci --ignore-scripts --no-audit --no-fund, in a scratch directory beside srt/: "
        f"{failure} {args!r} {cwd}",
        ok=failure is None
        and args == "ci --ignore-scripts --no-audit --no-fund"
        and cwd.parent == s.home / TREE_ROOT
        and cwd.name != "srt",
    )
    t = srt_target(s, version)
    case(
        f"srt/{version}/ holds the two shipped files and node_modules/.bin/srt, ~/.local/bin/srt links to "
        f"it, and no scratch directory is left: {listing(t)} {srt_linked(s)} {listing(s.home / TREE_ROOT)}",
        ok=all((t / n).is_file() and (t / n).read_bytes() == (SRT / n).read_bytes() for n in SRT_FILES)
        and (t / "node_modules" / ".bin" / "srt").is_file()
        and srt_linked(s) == str(t / "node_modules" / ".bin" / "srt")
        and listing(s.home / TREE_ROOT) == ["srt"]
        and listing(s.home / ".local" / "bin") == ["srt"],
    )

    s = srt_scratch(tmp, "upgrade")
    installed_srt(s.home, "0.0.79")
    failure = install_srt(s.machine(), version)
    t = srt_target(s, version)
    case(
        f"an upgrade removes 0.0.79 and links into {version}: {failure} {listing(t.parent)} {srt_linked(s)}",
        ok=failure is None
        and listing(t.parent) == [version]
        and srt_linked(s) == str(t / "node_modules" / ".bin" / "srt"),
    )

    s = srt_scratch(tmp, "upgrade-others")
    installed_srt(s.home, "0.0.79")
    t = srt_target(s, version)
    (t.parent / ".DS_Store").write_text("", encoding="utf-8")
    (s.root / "kept").mkdir()
    (t.parent / "0.0.78").symlink_to(s.root / "kept")
    failure = install_srt(s.machine(), version)
    case(
        f"an upgrade beside a file and a link to a directory below srt/ removes the link and 0.0.79, keeps "
        f"the file and the directory, and links into {version}: {failure} {listing(t.parent)}",
        ok=failure is None
        and listing(t.parent) == [".DS_Store", version]
        and (s.root / "kept").is_dir()
        and srt_linked(s) == str(t / "node_modules" / ".bin" / "srt"),
    )

    s = srt_scratch(tmp, "no-lockfile")
    source = s.root / "srt-source"
    source.mkdir()
    shutil.copyfile(SRT / "package.json", source / "package.json")
    work = s.root / "srt-work"
    work.mkdir()
    failure = npm_ci(s.machine(), str(s.bin / "npm"), source, work) or ""
    case(
        f"a package without its lockfile fails before npm runs, naming the file: {failure}",
        ok=failure.startswith(f"cannot copy {source / 'package-lock.json'}")
        and not (s.bin / "npm.args").exists(),
    )

    s = srt_scratch(tmp, "file")
    (s.home / ".local" / "bin").mkdir(parents=True)
    (s.home / ".local" / "bin" / "srt").write_text("#!/bin/sh\n", encoding="utf-8")
    failure = install_srt(s.machine(), version)
    case(
        f"a file at ~/.local/bin/srt is replaced by the link: {failure} {srt_linked(s)}",
        ok=failure is None and srt_linked(s) == str(srt_target(s, version) / "node_modules" / ".bin" / "srt"),
    )

    s = srt_scratch(tmp, "again")
    installed_srt(s.home, version)
    t = srt_target(s, version)
    (t / "package-lock.json").write_text("{}\n", encoding="utf-8")
    failure = install_srt(s.machine(), version)
    case(
        f"a tree of the same version with another lockfile is replaced by the new tree: {failure}",
        ok=failure is None
        and (t / "package-lock.json").read_bytes() == (SRT / "package-lock.json").read_bytes()
        and listing(t.parent) == [version]
        and listing(s.home / TREE_ROOT) == ["srt"],
    )


def srt_refusal_cases(case: Case, tmp: pathlib.Path) -> None:
    """Each failure of `install_srt`: the installed version stays linked, and no scratch directory,
    no other version and no srt.part link is left; a failure before npm runs no npm."""
    version = srt_version()

    def kept(s: Scratch, old: pathlib.Path) -> bool:
        """0.0.79 is still installed and linked, and nothing else is below the root or in ~/.local/bin."""
        return (
            srt_linked(s) == str(old)
            and listing(srt_target(s, version).parent) == ["0.0.79"]
            and listing(s.home / TREE_ROOT) == ["srt"]
            and listing(s.home / ".local" / "bin") == ["srt"]
        )

    for name, stderr, holds, lacks in (
        (
            "ENOTFOUND",
            NPM_ENOTFOUND,
            ("code ENOTFOUND", "network request to https://registry.npmjs.org/zod/-/zod-3.25.76.tgz failed"),
            ("A complete log", "syscall"),
        ),
        (
            "EUSAGE",
            NPM_EUSAGE,
            ("code EUSAGE", "can only install packages when your package.json and package-lock.json"),
            ("A complete log", "Invalid:", "help ci"),
        ),
        (
            "EINTEGRITY",
            NPM_EINTEGRITY,
            ("code EINTEGRITY", "integrity checksum failed when using sha512"),
            ("A complete log", "notice", "warn"),
        ),
        ("no npm error line", "node: bad option: --x\n", ("exits 1: node: bad option: --x;",), ()),
        ("empty stderr", "", ("exits 1 with an empty stderr; nothing is installed",), (": ;", ":;")),
        ("a byte that is not UTF-8", b"npm error code E\xffX\nnpm error boom\n", ("code E�X", "boom"), ()),
    ):
        s = srt_scratch(tmp, f"fail-{name.replace(' ', '-')}")
        recorded = s.root / "npm-stderr.txt"
        recorded.write_bytes(
            stderr
            if isinstance(stderr, bytes)
            else stderr.format(log=s.root / "npm-cache" / "_logs" / "debug-0.log").encode()
        )
        s.fake("npm", f'/bin/cat "{recorded}" >&2; exit 1')
        old = installed_srt(s.home, "0.0.79")
        failure = install_srt(s.machine(), version) or ""
        case(
            f"npm exiting 1 with the stderr of {name} fails the step naming npm's cause, and keeps 0.0.79 "
            f"linked: {failure}",
            ok=all(h in failure for h in holds) and not any(x in failure for x in lacks) and kept(s, old),
        )
    log = "npm error A complete log of this run can be found in: /x/_logs/debug-0.log"
    for stderr, want in (
        (
            NPM_ENOTFOUND.format(log="/x/_logs/debug-0.log"),
            "code ENOTFOUND; network request to https://registry.npmjs.org/zod/-/zod-3.25.76.tgz failed, "
            "reason: getaddrinfo ENOTFOUND registry.npmjs.org",
        ),
        (f"npm error code E401\n{log}\n", "code E401"),
        (f"first\nsecond\n{log}\n", "second"),
        (f"{log}\n", log),
        ("npm errors are here\n", "npm errors are here"),
        ("\n  \n", ""),
    ):
        got = npm_cause(stderr)
        case(f"npm_cause reads {stderr[:40]!r}… as {want!r}: {got!r}", ok=got == want)
    s = srt_scratch(tmp, "unstartable")
    (s.bin / "npm").write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    old = installed_srt(s.home, "0.0.79")
    failure = install_srt(s.machine(), version) or ""
    case(
        f"an npm that cannot start fails the step, and keeps 0.0.79 linked: {failure}",
        ok=failure.startswith("cannot run npm ci") and kept(s, old),
    )
    s = srt_scratch(tmp, "no-npm")
    (s.bin / "npm").unlink()
    old = installed_srt(s.home, "0.0.79")
    failure = install_srt(s.machine(), version)
    case(
        f"no npm on the PATH fails the step naming Node.js and npm, and keeps 0.0.79 linked: {failure}",
        ok=failure is not None and "Node.js" in failure and "npm" in failure and kept(s, old),
    )
    s = srt_scratch(tmp, "no-program", npm="exit 0")
    old = installed_srt(s.home, "0.0.79")
    failure = install_srt(s.machine(), version)
    case(
        f"npm exiting 0 without node_modules/.bin/srt fails the step, and keeps 0.0.79 linked: {failure}",
        ok=failure is not None and "node_modules/.bin/srt" in failure and kept(s, old),
    )
    s = srt_scratch(tmp, "signal", npm=f"{SRT_NPM}\nkill -9 $$")
    old = installed_srt(s.home, "0.0.79")
    failure = install_srt(s.machine(), version)
    case(
        f"npm killed by a signal after it made the program fails the step, and keeps 0.0.79 linked: "
        f"{failure}",
        ok=failure is not None and kept(s, old),
    )
    s = srt_scratch(tmp, "srt-file")
    (s.home / TREE_ROOT).mkdir(parents=True)
    (s.home / TREE_ROOT / "srt").write_text("", encoding="utf-8")
    failure = install_srt(s.machine(), version)
    case(
        f"a file at srt/ fails the step after npm, removes the scratch directory and the srt.part link, and "
        f"leaves ~/.local/bin empty: {failure} {listing(s.home / TREE_ROOT)} "
        f"{listing(s.home / '.local' / 'bin')}",
        ok=failure is not None
        and str(srt_target(s, version)) in failure
        and listing(s.home / TREE_ROOT) == ["srt"]
        and listing(s.home / ".local" / "bin") == [],
    )

    for node in ("v22.11.0", "v20.16.0", ""):
        s = srt_scratch(tmp, f"node-{node or 'none'}", node)
        if not node:
            (s.bin / "node").unlink()
        failure = install_srt(s.machine(), version)
        case(
            f"node {node or 'missing'} fails the step naming 22.12 and the version found, runs no npm, and "
            f"writes nothing: {failure}",
            ok=failure is not None
            and "22.12" in failure
            and node.removeprefix("v") in failure
            and not (s.bin / "npm.args").exists()
            and not (s.home / TREE_ROOT / "srt").exists()
            and not (s.home / ".local" / "bin").exists(),
        )

    s = srt_scratch(tmp, "dir")
    link = s.home / ".local" / "bin" / "srt"
    link.mkdir(parents=True)
    failure = install_srt(s.machine(), version)
    case(
        f"a directory at ~/.local/bin/srt fails the step naming it, and writes nothing below srt/: {failure}",
        ok=failure is not None
        and str(link) in failure
        and link.is_dir()
        and not link.is_symlink()
        and listing(s.home / TREE_ROOT) == []
        and listing(s.home / ".local" / "bin") == ["srt"],
    )


def ubuntu_2404_cases(case: Case, tmp: pathlib.Path) -> None:
    """One run on a model of Ubuntu 24.04: its os-release, an apt candidate nodejs 18.19.1, a
    python3 3.12.3 and the Node.js release on a local server. The plan installs Node.js from the
    release, the dry run lists that step, the step installs the tree, the next plan has no such step,
    and `harness doctor` with an environment interpreter of 3.14 prints no FAIL on the lines Python,
    Python environment and Node.js."""
    s = scratch(tmp, "ubuntu-2404", LINUX_FAKES)
    os_release = s.root / "os-release"
    os_release.write_text(
        'PRETTY_NAME="Ubuntu 24.04.5 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\nID_LIKE=debian\n',
        encoding="utf-8",
    )
    s.fake(
        "apt-cache",
        'case "$2" in nodejs) echo "  Candidate: 18.19.1+dfsg-6ubuntu5";; '
        '*) echo "  Candidate: 9.9.9-1";; esac',
    )
    s.fake("python3", 'echo "Python 3.12.3"')
    data = node_tree("24.11.1")
    with release_server({"/node.tar.xz": data}) as url:
        offline = offline_pins(load_pins())
        node = Release("24.11.1", f"{url}/node.tar.xz", hashlib.sha256(data).hexdigest())
        pins = Pins(
            offline.minimum, {**offline.releases, "Node.js": {"linux-x86_64": node, "linux-aarch64": node}}
        )
        machine = s.machine("Linux", "x86_64", distro(os_release))
        loaded = profile_module.load(s.profile, home=str(s.home))
        the_plan = plan(machine, profile_module.Setup(), loaded, s.options(), pins)
        steps = [step for step in the_plan.steps if step.show.startswith("install node 24.11.1 ")]
        apt_lines = [step.show for step in the_plan.steps if step.show.startswith("sudo apt-get")]
        case(
            "Ubuntu 24.04 with nodejs 18.19.1: the plan installs the Node.js release, apt installs no "
            f"nodejs, and no line by hand names Node.js: {[step.show for step in steps]} {apt_lines} "
            f"{the_plan.by_hand}",
            ok=distro(os_release) == "ubuntu"
            and len(steps) == 1
            and "~/.local/share/research-harness/node/24.11.1" in steps[0].show
            and node.sha256 in steps[0].show
            and not any("nodejs" in line.split() for line in apt_lines)
            and not any("Node.js" in line for line in the_plan.by_hand),
        )
        code, out = attempt(machine, s.options(dry_run=True), pins=pins)
        case(
            f"the dry run lists the Node.js release step: {code}",
            ok=code == "0" and "install node 24.11.1 from " in out,
        )
        failure = steps[0].action() if steps else "no step"
        case(f"the step installs the Node.js tree: {failure}", ok=failure is None)
        lines = shows(machine, profile_module.Setup(), s.options(), pins)
        case(
            f"with the tree of the pinned version linked, the plan has no Node.js step: {lines}",
            ok=not any(line.startswith("install node ") for line in lines),
        )
    environment = s.root / "python-env"
    (environment / "bin").mkdir(parents=True)
    interpreter = environment / "bin" / "python"
    interpreter.write_text("#!/bin/sh\necho 3.14.8\n", encoding="utf-8")
    interpreter.chmod(0o755)
    env = {"HOME": str(s.home), "PATH": machine.env["PATH"], "RESEARCH_HARNESS_PYTHON": str(environment)}
    with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
        d = doctor_module.Doctor(argparse.Namespace(profile=str(s.profile), models=None))
        results = [
            cast("tuple[str, str, str]", d.tool(*t))
            for t in doctor_module.TOOLS
            if t[0] in ("Python", "Node.js")
        ]
        results.append(cast("tuple[str, str, str]", d.python_environment()))
    statuses = {name: status for status, name, _ in results}
    case(
        "harness doctor on the same machine, with an environment interpreter of 3.14: no FAIL on Python, "
        f"Python environment and Node.js: {results}",
        ok=set(statuses) == {"Python", "Python environment", "Node.js"}
        and "FAIL" not in statuses.values()
        and statuses["Node.js"] == "PASS",
    )


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


def explained(answers: Sequence[str]) -> tuple[list[tuple[str, str]], str]:
    """`new_profile` of the example with `answers`: each question with the output printed since the
    question before it, and the profile's text, or the message with which it exits 2."""
    out, asker, seen = io.StringIO(), Asker(*answers), list[tuple[str, str]]()

    def ask(question: str) -> str:
        printed = out.getvalue()
        seen.append((question, printed[sum(len(p) for _, p in seen) :]))
        return asker(question)

    with contextlib.redirect_stdout(out):
        try:
            text = new_profile(profile_module.DUMMY.read_text(encoding="utf-8"), ask)
        except HarnessError as e:
            text = f"exit 2: {e}"
    return seen, text


def question_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The explanation before each question, and the answers to a list question."""
    names = (*frontends.FRONTENDS, *profile_module.COMPONENTS)
    questions = ("frontends", "components", "develop")
    missing = [n for n in (*profile_module.REQUIRED, *names, *questions) if not EXPLAINED.get(n)]
    case(
        f"EXPLAINED holds one explanation for each REQUIRED key, frontend and component, and for the "
        f"lists and develop: missing {missing}",
        ok=not missing and all(all(EXPLAINED[n]) for n in EXPLAINED),
    )
    long = [k for k in profile_module.REQUIRED if len(EXPLAINED.get(k, ())) > EXPLAINED_LINES]
    long += [n for n in names if len(EXPLAINED.get(n, ())) > 1]
    case(
        f"each explanation of a REQUIRED key has at most three lines, and each frontend and component "
        f"one: longer {long}",
        ok=not long,
    )

    seen, _ = explained([""] * len(profile_module.REQUIRED))
    before = [p.splitlines() for _, p in seen]
    case(
        f"before each question of new_profile, setup prints its key's explanation and nothing else: {before}",
        ok=len(seen) == len(profile_module.REQUIRED)
        and before == [list(EXPLAINED[k]) for k in profile_module.REQUIRED],
    )
    prompts = {q.split(",")[0]: q for q, _ in seen}
    case(
        f"the prompt of each list says that the answer replaces the example list: {prompts}",
        ok=all(
            ("replaces the example list" in q) == (profile_module.REQUIRED[k] != profile_module.STRING)
            for k, q in prompts.items()
        ),
    )

    # (a list key, an answer to it, the list that the profile holds after it, the item that a
    # refusal names)
    for key, answer, want, named in (
        ("org", '["a", "b"]', ["a", "b"], ""),
        ("org", "a, b", ["a", "b"], ""),
        ("org", " a ,b,, ", ["a", "b"], ""),
        ("leak", '["a,b", "c"]', ["a,b", "c"], ""),
        ("org", '["a"', ["x"], '["a"'),
        ("org", '"a"', ["x"], '"a"'),
        ("org", "[1, 2]", ["x"], "[1, 2]"),
        ("org", '[["a"]]', ["x"], '[["a"]]'),
        ("org", '["a"] b', ["x"], '["a"] b'),
        ("org", "[]", ["x"], "[]"),
        ("org", ",, ,", ["x"], ",, ,"),
        ("org", "a, b]", ["x"], "b]"),
        ("org", "it's", ["x"], "it's"),
        ("org", '["a\'b"]', ["x"], "a'b"),
        ("leak", '["", "a"]', ["x"], '["", "a"]'),
        ("leak", '[""]', ["x"], '[""]'),
        ("org", "a, b_c", ["x"], "b_c"),
        ("org", '["a", "-b"]', ["x"], "-b"),
    ):
        at = list(profile_module.REQUIRED).index(key)
        answers = [""] * len(profile_module.REQUIRED)
        answers[at : at + 1] = [answer, "x"] if named else [answer]
        seen, text = explained(answers)
        try:
            got = cast("dict[str, object]", tomllib.loads(text)).get(key)
        except tomllib.TOMLDecodeError:
            got = text
        asked = [q.split(",")[0] for q, _ in seen]
        refusal = seen[at + 1][1].splitlines() if named and len(seen) > at + 1 else []
        case(
            f"the {key} answer {answer!r} gives {want}"
            + (f", after one line that names {named!r} and the question again" if named else "")
            + f": {got} {asked} {refusal}",
            ok=got == want
            and asked.count(key) == (2 if named else 1)
            and len(asked) == len(profile_module.REQUIRED) + (1 if named else 0)
            and (not named or (len(refusal) == 1 and repr(named) in refusal[0])),
        )

    out = io.StringIO()
    asker = Asker("", "", "")
    with contextlib.redirect_stdout(out):
        choose(profile_module.Setup(), asker)
    shown = out.getvalue().splitlines()
    rows = [
        f"  {i}. {name}: {EXPLAINED[name][0]}"
        for group in (frontends.FRONTENDS, profile_module.COMPONENTS)
        for i, name in enumerate(group, 1)
    ]
    case(
        f"the lists of frontends and components give one description per name, and develop says what it "
        f"is for, before its question: {shown}",
        ok=all(r in shown for r in rows)
        and all(line in shown for n in questions for line in EXPLAINED[n])
        and shown[-len(EXPLAINED["develop"]) :] == list(EXPLAINED["develop"])
        and len(asker.questions) == len(questions),
    )

    s = scratch(tmp, "explained-yes", MACOS_FAKES)
    code, out_yes = attempt(s.machine(), s.options(), pins=pins)
    said = [line for lines in EXPLAINED.values() for line in lines if line in out_yes]
    case(f"--yes prints no explanation: {code} {said}", ok=code == "0" and not said)


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


REMOTE = "https://example.invalid/claude.git"


def claude_repository(s: Scratch) -> Scratch:
    """`s`, with the `claude_remote` REMOTE in its profile and a git repository in ~/.claude."""
    s.profile.write_text(with_remote(s.profile.read_text(encoding="utf-8"), REMOTE), encoding="utf-8")
    git(s.home / ".claude", "init", "-q")
    return s


def git(directory: pathlib.Path, *arguments: str) -> str:
    """`git -C directory arguments` of a case, with an author and no global configuration: its
    stdout; a failure raises."""
    directory.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(directory),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "case",
        "GIT_AUTHOR_EMAIL": "case@example.invalid",
        "GIT_COMMITTER_NAME": "case",
        "GIT_COMMITTER_EMAIL": "case@example.invalid",
    }
    return subprocess.run(
        [shutil.which("git") or "git", "-C", str(directory), *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=TIMEOUT,
        check=True,
    ).stdout


JOBS_ONLY = profile_module.Setup(frontends=(), components=("jobs",))


def remote_machine(tmp: pathlib.Path, name: str, target: pathlib.Path) -> tuple[Scratch, Machine]:
    """A scratch macOS machine whose profile chooses the jobs alone and names REMOTE, which git
    reads as the repository at `target`."""
    s = scratch(tmp, name, MACOS_FAKES)
    chosen_profile(s, JOBS_ONLY)
    s.profile.write_text(with_remote(s.profile.read_text(encoding="utf-8"), REMOTE), encoding="utf-8")
    m = s.machine()
    env = {
        **m.env,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{target.as_uri()}.insteadOf",
        "GIT_CONFIG_VALUE_0": REMOTE,
    }
    return s, dataclasses.replace(m, env=env)


def clone_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The clone of `claude_remote` into ~/.claude from a local bare repository, the refusal of a
    ~/.claude that holds files, a clone that fails, and the key without the jobs."""
    source = tmp / "claude-source"
    (source / "CLAUDE.md").parent.mkdir(parents=True)
    (source / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
    git(source, "init", "-q")
    git(source, "add", "CLAUDE.md")
    git(source, "commit", "-q", "-m", "first")
    bare = tmp / "claude.git"
    git(tmp, "clone", "-q", "--bare", str(source), str(bare))
    jobs = JOBS_ONLY

    def remote(name: str, target: pathlib.Path) -> tuple[Scratch, Machine]:
        return remote_machine(tmp, name, target)

    claude_md = pathlib.Path(".claude") / "CLAUDE.md"
    for name in ("missing", "empty"):
        s, m = remote(f"clone-{name}", bare)
        claude = s.home / ".claude"
        if name == "empty":
            claude.mkdir()
        lines = shows(m, jobs, s.options(), pins)
        clone = f"git clone {REMOTE} {claude}"
        code, out = attempt(m, s.options(), pins=pins)
        case(
            f"a ~/.claude that is {name}: the plan clones claude_remote before harness install --apply, "
            f"and the run clones it: {lines[:3]} {code} {out[-200:]!r}",
            ok=clone in lines
            and lines.index(clone) < lines.index("harness install --apply")
            and code == "0"
            and (claude / ".git").is_dir()
            and (s.home / claude_md).read_text(encoding="utf-8") == "# mine\n",
        )
        lines = shows(m, jobs, s.options(), pins)
        case(
            f"a ~/.claude that is a git repository: the plan has no clone step: {lines[:3]}",
            ok=not any(line.startswith("git clone") for line in lines),
        )

    s, m = remote("clone-files", bare)
    claude = s.home / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}\n", encoding="utf-8")
    code, out = attempt(m, s.options(), pins=pins)
    case(
        f"a ~/.claude that holds files and is no repository: the clone step fails with the lines that "
        f"move it aside and clone, and changes nothing: {code} {out[-300:]!r}",
        ok=code.startswith("exit 2")
        and f"git clone {REMOTE}" in code
        and f"  mv {claude} {claude}.setup" in out
        and f"  git clone {REMOTE} {claude}" in out
        and sorted(p.name for p in claude.iterdir()) == ["settings.json"]
        and not any(c.startswith("harness") for c in s.calls()),
    )

    for name in ("missing", "empty"):
        s, m = remote(f"clone-fails-{name}", tmp / "no-such.git")
        claude = s.home / ".claude"
        if name == "empty":
            claude.mkdir()
        code, out = attempt(m, s.options(), pins=pins)
        last = out.rstrip().splitlines()[-1] if out.strip() else ""
        # The same clone, run alone: its last line of stderr.
        alone = subprocess.run(
            [shutil.which("git") or "git", "clone", REMOTE, str(s.root / "alone")],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=dict(m.env),
            timeout=TIMEOUT,
            check=False,
        ).stderr.strip()
        case(
            f"a clone that fails, into a ~/.claude that is {name}: the step fails with git's last line, "
            f"and nothing below ~/.claude is left: {code} {last!r}",
            ok=code.startswith("exit 2")
            and "git clone" in code
            and bool(alone)
            and last == alone.splitlines()[-1].strip()
            and (not claude.exists() if name == "missing" else claude.is_dir() and not any(claude.iterdir())),
        )
        # A git that leaves a partial clone behind, as one stopped at its timeout would: the step
        # removes it. The link to the real git goes first, so that the fake does not write through it;
        # the fake lists what it left in git.left, and its PATH holds no /bin.
        (s.bin / "git").unlink()
        s.fake(
            "git",
            '/bin/mkdir -p "$3/.git/objects"; echo partial > "$3/CLAUDE.md"; /bin/ls -A "$3" > "$0.left"; '
            'echo "fatal: cut" >&2; exit 128',
        )
        code, out = attempt(m, s.options(), pins=pins)
        left = (
            (s.bin / "git.left").read_text(encoding="utf-8").split() if (s.bin / "git.left").exists() else []
        )
        case(
            f"a clone that fails and leaves {left} in a ~/.claude that was {name}: nothing below "
            f"~/.claude is left: {code} {out.rstrip().splitlines()[-1:]}",
            ok=code.startswith("exit 2")
            and left == [".git", "CLAUDE.md"]
            and out.rstrip().endswith("fatal: cut")
            and (not claude.exists() if name == "missing" else claude.is_dir() and not any(claude.iterdir())),
        )

    clone_first_cases(case, tmp, pins, bare)

    # The key without the jobs component is unused.
    s, m = remote("clone-no-jobs", bare)
    none = profile_module.Setup(frontends=(), components=())
    lines = shows(m, none, s.options(), pins)
    case(
        f"claude_remote without the jobs component: no clone step and no error: {lines}",
        ok=not any(line.startswith(("git clone", "exit 2")) for line in lines),
    )


def clone_first_cases(case: Case, tmp: pathlib.Path, pins: Pins, bare: pathlib.Path) -> None:
    """The clone of ~/.claude from `bare` is the first step: before a vendor installer that writes
    below ~/.claude, and before the writes of the profile and the model tables."""
    # A vendor installer that writes below ~/.claude, as the Claude Code installer may write
    # ~/.claude/downloads: the clone comes first, while ~/.claude is still missing.
    s, m = remote_machine(tmp, "clone-installer", bare)
    claude = s.home / ".claude"
    (s.root / "installer.sh").write_text(
        '/bin/mkdir -p "$HOME/.claude/downloads" "$HOME/.local/bin"\n'
        'printf "#!/bin/sh\\necho 9.9.9\\n" > "$HOME/.local/bin/claude"\n'
        '/bin/chmod 755 "$HOME/.local/bin/claude"\n',
        encoding="utf-8",
    )
    s.fake("curl", f'case "$*" in *claude.ai*) /bin/cat "{s.root / "installer.sh"}";; esac; exit 0')
    with_claude = profile_module.Setup(frontends=("claude",), components=("jobs",))
    chosen_profile(s, with_claude)
    lines = shows(m, with_claude, s.options(), pins)
    clone = f"git clone {REMOTE} {claude}"
    code, out = attempt(m, s.options(), pins=pins)
    case(
        f"an installer that writes ~/.claude/downloads: the clone is the first step, and the run "
        f"clones claude_remote: {lines[:3]} {code} {out[-200:]!r}",
        ok=lines[:1] == [clone]
        and any("claude.ai" in line for line in lines)
        and code == "0"
        and (claude / ".git").is_dir()
        and (claude / "downloads").is_dir()
        and (claude / "CLAUDE.md").read_text(encoding="utf-8") == "# mine\n",
    )
    # The clone comes before the steps that write the profile and the model tables, too.
    s, m = remote_machine(tmp, "clone-models", bare)
    s.options().models.unlink()
    code, out = attempt(m, s.options(dry_run=True), pins=pins)
    planned = [x.split(". ", 1)[1] for x in out.splitlines() if re.match(r"  \d+\. ", x)]
    case(
        f"the clone is the first step, before the copy of the model tables: {code} {planned[:3]}",
        ok=code == "0"
        and planned[:2] == [f"git clone {REMOTE} {s.home / '.claude'}", f"cp {MODELS} {s.options().models}"],
    )


def no_remote_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The jobs without `claude_remote`: no autocommit job, on macOS and on Linux; a line by hand
    names the key."""
    jobs = JOBS_ONLY
    s = scratch(tmp, "no-remote-mac", MACOS_FAKES)
    chosen_profile(s, jobs)
    code, out = attempt(s.machine(), s.options(), pins=pins)
    agents = sorted(p.name for p in (s.home / "Library" / "LaunchAgents").glob("*.plist"))
    boots = [c for c in s.calls() if c.startswith("launchctl bootstrap")]
    case(
        f"macOS without claude_remote: no plist of the autocommit job is rendered or bootstrapped, and "
        f"a line by hand names claude_remote: {code} {agents} {boots}",
        ok=code == "0"
        and agents == ["org.example.julia-update.plist", "org.example.kaimon.plist"]
        and not any("claude-autocommit" in c for c in boots)
        and len(boots) == len(JOBS) - 1
        and "set claude_remote in the profile" in out
        and not (s.home / ".claude").exists(),
    )
    s = scratch(tmp, "no-remote-linux", LINUX_FAKES)
    chosen_profile(s, jobs)
    code, out = attempt(s.machine("Linux"), s.options(), pins=pins)
    units = sorted(p.name for p in (s.home / ".config" / "systemd" / "user").glob("*"))
    systemctl = [c for c in s.calls() if c.startswith("systemctl")]
    case(
        f"Linux without claude_remote: no unit of the autocommit job is rendered or enabled, and a "
        f"line by hand names claude_remote: {code} {units} {systemctl}",
        ok=code == "0"
        and units == ["julia-update.service", "julia-update.timer", "kaimon.service"]
        and not any("claude-autocommit" in c for c in systemctl)
        and "systemctl --user enable --now kaimon.service julia-update.timer" in systemctl
        and "set claude_remote in the profile" in out,
    )


def ask_remote_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The question for `claude_remote`, in a terminal: after the choices, before the plan, with
    its explanation; only with the jobs, and never with --yes."""
    jobs = JOBS_ONLY
    for name, answers, want in (
        ("a URL", ("", "", "", REMOTE, "n"), REMOTE),
        ("a wrong answer, then a URL", ("", "", "", "http://x", REMOTE, "n"), REMOTE),
        ("an empty answer", ("", "", "", "", "n"), ""),
    ):
        s = scratch(tmp, f"ask-remote-{len(answers)}-{bool(want)}", MACOS_FAKES)
        chosen_profile(s, jobs)
        out = io.StringIO()
        asker = Asker(*answers)
        printed: list[str] = []

        def ask(
            question: str, asker: Asker = asker, out: io.StringIO = out, printed: list[str] = printed
        ) -> str:
            printed.append(out.getvalue())
            return asker(question)

        with contextlib.redirect_stdout(out):
            try:
                code = str(
                    setup(s.machine(), s.options(yes=False, dry_run=True), ask, terminal=True, pins=pins)
                )
            except HarnessError as e:
                code = f"exit 2: {e}"
        asked = [q.split(",")[0].split(" [")[0] for q in asker.questions]
        at = asked.index("claude_remote") if "claude_remote" in asked else -1
        explained_before = printed[at].splitlines()[-len(EXPLAINED["claude_remote"]) :] if at >= 0 else []
        shown = out.getvalue()
        planned = shown[shown.find("The plan, in this order:") :]
        case(
            f"in a terminal with the jobs and no claude_remote, setup asks for it after the choices "
            f"and before the plan, with its explanation; {name} gives {want!r}: {code} {asked}",
            ok=code == "0"
            and "Develop the harness" in asked
            and at == asked.index("Develop the harness") + 1
            and asked[-1] == "claude_remote"
            and "The plan, in this order:" not in printed[-1]
            and "The plan, in this order:" in shown
            and explained_before == list(EXPLAINED["claude_remote"])
            and (f"git clone {want}" in planned if want else "the autocommit job of ~/.claude" in planned),
        )
    s = scratch(tmp, "ask-remote-written", MACOS_FAKES)
    chosen_profile(s, jobs)
    # A ~/.claude that is a repository already: the run clones nothing.
    git(s.home / ".claude", "init", "-q")
    code, _ = attempt(
        s.machine(), s.options(yes=False), Asker("", "", "", REMOTE, "y"), terminal=True, pins=pins
    )
    loaded = profile_module.load(s.profile, home=str(s.home))
    case(
        f"the answer goes into the profile that the run writes: {code} {loaded.claude_remote!r}",
        ok=code == "0" and loaded.claude_remote == REMOTE,
    )
    s = scratch(tmp, "ask-remote-no-jobs", MACOS_FAKES)
    chosen_profile(s, profile_module.Setup(frontends=(), components=("jq",)))
    asker = Asker("", "", "", "n")
    code, _ = attempt(s.machine(), s.options(yes=False, dry_run=True), asker, terminal=True, pins=pins)
    case(
        f"without the jobs component, setup does not ask for claude_remote: {code} {asker.questions}",
        ok=code == "0" and not any(q.startswith("claude_remote") for q in asker.questions),
    )
    s = scratch(tmp, "ask-remote-yes", MACOS_FAKES)
    chosen_profile(s, jobs)
    asker = Asker()
    code, _ = attempt(s.machine(), s.options(dry_run=True), asker, terminal=True, pins=pins)
    case(
        f"--yes does not ask for claude_remote: {code} {asker.questions}",
        ok=code == "0" and not asker.questions,
    )


def token_wait_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The token step waits for Kaimon's key after the jobs start the server, and only then."""
    directory = tmp / "token-wait" / ".config" / "kaimon"
    directory.mkdir(parents=True)
    config, token = directory / "config.json", directory / "auth-token"
    # The sleeps after the reads that find no key: the server writes its key after the second.
    before = [1, 1]
    for name, text, late in (
        ("no file", None, '{"api_keys": ["late_key"]}\n'),
        ("no key", '{"api_keys": []}\n', '{"api_keys": ["late_key"]}\n'),
        ("no JSON", "{not json", '{"api_keys": ["late_key"]}\n'),
        ("never a key", '{"api_keys": []}\n', None),
        ("never JSON", "{not json", None),
    ):
        token.unlink(missing_ok=True)
        config.unlink(missing_ok=True)
        if text is not None:
            config.write_text(text, encoding="utf-8")
        slept: list[float] = []

        def sleep(seconds: float, slept: list[float] = slept, late: str | None = late) -> None:
            slept.append(seconds)
            if late is not None and len(slept) == len(before):
                config.write_text(late, encoding="utf-8")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            failure = kaimon_token(tmp / "token-wait", TOKEN_READS, sleep)
        got = token.read_text(encoding="utf-8") if token.exists() else None
        if late is not None:
            case(
                f"{name}, then a key after two reads: the token step waits, reading once a second, and "
                f"writes the key: {failure} {got!r} {slept}",
                ok=failure is None and got == "late_key" and slept == before,
            )
        else:
            case(
                f"{name} until the bound: the step reads {TOKEN_READS} times, once a second, prints the "
                f"line by hand and does not fail: {failure} {len(slept)} {out.getvalue()!r}",
                ok=failure is None
                and got is None
                and slept == [1] * (TOKEN_READS - 1)
                and sum(slept) < TOKEN_READS
                and "holds no key yet" in out.getvalue(),
            )

    s = scratch(tmp, "token-plan", LINUX_FAKES)
    for components, waits in ((("julia", "jobs"), True), (("julia",), False)):
        choice = profile_module.Setup(frontends=(), components=components)
        slept = []
        m = dataclasses.replace(s.machine("Linux"), sleep=slept.append)
        loaded = profile_module.load(s.profile, home=str(s.home))
        steps = plan(m, choice, loaded, s.options(), pins).steps
        step = next((x for x in steps if "auth-token" in x.show), None)
        with contextlib.redirect_stdout(io.StringIO()):
            failure = step.action() if step else "no token step"
        case(
            f"the token step with components {components} {'waits' if waits else 'does not wait'} for "
            f"the key: {failure} {len(slept)} {step.show if step else None}",
            ok=failure is None
            and step is not None
            and (len(slept) == TOKEN_READS - 1) == waits
            and (not slept) == (not waits)
            and ("up to 60 s" in step.show) == waits,
        )
    (s.home / ".config" / "kaimon").mkdir(parents=True, exist_ok=True)
    (s.home / ".config" / "kaimon" / "config.json").write_text("{not json", encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        failure = kaimon_token(s.home)
    case(
        f"without the wait, a config.json that is no JSON fails the step: {failure}",
        ok=failure is not None and "config.json" in failure,
    )


def path_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The `export PATH=…` line of the directories that the PATH that setup started with lacks,
    and its append to ~/.zshrc."""
    s = scratch(tmp, "path", {**LINUX_FAKES, "brew": "exit 0"})
    loaded = profile_module.load(s.profile, home=str(s.home))
    linux, mac = s.machine("Linux"), s.machine()
    home = s.home
    everything = [str(home / d) for d in EXTRA_PATH]
    for name, machine, choice, start, want in (
        (
            "Linux, every component and frontend, a PATH without them",
            linux,
            profile_module.Setup(),
            str(s.bin),
            [".local/bin", ".juliaup/bin", ".julia/bin", ".opencode/bin"],
        ),
        (
            "macOS, every component and frontend",
            mac,
            profile_module.Setup(),
            str(s.bin),
            [".local/bin", ".juliaup/bin", ".julia/bin"],
        ),
        (
            "Linux, no component and no frontend",
            linux,
            profile_module.Setup(frontends=(), components=()),
            str(s.bin),
            [".local/bin"],
        ),
        (
            "Linux, the PATH holds ~/.local/bin with a trailing slash",
            linux,
            profile_module.Setup(frontends=(), components=("julia",)),
            os.pathsep.join([f"{home}/.local/bin/", str(home / ".julia/bin"), str(s.bin)]),
            [".juliaup/bin"],
        ),
        (
            "Linux, the PATH holds every directory",
            linux,
            profile_module.Setup(),
            os.pathsep.join([*everything, str(s.bin)]),
            [],
        ),
    ):
        the_plan = plan(dataclasses.replace(machine, path=start), choice, loaded, s.options(), pins)
        line = 'export PATH="' + "".join(f"$HOME/{d}:" for d in want) + '$PATH"' if want else ""
        printed = [x for x in the_plan.by_hand if "export PATH=" in x]
        case(
            f"{name}: the plan prints one export PATH line with {want}: {printed}",
            ok=the_plan.path_line == line and printed == ([PATH_BY_HAND + line] if want else []),
        )

    # The whole run in a terminal, with zsh as the login shell: a yes appends the line.
    nothing = profile_module.Setup(frontends=(), components=())
    s = scratch(tmp, "path-zsh", MACOS_FAKES)
    chosen_profile(s, nothing)
    zsh = dataclasses.replace(s.machine(), login_shell="/bin/zsh")
    zshrc = s.home / ".zshrc"
    zshrc.write_text("# mine\n", encoding="utf-8")
    asker = Asker("", "", "", "y", "y")
    code, out = attempt(zsh, s.options(yes=False), asker, terminal=True, pins=pins)
    text = zshrc.read_text(encoding="utf-8")
    line = 'export PATH="$HOME/.local/bin:$PATH"'
    case(
        f"zsh as the login shell, the answer y: the line is appended to ~/.zshrc after a comment line "
        f"that names harness setup: {code} {asker.questions} {text!r}",
        ok=code == "0"
        and any(line in q and str(zshrc) in q for q in asker.questions)
        and text == f"# mine\n\n{PATH_COMMENT}\n{line}\n"
        and "harness setup" in PATH_COMMENT
        and PATH_BY_HAND + line not in out,
    )
    # A second run from the same shell, whose PATH did not read ~/.zshrc again, answered y: the
    # file already holds the line, so it holds one block.
    code, _ = attempt(zsh, s.options(yes=False), Asker("", "", "", "y", "y"), terminal=True, pins=pins)
    again_text = zshrc.read_text(encoding="utf-8")
    case(
        f"a second run answered y: ~/.zshrc holds one block: {code} {again_text!r}",
        ok=code == "0" and again_text == text and again_text.count(PATH_COMMENT) == 1,
    )
    # A ~/.zshrc that holds the same line without the comment, indented: nothing is appended.
    own = f"# mine\n  {line}\n"
    zshrc.write_text(own, encoding="utf-8")
    code, _ = attempt(zsh, s.options(yes=False), Asker("", "", "", "y", "y"), terminal=True, pins=pins)
    case(
        f"a ~/.zshrc that holds the line already, answered y: it is unchanged: {code}",
        ok=code == "0" and zshrc.read_text(encoding="utf-8") == own,
    )
    # A ~/.zshrc that holds another export PATH line, or the line in a comment: the line is appended.
    for other in ('export PATH="$HOME/bin:$PATH"\n', f"# {line}\n"):
        zshrc.write_text(other, encoding="utf-8")
        code, _ = attempt(zsh, s.options(yes=False), Asker("", "", "", "y", "y"), terminal=True, pins=pins)
        case(
            f"a ~/.zshrc that holds {other.strip()!r}, answered y: the line is appended: {code}",
            ok=code == "0" and zshrc.read_text(encoding="utf-8") == f"{other}\n{PATH_COMMENT}\n{line}\n",
        )
    # No ~/.zshrc: the append creates it with the block alone.
    zshrc.unlink()
    code, _ = attempt(zsh, s.options(yes=False), Asker("", "", "", "y", "y"), terminal=True, pins=pins)
    case(
        f"no ~/.zshrc, answered y: the append creates it with the block alone: {code}",
        ok=code == "0" and zshrc.read_text(encoding="utf-8") == f"{PATH_COMMENT}\n{line}\n",
    )
    zshrc.write_text(text, encoding="utf-8")
    # A shell that reads ~/.zshrc has the line's PATH: a second plan finds nothing missing.
    read = subprocess.run(
        ["/bin/sh", "-c", f'. "{zshrc}"; printf %s "$PATH"'],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env={"PATH": str(s.bin), "HOME": str(s.home)},
        timeout=TIMEOUT,
        check=False,
    ).stdout
    again = plan(dataclasses.replace(zsh, path=read), nothing, loaded, s.options(), pins)
    case(
        f"a second run in a shell that read ~/.zshrc finds nothing missing: {read!r} {again.path_line!r}",
        ok=read.startswith(str(s.home / ".local/bin")) and again.path_line == "",
    )
    for name, machine, options, answers, prepare in (
        ("the answer n", zsh, s.options(yes=False), ("", "", "", "n", "y"), None),
        ("--yes", zsh, s.options(), (), None),
        (
            "a login shell that is bash",
            dataclasses.replace(zsh, login_shell="/bin/bash"),
            s.options(yes=False),
            ("", "", "", "y"),
            None,
        ),
        ("a ~/.zshrc that is a symlink", zsh, s.options(yes=False), ("", "", "", "y"), "symlink"),
    ):
        target = s.root / "dotfiles-zshrc"
        zshrc.unlink(missing_ok=True)
        if prepare == "symlink":
            target.write_text("# managed\n", encoding="utf-8")
            zshrc.symlink_to(target)
        asker = Asker(*answers)
        code, out = attempt(machine, options, asker, terminal=True, pins=pins)
        case(
            f"{name}: ~/.zshrc is not written, and the line is printed by hand: {code} {asker.questions}",
            ok=code == "0"
            and (
                not zshrc.exists() if prepare is None else target.read_text(encoding="utf-8") == "# managed\n"
            )
            and PATH_BY_HAND + line in out
            and (
                name == "the answer n" or not any("~/.zshrc" in q or ".zshrc" in q for q in asker.questions)
            ),
        )


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
        machine = Machine("Linux", "x86_64", "ubuntu", home, {}, tmp, ())
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
            machine = Machine("Linux", "x86_64", "ubuntu", home, {}, tmp, ())
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
    for older in ("v20.16.0", "v22.11.0"):
        s.fake("node", f'echo "{older}"')
        lines = shows(s.machine(), profile_module.Setup(frontends=(), components=()), s.options(), pins)
        case(
            f"a Node.js {older}, below the 22.12 of srt, gets brew upgrade: {lines[:3]}",
            ok="brew upgrade node" in lines,
        )
    s.fake(
        "brew",
        f'[ "$1" = upgrade ] && printf \'#!/bin/sh\\necho v22.12.0\\n\' > "{s.bin / "node"}"; exit 0',
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
        # Without claude_remote, the launch agent of the autocommit job is not rendered; the
        # Kaimon and julia-update jobs render their profile and their plist each.
        case(
            f"a harness doctor that exits {status} gives {want}, after every earlier step: {code} {calls}",
            ok=code.startswith(want) and calls == ["install", "trust", *["render"] * 4, "doctor"],
        )
        if status == "1":
            case(
                f"doctor's output comes once, after the lines by hand: {out[-400:]!r}",
                ok=out.count("doctor: FAIL here") == 1
                and out.rfind("antigravity.google") < out.find("doctor: FAIL here"),
            )


def trust_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """`harness trust --apply` runs only with the frontend `claude`, and only once Claude Code has
    written ~/.claude.json (K126)."""
    s = scratch(tmp, "trust-no-state", MACOS_FAKES)
    (s.home / ".claude.json").unlink()
    code, out = attempt(s.machine(), s.options(), pins=pins)
    calls = [c.split()[1] for c in s.calls() if c.startswith("harness ")]
    case(
        f"without ~/.claude.json the run skips harness trust, names the step by hand, and goes on to "
        f"harness doctor: {code} {calls}",
        ok=code == "0"
        and "trust" not in calls
        and calls[-1] == "doctor"
        and "start claude once, then run harness trust --apply" in out
        and not (s.home / ".claude.json").exists(),
    )
    s = scratch(tmp, "trust-no-claude", MACOS_FAKES)
    chosen_profile(s, profile_module.Setup(frontends=("omp",), components=()))
    lines = shows(s.machine(), profile_module.Setup(frontends=("omp",), components=()), s.options(), pins)
    code, out = attempt(s.machine(), s.options(), pins=pins)
    calls = [c.split()[1] for c in s.calls() if c.startswith("harness ")]
    case(
        f"without the frontend claude the plan has no trust step, and the run runs none: {code} {calls}",
        ok=code == "0"
        and not any("harness trust" in line for line in lines)
        and "trust" not in calls
        and "harness trust" not in out,
    )


def sandbox_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """The Seatbelt profiles of the Kaimon and julia-update jobs: on macOS each is written before
    its plist is rendered, on Linux none is; and both plists start their program under
    sandbox-exec with that profile."""
    s = scratch(tmp, "macos-sandbox", MACOS_FAKES)
    lines = shows(s.machine(), JOBS_ONLY, s.options(), pins)

    def index(start: str, *, holds: str = "") -> int:
        return next((i for i, line in enumerate(lines) if line.startswith(start) and holds in line), -1)

    for job in jobsandbox.JOBS:
        at = [
            index(f"harness render sandbox/{job}.sb > {s.home / SANDBOX / f'{job}.sb'}"),
            index(f"harness render launchagents/{job}.plist > "),
            index("launchctl ", holds=f".{job}.plist"),
        ]
        case(
            f"on macOS, the profile of {job} is written before its plist is rendered and loaded: {at}",
            ok=-1 not in at and at == sorted(at),
        )
    chosen_profile(s, JOBS_ONLY)
    code, out = attempt(s.machine(), s.options(), pins=pins)
    written = {
        job: (s.home / SANDBOX / f"{job}.sb").read_text(encoding="utf-8")
        if (s.home / SANDBOX / f"{job}.sb").exists()
        else None
        for job in jobsandbox.JOBS
    }
    case(
        f"on macOS, the run writes each profile from harness render sandbox/<job>.sb: {code} {written}",
        ok=code == "0"
        and all(text == f"rendered {s.clone / 'sandbox' / f'{job}.sb'}\n" for job, text in written.items()),
    )
    case(
        f"no profile is written for the autocommit job: {out[-200:]!r}",
        ok=not (s.home / SANDBOX / "claude-autocommit.sb").exists(),
    )
    shim = s.home / SHIMS / "ps"
    case(
        "on macOS, one step installs the ps shim, mode 755, before kaimon's plist is rendered: "
        f"{[line for line in lines if 'shims' in line]}",
        ok=[line for line in lines if "shims" in line] == [f"install -m 755 {s.clone / PS_SHIM} {shim}"]
        and -1
        < index(f"install -m 755 {s.clone / PS_SHIM} ")
        < index("harness render launchagents/kaimon.plist > "),
    )
    case(
        f"on macOS, the run installs the clone's shim with mode 755: {shim.exists()}",
        ok=shim.is_file()
        and shim.read_bytes() == (s.clone / PS_SHIM).read_bytes()
        and oct(shim.stat().st_mode & 0o777) == "0o755",
    )
    s = scratch(tmp, "linux-sandbox", LINUX_FAKES)
    lines = shows(s.machine("Linux"), JOBS_ONLY, s.options(), pins)
    case(
        f"on Linux, no step writes a .sb file or the shim: {[line for line in lines if '.sb' in line]}",
        ok=bool(lines) and not any(".sb" in line or "shims" in line for line in lines),
    )
    paths = {
        job: cast(
            "str",
            plistlib.loads((REPO / "launchagents" / f"{job}.plist").read_bytes())["EnvironmentVariables"][
                "PATH"
            ],
        )
        for job in jobsandbox.JOBS
    }
    case(
        f"kaimon.plist's PATH starts with the shim directory, and julia-update.plist's names none: {paths}",
        ok=paths["kaimon"].startswith(f"{{home}}/{SHIMS}:") and "shims" not in paths["julia-update"],
    )
    programs = {"kaimon": "{home}/.julia/bin/kaimon", "julia-update": "{home}/.juliaup/bin/julia"}
    for job in jobsandbox.JOBS:
        args = cast(
            "list[str]",
            plistlib.loads((REPO / "launchagents" / f"{job}.plist").read_bytes())["ProgramArguments"],
        )
        want = ["/usr/bin/sandbox-exec", "-f", f"{{home}}/{SANDBOX}/{job}.sb", programs[job]]
        case(
            f"{job}.plist starts its program under sandbox-exec -f <its profile>: {args[:4]}",
            ok=args[:4] == want,
        )


def pocl_cases(case: Case, tmp: pathlib.Path, pins: Pins) -> None:
    """Kaimon's PoCL cache: the plist and the unit set POCL_CACHE_DIR below ~/.cache/kaimon, and on
    macOS and on Linux one step creates that directory, mode 700 where it creates it, before the
    Kaimon job is loaded, and leaves an existing directory as it is."""
    plist = plistlib.loads((REPO / "launchagents" / "kaimon.plist").read_bytes())
    variables = cast("dict[str, str]", plist["EnvironmentVariables"])
    case(
        f"kaimon.plist sets POCL_CACHE_DIR to {{home}}/{POCL_CACHE}: {variables.get('POCL_CACHE_DIR')!r}",
        ok=variables.get("POCL_CACHE_DIR") == f"{{home}}/{POCL_CACHE}",
    )
    unit = (REPO / "systemd" / "kaimon.service").read_text(encoding="utf-8").splitlines()
    case(
        f"kaimon.service sets POCL_CACHE_DIR to {{home}}/{POCL_CACHE}: "
        f"{[line for line in unit if 'POCL' in line]}",
        ok=[line for line in unit if "POCL" in line and not line.startswith("#")]
        == [f"Environment=POCL_CACHE_DIR={{home}}/{POCL_CACHE}"],
    )
    dummy = profile_module.load(profile_module.DUMMY, home=profile_module.DUMMY_HOME)
    rendered = plistlib.loads(
        profile_module.render_file(REPO / "launchagents" / "kaimon.plist", dummy).encode("utf-8")
    )
    got = cast("dict[str, str]", rendered["EnvironmentVariables"]).get("POCL_CACHE_DIR")
    case(
        f"kaimon.plist rendered with the dummy profile sets POCL_CACHE_DIR in its home: {got!r}",
        ok=got == f"{profile_module.DUMMY_HOME}/{POCL_CACHE}",
    )
    for system, fakes, load in (
        ("Darwin", MACOS_FAKES, "launchctl "),
        ("Linux", LINUX_FAKES, "systemctl "),
    ):
        s = scratch(tmp, f"pocl-{system}", fakes)
        machine = s.machine(system)
        options = s.options()
        loaded = profile_module.load(options.profile, home=str(machine.home))
        steps = plan(machine, JOBS_ONLY, loaded, options, pins).steps
        shown = [step.show for step in steps]
        target = s.home / POCL_CACHE
        at = [i for i, line in enumerate(shown) if POCL_CACHE in line]
        loads = [i for i, line in enumerate(shown) if line.startswith(load)]
        case(
            f"on {system}, one step creates ~/{POCL_CACHE}, before the first {load.strip()} step: "
            f"{[shown[i] for i in at]} at {at}, loads at {loads}",
            ok=[shown[i] for i in at] == [f"mkdir -p {target}, each new directory mode 700"]
            and bool(loads)
            and at[0] < loads[0],
        )
        if len(at) != 1:
            continue
        action = steps[at[0]].action
        first = action()
        modes = {
            str(d.relative_to(s.home)): oct(d.stat().st_mode & 0o777) if d.is_dir() else None
            for d in (target.parent.parent, target.parent, target)
        }
        case(
            f"on {system}, the step creates ~/{POCL_CACHE} and each directory it creates with mode 700: "
            f"{first!r} {modes}",
            ok=first is None and set(modes.values()) == {"0o700"},
        )
        target.chmod(0o755)
        second = action()
        case(
            f"on {system}, the step run again succeeds and leaves the existing ~/{POCL_CACHE} as it is: "
            f"{second!r} {oct(target.stat().st_mode & 0o777)}",
            ok=second is None and oct(target.stat().st_mode & 0o777) == "0o755",
        )
        shutil.rmtree(s.home / ".cache")
        (s.home / ".cache").write_text("", encoding="utf-8")
        failed = action()
        case(
            f"on {system}, a file at ~/.cache fails the step with the path: {failed!r}",
            ok=failed is not None and failed.startswith(f"cannot create {s.home / '.cache'}"),
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
        node_plan_cases(case, root, pins)
        step_cases(case, root, pins)
        helper_cases(case, root)
        dry_run_cases(case, root, pins)
        release_cases(case, root)
        tree_cases(case, root)
        tree_refusal_cases(case, root)
        srt_file_cases(case, root)
        srt_plan_cases(case, root, pins)
        srt_install_cases(case, root)
        srt_refusal_cases(case, root)
        ubuntu_2404_cases(case, root)
        interactive_cases(case, root, pins)
        question_cases(case, root, pins)
        token_cases(case, root)
        token_wait_cases(case, root, pins)
        clone_cases(case, root, pins)
        no_remote_cases(case, root, pins)
        ask_remote_cases(case, root, pins)
        path_cases(case, root, pins)
        yes_cases(case, root, pins)
        header_cases(case)
        string_header_cases(case, root, pins)
        edge_cases(case, root)
        redirect_cases(case, root)
        apt_cache_cases(case, root, pins)
        recheck_cases(case, root, pins)
        doctor_cases(case, root, pins)
        trust_cases(case, root, pins)
        sandbox_cases(case, root, pins)
        pocl_cases(case, root, pins)
    return total, wrong
