"""`harness test`: the harness's own test cases, run as parts, each in a process of its own.

    harness test [NAME ...] [--changed BASE] [--list] [--jobs N] [--log FILE]

A part is a module of lib/harness/ with a `selftest`, by its module name; an adapter, by the name
of its directory below adapters/; a group of the hook probe, `probe:<group>`; a group of doctor's
cases, `doctor:<group>`; or the contract sweep, `sweep`. Each part runs in a child process that
prints one line per case and, last, `<n> cases, <w> wrong`. A part that ends with no such line,
or whose exit status disagrees with it, is one more wrong case; a part that runs longer than
TIMEOUT seconds is one wrong case. The run goes on.

Names select those parts; `--changed BASE` selects the parts that OWNERS gives for each path of
`git diff --name-status BASE...HEAD`, and every part when a path has no owner. `docs` and `sweep`
run in every selection. At most `--jobs` parts run at once, half the CPUs by default; their output
is printed whole, part by part, in the order of the part names.

A run holds one of SLOTS slots, an exclusive `flock` on a file below `slot_directory()`, so that at
most two runs share a machine; the kernel frees a slot when the process that holds it ends.
"""

import argparse
import concurrent.futures
import contextlib
import fcntl
import fnmatch
import importlib.util
import inspect
import io
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
from unittest import mock

from . import REPO, HarnessError, changelog, doctor, sweep

HARNESS = [sys.executable, str(REPO / "bin" / "harness")]
PROBE = REPO / "hooks" / "probe.py"
# The groups of hooks/probe.py, its GROUPS; a case of `selftest` checks that the two agree.
PROBE_GROUPS = ("commands", "payloads", "manifest", "drift", "omp", "opencode", "antigravity")
ALWAYS = ("docs", "sweep")
SUMMARY = re.compile(r"(\d+) cases, (\d+) wrong")
TIMEOUT = 300  # seconds per part
SLOTS = 2

# The owners of a path of the repository: the first pattern that matches the whole path gives
# them, as part names or globs over the part names, with `\1` the pattern's group. A path that no
# pattern matches, or whose owners are no part, selects every part.
OWNERS = [
    # The probe groups of these three adapters load their guard files from the repository.
    (r"adapters/(omp|opencode|antigravity)/.+", [r"\1", r"probe:\1"]),
    (r"adapters/([^/]+)/.+", [r"\1"]),
    (r"hooks/.+", ["probe:*"]),
    (r"lib/harness/doctor\.py", ["doctor:*"]),
    (r"lib/harness/([^/]+)\.py", [r"\1"]),
    (r"docs/src/dependencies\.md", ["docs", "doctor:minimum"]),
    (r"docs/.+", ["docs"]),
    (r"changelog\.d/.+", ["changelog"]),
]


def part_name(module):
    """The part name of a module of lib/harness/ or of an adapter."""
    return module.__name__.removeprefix("harness_adapter_").rpartition(".")[2]


def parts(modules):
    """Every part, sorted by name: {name: the command line of the child process that runs it}."""
    table = {part_name(m): [*HARNESS, "test", "--part", part_name(m)]
             for m in modules if hasattr(m, "selftest") and m is not doctor}
    table |= {f"doctor:{g}": [*HARNESS, "test", "--part", f"doctor:{g}"] for g in doctor.GROUPS}
    table |= {f"probe:{g}": [sys.executable, str(PROBE), g] for g in PROBE_GROUPS}
    table["sweep"] = [*HARNESS, "test", "--part", "sweep"]
    return dict(sorted(table.items()))


def selftest_of(name, modules):
    """The function that the child process of the part `name` runs: () -> (cases, wrong)."""
    if name.startswith("doctor:"):
        return lambda: doctor.selftest((name.partition(":")[2],))
    if name == "sweep":
        return sweep.selftest
    return {part_name(m): m.selftest for m in modules if hasattr(m, "selftest")}[name]


