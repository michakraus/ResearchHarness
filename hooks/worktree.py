#!/usr/bin/env python3
"""Create and remove a worktree of Claude Code, and through `harness worktree` of OpenCode and
oh-my-pi, at `~/Research/.worktrees/<Repository>-<slug>`.

One script for two hook events, told apart by `hook_event_name`:

  * **`WorktreeCreate`** — input `{"cwd": …, "name": …}`. Fetches `origin`, up to three times
    where a parallel fetch of the repository holds a ref's lock (`fetch`), then runs
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
    The branch stays: it may carry an open pull request. First it refuses where it cannot write
    in a `.githooks` or `.claude` of the worktree (`deletable`), as inside a sandbox: git would
    delete the files up to the first one there, then the worktree's record, and leave the rest.

Why a hook: Claude Code runs a `git worktree add` whose path is absolute, starts with `~`
or holds `..` inside the sandbox, whatever `excludedCommands` says, and the sandbox
denies every write under `.git`. Every spelling of a path under `~/Research/.worktrees/`
is one of those.

**The repository is found by reading files, before any git runs** (`main_checkout`): the
directory must lie below `~/Research`, and the first `.git` above it must be a directory, or
the `.git` file of a linked worktree whose admin directory holds the `commondir` and `gitdir`
that git writes, and the main checkout's `.git` must hold no `commondir`. git then runs only in
that main checkout, and every git gets `-c core.hooksPath=/dev/null -c core.fsmonitor=false`
and `GIT_ALLOW_PROTOCOL=https:ssh` (`run_git`), so that no hook and no fsmonitor daemon of the
repository runs, and no transport but https and ssh. Every git also gets `GIT_DIR` set to that
checkout's `.git` and none of the caller's `GIT_WORK_TREE` and `GIT_COMMON_DIR`, so that git
uses the repository that was checked and does not search for one itself.

**Its git config is checked before any other git** (`checked_config`): a program inside a
sandbox can rename a directory of its own into place as `.git`, with a `config` that it chose,
and a key there can run a command for the git outside it. A create runs the check after the
test of the worktree path, a remove before it asks git for the worktrees; a key outside the
fixed list of `allowed`, or a remote URL that `remote_url` refuses, refuses the repository.

**Under `agentbox` a broker does the git work.** srt denies writes to every `.githooks`, so a
`git worktree add` inside it fails. With `AGENTBOX` in the environment, the hook runs no git:
it sends its payload as one JSON line to the socket that `AGENTBOX_BROKER` names, and reads one
JSON line back, `{"path": …, "stderr": …}` or `{"error": …, "stderr": …}`. `agentbox` starts
the broker outside srt, as this script:

    worktree.py --serve <socket> --parent <pid> --settings <file>

`<file>` is the srt settings file of the frontend. The broker reads it, a JSON object whose
`filesystem.allowWrite` is a list of strings, makes its staging directory `STAGES/<pid>` with mode
700, replacing a stale directory and refusing a link or any other file there, and writes the
profile `STAGES/<pid>.json` with mode 600: `<file>` with the staging directory appended to
`filesystem.allowWrite`. It binds `<socket>` with mode 600, replacing a stale socket and refusing
any other file there, serves one connection at a time, runs each create or remove as this script
in a process of its own, `worktree.py --boxed <profile>`, without `AGENTBOX` and with
`GIT_TERMINAL_PROMPT=0`, and answers a request that is larger than 64 KiB, no JSON object, or of
another `hook_event_name` with an `error`. An idle broker exits and removes its socket, its
profile and its staging directory, the last only where it is empty, within 5 seconds after its
parent ends. When the parent ends during a request, the broker does not stop the request: it reads
the request (at most `LOCAL`, 60 s), runs the create or remove to its end or to `WORK` (400 s),
then looks at its parent and exits without taking another connection. SIGTERM and SIGHUP still end
it at once.

**A boxed child runs every git inside srt**, as `SRT --settings <profile> -- git …`, the config
check included: a program in the box can swap the `.git` that the check read for another before
git reads it, so a git outside srt would run a config that the box chose with the host's rights.
srt denies the box's writes to `.githooks`, so a boxed create adds the worktree in the staging
directory, which must lie on the device of ROOT, renames it to ROOT without git, runs `git worktree
repair` and checks that the repaired `.git` file names the repository (`staged_add`). It makes a
new branch in a step of its own, `git branch --no-track <name> <base>`, before `git worktree add`;
a failed step, the add included, removes what the child made, runs `git worktree prune`, and
deletes with `git branch -D` a branch that the create made. A boxed remove renames the worktree
into the staging directory, repairs and removes it there, and renames it back where git refuses
or cannot start (`staged_remove`). Without `--boxed` git runs as `git …`, outside srt.

Every git, and the srt of a boxed git, starts in a session of its own (`run_git`). One that
outlives its timeout is stopped with its process group, which holds the programs that it started,
such as the git inside srt or the ssh of a fetch: SIGTERM, then SIGKILL where it has not ended
after GRACE seconds. A SIGINT, SIGTERM or SIGHUP of the hook stops the group of its running git
the same way (`main`), since a signal to the hook's own group does not reach that session.

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
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

from guard import HarnessError
from guard.jsonio import JsonValue, load, loads

ROOT = Path.home() / "Research" / ".worktrees"
# The tree whose repositories this hook makes worktrees of.
RESEARCH = ROOT.parent
SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
AGENT = re.compile(r"^agent-[0-9a-f]+$")
# Seconds that a local git command may take, and a fetch, which reaches the network.
LOCAL = 60
NETWORK = 300
# Seconds between the SIGTERM and the SIGKILL to the process group of a git past its timeout.
GRACE = 5
# The runs of a fetch that another fetch of the same repository can make fail with git's LOCKED,
# and the seconds between two runs.
FETCHES = 3
LOCKED = "cannot lock ref"
PAUSE = 2
# The directories of a worktree that a sandbox denies writes in: srt and Claude Code's sandbox deny
# every `.githooks`, and Claude Code's sandbox every `.claude` below the session's folders.
SHIELDED = frozenset({".githooks", ".claude"})
# The options of every git: no hook of the repository runs, and no fsmonitor daemon starts.
OPTIONS = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")
# The transports that every git may use, in GIT_ALLOW_PROTOCOL, in place of the caller's value.
PROTOCOLS = "https:ssh"
# The variables of the caller that no git of this hook gets: each would name another work tree or
# another common directory, whose config git would read, beside the GIT_DIR that `run_git` sets.
UNSET = frozenset({"GIT_WORK_TREE", "GIT_COMMON_DIR"})
# The keys of a repository's `.git/config` that `checked_config` allows, lowercased: the keys
# without a subsection, and the names of the keys of each `branch.<n>` and `remote.<n>`. A key
# whose name is in URL_KEYS holds a URL that `remote_url` accepts; every other allowed key holds
# any value.
PLAIN_KEYS = frozenset(
    {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.ignorecase",
        "core.precomposeunicode",
        "core.hookspath",
        "pull.rebase",
        "lfs.repositoryformatversion",
        "user.name",
        "user.email",
    }
)
SECTION_KEYS = {
    "branch": frozenset(
        {
            "remote",
            "merge",
            "pushremote",
            "vscode-merge-base",
            "github-pr-owner-number",
            "github-pr-base-branch",
        }
    ),
    "remote": frozenset({"url", "pushurl", "fetch", "glab-resolved-head"}),
}
URL_KEYS = frozenset({"url", "pushurl"})
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
# The srt that a boxed child runs every git in, `~/.local/bin/srt`, as `agentbox` runs the frontend
# in it; and the directory of the brokers' staging directories,
# `~/.local/state/research-harness/worktree-stage`, one `<pid>` per broker with its profile
# `<pid>.json` beside it, below `~/.local/state/research-harness`, which no box may write.
SRT = Path.home() / ".local" / "bin" / "srt"
STAGES = Path.home() / ".local" / "state" / "research-harness" / "worktree-stage"


# What a caller whose working directory is in no repository does instead. Claude Desktop sends the
# session's folder as `cwd`, and refuses a `cwd` in a repository that it has no record of, so a side
# session of such a session starts without a worktree and makes its own.
NO_REPOSITORY = (
    "`cd` into the repository first, or start a side session with use_worktree false and its cwd "
    "in the repository, whose first step is EnterWorktree"
)


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


def run_git(
    *args: str, repo: Path, cwd: Path | None = None, timeout: int = LOCAL, profile: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """git with OPTIONS and `args` in `cwd`, by default `repo`, with GIT_DIR set to `repo`'s `.git`,
    GIT_ALLOW_PROTOCOL set to PROTOCOLS, and no GIT_WORK_TREE or GIT_COMMON_DIR of the caller: the one
    place where this hook starts git. GIT_DIR pins git to the repository that `main_checkout` and
    `checked_config` read, so that git does not search for one itself: a `.git` that git does not
    take as a repository would make it walk up to a parent's, and a directory with a HEAD, `objects`
    and `refs` would make it take that directory as a bare repository. With a `profile`, the boxed
    child's, git runs as `SRT --settings <profile> -- git …`, inside srt, with the same `cwd`,
    environment and timeout. git, or the srt of a boxed git, starts in a session of its own: where
    it outlives `timeout`, `stop_group` stops its process group, the programs that it started
    included, and the subprocess.TimeoutExpired of the git command is raised. Any other exception
    that ends the wait, such as the KeyboardInterrupt of a SIGINT or the SystemExit of
    `interrupted`, stops the group the same way and passes on. A program that cannot start is a
    Refusal that names it."""
    env = {key: value for key, value in os.environ.items() if key not in UNSET}
    boxed = [str(SRT), "--settings", str(profile), "--"] if profile is not None else []
    command = [*boxed, "git", *OPTIONS, *args]
    try:
        proc = subprocess.Popen(
            command,
            cwd=repo if cwd is None else cwd,
            env={**env, "GIT_DIR": str(repo / ".git"), "GIT_ALLOW_PROTOCOL": PROTOCOLS},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=True,
        )
    except OSError as err:
        raise Refusal(f"{command[0]} cannot start: {err}") from None
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_group(proc)
        raise
    except BaseException:
        stop_group(proc)
        raise
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def stop_group(proc: subprocess.Popen[str]) -> None:
    """Stop the process group of `proc`, a git or the srt of a boxed git, which holds every program
    that it started: SIGTERM, so that git removes its lock files, then SIGKILL where `proc` has not
    ended after GRACE seconds. A group that is gone raises ProcessLookupError, and on macOS a group
    that holds only the unreaped `proc` raises PermissionError; neither has a program left to stop."""
    for signum in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signum)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.communicate(timeout=GRACE)
            return


def git(*args: str, repo: Path, timeout: int = LOCAL, profile: Path | None = None) -> str:
    proc = run_git(*args, repo=repo, timeout=timeout, profile=profile)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise Refusal(f"`git {' '.join(args)}` in {repo} exited {proc.returncode}")
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
    if here == top:
        raise Refusal(f"{start} is the root of the tree, no repository; {NO_REPOSITORY}")
    if not here.is_relative_to(top):
        raise Refusal(f"{start} is not below {top}; this hook makes worktrees of the repositories there only")
    for directory in (here, *here.parents):
        if directory == top:
            break
        dot = directory / ".git"
        if dot.is_symlink():
            raise Refusal(f"{dot} is a symbolic link; this hook follows none")
        if dot.is_dir():
            return without_commondir(directory)
        if dot.is_file():
            return without_commondir(linked_checkout(dot, top))
        if dot.exists():
            raise Refusal(f"{dot} is neither a directory nor a file")
    raise Refusal(f"{start} is inside no repository below {top}; {NO_REPOSITORY}")


def without_commondir(repo: Path) -> Path:
    """`repo`, refused where its `.git` holds a `commondir`: git would then read the config of the
    directory that it names, which `checked_config` does not read."""
    common = repo / ".git" / "commondir"
    if common.is_symlink() or common.exists():
        raise Refusal(f"{common} exists; git would read the config of the commondir that it names")
    return repo


def checked_config(repo: Path, profile: Path | None = None) -> None:
    """Refuse `repo` where its `.git/config`, read by `git config --no-includes`, holds a key that
    `allowed` refuses, or cannot be read: git outside the sandbox reads that file, and a key there
    can run a command (`core.sshCommand`, a filter, a URL rewrite) or pull in another file. A boxed
    child reads it under srt with its `profile`, as every other git of it."""
    config = repo / ".git" / "config"
    proc = run_git(
        "config",
        "--file",
        str(config),
        "--no-includes",
        "--null",
        "--list",
        repo=repo,
        cwd=Path("/"),
        profile=profile,
    )
    if proc.returncode != 0:
        raise Refusal(
            f"`git config --file {config} --list` exited {proc.returncode}: {' '.join(proc.stderr.split())}"
        )
    for entry in proc.stdout.split("\0"):
        if not entry:
            continue
        key, newline, value = entry.partition("\n")
        if not allowed(key.lower(), value if newline else None):
            raise Refusal(f"{config} holds {key.lower()}, which this hook does not allow")


def allowed(key: str, value: str | None) -> bool:
    """Whether `checked_config` allows the lowercased `key` with `value`, None for a key with no
    value: a key of PLAIN_KEYS, or `<section>.<subsection>.<name>`, split at the first and the last
    dot, with `name` in SECTION_KEYS of `section`; a URL key's value must pass `remote_url`."""
    if key in PLAIN_KEYS:
        return True
    section, _, rest = key.partition(".")
    subsection, _, name = rest.rpartition(".")
    if not subsection or name not in SECTION_KEYS.get(section, frozenset()):
        return False
    return name not in URL_KEYS or (value is not None and remote_url(value))


