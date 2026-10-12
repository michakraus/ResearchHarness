"""The `systemd --user` units of `systemd/` against the launch agents of `launchagents/`.

Each job has a plist for launchd on macOS and a unit for `systemd --user` on Linux, both
templates of the profile. JOBS pairs them. `harness test` renders each with
`examples/profile.toml` and checks that the two describe one job:

- `ExecStart`, split as a shell splits it, equals `ProgramArguments`;
- the `Environment=` entries equal `EnvironmentVariables`, so the `PATH` is the same;
- the timer's `OnCalendar` equals `StartCalendarInterval`, and its `OnUnitActiveSec` equals
  `StartInterval`; a job with neither has no timer;
- a timer job that launchd starts at load (`RunAtLoad`) has `OnActiveSec`, and a persistent job
  has `[Install] WantedBy=default.target`;
- the service has `Restart=always` where the plist has `KeepAlive`;
- every directory of the `PATH` is denied to a session's writes by the settings template, that is
  no `allowWrite` entry covers it or a `denyWrite` entry names it, or is a system directory of
  SYSTEM_DIRS. A job runs outside the sandbox, so a directory that a session can write would let a
  session put a program on its `PATH`.

The module has no verb; its cases run in `harness test`.
"""

import contextlib
import fnmatch
import io
import json
import pathlib
import plistlib
import shlex
import tempfile
import types

from . import REPO, HarnessError, profile

UNITS = REPO / "systemd"
SETTINGS = REPO / "settings" / "settings.proposal.json"
# (service, timer or None, plist), relative to the repository.
JOBS = [
    ("systemd/kaimon.service", None, "launchagents/kaimon.plist"),
    ("systemd/julia-update.service", "systemd/julia-update.timer", "launchagents/julia-update.plist"),
    ("systemd/claude-autocommit.service", "systemd/claude-autocommit.timer", "launchagents/claude-autocommit.plist"),
]
# The directories that no session can write and that a job's PATH may hold beyond the denied ones.
SYSTEM_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/opt/homebrew/bin")
# The suffixes of a systemd time span that a timer here uses, in seconds.
SPAN = {"": 1, "s": 1, "sec": 1, "min": 60, "m": 60, "h": 3600}


def parse_unit(text):
    """{section: [(key, value), …]} of a unit file; `#` and `;` lines are comments."""
    sections, current = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#;":
            continue
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
    return int(number) * SPAN[span[len(number):]]


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


def path_problems(path, filesystem, home):
    """The directories of `path` that a session can write: not a system directory, covered by an
    `allowWrite` entry and named by no `denyWrite` entry."""
    allow = [expand(e, home) for e in filesystem["allowWrite"]]
    deny = [expand(e, home) for e in filesystem["denyWrite"]]
    return [d for d in path.split(":")
            if d not in SYSTEM_DIRS and (any(covers(e, d) for e in allow) and not any(covers(e, d) for e in deny))]


def job_problems(service, timer, plist, filesystem, home):
    """What differs between a rendered unit (and timer) and its rendered plist, and the PATH
    directories that a session can write."""
    problems = []
    args = shlex.split(one(service, "Service", "ExecStart") or "")
    if args != plist["ProgramArguments"]:
        problems.append(f"ExecStart {args} is not ProgramArguments {plist['ProgramArguments']}")
    env, penv = environment(service), plist.get("EnvironmentVariables", {})
    if env != penv:
        problems.append(f"Environment {env} is not EnvironmentVariables {penv}")
    keep = plist.get("KeepAlive", False)
    if keep != (one(service, "Service", "Restart") == "always"):
        problems.append(f"KeepAlive is {keep}, Restart= is {one(service, 'Service', 'Restart')}")
    scheduled = "StartCalendarInterval" in plist or "StartInterval" in plist
    if scheduled != (timer is not None):
        problems.append(f"the plist {'has' if scheduled else 'has no'} schedule, the job "
                        f"{'has' if timer is not None else 'has no'} timer")
    load = plist.get("RunAtLoad", False)
    if timer is not None:
        if "StartCalendarInterval" in plist and one(timer, "Timer", "OnCalendar") != calendar(plist["StartCalendarInterval"]):
            problems.append(f"OnCalendar {one(timer, 'Timer', 'OnCalendar')} is not {plist['StartCalendarInterval']}")
        active = one(timer, "Timer", "OnUnitActiveSec")
        if (active and seconds(active)) != plist.get("StartInterval"):
            problems.append(f"OnUnitActiveSec {active} is not StartInterval {plist.get('StartInterval')}")
        if load != (one(timer, "Timer", "OnActiveSec") is not None):
            problems.append(f"RunAtLoad is {load}, OnActiveSec= is {one(timer, 'Timer', 'OnActiveSec')}")
        if one(timer, "Timer", "Persistent") != "true":
            problems.append("the timer has no Persistent=true")
    elif load != (one(service, "Install", "WantedBy") == "default.target"):
        problems.append(f"RunAtLoad is {load}, WantedBy= is {one(service, 'Install', 'WantedBy')}")
    if "PATH" not in env:
        problems.append("the unit sets no PATH")
    else:
        problems += [f"PATH holds {d}, which a session can write" for d in path_problems(env["PATH"], filesystem, home)]
    return problems


