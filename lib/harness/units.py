"""The `systemd --user` units of `systemd/` against the launch agents of `launchagents/`.

Each job has a plist for launchd on macOS and a unit for `systemd --user` on Linux, both
templates of the profile. JOBS pairs them. `harness test` renders each with
`examples/profile.toml` and checks that the two describe one job:

- the units hold only the sections and keys of SERVICE_KEYS and TIMER_KEYS, each key but
  `Environment` once, and no continued line: anything else could change the job unseen;
- `ExecStart`, split as a shell splits it, equals `ProgramArguments`, and `WorkingDirectory`
  equals the plist's;
- the `Environment=` entries equal `EnvironmentVariables`, so the `PATH` is the same;
- the timer's triggers are exactly those the plist implies: `OnCalendar` for
  `StartCalendarInterval`, `OnUnitActiveSec` for `StartInterval`, and `OnActiveSec=0` for
  `RunAtLoad`; a job with no schedule has no timer, and starts at login
  (`WantedBy=default.target`) where the plist has `RunAtLoad`; a timer is wanted by
  `timers.target` and its service has no `[Install]`;
- the service has `Restart=always` where the plist has `KeepAlive`;
- every element of the `PATH` is an absolute, normalised directory that the settings keep out
  of session writes (no `allowWrite` entry covers it, or a `denyWrite` entry names it), or a
  system directory of SYSTEM_DIRS, and is not at or below $TMPDIR or a directory of
  SESSION_DIRS, which the live sandbox lets a session write. A job runs outside the sandbox, so a
  directory that a session can write, the working directory of an empty element included, would
  let a session put a program on its `PATH`. A session's working directory, which the sandbox
  lets it write too, has no fixed value, and the check does not place it.

The module has no subcommand; its cases run in `harness test`.
"""

import contextlib
import fnmatch
import io
import os
import pathlib
import plistlib
import posixpath
import runpy
import shlex
import tempfile
import types
from collections.abc import Callable
from typing import Any, cast
from unittest import mock

from . import REPO, HarnessError, jsonio, profile

UNITS = REPO / "systemd"
SETTINGS = REPO / "settings" / "settings.proposal.json"
# (service, timer or None, plist), relative to the repository.
JOBS = [
    ("systemd/kaimon.service", None, "launchagents/kaimon.plist"),
    ("systemd/julia-update.service", "systemd/julia-update.timer", "launchagents/julia-update.plist"),
    (
        "systemd/claude-autocommit.service",
        "systemd/claude-autocommit.timer",
        "launchagents/claude-autocommit.plist",
    ),
]
# The directories that no session can write and that a job's PATH may hold beyond the denied ones.
SYSTEM_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/opt/homebrew/bin")
# The directories below which macOS puts a session's $TMPDIR, which the live sandbox lets the session
# write, and the settings template does not name.
SESSION_DIRS = ("/var/folders", "/private/var/folders")
# The suffixes of a systemd time span that a timer here uses, in seconds.
SPAN = {"": 1, "s": 1, "sec": 1, "min": 60, "m": 60, "h": 3600}
# The sections and keys that the check reads, {section: keys}, of a service and of a timer. Any
# other section or key is a problem: the check cannot say what it does to the job.
SERVICE_KEYS = {
    "Unit": {"Description"},
    "Service": {
        "Type",
        "ExecStart",
        "WorkingDirectory",
        "Restart",
        "RestartSec",
        "Environment",
        "Nice",
        "IOSchedulingClass",
    },
    "Install": {"WantedBy"},
}
TIMER_KEYS = {
    "Unit": {"Description"},
    "Timer": {"OnCalendar", "OnUnitActiveSec", "OnActiveSec", "Persistent"},
    "Install": {"WantedBy"},
}
# The keys of a timer that start the job, and the keys that may appear only once.
TRIGGERS = {"OnCalendar", "OnUnitActiveSec", "OnActiveSec"}
ONCE = set().union(*SERVICE_KEYS.values(), *TIMER_KEYS.values()) - {"Environment"}