def remote_url(value: str) -> bool:
    """Whether `value` is an `https://` or `ssh://` URL, or scp-like `<host>:<path>`: a `:` with no
    `/` before it, no `::` (a remote helper's form), no `://` (another scheme) and no leading `-`."""
    if value.startswith(("https://", "ssh://")):
        return True
    host, colon, _ = value.partition(":")
    return (
        bool(colon)
        and "/" not in host
        and "::" not in value
        and "://" not in value
        and not value.startswith("-")
    )


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


def slug(name: str) -> str:
    segments = name.split("/")
    if not name or any(s in ("", ".", "..") or not SEGMENT.fullmatch(s) for s in segments):
        raise Refusal(
            f"worktree name {name!r}: each `/`-separated segment must be letters, digits, `.`, `_` or `-`"
        )
    return "-".join(segments)


def registered(repo: Path, path: Path, profile: Path | None = None) -> bool:
    listing = git("worktree", "list", "--porcelain", repo=repo, profile=profile)
    return f"worktree {path}" in listing.splitlines()


def base_ref(repo: Path, profile: Path | None = None) -> str:
    head = run_git(
        "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", repo=repo, profile=profile
    )
    if head.returncode == 0:
        return head.stdout.strip()
    main = run_git("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main", repo=repo, profile=profile)
    if main.returncode == 0:
        return "origin/main"
    raise Refusal(
        f"{repo} has neither `origin/HEAD` nor `origin/main`; run `git remote set-head origin --auto` there"
    )


