"""The Seatbelt profiles of the launch agents `kaimon` and `julia-update` on macOS.

    harness render sandbox/kaimon.sb        # print the profile of the Kaimon server
    harness render sandbox/julia-update.sb  # print the profile of the update job
    harness test jobsandbox                 # the cases below

`sandbox/daemon.toml` holds the rules of both jobs. `load` reads it into a `DaemonPolicy`, a frozen
dataclass: once for both jobs the denied operations and the denied Mach services, and for each job
of JOBS, in a table `[job.<name>]`, its read paths, read files, write paths, write files, write
denies, the files that it writes back inside a write deny, and `pty`, whether it uses
pseudo-terminals (`JobRules`). Each key is required, `pty` is true or false, each other value is a
list of strings, and a path is a token of TOKENS alone, or a start, `~`, nothing or a token, and
then `/` and one or more segments, none of them empty, `.` or `..`, so no `//` and no final `/`;
a read file can also be the root `/` alone, which dyld reads when a process starts.
A system path is in its real form: a path at or below `/etc`, `/tmp` or `/var`, in any case of
letters, is refused, because Seatbelt matches a path after it resolves the symlink
`/etc -> private/etc`, and a file system that ignores case reads `/ETC` as `/etc`. A denied
operation is lower-case words joined by `-`, with `*` (OPERATION), because the renderer writes it
into the profile as it is. A file that is not UTF-8 or not TOML, a missing job or key, an unknown
key or job, a relative path, a path with such a segment, a path in its link form, another operation,
a `pty` that is not a boolean and another value that is not a list of strings raise HarnessError,
which names the key or the path.

`profile` renders the profile of one job as SBPL text, in this order: `(version 1)`,
`(allow default)`, `(deny file-read* file-write*)`, `(allow file-read-metadata)`, one
`(allow file-read* …)` with a `subpath` per read path and a `literal` per read file, one
`(allow file-write* …)` with a `subpath` per write path and a `literal` per write file, for a job
with `pty = true` `(allow pseudo-tty)` and one `(allow file-read* file-write* file-ioctl …)` with
the `literal` PTY_MASTER and the `regex` PTY_SLAVES, both fixed in this module, one
`(deny file-write* …)` with a `subpath` per write deny and a `regex` per repository part of
REPOSITORY_PARTS at any depth below ~/Research, one `(allow file-write* …)` with a `literal` per
file written back, one `(deny <operation>)` per denied operation, and one `(deny mach-lookup …)`
with a `global-name` per denied service. Seatbelt applies the last rule that matches, so the write
denies follow the write allows, and the files written back follow the write denies. A block whose
list is empty is left out, because a block with no filter matches every path. `~` becomes `home`,
`$HARNESS` the profile's `harness`, and each `getconf` token its value (`UserDirs`) without a final
`/`, with a leading `/var/` written as `/private/var/`. Every path and regex is an ordinary SBPL
string, with `"` and `\\` escaped, and a regex escapes the metacharacters of the home path.

`harness render` of a template `sandbox/<job>.sb` (`job_of`), a file that does not exist, prints
`render` of that job: `profile` with the rule list `daemon.toml` beside the template, the profile's
`home` and `harness`, and the values of `getconf DARWIN_USER_TEMP_DIR` and
`getconf DARWIN_USER_CACHE_DIR`. A `getconf` that is not on the PATH, fails, or prints other than
one absolute path, a rule list that `load` refuses, and a job that is not one of JOBS, end it with
exit 2 and one line. `harness setup` on macOS and the services script of the dotfiles kit write
each render into `~/.config/research-harness/sandbox/<job>.sb` before they render and load the
job's plist.

The cases start `/bin/sh -c true` under the profile of each job, rendered with this user's home and
`getconf` directories, and expect exit 0; then, under kaimon's profile, this Python opening a
pseudo-terminal pair and forking `/bin/sh -c true` on a pseudo-terminal, as Kaimon starts a
session, and the juliaup launcher `~/.juliaup/bin/julia --startup-file=no -e 'exit(0)'`, which
opens juliaup's lock file for writing at every start, and expect exit 0 from each. Without
`/usr/bin/sandbox-exec` or `getconf`, or where `sandbox-exec` cannot apply even `(allow default)`,
as inside another Seatbelt sandbox, they print a skip line; where this Python cannot start under
kaimon's profile, a skip line for the pty runs, and without the launcher a skip line for its run.

`sandbox/probe-daemon.jl` holds the probes that a session runs through Kaimon's `ex` once the
server runs under its profile; the cases below run each probe against a scratch tree, where no
profile applies, and check the form of its result. Without `julia` on the PATH they print a skip
line.
"""

