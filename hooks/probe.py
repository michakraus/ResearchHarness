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
with its shebang, and each call has a timeout.
"""

import ast
import contextlib
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
import subprocess
import sys
import tempfile
import time
import types
from dataclasses import replace
from typing import Any, NamedTuple, TextIO, cast

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
# fixture's git commands and the hooks' to the caller's repository.
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV = {**CLEAN, "HOME": HOME}
q = shlex.quote  # a fixture path spliced into a command, for a `$TMPDIR` with a space
TIMEOUT = 30  # seconds per hook call; a timeout is a wrong case
MIB = 1024 * 1024  # bytes: the largest command that the guard decides by its checks
MIB_LIMIT = 10  # seconds: the bound within which the guard decides a command of 1 MiB
# stat and lstat calls of a payload beside those for the distinct names of its words: the walk of
# its working directory, the roots of the checks, the `.git` above a write. 62 for the first two
# counted `cd` payloads, 180 for the third and at most 74 for the payloads that resolve operands and
# `git init` targets, on macOS with the fixture below `/tmp/<one name>/`; the margin holds a fixture
# below a deeper `$TMPDIR`. Also the bound of the steps of a walk beside those of the distinct names.
WALK_READS = 400

WORKTREE = HOOKS + "worktree.py"

# The guard package, run as the settings template runs it, on the differential corpus that holds
# the cases of the guard scripts whose checks it holds. Each record is one JSON object per line:
# `stdin` (an object, sent as its JSON text, or a string, sent as it is) and `decision`, the guard's
# expected decision; a placeholder `@@<NAME>@@` in a string stands for the fixture's value of NAME.
# A record with `"frontend": "antigravity"` is an Antigravity call instead: `tool`, `args`, an
# optional `workspace`, Antigravity's `decision` and the `bypass` of its `overwrite`, and `differs`,
# the reason, where the removed Antigravity hook answered otherwise; `@@AGYHOME@@` stands for the
# fixture home of the Antigravity cases.
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

# `worktree.py` is not a `PreToolUse` hook: it fails closed, so every case here expects 1.
# Creation needs an unsandboxed git and is probed by `EnterWorktree`, not here.
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
# link; and `.ssh/`, `.omp/`, `Research/P/.git/` and `bin/`. The groups `omp` and `opencode` run each
# record of their frontend in `tests/guard/corpus.jsonl` through the extension or the plugin and the
# guard, and the edges of the transport that a record cannot hold: an interpreter that is missing, a
# guard that exits 3 after its answer, prints `{`, is killed after its answer or does not answer in
# time, a path list that is missing, malformed or without `python`, and a message that the guard
# cannot read. The timeout case runs a copy whose timeout is 0.3 s, so that it costs no 10 s.
#
# An oh-my-pi record holds `tool`, `input`, the `decision` and, where it needs them, `cwd`, the
# session's working directory (CWD by default), and `agent`, the kind of the context's agent. An
# OpenCode record holds `tool`, `input`, the `decision` and, where it needs them, `directory`, the
# session's directory (CWD by default; "" for a context with no `location`), `process_cwd`, the
# working directory of `node`, and `local`, the list in `$OPENCODE_CONFIG_DIR/guard-paths.json`.
# `covers` names the functions of the removed path guards that a record exercised, and `differs`
# why the guard decides otherwise than they did. `@@OMPHOME@@` and `@@OCHOME@@` stand for the two
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
# for oh-my-pi on the simple commands below and is no evidence for a compound one. `gh pr create`
# runs unasked only with `-R` or `--repo` first, on an organisation of the profile; with the
# repository later, elsewhere, or not named at all, it asks.
OMP_PATTERNS = [
    ("git push --force origin x", "deny"),
    ("sed -i s/a/b/ f", "deny"),
    ("cat ~/.local/share/opencode/auth.json", "allow"),
    ("git status", "allow"),
    ("ls -la", "allow"),
    ("gh pr create --repo example-org/X.jl --title T --body-file b.md", "allow"),
    ("gh pr create -R example-user/X.jl --title T", "allow"),
    ("gh pr create --title T --repo example-org/X.jl", "prompt"),
    ("gh pr create --repo other/X.jl --title T", "prompt"),
    ("gh pr create --title T --body-file b.md", "prompt"),
    ("gh pr create", "prompt"),
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
    listed = cast("dict[str, object]", json.loads(text))
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
    for directory in (layout, ".ssh", ".omp", "Research/P/.git", "bin"):
        (home / directory).mkdir(parents=True)
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
    home: str, tool: str, data: object, *, cwd: str = CWD, mode: str = "", path: str | None = None
) -> PluginReply:
    """The extension's answer in the home `home` to one event of `tool` with the input `data`, in the
    working directory `cwd`, the driver in the mode `mode`; `path`, the `PATH` of `node`."""
    node = shutil.which("node") or "node"
    event = json.dumps({"type": "tool_call", "toolCallId": "probe", "toolName": tool, "input": data})
    env = {**CLEAN, "HOME": home}
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
    scripts that run the guard and exit 3, print `{`, run the guard and are killed, or answer late."""
    fakes = pathlib.Path(FIXTURE.name, f"fakes-{frontend}")
    fakes.mkdir()
    python = shlex.quote(sys.executable)
    texts = {
        "the guard exits 3 after its answer": f'#!/bin/sh\n{python} "$@"\nexit 3\n',
        "the guard prints {": "#!/bin/sh\ncat > /dev/null\necho '{'\n",
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


# The text of the reason of each transport case.
TRANSPORT_WANTS = {
    "the interpreter is missing": "could not start",
    "the guard exits 3 after its answer": "exited with status 3",
    "the guard prints {": "printed no valid answer",
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
        patterns = json.loads("".join(l for l in config.splitlines(keepends=True) if not l.startswith("#")))
        patterns = patterns["bash"]["patterns"]
        good = plugin_home("omp", "omp-home")
        homes = transport_homes("omp")
    # The adapter, the profile and the rendering fail with HarnessError, an input of an unexpected
    # shape with the others; the case reports it as wrong, and the probe goes on to its summary.
    except (ImportError, OSError, ValueError, LookupError, TypeError, AttributeError, RuntimeError) as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [omp-guard]  {e}")
        return report.total, report.wrong
    for record in plugin_records("omp"):
        cwd = str(record.get("cwd", CWD))
        got = omp_reply(good, record["tool"], record["input"], cwd=cwd, mode=str(record.get("agent", "")))
        report(
            ok=got.decision == record["decision"],
            line=f"exp {record['decision']} got {got.decision}  [omp-guard]  {record['tool']} "
            f"{json.dumps(record['input'])[:160]} in {cwd} {record.get('agent', '')}",
        )
    for command, expected in OMP_PATTERNS:
        got = omp_pattern(command, patterns)
        report(ok=got == expected, line=f"exp {expected} got {got}  [omp-patts]  {command}")
    status = {"command": "git status"}
    for label, (home, want) in homes.items():
        calls = [
            ("bash", status),
            *([("read", {"path": "src/Foo.jl"})] if label == "the path list is missing" else []),
        ]
        for tool, data in calls:
            got = omp_reply(home, tool, data)
            report(
                ok=got.decision == "deny" and want in got.reason,
                line=f"exp deny, {want!r} got {got.decision}  [omp-guard]  fail-closed, {label}: {tool} {data}: "
                f"{got.seconds:.2f} seconds",
            )
    got = omp_reply(good, "bash", status, mode="throw")
    report(
        ok=got.decision == "deny" and "failed" in got.reason,
        line=f"exp deny got {got}  [omp-guard]  the handler throws",
    )
    # The extension runs the interpreter that the list names, never `python3` from the PATH.
    got = omp_reply(good, "bash", status, path="/nonexistent")
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
    return report.total, report.wrong


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
    ) -> Any:
        """The driver's answer for one event, or the text of what went wrong. `cwd` is the
        session's directory, `ctx.location.directory`, or "" for a context with no `location`;
        `process_cwd`, the working directory of the `node` process, or None for this one's; `path`,
        the `PATH` of the `node` process, or None for this one's; `config_dir`, its
        `OPENCODE_CONFIG_DIR`, or None for none."""
        env = {k: v for k, v in CLEAN.items() if k != "OPENCODE_CONFIG_DIR"}
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
            return json.loads(p.stdout)
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
        fail = {
            "rtk exits 1": plugin_home(
                "opencode", "oc-rtk-1", rtk='#!/bin/sh\necho "rtk git status"\nexit 1\n'
            ),
            "no rtk": plugin_home("opencode", "oc-rtk-none"),
        }
        homes = transport_homes("opencode")
    # The profile and the rendering fail with HarnessError, an input of an unexpected shape with the
    # others; the case reports it as wrong, and the probe goes on to its summary.
    except (ImportError, OSError, ValueError, LookupError, TypeError, AttributeError, RuntimeError) as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [oc-plugin]  {e}")
        return report.total, report.wrong

    def reply(
        home: str,
        event: object,
        directory: str = CWD,
        *,
        process_cwd: str | None = None,
        config_dir: str | None = None,
        path: str | None = None,
    ) -> PluginReply:
        """The guard plugin's answer in the home `home` to one event, with the options of `drive`."""
        start = time.monotonic()
        answer = drive(
            home, "guards", event, cwd=directory, process_cwd=process_cwd, config_dir=config_dir, path=path
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
        got = reply(good, event, directory, process_cwd=record.get("process_cwd"), config_dir=config_dir)
        report(
            ok=got.decision == record["decision"],
            line=f"exp {record['decision']} got {got.decision}  [oc-guards]  {record['tool']} "
            f"{json.dumps(record['input'])[:160]} in {directory or record.get('process_cwd')}"
            + (f" with the local list {record['local']}" if "local" in record else ""),
        )

    # It fails closed: each refuses `git status`, and a missing list a read too, with a reason that
    # names the plugin and the cause.
    status = oc_event("git status")
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
                line=f"exp deny, {want!r} got {got.decision}  [oc-guards]  fail-closed, {label}: {event['tool']}: "
                f"{got.seconds:.2f} seconds",
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

    # A local list in `$OPENCODE_CONFIG_DIR` that is no JSON refuses every call, as one that holds
    # no list of strings does (a record).
    local = pathlib.Path(FIXTURE.name, "oc-local", "broken")
    local.mkdir(parents=True)
    (local / "guard-paths.json").write_text('{"allow": [', encoding="utf-8")
    got = reply(good, status, config_dir=str(local))
    report(
        ok=got.decision == "deny",
        line=f"exp deny got {got.decision}  [oc-guards]  a local list that is no JSON",
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
        value: object = json.loads(text)
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


def agy_reply(home: str, payload: str, *, limit: float = TIMEOUT) -> AgyReply:
    """The guard's answer to `payload`, run as `hooks.json` runs it from the fixture home `home`
    within `limit` seconds."""
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
            env={**CLEAN, "HOME": "/" + home},
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
        got = agy_reply(home, agy_payload(record["tool"], record["args"], str(workspace)))
        bypass = bypass_of(got.overwrite)
        reasoned = (got.reason is None) if got.decision == "ask" else bool(got.reason and got.reason.strip())
        want = (record["decision"], record["bypass"])
        report(
            ok=(got.decision, bypass) == want and reasoned,
            line=f"exp {want} got {(got.decision, bypass)}, reason {got.reason is not None}  [agy-guard]  "
            f"{record['tool']} {json.dumps(record['args'])[:160]}"
            + (f" in {workspace}" if "workspace" in record else ""),
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
    rendered list and that no rule matches, then distinct segments: the guard asks within MIB_LIMIT,
    and each rule meets only the word lists that hold all its needed texts, so the matcher calls are
    at most those (rule, word list) pairs."""
    sys.path.insert(0, HOOKS)
    try:
        path_list: Any = importlib.import_module("guard.path_list")
    finally:
        sys.path.remove(HOOKS)
    config = pathlib.Path(home, ".gemini", "config")
    lists = cast(
        "dict[str, list[str]]", json.loads((config / "guard-paths.json").read_text(encoding="utf-8"))
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
            timeout=MIB_LIMIT,
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
        ok=got == "ask" and 0 <= calls <= indexed and seconds <= MIB_LIMIT,
        line=f"exp ask, at most {indexed} matcher calls got {got}  [mib-rules]  {len(needs)} rules, {shape}: "
        f"matcher calls {calls}, {seconds:.2f} seconds, within {MIB_LIMIT} s",
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
    # The adapters, the profile and the rendering fail with HarnessError, an input of an unexpected
    # shape with the others; the case reports it as wrong, and the probe goes on to its summary.
    except (harness_error, ImportError, OSError, ValueError, LookupError, TypeError, AttributeError) as e:
        report(ok=False, line=f"exp fixture got {type(e).__name__}  [agy-guard]  {e}")
        return report.total, report.wrong
    agy_record_cases(report, home)
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


def run(script, payload):
    proc = call(script, payload)
    return "timeout" if proc is None else proc.returncode


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
        return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
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
            )
    pathlib.Path(DEEP).mkdir(parents=True)
    pathlib.Path(OUTSIDE).mkdir(parents=True)
    pathlib.Path(DANGLING).mkdir()
    pathlib.Path(DANGLING, ".git").symlink_to("missing")
    pathlib.Path(LOGS, "a").mkdir()
    pathlib.Path(LOGS, "loop").symlink_to("loop")
    pathlib.Path(LOGS, ".gitignore").write_text("*.log\n", encoding="utf-8")
    git = shutil.which("git") or "git"
    subprocess.run([git, "init", "-q", LOGS], env=git_env, check=True, capture_output=True)
    os.symlink("/", LINK)
    # A link in a scratch zone to a guarded directory: a recursive `rm` of the link removes the link,
    # and of the link with a trailing `/` the directory.
    pathlib.Path(SCRATCH, "link-out").symlink_to("/")


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
        out = json.loads(proc.stdout)
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
        handlers = [h for hook in json.load(f).values() for h in hook.get("SessionStart", [])]
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
        out = json.loads(p.stdout)
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
            return json.load(f)

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


def guard_run(data: bytes, frontend: str = "claude", limit: float = TIMEOUT) -> tuple[str, str]:
    """The guard's decision on the payload bytes `data`, run as the settings template runs it but from
    the fixture's directory, and its stdout and stderr: `deny` for exit 2, the `permissionDecision` of
    stdout for exit 0, `pass` for exit 0 with no output, `exit <n>` or `timeout` after `limit` seconds."""
    try:
        proc = subprocess.run(
            [sys.executable, GUARD, "--from", frontend],
            input=data,
            capture_output=True,
            env=ENV,
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
        return str(json.loads(stdout)["hookSpecificOutput"]["permissionDecision"]), output
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
    """The guard's decision on the payload bytes `data`, `deny`, `pass`, `exit <n>` or `timeout`, and
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
    if proc.returncode != 0 or proc.stdout.strip():
        return f"exit {proc.returncode} {proc.stdout[:80]!r}", stats, spawns, steps
    return "pass", stats, spawns, steps


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


def corpus_records() -> list[tuple[str, str]]:
    """(payload text, expected decision) of each Claude Code record of the corpus, its placeholders
    replaced by the fixture's values; a record with a `frontend` is another frontend's."""
    records: list[tuple[str, str]] = []
    for placed in corpus_lines({}):
        record = json.loads(placed)
        if "frontend" in record:
            continue
        stdin = record["stdin"]
        records.append((stdin if isinstance(stdin, str) else json.dumps(stdin), str(record["decision"])))
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
# at import, and the one path of a directory or worktree call, which holds no shell command.
READS_ALLOWED = frozenset(
    {
        ("__main__.py", "Path(__file__).resolve()"),
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


def guard_entry(missing: str) -> tuple[list[str], str]:
    """The commands of the `Bash` group of the settings template as the Claude Code adapter renders them
    with the dummy profile, a home `missing` and this interpreter, and the guard's command among them."""
    sys.path.insert(0, REPO + "/lib")
    frontends = importlib.import_module("harness.frontends")
    profile = importlib.import_module("harness.profile")
    dummy = replace(profile.load(REPO + "/examples/profile.toml"), home=missing)
    cfg = frontends.adapter("claude").settings_template(
        dummy, FIXTURE.name + "/no-network.toml", sys.executable
    )
    group = next(g for g in cfg["hooks"]["PreToolUse"] if g.get("matcher") == "Bash")
    guard = shlex.join([sys.executable, missing + "/.claude/hooks/guard", "--from", "claude"]) + " || exit 2"
    return [str(h["command"]) for h in group["hooks"]], guard


def command_cases():
    """The guard on each record of the corpus, and on the edges that a line of it cannot hold."""
    wrong = 0
    total = 0

    def report(*, ok: bool, line: str) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    for stdin, expected in corpus_records():
        got, _ = guard_run(stdin.encode("utf-8"))
        report(ok=got == expected, line=f"exp {expected} got {got}  [guard    ]  {stdin[:200]!r}")

    for size, expected in ((MIB, "pass"), (MIB + 1, "deny")):
        payload = {"tool_name": "Bash", "tool_input": {"command": "echo " + "a" * (size - 5)}, "cwd": CWD}
        got, output = guard_run(json.dumps(payload).encode("utf-8"))
        ok = got == expected and (expected == "pass" or "more than" in output)
        report(ok=ok, line=f"exp {expected} got {got}  [guard    ]  a command of {size} bytes")
    # Commands of 1 MiB whose words each check walks: a chain of `cd`, through a link too, one `cd`
    # word of many names, a repeated `cd` to a deep directory, many operands of a recursive `rm`, four
    # readings, loop words with no `do` or `done`, many distinct writes that git ignores. Each is
    # decided within MIB_LIMIT, and its line gives the seconds.
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
        (SCRATCH, mib_command("cd a; rm -rf x; ", "true"), "pass"),
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
        got, _ = guard_run(json.dumps(payload).encode("utf-8"), limit=MIB_LIMIT)
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
    for cwd, starts, stepped, (command, shape) in (
        (LOGS, 2, True, mib_command("d{}/../", four, "cd ")),
        (LOGS, 2, False, mib_command("a/../", four, "cd ")),
        (LOGS, 3, False, mib_command(f"cd d{{}}; cd {DEEP}; ", four.removeprefix("; "))),
    ):
        words = re.findall(r"(?:^|; )cd (\S+)", command)
        names = len({name for word in words for name in word.split("/") if name not in ("", "..")})
        got, stats, spawns, steps = guard_counted(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}).encode("utf-8")
        )
        bound = f"at most {starts} x {names} + {WALK_READS} reads" + (" and steps" if stepped else "")
        ok = got == "pass" and 0 <= stats <= starts * names + WALK_READS
        report(
            ok=ok and (not stepped or 0 <= steps <= starts * names + WALK_READS),
            line=f"exp pass, {bound} got {got}, {stats} reads, {steps} steps  [guard    ]  {shape}",
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
        commands, guard = guard_entry(FIXTURE.name + "/missing-home")
    except (ImportError, OSError, ValueError, LookupError, TypeError) as e:
        report(ok=False, line=f"exp render got {type(e).__name__}  [guard    ]  {e}")
        return total, wrong
    report(
        ok=commands == ["rtk hook claude", guard],
        line=f"exp rtk and guard got {commands}  [guard    ]  the rendered Bash group",
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


def payload_cases():
    """The other hooks on their payloads."""
    wrong = 0
    total = 0
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
    for payload in WORKTREE_CASES:
        got = run(WORKTREE, payload)
        total += 1
        wrong += got != 1
        mark = "ok " if got == 1 else "BAD"
        print(f"{mark} exp 1 got {got}  [worktree ]  fail-closed: {payload!r}")
    return total, wrong


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
}


if __name__ == "__main__":
    sys.exit(main())