def create(payload: dict[str, JsonValue], profile: Path | None = None) -> Path:
    """The worktree of the payload's `name` for the repository of its `cwd`, made at ROOT; with the
    `profile` of a boxed child, every git runs under srt and the worktree is made in the staging
    directory and moved to ROOT (`staged_add`)."""
    cwd, name = payload.get("cwd", ""), payload.get("name", "")
    if not isinstance(cwd, str) or not isinstance(name, str):
        raise Refusal(f"the hook input's cwd {cwd!r} or name {name!r} is not a string")
    repo = main_checkout(cwd, RESEARCH)
    path = ROOT / f"{repo.name}-{slug(name)}"

    if path.is_symlink():
        raise Refusal(f"{path} is a symbolic link; a worktree path must be a new directory")
    checked_config(repo, profile)
    if path.exists():
        if registered(repo, path, profile):
            return path
        raise Refusal(f"{path} exists and is not a worktree of {repo}; look at it before removing it")

    fetch(repo, profile)
    if profile is None:
        git(*add_arguments(repo, name, path, None), repo=repo)
    else:
        staged_add(repo, name, path, profile)
    copy_manifest(repo, path)
    return path


def fetch(repo: Path, profile: Path | None = None) -> None:
    """`git fetch --quiet origin` in `repo`, run up to FETCHES times while it fails only because
    another fetch of the repository holds a ref's lock (`cannot lock ref`), PAUSE seconds apart; the
    stderr of the last run passes through. Any other failure, and the last of FETCHES, refuses."""
    for attempt in range(1, FETCHES + 1):
        proc = run_git("fetch", "--quiet", "origin", repo=repo, timeout=NETWORK, profile=profile)
        if proc.returncode == 0 or LOCKED not in proc.stderr or attempt == FETCHES:
            sys.stderr.write(proc.stderr)
            if proc.returncode != 0:
                raise Refusal(f"`git fetch --quiet origin` in {repo} exited {proc.returncode}")
            return
        time.sleep(PAUSE)