import dataclasses
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from typing import cast

from . import REPO, HarnessError
from .fsutil import Case

POLICY = REPO / "sandbox" / "daemon.toml"
PROBES = REPO / "sandbox" / "probe-daemon.jl"
JOBS = ("kaimon", "julia-update")
# The path-list keys of a job's table, its boolean key, and the keys of the rule list's top level.
JOB_KEYS = ("read", "read_files", "write", "write_files", "deny_write", "allow_write_files")
PTY_KEY = "pty"
TOP_KEYS = ("deny_operations", "deny_services", "job")
TOKENS = ("$DARWIN_USER_TEMP_DIR", "$DARWIN_USER_CACHE_DIR", "$HARNESS")
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
# Seconds for one `getconf` or one `sandbox-exec`, and for the cold Julia process of the probe cases.
TIMEOUT, JULIA_TIMEOUT = 60, 600


@dataclasses.dataclass(frozen=True, slots=True)
class JobRules:
    """The file rules of one job, each path as `daemon.toml` writes it, and whether the job uses
    pseudo-terminals."""

    read: tuple[str, ...]
    read_files: tuple[str, ...]
    write: tuple[str, ...]
    write_files: tuple[str, ...]
    deny_write: tuple[str, ...]
    allow_write_files: tuple[str, ...]
    pty: bool


@dataclasses.dataclass(frozen=True, slots=True)
class DaemonPolicy:
    """The rule list of `daemon.toml`: the rules of each job of JOBS, and the operations and Mach
    services that both deny."""

    kaimon: JobRules
    julia_update: JobRules
    deny_operations: tuple[str, ...]
    deny_services: tuple[str, ...]

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
        if key not in (*JOB_KEYS, PTY_KEY):
            raise HarnessError(f"{path}: unknown key `job.{job}.{key}`")
    lists: dict[str, tuple[str, ...]] = {}
    for key in JOB_KEYS:
        where = f"job.{job}.{key}"
        if key not in entries:
            raise HarnessError(f"{path}: no key `{where}`")
        lists[key] = tuple(checked_path(p, where, path) for p in strings(entries[key], where, path))
    if PTY_KEY not in entries:
        raise HarnessError(f"{path}: no key `job.{job}.{PTY_KEY}`")
    pty = entries[PTY_KEY]
    if not isinstance(pty, bool):
        raise HarnessError(f"{path}: `job.{job}.{PTY_KEY}` is not true or false")
    return JobRules(**lists, pty=pty)


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
    for key in data:
        if key not in TOP_KEYS:
            raise HarnessError(f"{path}: unknown key `{key}`")
    for key in TOP_KEYS:
        if key not in data:
            raise HarnessError(f"{path}: no key `{key}`")
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
    ]
    return "\n".join(lines) + "\n"


def job_of(template: pathlib.Path) -> str | None:
    """The job of a template `sandbox/<job>.sb`, else None."""
    return template.stem if template.parent.name == "sandbox" and template.suffix == ".sb" else None


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
    """The profile of the job of `template`, a path `sandbox/<job>.sb`, from the rule list beside it."""
    job = job_of(template)
    if job is None or job not in JOBS:
        raise HarnessError(f"{template}: no job {job!r}; the jobs are {', '.join(JOBS)}")
    dirs = UserDirs(getconf("DARWIN_USER_TEMP_DIR"), getconf("DARWIN_USER_CACHE_DIR"))
    return profile(load(template.parent / "daemon.toml"), job, home, dirs, harness)


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
        kaimon=JobRules(("$DARWIN_USER_CACHE_DIR",), (), ("$DARWIN_USER_TEMP_DIR",), (), (), (), pty=False),
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
        f"after kaimon's write denies, the one allow is juliaup's lock file, so juliaup.json and the "
        f"installed Julia versions stay unwritable: {after.count('(allow')} allow(s)",
        ok=after.count("(allow") == 1
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
    empty = dataclasses.replace(policy, kaimon=JobRules((), (), (), (), (), (), pty=False), deny_services=())
    bare = profile(empty, "kaimon", HOME, DIRS)
    case(
        "an empty list leaves its block out, never a block with no filter",
        ok="(allow file-read*" not in bare
        and "(allow file-write*" not in bare
        and "(deny mach-lookup" not in bare
        and "(deny file-write*\n" in bare,
    )
    case("two renders give the same bytes", ok=text == profile(load(POLICY), "kaimon", HOME, DIRS))


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
    bare = dataclasses.replace(policy, kaimon=JobRules((), (), (), (), (), (), pty=True))
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
        "job_of reads sandbox/<job>.sb and nothing else",
        ok=job_of(pathlib.Path("x/sandbox/kaimon.sb")) == "kaimon"
        and job_of(pathlib.Path("x/launchagents/kaimon.plist")) is None
        and job_of(pathlib.Path("x/sandbox/daemon.toml")) is None
        and job_of(pathlib.Path("x/other/kaimon.sb")) is None,
    )