def parse_unit(text):
    """{section: [(key, value), …]} of a unit file; `#` and `;` lines are comments. A line
    continued with a backslash is refused, because the check does not join lines."""
    sections, current = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#;":
            continue
        if line.endswith("\\"):
            raise ValueError(f"a continued line: {line!r}")
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], [])
        elif current is None or "=" not in line:
            raise ValueError(f"not a unit line: {line!r}")
        else:
            key, _, val = line.partition("=")
            current.append((key.strip(), val.strip()))
    return sections


def entries(unit, section, key):
    """Every value of `key` in `section`, in order."""
    return [v for k, v in unit.get(section, []) if k == key]


def one(unit, section, key):
    """The single value of `key` in `section`, else None."""
    found = entries(unit, section, key)
    if len(found) > 1:
        raise ValueError(f"[{section}] has {key}= {len(found)} times")
    return found[0] if found else None


def environment(unit):
    """{name: value} of the `Environment=` entries of [Service], each one assignment."""
    env = {}
    for v in entries(unit, "Service", "Environment"):
        name, sep, val = v.strip('"').partition("=")
        if not sep:
            raise ValueError(f"Environment={v}: not NAME=value")
        env[name] = val
    return env


def seconds(span):
    """The seconds of a time span such as `900`, `900s` or `15min`."""
    number = span.rstrip("abcdefghijklmnopqrstuvwxyz")
    return int(number) * SPAN[span[len(number) :]]


def calendar(interval):
    """The `OnCalendar` expression of a daily `StartCalendarInterval` {Hour, Minute}."""
    if set(interval) != {"Hour", "Minute"}:
        raise ValueError(f"StartCalendarInterval {interval}: only a daily Hour and Minute is mapped")
    return f"*-*-* {interval['Hour']:02d}:{interval['Minute']:02d}:00"


def expand(entry, home):
    """A settings path with `~` as the home."""
    return home + entry[1:] if entry == "~" or entry.startswith("~/") else entry


def covers(entry, directory):
    """Whether the settings path `entry`, a glob, names `directory` or a directory above it."""
    path = pathlib.PurePosixPath(directory)
    return any(fnmatch.fnmatchcase(str(p), entry) for p in [path, *path.parents])


def session_dirs():
    """The directories that the live sandbox lets a session write beyond the template's
    `allowWrite`, whatever it denies: $TMPDIR when it is an absolute path, as written and with its
    symlinks resolved (on macOS /tmp is /private/tmp), and SESSION_DIRS."""
    tmpdir = os.environ.get("TMPDIR", "")
    if not tmpdir.startswith("/"):
        return list(SESSION_DIRS)
    return list(dict.fromkeys([posixpath.normpath(tmpdir), os.path.realpath(tmpdir), *SESSION_DIRS]))


def path_problems(path, filesystem, home):
    """The elements of `path` that a session can write, or that this check cannot place: one that
    is not an absolute, normalised path (an empty element is the working directory), a directory
    at or below one of `session_dirs`, and a directory that is not a system directory, is covered
    by an `allowWrite` entry and is named by no `denyWrite` entry."""
    allow = [expand(e, home) for e in filesystem["allowWrite"]]
    deny = [expand(e, home) for e in filesystem["denyWrite"]]
    session = session_dirs()
    return [
        d
        for d in path.split(":")
        if not d.startswith("/")
        or posixpath.normpath(d) != d
        or any(pathlib.PurePosixPath(d).is_relative_to(s) for s in session)
        or (d not in SYSTEM_DIRS and any(covers(e, d) for e in allow) and not any(covers(e, d) for e in deny))
    ]


def key_problems(unit, name, keys):
    """The sections and keys of `unit` outside `keys`, {section: allowed keys}, and the keys of
    ONCE that it repeats."""
    problems = []
    for section, pairs in unit.items():
        if section not in keys:
            problems.append(f"{name} has the section [{section}], which this check does not read")
            continue
        names = [k for k, _ in pairs]
        problems += [
            f"{name} has {k}= in [{section}], which this check does not read"
            for k in dict.fromkeys(names)
            if k not in keys[section]
        ]
        problems += [
            f"{name} has {k}= {names.count(k)} times in [{section}]"
            for k in dict.fromkeys(names)
            if k in ONCE and names.count(k) > 1
        ]
    return problems