def add_arguments(repo: Path, name: str, target: Path, profile: Path | None) -> list[str]:
    """The `git worktree add` that makes the worktree `name` at `target`: detached at the base for
    a sub-agent's `agent-<hex>`, the existing branch `name`, or a new branch `name` from the base,
    with no upstream."""
    if AGENT.fullmatch(name):
        return ["worktree", "add", "--detach", str(target), base_ref(repo, profile)]
    branch = run_git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}", repo=repo, profile=profile)
    if branch.returncode == 0:
        return ["worktree", "add", str(target), name]
    return ["worktree", "add", "--no-track", "-b", name, str(target), base_ref(repo, profile)]


def same_device(a: Path, b: Path, stat: Callable[[Path], os.stat_result] = os.stat) -> bool:
    """Whether `a` and `b` lie on one device, so that `os.rename` moves one into the other."""
    return stat(a).st_dev == stat(b).st_dev


def stage_of(profile: Path) -> Path:
    """The staging directory of the boxed child whose profile is `profile`: `<pid>` beside
    `<pid>.json`, refused where it is a link or no directory, where ROOT is a link or no directory,
    or where the two lie on different devices. ROOT is made where it is missing, `~/Research`
    itself not; `mkdir` with `exist_ok` refuses a ROOT that exists and is no directory."""
    stage = profile.with_suffix("")
    if stage.is_symlink() or not stage.is_dir():
        raise Refusal(f"the staging directory {stage} is a symbolic link or no directory")
    if ROOT.is_symlink():
        raise Refusal(f"{ROOT} is a symbolic link; the worktrees' root must be a directory")
    try:
        ROOT.mkdir(exist_ok=True)
    except OSError as err:
        raise Refusal(f"{ROOT} is no directory and cannot be made one: {err}") from None
    if not same_device(stage, ROOT):
        raise Refusal(
            f"the staging directory {stage} and {ROOT} lie on different devices; a worktree is moved, "
            "never copied, between them"
        )
    return stage


