#!/usr/bin/env python3
"""Create and remove a Claude Code worktree at `~/Research/.worktrees/<Repository>-<slug>`.

One script for two hook events, told apart by `hook_event_name`:

  * **`WorktreeCreate`** — input `{"cwd": …, "name": …}`. Fetches `origin`, then runs
    `git worktree add --no-track -b <name> <path> origin/<default>` in the repository that
    owns `cwd`, and prints `<path>` on stdout. That one line is the whole of stdout; git's
    own output goes to stderr. An existing branch is checked out rather than recreated,
    and a path that is already a worktree of this repository is printed as it is.
    A name `agent-<hex>` is a sub-agent's `isolation: "worktree"`: that worktree is
    detached at the base and gets no branch, so nothing is left behind but the worktree.
    The agent makes its own branch with `git switch -c`. Either way the main checkout's
    gitignored `Manifest.toml` is copied in, so the pre-commit load test can run, when it
    holds every dependency of the worktree's `Project.toml` inside its `[compat]`.
  * **`WorktreeRemove`** — input `{"worktree_path": …}`. Runs `git worktree remove <path>`
    from the owning repository. Without `--force`, so git refuses a worktree with changes.
    The branch stays: it may carry an open pull request.

Why a hook: Claude Code runs a `git worktree add` whose path is absolute, starts with `~`
or holds `..` inside the sandbox, whatever `excludedCommands` says, and the sandbox
denies every write under `.git`. Every spelling of a path under `~/Research/.worktrees/`
is one of those.

**The repository is found by reading files, before any git runs** (`main_checkout`): the
directory must lie below `~/Research`, and the first `.git` above it must be a directory, or
the `.git` file of a linked worktree whose admin directory holds the `commondir` and `gitdir`
that git writes. git then runs only in that main checkout, and every git gets
`-c core.hooksPath=/dev/null -c core.fsmonitor=false` (`run_git`), so that no hook and no
fsmonitor daemon of the repository runs.

**Under `agentbox` a broker does the git work.** srt denies writes to every `.githooks`, so a
`git worktree add` inside it fails. With `AGENTBOX` in the environment, the hook runs no git:
it sends its payload as one JSON line to the socket that `AGENTBOX_BROKER` names, and reads one
JSON line back, `{"path": …, "stderr": …}` or `{"error": …, "stderr": …}`. `agentbox` starts
the broker outside srt, as this script:

    worktree.py --serve <socket> --parent <pid>

It binds `<socket>` with mode 600, replacing a stale socket and refusing any other file there,
serves one connection at a time, runs each create or remove as this script in a process of its
own, without `AGENTBOX` and with `GIT_TERMINAL_PROMPT=0`, and answers a request that is larger
than 64 KiB, no JSON object, or of another `hook_event_name` with an `error`. An idle broker
exits and removes its socket within 5 seconds after its parent ends. When the parent ends during
a request, the broker does not stop the request: it reads the request (at most `LOCAL`, 60 s),
runs the create or remove to its end or to `WORK` (400 s), then looks at its parent and exits
without taking another connection. SIGTERM and SIGHUP still end it at once.

A worktree made with `--relative-paths`, or in a repository or git config with
`worktree.useRelativePaths=true`, is refused, even one this hook made itself: `main_checkout`
accepts only the absolute paths that git writes by default.

**It fails closed.** Every error exits 1 with the reason on stderr, and Claude Code then
reports the hook as failed. No worktree is better than one in the wrong place or on the
wrong base. Under `AGENTBOX`, no `AGENTBOX_BROKER`, a broker that does not answer and a reply
with an `error` each fail so.

Test the parts that need no repository:

    echo '{"hook_event_name":"WorktreeCreate","cwd":"/","name":"x"}' | ./worktree.py ; echo "exit $?"
"""

import contextlib
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

from guard import HarnessError
from guard.jsonio import JsonValue, loads

