#!/usr/bin/env python3
"""Run the case battery for the hooks in this directory, one subprocess call per case.

Each case is checked on its own and printed on its own line, so a passing total cannot
hide a case that went the wrong way. Exit status is 1 when any case is wrong.

    ./probe.py [GROUP ...]

With no argument it runs every group of GROUPS; with names, only those groups. Each run
builds its own fixture.

A case gives a hook a payload and compares its answer: exit 2 refuses the call, exit 0
lets it through or answers with a JSON decision. The group `commands` runs the guard
package on each Claude Code record of `tests/guard/corpus.jsonl` and on its edges, the group
`antigravity` on each Antigravity record, and the groups `omp` and `opencode` on each record
of their frontend, through its plugin; the guard fails closed, so a payload it cannot read is
refused.

The hooks run against a fixture `HOME`, never the real one, so the cases mean the same on
every machine and in CI. Each Python hook runs with this interpreter, `sys.executable`, not
with its shebang, and each call has a timeout. Each fixture home in which the guard of Claude
Code, OpenCode or oh-my-pi runs holds a `.ssh` that the guard cannot list, as under `agentbox`,
so that its launcher check passes there; only the cases of the launcher check add homes whose
`.ssh` it can list.
"""

import ast
import contextlib
import errno
import getpass
import importlib.util
import io
import json
import os
import pathlib
import pwd
import re
import runpy
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import types
from collections.abc import Callable
from dataclasses import replace
from typing import Any, NamedTuple, TextIO, cast
from unittest import mock

HOOKS = os.path.dirname(os.path.abspath(__file__)) + "/"

# The fixture: one temporary directory per run, removed on exit, also after a failure. The
# hooks get it as `HOME` with exactly two leading slashes. The guard's write check exempts
# every path whose text begins with `/tmp/`, `/var/folders/` or `$TMPDIR` as a scratch root,
# and so a fixture `HOME` spelt there with one slash; a leading `//` is kept as text, so the
# check sees the fixture `HOME` as it sees a real one. macOS and Linux resolve `//` as `/`.
# `HOME` is one level below the temporary directory, so its parent is that directory and never
# `/tmp` itself, which holds the scratch paths of the rm cases.
FIXTURE = tempfile.TemporaryDirectory(prefix="harness-probe-")
HOME = "/" + FIXTURE.name + "/home"
R = HOME + "/Research"
WT = R + "/.worktrees/Foo-bar"
PKG = R + "/Packages/Example"
# The working directory of the cases: a git work tree of the fixture, whose `.gitignore` ignores
# `__pycache__/`, never this checkout. A checkout below `/tmp/` or `$TMPDIR` is scratch to the
# guard's write check, which would then let every write of the cases through.
TOOL = R + "/Harness"
CWD = TOOL + "/hooks/"
# No `GIT_*` variable of the caller: a `GIT_DIR`, as git exports it to a hook, would send the
# fixture's git commands and the hooks' to the caller's repository. No `RESEARCH_HARNESS_PROFILE`
# either: the guard would read the caller's profile in place of the fixture home's.
CLEAN = {
    k: v
    for k, v in os.environ.items()
    if not k.startswith("GIT_") and k not in ("RESEARCH_HARNESS_PROFILE", "AGENTBOX", "AGENTBOX_BROKER")
}
# The global git configuration of every hook, in place of the caller's `~/.gitconfig` and
# `$XDG_CONFIG_HOME/git/config`: it names OWN_EMAIL, the address that the web check refuses.
OWN_EMAIL = "probe-user@example.org"
GIT_CONFIG = FIXTURE.name + "/gitconfig"
pathlib.Path(GIT_CONFIG).write_text(f"[user]\n\temail = {OWN_EMAIL}\n", encoding="utf-8")
CLEAN["GIT_CONFIG_GLOBAL"] = GIT_CONFIG
# Kaimon's cache, whose `sock/` the Kaimon check reads: the gate file of each key of LIVE_GATES
# names this process, which runs for the whole run, and that of STALE_GATE a process that has
# ended, as a session that died leaves it. The gate files of UNREAD_GATES name no process: one
# holds a `pid` that is no integer, the other no JSON.
KAIMON_CACHE = FIXTURE.name + "/kaimon"
LIVE_GATES = ("a1b2c3d4", "abcd1234")
STALE_GATE = "deadbeef"
UNREAD_GATES = {"c0ffee00": '{"pid": "4892"}', "badf00d0": "not json"}


def ended_pid() -> int:
    """The process id of a process that has ended."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=60)
    return child.pid


def gate_files() -> None:
    """Write the gate file of each key of LIVE_GATES and STALE_GATE below KAIMON_CACHE."""
    sock = pathlib.Path(KAIMON_CACHE, "sock")
    sock.mkdir(parents=True)
    for key, pid in (*((key, os.getpid()) for key in LIVE_GATES), (STALE_GATE, ended_pid())):
        sid = f"{key}-0000-5000-8000-000000000000"
        sock.joinpath(f"{sid}.json").write_text(json.dumps({"session_id": sid, "pid": pid}), encoding="utf-8")
        sock.joinpath(f"{sid}.sock").touch()
    for key, text in UNREAD_GATES.items():
        sock.joinpath(f"{key}-0000-5000-8000-000000000000.json").write_text(text, encoding="utf-8")


gate_files()
CLEAN["KAIMON_CACHE_DIR"] = KAIMON_CACHE
# Three more Kaimon caches: one with no `sock/`, one with an empty `sock/`, and one whose two live
# gates share the key of their first 8 characters, TWIN_GATE.
NO_GATES = FIXTURE.name + "/kaimon-no-sock"
pathlib.Path(NO_GATES).mkdir()
EMPTY_GATES = FIXTURE.name + "/kaimon-empty"
pathlib.Path(EMPTY_GATES, "sock").mkdir(parents=True)
TWIN_CACHE = FIXTURE.name + "/kaimon-twins"
TWIN_GATE = "a1b2c3d4"
for twin in ("0001", "0002"):
    twin_sid = f"{TWIN_GATE}-0000-5000-8000-00000000{twin}"
    twin_file = pathlib.Path(TWIN_CACHE, "sock", f"{twin_sid}.json")
    twin_file.parent.mkdir(parents=True, exist_ok=True)
    twin_file.write_text(json.dumps({"session_id": twin_sid, "pid": os.getpid()}), encoding="utf-8")
# A Kaimon cache of eight live gates, MANY_GATES, whose keys a set under the hash seed 0 does not
# hold in sorted order, so that a refusal that lists them unsorted fails its case on every run.
MANY_CACHE = FIXTURE.name + "/kaimon-many"
MANY_GATES = ("0a1b2c3d", "1b2c3d4e", "2c3d4e5f", "3d4e5f60", "4e5f6071", "5f607182", "60718293", "718293a4")
for many in MANY_GATES:
    many_sid = f"{many}-0000-5000-8000-000000000000"
    many_file = pathlib.Path(MANY_CACHE, "sock", f"{many_sid}.json")
    many_file.parent.mkdir(parents=True, exist_ok=True)
    many_file.write_text(json.dumps({"session_id": many_sid, "pid": os.getpid()}), encoding="utf-8")
ENV = {**CLEAN, "HOME": HOME}
# The `.ssh` of each fixture home in which a guard case of Claude Code, OpenCode or oh-my-pi runs: a
# directory with mode 000, which the guard cannot list, as under `agentbox`, whose sandbox denies
# `~/.ssh`. On macOS the guard refuses every call of those frontends when it can list `~/.ssh`
# (`guard/launcher.py`). `main` gives each one mode 700 again before it removes the fixture, so that
# the removal need not go through a directory that it cannot list.
CLOSED_SSH: list[pathlib.Path] = []
# The launcher check answers on macOS alone; on another platform it passes every call, so there each
# case of the launcher that runs the guard in a process of its own expects the decision of the corpus.
MAC = sys.platform == "darwin"
# A text of the launcher check's refusal of a session whose `~/.ssh` the guard can list, and one of
# its refusal when the listing fails with another error than `PermissionError`.
LAUNCHER_OUTSIDE = "runs outside `agentbox`, with `~/.ssh` readable"
LAUNCHER_UNKNOWN = "cannot tell whether a sandbox holds"
# The variables of the caller's session that the launcher check reads; each launcher case that runs
# the guard in a process of its own removes them and sets its own.
LAUNCHER_ENV = ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CONFIG_DIR")
# The `enabled` of `sandbox_settings` that makes the settings file a named pipe, whose read blocks.
FIFO = object()


def closed_ssh(home: str | pathlib.Path) -> None:
    """Make `<home>/.ssh` with mode 000, and record it in CLOSED_SSH."""
    ssh = pathlib.Path(home, ".ssh")
    ssh.mkdir()
    CLOSED_SSH.append(ssh)
    ssh.chmod(0o000)


def sandbox_settings(directory: pathlib.Path, enabled: object) -> None:
    """Make the directory `directory` with a `settings.json` whose `sandbox.enabled` is `enabled`, or
    none for None; a bytes `enabled` is the file's whole content, and FIFO a named pipe in its place."""
    directory.mkdir(parents=True, exist_ok=True)
    if enabled is FIFO:
        os.mkfifo(directory / "settings.json")
    elif enabled is not None:
        data = (
            enabled
            if isinstance(enabled, bytes)
            else json.dumps({"sandbox": {"enabled": enabled}}).encode("utf-8")
        )
        (directory / "settings.json").write_bytes(data)


def launcher_home(home: str | pathlib.Path, *, ssh: bool = True, enabled: object = None) -> str:
    """Give the fixture home `home` a readable `.ssh` unless `ssh` is false, and a
    `.claude/settings.json` as `sandbox_settings` writes it for `enabled`. Return the home spelt with
    two leading slashes, as HOME is."""
    path = pathlib.Path(home)
    path.mkdir(exist_ok=True)
    if ssh:
        (path / ".ssh").mkdir(exist_ok=True)
        (path / ".ssh").chmod(0o700)
    if enabled is not None:
        sandbox_settings(path / ".claude", enabled)
    return "/" + str(path)


def claudex_home(
    home: str | pathlib.Path, *, enabled: object = None, directory: str = ".config/claudex"
) -> str:
    """Make the directory `<home>/<directory>`, `claudex`'s `CLAUDE_CONFIG_DIR` by default, with a
    `settings.json` as `sandbox_settings` writes it for `enabled`. Return the directory spelt as `home`
    is, with its two leading slashes where `launcher_home` gave it."""
    path = pathlib.Path(home, directory)
    sandbox_settings(path, enabled)
    return str(path)


# The profile of each fixture home, whose `org` list the `gh api` check reads: an own organisation
# and an own account. A record's `profile` names another file in place of it, through
# `RESEARCH_HARNESS_PROFILE`: one of PROFILES below the fixture's `profiles/`, or a missing one.
OWN_PROFILE = 'org = ["own-org", "own-user"]\n'
PROFILES = {
    "not-toml.toml": b"org = [\n",
    "not-utf8.toml": b'org = ["own-org"] # \xff\n',
    "no-org.toml": b'leak = ["x"]\n',
    "org-text.toml": b'org = "own-org"\n',
    "org-mixed.toml": b'org = ["own-org", 1]\n',
    "other.toml": b'org = ["other-org"]\n',
    "dotted.toml": b'org = ["own.org"]\n',
}
# A fake token of each form that the token check reads, by its placeholder `@@<NAME>@@` in the corpus.
# Each is joined here at run time, so that no file of the repository holds one for gitleaks to find.
# GHP is the GitHub classic form, GHO, GHU, GHS and GHR the other kinds of its prefix `gh[pousr]_`,
# PAT the fine-grained form and PAT_ENCODED it percent-encoded, GLPAT GitLab's form and SK the form
# of the `sk-` keys, each with the shortest body of its form, and a body with each `_` or `-` that
# the form allows; `_SHORT` names the same token one character short, and GHP_UPPER the classic
# form with an upper-case prefix.
GHP_BODY = "0123456789abcdefghijKLMNOPQRSTUVWXYZ"
PAT_BODY = GHP_BODY[:10] + "_" + GHP_BODY[10:21]
GLPAT_BODY = GHP_BODY[:9] + "-_" + GHP_BODY[9:18]
SK_BODY = "ant-api03_" + GHP_BODY[:10]
TOKENS = {
    "GHP": "gh" + "p_" + GHP_BODY,
    "GHP_SHORT": "gh" + "p_" + GHP_BODY[:-1],
    "GHP_UPPER": "GH" + "P_" + GHP_BODY,
    **{f"GH{kind.upper()}": "gh" + kind + "_" + GHP_BODY for kind in "ousr"},
    "PAT": "github" + "_pat_" + PAT_BODY,
    "PAT_SHORT": "github" + "_pat_" + PAT_BODY[:-1],
    "PAT_ENCODED": "github" + "%5Fpat%5F" + PAT_BODY,
    "GLPAT": "glpat" + "-" + GLPAT_BODY,
    "GLPAT_SHORT": "glpat" + "-" + GLPAT_BODY[:-1],
    "SK": "s" + "k-" + SK_BODY,
    "SK_SHORT": "s" + "k-" + SK_BODY[:-1],
}
# The query files of the `gh api graphql` records, below the fixture's `gh/`.
GH_QUERIES = {
    "read.graphql": b"# no mutation is named but in this comment\nquery { viewer { login } }\n",
    "merge.graphql": b'mutation { mergePullRequest(input: {pullRequestId: "P"}) { clientMutationId } }\n',
    "resolve.graphql": b'mutation { resolveReviewThread(input: {threadId: "T"}) { thread { id } } }\n',
    "quote-comment.graphql": b'# a " in a comment\nmutation { mergePullRequest(input: {pullRequestId: "P"}) { clientMutationId } }\n',
    "not-utf8.graphql": b"query { viewer { login } } # \xff\n",
    "reply.json": b'{"query": "mutation($t: ID!, $b: String!) { addPullRequestReviewThreadReply(input: '
    b'{pullRequestReviewThreadId: $t, body: $b}) { comment { id } } }", "variables": {"t": "T", "b": "x"}}\n',
    "merge.json": b'{"query": "mutation { mergePullRequest(input: {pullRequestId: \\"P\\"}) { clientMutationId } }"}\n',
    "no-query.json": b'{"variables": {"t": "T"}}\n',
    "not-json.json": b"query { viewer { login } }\n",
}
q = shlex.quote  # a fixture path spliced into a command, for a `$TMPDIR` with a space
TIMEOUT = 30  # seconds per hook call; a timeout is a wrong case
MIB = 1024 * 1024  # bytes: the largest command that the guard decides by its checks
# seconds: a guard call on a command of 1 MiB that runs longer has hung. Its decision and its count
# of work decide each case of such a command; this limit only stops a hang, far above the seconds
# that a loaded runner takes.
MIB_HANG = 120
# stat and lstat calls of a payload beside those for the distinct names of its words: the walk of
# its working directory, the roots of the checks, the `.git` above a write. 62 for the first two
# counted `cd` payloads, 180 for the third and at most 74 for the payloads that resolve operands and
# `git init` targets, on macOS with the fixture below `/tmp/<one name>/`; the margin holds a fixture
# below a deeper `$TMPDIR`. Also the bound of the steps of a walk beside those of the distinct names.
WALK_READS = 400

WORKTREE = HOOKS + "worktree.py"
# The variables that send `worktree.py` to its broker. Every case of the hook runs without them,
# also where the caller runs under `agentbox`, unless the case sets them itself.
AGENTBOX_VARS = ("AGENTBOX", "AGENTBOX_BROKER")
WORKTREE_ENV = {k: v for k, v in ENV.items() if k not in AGENTBOX_VARS}

# The guard package, run as the settings template runs it, on the differential corpus that holds
# the cases of the hook scripts whose checks it holds. Each record is one JSON object per line:
# `stdin` (an object, sent as its JSON text, or a string, sent as it is) and `decision`, the guard's
# expected decision; a placeholder `@@<NAME>@@` in a string stands for the fixture's value of NAME.
# A record of any frontend may hold `profile`, the path that `RESEARCH_HARNESS_PROFILE` names for its
# call; without it, the guard reads OWN_PROFILE in the fixture home.
# A record with `"frontend": "antigravity"` is an Antigravity call instead: `tool`, `args`, an
# optional `workspace`, Antigravity's `decision` and the `bypass` of its `overwrite`, and `differs`,
# the reason, where the removed Antigravity hook answered otherwise; `@@AGYHOME@@` stands for the
# fixture home of the Antigravity cases. The records of oh-my-pi and OpenCode are described above
# OMP_DRIVER.
GUARD = HOOKS + "guard"
SCRATCH = R + "/.scratch"
# A work tree of the fixture in a worktree zone, whose `.gitignore` ignores `*.log`, with the
# directories `a` and `d1/…/d40` and a link `loop` to itself: the working directory of the commands
# of 1 MiB that walk `cd` words and write files that git ignores.
LOGS = str(pathlib.PurePosixPath(R, ".worktrees", "Logs"))
DEEP = str(pathlib.PurePosixPath(LOGS, *(f"d{i}" for i in range(1, 41))))
# A directory 13 names below the fixture's directory, in no work tree: the working directory of a
# `git init` whose work tree check climbs to `/`.
OUTSIDE = str(pathlib.PurePosixPath(FIXTURE.name, "outside", *(f"o{i}" for i in range(1, 13))))
# A directory whose `.git` is a link to a name that does not exist.
DANGLING = HOME + "/dangling"

# `worktree.py` is not a `PreToolUse` hook: it fails closed, so every case here expects 1. Its git
# work runs in `worktree_git_cases`, on a fixture of its own below the fixture directory.
WORKTREE_CASES = [
    "not json at all",
    "[1]",
    '{"hook_event_name":"Other"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"/","name":"x"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"/nonexistent","name":"x"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"' + CWD + '","name":"a/../b"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"' + CWD + '","name":""}',
    '{"hook_event_name":"WorktreeRemove","worktree_path":"' + CWD + '"}',
    '{"hook_event_name":"WorktreeRemove","worktree_path":"/nonexistent/.worktrees/x"}',
]

# `worktree.py`'s manifest test, called as a function: (version, `[compat]` entry, inside or not).
COMPAT_CASES = [
    ("0.3.5", "0.4", False),
    ("0.4.2", "0.4", True),
    ("0.5.0", "0.4", False),
    ("1.9.0", "1.2", True),
    ("2.0.0", "1.2", False),
    ("1.1.9", "1.2", False),
    ("0.0.3", "0.0.3", True),
    ("0.0.4", "0.0.3", False),
    ("0.9.0", "0", True),
    ("1.0.0", "0", False),
    ("1.2.9", "~1.2", True),
    ("1.3.0", "~1.2", False),
    ("0.0.3", "~0.0.3", True),
    ("0.0.4", "~0.0.3", False),
    ("1.2.3", "=1.2.3", True),
    ("1.2.4", "=1.2.3", False),
    ("5.0.0", ">= 1.2", True),
    ("1.1.0", "≥ 1.2", False),
    ("1.9.9", "< 2", True),
    ("2.0.0", "< 2", False),
    ("2.3.7", "1.2 - 2.3", True),
    ("2.4.0", "1.2 - 2.3", False),
    ("0.3.1", "0.3, 0.4", True),
    ("0.4.1", "0.3, 0.4", True),
    ("0.5.0", "0.3, 0.4", False),
    ("1.2.3", "<= 2", None),
    ("1.2.3", "1.x", None),
]
# (manifest deps as {name: version or None}, the project's `[deps]` and `[compat]`, copied or not)
MANIFEST_CASES = [
    ({"A": "0.4.1", "B": None}, ["A", "B"], {"A": "0.4"}, True),
    ({"A": "0.3.0", "B": None}, ["A", "B"], {"A": "0.4"}, False),
    ({"A": "0.4.1"}, ["A", "C"], {"A": "0.4"}, False),
    ({"A": "0.4.1"}, ["A"], {"A": "<= 1"}, False),
    ({"A": "0.4.1"}, ["A"], {"julia": "1.11"}, True),
]


def own_profile(home: str) -> None:
    """Write OWN_PROFILE as the profile of the fixture home `home`."""
    config = pathlib.Path(home, ".config", "research-harness")
    config.mkdir(parents=True, exist_ok=True)
    (config / "profile.toml").write_text(OWN_PROFILE, encoding="utf-8")


def profile_env(record: dict[str, Any]) -> dict[str, str]:
    """The variables of a corpus record: its `env` object, and `RESEARCH_HARNESS_PROFILE` where it
    names a `profile`."""
    env = {str(k): str(v) for k, v in record.get("env", {}).items()}
    return env | ({"RESEARCH_HARNESS_PROFILE": str(record["profile"])} if "profile" in record else {})


def load_module(name: str, path: str) -> types.ModuleType:
    """The Python file `path`, loaded as the module `name`."""
    spec = importlib.util.spec_from_file_location(name, path)
    # A path that ends in `.py` always gets a spec with a source loader.
    if spec is None or spec.loader is None:
        raise ImportError(f"{path} gives no module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_cases():
    """`worktree.py`'s `compat_ranges` and `copy_manifest`: (number of cases, number wrong)."""
    hook = load_module("worktree_hook", WORKTREE)
    total = wrong = 0
    for version, entry, expected in COMPAT_CASES:
        ranges = hook.compat_ranges(entry)
        v = hook.parse_version(version)
        got = None if ranges is None else any(lo <= v < hi for lo, hi in ranges)
        total, wrong = total + 1, wrong + (got != expected)
        print(
            f"{'ok ' if got == expected else 'BAD'} exp {expected} got {got}  [worktree ]  {version} in [compat] {entry!r}"
        )
    for k, (deps, names, compat, expected) in enumerate(MANIFEST_CASES):
        repo, wt = (
            os.path.join(FIXTURE.name, f"manifest-{k}", "repo"),
            os.path.join(FIXTURE.name, f"manifest-{k}", "wt"),
        )
        os.makedirs(repo)
        os.makedirs(wt)
        with open(os.path.join(repo, "Manifest.toml"), "w") as f:
            f.write('julia_version = "1.13.0"\nmanifest_format = "2.0"\n')
            for name, version in deps.items():
                f.write(
                    f'\n[[deps.{name}]]\nuuid = "{k}"\n' + (f'version = "{version}"\n' if version else "")
                )
        with open(os.path.join(wt, "Project.toml"), "w") as f:
            f.write(
                'name = "P"\n\n[deps]\n'
                + "".join(f'{n} = "u"\n' for n in names)
                + "\n[compat]\n"
                + "".join(f'{n} = "{c}"\n' for n, c in compat.items())
            )
        hook.copy_manifest(hook.Path(repo), hook.Path(wt))
        got = os.path.exists(os.path.join(wt, "Manifest.toml"))
        total, wrong = total + 1, wrong + (got != expected)
        print(
            f"{'ok ' if got == expected else 'BAD'} exp {expected} got {got}  [worktree ]  manifest {deps} for {names} {compat}"
        )
    # A git that runs longer than its timeout fails closed: exit 1 and one line that names it. The
    # fake git outlives its SIGTERM and its SIGKILL, which go to a recorder.
    err = io.StringIO()
    payload = '{"hook_event_name":"WorktreeCreate","cwd":"' + CWD + '","name":"x"}'

    def stuck(*args: object, **kwargs: object) -> FakeGit:
        del args, kwargs
        return FakeGit(["git", "rev-parse"], 3, [])

    with (
        mock.patch.object(subprocess, "Popen", side_effect=stuck),
        mock.patch.object(os, "killpg"),
        mock.patch.object(sys, "stdin", io.StringIO(payload)),
        mock.patch.dict(os.environ, WORKTREE_ENV, clear=True),
        mock.patch.object(hook, "RESEARCH", pathlib.Path(R)),
        mock.patch.object(hook, "ROOT", pathlib.Path(R, ".worktrees")),
        contextlib.redirect_stderr(err),
    ):
        code = hook.main()
    said = err.getvalue().strip()
    ok = code == 1 and said == "worktree hook: `git rev-parse` took more than 60 s"
    total, wrong = total + 1, wrong + (not ok)
    print(f"{'ok ' if ok else 'BAD'} exp 1 got {code}  [worktree ]  a git past its timeout: {said!r}")
    # A payload that is no JSON object fails closed with one line that names the hook input.
    for payload in ("not json at all", "[1]"):
        err = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", io.StringIO(payload)),
            mock.patch.dict(os.environ, WORKTREE_ENV, clear=True),
            contextlib.redirect_stderr(err),
        ):
            try:
                code = hook.main()
            except hook.HarnessError as e:
                code = f"{type(e).__name__}: {e}"
        said = err.getvalue().strip()
        ok = code == 1 and said.startswith("worktree hook: hook input: ") and "\n" not in said
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} exp 1 got {code}  [worktree ]  {payload!r} is one line: {said!r}")
    return total, wrong


# The fixture of `worktree.py`'s git work, made by `worktree_fixture` in a home of its own below the
# fixture directory, WT_HOME. Its `Research` holds `Repo`, a clone of the bare `wt-origin.git` with
# the origin WT_ORIGIN's `ssh://` URL and the keys of WT_KEYS, whose `core.hooksPath` is its tracked
# `.githooks`, whose `post-checkout` writes WT_MARKER; `Linked`, whose `.git` is a link to
# `Repo/.git`; the worktrees `.worktrees/Repo-common` and `.worktrees/Repo-gitdir` of `Repo`, whose
# admin directories hold another `commondir` and another `gitdir`, and `.worktrees/Repo-via`, whose
# `.git` file names its admin directory through `Linked/.git`; `.worktrees/Repo-linked`, a link to
# an empty directory; `Common`, whose `.git` holds a `commondir`, with its worktree
# `.worktrees/Common-x`; and the repositories of WT_REFUSED and WT_RAW, whose `.git/config` the hook
# refuses. WT_OUTSIDE is a repository outside it with one commit, whose worktree
# `.worktrees/Outside-x` lies inside it. The `git` first on the PATH of WT_ENV appends its
# arguments to WT_LOG and runs git.
WT_HOME = "/" + FIXTURE.name + "/wt"
WT_R = WT_HOME + "/Research"
WT_REPO = WT_R + "/Repo"
WT_ROOT = WT_R + "/.worktrees"
WT_OUTSIDE = FIXTURE.name + "/wt-outside"
WT_MARKER = FIXTURE.name + "/wt-marker"
WT_LOG = FIXTURE.name + "/wt-git.log"
WT_BIN = FIXTURE.name + "/wt-bin"
# The directory of the brokers' sockets, near the top of the fixture: a socket path holds at most
# 103 bytes on macOS.
WT_SOCKETS = FIXTURE.name + "/s"
# The origin of `Repo`, an `ssh://` URL that the fake ssh WT_BIN/fake-ssh serves from the bare
# repository at the URL's path, so that the hook's fetch passes its protocol and URL tests.
WT_ORIGIN = FIXTURE.name + "/wt-origin.git"
WT_SSH = FIXTURE.name + "/wt-ssh.log"
WT_ENV = {
    **WORKTREE_ENV,
    "HOME": WT_HOME,
    "PATH": WT_BIN + ":" + WORKTREE_ENV.get("PATH", "/usr/bin:/bin"),
    "GIT_SSH_COMMAND": WT_BIN + "/fake-ssh",
    "GIT_SSH_VARIANT": "simple",
}
# The keys of `Repo`'s `.git/config` beyond those of a clone: every key that the hook allows by
# name, a scp-like push URL and a second remote.
WT_KEYS = [
    ("remote.origin.pushurl", "fixture:" + WT_ORIGIN),
    ("remote.origin.glab-resolved-head", "main"),
    ("remote.private.url", "https://example.org/private.git"),
    ("pull.rebase", "true"),
    ("lfs.repositoryformatversion", "0"),
    ("user.name", "probe"),
    ("user.email", "probe@example.org"),
    ("branch.main.pushremote", "origin"),
    ("branch.main.vscode-merge-base", "origin/main"),
    ("branch.main.github-pr-owner-number", "owner#repo#1"),
    ("branch.main.github-pr-base-branch", "owner#repo#main"),
]
# The repositories of the fixture's Research whose `.git/config` holds one key that the hook
# refuses, each with a worktree `.worktrees/<directory>-x` made before the key was set:
# (directory, key, value).
WT_REFUSED = [
    ("Ssh", "core.sshCommand", "false"),
    ("Include", "include.path", "elsewhere"),
    ("Extensions", "extensions.worktreeConfig", "true"),
    ("Data", "remote.datashare.url", "/x"),
]
# The repositories whose `.git/config` is these bytes, and the word of the hook's line on each:
# (directory, bytes, word).
WT_RAW = [
    ("Broken", b"[core\n", "exited"),
    ("Latin", b"[core]\n\tsshCommand = \xff\n", "core.sshcommand"),
]
# The options before the subcommand of every git that `worktree.py` starts.
WT_OPTIONS = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"]
# The `.git` line of a worktree that `git worktree add --relative-paths` makes in the fixture.
WT_RELATIVE = "gitdir: ../../Repo/.git/worktrees/Repo-rel"
# The fixture of git's own search for a repository: `Evil`, a repository whose `.git/config` holds a
# `core.sshCommand` that writes WT_EVIL_MARKER and an `ssh://` origin; `Evil/sub`, whose `.git` is
# a directory that holds only a config of allowed keys, so that git does not take it as a
# repository; `Evil/bare`, the same plus a HEAD, `objects` and `refs` of its own and a config with
# that `core.sshCommand`, so that git takes `Evil/bare` itself as a bare repository; and
# WT_COMMON, a bare repository with that `core.sshCommand` and origin, for a caller's
# GIT_COMMON_DIR. WT_EVIL_ENV reaches the fake ssh through GIT_SSH, which a `core.sshCommand`
# overrides, where WT_ENV's GIT_SSH_COMMAND overrides the key.
WT_EVIL_MARKER = WT_HOME + "/evil-marker"
WT_EVIL = WT_R + "/Evil"
WT_COMMON = WT_HOME + "/common.git"
WT_EVIL_SSH = f"touch '{WT_EVIL_MARKER}'; false"
WT_EVIL_ENV = {
    **{k: v for k, v in WT_ENV.items() if k != "GIT_SSH_COMMAND"},
    "GIT_SSH": WT_BIN + "/fake-ssh",
}
# The script of a broker's parent: a shell that starts `worktree.py --serve` as its child, with its
# output in a log file, prints the broker's process ID, and runs until its own stdin ends.
BROKER_PARENT = (
    '"$0" "$1" --serve "$2" --parent $$ --settings "$4" > "$3" 2>&1 < /dev/null & echo "$!"; read -r line'
)
# The boxed git of `worktree.py`: the stub srt WT_SRT in the fixture home's `.local/bin` (STUB_SRT),
# which appends its arguments to WT_SRT_LOG; the brokers' staging directories below WT_STAGES; the
# staging directory WT_STAGE and its profile WT_PROFILE of the cases that run `--boxed` directly;
# and the settings file WT_SETTINGS of a broker, whose value is WT_SETTINGS_VALUE.
WT_SRT = WT_HOME + "/.local/bin/srt"
WT_SRT_LOG = FIXTURE.name + "/wt-srt.log"
WT_STAGES = WT_HOME + "/.local/state/research-harness/worktree-stage"
WT_STAGE = WT_STAGES + "/1"
WT_PROFILE = WT_STAGE + ".json"
WT_SETTINGS = FIXTURE.name + "/wt-settings.json"
WT_SETTINGS_VALUE: dict[str, Any] = {
    "filesystem": {"allowWrite": ["/x"], "denyWrite": ["/y"]},
    "network": {"allowedDomains": ["example.org"]},
}
# The arguments with which a boxed child starts every git: srt with the profile, then git with
# WT_OPTIONS.
WT_BOXED = [WT_SRT, "--settings", WT_PROFILE, "--", "git", *WT_OPTIONS]
# The stub srt: it appends its arguments as one line to WT_SRT_LOG, drops its options up to `--`,
# and runs the rest with the environment that it got, as srt 0.0.81 does. STUB_SRT_MODE breaks one
# step: `fail-add` runs a `worktree add` and exits 3; `fail-repair` exits 3 on a `worktree repair`,
# and `fail-repair-branch` also on a `branch -D`, without running either; `link-after-add`
# replaces the staged directory of a `worktree add` by a link to the empty `wt-empty`;
# `final-after-add` makes the final path of a `worktree add`, with a file `found` in it; `wrong-git`
# writes a `.git` file that names the worktree `Ssh-x` of another repository after a `worktree
# repair`, and points the admin `gitdir` of `Ssh-x` back at it, so that the `.git` file is a valid
# one of `Ssh`.
STUB_SRT = f"""#!/bin/sh
printf '%s\\n' "$*" >> '{WT_SRT_LOG}'
while [ "$#" -gt 0 ] && [ "$1" != -- ]; do shift; done
shift
case "${{STUB_SRT_MODE-}}:$*" in
"fail-add:"*" worktree add "*) "$@"; exit 3 ;;
"fail-repair:"*" worktree repair "* | "fail-repair-branch:"*" worktree repair "*) exit 3 ;;
"fail-repair-branch:"*" branch -D "*) exit 3 ;;
esac
"$@"
status=$?
case "${{STUB_SRT_MODE-}}:$*" in
"link-after-add:"*" worktree add "*)
    for a; do
        case $a in */worktree-stage/*) rm -rf "$a"; ln -s '{FIXTURE.name}/wt-empty' "$a" ;; esac
    done ;;
"final-after-add:"*" worktree add "*)
    for a; do
        case $a in */worktree-stage/*) mkdir "{WT_ROOT}/${{a##*/}}"; : > "{WT_ROOT}/${{a##*/}}/found" ;; esac
    done ;;
"wrong-git:"*" worktree repair "*)
    for a; do last=$a; done
    printf 'gitdir: %s\\n' '{WT_R}/Ssh/.git/worktrees/Ssh-x' > "$last/.git"
    real=$(cd "$last" && pwd -P)
    case $real in //*) real=${{real#/}} ;; esac
    printf '%s/.git\\n' "$real" > '{WT_R}/Ssh/.git/worktrees/Ssh-x/gitdir' ;;
esac
exit "$status"
"""


def worktree_fixture() -> None:
    """Make the repositories, the links and the logging `git` of WT_HOME's fixture."""
    git = shutil.which("git") or "git"
    env = {
        **WORKTREE_ENV,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "probe",
        "GIT_AUTHOR_EMAIL": "probe@example.org",
        "GIT_COMMITTER_NAME": "probe",
        "GIT_COMMITTER_EMAIL": "probe@example.org",
    }

    def run(*args: str) -> None:
        subprocess.run(
            [git, "-c", "core.hooksPath=/dev/null", *args],
            env=env,
            check=True,
            capture_output=True,
            timeout=60,
        )

    source = pathlib.Path(FIXTURE.name, "wt-source")
    hook = source / ".githooks" / "post-checkout"
    hook.parent.mkdir(parents=True)
    hook.write_text(f"#!/bin/sh\n: > '{WT_MARKER}'\n", encoding="utf-8")
    hook.chmod(0o755)
    run("init", "-q", "-b", "main", str(source))
    run("-C", str(source), "add", ".githooks")
    run("-C", str(source), "commit", "-q", "-m", "fixture")
    run("clone", "-q", "--bare", str(source), WT_ORIGIN)
    pathlib.Path(WT_ROOT).mkdir(parents=True)
    run("clone", "-q", WT_ORIGIN, WT_REPO)
    run("-C", WT_REPO, "remote", "set-url", "origin", "ssh://fixture" + WT_ORIGIN)
    for key, value in WT_KEYS:
        run("-C", WT_REPO, "config", key, value)
    for name in ("common", "gitdir", "via", "rel"):
        run("-C", WT_REPO, "worktree", "add", "-q", "--detach", f"{WT_ROOT}/Repo-{name}")
    admin = pathlib.Path(WT_REPO, ".git", "worktrees")
    common = pathlib.Path(WT_REPO, ".git").resolve()
    (admin / "Repo-common" / "commondir").write_text(f"{common}\n", encoding="utf-8")
    (admin / "Repo-gitdir" / "gitdir").write_text(f"{FIXTURE.name}/elsewhere/.git\n", encoding="utf-8")
    # A `.git` file as `git worktree add --relative-paths` writes it, and a relative admin `gitdir`;
    # git writes `../../../../.worktrees/Repo-rel/.git` there, but the case refuses at the `.git` line.
    pathlib.Path(WT_ROOT, "Repo-rel", ".git").write_text(WT_RELATIVE + "\n", encoding="utf-8")
    (admin / "Repo-rel" / "gitdir").write_text("../../../.worktrees/Repo-rel/.git\n", encoding="utf-8")
    run("-C", WT_REPO, "config", "core.hooksPath", ".githooks")
    pathlib.Path(WT_R, "Linked").mkdir()
    pathlib.Path(WT_R, "Linked", ".git").symlink_to(pathlib.Path(WT_REPO, ".git"))
    linked = pathlib.Path(WT_R, "Linked").resolve()
    pathlib.Path(WT_ROOT, "Repo-via", ".git").write_text(
        f"gitdir: {linked}/.git/worktrees/Repo-via\n", encoding="utf-8"
    )
    pathlib.Path(FIXTURE.name, "wt-empty").mkdir()
    pathlib.Path(WT_ROOT, "Repo-linked").symlink_to(pathlib.Path(FIXTURE.name, "wt-empty"))
    run("init", "-q", "-b", "main", WT_OUTSIDE)
    run("-C", WT_OUTSIDE, "commit", "-q", "--allow-empty", "-m", "fixture")
    run("-C", WT_OUTSIDE, "worktree", "add", "-q", "--detach", f"{WT_ROOT}/Outside-x")
    # `Common`, whose `.git` holds a `commondir` that names `Repo/.git`, and its worktree
    # `.worktrees/Common-x`, made before the `commondir` was written.
    common = WT_R + "/Common"
    run("init", "-q", "-b", "main", common)
    run("-C", common, "commit", "-q", "--allow-empty", "-m", "fixture")
    run("-C", common, "worktree", "add", "-q", "--detach", f"{WT_ROOT}/Common-x")
    pathlib.Path(common, ".git", "commondir").write_text(
        f"{pathlib.Path(WT_REPO, '.git').resolve()}\n", encoding="utf-8"
    )
    for name, key, value in WT_REFUSED:
        run("init", "-q", "-b", "main", f"{WT_R}/{name}")
        run("-C", f"{WT_R}/{name}", "commit", "-q", "--allow-empty", "-m", "fixture")
        run("-C", f"{WT_R}/{name}", "worktree", "add", "-q", "--detach", f"{WT_ROOT}/{name}-x")
        run("-C", f"{WT_R}/{name}", "config", key, value)
    for name, data, _ in WT_RAW:
        run("init", "-q", "-b", "main", f"{WT_R}/{name}")
        pathlib.Path(WT_R, name, ".git", "config").write_bytes(data)
    run("init", "-q", "-b", "main", WT_EVIL)
    run("-C", WT_EVIL, "commit", "-q", "--allow-empty", "-m", "fixture")
    run("-C", WT_EVIL, "remote", "add", "origin", "ssh://fixture" + WT_ORIGIN)
    run("-C", WT_EVIL, "config", "core.sshCommand", WT_EVIL_SSH)
    allowed = "[core]\n\trepositoryformatversion = 0\n"
    for sub in ("sub", "bare"):
        dot = pathlib.Path(WT_EVIL, sub, ".git")
        dot.mkdir(parents=True)
        (dot / "config").write_text(allowed, encoding="utf-8")
    bare = pathlib.Path(WT_EVIL, "bare")
    (bare / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (bare / "objects").mkdir()
    (bare / "refs").mkdir()
    (bare / "config").write_text(
        f'{allowed}\tbare = true\n\tsshCommand = "{WT_EVIL_SSH}"\n[remote "origin"]\n'
        f"\turl = ssh://fixture{WT_ORIGIN}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n",
        encoding="utf-8",
    )
    run("init", "-q", "--bare", WT_COMMON)
    run("-C", WT_COMMON, "remote", "add", "origin", "ssh://fixture" + WT_ORIGIN)
    run("-C", WT_COMMON, "config", "core.sshCommand", WT_EVIL_SSH)
    wrapper = pathlib.Path(WT_BIN, "git")
    wrapper.parent.mkdir()
    wrapper.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{WT_LOG}'\nexec '{git}' \"$@\"\n", encoding="utf-8"
    )
    wrapper.chmod(0o755)
    # The ssh of GIT_SSH_VARIANT=simple: git gives it the host and the remote command
    # `git-upload-pack '<path>'`, which it logs and runs with the real git, not the logging one.
    ssh = pathlib.Path(WT_BIN, "fake-ssh")
    ssh.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{WT_SSH}'\n"
        'for last; do :; done\neval "set -- $last"\n'
        f'exec \'{git}\' "${{1#git-}}" "$2"\n',
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    pathlib.Path(WT_SOCKETS).mkdir()
    srt = pathlib.Path(WT_SRT)
    srt.parent.mkdir(parents=True)
    srt.write_text(STUB_SRT, encoding="utf-8")
    srt.chmod(0o755)
    pathlib.Path(WT_STAGE).mkdir(parents=True, mode=0o700)
    pathlib.Path(WT_PROFILE).write_text(json.dumps(WT_SETTINGS_VALUE), encoding="utf-8")
    pathlib.Path(WT_SETTINGS).write_text(json.dumps(WT_SETTINGS_VALUE), encoding="utf-8")


def worktree_run(
    payload: dict[str, str], env: dict[str, str], args: tuple[str, ...] = ()
) -> tuple[subprocess.CompletedProcess[str] | None, list[str]]:
    """`worktree.py` with `args` on the JSON text of `payload` in `env`, and the arguments of each
    git that the logging `git` started meanwhile, one string each."""
    log = pathlib.Path(WT_LOG)
    log.unlink(missing_ok=True)
    proc = call(WORKTREE, json.dumps(payload), env, args)
    return proc, log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def boxed_run(
    payload: dict[str, str], mode: str = ""
) -> tuple[subprocess.CompletedProcess[str] | None, list[str], list[str]]:
    """`worktree.py --boxed WT_PROFILE` on `payload` in WT_ENV, with the stub srt's STUB_SRT_MODE
    `mode`: the process, the arguments of each git that the logging `git` started, and the
    arguments of each call of the stub srt."""
    log = pathlib.Path(WT_SRT_LOG)
    log.unlink(missing_ok=True)
    proc, started = worktree_run(payload, {**WT_ENV, "STUB_SRT_MODE": mode}, ("--boxed", WT_PROFILE))
    return proc, started, log.read_text(encoding="utf-8").splitlines() if log.exists() else []


class Broker(NamedTuple):
    """A broker that `start_broker` started: its parent shell, its process ID and its socket."""

    parent: subprocess.Popen[str]
    pid: int
    socket: pathlib.Path


def start_broker(name: str) -> Broker:
    """`worktree.py --serve` at WT_SOCKETS/<name>.sock with the settings file WT_SETTINGS in WT_ENV,
    as the child of a shell that runs BROKER_PARENT; its output goes to WT_SOCKETS/<name>.log."""
    path = pathlib.Path(WT_SOCKETS, f"{name}.sock")
    log = str(path.with_suffix(".log"))
    parent = subprocess.Popen(  # no timeout: stop_broker ends it by closing its stdin
        ["/bin/sh", "-c", BROKER_PARENT, sys.executable, WORKTREE, str(path), log, WT_SETTINGS],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=WT_ENV,
    )
    line = parent.stdout.readline() if parent.stdout is not None else ""
    return Broker(parent, int(line), path)


def ended(pid: int) -> bool:
    """Whether no process `pid` runs."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def stop_broker(broker: Broker) -> None:
    """End the broker's parent, and the broker where it still runs."""
    if broker.parent.stdin is not None and not broker.parent.stdin.closed:
        broker.parent.stdin.close()
    broker.parent.wait(timeout=TIMEOUT)
    if broker.parent.stdout is not None:
        broker.parent.stdout.close()
    if not ended(broker.pid):
        with contextlib.suppress(ProcessLookupError):
            os.kill(broker.pid, signal.SIGTERM)


def until(condition: Callable[[], bool], seconds: float) -> bool:
    """Whether `condition` holds within `seconds`, looked at every 50 ms."""
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def is_socket(path: pathlib.Path) -> bool:
    try:
        return stat.S_ISSOCK(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def answers(path: pathlib.Path) -> bool:
    """Whether a process accepts a connection at the socket `path`."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        try:
            s.connect(str(path))
        except OSError:
            return False
    return True


def unix_bind(path: str) -> None:
    """Bind an AF_UNIX socket at `path`, and close it."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.bind(path)


def bind_verdict(bind: Callable[[str], None], *, ci: bool) -> tuple[str, str]:
    """Whether the cases that bind an AF_UNIX socket run here, from one `bind` at a short path in a
    fresh private temporary directory: ("run", ""), or ("skip", <errno text>) where it raises
    PermissionError, as in a session's sandbox; with `ci`, which says that CI runs the cases, a
    refusal is ("wrong", <errno text>)."""
    with tempfile.TemporaryDirectory() as directory:
        try:
            bind(str(pathlib.Path(directory, "s")))
        except PermissionError as err:
            return ("wrong" if ci else "skip"), err.strerror or str(err)
    return "run", ""


def request(path: pathlib.Path, data: bytes) -> dict[str, Any] | None:
    """The JSON object of the first line that the broker at `path` replies to the line `data`, or
    None where it gives none. A broker may close the connection before it has read the whole of a
    large request, and Linux then resets it: the bytes read before the reset stay, and the reading
    stops at the reply's newline."""
    received = b""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect(str(path))
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                s.sendall(data + b"\n")
                s.shutdown(socket.SHUT_WR)
            with contextlib.suppress(ConnectionResetError):
                while b"\n" not in received and (chunk := s.recv(65536)):
                    received += chunk
    except OSError:
        return None
    try:
        value = json_value(received.split(b"\n", 1)[0].decode("utf-8", "replace"), "the reply")
    except ValueError:
        return None
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def broker_unit_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """The broker's answers and the client's reading of a reply, in this process and with no socket
    bound: a create whose process cannot start gets an `error` reply, also through `answer` on a
    socket pair; the create runs with GIT_TERMINAL_PROMPT=0 and without AGENTBOX; a request of more
    than LIMIT bytes, also a valid object followed by white space, gets an error that names the
    limit and starts nothing; and a reply whose `path`, `error` or `stderr` is no string is
    refused."""
    payload = json.dumps({"hook_event_name": "WorktreeCreate", "cwd": WT_REPO, "name": "unit"}).encode()
    absent = str(pathlib.Path(WT_SOCKETS, "no-python"))
    profile = pathlib.Path(WT_PROFILE)
    try:
        with mock.patch.object(sys, "executable", absent):
            reply: object = hook.respond(payload, profile)
    except (OSError, TypeError) as err:
        reply = err
    error = getattr(reply, "error", None)
    report(
        isinstance(error, str) and absent in error and getattr(reply, "path", None) == "",
        f"a create whose process cannot start gets an error that names the interpreter: {reply!r}",
    )
    ours, theirs = socket.socketpair()
    with ours, theirs:
        theirs.settimeout(TIMEOUT)
        theirs.sendall(payload + b"\n")
        theirs.shutdown(socket.SHUT_WR)
        try:
            with mock.patch.object(sys, "executable", absent):
                hook.answer(ours, profile)
            outcome = "answered"
        except (OSError, TypeError) as err:
            outcome = repr(err)
        sending = ours.gettimeout()
        ours.shutdown(socket.SHUT_WR)
        sent = theirs.recv(65536)
    line = json_object(sent.decode("utf-8", "replace"))
    report(
        line is not None
        and isinstance(line.get("error"), str)
        and absent in str(line["error"])
        and "path" not in line
        and sending == getattr(hook, "LOCAL", None),
        f"answer sends that error as one JSON line, with a timeout of LOCAL seconds: {outcome}, {sent!r}, "
        f"timeout {sending}",
    )

    runs: list[dict[str, str]] = []
    argv: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        runs.append(dict(kwargs.get("env") or {}))
        argv.append([str(a) for a in args])
        return subprocess.CompletedProcess(args, 0, f"{WT_ROOT}/Repo-unit\n", "said\n")

    with (
        mock.patch.dict(os.environ, {**WT_ENV, "AGENTBOX": "1", "AGENTBOX_BROKER": "/x.sock"}, clear=True),
        mock.patch.object(subprocess, "run", side_effect=run),
    ):
        try:
            reply = hook.respond(payload, profile)
            valid = len(runs)
            big = [
                hook.respond(
                    json.dumps({"hook_event_name": "WorktreeCreate", "pad": "x" * 70 * 1024}).encode(),
                    profile,
                ),
                hook.respond(payload + b" " * 70 * 1024, profile),
            ]
            after_big = len(runs)
            other = hook.respond(b'{"hook_event_name": "Other", "cwd": "/"}', profile)
        except TypeError as err:
            reply, valid, big, after_big, other = err, len(runs), [err, err], len(runs), err
        after_other = len(runs)
    env = runs[0] if valid == 1 else {}
    report(
        valid == 1 and argv[0][1:] == [str(pathlib.Path(WORKTREE).absolute()), "--boxed", WT_PROFILE],
        f"the broker starts a create as worktree.py --boxed <profile>: {argv[:1]}",
    )
    report(
        "Other" in str(getattr(other, "error", None)) and after_other == after_big,
        f"a request of hook_event_name Other gets an error that names it and starts nothing: {other!r}, "
        f"{after_other - after_big} runs",
    )
    report(
        getattr(reply, "path", None) == f"{WT_ROOT}/Repo-unit"
        and getattr(reply, "stderr", None) == "said\n"
        and getattr(reply, "error", "") is None
        and env.get("GIT_TERMINAL_PROMPT") == "0"
        and "AGENTBOX" not in env
        and "AGENTBOX_BROKER" not in env,
        f"the broker runs a create with GIT_TERMINAL_PROMPT=0 and without AGENTBOX and AGENTBOX_BROKER, "
        f"and replies its path and stderr: {reply!r}, {len(runs)} runs, "
        f"{ {k: env.get(k) for k in ('GIT_TERMINAL_PROMPT', 'AGENTBOX', 'AGENTBOX_BROKER')} }",
    )
    report(
        all(f"larger than {64 * 1024} bytes" in str(getattr(r, "error", None)) for r in big)
        and after_big == valid,
        f"a request of more than 64 KiB, inside the object or after it, gets an error that names the "
        f"limit and starts nothing: {[getattr(r, 'error', r) for r in big]}, {after_big - valid} runs",
    )
    receive_deadline_cases(hook, report)
    fetch_retry_cases(hook, report)
    deletable_cases(hook, report)

    read = getattr(hook, "read_reply", None)
    for text, want in [
        (b'{"path": "/p", "stderr": "s\\n"}', ("/p", None, "s\n")),
        (b'{"error": "no", "stderr": ""}', ("", "no", "")),
        (b'{"path": 1, "stderr": ""}', None),
        (b'{"error": null, "stderr": ""}', None),
        (b'{"error": ["no"], "stderr": ""}', None),
        (b'{"path": "/p", "stderr": 2}', None),
        (b"[1]", None),
    ]:
        try:
            value = read(text, "the reply") if read is not None else "no read_reply"
            got: object = (value.path, value.error, value.stderr) if not isinstance(value, str) else value
        except (hook.Refusal, hook.HarnessError) as err:
            got = f"refused: {err}"
        report(
            got == want if want is not None else str(got).startswith("refused: "),
            f"the client reads the reply {text!r} as {want or 'a refusal'}: {got!r}",
        )
    reply_type = getattr(hook, "Reply", None)
    for fields, want_line in [
        ({"path": "/p", "stderr": "s"}, {"path": "/p", "stderr": "s"}),
        ({"error": "no", "stderr": "s"}, {"error": "no", "stderr": "s"}),
    ]:
        sent = reply_type(**fields).line() if reply_type is not None else b""
        report(
            sent.endswith(b"\n") and sent.count(b"\n") == 1 and json_object(sent.decode()) == want_line,
            f"the broker sends {fields} as the one JSON line {want_line}: {sent!r}",
        )


class DripClock:
    """A clock that advances by `step` seconds at each reading, from 0."""

    def __init__(self, step: float) -> None:
        self.step = step
        self.now = -step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


class DripConnection:
    """A connection whose `recv` returns one byte at each call, for at most 20 calls, and which
    records each timeout that it is given with the time of `clock` at that moment."""

    def __init__(self, clock: DripClock) -> None:
        self.clock = clock
        self.timeouts: list[tuple[float, float]] = []
        self.reads = 0

    def settimeout(self, value: float) -> None:
        self.timeouts.append((value, self.clock.now))

    def recv(self, size: int) -> bytes:
        del size
        self.reads += 1
        return b"x" if self.reads <= 20 else b""


def fetch_retry_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`fetch` runs the fetch again only while it fails on a ref's lock, at most FETCHES times with
    a pause between runs, and passes the last run's stderr through; any other failure refuses at
    once."""
    locked = "error: cannot lock ref 'refs/remotes/origin/main': is at a but expected b\n"
    for results, runs, outcome in (
        ([(1, locked), (0, "")], 2, "fetched"),
        ([(1, locked)] * 3, 3, "refused"),
        ([(128, "fatal: unable to access\n")], 1, "refused"),
        ([(0, "")], 1, "fetched"),
    ):
        calls: list[tuple[str, ...]] = []
        pauses: list[float] = []
        answers = iter(results)

        def fake(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
            del kwargs
            calls.append(args)
            code, err = next(answers)
            return subprocess.CompletedProcess(list(args), code, "", err)

        stderr = io.StringIO()
        with (
            mock.patch.object(hook, "run_git", side_effect=fake),
            mock.patch.object(hook.time, "sleep", side_effect=pauses.append),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                hook.fetch(pathlib.Path("/repo"))
                got = "fetched"
            except hook.Refusal:
                got = "refused"
        last_err = results[-1][1]
        report(
            got == outcome
            and len(calls) == runs
            and all(c == ("fetch", "--quiet", "origin") for c in calls)
            and pauses == [hook.PAUSE] * (runs - 1)
            and stderr.getvalue() == last_err,
            f"a fetch that answers {[code for code, _ in results]} runs {runs} times with "
            f"{runs - 1} pauses and is {outcome}, with the last run's stderr: {got}, {len(calls)} "
            f"runs, pauses {pauses}, stderr {stderr.getvalue()!r}",
        )


def deletable_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`deletable` passes a tree whose `.githooks` and `.claude` it can write in, and leaves no file
    there; it refuses, naming the directory, where one of them, also a nested one, has mode 500;
    `.git` and other directories of mode 500 are not tested."""
    with tempfile.TemporaryDirectory() as name:
        tree = pathlib.Path(name, "Repo-x")
        for sub in (".githooks", ".claude", "src/.claude", ".git/hooks", "locked"):
            (tree / sub).mkdir(parents=True)
        for case, locked, refused in (
            ("writable", None, None),
            ("a .githooks of mode 500", ".githooks", ".githooks"),
            ("a nested .claude of mode 500", "src/.claude", "src/.claude"),
            ("a .git and another directory of mode 500", ".git", None),
        ):
            shut = [tree / locked] if locked else []
            if locked == ".git":
                shut.append(tree / "locked")
            for directory in shut:
                directory.chmod(0o500)
            try:
                hook.deletable(tree)
                got = None
            except hook.Refusal as err:
                got = str(err)
            finally:
                for directory in shut:
                    directory.chmod(0o700)
            left = sorted(str(p.relative_to(tree)) for p in tree.rglob(".worktree-hook-*"))
            report(
                (got is None if refused is None else got is not None and str(tree / refused) in got)
                and not left,
                f"deletable on a tree with {case}: refuses {refused}, leaves no probe file: {got!r}, {left}",
            )
    calls: list[tuple[str, ...]] = []

    def refuse(tree: pathlib.Path) -> None:
        raise hook.Refusal(f"cannot write in {tree}")

    def record(*args: str, **kwargs: object) -> str:
        del kwargs
        calls.append(args)
        return ""

    with (
        mock.patch.object(hook, "main_checkout", return_value=pathlib.Path("/repo")),
        mock.patch.object(hook, "checked_config"),
        mock.patch.object(hook, "registered", return_value=True),
        mock.patch.object(hook, "deletable", side_effect=refuse),
        mock.patch.object(hook, "git", side_effect=record),
    ):
        try:
            hook.remove({"worktree_path": str(hook.ROOT / "Repo-x")})
            outcome = "removed"
        except hook.Refusal as err:
            outcome = str(err)
    report(
        outcome.startswith("cannot write in") and not calls,
        f"remove runs no git once deletable refuses: {outcome!r}, git calls {calls}",
    )


def receive_deadline_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`receive` bounds the whole read by its deadline: a client that sends one byte per read, while
    the clock advances by a quarter of LOCAL per reading, gets TimeoutError within 5 reads, and
    each timeout that a read gets is at most the time left."""
    local = float(getattr(hook, "LOCAL", 60))
    clock = DripClock(local / 4)
    connection = DripConnection(clock)
    try:
        hook.receive(connection, getattr(hook, "LIMIT", 65536), local, clock)
        outcome = "returned"
    except TimeoutError:
        outcome = "TimeoutError"
    except TypeError as err:
        outcome = f"TypeError: {err}"
    report(
        outcome == "TimeoutError"
        and connection.reads <= 5
        and connection.timeouts
        and all(0 < value <= local - now for value, now in connection.timeouts),
        f"a client that sends one byte per read gets TimeoutError within 5 reads, each read with a "
        f"timeout of at most the time left before the deadline {local}: {outcome}, {connection.reads} "
        f"reads, timeouts {connection.timeouts}",
    )


def config_check_cases(report: Callable[[object, str], None]) -> None:
    """The refusals of `worktree.py` for the git config that its git would read, on the fixture of
    `worktree_fixture`: a create and a remove in `Common`, whose `.git` holds `commondir`, start no
    git; a create and a remove in each repository of WT_REFUSED, and a create in each of WT_RAW,
    start only the config read; each exits 1 with one line that names the cause; then
    `config_key_cases`."""

    def said(proc: subprocess.CompletedProcess[str] | None) -> str:
        return "timeout" if proc is None else f"exit {proc.returncode}, {proc.stdout!r}, {proc.stderr!r}"

    def create(cwd: str) -> dict[str, str]:
        return {"hook_event_name": "WorktreeCreate", "cwd": cwd, "name": "config"}

    def remove(name: str) -> dict[str, str]:
        return {"hook_event_name": "WorktreeRemove", "worktree_path": f"{WT_ROOT}/{name}-x"}

    for label, payload in [
        ("a create in a repository whose .git holds commondir", create(WT_R + "/Common")),
        ("a remove of a worktree of a repository whose .git holds commondir", remove("Common")),
    ]:
        proc, started = worktree_run(payload, WT_ENV)
        report(
            proc is not None
            and proc.returncode == 1
            and proc.stderr.count("\n") == 1
            and "commondir" in proc.stderr
            and not started,
            f"{label}: exits 1 with one line that names commondir, and starts no git: {said(proc)}, {started}",
        )

    def refused(label: str, payload: dict[str, str], word: str, worktree: str, *, stays: bool) -> None:
        proc, started = worktree_run(payload, WT_ENV)
        report(
            proc is not None
            and proc.returncode == 1
            and proc.stderr.count("\n") == 1
            and proc.stderr.startswith("worktree hook: ")
            and word in proc.stderr
            and len(started) == 1
            and " config --file " in started[0]
            and pathlib.Path(WT_ROOT, worktree).is_dir() == stays,
            f"{label}: exits 1 with one line that names {word}, and starts only the config read: "
            f"{said(proc)}, {started}",
        )

    for name, key, _ in WT_REFUSED:
        word = key.lower()
        where = f"a repository whose .git/config holds {key}"
        refused(f"a create in {where}", create(f"{WT_R}/{name}"), word, f"{name}-config", stays=False)
        refused(f"a remove of a worktree of {where}", remove(name), word, f"{name}-x", stays=True)
    for name, _, word in WT_RAW:
        label = f"a create in {name}, whose .git/config git cannot read or is no UTF-8"
        refused(label, create(f"{WT_R}/{name}"), word, f"{name}-config", stays=False)
    config_key_cases(load_module("worktree_keys", WORKTREE), report)


def config_key_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`allowed` on the keys and values of `.git/config` that the fixture's repositories do not
    hold: a key that splits at its first and last dot, an empty subsection, a key of an allowed
    name in another section or below a subsection of `core`, a URL key with no value, and the
    URLs that `remote_url` refuses or accepts."""
    allowed = getattr(hook, "allowed", None)
    for key, value, want in [
        ("remote.a.b.url", "https://example.org/x.git", True),
        ("branch.feature/x.y.merge", "refs/heads/x", True),
        ("branch..remote", "origin", False),
        ("core.x.hookspath", ".githooks", False),
        ("user.x.name", "probe", False),
        ("other.a.remote", "origin", False),
        ("remote.a.url", None, False),
        ("remote.a.url", "host:path/x.git", True),
        ("remote.a.url", "git@host.org:x.git", True),
        ("remote.a.url", "ssh://host.org/x.git", True),
        ("remote.a.url", "file:///x.git", False),
        ("remote.a.url", "ext::sh -c x", False),
        ("remote.a.url", "a/b:c", False),
        ("remote.a.url", "-oProxyCommand=x:y", False),
        ("remote.a.url", "/x.git", False),
        ("remote.a.pushurl", "fd::3", False),
    ]:
        try:
            got: object = allowed(key, value) if allowed is not None else "no allowed"
        except (AttributeError, TypeError) as err:
            got = repr(err)
        report(got is want, f"the config check gives {want} for {key} = {value!r}: {got}")


def discovery_cases(report: Callable[[object, str], None]) -> None:
    """git pinned to the repository that `worktree.py` checked, on the fixture of WT_EVIL: a create
    from `Evil/sub`, whose `.git` git does not take as a repository, and from `Evil/bare`, which git
    takes as a bare repository, each exit 1 with git's `not a git repository` and run no
    `core.sshCommand`; and a create and remove of `Repo` recorded in this process, where the caller
    sets GIT_COMMON_DIR to WT_COMMON and GIT_WORK_TREE, give every git GIT_DIR `Repo/.git` and
    neither variable, and run no `core.sshCommand` of WT_COMMON."""
    marker = pathlib.Path(WT_EVIL_MARKER)

    def said(proc: subprocess.CompletedProcess[str] | None) -> str:
        return "timeout" if proc is None else f"exit {proc.returncode}, {proc.stdout!r}, {proc.stderr!r}"

    for sub, label in [
        ("sub", "whose .git git does not take as a repository, below a repository"),
        ("bare", "which git takes as a bare repository, below a repository"),
    ]:
        marker.unlink(missing_ok=True)
        payload = {"hook_event_name": "WorktreeCreate", "cwd": f"{WT_EVIL}/{sub}", "name": "evil"}
        proc, _ = worktree_run(payload, WT_EVIL_ENV)
        report(
            proc is not None
            and proc.returncode == 1
            and "not a git repository" in proc.stderr
            and not marker.exists()
            and not pathlib.Path(WT_ROOT, f"{sub}-evil").exists(),
            f"a create in Evil/{sub}, {label}: exits 1 with git's `not a git repository`, and runs no "
            f"core.sshCommand: {said(proc)}, marker {marker.exists()}",
        )

    hook = load_module("worktree_pinned", WORKTREE)
    envs: list[dict[str, str]] = []
    real = subprocess.Popen

    def record(args: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        envs.append(dict(kwargs.get("env") or os.environ))
        return real(args, **kwargs)

    marker.unlink(missing_ok=True)
    tree = pathlib.Path(WT_HOME, "other-tree")
    tree.mkdir()
    caller = {**WT_EVIL_ENV, "GIT_COMMON_DIR": WT_COMMON, "GIT_WORK_TREE": str(tree)}
    err = io.StringIO()
    with (
        mock.patch.dict(os.environ, caller, clear=True),
        mock.patch.object(subprocess, "Popen", side_effect=record),
        mock.patch.object(hook, "RESEARCH", pathlib.Path(WT_R)),
        mock.patch.object(hook, "ROOT", pathlib.Path(WT_ROOT)),
        contextlib.redirect_stderr(err),
    ):
        try:
            path = hook.create({"hook_event_name": "WorktreeCreate", "cwd": WT_REPO, "name": "pinned"})
            hook.remove({"worktree_path": str(path)})
            outcome = "made and removed"
        except hook.Refusal as e:
            outcome = str(e)
    pinned = str(pathlib.Path(WT_REPO, ".git").resolve())
    report(
        outcome == "made and removed"
        and envs
        and all(
            e.get("GIT_DIR") == pinned and "GIT_COMMON_DIR" not in e and "GIT_WORK_TREE" not in e
            for e in envs
        )
        and not marker.exists()
        and not any(tree.iterdir()),
        f"where the caller sets GIT_COMMON_DIR and GIT_WORK_TREE, every git that the hook starts gets "
        f"GIT_DIR {pinned} and neither variable, and runs no core.sshCommand of that common directory: "
        f"{outcome}, {[(e.get('GIT_DIR'), e.get('GIT_COMMON_DIR'), e.get('GIT_WORK_TREE')) for e in envs]}, "
        f"marker {marker.exists()}",
    )


def no_repository_cases(report: Callable[[object, str], None]) -> None:
    """A create whose `cwd` is the root of the tree, as Claude Desktop sends for a session there, or
    a directory below it in no repository, exits 1 with one line that names the side-session route:
    `use_worktree false`, a cwd in the repository, and `EnterWorktree`."""
    plain = pathlib.Path(WT_R, "Plain")
    plain.mkdir(exist_ok=True)
    for cwd, said_first in (
        (WT_R, "is the root of the tree, no repository"),
        (str(plain), "is inside no repository below"),
    ):
        proc, _ = worktree_run({"hook_event_name": "WorktreeCreate", "cwd": cwd, "name": "x"}, WT_ENV)
        lines = [] if proc is None else proc.stderr.splitlines()
        report(
            proc is not None
            and proc.returncode == 1
            and len(lines) == 1
            and said_first in lines[0]
            and "use_worktree false" in lines[0]
            and "EnterWorktree" in lines[0],
            f"a create from {cwd} exits 1 with one line that names the side-session route: "
            f"{None if proc is None else (proc.returncode, proc.stderr)!r}",
        )


def stage_state(stage: pathlib.Path) -> tuple[int, list[str]] | None:
    """The mode and the sorted entries of the staging directory `stage`, or None where it is no
    directory or a link."""
    if stage.is_symlink() or not stage.is_dir():
        return None
    return stat.S_IMODE(stage.stat().st_mode), sorted(p.name for p in stage.iterdir())


def profile_state(profile: pathlib.Path) -> tuple[int, object] | None:
    """The mode and the JSON value of the profile file `profile`, or None where it is no file."""
    if profile.is_symlink() or not profile.is_file():
        return None
    try:
        value = json_value(profile.read_text(encoding="utf-8"), str(profile))
    except ValueError as err:
        value = repr(err)
    return stat.S_IMODE(profile.stat().st_mode), value


def profiled(stage: pathlib.Path) -> dict[str, Any]:
    """WT_SETTINGS_VALUE with `stage` appended to its `filesystem.allowWrite`."""
    filesystem = cast("dict[str, Any]", WT_SETTINGS_VALUE["filesystem"])
    return {
        **WT_SETTINGS_VALUE,
        "filesystem": {**filesystem, "allowWrite": [*filesystem["allowWrite"], str(stage)]},
    }


def listed(path: pathlib.Path) -> bool:
    """Whether `git worktree list` of `Repo` names `path`, resolved."""
    proc = subprocess.run(
        ["git", "-C", WT_REPO, "worktree", "list", "--porcelain"],  # noqa: S607 -- the `git` on PATH
        capture_output=True,
        text=True,
        env=WORKTREE_ENV,
        timeout=60,
        check=False,
    )
    return f"worktree {path.resolve()}" in proc.stdout.splitlines()


def linked(path: pathlib.Path) -> bool:
    """Whether the `.git` file of the worktree `path` names an admin directory whose `gitdir` names
    that `.git` file, resolved, as git writes them."""
    dot = path.resolve() / ".git"
    if not dot.is_file():
        return False
    admin = pathlib.Path(dot.read_text(encoding="utf-8").strip().removeprefix("gitdir: "))
    gitdir = admin / "gitdir"
    return gitdir.is_file() and gitdir.read_text(encoding="utf-8").strip() == str(dot)


def via_srt(line: str) -> bool:
    """Whether a line of the stub srt's log starts with `--settings WT_PROFILE -- git` and WT_OPTIONS."""
    return line.split()[: len(WT_BOXED) - 1] == WT_BOXED[1:]


def stage_empty() -> bool:
    """Whether the staging directory WT_STAGE is an empty directory."""
    return stage_state(pathlib.Path(WT_STAGE)) == (0o700, [])


def said(proc: subprocess.CompletedProcess[str] | None) -> str:
    """The exit status, stdout and stderr of `proc`, or `timeout`."""
    return "timeout" if proc is None else f"exit {proc.returncode}, {proc.stdout!r}, {proc.stderr!r}"


def last(proc: subprocess.CompletedProcess[str] | None) -> str:
    """The last line of the stderr of `proc`."""
    return (proc.stderr.splitlines() or [""])[-1] if proc is not None else ""


def create(name: str) -> dict[str, str]:
    """The payload of a create of the worktree `name` of `Repo`."""
    return {"hook_event_name": "WorktreeCreate", "cwd": WT_REPO, "name": name}


def remove(name: str) -> dict[str, str]:
    """The payload of a remove of the worktree `Repo-<name>`."""
    return {"hook_event_name": "WorktreeRemove", "worktree_path": f"{WT_ROOT}/Repo-{name}"}


def inprocess(
    hook: types.ModuleType, work: Callable[[], object], *patches: contextlib.AbstractContextManager[object]
) -> tuple[str, list[list[str]]]:
    """`work` in this process with the hook's ROOT, RESEARCH and SRT those of the fixture, and
    `patches`: its outcome, and the arguments of each process that the hook started."""
    seen: list[list[str]] = []
    real = subprocess.Popen

    def record(args: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        seen.append([str(a) for a in args])
        return real(args, **kwargs)

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, WT_ENV, clear=True))
        stack.enter_context(mock.patch.object(subprocess, "Popen", side_effect=record))
        stack.enter_context(mock.patch.object(hook, "RESEARCH", pathlib.Path(WT_R)))
        stack.enter_context(mock.patch.object(hook, "ROOT", pathlib.Path(WT_ROOT)))
        stack.enter_context(mock.patch.object(hook, "SRT", pathlib.Path(WT_SRT), create=True))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        for patch in patches:
            stack.enter_context(patch)
        try:
            outcome = f"done: {work()}"
        except (hook.Refusal, hook.HarnessError, TypeError, AttributeError, OSError) as err:
            outcome = f"refused: {err}"
    return outcome, seen


def boxed_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`worktree.py --boxed <profile>` with the stub srt: a create and a remove of `Repo` through
    the staging directory, every git under srt; then `boxed_recorded_cases`, `boxed_device_cases`,
    `boxed_step_cases`, `boxed_dirty_case` and `boxed_undo_case`."""
    marker = pathlib.Path(WT_MARKER)
    final = pathlib.Path(WT_ROOT, "Repo-boxed")
    proc, started, boxed = boxed_run(create("boxed"))
    report(
        proc is not None
        and proc.returncode == 0
        and pathlib.Path(proc.stdout.strip()) == final
        and final.is_dir()
        and listed(final)
        and linked(final)
        and stage_empty()
        and not marker.exists(),
        f"a boxed create prints the final path; the worktree is there, registered, its .git file and "
        f"admin gitdir name each other, the staging directory is empty, and no post-checkout ran: "
        f"{said(proc)}, listed {listed(final)}, linked {linked(final)}, "
        f"stage {stage_state(pathlib.Path(WT_STAGE))}",
    )
    adds = [line for line in boxed if " worktree add " in line]
    report(
        boxed
        and len(boxed) == len(started)
        and all(via_srt(line) for line in boxed)
        and any(" config --file " in line for line in boxed),
        f"every git of a boxed create runs as {' '.join(WT_BOXED)}, the config read included: "
        f"{len(started)} gits, {boxed}",
    )
    report(
        len(adds) == 1 and f" {WT_STAGE}/Repo-boxed " in f"{adds[0]} ",
        f"the boxed worktree add names its path below the staging directory {WT_STAGE}: {adds}",
    )
    proc, started, boxed = boxed_run(remove("boxed"))
    removes = [line for line in boxed if " worktree remove " in line]
    report(
        proc is not None
        and proc.returncode == 0
        and not final.exists(follow_symlinks=False)
        and not listed(final)
        and stage_empty()
        and boxed
        and len(boxed) == len(started)
        and all(via_srt(line) for line in boxed)
        and len(removes) == 1
        and removes[0].endswith(f" worktree remove {WT_STAGE}/Repo-boxed"),
        f"a boxed remove runs every git under srt, removes the worktree below the staging directory, and "
        f"the worktree is gone: {said(proc)}, {boxed}",
    )
    boxed_recorded_cases(hook, report)
    boxed_device_cases(hook, report)
    boxed_step_cases(report)
    boxed_dirty_case(report)
    boxed_undo_case(hook, report)


def boxed_undo_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`undo` where the directory that the child made cannot be removed, as a process that a config
    started can leave a directory of mode 500 with a file in it: one stderr line names the directory
    and the error, `git worktree prune` still runs after the failed removal, and no exception leaves
    `undo`."""
    made = pathlib.Path(FIXTURE.name, "wt-undo", "Repo-locked")
    locked = made / "locked"
    locked.mkdir(parents=True)
    (locked / "file").write_text("locked\n", encoding="utf-8")
    calls: list[str] = []
    real_discard = hook.discard

    def discard(path: pathlib.Path) -> None:
        calls.append(f"discard {path}")
        real_discard(path)

    def record(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(" ".join(args))
        return subprocess.CompletedProcess(list(args), 0, "", "")

    err = io.StringIO()
    locked.chmod(0o500)  # not private: a directory whose file rmtree cannot remove
    try:
        with (
            mock.patch.object(hook, "discard", discard),
            mock.patch.object(hook, "run_git", record),
            contextlib.redirect_stderr(err),
        ):
            hook.undo(pathlib.Path(WT_REPO), made, pathlib.Path(WT_PROFILE))
    except OSError as raised:
        outcome = f"raised: {raised!r}"
    else:
        outcome = "returned"
    finally:
        locked.chmod(0o700)  # not private: the probe's own removal of that directory
    lines = [line for line in err.getvalue().splitlines() if str(made) in line.replace(str(locked), "")]
    report(
        outcome == "returned"
        and len(lines) == 1
        and "Permission denied" in lines[0]
        and calls == [f"discard {made}", "worktree prune"],
        f"undo where the directory it made cannot be removed writes one line that names it and the "
        f"error, runs `git worktree prune` after it, and raises nothing: {outcome}, {err.getvalue()!r}, "
        f"{calls}",
    )
    shutil.rmtree(made.parent)


def boxed_recorded_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A boxed create and remove of `Repo` in this process: every process that they start starts
    with WT_BOXED, the config read included, and the add and the remove name the path below the
    staging directory."""
    profile = pathlib.Path(WT_PROFILE)

    def recorded() -> object:
        path = hook.create(create("boxrec"), profile=profile)
        hook.remove({"worktree_path": str(path)}, profile=profile)
        return path

    outcome, seen = inprocess(hook, recorded)
    report(
        outcome.startswith("done: ")
        and seen
        and all(a[: len(WT_BOXED)] == WT_BOXED for a in seen)
        and any(a[len(WT_BOXED) : len(WT_BOXED) + 2] == ["config", "--file"] for a in seen),
        f"every process that a boxed create and remove start in this process starts with "
        f"{' '.join(WT_BOXED)}, the config read included: {outcome}, {seen}",
    )
    verbs = {" ".join(a[len(WT_BOXED) : len(WT_BOXED) + 2]): a[len(WT_BOXED) + 2 :] for a in seen}
    add = verbs.get("worktree add", [])
    report(
        any(x == f"{WT_STAGE}/Repo-boxrec" for x in add),
        f"the boxed worktree add, recorded, names {WT_STAGE}/Repo-boxrec: {add}",
    )
    report(
        verbs.get("worktree remove") == [f"{WT_STAGE}/Repo-boxrec"],
        f"the boxed worktree remove, recorded, names {WT_STAGE}/Repo-boxrec: {verbs.get('worktree remove')}",
    )


def boxed_device_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`same_device` with an injected stat that gives two devices, and a boxed create in this
    process with that stat and with a ROOT that is a link: each refused with a line that
    names its cause, with no `worktree add`, a `worktree prune` under srt, and no worktree."""
    profile = pathlib.Path(WT_PROFILE)
    real_same = getattr(hook, "same_device", None)

    def devices(path: object) -> types.SimpleNamespace:
        return types.SimpleNamespace(st_dev=1 if str(path).startswith(WT_STAGES) else 2)

    def two_devices(a: pathlib.Path, b: pathlib.Path) -> bool:
        """The hook's `same_device` with the injected `devices`; True where the hook has none."""
        return True if real_same is None else bool(real_same(a, b, stat=devices))

    try:
        unit: object = (
            two_devices(pathlib.Path(WT_STAGE), pathlib.Path(WT_ROOT)),
            None if real_same is None else real_same(pathlib.Path(WT_STAGE), pathlib.Path(WT_ROOT)),
        )
    except TypeError as err:
        unit = repr(err)
    report(
        unit == (False, True),
        f"same_device gives False where the injected stat gives two devices, and True on the fixture: {unit}",
    )

    def refused_create(
        name: str, words: tuple[str, ...], *patches: contextlib.AbstractContextManager[object]
    ) -> None:
        outcome, seen = inprocess(hook, lambda: hook.create(create(name), profile=profile), *patches)
        verbs = [" ".join(a[len(WT_BOXED) : len(WT_BOXED) + 2]) for a in seen]
        word = " and ".join(words)
        report(
            outcome.startswith("refused: ")
            and all(w in outcome for w in words)
            and "worktree add" not in verbs
            and "worktree prune" in verbs
            and all(a[: len(WT_BOXED)] == WT_BOXED for a in seen)
            and not pathlib.Path(WT_ROOT, f"Repo-{name}").exists(follow_symlinks=False)
            and stage_empty(),
            f"a boxed create {name}: refused with a line that names {word}, no worktree add, a worktree "
            f"prune under srt, no worktree, an empty staging directory: {outcome}, {verbs}",
        )

    two = mock.patch.object(hook, "same_device", two_devices, create=True)
    refused_create("twodevices", (WT_STAGE, WT_ROOT), two)
    root_link = pathlib.Path(WT_HOME, "root-link")
    root_link.symlink_to(WT_ROOT)
    refused_create("rootlink", (str(root_link),), mock.patch.object(hook, "ROOT", root_link))
    boxed_edge_cases(hook, report)


def boxed_edge_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """The decided edges of a boxed create and remove, in this process: a staging directory that is
    a link; a ROOT that is missing, which the child makes, and a ROOT below a directory that is
    missing, which it does not make; a rename that fails, as across devices; a final path that
    becomes a link after the rename; and a refused remove whose rename back fails."""
    profile = pathlib.Path(WT_PROFILE)
    target = pathlib.Path(FIXTURE.name, "wt-stage-target")
    target.mkdir()
    linked_stage = pathlib.Path(WT_STAGES, "linked")
    linked_stage.symlink_to(target)
    outcome, seen = inprocess(
        hook, lambda: hook.create(create("stagelink"), profile=linked_stage.with_suffix(".json"))
    )
    report(
        outcome.startswith("refused: ")
        and str(linked_stage) in outcome
        and not any(" ".join(a[len(WT_BOXED) : len(WT_BOXED) + 2]) == "worktree add" for a in seen)
        and not any(target.iterdir())
        and not pathlib.Path(WT_ROOT, "Repo-stagelink").exists(follow_symlinks=False),
        f"a boxed create whose staging directory is a link: refused with a line that names it, and no "
        f"worktree add: {outcome}",
    )

    fresh = pathlib.Path(WT_R, "fresh-root")

    def made_and_removed() -> object:
        path = hook.create(create("freshroot"), profile=profile)
        listed_path = listed(path)
        hook.remove({"worktree_path": str(path)}, profile=profile)
        return f"{path} listed {listed_path}"

    outcome, _ = inprocess(hook, made_and_removed, mock.patch.object(hook, "ROOT", fresh))
    report(
        outcome == f"done: {fresh}/Repo-freshroot listed True" and fresh.is_dir() and stage_empty(),
        f"a boxed create where the worktrees' root is missing makes it and the worktree in it: {outcome}",
    )
    absent = pathlib.Path(WT_HOME, "absent", ".worktrees")
    outcome, _ = inprocess(
        hook,
        lambda: hook.create(create("absentroot"), profile=profile),
        mock.patch.object(hook, "ROOT", absent),
    )
    report(
        outcome.startswith("refused: ")
        and str(absent) in outcome
        and not absent.parent.exists()
        and stage_empty(),
        f"a boxed create whose worktrees' root lies in a directory that is missing makes neither: {outcome}",
    )

    def exdev(self: pathlib.Path, target: pathlib.Path) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link", str(self), None, str(target))

    outcome, seen = inprocess(
        hook,
        lambda: hook.create(create("exdev"), profile=profile),
        mock.patch.object(pathlib.Path, "rename", exdev),
    )
    report(
        outcome.startswith("refused: ")
        and "cannot be renamed" in outcome
        and "Invalid cross-device link" in outcome
        and any(" ".join(a[len(WT_BOXED) : len(WT_BOXED) + 2]) == "worktree prune" for a in seen)
        and not pathlib.Path(WT_ROOT, "Repo-exdev").exists(follow_symlinks=False)
        and stage_empty(),
        f"a boxed create whose rename fails across devices: refused with the error, nothing copied, the "
        f"staged worktree removed and pruned: {outcome}",
    )

    real_move = hook.move
    empty = pathlib.Path(FIXTURE.name, "wt-empty")

    def raced(source: pathlib.Path, target: pathlib.Path) -> None:
        real_move(source, target)
        moved = target.with_name(f"{target.name}-moved")
        target.rename(moved)
        target.symlink_to(empty)
        shutil.rmtree(moved)

    outcome, _ = inprocess(
        hook, lambda: hook.create(create("raced"), profile=profile), mock.patch.object(hook, "move", raced)
    )
    report(
        outcome.startswith("refused: ")
        and "Repo-raced is a symbolic link or no directory after the rename" in outcome
        and not pathlib.Path(WT_ROOT, "Repo-raced").exists(follow_symlinks=False)
        and not any(empty.iterdir())
        and stage_empty(),
        f"a boxed create whose final path is a link after the rename: refused, the link removed and not "
        f"followed: {outcome}",
    )

    stuck = pathlib.Path(WT_ROOT, "Repo-stuck")
    outcome, _ = inprocess(hook, lambda: hook.create(create("stuck"), profile=profile))
    (stuck / "change.txt").write_text("a change\n", encoding="utf-8")

    def back_fails(source: pathlib.Path, target: pathlib.Path) -> None:
        if str(source).startswith(WT_STAGE):
            raise hook.Refusal(f"{source} cannot be renamed to {target}: refused by the probe")
        real_move(source, target)

    outcome, _ = inprocess(
        hook,
        lambda: hook.remove({"worktree_path": str(stuck)}, profile=profile),
        mock.patch.object(hook, "move", back_fails),
    )
    staged = pathlib.Path(WT_STAGE, "Repo-stuck")
    report(
        outcome.startswith("refused: ")
        and f"the worktree stays at {staged}" in outcome
        and (staged / "change.txt").is_file(),
        f"a refused boxed remove whose rename back fails: refused with a line that names the staged "
        f"path, where the worktree stays: {outcome}",
    )
    if staged.is_dir():
        staged.rename(stuck)
        (stuck / "change.txt").unlink()
        subprocess.run(
            ["git", "-C", WT_REPO, "worktree", "repair", str(stuck)],  # noqa: S607 -- the `git` on PATH
            capture_output=True,
            env=WORKTREE_ENV,
            timeout=60,
            check=False,
        )
        outcome, _ = inprocess(hook, lambda: hook.remove({"worktree_path": str(stuck)}, profile=profile))
    report(
        not stuck.exists(follow_symlinks=False) and stage_empty(),
        f"that worktree, moved back by the probe, is removed: {outcome}",
    )
    boxed_swap_case(hook, report)


def boxed_swap_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A boxed remove whose staged worktree becomes a link to another worktree right after the
    rename, as a process that a config started could make it: refused before any git runs on the
    staged path, and the other worktree stays, registered."""
    profile = pathlib.Path(WT_PROFILE)
    victim = pathlib.Path(WT_ROOT, "Repo-victim")
    racer = pathlib.Path(WT_ROOT, "Repo-racer")
    staged = pathlib.Path(WT_STAGE, "Repo-racer")
    aside = pathlib.Path(FIXTURE.name, "wt-racer-aside")
    made = [
        inprocess(hook, lambda name=name: hook.create(create(name), profile=profile))[0]
        for name in ("victim", "racer")
    ]
    real_move = hook.move

    def swapped(source: pathlib.Path, target: pathlib.Path) -> None:
        real_move(source, target)
        if target == staged:
            target.rename(aside)
            target.symlink_to(victim)

    outcome, seen = inprocess(
        hook,
        lambda: hook.remove({"worktree_path": str(racer)}, profile=profile),
        mock.patch.object(hook, "move", swapped),
    )
    on_staged = [a[len(WT_BOXED) :] for a in seen if str(staged) in a]
    report(
        outcome.startswith("refused: ")
        and not on_staged
        and victim.is_dir()
        and listed(victim)
        and linked(victim),
        f"a boxed remove whose staged worktree becomes a link to another worktree: refused before any "
        f"git on the staged path, and the other worktree stays: {made}, {outcome}, {on_staged}",
    )
    if staged.is_symlink():
        staged.unlink()
    if aside.is_dir():
        aside.rename(racer)
        subprocess.run(
            ["git", "-C", WT_REPO, "worktree", "repair", str(racer)],  # noqa: S607 -- the `git` on PATH
            capture_output=True,
            env=WORKTREE_ENV,
            timeout=60,
            check=False,
        )
    for path in (racer, victim):
        inprocess(hook, lambda path=path: hook.remove({"worktree_path": str(path)}, profile=profile))
    report(
        not racer.exists(follow_symlinks=False)
        and not victim.exists(follow_symlinks=False)
        and stage_empty(),
        "the probe removes both worktrees of that case",
    )


def boxed_step_cases(report: Callable[[object, str], None]) -> None:
    """A boxed create where srt is no executable file, which starts no git; and one per step that the
    stub srt breaks (STUB_SRT): each exits 1 with a line that names its cause, leaves no worktree
    at the final path and nothing in the staging directory, and runs a `worktree prune` under
    srt; where the `worktree add` fails, the branch that the create made is deleted under srt."""
    srt = pathlib.Path(WT_SRT)
    aside = srt.with_name("srt-aside")
    for label in ("a file that is not executable", "a directory"):
        if label == "a directory":
            srt.rename(aside)
            srt.mkdir(mode=0o755)
        else:
            srt.chmod(0o644)
        try:
            proc, started, boxed = boxed_run(create("nosrt"))
        finally:
            if label == "a directory":
                srt.rmdir()
                aside.rename(srt)
            srt.chmod(0o755)
        report(
            proc is not None
            and proc.returncode == 1
            and proc.stderr
            == f"worktree hook: {WT_SRT} is not an executable file; a boxed child runs every git in srt\n"
            and not started
            and not boxed
            and not pathlib.Path(WT_ROOT, "Repo-nosrt").exists(follow_symlinks=False)
            and stage_empty(),
            f"a boxed create where srt is {label}: exits 1 with the one line that names {WT_SRT}, before "
            f"any git: {said(proc)}, {started}",
        )

    found = pathlib.Path(WT_STAGE, "Repo-found")
    found.mkdir()
    (found / "keep").write_text("keep\n", encoding="utf-8")
    proc, _, boxed = boxed_run(create("found"))
    report(
        proc is not None
        and proc.returncode == 1
        and f"{WT_STAGE}/Repo-found exists" in last(proc)
        and (found / "keep").read_text(encoding="utf-8") == "keep\n"
        and not any(" worktree add " in line for line in boxed)
        and not pathlib.Path(WT_ROOT, "Repo-found").exists(follow_symlinks=False),
        f"a boxed create whose staged path exists already: exits 1 with a line that names it, runs no "
        f"worktree add, and leaves what it found: {said(proc)}",
    )
    shutil.rmtree(found)

    empty = pathlib.Path(FIXTURE.name, "wt-empty")
    for mode, name, word in [
        ("fail-add", "failadd", "exited 3"),
        ("link-after-add", "linkadd", f"{WT_STAGE}/Repo-linkadd is a symbolic link"),
        ("final-after-add", "finaladd", f"{WT_ROOT}/Repo-finaladd exists;"),
        ("wrong-git", "wronggit", "Repo-wronggit/.git names"),
    ]:
        proc, started, boxed = boxed_run(create(name), mode)
        path = pathlib.Path(WT_ROOT, f"Repo-{name}")
        if mode == "final-after-add":
            left = path.is_dir() and not path.is_symlink() and [p.name for p in path.iterdir()] == ["found"]
        else:
            left = not path.exists(follow_symlinks=False)
        if mode == "fail-add":
            deletes = [line for line in boxed if " branch -D " in line]
            report(
                fixture_git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}").returncode == 1
                and len(deletes) == 1
                and via_srt(deletes[0])
                and deletes[0].endswith(f" branch -D {name}"),
                f"a boxed create of a new branch whose worktree add fails deletes the branch under srt: "
                f"{said(proc)}, {deletes}",
            )
        report(
            proc is not None
            and proc.returncode == 1
            and word in last(proc)
            and left
            and not listed(path)
            and stage_empty()
            and not any(empty.iterdir())
            and any(" worktree prune" in line and via_srt(line) for line in boxed),
            f"a boxed create whose stub srt does {mode}: exits 1 with a line that names {word}, leaves no "
            f"worktree at the final path and nothing in the staging directory, and runs a worktree prune "
            f"under srt: {said(proc)}, stage {stage_state(pathlib.Path(WT_STAGE))}, {boxed[-2:]}",
        )
        if mode == "final-after-add" and path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)


def boxed_dirty_case(report: Callable[[object, str], None]) -> None:
    """A boxed remove of a worktree with a change: exits 1 with git's reason, and the worktree is
    back at its path, registered; without the change, the remove succeeds."""
    dirty = pathlib.Path(WT_ROOT, "Repo-dirty")
    proc, _, _ = boxed_run(create("dirty"))
    made = proc is not None and proc.returncode == 0 and dirty.is_dir()
    if made:
        (dirty / "change.txt").write_text("a change\n", encoding="utf-8")
    proc, _, _ = boxed_run(remove("dirty"))
    report(
        made
        and proc is not None
        and proc.returncode == 1
        and "untracked" in proc.stderr
        and (dirty / "change.txt").is_file()
        and listed(dirty)
        and linked(dirty)
        and stage_empty(),
        f"a boxed remove of a worktree with a change exits 1 with git's reason, and the worktree is back "
        f"at its path, registered: {said(proc)}, listed {listed(dirty)}, linked {linked(dirty)}, stage "
        f"{stage_state(pathlib.Path(WT_STAGE))}",
    )
    if made:
        (dirty / "change.txt").unlink()
        proc, _, _ = boxed_run(remove("dirty"))
        report(
            proc is not None and proc.returncode == 0 and not dirty.exists(follow_symlinks=False),
            f"the boxed remove of that worktree without its change removes it: {said(proc)}",
        )


class FakeGit:
    """A git that `run_git` starts in place of a real one: its `communicate` appends its timeout to
    `waits`, raises subprocess.TimeoutExpired with `args` for each of its first `timeouts` calls,
    and then returns no output. It starts no process; its `pid` reaches only the `os.killpg`
    recorder of a case, never the real `os.killpg`."""

    pid = 99999

    def __init__(self, args: list[str], timeouts: int, waits: list[float | None]) -> None:
        self.args = args
        self.timeouts = timeouts
        self.waits = waits
        self.returncode: int | None = None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.waits.append(timeout)
        if self.timeouts > 0:
            self.timeouts -= 1
            raise subprocess.TimeoutExpired(self.args, timeout or 0)
        self.returncode = -signal.SIGTERM
        return "", ""


def run_git_timeout_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`run_git` in this process with `subprocess.Popen` patched to start a FakeGit and `os.killpg`
    patched to a recorder: a git that times out, with a profile and without, gets SIGTERM to its
    process group and, where it outlives GRACE seconds, SIGKILL; a group that is gone or that holds
    only the unreaped child is no error; and `run_git` raises the subprocess.TimeoutExpired of the
    git command. A program that cannot start is a Refusal that names it."""
    profile = pathlib.Path(WT_PROFILE)
    repo = pathlib.Path(WT_REPO)
    grace = getattr(hook, "GRACE", None)
    term, kill = signal.SIGTERM, signal.SIGKILL
    for label, given, timeouts, failure, want in [
        ("with a profile", profile, 1, None, [term]),
        ("without a profile", None, 1, None, [term]),
        ("that outlives the SIGTERM", None, 2, None, [term, kill]),
        ("whose group is gone", profile, 2, ProcessLookupError, [term, kill]),
        ("whose group holds only the unreaped child", None, 1, PermissionError, [term]),
    ]:
        starts: list[object] = []
        waits: list[float | None] = []
        signals: list[tuple[int, int]] = []

        def start(
            args: list[str], timeouts: int = timeouts, waits: list[float | None] = waits, **kwargs: Any
        ) -> FakeGit:
            starts.append(kwargs.get("start_new_session"))
            return FakeGit([str(a) for a in args], timeouts, waits)

        def killpg(
            pid: int,
            signum: int,
            signals: list[tuple[int, int]] = signals,
            failure: type[OSError] | None = failure,
        ) -> None:
            signals.append((pid, signum))
            if failure is not None:
                raise failure(errno.ESRCH if failure is ProcessLookupError else errno.EPERM, "by the probe")

        with (
            mock.patch.object(subprocess, "Popen", side_effect=start),
            mock.patch.object(os, "killpg", side_effect=killpg),
            mock.patch.object(hook, "SRT", pathlib.Path(WT_SRT), create=True),
        ):
            try:
                hook.run_git("status", repo=repo, profile=given)
                outcome: object = "returned"
            except subprocess.TimeoutExpired as err:
                outcome = err
            except (hook.Refusal, OSError, TypeError, AttributeError) as err:
                outcome = f"raised {err!r}"
        command = [str(c) for c in outcome.cmd] if isinstance(outcome, subprocess.TimeoutExpired) else []
        report(
            isinstance(outcome, subprocess.TimeoutExpired)
            and "git" in command
            and starts == [True]
            and signals == [(FakeGit.pid, signum) for signum in want]
            and grace == 5
            and waits == [hook.LOCAL, *[grace] * len(want)],
            f"run_git {label}, whose git times out: started in a session of its own, {want} to its "
            f"process group, GRACE (5) seconds after each, and the git command's TimeoutExpired: "
            f"{outcome!r}, start_new_session {starts}, signals {signals}, waits {waits}",
        )
    for given, program, error in [
        (profile, WT_SRT, FileNotFoundError(errno.ENOENT, "No such file or directory", WT_SRT)),
        (None, "git", PermissionError(errno.EACCES, "Permission denied")),
    ]:
        with (
            mock.patch.object(subprocess, "Popen", side_effect=error),
            mock.patch.object(hook, "SRT", pathlib.Path(WT_SRT), create=True),
        ):
            try:
                hook.run_git("status", repo=repo, profile=given)
                said = "returned"
            except hook.Refusal as err:
                said = f"refused: {err}"
            except OSError as err:
                said = f"passed through: {err!r}"
        report(
            said.startswith("refused: ") and program in said,
            f"run_git whose {program} cannot start with {type(error).__name__}: a Refusal that names "
            f"{program}: {said}",
        )


class InterruptedGit(FakeGit):
    """A FakeGit whose first `communicate` calls `interrupt`, as a signal that arrives while the
    hook waits for git, and whose later calls return no output."""

    def __init__(self, args: list[str], waits: list[float | None], interrupt: Callable[[], None]) -> None:
        super().__init__(args, 0, waits)
        self.interrupt = interrupt

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        first = not self.waits
        self.waits.append(timeout)
        if first:
            self.interrupt()
        return "", ""


class TwiceSignalledGit(InterruptedGit):
    """An InterruptedGit whose second `communicate`, the wait of the group stop after its SIGTERM,
    calls `again`, as a second signal, and then raises subprocess.TimeoutExpired, as a git that
    outlives the SIGTERM; its third call returns no output."""

    def __init__(
        self,
        args: list[str],
        waits: list[float | None],
        interrupt: Callable[[], None],
        again: Callable[[], None],
    ) -> None:
        super().__init__(args, waits, interrupt)
        self.again = again

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if len(self.waits) == 1:
            self.waits.append(timeout)
            self.again()
            raise subprocess.TimeoutExpired(self.args, timeout or 0)
        return super().communicate(timeout)


def run_git_signal_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A signal while the hook waits for git, with `subprocess.Popen` patched to start an
    InterruptedGit and `os.killpg` to a recorder: a KeyboardInterrupt in `run_git` stops git's
    process group and passes on; `main` on a create, for SIGTERM and for SIGHUP, whose git calls
    the handler of that signal, stops the group, raises SystemExit with 128 + the signal's
    number, and leaves the handlers as they were before it. A SIGHUP after the SIGTERM, or a
    SIGTERM after the SIGHUP, while the group stop waits for a git that outlives its SIGTERM
    (TwiceSignalledGit), does not end the stop before its SIGKILL."""
    repo = pathlib.Path(WT_REPO)

    def interrupt() -> None:
        raise KeyboardInterrupt

    def handler_of(signum: int) -> Callable[[], None]:
        def call() -> None:
            handler = signal.getsignal(signum)
            if callable(handler):
                handler(signum, None)

        return call

    term, hup, kill = signal.SIGTERM, signal.SIGHUP, signal.SIGKILL
    runs: list[
        tuple[str, Callable[[], object], Callable[[], None], Callable[[], None] | None, int | None]
    ] = [
        ("KeyboardInterrupt", lambda: hook.run_git("status", repo=repo), interrupt, None, None),
        *[(signum.name, hook.main, handler_of(signum), None, 128 + signum) for signum in (term, hup)],
        *[
            (
                f"{first.name} and then a {second.name} within GRACE",
                hook.main,
                handler_of(first),
                handler_of(second),
                128 + first,
            )
            for first, second in ((term, hup), (hup, term))
        ],
    ]
    for label, work, call, again, code in runs:
        signals: list[tuple[int, int]] = []
        waits: list[float | None] = []
        before = {s: signal.getsignal(s) for s in (term, hup)}

        def start(
            args: list[str],
            waits: list[float | None] = waits,
            call: Callable[[], None] = call,
            again: Callable[[], None] | None = again,
            **_: Any,
        ) -> InterruptedGit:
            if again is None:
                return InterruptedGit([str(a) for a in args], waits, call)
            return TwiceSignalledGit([str(a) for a in args], waits, call, again)

        def killpg(pid: int, signum: int, signals: list[tuple[int, int]] = signals) -> None:
            signals.append((pid, signum))

        payload = json.dumps(create("signalled"))
        with (
            mock.patch.object(subprocess, "Popen", side_effect=start),
            mock.patch.object(os, "killpg", side_effect=killpg),
            mock.patch.dict(os.environ, WT_ENV, clear=True),
            mock.patch.object(sys, "stdin", io.StringIO(payload)),
            mock.patch.object(hook, "RESEARCH", pathlib.Path(WT_R)),
            mock.patch.object(hook, "ROOT", pathlib.Path(WT_ROOT)),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            try:
                outcome: object = f"returned {work()!r}"
            except KeyboardInterrupt:
                outcome = "KeyboardInterrupt"
            except SystemExit as raised:
                outcome = raised.code
        after = {s: signal.getsignal(s) for s in (term, hup)}
        want = "KeyboardInterrupt" if code is None else code
        stops = [(FakeGit.pid, term)] if again is None else [(FakeGit.pid, term), (FakeGit.pid, kill)]
        report(
            outcome == want and signals[: len(stops)] == stops and after == before,
            f"a {label} while the hook waits for git stops git's process group with {stops} and ends "
            f"with {want}, and the signal handlers are those of before: {outcome}, {signals}, "
            f"{'kept' if after == before else (before, after)}",
        )


def interrupted_state_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """After `interrupted` raised SystemExit for a SIGTERM, the handler of SIGTERM and of SIGHUP is
    each a callable other than SIG_IGN that returns None and raises nothing when called; the
    handlers of before are restored."""
    term, hup = signal.SIGTERM, signal.SIGHUP
    before = {s: signal.getsignal(s) for s in (term, hup)}
    called: dict[str, str] = {}
    try:
        try:
            hook.interrupted(term, None)
            raised = "returned"
        except SystemExit as err:
            raised = f"SystemExit({err.code})"
        for s in (term, hup):
            handler = signal.getsignal(s)
            if handler is signal.SIG_IGN or not callable(handler):
                called[s.name] = f"{handler!r}"
                continue
            try:
                called[s.name] = f"returned {handler(s, None)!r}"
            except SystemExit as err:
                called[s.name] = f"raised {err!r}"
    finally:
        for s, handler in before.items():
            if handler is not None:
                signal.signal(s, handler)
    report(
        raised == f"SystemExit({128 + term})"
        and called == {"SIGTERM": "returned None", "SIGHUP": "returned None"},
        f"after interrupted, SIGTERM and SIGHUP have a handler that does nothing, not SIG_IGN: "
        f"{raised}, {called}",
    )


def interrupted_child_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """After `interrupted` raised SystemExit, a git that `run_git` starts, as undo's prune while that
    SystemExit unwinds, has the default handlers: a stub srt that sends itself SIGTERM and then
    SIGHUP ends on the SIGTERM, and one that sends SIGHUP first ends on the SIGHUP. The stub runs in
    a session of its own, so its signals do not reach the probe."""
    term, hup = signal.SIGTERM, signal.SIGHUP
    stub = pathlib.Path(WT_HOME, ".local", "bin", "srt-signalled")
    try:
        for first, second in ((term, hup), (hup, term)):
            stub.write_text(
                f"#!/bin/sh\nkill -{first.name[3:]} $$\nkill -{second.name[3:]} $$\necho alive\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            before = {s: signal.getsignal(s) for s in (term, hup)}
            outcome = "no SystemExit"
            try:
                try:
                    hook.interrupted(term, None)
                except SystemExit:
                    with mock.patch.object(hook, "SRT", stub, create=True):
                        proc = hook.run_git(
                            "worktree", "prune", repo=pathlib.Path(WT_REPO), profile=pathlib.Path(WT_PROFILE)
                        )
                    outcome = f"exit {proc.returncode}, stdout {proc.stdout!r}"
                    good = proc.returncode == -first and "alive" not in proc.stdout
                else:
                    good = False
            finally:
                for s, handler in before.items():
                    if handler is not None:
                        signal.signal(s, handler)
            report(
                good,
                f"a git that the hook starts after interrupted ends on its own {first.name} and then "
                f"{second.name} with the default handler: {outcome}",
            )
    finally:
        stub.unlink(missing_ok=True)


# Where a case moves the stub srt WT_SRT aside, so that it cannot start.
WT_SRT_GONE = WT_SRT + "-gone"


def srt_away() -> None:
    """Move the stub srt aside to WT_SRT_GONE."""
    pathlib.Path(WT_SRT).rename(WT_SRT_GONE)


def srt_back() -> None:
    """Move the stub srt back from WT_SRT_GONE, where a case moved it there."""
    aside, srt = pathlib.Path(WT_SRT_GONE), pathlib.Path(WT_SRT)
    if aside.exists(follow_symlinks=False) and not srt.exists(follow_symlinks=False):
        aside.rename(srt)


def hooked(text: str) -> list[str]:
    """The lines of `text` that the worktree hook writes, `worktree hook: …`."""
    return [line for line in text.splitlines() if line.startswith("worktree hook: ")]


def unstage(path: pathlib.Path) -> None:
    """Move the worktree `path` back from the staging directory WT_STAGE, where a case left it
    there, and repair it, so that the later cases find the staging directory empty."""
    staged = pathlib.Path(WT_STAGE, path.name)
    if staged.is_dir() and not path.exists(follow_symlinks=False):
        staged.rename(path)
    if path.is_dir():
        fixture_git("worktree", "repair", str(path))


def boxed_gone_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A boxed remove through `main` whose stub srt is gone after the rename into the staging
    directory and back before the rename back: exit 1 with one `worktree hook:` line that names
    srt, and the worktree back at its path, registered."""
    profile = pathlib.Path(WT_PROFILE)
    stage = pathlib.Path(WT_STAGE)
    real_move = hook.move
    gone = pathlib.Path(WT_ROOT, "Repo-gone")
    inprocess(hook, lambda: hook.create(create("gone"), profile=profile))

    def vanish(source: pathlib.Path, target: pathlib.Path) -> None:
        real_move(source, target)
        if target.parent == stage:
            srt_away()
        else:
            srt_back()

    err = io.StringIO()
    try:
        outcome, _ = inprocess(
            hook,
            lambda: hook.main(["--boxed", WT_PROFILE]),
            mock.patch.object(hook, "move", vanish),
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(remove("gone")))),
            contextlib.redirect_stderr(err),
        )
    finally:
        srt_back()
    lines = hooked(err.getvalue())
    report(
        outcome == "done: 1"
        and len(lines) == 1
        and WT_SRT in lines[0]
        and gone.is_dir()
        and listed(gone)
        and linked(gone)
        and stage_empty(),
        f"a boxed remove whose srt is gone after the rename: exits 1 with one line that names srt, and "
        f"the worktree is back at its path, registered: {outcome}, {err.getvalue()!r}, "
        f"stage {stage_state(stage)}",
    )
    unstage(gone)
    inprocess(hook, lambda: hook.remove(remove("gone"), profile=profile))


def boxed_norepair_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A boxed remove whose `git worktree remove` refuses, a worktree with a change, and whose stub
    srt is gone before the repair after the rename back: the refusal of the remove is raised, and
    one stderr line is on the repair."""
    profile = pathlib.Path(WT_PROFILE)
    stage = pathlib.Path(WT_STAGE)
    real_move = hook.move
    kept = pathlib.Path(WT_ROOT, "Repo-norepair")
    inprocess(hook, lambda: hook.create(create("norepair"), profile=profile))
    if kept.is_dir():
        (kept / "change.txt").write_text("a change\n", encoding="utf-8")

    def back_gone(source: pathlib.Path, target: pathlib.Path) -> None:
        real_move(source, target)
        if source.parent == stage:
            srt_away()

    err = io.StringIO()
    try:
        outcome, _ = inprocess(
            hook,
            lambda: hook.remove(remove("norepair"), profile=profile),
            mock.patch.object(hook, "move", back_gone),
            contextlib.redirect_stderr(err),
        )
    finally:
        srt_back()
    lines = hooked(err.getvalue())
    report(
        outcome.startswith("refused: ")
        and "worktree remove" in outcome
        and len(lines) == 1
        and "worktree repair" in lines[0]
        and (kept / "change.txt").is_file()
        and stage_empty(),
        f"a boxed remove whose git worktree remove refuses and whose repair after the rename back has no "
        f"srt: the refusal of the remove, and one line on the repair: {outcome}, {err.getvalue()!r}",
    )
    unstage(kept)
    if kept.is_dir():
        (kept / "change.txt").unlink(missing_ok=True)
        inprocess(hook, lambda: hook.remove(remove("norepair"), profile=profile))


def boxed_prune_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A boxed create whose stub srt fails its repair and is gone before the prune of `undo`: the
    refusal of the repair, `undo` raises nothing, and one stderr line names the prune."""
    real_discard = hook.discard

    def discard_then_gone(path: pathlib.Path) -> None:
        real_discard(path)
        srt_away()

    err = io.StringIO()
    try:
        outcome, _ = inprocess(
            hook,
            lambda: hook.create(create("agent-0c"), profile=pathlib.Path(WT_PROFILE)),
            mock.patch.dict(os.environ, {"STUB_SRT_MODE": "fail-repair"}),
            mock.patch.object(hook, "discard", discard_then_gone),
            contextlib.redirect_stderr(err),
        )
    finally:
        srt_back()
    prunes = [line for line in err.getvalue().splitlines() if "worktree prune" in line]
    report(
        outcome.startswith("refused: ")
        and "worktree repair" in outcome
        and len(prunes) == 1
        and not pathlib.Path(WT_ROOT, "Repo-agent-0c").exists(follow_symlinks=False)
        and stage_empty(),
        f"a boxed create that fails while the srt of its prune cannot start: the refusal of the repair, "
        f"and one line that names the prune: {outcome}, {err.getvalue()!r}",
    )
    fixture_git("worktree", "prune")


def failure_unit_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`undo` and `staged_remove` in this process with `run_git` patched to fail: a prune and a
    branch deletion that time out or cannot start each write one stderr line, and `undo` raises
    nothing; a remove whose first error is a refusal or a timeout raises that error where the
    repair after the rename back times out, with one stderr line on the repair."""
    repo = pathlib.Path("/repo")
    timeout = subprocess.TimeoutExpired(["git", "worktree"], 60)
    refusal = hook.Refusal("srt cannot start: by the probe")
    for prune, delete in [(timeout, refusal), (refusal, timeout)]:
        err = io.StringIO()
        with (
            mock.patch.object(hook, "run_git", side_effect=[prune, delete]),
            contextlib.redirect_stderr(err),
        ):
            try:
                hook.undo(repo, None, pathlib.Path(WT_PROFILE), "made")
                outcome = "returned"
            except (hook.Refusal, subprocess.TimeoutExpired, TypeError) as raised:
                outcome = f"raised {raised!r}"
        lines = err.getvalue().splitlines()
        report(
            outcome == "returned"
            and len(lines) == 2
            and "worktree prune" in lines[0]
            and "branch -D made" in lines[1],
            f"undo whose prune gives {type(prune).__name__} and whose branch deletion gives "
            f"{type(delete).__name__}: one line on each, and nothing raised: {outcome}, {lines}",
        )
    for first in (hook.Refusal("`git worktree remove` exited 128"), timeout):
        err = io.StringIO()
        with (
            mock.patch.object(hook, "stage_of", return_value=pathlib.Path("/stage")),
            mock.patch.object(hook, "move"),
            mock.patch.object(hook, "moved"),
            mock.patch.object(hook, "git", side_effect=["", first]),
            mock.patch.object(hook, "run_git", side_effect=subprocess.TimeoutExpired(["git", "repair"], 60)),
            contextlib.redirect_stderr(err),
        ):
            try:
                hook.staged_remove(repo, pathlib.Path("/root/Repo-x"), pathlib.Path(WT_PROFILE))
                raised: object = None
            except (hook.Refusal, subprocess.TimeoutExpired) as error:
                raised = error
        lines = err.getvalue().splitlines()
        report(
            raised is first and len(lines) == 1 and "worktree repair" in lines[0],
            f"a remove whose first error is {first!r} and whose repair after the rename back times "
            f"out raises the first error, with one line on the repair: {raised!r}, {lines}",
        )


def fixture_git(*args: str) -> subprocess.CompletedProcess[str]:
    """The real git with `args` in `Repo`, outside the hook."""
    git = shutil.which("git") or "git"
    return subprocess.run(
        [git, "-C", WT_REPO, *args],
        capture_output=True,
        text=True,
        env=WORKTREE_ENV,
        timeout=60,
        check=False,
    )


def boxed_branch_cases(report: Callable[[object, str], None]) -> None:
    """A boxed create whose stub srt fails `git worktree repair`: with a new name, the branch that it
    made is gone, deleted under srt; with the name of an existing branch, that branch stays at its
    commit; with `agent-0a`, no branch is added; and with a new name where the stub also fails
    `git branch -D`, one stderr line names the branch and the refusal is the repair's."""

    def commit(name: str) -> str | None:
        proc = fixture_git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}")
        return proc.stdout.strip() if proc.returncode == 0 else None

    def heads() -> list[str]:
        return fixture_git("for-each-ref", "--format=%(refname)", "refs/heads").stdout.split()

    def failed(proc: subprocess.CompletedProcess[str] | None, name: str) -> bool:
        return (
            proc is not None
            and proc.returncode == 1
            and "worktree repair" in last(proc)
            and not pathlib.Path(WT_ROOT, f"Repo-{name}").exists(follow_symlinks=False)
            and stage_empty()
        )

    proc, _, boxed = boxed_run(create("newbr"), "fail-repair")
    deletes = [line for line in boxed if " branch -D " in line]
    report(
        failed(proc, "newbr")
        and commit("newbr") is None
        and len(deletes) == 1
        and via_srt(deletes[0])
        and deletes[0].endswith(" branch -D newbr"),
        f"a boxed create of a new branch whose repair fails deletes the branch under srt: {said(proc)}, "
        f"{deletes}, branch {commit('newbr')}",
    )
    fixture_git("branch", "kept", "main")
    before = commit("kept")
    proc, _, boxed = boxed_run(create("kept"), "fail-repair")
    report(
        failed(proc, "kept")
        and before is not None
        and commit("kept") == before
        and not any(" branch -D " in line for line in boxed),
        f"a boxed create of an existing branch whose repair fails leaves the branch at its commit: "
        f"{said(proc)}, {before} -> {commit('kept')}",
    )
    fixture_git("branch", "-D", "kept")
    listing = heads()
    proc, _, boxed = boxed_run(create("agent-0a"), "fail-repair")
    report(
        failed(proc, "agent-0a") and heads() == listing and not any(" branch -D " in line for line in boxed),
        f"a boxed create of a detached agent worktree whose repair fails adds no branch: {said(proc)}, "
        f"{listing} -> {heads()}",
    )
    proc, _, _ = boxed_run(create("newbr2"), "fail-repair-branch")
    lines = [] if proc is None else hooked(proc.stderr)
    named = [line for line in lines if "newbr2" in line.replace("Repo-newbr2", "")]
    report(
        failed(proc, "newbr2") and len(named) == 1 and "branch -D newbr2" in named[0],
        f"a boxed create whose repair and branch deletion fail: one line that names the branch, and the "
        f"refusal of the repair: {said(proc)}",
    )
    if commit("newbr2") is not None:
        fixture_git("branch", "-D", "newbr2")


def boxed_base_case(report: Callable[[object, str], None]) -> None:
    """A boxed create of a new name while the main checkout's HEAD is a commit other than the base:
    the new branch is at the base, `origin/main`, and has no upstream."""
    identity = ("-c", "user.name=probe", "-c", "user.email=probe@example.org")
    aside = fixture_git(*identity, "commit-tree", "main^{tree}", "-p", "main", "-m", "aside").stdout.strip()
    fixture_git("update-ref", "--no-deref", "HEAD", aside)
    try:
        proc, _, _ = boxed_run(create("based"))
    finally:
        fixture_git("symbolic-ref", "HEAD", "refs/heads/main")
    branch = fixture_git("rev-parse", "--verify", "--quiet", "refs/heads/based").stdout.strip()
    base = fixture_git("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main").stdout.strip()
    upstream = fixture_git("rev-parse", "--abbrev-ref", "based@{upstream}")
    report(
        proc is not None
        and proc.returncode == 0
        and aside
        and base
        and aside != base
        and branch == base
        and upstream.returncode != 0,
        f"a boxed create of a new branch while the main checkout's HEAD is {aside} makes the branch at "
        f"the base {base}, with no upstream: {said(proc)}, branch {branch}, upstream "
        f"{upstream.stdout.strip() or upstream.returncode}",
    )
    if proc is not None and proc.returncode == 0:
        boxed_run(remove("based"))
    fixture_git("branch", "-D", "based")


def boxed_racer_case(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A boxed create of a new name in this process where another process makes the branch after
    `add_arguments` found none, as a racer would: the create refuses with the line of `git branch`,
    the racer's branch stays at its commit, and no `git branch -D` runs."""
    real_arguments = hook.add_arguments
    raced: list[str] = []

    def racing(
        repo: pathlib.Path, name: str, target: pathlib.Path, profile: pathlib.Path | None
    ) -> list[str]:
        got = real_arguments(repo, name, target, profile)
        proc = fixture_git("branch", name, "main")
        raced.append(f"exit {proc.returncode} {proc.stderr.strip()}")
        return got

    outcome, seen = inprocess(
        hook,
        lambda: hook.create(create("lateracer"), profile=pathlib.Path(WT_PROFILE)),
        mock.patch.object(hook, "add_arguments", racing),
    )
    left = fixture_git("rev-parse", "--verify", "--quiet", "refs/heads/lateracer")
    main = fixture_git("rev-parse", "--verify", "--quiet", "refs/heads/main")
    deletes = [a for a in seen if a[len(WT_BOXED) : len(WT_BOXED) + 2] == ["branch", "-D"]]
    report(
        raced == ["exit 0 "]
        and outcome.startswith("refused: ")
        and "`git branch " in outcome
        and left.returncode == 0
        and left.stdout == main.stdout
        and not deletes
        and not pathlib.Path(WT_ROOT, "Repo-lateracer").exists(follow_symlinks=False)
        and stage_empty(),
        f"a boxed create whose new branch another process makes first refuses with the line of git "
        f"branch, and the racer's branch stays: racer {raced}, {outcome}, {left.stdout.strip()} at main "
        f"{main.stdout.strip()}, {deletes}",
    )
    if left.returncode == 0:
        fixture_git("branch", "-D", "lateracer")


def boxed_dash_case(report: Callable[[object, str], None]) -> None:
    """A boxed create of the name `-f`, which git would read as an option: exit 1, no git under srt
    that makes a branch or adds a worktree, and the branches and HEAD of the fixture as before."""

    def refs() -> tuple[str, str]:
        listing = fixture_git("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads").stdout
        return listing, fixture_git("symbolic-ref", "HEAD").stdout

    before = refs()
    proc, _, boxed = boxed_run(create("-f"))
    made = [line for line in boxed if "branch" in line or "worktree add" in line]
    report(
        proc is not None and proc.returncode == 1 and not made and refs() == before,
        f"a boxed create of the name '-f' refuses before git makes a branch or a worktree: {said(proc)}, "
        f"{made}, refs {'kept' if refs() == before else (before, refs())}",
    )


def name_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """A create whose name ends in a newline, `agent-ab` or `x`, or begins with `-`, as `-f`, `-m`
    and `--force` do, refuses before any git runs; `add_arguments` does not take `agent-ab` and a
    newline as a sub-agent's name; and `serve_arguments` refuses a `--parent` of a digit that is not
    ASCII with the usage line."""
    for name in ("agent-ab\n", "x\n", "-f", "-m", "--force"):
        outcome, seen = inprocess(hook, lambda name=name: hook.create(create(name)))
        report(
            outcome.startswith("refused: ") and "worktree name" in outcome and not seen,
            f"a create whose name is {name!r} refuses before any git runs: {outcome}, {seen}",
        )

    def answer(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(list(args), 1, "", "")

    with (
        mock.patch.object(hook, "run_git", side_effect=answer),
        mock.patch.object(hook, "base_ref", return_value="origin/main"),
    ):
        got = hook.add_arguments(pathlib.Path(WT_REPO), "agent-ab\n", pathlib.Path("/t"), None)
    report(
        "--detach" not in got,
        f"add_arguments takes 'agent-ab\\n' as no sub-agent's name: {got}",
    )
    for digit in ("²", "٣"):
        try:
            value = hook.serve_arguments(["--serve", "/s", "--parent", digit, "--settings", "/f"])
            outcome = f"returned {value}"
        except hook.Refusal as err:
            outcome = f"refused: {err}"
        except ValueError as err:
            outcome = f"raised {err!r}"
        report(
            outcome == f"refused: {hook.USAGE}",
            f"serve_arguments refuses --parent {digit!r} with the usage line: {outcome}",
        )


class FakeListener:
    """A listening socket for a broker in this process: `bind` calls `seen` and writes an empty file
    at the socket's path, and `accept` raises TimeoutError, as when no client comes."""

    def __init__(self, seen: Callable[[], None]) -> None:
        self.seen = seen

    def __enter__(self) -> FakeListener:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def bind(self, address: str) -> None:
        self.seen()
        pathlib.Path(address).write_bytes(b"")

    def listen(self) -> None:
        pass

    def settimeout(self, value: float) -> None:
        del value

    def accept(self) -> tuple[socket.socket, object]:
        raise TimeoutError


def broker_profile_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`main` with `--serve` in this process, `os.getppid` patched to the probe's process ID: with a
    directory at the profile's path, it exits 1 with one `worktree hook:` line that names the
    profile, no traceback, and the directory stands; after a normal end, with a listener that
    binds no socket (FakeListener) and a parent that ends after one look, the profile is gone; and
    where the profile becomes a directory before a bind that the probe refuses, one line names the
    profile and the bind's refusal stays the error."""
    own = pathlib.Path(WT_STAGES, f"{os.getpid()}.json")
    own.mkdir(parents=True)
    code, said = serve_inprocess(hook, None, None)
    lines = said.splitlines()
    report(
        code == 1
        and len(lines) == 1
        and lines[0].startswith("worktree hook: ")
        and str(own) in lines[0]
        and "Traceback" not in said
        and own.is_dir(),
        f"a broker with a directory at its profile's path exits 1 with one line that names the profile, "
        f"and the directory stands: {code}, {said!r}, directory {own.is_dir()}",
    )
    clear_broker_stage()
    broker_profile_end_cases(hook, report)


def serve_inprocess(
    hook: types.ModuleType, listener: Callable[[int, int], object] | None, looks: list[int] | None
) -> tuple[object, str]:
    """`main` with `--serve` in this process, with STAGES that of the fixture, the probe's process
    ID as `--parent`, the hook's `socket.socket` replaced by `listener` where given, and
    `os.getppid` giving `looks` and then 1, or the parent where `looks` is None: the exit status, or
    the exception that left `main`, and the stderr. The signal handlers that `serve` installs are
    restored."""
    parent = os.getpid()
    socket_path = pathlib.Path(WT_SOCKETS, "profile.sock")
    args = ["--serve", str(socket_path), "--parent", str(parent), "--settings", WT_SETTINGS]
    handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGHUP)}
    given = iter(looks or [])
    err = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(hook, "STAGES", pathlib.Path(WT_STAGES), create=True))
        stack.enter_context(
            mock.patch.object(os, "getppid", side_effect=lambda: next(given, 1) if looks else parent)
        )
        if listener is not None:
            fake = types.SimpleNamespace(
                socket=listener, AF_UNIX=socket.AF_UNIX, SOCK_STREAM=socket.SOCK_STREAM
            )
            stack.enter_context(mock.patch.object(hook, "socket", fake))
        stack.enter_context(contextlib.redirect_stderr(err))
        try:
            code: object = hook.main(args)
        except (OSError, hook.Refusal, hook.HarnessError) as raised:
            code = repr(raised)
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
    return code, err.getvalue()


def clear_broker_stage() -> None:
    """Remove the staging directory and the profile of the probe's process ID that a case left, where
    they are empty directories."""
    for path in (pathlib.Path(WT_STAGES, f"{os.getpid()}.json"), pathlib.Path(WT_STAGES, str(os.getpid()))):
        with contextlib.suppress(OSError):
            path.rmdir()


def broker_profile_end_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """The ends of `broker_profile_cases`: a normal end after one look at the parent, and a profile
    that becomes a directory before a bind that the probe refuses."""
    parent = os.getpid()
    stage = pathlib.Path(WT_STAGES, str(parent))
    own = stage.parent / f"{stage.name}.json"
    written: list[object] = []

    def listener(family: int, kind: int) -> FakeListener:
        del family, kind
        return FakeListener(lambda: written.append(profile_state(own)))

    code, said = serve_inprocess(hook, listener, [parent, parent])
    report(
        code == 0
        and written == [(0o600, profiled(stage))]
        and not own.exists(follow_symlinks=False)
        and not stage.exists(follow_symlinks=False)
        and not pathlib.Path(WT_SOCKETS, "profile.sock").exists(follow_symlinks=False),
        f"a broker that ends after one look at its parent removes the profile that it wrote, its staging "
        f"directory and its socket: {code}, {written}, {said!r}",
    )

    def swap() -> None:
        own.unlink()
        own.mkdir()

    def swapped(family: int, kind: int) -> Listener:
        del family, kind
        return Listener(swap)

    code, said = serve_inprocess(hook, swapped, None)
    lines = said.splitlines()
    report(
        code == 1
        and len(lines) == 2
        and str(own) in lines[0]
        and "cannot remove its profile" in lines[0]
        and "cannot bind" in lines[1]
        and own.is_dir(),
        f"a broker whose profile becomes a directory and whose bind is refused exits 1 with one line on "
        f"the profile and the bind's refusal last: {code}, {said!r}",
    )
    clear_broker_stage()


class Listener:
    """A listening socket whose `bind` calls `seen` and then raises PermissionError, as a session's
    sandbox refuses an AF_UNIX bind."""

    def __init__(self, seen: Callable[[], None]) -> None:
        self.seen = seen

    def __enter__(self) -> Listener:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def bind(self, address: str) -> None:
        del address
        self.seen()
        raise PermissionError(errno.EPERM, "refused by the probe")


def broker_start_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """The broker's settings file, staging directory and profile: `serve_arguments` and
    `allowed_writes` (`broker_argument_cases`); the starts that refuse (`broker_bad_start_cases`);
    and the starts in this process with a bind that the probe refuses (`broker_listener_cases`)."""
    broker_argument_cases(hook, report)
    bad_json = pathlib.Path(FIXTURE.name, "wt-bad.json")
    bad_json.write_text("not json\n", encoding="utf-8")
    broker_bad_start_cases(report, bad_json)
    try:
        broker_listener_cases(hook, report, bad_json)
    finally:
        remove_asides(pathlib.Path(WT_STAGES, str(os.getppid())))


def asides(stage: pathlib.Path) -> list[pathlib.Path]:
    """The directories `<stage>.stale-*` beside the staging directory `stage`, where a broker moves
    a stale staging directory that holds anything."""
    return sorted(stage.parent.glob(f"{stage.name}.stale-*"))


def remove_asides(stage: pathlib.Path) -> None:
    """Remove every directory `<stage>.stale-*` beside the staging directory `stage`."""
    for aside in asides(stage):
        shutil.rmtree(aside)


def broker_argument_cases(hook: types.ModuleType, report: Callable[[object, str], None]) -> None:
    """`serve_arguments` takes `--serve <socket> --parent <pid> --settings <file>` alone, and
    `allowed_writes` reads `filesystem.allowWrite` as a list of strings or refuses with a line that
    names the file."""
    arguments = getattr(hook, "serve_arguments", None)
    got: list[object] = []
    for args in (
        ["--serve", "/s", "--parent", "1", "--settings", "/f"],
        ["--serve", "/s", "--parent", "1"],
        ["--serve", "/s", "--parent", "1", "--profile", "/f"],
        ["--serve", "/s", "--parent", "x", "--settings", "/f"],
    ):
        try:
            got.append(arguments(args) if arguments is not None else None)
        except hook.Refusal as err:
            got.append(f"refused: {err}")
    report(
        got[0] == (pathlib.Path("/s"), 1, pathlib.Path("/f"))
        and all(str(g).startswith("refused: ") for g in got[1:]),
        f"serve_arguments takes --serve <socket> --parent <pid> --settings <file> and refuses four "
        f"arguments, another option and a parent that is no number: {got}",
    )
    writes = getattr(hook, "allowed_writes", None)
    values: list[tuple[dict[str, object], list[str] | None]] = [
        ({"filesystem": {"allowWrite": ["/a", "/b"]}}, ["/a", "/b"]),
        ({"filesystem": {"allowWrite": ["/a", 1]}}, None),
        ({"filesystem": ["/a"]}, None),
        ({"filesystem": {}}, None),
        ({}, None),
    ]
    for value, want in values:
        try:
            result: object = writes(value, pathlib.Path("/f")) if writes is not None else "no allowed_writes"
        except hook.Refusal as err:
            result = f"refused: {err}"
        report(
            result == want if want is not None else str(result).startswith("refused: /f "),
            f"the broker reads {value} as {want or 'a refusal that names the file'}: {result}",
        )


def broker_bad_start_cases(report: Callable[[object, str], None], bad_json: pathlib.Path) -> None:
    """A broker whose settings file is `bad_json`, no JSON, or whose `filesystem.allowWrite` is a
    string, or whose staging directory is a link, exits non-zero, binds no socket, writes no
    profile, and leaves the link's target."""
    bad_list = pathlib.Path(FIXTURE.name, "wt-string.json")
    bad_list.write_text(json.dumps({"filesystem": {"allowWrite": "/x"}}), encoding="utf-8")
    stage = pathlib.Path(WT_STAGES, str(os.getpid()))
    own = stage.parent / f"{stage.name}.json"
    target = pathlib.Path(FIXTURE.name, "wt-target")
    target.mkdir()
    (target / "keep").write_text("keep\n", encoding="utf-8")
    for index, (label, settings, word) in enumerate(
        [
            ("whose settings file is no JSON", bad_json, str(bad_json)),
            ("whose settings file's filesystem.allowWrite is a string", bad_list, str(bad_list)),
            ("whose staging directory is a link", pathlib.Path(WT_SETTINGS), f"{stage} is a symbolic link"),
        ]
    ):
        if settings == pathlib.Path(WT_SETTINGS):
            stage.symlink_to(target)
        path = pathlib.Path(WT_SOCKETS, f"st{index}.sock")
        proc = subprocess.run(
            [
                sys.executable,
                WORKTREE,
                "--serve",
                str(path),
                "--parent",
                str(os.getpid()),
                "--settings",
                str(settings),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=WT_ENV,
            timeout=TIMEOUT,
            check=False,
        )
        kept = (
            sorted(p.name for p in target.iterdir()) == ["keep"]
            and (target / "keep").read_text(encoding="utf-8") == "keep\n"
        )
        linked_stage = stage.is_symlink()
        report(
            proc.returncode != 0
            and word in proc.stderr
            and not path.exists(follow_symlinks=False)
            and kept
            and (
                linked_stage
                if settings == pathlib.Path(WT_SETTINGS)
                else not stage.exists(follow_symlinks=False)
            )
            and not own.exists(follow_symlinks=False),
            f"a broker {label} exits non-zero with a line that names {word}, binds no socket, writes no "
            f"profile and leaves the link's target: {proc.returncode}, {proc.stderr!r}",
        )
        if linked_stage:
            stage.unlink()


def broker_listener_cases(
    hook: types.ModuleType, report: Callable[[object, str], None], bad_json: pathlib.Path
) -> None:
    """In this process, with a bind that the probe refuses, the broker makes the staging directory
    with mode 700 in place of a stale one and the profile with mode 600 before it binds, reads the
    settings file `bad_json`, no JSON, before it binds, removes both when it ends, and leaves a
    staging directory that holds a worktree; the next broker moves that directory aside
    (`broker_stale_cases`)."""
    parent = os.getppid()
    stage = pathlib.Path(WT_STAGES, str(parent))
    own = stage.parent / f"{stage.name}.json"
    (stage / "stale").mkdir(parents=True)
    (stage / "stale" / "file").write_text("stale\n", encoding="utf-8")
    snapshots: list[tuple[object, object]] = []

    def listener(family: int, kind: int) -> Listener:
        del family, kind
        return Listener(lambda: snapshots.append((stage_state(stage), profile_state(own))))

    fake = types.SimpleNamespace(socket=listener, AF_UNIX=socket.AF_UNIX, SOCK_STREAM=socket.SOCK_STREAM)
    handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGHUP)}

    def start(settings: pathlib.Path) -> tuple[str, str]:
        errors = io.StringIO()
        with (
            mock.patch.object(hook, "socket", fake),
            mock.patch.object(hook, "STAGES", pathlib.Path(WT_STAGES), create=True),
            contextlib.redirect_stderr(errors),
        ):
            try:
                hook.serve(pathlib.Path(WT_SOCKETS, "fake.sock"), parent, settings)
            except (hook.Refusal, hook.HarnessError, TypeError) as err:
                return f"refused: {err}", errors.getvalue()
            else:
                return "served", errors.getvalue()
            finally:
                for signum, handler in handlers.items():
                    signal.signal(signum, handler)

    outcome, _ = start(pathlib.Path(WT_SETTINGS))
    report(
        snapshots == [((0o700, []), (0o600, profiled(stage)))],
        f"before it binds, the broker replaces a stale staging directory by an empty one of mode 700 and "
        f"writes its profile with mode 600, the settings file with that directory appended to "
        f"filesystem.allowWrite: {outcome}, {snapshots}",
    )
    moved = asides(stage)
    report(
        len(moved) == 1 and (moved[0] / "stale" / "file").read_text(encoding="utf-8") == "stale\n",
        f"the broker moves a stale staging directory that holds a file aside, with the file: {moved}",
    )
    remove_asides(stage)
    report(
        "refused by the probe" in outcome
        and not stage.exists(follow_symlinks=False)
        and not own.exists(follow_symlinks=False),
        f"a broker that ends removes its staging directory and its profile: {outcome}, "
        f"stage {stage.exists(follow_symlinks=False)}, profile {own.exists(follow_symlinks=False)}",
    )
    outcome, _ = start(bad_json)
    report(
        len(snapshots) == 1 and str(bad_json) in outcome and not stage.exists(follow_symlinks=False),
        f"a broker whose settings file is no JSON refuses before it binds and makes no staging directory: "
        f"{outcome}, {len(snapshots)} binds",
    )

    def stuck(family: int, kind: int) -> Listener:
        del family, kind
        return Listener((stage / "Repo-stuck").mkdir)

    with mock.patch.object(fake, "socket", stuck):
        outcome, _ = start(pathlib.Path(WT_SETTINGS))
    report(
        (stage / "Repo-stuck").is_dir() and not own.exists(follow_symlinks=False),
        f"a broker that ends with a worktree in its staging directory removes its profile and leaves the "
        f"directory: {outcome}, {stage_state(stage)}",
    )
    broker_stale_cases(hook, report, start, snapshots, stage)


def broker_stale_cases(
    hook: types.ModuleType,
    report: Callable[[object, str], None],
    start: Callable[[pathlib.Path], tuple[str, str]],
    snapshots: list[tuple[object, object]],
    stage: pathlib.Path,
) -> None:
    """The next broker on a staging directory `stage` that a broker left: `start` serves in this
    process and appends the staging directory and profile at its bind to `snapshots`. A stale
    directory that holds a worktree with a change moves aside to `<stage>.stale-<ns>`, with a line on
    standard error that names it, and the new one is empty; an empty stale directory is removed and
    moves nowhere; `staged_profile` refuses where the path aside exists, and moves nothing."""
    stuck = stage / "Repo-stuck"
    stuck.mkdir(parents=True, exist_ok=True)
    stuck.chmod(0o700)  # not private: the listener made it under the broker's umask 177
    (stuck / "change.txt").write_text("change\n", encoding="utf-8")
    snapshots.clear()
    outcome, errors = start(pathlib.Path(WT_SETTINGS))
    moved = asides(stage)
    report(
        [s[0] for s in snapshots] == [(0o700, [])]
        and len(moved) == 1
        and (moved[0] / "Repo-stuck" / "change.txt").read_text(encoding="utf-8") == "change\n"
        and str(moved[0]) in errors,
        f"a broker moves a stale staging directory that holds a worktree aside, with its change, names the "
        f"path aside on standard error, and binds with an empty one: {outcome}, {snapshots}, {moved}, "
        f"{errors!r}",
    )
    remove_asides(stage)
    stage.mkdir(mode=0o700)
    snapshots.clear()
    outcome, errors = start(pathlib.Path(WT_SETTINGS))
    report(
        [s[0] for s in snapshots] == [(0o700, [])] and not asides(stage),
        f"a broker removes an empty stale staging directory and moves nothing aside: {outcome}, "
        f"{snapshots}, {asides(stage)}, {errors!r}",
    )
    stage.mkdir(mode=0o700)
    (stage / "keep").write_text("keep\n", encoding="utf-8")
    taken = stage.parent / f"{stage.name}.stale-7"
    taken.mkdir()
    writes = [*WT_SETTINGS_VALUE["filesystem"]["allowWrite"]]
    profile = stage.parent / f"{stage.name}.json"
    try:
        hook.staged_profile(WT_SETTINGS_VALUE, writes, stage, profile, now=lambda: 7)
    except hook.Refusal as err:
        outcome = f"refused: {err}"
    else:
        outcome = "made"
    report(
        str(taken) in outcome
        and stage_state(stage) == (0o700, ["keep"])
        and stage_state(taken) is not None
        and not any(taken.iterdir())
        and not profile.exists(follow_symlinks=False),
        f"where the path aside exists, the broker refuses to start and moves nothing: {outcome}, "
        f"{stage_state(stage)}, {stage_state(taken)}",
    )
    shutil.rmtree(stage)


def worktree_git_cases() -> tuple[int, int]:
    """`worktree.py`'s git work on the fixture of `worktree_fixture`: a create and a remove without
    `AGENTBOX` and through a broker, with no hook of the repository run; the refusals of the
    repository check and of a worktree path that is a link, which start no git; the refusals of
    the git config (`config_check_cases`); git pinned to the checked repository
    (`discovery_cases`); the GIT_ALLOW_PROTOCOL of every git; the client's
    refusals under `AGENTBOX`; the boxed child (`boxed_cases`); the broker's settings file, staging
    directory and profile (`broker_start_cases`); the stop of a git past its timeout
    (`run_git_timeout_cases`) and on a signal to the hook (`run_git_signal_cases`); the handlers
    after that signal and a git started after it (`interrupted_state_case`,
    `interrupted_child_cases`); the failures of a boxed remove and of `undo` whose srt cannot start
    at one step (`boxed_gone_case`, `boxed_norepair_case`, `boxed_prune_case`) or whose git fails
    (`failure_unit_cases`); the branch of a boxed create (`boxed_branch_cases`, `boxed_base_case`,
    `boxed_racer_case`); names that end in a newline or begin with `-` (`name_cases`,
    `boxed_dash_case`) and parents of a digit that is not ASCII (`name_cases`); the broker's
    profile at its end (`broker_profile_cases`); the life of a broker; and the options of every git
    that the hook starts, recorded in this process: (number of cases, number wrong)."""
    verdict, why = bind_verdict(unix_bind, ci="CI" in os.environ)
    worktree_fixture()
    total = wrong = 0

    def report(ok: object, label: str) -> None:
        nonlocal total, wrong
        total += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  [worktree ]  {label}")

    report(
        verdict != "wrong",
        f"the probe bind of an AF_UNIX socket succeeds, or is refused where CI is not set: {verdict} {why}",
    )

    def refused(path: str) -> None:
        raise PermissionError(errno.EPERM, "Operation not permitted", path)

    got = [
        bind_verdict(refused, ci=False),
        bind_verdict(lambda _: None, ci=False),
        bind_verdict(refused, ci=True),
    ]
    report(
        got == [("skip", "Operation not permitted"), ("run", ""), ("wrong", "Operation not permitted")],
        f"a refused bind gives skip, and wrong where CI is set; a bind that succeeds gives run: {got}",
    )

    marker = pathlib.Path(WT_MARKER)

    def create(name: str, cwd: str = WT_REPO) -> dict[str, str]:
        return {"hook_event_name": "WorktreeCreate", "cwd": cwd, "name": name}

    def remove(name: str) -> dict[str, str]:
        return {"hook_event_name": "WorktreeRemove", "worktree_path": f"{WT_ROOT}/Repo-{name}"}

    def made(stdout: str, name: str) -> bool:
        """Whether `stdout` names the worktree `Repo-<name>`, which exists, with its HEAD on the
        branch `name`, read from the HEAD of its admin directory."""
        want = pathlib.Path(WT_ROOT, f"Repo-{name}").resolve()
        dot = want / ".git"
        if pathlib.Path(stdout.strip()).resolve() != want or not dot.is_file():
            return False
        admin = pathlib.Path(dot.read_text(encoding="utf-8").strip().removeprefix("gitdir: "))
        head = admin / "HEAD"
        return head.is_file() and head.read_text(encoding="utf-8") == f"ref: refs/heads/{name}\n"

    def said(proc: subprocess.CompletedProcess[str] | None) -> str:
        return "timeout" if proc is None else f"exit {proc.returncode}, {proc.stdout!r}, {proc.stderr!r}"

    proc, started = worktree_run(create("direct"), WT_ENV)
    report(
        proc is not None and proc.returncode == 0 and made(proc.stdout, "direct") and not marker.exists(),
        f"a create without AGENTBOX prints the path, makes the worktree with its HEAD on the branch and "
        f"runs no post-checkout of core.hooksPath: {said(proc)}, marker {marker.exists()}",
    )
    report(
        started and all(line.split()[:4] == WT_OPTIONS for line in started),
        f"every git of that create gets {' '.join(WT_OPTIONS)} first: {started}",
    )
    proc, started = worktree_run(remove("direct"), WT_ENV)
    report(
        proc is not None and proc.returncode == 0 and not pathlib.Path(WT_ROOT, "Repo-direct").exists(),
        f"a remove without AGENTBOX removes the worktree: {said(proc)}",
    )

    for label, payload in [
        ("a cwd outside the fixture's Research", create("outside", WT_OUTSIDE)),
        ("a cwd whose .git is a symbolic link", create("link", WT_R + "/Linked")),
        ("a worktree whose admin directory holds another commondir", remove("common")),
        ("a worktree whose admin directory holds another gitdir", remove("gitdir")),
        (
            "a worktree whose .git file names its admin directory through a .git link",
            remove("via"),
        ),
        (
            "a worktree below the fixture's Research of a repository outside it",
            {"hook_event_name": "WorktreeRemove", "worktree_path": f"{WT_ROOT}/Outside-x"},
        ),
        ("a worktree path that is a symbolic link", create("linked")),
    ]:
        proc, started = worktree_run(payload, WT_ENV)
        report(
            proc is not None and proc.returncode == 1 and not started,
            f"{label}: exits 1 and starts no git: {said(proc)}, {started}",
        )
    report(
        pathlib.Path(WT_ROOT, "Repo-linked").is_symlink()
        and not any(pathlib.Path(FIXTURE.name, "wt-empty").iterdir()),
        "the worktree path that is a link stays a link to an empty directory",
    )
    proc, started = worktree_run(remove("rel"), WT_ENV)
    report(
        proc is not None
        and proc.returncode == 1
        and proc.stderr.count("\n") == 1
        and WT_RELATIVE in proc.stderr
        and not started
        and pathlib.Path(WT_ROOT, "Repo-rel").is_dir(),
        f"a worktree made with --relative-paths: exits 1 with a line that names its gitdir line, "
        f"and starts no git: {said(proc)}, {started}",
    )
    config_check_cases(report)
    discovery_cases(report)
    no_repository_cases(report)

    hook = load_module("worktree_recorded", WORKTREE)
    seen: list[list[str]] = []
    protocols: list[str | None] = []
    real = subprocess.Popen

    def record(args: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        seen.append([str(a) for a in args])
        protocols.append((kwargs.get("env") or os.environ).get("GIT_ALLOW_PROTOCOL"))
        return real(args, **kwargs)

    err = io.StringIO()
    with (
        mock.patch.dict(os.environ, {**WT_ENV, "GIT_ALLOW_PROTOCOL": "file:https:ssh"}, clear=True),
        mock.patch.object(subprocess, "Popen", side_effect=record),
        mock.patch.object(hook, "RESEARCH", pathlib.Path(WT_R)),
        mock.patch.object(hook, "ROOT", pathlib.Path(WT_ROOT)),
        contextlib.redirect_stderr(err),
    ):
        try:
            path = hook.create(create("recorded"))
            hook.remove({"worktree_path": str(path)})
            outcome = "made and removed"
        except hook.Refusal as e:
            outcome = str(e)
    report(
        outcome == "made and removed"
        and seen
        and all(pathlib.Path(a[0]).name == "git" and a[1:5] == WT_OPTIONS for a in seen),
        f"every process that the hook starts is git with {' '.join(WT_OPTIONS)} first: {outcome}, {seen}",
    )
    report(
        protocols and all(p == "https:ssh" for p in protocols),
        f"every git that the hook starts gets GIT_ALLOW_PROTOCOL=https:ssh, also where the caller sets "
        f"file:https:ssh: {protocols}",
    )
    ssh = pathlib.Path(WT_SSH).read_text(encoding="utf-8") if pathlib.Path(WT_SSH).exists() else ""
    report(
        f"fixture git-upload-pack '{WT_ORIGIN}'" in ssh.splitlines(),
        f"git calls the fixture's ssh with the host and the remote command alone: {ssh.splitlines()[:2]}",
    )

    proc, started = worktree_run(create("nul", "/a\0b"), WT_ENV)
    report(
        proc is not None
        and proc.returncode == 1
        and proc.stderr.startswith("worktree hook: ")
        and proc.stderr.count("\n") == 1
        and not started,
        f"a cwd that holds a NUL byte: exits 1 with one line of the hook and starts no git: {said(proc)}",
    )
    proc = call(WORKTREE, '{"hook_event_name": "WorktreeRemove", "worktree_path": 1}', WT_ENV)
    report(
        proc is not None
        and proc.returncode == 1
        and proc.stderr == "worktree hook: the hook input's worktree_path 1 is not a string\n",
        f"a remove whose worktree_path is no string: exits 1 with one line that says so: {said(proc)}",
    )
    broker_unit_cases(hook, report)

    def client_refused(label: str, extra: dict[str, str], word: str) -> None:
        proc, started = worktree_run(create("agentbox"), {**WT_ENV, **extra})
        report(
            proc is not None
            and proc.returncode == 1
            and proc.stdout == ""
            and proc.stderr.count("\n") == 1
            and word in proc.stderr
            and not started
            and not pathlib.Path(WT_ROOT, "Repo-agentbox").exists(),
            f"{label}: exits 1 with one line that names {word} and starts no git: {said(proc)}, {started}",
        )

    client_refused("AGENTBOX=1 and no AGENTBOX_BROKER", {"AGENTBOX": "1"}, "AGENTBOX_BROKER")
    client_refused(
        "AGENTBOX=1 and an empty AGENTBOX_BROKER", {"AGENTBOX": "1", "AGENTBOX_BROKER": ""}, "AGENTBOX_BROKER"
    )
    none = f"{WT_SOCKETS}/none.sock"
    client_refused(
        "AGENTBOX=1 and a socket path that does not exist", {"AGENTBOX": "1", "AGENTBOX_BROKER": none}, none
    )
    regular = pathlib.Path(WT_SOCKETS, "b3.sock")
    regular.write_text("keep\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            WORKTREE,
            "--serve",
            str(regular),
            "--parent",
            str(os.getpid()),
            "--settings",
            WT_SETTINGS,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=WT_ENV,
        timeout=TIMEOUT,
        check=False,
    )
    report(
        proc.returncode != 0
        and regular.read_text(encoding="utf-8") == "keep\n"
        and str(regular) in proc.stderr,
        f"a broker at the path of a regular file exits non-zero, names it and leaves it: "
        f"{proc.returncode}, {proc.stderr!r}",
    )
    orphan = pathlib.Path(WT_SOCKETS, "b4.sock")
    proc = subprocess.run(
        [
            sys.executable,
            WORKTREE,
            "--serve",
            str(orphan),
            "--parent",
            str(ended_pid()),
            "--settings",
            WT_SETTINGS,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=WT_ENV,
        timeout=TIMEOUT,
        check=False,
    )
    report(
        proc.returncode != 0 and "parent" in proc.stderr and not orphan.exists(follow_symlinks=False),
        f"a broker whose --parent is not its parent exits non-zero, names the parent and binds nothing: "
        f"{proc.returncode}, {proc.stderr!r}",
    )
    boxed_cases(hook, report)
    broker_start_cases(hook, report)
    run_git_timeout_cases(hook, report)
    run_git_signal_cases(hook, report)
    interrupted_state_case(hook, report)
    interrupted_child_cases(hook, report)
    boxed_gone_case(hook, report)
    boxed_norepair_case(hook, report)
    boxed_prune_case(hook, report)
    failure_unit_cases(hook, report)
    boxed_branch_cases(report)
    boxed_base_case(report)
    boxed_racer_case(hook, report)
    boxed_dash_case(report)
    name_cases(hook, report)
    broker_profile_cases(hook, report)

    if verdict == "skip":
        report(
            verdict == "skip",
            f"the bind cases skip only where the probe bind is refused: {verdict} {why}",
        )
        print(
            f"skip  payloads: AF_UNIX bind refused in this environment ({why}); the worktree cases of a "
            "socket where nothing listens, of a broker's create, remove, refusals, bad requests, mode, "
            "parent, stale socket, SIGHUP and SIGTERM do not run"
        )
        return total, wrong
    dead = pathlib.Path(WT_SOCKETS, "dead.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.bind(str(dead))
    client_refused(
        "AGENTBOX=1 and a socket where nothing listens",
        {"AGENTBOX": "1", "AGENTBOX_BROKER": str(dead)},
        str(dead),
    )

    broker = start_broker("b1")
    try:
        up = until(lambda: is_socket(broker.socket), 10)
        mode = stat.S_IMODE(broker.socket.lstat().st_mode) if up else None
        report(up and mode == 0o600, f"the broker binds its socket with mode 600: {mode and oct(mode)}")
        stage = pathlib.Path(WT_STAGES, str(broker.parent.pid))
        own = stage.parent / f"{stage.name}.json"
        report(
            up and stage_state(stage) == (0o700, []) and profile_state(own) == (0o600, profiled(stage)),
            f"the broker makes its staging directory with mode 700, empty, and its profile with mode 600, "
            f"the settings file with that directory appended to filesystem.allowWrite: "
            f"{stage_state(stage)}, {profile_state(own)}",
        )
        env = {**WT_ENV, "AGENTBOX": "1", "AGENTBOX_BROKER": str(broker.socket)}
        proc, _ = worktree_run(create("brokered"), env)
        report(
            proc is not None
            and proc.returncode == 0
            and made(proc.stdout, "brokered")
            and not marker.exists(),
            f"a create through the broker prints the path, makes the worktree with its HEAD on the "
            f"branch and runs no post-checkout: {said(proc)}",
        )
        proc, _ = worktree_run(remove("brokered"), env)
        report(
            proc is not None
            and proc.returncode == 0
            and proc.stdout == ""
            and not pathlib.Path(WT_ROOT, "Repo-brokered").exists(),
            f"a remove through the broker removes the worktree and prints nothing: {said(proc)}",
        )
        proc, _ = worktree_run(remove("brokered"), env)
        report(
            proc is not None
            and proc.returncode == 1
            and proc.stdout == ""
            and str(broker.socket) in (proc.stderr.splitlines() or [""])[-1],
            f"a remove that the broker refuses, of a worktree that no longer exists: exits 1 with a last "
            f"line that names the socket: {said(proc)}",
        )
        proc, started = worktree_run(create("refused", WT_OUTSIDE), env)
        report(
            proc is not None
            and proc.returncode == 1
            and proc.stdout == ""
            and WT_OUTSIDE in proc.stderr
            and str(broker.socket) in (proc.stderr.splitlines() or [""])[-1]
            and not started,
            f"a create that the broker refuses: exits 1, writes the broker's lines and one that names "
            f"the socket, and starts no git: {said(proc)}, {started}",
        )
        limit = f"larger than {64 * 1024} bytes"
        for label, data, word in [
            ("a create of 70 KiB", json.dumps({**create("big"), "pad": "x" * 70 * 1024}).encode(), limit),
            (
                "a create followed by 70 KiB of spaces",
                json.dumps(create("big")).encode() + b" " * 70 * 1024,
                limit,
            ),
            ("a request that is no JSON", b"not json", ""),
            ("a request that is no JSON object", b"[1]", ""),
            ("a request of hook_event_name Other", b'{"hook_event_name": "Other"}', "Other"),
        ]:
            reply = request(broker.socket, data)
            report(
                reply is not None
                and isinstance(reply.get("error"), str)
                and word in reply["error"]
                and "path" not in reply
                and not pathlib.Path(WT_ROOT, "Repo-big").exists(),
                f"the broker answers {label} with an error{f' that names {word!r}' if word else ''}: {reply}",
            )
        reply = request(broker.socket, json.dumps(create("after")).encode())
        report(
            reply is not None and isinstance(reply.get("path"), str) and made(reply["path"], "after"),
            f"the broker makes the worktree of a create after those requests, with its HEAD on the "
            f"branch: {reply}",
        )
        if broker.parent.stdin is not None:
            broker.parent.stdin.close()
        broker.parent.wait(timeout=TIMEOUT)
        gone = until(lambda: ended(broker.pid) and not broker.socket.exists(follow_symlinks=False), 10)
        report(gone, "the broker exits and removes its socket within 10 s after its parent ends")
        cleared = until(
            lambda: not stage.exists(follow_symlinks=False) and not own.exists(follow_symlinks=False), 10
        )
        report(
            cleared,
            "the broker removes its staging directory and its profile within 10 s after its parent ends",
        )
    finally:
        stop_broker(broker)

    stale = pathlib.Path(WT_SOCKETS, "b2.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.bind(str(stale))
    broker = start_broker("b2")
    try:
        up = until(lambda: answers(stale), 10)
        reply = request(stale, b'{"hook_event_name": "Other"}') if up else None
        report(
            reply is not None and "error" in reply,
            f"a broker at the path of a stale socket replaces it and serves: {reply}",
        )
    finally:
        stop_broker(broker)

    for name, signum in [("b5", signal.SIGHUP), ("b6", signal.SIGTERM)]:
        broker = start_broker(name)
        try:
            up = until(lambda: is_socket(broker.socket), 10)
            if up:
                os.kill(broker.pid, signum)
            removed = up and until(lambda: not broker.socket.exists(follow_symlinks=False), 10)
        finally:
            stop_broker(broker)
        # The broker stays a zombie of its parent shell until that shell ends, so `ended` is looked at
        # after stop_broker.
        report(
            removed and until(lambda: ended(broker.pid), 10),
            f"a broker that gets {signum.name} removes its socket and exits within 10 s",
        )
    return total, wrong


# `LINK` is a symlink inside the tree that points out of it, made by `fixture`.
LINK = R + "/probe-link-out"

# `edit-scope.py`, in this order, because `--record` writes the grants that later cases read:
# (record, session, path or None, extra input fields, expected). A gated path below a worktree asks
# until `--record` grants it to the session; a main checkout always asks.
WT2 = R + "/.worktrees/Foo-other"
EDITSCOPE = HOOKS + "edit-scope.py"
EDITSCOPE_CASES: list[tuple[bool, str, str | None, dict[str, str], str]] = [
    (False, "a", WT + "/.githooks/pre-commit", {}, "ask"),
    (False, "a", WT + "/.github/workflows/CI.yml", {}, "ask"),
    (False, "a", PKG + "/.githooks/pre-commit", {}, "ask"),
    (False, "a", WT + "/src/Foo.jl", {}, "pass"),
    (False, "a", HOME + "/elsewhere/x/.githooks/pre-commit", {}, "pass"),
    # A grant comes only from `--record`, and only below a worktree.
    (True, "a", PKG + "/.githooks/pre-commit", {}, "pass"),
    (False, "a", PKG + "/.githooks/pre-commit", {}, "ask"),
    (True, "a", WT + "/.githooks/pre-commit", {}, "pass"),
    (False, "a", WT + "/.githooks/pre-commit", {}, "pass"),
    (False, "a", WT + "/.github/workflows/CI.yml", {}, "pass"),
    (False, "a", WT + "/docs/.github/workflows/x.yml", {}, "pass"),
    (False, "a", ".githooks/pre-push", {"cwd": WT}, "pass"),
    (False, "a", WT + "/../Foo-other/.githooks/pre-commit", {}, "ask"),
    (False, "a", WT2 + "/.githooks/pre-commit", {}, "ask"),
    (False, "b", WT + "/.githooks/pre-commit", {}, "ask"),
    (False, "", WT + "/.githooks/pre-commit", {}, "ask"),
    (False, "a", PKG + "/.githooks/pre-commit", {}, "ask"),
    (False, "a", None, {"notebook_path": WT2 + "/.github/workflows/n.ipynb"}, "ask"),
    # Fail closed before the edit; never block after it.
    (False, "a", ".githooks/pre-push", {}, "ask"),
    (True, "a", ".githooks/pre-push", {}, "pass"),
]
EDITSCOPE_PAYLOADS = [
    ((), "not json at all", "ask"),
    ((), '{"tool_input":{}}', "pass"),
    ((), '{"session_id":"a"}', "ask"),
    (("--record",), "not json at all", "pass"),
    (("--record",), '{"session_id":"a"}', "pass"),
]

# `prompt-log.py` decides nothing: every payload exits 0 with no output.
PROMPTLOG = HOOKS + "prompt-log.py"
PROMPTLOG_CASES = [
    '{"tool_name":"Bash","tool_input":{"command":"ls"},"permission_mode":"default"}',
    '{"tool_name":"Write","tool_input":{"file_path":"/x","content":"' + "a" * 5000 + '"}}',
    "not json at all",
    "",
    "[1]",
]

# The fixture of `worktree.py sweep`, in a home of its own below the fixture directory, SW_HOME.
# Its `Research` holds `Repo`, whose `origin/HEAD` names its one commit, and `Watched`, whose
# `.git/config` holds a `core.fsmonitor` that writes SW_MARKER, which the hook refuses. Below
# `Research/.worktrees`, by name: the worktrees of `Repo` of SW_KINDS, made with SW_AGED dated two
# FRESH spans back, `dirty` with an untracked file and `ahead` with a commit of its own; `lost`, whose
# record is gone; `bare`, with no `.git`; `forged`, whose `.git` file names the admin directory of a
# worktree of SW_OUTSIDE, a repository outside `Research`; `Watched-x`, an old clean worktree of
# `Watched`; and a hidden `.claude`. SW_BIN holds a `git` that appends its arguments to SW_LOG and,
# on a `worktree remove`, sends its parent, the hook, a SIGTERM.
SW_HOME = FIXTURE.name + "/sw"
SW_R = SW_HOME + "/Research"
SW_REPO = SW_R + "/Repo"
SW_ROOT = SW_R + "/.worktrees"
SW_OUTSIDE = FIXTURE.name + "/sw-outside"
SW_MARKER = FIXTURE.name + "/sw-marker"
SW_BIN = FIXTURE.name + "/sw-bin"
SW_LOG = FIXTURE.name + "/sw-git.log"
SW_ENV = {**WORKTREE_ENV, "HOME": SW_HOME}
SW_KINDS = {
    "old": "removable",
    "old2": "removable",
    "fresh": "kept",
    "dirty": "kept",
    "ahead": "kept",
    "lost": "orphan",
    "bare": "orphan",
    "forged": "kept",
}
SW_AGED = ("old", "old2", "dirty", "ahead")


def sweep_fixture() -> None:
    """Make the repositories, the worktrees and the signalling `git` of SW_HOME's fixture."""
    git = shutil.which("git") or "git"
    env = {**WORKTREE_ENV, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    env |= {f"GIT_{who}_{what}": value for who in ("AUTHOR", "COMMITTER") for what, value in WHO}

    def run(*args: str) -> None:
        subprocess.run([git, *args], env=env, check=True, capture_output=True, timeout=60)

    run("init", "-q", "-b", "main", SW_REPO)
    run("-C", SW_REPO, "commit", "-q", "--allow-empty", "-m", "fixture")
    run("-C", SW_REPO, "update-ref", "refs/remotes/origin/main", "HEAD")
    run("-C", SW_REPO, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    for name in ("old", "old2", "fresh", "dirty", "ahead", "lost"):
        run("-C", SW_REPO, "worktree", "add", "-q", "--detach", f"{SW_ROOT}/Repo-{name}", "origin/main")
    pathlib.Path(SW_ROOT, "Repo-dirty", "b").write_text("b\n", encoding="utf-8")
    run("-C", f"{SW_ROOT}/Repo-ahead", "commit", "-q", "--allow-empty", "-m", "ahead")
    shutil.rmtree(pathlib.Path(SW_REPO, ".git", "worktrees", "Repo-lost"))
    pathlib.Path(SW_ROOT, "Repo-bare").mkdir()
    pathlib.Path(SW_ROOT, ".claude").mkdir()
    run("init", "-q", "-b", "main", SW_OUTSIDE)
    run("-C", SW_OUTSIDE, "commit", "-q", "--allow-empty", "-m", "fixture")
    run("-C", SW_OUTSIDE, "worktree", "add", "-q", "--detach", f"{SW_OUTSIDE}-x")
    forged = pathlib.Path(SW_ROOT, "Repo-forged")
    forged.mkdir()
    admin = pathlib.Path(SW_OUTSIDE, ".git", "worktrees", pathlib.Path(f"{SW_OUTSIDE}-x").name).resolve()
    (forged / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    watched = SW_R + "/Watched"
    run("init", "-q", "-b", "main", watched)
    run("-C", watched, "commit", "-q", "--allow-empty", "-m", "fixture")
    run("-C", watched, "update-ref", "refs/remotes/origin/main", "HEAD")
    run("-C", watched, "worktree", "add", "-q", "--detach", f"{SW_ROOT}/Watched-x", "origin/main")
    run("-C", watched, "config", "core.fsmonitor", f"touch '{SW_MARKER}'; false")
    for name in SW_AGED:
        sweep_aged(SW_REPO, f"{SW_ROOT}/Repo-{name}")
    sweep_aged(watched, f"{SW_ROOT}/Watched-x")
    sweep_aged(SW_OUTSIDE, str(admin))
    wrapper = pathlib.Path(SW_BIN, "git")
    wrapper.parent.mkdir()
    wrapper.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{SW_LOG}'\n"
        f'case " $* " in *" worktree remove "*) kill -TERM "$PPID"; sleep 10 ;; esac\n'
        f"exec '{git}' \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)


# The author and committer of the sweep fixture's commits.
WHO = (("NAME", "probe"), ("EMAIL", "probe@example.org"))


def sweep_aged(repo: str, tree: str) -> None:
    """Date the record of the worktree `tree` of `repo`, or the admin directory `tree`, two FRESH
    spans back."""
    old = time.time() - 2 * 12 * 3600
    record = pathlib.Path(tree)
    if not record.is_relative_to(pathlib.Path(repo, ".git").resolve()):
        record = pathlib.Path(repo, ".git", "worktrees", record.name)
    for path in (record, record / "HEAD", record / "index", record / "logs" / "HEAD"):
        if path.exists():
            os.utime(path, (old, old))


def sweep_run(
    args: tuple[str, ...], env: dict[str, str] = SW_ENV, cwd: str = FIXTURE.name
) -> subprocess.CompletedProcess[str] | None:
    """`worktree.py <args>` in `cwd` with `env` and an empty stdin; None after the timeout."""
    try:
        return subprocess.run(
            [sys.executable, WORKTREE, *args],
            input="",
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def worktree_sweep_cases() -> tuple[int, int]:
    """`worktree.py`'s command-line forms: `add <name>` and `remove <path>` on the fixture of
    `worktree_fixture`, wrong arguments, and `sweep` on the fixture of `sweep_fixture`: the dry run
    lists each worktree with its kind and removes none, and starts no git of a repository that the
    hook refuses; a SIGTERM during the first of two removals ends `sweep --apply` with 143 before the
    second; `--apply` removes each removable worktree alone; a refused removal exits 1 with one line
    that names the count, and the next removal still runs: (number of cases, number wrong)."""
    total = wrong = 0

    def report(ok: object, label: str) -> None:
        nonlocal total, wrong
        total += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  [wt-sweep ]  {label}")

    def said(proc: subprocess.CompletedProcess[str] | None) -> str:
        return "timeout" if proc is None else f"exit {proc.returncode}, {proc.stdout!r}, {proc.stderr!r}"

    made = pathlib.Path(WT_ROOT, "Repo-argv")
    proc = sweep_run(("add", "argv"), WT_ENV, WT_REPO)
    report(
        proc is not None and proc.returncode == 0 and proc.stdout == f"{made}\n" and made.is_dir(),
        f"`add argv` in the repository makes the worktree of the working directory and prints its path: {said(proc)}",
    )
    proc = sweep_run(("remove", made.name), WT_ENV, WT_ROOT)
    report(
        proc is not None and proc.returncode == 0 and not made.exists(),
        f"`remove <relative path>` removes the worktree that the path names from the working directory: {said(proc)}",
    )
    for args in (
        ("add",),
        ("add", "a", "b"),
        ("remove",),
        ("sweep", "--bogus"),
        ("sweep", "--apply", "x"),
        ("x",),
    ):
        proc = sweep_run(args)
        report(
            proc is not None and proc.returncode == 1 and proc.stderr == f"worktree hook: {USAGE_LINE}\n",
            f"`{' '.join(args)}` exits 1 with the usage line: {said(proc)}",
        )

    sweep_fixture()
    proc = sweep_run(("sweep",))
    lines = proc.stdout.splitlines() if proc is not None else []
    listed = {words[1]: words[0] for words in (line.split() for line in lines[:-1])}
    want = {f"{SW_ROOT}/Repo-{name}": kind for name, kind in SW_KINDS.items()} | {
        f"{SW_ROOT}/Watched-x": "kept"
    }
    report(
        proc is not None
        and proc.returncode == 1
        and listed == want
        and lines[-1:] == ["would remove 2 worktrees"]
        and all(pathlib.Path(path).exists() for path in want),
        f"the dry run lists each worktree with its kind, and not the hidden .claude, removes none and exits 1: {said(proc)}",
    )
    report(
        proc is not None
        and f"{'kept':<9}  {SW_ROOT}/Repo-forged  the hook refuses it: " in proc.stdout
        and f"{'kept':<9}  {SW_ROOT}/Watched-x  the hook refuses it: " in proc.stdout
        and not pathlib.Path(SW_MARKER).exists(),
        "a worktree whose .git names a repository outside Research, and one of a repository whose "
        f"config holds core.fsmonitor, are kept, and no git runs that config: {said(proc)}",
    )
    pathlib.Path(SW_LOG).unlink(missing_ok=True)
    signalling = {**SW_ENV, "PATH": SW_BIN + ":" + SW_ENV.get("PATH", "/usr/bin:/bin")}
    proc = sweep_run(("sweep", "--apply"), signalling)
    log = pathlib.Path(SW_LOG)
    started = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    removes = [line for line in started if "worktree remove" in line]
    report(
        proc is not None
        and proc.returncode == 128 + signal.SIGTERM
        and len(removes) == 1
        and pathlib.Path(SW_ROOT, "Repo-old2").is_dir(),
        f"a SIGTERM during the first of two removals ends sweep --apply with 143 before the second: {said(proc)} {removes}",
    )
    proc = sweep_run(("sweep", "--apply"))
    report(
        proc is not None
        and proc.returncode == 0
        and not pathlib.Path(SW_ROOT, "Repo-old").exists()
        and not pathlib.Path(SW_ROOT, "Repo-old2").exists()
        and all(
            pathlib.Path(SW_ROOT, f"Repo-{name}").exists()
            for name, kind in SW_KINDS.items()
            if kind != "removable"
        )
        and pathlib.Path(SW_ROOT, "Watched-x").is_dir()
        and not pathlib.Path(SW_MARKER).exists(),
        f"sweep --apply removes each removable worktree and no other: {said(proc)}",
    )
    git = shutil.which("git") or "git"
    for name in ("old3", "old4"):
        subprocess.run(
            [
                git,
                "-C",
                SW_REPO,
                "worktree",
                "add",
                "-q",
                "--detach",
                f"{SW_ROOT}/Repo-{name}",
                "origin/main",
            ],
            env={**WORKTREE_ENV, "GIT_CONFIG_GLOBAL": "/dev/null"},
            check=True,
            capture_output=True,
            timeout=60,
        )
        sweep_aged(SW_REPO, f"{SW_ROOT}/Repo-{name}")
    shielded = pathlib.Path(SW_ROOT, "Repo-old3", ".githooks")
    shielded.mkdir()
    shielded.chmod(0o500)
    try:
        proc = sweep_run(("sweep", "--apply"))
    finally:
        shielded.chmod(0o700)
    last = proc.stderr.splitlines()[-1:] if proc is not None else []
    report(
        proc is not None
        and proc.returncode == 1
        and len(last) == 1
        and last[0].startswith(
            "worktree hook: 1 of 2 removals failed: Repo-old3: this process cannot write in "
        )
        and pathlib.Path(SW_ROOT, "Repo-old3").is_dir()
        and not pathlib.Path(SW_ROOT, "Repo-old4").exists(),
        f"a refused removal exits 1 with one line that names the count, and the next removal runs: {said(proc)}",
    )
    return total, wrong


# The usage line of `worktree.py`.
USAGE_LINE = (
    "usage: worktree.py [add <name> | remove <path> | sweep [--apply] | "
    "--serve <socket> --parent <pid> --settings <file> | --boxed <profile>]"
)

# `context-handoff.py` reads the context size of the last two model calls of the main chain from a
# transcript of the fixture. A transcript is a list of records: (message id, context in tokens) for
# a model call, ("side", tokens) for a sub-agent's call, ("bad", 0) for a line that is not JSON,
# ("syn", 0) for a record that Claude Code writes itself, such as an API error, and ("pad", bytes)
# for a user record of that size, which puts the calls before it into an earlier block of the
# hook's read. Its 412k call is split in two input counts, and written twice, as Claude
# Code writes one record per content block. A case: (transcript, event, extra payload fields,
# expected), where "pass" is no output and exit 0, and "<k>k" the context line with that size.
CONTEXT = HOOKS + "context-handoff.py"
CONTEXT_TRANSCRIPTS = {
    "below": [("a", 120_000), ("b", 300_000)],
    "crosses": [("a", 350_000), ("b", 412_000), ("b", 412_000)],
    "above": [("a", 410_000), ("b", 412_000)],
    "step": [("a", 495_000), ("b", 505_000)],
    "side": [("a", 300_000), ("side", 520_000)],
    "bad": [("a", 350_000), ("b", 412_000), ("bad", 0)],
    "padded": [("a", 350_000), ("b", 412_000), ("pad", 300_000)],
    "one": [("b", 412_000)],
    "error-last": [("a", 410_000), ("b", 412_000), ("syn", 0)],
    "error-between": [("a", 410_000), ("syn", 0), ("b", 412_000)],
}
CONTEXT_CASES: list[tuple[str, str, dict[str, str], str]] = [
    ("below", "UserPromptSubmit", {}, "pass"),
    ("below", "PostToolUse", {}, "pass"),
    ("crosses", "UserPromptSubmit", {}, "412k"),
    ("crosses", "PostToolUse", {}, "412k"),
    ("above", "UserPromptSubmit", {}, "412k"),
    ("above", "PostToolUse", {}, "pass"),
    ("step", "PostToolUse", {}, "505k"),
    ("side", "UserPromptSubmit", {}, "pass"),
    ("bad", "PostToolUse", {}, "412k"),
    ("padded", "PostToolUse", {}, "412k"),
    ("one", "PostToolUse", {}, "412k"),
    ("error-last", "UserPromptSubmit", {}, "412k"),
    ("error-between", "PostToolUse", {}, "pass"),
    ("crosses", "PostToolUse", {"agent_id": "x"}, "pass"),
    ("crosses", "SessionStart", {}, "pass"),
    ("missing", "UserPromptSubmit", {}, "pass"),
]


def context_transcript(name: str) -> str:
    """The path of the fixture transcript `name` of CONTEXT_TRANSCRIPTS, written on first use."""
    path = pathlib.Path(FIXTURE.name, f"transcript-{name}.jsonl")
    if name in CONTEXT_TRANSCRIPTS and not path.exists():
        lines: list[str] = []
        for ident, tokens in CONTEXT_TRANSCRIPTS[name]:
            if ident == "bad":
                lines.append("{not json")
            elif ident == "pad":
                lines.append(
                    json.dumps({"type": "user", "message": {"content": "x" * tokens}}, separators=(",", ":"))
                )
            else:
                split = (2, 1000, tokens - 1002) if ident != "syn" else (0, 0, 0)
                usage = dict(
                    zip(
                        ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"),
                        split,
                        strict=True,
                    )
                )
                record = {
                    "type": "assistant",
                    "isSidechain": ident == "side",
                    "message": {
                        "id": ident,
                        "model": "<synthetic>" if ident == "syn" else "claude-opus-5-5",
                        "usage": usage,
                    },
                }
                lines.append(json.dumps(record, separators=(",", ":")))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def context_answer(proc: subprocess.CompletedProcess[str] | None, event: str) -> str:
    """'pass', the size of the context line as '<k>k', or what else the hook did."""
    if proc is None:
        return "timeout"
    if proc.returncode != 0:
        return f"exit {proc.returncode}"
    if not proc.stdout.strip():
        return "pass"
    try:
        out = json_value(proc.stdout, "the output")["hookSpecificOutput"]
        text = out["additionalContext"]
    except ValueError, KeyError, TypeError:
        return "unreadable output"
    match = re.match(r"Context: (\d+)k tokens, above the hand-off mark of 400k\.", text)
    return f"{match.group(1)}k" if match and out["hookEventName"] == event else f"other output {text[:60]!r}"


# `install-drift.py`, the `SessionStart` hook, runs against an installation that `harness install
# --apply` makes in a fixture of its own, with the dummy profile and tree instructions in the
# fixture. It decides nothing and exits 0: "quiet" is no output, "warn" a `systemMessage`.
DRIFT = HOOKS + "install-drift.py"
REPO = os.path.dirname(os.path.dirname(HOOKS))
STAMP = ".harness-install.json"

# oh-my-pi's guard extension, `adapters/omp/guards.ts`, and OpenCode's plugins,
# `adapters/opencode/plugins/*.ts`, run under `node` with a stub of their APIs. Each is copied into a
# fixture home as `<name>.mjs`, so that a `node` with no TypeScript support loads it too; the files
# therefore hold JavaScript syntax only. A home holds the extension in `extensions/`, or the plugins
# in `plugins/`, beside the path list that `harness install` renders with the dummy profile and the
# home, with this interpreter as its `python`; a copy of the guard package in `hooks/guard/`, never a
# link; and `.ssh/` with mode 000 (CLOSED_SSH), `.omp/`, `Research/P/.git/` and `bin/`. The groups
# `omp` and `opencode` run each record of their frontend in `tests/guard/corpus.jsonl` through the
# extension or the plugin and the guard, and the edges of the transport that a record cannot hold: an
# interpreter that is missing, a guard that exits 3 after its answer, prints `{`, is killed after its
# answer or does not answer in time, a path list that is missing, malformed or without `python`, and
# a message that the guard cannot read. The timeout case runs a copy whose timeout is 0.3 s, so that
# it costs no 10 s. The group `omp` also runs the GPU shell check on the script files that
# `gpu_script_cases` makes below the home.
#
# An oh-my-pi record holds `tool`, `input`, the `decision` and, where it needs them, `cwd`, the
# session's working directory (CWD by default), and `agent`, the kind of the context's agent. An
# OpenCode record holds `tool`, `input`, the `decision` and, where it needs them, `directory`, the
# session's directory (CWD by default; "" for a context with no `location`), `process_cwd`, the
# working directory of `node`, and `local`, the list in `$OPENCODE_CONFIG_DIR/guard-paths.json`.
# `covers` names the functions of the base's path guards that a record exercises, and `differs`
# why the guard decides otherwise than they do. `@@OMPHOME@@` and `@@OCHOME@@` stand for the two
# fixture homes. A decision is `pass`, `ask` (a refusal whose reason holds ASK_USER) or `deny`.
#
# The oh-my-pi driver hands the extension's `tool_call` handler one event and prints its answer.
OMP_DRIVER = """
const [ext, event, cwd, mode] = process.argv.slice(1);
let handler = null;
const mod = await import(ext);
await mod.default({ on: (name, h) => { if (name === 'tool_call') handler = h; } });
let ev = JSON.parse(event);
// "throw": reading the event's input throws, so the handler's own error path runs.
if (mode === 'throw') ev = new Proxy(ev, { get: (t, k) => { if (k === 'input') throw new Error('probe'); return t[k]; } });
// "sub" and "main": the context names the agent as oh-my-pi does for a sub-agent and the session.
const agent = { sub: { kind: 'sub', id: 'Probe', name: 'reader', depth: 1, parentId: 'main' },
                main: { kind: 'main', id: 'main', name: 'main', depth: 0 } }[mode];
const answer = await handler(ev, agent ? { cwd, agent } : { cwd });
process.stdout.write(JSON.stringify(answer ?? null));
"""
OMP_HOME = FIXTURE.name + "/omp-home"
OC_HOME = FIXTURE.name + "/oc-home"
ASK_USER = "Ask the user in chat"
# A bash command, and the verdict of `harness.yml`'s `bash.patterns` on it, rendered with the dummy
# profile, by oh-my-pi's matching (`src/tools/bash.ts` at v18.6.1): the first rule that matches
# wins; `allow` matches only a whole command with no shell control character; `deny` and `prompt`
# match the whole command or one of its segments. This port splits segments by text, so it stands
# for oh-my-pi on the simple commands below and is no evidence for a compound one. No pattern
# prompts for `gh pr create`: one with `-R` or `--repo` on an organisation of the profile is
# allowed, and any other matches no pattern, so `yolo` runs it and the guard extension decides it
# (the `gh pr create` records of the corpus). A lease push, a cherry-pick and a forced worktree
# removal meet no rule, or the `allow` of a worktree path: the guard's git write check blocks the
# unsafe ones.
OMP_PATTERNS = [
    ("git push --force origin x", "deny"),
    ("git push --force-with-lease origin x", "none"),
    ("git push --force-with-lease=x origin HEAD:refs/heads/main", "deny"),
    ("git cherry-pick abc123", "none"),
    ("git worktree remove --force /r/.worktrees/x", "allow"),
    ("sed -i s/a/b/ f", "deny"),
    ("cat ~/.local/share/opencode/auth.json", "allow"),
    ("git status", "allow"),
    ("ls -la", "allow"),
    ("gh pr create --repo example-org/X.jl --title T --body-file b.md", "allow"),
    ("gh pr create -R example-user/X.jl --title T", "allow"),
    ("gh pr create --title T --repo example-org/X.jl", "allow"),
    ("gh pr create --title T -R example-org/X.jl", "allow"),
    ("gh pr create --repo example-org/X.jl --title T 2>&1 | tail -3", "none"),
    ("gh pr create --repo other/X.jl --title T", "none"),
    ("gh pr create --title T --body-file b.md", "none"),
    ("gh pr create", "none"),
]


def omp_pattern(command, patterns):
    """The approval of the first rule of `patterns` that matches `command`, or "none"."""

    def norm(s):
        return re.sub(r"\s+", " ", s.strip())

    def matches(glob, text):
        return re.fullmatch(".*".join(re.escape(p) for p in norm(glob).split("*")), text) is not None

    whole = norm(command)
    segments = [norm(s) for s in re.split(r"&&|\|\||[;|&\n()]", command) if s.strip()]
    control = re.search(r"[;&|<>`$()\n]", command)
    for rule in patterns:
        if rule["approval"] == "allow":
            if not control and matches(rule["match"], whole):
                return "allow"
        elif matches(rule["match"], whole) or any(matches(rule["match"], s) for s in segments):
            return rule["approval"]
    return "none"


class PluginReply(NamedTuple):
    """The answer of a plugin and the guard to one event: `pass`, `ask`, `deny` or what went wrong;
    the reason of a refusal; and the seconds it took."""

    decision: str
    reason: str
    seconds: float


def json_value(text: str, where: str) -> Any:
    """The JSON value of `text`, read by the harness's `jsonio` with `top=object`. A refusal names
    `where` and raises ValueError, as `json` raises on a text that it cannot read."""
    if REPO + "/lib" not in sys.path:
        sys.path.insert(0, REPO + "/lib")
    harness = importlib.import_module("harness")
    jsonio = importlib.import_module("harness.jsonio")
    try:
        return jsonio.loads(text, where=where, top=object)
    except harness.HarnessError as e:
        raise ValueError(str(e)) from None


def rendered_list(frontend: str, home: str, python: str | None) -> str:
    """The path list that `harness install` writes beside the plugin of `frontend` for the home
    `home`, with `python` as its interpreter, or with no `python` for None."""
    sys.path.insert(0, REPO + "/lib")
    frontends = importlib.import_module("harness.frontends")
    profile = importlib.import_module("harness.profile")
    dummy = replace(profile.load(REPO + "/examples/profile.toml"), home=home)
    if frontend == "omp":
        text = str(frontends.adapter("omp").guard_paths(dummy))
    else:
        text = str(profile.render_file(REPO + "/adapters/opencode/plugins/guard-paths.json", dummy))
    listed = cast("dict[str, object]", json_value(text, "the rendered path list"))
    return json.dumps(listed if python is None else {**listed, "python": python}, indent=2) + "\n"


def plugin_home(
    frontend: str, name: str, *, listed: str | None = "", timeout: int | None = None, rtk: str | None = None
) -> str:
    """A fixture home `name` for `frontend`, `omp` or `opencode`, as the comment above OMP_DRIVER
    says: the path list `listed`, the rendered one for "", none for None; the plugin's timeout
    replaced by `timeout` milliseconds; `rtk`, the text of a fixture `bin/rtk`."""
    home = pathlib.Path(FIXTURE.name, name)
    layout = "extensions" if frontend == "omp" else "plugins"
    sources = (
        {"guards": "adapters/omp/guards.ts"}
        if frontend == "omp"
        else {plugin: f"adapters/opencode/plugins/{plugin}.ts" for plugin in OC_PLUGINS}
    )
    for directory in (layout, ".omp", "Research/P/.git", "bin"):
        (home / directory).mkdir(parents=True)
    closed_ssh(home)
    own_profile(str(home))
    shutil.copytree(GUARD, home / "hooks" / "guard", ignore=shutil.ignore_patterns("__pycache__"))
    for plugin, source in sources.items():
        text = pathlib.Path(REPO, source).read_text(encoding="utf-8")
        line = "const TIMEOUT_MS = 10_000;"
        if timeout is not None and plugin == "guards":
            if line not in text:
                raise OSError(f"{source} holds no line {line!r}, which the timeout case replaces")
            text = text.replace(line, f"const TIMEOUT_MS = {timeout};")
        (home / layout / f"{plugin}.mjs").write_text(text, encoding="utf-8")
    if rtk is not None:
        (home / "bin" / "rtk").write_text(rtk, encoding="utf-8")
        (home / "bin" / "rtk").chmod(0o755)
    if listed is not None:
        text = listed or rendered_list(frontend, str(home), sys.executable)
        (home / layout / "guard-paths.json").write_text(text, encoding="utf-8")
    return str(home)


def plugin_records(frontend: str) -> list[dict[str, Any]]:
    """Each record of `frontend` in the corpus, its placeholders replaced by the fixture's values."""
    extra = {"OMPHOME": OMP_HOME, "OCHOME": OC_HOME, "OUT": FIXTURE.name}
    found = (json_object(line) for line in corpus_lines(extra))
    return [record for record in found if record is not None and record.get("frontend") == frontend]


def refusal(reason: str, seconds: float) -> PluginReply:
    """The reply of a refusal: `ask` when its reason holds ASK_USER, else `deny`."""
    return PluginReply("ask" if ASK_USER in reason else "deny", reason, seconds)


def omp_reply(
    home: str,
    call: tuple[str, object],
    *,
    cwd: str = CWD,
    mode: str = "",
    path: str | None = None,
    extra: dict[str, str] | None = None,
    drop: tuple[str, ...] = (),
) -> PluginReply:
    """The extension's answer in the home `home` to one event of the call (tool, input), in the
    working directory `cwd`, the driver in the mode `mode`; `path`, the `PATH` of `node`; `extra`,
    further variables of its environment; `drop`, the variables of this process that it lacks."""
    node = shutil.which("node") or "node"
    tool, data = call
    event = json.dumps({"type": "tool_call", "toolCallId": "probe", "toolName": tool, "input": data})
    env = {**{k: v for k, v in CLEAN.items() if k not in drop}, "HOME": home, **(extra or {})}
    if path is not None:
        env["PATH"] = path
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [
                node,
                "--input-type=module",
                "-e",
                OMP_DRIVER,
                home + "/extensions/guards.mjs",
                event,
                cwd,
                mode,
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PluginReply("timeout", "", time.monotonic() - start)
    seconds = time.monotonic() - start
    if proc.stdout.strip() == "null":
        return PluginReply("pass", "", seconds)
    answer = json_object(proc.stdout)
    reason = answer.get("reason") if answer is not None else None
    if answer is None or answer.get("block") is not True or not isinstance(reason, str) or not reason:
        return PluginReply(f"exit {proc.returncode}, output {proc.stdout[-80:]!r}", "", seconds)
    return refusal(reason, seconds)


def guard_message(home: str, frontend: str, data: bytes) -> str:
    """The guard's stdout in the home `home` on the message bytes `data` from `frontend`."""
    proc = subprocess.run(
        [sys.executable, home + "/hooks/guard", "--from", frontend],
        input=data,
        capture_output=True,
        env={**CLEAN, "HOME": home},
        timeout=TIMEOUT,
        check=False,
    )
    return f"exit {proc.returncode}: " + proc.stdout.decode("utf-8", "replace").strip()


def fake_interpreters(frontend: str) -> dict[str, str]:
    """The interpreters of the transport cases of `frontend`, by label: one that is missing, and
    scripts that run the guard and exit 3, print `{` or a block with no reason, run the guard and
    are killed, or answer late."""
    fakes = pathlib.Path(FIXTURE.name, f"fakes-{frontend}")
    fakes.mkdir()
    python = shlex.quote(sys.executable)
    texts = {
        "the guard exits 3 after its answer": f'#!/bin/sh\n{python} "$@"\nexit 3\n',
        "the guard prints {": "#!/bin/sh\ncat > /dev/null\necho '{'\n",
        "the guard blocks with no reason": "#!/bin/sh\ncat > /dev/null\n"
        + 'echo \'{"block": true, "reason": ""}\'\n',
        "the guard is killed after its answer": f'#!/bin/sh\n{python} "$@"\nkill -9 $$\n',
        "the guard answers after the timeout": f'#!/bin/sh\nsleep 1\nexec {python} "$@"\n',
    }
    found = {"the interpreter is missing": str(fakes / "missing")}
    for number, (label, text) in enumerate(texts.items()):
        script = fakes / f"python-{number}"
        script.write_text(text, encoding="utf-8")
        script.chmod(0o755)
        found[label] = str(script)
    return found


def transport_homes(frontend: str) -> dict[str, tuple[str, str]]:
    """(home, text the reason holds) of each transport case of `frontend`, by label: each fake
    interpreter as the list's `python`, the timeout case on a copy whose timeout is 0.3 s, a list
    with no `python`, a list that is no JSON, and no list."""
    homes: dict[str, tuple[str, str]] = {}
    for number, (label, interpreter) in enumerate(fake_interpreters(frontend).items()):
        name = f"{frontend}-home-{number}"
        listed = rendered_list(frontend, str(pathlib.Path(FIXTURE.name, name)), interpreter)
        late = label == "the guard answers after the timeout"
        home = plugin_home(frontend, name, listed=listed, timeout=300 if late else None)
        homes[label] = (home, TRANSPORT_WANTS[label])
    for label, listed in (
        ("the path list has no python", None),
        ("the path list is no JSON", "{"),
        ("the path list is missing", ""),
    ):
        name = f"{frontend}-home-{len(homes)}"
        text = (
            rendered_list(frontend, str(pathlib.Path(FIXTURE.name, name)), None) if listed is None else listed
        )
        homes[label] = (plugin_home(frontend, name, listed=text or None), TRANSPORT_WANTS[label])
    return homes


def unusable_list_home(frontend: str, key: str, value: object) -> str:
    """A fixture home for `frontend` whose path list names this interpreter as its `python` but holds
    `value`, no list of strings, under `key`, which the guard itself refuses."""
    name = f"{frontend}-unusable-{key}"
    listed = json_value(
        rendered_list(frontend, str(pathlib.Path(FIXTURE.name, name)), sys.executable), "the path list"
    )
    return plugin_home(frontend, name, listed=json.dumps({**listed, key: value}))


# The text of the reason of each transport case.
TRANSPORT_WANTS = {
    "the interpreter is missing": "could not start",
    "the guard exits 3 after its answer": "exited with status 3",
    "the guard prints {": "printed no valid answer",
    "the guard blocks with no reason": "printed no valid answer",
    "the guard is killed after its answer": "SIGKILL",
    "the guard answers after the timeout": "did not answer within 0.3 s",
    "the path list has no python": "no string",
    "the path list is no JSON": "could not start",
    "the path list is missing": "could not start",
}


def omp_cases():
    """The cases of the oh-my-pi guard extension: (number of cases, number wrong)."""
    report = AgyReport()
    if shutil.which("node") is None:
        report(
            ok=False,
            line="exp node got none  [omp-guard]  `node` is not on PATH, so no case of guards.ts runs",
        )
        return report.total, report.wrong
    sys.path.insert(0, REPO + "/lib")
    try:
        omp = importlib.import_module("harness.frontends").adapter("omp")
        dummy = importlib.import_module("harness.profile").load(REPO + "/examples/profile.toml")
        config = omp.render_config(dummy, omp.load_models(REPO + "/examples/models.toml"))
        lines = config.splitlines(keepends=True)
        patterns = json_value("".join(line for line in lines if not line.startswith("#")), "the config")
        patterns = patterns["bash"]["patterns"]
        good = plugin_home("omp", "omp-home")
        opened = plugin_home("omp", "omp-open")
        launcher_home(opened, enabled=True)
        opened_unusable = unusable_list_home("omp", "ask", "x")
        launcher_home(opened_unusable)
        homes = transport_homes("omp")
        unusable = {
            key: unusable_list_home("omp", key, value) for key, value in (("deny", "x"), ("edit", [1]))
        }
    # The adapter, the profile and the rendering fail with HarnessError, an input of an unexpected
    # shape with the others; the case reports it as wrong, and the probe goes on to its summary.
    except (ImportError, OSError, ValueError, LookupError, TypeError, AttributeError, RuntimeError) as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [omp-guard]  {e}")
        return report.total, report.wrong
    for record in plugin_records("omp"):
        cwd = str(record.get("cwd", CWD))
        got = omp_reply(
            good,
            (record["tool"], record["input"]),
            cwd=cwd,
            mode=str(record.get("agent", "")),
            extra=profile_env(record),
        )
        report(
            ok=got.decision == record["decision"],
            line=f"exp {record['decision']} got {got.decision}  [omp-guard]  {record['tool']} "
            f"{json.dumps(record['input'])[:160]} in {cwd} {record.get('agent', '')}"
            + (f" with the profile {record['profile']}" if "profile" in record else ""),
        )
    gpu_script_cases(report, good)
    for command, expected in OMP_PATTERNS:
        got = omp_pattern(command, patterns)
        report(ok=got == expected, line=f"exp {expected} got {got}  [omp-patts]  {command}")
    status = {"command": "git status"}
    # The launcher check: in a home whose `.ssh` the guard can list, a call that the corpus passes is
    # refused on macOS, also with the entrypoint and the settings of Claude Code's Code tab, which
    # count for Claude Code alone.
    got = omp_reply(opened, ("bash", status), extra={"CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})
    expected, reason = ("deny", LAUNCHER_OUTSIDE) if MAC else ("pass", "")
    report(
        ok=got.decision == expected and reason in got.reason,
        line=f"exp {expected} got {got.decision}  [omp-guard]  a readable .ssh, the Code tab's settings: "
        f"bash {status}: {got.reason[:70]!r}",
    )
    # The check runs before the guard reads its path list: a list that holds no list of strings under
    # `ask` gives the launcher's reason.
    got = omp_reply(opened_unusable, ("bash", status), drop=LAUNCHER_ENV)
    reason = LAUNCHER_OUTSIDE if MAC else "no list of strings"
    report(
        ok=got.decision == "deny" and reason in got.reason,
        line=f"exp deny, {reason!r} got {got.decision}  [omp-guard]  a readable .ssh and a list whose ask is "
        f"no list of strings: bash {status}: {got.reason[:70]!r}",
    )
    for label, (home, want) in homes.items():
        calls = [
            ("bash", status),
            *([("read", {"path": "src/Foo.jl"})] if label == "the path list is missing" else []),
        ]
        for tool, data in calls:
            got = omp_reply(home, (tool, data))
            report(
                ok=got.decision == "deny" and want in got.reason,
                line=f"exp deny, {want!r} got {got.decision}  [omp-guard]  fail-closed, {label}: "
                f"{tool} {data}: {got.seconds:.2f} seconds",
            )
    # The guard reads its path list before the tool: a list that holds no list of strings under a key
    # refuses every call, a tool that the table does not name too.
    for key, home in unusable.items():
        for tool, data in (("bash", status), ("read", {"path": "src/Foo.jl"}), ("lsp", {"action": "hover"})):
            got = omp_reply(home, (tool, data))
            report(
                ok=got.decision == "deny" and "no list of strings" in got.reason,
                line=f"exp deny got {got.decision}  [omp-guard]  a list whose {key} is no list of strings: "
                f"{tool} {data}",
            )
    got = omp_reply(good, ("bash", status), mode="throw")
    report(
        ok=got.decision == "deny" and "failed" in got.reason,
        line=f"exp deny got {got}  [omp-guard]  the handler throws",
    )
    # The extension runs the interpreter that the list names, never `python3` from the PATH.
    got = omp_reply(good, ("bash", status), path="/nonexistent")
    report(
        ok=got.decision == "pass",
        line=f"exp pass got {got.decision}  [omp-guard]  python3 is not on the PATH: git status",
    )
    for data in (b"not json", b'{"event": 5}', b'{"event": {"toolName": "bash", "input": {}}, "cwd": "/"}'):
        got = guard_message(good, "omp", data)
        ok = got.startswith('exit 0: {"block": true') and "cannot read" in got
        report(
            ok=ok,
            line=f"exp a block got {got[:120]!r}  [omp-guard]  a message the table cannot read: {data!r}",
        )
    # A relative `input.cwd` in a message whose `cwd` is not absolute has no place, so it is refused.
    data = b'{"event": {"toolName": "bash", "input": {"command": "cat id", "cwd": "../.ssh"}}, "cwd": "rel"}'
    got = guard_message(good, "omp", data)
    report(
        ok=got.startswith('exit 0: {"block": true'),
        line=f"exp a block got {got[:120]!r}  [omp-guard]  a relative cwd with no working directory",
    )
    size_cases(
        report,
        good,
        "omp",
        lambda command: {"event": {"toolName": "bash", "input": {"command": command}}, "cwd": CWD},
    )
    return report.total, report.wrong


def gpu_script_cases(report: AgyReport, home: str) -> None:
    """The GPU shell check on a `julia` run of a script file, under `AGENTBOX`, in the home `home`:
    below `home/gpu`, a `probe.jl` that holds `using Metal`, one that holds `println(1)`, one that
    holds `println(1)` after bytes that are not UTF-8, none, a FIFO and a directory of that name, a
    FIFO that holds `using Metal`, `probe.txt` that holds `using Metal`, and files whose `Metal`
    ends at the last byte of their first MiB or one byte after it. The Metal file is refused by its
    absolute path, by a path relative to the call's working directory and by a `~` path, and so is
    the file whose first MiB ends in `Metal`; every other case passes, the FIFOs without a block,
    since the check reads only a regular file whose name ends in `.jl`, and only its first MiB. In
    process, a read that fails adds nothing, and a call that is no shell call
    passes."""
    gpu = pathlib.Path(home, "gpu")
    for name in ("metal", "plain", "latin", "fifo", "fed", "dir", "missing", "near", "far"):
        (gpu / name).mkdir(parents=True)
    (gpu / "metal" / "probe.jl").write_text("using Metal\nMtlArray(Float32[1, 2, 3])\n", encoding="utf-8")
    (gpu / "metal" / "probe.txt").write_text("using Metal\n", encoding="utf-8")
    (gpu / "plain" / "probe.jl").write_text("println(1)\n", encoding="utf-8")
    (gpu / "latin" / "probe.jl").write_bytes(b"# \xff\xfe\nprintln(1)\n")
    # The guard reads the first MiB: `Metal` ends at its last byte in `near` and one byte after it in
    # `far`, so the first MiB of `far` ends in `Meta`.
    tail = b"\nusing Metal"
    (gpu / "near" / "probe.jl").write_bytes(b"#" * (1024 * 1024 - len(tail)) + tail)
    (gpu / "far" / "probe.jl").write_bytes(b"#" * (1024 * 1024 - len(tail) + 1) + tail)
    os.mkfifo(gpu / "fifo" / "probe.jl")
    os.mkfifo(gpu / "fed" / "probe.jl")
    (gpu / "dir" / "probe.jl").mkdir()
    # The read end first: a FIFO with no reader refuses a writer that does not block. The writer
    # closes before the call, so a reader of the FIFO gets the text and then its end.
    reader = os.open(gpu / "fed" / "probe.jl", os.O_RDONLY | os.O_NONBLOCK)
    try:
        writer = os.open(gpu / "fed" / "probe.jl", os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(writer, b"using Metal\n")
        finally:
            os.close(writer)
        got = omp_reply(home, ("bash", {"command": f"julia {gpu}/fed/probe.jl"}), extra={"AGENTBOX": "1"})
    finally:
        os.close(reader)
    report(
        ok=got.decision == "pass",
        line=f"exp pass got {got.decision}  [omp-gpu]  a FIFO that holds using Metal: "
        f"{got.seconds:.2f} seconds",
    )
    run = "julia --startup-file=no --project=. "
    cases = [
        ("the Metal file", run + f"{gpu}/metal/probe.jl", CWD, "deny"),
        ("the Metal file, relative to the call's directory", "julia probe.jl", f"{gpu}/metal", "deny"),
        ("the Metal file, by ~", "julia ~/gpu/metal/probe.jl", CWD, "deny"),
        ("the println file", run + f"{gpu}/plain/probe.jl", CWD, "pass"),
        ("the println file, relative to the call's directory", "julia probe.jl", f"{gpu}/plain", "pass"),
        ("the println file after bytes that are not UTF-8", run + f"{gpu}/latin/probe.jl", CWD, "pass"),
        ("no file", run + f"{gpu}/missing/probe.jl", CWD, "pass"),
        ("a FIFO", run + f"{gpu}/fifo/probe.jl", CWD, "pass"),
        ("a directory", run + f"{gpu}/dir/probe.jl", CWD, "pass"),
        ("the Metal text in no .jl file", run + f"{gpu}/metal/probe.txt", CWD, "pass"),
        ("Metal at the end of the first MiB", run + f"{gpu}/near/probe.jl", CWD, "deny"),
        ("Metal that ends one byte after the first MiB", run + f"{gpu}/far/probe.jl", CWD, "pass"),
    ]
    for label, command, cwd, expected in cases:
        got = omp_reply(home, ("bash", {"command": command}), cwd=cwd, extra={"AGENTBOX": "1"})
        report(
            ok=got.decision == expected,
            line=f"exp {expected} got {got.decision}  [omp-gpu]  {label}: {command} in {cwd}: "
            f"{got.seconds:.2f} seconds",
        )
    sys.path.insert(0, HOOKS)
    try:
        shell: Any = importlib.import_module("guard.gpu_shell")
        paths: Any = importlib.import_module("guard.paths")
        contract: Any = importlib.import_module("guard.contract")
    finally:
        sys.path.remove(HOOKS)
    with mock.patch.object(paths.os, "read", side_effect=OSError(errno.EIO, "probe")):
        text = paths.regular_prefix.__wrapped__(str(gpu / "metal" / "probe.jl"))
    report(ok=text == "", line=f"exp '' got {text!r}  [omp-gpu]  a regular file whose read fails")
    # The table runs the check on a shell call alone; the check itself passes any other call.
    command = "julia -e 'using Metal'"
    with mock.patch.dict(os.environ, {"AGENTBOX": "1"}):
        got = shell.check(contract.Call("read", command, (command,), CWD, "main")).decision
    report(ok=got == "pass", line=f"exp pass got {got}  [omp-gpu]  a read call whose path is {command}")


def size_cases(report: AgyReport, home: str, frontend: str, message: Callable[[str], object]) -> None:
    """The guard of `frontend` in the home `home` reads a command of 1 MiB, and refuses one of a
    byte more as a message that it cannot read; `message` gives the message of a command."""
    limit = 1024 * 1024
    for size, block in ((limit, False), (limit + 1, True)):
        got = guard_message(home, frontend, json.dumps(message("x" * size)).encode())
        ok = got.startswith(f'exit 0: {{"block": {str(block).lower()}') and (
            not block or "cannot read" in got
        )
        report(
            ok=ok, line=f"exp block {block} got {got[:120]!r}  [{frontend}-size]  a command of {size} bytes"
        )


# OpenCode v2's plugins, `adapters/opencode/plugins/*.ts`, run under `node` with a stub of the
# plugin context: the driver imports a plugin, calls its `setup(ctx)`, keeps the callbacks that
# `ctx.tool.hook` and `ctx.shell.hook` register under one hook name, and calls them in order on one
# event, as OpenCode 2.0.25 does. The event of `execute.before` is the shape the binary builds,
# `{tool, sessionID, agent, messageID, id, input}`, with the shell tool named `shell`; that of the
# shell's `create.before` is `{command, cwd, timeout, shell, env}`; `ctx.location.directory` is the
# session's directory, and an empty directory leaves `location` out of the stub context. A hook that
# throws refuses the call, and the driver prints the reason, the event after the hooks, the plugin's
# exports and its id. An rtk case runs `node` with the fixture home's `bin/` as its whole `PATH`, so
# the plugin finds the fixture `rtk` there or none.
OC_DRIVER = """
const [plugin, kind, name, event, dir] = process.argv.slice(1);
const hooks = [];
const register = (k) => async (n, cb) => {
  if (k === kind && n === name) hooks.push(cb);
  return { dispose: async () => {} };
};
const mod = await import(plugin);
const out = { exports: Object.keys(mod).sort(), id: mod.default?.id };
const ctx = { tool: { hook: register('tool') }, shell: { hook: register('shell') } };
if (dir !== '') ctx.location = { directory: dir };
try {
  await mod.default.setup(ctx);
} catch (e) {
  out.setup = String(e?.message ?? e);
}
const ev = JSON.parse(event);
out.hooks = hooks.length;
try {
  for (const cb of hooks) await cb(ev);
  out.verdict = 'pass';
} catch (e) {
  out.verdict = 'refuse';
  out.reason = String(e?.message ?? e);
}
out.event = ev;
process.stdout.write(JSON.stringify(out));
"""
OC_PLUGINS = {
    "guards": "research-harness.guards",
    "rtk": "research-harness.rtk",
    "env": "research-harness.env",
}
OC_GUARD = "research-harness.guards"  # each refusal of a guard that cannot answer names the plugin


def oc_event(command: str | None, tool: str = "shell", **fields: object) -> dict[str, object]:
    """An `execute.before` event of OpenCode 2.0.25 for one call of `tool`, whose input holds
    `command`, unless it is None, and `fields`."""
    data = {"command": command, **fields} if command is not None else fields
    return {
        "tool": tool,
        "sessionID": "probe-session",
        "agent": "build",
        "messageID": "probe-message",
        "id": "probe-call",
        "input": data,
    }


def oc_cases():
    """The cases of the OpenCode plugins: (number of cases, number wrong)."""
    report = AgyReport()
    node = shutil.which("node")

    def drive(
        h: str,
        plugin: str,
        event: object,
        kind: str = "tool",
        name: str = "execute.before",
        cwd: str = CWD,
        process_cwd: str | None = None,
        path: str | None = None,
        config_dir: str | None = None,
        extra: dict[str, str] | None = None,
        drop: tuple[str, ...] = (),
    ) -> Any:
        """The driver's answer for one event, or the text of what went wrong. `cwd` is the
        session's directory, `ctx.location.directory`, or "" for a context with no `location`;
        `process_cwd`, the working directory of the `node` process, or None for this one's; `path`,
        the `PATH` of the `node` process, or None for this one's; `config_dir`, its
        `OPENCODE_CONFIG_DIR`, or None for none; `extra`, further variables of its environment;
        `drop`, the variables of this process that it lacks."""
        env = {k: v for k, v in CLEAN.items() if k != "OPENCODE_CONFIG_DIR" and k not in drop} | (extra or {})
        if path is not None:
            env["PATH"] = path
        if config_dir is not None:
            env["OPENCODE_CONFIG_DIR"] = config_dir
        # oc_cases returns before its first case when `node` is not on PATH.
        if node is None:
            raise RuntimeError("`node` is not on PATH")
        try:
            p = subprocess.run(
                [
                    node,
                    "--input-type=module",
                    "-e",
                    OC_DRIVER,
                    h + f"/plugins/{plugin}.mjs",
                    kind,
                    name,
                    json.dumps(event),
                    cwd,
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                env={**env, "HOME": h},
                cwd=process_cwd,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        if p.returncode != 0:
            return f"exit {p.returncode}: {p.stderr.strip()[-160:]!r}"
        try:
            return json_value(p.stdout, "the output")
        except ValueError:
            return f"unreadable output {p.stdout[-80:]!r}"

    if node is None:
        report(
            ok=False,
            line="exp node got none  [oc-plugin]  `node` is not on PATH, so no case of the plugins runs",
        )
        return report.total, report.wrong
    # The fixture's rewrite is not the real RTK's `rtk git status`, so an `rtk` found elsewhere than
    # on the fixture's PATH, such as a fixed path in the plugin, cannot give it.
    rewrite = (
        '#!/bin/sh\nif [ "$1 $2 $3" = "hook check git status" ]; then echo "fixture-rtk git status"; exit 0; fi\n'
        'echo "No rewrite for: $3"; exit 1\n'
    )
    try:
        good = plugin_home("opencode", "oc-home", rtk=rewrite)
        opened = plugin_home("opencode", "oc-open")
        launcher_home(opened, enabled=True)
        fail = {
            "rtk exits 1": plugin_home(
                "opencode", "oc-rtk-1", rtk='#!/bin/sh\necho "rtk git status"\nexit 1\n'
            ),
            "no rtk": plugin_home("opencode", "oc-rtk-none"),
        }
        homes = transport_homes("opencode")
        unusable = unusable_list_home("opencode", "deny", ["/etc/**", 1])
    # The profile and the rendering fail with HarnessError, an input of an unexpected shape with the
    # others; the case reports it as wrong, and the probe goes on to its summary.
    except (ImportError, OSError, ValueError, LookupError, TypeError, AttributeError, RuntimeError) as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [oc-plugin]  {e}")
        return report.total, report.wrong

    def reply(
        home: str,
        event: object,
        place: tuple[str, str | None] = (CWD, None),
        *,
        config_dir: str | None = None,
        path: str | None = None,
        extra: dict[str, str] | None = None,
        drop: tuple[str, ...] = (),
    ) -> PluginReply:
        """The guard plugin's answer in the home `home` to one event, with the session's directory and
        the directory of `node` of `place`, and the options of `drive`."""
        start = time.monotonic()
        directory, process_cwd = place
        answer = drive(
            home,
            "guards",
            event,
            cwd=directory,
            process_cwd=process_cwd,
            config_dir=config_dir,
            path=path,
            extra=extra,
            drop=drop,
        )
        seconds = time.monotonic() - start
        if isinstance(answer, str) or "setup" in answer:
            return PluginReply(f"no answer: {str(answer)[:120]}", "", seconds)
        return (
            PluginReply("pass", "", seconds)
            if answer["verdict"] == "pass"
            else refusal(answer["reason"], seconds)
        )

    # The v2 form: a default export {id, setup} and no other, and no module imported.
    for plugin, id in OC_PLUGINS.items():
        answer = drive(good, plugin, oc_event("true"))
        got = answer if isinstance(answer, str) else (answer["exports"], answer["id"], answer.get("setup"))
        report(
            ok=got == (["default"], id, None),
            line=f"exp {(['default'], id, None)} got {got}  [oc-plugin]  {plugin}.ts",
        )
        with open(REPO + f"/adapters/opencode/plugins/{plugin}.ts") as f:
            imports = [
                l.strip() for l in f if re.match(r"\s*import\b", l) or re.search(r"\b(?:import|require)\(", l)
            ]
        report(ok=imports == [], line=f"exp no import got {imports}  [oc-plugin]  {plugin}.ts")

    # Each OpenCode record of the corpus; a `local` list goes to a directory of its own, which
    # `$OPENCODE_CONFIG_DIR` names.
    for number, record in enumerate(plugin_records("opencode")):
        config_dir = None
        if "local" in record:
            config = pathlib.Path(FIXTURE.name, "oc-local", str(number))
            config.mkdir(parents=True)
            (config / "guard-paths.json").write_text(json.dumps(record["local"]), encoding="utf-8")
            config_dir = str(config)
        directory = str(record.get("directory", CWD))
        event = {**oc_event(None, tool=record["tool"]), "input": record["input"]}
        got = reply(
            good,
            event,
            (directory, record.get("process_cwd")),
            config_dir=config_dir,
            extra=profile_env(record),
        )
        report(
            ok=got.decision == record["decision"],
            line=f"exp {record['decision']} got {got.decision}  [oc-guards]  {record['tool']} "
            f"{json.dumps(record['input'])[:160]} in {directory or record.get('process_cwd')}"
            + (f" with the local list {record['local']}" if "local" in record else "")
            + (f" with the profile {record['profile']}" if "profile" in record else ""),
        )

    # The launcher check: in a home whose `.ssh` the guard can list, a call that the corpus passes is
    # refused on macOS, also with the entrypoint and the settings of Claude Code's Code tab, which
    # count for Claude Code alone.
    status = oc_event("git status")
    got = reply(opened, status, extra={"CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})
    expected, reason = ("deny", LAUNCHER_OUTSIDE) if MAC else ("pass", "")
    report(
        ok=got.decision == expected and reason in got.reason,
        line=f"exp {expected} got {got.decision}  [oc-guards]  a readable .ssh, the Code tab's settings: "
        f"shell git status: {got.reason[:70]!r}",
    )
    # The check runs before the guard reads its path lists: a local list that is no JSON gives the
    # launcher's reason.
    broken = pathlib.Path(FIXTURE.name, "oc-local", "launcher")
    broken.mkdir(parents=True)
    (broken / "guard-paths.json").write_text("{", encoding="utf-8")
    got = reply(opened, status, config_dir=str(broken), drop=LAUNCHER_ENV)
    reason = LAUNCHER_OUTSIDE if MAC else "so the call is blocked"
    report(
        ok=got.decision == "deny" and reason in got.reason,
        line=f"exp deny, {reason!r} got {got.decision}  [oc-guards]  a readable .ssh and a local list that "
        f"is no JSON: shell git status: {got.reason[:70]!r}",
    )

    # It fails closed: each refuses `git status`, and a missing list a read too, with a reason that
    # names the plugin and the cause.
    for label, (home, want) in homes.items():
        events = [
            status,
            *(
                [oc_event(None, tool="read", filePath="src/Foo.jl")]
                if label == "the path list is missing"
                else []
            ),
        ]
        for event in events:
            got = reply(home, event)
            report(
                ok=got.decision == "deny" and want in got.reason and OC_GUARD in got.reason,
                line=f"exp deny, {want!r} got {got.decision}  [oc-guards]  fail-closed, {label}: "
                f"{event['tool']}: {got.seconds:.2f} seconds",
            )
    # With no path list, `setup` still resolves and registers its hook.
    answer = drive(homes["the path list is missing"][0], "guards", status)
    got = answer if isinstance(answer, str) else (answer.get("setup"), answer["hooks"])
    report(ok=got == (None, 1), line=f"exp {(None, 1)} got {got}  [oc-guards]  setup with no path list")
    # The plugin runs the interpreter that the list names, never `python3` from the PATH.
    got = reply(good, status, path="/nonexistent")
    report(
        ok=got.decision == "pass",
        line=f"exp pass got {got.decision}  [oc-guards]  python3 is not on the PATH: git status",
    )
    for data in (
        b"not json",
        b'{"event": []}',
        b'{"event": {"tool": "shell", "input": {}}, "directory": "/"}',
    ):
        got = guard_message(good, "opencode", data)
        ok = got.startswith('exit 0: {"block": true') and "cannot read" in got
        report(
            ok=ok,
            line=f"exp a block got {got[:120]!r}  [oc-guards]  a message the table cannot read: {data!r}",
        )
    size_cases(
        report,
        good,
        "opencode",
        lambda command: {"event": {"tool": "shell", "input": {"command": command}}, "directory": CWD},
    )

    # The guard reads its path lists before the tool: a list that holds no list of strings under
    # `deny`, and a local list in `$OPENCODE_CONFIG_DIR` that is no JSON or holds no list of strings
    # under `allow`, refuse every call, a tool that the table does not check too.
    unread = [
        status,
        oc_event(None, tool="read", filePath="src/Foo.jl"),
        oc_event(None, tool="kaimon_ex", e="1", ses="x"),
    ]
    for event in unread:
        got = reply(unusable, event)
        report(
            ok=got.decision == "deny" and "no list of strings" in got.reason,
            line=f"exp deny got {got.decision}  [oc-guards]  a list whose deny is no list of strings: "
            f"{event['tool']}",
        )
    for label, text in (("is no JSON", '{"allow": ['), ("holds an allow that is no list", '{"allow": "x"}')):
        local = pathlib.Path(FIXTURE.name, "oc-local", label.replace(" ", "-"))
        local.mkdir(parents=True)
        (local / "guard-paths.json").write_text(text, encoding="utf-8")
        for event in unread:
            got = reply(good, event, config_dir=str(local))
            report(
                ok=got.decision == "deny" and "so the call is blocked" in got.reason,
                line=f"exp deny got {got.decision}  [oc-guards]  a local list that {label}: {event['tool']}",
            )
    # A `$OPENCODE_CONFIG_DIR` that holds no list adds no rule.
    empty = pathlib.Path(FIXTURE.name, "oc-local", "empty")
    empty.mkdir(parents=True)
    got = reply(good, status, config_dir=str(empty))
    report(
        ok=got.decision == "pass",
        line=f"exp pass got {got.decision}  [oc-guards]  a config directory with no list: git status",
    )

    # The rewrite: (home, command after the hook, verdict). The plugin finds `rtk` on the PATH of
    # `node` alone, which is the home's `bin/`: the fixture there, or no `rtk` at all.
    for label, h, expected in [
        ("rtk rewrites", good, ("fixture-rtk git status", "pass")),
        ("rtk exits 1", fail["rtk exits 1"], ("git status", "pass")),
        ("no rtk on the PATH", fail["no rtk"], ("git status", "pass")),
    ]:
        answer = drive(h, "rtk", oc_event("git status"), path=h + "/bin")
        got = answer if isinstance(answer, str) else (answer["event"]["input"]["command"], answer["verdict"])
        report(ok=got == expected, line=f"exp {expected!r} got {got!r}  [oc-rtk   ]  {label}: git status")
    # Only the `shell` tool's command is rewritten.
    answer = drive(good, "rtk", oc_event("git status", tool="bash"), path=good + "/bin")
    got = answer if isinstance(answer, str) else answer["event"]["input"]["command"]
    report(
        ok=got == "git status",
        line=f"exp 'git status' got {got!r}  [oc-rtk   ]  rtk rewrites, a bash event: git status",
    )

    # The environment of a shell command.
    event = {"command": "true", "cwd": CWD, "timeout": 0, "shell": "/bin/zsh", "env": {"A": "1"}}
    answer = drive(good, "env", event, kind="shell", name="create.before")
    got = answer if isinstance(answer, str) else answer["event"]["env"]
    expected = {
        "A": "1",
        "JULIA_PKG_USE_CLI_GIT": "true",
        "JULIA_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
    }
    report(ok=got == expected, line=f"exp {expected} got {got}  [oc-env   ]  create.before")
    return report.total, report.wrong


# Antigravity's guard: the guard package run with `--from antigravity`, as `hooks.json` runs it, from
# a fixture home's `.gemini/config/`, which is no git work tree, as the real one is not. The package
# is a copy of hooks/guard/ at `.gemini/config/hooks/guard/`, never a link, beside `guard-paths.json`
# rendered with the dummy profile and that home. A call gets the payload that Antigravity sends,
# `toolCall` and `workspacePaths`; its working directory is CWD, the probe's work tree, unless the
# case names another. The group runs each Antigravity record of `tests/guard/corpus.jsonl` and the
# edges that a record cannot hold: a broken path list, a payload that cannot be read, no workspace,
# commands of many words and of 1 MiB, the work of a payload, the rendered handler, and a check
# that raises.
AGY_HOME = FIXTURE.name + "/agy-home"
AGY_ELSEWHERE = FIXTURE.name + "/agy-elsewhere"
AGY_MAX_GIT = 2  # the git spawns that a payload of the counted rows may make
# The verdict of the rendered `permissions` rules, deny before ask before allow, on a command.
AGY_PERMS = (("git push --force origin x", "deny"), ("sed -i s/a/b/ f", "deny"), ("git status", "allow"))
# Commands that a rule of the template's excludedCommands allows in the app's policy, which the guard,
# run before that policy, still refuses or asks for: (command, decision, the allow rule).
AGY_GRANTS = (
    ("git push --force origin x", "deny", "command(git)"),
    ("git add -A", "deny", "command(git)"),
    ("gh pr merge 1", "force_ask", "command(gh)"),
)
# The line of the core's rule that the case of an installed rule that lifts julia replaces.
AGY_EXCLUDED = 'EXCLUDED = frozenset({"git", "gh", "glab", "ps"})\n'
# Runs the guard package `sys.argv[2]` with `--from antigravity` after its rm check is replaced by one
# that raises, the package's parent directory `sys.argv[1]` first on `sys.path`.
AGY_RAISES = """
import runpy, sys
sys.path.insert(0, sys.argv[1])
import guard.rm_scope
def raising(call):
    raise RuntimeError("probe: a check raises")
guard.rm_scope.check = raising
sys.argv = [sys.argv[2], "--from", "antigravity"]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


class AgyReply(NamedTuple):
    """The answer of the guard to one Antigravity payload: its decision, or what went wrong; its
    reason, or None when it has none; its `overwrite`, or "none"; and the seconds it took."""

    decision: str
    reason: str | None
    overwrite: object
    seconds: float


class AgyReport:
    """The count of the Antigravity cases and of those that are wrong; a call reports one case."""

    def __init__(self) -> None:
        self.total = 0
        self.wrong = 0

    def __call__(self, *, ok: bool, line: str) -> None:
        self.total, self.wrong = self.total + 1, self.wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")


def json_object(text: str) -> dict[str, object] | None:
    """The JSON object of `text`, or None when it holds no JSON object."""
    try:
        value: object = json_value(text, "the text")
    except ValueError:
        return None
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def agy_payload(tool: object, args: object, workspace: str | None = CWD) -> str:
    """The payload that Antigravity sends for a call of `tool` with `args`, with `workspace` as the
    one workspace path, or with none for None."""
    return json.dumps(
        {
            "conversationId": "probe",
            "modelName": "probe",
            "stepIdx": 1,
            "toolCall": {"name": tool, "args": args},
            "workspacePaths": [] if workspace is None else [workspace],
        }
    )


def agy_reply(
    home: str, payload: str, *, limit: float = TIMEOUT, extra: dict[str, str] | None = None
) -> AgyReply:
    """The guard's answer to `payload`, run as `hooks.json` runs it from the fixture home `home`
    within `limit` seconds; `extra`, further variables of its environment."""
    config = pathlib.Path(home, ".gemini", "config")
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(config / "hooks" / "guard"), "--from", "antigravity"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=limit,
            cwd=config,
            env={**CLEAN, "HOME": "/" + home, **(extra or {})},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return AgyReply("timeout", None, "none", time.monotonic() - start)
    seconds = time.monotonic() - start
    answer = json_object(proc.stdout)
    if proc.returncode != 0 or answer is None or not isinstance(answer.get("decision"), str):
        return AgyReply(f"exit {proc.returncode}, output {proc.stdout[-80:]!r}", None, "none", seconds)
    reason = answer.get("reason")
    return AgyReply(
        str(answer["decision"]),
        None if reason is None else str(reason),
        answer.get("overwrite", "none"),
        seconds,
    )


def bypass_of(overwrite: object) -> object:
    """The `BypassSandbox` of an `overwrite` that holds it alone, as a bool; None for no `overwrite`;
    the `overwrite` written out for any other."""
    if overwrite == "none":
        return None
    found = cast("dict[str, object]", overwrite) if isinstance(overwrite, dict) else {}
    value = found.get("BypassSandbox")
    return value if set(found) == {"BypassSandbox"} and isinstance(value, bool) else f"{overwrite!r}"


def corpus_lines(extra: dict[str, str]) -> list[str]:
    """Each line of the corpus, each placeholder `@@NAME@@` replaced by the fixture's value of NAME,
    or by that of `extra`, as JSON string text."""
    table = {
        "FIXTURE": FIXTURE.name,
        "HOME": HOME,
        "R": R,
        "WT": WT,
        "PKG": PKG,
        "TOOL": TOOL,
        "CWD": CWD,
        "SCRATCH": SCRATCH,
        "LINK": LINK,
        **TOKENS,
        **extra,
    }
    found: list[str] = []
    for line in pathlib.Path(REPO, "tests", "guard", "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        placed = line
        for name, value in table.items():
            placed = placed.replace(f"@@{name}@@", json.dumps(value)[1:-1])
        found.append(placed)
    return found


def agy_records(home: str) -> list[dict[str, object]]:
    """Each Antigravity record of the corpus, its placeholders replaced by the fixture's values and
    `@@AGYHOME@@` by `home`."""
    records: list[dict[str, object]] = []
    for placed in corpus_lines({"AGYHOME": home}):
        record = json_object(placed)
        if record is not None and record.get("frontend") == "antigravity":
            records.append(record)
    return records


class AgyFixture:
    """The adapter of Antigravity, the dummy profile and the rendered permission rules, and the fixture
    homes of the Antigravity cases."""

    def __init__(self) -> None:
        frontends = importlib.import_module("harness.frontends")
        profile = importlib.import_module("harness.profile")
        self.adapter: Any = frontends.adapter("antigravity")
        self.dummy: Any = profile.load(REPO + "/examples/profile.toml")
        settings: Any = frontends.adapter("claude").settings_template(
            self.dummy, FIXTURE.name + "/no-network.toml"
        )
        self.rules: dict[str, list[str]] = self.adapter.render_permissions(settings, self.dummy)[0]
        self.timeout = float(self.adapter.HOOK_TIMEOUT)

    def rendered(self, home: str) -> str:
        """The path list that the adapter renders for the home `home`."""
        return str(self.adapter.guard_paths(replace(self.dummy, home=home)))

    def home(self, name: str, paths: str | None = "", excluded: str | None = None) -> str:
        """A fixture home `name` with a copy of the guard package and the path list `paths`: the
        rendered one for "", none for None. `excluded` replaces the line AGY_EXCLUDED of the copy's
        `sandbox_semantics.py`."""
        home = FIXTURE.name + "/" + name
        config = pathlib.Path(home, ".gemini", "config")
        config.mkdir(parents=True)
        own_profile(home)
        shutil.copytree(GUARD, config / "hooks" / "guard", ignore=shutil.ignore_patterns("__pycache__"))
        if excluded is not None:
            rule = config / "hooks" / "guard" / "sandbox_semantics.py"
            text = rule.read_text(encoding="utf-8")
            if AGY_EXCLUDED not in text:
                raise OSError(f"{rule} holds no line {AGY_EXCLUDED!r}, which the case replaces")
            rule.write_text(text.replace(AGY_EXCLUDED, excluded), encoding="utf-8")
        if paths is not None:
            (config / "guard-paths.json").write_text(paths or self.rendered(home), encoding="utf-8")
        return home

    def permission(self, command: str) -> str:
        """The verdict of the rendered permission rules on `command`, deny before ask before allow."""
        for kind in ("deny", "ask", "allow"):
            if any(self.adapter.rule_matches(rule, command) for rule in self.rules[kind]):
                return kind
        return "none"


def agy_record_cases(report: AgyReport, home: str) -> None:
    """Each Antigravity record of the corpus, run in the home `home`: its decision and its
    `BypassSandbox`, a reason with each `deny` and `force_ask`, and none with an `ask`."""
    for record in agy_records(home):
        workspace = record.get("workspace", CWD)
        got = agy_reply(
            home,
            agy_payload(record["tool"], record["args"], str(workspace)),
            extra=profile_env(cast("dict[str, Any]", record)),
        )
        bypass = bypass_of(got.overwrite)
        reasoned = (got.reason is None) if got.decision == "ask" else bool(got.reason and got.reason.strip())
        want = (record["decision"], record["bypass"])
        report(
            ok=(got.decision, bypass) == want and reasoned,
            line=f"exp {want} got {(got.decision, bypass)}, reason {got.reason is not None}  [agy-guard]  "
            f"{record['tool']} {json.dumps(record['args'])[:160]}"
            + (f" in {workspace}" if "workspace" in record else "")
            + (f" with the profile {record['profile']}" if "profile" in record else ""),
        )


def agy_policy_cases(report: AgyReport, fixture: AgyFixture, home: str) -> None:
    """The rendered permission rules beside the guard: their verdict on AGY_PERMS, and the guard's
    refusal or ask on the commands that a rule of AGY_GRANTS allows."""
    for command, expected in AGY_PERMS:
        got = fixture.permission(command)
        report(ok=got == expected, line=f"exp {expected} got {got}  [agy-perms]  {command}")
    for command, expected, grant in AGY_GRANTS:
        got = agy_reply(home, agy_payload("run_command", {"CommandLine": command}))
        granted = grant in fixture.rules["allow"] and bool(fixture.adapter.rule_matches(grant, command))
        report(
            ok=got.decision == expected and granted,
            line=f"exp {expected} got {got.decision}  [agy-grant]  {command}, which the allow rule {grant} "
            f"matches: {granted}",
        )


def agy_home_cases(report: AgyReport, fixture: AgyFixture) -> None:
    """The cases of a home whose path list or package differs from the rendered one."""
    rendered = json_object(fixture.rendered(AGY_HOME)) or {}

    def changed(**lists: object) -> str:
        """The rendered list with each key of `lists` replaced, or dropped for None."""
        found = {**rendered, **lists}
        return json.dumps({key: value for key, value in found.items() if value is not None})

    status = ("run_command", {"CommandLine": "git status"})
    for name, paths, (tool, args), expected, reason in (
        ("missing", None, status, "deny", "cannot be used"),
        ("missing-message", None, ("send_message", {"Message": "x"}), "deny", "cannot be used"),
        ("not-json", "{", status, "deny", "cannot be used"),
        ("deny-text", '{"deny": "x"}', status, "deny", "no list of strings"),
        ("deny-number", changed(deny=["x", 5]), status, "deny", "no list of strings"),
        ("bash-deny-text", changed(bash_deny="x"), status, "deny", "no list of strings"),
        ("bash-ask-missing", changed(bash_ask=None), status, "deny", "cannot be used"),
        (
            "edit-missing",
            changed(edit=None),
            ("write_file", {"Path": "notes.md", "Content": "x"}),
            "deny",
            "used",
        ),
        ("edit-missing-read", changed(edit=None), ("read_file", {"Path": "src/Foo.jl"}), "ask", ""),
        (
            "ask-text",
            changed(ask="x"),
            ("write_to_file", {"TargetFile": "notes.md"}),
            "deny",
            "no list of strings",
        ),
    ):
        got = agy_reply(fixture.home("agy-list-" + name, paths), agy_payload(tool, args))
        ok = got.decision == expected and reason in (got.reason or "")
        report(
            ok=ok, line=f"exp {expected} got {got.decision}  [agy-guard]  the path list {name}: {tool} {args}"
        )
    # Without the template's Bash rules, the shell checks alone decide a `sed -i`, which writes a file
    # of a work tree only when the call's working directory, its `Cwd` or else its workspace, is one.
    bare = fixture.home("agy-home-no-bash", changed(bash_deny=[], bash_ask=[]))
    for args, workspace, expected in (
        ({"CommandLine": "sed -i s/a/b/ f"}, AGY_ELSEWHERE, "ask"),
        ({"CommandLine": "sed -i s/a/b/ f", "Cwd": CWD}, AGY_ELSEWHERE, "deny"),
        ({"CommandLine": "sed -i s/a/b/ f", "Cwd": AGY_ELSEWHERE}, CWD, "ask"),
        ({"CommandLine": "sed -i s/a/b/ f", "Cwd": "."}, CWD, "deny"),
    ):
        got = agy_reply(bare, agy_payload("run_command", args, workspace))
        report(
            ok=got.decision == expected,
            line=f"exp {expected} got {got.decision}  [agy-guard]  {args} with workspacePaths [{workspace}]",
        )
    # `~<user>` is the home of that user, as the shell expands it.
    user = getpass.getuser()
    own = fixture.home("agy-home-own", fixture.rendered(pwd.getpwnam(user).pw_dir))
    got = agy_reply(own, agy_payload("run_command", {"CommandLine": f"cat ~{user}/.netrc"}))
    report(ok=got.decision == "deny", line=f"exp deny got {got.decision}  [agy-guard]  cat ~{user}/.netrc")
    # The lift reads the package's own rule: a copy of it that also lifts julia lifts `julia --version`.
    julia = fixture.home("agy-home-julia", excluded=AGY_EXCLUDED.replace('"ps"', '"ps", "julia"'))
    got = agy_reply(julia, agy_payload("run_command", {"CommandLine": "julia --version"}))
    report(
        ok=bypass_of(got.overwrite) is True,
        line=f"exp True got {bypass_of(got.overwrite)}  [agy-bypass]  julia --version, with a rule that "
        f"lifts julia",
    )


def agy_payload_cases(report: AgyReport, home: str) -> None:
    """A payload that the table cannot read is refused with a reason; a call with no workspace path
    has no working directory, so a relative path of it is refused and a call with none is decided
    by its checks; a check's refusal carries the check's own reason."""
    for label, payload in (
        ("the payload is not JSON", "not json"),
        ("the payload has no toolCall", '{"workspacePaths": []}'),
        ("the tool call has no name", '{"toolCall": {"args": {}}}'),
        ("the tool name is not a string", '{"toolCall": {"name": 5, "args": {}}}'),
        ("the args are a list", agy_payload("read_file", [])),
        ("a run_command has no CommandLine", agy_payload("run_command", {})),
    ):
        got = agy_reply(home, payload)
        ok = got.decision == "deny" and bool(got.reason and "cannot read" in got.reason)
        report(ok=ok, line=f"exp deny got {got.decision}  [agy-guard]  fail-closed, {label}: {got.reason!r}")
    for label, tool, args, workspace, expected in (
        ("git status", "run_command", {"CommandLine": "git status"}, None, "deny"),
        ("send_message", "send_message", {"Message": "x"}, None, "ask"),
        ("read_file of an absolute path", "read_file", {"Path": "/etc/hosts"}, None, "ask"),
        ("read_file of a relative path", "read_file", {"Path": "notes.md"}, None, "deny"),
        (
            "git status, a relative workspace path",
            "run_command",
            {"CommandLine": "git status"},
            "sub",
            "deny",
        ),
    ):
        got = agy_reply(home, agy_payload(tool, args, workspace))
        reasoned = got.reason is None if expected == "ask" else "working directory" in (got.reason or "")
        report(
            ok=got.decision == expected and reasoned and got.overwrite == "none",
            line=f"exp {expected} got {got.decision}, overwrite {got.overwrite}  [agy-guard]  {label}, "
            f"workspacePaths {[] if workspace is None else [workspace]}",
        )
    got = agy_reply(home, agy_payload("run_command", {"CommandLine": "git add -A"}))
    ok = got.decision == "deny" and bool(got.reason) and "fails closed" not in (got.reason or "")
    report(
        ok=ok,
        line=f"exp deny got {got.decision}  [agy-guard]  git add -A with its check's reason: {got.reason!r}",
    )


def agy_timed_cases(report: AgyReport, home: str, limit: float) -> None:
    """Commands of many words and of 1 MiB, each decided within `limit`, the timeout of `hooks.json`;
    a command of more than 1 MiB is refused."""
    for line, expected in (
        ("echo " + "git push " * 10000, "ask"),
        ("echo " + "a " * 20000, "ask"),
        ("echo " + "a" * (MIB - 5), "ask"),
        ("echo " + "a" * (MIB - 4), "deny"),
    ):
        got = agy_reply(home, agy_payload("run_command", {"CommandLine": line}), limit=limit)
        size = len(line.encode("utf-8"))
        ok = got.decision == expected and (expected == "ask" or "more than" in (got.reason or ""))
        report(
            ok=ok,
            line=f"exp {expected} got {got.decision}  [agy-guard]  {line[:20]!r}…, {size} bytes, "
            f"{len(line.split())} words: {got.seconds:.2f} seconds, within {limit:g} s",
        )


def agy_counted(home: str, payload: str, limit: float) -> tuple[str, int, int, int, float]:
    """The guard's decision on `payload` in the home `home`, under COUNTED, and its counts of `os.stat`
    and `os.lstat` calls, of `git` spawns and of other spawns, -1 for a count it did not print; and
    the seconds it took."""
    config = pathlib.Path(home, ".gemini", "config")
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", COUNTED, str(config / "hooks" / "guard"), "antigravity"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=limit,
            cwd=config,
            env={**CLEAN, "HOME": "/" + home},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", -1, -1, -1, time.monotonic() - start
    seconds = time.monotonic() - start
    counts = re.search(r"\ncounts (\d+) (\d+) \d+ (\d+)\n$", proc.stderr)
    stats, git, other = (int(counts[1]), int(counts[2]), int(counts[3])) if counts else (-1, -1, -1)
    answer = json_object(proc.stdout) or {}
    return str(answer.get("decision", f"exit {proc.returncode}")), stats, git, other, seconds


def agy_work_cases(report: AgyReport, home: str, limit: float) -> None:
    """The work of an Antigravity payload of 1 MiB, in a workspace that is no work tree: no spawn but
    `git`, at most AGY_MAX_GIT of them, at most two reads per unit of the command and WALK_READS more,
    within `limit`."""
    for unit in ("cat ~/x{}; ", "echo x > {}.log; ", "cd d{}/..; "):
        command, shape = mib_command(unit, "true")
        units = command.count("; ")
        payload = agy_payload("run_command", {"CommandLine": command}, AGY_ELSEWHERE)
        got, stats, git, other, seconds = agy_counted(home, payload, limit)
        ok = got == "ask" and 0 <= stats <= 2 * units + WALK_READS and 0 <= git <= AGY_MAX_GIT and other == 0
        report(
            ok=ok and seconds <= limit,
            line=f"exp ask, at most 2 x {units} + {WALK_READS} reads, {AGY_MAX_GIT} git, no other spawn got "
            f"{got}, {stats} reads, {git} git, {other} other  [agy-work ]  {shape}: {seconds:.2f} seconds",
        )


# Runs the guard package `sys.argv[1]` with `--from antigravity`, each call of a matcher that
# `path_list.bash_matcher` makes counted, and writes `matcher calls <n>` as the last line of stderr.
MATCHERS_COUNTED = """
import pathlib, runpy, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))
from guard import path_list
calls = [0]
make = path_list.bash_matcher
def counted(body):
    matcher = make(body)
    def wrapped(words, text):
        calls[0] += 1
        return matcher(words, text)
    return wrapped
path_list.bash_matcher = counted
sys.argv = [sys.argv[1], "--from", "antigravity"]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as e:
    code = e.code
sys.stderr.write(f"\\nmatcher calls {calls[0]}\\n")
sys.exit(code)
"""


def agy_rules_cases(report: AgyReport, home: str) -> None:
    """A command of 1 MiB whose first segments each hold every needed text of one Bash rule of the
    rendered list and that no rule matches, then distinct segments: the guard asks, and each rule
    meets only the word lists that hold all its needed texts, so the matcher calls are at most those
    (rule, word list) pairs. The count of the matcher calls decides the case, not its seconds."""
    sys.path.insert(0, HOOKS)
    try:
        path_list: Any = importlib.import_module("guard.path_list")
    finally:
        sys.path.remove(HOOKS)
    config = pathlib.Path(home, ".gemini", "config")
    lists = cast(
        "dict[str, list[str]]",
        json_value((config / "guard-paths.json").read_text(encoding="utf-8"), "guard-paths.json"),
    )
    needs = [path_list.needed(body) for body in (*lists["bash_deny"], *lists["bash_ask"])]
    words = (" ".join(w for need in needed for w in need.split(path_list.WORD_BREAK)) for needed in needs)
    lead = "".join(f"echo q{text}q; " for text in words)
    command, shape = mib_command("t{}; ", "true", lead)
    shape = f"one 'echo q<needed texts>q; ' per rule + {shape[len(repr(lead)) + 3 :]}"
    texts = [
        path_list.WORD_BREAK.join(listed)
        for segment in dict.fromkeys(path_list.segments(command))
        for listed in path_list.segment_words(segment)
    ]
    indexed = sum(all(need in text for need in needed) for needed in needs if needed for text in texts)
    payload = agy_payload("run_command", {"CommandLine": command}, AGY_ELSEWHERE)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", MATCHERS_COUNTED, str(config / "hooks" / "guard")],
            input=payload,
            capture_output=True,
            text=True,
            timeout=MIB_HANG,
            cwd=config,
            env={**CLEAN, "HOME": "/" + home},
            check=False,
        )
        found = re.search(r"\nmatcher calls (\d+)\n$", proc.stderr)
        calls, got = (int(found[1]) if found else -1), str((json_object(proc.stdout) or {}).get("decision"))
    except subprocess.TimeoutExpired:
        calls, got = -1, "timeout"
    seconds = time.monotonic() - start
    report(
        ok=got == "ask" and 0 <= calls <= indexed,
        line=f"exp ask, at most {indexed} matcher calls got {got}  [mib-rules]  {len(needs)} rules, {shape}: "
        f"matcher calls {calls}, {seconds:.2f} seconds",
    )


def agy_handler_cases(report: AgyReport, fixture: AgyFixture, home: str) -> None:
    """The handler of hooks.json, rendered for a home whose name holds a space, runs the guard on the
    interpreter that it names, from any working directory and with no python3 on the PATH; with no
    interpreter there, it fails and prints nothing, which Antigravity reads as a block."""
    spaced = fixture.home("agy home")
    interpreter = pathlib.Path(spaced, "python env", "bin", "python")
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.symlink_to(sys.executable)
    status = agy_payload("run_command", {"CommandLine": "git status"})
    for python, payload, env in (
        (str(interpreter), status, {**CLEAN, "HOME": spaced, "PATH": "/nonexistent"}),
        (spaced + "/no environment/bin/python", "{}", {**CLEAN, "HOME": spaced}),
    ):
        hooks = json_object(str(fixture.adapter.render_hooks(pathlib.Path(spaced, ".gemini"), python))) or {}
        handler = str(cast("Any", hooks)[fixture.adapter.HOOK]["PreToolUse"][0]["hooks"][0]["command"])
        proc = subprocess.run(
            ["/bin/sh", "-c", handler],
            input=payload,
            capture_output=True,
            text=True,
            cwd=AGY_ELSEWHERE,
            env=env,
            timeout=TIMEOUT,
            check=False,
        )
        if payload == status:
            got, ok = (
                proc.stdout.strip(),
                proc.stdout.strip() == '{"decision": "ask", "overwrite": {"BypassSandbox": true}}',
            )
        else:
            got, ok = (
                f"exit {proc.returncode}, output {proc.stdout!r}",
                proc.returncode != 0 and proc.stdout == "",
            )
        report(
            ok=ok, line=f"exp the guard's answer got {got}  [agy-guard]  the handler {handler}, from {home}"
        )


def agy_unit_cases(report: AgyReport, home: str) -> None:
    """The table's rendering of a neutral `allow`, and a check that raises under `--from antigravity`."""
    sys.path.insert(0, HOOKS)
    try:
        table: Any = importlib.import_module("guard.frontends.antigravity")
        contract: Any = importlib.import_module("guard.contract")
        semantics: Any = importlib.import_module("guard.sandbox_semantics")
    finally:
        sys.path.remove(HOOKS)
    # The work-tree check refuses a `git init` that only a working directory places; through the
    # table, the path list refuses such a call first, for its relative words.
    landed: Any = semantics.work_tree_check(
        contract.Call("shell", "/usr/bin/git init /tmp/x", (), None, "main")
    )
    report(
        ok=landed.decision == "deny" and "working directory" in landed.reason,
        line=f"exp deny got {landed.decision}  [agy-guard]  the work-tree check on git init with no working "
        f"directory",
    )
    for shell, want in (
        (False, {"decision": "ask"}),
        (True, {"decision": "ask", "overwrite": {"BypassSandbox": False}}),
    ):
        got: object = table.render(contract.Verdict("allow"), shell=shell)
        report(
            ok=got == want,
            line=f"exp {want} got {got}  [agy-guard]  the answer to a neutral allow, shell {shell}",
        )
    config = pathlib.Path(home, ".gemini", "config")
    proc = subprocess.run(
        [sys.executable, "-c", AGY_RAISES, str(config / "hooks"), str(config / "hooks" / "guard")],
        input=agy_payload("run_command", {"CommandLine": "git status"}),
        capture_output=True,
        text=True,
        cwd=config,
        env={**CLEAN, "HOME": "/" + home},
        timeout=TIMEOUT,
        check=False,
    )
    answer = json_object(proc.stdout)
    blocked = (proc.returncode != 0 and proc.stdout.strip() == "") or (
        answer is not None and answer.get("decision") == "deny" and bool(answer.get("reason"))
    )
    report(
        ok=blocked,
        line=f"exp a block got exit {proc.returncode}, output {proc.stdout[:80]!r}  [agy-guard]  under "
        f"--from antigravity, a check that raises: {proc.stderr.strip()[-100:]!r}",
    )


def agy_cases() -> tuple[int, int]:
    """The cases of Antigravity's guard: (number of cases, number wrong)."""
    report = AgyReport()
    sys.path.insert(0, REPO + "/lib")
    try:
        harness_error: type[Exception] = importlib.import_module("harness").HarnessError
    except ImportError as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [agy-guard]  {e}")
        return report.total, report.wrong
    try:
        fixture = AgyFixture()
        pathlib.Path(AGY_ELSEWHERE, "sub").mkdir(parents=True)
        home = fixture.home("agy-home")
        opened = fixture.home("agy-open")
        launcher_home(opened)
    # The adapters, the profile and the rendering fail with HarnessError, an input of an unexpected
    # shape with the others; the case reports it as wrong, and the probe goes on to its summary.
    except (harness_error, ImportError, OSError, ValueError, LookupError, TypeError, AttributeError) as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [agy-guard]  {e}")
        return report.total, report.wrong
    agy_record_cases(report, home)
    # Antigravity's table runs no launcher check: in a home whose `.ssh` the guard can list, the first
    # record that the guard lets through gives its recorded decision.
    record = next(r for r in agy_records(opened) if r["decision"] == "ask")
    got = agy_reply(
        opened,
        agy_payload(record["tool"], record["args"], str(record.get("workspace", CWD))),
        extra=profile_env(cast("dict[str, Any]", record)),
    )
    want = (record["decision"], record["bypass"])
    report(
        ok=(got.decision, bypass_of(got.overwrite)) == want,
        line=f"exp {want} got {(got.decision, bypass_of(got.overwrite))}  [agy-guard]  a readable .ssh: "
        f"{record['tool']} {json.dumps(record['args'])[:120]}",
    )
    agy_policy_cases(report, fixture, home)
    agy_home_cases(report, fixture)
    agy_payload_cases(report, home)
    agy_timed_cases(report, home, fixture.timeout)
    agy_work_cases(report, home, fixture.timeout)
    agy_rules_cases(report, home)
    agy_handler_cases(report, fixture, home)
    agy_unit_cases(report, home)
    return report.total, report.wrong


def call(script, payload, env=None, args: tuple[str, ...] = ()):
    """Run a Python hook with this interpreter on the fixture; None after the timeout."""
    try:
        return subprocess.run(
            [sys.executable, script, *args],  # pyright: ignore[reportUnknownArgumentType]
            input=payload,
            capture_output=True,
            text=True,
            env=env or ENV,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def decision(script, payload, args: tuple[str, ...] = ()):
    """Return 'deny', 'ask' or 'pass' for a hook that may answer with a JSON decision."""
    proc = call(script, payload, args=args)
    if proc is None:
        return "timeout"
    if proc.returncode == 2:
        return "deny"
    if proc.returncode != 0:
        return f"exit {proc.returncode}"
    if not proc.stdout.strip():
        return "pass"
    try:
        return json_value(proc.stdout, "the output")["hookSpecificOutput"]["permissionDecision"]
    except ValueError, KeyError, TypeError:
        return "unreadable output"


def fixture():
    """Make the tree the cases assume below the fixture `HOME`.

    `Packages/Example`, `~/.claude` and `Harness`, the cases' working directory, are
    repositories with tracked files; git reads no user or system configuration, and the identity
    is the environment's, so a CI runner with none and a user's global configuration give one
    result.
    """
    home = FIXTURE.name + "/home"
    git_env = {
        **CLEAN,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "probe",
        "GIT_AUTHOR_EMAIL": "probe@example.org",
        "GIT_COMMITTER_NAME": "probe",
        "GIT_COMMITTER_EMAIL": "probe@example.org",
    }
    repositories = {
        home + "/Research/Packages/Example": ["Project.toml", "CHANGELOG.md", "src/Example.jl"],
        home + "/.claude": ["CLAUDE.md"],
        home + "/Research/Harness": [".gitignore", "hooks/probe.py"],
    }
    content = {".gitignore": "__pycache__/\n"}
    for directory in (home + "/Research/.scratch", home + "/Research/.worktrees"):
        os.makedirs(directory)
    closed_ssh(home)
    open(home + "/Research/CLAUDE.md", "w").close()
    for repository, files in repositories.items():
        for name in files:
            os.makedirs(os.path.dirname(os.path.join(repository, name)), exist_ok=True)
            with open(os.path.join(repository, name), "w") as f:
                f.write(content.get(name, ""))
        for command in (
            ["init", "-q", "-b", "main"],
            ["add", "--", *files],
            ["commit", "-q", "-m", "fixture"],
        ):
            subprocess.run(
                ["git", "-C", repository, *command],  # noqa: S607 -- git runs from PATH
                env=git_env,
                check=True,
                capture_output=True,
                timeout=60,
            )
    pathlib.Path(DEEP).mkdir(parents=True)
    pathlib.Path(OUTSIDE).mkdir(parents=True)
    pathlib.Path(DANGLING).mkdir()
    pathlib.Path(DANGLING, ".git").symlink_to("missing")
    pathlib.Path(LOGS, "a").mkdir()
    pathlib.Path(LOGS, "loop").symlink_to("loop")
    pathlib.Path(LOGS, ".gitignore").write_text("*.log\n", encoding="utf-8")
    git = shutil.which("git") or "git"
    subprocess.run([git, "init", "-q", LOGS], env=git_env, check=True, capture_output=True, timeout=60)
    os.symlink("/", LINK)
    # A link in a scratch zone to a guarded directory: a recursive `rm` of the link removes the link,
    # and of the link with a trailing `/` the directory.
    pathlib.Path(SCRATCH, "link-out").symlink_to("/")
    own_profile(home)
    profiles = pathlib.Path(FIXTURE.name, "profiles")
    profiles.mkdir()
    for name, data in PROFILES.items():
        (profiles / name).write_bytes(data)
    queries = pathlib.Path(FIXTURE.name, "gh")
    queries.mkdir()
    for name, data in GH_QUERIES.items():
        (queries / name).write_bytes(data)
    git_write_repositories(git, git_env)


def git_write_repositories(git: str, git_env: dict[str, str]) -> None:
    """The repositories of the git write check, below the fixture's `Research`.

    `Packages/Own` has `origin` on GitHub in the own organisation of OWN_PROFILE, the remote refs
    `origin/main` and `origin/trunk`, `origin/HEAD` naming `trunk`, a local branch `feature`, and
    the aliases `p` (`push`), `pp` (`p`), `lg` (`log --oneline`), `sh` (`!git push`) and `x`
    (`-p p`).
    Its worktrees below `.worktrees/`: `Own-pushed`, whose HEAD commit `origin/pushed` holds, with
    an untracked file; `Own-unpushed`, with a commit on no remote ref; `Own-modified`, with a
    modified tracked file; and `Own-staged`, with a staged new file. `Packages/Foreign` has
    `origin` in another organisation and a local branch `feature`. `Packages/Mapped` has `origin` in
    the own organisation, a local branch `feature`, and a `remote.origin.push` refspec that maps
    `feature` onto `main`. No remote is ever reached: the remote refs are written with `update-ref`.
    """
    own, foreign, mapped = R + "/Packages/Own", R + "/Packages/Foreign", R + "/Packages/Mapped"
    worktrees = {name: R + "/.worktrees/Own-" + name for name in ("pushed", "unpushed", "modified", "staged")}

    def run(directory: str, *arguments: str) -> None:
        subprocess.run(
            [git, "-C", directory, *arguments], env=git_env, check=True, capture_output=True, timeout=60
        )

    for repository, owner in ((own, "own-org"), (foreign, "other-org"), (mapped, "own-org")):
        pathlib.Path(repository).mkdir(parents=True)
        pathlib.Path(repository, "README.md").write_text("a\n", encoding="utf-8")
        run(repository, "init", "-q", "-b", "main")
        run(repository, "add", "--", "README.md")
        run(repository, "commit", "-q", "-m", "fixture")
        run(
            repository,
            "remote",
            "add",
            "origin",
            f"https://github.com/{owner}/{pathlib.Path(repository).name}.jl.git",
        )
        run(repository, "update-ref", "refs/remotes/origin/main", "HEAD")
        run(repository, "branch", "feature")
    run(mapped, "config", "remote.origin.push", "refs/heads/feature:refs/heads/main")
    for alias, value in (
        ("p", "push"),
        ("pp", "p"),
        ("lg", "log --oneline"),
        ("sh", "!git push"),
        ("x", "-p p"),
    ):
        run(own, "config", f"alias.{alias}", value)
    run(own, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    run(own, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    for name, path in worktrees.items():
        run(own, "worktree", "add", "-q", "-b", name, path)
    for name in ("pushed", "unpushed"):
        run(worktrees[name], "commit", "-q", "--allow-empty", "-m", name)
    run(worktrees["pushed"], "update-ref", "refs/remotes/origin/pushed", "HEAD")
    pathlib.Path(worktrees["pushed"], "scratch.txt").write_text("untracked\n", encoding="utf-8")
    pathlib.Path(worktrees["modified"], "README.md").write_text("b\n", encoding="utf-8")
    pathlib.Path(worktrees["staged"], "new.md").write_text("new\n", encoding="utf-8")
    run(worktrees["staged"], "add", "--", "new.md")


def drift(env, payload="{}"):
    """('quiet', '') or ('warn', message) for `install-drift.py`; any other result is its exit."""
    proc = call(DRIFT, payload, env)
    if proc is None:
        return "timeout", ""
    if proc.returncode != 0:
        return f"exit {proc.returncode}", proc.stderr[-200:]
    if not proc.stdout.strip():
        return "quiet", ""
    try:
        out = json_value(proc.stdout, "the output")
        message = out["systemMessage"]
        context = out["hookSpecificOutput"]["additionalContext"]
    except ValueError, KeyError, TypeError:
        return "unreadable output", proc.stdout[-200:]
    return (
        ("warn", message)
        if message == context and out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        else ("unreadable output", proc.stdout[-200:])
    )


def agy_drift(env, payload="{}"):
    """('quiet', '') or ('warn', message) for the `SessionStart` handler of the `hooks.json` that
    `harness install` wrote below the `HOME` of `env`, run as Antigravity runs it, by `sh -c` in the
    directory of `hooks.json`: `{}` is quiet, and one `injectSteps` system message is a warning; any
    other answer is its exit and its output."""
    config = env["HOME"] + "/.gemini/config"
    with open(config + "/hooks.json") as f:
        handlers = [
            h for hook in json_value(f.read(), "hooks.json").values() for h in hook.get("SessionStart", [])
        ]
    if len(handlers) != 1:
        return f"{len(handlers)} SessionStart handlers", ""
    try:
        p = subprocess.run(
            ["/bin/sh", "-c", handlers[0]["command"]],
            input=payload,
            capture_output=True,
            text=True,
            cwd=config,
            env=env,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    try:
        out = json_value(p.stdout, "the output")
    except ValueError:
        return f"exit {p.returncode}, unreadable output", (p.stdout + p.stderr)[-200:]
    if p.returncode == 0 and out == {}:
        return "quiet", ""
    try:
        [step] = out["injectSteps"]
        message = step["systemMessage"]["systemMessage"]
    except KeyError, TypeError, ValueError:
        return f"exit {p.returncode}, unreadable output", p.stdout[-200:]
    return (
        ("warn", message)
        if p.returncode == 0 and list(out) == ["injectSteps"] and isinstance(message, str)
        else (f"exit {p.returncode}, unreadable output", p.stdout[-200:])
    )


class SetupFailed(Exception):
    """A `harness install --apply` of the drift cases that exits with another status than 0."""


def install(base, env):
    """`harness install --apply` on the drift fixture below `base`: (exit status, output)."""
    p = subprocess.run(
        [
            sys.executable,
            REPO + "/bin/harness",
            "--profile",
            base + "/profile.toml",
            "--models",
            REPO + "/examples/models.toml",
            "install",
            "--apply",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def drift_cases(install=install):
    """The cases of `install-drift.py`: (number of cases, number wrong).

    `install` runs `harness install --apply` into a fixture `HOME`, from this repository and from
    tree instructions in the fixture. Each case changes the fixture and expects the hook to be
    quiet, or to warn with a text that names what it found. Antigravity's `SessionStart` handler,
    which the install writes into the fixture's `~/.gemini/config/hooks.json`, gets the same verdict
    and the same text in each case. The cases read the files that the install writes, so a failed
    install is one wrong case with its exit status and last line, and the cases after it do not run."""
    base = os.path.join(FIXTURE.name, "drift")
    home, tree = base + "/home", base + "/Agents"
    claude = home + "/.claude"
    os.makedirs(claude + "/skills")
    os.makedirs(home + "/.gemini")
    os.makedirs(base + "/opencode")
    os.makedirs(base + "/julia")
    with open(REPO + "/Project.toml", "rb") as f, open(base + "/julia/Project.toml", "wb") as g:
        g.write(f.read())
    open(base + "/julia/Manifest.toml", "w").close()
    # A synced Python environment, so that the install starts no uv.
    sys.path.insert(0, REPO + "/lib")
    from harness import install_cases

    install_cases.python_env(pathlib.Path(base, "python"))
    for name in ("instructions/research-tree.md", "rules/meta-repository.md", "README.md"):
        os.makedirs(os.path.dirname(os.path.join(tree, name)), exist_ok=True)
        with open(os.path.join(tree, name), "w") as f:
            # A rule needs a `description`, or the install exits 2 on oh-my-pi's rendering of it.
            f.write(f"---\ndescription: d\n---\n{name}\n" if name.startswith("rules/") else f"{name}\n")
    # The stamp names the sources below the profile's `harness`, so the profile names this checkout.
    with open(REPO + "/examples/profile.toml") as f:
        lines = [
            f'tree_agents = "{tree}"'
            if l.startswith("tree_agents = ")
            else f'harness = "{REPO}"'
            if l.startswith("harness = ")
            else l
            for l in f.read().splitlines()
        ]
    with open(base + "/profile.toml", "w") as f:
        f.write("\n".join(lines) + "\n")
    env = {
        **CLEAN,
        "HOME": home,
        "OPENCODE_CONFIG_DIR": base + "/opencode",
        "RESEARCH_HARNESS_JULIA": base + "/julia",
        "RESEARCH_HARNESS_PYTHON": base + "/python",
        "PI_CODING_AGENT_DIR": base + "/omp",
    }

    def apply():
        """`harness install --apply` on the fixture; an exit other than 0 raises SetupFailed."""
        code, text = install(base, env)
        if code != 0:
            raise SetupFailed(
                f"harness install --apply exits {code}: {(text.strip().splitlines() or ['no output'])[-1]}"
            )

    def edit(path, text="an edit that is not installed\n"):
        with open(path, "a") as f:
            f.write(text)

    def read_stamp():
        with open(claude + "/" + STAMP) as f:
            return json_value(f.read(), STAMP)

    def write_stamp(data):
        with open(claude + "/" + STAMP, "w") as f:
            f.write(data)

    def copy_sources():
        """The stamp with its rules/ and hooks/ sources pointed at copies of this repository's."""
        copies = {REPO + "/rules": base + "/rules", REPO + "/hooks": base + "/hooks"}
        for source, copy in copies.items():
            shutil.copytree(source, copy)
        stamp = read_stamp()
        stamp["sources"] = [[copies.get(s[0], s[0]), *s[1:]] for s in stamp["sources"]]
        write_stamp(json.dumps(stamp))

    def toggle_x(path):
        """`path` with its owner's execute bit flipped."""
        os.chmod(path, os.stat(path).st_mode ^ 0o100)

    rules = tree + "/rules"

    # (label, the change before the hook runs, the expected result, a text the warning holds)
    steps = [
        ("the installation that --apply made is current", lambda: apply(), "quiet", ""),
        ("a payload that is not JSON changes nothing", None, "quiet", ""),
        (
            "an edit in the tree instructions is drift",
            lambda: edit(tree + "/rules/meta-repository.md"),
            "warn",
            "behind",
        ),
        ("after a second --apply, the installation is current", lambda: apply(), "quiet", ""),
        (
            "a rename in a source, with the same bytes and the same order, is drift",
            lambda: os.rename(rules + "/meta-repository.md", rules + "/meta-repository0.md"),
            "warn",
            "behind",
        ),
        (
            "the name restored, the installation is current",
            lambda: os.rename(rules + "/meta-repository0.md", rules + "/meta-repository.md"),
            "quiet",
            "",
        ),
        (
            "a hidden file in a source, such as .DS_Store, is no drift",
            lambda: edit(rules + "/.DS_Store"),
            "quiet",
            "",
        ),
        (
            "a FIFO in a source is a warning that names it",
            lambda: os.mkfifo(rules + "/fifo"),
            "warn",
            rules + "/fifo",
        ),
        (
            "a symlinked directory in a source is a warning that names it",
            lambda: (os.remove(rules + "/fifo"), os.symlink(rules, tree + "/linked")),
            "warn",
            tree + "/linked",
        ),
        (
            "the stamp names copies of rules/ and hooks/, which equal them",
            lambda: (os.remove(tree + "/linked"), copy_sources()),
            "quiet",
            "",
        ),
        (
            "a mode change of a hooks/ source is drift",
            lambda: toggle_x(base + "/hooks/install-drift.py"),
            "warn",
            "behind",
        ),
        (
            "an edit in rules/ is drift",
            lambda: (toggle_x(base + "/hooks/install-drift.py"), edit(base + "/rules/julia-code.md")),
            "warn",
            "behind",
        ),
        ("a missing stamp is drift", lambda: os.remove(claude + "/" + STAMP), "warn", claude + "/" + STAMP),
        (
            "a stamp that is not JSON is a warning that names it",
            lambda: write_stamp("{ not json"),
            "warn",
            claude + "/" + STAMP,
        ),
        (
            "a source tree that cannot be read is a warning that names it",
            lambda: (apply(), os.chmod(tree + "/rules", 0)),
            "warn",
            tree + "/rules",
        ),
        (
            "a source tree that does not exist is a warning that names it",
            lambda: (os.chmod(tree + "/rules", 0o755), os.rename(tree, tree + "-moved")),
            "warn",
            tree,
        ),
    ]
    total = wrong = 0
    for label, change, expected, text in steps:
        payload = "not json at all" if label.startswith("a payload") else "{}"
        try:
            if change is not None:
                change()
            got, message = drift(env, payload)
        except SetupFailed as e:  # the cases after it would read files that the install did not write
            total, wrong = total + 1, wrong + 1
            print(f"BAD exp {expected} got {e}  [inst-drif]  {label}; the cases after it do not run")
            return total, wrong
        # A change or a hook run that fails on a file, a stamp of an unexpected shape, or a timeout
        # of the install: a case that crashes is wrong, and the next case still runs.
        except (OSError, ValueError, LookupError, TypeError, subprocess.SubprocessError) as e:
            got, message = f"raised {type(e).__name__}", str(e)
        ok = got == expected and text in message
        total += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'} exp {expected} got {got}  [inst-drif]  {label}: {message[:160]!r}")
        try:
            agy, agy_message = agy_drift(env, payload)
        # A hooks.json that cannot be read or is of an unexpected shape: a case that crashes is
        # wrong, and the next case still runs.
        except (OSError, ValueError, LookupError, TypeError, AttributeError) as e:
            agy, agy_message = f"raised {type(e).__name__}", str(e)
        ok = agy == expected and agy_message == message
        total += 1
        wrong += not ok
        print(
            f"{'ok ' if ok else 'BAD'} exp {expected} got {agy}  [agy-drift]  {label}, the same text as "
            f"install-drift.py's: {agy_message[:160]!r}"
        )
    # Antigravity's handler warns, and never answers `{}`, when its copy of install-drift.py gives no
    # answer: the warning names the copy and what went wrong.
    copy = home + "/.gemini/config/hooks/install-drift.py"
    failures = [
        ("install-drift.py exits 1", "import sys; sys.stderr.write('boom'); sys.exit(1)\n", "exit 1: boom"),
        ("install-drift.py prints text that is not JSON", "print('not json')\n", "JSONDecodeError"),
        ("install-drift.py prints JSON that is no object", "print('[1]')\n", "TypeError"),
        ("install-drift.py prints an object with no systemMessage", "print('{}')\n", "KeyError"),
        (
            "install-drift.py prints a systemMessage that is no text",
            "print('{\"systemMessage\": 1}')\n",
            "TypeError",
        ),
        ("install-drift.py is missing", None, "exit 2: "),
    ]
    for label, source, text in failures:
        try:
            if source is None:
                os.remove(copy)
            else:
                with open(copy, "w") as f:
                    f.write(source)
            agy, agy_message = agy_drift(env)
        # A copy that cannot be written, or a hooks.json that cannot be read or is of an unexpected
        # shape: a case that crashes is wrong, and the next case still runs.
        except (OSError, ValueError, LookupError, TypeError, AttributeError) as e:
            agy, agy_message = f"raised {type(e).__name__}", str(e)
        ok = agy == "warn" and copy in agy_message and text in agy_message
        total += 1
        wrong += not ok
        print(
            f"{'ok ' if ok else 'BAD'} exp warn got {agy}  [agy-drift]  {label}: a warning that names the copy "
            f"and {text!r}: {agy_message[:200]!r}"
        )
    return total, wrong


def main(argv=None):
    """Run the groups that `argv` names, every group when it names none, on one fixture; print one
    line per case and the summary `<n> cases, <w> wrong`. An unknown group exits 2."""
    names = sys.argv[1:] if argv is None else argv
    unknown = [name for name in names if name not in GROUPS]
    if unknown:
        print(f"probe.py: no group {', '.join(unknown)}; the groups are {', '.join(GROUPS)}", file=sys.stderr)
        return 2
    try:
        fixture()
        return cases(names or list(GROUPS))
    finally:
        for ssh in CLOSED_SSH:
            ssh.chmod(0o700)
        FIXTURE.cleanup()


def cases(names):
    """Run the groups `names` in order and print the summary line: exit status 1 when a case is wrong."""
    wrong = 0
    total = 0
    for name in names:
        n, bad = GROUPS[name]()
        total, wrong = total + n, wrong + bad
    print(f"\n{total} cases, {wrong} wrong")
    return 1 if wrong else 0


def guard_run(
    data: bytes, frontend: str = "claude", limit: float = TIMEOUT, env: dict[str, str] | None = None
) -> tuple[str, str]:
    """The guard's decision on the payload bytes `data`, run as the settings template runs it but from
    the fixture's directory, with the environment `env`, ENV by default, and its stdout and stderr:
    `deny` for exit 2, the `permissionDecision` of stdout for exit 0, `pass` for exit 0 with no
    output, `exit <n>` or `timeout` after `limit` seconds."""
    try:
        proc = subprocess.run(
            [sys.executable, GUARD, "--from", frontend],
            input=data,
            capture_output=True,
            env=ENV if env is None else env,
            cwd=FIXTURE.name,
            timeout=limit,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    stdout = proc.stdout.decode("utf-8", "replace")
    output = stdout + proc.stderr.decode("utf-8", "replace")
    if proc.returncode == 2:
        return "deny", output
    if proc.returncode != 0:
        return f"exit {proc.returncode}", output
    if not stdout.strip():
        return "pass", output
    try:
        return str(json_value(stdout, "the output")["hookSpecificOutput"]["permissionDecision"]), output
    except ValueError, KeyError, TypeError:
        return "unreadable output", output


# Runs the guard `sys.argv[1]` with `--from <sys.argv[2]>`, as the frontend runs it, with each
# `os.stat` and `os.lstat` call, each spawn of `git`, each step of a walk (a call of `Place.child`
# of the package's `paths`, imported first so that the guard runs the counted class) and each spawn
# of another program counted, and writes the counts as the last line of stderr after the guard exits:
# `counts <stat and lstat calls> <git spawns> <steps> <other spawns>`.
COUNTED = """
import os, pathlib, runpy, subprocess, sys
counts = [0, 0, 0, 0]
def counted(call, index):
    def wrapped(*args, **kwargs):
        counts[index] += 1
        return call(*args, **kwargs)
    return wrapped
os.stat, os.lstat = counted(os.stat, 0), counted(os.lstat, 0)
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))
from guard import paths
paths.Place.child = counted(paths.Place.child, 2)
class Popen(subprocess.Popen):
    def __init__(self, args, *rest, **kwargs):
        counts[1 if pathlib.PurePath(str(args[0])).name == "git" else 3] += 1
        super().__init__(args, *rest, **kwargs)
subprocess.Popen = Popen
sys.argv = [sys.argv[1], "--from", sys.argv[2]]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as e:
    code = e.code
sys.stderr.write(f"\\ncounts {counts[0]} {counts[1]} {counts[2]} {counts[3]}\\n")
sys.exit(code)
"""


def guard_counted(data: bytes) -> tuple[str, int, int, int]:
    """The guard's decision on the payload bytes `data`, `deny`, `pass`, the decision of its JSON
    output such as `ask`, `exit <n>` or `timeout`, and
    its count of `os.stat` and `os.lstat` calls, of `git` spawns and of the steps of its walks; -1 for
    a count it did not print."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", COUNTED, GUARD, "claude"],
            input=data,
            capture_output=True,
            env=ENV,
            cwd=FIXTURE.name,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", -1, -1, -1
    counts = re.search(rb"\ncounts (\d+) (\d+) (\d+) \d+\n$", proc.stderr)
    stats, spawns, steps = (
        (int(counts.group(1)), int(counts.group(2)), int(counts.group(3))) if counts else (-1, -1, -1)
    )
    if proc.returncode == 2:
        return "deny", stats, spawns, steps
    if proc.returncode != 0:
        return f"exit {proc.returncode} {proc.stdout[:80]!r}", stats, spawns, steps
    stdout = proc.stdout.decode("utf-8", "replace")
    if not stdout.strip():
        return "pass", stats, spawns, steps
    try:
        decision = str(json_value(stdout, "the output")["hookSpecificOutput"]["permissionDecision"])
    except ValueError, KeyError, TypeError:
        decision = f"exit 0 {proc.stdout[:80]!r}"
    return decision, stats, spawns, steps


def mib_command(unit: str, tail: str, lead: str = "") -> tuple[str, str]:
    """A command of exactly 1 MiB, `lead`, then `unit` as often as it fits, each `{}` in it filled with
    0, 1, 2, …, then spaces and `tail`; and its shape for a case's line."""
    units: list[str] = []
    size = len(lead) + len(tail)
    while size + len(filled := unit.format(len(units))) <= MIB:
        units.append(filled)
        size += len(filled)
    text = lead + "".join(units)
    shape = (
        f"{lead!r} + {len(units)} x {unit!r} + {tail!r}" if lead else f"{len(units)} x {unit!r} + {tail!r}"
    )
    return text + " " * (MIB - len(text) - len(tail)) + tail, shape


def corpus_records() -> list[tuple[str, str, dict[str, str]]]:
    """(payload text, expected decision, the variables of its `profile`) of each Claude Code record
    of the corpus, its placeholders replaced by the fixture's values; a record with a `frontend` is
    another frontend's."""
    records: list[tuple[str, str, dict[str, str]]] = []
    for placed in corpus_lines({}):
        record = json_value(placed, "a record of the corpus")
        if "frontend" in record:
            continue
        stdin = record["stdin"]
        records.append(
            (
                stdin if isinstance(stdin, str) else json.dumps(stdin),
                str(record["decision"]),
                profile_env(record),
            )
        )
    return records


class RaisingStdin(io.TextIOBase):
    """A stdin whose every read raises, also through its `buffer`."""

    def read(self, size: int | None = -1, /) -> str:
        raise RuntimeError(f"probe: a read of {size} raises")

    @property
    def buffer(self) -> RaisingStdin:
        return self


def guard_raises() -> tuple[object, str]:
    """The exit status and stderr of the guard run in this process with a stdin whose read raises."""
    saved = sys.argv, sys.stdin, list(sys.path)
    stderr = io.StringIO()
    sys.argv, sys.stdin = [GUARD, "--from", "claude"], cast("TextIO", RaisingStdin())
    try:
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(GUARD, run_name="__main__")
    except SystemExit as e:
        return e.code, stderr.getvalue()
    except RuntimeError as e:  # the raise escaped the guard: the case reports it as wrong
        return f"raised {e}", stderr.getvalue()
    finally:
        sys.argv, sys.stdin = saved[0], saved[1]
        sys.path[:] = saved[2]
    return "no exit", stderr.getvalue()


# The methods of a path and the names of `os` that read the file system.
FS_METHODS = frozenset(
    {
        "stat",
        "lstat",
        "exists",
        "resolve",
        "is_dir",
        "is_file",
        "is_symlink",
        "iterdir",
        "readlink",
        "samefile",
        "glob",
        "rglob",
        "open",
        "read_text",
        "read_bytes",
    }
)
OS_READS = frozenset(
    {"stat", "lstat", "listdir", "scandir", "access", "readlink", "walk", "getcwd", "path", "open"}
)
# The reads of the guard outside `paths.py` and `jsonio.py` that the bound per payload leaves out, by
# file and call: the package's own directory and the roots of the checks, each read once per process
# at import, the one path of a directory or worktree call, which holds no shell command, and the
# launcher check's listing of `~/.ssh` and its resolution of `CLAUDE_CONFIG_DIR` and of
# `~/.config/claudex`, each once per process. The launcher check reads Claude Code's settings through
# `jsonio.load`.
READS_ALLOWED = frozenset(
    {
        ("__main__.py", "Path(__file__).resolve()"),
        ("launcher.py", "Path(home, '.ssh').iterdir()"),
        ("launcher.py", "Path(value).resolve()"),
        ("launcher.py", "Path(home, '.config', 'claudex').resolve()"),
        ("directory_scope.py", "Path(Path.home(), 'Research').resolve()"),
        ("directory_scope.py", "Path(path).resolve()"),
        ("rm_scope.py", "Path.home().resolve()"),
        ("rm_scope.py", "Path(HOME, 'Research').resolve()"),
    }
)


def guard_reads() -> list[str]:
    """Each read of the file system in the guard package outside `paths.py`, which memoises every read
    of a payload, and `jsonio.py`, that `READS_ALLOWED` does not name: `<file>:<line> <call>`."""
    found: list[str] = []
    for path in sorted(pathlib.Path(GUARD).rglob("*.py")):
        name = path.relative_to(GUARD).as_posix()
        if name in ("paths.py", "jsonio.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FS_METHODS
            ):
                read: ast.expr = node
            elif (
                isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os"
            ):
                if node.attr not in OS_READS:
                    continue
                read = node
            else:
                continue
            text = ast.unparse(read)
            if (name, text) not in READS_ALLOWED:
                found.append(f"{name}:{read.lineno} {text}")
    return found


def guard_entry(missing: str) -> tuple[list[str], list[str], str]:
    """The commands of the `*` group and of the `Bash` group of the settings template as the Claude
    Code adapter renders them with the dummy profile, a home `missing` and this interpreter, and the
    guard's command, which the `*` group runs on every tool call."""
    sys.path.insert(0, REPO + "/lib")
    frontends = importlib.import_module("harness.frontends")
    profile = importlib.import_module("harness.profile")
    dummy = replace(profile.load(REPO + "/examples/profile.toml"), home=missing)
    cfg = frontends.adapter("claude").settings_template(
        dummy, FIXTURE.name + "/no-network.toml", sys.executable
    )
    every = next(g for g in cfg["hooks"]["PreToolUse"] if g.get("matcher") == "*")
    bash = next(g for g in cfg["hooks"]["PreToolUse"] if g.get("matcher") == "Bash")
    guard = shlex.join([sys.executable, missing + "/.claude/hooks/guard", "--from", "claude"]) + " || exit 2"
    return [str(h["command"]) for h in every["hooks"]], [str(h["command"]) for h in bash["hooks"]], guard


def quoted_reserved_cases(report: Callable[..., None]) -> None:
    """The reader of reserved words in this process, where its cache lives: the readings of
    `false && { true; }; cd x || exit; }` and of the same command with `"}"` are equal tokens, since
    a quoted word equals its text, and each gets its own commands (`shell.cached_commands`), in
    either order. The corpus cannot hold this case: each of its records runs in a process of its
    own."""
    sys.path.insert(0, HOOKS)
    try:
        shell: Any = importlib.import_module("guard.shell")
    finally:
        sys.path.remove(HOOKS)
    readings = {word: shell.lex(f"false && {{ true; {word}; cd x || exit; }}") for word in ("}", '"}"')}
    expected = {"}": ["false", "true", "cd", "exit"], '"}"': ["false", "true", "}", "cd", "exit"]}
    for word in ("}", '"}"', "}"):
        got = [str(simple.words[0]) for simple in shell.builtin_commands(readings[word])]
        report(
            ok=got == expected[word],
            line=f"exp {expected[word]} got {got}  [reserved ]  the programs after {word} in one process",
        )


def launcher_cases(report: Callable[..., None]) -> None:
    """The launcher check of Claude Code's table, run as the frontend runs the guard, and the check
    itself in this process with an explicit platform, so that its answers on macOS are tested on
    every platform. A `Bash` call of `true` and a `Read` call, a tool that no entry of the table
    names, each pass by the corpus, and a payload that the table cannot read is refused with the
    launcher's reason, which the check gives before the payload is read; each subprocess case sets
    `CLAUDE_CODE_ENTRYPOINT` and `CLAUDE_CONFIG_DIR` or removes them. The Code tab and a session
    that `claudex` starts are the two exceptions of Claude Code."""
    fixture_dir = pathlib.Path(FIXTURE.name)
    opened = launcher_home(fixture_dir / "launcher-open")
    on = launcher_home(fixture_dir / "launcher-on", enabled=True)
    off = launcher_home(fixture_dir / "launcher-off", enabled=False)
    text_true = launcher_home(fixture_dir / "launcher-text", enabled="true")
    unread = launcher_home(fixture_dir / "launcher-unread", enabled=b"{")
    no_sandbox = launcher_home(fixture_dir / "launcher-empty", enabled=b"{}")
    not_utf8 = launcher_home(fixture_dir / "launcher-bytes", enabled=b'{"sandbox": {"enabled": true}} \xff')
    missing = launcher_home(fixture_dir / "launcher-none", ssh=False)
    plain = launcher_home(fixture_dir / "launcher-file", ssh=False)
    pathlib.Path(FIXTURE.name, "launcher-file", ".ssh").write_text("", encoding="utf-8")
    bash = json.dumps({"tool_name": "Bash", "tool_input": {"command": "true"}, "cwd": CWD}).encode("utf-8")
    read = json.dumps({"tool_name": "Read", "tool_input": {"file_path": CWD + "probe.py"}, "cwd": CWD})
    desktop = "claude-desktop"
    corpus_pass = ("pass", "")
    for label, home, entry, data, on_mac, elsewhere in (
        ("a readable .ssh: Bash", opened, None, bash, ("deny", LAUNCHER_OUTSIDE), corpus_pass),
        (
            "a readable .ssh: Read, a tool with no entry",
            opened,
            None,
            read.encode("utf-8"),
            ("deny", LAUNCHER_OUTSIDE),
            corpus_pass,
        ),
        (
            "a readable .ssh: a payload that the table cannot read",
            opened,
            None,
            b"not json",
            ("deny", LAUNCHER_OUTSIDE),
            ("deny", "cannot read"),
        ),
        ("no .ssh: Bash", missing, None, bash, ("deny", LAUNCHER_UNKNOWN), corpus_pass),
        ("the Code tab, sandbox.enabled true: Bash", on, desktop, bash, corpus_pass, corpus_pass),
        (
            "the Code tab, sandbox.enabled false: Bash",
            off,
            desktop,
            bash,
            ("deny", LAUNCHER_OUTSIDE),
            corpus_pass,
        ),
        (
            "the Code tab, no settings file: Bash",
            opened,
            desktop,
            bash,
            ("deny", LAUNCHER_OUTSIDE),
            corpus_pass,
        ),
        ("the CLI, sandbox.enabled true: Bash", on, "cli", bash, ("deny", LAUNCHER_OUTSIDE), corpus_pass),
    ):
        env = {k: v for k, v in ENV.items() if k not in LAUNCHER_ENV} | {"HOME": home}
        if entry is not None:
            env["CLAUDE_CODE_ENTRYPOINT"] = entry
        expected, reason = on_mac if MAC else elsewhere
        got, output = guard_run(data, env=env)
        report(
            ok=got == expected and reason in output,
            line=f"exp {expected} got {got}  [launcher ]  {label}: {output[:70]!r}",
        )
    # A session that `claudex` starts: Claude Code's own sandbox, with `CLAUDE_CONFIG_DIR` at
    # `<home>/.config/claudex`. Each home has a readable `.ssh`, and each case sets one of
    # `CLAUDE_CONFIG_DIR` and `CLAUDE_CODE_ENTRYPOINT` and removes the other: a claudex case has no
    # Code-tab settings, and the Code-tab case, a config of None, no claudex directory. A settings file
    # that is a FIFO is refused at once, not after the time limit. A refusal names both ways in.
    cx_on = launcher_home(fixture_dir / "launcher-cx-on")
    cx_dir = claudex_home(cx_on, enabled=True)
    cx_other = claudex_home(cx_on, enabled=True, directory=".config/other")
    cx_off_home = launcher_home(fixture_dir / "launcher-cx-off")
    cx_text_home = launcher_home(fixture_dir / "launcher-cx-text")
    cx_none_home = launcher_home(fixture_dir / "launcher-cx-none")
    cx_bad_home = launcher_home(fixture_dir / "launcher-cx-bad")
    cx_fifo_home = launcher_home(fixture_dir / "launcher-cx-fifo")
    tab_fifo = launcher_home(fixture_dir / "launcher-tab-fifo", enabled=FIFO)
    cx_link = fixture_dir / "launcher-cx-link"
    cx_link.symlink_to(cx_dir[1:], target_is_directory=True)
    # The guard runs in FIXTURE, so this relative path names the claudex directory of `cx_on` there.
    cx_relative = "launcher-cx-on/.config/claudex"
    passed: tuple[str, tuple[str, ...]] = ("pass", ())
    refused: tuple[str, tuple[str, ...]] = ("deny", ("`agentbox claude`", "`claudex`"))
    for label, home, config, on_mac in (
        ("claudex, sandbox.enabled true", cx_on, cx_dir, passed),
        ("claudex spelt with one leading slash", cx_on, cx_dir[1:], passed),
        ("claudex through a link", cx_on, "/" + str(cx_link), passed),
        ("claudex, sandbox.enabled false", cx_off_home, claudex_home(cx_off_home, enabled=False), refused),
        (
            'claudex, sandbox.enabled "true"',
            cx_text_home,
            claudex_home(cx_text_home, enabled="true"),
            refused,
        ),
        ("claudex, no settings file", cx_none_home, claudex_home(cx_none_home), refused),
        ("claudex, settings that are no JSON", cx_bad_home, claudex_home(cx_bad_home, enabled=b"{"), refused),
        (
            "claudex, settings that are a FIFO",
            cx_fifo_home,
            claudex_home(cx_fifo_home, enabled=FIFO),
            refused,
        ),
        ("CLAUDE_CONFIG_DIR at another directory", cx_on, cx_other, refused),
        ("CLAUDE_CONFIG_DIR relative", cx_on, cx_relative, refused),
        ("the Code tab, settings that are a FIFO", tab_fifo, None, refused),
    ):
        env = {k: v for k, v in ENV.items() if k not in LAUNCHER_ENV} | {"HOME": home}
        if config is None:
            env["CLAUDE_CODE_ENTRYPOINT"] = desktop
        else:
            env["CLAUDE_CONFIG_DIR"] = config
        expected, texts = on_mac if MAC else passed
        for tool, data in (("Bash", bash), ("Read", read.encode("utf-8"))):
            got, output = guard_run(data, env=env)
            report(
                ok=got == expected and all(t in output for t in texts),
                line=f"exp {expected} got {got}  [launcher ]  {label}: {tool}: {output[:70]!r}",
            )
    sys.path.insert(0, HOOKS)
    try:
        launcher: Any = importlib.import_module("guard.launcher")
    except ImportError as e:
        report(ok=False, line=f"exp the module got {type(e).__name__}  [launcher ]  guard.launcher: {e}")
        return
    finally:
        sys.path.remove(HOOKS)
    for frontend, home, environ, platform, want, text in (
        ("claude", opened, {}, "linux", "pass", ""),
        ("claude", opened, {}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", HOME, {}, "darwin", "pass", ""),
        ("claude", missing, {}, "darwin", "deny", LAUNCHER_UNKNOWN + " this Claude Code session"),
        ("claude", plain, {}, "darwin", "deny", "NotADirectoryError"),
        ("claude", on, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "pass", ""),
        ("claude", off, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", text_true, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", unread, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", no_sandbox, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", not_utf8, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", opened, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", on, {"CLAUDE_CODE_ENTRYPOINT": "cli"}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("claude", on, {"CLAUDE_CODE_ENTRYPOINT": desktop + "-3p"}, "darwin", "deny", LAUNCHER_OUTSIDE),
        ("opencode", on, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", "this OpenCode session"),
        ("omp", on, {"CLAUDE_CODE_ENTRYPOINT": desktop}, "darwin", "deny", "agentbox omp"),
    ):
        verdict = launcher.outside(frontend, home, environ, platform)
        settings = pathlib.Path(home, ".claude", "settings.json")
        shown = repr(settings.read_bytes()) if settings.exists() else "no settings"
        report(
            ok=verdict.decision == want and text in verdict.reason,
            line=f"exp {want} got {verdict.decision}  [launcher ]  outside({frontend!r}, {home[-22:]!r}, "
            f"{environ}, {platform!r}) with {shown}: {verdict.reason[:60]!r}",
        )
    # The claudex exception in this process: only for Claude Code, only with an absolute
    # `CLAUDE_CONFIG_DIR` that resolves to `<home>/.config/claudex`, and only with `sandbox.enabled`
    # the boolean `true` there. A refusal of Claude Code names `claudex` and its directory; one of
    # OpenCode and oh-my-pi names neither.
    here = pathlib.Path.cwd().resolve()
    cx_here = str(pathlib.Path(cx_dir).resolve().relative_to(here, walk_up=True))
    cx_empty_home = launcher_home(fixture_dir / "launcher-cx-empty")
    cx_list_home = launcher_home(fixture_dir / "launcher-cx-list")
    cx_bytes_home = launcher_home(fixture_dir / "launcher-cx-bytes")
    cx_bytes = claudex_home(cx_bytes_home, enabled=b'{"sandbox": {"enabled": true}} \xff')
    for frontend, home, config, want in (
        ("claude", cx_empty_home, claudex_home(cx_empty_home, enabled=b"{}"), "deny"),
        ("claude", cx_list_home, claudex_home(cx_list_home, enabled=b'{"sandbox": [true]}'), "deny"),
        ("claude", cx_bytes_home, cx_bytes, "deny"),
        ("claude", cx_on, cx_dir, "pass"),
        ("claude", cx_on, cx_dir[1:], "pass"),
        ("claude", cx_on, "/" + str(cx_link), "pass"),
        ("claude", cx_on, cx_dir + "/", "pass"),
        ("claude", cx_off_home, cx_off_home + "/.config/claudex", "deny"),
        ("claude", cx_text_home, cx_text_home + "/.config/claudex", "deny"),
        ("claude", cx_none_home, cx_none_home + "/.config/claudex", "deny"),
        ("claude", cx_bad_home, cx_bad_home + "/.config/claudex", "deny"),
        ("claude", cx_on, cx_other, "deny"),
        ("claude", cx_on, cx_dir + "/../other", "deny"),
        ("claude", cx_on, cx_here, "deny"),
        ("claude", cx_on, "", "deny"),
        ("opencode", cx_on, cx_dir, "deny"),
        ("omp", cx_on, cx_dir, "deny"),
    ):
        environ = {"CLAUDE_CONFIG_DIR": config}
        verdict = launcher.outside(frontend, home, environ, "darwin")
        # A refusal asks for `agentbox <frontend>`, a refusal of Claude Code for `claudex` too, and it
        # names `claudex` and `~/.config/claudex` exactly when it refuses Claude Code.
        ways = "`agentbox claude`,\nor with `claudex`" if frontend == "claude" else f"`agentbox {frontend}`."
        named = want == "pass" or ways in verdict.reason
        claudex_named = frontend == "claude" and want == "deny"
        report(
            ok=verdict.decision == want
            and named
            and ("`claudex`" in verdict.reason) == claudex_named
            and ("`~/.config/claudex`" in verdict.reason) == claudex_named,
            line=f"exp {want} got {verdict.decision}  [launcher ]  outside({frontend!r}, {home[-22:]!r}, "
            f"{environ}, 'darwin'): {verdict.reason[:60]!r}",
        )
    # The listing comes before the claudex exception: a claudex session whose `.ssh` is missing or a
    # file is refused because the guard cannot tell, and one whose `.ssh` it cannot list passes.
    cx_no_ssh = launcher_home(fixture_dir / "launcher-cx-nossh", ssh=False)
    cx_ssh_file = launcher_home(fixture_dir / "launcher-cx-sshfile", ssh=False)
    pathlib.Path(FIXTURE.name, "launcher-cx-sshfile", ".ssh").write_text("", encoding="utf-8")
    cx_closed = launcher_home(fixture_dir / "launcher-cx-closed", ssh=False)
    closed_ssh(cx_closed[1:])
    for home, want, text in (
        (cx_no_ssh, "deny", LAUNCHER_UNKNOWN + " this Claude Code session"),
        (cx_ssh_file, "deny", LAUNCHER_UNKNOWN + " this Claude Code session"),
        (cx_closed, "pass", ""),
    ):
        environ = {"CLAUDE_CONFIG_DIR": claudex_home(home, enabled=True)}
        verdict = launcher.outside("claude", home, environ, "darwin")
        report(
            ok=verdict.decision == want and text in verdict.reason,
            line=f"exp {want} got {verdict.decision}  [launcher ]  outside('claude', {home[-22:]!r}, "
            f"{environ}, 'darwin') with sandbox.enabled true: {verdict.reason[:60]!r}",
        )


def command_cases():
    """The guard on each record of the corpus, and on the edges that a line of it cannot hold."""
    wrong = 0
    total = 0

    def report(*, ok: bool, line: str) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    for stdin, expected, profile in corpus_records():
        got, _ = guard_run(stdin.encode("utf-8"), env={**ENV, **profile})
        named = f" with {profile}" if profile else ""
        report(ok=got == expected, line=f"exp {expected} got {got}  [guard    ]  {stdin[:200]!r}{named}")
    launcher_cases(report)
    quoted_reserved_cases(report)

    for size, expected in ((MIB, "pass"), (MIB + 1, "deny")):
        payload = {"tool_name": "Bash", "tool_input": {"command": "echo " + "a" * (size - 5)}, "cwd": CWD}
        got, output = guard_run(json.dumps(payload).encode("utf-8"))
        ok = got == expected and (expected == "pass" or "more than" in output)
        report(ok=ok, line=f"exp {expected} got {got}  [guard    ]  a command of {size} bytes")
    # Commands of 1 MiB whose words each check walks: a chain of `cd`, through a link too, one `cd`
    # word of many names, a repeated `cd` to a deep directory, many operands of a recursive `rm`, four
    # readings, loop words with no `do` or `done`, many distinct writes that git ignores. The
    # guard's decision decides each case, and its line gives the seconds; the counted cases below
    # bound the work of several of them.
    four = "; git status > /dev/null; rm -rf x; echo x > y.log ';' \\\n"
    # Commands of 1 MiB whose operands and `git init` targets a check resolves many times: the same or
    # distinct operands of a recursive `rm` below a directory ten names deep, operands in distinct
    # directories below it and below an absolute directory 40 names deep, and a `git init` from a
    # working directory in no work tree, whose work tree
    # check climbs to `/`; in one and in four readings. The flag marks a command whose steps are bound.
    ten = pathlib.PurePosixPath(*(f"d{i}" for i in range(1, 11)))
    distinct, same, below = (str(ten / name) + " " for name in ("x{}", "x", "x{}/y"))
    # The absolute directory is resolved, so that no link on its path (`/tmp` on macOS) settles its
    # walks into one.
    absolute = str(pathlib.PurePosixPath(pathlib.Path(DEEP).resolve(), "x{}", "y")) + " "
    resolved = (
        (LOGS, False, mib_command(distinct, "x", "rm -rf ")),
        (LOGS, False, mib_command(distinct, "x ';' \\\n", "rm -rf ")),
        (LOGS, False, mib_command(same, "x ';' \\\n", "rm -rf ")),
        (LOGS, False, mib_command(below, "x", "rm -rf ")),
        (LOGS, False, mib_command(absolute, "x", "rm -rf ")),
        (OUTSIDE, True, mib_command("git init x; ", "git status")),
        (OUTSIDE, True, mib_command("git init x; ", "git status ';' \\\n")),
    )
    for cwd, (command, shape), expected in (
        *((cwd, made, "pass") for cwd, _, made in resolved),
        (CWD, mib_command("cd a; ", "echo x > /tmp/x"), "pass"),
        (CWD, mib_command("cd a && git status; ", "true"), "pass"),
        (CWD, mib_command("cd a; ", "git add -A; rm x"), "deny"),
        (CWD, mib_command("cd ../a; ", "rm -rf x"), "deny"),
        # Each `cd a` can fail, so the `rm` can run in more directories than the rm check follows.
        (SCRATCH, mib_command("cd a; rm -rf x; ", "true"), "ask"),
        (SCRATCH, mib_command("cd a; echo x > f.txt; ", "true"), "pass"),
        (CWD, mib_command("cd a; git status; ", "git init x"), "deny"),
        (CWD, mib_command(f"cd {LINK}; cd ..; ", "rm -rf ."), "deny"),
        (CWD, mib_command("while git ", "x"), "pass"),
        (CWD, mib_command("for do ", "git status"), "pass"),
        (CWD, mib_command("echo x > __pycache__/a{}.log; ", "true"), "pass"),
        (WT, mib_command("rm -rf x ", ".."), "deny"),
        (WT, mib_command("rm -rf x ", ".. ';' \\\n"), "deny"),
        (LOGS, mib_command("a/../", four, "cd "), "pass"),
        (LOGS, mib_command(f"cd {DEEP}; ", "git status > /dev/null; rm -rf x; echo x > y.log"), "pass"),
        (DEEP, mib_command("echo x > f{}.log; ", "true"), "pass"),
    ):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
        start = time.monotonic()
        got, _ = guard_run(json.dumps(payload).encode("utf-8"), limit=MIB_HANG)
        took = time.monotonic() - start
        report(
            ok=got == expected, line=f"exp {expected} got {got}  [guard    ]  {shape}, 1 MiB: {took:.1f} s"
        )
    # The work per payload: each check and each reading takes a walk of a `cd` word from the memo of
    # `paths.py`, an absolute word is walked once whatever the start, and a walk reads each name once
    # from each directory, so a payload reads each distinct name of its `cd` words at most once in each
    # of the two modes from each start; and the writes of a command ask git once per work tree. The
    # third command reads each `d<i>` from two starts in the `real` mode: from the directory of the
    # chain of `cd`, and from the call's working directory, against which the sandbox check tests each
    # `cd`; and the work tree check walks each `cd` to the deep directory from a new start.
    # The first command's walks step once per name of its `cd` word in each mode, however many checks
    # and readings take them.
    # The third command's `cd`s can fail, so its `rm` can run in more directories than the rm check
    # follows, and it asks.
    for cwd, starts, stepped, expected, (command, shape) in (
        (LOGS, 2, True, "pass", mib_command("d{}/../", four, "cd ")),
        (LOGS, 2, False, "pass", mib_command("a/../", four, "cd ")),
        (LOGS, 3, False, "ask", mib_command(f"cd d{{}}; cd {DEEP}; ", four.removeprefix("; "))),
    ):
        words = re.findall(r"(?:^|; )cd (\S+)", command)
        names = len({name for word in words for name in word.split("/") if name not in ("", "..")})
        got, stats, spawns, steps = guard_counted(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}).encode("utf-8")
        )
        bound = f"at most {starts} x {names} + {WALK_READS} reads" + (" and steps" if stepped else "")
        ok = got == expected and 0 <= stats <= starts * names + WALK_READS
        report(
            ok=ok and (not stepped or 0 <= steps <= starts * names + WALK_READS),
            line=f"exp {expected}, {bound} got {got}, {stats} reads, {steps} steps  [guard    ]  {shape}",
        )
    # The commands that resolve an operand or a `git init` target many times read each (directory,
    # name) once in each mode: at most two reads for each distinct name of the command. A `git init`
    # climbs from each directory once, so its steps are bound too.
    for cwd, stepped, (command, shape) in resolved:
        names = len({name for name in re.split(r"[ /;]+", command) if name not in ("", "..")})
        got, stats, spawns, steps = guard_counted(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}).encode("utf-8")
        )
        bound = f"at most 2 x {names} + {WALK_READS} reads" + (" and steps" if stepped else "")
        ok = got == "pass" and 0 <= stats <= 2 * names + WALK_READS
        report(
            ok=ok and (not stepped or 0 <= steps <= 2 * names + WALK_READS),
            line=f"exp pass, {bound} got {got}, {stats} reads, {steps} steps  [guard    ]  {shape}",
        )
    command, shape = mib_command("echo x > __pycache__/a{}.log; ", "true")
    got, stats, spawns, steps = guard_counted(
        json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": CWD}).encode("utf-8")
    )
    report(
        ok=got == "pass" and 0 <= spawns <= 2,
        line=f"exp pass, at most 2 git spawns got {got}, {spawns}  [guard    ]  {shape}",
    )
    # A write target with a NUL, which git cannot read, is not ignored: the write check refuses it with
    # its reason, and the guard does not raise. Git would read the NUL as the end of a path, and the
    # absolute path after it, outside the work tree, as one that stops git.
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo x > a\x00/x.log"}, "cwd": CWD}
    got, output = guard_run(json.dumps(payload).encode("utf-8"))
    report(
        ok=got == "deny" and "writes a file in a git working tree" in output,
        line=f"exp deny got {got}  [guard    ]  a write to a path with a NUL: {output[:60]!r}",
    )
    # An `EnterWorktree` call with the path of a worktree outside `.claude/worktrees/` is refused, and
    # the reason names the call that reaches it with no prompt: a `cd` to that path on its own.
    payload = {"tool_name": "EnterWorktree", "tool_input": {"path": WT}, "cwd": CWD}
    got, output = guard_run(json.dumps(payload).encode("utf-8"))
    report(
        ok=got == "deny" and f"`cd {WT}` as a Bash call of its own" in output,
        line=f"exp deny got {got}  [guard    ]  EnterWorktree with a worktree's path: {output[:60]!r}",
    )
    # A `.git` that is a dangling link: the sandbox check reads the link itself, so to it the directory
    # is a work tree and a `git init` there is refused; the write check reads what the link names, so
    # to it the directory lies in no work tree and a write there of a file that is no source passes.
    for command, expected in (("git init x", "deny"), ("echo x > f.txt", "pass")):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": DANGLING}
        got, _ = guard_run(json.dumps(payload).encode("utf-8"))
        report(
            ok=got == expected,
            line=f"exp {expected} got {got}  [guard    ]  {command!r} beside a dangling .git",
        )
    # A link to itself, which `Path.resolve` leaves in the path it returns: the path is settled without
    # following its links, so the guard decides the operand below it and does not raise.
    payload = {"tool_name": "Bash", "tool_input": {"command": "rm -rf loop/x"}, "cwd": LOGS}
    got, _ = guard_run(json.dumps(payload).encode("utf-8"))
    report(ok=got == "pass", line=f"exp pass got {got}  [guard    ]  'rm -rf loop/x' below a link to itself")
    got, output = guard_run(b'{"tool_name":"Bash","tool_input":{"command":"echo \xff"},"cwd":"/"}')
    report(
        ok=got == "deny" and "UTF-8" in output, line=f"exp deny got {got}  [guard    ]  a payload byte 0xFF"
    )
    # The `gh api` check asks, and a check before it (staging) or after it (archive) refuses: the
    # answer is the refusal, with the reason of the check that refused.
    for then, reason in (
        ("git add -A", "stages files this session did not write"),
        ("git archive -o x.tar HEAD", "writes its file outside the sandbox"),
    ):
        command = "gh api -X POST repos/o/r/issues -f title=t && " + then
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": CWD}
        got, output = guard_run(json.dumps(payload).encode("utf-8"))
        ok = got == "deny" and reason in output and "review and comment" not in output
        report(
            ok=ok,
            line=f"exp deny got {got}  [guard    ]  the reason of the winner on {command!r}: {output[:80]!r}",
        )
    token_cases(report)
    # The Kaimon check's refusal of a missing key, like that of a dead key, names the live sessions
    # of the fixture cache, sorted and each once, and neither the stale gate nor a gate that cannot
    # be read; with an empty gate directory it says none is live, and with no gate directory it
    # names no session and does not say that none is live.
    listed = "The live sessions are " + ", ".join(f"`{key}`" for key in LIVE_GATES) + "."
    unlisted = (STALE_GATE, *UNREAD_GATES)
    for tool, arguments, cache, want, label in (
        ("ex", {"e": "1 + 1"}, KAIMON_CACHE, (listed + " Pass the",), "ex without ses lists the live keys"),
        (
            "manage_repl",
            {"command": "restart"},
            KAIMON_CACHE,
            (listed,),
            "manage_repl without session lists the live keys",
        ),
        (
            "ex",
            {"e": "1 + 1", "ses": STALE_GATE},
            KAIMON_CACHE,
            (f"no live Kaimon session has the key `{STALE_GATE}`", listed),
            "a dead key lists the live keys",
        ),
        ("ex", {"e": "1 + 1"}, NO_GATES, (), "ex without ses and no gate directory names no key"),
        (
            "ex",
            {"e": "1 + 1"},
            EMPTY_GATES,
            ("No session is live.",),
            "ex without ses and an empty gate directory says none is live",
        ),
        (
            "ex",
            {"e": "1 + 1"},
            TWIN_CACHE,
            (f"The live sessions are `{TWIN_GATE}`.",),
            "ex without ses lists a key of two sessions once",
        ),
        (
            "ex",
            {"e": "1 + 1"},
            MANY_CACHE,
            ("The live sessions are " + ", ".join(f"`{key}`" for key in MANY_GATES) + ".",),
            "ex without ses lists eight live keys sorted",
        ),
    ):
        payload = {"tool_name": f"mcp__kaimon__{tool}", "tool_input": arguments, "cwd": CWD}
        # The hash seed 0 fixes the order of a set of keys in the guard, so that each case gives
        # one verdict on every run.
        got, output = guard_run(
            json.dumps(payload).encode("utf-8"),
            env={**ENV, "KAIMON_CACHE_DIR": cache, "PYTHONHASHSEED": "0"},
        )
        shown = [key for key in unlisted if key in output and key not in arguments.values()]
        claims = "The live sessions are" in output or "No session is live." in output
        ok = (
            got == "deny"
            and all(text in output for text in want)
            and not shown
            and (bool(want) or not claims)
        )
        report(ok=ok, line=f"exp deny got {got}  [guard    ]  {label}: {output[:70]!r}")
    # With no gate directory the check cannot tell whether a key is live, and passes the call.
    payload = {"tool_name": "mcp__kaimon__ex", "tool_input": {"e": "1 + 1", "ses": STALE_GATE}, "cwd": CWD}
    got, output = guard_run(json.dumps(payload).encode("utf-8"), env={**ENV, "KAIMON_CACHE_DIR": NO_GATES})
    report(
        ok=got == "pass",
        line=f"exp pass got {got}  [guard    ]  a key and no gate directory: {output[:70]!r}",
    )
    # The refusal of a dead key names the live sessions of the one listing that found the key
    # dead: a gate directory that cannot be listed after it does not turn into "No session is live.".
    sys.path.insert(0, HOOKS)
    try:
        kaimon: Any = importlib.import_module("guard.kaimon_session")
    finally:
        sys.path.remove(HOOKS)
    with mock.patch.dict(os.environ, {"KAIMON_CACHE_DIR": KAIMON_CACHE}):
        listing = kaimon.gates()
        with mock.patch.object(kaimon, "gates", side_effect=[listing, None]):
            reason = kaimon.gone(STALE_GATE).reason
    report(
        ok=listing is not None and listed in reason and "No session is live." not in reason,
        line=f"exp the live keys  [guard    ]  a dead key, then an unlistable gate directory: {reason[-70:]!r}",
    )
    got, output = guard_run(b'{"tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"/"}', "other")
    report(
        ok=got == "deny" and "usage" in output,
        line=f"exp deny got {got}  [guard    ]  --from a frontend it lacks",
    )
    code, stderr = guard_raises()
    report(
        ok=code == 2 and "RuntimeError" in stderr,
        line=f"exp 2 got {code}  [guard    ]  the guard raises: {stderr!r}",
    )
    copy, source = pathlib.Path(GUARD, "jsonio.py"), pathlib.Path(REPO, "lib", "harness", "jsonio.py")
    same = copy.read_bytes() == source.read_bytes()
    report(
        ok=same,
        line=f"exp same got {'same' if same else 'other'}  [guard    ]  the guard's jsonio.py, byte for byte",
    )
    # Every read of the file system that a payload makes goes through `paths.py`, so no call site can
    # read again what another check or reading has read.
    reads = guard_reads()
    report(ok=not reads, line=f"exp none got {reads}  [guard    ]  file-system reads outside paths.py")

    try:
        commands, bash, guard = guard_entry(FIXTURE.name + "/missing-home")
    except (ImportError, OSError, ValueError, LookupError, TypeError, StopIteration) as e:
        report(ok=False, line=f"exp render got {type(e).__name__}  [guard    ]  {e}")
        return total, wrong
    note = shlex.join([sys.executable, FIXTURE.name + "/missing-home/.claude/hooks/kaimon-note.py"])
    report(
        ok=commands == [guard] and bash == ["rtk hook claude", note],
        line=f"exp guard; rtk and kaimon-note got {commands}; {bash}  [guard    ]  the rendered * and Bash groups",
    )
    # Claude Code runs the rendered hook command through a shell, the payload on stdin. The guard's path
    # is missing below the fixture's home, and then the interpreter is too, which exits 127 without the
    # fallback.
    rendered = next((c for c in commands if "/.claude/hooks/guard" in c), "")
    missing_python = shlex.quote(FIXTURE.name + "/missing-env/bin/python")
    for what, command in (
        ("the guard is missing", rendered),
        ("the interpreter is missing", rendered.replace(shlex.quote(sys.executable), missing_python, 1)),
    ):
        try:
            proc = subprocess.run(
                [shutil.which("bash") or "/bin/bash", "-c", command],
                input=b'{"tool_name":"Bash","tool_input":{"command":"ls"}}',
                capture_output=True,
                timeout=TIMEOUT,
                check=False,
            )
            got = str(proc.returncode)
        except subprocess.TimeoutExpired:
            got = "timeout"
        report(ok=got == "2", line=f"exp 2 got {got}  [guard    ]  the guard cannot start, {what}: {command}")
    return total, wrong


def token_cases(report: Callable[..., None]) -> None:
    """The token check's reason on calls that hold a token, and its place in each list of checks."""
    # The token check names the form in its reason, and neither the token nor its body. It stands
    # first in each list of checks, so its reason answers a call that another check refuses too: the
    # web check a parameter `access_token=`, the `gh api` check a DELETE, the Kaimon check a gate
    # that is not live.
    ghp, sk = TOKENS["GHP"], TOKENS["SK"]
    for tool, tool_input, (form, token, body) in (
        ("Bash", {"command": "echo " + ghp}, ("gh[pousr]_", ghp, GHP_BODY)),
        ("WebFetch", {"url": f"https://example.org/x?access_token={ghp}"}, ("gh[pousr]_", ghp, GHP_BODY)),
        (
            "Bash",
            {"command": f'curl -s "https://example.org/x?access_token={ghp}"'},
            ("gh[pousr]_", ghp, GHP_BODY),
        ),
        ("Bash", {"command": f"gh api -X DELETE repos/{ghp}/r"}, ("gh[pousr]_", ghp, GHP_BODY)),
        ("mcp__kaimon__ex", {"e": f'ENV["KEY"] = "{sk}"', "ses": STALE_GATE}, ("sk-", sk, SK_BODY)),
    ):
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": CWD}
        got, output = guard_run(json.dumps(payload).encode("utf-8"))
        hidden = token not in output and body not in output
        report(
            ok=got == "deny" and f"`{form}`" in output and hidden,
            line=f"exp deny, the form and no token got {got}, the token {'hidden' if hidden else 'SHOWN'}  "
            f"[guard    ]  the reason of the token check on a {tool} call: {output[:60]!r}",
        )
    # The token check is the first element of each list of checks that holds it, in each frontend.
    sys.path.insert(0, HOOKS)
    try:
        token: Any = importlib.import_module("guard.token_forms")
        tables: dict[str, Any] = {
            name: importlib.import_module(f"guard.frontends.{name}")
            for name in ("claude", "opencode", "omp", "antigravity")
        }
    finally:
        sys.path.remove(HOOKS)
    claude_entries = {matcher.pattern: checks for matcher, checks in tables["claude"].TABLE}
    for where, checks in (
        ("claude SHELL", tables["claude"].SHELL),
        ("claude mcp__kaimon__.*", claude_entries["mcp__kaimon__.*"]),
        ("claude WebFetch|WebSearch", claude_entries["WebFetch|WebSearch"]),
        ("opencode SHELL", tables["opencode"].SHELL),
        ("opencode KAIMON_CHECKS", getattr(tables["opencode"], "KAIMON_CHECKS", ())),
        ("opencode WEB_CHECKS", getattr(tables["opencode"], "WEB_CHECKS", ())),
        ("omp SHELL", tables["omp"].SHELL),
        ("omp CHECKS['mcp']", tables["omp"].CHECKS["mcp"]),
        ("antigravity SHELL", tables["antigravity"].SHELL),
        ("antigravity CHECKS['mcp']", tables["antigravity"].CHECKS["mcp"]),
    ):
        first = bool(checks) and checks[0] is token.check
        report(
            ok=first,
            line=f"exp first got {'first' if first else 'later'}  [guard    ]  the token check in {where}",
        )


def payload_cases():
    """The other hooks on their payloads."""
    wrong = 0
    total = 0
    # A line of the grants that is not JSON is passed over, and the grants after it count.
    grants = pathlib.Path(HOME, ".claude", "logs", "edit-scope.jsonl")
    grants.parent.mkdir(parents=True, exist_ok=True)
    grants.write_text("not json\n", encoding="utf-8")
    for record, session, path, fields, expected in EDITSCOPE_CASES:
        tool_input = {"file_path": path} if path is not None else {}
        tool_input.update({k: v for k, v in fields.items() if k != "cwd"})
        payload = {"session_id": session, "tool_input": tool_input}
        if "cwd" in fields:
            payload["cwd"] = fields["cwd"]
        got = decision(EDITSCOPE, json.dumps(payload), ("--record",) if record else ())
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(
            f"{mark} exp {expected} got {got}  [edit-scop]  {'record ' if record else ''}{session!r} {path or tool_input}"
        )
    for args, payload, expected in EDITSCOPE_PAYLOADS:
        got = decision(EDITSCOPE, payload, args)
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [edit-scop]  {' '.join(args)} payload {payload!r}")
    log = os.path.join(FIXTURE.name, "probe-prompt-log.jsonl")
    for payload in PROMPTLOG_CASES:
        proc = call(PROMPTLOG, payload, {**ENV, "LOG": log})
        if proc is None:
            got = "timeout"
        else:
            got = "pass" if proc.returncode == 0 and not proc.stdout else f"exit {proc.returncode}"
        total += 1
        wrong += got != "pass"
        mark = "ok " if got == "pass" else "BAD"
        print(f"{mark} exp pass got {got}  [prompt-lo]  {payload[:60]!r}")
    try:
        with open(log, encoding="utf-8") as lines:
            logged = sum(1 for _ in lines)
    except FileNotFoundError:
        logged = 0
    total += 1
    wrong += logged != 2
    print(f"{'ok ' if logged == 2 else 'BAD'} exp 2 got {logged}  [prompt-lo]  lines logged")
    for name, event, fields, expected in CONTEXT_CASES:
        payload = json.dumps(
            {"hook_event_name": event, "transcript_path": context_transcript(name), **fields}
        )
        got = context_answer(call(CONTEXT, payload), event)
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [context  ]  {name} {event} {fields or ''}")
    for payload in (
        "not json at all",
        "",
        "[1]",
        '{"hook_event_name":"UserPromptSubmit","transcript_path":7}',
    ):
        got = context_answer(call(CONTEXT, payload), "UserPromptSubmit")
        total += 1
        wrong += got != "pass"
        mark = "ok " if got == "pass" else "BAD"
        print(f"{mark} exp pass got {got}  [context  ]  payload {payload!r}")
    for payload in WORKTREE_CASES:
        proc = call(WORKTREE, payload, WORKTREE_ENV)
        got = "timeout" if proc is None else proc.returncode
        total += 1
        wrong += got != 1
        mark = "ok " if got == 1 else "BAD"
        print(f"{mark} exp 1 got {got}  [worktree ]  fail-closed: {payload!r}")
    n, bad = worktree_git_cases()
    m, worse = worktree_sweep_cases()
    return total + n + m, wrong + bad + worse


# `kaimon-note.py` adds a note to a Bash call that runs a Julia probe and lets every call run. A
# case gives it a list of payloads, with one Kaimon cache in its environment, and expects each to
# get the note or no output; one wrong payload makes the case wrong.
KAIMON_NOTE = HOOKS + "kaimon-note.py"
NOTED = ("mcp__kaimon__ex", "`ping`", "`start_session")
LEFT_ALONE = (
    "grep -rn julia src",
    'echo "julia -e 1"',
    "julia +1.12 -e 1",
    "julia --version",
    "julia --startup-file=no ~/Research/Harness/scripts/run-tests.jl . affected",
    "julia --project=. .githooks/test-layout.jl",
    "julia test/runtests.jl",
    "julia docs/make.jl",
    "julia scripts/foo-test.jl",
    "julia -e 'using Pkg; Pkg.test()'",
    "julia -e 'using BenchmarkTools; @btime f()'",
    "julia -e '@allocated f()'",
    "time julia x.jl",
)
MORE_PROBES = (
    "julia --eval='f(1)'",
    "julia -e'f(1)'",
    "julia -qe 'f(1)'",
    "julia -E 'f(1)'",
    "julia --print 'f(1)'",
    "julia -p 4 probe.jl",
    "julia -p4 probe.jl",
    "julia --procs auto probe.jl",
    "julia -p 2 -e 'f(1)'",
    "julia -t 4 probe.jl",
    "julia --project test/probe.jl",
    "julia -e 'f(1)' test/runtests.jl",
    "~/.juliaup/bin/julia -e 'f(1)'",
    "julia --project=. <<'EOF'\nusing Foo\nprintln(\"it's\")\nEOF",
    "julia --project=. < probe.jl",
    "echo 'f(1)' | julia --project=.",
    "julia --project=. <<< 'f(1)'",
    "(cd x; julia -e 'f(1)') 2>&1",
    "julia -e 'f(1)' > out.txt",
    "julia 2>err.txt -e 'f(1)'",
    "julia +1.12 -e 1;(julia -e 'f(1)')",
    "A=1 B=2 julia -e 'f(1)'",
    "julia --threads 4 probe.jl",
    "julia -- -v.jl",
    "echo 'f(1)' | julia -",
    "julia - foo-test.jl < probe.jl",
    "cat <<-EOF\n\tit's\n\tEOF\njulia -e 'f(1)'",
    "cat <<A <<B\nx\nA\nit's\nB\njulia -e 'f(1)'",
    "cat <<'EOF'\nit's\nEOF\njulia -e 'f(1)'",
    "cat <<\"EOF\"\nit's\nEOF\njulia -e 'f(1)'",
    "cat <<\\EOF\nit's\nEOF\njulia -e 'f(1)'",
    "cat <<< 'x'\njulia -e 'f(1)'",
)
MORE_LEFT_ALONE = (
    "julia",
    "julia --project=.",
    "julia x.sh",
    "julia -v",
    "julia -qv",
    "/usr/bin/time -l julia -e 'f(1)'",
    "julia -m Foo",
    "julia -m Foo x.jl",
    "julia --module Foo -e 1",
    "julia --project=. <<'EOF'\nusing Pkg; Pkg.test()\nEOF",
    "cat <<EOF > x.sh\njulia -e 'f(1)'\nEOF",
    "echo 'using BenchmarkTools' | julia",
    "julia -e 'f(1",
    "julia -L setup.jl --sysimage img.so -- test/runtests.jl",
    "julia +release probe.jl",
    "julia --version=1 -e 1",
    "env julia -e 1",
    "timeout 60 julia -e 1",
    "cat probe.jl",
    "echo -e 'f(1)'",
    "echo julia -e 1",
    "grep -rn 'julia -e 1' src",
    "julia --version -e 1",
    "julia -v probe.jl",
    "julia -p 'f(1)'",
    "julia --procs 'f(1)'",
    "julia -p 4",
    "julia --eval='using Pkg; Pkg.status()'",
    "julia -e'using Pkg; Pkg.status()'",
    "julia -e '@time f()'",
    "julia -e '@btime f()'",
    "julia -e '@benchmark f()'",
    "julia -e '@ballocated f()'",
    "julia -e '@elapsed f()'",
)
# Each option of `julia` that takes the next word as its value, with a value of its own form: the
# value in the next word is no script, so the code or the script after it is read. No value ends in
# `.jl`, so that the value read as a script gives no note.
SPACED_VALUES = (
    ("--sysimage", "img.so"),
    ("--home", "/x"),
    ("--load", "setup"),
    ("--threads", "4"),
    ("--procs", "2"),
    ("--machine-file", "hosts"),
    ("--cpu-target", "native"),
    ("--banner", "no"),
    ("--startup-file", "no"),
    ("--handle-signals", "yes"),
    ("--sysimage-native-code", "yes"),
    ("--compiled-modules", "no"),
    ("--pkgimages", "no"),
    ("--gcthreads", "2"),
    ("--color", "yes"),
    ("--history-file", "no"),
    ("--depwarn", "no"),
    ("--warn-overwrite", "no"),
    ("--warn-scope", "yes"),
    ("--inline", "yes"),
    ("--check-bounds", "yes"),
    ("--math-mode", "ieee"),
    ("--heap-size-hint", "1G"),
    ("--hard-heap-limit", "8G"),
    ("--heap-target-increment", "1G"),
    ("--compile", "yes"),
    ("--compress-sysimage", "no"),
    ("--output-incremental", "no"),
    ("--timeout-for-safepoint-straggler", "60"),
    ("--trace-compile", "stderr"),
    ("--trace-dispatch", "stderr"),
    ("--task-metrics", "no"),
    ("--permalloc-pkgimg", "no"),
    ("--output-o", "x.o"),
    ("--output-ji", "x.ji"),
    ("--output-bc", "x.bc"),
    ("--output-unopt-bc", "x.bc"),
    ("--output-asm", "x.s"),
    ("--bug-report", "rr"),
    ("--bind-to", "127.0.0.1"),
    ("-O", "3"),
    ("-g", "2"),
)
SPACED_PROBES = tuple(
    command
    for option, value in SPACED_VALUES
    for command in (f"julia {option} {value} -e 'f(1)'", f"julia {option} {value} probe.jl")
)
# A simple command after a reserved word or a pattern of `case`, in a group, or in a group that
# reads a pipe or a file.
RESERVED_PROBES = (
    "if true; then julia -e 'f(1)'; fi",
    "if julia -e 'f(1)'; then :; fi",
    "if false; then :; elif julia -e 'f(1)'; then :; fi",
    "if false; then :; else julia -e 'f(1)'; fi",
    "for f in a b; do julia -e 'f(1)'; done",
    "while julia -e 'f(1)'; do :; done",
    "until julia -e 'f(1)'; do :; done",
    "! julia -e 'f(1)'",
    "! A=1 julia -e 'f(1)'",
    "{ julia -e 'f(1)'; }",
    "! { julia -e 'f(1)'; }",
    "then { cd x; julia probe.jl; }",
    "echo 'f(1)' | (cd x; julia)",
    "echo 'f(1)' | { cd x; julia; }",
    "echo 'f(1)' | (cd x; (julia))",
    "{ cd x; julia; } < probe.jl",
    "(cd x; julia) 2>err.txt < probe.jl",
    "diff <(julia -e 'f(1)') x",
    "echo 'f(1)' | cat <(julia)",
    "echo 'f(1)' |(cd x; julia)",
    "case a in a) julia -e 'f(1)';; esac",
    "echo 'f(1)' | { case a in a) julia;; esac; }",
    "{ case a in a) julia;; esac; } < probe.jl",
)
# Calls that hold no probe when groups, reserved words and option values are read: a `julia` with
# no code and no `.jl` script that reads no pipe and no file, one after `time`, or a `julia` word
# that is no command name.
RESERVED_LEFT_ALONE = (
    "{ time julia x.jl; }",
    "! time julia x.jl",
    "echo then julia -e 1",
    "{julia -e 1;}",
    "(cd x; julia)",
    "{ cd x; julia; }",
    "echo 'f(1)' | (cd x); julia",
    "(echo 'f(1)') | cat; julia",
    "cat <(echo x) julia -e 1",
    "x=$(julia) && julia",
    "(cd x; julia); cat < probe.jl",
    "cat < probe.jl <(julia)",
    "julia --startup-file no",
    "julia --color yes x.sh",
    "julia -O 3",
)
NOT_BASH = json.dumps({"tool_name": "Read", "tool_input": {"command": "julia -e 1", "file_path": "/x"}})


def note_payload(command: object) -> str:
    """The payload of a Bash call whose `tool_input.command` is `command`."""
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def note_answer(data: bytes, cache: str = KAIMON_CACHE) -> tuple[str, str]:
    """('note', its text), ('silent', '') for exit 0 with no output, or what else `kaimon-note.py`
    did on the payload bytes `data` with the Kaimon cache `cache`. The hook reads its input as
    strict UTF-8, as under a UTF-8 locale, so a byte that is no UTF-8 raises in its read."""
    try:
        proc = subprocess.run(
            [sys.executable, KAIMON_NOTE],
            input=data,
            capture_output=True,
            env={**ENV, "KAIMON_CACHE_DIR": cache, "PYTHONIOENCODING": "utf-8"},
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    failed = f"exit {proc.returncode}" if proc.returncode else "stderr" if proc.stderr else ""
    if failed or not proc.stdout.strip():
        return failed or "silent", ""
    try:
        out = json_value(proc.stdout.decode("utf-8"), "the output")["hookSpecificOutput"]
        text = out["additionalContext"]
    except UnicodeDecodeError, ValueError, KeyError, TypeError:
        return "unreadable output", ""
    if out["hookEventName"] != "PreToolUse" or not isinstance(text, str):
        return "other output", ""
    return "note", text


def note_wrong(data: bytes, keys: tuple[str, ...] | None, cache: str = KAIMON_CACHE) -> str | None:
    """What is wrong with the hook's answer to `data` with the Kaimon cache `cache`, or None: with
    `keys` None, exit 0 and no output; else a note of at most three lines that names NOTED and the
    keys `keys` in sorted order, and no other gate of the fixture."""
    got, text = note_answer(data, cache)
    if keys is None:
        return None if got == "silent" else got
    if got != "note":
        return got
    listed = "The live sessions are " + ", ".join(f"`{key}`" for key in keys) + "." if keys else ""
    other = [g for g in (*LIVE_GATES, STALE_GATE, *UNREAD_GATES) if g not in keys and g in text]
    if text.count("\n") > 2 or not all(n in text for n in NOTED) or listed not in text or other:
        return f"note {text!r}"
    return None


def kaimon_note_cases():
    """The cases of `kaimon-note.py`: (number of cases, number wrong)."""
    probe = ("julia --startup-file=no --project=. -e 'using Foo; Foo.f(1)'",)

    def payloads(commands: tuple[str, ...]) -> list[bytes]:
        return [note_payload(command).encode("utf-8") for command in commands]

    cases: list[tuple[str, list[bytes], tuple[str, ...] | None, str]] = [
        ("a -e probe gets the note", payloads(probe), LIVE_GATES, KAIMON_CACHE),
        (
            "a probe file after cd and an assignment gets the note",
            payloads(("cd /x && JULIA_NUM_THREADS=2 julia --project=env probe.jl",)),
            LIVE_GATES,
            KAIMON_CACHE,
        ),
        ("the calls left alone get no note", payloads(LEFT_ALONE), None, KAIMON_CACHE),
        (
            "a mixed call gets the note",
            payloads(("julia +1.12 -e 1 && julia -e 'f(1)'",)),
            LIVE_GATES,
            KAIMON_CACHE,
        ),
        (
            "an unreadable payload passes in silence",
            [
                b"not json",
                b"{}",
                b'{"tool_name": "Bash", "tool_input": {}}',
                b'{"tool_name": "Bash", "tool_input": "julia -e 1"}',
                NOT_BASH.encode("utf-8"),
                note_payload(7).encode("utf-8"),
                json.dumps({"tool_input": {"command": probe[0]}}).encode("utf-8"),
                b"",
                b"[1]",
                b"\xff",
            ],
            None,
            KAIMON_CACHE,
        ),
        ("a note with no gate directory names no key", payloads(probe), (), NO_GATES),
        ("a note with an empty gate directory names no key", payloads(probe), (), EMPTY_GATES),
        ("more probe forms get the note", payloads(MORE_PROBES), LIVE_GATES, KAIMON_CACHE),
        ("more calls left alone get no note", payloads(MORE_LEFT_ALONE), None, KAIMON_CACHE),
        (
            "a probe with an option value in the next word gets the note",
            payloads(SPACED_PROBES),
            LIVE_GATES,
            KAIMON_CACHE,
        ),
        (
            "a probe after a reserved word or in a group gets the note",
            payloads(RESERVED_PROBES),
            LIVE_GATES,
            KAIMON_CACHE,
        ),
        (
            "a group or a reserved word gives no note of its own",
            payloads(RESERVED_LEFT_ALONE),
            None,
            KAIMON_CACHE,
        ),
    ]
    wrong = 0
    for label, data, keys, cache in cases:
        bad = [(d, w) for d in data if (w := note_wrong(d, keys, cache)) is not None]
        wrong += bool(bad)
        mark = "BAD" if bad else "ok "
        got = "; ".join(f"{d[:80]!r}: {w}" for d, w in bad) or "as expected"
        print(f"{mark} {label}  [kaimon-no]  {got}")
    # A gate directory with no gate says that no session is live; one that cannot be listed says
    # nothing of the sessions.
    for label, cache, expected in (
        ("an empty gate directory is named as one", EMPTY_GATES, True),
        ("no gate directory gives no claim of the sessions", NO_GATES, False),
    ):
        _, text = note_answer(note_payload(probe[0]).encode("utf-8"), cache)
        right = bool(text) and ("No session is live." in text) == expected
        wrong += not right
        print(f"{'ok ' if right else 'BAD'} {label}  [kaimon-no]  {text[:60]!r}")
    return len(cases) + 2, wrong


# `registry-copies.py` warns after a Bash call that runs Julia when the registries directory of the
# first depot holds more than one `General.tar.*` file, or when `General.toml` names no newest one.
# Each depot of the fixture holds `registries/` with the files of REGISTRY_DEPOTS, each with its age
# in seconds, and `General.toml` naming the file `path`; a depot of None has no `registries/`.
REGISTRY_COPIES = HOOKS + "registry-copies.py"
REGISTRY_DEPOTS: dict[str, tuple[dict[str, int], str] | None] = {
    "one": ({"General.tar.zst": 60}, "General.tar.zst"),
    "newest": ({"General.tar.gz": 3600, "General.tar.zst": 60}, "General.tar.zst"),
    "older": ({"General.tar.gz": 60, "General.tar.zst": 3600}, "General.tar.zst"),
    "missing": ({"General.tar.zst": 60}, "General.tar.gz"),
    "none": None,
}


def registry_depot(name: str) -> str:
    """The path of the fixture depot `name` of REGISTRY_DEPOTS, written on first use."""
    depot = pathlib.Path(FIXTURE.name, f"depot-{name}")
    spec = REGISTRY_DEPOTS[name]
    if not depot.exists():
        depot.mkdir()
        if spec is not None:
            registries = depot / "registries"
            registries.mkdir()
            now = time.time()
            for file, age in spec[0].items():
                (registries / file).write_bytes(b"")
                os.utime(registries / file, (now - age, now - age))
            (registries / "General.toml").write_text(f'path = "{spec[1]}"\n', encoding="utf-8")
    return str(depot)


def registry_answer(data: bytes, depot: str | None) -> tuple[str, str]:
    """('warn', its text), ('silent', '') for exit 0 with no output, or what else
    `registry-copies.py` did on the payload bytes `data` with JULIA_DEPOT_PATH `depot`, or with
    none set when `depot` is None."""
    env = {k: v for k, v in ENV.items() if k != "JULIA_DEPOT_PATH"}
    if depot is not None:
        env["JULIA_DEPOT_PATH"] = depot + os.pathsep
    try:
        proc = subprocess.run(
            [sys.executable, REGISTRY_COPIES],
            input=data,
            capture_output=True,
            env={**env, "PYTHONIOENCODING": "utf-8"},
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    failed = f"exit {proc.returncode}" if proc.returncode else "stderr" if proc.stderr else ""
    if failed or not proc.stdout.strip():
        return failed or "silent", ""
    try:
        out = json_value(proc.stdout.decode("utf-8"), "the output")["hookSpecificOutput"]
        text = out["additionalContext"]
    except UnicodeDecodeError, ValueError, KeyError, TypeError:
        return "unreadable output", ""
    if out["hookEventName"] != "PostToolUse" or not isinstance(text, str):
        return "other output", ""
    return "warn", text


def registry_cases():
    """The cases of `registry-copies.py`: (number of cases, number wrong)."""
    julia = note_payload("julia --project=. -e 'using Foo'").encode("utf-8")
    remedy = ("Pkg.Registry.update()", "delete the copy that `General.toml` does not name")
    # A case: label, payloads, depot name (None: JULIA_DEPOT_PATH unset, the fixture HOME has no
    # depot), and the texts that the warning holds, or None for no output.
    cases: list[tuple[str, list[bytes], str | None, tuple[str, ...] | None]] = [
        ("one copy that General.toml names gives no warning", [julia], "one", None),
        (
            "two copies, General.toml naming the newest, give a warning",
            [julia],
            "newest",
            (
                "`General.tar.gz` (modified",
                "`General.tar.zst` (modified",
                "names `General.tar.zst`, the newest",
                *remedy,
            ),
        ),
        (
            "two copies, General.toml naming the older, give a warning",
            [julia],
            "older",
            (
                "`General.tar.gz` (modified",
                "`General.tar.zst` (modified",
                "Pkg reads the older copy",
                *remedy,
            ),
        ),
        (
            "a General.toml that names a missing file gives a warning",
            [julia],
            "missing",
            ("names `General.tar.gz`, which is missing", *remedy),
        ),
        ("no registries directory gives no warning", [julia], "none", None),
        ("no depot below HOME gives no warning", [julia], None, None),
        (
            "more calls that run Julia give a warning",
            [
                note_payload(c).encode("utf-8")
                for c in (
                    "juliaup update",
                    "cd x && A=1 ~/.juliaup/bin/julia +1.13 x.jl",
                    "(cd x; julia -e 1) 2>&1",
                    "if true; then julia -e 1; fi",
                    "echo 1 | julia",
                    "echo $(julia -e 1)",
                    "> out julia -e 1",
                )
            ],
            "newest",
            remedy,
        ),
        (
            "a call that runs no Julia gives no warning",
            [
                note_payload(c).encode("utf-8")
                for c in (
                    "ls",
                    "grep -rn julia src",
                    'echo "julia -e 1"',
                    "cat x > julia",
                    "> julia ls",
                    "ls &> julia",
                    "echo 'julia",
                )
            ],
            "older",
            None,
        ),
        (
            "an unreadable payload gives no warning",
            [
                b"not json",
                b"{}",
                b"",
                b"[1]",
                b"\xff",
                b'{"tool_name": "Bash", "tool_input": "julia -e 1"}',
                note_payload(7).encode("utf-8"),
                NOT_BASH.encode("utf-8"),
            ],
            "older",
            None,
        ),
    ]
    wrong = 0
    for label, data, depot, texts in cases:
        path = None if depot is None else registry_depot(depot)
        bad: list[tuple[bytes, str]] = []
        for d in data:
            got, text = registry_answer(d, path)
            right = got == "silent" if texts is None else got == "warn" and all(t in text for t in texts)
            if not right:
                bad.append((d, f"{got} {text!r}"))
        wrong += bool(bad)
        mark = "BAD" if bad else "ok "
        got = "; ".join(f"{d[:80]!r}: {w}" for d, w in bad) or "as expected"
        print(f"{mark} {label}  [registry ]  {got}")
    return len(cases), wrong


# The groups of cases, in the order of a run of every group; each returns (number of cases, number
# wrong). `harness test` runs each group as the part `probe:<group>`.
GROUPS = {
    "commands": command_cases,
    "payloads": payload_cases,
    "manifest": manifest_cases,
    "drift": drift_cases,
    "omp": omp_cases,
    "opencode": oc_cases,
    "antigravity": agy_cases,
    "kaimon-note": kaimon_note_cases,
    "registry-copies": registry_cases,
}


if __name__ == "__main__":
    sys.exit(main())