def plain_directory(path: Path) -> bool:
    """Whether `path` is a directory and no symbolic link."""
    return not path.is_symlink() and path.is_dir()


def move(source: Path, target: Path) -> None:
    """Rename the directory `source` to `target`, which must not exist; refused where `source` is
    a link or no directory, where `target` exists or is a link, and where the rename fails. On
    macOS a rename replaces an empty directory that appears at `target` after the test, and fails
    on any other entry there."""
    if not plain_directory(source):
        raise Refusal(f"{source} is a symbolic link or no directory")
    if target.exists(follow_symlinks=False):
        raise Refusal(f"{target} exists; a worktree is moved only to a new path")
    try:
        source.rename(target)
    except OSError as err:
        raise Refusal(f"{source} cannot be renamed to {target}: {err}") from None


def moved(target: Path) -> None:
    """Refuse a `target` of `move` that is a symbolic link or no directory after the rename."""
    if not plain_directory(target):
        raise Refusal(f"{target} is a symbolic link or no directory after the rename")


def discard(path: Path) -> None:
    """Remove `path`, a directory that this child made: a link there is unlinked, never followed."""
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def staged_add(repo: Path, name: str, final: Path, profile: Path) -> None:
    """Make the worktree `name` at `final` through the staging directory of `profile`: `git worktree
    add` there under srt, a rename to `final` without git, `git worktree repair` under srt, and a
    test that the repaired `.git` file names `repo`. A new branch `name` is made in a step of its
    own before the add, `git branch --no-track <name> <base>` under srt, since git keeps the branch
    of a `git worktree add -b` that fails. A failed step removes what this child made, the staged
    directory or, after its rename, `final`, and nothing that it found, runs `git worktree prune`
    under srt, deletes the branch `name` where this child's `git branch` made it, the add's failure
    included, and raises the step's refusal. A `git branch` that refuses deletes nothing; one that
    times out is not undone."""
    made: Path | None = None
    branch: str | None = None
    done = False
    try:
        stage = stage_of(profile)
        staged = stage / final.name
        if staged.exists(follow_symlinks=False):
            raise Refusal(f"{staged} exists; the staging directory holds no worktree between requests")
        made = staged
        arguments = add_arguments(repo, name, staged, profile)
        if arguments[2:4] == ["--no-track", "-b"]:
            git("branch", "--no-track", name, arguments[-1], repo=repo, profile=profile)
            branch = name
            git("worktree", "add", str(staged), name, repo=repo, profile=profile)
        else:
            git(*arguments, repo=repo, profile=profile)
        move(staged, final)
        made = final
        moved(final)
        git("worktree", "repair", str(final), repo=repo, profile=profile)
        dot = final.resolve() / ".git"
        try:
            owner = linked_checkout(dot, RESEARCH.resolve())
        except Refusal as err:
            raise Refusal(f"the repaired {dot} does not name {repo}: {err}") from None
        if owner != repo:
            raise Refusal(f"the repaired {dot} names {owner}, not {repo}")
        done = True
    finally:
        if not done:
            undo(repo, made, profile, branch)