def owners(path, names):
    """The parts of `names` that own `path`, a path relative to the repository, sorted; [] when no
    part does."""
    for pattern, owned in OWNERS:
        m = re.fullmatch(pattern, path)
        if m:
            globs = [m.expand(o) for o in owned]
            return sorted(n for n in names if any(fnmatch.fnmatchcase(n, g) for g in globs))
    return []


def changed(base, names, root=REPO):
    """The parts of `names` that the paths of `git diff --name-status base...HEAD` in `root` select,
    both paths of a rename or a copy, with docs and sweep: (the selected names in the order of
    `names`, one line per path that says what it selects). An empty base, which git would read as
    HEAD, and a base that git cannot resolve raise."""
    if not base:
        raise HarnessError("--changed: BASE is empty")
    p = subprocess.run(["git", "diff", "--name-status", "-z", "--end-of-options", f"{base}...HEAD", "--"], cwd=root,
                       capture_output=True, text=True, check=False)
    if p.returncode != 0:
        message = p.stderr.strip().splitlines()
        raise HarnessError(f"--changed {base}: git diff exits {p.returncode}" + (f": {message[0]}" if message else ""))
    chosen, reasons = set(ALWAYS), []
    for path in dict.fromkeys(path for _, path in changelog.changes(p.stdout)):
        owned = owners(path, names)
        if owned:
            chosen |= set(owned)
            reasons.append(f"{path} selects {', '.join(owned)}")
        else:
            chosen = set(names)
            reasons.append(f"{path} has no owner and selects every part")
    return [n for n in names if n in chosen], reasons


# The child processes that run now; an error, an interrupt, a SIGTERM or a SIGHUP of the run stops
# their process groups.
LIVE = set()
LIVE_LOCK = threading.Lock()


def stop(p):
    """Kill the process group of the child `p`, which `run_part` starts as a group of its own."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(p.pid, signal.SIGKILL)


def leave(signum, _frame):
    """The handler of SIGTERM and SIGHUP while parts run: ignore a second one, and end the run with
    status 128 + `signum` through an exception, so that `run_parts` stops the parts first."""
    for s in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, signal.SIG_IGN)
    raise SystemExit(128 + signum)


def run_part(name, argv, timeout=TIMEOUT):
    """Run one part's child process: (cases, wrong, its output lines without the summary line).

    A child that ends with no summary line or with an exit status that disagrees with it is one more
    wrong case, and a child that runs longer than `timeout` seconds is stopped and is one wrong case;
    each has a BAD line that names the part. Its stderr follows its stdout, so a crash shows its
    traceback."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    with LIVE_LOCK:
        LIVE.add(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(p)
        out, err = p.communicate()
        lines = out.rstrip().splitlines()
        return 1, 1, [*lines, f"BAD  {name}: runs longer than {timeout} s and is stopped", *err.rstrip().splitlines()]
    finally:
        with LIVE_LOCK:
            LIVE.discard(p)
    lines = out.rstrip().splitlines()
    m = SUMMARY.fullmatch(lines[-1]) if lines else None
    body = "\n".join(lines[:-1] if m else lines).rstrip().splitlines()
    n, w = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if m is None or (p.returncode != 0) != (w > 0):
        body.append(f"BAD  {name}: exit {p.returncode} with {'no summary line' if m is None else lines[-1]!r}")
        n, w = n + 1, w + 1
    return n, w, body + err.rstrip().splitlines()


def run_parts(table, jobs, emit, timeout=TIMEOUT):
    """Run the parts of `table`, {name: argv}, at most `jobs` at once, and call
    `emit(name, lines, cases, wrong)` for each part in the order of `table`: (cases, wrong). It runs
    in the main thread, where a SIGTERM or a SIGHUP stops the parts and ends the run (`leave`)."""
    total = wrong = 0
    previous = {s: signal.signal(s, leave) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            try:
                results = pool.map(lambda item: run_part(*item, timeout=timeout), table.items())
                for name, (n, w, lines) in zip(table, results, strict=True):
                    emit(name, lines, n, w)
                    total, wrong = total + n, wrong + w
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)
                with LIVE_LOCK:
                    for p in LIVE:
                        stop(p)
                raise
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)
    return total, wrong