ROOT = Path.home() / "Research" / ".worktrees"
# The tree whose repositories this hook makes worktrees of.
RESEARCH = ROOT.parent
SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
AGENT = re.compile(r"^agent-[0-9a-f]+$")
# Seconds that a local git command may take, and a fetch, which reaches the network.
LOCAL = 60
NETWORK = 300
# The options of every git: no hook of the repository runs, and no fsmonitor daemon starts.
OPTIONS = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")
# The variable that names the broker's socket, the events it serves, and the largest request in
# bytes.
BROKER = "AGENTBOX_BROKER"
EVENTS = ("WorktreeCreate", "WorktreeRemove")
LIMIT = 64 * 1024
# Seconds that the broker gives one create or remove, which may fetch, and that the client waits
# for the reply; seconds between two looks of the broker at its parent.
WORK = 400
ANSWER = 420
LOOK = 1


class Refusal(Exception):
    pass


@dataclass(frozen=True)
class Request:
    """A request to the broker: its `hook_event_name`, one of EVENTS, and its payload as JSON text."""

    event: str
    text: str


@dataclass(frozen=True)
class Reply:
    """The broker's answer to one request: the path that a create printed, empty for a remove, or
    the reason why the request failed; and the stderr of the create or remove."""

    path: str = ""
    error: str | None = None
    stderr: str = ""

    def line(self) -> bytes:
        """The reply as one JSON line, `{"path": …, "stderr": …}` or `{"error": …, "stderr": …}`."""
        head = {"path": self.path} if self.error is None else {"error": self.error}
        return (json.dumps({**head, "stderr": self.stderr}) + "\n").encode()