def undo(repo: Path, made: Path | None, profile: Path, branch: str | None = None) -> None:
    """Remove `made`, where given, run `git worktree prune` under srt, and then, where given, delete
    `branch` with `git branch -D` under srt. A failed removal, a prune that cannot start or times
    out, and a deletion that fails each write one stderr line that names `made`, the repository or
    the branch; the prune's own stderr passes through. Raises nothing: the earlier step refuses."""
    if made is not None:
        try:
            discard(made)
        except OSError as err:
            sys.stderr.write(f"worktree hook: {made} cannot be removed: {err}\n")
    try:
        proc = run_git("worktree", "prune", repo=repo, profile=profile)
    except (Refusal, subprocess.TimeoutExpired) as err:
        sys.stderr.write(f"worktree hook: `git worktree prune` in {repo} failed: {err}\n")
    else:
        sys.stderr.write(proc.stderr)
    if branch is None:
        return
    try:
        proc = run_git("branch", "-D", branch, repo=repo, profile=profile)
    except (Refusal, subprocess.TimeoutExpired) as err:
        failure = str(err)
    else:
        if proc.returncode == 0:
            return
        said = " ".join(proc.stderr.split())
        failure = f"exited {proc.returncode}" + (f": {said}" if said else "")
    sys.stderr.write(
        f"worktree hook: `git branch -D {branch}` in {repo}, of the branch that this create made, "
        f"failed: {failure}\n"
    )


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


def remove(payload: dict[str, JsonValue], profile: Path | None = None) -> None:
    """Remove the worktree at the payload's `worktree_path`, directly below ROOT; with the `profile`
    of a boxed child, every git runs under srt and the worktree is removed in the staging directory
    (`staged_remove`)."""
    where = payload.get("worktree_path", "")
    if not isinstance(where, str):
        raise Refusal(f"the hook input's worktree_path {where!r} is not a string")
    path = Path(where).resolve()
    if path.parent != ROOT.resolve():
        raise Refusal(f"{path} is not directly under {ROOT}; this hook removes only the worktrees it creates")
    repo = main_checkout(str(path), RESEARCH)
    checked_config(repo, profile)
    if not registered(repo, path, profile):
        raise Refusal(f"{path} is not a registered worktree of {repo}")
    if profile is None:
        deletable(path)
        git("worktree", "remove", str(path), repo=repo)
    else:
        staged_remove(repo, path, profile)


def deletable(tree: Path) -> None:
    """Refuse where this process cannot write in a directory of `tree` named one of SHIELDED, `.git`
    left out: it makes and removes one file in each. A sandbox denies writes there, and `git worktree
    remove` deletes the files up to the first one that it cannot delete, then deletes the worktree's
    record anyway, so the directory stays behind with no record."""
    for top, names, _ in os.walk(tree):
        names[:] = [name for name in names if name != ".git"]
        for name in names:
            if name not in SHIELDED:
                continue
            directory = Path(top, name)
            try:
                descriptor, probe = tempfile.mkstemp(prefix=".worktree-hook-", dir=directory)
                os.close(descriptor)
                Path(probe).unlink()
            except OSError as err:
                raise Refusal(
                    f"this process cannot write in {directory} ({err.strerror}), as in a sandbox, and "
                    "`git worktree remove` would delete the worktree's record and leave the directory: "
                    "remove it from a process outside the sandbox"
                ) from None


def staged_remove(repo: Path, path: Path, profile: Path) -> None:
    """Remove the worktree `path` through the staging directory of `profile`: a rename there without
    git, then `git worktree repair` and `git worktree remove`, without `--force`, under srt. Where
    a later step refuses, srt or git cannot start included, or git times out, the worktree is
    renamed back and repaired, and that error is raised; a repair after the rename back that
    refuses or times out writes one stderr line and does not replace it. Where the rename back
    fails, the refusal names the staged path."""
    stage = stage_of(profile)
    staged = stage / path.name
    move(path, staged)
    try:
        moved(staged)
        git("worktree", "repair", str(staged), repo=repo, profile=profile)
        git("worktree", "remove", str(staged), repo=repo, profile=profile)
    except Refusal, subprocess.TimeoutExpired:
        try:
            move(staged, path)
        except Refusal as err:
            raise Refusal(f"the worktree stays at {staged}, since it cannot be moved back: {err}") from None
        try:
            sys.stderr.write(run_git("worktree", "repair", str(path), repo=repo, profile=profile).stderr)
        except (Refusal, subprocess.TimeoutExpired) as err:
            sys.stderr.write(
                f"worktree hook: `git worktree repair {path}` after the move back failed: {err}\n"
            )
        raise


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
            data = receive(connection, None, time.monotonic() + ANSWER)
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


