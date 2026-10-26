"""The cases of the Python environment of the harness: the start of `bin/harness`, which makes the
environment and runs each command on its interpreter, and the plan and the sync of
`harness install`.

Each case of the start runs `bin/harness` as a child process under a scratch HOME, with a fake
`uv` first on the PATH that logs its arguments, `UV_PROJECT_ENVIRONMENT` and `UV_PYTHON`, and
makes the environment with `python -m venv`. The child has no SANDBOX_RUNTIME, CLAUDECODE,
RESEARCH_HARNESS_PYTHON, RESEARCH_HARNESS_INTERPRETER or UV_PYTHON, except where a case sets one.
The cases of the marker that a start exports run `start` in this process. The cases
of the Linux download set the platform and the release URL through the variables that bin/harness
reads for the cases alone, and serve the release from a local `http.server`; the cases of a
download that succeeds load bin/harness in this process with a patched checksum, because no fake
archive has the pinned sha256.
"""

import ast
import contextlib
import gzip
import hashlib
import http.server
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tokenize
from unittest import mock

from . import REPO, install
from . import install_cases

HARNESS = REPO / "bin" / "harness"
# The variables of the caller that would point the child past its scratch HOME.
UNSET = ["SANDBOX_RUNTIME", "CLAUDECODE", "RESEARCH_HARNESS_PYTHON", "RESEARCH_HARNESS_INTERPRETER",
         "RESEARCH_HARNESS_RESTARTED", "RESEARCH_HARNESS_TEST_PLATFORM", "RESEARCH_HARNESS_TEST_UV_URL",
         "UV_PROJECT_ENVIRONMENT", "UV_PYTHON"]
# The system directories of the child's PATH, after the fake uv; they hold no uv.
SYSTEM_PATH = ["/usr/bin", "/bin"]
TIMEOUT = 60
# A command whose output shows that the restarted process kept its arguments: the profile's
# `harness`, `~/Research/Harness` below the scratch HOME.
GET = ["--profile", str(REPO / "examples" / "profile.toml"), "get", "harness"]
# The closed set of forms that bin/harness may use: the node types of `ast`, the token types and
# the operators that it uses, each of which Python 3.0 reads.
NODES = frozenset("Add And Assign Attribute AugAssign BinOp BoolOp Call ClassDef Compare Constant Dict Eq "
                  "ExceptHandler Expr For FunctionDef If IfExp Import ImportFrom Is List ListComp Load Lt Mod "
                  "Module Name Not NotEq Or Raise Return Slice Store Subscript Try Tuple USub UnaryOp With alias "
                  "arg arguments comprehension keyword withitem".split())
TOKENS = frozenset("NAME OP STRING NUMBER NEWLINE NL COMMENT INDENT DEDENT ENDMARKER".split())
OPERATORS = frozenset("!= % ( ) + += , - . : < = == [ ] { }".split())
NUMBER = re.compile(r"0|[1-9][0-9]*|0o[0-7]+")


