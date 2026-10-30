#!/usr/bin/env python3
"""Run the case battery for the hooks in this directory, one subprocess call per case.

Each case is checked on its own and printed on its own line, so a passing total cannot
hide a case that went the wrong way. Exit status is 1 when any case is wrong.

    ./probe.py [GROUP ...]

With no argument it runs every group of GROUPS; with names, only those groups. Each run
builds its own fixture.

A case gives a hook a payload and compares its answer: exit 2 refuses the call, exit 0
lets it through or answers with a JSON decision. The group `commands` runs the guard
package on each record of `tests/guard/corpus.jsonl` and on its edges; the guard fails
closed, so a payload it cannot read is refused.

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
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Literal, TextIO, TypedDict, Unpack, cast

HOOKS = os.path.dirname(os.path.abspath(__file__)) + "/"

# The fixture: one temporary directory per run, removed on exit, also after a failure. The
# hooks get it as `HOME` with exactly two leading slashes. `no-shell-file-write.py` exempts
# every path whose text begins with `/tmp/`, `/var/folders/` or `$TMPDIR` as a scratch root,
# and so a fixture `HOME` spelt there with one slash; `os.path.normpath` keeps a leading `//`,
# so the hook sees the fixture `HOME` as it sees a real one. macOS and Linux resolve `//` as `/`.
# `HOME` is one level below the temporary directory, so its parent is that directory and never
# `/tmp` itself, which holds the scratch paths of the `rm-scope` cases.
FIXTURE = tempfile.TemporaryDirectory(prefix="harness-probe-")
HOME = "/" + FIXTURE.name + "/home"
R = HOME + "/Research"
WT = R + "/.worktrees/Foo-bar"
PKG = R + "/Packages/Example"
# The working directory of the cases: a git work tree of the fixture, whose `.gitignore` ignores
# `__pycache__/`, never this checkout. A checkout below `/tmp/` or `$TMPDIR` is scratch to
# `no-shell-file-write.py`, which would then let every write of the cases through.
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

# oh-my-pi's guard extension, `adapters/omp/guards.ts`, runs under `node` with a stub of its
# extension API: the driver hands its `tool_call` handler one event, and the case reads the answer,
# "block" or "pass". The extension is copied into the fixture as `guards.mjs`, so that a `node`
# with no TypeScript support loads it too; `guards.ts` therefore holds JavaScript syntax only. Its
# guard scripts are the seven of `OC_SCRIPTS`, linked into the fixture's `~/.claude/hooks/`, and
# its path list is the one `harness install` writes, `omp.guard_paths`, rendered with the dummy
# profile and the fixture's home. A case runs in the probe's work tree, in the fixture home `~`, or
# in `~/Research` below it, so that a relative path reaches the home. A fail-closed case gets a
# fixture home of its own, with one guard script replaced or the path list changed; the timeout
# case runs a copy of the extension whose timeout is 0.3 s, so that it costs no 10 s.
#
# A bash case also gives the verdict of `harness.yml`'s `bash.patterns`, rendered with the dummy
# profile, by oh-my-pi's matching (`src/tools/bash.ts` at v18.6.1): the first rule that matches
# wins; `allow` matches only a whole command with no shell control character; `deny` and `prompt`
# match the whole command or one of its segments. This port splits segments by text, so it stands
# for oh-my-pi on the simple commands below and is no evidence for a compound one.
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
# (tool, input, the extension's verdict, the patterns' verdict for a bash command)
OMP_CASES = [
    ("bash", {"command": "git push --force origin x"}, "pass", "deny"),
    ("bash", {"command": "sed -i s/a/b/ f"}, "block", "deny"),
    ("bash", {"command": "cat ~/.local/share/opencode/auth.json"}, "block", "allow"),
    ("bash", {"command": "git status"}, "pass", "allow"),
    ("bash", {"command": "ls -la", "cwd": "~/.ssh"}, "block", "allow"),
    ("read", {"path": "~/.local/share/opencode/auth.json"}, "block", None),
    ("read", {"path": "~/.local/share/opencode/auth.json:1-5"}, "block", None),
    ("read", {"path": "@~/.ssh/id_ed25519"}, "block", None),
    ("read", {"path": "file://" + OMP_HOME + "/.netrc"}, "block", None),
    ("read", {"path": "src/Foo.jl"}, "pass", None),
    ("grep", {"pattern": "token", "path": "~/.local/share/opencode"}, "block", None),
    ("grep", {"pattern": "token", "path": "~"}, "block", None),
    ("grep", {"pattern": "token", "path": "src,~/.ssh"}, "block", None),
    ("grep", {"pattern": "token", "path": "src"}, "pass", None),
    ("write", {"path": "notes.md", "content": "x"}, "pass", None),
    # gh-api-writes.py answers exit 0 with an "ask" decision, which the extension turns into a block.
    ("bash", {"command": "gh api -X POST repos/a/b/issues"}, "block", None),
    # `gh pr create` runs unasked only with `-R` or `--repo` first, on an organisation of the
    # profile; with the repository later, elsewhere, or not named at all, it asks.
    ("bash", {"command": "gh pr create --repo example-org/X.jl --title T --body-file b.md"}, "pass", "allow"),
    ("bash", {"command": "gh pr create -R example-user/X.jl --title T"}, "pass", "allow"),
    ("bash", {"command": "gh pr create --title T --repo example-org/X.jl"}, "pass", "prompt"),
    ("bash", {"command": "gh pr create --repo other/X.jl --title T"}, "pass", "prompt"),
    ("bash", {"command": "gh pr create --title T --body-file b.md"}, "pass", "prompt"),
    ("bash", {"command": "gh pr create"}, "pass", "prompt"),
]
# (tool, input, the session's working directory, the extension's verdict): "tree" is the probe's
# work tree, "~" the fixture home, "~/Research" a directory below it.
OMP_PATH_CASES = [
    # A relative path of a bash command, and a relative `cwd`, resolve against the working directory.
    ("bash", {"command": "cat ../.local/share/opencode/auth.json"}, "~/Research", "block"),
    ("bash", {"command": "cat ../.netrc"}, "~/Research", "block"),
    ("bash", {"command": "cat .local/share/opencode/auth.json"}, "~", "block"),
    ("bash", {"command": "cat .ssh/id_ed25519"}, "~", "block"),
    ("bash", {"command": "cat id_ed25519", "cwd": ".ssh"}, "~", "block"),
    ("bash", {"command": "ls -la", "cwd": "../.ssh"}, "~/Research", "block"),
    ("bash", {"command": "ls"}, "~/.ssh", "block"),
    # A command that recurses, with no path, reaches below its working directory, which holds ~/.ssh.
    ("bash", {"command": "grep -r token", "cwd": "~"}, "tree", "block"),
    ("bash", {"command": "find -name x"}, "~", "block"),
    ("bash", {"command": "cat .env"}, "tree", "block"),
    ("bash", {"command": "cat config/.env.local"}, "tree", "block"),
    ("bash", {"command": "cat secrets/token"}, "tree", "block"),
    ("bash", {"command": "cat deploy.pem"}, "tree", "block"),
    ("bash", {"command": "cat tls.key"}, "tree", "block"),
    ("bash", {"command": "cat <.env"}, "tree", "block"),
    ("bash", {"command": "cat --file=../.netrc"}, "~/Research", "block"),
    # A `cd` with no directory, or with `-`, moves home; a `cd` reaches below each of its arguments.
    ("bash", {"command": "cd && cat .netrc"}, "~/Research", "block"),
    ("bash", {"command": "(cd && cat .local/share/opencode/auth.json)"}, "~/Research", "block"),
    ("bash", {"command": "cd - && cat .netrc"}, "~/Research", "block"),
    ("bash", {"command": "pushd; cat .netrc"}, "~/Research", "block"),
    ("bash", {"command": "cd -P .. && cat .netrc"}, "~/Research", "block"),
    # A brace expansion: the shell expands `{~/.netrc,x}` to `~/.netrc x`.
    ("bash", {"command": "cat {~/.netrc,x}"}, "tree", "block"),
    # Shell quotes are removed before the match, and the match ignores case (APFS does).
    ("bash", {"command": "cat ~/'.netrc'"}, "tree", "block"),
    ("bash", {"command": 'cat "$HOME/.netrc"'}, "tree", "block"),
    ("bash", {"command": "cat ~/.local/share/OpenCode/auth.json"}, "tree", "block"),
    ("read", {"path": "~/.SSH/config"}, "tree", "block"),
    # oh-my-pi's own directory, its credential store included.
    ("read", {"path": "~/.omp/agent/agent.db"}, "tree", "block"),
    ("bash", {"command": "cat ~/.omp/agent/agent.db"}, "tree", "block"),
    ("bash", {"command": "cat agent/agent.db"}, "~/.omp", "block"),
    ("grep", {"pattern": "token", "path": "~/.omp/agent"}, "tree", "block"),
    ("read", {"path": "~/.omp/agent/skillsx/a.md"}, "tree", "block"),
    ("read", {"path": "~/.omp/agent/hooks/rm-scope.py"}, "tree", "block"),
    # The copies of the skills, the rules and the instructions are readable; they are not editable.
    ("read", {"path": "~/.omp/agent/skills/build-part/edges.md"}, "tree", "pass"),
    ("read", {"path": "~/.omp/agent/rules/julia-code.md"}, "tree", "pass"),
    ("read", {"path": "~/.omp/agent/instructions/core.md"}, "tree", "pass"),
    ("read", {"path": "~/.omp/agent/RTK.md"}, "tree", "pass"),
    ("bash", {"command": "cat ~/.omp/agent/skills/build-part/SKILL.md"}, "tree", "pass"),
    ("grep", {"pattern": "x", "path": "~/.omp/agent/skills"}, "tree", "pass"),
    (
        "edit",
        {"path": "~/.omp/agent/skills/build-part/edges.md", "old_string": "a", "new_string": "b"},
        "tree",
        "block",
    ),
    ("write", {"path": "~/.omp/agent/rules/julia-code.md", "content": "x"}, "tree", "block"),
    # Commands that name no denied path still run.
    ("bash", {"command": "cat src/Foo.jl"}, "tree", "pass"),
    ("bash", {"command": "ls -la"}, "tree", "pass"),
    ("bash", {"command": "cd src && ls"}, "tree", "pass"),
    ("bash", {"command": "grep -rn token src"}, "tree", "pass"),
    ("bash", {"command": "git status"}, "~/Research", "pass"),
    ("bash", {"command": 'git commit -m "the .key rules"'}, "tree", "pass"),
    ("bash", {"command": "git commit -m cd"}, "~/Research", "pass"),
    # `edit` and `write`: the settings template's Edit and Write denies, and oh-my-pi's directory.
    (
        "edit",
        {"path": "~/.omp/agent/config.yml", "old_string": "a", "new_string": "b"},
        "~/Research",
        "block",
    ),
    ("write", {"path": "~/.omp/agent/config.yml", "content": "x"}, "~/Research", "block"),
    (
        "edit",
        {"path": "~/.omp/agent/extensions/guards.ts", "old_string": "a", "new_string": "b"},
        "~/Research",
        "block",
    ),
    ("write", {"path": "~/.omp/agent/extensions/guards.ts", "content": "x"}, "~/Research", "block"),
    (
        "edit",
        {"path": "~/.claude/hooks/no-shell-file-write.py", "old_string": "a", "new_string": "b"},
        "~/Research",
        "block",
    ),
    ("write", {"path": "~/.claude/hooks/no-shell-file-write.py", "content": "x"}, "~/Research", "block"),
    ("write", {"path": "../.claude/hooks/no-shell-file-write.py", "content": "x"}, "~/Research", "block"),
    # oh-my-pi's path resolver drops a leading `:` before `./` and `../`, as before `/` and `~`.
    ("write", {"path": ":../.claude/hooks/x.py", "content": "x"}, "~/Research", "block"),
    ("read", {"path": ":../.netrc"}, "~/Research", "block"),
    ("read", {"path": ":./../.netrc"}, "~/Research", "block"),
    ("write", {"path": ":./Notes/plan.md", "content": "x"}, "~/Research", "pass"),
    ("write", {"path": "~/.config/gh/config.yml", "content": "x"}, "~/Research", "block"),
    ("edit", {"path": ".git/config", "old_string": "a", "new_string": "b"}, "tree", "block"),
    ("edit", {"path": "Notes/plan.md", "old_string": "a", "new_string": "b"}, "~/Research", "pass"),
    ("write", {"path": "~/Research/Notes/plan.md", "content": "x"}, "tree", "pass"),
    # The write tool removes a hashline header, `[path]` or `[path#TAG]`, from its path.
    ("write", {"path": "[~/.omp/agent/config.yml]", "content": "x"}, "~/Research", "block"),
    (
        "write",
        {"path": "[~/.claude/hooks/no-shell-file-write.py#1A2B]", "content": "x"},
        "~/Research",
        "block",
    ),
    # An exact-file deny matches only the path without the tag, so this case needs the tag removed.
    ("write", {"path": "[~/.zshrc#1A2B]", "content": "x"}, "~/Research", "block"),
    ("write", {"path": "[Notes/plan.md#1A2B]", "content": "x"}, "~/Research", "pass"),
    # The other edit modes: a patch's `rename`, and the paths of a hashline or apply_patch `input`.
    (
        "edit",
        {"path": "Notes/plan.md", "edits": [{"op": "update", "rename": "~/.config/x.md"}]},
        "~/Research",
        "block",
    ),
    (
        "edit",
        {"input": "*** Begin Patch\n[~/.omp/agent/config.yml#1A2B]\nPUT 1.=1:\n+x\n*** End Patch\n"},
        "~/Research",
        "block",
    ),
    (
        "edit",
        {"input": "*** Begin Patch\n[Notes/plan.md#1A2B]\nMV ../.claude/hooks/x.py\n*** End Patch\n"},
        "~/Research",
        "block",
    ),
    (
        "edit",
        {
            "input": "*** Begin Patch\n*** Update File: ../.claude/hooks/gh-api-writes.py\n@@\n-a\n+b\n"
            "*** End Patch\n"
        },
        "~/Research",
        "block",
    ),
    # A hashline header in quotes, a header with no closing `]`, and an `MV` path in quotes.
    ("edit", {"input": '["~/.omp/agent/config.yml"#1A2B]\nPUT 1.=1:\n+x\n'}, "~/Research", "block"),
    (
        "edit",
        {"input": "[Notes/plan.md#1A2B]\nPUT 1.=1:\n+x\n[~/.omp/agent/config.yml#1A2B\nPUT 1.=1:\n+x\n"},
        "~/Research",
        "block",
    ),
    ("edit", {"input": "[Notes/plan.md#1A2B]\nMV '../.claude/hooks/x.py'\n"}, "~/Research", "block"),
    (
        "edit",
        {"input": "*** Begin Patch\n[Notes/plan.md#1A2B]\nPUT 1.=1:\n+x\n*** End Patch\n"},
        "~/Research",
        "pass",
    ),
    ("edit", {"input": "PUT 1.=1:\n+x\n"}, "~/Research", "block"),
    # The program argument of an awk, sed or grep is a pattern, not a path: the forms that the
    # guard refused as the path `/` in the oh-my-pi runs.
    ("bash", {"command": "sed -n '/\\[compat\\]/,$p' Project.toml"}, "~/Research", "pass"),
    ("bash", {"command": "git show v0.2.1:Project.toml | sed -n '/\\[compat\\]/,$p'"}, "~/Research", "pass"),
    ("bash", {"command": "sed -n '/^## \\[Unreleased\\]/,+3p' CHANGELOG.md | head -6"}, "~/Research", "pass"),
    (
        "bash",
        {
            "command": "awk '/^\\[\\[deps\\.(A|B)\\]\\]/{p=1;print;next} /^\\[\\[/{p=0} p&&/version|path/' "
            "Manifest.toml"
        },
        "~/Research",
        "pass",
    ),
    ("bash", {"command": "awk -F'|' '/^\\| \\*\\*P[0-9]+\\*\\*/ {print $2}' plan.md"}, "~/Research", "pass"),
    (
        "bash",
        {"command": "awk '/^\\[compat\\]/{f=1} f&&/^Base/{print $0; exit}' Project.toml"},
        "~/Research",
        "pass",
    ),
    ("bash", {"command": "grep -rn token src | sed -n '/function f!/,/^[0-9]*-end/p'"}, "tree", "pass"),
    ("bash", {"command": "grep -E '/[0-9]+/' notes.md"}, "~/Research", "pass"),
    ("bash", {"command": "sed -e '/[a-z]*/d' -e 's/x/y/' f.txt"}, "~/Research", "pass"),
    ("bash", {"command": "grep -n -e '/[*]/' f.txt"}, "~/Research", "pass"),
    # A glob reaches only the names that its first glob segment matches.
    ("bash", {"command": "ls /[0-9]*/x"}, "~/Research", "pass"),
    # The refusals stay: the files that such a program reads, a home path in the program text, a
    # `-f` file, a real root, and a glob whose segment matches a denied name.
    ("bash", {"command": "sed -n '/x/p' ~/.netrc"}, "tree", "block"),
    ("bash", {"command": "awk '/^machine/' .netrc"}, "~", "block"),
    ("bash", {"command": "awk 'BEGIN{while((getline l < \"~/.netrc\")>0) print l}'"}, "tree", "block"),
    ("bash", {"command": "grep -f ~/.netrc notes.md"}, "tree", "block"),
    ("bash", {"command": "find / -name x"}, "tree", "block"),
    ("bash", {"command": "grep -r token /*"}, "tree", "block"),
    ("bash", {"command": "cat ~/.ss*/config"}, "tree", "block"),
    ("bash", {"command": "ls ~/*"}, "tree", "block"),
    ("bash", {"command": "cat ~/[.]netrc"}, "tree", "block"),
]
# (tool, input, the session's working directory, the extension's verdict, text the reason holds):
# the cases whose reason matters. "~/Research/P" is a main checkout of the fixture home.
ASK_USER = "Ask the user in chat"
OMP_REASON_CASES = [
    # rm-scope.py: a recursive `rm` outside the scratch zones is refused with its message, one inside
    # them runs, and a `git rm` in a main checkout is its "ask", which the extension refuses.
    (
        "bash",
        {"command": "rm -rf ~/Research/x"},
        "~/Research",
        "block",
        "outside the zones where a recursive `rm` runs",
    ),
    ("bash", {"command": "rm -rf ~/Research/.scratch/x"}, "~/Research", "pass", None),
    ("bash", {"command": "git rm f"}, "~/Research/P", "block", ASK_USER),
    # git-archive-output.py: `git archive -o` is refused with the commands that read the tree instead.
    ("bash", {"command": "git archive -o base.tar origin/main"}, "~/Research/P", "block", "base-tree.jl"),
    ("bash", {"command": "git archive origin/main -- src"}, "~/Research/P", "pass", None),
    # The template's Edit asks: refused, and the model is told to ask in chat. Every path form of
    # an edit or a write goes through the ask list too.
    (
        "edit",
        {"path": "~/Research/P/.githooks/pre-commit", "old_string": "a", "new_string": "b"},
        "~/Research",
        "block",
        ASK_USER,
    ),
    (
        "edit",
        {"path": ".github/workflows/test.yml", "old_string": "a", "new_string": "b"},
        "~/Research/P",
        "block",
        ASK_USER,
    ),
    ("write", {"path": "~/.claude/skills/x/SKILL.md", "content": "x"}, "~/Research", "block", ASK_USER),
    ("write", {"path": "[~/.claude/workflows/x.js#1A2B]", "content": "x"}, "~/Research", "block", ASK_USER),
    (
        "edit",
        {"input": "[Notes/plan.md#1A2B]\nMV ../.claude/skills/x/SKILL.md\n"},
        "~/Research",
        "block",
        ASK_USER,
    ),
    (
        "edit",
        {"path": "~/Research/P/src/a.jl", "old_string": "a", "new_string": "b"},
        "~/Research",
        "pass",
        None,
    ),
    ("write", {"path": "~/.claude/skills.md", "content": "x"}, "~/Research", "pass", None),
    # A path under a deny and an ask is refused with the deny text: the deny list is checked first.
    (
        "edit",
        {"path": "~/.claude/skills/build-part/SKILL.md", "old_string": "a", "new_string": "b"},
        "~/Research",
        "block",
        "the deny rule",
    ),
    # sandbox-semantics.py --work-tree: a `git init` or `git clone` inside a work tree is refused,
    # one in a directory that is no work tree runs, also after a `cd` there.
    ("bash", {"command": "git init probe"}, "~/Research/P", "block", "inside the work tree"),
    (
        "bash",
        {"command": "git clone https://github.com/example-org/X.jl.git X"},
        "~/Research/P",
        "block",
        "inside the work tree",
    ),
    ("bash", {"command": "git init probe"}, "~/Research", "pass", None),
    ("bash", {"command": "cd .. && git init probe"}, "~/Research/P", "pass", None),
    ("bash", {"command": "cd P && git init probe"}, "~/Research", "block", "inside the work tree"),
    # kaimon-session.py on oh-my-pi's names of the Kaimon tools.
    ("mcp__kaimon_ex", {"e": "1 + 1"}, "~/Research", "block", "without `ses`"),
    ("mcp__kaimon_ex", {"e": "1 + 1", "ses": "a1b2c3d4"}, "~/Research", "pass", None),
    ("mcp__kaimon_manage_repl", {"command": "shutdown"}, "~/Research", "block", "without `session`"),
    ("mcp__kaimon_manage_repl", {"command": "shutdown", "session": "a1b2c3d4"}, "~/Research", "pass", None),
    ("mcp__kaimon_check_eval", {"eval_id": "e1f2a3b4"}, "~/Research", "pass", None),
]
# (tool, input, the agent whose context the driver gives, the extension's verdict, text the reason
# holds): a sub-agent writes to no other agent, since a write to `agent://` wakes a parked agent;
# the session, which continues an agent only by a new spawn, is left to OMP-DELTA.md.
SUB_AGENT = "a sub-agent writes to no other agent"
OMP_AGENT_CASES = [
    ("write", {"path": "agent://CriticP13a", "content": "Your round is done."}, "sub", "block", SUB_AGENT),
    ("write", {"path": " AGENT://SuiteP16a", "content": "Run the suite."}, "sub", "block", SUB_AGENT),
    ("write", {"path": "agent://CriticP34b", "content": "Write the report."}, "main", "pass", None),
    ("write", {"path": "agent://CriticP34b", "content": "Write the report."}, "", "pass", None),
    ("write", {"path": "Notes/plan.md", "content": "x"}, "sub", "pass", None),
    ("read", {"path": "agent://CriticP13a"}, "sub", "pass", None),
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


def omp_cases():
    """The cases of the oh-my-pi guard extension: (number of cases, number wrong)."""
    total = wrong = 0

    def report(ok, line):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    node = shutil.which("node")

    class HomeOptions(TypedDict, total=False):
        """The keywords of `home` that a fail-closed case sets."""

        scripts: dict[str, str | None]
        paths: str | Literal[False]
        timeout: int

    def home(
        name: str,
        scripts: dict[str, str | None] | None = None,
        paths: str | Callable[[str, str], str] | Literal[False] | None = None,
        timeout: int | None = None,
    ) -> str:
        """A fixture home with the seven guard scripts of OC_SCRIPTS in hooks/, beside ext/, each
        one that `scripts` names replaced by its text there, or left out for None, and the
        extension with its path list in `ext/`: `paths`, for a function the text
        `paths(rendered list, home)`, else the rendered list. `timeout` replaces the extension's
        timeout in milliseconds."""
        scripts = scripts or {}
        h = FIXTURE.name + "/" + name
        os.makedirs(h + "/hooks")
        os.makedirs(h + "/ext")
        for script in OC_SCRIPTS:
            if script not in scripts:
                os.symlink(HOOKS + script, h + "/hooks/" + script)
            elif (text := scripts[script]) is not None:
                with open(h + "/hooks/" + script, "w") as f:
                    f.write(text)
        with open(REPO + "/adapters/omp/guards.ts") as f:
            source = f.read()
        if timeout is not None:
            line = "const TIMEOUT_MS = 10_000;"
            if line not in source:
                raise OSError(
                    f"adapters/omp/guards.ts holds no line {line!r}, which the timeout case replaces"
                )
            source = source.replace(line, f"const TIMEOUT_MS = {timeout};")
        with open(h + "/ext/guards.mjs", "w") as f:
            f.write(source)
        if paths is not False:
            rendered = omp.guard_paths(replace(dummy, home=h))
            with open(h + "/ext/guard-paths.json", "w") as f:
                f.write(paths(rendered, h) if callable(paths) else paths if paths is not None else rendered)
        return h

    def verdict(h, tool, data, env=None, cwd=CWD, mode="", want=None):
        """'block', 'pass', or what went wrong, for one event of `tool` with input `data`; with
        `want`, a block whose reason lacks that text is wrong too."""
        event = json.dumps({"type": "tool_call", "toolCallId": "probe", "toolName": tool, "input": data})
        # omp_cases returns before its first case when `node` is not on PATH.
        if node is None:
            raise RuntimeError("`node` is not on PATH")
        try:
            p = subprocess.run(
                [node, "--input-type=module", "-e", OMP_DRIVER, h + "/ext/guards.mjs", event, cwd, mode],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                env=env or {**CLEAN, "HOME": "/" + h},
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        if p.returncode != 0:
            return f"exit {p.returncode}: {p.stderr.strip()[-160:]!r}"
        try:
            answer = json.loads(p.stdout)
        except ValueError:
            return f"unreadable output {p.stdout[-80:]!r}"
        if answer is None:
            return "pass"
        if answer.get("block") is not True or not answer.get("reason"):
            return f"unreadable answer {answer!r}"
        if want is not None and want not in answer["reason"]:
            return f"block without {want!r}: {answer['reason'][:160]!r}"
        return "block"

    try:
        sys.path.insert(0, REPO + "/lib")
        from harness import frontends, profile
    except ImportError as e:  # the case reports it as wrong, and the probe goes on to its summary
        report(ok=False, line=f"exp render got {type(e).__name__}  [omp-guard]  {e}")
        return total, wrong
    try:
        omp = frontends.adapter("omp")
        dummy = profile.load(REPO + "/examples/profile.toml")
        config = omp.render_config(dummy, omp.load_models(REPO + "/examples/models.toml"))
        patterns = json.loads("".join(l for l in config.splitlines(keepends=True) if not l.startswith("#")))
        patterns = patterns["bash"]["patterns"]
    # The adapter, the profile and the rendering fail with HarnessError; the parsing of their
    # output with the others. The case reports it as wrong, and the probe goes on to its summary.
    except (profile.HarnessError, OSError, ValueError, LookupError, TypeError) as e:
        report(False, f"exp render got {type(e).__name__}  [omp-guard]  {e}")
        return total, wrong
    if node is None:
        report(False, "exp node got none  [omp-guard]  `node` is not on PATH, so no case of guards.ts runs")
        return total, wrong
    exit_with = "import sys\nsys.exit({})\n".format
    decide = (
        'import json\nprint(json.dumps({"hookSpecificOutput": {"permissionDecision": "deny", '
        '"permissionDecisionReason": "probe-deny"}}))\n'
    )
    try:
        good = home("omp-home")
        os.makedirs(good + "/Research/P/.git")
        # A path list whose ask list also holds ~/.claude/hooks/**, which the edit list denies.
        both = home(
            "omp-home-both",
            paths=lambda text, h: json.dumps(
                {**json.loads(text), "ask": [*json.loads(text).get("ask", []), h + "/.claude/hooks/**"]}
            ),
        )
        options: list[tuple[str, HomeOptions]] = [
            ("a guard exits 1", {"scripts": {"no-blind-stage.py": exit_with(1)}}),
            ("a guard script is missing", {"scripts": {"no-blind-stage.py": None}}),
            (
                "a guard prints output that is not JSON",
                {"scripts": {"no-blind-stage.py": "print('hello')\n"}},
            ),
            ("a guard answers deny with exit 0", {"scripts": {"no-blind-stage.py": decide}}),
            (
                "a guard is killed by a signal",
                {
                    "scripts": {
                        "no-blind-stage.py": "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"
                    }
                },
            ),
            (
                "a guard takes longer than the timeout",
                {"scripts": {"no-blind-stage.py": "import time\ntime.sleep(20)\n"}, "timeout": 300},
            ),
            ("the path list is missing", {"paths": False}),
            ("the deny list is not a list", {"paths": '{"deny": "x", "edit": []}'}),
            ("the edit list is missing", {"paths": '{"deny": []}'}),
            ("rm-scope.py exits 1", {"scripts": {"rm-scope.py": exit_with(1)}}),
            ("the ask list is not a list", {"paths": '{"deny": [], "edit": [], "ask": "x"}'}),
            ("the ask list is missing", {"paths": '{"deny": [], "edit": []}'}),
        ]
        fail = {label: home("omp-home-" + str(i), **kw) for i, (label, kw) in enumerate(options)}
    except OSError as e:
        report(False, f"exp fixture got {type(e).__name__}  [omp-guard]  {e}")
        return total, wrong
    for tool, data, expected, pattern in OMP_CASES:
        got = verdict(good, tool, data)
        report(got == expected, f"exp {expected} got {got}  [omp-guard]  {tool} {data}")
        if pattern is not None:
            got = omp_pattern(data["command"], patterns)
            report(got == pattern, f"exp {pattern} got {got}  [omp-patts]  {data['command']}")
    where = {
        "tree": CWD,
        "~": good,
        "~/Research": good + "/Research",
        "~/.ssh": good + "/.ssh",
        "~/.omp": good + "/.omp",
        "~/Research/P": good + "/Research/P",
    }
    for tool, data, cwd, expected in OMP_PATH_CASES:
        got = verdict(good, tool, data, cwd=where[cwd])
        report(got == expected, f"exp {expected} got {got}  [omp-guard]  {tool} {data}  in {cwd}")
    for tool, data, cwd, expected, want in OMP_REASON_CASES:
        got = verdict(good, tool, data, cwd=where[cwd], want=want)
        report(
            got == expected, f"exp {expected} got {got}  [omp-guard]  {tool} {data}  in {cwd}, with {want!r}"
        )
    for tool, data, agent, expected, want in OMP_AGENT_CASES:
        got = verdict(good, tool, data, cwd=where["~/Research"], mode=agent, want=want)
        report(
            got == expected,
            f"exp {expected} got {got}  [omp-guard]  {tool} {data}  in a {agent or 'unnamed'} agent",
        )
    got = verdict(
        both,
        "edit",
        {"path": "~/.claude/hooks/x", "old_string": "a", "new_string": "b"},
        cwd=good + "/Research",
        want="the deny rule",
    )
    report(
        got == "block",
        f"exp block got {got}  [omp-guard]  a path under a deny and an ask: edit ~/.claude/hooks/x",
    )
    # It fails closed: a guard that cannot run, exits with another status than 0 or 2, prints
    # output that is not JSON, answers "deny", is killed or times out; a path list that is missing
    # or malformed; and an error of the handler itself each block the call. (label, home, tool,
    # input, environment, driver mode, text the reason must hold)
    status = "git status"
    for label, h, tool, data, env, mode, want in [
        (
            "python3 is not on PATH",
            good,
            "bash",
            {"command": status},
            {**CLEAN, "HOME": "/" + good, "PATH": "/nonexistent"},
            "",
            "fails closed",
        ),
        *[
            (label, fail[label], "bash", {"command": status}, None, "", want)
            for label, want in [
                ("a guard exits 1", "exited with status 1"),
                ("a guard script is missing", "is missing"),
                ("a guard prints output that is not JSON", "not JSON"),
                ("a guard answers deny with exit 0", "probe-deny"),
                ("a guard is killed by a signal", "SIGKILL"),
                ("a guard takes longer than the timeout", "did not answer"),
                ("the path list is missing", "cannot be used"),
                ("the deny list is not a list", "cannot be used"),
            ]
        ],
        (
            "the path list is missing",
            fail["the path list is missing"],
            "read",
            {"path": "src/Foo.jl"},
            None,
            "",
            "cannot be used",
        ),
        (
            "the edit list is missing",
            fail["the edit list is missing"],
            "edit",
            {"path": "src/Foo.jl", "old_string": "a", "new_string": "b"},
            None,
            "",
            "cannot be used",
        ),
        (
            "rm-scope.py exits 1",
            fail["rm-scope.py exits 1"],
            "bash",
            {"command": status},
            None,
            "",
            "rm-scope.py exited with status 1",
        ),
        (
            "the ask list is not a list",
            fail["the ask list is not a list"],
            "edit",
            {"path": "src/Foo.jl", "old_string": "a", "new_string": "b"},
            None,
            "",
            "cannot be used",
        ),
        (
            "the ask list is not a list",
            fail["the ask list is not a list"],
            "write",
            {"path": "src/Foo.jl", "content": "x"},
            None,
            "",
            "cannot be used",
        ),
        (
            "the ask list is missing",
            fail["the ask list is missing"],
            "edit",
            {"path": "src/Foo.jl", "old_string": "a", "new_string": "b"},
            None,
            "",
            "cannot be used",
        ),
        ("the handler throws", good, "bash", {"command": status}, None, "throw", "failed"),
    ]:
        got = verdict(h, tool, data, env, mode=mode, want=want)
        report(got == "block", f"exp block got {got}  [omp-guard]  fail-closed, {label}: {tool} {data}")
    # A missing edit list leaves the other tools to the deny list.
    got = verdict(fail["the edit list is missing"], "read", {"path": "src/Foo.jl"})
    report(got == "pass", f"exp pass got {got}  [omp-guard]  the edit list is missing: read src/Foo.jl")
    # A bad ask list leaves the other tools to the deny list.
    got = verdict(fail["the ask list is not a list"], "read", {"path": "src/Foo.jl"})
    report(got == "pass", f"exp pass got {got}  [omp-guard]  the ask list is not a list: read src/Foo.jl")
    return total, wrong


# OpenCode v2's plugins, `adapters/opencode/plugins/*.ts`, run under `node` with a stub of the
# plugin context: the driver imports a plugin, calls its `setup(ctx)`, keeps the callbacks that
# `ctx.tool.hook` and `ctx.shell.hook` register under one hook name, and calls them in order on one
# event, as OpenCode 2.0.25 does. The event of `execute.before` is the shape the binary builds,
# `{tool, sessionID, agent, messageID, id, input}`, with the shell tool named `shell`; that of the
# shell's `create.before` is `{command, cwd, timeout, shell, env}`; `ctx.location.directory` is the
# session's directory, and an empty directory leaves `location` out of the stub context. A hook that
# throws refuses the call, and the driver prints the reason, the
# event after the hooks, the plugin's exports and its id. Each plugin is copied into a fixture home
# as `<name>.mjs`, so the plugins hold JavaScript syntax only. The guard scripts are the seven of
# `OC_SCRIPTS`, linked into the fixture's `~/.claude/hooks/`, each run through its own shebang as the
# plugin runs it, and the path list is `guard-paths.json` rendered with the dummy profile and the
# fixture's home. A fail-closed case gets a home of its own, with one guard script replaced or the
# path list left out; the timeout case lowers `TIMEOUT_MS` in its copy. An rtk case runs `node` with
# the fixture home's `bin/` as its whole `PATH`, so the plugin finds the fixture `rtk` there or none.
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
OC_SCRIPTS = (
    "no-blind-stage.py",
    "no-shell-file-write.py",
    "gh-api-writes.py",
    "rm-scope.py",
    "git-archive-output.py",
    "sandbox-semantics.py",
    "kaimon-session.py",
)
OC_PLUGINS = {
    "guards": "research-harness.guards",
    "rtk": "research-harness.rtk",
    "env": "research-harness.env",
}
OC_GUARD = "research-harness.guards"  # each refusal of a guard that cannot answer names the plugin


def oc_event(command, tool="shell", **fields):
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
    total = wrong = 0

    def report(ok, line):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    node = shutil.which("node")

    def home(name, scripts=None, paths=None, timeout=None, rtk=None):
        """A fixture home with the seven guard scripts of OC_SCRIPTS in hooks/, beside plugins/,
        each one that `scripts` names replaced by its text there, or left out for None, and the
        plugins with their path list in `plugins/`: `paths`, else the rendered list, or none for
        False. `timeout` replaces the guard's timeout in milliseconds; `rtk`, the text of a
        fixture `bin/rtk`, or None for a `bin/` with none."""
        scripts = scripts or {}
        h = FIXTURE.name + "/" + name
        for d in ("/hooks", "/plugins", "/bin", "/.ssh"):
            os.makedirs(h + d)
        for script in OC_SCRIPTS:
            if script not in scripts:
                os.symlink(HOOKS + script, h + "/hooks/" + script)
            elif scripts[script] is not None:
                with open(h + "/hooks/" + script, "w") as f:
                    f.write("#!/usr/bin/env python3\n" + scripts[script])
                os.chmod(h + "/hooks/" + script, 0o755)
        if rtk is not None:
            with open(h + "/bin/rtk", "w") as f:
                f.write(rtk)
            os.chmod(h + "/bin/rtk", 0o755)
        for plugin in OC_PLUGINS:
            with open(REPO + f"/adapters/opencode/plugins/{plugin}.ts") as f:
                source = f.read()
            if timeout is not None and plugin == "guards":
                line = "const TIMEOUT_MS = 10_000;"
                if line not in source:
                    raise OSError(
                        f"adapters/opencode/plugins/{plugin}.ts holds no line {line!r}, which a case replaces"
                    )
                source = source.replace(line, f"const TIMEOUT_MS = {timeout};")
            with open(h + f"/plugins/{plugin}.mjs", "w") as f:
                f.write(source)
        if paths is not False:
            with open(h + "/plugins/guard-paths.json", "w") as f:
                f.write(
                    paths
                    if paths is not None
                    else profile.render_file(
                        REPO + "/adapters/opencode/plugins/guard-paths.json", replace(dummy, home=h)
                    )
                )
        return h

    def drive(
        h,
        plugin,
        event,
        kind="tool",
        name="execute.before",
        cwd=CWD,
        process_cwd=None,
        path=None,
        config_dir=None,
    ):
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
                env={**env, "HOME": "/" + h},
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

    def verdict(h, event, want=None, cwd=CWD, process_cwd=None, config_dir=None):
        """'refuse' or 'pass' for the guard plugin on one event; with `want`, a refusal whose
        reason lacks that text is wrong, and without it, a refusal because a guard failed."""
        answer = drive(h, "guards", event, cwd=cwd, process_cwd=process_cwd, config_dir=config_dir)
        if isinstance(answer, str):
            return answer
        if "setup" in answer:
            return f"setup threw {answer['setup'][:120]!r}"
        if answer["verdict"] == "refuse" and want is not None and want not in answer["reason"]:
            return f"refuse without {want!r}: {answer['reason'][:160]!r}"
        if answer["verdict"] == "refuse" and want is None and OC_GUARD in answer["reason"]:
            return f"refuse as failed: {answer['reason'][:160]!r}"
        return answer["verdict"]

    try:
        sys.path.insert(0, REPO + "/lib")
        from harness import profile
    except ImportError as e:  # the case reports it as wrong, and the probe goes on to its summary
        report(ok=False, line=f"exp profile got {type(e).__name__}  [oc-plugin]  {e}")
        return total, wrong
    try:
        dummy = profile.load(REPO + "/examples/profile.toml")
    # The profile fails with HarnessError, its fields of an unexpected shape with the others. The
    # case reports it as wrong, and the probe goes on to its summary.
    except (profile.HarnessError, OSError, ValueError, LookupError, TypeError) as e:
        report(False, f"exp profile got {type(e).__name__}  [oc-plugin]  {e}")
        return total, wrong
    if node is None:
        report(False, "exp node got none  [oc-plugin]  `node` is not on PATH, so no case of the plugins runs")
        return total, wrong
    exit_with = "import sys\nsys.exit({})\n".format
    # The fixture's rewrite is not the real RTK's `rtk git status`, so an `rtk` found elsewhere than
    # on the fixture's PATH, such as a fixed path in the plugin, cannot give it.
    rewrite = (
        '#!/bin/sh\nif [ "$1 $2 $3" = "hook check git status" ]; then echo "fixture-rtk git status"; exit 0; fi\n'
        'echo "No rewrite for: $3"; exit 1\n'
    )
    try:
        good = home("oc-home", rtk=rewrite)
        fail = {
            label: home("oc-home-" + str(i), **kw)
            for i, (label, kw) in enumerate(
                [
                    ("a guard script is missing", {"scripts": {"no-blind-stage.py": None}}),
                    ("a guard exits 1", {"scripts": {"no-blind-stage.py": exit_with(1)}}),
                    ("a guard prints {", {"scripts": {"no-blind-stage.py": "print('{')\n"}}),
                    (
                        "a guard takes longer than the timeout",
                        {"scripts": {"no-blind-stage.py": "import time\ntime.sleep(20)\n"}, "timeout": 300},
                    ),
                    ("the path list is missing", {"paths": False}),
                    (
                        "a guard denies",
                        {
                            "scripts": {
                                "no-blind-stage.py": "import json\nprint(json.dumps({'hookSpecificOutput': "
                                "{'permissionDecision': 'deny', 'permissionDecisionReason': "
                                "'the fixture guard denies'}}))\n"
                            }
                        },
                    ),
                    ("rtk exits 1", {"rtk": '#!/bin/sh\necho "rtk git status"\nexit 1\n'}),
                    ("no rtk", {}),
                ]
            )
        }
    except OSError as e:
        report(False, f"exp fixture got {type(e).__name__}  [oc-plugin]  {e}")
        return total, wrong

    # The v2 form: a default export {id, setup} and no other, and no module imported.
    for plugin, id in OC_PLUGINS.items():
        answer = drive(good, plugin, oc_event("true"))
        got = answer if isinstance(answer, str) else (answer["exports"], answer["id"], answer.get("setup"))
        report(
            got == (["default"], id, None),
            f"exp {(['default'], id, None)} got {got}  [oc-plugin]  {plugin}.ts",
        )
        with open(REPO + f"/adapters/opencode/plugins/{plugin}.ts") as f:
            imports = [
                l.strip() for l in f if re.match(r"\s*import\b", l) or re.search(r"\b(?:import|require)\(", l)
            ]
        report(imports == [], f"exp no import got {imports}  [oc-plugin]  {plugin}.ts")

    # The guard: (event, verdict, text the reason must hold).
    tree = FIXTURE.name + "/home/Research/Harness"
    for event, expected, want in [
        (oc_event("cat ~/.local/share/opencode/auth.json"), "refuse", "path guard"),
        (oc_event("sed -i s/a/b/ f"), "refuse", "in-place"),
        (oc_event("git add -A"), "refuse", None),
        (oc_event("gh api -X DELETE repos/o/r"), "refuse", None),
        (oc_event("rm -rf ~/Research/x"), "refuse", None),
        (oc_event("rtk cat ~/.local/share/opencode/auth.json"), "refuse", "path guard"),
        # The guard scripts do not know `rtk`, so only the form without it reaches no-blind-stage.py.
        (oc_event("rtk git add -A"), "refuse", None),
        (oc_event(" rtk git add -A"), "refuse", None),
        (oc_event("rtk\tgit add -A"), "refuse", None),
        (oc_event("rtk  git add -A"), "refuse", None),
        (oc_event("git status"), "pass", None),
        (oc_event(None, tool="read", filePath="~/.local/share/opencode/auth.json"), "pass", None),
        # Only the `shell` tool is checked, whatever command another tool's input holds.
        (oc_event("git add -A", tool="bash"), "pass", None),
        # A background call is checked as any other; a `workdir` is a `cd` the command does not spell.
        (oc_event("cat ~/.local/share/opencode/auth.json", background=True), "refuse", "path guard"),
        (oc_event("ls -la", workdir=good + "/.ssh"), "refuse", "path guard"),
        (oc_event("git status", workdir=tree), "pass", None),
    ]:
        got = verdict(good, event, want)
        report(got == expected, f"exp {expected} got {got}  [oc-guards]  {event['tool']} {event['input']}")

    # An `ask` of a guard script refuses too (decision 2), and so does a write of
    # `no-shell-file-write.py`. The scripts get `input.workdir` as their working directory, else the
    # session's directory, never the `node` process's: each case runs `node` in a directory where
    # the other answer comes out. `scratch` is below $TMPDIR, so no script refuses anything there.
    scratch, wt, pkg = (
        FIXTURE.name,
        "/" + good + "/Research/.worktrees/Foo-bar",
        "/" + good + "/Research/Packages/A",
    )
    os.makedirs(wt[1:])
    os.makedirs(pkg[1:])
    empty = FIXTURE.name + "/oc-no-work-tree"
    os.makedirs(empty)
    asked = "OpenCode cannot ask for it"
    for label, event, directory, process_cwd, expected, want in [
        ("gh-api-writes.py asks", oc_event("gh api -X POST repos/o/r/issues"), CWD, None, "refuse", asked),
        ("rm-scope.py asks", oc_event("git rm f"), pkg, wt, "refuse", asked),
        (
            "git-archive-output.py refuses",
            oc_event("git archive -o base.tar origin/main"),
            wt,
            wt,
            "refuse",
            "base-tree.jl",
        ),
        (
            "no-shell-file-write.py refuses",
            oc_event("echo x > f"),
            PKG,
            scratch,
            "refuse",
            "git working tree",
        ),
        ("workdir", oc_event("echo x > f", workdir=PKG), scratch, scratch, "refuse", "git working tree"),
        ("session directory", oc_event("rm -rf build"), wt, pkg, "pass", None),
        ("session directory", oc_event("rm -rf build"), pkg, wt, "refuse", None),
        ("workdir", oc_event("rm -rf build", workdir=wt), pkg, pkg, "pass", None),
        ("workdir", oc_event("rm -rf build", workdir=pkg), wt, wt, "refuse", None),
        # A context with no `location`: the session's directory is the `node` process's.
        ("no location, the node directory", oc_event("rm -rf build"), "", pkg, "refuse", None),
        ("no location, the node directory", oc_event("rm -rf build"), "", wt, "pass", None),
        # sandbox-semantics.py --work-tree: `PKG` is a work tree of the fixture, `scratch` none.
        (
            "a git init in a work tree",
            oc_event("git init probe"),
            PKG,
            scratch,
            "refuse",
            "inside the work tree",
        ),
        (
            "a git init in a work tree",
            oc_event("git init probe", workdir=PKG),
            scratch,
            scratch,
            "refuse",
            "inside the work tree",
        ),
        ("a git init elsewhere", oc_event("git init probe"), scratch, PKG, "pass", None),
        # An empty directory: the path guard refuses a `cd` into one that holds a denied path.
        ("a git init after a cd", oc_event("cd " + q(empty) + " && git init probe"), PKG, PKG, "pass", None),
        # kaimon-session.py on OpenCode's names of the Kaimon tools.
        ("kaimon_ex", oc_event(None, tool="kaimon_ex", e="1"), CWD, None, "refuse", "without `ses`"),
        ("kaimon_ex", oc_event(None, tool="kaimon_ex", e="1", ses="a1b2c3d4"), CWD, None, "pass", None),
        (
            "kaimon_manage_repl",
            oc_event("shutdown", tool="kaimon_manage_repl"),
            CWD,
            None,
            "refuse",
            "without `session`",
        ),
        (
            "kaimon_check_eval",
            oc_event(None, tool="kaimon_check_eval", eval_id="e1f2a3b4"),
            CWD,
            None,
            "pass",
            None,
        ),
    ]:
        got = verdict(good, event, want, cwd=directory, process_cwd=process_cwd)
        report(
            got == expected,
            f"exp {expected} got {got}  [oc-guards]  {label}: {event['input']} in {directory or process_cwd}",
        )

    # Fail closed: each refuses `git status`, with a reason that names the guard plugin.
    for label in (
        "a guard script is missing",
        "a guard exits 1",
        "a guard prints {",
        "a guard takes longer than the timeout",
        "the path list is missing",
    ):
        got = verdict(fail[label], oc_event("git status"), OC_GUARD)
        report(got == "refuse", f"exp refuse got {got}  [oc-guards]  fail-closed, {label}: git status")
    # With no path list, `setup` still resolves and registers its hook.
    answer = drive(fail["the path list is missing"], "guards", oc_event("git status"))
    got = answer if isinstance(answer, str) else (answer.get("setup"), answer["hooks"])
    report(got == (None, 1), f"exp {(None, 1)} got {got}  [oc-guards]  setup with no path list")
    # A `deny` decision of a guard script refuses, as an `ask` does.
    got = verdict(fail["a guard denies"], oc_event("git status"), "the fixture guard denies")
    report(got == "refuse", f"exp refuse got {got}  [oc-guards]  a guard prints a deny decision: git status")

    # The list in $OPENCODE_CONFIG_DIR: one that is not JSON refuses every `shell` call, as a missing
    # or broken global list does; a valid one, or none there, adds to the global list.
    local = FIXTURE.name + "/oc-config"
    os.makedirs(local + "/broken")
    os.makedirs(local + "/valid")
    os.makedirs(local + "/none")
    with open(local + "/broken/guard-paths.json", "w") as f:
        f.write('{"allow": [')
    with open(local + "/valid/guard-paths.json", "w") as f:
        f.write('{"deny": ["/etc/**"]}')
    for label, directory, event, expected, want in [
        ("a local list that is not JSON", "broken", oc_event("git status"), "refuse", OC_GUARD),
        ("a local list that is not JSON", "broken", oc_event("true"), "refuse", OC_GUARD),
        ("a valid local list", "valid", oc_event("git status"), "pass", None),
        ("a valid local list", "valid", oc_event("cat /etc/hosts"), "refuse", "path guard"),
        ("no local list", "none", oc_event("git status"), "pass", None),
    ]:
        got = verdict(good, event, want, config_dir=local + "/" + directory)
        report(
            got == expected, f"exp {expected} got {got}  [oc-guards]  {label}: {event['input']['command']}"
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
        report(got == expected, f"exp {expected!r} got {got!r}  [oc-rtk   ]  {label}: git status")
    # Only the `shell` tool's command is rewritten.
    answer = drive(good, "rtk", oc_event("git status", tool="bash"), path=good + "/bin")
    got = answer if isinstance(answer, str) else answer["event"]["input"]["command"]
    report(
        got == "git status",
        f"exp 'git status' got {got!r}  [oc-rtk   ]  rtk rewrites, a bash event: git status",
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
    report(got == expected, f"exp {expected} got {got}  [oc-env   ]  create.before")
    return total, wrong


# Antigravity's guard hook, `adapters/antigravity/guard.py`, runs with this interpreter in a fixture
# home's `.gemini/config/`, where `hooks.json` runs it, as hooks/guard.py beside the seven guard
# scripts of OC_SCRIPTS, linked from this directory, and with `guard-paths.json` rendered with the
# dummy profile and the fixture's home. It gets the payload that Antigravity sends, `toolCall` and
# `workspacePaths`, and its verdict is the `decision` it prints. The working directory of the
# process is the fixture's `.gemini/config/`, which is no git work tree, as the real one is not;
# the call's working directory is CWD, the probe's work tree, through `workspacePaths` or `Cwd`.
# A bash command also gets the verdict of the rendered `permissions` rules, deny before ask
# before allow, read with the adapter's `rule_matches`.
AGY_SSH = "~/.ssh/id_ed25519"
# (tool, args, the hook's decision, the permission rules' verdict for a run_command)
AGY_CASES = [
    ("run_command", {"CommandLine": "git push --force origin x"}, "deny", "deny"),
    ("run_command", {"CommandLine": "sed -i s/a/b/ f"}, "deny", "deny"),
    ("run_command", {"CommandLine": "git add -A"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.config/gh/hosts.yml"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.gemini/config/mcp_config.json"}, "deny", None),
    ("run_command", {"CommandLine": "cat .env"}, "deny", None),
    ("run_command", {"CommandLine": "git status"}, "ask", "allow"),
    ("run_command", {"CommandLine": "gh api -X POST repos/a/b/issues"}, "force_ask", None),
    ("run_command", {"CommandLine": "ls -la", "Cwd": "~/.ssh"}, "deny", None),
    ("run_command", {"CommandLine": "sed -i s/a/b/ f", "Cwd": CWD}, "deny", None),
    ("run_command", {"CommandLine": "env KEY=~/.netrc true"}, "deny", None),
    ("run_command", {"CommandLine": "cat " + AGY_SSH + ' "'}, "deny", None),
    ("run_command", {"CommandLine": "gh api -X POST repos/a/b/issues && git add -A"}, "deny", None),
    # sandbox-semantics.py runs with `--work-tree` alone: the work-tree check refuses, the other
    # shapes pass.
    ("run_command", {"CommandLine": "git init sub"}, "deny", None),
    ("run_command", {"CommandLine": "echo $(gh run view 1)"}, "ask", None),
    ("read_file", {"Path": AGY_SSH}, "deny", None),
    ("read_file", {"Path": "~/.SSH/ID_ED25519"}, "deny", None),
    ("read_file", {"Path": "~/.gemini/config/mcp_config.json"}, "deny", None),
    ("read_file", {"Path": "src/Foo.jl"}, "ask", None),
    ("view_file", {"AbsolutePath": AGY_SSH}, "deny", None),
    ("write_to_file", {"TargetFile": "~/.aws/credentials", "CodeContent": "x"}, "deny", None),
    (
        "replace_file_content",
        {"TargetFile": "~/.netrc", "TargetContent": "a", "ReplacementContent": "b"},
        "deny",
        None,
    ),
    ("grep_search", {"Query": "token", "SearchPath": "~/.gnupg"}, "deny", None),
    ("find_by_name", {"Pattern": "*", "SearchDirectory": "~/.ssh"}, "deny", None),
    ("list_dir", {"DirectoryPath": "~/.config/api-keys"}, "deny", None),
    ("write_file", {"Path": "notes.md", "Content": "x"}, "ask", None),
    ("send_message", {"Message": "done", "Recipient": "main"}, "ask", None),
    ("call_mcp_tool", {"ServerName": "kaimon", "ToolName": "ex", "Arguments": {"e": "1"}}, "deny", None),
    (
        "call_mcp_tool",
        {"ServerName": "kaimon", "ToolName": "ex", "Arguments": {"e": "1", "ses": "abcd1234"}},
        "ask",
        None,
    ),
    (
        "call_mcp_tool",
        {"ServerName": "kaimon", "ToolName": "manage_repl", "Arguments": {"command": "restart"}},
        "deny",
        None,
    ),
    ("call_mcp_tool", {"ServerName": "kaimon", "ToolName": "ex", "Arguments": '{"e": "1"}'}, "deny", None),
    ("call_mcp_tool", {"ServerName": "kaimon", "ToolName": "ping", "Arguments": {}}, "ask", None),
    ("call_mcp_tool", {"ServerName": "zotero", "ToolName": "ex", "Arguments": {}}, "ask", None),
    # The `edit` and `ask` lists, on the tools that write: a template Edit deny gives deny, an Edit
    # ask gives force_ask, a path under both gives deny; a read and a command word pass them.
    ("write_to_file", {"TargetFile": TOOL + "/.git/config", "CodeContent": "x"}, "deny", None),
    (
        "write_file",
        {"Path": "~/.julia/juliaup/julia-1.11.5+0.aarch64.apple.darwin14/bin/julia", "Content": "x"},
        "deny",
        None,
    ),
    ("view_file", {"AbsolutePath": TOOL + "/.git/config"}, "ask", None),
    ("run_command", {"CommandLine": "cat .git/HEAD"}, "ask", None),
    (
        "replace_file_content",
        {
            "TargetFile": "~/Research/X/.github/workflows/ci.yml",
            "TargetContent": "a",
            "ReplacementContent": "b",
        },
        "force_ask",
        None,
    ),
    (
        "edit_file",
        {"Path": "~/.claude/skills/build-part/SKILL.md", "Target": "a", "Replacement": "b"},
        "deny",
        None,
    ),
    # The files of the layer itself.
    ("write_to_file", {"TargetFile": "~/.gemini/config/hooks.json", "CodeContent": "{}"}, "deny", None),
    (
        "edit_file",
        {"Path": "~/.gemini/antigravity-cli/settings.json", "Target": "a", "Replacement": "b"},
        "deny",
        None,
    ),
    ("run_command", {"CommandLine": "echo {} > ~/.gemini/config/guard-paths.json"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.gemini/config/guard-paths.json"}, "deny", None),
    ("run_command", {"CommandLine": "rm ~/.gemini/config/hooks/guard.py"}, "deny", None),
    # The installed instructions, rules and skills: the template's Edit rules of Claude Code's copies
    # hold for Antigravity's, on the tools that write; a read and a command pass them.
    ("write_file", {"Path": "~/.gemini/config/GEMINI.md", "Content": "x"}, "deny", None),
    (
        "replace_file_content",
        {
            "TargetFile": "~/.gemini/config/rules/julia-code.md",
            "TargetContent": "a",
            "ReplacementContent": "b",
        },
        "deny",
        None,
    ),
    (
        "edit_file",
        {"Path": "~/.gemini/config/skills/build-part/SKILL.md", "Target": "a", "Replacement": "b"},
        "deny",
        None,
    ),
    (
        "write_to_file",
        {"TargetFile": "~/.gemini/config/skills/new-skill/SKILL.md", "CodeContent": "x"},
        "force_ask",
        None,
    ),
    ("view_file", {"AbsolutePath": "~/.gemini/config/GEMINI.md"}, "ask", None),
    ("run_command", {"CommandLine": "cat ~/.gemini/config/rules/julia-code.md"}, "ask", None),
    # The other global instruction files that Antigravity loads, which the install does not write.
    ("write_file", {"Path": "~/.gemini/config/AGENTS.md", "Content": "x"}, "deny", None),
    ("edit_file", {"Path": "~/.gemini/GEMINI.md", "Target": "a", "Replacement": "b"}, "deny", None),
    ("view_file", {"AbsolutePath": "~/.gemini/GEMINI.md"}, "ask", None),
    # The installed agents.
    ("write_file", {"Path": "~/.gemini/config/agents/julia-critic.md", "Content": "x"}, "deny", None),
    ("view_file", {"AbsolutePath": "~/.gemini/config/agents/julia-critic.md"}, "ask", None),
    # The app's grants, which an agent that rewrites them could use to widen its own; a read passes.
    ("write_file", {"Path": "~/.gemini/config/config.json", "Content": "{}"}, "deny", None),
    ("view_file", {"AbsolutePath": "~/.gemini/config/config.json"}, "ask", None),
    # A home path in each form of the shell.
    ("run_command", {"CommandLine": "cat $HOME/.netrc"}, "deny", None),
    ("run_command", {"CommandLine": "cat ${HOME}/.netrc"}, "deny", None),
    (
        "call_mcp_tool",
        {"ServerName": "kaimon", "ToolName": "ex", "Arguments": '{"e": "1", "ses": "abcd1234"}'},
        "ask",
        None,
    ),
    # A glob is checked as written and cut to its directory, which is wide; a recursive command, a
    # `cd`, a `Cwd` and a `SearchPath` make a path wide; a wide path that holds a deny path is refused.
    ("run_command", {"CommandLine": "cat ~/.gemini/config/mcp_conf*.json"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.gemini/config/*"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.netr[c]"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.config/gh/{hosts.yml,x}"}, "deny", None),
    ("run_command", {"CommandLine": "grep -r Bearer ~/.gemini/config"}, "deny", None),
    ("run_command", {"CommandLine": "cd ~/.gemini/config && cat mcp_config.json"}, "deny", None),
    ("run_command", {"CommandLine": "rg Bearer", "Cwd": "~/.gemini/config"}, "deny", None),
    ("grep_search", {"Query": "Bearer", "SearchPath": "~/.gemini/config"}, "deny", None),
    ("run_command", {"CommandLine": "cat ~/.gemini/config/skills/x/SKILL.md"}, "ask", None),
    ("run_command", {"CommandLine": "cat ~/.gemini/config/skills/*/SKILL.md"}, "ask", None),
    ("run_command", {"CommandLine": "ls ~/.gemini/config"}, "ask", None),
    ("run_command", {"CommandLine": "ls src/*.jl"}, "ask", None),
    ("run_command", {"CommandLine": "grep -r foo src"}, "ask", None),
    ("run_command", {"CommandLine": "cd ~/Research && git status"}, "ask", None),
    ("run_command", {"CommandLine": "grep -r Bearer ~/.GEMINI/config"}, "deny", None),
    ("run_command", {"CommandLine": "cat /*"}, "deny", None),
    ("run_command", {"CommandLine": "ls /"}, "ask", None),
    # The template's Bash denies and asks, on each segment of the line.
    ("run_command", {"CommandLine": "echo $(git push --force origin x)"}, "deny", None),
    ("run_command", {"CommandLine": "echo `git push --force origin x`"}, "deny", None),
    ("run_command", {"CommandLine": "(git push --force origin x)"}, "deny", None),
    ("run_command", {"CommandLine": "git status && git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "git status | git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "gh pr merge 1"}, "force_ask", None),
    ("run_command", {"CommandLine": "sed -i 's/a;b/c/' f"}, "deny", None),
    ("run_command", {"CommandLine": "echo 'a; git push --force origin x'"}, "ask", None),
    ("run_command", {"CommandLine": "git push origin main && ls -f"}, "ask", None),
    ("run_command", {"CommandLine": "git -C . reset --hard"}, "deny", None),
    ("run_command", {"CommandLine": "git status; git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "git status & git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "git status\ngit push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "echo \\'; git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": 'echo "a \\" ; git push --force origin x"'}, "ask", None),
    ("run_command", {"CommandLine": "git push \\\n--force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "git push --force\\\n origin x"}, "deny", None),
    ("run_command", {"CommandLine": 'echo "a; git push --force origin x"'}, "ask", None),
    ("run_command", {"CommandLine": 'git "push" --force origin x'}, "deny", None),
    ("run_command", {"CommandLine": "git push --force origin x '"}, "deny", None),
    ("run_command", {"CommandLine": "pushd ~/.gemini/config && cat mcp_config.json"}, "deny", None),
    # A rule matches the words of a segment from any word: an assignment, a wrapper or a keyword
    # before the command does not hide it, and a quoted word is one word.
    ("run_command", {"CommandLine": "FOO=1 git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "env git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "command git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "time git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "! git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": "{ git push --force origin x; }"}, "deny", None),
    ("run_command", {"CommandLine": "if true; then git push --force origin x; fi"}, "deny", None),
    ("run_command", {"CommandLine": "echo `date` git push --force origin x"}, "deny", None),
    ("run_command", {"CommandLine": 'git -C . "reset" --hard'}, "deny", None),
    ("run_command", {"CommandLine": "FOO=1 git -C . reset --hard"}, "deny", None),
    ("run_command", {"CommandLine": "git -C sub add .gitignore"}, "ask", None),
    ("run_command", {"CommandLine": 'git commit -m "git push --force"'}, "ask", None),
    ("run_command", {"CommandLine": 'git commit -m "x --amend"'}, "ask", None),
    # A rule that asks does not override a guard that refuses: no deny or ask rule of the template
    # matches `git init sub`, which sandbox-semantics.py refuses.
    ("run_command", {"CommandLine": "gh pr merge 1 && git init sub"}, "deny", None),
]
# The sandbox of a run_command that the hook does not deny: (args, the hook's decision, the
# `BypassSandbox` of its `overwrite`), in the probe's work tree. It is true only when `top_level`
# of sandbox-semantics.py lifts the command, as Claude Code's `excludedCommands` does (every part
# led by git, gh, glab or ps, and no file redirected), and none of the guard's screens applies. A
# line that does not parse stays in the sandbox, and so does any other command, whatever
# `BypassSandbox` the agent sets. The rm-scope guard asks on a line that does not parse and holds
# `rm`, as `--format` does.
AGY_BYPASS = [
    # The screens: a `#`, which shlex reads as a comment that hides the next line; a substitution
    # behind gh; a git option that runs a program or moves the repository; an assignment or a path
    # in front of the program; a git path argument that sandbox-semantics.py screens; a NUL.
    ({"CommandLine": "git status # x\njulia --version"}, "ask", False),
    ({"CommandLine": "git status#x; julia --version"}, "ask", False),
    ({"CommandLine": "gh pr view $(echo 1)"}, "ask", False),
    ({"CommandLine": "gh pr view '$(echo 1)'"}, "ask", False),
    ({"CommandLine": "git -c alias.x='!julia -e 1' x"}, "ask", False),
    ({"CommandLine": "git --git-dir=x status"}, "ask", False),
    ({"CommandLine": "git -C x -c a=b log"}, "ask", False),
    ({"CommandLine": "git -C log -c a=b log"}, "ask", False),
    ({"CommandLine": "git --config-env=a=B status"}, "ask", False),
    ({"CommandLine": "FOO=1 git status"}, "ask", False),
    ({"CommandLine": "./git status"}, "ask", False),
    ({"CommandLine": "git clone https://example.com/r.git /tmp/r"}, "ask", False),
    ({"CommandLine": "cd a\u0000b"}, "ask", False),
    ({"CommandLine": 'gh pr create --title "Fix #12"'}, "ask", False),
    # Text whose reading is not certain in sh, bash and zsh: an ANSI-C quote, which shlex ends at
    # its `\'`; a zsh process substitution and glob qualifier; a glob; a `$`, a backtick or a
    # backslash; a lone surrogate; a `\` or `!` in double quotes; a character outside ASCII; a lone
    # `&`; a newline outside quotes.
    ({"CommandLine": "git log $'\\'' ; julia --version ; true \\'"}, "ask", False),
    ({"CommandLine": "gh pr view 1 $'\\'' ; julia --version ; true \\'"}, "ask", False),
    ({"CommandLine": "git status $'\\''\njulia --version\ntrue \\'"}, "ask", False),
    ({"CommandLine": "git log =(julia --version)"}, "ask", False),
    ({"CommandLine": "git log *(e:'julia --version':)"}, "ask", False),
    ({"CommandLine": "git log -- *.md"}, "ask", False),
    ({"CommandLine": "git log $'x'"}, "ask", False),
    ({"CommandLine": 'git log "$(julia -e 1)"'}, "ask", False),
    ({"CommandLine": 'git log "`julia`"'}, "ask", False),
    ({"CommandLine": "git log a\\b"}, "ask", False),
    ({"CommandLine": "git log ${x:-y}"}, "ask", False),
    ({"CommandLine": "cd a\ud800b"}, "ask", False),
    ({"CommandLine": 'git log "a\\b"'}, "ask", False),
    ({"CommandLine": 'git log "a!b"'}, "ask", False),
    ({"CommandLine": "git log 'é'"}, "ask", False),
    ({"CommandLine": 'git log "é"'}, "ask", False),
    ({"CommandLine": "git fetch & git status"}, "ask", False),
    ({"CommandLine": "git fetch\ngit status"}, "ask", False),
    # Text whose reading is certain: plain words, quoted words and `2>&1`, with blanks and the four
    # separators between them.
    ({"CommandLine": "git -C ~/Research/Harness status --short --branch"}, "ask", True),
    ({"CommandLine": "gh auth status"}, "ask", True),
    ({"CommandLine": "gh auth status --hostname github.com"}, "ask", True),
    ({"CommandLine": 'git commit -m "Fix the parser\'s edge"'}, "ask", True),
    ({"CommandLine": "git commit -m 'Use \"x\" here'"}, "ask", True),
    ({"CommandLine": "git log --format=%H HEAD~1"}, "ask", True),
    ({"CommandLine": 'git add a && git commit -m "x y"'}, "ask", True),
    ({"CommandLine": " git fetch || git status\t--short "}, "ask", True),
    ({"CommandLine": "git fetch; git log --oneline | git status"}, "ask", True),
    # A `cd` to the working directory is dropped whatever its form, and a screened git option
    # screens git alone.
    ({"CommandLine": f"/usr/bin/cd {CWD} && git status"}, "ask", True),
    ({"CommandLine": "ps -c"}, "ask", True),
    ({"CommandLine": "git status"}, "ask", True),
    ({"CommandLine": "gh pr view 1"}, "ask", True),
    ({"CommandLine": "git -C x log"}, "ask", True),
    ({"CommandLine": "ps aux"}, "ask", True),
    ({"CommandLine": "glab mr list"}, "ask", True),
    ({"CommandLine": "git status 2>&1"}, "ask", True),
    ({"CommandLine": "git fetch && git status"}, "ask", True),
    ({"CommandLine": f"cd {CWD} && git status"}, "ask", True),
    ({"CommandLine": "gh pr merge 1"}, "force_ask", True),
    ({"CommandLine": "cd x && git status"}, "ask", False),
    ({"CommandLine": "julia --version"}, "ask", False),
    ({"CommandLine": "git status | cat"}, "ask", False),
    ({"CommandLine": "git log --oneline '"}, "ask", False),
    ({"CommandLine": 'git log --format="%h'}, "force_ask", False),
    ({"CommandLine": "julia --version", "BypassSandbox": True}, "ask", False),
    ({"CommandLine": "git status", "BypassSandbox": False}, "ask", True),
]


def agy_cases():
    """The cases of Antigravity's guard hook: (number of cases, number wrong)."""
    total = wrong = 0

    def report(ok, line):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    class HomeOptions(TypedDict, total=False):
        """The keywords of `home` that a fail-closed case sets."""

        scripts: dict[str, str | None]
        paths: str | Callable[[str], str] | Literal[False]
        timeout: int

    def home(
        name: str,
        scripts: dict[str, str | None] | None = None,
        paths: str | Callable[[str], str] | Literal[False] | None = None,
        timeout: int | None = None,
        rendered_for: str | None = None,
    ) -> str:
        """A fixture home with guard.py and the seven guard scripts of OC_SCRIPTS in
        .gemini/config/hooks/, each one that `scripts` names replaced by its text there, or left
        out for None, and the path list `paths`, for a function the text `paths(rendered list)`, else
        the rendered one, or none for False. The list is rendered for the home `rendered_for`, else
        the fixture home. `timeout` replaces guard.py's TIMEOUT in seconds."""
        scripts = scripts or {}
        h = FIXTURE.name + "/" + name
        config = h + "/.gemini/config"
        os.makedirs(config + "/hooks")
        for script in OC_SCRIPTS:
            if script not in scripts:
                os.symlink(HOOKS + script, config + "/hooks/" + script)
            elif (text := scripts[script]) is not None:
                with open(config + "/hooks/" + script, "w") as f:
                    f.write(text)
        with open(REPO + "/adapters/antigravity/guard.py") as f:
            source = f.read()
        if timeout is not None:
            line = "TIMEOUT = 10\n"
            if line not in source:
                raise OSError(
                    f"adapters/antigravity/guard.py holds no line {line!r}, which the timeout case replaces"
                )
            source = source.replace(line, f"TIMEOUT = {timeout}\n")
        with open(config + "/hooks/guard.py", "w") as f:
            f.write(source)
        if paths is not False:
            rendered = agy.guard_paths(replace(dummy, home=rendered_for or h))
            with open(config + "/guard-paths.json", "w") as f:
                f.write(paths(rendered) if callable(paths) else paths if paths is not None else rendered)
        return h

    class ReplyOptions(TypedDict, total=False):
        """The fields of the hook call that a case varies, beside the tool and its arguments."""

        workspace: str
        raw: str | None
        env: dict[str, str] | None
        argv: list[str] | None
        limit: float

    def reply(
        h: str, tool: str | None = None, args: dict[str, Any] | None = None, **options: Unpack[ReplyOptions]
    ) -> tuple[Any, tuple[str, str] | None]:
        """The answer of the hook in home `h` on a call of `tool` with `args`, or on the payload
        text `raw`, within `limit` seconds, as (the answer object, None); (None, what went wrong)
        when it prints no decision, or `{}`. `workspace` is CWD and `limit` TIMEOUT by default."""
        workspace = options.get("workspace", CWD)
        raw = options.get("raw")
        env = options.get("env")
        argv = options.get("argv")
        limit = options.get("limit", TIMEOUT)
        payload = (
            raw
            if raw is not None
            else json.dumps(
                {
                    "conversationId": "probe",
                    "modelName": "probe",
                    "stepIdx": 1,
                    "toolCall": {"name": tool, "args": args},
                    "workspacePaths": [workspace],
                }
            )
        )
        config = h + "/.gemini/config"
        try:
            p = subprocess.run(
                argv or [sys.executable, config + "/hooks/guard.py"],
                input=payload,
                capture_output=True,
                text=True,
                timeout=limit,
                cwd=config,
                env=env or {**CLEAN, "HOME": "/" + h},
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None, ("timeout", "")
        try:
            answer = json.loads(p.stdout)
        except ValueError:
            return None, (f"exit {p.returncode}, unreadable output {p.stdout[-80:]!r}", p.stderr)
        if p.returncode != 0 or not isinstance(answer, dict) or not answer.get("decision"):
            return None, (f"exit {p.returncode}, answer {answer!r}", p.stderr)
        if answer["decision"] != "ask" and not answer.get("reason"):
            return None, (f"{answer['decision']} without a reason", "")
        return answer, None

    def verdict(*args, **kw):
        """The decision of the hook and its reason, as `reply` gets them; what went wrong when it
        prints no decision, or `{}`."""
        answer, failed = reply(*args, **kw)
        return failed or (answer["decision"], answer.get("reason", ""))

    def overwrite_of(answer):
        """The `overwrite` of `answer`, or "none" when it has none."""
        return answer.get("overwrite", "none") if answer else "no answer"

    def permission(command):
        for kind in ("deny", "ask", "allow"):
            if any(agy.rule_matches(r, command) for r in rules[kind]):
                return kind
        return "none"

    try:
        sys.path.insert(0, REPO + "/lib")
        from harness import frontends, profile
    except ImportError as e:  # the case reports it as wrong, and the probe goes on to its summary
        report(ok=False, line=f"exp render got {type(e).__name__}  [agy-guard]  {e}")
        return total, wrong
    try:
        agy = frontends.adapter("antigravity")
        dummy = profile.load(REPO + "/examples/profile.toml")
        cfg = frontends.adapter("claude").settings_template(dummy, FIXTURE.name + "/no-network.toml")
        rules, _ = agy.render_permissions(cfg, dummy)
    # The adapters, the profile and the rendering fail with HarnessError, an input of an unexpected
    # shape with the others. The case reports it as wrong, and the probe goes on to its summary.
    except (profile.HarnessError, OSError, ValueError, LookupError, TypeError) as e:
        report(False, f"exp render got {type(e).__name__}  [agy-guard]  {e}")
        return total, wrong
    exit_with = "import sys\nsys.exit({})\n".format
    try:
        good = home("agy-home")
        options: list[tuple[str, HomeOptions]] = [
            (
                "a guard script is replaced by exit 7",
                {"scripts": {"no-blind-stage.py": exit_with(7)}},
            ),
            ("a guard script is missing", {"scripts": {"rm-scope.py": None}}),
            (
                "a guard prints output that is not JSON",
                {"scripts": {"gh-api-writes.py": "print('hello')\n"}},
            ),
            (
                "a guard takes longer than the timeout",
                {"scripts": {"git-archive-output.py": "import time\ntime.sleep(5)\n"}, "timeout": 1},
            ),
            ("the Kaimon guard exits 1", {"scripts": {"kaimon-session.py": exit_with(1)}}),
            ("the path list is missing", {"paths": False}),
            ("the deny list is not a list", {"paths": '{"deny": "x"}'}),
            ("the path list is not JSON", {"paths": "{"}),
            (
                "the edit list is missing",
                {
                    "paths": lambda text: json.dumps(
                        {k: v for k, v in json.loads(text).items() if k != "edit"}
                    )
                },
            ),
            (
                "the ask list is not a list",
                {"paths": lambda text: json.dumps({**json.loads(text), "ask": "x"})},
            ),
            (
                "the bash_deny list is not a list",
                {"paths": lambda text: json.dumps({**json.loads(text), "bash_deny": "x"})},
            ),
            (
                "the bash_ask list is missing",
                {
                    "paths": lambda text: json.dumps(
                        {k: v for k, v in json.loads(text).items() if k != "bash_ask"}
                    )
                },
            ),
        ]
        fail = {label: home("agy-home-" + str(i), **kw) for i, (label, kw) in enumerate(options)}
        # A home whose name holds a space, and a home whose list is rendered for the user's own
        # home, which `~<user>` names.
        spaced = home("agy home")
        user = getpass.getuser()
        own = home("agy-home-own", rendered_for=pwd.getpwnam(user).pw_dir)
        elsewhere = FIXTURE.name + "/agy-elsewhere"
        os.makedirs(elsewhere + "/sub")
        # A home without the template's rules, where the shell guards alone decide a `sed -i`.
        bare = home(
            "agy-home-no-bash",
            paths=lambda text: json.dumps({**json.loads(text), "bash_deny": [], "bash_ask": []}),
        )
        # A home whose sandbox-semantics.py lifts julia too.
        with open(HOOKS + "sandbox-semantics.py") as f:
            semantics = f.read()
        line = 'EXCLUDED = {"git", "gh", "glab", "ps"}\n'
        if line not in semantics:
            raise OSError(f"hooks/sandbox-semantics.py holds no line {line!r}, which the julia case replaces")
        lifts_julia = home(
            "agy-home-julia",
            scripts={
                "sandbox-semantics.py": semantics.replace(
                    line, 'EXCLUDED = {"git", "gh", "glab", "ps", "julia"}\n'
                )
            },
        )
    except OSError as e:
        report(False, f"exp fixture got {type(e).__name__}  [agy-guard]  {e}")
        return total, wrong
    for tool, args, expected, pattern in AGY_CASES:
        answer, failed = reply(good, tool, args)
        got = failed[0] if failed else answer["decision"]
        report(got == expected, f"exp {expected} got {got}  [agy-guard]  {tool} {args}")
        # Only a run_command that the hook does not deny carries an `overwrite`, and it holds
        # `BypassSandbox` alone, as a bool.
        sandbox = overwrite_of(answer)
        want = "BypassSandbox" if tool == "run_command" and expected != "deny" else "none"
        alone = (
            isinstance(sandbox, dict)
            and set(sandbox) == {"BypassSandbox"}
            and type(sandbox["BypassSandbox"]) is bool
        )
        shape = "BypassSandbox" if alone else "none" if sandbox == "none" else repr(sandbox)
        report(shape == want, f"exp {want} got {shape}  [agy-bypass]  the overwrite of {tool} {args}")
        if pattern is not None:
            got = permission(args["CommandLine"])
            report(got == pattern, f"exp {pattern} got {got}  [agy-perms]  {args['CommandLine']}")
    # The rules of the template's excludedCommands allow each of these lines in the app's policy, and
    # the guard, which runs before that policy, still refuses or asks.
    for line, expected, grant in [
        ("git push --force origin x", "deny", "command(git)"),
        ("git add -A", "deny", "command(git)"),
        ("gh pr merge 1", "force_ask", "command(gh)"),
    ]:
        answer, failed = reply(good, "run_command", {"CommandLine": line})
        got = failed[0] if failed else answer["decision"]
        granted = grant in rules["allow"] and agy.rule_matches(grant, line)
        report(
            got == expected and granted,
            f"exp {expected} got {got}  [agy-grant]  {line}, which the allow rule {grant} matches: {granted}",
        )
        # A deny leaves the sandbox as it is; a force_ask runs the lifted command outside it.
        sandbox, want = overwrite_of(answer), "none" if expected == "deny" else {"BypassSandbox": True}
        report(sandbox == want, f"exp {want} got {sandbox}  [agy-bypass]  the overwrite of {line}")
    for args, expected, bypass in AGY_BYPASS:
        answer, failed = reply(good, "run_command", args)
        got = failed[0] if failed else (answer["decision"], overwrite_of(answer))
        want = (expected, {"BypassSandbox": bypass})
        reason = "" if got == want or not answer else " " + repr(answer.get("reason", "")[:160])
        report(got == want, f"exp {want} got {got}  [agy-bypass]  {args}{reason}")
    # A file redirection keeps the command in the sandbox. The shell guards refuse `> f` in a work
    # tree, so the call runs in a directory that is none.
    answer, failed = reply(good, "run_command", {"CommandLine": "git status > f"}, workspace=elsewhere)
    got = failed[0] if failed else (answer["decision"], overwrite_of(answer))
    report(
        got == ("ask", {"BypassSandbox": False}),
        f"exp ('ask', {{'BypassSandbox': False}}) got {got}  [agy-bypass]  git status > f outside a work tree",
    )
    # A subagent's call carries its own Cwd, and a `cd` to that directory is dropped there, not at
    # the workspace.
    line = f"cd {elsewhere}/sub && git status"
    answer, failed = reply(good, "run_command", {"CommandLine": line, "Cwd": elsewhere + "/sub"})
    got = failed[0] if failed else (answer["decision"], overwrite_of(answer))
    report(
        got == ("ask", {"BypassSandbox": True}),
        f"exp ('ask', {{'BypassSandbox': True}}) got {got}  [agy-bypass]  {line} with that Cwd",
    )
    # The rule is the installed sandbox-semantics.py's, not a copy in guard.py: a copy of it that
    # also lifts julia lifts `julia --version`.
    got = overwrite_of(reply(lifts_julia, "run_command", {"CommandLine": "julia --version"})[0])
    report(
        got == {"BypassSandbox": True},
        f"exp {{'BypassSandbox': True}} got {got}  [agy-bypass]  julia --version, with an installed rule that "
        "lifts julia",
    )
    # Reading the rule writes no bytecode cache into the installed hooks/, also where the environment
    # allows one.
    reply(
        good,
        "run_command",
        {"CommandLine": "git status"},
        env={**{k: v for k, v in CLEAN.items() if k != "PYTHONDONTWRITEBYTECODE"}, "HOME": "/" + good},
    )
    cached = os.path.exists(good + "/.gemini/config/hooks/__pycache__")
    report(not cached, f"exp False got {cached}  [agy-bypass]  a __pycache__ in the hooks/ of guard.py")
    # A line of many words gets its answer within the timeout that hooks.json gives the hook.
    for line in ["echo " + "git push " * 10000, "echo " + "a " * 20000]:
        got, _ = verdict(good, "run_command", {"CommandLine": line}, limit=agy.HOOK_TIMEOUT)
        report(
            got == "ask",
            f"exp ask got {got}  [agy-guard]  {line[:20]!r}…, {len(line.split())} words, "
            f"within {agy.HOOK_TIMEOUT} s",
        )
    # The working directory of a call is its `Cwd`, resolved against the first of `workspacePaths`,
    # else that path: the `sed -i` runs in the work tree only through one of them. The template's
    # rules are left out of these homes, so that the shell guards decide the `sed -i`.
    for h, args, workspace, expected in [
        (bare, {"CommandLine": "sed -i s/a/b/ f"}, elsewhere, "ask"),
        (bare, {"CommandLine": "sed -i s/a/b/ f", "Cwd": CWD}, elsewhere, "deny"),
        (bare, {"CommandLine": "sed -i s/a/b/ f", "Cwd": elsewhere}, CWD, "ask"),
        (bare, {"CommandLine": "sed -i s/a/b/ f", "Cwd": "."}, CWD, "deny"),
        (good, {"CommandLine": "cat ../.netrc", "Cwd": "."}, good + "/sub", "deny"),
        (good, {"CommandLine": "cat .netrc", "Cwd": "~"}, elsewhere, "deny"),
        (good, {"CommandLine": "cat .ne*"}, good, "deny"),
        # A relative `Cwd` that goes down into a directory that holds a deny path is that directory.
        (good, {"CommandLine": "rg Bearer", "Cwd": "../.gemini/config"}, good + "/Research", "deny"),
        (good, {"CommandLine": "rg Bearer", "Cwd": ".gemini/config"}, good, "deny"),
        (good, {"CommandLine": "rg Bearer", "Cwd": "config"}, good + "/.gemini", "deny"),
    ]:
        got, _ = verdict(h, "run_command", args, workspace=workspace)
        report(
            got == expected,
            f"exp {expected} got {got}  [agy-guard]  {args} with workspacePaths [{workspace}]",
        )
    # `~<user>` is the home of that user, as the shell expands it.
    got, _ = verdict(own, "run_command", {"CommandLine": f"cat ~{user}/.netrc"})
    report(got == "deny", f"exp deny got {got}  [agy-guard]  cat ~{user}/.netrc")
    # A Kaimon call whose `Arguments` are not an object.
    for arguments in [None, "null", "[1]", "{"]:
        args = {"ServerName": "kaimon", "ToolName": "ex"} | (
            {} if arguments is None else {"Arguments": arguments}
        )
        got, _ = verdict(good, "call_mcp_tool", args)
        report(got == "deny", f"exp deny got {got}  [agy-guard]  fail-closed, Kaimon Arguments {arguments!r}")
    # The Kaimon guard runs on `ex` and `manage_repl` alone: with it broken, `ping` still passes.
    got, _ = verdict(
        fail["the Kaimon guard exits 1"],
        "call_mcp_tool",
        {"ServerName": "kaimon", "ToolName": "ping", "Arguments": {}},
    )
    report(got == "ask", f"exp ask got {got}  [agy-guard]  kaimon ping with the Kaimon guard broken")
    # A missing `edit` list leaves the tools that do not write to the `deny` list.
    got, _ = verdict(fail["the edit list is missing"], "read_file", {"Path": "src/Foo.jl"})
    report(got == "ask", f"exp ask got {got}  [agy-guard]  the edit list is missing: read_file src/Foo.jl")
    # A relative word is a path below the call's working directory.
    got, _ = verdict(good, "run_command", {"CommandLine": "cat .netrc", "Cwd": good})
    report(got == "deny", f"exp deny got {got}  [agy-guard]  cat .netrc with Cwd the home")
    # A payload with no workspace path still gets an answer.
    got, _ = verdict(
        good,
        raw=json.dumps(
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}, "workspacePaths": []}
        ),
    )
    report(got == "ask", f"exp ask got {got}  [agy-guard]  git status with no workspacePaths")
    # A guard's refusal reaches the model with the guard's own reason.
    got, reason = verdict(good, "run_command", {"CommandLine": "git add -A"})
    ok = got == "deny" and reason.strip() != "" and "fails closed" not in reason
    report(
        ok,
        f"exp deny got {got}  [agy-guard]  git add -A with no-blind-stage.py's own reason: {reason[:80]!r}",
    )
    # A guard that cannot start denies: guard.py loaded in this process, with a `subprocess.run`
    # that raises as a missing interpreter does.
    try:
        from unittest import mock

        shim = load_module("agy_guard", good + "/.gemini/config/hooks/guard.py")
        with mock.patch.object(shim.subprocess, "run", side_effect=FileNotFoundError(2, "No such file")):
            got = shim.run("no-blind-stage.py", "{}")
    # A guard.py that cannot be read or compiled, that has no `subprocess` or `run`, or whose `run`
    # lets the error of the start through: the case reports it as wrong.
    except (ImportError, SyntaxError, OSError, AttributeError, TypeError, ValueError) as e:
        got = (type(e).__name__, str(e))
    report(
        got[0] == "deny" and "could not start" in str(got[1]),
        f"exp deny got {got[0]}  [agy-guard]  fail-closed, a guard that cannot start: {str(got[1])[:80]!r}",
    )
    # It fails closed: each of these denies `git status`, or the Kaimon call, with its reason.
    status = {"CommandLine": "git status"}
    for label, h, tool, args, raw, want in [
        *[
            (label, fail[label], "run_command", status, None, want)
            for label, want in [
                ("a guard script is replaced by exit 7", "exited with status 7"),
                ("a guard script is missing", "is missing"),
                ("a guard prints output that is not JSON", "not a JSON answer"),
                ("a guard takes longer than the timeout", "did not answer"),
                ("the path list is missing", "cannot be used"),
                ("the deny list is not a list", "no list of strings"),
                ("the path list is not JSON", "cannot be used"),
                ("the bash_deny list is not a list", "no list of strings"),
                ("the bash_ask list is missing", "cannot be used"),
            ]
        ],
        (
            "the Kaimon guard exits 1",
            fail["the Kaimon guard exits 1"],
            "call_mcp_tool",
            {"ServerName": "kaimon", "ToolName": "ex", "Arguments": {"e": "1", "ses": "abcd1234"}},
            None,
            "exited with status 1",
        ),
        (
            "the path list is missing",
            fail["the path list is missing"],
            "send_message",
            {"Message": "x"},
            None,
            "cannot be used",
        ),
        (
            "the edit list is missing",
            fail["the edit list is missing"],
            "write_file",
            {"Path": "notes.md", "Content": "x"},
            None,
            "cannot be used",
        ),
        (
            "the ask list is not a list",
            fail["the ask list is not a list"],
            "write_to_file",
            {"TargetFile": "notes.md", "CodeContent": "x"},
            None,
            "no list of strings",
        ),
        ("the payload is not JSON", good, None, None, "not json", "failed"),
        ("the payload has no toolCall", good, None, None, '{"workspacePaths": []}', "failed"),
        ("the tool call has no name", good, None, None, '{"toolCall": {"args": {}}}', "failed"),
        ("the args are a list", good, "read_file", [], None, "not one that the guard hook can read"),
        (
            "the tool name is not a string",
            good,
            None,
            None,
            '{"toolCall": {"name": 5, "args": {}}}',
            "not one that the guard hook can read",
        ),
        ("a run_command has no CommandLine", good, "run_command", {}, None, "no CommandLine"),
    ]:
        got, reason = verdict(h, tool, args, raw=raw)
        ok = got == "deny" and want in reason
        report(
            ok,
            f"exp deny got {got}  [agy-guard]  fail-closed, {label}: {tool} {args}"
            f"{'' if ok else ' ' + repr(reason[:160])}",
        )

    # The handler of hooks.json, rendered for a home whose name holds a space, runs guard.py on the
    # interpreter that it names, from any working directory and with no python3 on the PATH.
    def pre_tool_use(python):
        return json.loads(agy.render_hooks(pathlib.Path(spaced) / ".gemini", python))[agy.HOOK]["PreToolUse"][
            0
        ]["hooks"][0]

    # The interpreter's path holds a space too: a link to this interpreter below the spaced home.
    interpreter = spaced + "/python env/bin/python"
    os.makedirs(os.path.dirname(interpreter), exist_ok=True)
    if not os.path.lexists(interpreter):
        os.symlink(sys.executable, interpreter)
    handler = pre_tool_use(interpreter)
    status_call = json.dumps(
        {"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}, "workspacePaths": [CWD]}
    )
    p = subprocess.run(
        ["/bin/sh", "-c", handler["command"]],
        input=status_call,
        capture_output=True,
        text=True,
        cwd=elsewhere,
        env={**CLEAN, "HOME": spaced, "PATH": "/nonexistent"},
        timeout=TIMEOUT,
        check=False,
    )
    got = p.stdout.strip()
    report(
        got == '{"decision": "ask", "overwrite": {"BypassSandbox": true}}',
        f"exp ask got {got!r}  [agy-guard]  the handler {handler['command']} from another directory, with no "
        f"python3 on the PATH",
    )
    # With no interpreter at the path that the handler names, the handler fails and prints nothing,
    # which Antigravity reads as a block.
    handler = pre_tool_use(spaced + "/no environment/bin/python")
    p = subprocess.run(
        ["/bin/sh", "-c", handler["command"]],
        input="{}",
        capture_output=True,
        text=True,
        cwd=elsewhere,
        env={**CLEAN, "HOME": spaced},
        timeout=TIMEOUT,
        check=False,
    )
    report(
        p.returncode != 0 and p.stdout == "",
        f"exp exit!=0 got {p.returncode}  [agy-guard]  fail-closed, the handler's interpreter is missing: no output "
        f"{p.stdout!r}",
    )
    return total, wrong


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


# Runs the guard `sys.argv[1]` as the settings template runs it, with each `os.stat` and `os.lstat`
# call, each spawn of `git` and each step of a walk (a call of `Place.child` of the package's
# `paths`, imported first so that the guard runs the counted class) counted, and writes the counts as
# the last line of stderr after the guard exits: `counts <stat and lstat calls> <git spawns> <steps>`.
COUNTED = """
import os, pathlib, runpy, subprocess, sys
counts = [0, 0, 0]
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
        counts[1] += pathlib.PurePath(str(args[0])).name == "git"
        super().__init__(args, *rest, **kwargs)
subprocess.Popen = Popen
sys.argv = [sys.argv[1], "--from", "claude"]
code = 0
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as e:
    code = e.code
sys.stderr.write(f"\\ncounts {counts[0]} {counts[1]} {counts[2]}\\n")
sys.exit(code)
"""


def guard_counted(data: bytes) -> tuple[str, int, int, int]:
    """The guard's decision on the payload bytes `data`, `deny`, `pass`, `exit <n>` or `timeout`, and
    its count of `os.stat` and `os.lstat` calls, of `git` spawns and of the steps of its walks; -1 for
    a count it did not print."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", COUNTED, GUARD],
            input=data,
            capture_output=True,
            env=ENV,
            cwd=FIXTURE.name,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", -1, -1, -1
    counts = re.search(rb"\ncounts (\d+) (\d+) (\d+)\n$", proc.stderr)
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
    """(payload text, expected decision) of each record of the corpus, its placeholders replaced by the
    fixture's values."""
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
    }
    records: list[tuple[str, str]] = []
    for line in pathlib.Path(REPO, "tests", "guard", "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        placed = line
        for name, value in table.items():
            placed = placed.replace(f"@@{name}@@", json.dumps(value)[1:-1])
        record = json.loads(placed)
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