def receive(
    connection: socket.socket, limit: int | None, deadline: float, clock: Callable[[], float] = time.monotonic
) -> bytes:
    """The bytes from `connection` up to its first newline or its end; where `limit` is given, it
    reads at most `limit` + 1 bytes, and returns them all when no newline comes before them. The
    whole read ends by `deadline`, a time of `clock`: each `recv` waits at most the time left, and
    TimeoutError is raised once none is left, so a client that sends a byte now and then cannot
    hold the read longer."""
    data = b""
    while b"\n" not in data and (limit is None or len(data) <= limit):
        left = deadline - clock()
        if left <= 0:
            raise TimeoutError(f"the read did not end by its deadline, {len(data)} bytes read")
        connection.settimeout(left)
        chunk = connection.recv(65536 if limit is None else limit + 1 - len(data))
        if not chunk:
            break
        data += chunk
    return data.split(b"\n", 1)[0]


def serve(path: Path, parent: int, settings: Path) -> None:
    """The broker: read the srt settings file `settings` (`allowed_writes`), make its staging
    directory and profile (`staged_profile`), bind `path` with mode 600, replacing a stale socket
    and refusing any other file there, and answer each connection in turn (`answer`) while `parent`
    is this process's parent; then remove the socket, the profile where `staged_profile` wrote it,
    and the staging directory, the last only where it is empty. A profile that cannot be removed
    writes one stderr line, and an error in flight stays the error. SIGTERM and SIGHUP end it the
    same way."""
    if os.getppid() != parent:
        raise Refusal(f"the parent of the broker is {os.getppid()}, not {parent}")
    value = load(settings)
    writes = allowed_writes(value, settings)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        mode = None
    if mode is not None:
        if not stat.S_ISSOCK(mode):
            raise Refusal(f"{path} exists and is not a socket; the broker replaces only a stale socket")
        path.unlink()
    stage = STAGES / str(parent)
    profile = stage.parent / f"{stage.name}.json"
    written = False
    try:
        staged_profile(value, writes, stage, profile)
        written = True
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
                        answer(connection, profile)
            finally:
                path.unlink(missing_ok=True)
    finally:
        if written:
            remove_profile(profile)
        with contextlib.suppress(OSError):
            stage.rmdir()


def remove_profile(profile: Path) -> None:
    """Remove the broker's `profile`; where that fails, as for a directory at its path, write one
    stderr line instead of raising, so that an error in flight stays the error."""
    try:
        profile.unlink(missing_ok=True)
    except OSError as err:
        sys.stderr.write(f"worktree hook: the broker cannot remove its profile {profile}: {err}\n")


def allowed_writes(value: dict[str, JsonValue], settings: Path) -> list[str]:
    """The `filesystem.allowWrite` list of the srt settings `value`, read from `settings`; refused
    where `filesystem` is no object or `allowWrite` no list of strings."""
    filesystem = value.get("filesystem")
    writes = filesystem.get("allowWrite") if isinstance(filesystem, dict) else None
    if not isinstance(writes, list) or not all(isinstance(w, str) for w in writes):
        raise Refusal(f"{settings} holds no filesystem.allowWrite that is a list of strings")
    return [w for w in writes if isinstance(w, str)]


