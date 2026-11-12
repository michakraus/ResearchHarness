"""The Seatbelt profiles of the launch agents `kaimon` and `julia-update` on macOS, and the
arguments of `bwrap` for their `systemd --user` units on Linux.

    harness render sandbox/kaimon.sb           # print the profile of the Kaimon server
    harness render sandbox/julia-update.sb     # print the profile of the update job
    harness render sandbox/kaimon.bwrap        # print the bwrap arguments of the Kaimon server
    harness render sandbox/julia-update.bwrap  # print the bwrap arguments of the update job
    harness test jobsandbox                    # the cases below

`sandbox/daemon.toml` holds the rules of both jobs. `load` reads it into a `DaemonPolicy`, a frozen
dataclass: once for both jobs the denied operations and the denied Mach services, on Linux the
system paths that both read (`linux_read`) and the root entries that are a link on one Linux and a
directory on another (`linux_links`), and for each job of JOBS, in a table `[job.<name>]`, its read
paths, read files, write paths, write files, write denies, the files that it writes back inside a
write deny, the directories that it writes on Linux only (`linux_write`), the paths below which it
connects to a Unix socket (`unix_sockets`), `pty`, whether it uses pseudo-terminals, and
`network`, one of NETWORKS (`JobRules`). Each key is required, `pty` is true or false, `network`
is the string "open" or "loopback", and a job with "open" has no `unix_sockets`, because it
reaches every socket. Each other value is a list of strings, and a path is a token of TOKENS
alone, or a start, `~`, nothing or a token, and then `/` and one or more segments, none of them
empty, `.` or `..`, so no `//` and no final `/`; a read file can also be the root `/` alone,
which dyld reads when a process starts. A `linux_write` path starts with `~/`. A path of
`linux_read` and `linux_links` is `/` and one or more such segments, and one of `linux_links` has
one segment only.
A system path is in its real form: a path at or below `/etc`, `/tmp` or `/var`, in any case of
letters, is refused, because Seatbelt matches a path after it resolves the symlink
`/etc -> private/etc`, and a file system that ignores case reads `/ETC` as `/etc`. A denied
operation is lower-case words joined by `-`, with `*` (OPERATION), because the renderer writes it
into the profile as it is. A file that is not UTF-8 or not TOML, a missing job or key, an unknown
key or job, a relative path, a path with such a segment, a path in its link form, another operation,
a `pty` that is not a boolean, a `network` that is not one of NETWORKS, a socket path of a job with
"open" and another value that is not a list of strings raise HarnessError, which names the key or
the path.

`profile` renders the profile of one job as SBPL text, in this order: `(version 1)`,
`(allow default)`, `(deny file-read* file-write*)`, `(allow file-read-metadata)`, one
`(allow file-read* …)` with a `subpath` per read path and a `literal` per read file, one
`(allow file-write* …)` with a `subpath` per write path and a `literal` per write file, for a job
with `pty = true` `(allow pseudo-tty)` and one `(allow file-read* file-write* file-ioctl …)` with
the `literal` PTY_MASTER and the `regex` PTY_SLAVES, both fixed in this module, one
`(deny file-write* …)` with a `subpath` per write deny and a `regex` per repository part of
REPOSITORY_PARTS at any depth below ~/Research, one `(allow file-write* …)` with a `literal` per
file written back, one `(deny <operation>)` per denied operation, and one `(deny mach-lookup …)`
with a `global-name` per denied service; and last, for a job with `network = "loopback"`, the
three rules of `network_rules`: `(deny network-outbound)`,
`(allow network-outbound (remote ip "localhost:*"))`, which allows a connect to 127.0.0.1 and
::1, and one `(allow network-outbound …)` with a `(remote unix-socket (subpath …))` per socket
path, the forms of srt. A job with "open" gets no rule of the network. Seatbelt applies the last
rule that matches, so the write denies follow the write allows, the files written back follow the
write denies, and the network allows follow the network deny and every other rule. A block whose
list is empty is left out, because a block with no filter matches every path, or every connect.
`~` becomes `home`, `$HARNESS` the profile's `harness`, and each `getconf` token its value
(`UserDirs`) without a final `/`, with a leading `/var/` written as `/private/var/`, in a socket
path as in a file rule. Every path and regex is an ordinary SBPL string, with `"` and `\\` escaped,
and a regex escapes the metacharacters of the home path.
`profile` reads no Linux key.

`bwrap_args` gives the static arguments of `bwrap` for one job, in this order: BWRAP_START, which
makes new namespaces of every kind but the network, ends the job with its unit, and mounts a new
/proc, the host's /dev, /sys read-only and a new /tmp; `--ro-bind-try` of each path of
`linux_read`; for each entry of `linux_links` as the host has it (`LinuxRoot`, `linux_root`)
`--symlink` of its target for a link and `--ro-bind` for a directory; `--tmpfs` of the home; then
`--ro-bind-try` of each read path and read file, `--bind-try` of each write path, write file and
`linux_write` path with `--bind` of each pin (`pins`) among them (`writable`), `--ro-bind` of
each write deny, and `--bind-try` of each file written back. Of the job's lists it takes only a
`~/` path, `~` becoming `home`, and `$HARNESS` and a path below it, `$HARNESS` becoming the
profile's `harness`: an absolute path, the root `/`, the `$DARWIN` tokens, MACOS_LIBRARY and
every path below it are macOS's, and `pty`, `network` and `unix_sockets` give no argument, so the
job keeps the network. A write deny that lies at or below no read path, write path or
`linux_write` path of the job is left out, because the job cannot see it. A pin is a path from a
write path of the job down to a bind source of the other job of JOBS, its pins included, which is
no effective mount point of the job yet (a bind destination that no later bind covers): bound onto
itself it is a mount point in the job's namespace, which the job cannot rename or remove while the
other job's `bwrap` mounts it, and a pin below a write deny of the job raises HarnessError. The
pins of the two jobs are computed against each other until no new pin appears, and each pin is
bound after the last write bind at or above it and before the first one after that below it, so
that no later bind covers it. `linux_dirs` names the write denies that are left in, the
`linux_write` paths and the pins that are directories, and `linux_files` the pins that are files,
which must exist before the job starts. An argument that holds a newline raises HarnessError,
because `jobbox` reads one argument per line.

`harness render` of a template `sandbox/<job>.sb` or `sandbox/<job>.bwrap` (`job_of`), a file
that does not exist, prints `render` of that job; a `.bwrap` template prints `bwrap_args` with the
profile's `home` and `harness` and `linux_root` of this host, one argument per line, and a `.sb`
template prints `profile` with the rule list `daemon.toml` beside the template, the profile's
`home` and `harness`, and the values of `getconf DARWIN_USER_TEMP_DIR` and
`getconf DARWIN_USER_CACHE_DIR`. A `getconf` that is not on the PATH, fails, or prints other than
one absolute path, a rule list that `load` refuses, a job that is not one of JOBS, and a `bwrap`
argument with a newline, end it with exit 2 and one line. `harness setup` on macOS and the
services script of the dotfiles kit write each `.sb` render into
`~/.config/research-harness/sandbox/<job>.sb` before they render and load the job's plist, and
before kaimon's profile they install PS_SHIM into SHIMS, which kaimon's profile reads and its plist
puts first on the job's PATH: the exec of the setuid /bin/ps fails under a Seatbelt profile, and
Kaimon reads a failed `ps -o state= -p PID` as a dead session. On Linux both, after the sandbox
check of `harness doctor`, install JOBBOX and UPDATE_SERVER into ~/.local/bin, write each
`.bwrap` render into `~/.config/research-harness/sandbox/<job>.bwrap` and create the directories
of `linux_dirs` and the files of `linux_files` before they render the units, which start each
job's program through `jobbox`, and julia-update's unit runs UPDATE_SERVER after it.

The cases on Linux's side check `load` of the Linux keys and its refusals, the order and the edges
of `bwrap_args` and its pins, `linux_root` on a scratch root, the render of `sandbox/<job>.bwrap`
through bin/harness with no `getconf` on the PATH, JOBBOX with a stub `bwrap` that writes its
arguments, its refusals, among them a bind source below the home that is a symbolic link or lies
below one, and shellcheck; UPDATE_SERVER with stubs of `lsof`, `readlink`, `systemctl` and
`notify-send`, against a state that holds a command substitution and a PATH that holds a
directory below the home, and shellcheck; and scripts/julia-update.jl run as on Linux
(JULIA_UPDATE_SYSTEM) with stubs of juliaup and the juliaup launcher: the update phase calls none
of the four, writes its state one value per line, and loads no package that a depot's default
environment names. No case starts the real `bwrap`. Without `julia` on the PATH the cases of the
script print a skip line, and without `shellcheck` its checks of JOBBOX and UPDATE_SERVER do.

The cases run PS_SHIM on each form that it accepts and on forms that it refuses, then start
`/bin/sh -c true` under the profile of each job, rendered with this user's home and `getconf`
directories, and expect exit 0; then, under kaimon's profile, this Python opening a pseudo-terminal
pair and forking `/bin/sh -c true` on a pseudo-terminal, as Kaimon starts a
session, and the juliaup launcher `~/.juliaup/bin/julia --startup-file=no -e 'exit(0)'`, which
opens juliaup's lock file for writing at every start, and expect exit 0 from each; and
`ps -o state= -p $$` under kaimon's profile with the PATH of kaimon's plist, which must print `S`
from the repository's shim and from the installed one; and the connects of `connect_cases`: under
kaimon's profile one to a TCP listener of the case on 127.0.0.1 succeeds and one to UNREACHABLE
fails with EPERM, under kaimon's rules with a scratch socket path below $DARWIN_USER_TEMP_DIR one
to a Unix socket below it succeeds and one to a socket beside it fails with EPERM, and under
julia-update's profile the connect to UNREACHABLE fails with no EPERM. No case connects to another
address or resolves a host name. Without `/usr/bin/sandbox-exec` or `getconf`, or where
`sandbox-exec` cannot apply even `(allow default)`, as inside another Seatbelt sandbox, they print
a skip line; where this Python cannot start under kaimon's profile, a skip line for the pty runs
and for its connects, where it cannot start under julia-update's, a skip line for that connect,
without the launcher a skip line for its run, and for a shim that is not at a path that kaimon's
profile reads, a skip line for its run.

`sandbox/probe-daemon.jl` holds the probes that a session runs through Kaimon's `ex` once the
server runs under its profile or its `bwrap`; the cases below run each probe of both systems'
sets against a scratch tree, where no sandbox applies, the network probes against a listener and
two resolver stubs of the case on loopback and never against their default targets, and check
the form of its result and the two sets of `run_all`. Without `julia` on the PATH they print a
skip line. `OPEN_GAPS` of the probe file names the negative probes that the profile does not stop, which
report `:allowed` under it: none. The cases check that value, that the file's header comment names
`OPEN_GAPS` and each open gap and expects no exception class of one, that it expects
`:ProcessFailedException` of `appleevent` and names its event, `name of startup disk`, that it
expects an `IOError` class of `connect_remote` and `:DNSError` of `resolve_name`, that the
network probes default to 127.0.0.1:2828, 1.1.1.1:443 and julialang.org (NETWORK_DEFAULTS), and
that the default command of `appleevent` asks the Finder for `name of startup disk`: AppleScript
answers `get name` of an application from the script itself and sends no Apple Event.
"""

import dataclasses
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Sequence
from typing import cast

from . import REPO, HarnessError
from .fsutil import Case

POLICY = REPO / "sandbox" / "daemon.toml"
PROBES = REPO / "sandbox" / "probe-daemon.jl"
JOBBOX = REPO / "sandbox" / "jobbox"
UPDATE_SCRIPT = REPO / "scripts" / "julia-update.jl"
UPDATE_SERVER = REPO / "scripts" / "julia-update-server"
JOBS = ("kaimon", "julia-update")
# The path-list keys of a job's table, its boolean key, its network key and the values of that key,
# and the keys of the rule list's top level.
JOB_KEYS = (
    "read",
    "read_files",
    "write",
    "write_files",
    "deny_write",
    "allow_write_files",
    "linux_write",
    "unix_sockets",
)
PTY_KEY = "pty"
NETWORK_KEY = "network"
NETWORKS = ("open", "loopback")
TOP_KEYS = ("deny_operations", "deny_services", "linux_read", "linux_links", "job")
TOKENS = ("$DARWIN_USER_TEMP_DIR", "$DARWIN_USER_CACHE_DIR", "$HARNESS")
# The first arguments of `bwrap` for every job: new namespaces of every kind but the network, the
# end of the job with its unit, a new /proc, the host's devices, /sys read-only, and a new tmpfs
# at JOB_TMP, the job's own /tmp, which hides the sockets and files of the host's /tmp.
JOB_TMP = "/tmp"  # noqa: S108 -- the mount point of the job's own tmpfs, not a file in the host's /tmp
BWRAP_START = (
    "--unshare-all",
    "--share-net",
    "--die-with-parent",
    "--proc",
    "/proc",
    "--dev-bind",
    "/dev",
    "/dev",
    "--ro-bind",
    "/sys",
    "/sys",
    "--tmpfs",
    JOB_TMP,
)
# The per-user library of macOS, which a rule path names for the logs of a launch agent: on Linux
# it and every path below it are left out.
MACOS_LIBRARY = "~/Library"
# The directories at the root of macOS that are symlinks into /private: a rule names the real path.
LINKS = ("etc", "tmp", "var")
# A denied operation of SBPL: lower-case words joined by `-`, with `*` for a family.
OPERATION = re.compile(r"[a-z][a-z*-]*")
# The exit status of a subcommand that fails.
FAILED = 2
# The parts of a repository that no job writes, at any depth below ~/Research: the hooks and the
# configuration of git, which name programs that the next git command runs, and a tracked hook
# directory.
REPOSITORY_PARTS = (".git/hooks", ".git/config", ".githooks")
# The pseudo-terminal devices of macOS that a job with `pty = true` opens: the master multiplexer,
# and a regex for every slave, `/dev/ttys` and a number. Both are fixed here, never read from the
# rule list.
PTY_MASTER = "/dev/ptmx"
PTY_SLAVES = "^/dev/ttys[0-9]+$"
# The metacharacters of a POSIX extended regex.
REGEX_META = re.compile(r"([\\.\[\]()*+?{}|^$])")
# The program that the plists start each job under.
SANDBOX_EXEC = pathlib.Path("/usr/bin/sandbox-exec")
# The directory that kaimon's plist puts first on the job's PATH, as a rule path, and the one
# program that `harness setup` installs there from the repository: a `ps` that answers Kaimon's
# liveness check of a session with `kill -0`, because the setuid /bin/ps does not start under a
# Seatbelt profile.
SHIMS = "~/.config/research-harness/sandbox/shims"
PS_SHIM = REPO / "sandbox" / "shims" / "ps"
# Seconds for one `getconf` or one `sandbox-exec`, and for the cold Julia process of the probe cases.
TIMEOUT, JULIA_TIMEOUT = 60, 600


@dataclasses.dataclass(frozen=True, slots=True)
class JobRules:
    """The file rules of one job, each path as `daemon.toml` writes it, the paths below which it
    connects to a Unix socket, whether it uses pseudo-terminals, and its network, one of
    NETWORKS."""

    read: tuple[str, ...]
    read_files: tuple[str, ...]
    write: tuple[str, ...]
    write_files: tuple[str, ...]
    deny_write: tuple[str, ...]
    allow_write_files: tuple[str, ...]
    linux_write: tuple[str, ...]
    unix_sockets: tuple[str, ...]
    pty: bool
    network: str


@dataclasses.dataclass(frozen=True, slots=True)
class DaemonPolicy:
    """The rule list of `daemon.toml`: the rules of each job of JOBS, the operations and Mach
    services that both deny, and on Linux the system paths that both read and the root entries
    that are a link on one Linux and a directory on another."""

    kaimon: JobRules
    julia_update: JobRules
    deny_operations: tuple[str, ...]
    deny_services: tuple[str, ...]
    linux_read: tuple[str, ...]
    linux_links: tuple[str, ...]

    def rules(self, job: str) -> JobRules:
        """The rules of `job`; HarnessError for a job that is not one of JOBS."""
        if job == "kaimon":
            return self.kaimon
        if job == "julia-update":
            return self.julia_update
        raise HarnessError(f"no job {job!r}; the jobs are {', '.join(JOBS)}")


@dataclasses.dataclass(frozen=True, slots=True)
class UserDirs:
    """The per-user directories of macOS, as `getconf DARWIN_USER_TEMP_DIR` and
    `getconf DARWIN_USER_CACHE_DIR` print them."""

    temp: str
    cache: str


@dataclasses.dataclass(frozen=True, slots=True)
class LinuxRoot:
    """The host's entries of `linux_links`: `(path, target)` for each that is a symbolic link, and
    the path of each that is a directory."""

    links: tuple[tuple[str, str], ...]
    dirs: tuple[str, ...]


def strings(value: object, key: str, path: pathlib.Path) -> tuple[str, ...]:
    """`value` as a tuple, when it is a list of strings."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in cast("list[object]", value)):
        raise HarnessError(f"{path}: `{key}` is not a list of strings")
    return tuple(cast("list[str]", value))


def checked_path(p: str, key: str, path: pathlib.Path) -> str:
    """`p`, when it is a start, `~`, nothing or a token of TOKENS, and then a remainder: `""` after
    a token, else `/` and one or more segments, none of them empty, `.` or `..`; and no link form
    of LINKS, in any case of letters. The root `/` alone is also a path of a `read_files` key,
    because dyld reads the root directory when a process starts."""
    if p == "/" and key.endswith(".read_files"):
        return p
    start = next((t for t in TOKENS if p.startswith(t)), "~" if p.startswith("~") else "")
    rest = p[len(start) :]
    if not (start in TOKENS and rest == "") and not (
        rest.startswith("/") and all(s not in {"", ".", ".."} for s in rest[1:].split("/"))
    ):
        raise HarnessError(
            f"{path}: `{key}` holds {p!r}, which is neither a token alone nor ~, nothing or one of "
            f"{', '.join(TOKENS)} and then / and segments, none of them empty, `.` or `..`"
        )
    if p.startswith("/") and pathlib.PurePosixPath(p).parts[1].lower() in LINKS:
        head, sep, tail = p[1:].partition("/")
        raise HarnessError(
            f"{path}: `{key}` holds {p!r}, not its real form /private/{head.lower()}{sep}{tail}"
        )
    return p


def operations(value: object, path: pathlib.Path) -> tuple[str, ...]:
    """The denied operations, when each is an operation name of OPERATION."""
    names = strings(value, "deny_operations", path)
    for name in names:
        if OPERATION.fullmatch(name) is None:
            raise HarnessError(f"{path}: `deny_operations` holds {name!r}, which is no operation of SBPL")
    return names


def job_rules(table: object, job: str, path: pathlib.Path) -> JobRules:
    """The rules of the table `[job.<job>]`."""
    if not isinstance(table, dict):
        raise HarnessError(f"{path}: `job.{job}` is not a table")
    entries = cast("dict[str, object]", table)
    for key in entries:
        if key not in (*JOB_KEYS, PTY_KEY, NETWORK_KEY):
            raise HarnessError(f"{path}: unknown key `job.{job}.{key}`")
    lists: dict[str, tuple[str, ...]] = {}
    for key in JOB_KEYS:
        where = f"job.{job}.{key}"
        if key not in entries:
            raise HarnessError(f"{path}: no key `{where}`")
        lists[key] = tuple(checked_path(p, where, path) for p in strings(entries[key], where, path))
    for p in lists["linux_write"]:
        if not p.startswith("~/"):
            raise HarnessError(f"{path}: `job.{job}.linux_write` holds {p!r}, which is not a path below ~/")
    if PTY_KEY not in entries:
        raise HarnessError(f"{path}: no key `job.{job}.{PTY_KEY}`")
    pty = entries[PTY_KEY]
    if not isinstance(pty, bool):
        raise HarnessError(f"{path}: `job.{job}.{PTY_KEY}` is not true or false")
    if NETWORK_KEY not in entries:
        raise HarnessError(f"{path}: no key `job.{job}.{NETWORK_KEY}`")
    network = entries[NETWORK_KEY]
    if not isinstance(network, str) or network not in NETWORKS:
        raise HarnessError(
            f"{path}: `job.{job}.{NETWORK_KEY}` is {network!r}, not one of {', '.join(map(repr, NETWORKS))}"
        )
    if network == "open" and lists["unix_sockets"]:
        raise HarnessError(
            f"{path}: `job.{job}.unix_sockets` holds {list(lists['unix_sockets'])}, but the job's "
            f"network is 'open', which reaches every socket"
        )
    return JobRules(**lists, pty=pty, network=network)


def linux_paths(value: object, key: str, path: pathlib.Path) -> tuple[str, ...]:
    """The system paths of the top-level key `key`, when each is `/` and one or more segments,
    none of them empty, `.` or `..`, and, in `linux_links`, a single segment."""
    paths = strings(value, key, path)
    for p in paths:
        segments = p[1:].split("/")
        if not p.startswith("/") or any(s in {"", ".", ".."} for s in segments):
            raise HarnessError(
                f"{path}: `{key}` holds {p!r}, which is not / and segments, none of them empty, `.` or `..`"
            )
        if key == "linux_links" and len(segments) > 1:
            raise HarnessError(f"{path}: `{key}` holds {p!r}, which is not an entry of the root /")
    return paths


def load(path: pathlib.Path) -> DaemonPolicy:
    """The rule list at `path`, checked as the module docstring says."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise HarnessError(f"cannot read {path}: {e.strerror}") from None
    except UnicodeDecodeError as e:
        raise HarnessError(f"{path}: not UTF-8 at byte {e.start}") from None
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path}: {e}") from None
    for key in TOP_KEYS:
        if key not in data:
            raise HarnessError(f"{path}: no key `{key}`")
    linux_read = linux_paths(data["linux_read"], "linux_read", path)
    linux_links = linux_paths(data["linux_links"], "linux_links", path)
    for key in data:
        if key not in TOP_KEYS:
            raise HarnessError(f"{path}: unknown key `{key}`")
    jobs = data["job"]
    if not isinstance(jobs, dict):
        raise HarnessError(f"{path}: `job` is not a table")
    tables = cast("dict[str, object]", jobs)
    for job in tables:
        if job not in JOBS:
            raise HarnessError(f"{path}: unknown key `job.{job}`")
    for job in JOBS:
        if job not in tables:
            raise HarnessError(f"{path}: no table `[job.{job}]`")
    return DaemonPolicy(
        kaimon=job_rules(tables["kaimon"], "kaimon", path),
        julia_update=job_rules(tables["julia-update"], "julia-update", path),
        deny_operations=operations(data["deny_operations"], path),
        deny_services=strings(data["deny_services"], "deny_services", path),
        linux_read=linux_read,
        linux_links=linux_links,
    )