def triggers(plist):
    """{the `[Timer]` key: its value} that the plist's schedule and RunAtLoad imply."""
    out = {}
    if "StartCalendarInterval" in plist:
        out["OnCalendar"] = calendar(plist["StartCalendarInterval"])
    if "StartInterval" in plist:
        out["OnUnitActiveSec"] = plist["StartInterval"]
    if out and plist.get("RunAtLoad", False):
        out["OnActiveSec"] = 0
    return out


def job_problems(service, timer, plist, filesystem, home):
    """What differs between a rendered unit (and timer) and its rendered plist, and the PATH
    directories that a session can write. A section, a key or a repeated key that the check does
    not read is a problem too, so that nothing it ignores can change the job."""
    problems = key_problems(service, "the service", SERVICE_KEYS)
    if timer is not None:
        problems += key_problems(timer, "the timer", TIMER_KEYS)
    if problems:
        return problems
    args = shlex.split(one(service, "Service", "ExecStart") or "")
    if args != plist["ProgramArguments"]:
        problems.append(f"ExecStart {args} is not ProgramArguments {plist['ProgramArguments']}")
    if one(service, "Service", "WorkingDirectory") != plist.get("WorkingDirectory"):
        problems.append(
            f"WorkingDirectory {one(service, 'Service', 'WorkingDirectory')} is not "
            f"{plist.get('WorkingDirectory')}"
        )
    env, penv = environment(service), plist.get("EnvironmentVariables", {})
    if env != penv:
        problems.append(f"Environment {env} is not EnvironmentVariables {penv}")
    keep = plist.get("KeepAlive", False)
    if keep != (one(service, "Service", "Restart") == "always"):
        problems.append(f"KeepAlive is {keep}, Restart= is {one(service, 'Service', 'Restart')}")
    want = triggers(plist)
    if bool(want) != (timer is not None):
        problems.append(
            f"the plist {'has' if want else 'has no'} schedule, the job "
            f"{'has' if timer is not None else 'has no'} timer"
        )
    load = plist.get("RunAtLoad", False)
    if timer is not None:
        have = {k: v for k, v in timer.get("Timer", []) if k in TRIGGERS}
        if set(have) != set(want):
            problems.append(
                f"the timer's triggers {sorted(have)} are not {sorted(want)}, which the plist implies"
            )
        for key in set(have) & set(want):
            value = have[key] if key == "OnCalendar" else seconds(have[key])
            if value != want[key]:
                problems.append(f"{key}={have[key]} is not {want[key]}, which the plist implies")
        if one(timer, "Timer", "Persistent") != "true":
            problems.append("the timer has no Persistent=true")
        if one(timer, "Install", "WantedBy") != "timers.target":
            problems.append(
                f"the timer's WantedBy= is {one(timer, 'Install', 'WantedBy')}, not timers.target"
            )
        if "Install" in service:
            problems.append(
                "the service of a timer has an [Install] section, which starts it beside the timer"
            )
    elif load != (one(service, "Install", "WantedBy") == "default.target"):
        problems.append(f"RunAtLoad is {load}, WantedBy= is {one(service, 'Install', 'WantedBy')}")
    if "PATH" not in env:
        problems.append("the unit sets no PATH")
    else:
        problems += [
            f"PATH holds {d!r}, which a session can write or this check cannot place"
            for d in path_problems(env["PATH"], filesystem, home)
        ]
    return problems


def render(path: str, data: profile.Profile) -> str:
    return profile.render_file(REPO / path, data)


def check_jobs(
    data: profile.Profile, read: Callable[[str, profile.Profile], str] = render
) -> dict[str, list[str]]:
    """{service: problems} for every job of JOBS rendered with the profile `data`; `read(path,
    data)` gives the rendered text of a template."""
    proposal = "settings/settings.proposal.json"
    filesystem = cast("dict[str, Any]", jsonio.loads(read(proposal, data), where=proposal))["sandbox"][
        "filesystem"
    ]
    out = {}
    for service, timer, plist in JOBS:
        try:
            out[service] = job_problems(
                parse_unit(read(service, data)),
                timer and parse_unit(read(timer, data)),
                plistlib.loads(read(plist, data).encode()),
                filesystem,
                data.home,
            )
        except (ValueError, KeyError) as e:  # a line, a time span or a schedule the check cannot read
            out[service] = [f"cannot read: {e}"]
    return out