def staged_profile(
    value: dict[str, JsonValue],
    writes: list[str],
    stage: Path,
    profile: Path,
    now: Callable[[], int] = time.time_ns,
) -> None:
    """Make the staging directory `stage` with mode 700 and write `profile` with mode 600: the srt
    settings `value` with `stage` appended to `writes`, its `filesystem.allowWrite`, so that the
    boxed git can write there and nowhere else that the box cannot. A link or any other file at
    `stage` refuses. A stale directory there is removed where it is empty; one that holds anything,
    such as a worktree that an earlier broker could not move back, is never deleted: it moves aside
    to `<stage>.stale-<now()>`, a path that must not exist, and one line on standard error names
    both paths."""
    try:
        stage.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stage.is_symlink() or (stage.exists() and not stage.is_dir()):
            raise Refusal(
                f"{stage} is a symbolic link or no directory; the broker replaces only a stale directory"
            )
        if stage.exists() and any(stage.iterdir()):
            aside = stage.with_name(f"{stage.name}.stale-{now()}")
            if aside.exists(follow_symlinks=False):
                raise Refusal(f"{aside} exists; the broker moves the stale {stage} only to a new path")
            stage.rename(aside)
            print(
                f"worktree hook: the stale {stage} is not empty, and moves aside to {aside}", file=sys.stderr
            )
        elif stage.exists():
            stage.rmdir()
        stage.mkdir(mode=0o700)
        stage.chmod(0o700)
        filesystem = value.get("filesystem")
        fields = filesystem if isinstance(filesystem, dict) else {}
        text = json.dumps({**value, "filesystem": {**fields, "allowWrite": [*writes, str(stage)]}}) + "\n"
        profile.unlink(missing_ok=True)
        descriptor = os.open(profile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as err:
        raise Refusal(
            f"the broker cannot make its staging directory {stage} and profile {profile}: {err}"
        ) from None


def ended(signum: int, frame: FrameType | None) -> None:
    """The SIGTERM and SIGHUP handler of the broker: exit through the cleanup of `serve`."""
    del signum, frame
    sys.exit(0)


def answer(connection: socket.socket, profile: Path) -> None:
    """Read one request from `connection` and send `respond`'s answer with `profile` as one JSON
    line. A client that leaves, or has not sent its request within LOCAL seconds, takes its reply
    with it; the broker serves the next."""
    try:
        data = receive(connection, LIMIT, time.monotonic() + LOCAL)
    except OSError:
        return
    reply = respond(data, profile)
    with contextlib.suppress(OSError):
        connection.settimeout(LOCAL)
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


def respond(data: bytes, profile: Path) -> Reply:
    """The answer to the request `data` (`read_request`): the path and stderr of this script run on
    it as `--boxed <profile>`, without AGENTBOX and AGENTBOX_BROKER, and with GIT_TERMINAL_PROMPT=0,
    so that a fetch never prompts on the frontend's terminal; or an error, also where that process
    cannot start."""
    try:
        request = read_request(data)
    except (Refusal, HarnessError) as err:
        return Reply(error=str(err))
    env = {k: v for k, v in os.environ.items() if k not in ("AGENTBOX", BROKER)} | {
        "GIT_TERMINAL_PROMPT": "0"
    }
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).absolute()), "--boxed", str(profile)],
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


USAGE = "usage: worktree.py [--serve <socket> --parent <pid> --settings <file> | --boxed <profile>]"


def serve_arguments(args: Sequence[str]) -> tuple[Path, int, Path]:
    """The socket, the parent's process ID and the settings file of `--serve <socket> --parent
    <pid> --settings <file>`."""
    match list(args):
        case ["--serve", path, "--parent", parent, "--settings", settings] if (
            parent.isascii() and parent.isdigit()
        ):
            return Path(path), int(parent), Path(settings)
        case _:
            raise Refusal(USAGE)


def boxed_profile(args: Sequence[str]) -> Path | None:
    """The profile of `--boxed <profile>`, or None for no arguments; refused where SRT is no
    executable file, links followed, since every git of a boxed child runs in it."""
    match list(args):
        case []:
            return None
        case ["--boxed", profile]:
            if not SRT.is_file() or not os.access(SRT, os.X_OK):
                raise Refusal(f"{SRT} is not an executable file; a boxed child runs every git in srt")
            return Path(profile)
        case _:
            raise Refusal(USAGE)


def main(args: Sequence[str] = ()) -> int:
    """`handle` with `args`, with SIGTERM and SIGHUP handlers (`interrupted`) that raise SystemExit,
    so that `run_git` stops the process group of a running git before the hook ends; git runs in a
    session of its own, which a signal to the hook's group does not reach. The handlers that were
    in place before are restored. SIGINT keeps Python's KeyboardInterrupt, which `run_git` treats
    the same way."""
    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGHUP)}
    for signum in previous:
        signal.signal(signum, interrupted)
    try:
        return handle(args)
    finally:
        for signum, handler in previous.items():
            if handler is not None:
                signal.signal(signum, handler)


def interrupted(signum: int, frame: FrameType | None) -> None:
    """The SIGTERM and SIGHUP handler of the hook: ignore both signals from here on, so that a second
    one does not end the group stop of `run_git` before its SIGKILL, and raise SystemExit with
    status 128 + `signum`. `main` restores the handlers of before."""
    del frame
    for each in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(each, signal.SIG_IGN)
    raise SystemExit(128 + signum)


def handle(args: Sequence[str]) -> int:
    """Serve as the broker, or run the create or the remove of the hook input on stdin: 0, or 1 with
    one `worktree hook:` line for a refusal or a git past its timeout."""
    try:
        if args and args[0] == "--serve":
            serve(*serve_arguments(args))
            return 0
        profile = boxed_profile(args)
        payload = loads(sys.stdin.read(), where="hook input")
        event = payload.get("hook_event_name")
        if "AGENTBOX" in os.environ:
            ask(payload, created=event == "WorktreeCreate")
        elif event == "WorktreeCreate":
            print(create(payload, profile))
        elif event == "WorktreeRemove":
            remove(payload, profile)
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