def start_cases(case: Case, root: pathlib.Path, policy: DaemonPolicy) -> None:
    """A process starts under the profile of each job, rendered with this user's home and `getconf`
    directories: `/bin/sh -c true` under `sandbox-exec -f` exits 0, and so do the pty runs of
    `pty_cases` and the juliaup launcher under kaimon's profile, the launcher in the environment of
    the launch agent. Without `sandbox-exec`, without `getconf`, or where `sandbox-exec` cannot
    apply even the profile `(allow default)`, as inside another Seatbelt sandbox, they print a skip
    line; without the launcher, a skip line for its run."""
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
# and `osascript` are stand-ins. One line `name result` per probe, then `classes true` when every
# result is `:allowed`, `:NotFunctional` or the name of an exception class of Base.
PROBE_RUN = """
include(ARGS[1])
P = ProbeDaemon
home = ARGS[2]
fake(ok) = () -> (m = Module(:FakeMetal); Core.eval(m, :(functional() = $ok)); m)
stand_ins = (:metal, :lsopen, :appleevent)
results = [
    [name => getfield(P, name)(home) for name in (P.POSITIVE..., P.NEGATIVE...) if !(name in stand_ins)];
    :metal => P.metal(home; module_of = fake(true));
    :metal_false => P.metal(home; module_of = fake(false));
    :metal_missing => P.metal(home; module_of = () -> error("no Metal"));
    :lsopen => P.lsopen(home; command = `true`);
    :lsopen_refused => P.lsopen(home; command = `false`);
    :appleevent => P.appleevent(home; command = `true`);
    :appleevent_refused => P.appleevent(home; command = `false`);
    :read_ssh_missing => P.read_ssh(joinpath(home, "none"));
    :write_julia_config_missing => P.write_julia_config(joinpath(home, "none"));
]
for (name, r) in results
    println(name, " ", r isa Symbol ? r : "not-a-symbol")
end
exception(r) = isdefined(Base, r) && getfield(Base, r) isa Type && getfield(Base, r) <: Exception
println("classes ", all(r -> r === :allowed || r === :NotFunctional || exception(r), last.(results)))
"""


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
    ]
    case(
        f"with no profile, every probe returns :allowed: {got}",
        ok=all(got.get(n) == "allowed" for n in allowed),
    )
    refused = {
        "metal_false": "NotFunctional",
        "metal_missing": "ErrorException",
        "lsopen_refused": "ProcessFailedException",
        "appleevent_refused": "ProcessFailedException",
        "read_ssh_missing": "IOError",
        "write_julia_config_missing": "SystemError",
    }
    case(
        f"a refused probe returns the name of its exception class: {got}",
        ok=all(got.get(n) == want for n, want in refused.items()),
    )
    case(
        "every result is :allowed or the name of an exception class, never a file's content",
        ok=got.get("classes") == "true" and "secret" not in p.stdout,
    )
    after = sorted(str(f.relative_to(home)) for f in home.rglob("*"))
    changed = sorted(set(after) ^ set(before))
    case(
        f"the write probes delete what they create, and ~/.zshrc keeps its bytes: {changed}",
        ok=after == before and (home / ".zshrc").read_text(encoding="utf-8") == files[".zshrc"],
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
        (root / "bad").mkdir()
        bad_cases(case, root / "bad")
        profile_cases(case, policy)
        pty_profile_cases(case, policy)
        (root / "render").mkdir()
        render_cases(case, root / "render", policy)
        (root / "start").mkdir()
        start_cases(case, root / "start", policy)
        probe_cases(case, root)
    return total, wrong