def system_dir(value: str) -> str:
    """A `getconf` directory as a rule names it: no final `/`, and `/var/` as `/private/var/`."""
    value = value.rstrip("/")
    return "/private" + value if value.startswith("/var/") else value


def quoted(text: str) -> str:
    """`text` as an SBPL string: in double quotes, with `\\` and `"` escaped."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def regex_of(text: str) -> str:
    """The regex that matches `text` literally: each metacharacter of REGEX_META escaped."""
    return REGEX_META.sub(r"\\\1", text)


def part_regex(research: pathlib.Path, part: str) -> str:
    """The filter that matches the repository part `part` at any depth below `research`, and
    everything below it: the regex in an ordinary SBPL string, because a regex literal `#"…"` takes
    no escape and so cannot hold a `"`."""
    pattern = f"^{regex_of(str(research) + '/')}(.+/)?{regex_of(part)}(/|$)"
    return f"(regex {quoted(pattern)})"


def block(head: str, filters: list[str]) -> list[str]:
    """The lines of the rule `(head filter …)`, one filter per line; none for no filter."""
    if not filters:
        return []
    return [f"({head}", *(f"    {f}" for f in filters[:-1]), f"    {filters[-1]})"]


def pty_rules() -> list[str]:
    """The lines of the two rules that let a job use pseudo-terminals, as Apple's own profiles
    write them: the operation `pseudo-tty`, and reads, writes and ioctls of PTY_MASTER and of every
    slave of PTY_SLAVES."""
    filters = [f"(literal {quoted(PTY_MASTER)})", f"(regex {quoted(PTY_SLAVES)})"]
    return ["(allow pseudo-tty)", *block("allow file-read* file-write* file-ioctl", filters)]


def network_rules(sockets: list[str]) -> list[str]:
    """The lines of the three rules of a job with `network = "loopback"`, as srt writes them: the
    deny of all outbound traffic, the allow of the loopback addresses, and one allow with a filter
    of `sockets` per socket path, left out for none."""
    return [
        "(deny network-outbound)",
        '(allow network-outbound (remote ip "localhost:*"))',
        *block("allow network-outbound", sockets),
    ]


def profile(
    policy: DaemonPolicy, job: str, home: pathlib.Path, dirs: UserDirs, harness: pathlib.Path | None = None
) -> str:
    """The SBPL profile of `job`, as the module docstring says. `dirs` holds the values of the two
    `getconf` tokens, and `harness` is the profile's `harness`, `home/Research/Harness` without it."""
    rules = policy.rules(job)
    values = {
        "$DARWIN_USER_TEMP_DIR": system_dir(dirs.temp),
        "$DARWIN_USER_CACHE_DIR": system_dir(dirs.cache),
        "$HARNESS": str(harness if harness is not None else home / "Research" / "Harness"),
    }

    def real(p: str) -> str:
        if p.startswith("~/"):
            return str(home / p[2:])
        for token, value in values.items():
            if p == token or p.startswith(token + "/"):
                return value + p[len(token) :]
        return p

    def filters(paths: tuple[str, ...], files: tuple[str, ...]) -> list[str]:
        return [f"(subpath {quoted(real(p))})" for p in paths] + [
            f"(literal {quoted(real(p))})" for p in files
        ]

    lines = [
        f"; The Seatbelt profile of the job {job}, from sandbox/daemon.toml.",
        "(version 1)",
        "(allow default)",
        "(deny file-read* file-write*)",
        "(allow file-read-metadata)",
        *block("allow file-read*", filters(rules.read, rules.read_files)),
        *block("allow file-write*", filters(rules.write, rules.write_files)),
        *(pty_rules() if rules.pty else []),
        *block(
            "deny file-write*",
            filters(rules.deny_write, ()) + [part_regex(home / "Research", p) for p in REPOSITORY_PARTS],
        ),
        *block("allow file-write*", filters((), rules.allow_write_files)),
        *(f"(deny {operation})" for operation in policy.deny_operations),
        *block("deny mach-lookup", [f"(global-name {quoted(s)})" for s in policy.deny_services]),
        *(
            network_rules([f"(remote unix-socket (subpath {quoted(real(p))}))" for p in rules.unix_sockets])
            if rules.network == "loopback"
            else []
        ),
    ]
    return "\n".join(lines) + "\n"


def home_path(p: str, home: pathlib.Path, harness: pathlib.Path) -> pathlib.Path | None:
    """The rule path `p` on Linux: a `~/` path below `home`, `$HARNESS` and a path below it below
    `harness`, and None for every other path, which is macOS's, as is ~/Library and every path
    below it."""
    if p == MACOS_LIBRARY or p.startswith(MACOS_LIBRARY + "/"):
        return None
    if p.startswith("~/"):
        return home / p[2:]
    if p == "$HARNESS":
        return harness
    if p.startswith("$HARNESS/"):
        return harness / p[len("$HARNESS/") :]
    return None


def linux_lists(
    rules: JobRules, home: pathlib.Path, harness: pathlib.Path
) -> tuple[list[pathlib.Path], list[pathlib.Path], list[pathlib.Path], list[pathlib.Path]]:
    """The Linux paths of a job, in the order of the binds: what it reads, what it writes, its
    write denies and the files it writes back inside them. A write deny is left out when it lies
    at or below no read path and no write path, because the job cannot see it."""

    def linux(*keys: tuple[str, ...]) -> list[pathlib.Path]:
        return [q for ps in keys for p in ps if (q := home_path(p, home, harness)) is not None]

    reads = linux(rules.read, rules.read_files)
    writes = linux(rules.write, rules.write_files, rules.linux_write)
    seen = linux(rules.read, rules.write, rules.linux_write)
    denies = [d for d in linux(rules.deny_write) if any(d.is_relative_to(v) for v in seen)]
    return reads, writes, denies, linux(rules.allow_write_files)


def effective(paths: Sequence[pathlib.Path]) -> set[pathlib.Path]:
    """The effective mount points of binds with the destinations `paths`, in their order: each
    destination that no later bind covers at a strict ancestor."""
    return {p for i, p in enumerate(paths) if not any(p != q and p.is_relative_to(q) for q in paths[i + 1 :])}


def job_pins(
    policy: DaemonPolicy,
    job: str,
    home: pathlib.Path,
    harness: pathlib.Path,
    theirs: Sequence[tuple[pathlib.Path, bool]],
) -> tuple[list[tuple[pathlib.Path, bool]], list[str]]:
    """The pins of `job` against the other job's bind sources and its pins `theirs`, each with
    whether it is a file: for each such source S that lies strictly below a write path W of `job`,
    each path from W's child down to S that is no effective mount point of `job`'s binds, in that
    order. Then the refusals: one message for each such path at or below a write deny of `job`,
    which cannot be a pin."""
    rules = policy.rules(job)
    reads, writes, denies, back = linux_lists(rules, home, harness)
    other = policy.rules(next(j for j in JOBS if j != job))
    files = {
        q
        for p in (*other.read_files, *other.write_files, *other.allow_write_files)
        if (q := home_path(p, home, harness)) is not None
    } | {p for p, file in theirs if file}
    sources = [p for ps in linux_lists(other, home, harness) for p in ps] + [p for p, _ in theirs]
    bound = effective([*reads, *writes, *denies, *back])
    found: list[tuple[pathlib.Path, bool]] = []
    refused: list[str] = []
    for s in sources:
        for w in writes:
            if s == w or not s.is_relative_to(w):
                continue
            parts = s.relative_to(w).parts
            for i in range(1, len(parts) + 1):
                p = w.joinpath(*parts[:i])
                if p in bound or any(p == q for q, _ in found):
                    continue
                below = [d for d in denies if p.is_relative_to(d)]
                if below:
                    refused.append(f"the pin {p} of {job} lies below its write deny {below[0]}")
                    continue
                found.append((p, p == s and s in files))
    return found, refused


def pins(
    policy: DaemonPolicy, job: str, home: pathlib.Path, harness: pathlib.Path
) -> list[tuple[pathlib.Path, bool]]:
    """The pins of `job`, each with whether it is a file. A pin is a path that the other job of
    JOBS binds, or that lies on the way to such a bind, in a tree that `job` writes. `job` binds
    each pin onto itself, so that in its namespace the pin is a mount point, which it can neither
    rename nor remove, and the other job's bind does not follow a link that `job` put there. A pin
    is a bind source too, so the pins of both jobs are computed against each other until no new
    pin appears. HarnessError for a pin at or below a write deny of `job`."""
    found: dict[str, list[tuple[pathlib.Path, bool]]] = {j: [] for j in JOBS}
    while True:
        new = {j: job_pins(policy, j, home, harness, found[next(o for o in JOBS if o != j)]) for j in JOBS}
        if all(new[j][0] == found[j] for j in JOBS):
            if new[job][1]:
                raise HarnessError(new[job][1][0])
            return found[job]
        found = {j: new[j][0] for j in JOBS}


def linux_dirs(
    policy: DaemonPolicy, job: str, home: pathlib.Path, harness: pathlib.Path
) -> list[pathlib.Path]:
    """The directories that must exist before `job` starts under `bwrap`: each write deny of its
    arguments, which `--ro-bind` binds and which the job could create were it missing, each
    `linux_write` path, which `--bind-try` skips when it is missing, and each pin that is a
    directory, which `--bind` binds."""
    rules = policy.rules(job)
    _, _, denies, _ = linux_lists(rules, home, harness)
    return (
        denies
        + [q for p in rules.linux_write if (q := home_path(p, home, harness)) is not None]
        + [p for p, file in pins(policy, job, home, harness) if not file]
    )


def linux_files(
    policy: DaemonPolicy, job: str, home: pathlib.Path, harness: pathlib.Path
) -> list[pathlib.Path]:
    """The files that must exist before `job` starts under `bwrap`: each pin that is a file."""
    return [p for p, file in pins(policy, job, home, harness) if file]


def writable(
    writes: Sequence[pathlib.Path], pinned: Sequence[pathlib.Path]
) -> list[tuple[str, pathlib.Path]]:
    """The writable binds of a job, each with its flag: `--bind-try` for each of `writes`, in
    their order, and `--bind` for each pin of `pinned`, in its order, after the last bind at or
    above the pin and before the first bind after that one that lies strictly below the pin: no
    later bind covers the pin, and the pin covers no bind that the binds before it leave open."""
    group: list[tuple[str, pathlib.Path]] = [("--bind-try", p) for p in writes]
    for pin in pinned:
        lo = max((i + 1 for i, (_, q) in enumerate(group) if pin.is_relative_to(q)), default=0)
        at = next(
            (i for i in range(lo, len(group)) if group[i][1] != pin and group[i][1].is_relative_to(pin)),
            len(group),
        )
        group.insert(at, ("--bind", pin))
    return group


def bwrap_args(
    policy: DaemonPolicy, job: str, home: pathlib.Path, root: LinuxRoot, harness: pathlib.Path | None = None
) -> tuple[str, ...]:
    """The static arguments of `bwrap` for `job`, as the module docstring says. `harness` is the
    profile's `harness`, `home/Research/Harness` without it. HarnessError for an argument that
    holds a newline, because `jobbox` reads one argument per line."""
    rules = policy.rules(job)
    harness = harness or home / "Research" / "Harness"
    reads, writes, denies, back = linux_lists(rules, home, harness)

    def bind(flag: str, paths: Sequence[pathlib.Path | str]) -> list[str]:
        return [x for p in paths for x in (flag, str(p), str(p))]

    args = [
        *BWRAP_START,
        *bind("--ro-bind-try", policy.linux_read),
        *(x for path, target in root.links for x in ("--symlink", target, path)),
        *bind("--ro-bind", root.dirs),
        "--tmpfs",
        str(home),
        *bind("--ro-bind-try", reads),
        *(
            x
            for flag, p in writable(writes, [p for p, _ in pins(policy, job, home, harness)])
            for x in bind(flag, [p])
        ),
        *bind("--ro-bind", denies),
        *bind("--bind-try", back),
    ]
    for a in args:
        if "\n" in a:
            raise HarnessError(f"the bwrap argument {a!r} of {job} holds a newline")
    return tuple(args)


def linux_root(policy: DaemonPolicy, base: pathlib.Path = pathlib.Path("/")) -> LinuxRoot:
    """The host's entries of `linux_links`, read below `base`, the root `/` by default: a symbolic
    link gives `(path, target)`, a directory its path, and anything else, such as a missing entry,
    nothing."""
    links: list[tuple[str, str]] = []
    dirs: list[str] = []
    for p in policy.linux_links:
        entry = base / p[1:]
        if entry.is_symlink():
            links.append((p, str(entry.readlink())))
        elif entry.is_dir():
            dirs.append(p)
    return LinuxRoot(tuple(links), tuple(dirs))


def job_of(template: pathlib.Path) -> str | None:
    """The job of a template `sandbox/<job>.sb` or `sandbox/<job>.bwrap`, else None."""
    suffixes = (".sb", ".bwrap")
    return template.stem if template.parent.name == "sandbox" and template.suffix in suffixes else None