def render(path, data):
    return profile.render_file(REPO / path, data)


def check_jobs(data, read=render):
    """{service: problems} for every job of JOBS rendered with the profile `data`; `read(path,
    data)` gives the rendered text of a template."""
    filesystem = json.loads(read("settings/settings.proposal.json", data))["sandbox"]["filesystem"]
    out = {}
    for service, timer, plist in JOBS:
        out[service] = job_problems(parse_unit(read(service, data)),
                                    timer and parse_unit(read(timer, data)),
                                    plistlib.loads(read(plist, data).encode()), filesystem, data["home"])
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
    dummy = profile.load(profile.DUMMY)
    for service, problems in check_jobs(dummy).items():
        check(not problems, f"{service} describes the job of its plist -> {problems}")

    # Each mutant changes one rendered template and must give a problem.
    def mutant(target, old, new):
        def read(path, data):
            text = render(path, data)
            if path == target:
                if old not in text:
                    raise AssertionError(f"{old!r} is not in {path}")
                text = text.replace(old, new, 1)
            return text
        return read

    home = dummy["home"]
    mutants = [
        ("kaimon.service without Restart=always", "systemd/kaimon.service", "Restart=always\n", ""),
        ("the home's Research directory on a unit's PATH", "systemd/claude-autocommit.service",
         "Environment=PATH=", f"Environment=PATH={home}/Research:"),
        ("the home's Research directory on a plist's PATH", "launchagents/kaimon.plist",
         f"<string>{home}/.juliaup/bin:", f"<string>{home}/Research:{home}/.juliaup/bin:"),
        ("another hour in julia-update.timer", "systemd/julia-update.timer", "OnCalendar=*-*-* 04:30",
         "OnCalendar=*-*-* 05:30"),
        ("another interval in claude-autocommit.timer", "systemd/claude-autocommit.timer",
         "OnUnitActiveSec=15min", "OnUnitActiveSec=10min"),
        ("another argument in kaimon.service", "systemd/kaimon.service", "--port 2828", "--port 2829"),
        ("no OnActiveSec in claude-autocommit.timer", "systemd/claude-autocommit.timer", "OnActiveSec=", "#"),
    ]
    for label, target, old, new in mutants:
        try:
            problems = check_jobs(dummy, mutant(target, old, new))
        except AssertionError as e:  # the template no longer holds the text the mutant changes
            check(False, f"the mutant {label} applies -> {e}")
            continue
        hit = [p for ps in problems.values() for p in ps]
        check(bool(hit), f"the mutant {label} is caught -> {hit}")

    # A directory that settings deny, inside an allowed one, passes; one only allowed fails.
    fs = {"allowWrite": ["~/R"], "denyWrite": ["~/R/bin", "~/R/**/.git/hooks"]}
    for path, bad in [("/h/R/bin", []), ("/h/R/x/.git/hooks", []), ("/h/R/x", ["/h/R/x"]),
                      ("/h/.juliaup/bin", []), ("/usr/sbin:/h/R", ["/h/R"]), ("/opt/homebrew/bin", [])]:
        got = path_problems(path, fs, "/h")
        check(got == bad, f"PATH {path} -> session-writable {got}")

    # autocommit_branch: the profile's value, `main` without it; a missing `home` exits 2.
    base = 'home = "/h"\nlaunchd_prefix = "org.x"\n'
    for template in ("systemd/claude-autocommit.service", "launchagents/claude-autocommit.plist"):
        for text, branch in [(base, "main"), (base + 'autocommit_branch = "memory/host"\n', "memory/host")]:
            got = render_default(template, text)
            want = (f"CLAUDE_AUTOCOMMIT_BRANCH={branch}\n" if template.endswith(".service")
                    else f"<string>{branch}</string>")
            check(got is not None and want in got, f"{template} renders branch {branch!r}")
        check(render_default(template, 'launchd_prefix = "org.x"\n') is None,
              f"{template} with no home exits 2")
    return n, wrong