def slot_directory():
    """The directory of the slot files: $XDG_RUNTIME_DIR, else $TMPDIR, else /tmp."""
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
    return pathlib.Path(base) / "research-harness-test"


def take_slot(directory, say, poll=0.5):
    """Hold one of the SLOTS slot files of `directory` with an exclusive `flock` and return the open
    file, which holds the slot until it is closed or the process ends. While every slot is held, call
    `say` once with a line that says the run waits, and try again every `poll` seconds."""
    directory.mkdir(parents=True, exist_ok=True)
    said = False
    while True:
        for i in range(1, SLOTS + 1):
            f = open(directory / f"slot-{i}.lock", "a")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
            else:
                return f
        if not said:
            say(f"harness test: {SLOTS} runs hold the slots of {directory}; this run waits until one ends")
            said = True
        time.sleep(poll)


def jobs_count(text):
    """The argument of --jobs: a whole number of 1 or more."""
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if n < 1:
        raise argparse.ArgumentTypeError(f"{n} is below 1")
    return n


def cmd_test(args, modules):
    table = parts(modules)
    if args.part is not None:
        if args.part not in table or args.part.startswith("probe:"):  # a probe group runs as hooks/probe.py
            raise HarnessError(f"no part {args.part} runs through --part")
        n, w = selftest_of(args.part, modules)()
        print(f"\n{n} cases, {w} wrong")
        return 1 if w else 0
    if args.names and args.changed is not None:
        raise HarnessError("part names and --changed exclude each other")
    unknown = [name for name in args.names if name not in table]
    if unknown:
        raise HarnessError(f"no part {', '.join(unknown)}; `harness test --list` lists the parts")
    if args.names:
        names = [n for n in table if n in {*args.names, *ALWAYS}]
    elif args.changed is not None:
        names, reasons = changed(args.changed, list(table))
        for line in reasons:
            print(f"harness test: {line}", file=sys.stderr)
    else:
        names = list(table)
    if args.list:
        print("\n".join(names))
        return 0
    try:
        log = open(args.log, "w", encoding="utf-8") if args.log else None
    except OSError as e:
        raise HarnessError(f"--log {args.log}: {e.strerror}") from None
    try:
        try:
            slot = take_slot(slot_directory(), lambda line: print(line, file=sys.stderr, flush=True))
        except OSError as e:
            raise HarnessError(f"the slot directory {slot_directory()}: {e.strerror}") from None
        with slot:
            wrong = report({n: table[n] for n in names}, jobs(args.jobs, len(names), os.cpu_count()), log, sys.stdout)
    finally:
        if log is not None:
            log.close()
    return 1 if wrong else 0