def getconf(name: str) -> str:
    """The value of `getconf name`; HarnessError for a getconf that is not on the PATH, fails, or
    prints other than one absolute path."""
    program = shutil.which("getconf")
    if program is None:
        raise HarnessError(f"getconf {name}: no getconf on the PATH")
    try:
        p = subprocess.run(
            [program, name],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except OSError as e:
        raise HarnessError(f"getconf {name}: cannot start {program}: {e.strerror}") from None
    value = p.stdout.strip()
    if p.returncode != 0:
        raise HarnessError(f"getconf {name}: exit {p.returncode}")
    if not value.startswith("/") or "\n" in value:
        raise HarnessError(f"getconf {name}: printed {value!r}, not one absolute path")
    return value


def render(template: pathlib.Path, home: pathlib.Path, harness: pathlib.Path) -> str:
    """The profile of the job of `template`, a path `sandbox/<job>.sb`, or the arguments of `bwrap`
    of the job of a path `sandbox/<job>.bwrap`, one per line, from the rule list beside it."""
    job = job_of(template)
    if job is None or job not in JOBS:
        raise HarnessError(f"{template}: no job {job!r}; the jobs are {', '.join(JOBS)}")
    policy = load(template.parent / "daemon.toml")
    if template.suffix == ".bwrap":
        return "".join(a + "\n" for a in bwrap_args(policy, job, home, linux_root(policy), harness))
    dirs = UserDirs(getconf("DARWIN_USER_TEMP_DIR"), getconf("DARWIN_USER_CACHE_DIR"))
    return profile(policy, job, home, dirs, harness)


# ------------------------------------------------------------------------------ the cases ----

HOME = pathlib.Path("/h/a.b")
TEMP, CACHE = "/var/folders/xy/T/", "/var/folders/xy/C/"
DIRS = UserDirs(TEMP, CACHE)
# The rule of kaimon's profile, rendered with HOME, that writes juliaup's lock file back.
LOCK_ALLOW = '(allow file-write*\n    (literal "/h/a.b/.julia/juliaup/.juliaup-lock"))'
# The two rules of a profile whose job uses pseudo-terminals, as the renderer writes them.
PTY_ALLOW = (
    "(allow pseudo-tty)\n"
    '(allow file-read* file-write* file-ioctl\n    (literal "/dev/ptmx")\n    (regex "^/dev/ttys[0-9]+$"))\n'
)
# The last lines of kaimon's profile, rendered with HOME: the network rules of a loopback job.
NETWORK_TAIL = [
    "(deny network-outbound)",
    '(allow network-outbound (remote ip "localhost:*"))',
    "(allow network-outbound",
    '    (remote unix-socket (subpath "/h/a.b/.cache/kaimon")))',
]
# A regex filter of a profile, `(regex "…")`, and an escape of an SBPL string.
REGEX_FILTER = re.compile(r'\(regex "((?:[^"\\]|\\.)*)"\)')
SBPL_ESCAPE = re.compile(r"\\(.)")


def rule_block(text: str, head: str) -> str:
    """The rule of `text` that starts with `head`, to its closing parenthesis; "" without one."""
    i = text.find(head)
    if i < 0:
        return ""
    depth = 0
    for j in range(i, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return text[i : j + 1]
    return ""


def raises(f: Callable[[], object]) -> bool:
    """Whether `f()` raises HarnessError."""
    try:
        f()
    except HarnessError:
        return True
    return False


def message(f: Callable[[], object]) -> str:
    """The message of the HarnessError that `f()` raises; "" when it raises none."""
    try:
        f()
    except HarnessError as e:
        return str(e)
    return ""


def list_cases(case: Case, policy: DaemonPolicy) -> None:
    """The shipped rule list holds the decided paths."""
    k, u = policy.kaimon, policy.julia_update
    reads = (
        "~/Research",
        "~/.julia",
        "~/.juliaup",
        "~/.config/kaimon",
        "~/.cache/kaimon",
        "~/Library/Logs/kaimon",
    )
    system = ("/System", "/usr", "/bin", "/Library", "/private/etc", "/dev", "/opt/homebrew")
    tokens = ("$DARWIN_USER_TEMP_DIR", "$DARWIN_USER_CACHE_DIR")
    case(
        f"kaimon reads the decided paths and both tokens, and the files / and ~/.gitconfig: {k.read} "
        f"{k.read_files}",
        ok=all(p in k.read for p in (*reads, *system, *tokens)) and k.read_files == ("/", "~/.gitconfig"),
    )
    case(
        f"both jobs read the root directory / as a file and as no subtree: {k.read_files} {u.read_files}",
        ok=all("/" in j.read_files and "/" not in j.read for j in (k, u)),
    )
    secret = ("~/.claude", "~/.omp", "~/.ssh", "~/.config/opencode", "~/.config/gh")
    case(
        "kaimon reads nothing below a frontend's directory, ~/.ssh or ~/.config/gh, and not ~/.config whole",
        ok=not any(p == s or p.startswith(s + "/") for p in k.read + k.read_files for s in secret)
        and "~/.config" not in k.read,
    )
    writes = ("~/Research", "~/.julia", "~/.cache/kaimon", "~/Library/Logs/kaimon", "$DARWIN_USER_TEMP_DIR")
    case(
        f"kaimon writes the decided paths and the temp token: {k.write}", ok=all(p in k.write for p in writes)
    )
    case(
        f"kaimon denies writes to the depot's programs, startup code and juliaup, and to the hooks' source: "
        f"{k.deny_write}",
        ok=set(k.deny_write) == {"~/.julia/bin", "~/.julia/config", "~/.julia/juliaup", "$HARNESS/githooks"},
    )
    case(
        f"kaimon writes back into a denied directory only juliaup's lock file, and julia-update nothing: "
        f"{k.allow_write_files} {u.allow_write_files}",
        ok=k.allow_write_files == ("~/.julia/juliaup/.juliaup-lock",) and u.allow_write_files == (),
    )
    case(f"kaimon uses pseudo-terminals and julia-update does not: {k.pty} {u.pty}", ok=k.pty and not u.pty)
    case(
        f"kaimon reaches loopback and the Unix sockets below ~/.cache/kaimon, and julia-update the "
        f"network: {k.network} {k.unix_sockets} {u.network} {u.unix_sockets}",
        ok=(k.network, k.unix_sockets, u.network, u.unix_sockets)
        == ("loopback", ("~/.cache/kaimon",), "open", ()),
    )

    def near(p: str) -> bool:
        return p == SHIMS or SHIMS.startswith(p + "/") or p.startswith(SHIMS + "/")

    case(
        f"kaimon reads its shim directory {SHIMS} and no directory above it: {k.read}",
        ok=SHIMS in k.read and not any(SHIMS.startswith(p + "/") for p in k.read),
    )
    case(
        "neither job writes the shim directory, a directory above it or a path below it, and "
        "julia-update does not read it",
        ok=not any(near(p) for j in (k, u) for p in j.write + j.write_files + j.allow_write_files)
        and not any(near(p) for p in u.read + u.read_files),
    )
    case(
        f"julia-update writes ~/.juliaup and ~/.julia/juliaup and denies neither: {u.write} {u.deny_write}",
        ok=all(p in u.write and p not in u.deny_write for p in ("~/.juliaup", "~/.julia/juliaup")),
    )
    case(
        f"julia-update reads its installed script and the profile: {u.read_files}",
        ok=all(
            p in u.read_files
            for p in ("~/.local/bin/julia-update.jl", "~/.config/research-harness/profile.toml")
        ),
    )
    case(
        f"both deny the four escapes and the two Launch Services: "
        f"{policy.deny_operations} {policy.deny_services}",
        ok=policy.deny_operations == ("lsopen", "appleevent-send", "file-mount", "file-unmount")
        and policy.deny_services
        == ("com.apple.coreservices.launchservicesd", "com.apple.CoreServices.coreservicesd"),
    )


def network_variants(text: str) -> list[tuple[str, str, str]]:
    """The broken network keys of the rule list `text`: (label, the broken text, what the message
    names)."""
    loopback, sockets = 'network = "loopback"', 'unix_sockets = ["~/.cache/kaimon"]'
    return [
        ("an unknown network", text.replace(loopback, 'network = "closed"', 1), "job.kaimon.network"),
        ("a network in capitals", text.replace(loopback, 'network = "Loopback"', 1), "job.kaimon.network"),
        ("a network that is a boolean", text.replace(loopback, "network = true", 1), "job.kaimon.network"),
        (
            "a network that is a list",
            text.replace(loopback, 'network = ["loopback"]', 1),
            "job.kaimon.network",
        ),
        ("kaimon without network", text.replace(loopback + "\n", "", 1), "no key `job.kaimon.network`"),
        (
            "julia-update without network",
            text.replace('network = "open"\n', "", 1),
            "no key `job.julia-update.network`",
        ),
        (
            "kaimon without unix_sockets",
            text.replace(sockets + "\n", "", 1),
            "no key `job.kaimon.unix_sockets`",
        ),
        (
            "unix_sockets that are a string",
            text.replace(sockets, 'unix_sockets = "~/.cache/kaimon"', 1),
            "job.kaimon.unix_sockets",
        ),
        (
            "unix_sockets with a number",
            text.replace(sockets, "unix_sockets = [1]", 1),
            "job.kaimon.unix_sockets",
        ),
        ("a relative socket path", text.replace(sockets, 'unix_sockets = ["cache"]', 1), "'cache'"),
        (
            "a socket path with ..",
            text.replace(sockets, 'unix_sockets = ["~/.cache/../.ssh"]', 1),
            "'~/.cache/../.ssh'",
        ),
        (
            "a socket path in its link form",
            text.replace(sockets, 'unix_sockets = ["/var/run"]', 1),
            "'/var/run'",
        ),
        (
            "a socket path of a job with the network open",
            text.replace("unix_sockets = []", 'unix_sockets = ["~/.cache/kaimon"]', 1),
            "job.julia-update.unix_sockets",
        ),
    ]


def bad_cases(case: Case, root: pathlib.Path) -> None:
    """Each broken rule list raises HarnessError, in one line that names the key or the path."""
    text = POLICY.read_text(encoding="utf-8")
    start = text.index("\nread = [") + 1
    end = text.index("]\n", start) + 2
    variants = [
        (
            "a list without julia-update",
            text.replace("[job.julia-update]", "[job.unused-name]"),
            "job.unused-name",
        ),
        (
            "a list without the table of julia-update",
            text.split("[job.julia-update]")[0],
            "[job.julia-update]",
        ),
        ("a key `reed`", text.replace("\nread = [", "\nreed = [", 1), "job.kaimon.reed"),
        ("an unknown key at the top", "deny_files = []\n" + text, "deny_files"),
        (
            "a list without deny_services",
            re.sub(r"^deny_services = .*\n", "", text, flags=re.M),
            "deny_services",
        ),
        (
            "a job without write_files",
            re.sub(r"^write_files = .*\n", "", text, count=1, flags=re.M),
            "write_files",
        ),
        (
            "a job without allow_write_files",
            re.sub(r"^allow_write_files = .*\n", "", text, count=1, flags=re.M),
            "job.kaimon.allow_write_files",
        ),
        ("kaimon without pty", text.replace("\npty = true\n", "\n", 1), "no key `job.kaimon.pty`"),
        (
            "julia-update without pty",
            text.replace("\npty = false\n", "\n", 1),
            "no key `job.julia-update.pty`",
        ),
        ("a pty that is a string", text.replace("\npty = true\n", '\npty = "true"\n', 1), "job.kaimon.pty"),
        ("a pty that is a number", text.replace("\npty = true\n", "\npty = 1\n", 1), "job.kaimon.pty"),
        (
            "a pty that is a list",
            text.replace("\npty = false\n", "\npty = [false]\n", 1),
            "job.julia-update.pty",
        ),
        (
            "the path / as a file written back",
            text.replace(
                'allow_write_files = ["~/.julia/juliaup/.juliaup-lock"]', 'allow_write_files = ["/"]', 1
            ),
            "job.kaimon.allow_write_files",
        ),
        (
            "a file written back with ..",
            text.replace(
                'allow_write_files = ["~/.julia/juliaup/.juliaup-lock"]',
                'allow_write_files = ["~/.julia/juliaup/../juliaup/juliaup.json"]',
                1,
            ),
            "'~/.julia/juliaup/../juliaup/juliaup.json'",
        ),
        ("a path `Research`", text.replace('"~/Research"', '"Research"', 1), "'Research'"),
        ("a path `~`", text.replace('"~/Research"', '"~"', 1), "'~'"),
        (
            "a token with no `/` after it",
            text.replace('"$HARNESS/githooks"', '"$HARNESSx"', 1),
            "'$HARNESSx'",
        ),
        ("the link form /etc/hosts", text.replace('"/private/etc"', '"/etc/hosts"', 1), "'/etc/hosts'"),
        ("the link form /etc", text.replace('"/private/etc"', '"/etc"', 1), "'/etc'"),
        ("the link form /tmp", text.replace('"/private/tmp"', '"/tmp"', 1), "'/tmp'"),
        (
            "the link form /var/db/timezone",
            text.replace('"/private/var/db/timezone"', '"/var/db/timezone"', 1),
            "'/var/db/timezone'",
        ),
        (
            "read paths that are a string",
            text[:start] + 'read = "~/Research"\n' + text[end:],
            "job.kaimon.read",
        ),
        (
            "a list with a number",
            text.replace('read_files = ["/", "~/.gitconfig"]', "read_files = [1]", 1),
            "read_files",
        ),
        (
            "denied services that are a string",
            re.sub(r"^deny_services = .*$", 'deny_services = "x"', text, flags=re.M),
            "deny_services",
        ),
        ("a job that is no table", text.split("[job.kaimon]")[0] + "job = 1\n", "`job` is not a table"),
        (
            "a job table that is no table",
            text.split("[job.kaimon]")[0] + "job = {kaimon = 1, julia-update = 1}\n",
            "job.kaimon",
        ),
        ("no TOML", text + "\n[", "daemon.toml"),
        ("a path with //", text.replace('"/private/etc"', '"//etc"', 1), "'//etc'"),
        ("a path with ..", text.replace('"/private/etc"', '"/private/../etc"', 1), "'/private/../etc'"),
        ("a home path with ..", text.replace('"~/Research"', '"~/../.ssh"', 1), "'~/../.ssh'"),
        ("a path with .", text.replace('"~/Research"', '"~/Research/."', 1), "'~/Research/.'"),
        ("a path with a final /", text.replace('"~/Research"', '"~/Research/"', 1), "'~/Research/'"),
        ("the path / as a read path", text.replace('"/private/etc"', '"/"', 1), "'/'"),
        (
            "the path / as a write file",
            text.replace('write_files = ["/dev/null"', 'write_files = ["/"', 1),
            "job.kaimon.write_files",
        ),
        (
            "a token path with ..",
            text.replace('"$HARNESS/githooks"', '"$HARNESS/../githooks"', 1),
            "'$HARNESS/../githooks'",
        ),
        (
            "an operation that holds SBPL",
            text.replace('"lsopen"', '"lsopen) (allow file-read* (subpath \\"/\\")"', 1),
            "deny_operations",
        ),
        ("an empty operation", text.replace('"lsopen"', '""', 1), "deny_operations"),
        *network_variants(text),
    ]
    f = root / "daemon.toml"
    for label, body, named in [*variants, ("a list that is not UTF-8", None, "daemon.toml")]:
        if body is None:
            f.write_bytes(text.replace("~/Research", "~/R\xe9search", 1).encode("latin-1"))
        else:
            f.write_text(body, encoding="utf-8")
        try:
            load(f)
        except HarnessError as e:
            case(
                f"{label} raises HarnessError naming {named}: {e}", ok=named in str(e) and "\n" not in str(e)
            )
            continue
        case(f"{label} raises HarnessError, but the list loads", ok=False)
    case("a missing rule list raises HarnessError", ok=raises(lambda: load(root / "none.toml")))
    path_cases(case, f)


def path_cases(case: Case, f: pathlib.Path) -> None:
    """The grammar of a path: a final `/`, `//`, `.` and `..` refused after each start, a link form
    refused in any case of letters, and a bare token and a path below each start accepted; the root
    `/` accepted as a read file only, and every other refusal held for a read file and a file
    written back too."""
    refused = [
        p
        for start in ("~", "", "$HARNESS", "$DARWIN_USER_TEMP_DIR")
        for p in (
            f"{start}/",
            f"{start}/x/",
            f"{start}//x",
            f"{start}/x//y",
            f"{start}/./x",
            f"{start}/x/.",
            f"{start}/../x",
            f"{start}/x/..",
        )
    ]
    keys = [f"job.kaimon.{k}" for k in JOB_KEYS]
    bad = [
        (p, key)
        for p in [*refused, "$HARNESSX/y", "$HARNESSxy/z", "/ETC/hosts", "/Tmp/x", "/VAR"]
        for key in ("job.kaimon.read", "job.kaimon.read_files", "job.kaimon.allow_write_files")
        if not (p == "/" and key == "job.kaimon.read_files")
    ] + [("/", key) for key in keys if key != "job.kaimon.read_files"]
    for p, key in bad:
        try:
            checked_path(p, key, f)
        except HarnessError as e:
            case(
                f"the path {p!r} in {key} raises HarnessError naming it: {e}",
                ok=repr(p) in str(e) and f"`{key}`" in str(e) and "\n" not in str(e),
            )
            continue
        case(f"the path {p!r} in {key} raises HarnessError, but it is accepted", ok=False)
    case(
        "the root / is accepted as a read file of either job",
        ok=not raises(lambda: checked_path("/", "job.julia-update.read_files", f))
        and not raises(lambda: checked_path("/", "job.kaimon.read_files", f)),
    )
    for p, real in (
        ("/ETC/hosts", "/private/etc/hosts"),
        ("/Tmp/x", "/private/tmp/x"),
        ("/VAR", "/private/var"),
    ):
        try:
            checked_path(p, "job.kaimon.read", f)
        except HarnessError as e:
            case(
                f"the link form {p!r} names its real form {real}: {e}",
                ok=str(e).endswith(f"real form {real}"),
            )
            continue
        case(f"the link form {p!r} raises HarnessError, but it is accepted", ok=False)
    for p in (
        "$HARNESS",
        "$DARWIN_USER_CACHE_DIR",
        "$DARWIN_USER_TEMP_DIR",
        "~/x",
        "/private/x",
        "$HARNESS/x",
    ):
        case(f"the path {p!r} is accepted", ok=not raises(lambda p=p: checked_path(p, "job.kaimon.read", f)))
    for p in ("~/.julia/juliaup/.juliaup-lock", "/private/x", "$HARNESS/x"):
        case(
            f"the path {p!r} is accepted as a file written back",
            ok=not raises(lambda p=p: checked_path(p, "job.kaimon.allow_write_files", f)),
        )


def linux_list_cases(case: Case, policy: DaemonPolicy) -> None:
    """The shipped rule list holds the decided Linux keys, and the Seatbelt profiles leave out
    `linux_write`."""
    case(
        f"linux_read holds the decided system paths: {policy.linux_read}",
        ok=policy.linux_read == ("/usr", "/etc", "/opt", "/run/systemd/resolve"),
    )
    case(
        f"linux_links holds the decided root entries: {policy.linux_links}",
        ok=policy.linux_links == ("/bin", "/sbin", "/lib", "/lib64", "/lib32"),
    )
    case(
        f"julia-update writes ~/.cache/julia-update on Linux only, and kaimon nothing more: "
        f"{policy.julia_update.linux_write} {policy.kaimon.linux_write}",
        ok=policy.julia_update.linux_write == ("~/.cache/julia-update",) and policy.kaimon.linux_write == (),
    )
    case(
        "no Seatbelt profile names ~/.cache/julia-update",
        ok=not any(".cache/julia-update" in profile(policy, job, HOME, DIRS) for job in JOBS),
    )


def linux_bad_cases(case: Case, root: pathlib.Path) -> None:
    """Each broken Linux key raises HarnessError, in one line that names the key or the path."""
    text = POLICY.read_text(encoding="utf-8")
    reads, links = 'linux_read = ["/usr"', 'linux_links = ["/bin"'
    update_write = 'linux_write = ["~/.cache/julia-update"]'
    variants = [
        ("a list without linux_read", re.sub(r"^linux_read = .*\n", "", text, flags=re.M), "linux_read"),
        ("a list without linux_links", re.sub(r"^linux_links = .*\n", "", text, flags=re.M), "linux_links"),
        (
            "a linux_read that is a string",
            text.replace(reads, 'linux_read = "/usr"\nx = ["/usr"', 1),
            "linux_read",
        ),
        ("a linux_read with a number", text.replace(reads, "linux_read = [1", 1), "linux_read"),
        ("a relative linux_read path", text.replace(reads, 'linux_read = ["usr"', 1), "'usr'"),
        ("a linux_read path with ..", text.replace(reads, 'linux_read = ["/usr/../etc"', 1), "'/usr/../etc'"),
        ("a linux_read path with .", text.replace(reads, 'linux_read = ["/usr/."', 1), "'/usr/.'"),
        ("a linux_read path with //", text.replace(reads, 'linux_read = ["//usr"', 1), "'//usr'"),
        ("a linux_read path with a final /", text.replace(reads, 'linux_read = ["/usr/"', 1), "'/usr/'"),
        ("the root / in linux_read", text.replace(reads, 'linux_read = ["/"', 1), "'/'"),
        ("a home path in linux_read", text.replace(reads, 'linux_read = ["~/usr"', 1), "'~/usr'"),
        ("a linux_links entry below /", text.replace(links, 'linux_links = ["/usr/bin"', 1), "'/usr/bin'"),
        ("a relative linux_links entry", text.replace(links, 'linux_links = ["bin"', 1), "'bin'"),
        ("a linux_links entry with ..", text.replace(links, 'linux_links = ["/.."', 1), "'/..'"),
        ("the root / in linux_links", text.replace(links, 'linux_links = ["/"', 1), "'/'"),
        (
            "a list without job.julia-update.linux_write",
            text.replace(update_write + "\n", "", 1),
            "job.julia-update.linux_write",
        ),
        ("a linux_write path /var/x", text.replace(update_write, 'linux_write = ["/var/x"]', 1), "'/var/x'"),
        ("a linux_write path /opt/x", text.replace(update_write, 'linux_write = ["/opt/x"]', 1), "'/opt/x'"),
        (
            "a linux_write path $HARNESS/x",
            text.replace(update_write, 'linux_write = ["$HARNESS/x"]', 1),
            "'$HARNESS/x'",
        ),
        (
            "a linux_write path ~/a/../b",
            text.replace(update_write, 'linux_write = ["~/a/../b"]', 1),
            "'~/a/../b'",
        ),
        (
            "a linux_write that is a string",
            text.replace(update_write, 'linux_write = "~/x"', 1),
            "linux_write",
        ),
    ]
    f = root / "daemon.toml"
    for label, body, named in variants:
        f.write_text(body, encoding="utf-8")
        try:
            load(f)
        except HarnessError as e:
            case(
                f"{label} raises HarnessError naming {named}: {e}",
                ok=body != text and named in str(e) and "\n" not in str(e),
            )
            continue
        case(f"{label} raises HarnessError, but the list loads", ok=False)


# The host root of the bwrap cases: two root entries that are links into /usr, one directory.
ROOT = LinuxRoot((("/bin", "usr/bin"), ("/lib", "usr/lib")), ("/lib64",))
# The arguments that every job's list starts with, joined by spaces, as the decision of the
# namespaces and the system mounts writes them, and their number.
BWRAP_HEAD = (
    "--unshare-all --share-net --die-with-parent --proc /proc --dev-bind /dev /dev --ro-bind /sys /sys "
    "--tmpfs /tmp"
)
HEAD = BWRAP_HEAD.count(" ") + 1


def triple(args: tuple[str, ...], flag: str, path: str, target: str | None = None) -> int:
    """The index of `flag path path` in `args`, `--symlink target path` with a target; -1
    without one."""
    want = (flag, target, path) if target is not None else (flag, path, path)
    return next((i for i in range(len(args) - 2) if args[i : i + 3] == want), -1)


def binds(args: tuple[str, ...], flag: str) -> list[str]:
    """The source of each `flag source target` of `args`, in order."""
    return [args[i + 1] for i in range(len(args) - 2) if args[i] == flag]


def unpinned(policy: DaemonPolicy) -> list[str]:
    """Each path that the closure of the pins leaves open: for each bind source S of one job's
    arguments, the pins included, and each write bind W of the other job strictly above S, each
    path from W's child down to S that is no effective mount point of the other job, that is the
    destination of a bind that no later bind of its arguments covers at a strict ancestor."""
    flags = ("--bind", "--bind-try", "--ro-bind", "--ro-bind-try")
    args = {job: bwrap_args(policy, job, HOME, LinuxRoot((), ())) for job in JOBS}
    mounts = {
        job: [
            (a[i], pathlib.Path(a[i + 1]))
            for i in range(len(a) - 2)
            if a[i] in flags and a[i + 1] == a[i + 2]
        ]
        for job, a in args.items()
    }
    found: list[str] = []
    for job, other in zip(JOBS, reversed(JOBS), strict=True):
        theirs = mounts[other]
        effective = {
            p
            for i, (_, p) in enumerate(theirs)
            if not any(p != q and p.is_relative_to(q) for _, q in theirs[i + 1 :])
        }
        writes = [p for flag, p in theirs if flag in ("--bind", "--bind-try")]
        for _, s in mounts[job]:
            for w in writes:
                if s == w or not s.is_relative_to(w):
                    continue
                parts = s.relative_to(w).parts
                found += [
                    f"{other} {p} (for {job}'s {s})"
                    for i in range(1, len(parts) + 1)
                    if (p := w.joinpath(*parts[:i])) not in effective
                ]
    return found


def bwrap_cases(case: Case, policy: DaemonPolicy) -> None:
    """The arguments of kaimon: their order, and what is left out."""
    a = bwrap_args(policy, "kaimon", HOME, ROOT)
    case(
        f"kaimon's arguments start with the namespaces and the system mounts: {a[:HEAD]}",
        ok=" ".join(a[:HEAD]) == BWRAP_HEAD,
    )
    home = next((i for i in range(HEAD, len(a) - 1) if a[i : i + 2] == ("--tmpfs", "/h/a.b")), -1)
    system = [
        triple(a, "--ro-bind-try", "/usr"),
        triple(a, "--ro-bind-try", "/etc"),
        triple(a, "--ro-bind-try", "/opt"),
        triple(a, "--ro-bind-try", "/run/systemd/resolve"),
        triple(a, "--symlink", "/bin", "usr/bin"),
        triple(a, "--symlink", "/lib", "usr/lib"),
        triple(a, "--ro-bind", "/lib64"),
        home,
    ]
    case(
        f"the linux_read binds, the links, the root directories, then the home tmpfs, in order: {system}",
        ok=-1 not in system and system == sorted(system) and system[0] == HEAD,
    )
    reads = [triple(a, "--ro-bind-try", f"/h/a.b/{p}") for p in ("Research", ".julia", ".gitconfig")]
    writes = [triple(a, "--bind-try", f"/h/a.b/{p}") for p in ("Research", ".julia", ".config/kaimon")]
    denies = [
        triple(a, "--ro-bind", f"/h/a.b/{p}")
        for p in (".julia/bin", ".julia/config", ".julia/juliaup", "Research/Harness/githooks")
    ]
    lock = triple(a, "--bind-try", "/h/a.b/.julia/juliaup/.juliaup-lock")
    case(
        f"after the home: the read binds, the write binds, the write denies, the file written back: "
        f"{reads} {writes} {denies} {lock}",
        ok=-1 not in (*reads, *writes, *denies, lock)
        and home < min(reads)
        and max(reads) < min(writes)
        and max(writes) < min(denies)
        and max(denies) < lock,
    )
    after = a[min(denies) :]
    case(
        f"no write bind follows the first write deny but the file written back: {binds(after, '--bind-try')}",
        ok=binds(after, "--bind-try") == ["/h/a.b/.julia/juliaup/.juliaup-lock"],
    )
    text = "\n".join(a)
    for word in ("/System", "/Library", "/private", "/opt/homebrew", "$DARWIN", "~", "$HARNESS", "/run/user"):
        case(f"no argument of kaimon names {word}", ok=word not in text)
    case(
        "kaimon's arguments hold no --unshare-net, no --dev /dev and no ~/.cache/julia-update",
        ok="--unshare-net" not in a and triple(a, "--dev", "/dev") < 0 and ".cache/julia-update" not in text,
    )
    case(
        "every argument but the flags and the link targets is an absolute path",
        ok=all(x.startswith("/") for x in a if not x.startswith("--") and x not in ("usr/bin", "usr/lib")),
    )
    case("two calls give the same arguments", ok=a == bwrap_args(load(POLICY), "kaimon", HOME, ROOT))


def bwrap_update_cases(case: Case, policy: DaemonPolicy) -> None:
    """The arguments of julia-update, and of a harness outside ~/Research."""
    a = bwrap_args(policy, "kaimon", HOME, ROOT)
    u = bwrap_args(policy, "julia-update", HOME, ROOT)
    u_text = "\n".join(u)
    case(
        "julia-update binds ~/.juliaup, ~/.julia/juliaup and ~/.cache/julia-update for writing",
        ok=all(
            triple(u, "--bind-try", f"/h/a.b/{p}") > 0
            for p in (".juliaup", ".julia/juliaup", ".cache/julia-update")
        ),
    )
    cache = triple(u, "--bind-try", "/h/a.b/.cache/julia-update")
    u_writes = [triple(u, "--bind-try", f"/h/a.b/{p}") for p in (".julia", ".juliaup", ".julia/bin")]
    u_denies = [triple(u, "--ro-bind", f"/h/a.b/{p}") for p in (".julia/config",)]
    case(
        f"julia-update's linux_write bind follows its write binds and precedes its write denies: "
        f"{u_writes} {cache} {u_denies}",
        ok=-1 not in (*u_writes, cache, *u_denies) and max(u_writes) < cache < min(u_denies),
    )
    case(
        "julia-update reads its installed script and the profile",
        ok=triple(u, "--ro-bind-try", "/h/a.b/.local/bin/julia-update.jl") > 0
        and triple(u, "--ro-bind-try", "/h/a.b/.config/research-harness/profile.toml") > 0,
    )
    case(
        "julia-update denies no write of ~/.julia/juliaup and binds nothing of ~/Research",
        ok=triple(u, "--ro-bind", "/h/a.b/.julia/juliaup") < 0 and "/h/a.b/Research" not in u_text,
    )
    case(
        "julia-update's arguments are not kaimon's",
        ok=u != a and "/h/a.b/.config/kaimon" not in u_text,
    )

    other = bwrap_args(policy, "kaimon", HOME, ROOT, pathlib.Path("/opt/harness"))
    case(
        "a harness outside ~/Research is in no argument: its write deny is invisible to the job",
        ok=not any("/opt/harness" in x for x in other),
    )
    case(
        "the default harness is ~/Research/Harness, whose githooks is a write deny",
        ok=triple(a, "--ro-bind", "/h/a.b/Research/Harness/githooks") > 0,
    )


def bwrap_pin_cases(case: Case, policy: DaemonPolicy) -> None:
    """The pins: each path from a write path of one job down to a bind source of the other, its
    pins included, bound with `--bind` in the writer's arguments after its write bind at or above
    the pin, before its write binds below the pin and before its write denies; the closure of the
    pins on the shipped list and on lists with nested write paths; the directories and files that
    setup makes for them; and a pin below the writer's own write deny, which raises
    HarnessError."""
    a = bwrap_args(policy, "kaimon", HOME, ROOT)
    u = bwrap_args(policy, "julia-update", HOME, ROOT)
    environments, apps = "/h/a.b/.julia/environments", "/h/a.b/.julia/environments/apps"
    lock = "/h/a.b/.julia/juliaup/.juliaup-lock"
    case(
        f"kaimon pins ~/.julia/environments and ~/.julia/environments/apps, julia-update's write bind "
        f"below kaimon's ~/.julia, and nothing else: {binds(a, '--bind')}",
        ok=binds(a, "--bind") == [environments, apps],
    )
    at = [
        triple(a, "--bind-try", "/h/a.b/.julia"),
        triple(a, "--bind", environments),
        triple(a, "--bind", apps),
        triple(a, "--ro-bind", "/h/a.b/.julia/bin"),
    ]
    case(
        f"kaimon's pins follow its write binds and precede its write denies, the parent first: {at}",
        ok=-1 not in at
        and at == sorted(at)
        and max(triple(a, "--bind-try", f"/h/a.b/{p}") for p in ("Research", ".config/kaimon")) < at[1],
    )
    case(
        f"julia-update pins kaimon's pin ~/.julia/environments, below its ~/.julia, and juliaup's lock "
        f"file, kaimon's file written back below its ~/.julia/juliaup, and nothing else: "
        f"{binds(u, '--bind')}",
        ok=binds(u, "--bind") == [environments, lock],
    )
    at = [
        triple(u, "--bind-try", "/h/a.b/.julia"),
        triple(u, "--bind", environments),
        triple(u, "--bind-try", apps),
    ]
    case(
        f"julia-update's pin ~/.julia/environments follows its write bind ~/.julia and precedes its "
        f"write bind below it, ~/.julia/environments/apps: {at}",
        ok=-1 not in at and at == sorted(at),
    )
    at = [
        triple(u, "--bind-try", "/h/a.b/.cache/julia-update"),
        triple(u, "--bind", lock),
        triple(u, "--ro-bind", "/h/a.b/.julia/config"),
    ]
    case(
        f"julia-update's pin of the lock file follows its write binds and precedes its write deny: {at}",
        ok=-1 not in at and at == sorted(at),
    )
    harness = HOME / "Research" / "Harness"
    case(
        "setup makes kaimon's two pins and julia-update's ~/.julia/environments as directories and "
        "julia-update's lock file pin as a file",
        ok=[str(p) for p in linux_dirs(policy, "kaimon", HOME, harness)][-2:] == [environments, apps]
        and [str(p) for p in linux_files(policy, "kaimon", HOME, harness)] == []
        and [str(p) for p in linux_dirs(policy, "julia-update", HOME, harness)][-1:] == [environments]
        and [str(p) for p in linux_files(policy, "julia-update", HOME, harness)] == [lock]
        and lock not in [str(p) for p in linux_dirs(policy, "julia-update", HOME, harness)],
    )
    case(
        f"the shipped list leaves no path of the pins' closure open: {unpinned(policy)}",
        ok=not unpinned(policy),
    )
    empty: dict[str, tuple[str, ...]] = dict.fromkeys(JOB_KEYS, ())
    # Nested write paths in both jobs: kaimon writes ~/a and ~/a/b/c and reads ~/r/x below its later
    # write ~/r; julia-update writes ~/r and ~/a/b/c/d and reads ~/a/q/z. Kaimon's ~/r/x needs a pin in
    # julia-update, and that pin one in kaimon, whose read ~/r/x its write ~/r covers.
    nested = dataclasses.replace(
        policy,
        kaimon=JobRules(
            **(empty | {"read": ("~/r/x",), "write": ("~/a", "~/a/b/c", "~/r")}), pty=False, network="open"
        ),
        julia_update=JobRules(
            **(empty | {"read": ("~/a/q/z",), "write": ("~/r", "~/a/b/c/d")}), pty=False, network="open"
        ),
    )
    case(
        f"a list with nested write paths in both jobs leaves no path of the pins' closure open: "
        f"{unpinned(nested)}",
        ok=not unpinned(nested),
    )
    # Kaimon's write ~/a/b/c precedes its write ~/a, which covers it: each pin follows ~/a.
    late = dataclasses.replace(
        policy,
        kaimon=JobRules(**(empty | {"write": ("~/a/b/c", "~/a")}), pty=False, network="open"),
        julia_update=JobRules(**(empty | {"read": ("~/a/b/c/d",)}), pty=False, network="open"),
    )
    case(
        f"a write path that precedes a write path above it leaves no path of the pins' closure open: "
        f"{unpinned(late)}",
        ok=not unpinned(late),
    )
    # Kaimon reads the file ~/t/f, which its write ~/t covers, and julia-update writes ~/t: each job
    # pins the file, kaimon because julia-update's pin is a bind source of its own.
    filed = dataclasses.replace(
        policy,
        kaimon=JobRules(**(empty | {"read_files": ("~/t/f",), "write": ("~/t",)}), pty=False, network="open"),
        julia_update=JobRules(**(empty | {"write": ("~/t",)}), pty=False, network="open"),
    )
    made = {
        job: (linux_dirs(filed, job, HOME, harness), linux_files(filed, job, HOME, harness)) for job in JOBS
    }
    case(
        f"a pin of the other job's pin that is a file is a file: {made}",
        ok=all(made[job] == ([], [HOME / "t" / "f"]) for job in JOBS),
    )
    covered = dataclasses.replace(
        policy,
        kaimon=JobRules(**(empty | {"read": ("~/t/x",), "write": ("~/t",)}), pty=False, network="open"),
        julia_update=JobRules(**(empty | {"read": ("~/t/x/s",)}), pty=False, network="open"),
    )
    got = binds(bwrap_args(covered, "kaimon", HOME, ROOT), "--bind")
    case(
        f"a read destination that a later write bind covers counts as no mount point: kaimon reads ~/t/x "
        f"and writes ~/t, julia-update reads ~/t/x/s, and kaimon pins both: {got}",
        ok=got == ["/h/a.b/t/x", "/h/a.b/t/x/s"],
    )
    below = dataclasses.replace(
        policy,
        kaimon=JobRules(**(empty | {"write": ("~/x",), "deny_write": ("~/x/d",)}), pty=False, network="open"),
        # julia-update also writes ~/x/d: the pin that kaimon cannot make gives julia-update no pin.
        julia_update=JobRules(
            **(empty | {"read": ("~/x/d/s",), "write": ("~/x/d",)}), pty=False, network="open"
        ),
    )
    case(
        "a pin below the pinning job's own write deny raises HarnessError that names it",
        ok=raises(lambda: bwrap_args(below, "kaimon", HOME, ROOT))
        and "/h/a.b/x/d/s" in message(lambda: bwrap_args(below, "kaimon", HOME, ROOT)),
    )
    case(
        "the job whose bind source lies below the other's write deny needs no pin and raises nothing",
        ok=binds(bwrap_args(below, "julia-update", HOME, ROOT), "--bind") == [],
    )
    deep = dataclasses.replace(
        policy,
        kaimon=JobRules(**(empty | {"write": ("~/x",)}), pty=False, network="open"),
        julia_update=JobRules(**(empty | {"read_files": ("~/x/y/f",)}), pty=False, network="open"),
    )
    made = (linux_dirs(deep, "kaimon", HOME, harness), linux_files(deep, "kaimon", HOME, harness))
    case(
        f"a pin above a file source is a directory, and the file source a file: {made}",
        ok=made == ([HOME / "x" / "y"], [HOME / "x" / "y" / "f"]),
    )


def bwrap_edge_cases(case: Case, policy: DaemonPolicy) -> None:
    """The edges of the input of `bwrap_args`: which write deny stays, which path is macOS's, `pty`,
    an empty root and an argument with a newline."""
    a = bwrap_args(policy, "kaimon", HOME, ROOT)

    def rules(**given: tuple[str, ...]) -> DaemonPolicy:
        empty: dict[str, tuple[str, ...]] = dict.fromkeys(JOB_KEYS, ())
        return dataclasses.replace(policy, kaimon=JobRules(**(empty | given), pty=True, network="open"))

    for label, given, deny, kept in (
        ("below a write path", {"write": ("~/x",), "deny_write": ("~/x/y",)}, "/h/a.b/x/y", True),
        ("at a read path", {"read": ("~/x",), "deny_write": ("~/x",)}, "/h/a.b/x", True),
        ("below a read file", {"read_files": ("~/x",), "deny_write": ("~/x/y",)}, "/h/a.b/x/y", False),
        ("beside a read path", {"read": ("~/x",), "deny_write": ("~/xy",)}, "/h/a.b/xy", False),
        ("above a write path", {"write": ("~/x/y",), "deny_write": ("~/x",)}, "/h/a.b/x", False),
        ("below a linux_write path", {"linux_write": ("~/x",), "deny_write": ("~/x/y",)}, "/h/a.b/x/y", True),
        ("below a macOS path", {"read": ("/usr",), "deny_write": ("~/usr/x",)}, "/h/a.b/usr/x", False),
        (
            "below $HARNESS",
            {"read": ("$HARNESS",), "deny_write": ("$HARNESS/g",)},
            "/h/a.b/Research/Harness/g",
            True,
        ),
    ):
        got = bwrap_args(rules(**given), "kaimon", HOME, ROOT)
        case(
            f"a write deny {label} is {'kept' if kept else 'left out'}: {got[HEAD:]}",
            ok=(triple(got, "--ro-bind", deny) > 0) == kept,
        )
    plain = rules(read=("$HARNESS", "/usr", "$DARWIN_USER_TEMP_DIR"), write=("$DARWIN_USER_CACHE_DIR",))
    got = bwrap_args(plain, "kaimon", HOME, ROOT)
    case(
        f"$HARNESS alone is the harness path, and the absolute paths and the tokens are left out: "
        f"{got[HEAD:]}",
        ok=triple(got, "--ro-bind-try", "/h/a.b/Research/Harness") > 0
        and triple(got, "--ro-bind-try", "/usr") == HEAD
        and binds(got, "--ro-bind-try").count("/usr") == 1
        and "$DARWIN" not in "\n".join(got),
    )
    lib = bwrap_args(rules(read=("~/Library", "~/Library/Logs/x", "~/Libraryx")), "kaimon", HOME, ROOT)
    case(
        f"~/Library and every path below it are macOS's and left out, a sibling is kept: {lib[HEAD:]}",
        ok=binds(lib, "--ro-bind-try")[-1:] == ["/h/a.b/Libraryx"]
        and not any(x.startswith("/h/a.b/Library/") or x == "/h/a.b/Library" for x in lib),
    )
    no_pty = dataclasses.replace(policy, kaimon=dataclasses.replace(policy.kaimon, pty=False))
    case("pty gives no argument", ok=bwrap_args(no_pty, "kaimon", HOME, ROOT) == a)
    case(
        "an empty LinuxRoot gives no link and no root bind, and the home tmpfs follows linux_read",
        ok=bwrap_args(policy, "kaimon", HOME, LinuxRoot((), ()))[HEAD + 3 * len(policy.linux_read) :][:2]
        == ("--tmpfs", "/h/a.b"),
    )
    for label, f in (
        ("a home with a newline", lambda: bwrap_args(policy, "kaimon", pathlib.Path("/h/a\nb"), ROOT)),
        (
            "a harness with a newline",
            lambda: bwrap_args(policy, "kaimon", HOME, ROOT, pathlib.Path("/h/a.b/Research/H\nx")),
        ),
        ("a rule path with a newline", lambda: bwrap_args(rules(read=("~/a\nb",)), "kaimon", HOME, ROOT)),
        (
            "a link target with a newline",
            lambda: bwrap_args(policy, "kaimon", HOME, LinuxRoot((("/bin", "a\nb"),), ())),
        ),
        ("a job that is not one of JOBS", lambda: bwrap_args(policy, "claude-autocommit", HOME, ROOT)),
    ):
        case(f"{label} raises HarnessError", ok=raises(f))


def linux_root_cases(case: Case, root: pathlib.Path, policy: DaemonPolicy) -> None:
    """`linux_root` reads each entry of `linux_links` below a root: a link gives its target, a
    directory its path, and anything else, a missing entry or a file, nothing."""
    base = root / "host"
    (base / "usr" / "bin").mkdir(parents=True)
    (base / "lib64").mkdir()
    (base / "bin").symlink_to("usr/bin")
    (base / "lib").symlink_to("/usr/lib")
    (base / "lib32").write_text("", encoding="utf-8")
    got = linux_root(policy, base)
    case(
        f"a link gives its target, a directory its path, a missing entry and a file nothing: {got}",
        ok=got == LinuxRoot((("/bin", "usr/bin"), ("/lib", "/usr/lib")), ("/lib64",)),
    )
    host = linux_root(policy)
    case(
        f"this host's root gives only entries of linux_links: {host}",
        ok={p for p, _ in host.links} | set(host.dirs) <= set(policy.linux_links),
    )


def jobbox_cases(case: Case, root: pathlib.Path) -> None:
    """`sandbox/jobbox` with a stub `bwrap` on the PATH that writes its arguments, one per line,
    into a file: the arguments of the job's file, `--chdir` and the working directory, the three
    binds of each repository at most four levels below ~/Research, `--`, then the program and its
    arguments; and each refusal exits 2 with one line on stderr and never starts the stub."""
    home = root / "home"
    research = home / "Research"
    for d in ("A/.git/hooks", "B/C/.git", "D/E/F/G/.git/hooks", "H/I/J/K/L/.git/hooks", "M/.git/x/.git"):
        (research / d).mkdir(parents=True)
    (research / "B" / "C" / ".git" / "config").write_text("", encoding="utf-8")
    # A worktree's .git is a file, which the search does not take.
    (research / "N").mkdir()
    (research / "N" / ".git").write_text("gitdir: /x\n", encoding="utf-8")
    sandbox = home / ".config" / "research-harness" / "sandbox"
    sandbox.mkdir(parents=True)
    lines = [
        "--unshare-all",
        "--tmpfs",
        str(home),
        "--ro-bind-try",
        "/a b",
        "/a b",
        "--bind-try",
        str(research),
        str(research),
    ]
    (sandbox / "kaimon.bwrap").write_text("".join(x + "\n" for x in lines), encoding="utf-8")
    # A file for a job that is not one of JOBS, so that the job's name alone refuses it.
    (sandbox / "claude-autocommit.bwrap").write_text("--unshare-all\n", encoding="utf-8")
    stubs = root / "stubs"
    stubs.mkdir()
    out = root / "bwrap.out"
    (stubs / "bwrap").write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{out}'\n", encoding="utf-8")
    (stubs / "bwrap").chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{stubs}{os.pathsep}/usr/bin{os.pathsep}/bin"}

    def jobbox(*args: str, cwd: pathlib.Path = research) -> subprocess.CompletedProcess[str]:
        out.unlink(missing_ok=True)
        return subprocess.run(
            ["/bin/sh", str(JOBBOX), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=TIMEOUT,
            check=False,
        )

    p = jobbox("kaimon", "/bin/true", "x")
    got = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
    repos = [research / r for r in ("A", "B/C", "D/E/F/G", "M")]
    want_binds = {
        (flag, f"{r}/{part}", f"{r}/{part}")
        for r in repos
        for part in REPOSITORY_PARTS
        for flag in ("--ro-bind-try",)
    }
    n = len(lines)
    middle = got[n + 2 : -3] if len(got) >= n + 5 else []
    found = {tuple(middle[i : i + 3]) for i in range(0, len(middle), 3)}
    case(
        f"jobbox runs bwrap with the file's lines, --chdir {research}, the binds, -- and the program: "
        f"exit {p.returncode} {p.stderr.strip()!r} {got}",
        ok=p.returncode == 0
        and got[:n] == lines
        and got[n : n + 2] == ["--chdir", str(research)]
        and got[-3:] == ["--", "/bin/true", "x"]
        and len(middle) == 3 * len(found),
    )
    case(
        f"the binds are the three repository parts of A, B/C, D/E/F/G and M, each once: {sorted(found)}",
        ok=found == want_binds,
    )
    case(
        "no bind of H/I/J/K/L, five levels below ~/Research, of M's nested .git, or of N's .git file",
        ok=not any("/H/" in x or "/x/.git" in x or "/N/" in x for x in got),
    )
    p = jobbox("kaimon", "/bin/true", cwd=home)
    got = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
    case(
        f"--chdir names the working directory of the start: {got[n : n + 2]}",
        ok=p.returncode == 0 and got[n : n + 2] == ["--chdir", str(home)] and got[-2:] == ["--", "/bin/true"],
    )
    for label, args in (
        ("another job", ("claude-autocommit", "/bin/true")),
        ("a job and no program", ("kaimon",)),
        ("no argument", ()),
        ("a job whose file is missing", ("julia-update", "/bin/true")),
    ):
        p = jobbox(*args)
        case(
            f"{label} exits 2 with one line on stderr and starts no bwrap: exit {p.returncode} {p.stderr!r}",
            ok=p.returncode == FAILED
            and p.stdout == ""
            and len(p.stderr.splitlines()) == 1
            and p.stderr.startswith("jobbox: ")
            and not out.exists(),
        )
    shutil.rmtree(research)
    research.mkdir()
    p = jobbox("kaimon", "/bin/true")
    got = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
    case(
        f"a ~/Research with no repository adds no bind: {got}",
        ok=p.returncode == 0 and got == [*lines, "--chdir", str(research), "--", "/bin/true"],
    )
    research.rmdir()
    p = jobbox("kaimon", "/bin/true", cwd=home)
    got = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
    case(
        f"a home without ~/Research adds no bind and prints nothing: {got} {p.stderr!r}",
        ok=p.returncode == 0 and p.stderr == "" and got == [*lines, "--chdir", str(home), "--", "/bin/true"],
    )


@dataclasses.dataclass(frozen=True, slots=True)
class JobboxRoot:
    """A scratch root for the link cases of JOBBOX: a stub `bwrap` in `stubs/` that writes its
    arguments into `bwrap.out`, a directory and a file in `outside/` for the links to name, and a
    scratch home per case."""

    case: Case
    root: pathlib.Path

    @property
    def out(self) -> pathlib.Path:
        return self.root / "bwrap.out"

    @property
    def outside(self) -> pathlib.Path:
        return self.root / "outside"

    def make(self) -> None:
        """The stub `bwrap` and the targets outside every home."""
        stubs = self.root / "stubs"
        stubs.mkdir()
        (stubs / "bwrap").write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{self.out}'\n", encoding="utf-8")
        (stubs / "bwrap").chmod(0o755)
        (self.outside / "hooks").mkdir(parents=True)
        (self.outside / "netrc").write_text("", encoding="utf-8")

    def home_of(self, name: str, lines: Sequence[str] = (), job: str = "kaimon") -> pathlib.Path:
        """A scratch home whose arguments file of `job` holds `lines`; without them, a bind of
        ~/Research."""
        home = self.root / name
        sandbox = home / ".config" / "research-harness" / "sandbox"
        sandbox.mkdir(parents=True)
        research = str(home / "Research")
        given = [*lines] or ["--unshare-all", "--bind-try", research, research]
        (sandbox / f"{job}.bwrap").write_text("".join(x + "\n" for x in given), encoding="utf-8")
        return home

    def rendered(self, name: str, job: str) -> pathlib.Path:
        """A scratch home whose arguments file of `job` is `bwrap_args` of the shipped list."""
        home = self.root / name
        return self.home_of(name, bwrap_args(load(POLICY), job, home, LinuxRoot((), ())), job)

    def run(
        self, home: pathlib.Path, given: str = "", job: str = "kaimon"
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        """`jobbox <job> /bin/true` with HOME `given`, else `home`: the process and the stub's
        arguments."""
        self.out.unlink(missing_ok=True)
        stubs = self.root / "stubs"
        p = subprocess.run(
            ["/bin/sh", str(JOBBOX), job, "/bin/true"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env={"HOME": given or str(home), "PATH": f"{stubs}{os.pathsep}/usr/bin{os.pathsep}/bin"},
            cwd=home,
            timeout=TIMEOUT,
            check=False,
        )
        return p, self.out.read_text(encoding="utf-8").splitlines() if self.out.exists() else []

    def refused(
        self, label: str, home: pathlib.Path, path: pathlib.Path, given: str = "", job: str = "kaimon"
    ) -> None:
        """The case that the run exits 2 with one line that names `path` and starts no stub."""
        p, got = self.run(home, given, job)
        self.case(
            f"{label} exits 2 with one line that names it and starts no bwrap: "
            f"exit {p.returncode} {p.stderr!r} {got}",
            ok=p.returncode == FAILED
            and len(p.stderr.splitlines()) == 1
            and p.stderr.startswith("jobbox: ")
            and str(path) in p.stderr
            and not self.out.exists(),
        )


def jobbox_link_cases(case: Case, box: JobboxRoot) -> None:
    """`sandbox/jobbox` against a stub `bwrap`, with symbolic links among the sources of its
    read-only binds below ~/Research: a repository part that is a link, a dangling one too, and a
    static source below a linked directory each exit 2 with one line on stderr that names the
    path, and never start the stub; a ~/Research that is itself a link keeps its binds on the
    logical paths."""
    root, outside = box.root, box.outside
    home_of, jobbox, refused = box.home_of, box.run, box.refused

    # A repository R and one of its parts, a link to `target`.
    for label, repository, part, target in (
        (
            "a .git/hooks that is a link to a directory outside ~/Research",
            "A",
            ".git/hooks",
            outside / "hooks",
        ),
        ("a .git/config that is a link to a file", "B", ".git/config", outside / "netrc"),
        ("a .githooks that is a dangling link", "C", ".githooks", outside / "none"),
    ):
        home = home_of(f"linked-{repository}")
        (home / "Research" / repository / ".git").mkdir(parents=True)
        (home / "Research" / repository / part).symlink_to(target)
        refused(label, home, home / "Research" / repository / part)
    home = root / "linked-harness"
    githooks = home / "Research" / "Harness" / "githooks"
    home = home_of("linked-harness", ["--ro-bind", str(githooks), str(githooks)])
    (home / "Research" / "X" / "githooks").mkdir(parents=True)
    (home / "Research" / "Harness").symlink_to(home / "Research" / "X")
    # The home as HOME names it, and with a trailing / or a . segment, as the arguments file never
    # spells it.
    for given in (str(home), f"{home}/", f"{home}/."):
        refused(
            f"with HOME {given!r}, a static --ro-bind source below a ~/Research/Harness that is a link",
            home,
            githooks,
            given,
        )
    home = root / "linked-try"
    linked = home / "Research" / "Y"
    home = home_of("linked-try", ["--ro-bind-try", str(linked), str(linked)])
    (home / "Research").mkdir()
    linked.symlink_to(outside / "hooks")
    refused("a static --ro-bind-try source that is a link", home, linked)
    home = root / "linked-research"
    githooks = home / "Research" / "Harness" / "githooks"
    research = str(home / "Research")
    home = home_of(
        "linked-research", ["--ro-bind", str(githooks), str(githooks), "--bind-try", research, research]
    )
    real = root / "real-research"
    (real / "A" / ".git" / "hooks").mkdir(parents=True)
    (real / "Harness" / "githooks").mkdir(parents=True)
    (home / "Research").symlink_to(real)
    p, got = jobbox(home)
    hooks = str(home / "Research" / "A" / ".git" / "hooks")
    case(
        f"a ~/Research that is a link is searched, and its binds keep the logical paths: "
        f"exit {p.returncode} {p.stderr!r} {got}",
        ok=p.returncode == 0
        and triple(tuple(got), "--ro-bind-try", hooks) >= 0
        and triple(tuple(got), "--ro-bind", str(githooks)) == 0
        and not any(x.startswith(str(real)) for x in got),
    )


def jobbox_home_cases(case: Case, box: JobboxRoot) -> None:
    """`sandbox/jobbox` against a stub `bwrap`, with the shipped arguments of each job: a source
    of a writable bind or of a file below the home that is a link, or that lies below a link under
    its anchor, exits 2 with one line that names it; an anchor such as ~/.julia that is itself a
    link passes with the logical paths; and a job that binds no ~/Research gets no repository
    part."""
    root, outside = box.root, box.outside
    rendered, jobbox, refused = box.rendered, box.run, box.refused
    # The sources of the rendered arguments below the home, writable binds and files too: each
    # directory below the home that one job writes holds a source of the other's binds.
    home = rendered("linked-apps", "julia-update")
    (home / ".julia" / "environments").mkdir(parents=True)
    (home / ".julia" / "environments" / "apps").symlink_to(outside / "hooks")
    refused(
        "julia-update's --bind-try ~/.julia/environments/apps that is a link",
        home,
        home / ".julia" / "environments" / "apps",
        job="julia-update",
    )
    home = rendered("linked-lock", "kaimon")
    (home / ".julia" / "juliaup").mkdir(parents=True)
    (home / ".julia" / "juliaup" / ".juliaup-lock").symlink_to(outside / "netrc")
    refused(
        "kaimon's --bind-try ~/.julia/juliaup/.juliaup-lock that is a link to a file",
        home,
        home / ".julia" / "juliaup" / ".juliaup-lock",
    )
    home = rendered("linked-environments", "julia-update")
    (outside / "environments" / "apps").mkdir(parents=True)
    (home / ".julia").mkdir()
    (home / ".julia" / "environments").symlink_to(outside / "environments")
    refused(
        "julia-update's pin ~/.julia/environments that is a link, with a real directory apps below it",
        home,
        home / ".julia" / "environments",
        job="julia-update",
    )
    # A read file, not itself a link, below a linked directory of the home.
    home = root / "linked-config"
    real = root / "real-config"
    (real / "sandbox").mkdir(parents=True)
    (real / "profile.toml").write_text("", encoding="utf-8")
    (home / ".config").mkdir(parents=True)
    (home / ".config" / "research-harness").symlink_to(real)
    args = bwrap_args(load(POLICY), "julia-update", home, LinuxRoot((), ()))
    (real / "sandbox" / "julia-update.bwrap").write_text("".join(a + "\n" for a in args), encoding="utf-8")
    refused(
        "julia-update's read file ~/.config/research-harness/profile.toml below a linked directory",
        home,
        home / ".config" / "research-harness" / "profile.toml",
        job="julia-update",
    )
    home = rendered("linked-depot", "julia-update")
    depot = root / "real-depot"
    for d in ("environments/apps", "juliaup", "bin", "config"):
        (depot / d).mkdir(parents=True)
    (depot / "juliaup" / ".juliaup-lock").write_text("", encoding="utf-8")
    (home / ".julia").symlink_to(depot)
    p, got = jobbox(home, job="julia-update")
    case(
        f"a ~/.julia that is itself a link passes, and the binds keep the logical paths: "
        f"exit {p.returncode} {p.stderr!r} {got}",
        ok=p.returncode == 0
        and triple(tuple(got), "--bind-try", str(home / ".julia" / "environments" / "apps")) >= 0
        and triple(tuple(got), "--bind", str(home / ".julia" / "juliaup" / ".juliaup-lock")) >= 0
        and not any(x.startswith(str(depot)) for x in got),
    )
    # julia-update binds nothing of ~/Research, so jobbox adds no repository part to it: kaimon
    # writes ~/Research while julia-update starts, and could swap a part for a link after the
    # check.
    home = rendered("update-research", "julia-update")
    (home / "Research" / "A" / ".git" / "hooks").mkdir(parents=True)
    p, got = jobbox(home, job="julia-update")
    case(
        f"a job that binds no ~/Research gets no bind of a repository part: exit {p.returncode} {got}",
        ok=p.returncode == 0 and got != [] and not any("/Research" in x for x in got),
    )


def jobbox_text_cases(case: Case) -> None:
    """`sandbox/jobbox` is an executable POSIX `sh` script that names no /run/user and passes
    shellcheck; without shellcheck on the PATH, a skip line for that check."""
    text = JOBBOX.read_text(encoding="utf-8")
    case(
        "jobbox is a POSIX sh script that names no /run/user",
        ok=text.startswith("#!/bin/sh\n") and "/run/user" not in text,
    )
    case("jobbox is executable", ok=os.access(JOBBOX, os.X_OK))
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        print("skip  jobsandbox: no shellcheck on the PATH; sandbox/jobbox is not checked")
        return
    p = subprocess.run(
        [shellcheck, str(JOBBOX)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    case(f"shellcheck passes sandbox/jobbox: {p.stdout.strip()[-300:]!r}", ok=p.returncode == 0)


def profile_cases(case: Case, policy: DaemonPolicy) -> None:
    """The profiles of both jobs, the escapes, the tokens and an empty list."""
    text = profile(policy, "kaimon", HOME, DIRS)
    heads = [
        "(version 1)",
        "(allow default)",
        "(deny file-read* file-write*)",
        "(allow file-read-metadata)",
        "(allow file-read*\n",
        "(allow file-write*\n",
        PTY_ALLOW,
        "(deny file-write*\n",
        LOCK_ALLOW,
        "(deny lsopen)",
        "(deny appleevent-send)",
        "(deny file-mount)",
        "(deny file-unmount)",
        "(deny mach-lookup\n",
    ]
    at = [text.find(h) for h in heads]
    case(f"kaimon's profile holds the blocks in their order: {at}", ok=-1 not in at and at == sorted(at))
    reads, writes = rule_block(text, "(allow file-read*\n"), rule_block(text, "(allow file-write*\n")
    denies = rule_block(text, "(deny file-write*\n")
    case(
        "~/Research is in the read and the write block",
        ok='(subpath "/h/a.b/Research")' in reads and '(subpath "/h/a.b/Research")' in writes,
    )
    case(
        "both getconf tokens are in the read and the write block, in their real form",
        ok=all(f'(subpath "/private/var/folders/xy/{d}")' in b for d in ("T", "C") for b in (reads, writes)),
    )
    apart = dataclasses.replace(
        policy,
        kaimon=JobRules(
            ("$DARWIN_USER_CACHE_DIR",),
            (),
            ("$DARWIN_USER_TEMP_DIR",),
            (),
            (),
            (),
            (),
            (),
            pty=False,
            network="open",
        ),
    )
    split = profile(apart, "kaimon", HOME, DIRS)
    w, r = rule_block(split, "(allow file-write*\n"), rule_block(split, "(allow file-read*\n")
    case(
        "the temp token is the getconf temp value and the cache token the cache value",
        ok='(subpath "/private/var/folders/xy/T")' in w
        and "/private/var/folders/xy/C" not in w
        and '(subpath "/private/var/folders/xy/C")' in r
        and "/private/var/folders/xy/T" not in r,
    )
    case("~/.gitconfig is a literal of the read block", ok='(literal "/h/a.b/.gitconfig")' in reads)
    case(
        "the shim directory is a subpath of kaimon's read block and in no other rule of its profile",
        ok='(subpath "/h/a.b/.config/research-harness/sandbox/shims")' in reads
        and text.count("/h/a.b/.config/research-harness/") == 1,
    )
    case(
        "julia-update's profile does not name the shim directory",
        ok="sandbox/shims" not in profile(policy, "julia-update", HOME, DIRS),
    )
    for job in JOBS:
        block_text = rule_block(profile(policy, job, HOME, DIRS), "(allow file-read*\n")
        case(
            f"the root / is a literal of {job}'s read block, and no subpath",
            ok='(literal "/")' in block_text and '(subpath "/")' not in block_text,
        )
    case("/dev/null is a literal of the write block", ok='(literal "/dev/null")' in writes)
    filters = REGEX_FILTER.findall(denies)
    want = [rf"^/h/a\.b/Research/(.+/)?{p}(/|$)" for p in (r"\.git/hooks", r"\.git/config", r"\.githooks")]
    regexes = [SBPL_ESCAPE.sub(r"\1", f) for f in filters]
    case(
        f"the write denies hold one escaped regex per repository part, as an SBPL string: {filters}",
        ok=regexes == want and '#"' not in text,
    )
    for path, hit in (
        ("/h/a.b/Research/.git/hooks/pre-commit", True),
        ("/h/a.b/Research/Packages/X/.git/hooks", True),
        ("/h/a.b/Research/Packages/X/.git/config", True),
        ("/h/a.b/Research/Harness/.githooks/pre-push", True),
        ("/h/a.b/Research/Packages/X/.git/objects/ab", False),
        ("/h/a.b/Research/Packages/X/.githooks-notes", False),
        ("/h/aXb/Research/X/.git/hooks", False),
    ):
        case(
            f"the regexes {'match' if hit else 'do not match'} {path}",
            ok=any(re.search(r, path) for r in regexes) == hit,
        )
    case(
        "$HARNESS/githooks is a write deny below the default harness path",
        ok='(subpath "/h/a.b/Research/Harness/githooks")' in denies,
    )
    case("the depot's juliaup is a write deny of kaimon", ok='(subpath "/h/a.b/.julia/juliaup")' in denies)
    after = text[text.index("(deny file-write*\n") :]
    case(
        f"after kaimon's write denies, the one file allow is juliaup's lock file, so juliaup.json and "
        f"the installed Julia versions stay unwritable: {after.count('(allow file')} allow(s)",
        ok=after.count("(allow file") == 1
        and rule_block(after, "(allow file-write*\n") == LOCK_ALLOW
        and text.index(LOCK_ALLOW) > text.index("(deny file-write*\n"),
    )
    top = profile(policy, "kaimon", pathlib.Path("/"), DIRS)
    case(
        "the home / gives /Research, and no path with //",
        ok='(subpath "/Research")' in top and '(regex "^/Research/' in top and "//" not in top,
    )
    case(
        "the two Launch Services are denied",
        ok='(global-name "com.apple.coreservices.launchservicesd")' in text
        and '(global-name "com.apple.CoreServices.coreservicesd")' in text,
    )
    case("no ~, $DARWIN or $HARNESS remains", ok=not any(t in text for t in ("~", "$DARWIN", "$HARNESS")))

    other = profile(policy, "kaimon", HOME, DIRS, pathlib.Path("/opt/harness"))
    allows = rule_block(other, "(allow file-read*\n") + rule_block(other, "(allow file-write*\n")
    case(
        "a harness outside ~/Research is a write deny and in no allow block",
        ok='(subpath "/opt/harness/githooks")' in rule_block(other, "(deny file-write*\n")
        and "/opt/harness" not in allows,
    )
    plain = profile(policy, "kaimon", HOME, UserDirs("/private/var/folders/xy/T", "/h/a.b/Library/Caches/"))
    case(
        "a getconf value in its real form or not below /var/ stays, without its final /",
        ok='(subpath "/private/var/folders/xy/T")' in plain and '(subpath "/h/a.b/Library/Caches")' in plain,
    )

    update = profile(policy, "julia-update", HOME, DIRS)
    w, d = rule_block(update, "(allow file-write*\n"), rule_block(update, "(deny file-write*\n")
    case(
        "julia-update writes ~/.juliaup and ~/.julia/juliaup and denies neither",
        ok=all(
            f'(subpath "/h/a.b/{p}")' in w and f'"/h/a.b/{p}"' not in d
            for p in (".juliaup", ".julia/juliaup")
        ),
    )
    case(
        "julia-update denies the depot's startup code and the hooks' source",
        ok='(subpath "/h/a.b/.julia/config")' in d and '(subpath "/h/a.b/Research/Harness/githooks")' in d,
    )
    case(
        "julia-update allows nothing after its write denies",
        ok="(allow" not in update[update.index("(deny file-write*\n") :],
    )
    case(
        "julia-update reads and writes nothing of ~/Research",
        ok="/h/a.b/Research" not in rule_block(update, "(allow file-read*\n") + w,
    )

    quote = profile(policy, "kaimon", pathlib.Path('/h/q"x\\y'), DIRS)
    case(
        "a quote and a backslash of the home path are escaped in every string, the regex too",
        ok=r'(subpath "/h/q\"x\\y/Research")' in quote
        and r'(regex "^/h/q\"x\\\\y/Research/' in quote
        and re.search(r'[^\\]"x', quote) is None,
    )
    case(
        "a job that is not one of JOBS raises HarnessError",
        ok=raises(lambda: profile(policy, "claude-autocommit", HOME, DIRS)),
    )
    empty = dataclasses.replace(
        policy, kaimon=JobRules((), (), (), (), (), (), (), (), pty=False, network="open"), deny_services=()
    )
    bare = profile(empty, "kaimon", HOME, DIRS)
    case(
        "an empty list leaves its block out, never a block with no filter",
        ok="(allow file-read*" not in bare
        and "(allow file-write*" not in bare
        and "(deny mach-lookup" not in bare
        and "(deny file-write*\n" in bare,
    )
    case("two renders give the same bytes", ok=text == profile(load(POLICY), "kaimon", HOME, DIRS))


def network_profile_cases(case: Case, policy: DaemonPolicy) -> None:
    """The network rules: kaimon's profile ends with them, after the Mach-service deny;
    julia-update's names no network; an empty socket list leaves its block out; a socket path is
    written as the file rules write theirs; and the network keys give no `bwrap` argument."""
    text = profile(policy, "kaimon", HOME, DIRS)
    lines = text.rstrip("\n").split("\n")
    case(
        f"kaimon's profile ends with the deny of outbound traffic, the loopback allow and the socket "
        f"allow: {lines[-4:]}",
        ok=lines[-4:] == NETWORK_TAIL,
    )
    case(
        "kaimon's profile names the network in the three rules alone",
        ok=sum("network" in line for line in lines) == len(NETWORK_TAIL) - 1,
    )
    order = [text.find(h + "\n") for h in ("(deny mach-lookup", *NETWORK_TAIL)]
    case(
        f"the network rules follow the Mach-service deny, the deny before the allows: {order}",
        ok=-1 not in order and order == sorted(set(order)),
    )
    update = profile(policy, "julia-update", HOME, DIRS)
    case(
        "julia-update's profile names no network and no Unix socket",
        ok="network" not in update and "unix-socket" not in update,
    )
    k = policy.kaimon
    bare = profile(
        dataclasses.replace(policy, kaimon=dataclasses.replace(k, unix_sockets=())), "kaimon", HOME, DIRS
    )
    case(
        "a loopback job with no socket path gets the deny and the loopback allow, and no socket block",
        ok=bare.rstrip("\n").split("\n")[-2:] == NETWORK_TAIL[:2]
        and "unix-socket" not in bare
        and bare.count("(allow network-outbound") == 1,
    )
    token = dataclasses.replace(
        policy, kaimon=dataclasses.replace(k, unix_sockets=("$DARWIN_USER_TEMP_DIR/k", "/private/s"))
    )
    t = profile(token, "kaimon", HOME, DIRS)
    case(
        "a socket path is a subpath of the socket block, a token as its value, one filter per line",
        ok=t.endswith(
            '(allow network-outbound\n    (remote unix-socket (subpath "/private/var/folders/xy/T/k"))\n'
            '    (remote unix-socket (subpath "/private/s")))\n'
        ),
    )
    quote = profile(policy, "kaimon", pathlib.Path('/h/q"x\\y'), DIRS)
    case(
        "a quote and a backslash of the home path are escaped in the socket rule",
        ok=r'(remote unix-socket (subpath "/h/q\"x\\y/.cache/kaimon")))' in quote,
    )
    opened = dataclasses.replace(policy, kaimon=dataclasses.replace(k, network="open"))
    case(
        "the switch alone decides: kaimon with the network open gets no network rule",
        ok="network" not in profile(opened, "kaimon", HOME, DIRS),
    )
    closed = dataclasses.replace(
        policy, julia_update=dataclasses.replace(policy.julia_update, network="loopback")
    )
    case(
        "julia-update with loopback gets the deny and the loopback allow last",
        ok=profile(closed, "julia-update", HOME, DIRS).rstrip("\n").split("\n")[-2:] == NETWORK_TAIL[:2],
    )
    plain = dataclasses.replace(policy, kaimon=dataclasses.replace(k, network="open", unix_sockets=()))
    case(
        "kaimon's bwrap arguments are those of the same rules with the network open and no socket path",
        ok=all(
            bwrap_args(policy, "kaimon", HOME, r) == bwrap_args(plain, "kaimon", HOME, r)
            for r in (ROOT, LinuxRoot((), ()))
        ),
    )


def pty_profile_cases(case: Case, policy: DaemonPolicy) -> None:
    """The pty rules: in kaimon's profile once, between the deny of every file read and write and
    the write denies; in no profile of a job with `pty = false`; the same text for any home,
    harness, `getconf` value and file list."""
    text = profile(policy, "kaimon", HOME, DIRS)
    case(
        "kaimon's profile holds the pty rules once, after the deny of every file read and write and "
        "before the write denies",
        ok=text.count(PTY_ALLOW) == 1
        and text.count("pseudo-tty") == 1
        and text.index("(deny file-read* file-write*)")
        < text.index(PTY_ALLOW)
        < text.index("(deny file-write*\n"),
    )
    update = profile(policy, "julia-update", HOME, DIRS)
    case(
        "julia-update's profile holds no pty rule",
        ok=not any(t in update for t in ("pseudo-tty", "/dev/ptmx", "ttys", "file-ioctl")),
    )
    bare = dataclasses.replace(
        policy, kaimon=JobRules((), (), (), (), (), (), (), (), pty=True, network="open")
    )
    renders = [
        profile(policy, "kaimon", pathlib.Path('/h/q"x\\y'), DIRS),
        profile(
            policy, "kaimon", pathlib.Path("/dev/ttys"), UserDirs("/dev/x", "/dev/y"), pathlib.Path("/dev")
        ),
        profile(bare, "kaimon", HOME, DIRS),
    ]
    case(
        "the pty rules are the same text for any home, harness, getconf value and file list",
        ok=all(r.count(PTY_ALLOW) == 1 for r in renders),
    )
    on = dataclasses.replace(policy, julia_update=dataclasses.replace(policy.julia_update, pty=True))
    case(
        "the switch alone decides: julia-update with pty = true gets the pty rules",
        ok=profile(on, "julia-update", HOME, DIRS).count(PTY_ALLOW) == 1,
    )


def render_cases(case: Case, root: pathlib.Path, policy: DaemonPolicy) -> None:
    """`harness render sandbox/<job>.sb` through bin/harness, with a getconf stub on the PATH."""
    stubs = root / "bin"
    stubs.mkdir()
    getconf_stub = stubs / "getconf"
    prof = root / "profile.toml"
    example = (REPO / "examples" / "profile.toml").read_text(encoding="utf-8")
    prof.write_text(f'home = "{HOME}"\n' + example, encoding="utf-8")
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}"}

    def stub(body: str) -> None:
        getconf_stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        getconf_stub.chmod(0o755)

    outside = root / "outside.toml"
    outside.write_text(
        prof.read_text(encoding="utf-8").replace(
            'harness = "~/Research/Harness"', 'harness = "/opt/harness"', 1
        ),
        encoding="utf-8",
    )

    def harness(template: pathlib.Path, given: pathlib.Path = prof) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPO / "bin" / "harness"), "--profile", str(given), "render", str(template)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            timeout=TIMEOUT,
            check=False,
        )

    def one_line(p: subprocess.CompletedProcess[str]) -> bool:
        return p.returncode == FAILED and p.stdout == "" and len(p.stderr.strip().splitlines()) == 1

    stub(
        f'case "$1" in DARWIN_USER_TEMP_DIR) echo {TEMP};; '
        f"DARWIN_USER_CACHE_DIR) echo {CACHE};; *) exit 1;; esac"
    )
    for job in JOBS:
        first, second = harness(REPO / "sandbox" / f"{job}.sb"), harness(REPO / "sandbox" / f"{job}.sb")
        want = profile(policy, job, HOME, DIRS, HOME / "Research" / "Harness")
        case(
            f"harness render sandbox/{job}.sb prints its profile with the profile's home and "
            f"getconf's values: exit {first.returncode} {first.stderr.strip()}",
            ok=first.returncode == 0 and first.stdout == want,
        )
        case(f"two renders of sandbox/{job}.sb give the same bytes", ok=first.stdout == second.stdout)
    moved = harness(REPO / "sandbox" / "kaimon.sb", outside)
    allows = "".join(rule_block(moved.stdout, f"(allow {k}\n") for k in ("file-read*", "file-write*"))
    case(
        f"harness render takes the profile's harness /opt/harness: exit {moved.returncode} "
        f"{moved.stderr.strip()}",
        ok=moved.returncode == 0
        and moved.stdout == profile(policy, "kaimon", HOME, DIRS, pathlib.Path("/opt/harness"))
        and '(subpath "/opt/harness/githooks")' in rule_block(moved.stdout, "(deny file-write*\n")
        and "/opt/harness" not in allows,
    )
    latin = root / "latin" / "sandbox"
    latin.mkdir(parents=True)
    (latin / "daemon.toml").write_bytes(
        POLICY.read_text(encoding="utf-8").replace("~/Research", "~/R\xe9search", 1).encode("latin-1")
    )
    p = harness(latin / "kaimon.sb")
    case(
        f"a rule list that is not UTF-8 ends the render with exit 2 and one line: {p.stderr.strip()!r}",
        ok=one_line(p) and "daemon.toml" in p.stderr,
    )
    other = harness(REPO / "sandbox" / "claude-autocommit.sb")
    case(
        f"another job name ends the render with exit 2 and one line: {other.stderr.strip()!r}",
        ok=one_line(other),
    )
    for label, body in (
        ("fails", "exit 1"),
        ("fails after it prints a path", f"echo {TEMP}; exit 1"),
        ("prints nothing", "exit 0"),
        ("prints a relative path", "echo T"),
        ("prints two lines", f"echo {TEMP}; echo /x"),
        ("is not on the PATH", None),
    ):
        if body is None:
            getconf_stub.unlink()
            env["PATH"] = str(stubs)
        else:
            stub(body)
        p = harness(REPO / "sandbox" / "kaimon.sb")
        case(
            f"a getconf that {label} ends the render with exit 2 and one line: {p.stderr.strip()!r}",
            ok=one_line(p) and "getconf" in p.stderr,
        )
    case(
        "job_of reads sandbox/<job>.sb and sandbox/<job>.bwrap and nothing else",
        ok=job_of(pathlib.Path("x/sandbox/kaimon.sb")) == "kaimon"
        and job_of(pathlib.Path("x/sandbox/julia-update.bwrap")) == "julia-update"
        and job_of(pathlib.Path("x/launchagents/kaimon.plist")) is None
        and job_of(pathlib.Path("x/sandbox/daemon.toml")) is None
        and job_of(pathlib.Path("x/sandbox/kaimon.txt")) is None
        and job_of(pathlib.Path("x/other/kaimon.sb")) is None
        and job_of(pathlib.Path("x/other/kaimon.bwrap")) is None,
    )
    bwrap_render_cases(case, root, harness, one_line)


def bwrap_render_cases(
    case: Case,
    root: pathlib.Path,
    harness: Callable[[pathlib.Path, pathlib.Path], subprocess.CompletedProcess[str]],
    one_line: Callable[[subprocess.CompletedProcess[str]], bool],
) -> None:
    """`harness render sandbox/<job>.bwrap` through bin/harness, with no getconf on the PATH: the
    arguments of `bwrap_args` with the profile's home and harness and this host's root, one per
    line; the refusals with exit 2 and one line."""
    prof = root / "profile.toml"
    policy = load(POLICY)
    for job in JOBS:
        template = REPO / "sandbox" / f"{job}.bwrap"
        first, second = harness(template, prof), harness(template, prof)
        want = "".join(x + "\n" for x in bwrap_args(policy, job, HOME, linux_root(policy)))
        case(
            f"harness render sandbox/{job}.bwrap prints its arguments one per line, without getconf: "
            f"exit {first.returncode} {first.stderr.strip()}",
            ok=first.returncode == 0 and first.stdout == want and first.stderr == "",
        )
        case(f"two renders of sandbox/{job}.bwrap give the same bytes", ok=first.stdout == second.stdout)
    outside = root / "outside.toml"
    moved = harness(REPO / "sandbox" / "kaimon.bwrap", outside)
    case(
        f"harness render of kaimon.bwrap takes the profile's harness /opt/harness: exit {moved.returncode}",
        ok=moved.returncode == 0
        and moved.stdout
        == "".join(
            x + "\n"
            for x in bwrap_args(policy, "kaimon", HOME, linux_root(policy), pathlib.Path("/opt/harness"))
        ),
    )
    other = harness(REPO / "sandbox" / "claude-autocommit.bwrap", prof)
    case(
        f"another job name ends the .bwrap render with exit 2 and one line: {other.stderr.strip()!r}",
        ok=one_line(other),
    )
    latin = root / "latin" / "sandbox"
    p = harness(latin / "kaimon.bwrap", prof)
    case(
        f"a rule list that load refuses ends the .bwrap render with exit 2 and one line: "
        f"{p.stderr.strip()!r}",
        ok=one_line(p) and "daemon.toml" in p.stderr,
    )
    newline = root / "newline.toml"
    newline.write_text(
        prof.read_text(encoding="utf-8").replace(f'home = "{HOME}"', 'home = "/h/a\\nb"', 1), encoding="utf-8"
    )
    p = harness(REPO / "sandbox" / "kaimon.bwrap", newline)
    case(
        f"a home with a newline ends the .bwrap render with exit 2 and one line: {p.stderr.strip()!r}",
        ok=one_line(p),
    )


def start_cases(case: Case, root: pathlib.Path, policy: DaemonPolicy) -> None:
    """A process starts under the profile of each job, rendered with this user's home and `getconf`
    directories: `/bin/sh -c true` under `sandbox-exec -f` exits 0, and so do the pty runs of
    `pty_cases`, the shim runs of `shim_start_cases` and the juliaup launcher under kaimon's
    profile, the launcher in the environment of the launch agent; the connects of `connect_cases`
    run under the profiles of both jobs. Without `sandbox-exec`, without
    `getconf`, or where `sandbox-exec` cannot apply even the profile `(allow default)`, as inside
    another Seatbelt sandbox, they print a skip line; without the launcher, a skip line for its
    run."""
    if not SANDBOX_EXEC.is_file():
        print(f"skip  jobsandbox: no {SANDBOX_EXEC}; no process starts under the profiles")
        return
    trivial = root / "trivial.sb"
    trivial.write_text("(version 1)\n(allow default)\n", encoding="utf-8")
    probe = sandboxed(trivial)
    if probe.returncode != 0:
        print(
            f"skip  jobsandbox: sandbox-exec cannot apply the profile (allow default), exit "
            f"{probe.returncode} {probe.stderr.strip()!r}; no process starts under the profiles"
        )
        return
    try:
        dirs = UserDirs(getconf("DARWIN_USER_TEMP_DIR"), getconf("DARWIN_USER_CACHE_DIR"))
    except HarnessError as e:
        print(f"skip  jobsandbox: {e}; no process starts under the profiles")
        return
    home = pathlib.Path.home()
    for job in JOBS:
        sb = root / f"{job}.sb"
        sb.write_text(profile(policy, job, home, dirs), encoding="utf-8")
        p = sandboxed(sb)
        case(
            f"/bin/sh -c true starts and exits 0 under the profile of {job}: exit {p.returncode} "
            f"{p.stderr.strip()[-300:]!r}",
            ok=p.returncode == 0,
        )
    pty_cases(case, root / "kaimon.sb")
    shim_start_cases(case, root / "kaimon.sb", home, dirs)
    connect_cases(case, root, policy, home, dirs)
    launcher = home / ".juliaup" / "bin" / "julia"
    if not launcher.is_file():
        print(f"skip  jobsandbox: no juliaup launcher {launcher}; it does not start under kaimon's profile")
        return
    # The environment of the launch agent: launchd sets HOME and TMPDIR, the plist the PATH.
    env = {
        "HOME": str(home),
        "TMPDIR": dirs.temp,
        "PATH": os.pathsep.join(
            (str(launcher.parent), "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")
        ),
    }
    p = sandboxed(
        root / "kaimon.sb", [str(launcher), "--startup-file=no", "-e", "exit(0)"], env, JULIA_TIMEOUT
    )
    case(
        f"the juliaup launcher starts Julia and exits 0 under kaimon's profile: exit {p.returncode} "
        f"{p.stderr.strip()[-300:]!r}",
        ok=p.returncode == 0,
    )


def pty_cases(case: Case, sb: pathlib.Path) -> None:
    """Under kaimon's profile at `sb`, this Python, by its resolved path and isolated from its
    environment, opens a pseudo-terminal pair, and forks `/bin/sh -c true` on a pseudo-terminal, as
    Kaimon starts a session; each exits 0. Where that Python cannot start under the profile, as one
    below a path that the profile does not read, they print a skip line."""
    python = str(pathlib.Path(sys.executable).resolve())
    p = sandboxed(sb, [python, "-I", "-c", "pass"])
    if p.returncode != 0:
        print(
            f"skip  jobsandbox: {python} does not start under kaimon's profile, exit {p.returncode} "
            f"{p.stderr.strip()[-300:]!r}; the pty cases do not run"
        )
        return
    for label, script in (
        ("opens a pseudo-terminal pair", PTY_OPEN),
        ("forks /bin/sh -c true on a pseudo-terminal", PTY_FORK),
    ):
        p = sandboxed(sb, [python, "-I", "-c", script])
        case(
            f"Python {label} and exits 0 under kaimon's profile: exit {p.returncode} "
            f"{p.stderr.strip()[-300:]!r}",
            ok=p.returncode == 0,
        )


def connect_cases(
    case: Case, root: pathlib.Path, policy: DaemonPolicy, home: pathlib.Path, dirs: UserDirs
) -> None:
    """Under the profiles at `root/<job>.sb`, this Python, by its resolved path and isolated from
    its environment, runs CONNECT: under kaimon's, a connect to a TCP listener of this case on
    127.0.0.1 succeeds and one to UNREACHABLE fails with EPERM; under kaimon's rules with a scratch
    directory below $DARWIN_USER_TEMP_DIR as their one socket path, a connect to a Unix socket of
    this case in that directory succeeds and one to a socket in a sibling directory fails with
    EPERM; under julia-update's, the connect to UNREACHABLE fails with another error than EPERM, or
    times out. Where that Python cannot start under a profile, a skip line for its runs."""
    python = str(pathlib.Path(sys.executable).resolve())

    def connect(sb: pathlib.Path, *target: str) -> str:
        p = sandboxed(sb, [python, "-I", "-c", CONNECT, *target])
        return p.stdout.strip() if p.returncode == 0 else f"exit {p.returncode} {p.stderr.strip()[-300:]!r}"

    def starts(job: str, sb: pathlib.Path) -> bool:
        p = sandboxed(sb, [python, "-I", "-c", "pass"])
        if p.returncode != 0:
            print(
                f"skip  jobsandbox: {python} does not start under the profile of {job}, exit "
                f"{p.returncode} {p.stderr.strip()[-300:]!r}; its connect cases do not run"
            )
        return p.returncode == 0

    far = (UNREACHABLE[0], str(UNREACHABLE[1]))
    kaimon, update = root / "kaimon.sb", root / "julia-update.sb"
    if starts("kaimon", kaimon):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = str(listener.getsockname()[1])
            got = connect(kaimon, "tcp", "127.0.0.1", port)
        case(f"a connect to 127.0.0.1:{port} succeeds under kaimon's profile: {got}", ok=got == "connected")
        got = connect(kaimon, "tcp", *far)
        case(
            f"a connect to {':'.join(far)} fails with EPERM under kaimon's profile: {got}", ok=got == "EPERM"
        )
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="hj-", dir=dirs.temp))
        try:
            rule = "$DARWIN_USER_TEMP_DIR/" + (scratch / "in").relative_to(dirs.temp).as_posix()
            rules = dataclasses.replace(policy.kaimon, unix_sockets=(rule,))
            sb = root / "sockets.sb"
            sb.write_text(
                profile(dataclasses.replace(policy, kaimon=rules), "kaimon", home, dirs), encoding="utf-8"
            )
            for name, want in (("in", "connected"), ("out", "EPERM")):
                (scratch / name).mkdir()
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                    listener.bind(str(scratch / name / "s"))
                    listener.listen()
                    got = connect(sb, "unix", str(scratch / name / "s"))
                case(
                    f"a connect to a Unix socket {'below' if name == 'in' else 'beside'} the socket path "
                    f"{rule} gives {want} under kaimon's rules: {got}",
                    ok=got == want,
                )
        finally:
            shutil.rmtree(scratch)
    if starts("julia-update", update):
        got = connect(update, "tcp", *far)
        case(
            f"a connect to {':'.join(far)} under julia-update's profile is not refused by the profile: {got}",
            ok=got != "EPERM" and not got.startswith("exit "),
        )


# The address of `connect_cases` that no packet reaches: TEST-NET-1 of RFC 5737, port 9 (discard).
UNREACHABLE = ("192.0.2.1", 9)
# The connect of `connect_cases`, run under a profile with the arguments `tcp HOST PORT` or
# `unix PATH`: it prints `connected`, the errno name of the failure, or `timeout` after 5 s.
CONNECT = """
import errno, socket, sys
tcp = sys.argv[1] == "tcp"
with socket.socket(socket.AF_INET if tcp else socket.AF_UNIX, socket.SOCK_STREAM) as s:
    s.settimeout(5)
    try:
        s.connect((sys.argv[2], int(sys.argv[3])) if tcp else sys.argv[2])
    except TimeoutError:
        print("timeout")
    except OSError as e:
        print(errno.errorcode.get(e.errno or 0, f"errno {e.errno}"))
    else:
        print("connected")
"""


def plist_path(home: pathlib.Path) -> str:
    """The PATH of kaimon's plist, rendered with `home`."""
    text = (REPO / "launchagents" / "kaimon.plist").read_text(encoding="utf-8")
    found = re.search(r"<key>PATH</key>\s*<string>([^<]*)</string>", text)
    if found is None:
        raise HarnessError("launchagents/kaimon.plist sets no PATH")
    return found.group(1).replace("{home}", str(home))


def shim_start_cases(case: Case, sb: pathlib.Path, home: pathlib.Path, dirs: UserDirs) -> None:
    """Under kaimon's profile at `sb`, with the PATH of kaimon's plist, a shell runs
    `ps -o state= -p $$` as Kaimon's liveness check does, and gets `S` from the shim: once with the
    repository's shim first on the PATH, where the repository is below ~/Research, and once with the
    installed shim, where `harness setup` has installed it. Each that cannot run prints a skip
    line."""
    path = plist_path(home)
    shims = pathlib.Path(path.split(os.pathsep)[0])
    check = "ps -o state= -p $$"
    for label, first, present in (
        ("the repository's shim", PS_SHIM.parent, PS_SHIM.is_relative_to(home / "Research")),
        ("the installed shim", shims, (shims / "ps").is_file()),
    ):
        if not present:
            print(f"skip  jobsandbox: {label} is not at a path that kaimon's profile reads: {first}")
            continue
        env = {
            "HOME": str(home),
            "TMPDIR": dirs.temp,
            "PATH": os.pathsep.join((str(first), *path.split(os.pathsep)[1:])),
        }
        p = sandboxed(sb, ["/bin/sh", "-c", check], env)
        case(
            f"{check} prints S from {label} under kaimon's profile: exit {p.returncode} "
            f"{p.stdout!r} {p.stderr.strip()[-300:]!r}",
            ok=p.returncode == 0 and p.stdout == "S\n" and p.stderr == "",
        )


def shim_cases(case: Case) -> None:
    """The `ps` shim, run as a program: `-o state= -p N` prints `S` and exits 0 for a live process,
    and exits 1 silently for one that is gone; `-o rss=,%cpu= -p N` exits 1 silently; each other
    form of the arguments, and an N that is not digits, exits 2 with one line on stderr."""

    def shim(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PS_SHIM), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )

    runnable = PS_SHIM.is_file() and os.access(PS_SHIM, os.X_OK)
    case(f"the shim {PS_SHIM.relative_to(REPO)} is an executable file", ok=runnable)
    if not runnable:
        return
    me = str(os.getpid())
    # A process that has exited and been reaped when `run` returns.
    gone = subprocess.run(
        ["/bin/sh", "-c", "echo $$"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    ).stdout.strip()
    for args in (("-o", "state=", "-p", me), ("-p", me, "-o", "state=")):
        p = shim(*args)
        case(
            f"ps {' '.join(args)} for this process prints S and exits 0: exit {p.returncode} "
            f"{p.stdout!r} {p.stderr!r}",
            ok=p.returncode == 0 and p.stdout == "S\n" and p.stderr == "",
        )
    for args in (
        ("-o", "state=", "-p", gone),
        ("-p", gone, "-o", "state="),
        ("-o", "rss=,%cpu=", "-p", me),
        ("-o", "rss=,%cpu=", "-p", gone),
        ("-p", me, "-o", "rss=,%cpu="),
    ):
        p = shim(*args)
        case(
            f"ps {' '.join(args)} exits 1 with no output: exit {p.returncode} {p.stdout!r} {p.stderr!r}",
            ok=p.returncode == 1 and p.stdout == "" and p.stderr == "",
        )
    for args in (
        (),
        ("-o", "state="),
        ("-o", "state=", "-p"),
        ("-o", "state=", "-p", me, "-x"),
        ("-o", "pid=", "-p", me),
        ("-o", "state", "-p", me),
        ("-o", "state=", "-q", me),
        ("-x", "state=", "-p", me),
        ("-o", "state=", "-o", "state="),
        ("-p", me, "-p", me),
        ("-ax", "-o", "state=", me),
        ("-o", "state=", "-p", ""),
        ("-o", "state=", "-p", "12a"),
        ("-o", "state=", "-p", "-1"),
        ("-o", "state=", "-p", "+5"),
        ("-o", "state=", "-p", " 5"),
        ("-o", "state=", "-p", "1 2"),
        ("-o", "state=", "-p", "1,2"),
        ("-o", "rss=,%cpu=", "-p", "x"),
    ):
        p = shim(*args)
        case(
            f"ps {args!r} exits 2 with one line on stderr: exit {p.returncode} {p.stdout!r} {p.stderr!r}",
            ok=p.returncode == FAILED and p.stdout == "" and len(p.stderr.splitlines()) == 1,
        )


# The pty probes of `pty_cases`: openpty(3), and forkpty(3) through `pty.fork`, which Kaimon's
# session spawn calls; the second exits with the status of the forked shell.
PTY_OPEN = "import os, pty; m, s = pty.openpty(); os.close(m); os.close(s)"
PTY_FORK = """
import os, pty
pid, fd = pty.fork()
if pid == 0:
    try:
        os.execv("/bin/sh", ["/bin/sh", "-c", "true"])
    finally:
        os._exit(127)
_, status = os.waitpid(pid, 0)
os.close(fd)
raise SystemExit(os.waitstatus_to_exitcode(status))
"""


def sandboxed(
    sb: pathlib.Path,
    command: list[str] | None = None,
    env: dict[str, str] | None = None,
    timeout: int = TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """`command`, `/bin/sh -c true` without one, under `sandbox-exec -f sb`, in the environment
    `env`, this process's without one."""
    return subprocess.run(
        [str(SANDBOX_EXEC), "-f", str(sb), *(command or ["/bin/sh", "-c", "true"])],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )


# The probe run of the cases: the probe file is ARGS[1] and the scratch home ARGS[2]. Metal, `open`
# and `osascript` are stand-ins, and so are a TCP listener of the run on 127.0.0.1, a port of
# 127.0.0.1 that it closed, and two resolvers, one that answers 127.0.0.1 and one that throws
# DNSError, for the network probes, which never reach their default targets. One line
# `name result` per probe, then `classes true` when every result is `:allowed`, `:NotFunctional` or
# the name of an exception class of Base or Sockets, `open_gaps true`
# when OPEN_GAPS is `()`, and `gaps_negative true` when each open gap is a negative probe.
PROBE_RUN = """
using Sockets
include(ARGS[1])
P = ProbeDaemon
home = ARGS[2]
fake(ok) = () -> (m = Module(:FakeMetal); Core.eval(m, :(functional() = $ok)); m)
listener = listen(ip"127.0.0.1", 0)
port = Int(getsockname(listener)[2])
gone = listen(ip"127.0.0.1", 0)
closed = Int(getsockname(gone)[2])
close(gone)
loopback(host) = ip"127.0.0.1"
no_name(host) = throw(Sockets.DNSError(host, Int32(-3008)))
stand_ins = (
    :metal, :lsopen, :appleevent, :systemd_run, :session_bus,
    :connect_loopback, :connect_remote, :resolve_name,
)
every = unique((P.probe_names(false)..., P.probe_names(true)...))
results = [
    [name => getfield(P, name)(home) for name in every if !(name in stand_ins)];
    :metal => P.metal(home; module_of = fake(true));
    :metal_false => P.metal(home; module_of = fake(false));
    :metal_missing => P.metal(home; module_of = () -> error("no Metal"));
    :lsopen => P.lsopen(home; command = `true`);
    :lsopen_refused => P.lsopen(home; command = `false`);
    :appleevent => P.appleevent(home; command = `true`);
    :appleevent_refused => P.appleevent(home; command = `false`);
    :systemd_run => P.systemd_run(home; command = `true`);
    :systemd_run_refused => P.systemd_run(home; command = `false`);
    :session_bus => P.session_bus(home; command = `true`);
    :session_bus_refused => P.session_bus(home; command = `false`);
    :read_ssh_missing => P.read_ssh(joinpath(home, "none"));
    :write_julia_config_missing => P.write_julia_config(joinpath(home, "none"));
    :connect_loopback => P.connect_loopback(home; port);
    :connect_loopback_refused => P.connect_loopback(home; port = closed);
    :connect_remote => P.connect_remote(home; address = ip"127.0.0.1", port);
    :connect_remote_refused => P.connect_remote(home; address = ip"127.0.0.1", port = closed);
    :resolve_name => P.resolve_name(home; resolver = loopback);
    :resolve_name_refused => P.resolve_name(home; resolver = no_name);
    :pkg_offline_unset => withenv(() -> P.pkg_offline(home), "JULIA_PKG_OFFLINE" => nothing);
    :pkg_offline_false => withenv(() -> P.pkg_offline(home), "JULIA_PKG_OFFLINE" => "false");
]
close(listener)
for (name, r) in results
    println(name, " ", r isa Symbol ? r : "not-a-symbol")
end
exception(M, r) = isdefined(M, r) && getfield(M, r) isa Type && getfield(M, r) <: Exception
exception(r) = exception(Base, r) || exception(Sockets, r)
println("classes ", all(r -> r === :allowed || r === :NotFunctional || exception(r), last.(results)))
println("open_gaps ", P.OPEN_GAPS == ())
println("gaps_negative ", all(g -> g in P.NEGATIVE || g in P.LINUX_NEGATIVE, P.OPEN_GAPS))
println("macos_set ", join(P.probe_names(false), ","))
println("linux_set ", join(P.probe_names(true), ","))
println("default_set ", P.probe_names() == P.probe_names(Sys.islinux()))
"""
# The probes of `run_all` on macOS and on Linux, the positive ones first.
MACOS_PROBES = (
    "read_research,write_research,write_tempdir,list_packages,metal,connect_loopback,pkg_offline,"
    "read_ssh,read_claude_json,read_documents,read_gh_hosts,write_zshrc,write_git_hooks,"
    "write_julia_config,lsopen,appleevent,connect_remote,resolve_name"
)
LINUX_PROBES = (
    "read_research,write_research,write_tempdir,list_packages,read_ssh,read_claude_json,read_gh_hosts,"
    "write_zshrc,write_git_hooks,write_julia_config,systemd_run,session_bus"
)


# The tuple of open gaps in sandbox/probe-daemon.jl, and one probe name inside it.
OPEN_GAPS_LINE = re.compile(r"^const OPEN_GAPS = \(([^)]*)\)$", re.MULTILINE)
GAP_NAME = re.compile(r":(\w+)")
# The definitions of the network probes with their default targets, each a line of the probe file:
# the cases run each probe against stubs, so only these lines say what a session's run reaches.
NETWORK_DEFAULTS = (
    'connect_loopback(home = homedir(); address = ip"127.0.0.1", port = 2828) = '
    "attempt(() -> connect_tcp(address, port))",
    'connect_remote(home = homedir(); address = ip"1.1.1.1", port = 443) = '
    "attempt(() -> connect_tcp(address, port))",
    'resolve_name(home = homedir(); host = "julialang.org", resolver = Sockets.getaddrinfo) = '
    "attempt(() -> resolver(host))",
    "connect_tcp(address, port) = close(Sockets.connect(address, port))",
)
# The default command of the probe `appleevent`, between its backticks.
APPLEEVENT_COMMAND = re.compile(
    r"^function appleevent\(home = homedir\(\); command = `([^`]*)`\)$", re.MULTILINE
)


def probe_text_cases(case: Case) -> None:
    """The header comment of sandbox/probe-daemon.jl names `OPEN_GAPS` and each open gap, expects
    no exception class of an open gap, `:ProcessFailedException` of `appleevent`, an `IOError`
    class of `connect_remote` and `:DNSError` of `resolve_name`, and names the event of
    `appleevent`, `name of startup disk`; the network probes default to Kaimon's port
    127.0.0.1:2828, to 1.1.1.1:443 and to a lookup of julialang.org through `getaddrinfo`; the
    default command of `appleevent` asks the Finder for `name of startup disk`, which only an
    Apple Event answers."""
    text = PROBES.read_text(encoding="utf-8")
    header = text.split("\nmodule ProbeDaemon\n", 1)[0]
    found = OPEN_GAPS_LINE.search(text)
    gaps = GAP_NAME.findall(found.group(1)) if found else []
    case(
        f"the probe file defines OPEN_GAPS as (): {found.group(0) if found else None}",
        ok=found is not None and not gaps,
    )
    case(
        "the probe file's header names OPEN_GAPS and each open gap, and expects no exception class of one",
        ok="`OPEN_GAPS`" in header
        and all(f"`{g}`" in header and f"`{g}` `:ProcessFailedException`" not in header for g in gaps),
    )
    case(
        "the probe file's header expects :ProcessFailedException of appleevent and names its event",
        ok="`appleevent` `:ProcessFailedException`" in header and "`name of startup disk`" in header,
    )
    case(
        "the probe file's header expects an IOError class of connect_remote and :DNSError of resolve_name",
        ok="`connect_remote` an `IOError` class" in header and "`resolve_name` `:DNSError`" in header,
    )
    missing = [d for d in NETWORK_DEFAULTS if d not in text.split("\n")]
    case(
        f"the network probes default to 127.0.0.1:2828, 1.1.1.1:443 and julialang.org through "
        f"getaddrinfo: missing {missing}",
        ok=not missing,
    )
    command = APPLEEVENT_COMMAND.search(text)
    case(
        f"the default command of appleevent asks the Finder for the name of its startup disk: "
        f"{command.group(1) if command else None}",
        ok=command is not None
        and command.group(1) == """osascript -e 'tell app "Finder" to get name of startup disk'""",
    )


def probe_cases(case: Case, root: pathlib.Path) -> None:
    """Every probe of sandbox/probe-daemon.jl against a scratch home, where each is allowed, and
    against a home without the files, where each gives the name of an exception class."""
    julia = shutil.which("julia")
    if julia is None:
        print("skip  jobsandbox: no julia on the PATH; the probe cases of sandbox/probe-daemon.jl do not run")
        return
    home = root / "probe-home"
    for d in (
        "Research/Harness/.git/hooks",
        ".julia/packages/X",
        ".julia/config",
        ".ssh",
        "Documents",
        ".config/gh",
    ):
        (home / d).mkdir(parents=True)
    files = {
        "Research/a.txt": "secret research\n",
        ".ssh/id_ed25519": "secret key\n",
        ".claude.json": "secret state\n",
        "Documents/d.txt": "secret document\n",
        ".config/gh/hosts.yml": "secret token\n",
        ".zshrc": "secret rc\n",
    }
    for name, body in files.items():
        (home / name).write_text(body, encoding="utf-8")
    before = sorted(str(f.relative_to(home)) for f in home.rglob("*"))
    depot = root / "depot"
    depot.mkdir()
    p = subprocess.run(
        [julia, "--startup-file=no", "-e", PROBE_RUN, str(PROBES), str(home)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env={**os.environ, "JULIA_DEPOT_PATH": f"{depot}{os.pathsep}", "JULIA_PKG_OFFLINE": "true"},
        timeout=JULIA_TIMEOUT,
        check=False,
    )
    got = dict(line.split(" ", 1) for line in p.stdout.splitlines() if " " in line)
    case(
        f"the probe file runs with no warning: exit {p.returncode} {p.stderr.strip()[-300:]}",
        ok=p.returncode == 0 and "WARNING" not in p.stderr,
    )
    allowed = [
        "read_research",
        "write_research",
        "write_tempdir",
        "list_packages",
        "metal",
        "read_ssh",
        "read_claude_json",
        "read_documents",
        "read_gh_hosts",
        "write_zshrc",
        "write_git_hooks",
        "write_julia_config",
        "lsopen",
        "appleevent",
        "systemd_run",
        "session_bus",
        "connect_loopback",
        "pkg_offline",
        "connect_remote",
        "resolve_name",
    ]
    case(
        f"with no profile, every probe returns :allowed: {got}",
        ok=all(got.get(n) == "allowed" for n in allowed),
    )
    case(
        f"run_all runs the base set on macOS and the Linux set on Linux, and the system's set by "
        f"default: {got.get('macos_set')} {got.get('linux_set')}",
        ok=got.get("macos_set") == MACOS_PROBES
        and got.get("linux_set") == LINUX_PROBES
        and got.get("default_set") == "true",
    )
    refused = {
        "metal_false": "NotFunctional",
        "metal_missing": "ErrorException",
        "lsopen_refused": "ProcessFailedException",
        "appleevent_refused": "ProcessFailedException",
        "systemd_run_refused": "ProcessFailedException",
        "session_bus_refused": "ProcessFailedException",
        "read_ssh_missing": "IOError",
        "write_julia_config_missing": "SystemError",
        "connect_loopback_refused": "IOError",
        "connect_remote_refused": "IOError",
        "resolve_name_refused": "DNSError",
        "pkg_offline_unset": "KeyError",
        "pkg_offline_false": "ErrorException",
    }
    case(
        f"a refused probe returns the name of its exception class: {got}",
        ok=all(got.get(n) == want for n, want in refused.items()),
    )
    case(
        "every result is :allowed or the name of an exception class, never a file's content",
        ok=got.get("classes") == "true" and "secret" not in p.stdout,
    )
    case(
        f"OPEN_GAPS is (), and each open gap is a negative probe: {got}",
        ok=got.get("open_gaps") == "true" and got.get("gaps_negative") == "true",
    )
    after = sorted(str(f.relative_to(home)) for f in home.rglob("*"))
    changed = sorted(set(after) ^ set(before))
    case(
        f"the write probes delete what they create, and ~/.zshrc keeps its bytes: {changed}",
        ok=after == before and (home / ".zshrc").read_text(encoding="utf-8") == files[".zshrc"],
    )


def server_cases(case: Case, root: pathlib.Path) -> None:
    """scripts/julia-update-server against a scratch home with stubs of lsof, readlink, systemctl
    and notify-send that log their calls: it reads the update phase's state as data and removes
    it, reports a missing state, restarts a server whose binary is gone, reports a restart that is
    due, and runs no program of a PATH entry below the home."""
    home, stubs, log = root / "server-home", root / "server-stubs", root / "server.log"
    bindir = root / "server-release" / "bin"
    for d in (home / ".cache" / "julia-update", home / ".juliaup" / "bin", stubs, bindir):
        d.mkdir(parents=True)
    (bindir / "julia").write_text("", encoding="utf-8")
    state, marker = home / ".cache" / "julia-update" / "state", root / "server-marker"

    def stub(path: pathlib.Path, body: str) -> None:
        path.write_text(f'#!/bin/sh\necho "{path.name} $*" >> "{log}"\n{body}\n', encoding="utf-8")
        path.chmod(0o755)

    stub(stubs / "lsof", '[ -z "$STUB_PID" ] || printf \'%s\\n\' "$STUB_PID"')
    stub(stubs / "readlink", '[ -n "$STUB_EXE" ] || exit 1\nprintf \'%s\\n\' "$STUB_EXE"')
    stub(stubs / "systemctl", '[ -z "$STUB_RESTART_FAILS" ] || exit 1')
    stub(stubs / "notify-send", "exit 0")
    # A systemctl in a directory that the jobs write, first on the PATH that the unit gives.
    planted = home / ".juliaup" / "bin" / "systemctl"
    planted.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    planted.chmod(0o755)
    # The stub directory without lsof, and an rm, because its PATH holds no system directory.
    bare = root / "server-bare"
    bare.mkdir()
    for name in ("readlink", "systemctl", "notify-send"):
        shutil.copy(stubs / name, bare / name)
    (bare / "rm").write_text('#!/bin/sh\nexec /bin/rm "$@"\n', encoding="utf-8")
    (bare / "rm").chmod(0o755)
    good = f"before=1.0.0\nafter=1.0.0\nbindir={bindir}\n"
    gone = f"{root}/server-gone/bin/julia (deleted)"

    def server(text: str | None, **extra: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        log.unlink(missing_ok=True)
        if text is not None:
            state.write_text(text, encoding="utf-8")
        env = {"HOME": str(home), "PATH": f"{stubs}{os.pathsep}/usr/bin{os.pathsep}/bin"} | extra
        p = subprocess.run(
            ["/bin/sh", str(UPDATE_SERVER)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            # The directory of the planted systemctl, which an empty or relative PATH entry names.
            cwd=planted.parent,
            timeout=TIMEOUT,
            check=False,
        )
        return p, log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def names(calls: list[str]) -> list[str]:
        return [c.split(" ", 1)[0] for c in calls]

    p, calls = server(good)
    case(
        f"with no process on the port the server phase exits 0, calls only lsof and removes the state: "
        f"exit {p.returncode} {calls} {p.stdout.strip()[-200:]!r}",
        ok=p.returncode == 0 and names(calls) == ["lsof"] and not state.exists(),
    )
    p, calls = server(None)
    case(
        f"without the state the server phase reports the update phase as failed and alerts: "
        f"exit {p.returncode} {calls}",
        ok=p.returncode == 1 and "notify-send" in names(calls) and "wrote no" in p.stdout,
    )
    p, calls = server(good + "failure=juliaup update\nfailure=Kaimon update\n")
    case(
        f"each failure of the state is reported, counted in the alert, and exits 1: "
        f"exit {p.returncode} {calls}",
        ok=p.returncode == 1
        and "FAILED: juliaup update; Kaimon update" in p.stdout
        and any(c.startswith("notify-send julia-update 2 step(s) failed") for c in calls),
    )
    p, calls = server(good, STUB_PID="4242", STUB_EXE=gone)
    case(
        f"a server whose binary is deleted is restarted with systemctl: exit {p.returncode} {calls} "
        f"{p.stdout.strip()[-200:]!r}",
        ok=p.returncode == 0
        and "readlink /proc/4242/exe" in calls
        and "systemctl --user restart kaimon.service" in calls
        and "RESTARTED" in p.stdout
        and "notify-send" not in names(calls),
    )
    p, calls = server(good, STUB_PID="4242", STUB_EXE=gone, STUB_RESTART_FAILS="1")
    case(
        f"a restart that fails is a failure with an alert: exit {p.returncode} {calls}",
        ok=p.returncode == 1 and "notify-send" in names(calls),
    )
    for label, text, exe, due in (
        ("the default release", good, f"{bindir}/julia", False),
        ("the default release, deleted and written again", good, f"{bindir}/julia (deleted)", False),
        ("another release", good.replace(str(bindir), f"{root}/other"), f"{bindir}/julia", True),
        # A state with an empty bindir: no default release to compare the server with.
        (
            "a release, with no default known",
            good.replace(f"bindir={bindir}", "bindir="),
            f"{bindir}/julia",
            False,
        ),
        ("an older Kaimon", good.replace("after=1.0.0", "after=1.1.0"), f"{bindir}/julia", True),
    ):
        p, calls = server(text, STUB_PID="4242", STUB_EXE=exe)
        case(
            f"a server that runs {label} is not restarted, and a restart is {'due' if due else 'not due'}: "
            f"exit {p.returncode} {calls} {p.stdout.strip()[-200:]!r}",
            ok=p.returncode == 0
            and "systemctl" not in names(calls)
            and ("RESTART DUE" in p.stdout) == due
            and ("notify-send" in names(calls)) == due,
        )
    p, calls = server(good, PATH=str(bare))
    case(
        f"no lsof on the PATH is a failure, never no server: exit {p.returncode} {calls}",
        ok=p.returncode == 1
        and "cannot read the server" in p.stdout
        and "No process listens" not in p.stdout,
    )
    touch = f"$(touch {marker})"
    injected = "".join(
        f"{key}={value}\n"
        for key in ("before", "after", "bindir", "failure")
        for value in (touch, f"`touch {marker}`")
    )
    p, calls = server(injected, STUB_PID="4242", STUB_EXE=f"{bindir}/julia")
    case(
        f"the state is data: a value that holds a command substitution runs nothing: "
        f"exit {p.returncode} {marker.exists()} {p.stdout.strip()[-300:]!r}",
        ok=not marker.exists() and touch in p.stdout and not state.exists(),
    )
    p, calls = server(
        good,
        STUB_PID="4242",
        STUB_EXE=gone,
        # An empty entry names the working directory only after a kept entry, here the scratch root,
        # which holds no systemctl.
        PATH=os.pathsep.join(
            [
                str(home / ".juliaup" / "bin"),
                f"{home}/",
                str(bare.parent),
                "",
                ".",
                # An entry that does not exist: dropped, never kept as an empty entry.
                str(root / "server-none"),
                str(stubs),
                "/usr/bin",
                "/bin",
            ]
        ),
    )
    case(
        f"the server phase runs no program of a PATH entry below the home, empty or relative: "
        f"exit {p.returncode} {marker.exists()} {calls}",
        ok=not marker.exists() and "systemctl --user restart kaimon.service" in calls,
    )


def server_path_cases(case: Case, root: pathlib.Path) -> None:
    """scripts/julia-update-server compares each PATH entry by its physical path: it runs no lsof
    that lies at or below the physical home, or at or below the physical target of a symbolic
    link directly in the home, however the home and the entry are spelled, and it keeps the stub
    directory outside the home, whose lsof it runs. A home that does not resolve, and the home
    `/`, leave the PATH empty."""
    log, marker = root / "server-path.log", root / "server-path-marker"
    stubs = root / "server-path-stubs"
    stubs.mkdir()
    (stubs / "lsof").write_text(f'#!/bin/sh\necho "lsof $*" >> "{log}"\n', encoding="utf-8")
    (stubs / "lsof").chmod(0o755)
    good = "before=1.0.0\nafter=1.0.0\nbindir=\n"
    real = root / "server-path-home"
    linked = root / "server-path-link"
    linked.symlink_to(real)
    # A home whose ~/.juliaup is a link to a directory outside the home, and a link to that home.
    anchored = root / "server-anchor-home"
    outside = root / "server-anchor-juliaup"
    anchored_link = root / "server-anchor-link"
    for h in (real, anchored):
        (h / ".cache" / "julia-update").mkdir(parents=True)
    (real / ".juliaup" / "bin").mkdir(parents=True)
    (outside / "bin").mkdir(parents=True)
    (anchored / ".juliaup").symlink_to(outside)
    anchored_link.symlink_to(anchored)
    # A dangling link directly in the home, which is no anchor.
    (real / "dangling").symlink_to(root / "server-path-none")
    for d in (real / ".juliaup" / "bin", outside / "bin", real, outside):
        (d / "lsof").write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
        (d / "lsof").chmod(0o755)
    for label, home, entry, cwd in (
        ("an entry equal to the home", str(real), str(real), root),
        ("an entry equal to the target of a link directly in the home", str(anchored), str(outside), root),
        ("the home with a trailing /", f"{real}/", f"{real}/.juliaup/bin", root),
        ("an entry spelled through a link to the home", str(real), f"{linked}/.juliaup/bin", root),
        ("the home a link, the entry its real path", str(linked), f"{real}/.juliaup/bin", root),
        (
            "an entry below a link of the home to a directory outside it, spelled through a link to the home",
            str(anchored),
            f"{anchored_link}/.juliaup/bin",
            root,
        ),
        ("a relative entry, run in a directory outside the home", str(real), ".", outside / "bin"),
    ):
        log.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        pathlib.Path(home, ".cache", "julia-update", "state").write_text(good, encoding="utf-8")
        p = subprocess.run(
            ["/bin/sh", str(UPDATE_SERVER)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env={"HOME": home, "PATH": os.pathsep.join([entry, str(stubs), "/usr/bin", "/bin"])},
            cwd=cwd,
            timeout=TIMEOUT,
            check=False,
        )
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        case(
            f"{label}: the server phase runs no lsof of that entry, and runs the stub's lsof outside the "
            f"home: exit {p.returncode} {marker.exists()} {calls} {p.stdout.strip()[-200:]!r}",
            ok=not marker.exists() and [c.split(" ", 1)[0] for c in calls] == ["lsof"],
        )
    for label, home in (("a home that does not resolve", str(root / "server-no-home")), ("the home /", "/")):
        log.unlink(missing_ok=True)
        p = subprocess.run(
            ["/bin/sh", str(UPDATE_SERVER)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env={"HOME": home, "PATH": os.pathsep.join([str(stubs), "/usr/bin", "/bin"])},
            timeout=TIMEOUT,
            check=False,
        )
        case(
            f"{label} leaves the PATH empty: the server phase cannot read the server, a failure: "
            f"exit {p.returncode} {log.exists()} {p.stdout.strip()[-200:]!r}",
            ok=p.returncode == 1 and "cannot read the server" in p.stdout and not log.exists(),
        )


def server_text_cases(case: Case) -> None:
    """scripts/julia-update-server is an executable POSIX `sh` script with no `eval` that passes
    shellcheck; without shellcheck on the PATH, a skip line for that check."""
    text = UPDATE_SERVER.read_text(encoding="utf-8")
    case(
        "julia-update-server is an executable POSIX sh script that names no eval",
        ok=text.startswith("#!/bin/sh\n") and os.access(UPDATE_SERVER, os.X_OK) and "eval" not in text,
    )
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        print("skip  jobsandbox: no shellcheck on the PATH; scripts/julia-update-server is not checked")
        return
    p = subprocess.run(
        [shellcheck, str(UPDATE_SERVER)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    case(f"shellcheck passes scripts/julia-update-server: {p.stdout.strip()[-300:]!r}", ok=p.returncode == 0)


def update_cases(case: Case, root: pathlib.Path) -> None:
    """scripts/julia-update.jl as on Linux, the update phase, then scripts/julia-update-server, the
    server phase, against a scratch home with stubs of juliaup, the juliaup launcher, lsof,
    readlink, systemctl and notify-send that log their calls: the update phase calls none of the
    last four and writes its state into ~/.cache/julia-update/, one value per line; the server
    phase reads it. Without `julia` on the PATH they print a skip line."""
    julia = shutil.which("julia")
    if julia is None:
        print("skip  jobsandbox: no julia on the PATH; the cases of scripts/julia-update.jl do not run")
        return
    # The Julia binary itself: the juliaup launcher reads its configuration below the real home.
    binary, minor = subprocess.run(
        [
            julia,
            "--startup-file=no",
            "-e",
            r'print(joinpath(Sys.BINDIR, Base.julia_exename()), "\n", VERSION.major, ".", VERSION.minor)',
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=JULIA_TIMEOUT,
        check=False,
    ).stdout.split("\n")
    home, stubs, log = root / "update-home", root / "update-stubs", root / "update.log"
    depot = root / "update-depot"
    for d in (".juliaup/bin", ".julia/juliaup", ".julia/environments/apps/Kaimon"):
        (home / d).mkdir(parents=True)
    for d in (stubs, depot):
        d.mkdir()
    (home / ".julia" / "juliaup" / "juliaup.json").write_text('{"InstalledChannels": {}}\n', encoding="utf-8")
    project = home / ".julia" / "environments" / "apps" / "Kaimon" / "Project.toml"
    project.write_text('version = "1.0.0"\n', encoding="utf-8")

    def stub(path: pathlib.Path, body: str) -> None:
        path.write_text(f'#!/bin/sh\necho "{path.name} $*" >> "{log}"\n{body}\n', encoding="utf-8")
        path.chmod(0o755)

    # The launcher prints the BINDIR of the default release when asked for it.
    bindir = root / "update-release" / "bin"
    stub(home / ".juliaup" / "bin" / "julia", f"case \"$*\" in *Sys.BINDIR*) printf '%s' '{bindir}' ;; esac")
    for name in ("lsof", "readlink", "systemctl", "notify-send"):
        stub(stubs / name, "exit 0")
    state = home / ".cache" / "julia-update" / "state"
    env = {
        "HOME": str(home),
        "PATH": f"{stubs}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "JULIA_UPDATE_SYSTEM": "Linux",
        "RESEARCH_HARNESS_JULIA": str(home / "none"),
        "JULIA_DEPOT_PATH": f"{depot}{os.pathsep}",
        "JULIA_PKG_OFFLINE": "true",
    }

    def update(*, server: bool = False) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        log.unlink(missing_ok=True)
        p = subprocess.run(
            ["/bin/sh", str(UPDATE_SERVER)] if server else [binary, "--startup-file=no", str(UPDATE_SCRIPT)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            timeout=JULIA_TIMEOUT,
            check=False,
        )
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return p, [c.split(" ", 1)[0] for c in calls]

    system = ("lsof", "readlink", "systemctl", "notify-send")
    stub(home / ".juliaup" / "bin" / "juliaup", "exit 1")
    p, calls = update()
    held = state.read_text(encoding="utf-8").splitlines() if state.is_file() else []
    case(
        f"the update phase with a failed step exits 1, calls no lsof, readlink, systemctl or notify-send, "
        f"and writes the failure, the versions and the default BINDIR into its state: exit {p.returncode} "
        f"{calls} {held!r} {p.stderr.strip()[-300:]!r}",
        ok=p.returncode == 1
        and "juliaup" in calls
        and not any(c in system for c in calls)
        and held == ["before=1.0.0", "after=1.0.0", f"bindir={bindir}", "failure=juliaup update"],
    )
    p, calls = update(server=True)
    case(
        f"the server phase reads the failure, checks the server with lsof and alerts with notify-send: "
        f"exit {p.returncode} {calls} {p.stdout.strip()[-300:]!r}",
        ok=p.returncode == 1
        and "lsof" in calls
        and "notify-send" in calls
        and "systemctl" not in calls
        and "FAILED: juliaup update" in p.stdout,
    )
    stub(home / ".juliaup" / "bin" / "juliaup", "exit 0")
    p, calls = update()
    first = (p.returncode, calls)
    p, calls = update(server=True)
    case(
        f"after an update phase with no failure, the server phase exits 0 and alerts nothing: "
        f"{first} exit {p.returncode} {calls} {p.stdout.strip()[-300:]!r}",
        ok=first[0] == 0
        and not any(c in system for c in first[1])
        and p.returncode == 0
        and calls == ["lsof"]
        and not state.exists(),
    )
    update_bindir_case(case, update, home, bindir)
    project.write_text('version = "1.0.0\\nbindir=/x\\nfailure=y"\n', encoding="utf-8")
    p, calls = update()
    held = state.read_text(encoding="utf-8").splitlines() if state.is_file() else []
    case(
        f"a version with line breaks stays one line of the state: exit {p.returncode} {held!r}",
        ok=p.returncode == 0
        and [h.split("=", 1)[0] for h in held] == ["before", "after", "bindir"]
        and held[2] == f"bindir={bindir}",
    )
    project.write_text('version = "1.0.0"\n', encoding="utf-8")
    marker = planted_dates(root, minor, (depot, home / ".julia"))
    p, calls = update()
    case(
        f"the update phase loads no package of a depot's default environment: exit {p.returncode} {calls} "
        f"{p.stderr.strip()[-300:]!r}",
        ok=not marker.exists() and p.returncode == 0,
    )
    project.unlink()
    p, calls = update()
    case(
        f"an update phase that ends in an error leaves no state of an earlier run: "
        f"exit {p.returncode} {calls}",
        ok=p.returncode != 0 and not state.exists() and not any(c in system for c in calls),
    )
    p, calls = update(server=True)
    case(
        f"the server phase without the update phase's state reports a failure and alerts: "
        f"exit {p.returncode} {calls} {p.stdout.strip()[-300:]!r}",
        ok=p.returncode == 1 and "notify-send" in calls,
    )


def update_bindir_case(
    case: Case,
    update: Callable[..., tuple[subprocess.CompletedProcess[str], list[str]]],
    home: pathlib.Path,
    bindir: pathlib.Path,
) -> None:
    """The update phase with a juliaup launcher at ~/.juliaup/bin/julia that fails when asked for
    the default release's Sys.BINDIR: the state holds an empty `bindir` and a failure, which the
    server phase names. The launcher prints `bindir` again after the case."""
    launcher, state = home / ".juliaup" / "bin" / "julia", home / ".cache" / "julia-update" / "state"
    launcher.write_text('#!/bin/sh\ncase "$*" in *Sys.BINDIR*) exit 1 ;; esac\n', encoding="utf-8")
    _ = update()
    held = state.read_text(encoding="utf-8").splitlines() if state.is_file() else []
    p, _ = update(server=True)
    case(
        f"a launcher that fails to print the default BINDIR is a failure of the state, which the server "
        f"phase names: {held!r} exit {p.returncode} {p.stdout.strip()[-300:]!r}",
        ok=held[:3] == ["before=1.0.0", "after=1.0.0", "bindir="]
        and any(h.startswith("failure=") and "Sys.BINDIR" in h for h in held)
        and p.returncode == 1
        and "Sys.BINDIR" in p.stdout,
    )
    launcher.write_text(
        f"#!/bin/sh\ncase \"$*\" in *Sys.BINDIR*) printf '%s' '{bindir}' ;; esac\n", encoding="utf-8"
    )


def planted_dates(root: pathlib.Path, minor: str, depots: Sequence[pathlib.Path]) -> pathlib.Path:
    """A package named Dates with a UUID of its own, in the default environment `v<minor>` of each
    of `depots`, which the jobs write; it writes the returned marker when it loads."""
    marker = root / "update-planted"
    planted = root / "update-planted-Dates"
    (planted / "src").mkdir(parents=True)
    uuid = "00000000-0000-0000-0000-00000000d00d"
    (planted / "Project.toml").write_text(f'name = "Dates"\nuuid = "{uuid}"\n', encoding="utf-8")
    (planted / "src" / "Dates.jl").write_text(
        f'module Dates\nwrite({quoted(str(marker))}, "ran")\nend\n', encoding="utf-8"
    )
    for d in depots:
        environment = d / "environments" / f"v{minor}"
        environment.mkdir(parents=True, exist_ok=True)
        (environment / "Project.toml").write_text(f'[deps]\nDates = "{uuid}"\n', encoding="utf-8")
        (environment / "Manifest.toml").write_text(
            f'manifest_format = "2.0"\n\n[[deps.Dates]]\nuuid = "{uuid}"\npath = {quoted(str(planted))}\n',
            encoding="utf-8",
        )
    return marker


def update_text_cases(case: Case) -> None:
    """scripts/julia-update.jl resets the load path and the depot path before its first `using`,
    and restarts the server on macOS with `launchctl kickstart -k`."""
    text = UPDATE_SCRIPT.read_text(encoding="utf-8")
    case(
        "on macOS the script restarts the server with launchctl kickstart -k",
        ok="kickstart -k gui/" in text,
    )
    first_using = text.find("\nusing ")
    resets = [
        text.find(r)
        for r in (
            "\nempty!(LOAD_PATH)\n",
            '\npush!(LOAD_PATH, "@stdlib")\n',
            "\nfilter!(d -> startswith(d, dirname(Sys.BINDIR) * '/'), DEPOT_PATH)\n",
        )
    ]
    case(
        f"the script resets LOAD_PATH to @stdlib and cuts DEPOT_PATH before its first using: "
        f"{resets} {first_using}",
        ok=first_using > 0 and all(0 <= r < first_using for r in resets),
    )


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  jobsandbox: {label}")

    policy = load(POLICY)
    with tempfile.TemporaryDirectory(prefix="harness-jobsandbox-") as tmp:
        root = pathlib.Path(tmp).resolve()
        list_cases(case, policy)
        linux_list_cases(case, policy)
        (root / "bad").mkdir()
        bad_cases(case, root / "bad")
        linux_bad_cases(case, root / "bad")
        bwrap_cases(case, policy)
        bwrap_update_cases(case, policy)
        bwrap_pin_cases(case, policy)
        bwrap_edge_cases(case, policy)
        linux_root_cases(case, root, policy)
        (root / "jobbox").mkdir()
        jobbox_cases(case, root / "jobbox")
        (root / "jobbox-links").mkdir()
        box = JobboxRoot(case, root / "jobbox-links")
        box.make()
        jobbox_link_cases(case, box)
        jobbox_home_cases(case, box)
        jobbox_text_cases(case)
        server_cases(case, root)
        server_path_cases(case, root)
        server_text_cases(case)
        update_cases(case, root)
        update_text_cases(case)
        profile_cases(case, policy)
        pty_profile_cases(case, policy)
        network_profile_cases(case, policy)
        shim_cases(case)
        (root / "render").mkdir()
        render_cases(case, root / "render", policy)
        (root / "start").mkdir()
        start_cases(case, root / "start", policy)
        probe_text_cases(case)
        probe_cases(case, root)
    return total, wrong