class Box:
    """A scratch HOME, a directory with the fake uv, its log, and a TMPDIR for the child, below
    `root`."""

    def __init__(self, root, uv=True):
        root.mkdir(parents=True)
        self.root, self.home, self.bin, self.tmp = root, root / "home", root / "bin", root / "tmp"
        self.log = root / "uv.log"
        for d in (self.home, self.bin, self.tmp):
            d.mkdir()
        if uv:
            fake_uv(self.bin / "uv", self.log)
        self.env_dir = self.home / ".local" / "share" / "research-harness" / "python"

    def environ(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in UNSET}
        env.update(HOME=str(self.home), PATH=os.pathsep.join([str(self.bin), *SYSTEM_PATH]), TMPDIR=str(self.tmp),
                   NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
        env.update(extra)
        return env

    def run(self, argv=("--help",), python=None, timeout=TIMEOUT, **extra):
        """bin/harness with `argv` on `python`, this interpreter by default: (exit status, stdout,
        stderr lines, seconds); a run past `timeout` is the status None."""
        start = time.monotonic()
        try:
            p = subprocess.run([python or sys.executable, str(HARNESS), *argv], capture_output=True, text=True,
                               env=self.environ(**extra), cwd=self.root, timeout=timeout)
            code, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            code, out, err = None, "", "TIMEOUT"
        return code, out, err.splitlines(), time.monotonic() - start

    def uv_lines(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def below(self, *parts):
        """The paths below HOME/parts, sorted."""
        return sorted(str(p) for p in self.home.joinpath(*parts).rglob("*")) if self.home.joinpath(*parts).exists() \
            else []


def fake_uv(path, log):
    """A uv that appends `<arguments> | <UV_PROJECT_ENVIRONMENT> | <UV_PYTHON>` to `log` and, by
    $FAKE_UV, makes the environment anew (ok, the default), makes a venv in it and then exits 1
    after two stderr lines, as a real `uv sync --locked` that fails can (fail), or exits 0 and makes
    nothing (empty)."""
    path.write_text(f"""#!/bin/sh
echo "$* | ${{UV_PROJECT_ENVIRONMENT:-unset}} | ${{UV_PYTHON:-unset}}" >> '{log}'
case "${{FAKE_UV:-ok}}" in
ok) rm -rf "$UV_PROJECT_ENVIRONMENT" && exec '{sys.executable}' -m venv --without-pip "$UV_PROJECT_ENVIRONMENT" ;;
fail) '{sys.executable}' -m venv --without-pip "$UV_PROJECT_ENVIRONMENT"
  echo "first line" >&2; echo "the lock does not resolve" >&2; exit 1 ;;
empty) exit 0 ;;
esac
""")
    path.chmod(0o755)


def make_env(directory, log=None):
    """A Python environment at `directory`, made with `python -m venv`; with `log`, a .pth file in
    it appends `sys.orig_argv` of each interpreter that starts there to `log`."""
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(directory)], check=True, capture_output=True)
    if log is not None:
        purelib = subprocess.run([str(directory / "bin" / "python"), "-c",
                                  "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                 check=True, capture_output=True, text=True).stdout.strip()
        pathlib.Path(purelib, "harness-case.pth").write_text(
            f"import sys; open({str(log)!r}, 'a').write(repr(sys.orig_argv[1:]) + '\\n')\n")
    return directory


def started(log):
    """The arguments of each start that the .pth file of `make_env` logged, once each and without
    the start check `-c ''` of bin/harness; the site module can run a .pth file more than once."""
    lines = log.read_text().splitlines() if log.exists() else []
    return sorted(set(lines) - {repr(["-c", ""])})


def archive(machine, uv=True):
    """A gzipped tar in the form of a uv release for `machine`, with a uv that prints 'fake uv';
    without `uv`, it holds only the directory."""
    name = f"uv-{machine}-unknown-linux-gnu"
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tar:
        entries = [(f"{name}/uv", b"#!/bin/sh\necho fake uv\n")] if uv else [(f"{name}/README", b"x\n")]
        for member, body in entries:
            info = tarfile.TarInfo(member)
            info.size, info.mode = len(body), 0o755
            tar.addfile(info, io.BytesIO(body))
    # The gzip header holds no time, so that each call gives the same bytes and the same sha256.
    return gzip.compress(data.getvalue(), mtime=0)


class Release(http.server.BaseHTTPRequestHandler):
    """The local release server: /ok/<file> serves the archive of its machine, /missing/ is 404,
    /away/ redirects to localhost, /near/ to 127.0.0.1 once, /twice/ twice, /plain/ to 127.0.0.1
    over http, for a case that allows only https to 127.0.0.1. It records the path of each
    request."""

    requests = []

    def do_GET(self):
        Release.requests.append(self.path)
        port = self.server.server_address[1]
        kind, _, rest = self.path.lstrip("/").partition("/")
        if kind == "ok":
            machine = rest.removeprefix("uv-").partition("-unknown")[0]
            body = archive(machine, uv=machine != "nouv")
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        targets = {"away": f"http://localhost:{port}/ok/{rest}", "near": f"http://127.0.0.1:{port}/ok/{rest}",
                   "twice": f"http://127.0.0.1:{port}/near/{rest}",
                   "plain": f"http://127.0.0.1:{port}/ok/{rest}"}
        if kind in targets:
            self.send_response(302)
            self.send_header("Location", targets[kind])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_error(404)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def release_server():
    """The URL of a running local release server."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Release)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def outside_syntax(text):
    """Each form in `text` outside the closed set that bin/harness may use, as "<rule> at line N",
    or an empty list. The set holds the node types of NODES, the token types of TOKENS, the
    operators of OPERATORS, strings with no prefix and no \\N escape, the numbers of NUMBER and
    ASCII text, and three rules on shapes that the node types do not show: a `with` has one item,
    no `with` is followed by `(`, and the tuple of an `except` is in parentheses. Every other form
    is outside the set, also where Python 3.0 reads it. A text that the running Python does not
    parse gives only its syntax error."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [f"syntax error ({e.msg}) at line {e.lineno}"]
    found = set()
    lines = text.encode().splitlines()
    for n in ast.walk(tree):
        line = getattr(n, "lineno", 1)
        if type(n).__name__ not in NODES:
            found.add(f"node {type(n).__name__} at line {line}")
        if isinstance(n, ast.With) and len(n.items) != 1:
            found.add(f"with of {len(n.items)} items at line {line}")
        if isinstance(n, ast.ExceptHandler) and isinstance(n.type, ast.Tuple) \
                and lines[n.type.lineno - 1][n.type.col_offset:n.type.col_offset + 1] != b"(":
            found.add(f"unparenthesized except at line {line}")
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    types = {getattr(tokenize, name) for name in TOKENS}
    for t, after in zip(tokens, tokens[1:] + [None]):
        line = t.start[0]
        if t.type not in types:
            found.add(f"token {tokenize.tok_name[t.type]} at line {line}")
        if t.type == tokenize.OP and t.string not in OPERATORS:
            found.add(f"operator {t.string} at line {line}")
        if t.type == tokenize.STRING and t.string[0] not in "'\"":
            found.add(f"string prefix at line {line}")
        if t.type == tokenize.STRING and "\\N" in t.string:
            found.add(f"\\N escape at line {line}")
        if t.type == tokenize.NUMBER and not NUMBER.fullmatch(t.string):
            found.add(f"number at line {line}")
        if t.type == tokenize.NAME and t.string == "with" and after.type == tokenize.OP and after.string == "(":
            found.add(f"parenthesized with at line {line}")
    for number, line in enumerate(lines, 1):
        if not line.isascii():
            found.add(f"non-ASCII at line {number}")
    return sorted(found)


def syntax_cases(case, tmp):
    """The version check of bin/harness on an interpreter that reports 3.13, under a scratch HOME,
    and the syntax of the whole file, which Python 3.0 must read to reach the check."""
    run = ("import runpy, sys; sys.version_info = (3, 13, 9, 'final', 0); "
           "runpy.run_path(sys.argv[1], run_name='__main__')")
    b = Box(tmp / "syntax")
    p = subprocess.run([sys.executable, "-c", run, str(HARNESS), "--help"], capture_output=True, text=True,
                       timeout=TIMEOUT, env=b.environ(), cwd=b.root)
    lines = p.stderr.splitlines()
    case(lambda: p.returncode == 2 and lines == ["harness: Python 3.13 found, 3.14 or later needed"] and not p.stdout
         and not b.uv_lines() and b.below(".local") == [],
         f"an interpreter that reports 3.13 exits 2 with one line that names 3.13 and 3.14, and starts no uv: "
         f"{p.returncode}, {lines}, uv {b.uv_lines()}")
    found = outside_syntax(HARNESS.read_text())
    case(lambda: found == [], f"bin/harness uses only the closed set of Python 3.0 forms: {found}")
    for snippet, phrase in [("def f(:\n", "syntax error"),
                            ("def g():\n    yield from h()\n", "node YieldFrom"),
                            ("def g():\n    x = yield\n    return 2\n", "node Yield"),
                            ("def same[T](a, b):\n    pass\n", "node TypeVar"),
                            ("x = f'{y}'\n", "token FSTRING_START"),
                            ("def f(a, /):\n    pass\n", "operator /"),
                            ("@a.b[0]\ndef f():\n    pass\n", "operator @"),
                            ("def f(*a,):\n    pass\n", "operator *"),
                            ("f(**k, a=1)\n", "operator **"),
                            ("x = rb'x'\n", "string prefix"),
                            ("x = u'y'\n", "string prefix"),
                            ("x = 1_000\n", "number"),
                            ("with a as b, c as d:\n    pass\n", "with of 2 items"),
                            ("with (a as b):\n    pass\n", "parenthesized with"),
                            ("try:\n    pass\nexcept A, B:\n    pass\n", "unparenthesized except"),
                            ("\u00e9t\u00e9 = 1\n", "non-ASCII"),
                            ('x = "\\N{FACE WITH TEARS OF JOY}"\n', "\\N escape")]:
        found = outside_syntax(snippet)
        case(lambda: any(f.startswith(phrase + " ") for f in found),
             f"the syntax check refuses {snippet!r} with {phrase!r}: {found}")
    found = outside_syntax('class A(B):\n    w = 1\ntry:\n    with open(x) as f:\n        y = "%d" % n\n'
                           "except (A, B) as e:\n    z = 0o755\n")
    case(lambda: found == [], f"the syntax check accepts the forms that bin/harness uses: {found}")


def start_cases(case, tmp):
    """The start of bin/harness on macOS and in a session: each refusal, the sync, the restart and
    the marker."""
    n = 0

    def box(**options):
        nonlocal n
        n += 1
        return Box(tmp / f"start{n}", **options)

    def one_line(err, *words):
        return len(err) == 1 and all(w in err[0] for w in words)

    # A session with no environment: the command runs here, after one line; no uv, no environment.
    for variable in ("SANDBOX_RUNTIME", "CLAUDECODE"):
        b = box()
        code, out, err, _ = b.run(**{variable: "1"})
        case(lambda: code == 0 and "usage" in out and not b.uv_lines() and not b.env_dir.exists()
             and one_line(err, "harness install --apply", str(b.env_dir)),
             f"{variable}=1 with no environment runs the command, starts no uv, makes no environment and prints one "
             f"line that names the environment and harness install --apply: {code}, uv {b.uv_lines()}, {err}")

    # The marker set to this interpreter: no lookup, no uv, no line.
    b = box()
    code, out, err, _ = b.run(RESEARCH_HARNESS_INTERPRETER=sys.executable)
    case(lambda: code == 0 and "usage" in out and not b.uv_lines() and err == [] and not b.env_dir.exists(),
         f"the marker set to the running interpreter: no uv, no stderr: {code}, uv {b.uv_lines()}, {err}")
    b = box()
    link = b.root / "python-link"
    link.symlink_to(sys.executable)
    code, out, err, _ = b.run(RESEARCH_HARNESS_INTERPRETER=str(link))
    case(lambda: code == 0 and "usage" in out and not b.uv_lines() and err == [],
         f"the marker set to a link to the running interpreter names that interpreter: {code}, {err}")

    # A restarted process removes the variable of the restart, so that its children do not inherit it.
    boot = install.boot()
    with (mock.patch.dict(os.environ, {"RESEARCH_HARNESS_INTERPRETER": sys.executable,
                                       "RESEARCH_HARNESS_RESTARTED": "1"}),
          mock.patch.object(boot, "run", lambda: os.environ.get("RESEARCH_HARNESS_RESTARTED"))):
        left = boot.start([])
    case(lambda: left is None, f"a restarted process runs the command without RESEARCH_HARNESS_RESTARTED: {left!r}")

    # No environment, outside a session: one `uv sync --locked --no-dev` into the default path, then
    # the command runs on the new interpreter; a second run syncs no more and prints nothing.
    b = box()
    code, out, err, _ = b.run()
    lines = b.uv_lines()
    stamp = b.env_dir / install.boot().STAMP
    case(lambda: code == 0 and "usage" in out and len(lines) == 1
         and lines[0] == f"sync --locked --project {REPO} --no-dev | {b.env_dir} | 3.14"
         and (b.env_dir / "bin" / "python").is_file() and stamp.read_text() == install.boot().stamp_text(False),
         f"no environment: one uv sync --locked --no-dev into {b.env_dir} on Python 3.14, the stamp without the dev "
         f"group, then the command: {code}, uv {lines}, {err}")
    code, out, err, _ = b.run()
    case(lambda: code == 0 and "usage" in out and len(b.uv_lines()) == 1 and err == [],
         f"a working environment: no second sync, and no line: {code}, uv {b.uv_lines()}, {err}")
    # A caller's own UV_PYTHON wins over the floor's version.
    b = box()
    code, out, err, _ = b.run(UV_PYTHON="3.15")
    case(lambda: code == 0 and b.uv_lines() == [f"sync --locked --project {REPO} --no-dev | {b.env_dir} | 3.15"],
         f"UV_PYTHON=3.15 from the caller is the Python that uv is asked for: {code}, uv {b.uv_lines()}, {err}")

    # The restart keeps every argument: `--profile F get harness` after a sync prints the value.
    b = box()
    code, out, err, _ = b.run(GET)
    case(lambda: code == 0 and out.strip() == str(b.home / "Research" / "Harness") and len(b.uv_lines()) == 1,
         f"the restart after the sync keeps the arguments: {code}, {out.strip()!r}, {err}")

    # A working environment: the command restarts on its interpreter with the same arguments, in a
    # session too, and no uv runs.
    for extra in ({}, {"SANDBOX_RUNTIME": "1"}):
        b = box()
        seen = b.root / "seen.log"
        make_env(b.env_dir, seen)
        code, out, err, _ = b.run(GET, **extra)
        runs = started(seen)
        want = repr([str(HARNESS.resolve()), *GET])
        case(lambda: code == 0 and out.strip() == str(b.home / "Research" / "Harness") and runs == [want]
             and not b.uv_lines() and err == [],
             f"a working environment{', in a session' if extra else ''}: the command restarts on its interpreter "
             f"with the same arguments, and no uv runs: {code}, ran {runs}, {err}")

    # Started on the environment's interpreter: the command runs at once, with no start check of
    # the interpreter and no restart.
    b = box()
    seen = b.root / "seen.log"
    make_env(b.env_dir, seen)
    code, out, err, _ = b.run(GET, python=str(b.env_dir / "bin" / "python"))
    raw = seen.read_text().splitlines() if seen.exists() else []
    case(lambda: code == 0 and out.strip() == str(b.home / "Research" / "Harness") and repr(["-c", ""]) not in raw
         and started(seen) == [repr([str(HARNESS), *GET])] and err == [],
         f"started on the environment's interpreter: no start check and no restart: {code}, ran {raw}, {err}")

    # The marker set to another interpreter: one restart onto it, no lookup and no uv.
    b = box()
    seen = b.root / "seen.log"
    other = make_env(b.root / "other", seen)
    code, out, err, _ = b.run(GET, RESEARCH_HARNESS_INTERPRETER=str(other / "bin" / "python"))
    runs = started(seen)
    case(lambda: code == 0 and runs == [repr([str(HARNESS.resolve()), *GET])] and not b.uv_lines() and err == []
         and not b.env_dir.exists(),
         f"the marker set to another interpreter: one restart onto it, no uv, no environment: {code}, ran {runs}, "
         f"{err}")

    # $RESEARCH_HARNESS_PYTHON: an absolute path is the environment; a relative one exits 2.
    b = box()
    given = b.root / "given-env"
    code, out, err, _ = b.run(RESEARCH_HARNESS_PYTHON=str(given))
    case(lambda: code == 0 and b.uv_lines() == [f"sync --locked --project {REPO} --no-dev | {given} | 3.14"]
         and (given / "bin" / "python").is_file() and not b.env_dir.exists(),
         f"an absolute $RESEARCH_HARNESS_PYTHON is the environment: {code}, uv {b.uv_lines()}, {err}")
    b = box()
    code, out, err, _ = b.run(RESEARCH_HARNESS_PYTHON="rel/env")
    case(lambda: code == 2 and one_line(err, "rel/env", "absolute") and not b.uv_lines(),
         f"a relative $RESEARCH_HARNESS_PYTHON exits 2 with one line, and no uv runs: {code}, {err}")

    # A sync that fails: its last stderr line, exit 2, and the venv that it left is removed; one
    # that makes nothing: exit 2, once. A directory that was there before the sync stays.
    b = box()
    code, out, err, _ = b.run(FAKE_UV="fail")
    case(lambda: code == 2 and one_line(err, "the lock does not resolve") and "first line" not in err[0]
         and len(b.uv_lines()) == 1 and not b.env_dir.exists(),
         f"a uv sync that fails exits 2 with its last stderr line, and removes the environment that it made: {code}, "
         f"{err}, exists {b.env_dir.exists()}")
    b = box()
    b.env_dir.mkdir(parents=True)
    (b.env_dir / "keep").write_text("x\n")
    code, out, err, _ = b.run(FAKE_UV="fail")
    case(lambda: code == 2 and one_line(err, "the lock does not resolve") and (b.env_dir / "keep").is_file(),
         f"a uv sync that fails into a directory that was there keeps the directory: {code}, {err}, "
         f"{b.below('.local', 'share')}")
    b = box()
    code, out, err, seconds = b.run(FAKE_UV="empty", timeout=30)
    case(lambda: code == 2 and len(b.uv_lines()) == 1 and one_line(err, "no working environment"),
         f"a sync that makes no environment exits 2 after one sync, never a loop: {code} in {seconds:.1f} s, "
         f"uv {b.uv_lines()}, {err}")
    # A removal that fails after a failed sync: one Refusal that names both.
    b = box()
    boot = install.boot()
    failing = mock.Mock(rmtree=mock.Mock(side_effect=OSError(13, "Permission denied")))
    with (mock.patch.dict(os.environ, b.environ(FAKE_UV="fail"), clear=True),
          mock.patch.object(boot, "shutil", failing)):
        try:
            boot.sync(str(b.bin / "uv"), str(b.env_dir), False)
            refused = None
        except boot.Refusal as e:
            refused = str(e)
    case(lambda: refused is not None and "the lock does not resolve" in refused and "cannot remove" in refused
         and str(b.env_dir) in refused and failing.rmtree.call_count == 1,
         f"a failed removal of the environment of a failed sync is part of its one Refusal: {refused!r}")

    # The marker that a process exports to its children: the environment's interpreter when it
    # runs there, and the current interpreter in the session fallback, after one line.
    boot = install.boot()
    clean = {k: v for k, v in os.environ.items() if k not in UNSET}
    with (mock.patch.dict(os.environ, clean, clear=True), mock.patch.object(boot, "interpreter",
                                                                             lambda environment: sys.executable),
          mock.patch.object(boot, "run", lambda: os.environ.get(boot.MARKER))):
        exported = boot.start([])
    case(lambda: exported == sys.executable,
         f"a process on the environment's interpreter exports it as the marker: {exported!r}")
    stderr = io.StringIO()
    with (mock.patch.dict(os.environ, {**clean, "SANDBOX_RUNTIME": "1", "RESEARCH_HARNESS_PYTHON":
                                       str(tmp / "no-such-env")}, clear=True),
          mock.patch.object(boot, "run", lambda: os.environ.get(boot.MARKER)), contextlib.redirect_stderr(stderr)):
        exported = boot.start([])
    case(lambda: exported == os.path.abspath(sys.executable) and len(stderr.getvalue().splitlines()) == 1,
         f"the session fallback exports the current interpreter as the marker, after one line: {exported!r}, "
         f"{stderr.getvalue().splitlines()}")

    # An environment whose bin/python starts another interpreter: the restart lands elsewhere, and
    # the restarted process exits 2 instead of restarting again.
    b = box()
    (b.env_dir / "bin").mkdir(parents=True)
    wrapper = b.env_dir / "bin" / "python"
    wrapper.write_text(f"#!/bin/sh\nexec '{sys.executable}' \"$@\"\n")
    wrapper.chmod(0o755)
    code, out, err, seconds = b.run(timeout=30)
    case(lambda: code == 2 and one_line(err, "started again on") and not b.uv_lines(),
         f"a restart that lands on another interpreter exits 2, never a loop: {code} in {seconds:.1f} s, {err}")

    # An environment whose interpreter does not start counts as none: the start syncs it again.
    b = box()
    (b.env_dir / "bin").mkdir(parents=True)
    broken = b.env_dir / "bin" / "python"
    broken.write_text("#!/bin/sh\nexit 1\n")
    broken.chmod(0o755)
    code, out, err, _ = b.run()
    case(lambda: code == 0 and "usage" in out and len(b.uv_lines()) == 1,
         f"an environment whose interpreter does not start is synced again: {code}, uv {b.uv_lines()}, {err}")

    # No uv: macOS names brew, another system names uv; nothing is written.
    for system, words in (("Darwin arm64", ("brew install uv",)),
                          ("FreeBSD amd64", ("no uv on the PATH: install uv",))):
        b = box(uv=False)
        code, out, err, _ = b.run(RESEARCH_HARNESS_TEST_PLATFORM=system)
        case(lambda: code == 2 and one_line(err, *words) and b.below(".local") == [],
             f"{system} with no uv exits 2 with one line that names {words[0]}, and writes nothing below ~/.local: "
             f"{code}, {err}, {b.below('.local')}")

    # A uv in ~/.local/bin, where the bootstrap fetches it, serves when the PATH has none.
    b = box(uv=False)
    (b.home / ".local" / "bin").mkdir(parents=True)
    fake_uv(b.home / ".local" / "bin" / "uv", b.log)
    code, out, err, _ = b.run(RESEARCH_HARNESS_TEST_PLATFORM="Linux x86_64",
                              RESEARCH_HARNESS_TEST_UV_URL="http://127.0.0.1:9/missing")
    case(lambda: code == 0 and len(b.uv_lines()) == 1,
         f"a uv in ~/.local/bin syncs the environment, and nothing is fetched: {code}, uv {b.uv_lines()}, {err}")


def download_cases(case, tmp):
    """The Linux download of the pinned uv: each refusal in a child process, then the download
    that succeeds, in this process with a patched checksum."""
    n = 0

    def box():
        nonlocal n
        n += 1
        return Box(tmp / f"download{n}", uv=False)

    with release_server() as url:
        for machine, kind, words, label in [
            ("riscv64", "ok", ("riscv64",), "an architecture with no pinned release"),
            ("x86_64", "missing", ("cannot download", "404"), "a download that fails"),
            ("x86_64", "ok", ("sha256", "removed"), "a checksum that is not the pinned one"),
            ("aarch64", "ok", ("sha256", "removed"), "a checksum that is not the pinned one, aarch64"),
            ("x86_64", "away", ("redirects to http://localhost:",), "a redirect to another host"),
        ]:
            b = box()
            Release.requests.clear()
            code, out, err, _ = b.run(RESEARCH_HARNESS_TEST_PLATFORM=f"Linux {machine}",
                                      RESEARCH_HARNESS_TEST_UV_URL=f"{url}/{kind}")
            asked = list(Release.requests)
            case(lambda: code == 2 and len(err) == 1 and all(w in err[0] for w in words) and b.below(".local") == []
                 and list(b.tmp.iterdir()) == [] and (asked == [] if machine == "riscv64" else asked != []),
                 f"Linux, {label}: exit 2 with one line, nothing below ~/.local and no file left in TMPDIR: {code}, "
                 f"{err}, {b.below('.local')}, {sorted(p.name for p in b.tmp.iterdir())}, requests {asked}")

        boot = install.boot()
        good = hashlib.sha256(archive("x86_64")).hexdigest()
        environ = {"RESEARCH_HARNESS_TEST_PLATFORM": "Linux x86_64", "NO_PROXY": "127.0.0.1,localhost",
                   "no_proxy": "127.0.0.1,localhost"}
        for kind, redirect, want, label in [
            ("ok", boot.REDIRECT, "installed", "the archive with the pinned sha256"),
            ("near", ("http", "127.0.0.1"), "installed", "one redirect to the allowed host"),
            ("twice", ("http", "127.0.0.1"), "redirects to", "a second redirect"),
            ("near", boot.REDIRECT, "redirects to", "a redirect to a host that is not the allowed one"),
            ("plain", ("https", "127.0.0.1"), "redirects to", "a redirect to the allowed host over http"),
        ]:
            b = box()
            patches = {**environ, "RESEARCH_HARNESS_TEST_UV_URL": f"{url}/{kind}"}
            with (mock.patch.dict(os.environ, patches), mock.patch.object(boot, "UV_SHA256", {"x86_64": good}),
                  mock.patch.object(boot, "REDIRECT", redirect)):
                try:
                    path, got = boot.fetch_uv(str(b.home)), "installed"
                except boot.Refusal as e:
                    path, got = None, str(e)
            uv = b.home / ".local" / "bin" / "uv"
            ok = want in got and (uv.is_file() and os.access(uv, os.X_OK) and path == str(uv)
                                  and uv.read_bytes() == b"#!/bin/sh\necho fake uv\n"
                                  and b.below(".local", "bin") == [str(uv)] if want == "installed"
                                  else b.below(".local") == [])
            case(lambda: ok, f"in this process, {label}: {want} -> {got}, {b.below('.local')}")

        b = box()
        bare = hashlib.sha256(archive("nouv", uv=False)).hexdigest()
        with (mock.patch.dict(os.environ, {**environ, "RESEARCH_HARNESS_TEST_PLATFORM": "Linux nouv",
                                           "RESEARCH_HARNESS_TEST_UV_URL": f"{url}/ok"}),
              mock.patch.object(boot, "UV_SHA256", {"nouv": bare})):
            try:
                boot.fetch_uv(str(b.home))
                got = "installed"
            except boot.Refusal as e:
                got = str(e)
        case(lambda: "cannot read uv-nouv-unknown-linux-gnu/uv" in got and b.below(".local") == [],
             f"in this process, an archive with no uv: a refusal, and nothing below ~/.local -> {got}")

        # The start fetches the checked uv, whose sync makes nothing: the start refuses, and the
        # fetched uv stays in ~/.local/bin for the next start. A restart would replace this process,
        # so it raises here instead.
        b = box()
        env = {k: v for k, v in b.environ().items() if k not in (boot.MARKER, boot.RESTARTED)}
        env.update(environ, RESEARCH_HARNESS_TEST_UV_URL=f"{url}/ok")

        def no_restart(python, argv):
            raise boot.Refusal(f"a restart onto {python}")

        with (mock.patch.dict(os.environ, env, clear=True), mock.patch.object(boot, "UV_SHA256", {"x86_64": good}),
              mock.patch.object(boot, "restart", no_restart)):
            try:
                boot.start(["--help"])
                got = "ran"
            except boot.Refusal as e:
                got = str(e)
        uv = b.home / ".local" / "bin" / "uv"
        case(lambda: "no working environment" in got and uv.is_file() and os.access(uv, os.X_OK)
             and uv.read_bytes() == b"#!/bin/sh\necho fake uv\n" and not b.env_dir.exists(),
             f"in this process, a fetched uv whose sync makes nothing: a refusal, the uv stays in ~/.local/bin, and "
             f"no environment -> {got}, {b.below('.local')}")


def install_cases_of(case, tmp):
    """`harness install` on a scratch HOME with the fake uv: the plan line, the sync with and
    without the dev group, an interpreter that does not start, a sync that fails, no uv, and a
    `develop` that is not a boolean."""
    scratch = install_cases.Scratch(lambda ok, label: None, tmp / "install")
    stubs = tmp / "install-uv"
    stubs.mkdir()
    log = tmp / "install-uv.log"
    fake_uv(stubs / "uv", log)
    path = os.pathsep.join([str(stubs), os.environ.get("PATH", "")])

    def uv_lines():
        lines = log.read_text().splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return lines

    def plan_line(text):
        return [line for line in text.splitlines() if line.startswith("python environment")]

    # A synced environment is no change; an empty one is one SYNC line, and the dry run starts no uv.
    base, _, _ = scratch.fresh()
    code, text = scratch.run(base, extra_env={"PATH": path})
    case(lambda: len(plan_line(text)) == 1 and plan_line(text)[0].endswith("already synced") and not uv_lines(),
         f"a synced environment: one line, already synced: {code}, {plan_line(text)}")
    for develop, flag in ((None, True), ("false", True), ("true", False)):
        base, _, _ = scratch.fresh()
        if develop is not None:
            (base / "profile.toml").write_text((base / "profile.toml").read_text() + f"develop = {develop}\n")
        env_dir = base / "fresh-env"
        extra = {"PATH": path, "RESEARCH_HARNESS_PYTHON": str(env_dir)}
        code, text = scratch.run(base, extra_env=extra)
        lines = plan_line(text)
        case(lambda: code == 1 and len(lines) == 1 and " SYNC: no interpreter that starts" in lines[0]
             and not uv_lines(),
             f"develop {develop}: the dry run plans one SYNC line and starts no uv: {code}, {lines}")
        code, text = scratch.run(base, "--apply", extra_env=extra)
        got = uv_lines()
        # The install's environment is the caller's, whose UV_PYTHON wins over the floor's version.
        want = (f"sync --locked --project {REPO}{' --no-dev' if flag else ''} | {env_dir} | "
                f"{os.environ.get('UV_PYTHON') or '3.14'}")
        stamp = env_dir / install.boot().STAMP
        case(lambda: code == 0 and got == [want] and stamp.read_text() == install.boot().stamp_text(not flag),
             f"develop {develop}: --apply runs `{want}` and stamps the group: {code}, {got}, {scratch.tail(text)!r}")
        code, text = scratch.run(base, extra_env=extra)
        case(lambda: plan_line(text)[0].endswith("already synced") and not uv_lines(),
             f"develop {develop}: the dry run after --apply plans no sync: {plan_line(text)}")
        if develop is None:
            (base / "profile.toml").write_text((base / "profile.toml").read_text() + "develop = true\n")
            code, text = scratch.run(base, extra_env=extra)
            case(lambda: code == 1 and "SYNC: it was not synced with this uv.lock with the dev group"
                 in plan_line(text)[0], f"develop turned on: the dry run plans a sync: {code}, {plan_line(text)}")

    # An interpreter that does not start is a change, and --apply makes it anew.
    base, _, _ = scratch.fresh()
    python = base / "python" / "bin" / "python"
    python.unlink()
    python.write_text("#!/bin/sh\nexit 1\n")
    python.chmod(0o755)
    code, text = scratch.run(base, extra_env={"PATH": path})
    case(lambda: code == 1 and "SYNC: no interpreter that starts" in plan_line(text)[0],
         f"an interpreter that does not start is planned as a sync: {code}, {plan_line(text)}")
    code, text = scratch.run(base, "--apply", extra_env={"PATH": path})
    case(lambda: code == 0 and len(uv_lines()) == 1 and subprocess.run([str(python), "-c", ""]).returncode == 0,
         f"--apply makes an environment whose interpreter starts: {code}, {scratch.tail(text)!r}")

    # A sync that fails exits 2 with its last stderr line; no uv exits 2.
    base, _, _ = scratch.fresh()
    extra = {"PATH": path, "RESEARCH_HARNESS_PYTHON": str(base / "fresh-env"), "FAKE_UV": "fail"}
    code, text = scratch.run(base, "--apply", extra_env=extra)
    case(lambda: scratch.refused(code, text)
         and scratch.tail(text).endswith("uv sync exits 1: the lock does not resolve")
         and not (base / "fresh-env").exists(),
         f"a uv sync that fails exits 2 with its last stderr line, and removes the environment that it made: {code}, "
         f"{scratch.tail(text)!r}")
    uv_lines()
    tools = tmp / "install-no-uv"
    tools.mkdir()
    for tool in install_cases.NO_JULIA_TOOLS:
        (tools / tool).symlink_to(shutil.which(tool))
    code, text = scratch.run(base, "--apply", extra_env={"PATH": str(tools),
                                                         "RESEARCH_HARNESS_PYTHON": str(base / "fresh-env")})
    case(lambda: scratch.refused(code, text) and "uv is not found" in scratch.tail(text),
         f"no uv: --apply exits 2 and names uv: {code}, {scratch.tail(text)!r}")

    # A relative $RESEARCH_HARNESS_PYTHON and a `develop` that is not a boolean exit 2.
    code, text = scratch.run(base, extra_env={"PATH": path, "RESEARCH_HARNESS_PYTHON": "rel/env"})
    case(lambda: scratch.refused(code, text) and "rel/env" in scratch.tail(text),
         f"a relative $RESEARCH_HARNESS_PYTHON exits 2: {code}, {scratch.tail(text)!r}")
    for value in ('"yes"', "1", "[]"):
        base, _, _ = scratch.fresh()
        (base / "profile.toml").write_text((base / "profile.toml").read_text() + f"develop = {value}\n")
        for argv in (["install"], ["get", "home"]):
            p = subprocess.run([sys.executable, str(HARNESS), "--profile", str(base / "profile.toml"),
                                "--models", str(REPO / "examples" / "models.toml"), *argv],
                               capture_output=True, text=True, env=scratch.env(base), cwd=base, timeout=TIMEOUT)
            case(lambda: p.returncode == 2 and "`develop`" in p.stderr and "not true or false" in p.stderr
                 and "Traceback" not in p.stderr,
                 f"develop = {value}: harness {argv[0]} exits 2 and names the key: {p.returncode}, "
                 f"{p.stderr.strip()[-200:]!r}")


def prepush_cases(case, tmp):
    """The Python of `.githooks/pre-push`, for a push of a branch: a `python3` that reports 3.13
    and no `python3.14` refuse the push with one line; a `python3` of 3.14 passes, and the hook
    goes on to the next step, which refuses a checkout with no `origin`. The PATH holds the tools
    that the hook runs up to there, and the `python3`."""
    repo, tools = tmp / "pre-push-repo", tmp / "pre-push-tools"
    tools.mkdir()
    for tool in ("git", "bash", "mktemp", "rm"):
        (tools / tool).symlink_to(shutil.which(tool))
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="case",
               GIT_AUTHOR_EMAIL="case@example.org", GIT_COMMITTER_NAME="case", GIT_COMMITTER_EMAIL="case@example.org")
    for args in (["init", "-q", "-b", "main", str(repo)],
                 ["-C", str(repo), "commit", "-q", "--allow-empty", "-m", "c"]):
        subprocess.run(["git", *args], check=True, capture_output=True, env=env)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
                         env=env).stdout.strip()
    for version, want in (("(3, 13, 9, 'final', 0)", "pre-push: refused, no python3 of 3.14 or later"),
                          (None, "pre-push: refused, the checkout has no origin remote")):
        patch = "" if version is None else f"sys.version_info = {version}; "
        python = tools / "python3"
        python.unlink(missing_ok=True)
        python.write_text(f"#!/bin/sh\n[ \"$1\" = -c ] && exec '{sys.executable}' -c \"import sys; {patch}"
                          f"exec(sys.argv[1])\" \"$2\"\nexec '{sys.executable}' \"$@\"\n")
        python.chmod(0o755)
        p = subprocess.run([str(REPO / ".githooks" / "pre-push"), "origin", "https://example.org/x.git"],
                           input=f"refs/heads/topic {sha} refs/heads/topic {'0' * 40}\n", cwd=repo, capture_output=True,
                           text=True, env={**env, "PATH": str(tools), "TMPDIR": str(tmp)}, timeout=TIMEOUT)
        lines = p.stdout.strip().splitlines()
        case(lambda: p.returncode == 1 and lines == [want],
             f"pre-push with a python3 that reports {version or 'its own version'}: {want!r} -> {p.returncode}, "
             f"{lines}")


def selftest():
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  environment: {label}")

    def case(ok, label):
        try:
            ok = ok()
        except Exception as e:  # a case that crashes is BAD, and the next case still runs
            ok, label = False, f"{label}; raised {type(e).__name__}: {e}"
        check(ok, label)

    case(lambda: all(shutil.which("uv", path=d) is None for d in SYSTEM_PATH),
         f"no uv in {', '.join(SYSTEM_PATH)}, the system part of the cases' PATH")
    with tempfile.TemporaryDirectory(prefix="harness-environment-") as tmp:
        tmp = pathlib.Path(tmp)
        syntax_cases(case, tmp)
        start_cases(case, tmp)
        download_cases(case, tmp)
        install_cases_of(case, tmp)
        prepush_cases(case, tmp)
    return total, wrong