def jobs(requested, count, cpus):
    """The number of parts that run at once: `requested`, by default half of `cpus` (None when
    unknown) and at least 1, and never more than the `count` parts."""
    return min(requested or max(1, (cpus or 2) // 2), count)


def report(table, at_once, log, out, timeout=TIMEOUT):
    """Run the parts of `table` with `run_parts`, `at_once` at a time, and write each part's lines, a line
    `part <name>: <n> cases, <w> wrong` and, last, the summary `<n> cases, <w> wrong`: all of it to
    `out` when `log` is None, else all of it to `log` and only the BAD lines and the summary to
    `out`. Returns the number of wrong cases."""

    def emit(name, lines, n, w):
        text = "\n".join([*lines, f"part {name}: {n} cases, {w} wrong"]) + "\n"
        if log is None:
            out.write(text)
        else:
            log.write(text)
            out.write("".join(line + "\n" for line in lines if line.startswith("BAD")))
        out.flush()

    total, wrong = run_parts(table, at_once, emit, timeout=timeout)
    summary = f"\n{total} cases, {wrong} wrong\n"
    if log is not None:
        log.write(summary)
    out.write(summary)
    return wrong


def register(sub, modules):
    """The subcommand `test`; `modules` returns the modules and adapters whose cases it runs."""
    p = sub.add_parser("test", help="run the harness's own test cases, or the parts that a name or a change selects",
                       description="Run the harness's own test cases as parts, each in a process of its own: the "
                                   "cases of each module and adapter, the groups of the hook probe and of doctor, "
                                   "and the contract sweep. It prints each part's lines and `<n> cases, <w> wrong`, "
                                   "and exits 1 when a case fails, 2 on a usage error.")
    p.add_argument("names", nargs="*", metavar="NAME", help="run these parts, with docs and sweep")
    p.add_argument("--changed", metavar="BASE",
                   help="run the parts that own a path of `git diff BASE...HEAD`, with docs and sweep")
    p.add_argument("--list", action="store_true", help="print the selected part names and run nothing")
    p.add_argument("--jobs", type=jobs_count, metavar="N", help="run at most N parts at once; default: half the CPUs")
    p.add_argument("--log", metavar="FILE",
                   help="write every line to FILE, and print only the BAD lines and the summary")
    p.add_argument("--part", help=argparse.SUPPRESS)  # the child process of one part
    p.set_defaults(run=lambda args: cmd_test(args, modules()))


def selftest():
    """The runner's own cases: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  testrun: {label}")

    def child(code):
        return [sys.executable, "-c", code]

    def passing(n):
        return child(f"print('ok   a case'); print(); print('{n} cases, 0 wrong')")

    # Each part's result is counted once, also the last one, and emitted whole in the order of the
    # table, whatever the number of jobs.
    table = {"a": passing(1), "b": passing(2),
             "c": child("import sys; print('BAD  a case'); print('4 cases, 1 wrong'); sys.exit(1)"),
             "d": passing(3), "e": passing(5)}
    for at_once in (1, 3, 5):
        seen = []
        got = run_parts(table, at_once, lambda name, lines, n, w, seen=seen: seen.append((name, n, w, lines)))
        check(got == (15, 1) and [s[:3] for s in seen] == [("a", 1, 0), ("b", 2, 0), ("c", 4, 1), ("d", 3, 0),
                                                           ("e", 5, 0)]
              and seen[0][3] == ["ok   a case"],
              f"--jobs {at_once}: five parts give 15 cases, 1 wrong, each part once and in order: {got}, "
              f"{[s[:3] for s in seen]}")

    # A part that crashes, ends with no summary line, or whose exit status disagrees with its summary
    # is one more wrong case, and the run goes on.
    for label, code, want, text in (
            ("a crash", "raise ValueError('boom')", (1, 1), "ValueError: boom"),
            ("no summary line", "print('ok   a case')", (1, 1), "no summary line"),
            ("exit 1 with no wrong case", "import sys; print('2 cases, 0 wrong'); sys.exit(1)", (3, 1), "exit 1"),
            ("exit 0 with a wrong case", "print('2 cases, 1 wrong')", (3, 2), "exit 0")):
        n, w, lines = run_part("x", child(code))
        check((n, w) == want and any(line.startswith("BAD  x: ") for line in lines) and text in "\n".join(lines),
              f"{label}: {(n, w)} -> {want}, a BAD line that names the part, and {text!r} in {lines[-3:]}")

    # A part that runs past the timeout is stopped with the children it started, and is one wrong case.
    start = time.monotonic()
    n, w, lines = run_part("slow", child("import subprocess, sys, time; "
                                         "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                                         "print('ok   a case', flush=True); time.sleep(30)"), timeout=1)
    took = time.monotonic() - start
    check((n, w) == (1, 1) and took < 10 and "BAD  slow: runs longer than 1 s and is stopped" in lines,
          f"a part past its timeout: {(n, w)} after {took:.1f} s, {lines}")
    defaults = {f.__name__: inspect.signature(f).parameters["timeout"].default for f in (run_part, run_parts, report)}
    check(set(defaults.values()) == {300}, f"a part's timeout is 300 s: {defaults}")
    n, w, lines = run_part("x", child("print('2 cases, 0 wrong.')"))
    check((n, w) == (1, 1), f"a last line with more than the summary is no summary line: {(n, w)}, {lines}")

    # --jobs runs the parts at once: three parts of 1.5 s each take less than two of them in a row.
    def mark(*_):
        pass

    before = [signal.signal(s, mark) for s in (signal.SIGTERM, signal.SIGHUP)]
    start = time.monotonic()
    run_parts({k: child("import time; time.sleep(1.5); print('1 cases, 0 wrong')") for k in "abc"}, 3,
              lambda *_: None)
    took = time.monotonic() - start
    check(took < 3, f"--jobs 3 runs three parts of 1.5 s at once: {took:.1f} s")
    after = [signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)]
    check(after == [mark, mark], f"run_parts gives SIGTERM and SIGHUP their handlers back: {after}")
    try:
        leave(signal.SIGTERM, None)
        code = None
    except SystemExit as e:
        code = e.code
    ignored = [signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)]
    for s, handler in zip((signal.SIGTERM, signal.SIGHUP), before, strict=True):
        signal.signal(s, handler)
    check(code == 128 + signal.SIGTERM and ignored == [signal.SIG_IGN] * 2,
          f"a SIGTERM ends the run with 128 + 15 and ignores a second one: {code}, {ignored}")
    got = [jobs(*a) for a in ((None, 99, None), (None, 99, 1), (None, 99, 3), (None, 99, 16), (None, 3, 16),
                              (5, 99, 16), (50, 3, 16))]
    check(got == [1, 1, 1, 8, 3, 5, 3],
          f"--jobs: by default half the CPUs and at least 1, and never more than the parts: {got}")

    # An error of the run stops the parts that still run, with their children.
    def fail(name, *_):
        raise RuntimeError(name)

    start = time.monotonic()
    try:
        run_parts({"a": child("import time; time.sleep(0.5); print('1 cases, 0 wrong')"),
                   "b": child("import subprocess, sys, time; "
                              "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                              "time.sleep(30)")},
                  2, fail)
        raised = None
    except RuntimeError as e:
        raised = str(e)
    took = time.monotonic() - start
    check(raised == "a" and took < 10,
          f"an error of the run stops the other parts: raised {raised!r} after {took:.1f} s")

    # The output: without a log, every line; with one, every line to the log and only the BAD lines
    # and the summary to the terminal.
    two = {"a": passing(1), "b": child("import sys; print('ok   one'); print('BAD  two'); print('2 cases, 1 wrong'); "
                                       "sys.exit(1)")}
    out = io.StringIO()
    got = report(two, 2, None, out)
    check(got == 1 and out.getvalue() == "ok   a case\npart a: 1 cases, 0 wrong\nok   one\nBAD  two\n"
                                          "part b: 2 cases, 1 wrong\n\n3 cases, 1 wrong\n",
          f"without --log, every line: {got}, {out.getvalue()!r}")
    out, log = io.StringIO(), io.StringIO()
    got = report(two, 2, log, out)
    check(got == 1 and out.getvalue() == "BAD  two\n\n3 cases, 1 wrong\n"
          and log.getvalue() == "ok   a case\npart a: 1 cases, 0 wrong\nok   one\nBAD  two\npart b: 2 cases, 1 wrong\n"
                                "\n3 cases, 1 wrong\n",
          f"with --log, the BAD lines and the summary: {out.getvalue()!r}, and the log {log.getvalue()!r}")

    # The part table: every module with cases, each adapter, the groups of the probe and of doctor,
    # and the sweep; the probe's groups are those of hooks/probe.py.
    from . import cli

    names = list(parts(cli.modules()))
    spec = importlib.util.spec_from_file_location("harness_probe", PROBE)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    probe.FIXTURE.cleanup()
    probe.GROUPS |= {"x": lambda: (3, 1), "y": lambda: (4, 1)}
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = probe.cases(["x", "y"])
    check(code == 1 and out.getvalue() == "\n7 cases, 2 wrong\n",
          f"the probe adds up its groups and exits 1 with a wrong case: exit {code}, {out.getvalue()!r}")
    for name in ("x", "y"):
        del probe.GROUPS[name]
    check(tuple(probe.GROUPS) == PROBE_GROUPS, f"PROBE_GROUPS {PROBE_GROUPS} are the groups of hooks/probe.py, "
                                               f"{tuple(probe.GROUPS)}")
    check(names == sorted(names) and {"docs", "sweep", "testrun", "install", "claude", "opencode", "omp",
                                      "antigravity"} <= set(names)
          and {f"doctor:{g}" for g in doctor.GROUPS} | {f"probe:{g}" for g in PROBE_GROUPS} <= set(names)
          and not {"doctor", "probe"} & set(names),
          f"the parts, sorted, with the groups of the probe and of doctor and neither whole: {names}")
    for result, want in (((2, 1), 1), ((2, 0), 0)):
        fake = types.SimpleNamespace(__name__="harness.fake", selftest=lambda result=result: result)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cmd_test(argparse.Namespace(part="fake"), [fake])
        check(code == want and out.getvalue() == f"\n{result[0]} cases, {result[1]} wrong\n",
              f"the child of a part with {result} prints its summary and exits {want}: exit {code}, {out.getvalue()!r}")
    with contextlib.redirect_stdout(io.StringIO()):
        here = doctor.selftest(("minimum",))
    n, w, _ = run_part("doctor:minimum", parts(cli.modules())["doctor:minimum"])
    check((n, w) == here and n > 0, f"the part doctor:minimum runs that group alone: {(n, w)}, in this process {here}")
    p = subprocess.run([sys.executable, str(PROBE), "no-such-group"], capture_output=True, text=True, check=False,
                       timeout=60)
    check(p.returncode == 2 and "no-such-group" in p.stderr and "cases" not in p.stdout,
          f"hooks/probe.py no-such-group exits 2 and names it: exit {p.returncode}, {p.stderr.strip()!r}")

    # The owners of a path.
    for path, want in (
            ("lib/harness/profile.py", ["profile"]),
            ("lib/harness/profile.py.orig", []),
            ("lib/harness/fmt.py", []),
            ("lib/harness/doctor.py", sorted(f"doctor:{g}" for g in doctor.GROUPS)),
            ("hooks/rm-scope.py", sorted(f"probe:{g}" for g in PROBE_GROUPS)),
            ("adapters/omp/OMP-DELTA.md", ["omp", "probe:omp"]),
            ("adapters/antigravity/guard.py", ["antigravity", "probe:antigravity"]),
            ("adapters/omp/guards.ts", ["omp", "probe:omp"]),
            ("adapters/opencode/plugins/guards.ts", ["opencode", "probe:opencode"]),
            ("adapters/claude/adapter.py", ["claude"]),
            ("docs/src/dependencies.md", ["docs", "doctor:minimum"]),
            ("docs/src/development.md", ["docs"]),
            ("changelog.d/topic.md", ["changelog"]),
            ("lib/harness/cli.py", []),
            ("adapters/README.md", []),
            ("bin/harness", [])):
        check(owners(path, names) == want, f"{path} is owned by {want}: {owners(path, names)}")

    # --changed on a repository: a modified path selects its owner, a rename both paths' owners, a
    # path with no owner every part, and a base that git cannot resolve raises.
    with tempfile.TemporaryDirectory(prefix="harness-testrun-") as tmp:
        root = pathlib.Path(tmp)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}

        def git(*argv):
            subprocess.run(["git", *argv], cwd=root, env=env, check=True, capture_output=True)

        def changed_here(base):
            with mock.patch.dict(os.environ, env, clear=True):
                return changed(base, names, root)

        for path in ("adapters/omp/OMP-DELTA.md", "lib/harness/profile.py"):
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(f"{path}\n" * 20)
        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        git("switch", "-q", "-c", "rename")
        (root / "adapters" / "opencode").mkdir()
        git("mv", "adapters/omp/OMP-DELTA.md", "adapters/opencode/OMP-DELTA.md")
        git("commit", "-q", "-m", "rename")
        got, reasons = changed_here("main")
        check(got == ["docs", "omp", "opencode", "probe:omp", "probe:opencode", "sweep"] and len(reasons) == 2,
              f"a rename selects the owners of both paths: {got}, {reasons}")
        git("switch", "-q", "-c", "profile", "main")
        (root / "lib" / "harness" / "profile.py").write_text("changed\n")
        git("commit", "-q", "-am", "profile")
        got, reasons = changed_here("main")
        check(got == ["docs", "profile", "sweep"] and reasons == ["lib/harness/profile.py selects profile"],
              f"a modified module selects its part: {got}, {reasons}")
        (root / "unowned.txt").write_text("x\n")
        git("add", "unowned.txt")
        git("commit", "-q", "-m", "unowned")
        got, _ = changed_here("main")
        check(got == names, f"a path with no owner selects every part: {len(got)} of {len(names)}")
        # An empty base would read as HEAD...HEAD, and a base that starts with `-` as an option of git.
        for base in ("no-such-ref", "", "--output=x"):
            try:
                changed_here(base)
                raised = None
            except HarnessError as e:
                raised = str(e)
            check(raised is not None and base in raised and not list(root.glob("x*")),
                  f"the base {base!r} raises and writes no file: {raised!r}")

        # The slots: with both held, a run says once that it waits and holds a slot once one frees.
        slots = root / "slots"
        slots.mkdir()
        held = [open(slots / f"slot-{i}.lock", "a") for i in (1, 2)]
        for f in held:
            fcntl.flock(f, fcntl.LOCK_EX)
        said, taken = [], []
        waiter = threading.Thread(target=lambda: taken.append(take_slot(slots, said.append, poll=0.05)))
        waiter.start()
        time.sleep(0.5)
        waiting = waiter.is_alive() and not taken
        held[1].close()
        waiter.join(10)
        check(waiting and len(said) == 1 and "waits" in said[0] and len(taken) == 1
              and taken[0].name.endswith("slot-2.lock"),
              f"a third run waits while two hold the slots, says so once, and takes the slot that frees: "
              f"waited {waiting}, said {said}, took {[f.name for f in taken]}")
        for f in [held[0], *taken]:
            f.close()
        free = take_slot(slots, said.append)
        check(len(said) == 1, f"a free slot is taken with no wait: said {said}")
        free.close()

        # Two runs that hold a slot each make a third wait.
        said, taken = [], []
        runs = [take_slot(slots, said.append), take_slot(slots, said.append)]
        waiter = threading.Thread(target=lambda: taken.append(take_slot(slots, said.append, poll=0.05)))
        waiter.start()
        time.sleep(0.5)
        waiting = waiter.is_alive() and not taken
        runs[0].close()
        waiter.join(10)
        check(waiting and not said[1:] and len(taken) == 1
              and sorted(f.name for f in runs) == [str(slots / "slot-1.lock"), str(slots / "slot-2.lock")],
              f"two runs of take_slot hold the two slots and a third waits: waited {waiting}, "
              f"held {[f.name for f in runs]}, said {said}")
        for f in [runs[1], *taken]:
            f.close()

        # A slot directory that cannot be made is a usage error, before any part runs.
        (root / "a-file").write_text("x\n")
        p = subprocess.run([*HARNESS, "test", "docs"], capture_output=True, text=True, check=False, timeout=60,
                           env=os.environ | {"XDG_RUNTIME_DIR": str(root / "a-file")})
        check(p.returncode == 2 and "a-file" in p.stderr and "Traceback" not in p.stderr and "ok " not in p.stdout,
              f"a slot directory that cannot be made exits 2: exit {p.returncode}, {p.stderr.strip()[-200:]!r}")

        # A SIGTERM or a SIGHUP of the run stops the parts that still run, as an interrupt does.
        for signum in (signal.SIGTERM, signal.SIGHUP):
            pidfile = root / f"part-{signum}.pid"
            part = [sys.executable, "-c", f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); "
                                          "time.sleep(30)"]
            run = subprocess.Popen([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(REPO / 'lib')!r}); "
                                    f"from harness import testrun; testrun.run_parts({{'a': {part!r}}}, 1, "
                                    "lambda *_: None)"])
            deadline = time.monotonic() + 20
            while not (pidfile.exists() and pidfile.read_text()) and time.monotonic() < deadline:
                time.sleep(0.05)
            pid = int(pidfile.read_text() or 0) if pidfile.exists() else 0
            run.send_signal(signum)
            try:
                ended = run.wait(10)
            except subprocess.TimeoutExpired:
                run.kill()
                run.wait(5)
                ended = None
            deadline = time.monotonic() + 5
            alive = pid > 0
            while alive and time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                    time.sleep(0.05)
                except ProcessLookupError:
                    alive = False
            if alive:
                os.kill(pid, signal.SIGKILL)
            check(pid > 0 and not alive and ended == 128 + signum,
                  f"a {signal.Signals(signum).name} of the run stops its parts: part {pid} alive {alive}, "
                  f"the run exits {ended}")

        # The slot directory, and --list, which takes no slot.
        for variables, want in (({"XDG_RUNTIME_DIR": "/x", "TMPDIR": "/t"}, "/x"),
                                ({"XDG_RUNTIME_DIR": "", "TMPDIR": "/t"}, "/t"), ({}, "/tmp")):
            clean = {k: v for k, v in os.environ.items() if k not in ("XDG_RUNTIME_DIR", "TMPDIR")}
            with mock.patch.dict(os.environ, clean | variables, clear=True):
                got = slot_directory()
            check(got == pathlib.Path(want) / "research-harness-test", f"the slot directory with {variables}: {got}")
        runtime = root / "runtime"
        (runtime / "research-harness-test").mkdir(parents=True)
        held = [open(runtime / "research-harness-test" / f"slot-{i}.lock", "a") for i in (1, 2)]
        for f in held:
            fcntl.flock(f, fcntl.LOCK_EX)
        p = subprocess.run([*HARNESS, "test", "--list"], capture_output=True, text=True, check=False, timeout=30,
                           env=os.environ | {"XDG_RUNTIME_DIR": str(runtime)})
        check(p.returncode == 0 and "wait" not in p.stderr, f"--list takes no slot: exit {p.returncode}, {p.stderr!r}")
        for f in held:
            f.close()

    # The command line: a usage error exits 2 before any part runs.
    for argv, text in ((["no-such-part"], "no-such-part"), (["--jobs", "0", "docs"], "--jobs"),
                       (["--jobs", "-1", "docs"], "--jobs"), (["--changed", "HEAD", "docs"], "exclude"),
                       (["--log", str(REPO / "no-such-dir" / "x.log"), "docs"], "no-such-dir"),
                       (["--part", "no-such-part"], "no-such-part"), (["--part", "probe:drift"], "probe:drift"),
                       (["--changed", "", "--list"], "BASE is empty")):
        p = subprocess.run([*HARNESS, "test", *argv], capture_output=True, text=True, check=False, timeout=60)
        check(p.returncode == 2 and text in p.stderr and "Traceback" not in p.stderr and "ok " not in p.stdout,
              f"harness test {' '.join(argv)}: exit {p.returncode}, {p.stderr.strip()[-200:]!r}")
    p = subprocess.run([*HARNESS, "test", "--list", "profile"], capture_output=True, text=True, check=False, timeout=60)
    check(p.returncode == 0 and p.stdout.split() == ["docs", "profile", "sweep"],
          f"harness test --list profile prints docs, profile, sweep and runs nothing: exit {p.returncode}, "
          f"{p.stdout!r}")
    return total, wrong