def run_git(*args: str, cwd: Path, timeout: int = LOCAL) -> subprocess.CompletedProcess[str]:
    """git with OPTIONS and `args` in `cwd`: the one place where this hook starts git."""
    return subprocess.run(
        ["git", *OPTIONS, *args],  # noqa: S607 -- the `git` on PATH
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def git(*args: str, cwd: Path, timeout: int = LOCAL) -> str:
    proc = run_git(*args, cwd=cwd, timeout=timeout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise Refusal(f"`git {' '.join(args)}` in {cwd} exited {proc.returncode}")
    return proc.stdout.strip()


def main_checkout(start: str, research: Path) -> Path:
    """The main checkout of the repository that holds `start`, also from a linked worktree, found
    by reading files: `start` must be an existing directory below `research`, and the first `.git`
    from it up to `research`, `research` left out, must be a directory, which makes its parent the
    main checkout, or a file that `linked_checkout` accepts. A `.git` that is a symbolic link, or
    neither a directory nor a file, is refused."""
    top = research.resolve()
    if "\0" in start:
        raise Refusal(f"{start!r} holds a NUL byte, which no path holds")
    here = Path(start).resolve() if start else None
    if here is None or not here.is_dir():
        raise Refusal(f"{start!r} is not a directory")
    if here == top or not here.is_relative_to(top):
        raise Refusal(f"{start} is not below {top}; this hook makes worktrees of the repositories there only")
    for directory in (here, *here.parents):
        if directory == top:
            break
        dot = directory / ".git"
        if dot.is_symlink():
            raise Refusal(f"{dot} is a symbolic link; this hook follows none")
        if dot.is_dir():
            return directory
        if dot.is_file():
            return linked_checkout(dot, top)
        if dot.exists():
            raise Refusal(f"{dot} is neither a directory nor a file")
    raise Refusal(f"{start} is inside no repository below {top}; `cd` into the repository first")


def linked_checkout(dot: Path, top: Path) -> Path:
    """The main checkout `<X>` of the linked worktree whose `.git` file is `dot`: its one line must
    be `gitdir: <X>/.git/worktrees/<name>`, with `<X>` below `top` and `<X>/.git` a directory that
    is not a link, and that admin directory must hold `commondir` `../..` and `gitdir` `dot`, as
    git writes them."""
    line = one_line(dot)
    admin = Path(line.removeprefix("gitdir: "))
    if (
        not line.startswith("gitdir: ")
        or not admin.is_absolute()
        or ".." in admin.parts
        or admin.parent.name != "worktrees"
        or admin.parent.parent.name != ".git"
    ):
        raise Refusal(f"{dot} holds {line!r}, not `gitdir: <repository>/.git/worktrees/<name>`")
    repo = admin.parent.parent.parent.resolve()
    common = repo / ".git"
    if repo == top or not repo.is_relative_to(top):
        raise Refusal(f"{dot} names the repository {repo}, which is not below {top}")
    if common.is_symlink() or not common.is_dir():
        raise Refusal(f"{common}, which {dot} names, is not a directory")
    admin = common / "worktrees" / admin.name
    if one_line(admin / "commondir") != "../..":
        raise Refusal(f"{admin / 'commondir'} does not hold `../..`, as git writes it")
    if one_line(admin / "gitdir") != str(dot):
        raise Refusal(f"{admin / 'gitdir'} does not name {dot}")
    return repo


def one_line(path: Path) -> str:
    """The text of the file `path` with its trailing newline cut; refused where it cannot be read
    or holds more than one line."""
    try:
        text = path.read_text(encoding="utf-8").removesuffix("\n")
    except (OSError, UnicodeDecodeError) as err:
        raise Refusal(f"{path} cannot be read: {err}") from None
    if "\n" in text:
        raise Refusal(f"{path} holds more than one line")
    return text


def slug(name):
    segments = name.split("/")
    if not name or any(s in ("", ".", "..") or not SEGMENT.match(s) for s in segments):
        raise Refusal(
            f"worktree name {name!r}: each `/`-separated segment must be letters, digits, `.`, `_` or `-`"
        )
    return "-".join(segments)


def registered(repo, path):
    listing = git("worktree", "list", "--porcelain", cwd=repo)
    return f"worktree {path}" in listing.splitlines()


def base_ref(repo: Path) -> str:
    head = run_git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", cwd=repo)
    if head.returncode == 0:
        return head.stdout.strip()
    if run_git("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main", cwd=repo).returncode == 0:
        return "origin/main"
    raise Refusal(
        f"{repo} has neither `origin/HEAD` nor `origin/main`; run `git remote set-head origin --auto` there"
    )


def create(payload: dict[str, JsonValue]) -> Path:
    cwd, name = payload.get("cwd", ""), payload.get("name", "")
    if not isinstance(cwd, str) or not isinstance(name, str):
        raise Refusal(f"the hook input's cwd {cwd!r} or name {name!r} is not a string")
    repo = main_checkout(cwd, RESEARCH)
    path = ROOT / f"{repo.name}-{slug(name)}"

    if path.is_symlink():
        raise Refusal(f"{path} is a symbolic link; a worktree path must be a new directory")
    if path.exists():
        if registered(repo, path):
            return path
        raise Refusal(f"{path} exists and is not a worktree of {repo}; look at it before removing it")

    git("fetch", "--quiet", "origin", cwd=repo, timeout=NETWORK)
    if AGENT.match(name):
        git("worktree", "add", "--detach", str(path), base_ref(repo), cwd=repo)
        copy_manifest(repo, path)
        return path
    if run_git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}", cwd=repo).returncode == 0:
        git("worktree", "add", str(path), name, cwd=repo)
    else:
        git("worktree", "add", "--no-track", "-b", name, str(path), base_ref(repo), cwd=repo)
    copy_manifest(repo, path)
    return path


def copy_manifest(repo, path):
    """Copy the main checkout's `Manifest.toml` into a worktree that has none, when it fits.

    The manifest is gitignored, so a new worktree has none, and the pre-commit load test
    `julia --project=. -e "using <Package>"` then fails with "is required but does not seem
    to be installed". The main checkout's copy names packages already in the depot, so no
    resolve and no network is needed.

    Julia does not check `[compat]` at `using`, so a manifest that a main checkout behind
    `origin` resolved loads old dependency versions, and the load test fails on a later
    commit as if the source were broken. So the copy is made only when `manifest_fits` says
    the manifest fits the worktree's `Project.toml`; else stderr says why, and the worktree
    gets no manifest.
    """
    source, target = repo / "Manifest.toml", path / "Manifest.toml"
    if not source.is_file() or target.exists():
        return
    try:
        import tomllib  # Python 3.11; an older `python3` makes the worktree with no manifest
    except ImportError:
        sys.stderr.write("worktree hook: no Manifest.toml copied: this Python has no tomllib\n")
        return
    try:
        with open(path / "Project.toml", "rb") as f:
            project = tomllib.load(f)
        with open(source, "rb") as f:
            manifest = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as err:
        sys.stderr.write(f"worktree hook: no Manifest.toml copied: {err}\n")
        return
    why = manifest_fits(project, manifest)
    if why:
        sys.stderr.write(
            f"worktree hook: no Manifest.toml copied, because {why}; "
            "run `Pkg.instantiate()` in the worktree\n"
        )
        return
    shutil.copy2(source, target)


def manifest_fits(project, manifest):
    """None when `manifest` fits `project`, else the reason it does not.

    It fits when it is of format 2, holds every package of the project's `[deps]`, and the
    version of each lies inside that package's `[compat]` entry. A package with no version, a
    standard library, has nothing to compare. The test reads the names and the versions, not
    Pkg's `project_hash`: Pkg computes that hash with an internal function whose input changes
    between Pkg versions, so a hash computed here would disagree with a manifest that fits.
    """
    if not str(manifest.get("manifest_format", "")).startswith("2."):
        return "the manifest is not of format 2"
    entries = manifest.get("deps", {})
    compat = project.get("compat", {})
    for name in sorted(project.get("deps", {})):
        if name not in entries:
            return f"the manifest has no entry for {name}"
        version = entries[name][0].get("version") if entries[name] else None
        if version is None or name not in compat:
            continue
        ranges = compat_ranges(compat[name])
        if ranges is None:
            return f"the [compat] entry {name} = {compat[name]!r} is not one this hook reads"
        v = parse_version(version.split("-")[0].split("+")[0])
        if v is None or not any(lo <= v < hi for lo, hi in ranges):
            return f"the manifest holds {name} {version}, outside [compat] {name} = {compat[name]!r}"
    return None


INFINITY = (float("inf"),) * 3


def parse_version(text):
    """`1`, `1.2` or `1.2.3` as a tuple of one to three integers, or None."""
    parts = text.strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def pad(v):
    return v + (0,) * (3 - len(v))


def bump(v, depth):
    """The version after every version that agrees with `v` in its first `depth` parts."""
    v = pad(v)
    return v[: depth - 1] + (v[depth - 1] + 1,) + (0,) * (3 - depth)


def compat_ranges(spec):
    """The `[compat]` entry `spec` as half-open version ranges [lo, hi), as Pkg reads it, or None.

    Caret (the default) and tilde specifiers, `=`, `>=`/`≥`, `<`, and hyphen ranges, separated by
    commas, which make a union."""
    ranges = []
    for term in str(spec).split(","):
        term = term.strip()
        if " - " in term:
            a, b = (parse_version(x) for x in term.split(" - ", 1))
            if a is None or b is None:
                return None
            ranges.append((pad(a), bump(b, len(b))))
            continue
        m = re.fullmatch(r"(\^|~|=|>=|≥|<)?\s*(.+)", term)
        if m is None:
            return None
        op, v = m.group(1) or "^", parse_version(m.group(2))
        if v is None:
            return None
        n = len(v)
        if op == "^":
            depth = 1 if v[0] != 0 or n == 1 else 2 if v[1] != 0 or n == 2 else 3
            ranges.append((pad(v), bump(v, depth)))
        elif op == "~":
            depth = 1 if n == 1 else 3 if n == 3 and v[0] == v[1] == 0 else 2
            ranges.append((pad(v), bump(v, depth)))
        elif op == "=":
            ranges.append((pad(v), bump(v, n)))
        elif op in (">=", "≥"):
            ranges.append((pad(v), INFINITY))
        else:
            ranges.append(((0, 0, 0), pad(v)))
    return ranges


def remove(payload):
    path = Path(payload.get("worktree_path", "")).resolve()
    if path.parent != ROOT.resolve():
        raise Refusal(f"{path} is not directly under {ROOT}; this hook removes only the worktrees it creates")
    repo = main_checkout(str(path), RESEARCH)
    if not registered(repo, path):
        raise Refusal(f"{path} is not a registered worktree of {repo}")
    git("worktree", "remove", str(path), cwd=repo)


def ask(payload: dict[str, JsonValue], *, created: bool) -> None:
    """Send `payload` to the broker at AGENTBOX_BROKER, write the reply's `stderr` to stderr, and
    print its `path` where `created` says that the payload is a create; refused where the variable
    is unset or empty, the broker does not answer within ANSWER seconds, or the reply is no `Reply`
    (`read_reply`) or holds an `error`."""
    address = os.environ.get(BROKER, "")
    if not address:
        raise Refusal(
            f"AGENTBOX is set and {BROKER} is not: agentbox started no worktree broker, "
            "and this hook runs no git inside the sandbox"
        )
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(ANSWER)
            connection.connect(address)
            connection.sendall((json.dumps(payload) + "\n").encode())
            connection.shutdown(socket.SHUT_WR)
            data = receive(connection, None)
    except OSError as err:
        raise Refusal(f"the worktree broker at {address} does not answer: {err}") from None
    reply = read_reply(data, f"the reply of the worktree broker at {address}")
    sys.stderr.write(reply.stderr)
    if reply.error is not None:
        raise Refusal(f"the worktree broker at {address}: {reply.error}")
    if created:
        if not reply.path:
            raise Refusal(f"the worktree broker at {address} replied no path")
        print(reply.path)


def read_reply(data: bytes, where: str) -> Reply:
    """The `Reply` in the JSON line `data`, which `where` names; refused where it is no JSON object,
    or its `path` or `stderr` is no string, or it holds an `error` that is no string."""
    value = loads(data.decode("utf-8", "replace"), where=where)
    path, error, stderr = value.get("path", ""), value.get("error"), value.get("stderr", "")
    if not isinstance(path, str) or not isinstance(stderr, str):
        raise Refusal(f"{where} holds a path or a stderr that is no string")
    if "error" in value and not isinstance(error, str):
        raise Refusal(f"{where} holds an error that is no string")
    return Reply(path, error if isinstance(error, str) else None, stderr)


def receive(connection: socket.socket, limit: int | None) -> bytes:
    """The bytes from `connection` up to its first newline or its end; where `limit` is given, it
    reads at most `limit` + 1 bytes, and returns them all when no newline comes before them."""
    data = b""
    while b"\n" not in data and (limit is None or len(data) <= limit):
        chunk = connection.recv(65536 if limit is None else limit + 1 - len(data))
        if not chunk:
            break
        data += chunk
    return data.split(b"\n", 1)[0]


def serve(path: Path, parent: int) -> None:
    """The broker: bind `path` with mode 600, replacing a stale socket and refusing any other file
    there, and answer each connection in turn (`answer`) while `parent` is this process's parent;
    then remove the socket. SIGTERM and SIGHUP end it the same way."""
    if os.getppid() != parent:
        raise Refusal(f"the parent of the broker is {os.getppid()}, not {parent}")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        mode = None
    if mode is not None:
        if not stat.S_ISSOCK(mode):
            raise Refusal(f"{path} exists and is not a socket; the broker replaces only a stale socket")
        path.unlink()
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, ended)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        old = os.umask(0o177)
        try:
            listener.bind(str(path))
        except OSError as err:
            raise Refusal(f"the broker cannot bind {path}: {err}") from None
        finally:
            os.umask(old)
        try:
            path.chmod(0o600)
            listener.listen()
            listener.settimeout(LOOK)
            while os.getppid() == parent:
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    answer(connection)
        finally:
            path.unlink(missing_ok=True)