def render_default(template, text):
    """`harness render` of `template` with a profile file of `text`: the rendered text, or None
    for an exit 2."""
    with tempfile.TemporaryDirectory(prefix="harness-units-") as tmp:
        path = pathlib.Path(tmp) / "profile.toml"
        path.write_text(text)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                profile.cmd_render(types.SimpleNamespace(template=str(REPO / template), profile=str(path)))
        except HarnessError:
            return None
        return out.getvalue()


def selftest():
    """The units against the plists, the mutants of the cases, and the default of
    `autocommit_branch`: (number of cases, number wrong)."""
    wrong = n = 0

    def check(ok, label):
        nonlocal wrong, n
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  units: {label}")

    expected = sorted(p for job in JOBS for p in job[:2] if p)
    found = sorted(f"systemd/{p.name}" for p in UNITS.iterdir()) if UNITS.is_dir() else []
    check(found == expected, f"systemd/ holds the five units -> {found}")
    if found != expected:
        return n, wrong
    # The dummy home, not this process's HOME: a HOME below $TMPDIR, which a session can write,
    # would put each unit's PATH below a session directory.
    dummy = profile.load(profile.DUMMY, home=profile.DUMMY_HOME)
    for service, problems in check_jobs(dummy).items():
        check(not problems, f"{service} describes the job of its plist -> {problems}")

    # The plist and the unit of claude-autocommit start the interpreter that bin/harness names by
    # default for the dummy's home, with the installed copy as its argument.
    boot = runpy.run_path(str(REPO / "bin" / "harness"), run_name="harness_boot")
    environment_path = cast("Callable[[], str]", boot["environment_path"])
    interpreter = cast("Callable[[str], str]", boot["interpreter"])
    clean = {k: v for k, v in os.environ.items() if k != "RESEARCH_HARNESS_PYTHON"}
    with mock.patch.dict(os.environ, clean | {"HOME": dummy.home}, clear=True):
        want = [interpreter(environment_path()), f"{dummy.home}/.local/bin/claude-autocommit"]
    plist_args = cast(
        "list[str]",
        plistlib.loads(render("launchagents/claude-autocommit.plist", dummy).encode())["ProgramArguments"],
    )
    exec_start = cast(
        "str", one(parse_unit(render("systemd/claude-autocommit.service", dummy)), "Service", "ExecStart")
    )
    check(
        plist_args == want and shlex.split(exec_start) == want,
        f"claude-autocommit runs on the interpreter of the Python environment "
        f"-> {plist_args}, {exec_start!r}",
    )

    # Each mutant changes one or more rendered templates, (path, old, new) each, and must give a
    # problem.
    def mutant(*edits: tuple[str, str, str]) -> Callable[[str, profile.Profile], str]:
        def read(path: str, data: profile.Profile) -> str:
            text = render(path, data)
            for target, old, new in edits:
                if path == target:
                    if old not in text:
                        raise AssertionError(f"{old!r} is not in {path}")
                    text = text.replace(old, new, 1)
            return text

        return read

    home, branch = dummy.home, dummy.autocommit_branch
    kaimon_path = f"{home}/.juliaup/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    autocommit_timer, update_timer = "systemd/claude-autocommit.timer", "systemd/julia-update.timer"
    update_service = "systemd/julia-update.service"
    mutants = [
        ("kaimon.service without Restart=always", [("systemd/kaimon.service", "Restart=always\n", "")]),
        (
            "the home's Research directory on a unit's PATH",
            [
                (
                    "systemd/claude-autocommit.service",
                    "Environment=PATH=",
                    f"Environment=PATH={home}/Research:",
                )
            ],
        ),
        (
            "the home's Research directory on a plist's PATH",
            [
                (
                    "launchagents/kaimon.plist",
                    f"<string>{home}/.juliaup/bin:",
                    f"<string>{home}/Research:{home}/.juliaup/bin:",
                )
            ],
        ),
        # The empty element is the working directory, which is ~/Research for kaimon.service.
        (
            "an empty element on the PATH of kaimon.service and its plist",
            [
                ("systemd/kaimon.service", kaimon_path + "\n", kaimon_path + ":\n"),
                ("launchagents/kaimon.plist", kaimon_path + "<", kaimon_path + ":<"),
            ],
        ),
        (
            "a relative directory on the PATH of kaimon.service and its plist",
            [
                ("systemd/kaimon.service", kaimon_path + "\n", kaimon_path + ":bin\n"),
                ("launchagents/kaimon.plist", kaimon_path + "<", kaimon_path + ":bin<"),
            ],
        ),
        (
            "another hour in julia-update.timer",
            [(update_timer, "OnCalendar=*-*-* 04:30", "OnCalendar=*-*-* 05:30")],
        ),
        (
            "another interval in claude-autocommit.timer",
            [(autocommit_timer, "OnUnitActiveSec=15min", "OnUnitActiveSec=10min")],
        ),
        ("another argument in kaimon.service", [("systemd/kaimon.service", "--port 2828", "--port 2829")]),
        ("no OnActiveSec in claude-autocommit.timer", [(autocommit_timer, "OnActiveSec=", "#")]),
        (
            "a later OnActiveSec in claude-autocommit.timer",
            [(autocommit_timer, "OnActiveSec=0", "OnActiveSec=5min")],
        ),
        (
            "an extra OnCalendar in claude-autocommit.timer",
            [(autocommit_timer, "\nPersistent=true", "\nOnCalendar=hourly\nPersistent=true")],
        ),
        (
            "an OnBootSec in julia-update.timer",
            [(update_timer, "\nPersistent=true", "\nOnBootSec=5min\nPersistent=true")],
        ),
        (
            "a second OnCalendar in julia-update.timer",
            [(update_timer, "\nPersistent=true", "\nOnCalendar=*-*-* 12:00:00\nPersistent=true")],
        ),
        (
            "a second ExecStart in julia-update.service",
            [(update_service, "Nice=5", f"ExecStart={home}/.local/bin/other\nNice=5")],
        ),
        (
            "an ExecStartPre in julia-update.service",
            [(update_service, "Nice=5", "ExecStartPre=/usr/bin/true\nNice=5")],
        ),
        (
            "an EnvironmentFile in julia-update.service",
            [(update_service, "Nice=5", f"EnvironmentFile={home}/Research/env\nNice=5")],
        ),
        (
            "a continued ExecStart line in julia-update.service",
            [(update_service, "julia-update.jl\n", "julia-update.jl \\\n  --extra\n")],
        ),
        (
            "an [Install] section in claude-autocommit.service",
            [
                (
                    "systemd/claude-autocommit.service",
                    f"Environment=CLAUDE_AUTOCOMMIT_BRANCH={branch}\n",
                    f"Environment=CLAUDE_AUTOCOMMIT_BRANCH={branch}\n[Install]\nWantedBy=default.target\n",
                )
            ],
        ),
        (
            "julia-update.timer wanted by no timers.target",
            [(update_timer, "WantedBy=timers.target", "WantedBy=default.target")],
        ),
        (
            "a section the check does not read in kaimon.service",
            [("systemd/kaimon.service", "[Install]", "[Socket]\nListenStream=2828\n[Install]")],
        ),
        (
            "another working directory in kaimon.service",
            [("systemd/kaimon.service", f"WorkingDirectory={home}/Research", f"WorkingDirectory={home}")],
        ),
    ]
    for label, edits in mutants:
        try:
            problems = check_jobs(dummy, mutant(*edits))
        except AssertionError as e:  # the template no longer holds the text the mutant changes
            check(False, f"the mutant {label} applies -> {e}")
            continue
        hit = [p for ps in problems.values() for p in ps]
        check(bool(hit), f"the mutant {label} is caught -> {hit}")

    # A directory that settings deny, inside an allowed one, passes; one only allowed fails.
    fs = {"allowWrite": ["~/R"], "denyWrite": ["~/R/bin", "~/R/**/.git/hooks"]}
    for path, bad in [
        ("/h/R/bin", []),
        ("/h/R/x/.git/hooks", []),
        ("/h/R/x", ["/h/R/x"]),
        ("/h/.juliaup/bin", []),
        ("/usr/sbin:/h/R", ["/h/R"]),
        ("/opt/homebrew/bin", []),
        ("/usr/bin:", [""]),
        (":/usr/bin", [""]),
        ("/usr/bin::/bin", [""]),
        ("/usr/bin:bin", ["bin"]),
        ("/usr/bin:./bin", ["./bin"]),
        ("/h/R/bin/../x", ["/h/R/bin/../x"]),
    ]:
        got = path_problems(path, fs, "/h")
        check(got == bad, f"PATH {path} -> session-writable {got}")

    # A directory below $TMPDIR, /var/folders or /private/var/folders is a session's to write, whatever
    # the settings grant or deny; a sibling of one is not below it.
    fs = {"allowWrite": [], "denyWrite": ["/s/**", "/var/**", "/private/**"]}
    for tmpdir in ["/s/tmp/", None]:
        env = {k: v for k, v in os.environ.items() if k != "TMPDIR"} | ({"TMPDIR": tmpdir} if tmpdir else {})
        for path, bad in [
            ("/s/tmp", ["/s/tmp"]),
            ("/s/tmp/bin", ["/s/tmp/bin"]),
            ("/s/tmp2/bin", []),
            ("/s/bin", []),
            ("/var/folders/ab/T/bin", ["/var/folders/ab/T/bin"]),
            ("/var/folders", ["/var/folders"]),
            ("/private/var/folders/ab/T", ["/private/var/folders/ab/T"]),
            ("/var/folders2/bin", []),
            ("/usr/bin:/var/folders/x:/bin", ["/var/folders/x"]),
        ]:
            want = bad if tmpdir or not path.startswith("/s/tmp") else []
            with mock.patch.dict(os.environ, env, clear=True):
                got = path_problems(path, fs, "/h")
            check(got == want, f"PATH {path} with TMPDIR={tmpdir} -> session-writable {got}")
    # A $TMPDIR that is a symlink, as /tmp is on macOS: an element below its real path fails too.
    with tempfile.TemporaryDirectory(prefix="harness-units-") as tmp:
        real, link = pathlib.Path(tmp, "real"), pathlib.Path(tmp, "link")
        real.mkdir()
        link.symlink_to(real)
        element = os.path.realpath(real) + "/bin"
        with mock.patch.dict(os.environ, {"TMPDIR": str(link)}):
            got = path_problems(element, {"allowWrite": [], "denyWrite": []}, "/h")
        check(
            got == [element],
            f"PATH {element} below the real path of a symlinked TMPDIR -> session-writable {got}",
        )

    # autocommit_branch: the profile's value, else `memory/<short host name>` on a host that is
    # not `template_host`, else `main`; a missing `home` is the running user's, and a relative one
    # exits 2.
    base = profile.profile_text(home='"/h"', launchd_prefix='"org.x"')
    for template in ("systemd/claude-autocommit.service", "launchagents/claude-autocommit.plist"):
        for text, branch in [
            (base, "main"),
            (base + 'autocommit_branch = "memory/host"\n', "memory/host"),
            (base + 'template_host = "alpha"\n', "memory/beta"),
            (base + 'template_host = "beta"\n', "main"),
        ]:
            with mock.patch("socket.gethostname", return_value="beta.example.org"):
                got = render_default(template, text)
            want = (
                f"CLAUDE_AUTOCOMMIT_BRANCH={branch}\n"
                if template.endswith(".service")
                else f"<string>{branch}</string>"
            )
            check(got is not None and want in got, f"{template} renders branch {branch!r}")
        with mock.patch.dict(os.environ, HOME="/running/user"):
            got = render_default(template, profile.profile_text(launchd_prefix='"org.x"'))
        check(
            got is not None and "/running/user/" in got and "{home}" not in got,
            f"{template} with no home renders the running user's home",
        )
        check(
            render_default(template, profile.profile_text(home='"h"', launchd_prefix='"org.x"')) is None,
            f"{template} with a relative home exits 2",
        )
    return n, wrong