def ended(signum: int, frame: FrameType | None) -> None:
    """The SIGTERM and SIGHUP handler of the broker: exit through the cleanup of `serve`."""
    del signum, frame
    sys.exit(0)


def answer(connection: socket.socket) -> None:
    """Read one request from `connection` and send `respond`'s answer as one JSON line. A client that
    leaves or stalls past LOCAL seconds takes its reply with it; the broker serves the next."""
    connection.settimeout(LOCAL)
    try:
        data = receive(connection, LIMIT)
    except OSError:
        return
    reply = respond(data)
    with contextlib.suppress(OSError):
        connection.sendall(reply.line())


def read_request(data: bytes) -> Request:
    """The `Request` in `data`; refused where `data` is larger than LIMIT, no UTF-8 or no JSON
    object, or its `hook_event_name` is not one of EVENTS."""
    if len(data) > LIMIT:
        raise Refusal(f"the request is larger than {LIMIT} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as err:
        raise Refusal(f"the request is no UTF-8: {err}") from None
    payload = loads(text, where="the request")
    event = payload.get("hook_event_name")
    if not isinstance(event, str) or event not in EVENTS:
        raise Refusal(f"unexpected hook_event_name {event!r}")
    return Request(event, json.dumps(payload))


def respond(data: bytes) -> Reply:
    """The answer to the request `data` (`read_request`): the path and stderr of this script run on
    it without AGENTBOX and AGENTBOX_BROKER, and with GIT_TERMINAL_PROMPT=0, so that a fetch never
    prompts on the frontend's terminal; or an error, also where that process cannot start."""
    try:
        request = read_request(data)
    except (Refusal, HarnessError) as err:
        return Reply(error=str(err))
    env = {k: v for k, v in os.environ.items() if k not in ("AGENTBOX", BROKER)} | {
        "GIT_TERMINAL_PROMPT": "0"
    }
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).absolute())],
            input=request.text,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=WORK,
        )
    except subprocess.TimeoutExpired:
        return Reply(error=f"the {request.event} took more than {WORK} s")
    except OSError as err:
        return Reply(error=f"the {request.event} cannot start {sys.executable}: {err}")
    if proc.returncode != 0:
        return Reply(error=f"the {request.event} exited {proc.returncode}", stderr=proc.stderr)
    return Reply(path=proc.stdout.strip(), stderr=proc.stderr)


def serve_arguments(args: Sequence[str]) -> tuple[Path, int]:
    """The socket and the parent's process ID of `--serve <socket> --parent <pid>`."""
    if len(args) != 4 or args[0] != "--serve" or args[2] != "--parent" or not args[3].isdigit():
        raise Refusal("usage: worktree.py [--serve <socket> --parent <pid>]")
    return Path(args[1]), int(args[3])


def main(args: Sequence[str] = ()) -> int:
    try:
        if args:
            serve(*serve_arguments(args))
            return 0
        payload = loads(sys.stdin.read(), where="hook input")
        event = payload.get("hook_event_name")
        if "AGENTBOX" in os.environ:
            ask(payload, created=event == "WorktreeCreate")
        elif event == "WorktreeCreate":
            print(create(payload))
        elif event == "WorktreeRemove":
            remove(payload)
        else:
            raise Refusal(f"unexpected hook_event_name {event!r}")
    except (Refusal, HarnessError) as err:
        sys.stderr.write(f"worktree hook: {err}\n")
        return 1
    except subprocess.TimeoutExpired as err:
        sys.stderr.write(f"worktree hook: `{' '.join(map(str, err.cmd))}` took more than {err.timeout} s\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
