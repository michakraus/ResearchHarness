"""The cases of scripts in scripts/ that need no Julia. No subcommand of its own; `harness test`
runs them.

- The two package copies, the critic's copy in skills/build-part/evidence.md and `copy_command` in
  scripts/run-tests.jl: each is read from its source file and run with rsync on a fixture tree
  that holds a `.env` and `.env.*` files. The sandbox denies those files, so a copy of one leaves
  a temporary file that no one can remove; each copy leaves them out, keeps `env.ts`, and
  carries `--inplace`, so that rsync writes no temporary `.env.ts.XXXXXX`.
- scripts/spec-gate.py on a fixture task file: a part whose **Files** span two repositories is
  SPANS, and one whose files lie in its repository is not.
- scripts/spec-bundle.py on a fixture task file: the bundle holds the part's sections, its
  T-number row, §V, §L without the handovers filed below it, and what §L's *also reads* lines
  name; it leaves out the other parts and the state cell's narration; a name that matches nothing
  is unresolved, with exit status 1.
- scripts/spec-validate.py on a fixture spec in the spec-delta format: it passes, an `--env` name
  that it sets itself exits 3, and a missing domain, a failing premise and a mutant with no row
  each fail; with `--head`, a failing check and a check that writes into the head fail the gate.
  spec-gate.py validates a part whose cell names `spec` and finds a missing spec, and
  spec-bundle.py copies the spec and names `$SPEC`.
- A git of spec-validate.py and spec-bundle.py that runs past its timeout gives the answer of a git
  that fails: no status, a rule-9 error, and no commit.
- The fix round's mutants: skills/build-part/evidence.md defines them in one section, with its
  four rules, and both builders and both build skills point at it.
- scripts/probe-agentbox.py in a scratch home, with a stub for `srt`, `agentbox` and every program
  that a probe or the script names, first on the PATH, and the platform that each case sets, so
  that the cases run on Linux too and start no real sandbox, frontend, app or launchd job: each
  refusal exits 2 and calls neither stub; under a stub `srt` that refuses everything and one that
  allows everything, each probe gets its verdict, no report holds a marker line, no appended file
  changes, no probe file stays, and the launchd job is removed; the listeners and the second route
  of an `opencode` listener, the command lines of the frontend probes, F3 void where F1 is not
  `match`, a frontend past its time limit, and the report's files with their `## Listeners`.
"""

import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
from collections import Counter
from collections.abc import Callable
from typing import cast
from unittest import mock

from . import REPO

EVIDENCE = REPO / "skills" / "build-part" / "evidence.md"
RUN_TESTS = REPO / "scripts" / "run-tests.jl"
SPEC_GATE = REPO / "scripts" / "spec-gate.py"
SPEC_BUNDLE = REPO / "scripts" / "spec-bundle.py"
SPEC_VALIDATE = REPO / "scripts" / "spec-validate.py"
PROBE = REPO / "scripts" / "probe-agentbox.py"

# The stub of every program that probe-agentbox.py starts. Each copy appends the time, its working
# directory and its arguments, joined by \x1f, to `<name>.log` in the directory of the stubs, and
# acts on `config.json` there:
#   srt        "refuse": exits 1 and runs nothing; "allow": runs the command after `--`
#   agentbox   prints `answer`; for the frontend `sleep`, F1's call first runs `sleep 60`
#   curl       prints its -w template with the status in `curl` of the URL's port and path
#              (`4096/path`), else of its port, else 200 ("none" is no answer, 000 and exit 7),
#              and 000 for the CONNECT status
#   lsof       prints `lsof_opencode` with -c, `lsof` otherwise
#   launchctl, mount, umount   keep their jobs and mounts in files, so that `list` and a bare
#              `mount` show what `submit` and `mount` left
#   git        answers ls-remote and push itself, and runs the real git (`git`) for the rest
#   gh         prints a login; every other name exits 0
PROBE_STUB = r"""#!{python}
import json, os, pathlib, re, subprocess, sys, time
here = pathlib.Path("{dir}")
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
config = json.loads((here / "config.json").read_text())
with (here / (name + ".log")).open("a") as f:
    f.write("\x1f".join([str(time.time()), os.getcwd(), *args]) + "\n")
def kept(file):
    p = here / file
    return p.read_text().splitlines() if p.exists() else []
def keep(file, lines):
    (here / file).write_text("".join(line + "\n" for line in lines))
if name == "srt":
    if config["srt"] == "refuse":
        sys.exit(1)
    sys.exit(subprocess.run(args[args.index("--") + 1:]).returncode)
if name == "agentbox":
    if args[0] == config.get("sleep") and "single word OK" in " ".join(args):
        subprocess.run(["sleep", "60"])
    print(config.get("answer", ""))
elif name == "curl":
    url = re.search(r":(\d+)(/\S*)", args[-1])
    codes = config.get("curl", {})
    route = url.group(1) + url.group(2) if url else ""
    code = codes.get(route, codes.get(url.group(1) if url else "", "200"))
    template = args[args.index("-w") + 1].replace("%{http_connect}", "000")
    print(template.replace("%{http_code}", "000" if code == "none" else code), end="")
    sys.exit(7 if code == "none" else 0)
elif name == "lsof":
    print(config.get("lsof_opencode" if "-c" in args else "lsof", ""), end="")
elif name == "launchctl":
    jobs = kept("jobs")
    if args[0] == "submit":
        keep("jobs", [*jobs, args[args.index("-l") + 1]])
    elif args[0] == "list":
        print("".join("-\t0\t" + job + "\n" for job in jobs), end="")
    elif args[0] == "remove":
        keep("jobs", [job for job in jobs if job != args[1]])
elif name == "mount":
    if args:
        keep("mounts", [*kept("mounts"), args[-1]])
    else:
        print("".join("devfs on " + m + " (devfs, local)\n" for m in kept("mounts")), end="")
elif name == "umount":
    keep("mounts", [m for m in kept("mounts") if m != args[-1]])
elif name == "git":
    if args and args[0] in ("ls-remote", "push"):
        print("canned " + args[0])
    else:
        os.execv(config["git"], [config["git"], *args])
elif name == "gh":
    print("probe-login")
"""
# Runs probe-agentbox.py as __main__ with sys.platform set to the case's platform.
PROBE_RUNNER = (
    "import runpy, shutil, subprocess, sys; sys.platform = sys.argv[1]; path = sys.argv[2]; "
    "sys.argv = sys.argv[2:]; runpy.run_path(path, run_name='__main__')"
)
PROBE_STUBS = (
    *("curl", "nc", "dig", "gh", "open", "osascript", "mount", "umount", "launchctl", "sandbox-exec"),
    *("lsof", "git", "claude", "opencode", "omp", "agy"),
)
PROBE_MARKER = "AGENTBOX-PROBE-FIXTURE-MARKER"
# The files of the scratch home that a read probe counts, each with a marker line, and the files
# that an append probe opens, each with an old modification time.
PROBE_READ = (
    ".ssh/config",
    ".claude.json",
    ".config/kaimon/config.json",
    ".config/api-keys/a",
    "Library/Preferences/com.apple.dock.plist",
    ".claude/.credentials.json",
    ".local/share/opencode/auth.json",
    ".omp/agent/agent.db",
)
PROBE_APPENDED = (".claude/settings.json", ".zshrc", ".julia/config/startup.jl", ".omp/agent/config.yml")
PROBE_DIRS = ("Research", ".claude/hooks", "Library/LaunchAgents", ".omp/agent/extensions", ".gemini")
PROBE_POLICY = {"claude": "claude", "opencode": "opencode", "omp": "omp", "agy": "antigravity"}
PROBE_STATE = {"claude": ".claude", "opencode": ".local/share/opencode", "omp": ".omp", "agy": ".gemini"}
PROBE_CREDENTIAL = {
    "claude": (".claude/.credentials.json",),
    "opencode": (".local/share/opencode/auth.json",),
    "omp": (".omp/agent/agent.db",),
}
PROBE_SHELL_IDS = (
    *(f"R{k}" for k in range(1, 9)),
    *(f"W{k}" for k in range(1, 15)),
    *(f"N{k}" for k in range(1, 10)),
    *(f"X{k}" for k in range(1, 9)),
)
PROBE_MODEL_IDS = {
    "claude": ("F1", "F2", "F3", "F4"),
    "opencode": ("F1", "F2", "F3", "F4", "F6"),
    "omp": ("F1", "F2", "F3", "F4", "F7"),
    "agy": ("F1", "F2", "F3", "F4", "F5"),
}
OLD = 1_000_000_000

# The fixture task file of the spec bundle. Part P names a T-number row and its section; §L names
# §6, *Traps* and the preamble of §9, and one relative phrase. A handover filed below §L, part Q's
# section, §9's subsection and the state cell's narration stay out.
BUNDLE_PLAN = """# Plan

## Parts

| part | repository | sections | what it is | tier | state |
|:--|:--|:--|:--|:--|:--|
| **P** | `Example` | T1.2, §5V.P, §V, §L | The part. | build | open — NARRATION OF EARLIER BUILDS |
| **Q** | `Example` | §5V.Q, §V, §L | Another part. | build | open |

## §V · Plan rules

V-RULE.

## §L · The loop for this plan

- **The builder also reads:** the part's T-numbers in §5, §6 and *Traps*.
- **The critic also reads:** the preamble of §9, and §6.

### 0.9 Handover — 2026-10-17

HANDOVER-TEXT.

## 5 · The work

| id | goal | verification |
|:--|:--|:--|
| **T1.1** | other goal | x |
| **T1.2** | P-GOAL | x |

### 5V.P · Part P

P-SECTION. **Decided (advisor, 2026-10-20, high):** P-DECISION.

### 5V.Q · Part Q

Q-SECTION.

## 6 · Working rules

SIX-RULE.

## 9 · Background

NINE-PREAMBLE.

### 9.1 Detail

NINE-DETAIL.

## Traps

TRAP-TEXT.
"""
BUNDLE_IN = [
    "P-GOAL",
    "P-SECTION",
    "P-DECISION",
    "V-RULE",
    "builder also reads",
    "SIX-RULE",
    "NINE-PREAMBLE",
    "TRAP-TEXT",
    "| id | goal | verification |",
]
BUNDLE_OUT = ["HANDOVER-TEXT", "Q-SECTION", "other goal", "NINE-DETAIL", "NARRATION"]

# The fixture spec in the spec-delta format: one premise, one MODIFIED and one ADDED requirement,
# the second with a reference, and its mutant table. `{premise}`, `{domain}` and `{check}` vary.
SPEC_MD = """# S · The fixture part

**Base.** Example `1234567`.

## 1 · Living spec — Example at `1234567`

### Requirement: The answer

`answer()` SHALL return 41 on the base.

#### Scenario: the call

- WHEN `answer()` is called
- THEN it returns 41
- check: `{premise}`
- catches: none — a premise of the base

## 2 · Change proposal

**Why.** The answer is wrong.

**Files.** `src/answer.jl`, `test/answer.jl`.

## 3 · Delta

### MODIFIED Requirements

### Requirement: The answer

`answer()` SHALL return 42.

#### Scenario: the call

- WHEN `answer()` is called
- THEN it returns 42
- check: `{check}`
- catches: MU1, the old 41 back in `src/answer.jl`

### ADDED Requirements

### Requirement: The answer's sign (reference: the book, page 1)

The answer SHALL be positive, as the book's is.

#### Scenario: the sign

- WHEN `answer()` is called
- THEN it is positive
{domain}- check: `test -f "$SPEC"/checks/sign.sh`
- catches: none — the check is the command

## 4 · What stays from the plan

| mutant | change | kept test |
|:--|:--|:--|
| MU1 | the old 41 | `test/answer.jl` |
"""
SPEC_OK = {"premise": "true", "domain": "- domain: the default call, with no argument\n", "check": "true"}

# The fixture tree of the copies: what each copy holds, and what it leaves out.
KEPT = ["src/A.jl", "test/runtests.jl", "env.jl", "env.ts", "src/env.ts"]
LEFT_OUT = [".env", ".env.ts", "test/.env.local", ".git/HEAD", ".claude/scratch/x"]

# The files whose fix round runs only the mutants that the fix touches.
FIX_ROUND_FILES = [
    "agents/julia-builder.md",
    "agents/part-builder.md",
    "agents/python-builder.md",
    "skills/build-part/SKILL.md",
    "skills/build-reviewed/SKILL.md",
]

# The fixture task file of the spec gate: (part, repository, tier, Files, expected verdict).
SPEC_PARTS = [
    ("A", "Example", "build", "`src/A.jl`, `test/a.jl`, `CHANGELOG.md`", "PASS"),
    ("B", "Example", "build", "`src/B.jl`, `Tasks/plan.md`", "SPANS Example-Tasks"),
    ("C", "Example", "build", "`src/C.jl`, `Harness/scripts/x.py`", "SPANS Example-Harness"),
    ("D", "Example", "build", "`src/D.jl`, `~/Research/Packages/Other/src/x.jl`", "SPANS Example-Other"),
    ("E", "Example", "build", "`src/E.jl`, `~/.claude/rules/x.md`", "SPANS Example-.claude"),
    ("F", "Example", "build", "`Packages/Example/src/F.jl`, `docs/src/index.md`", "PASS"),
    ("G", "Example", "direct", "`src/G.jl`, `Tasks/plan.md`", "PASS"),
    ("H", "Harness", "reviewed", "`scripts/x.py`, `CHANGELOG.md`", "EXEMPT"),
    ("I", "Harness", "reviewed", "`scripts/x.py`, `Tasks/plan.md`", "SPANS Harness-Tasks"),
]


def fix_round_mutants(read: Callable[[str], str]) -> list[str]:
    """The problems of the fix round's mutant rule, with `read(relpath)` giving a file's text: the
    section in evidence.md with its four rules, and a pointer to it in each builder and skill."""
    evidence = read("skills/build-part/evidence.md")
    section = re.search(r"^### A fix round's mutants\n(.*?)(?=^#)", evidence, re.S | re.M)
    if section is None:
        return ["evidence.md has no section `### A fix round's mutants`"]
    problems = [
        f"the section lacks {phrase}"
        for phrase in (
            "**Round 1 runs the full set**",
            "**Own**",
            "**Function**",
            "**Test**",
            "**Survivor**",
            "do not run the earlier lists again",
        )
        if phrase not in section.group(1)
    ]
    problems.extend(
        f"{path} names no *A fix round's mutants*"
        for path in FIX_ROUND_FILES
        if "*A fix round's mutants*" not in " ".join(read(path).split())
    )
    return problems


def critic_excludes(text: str) -> list[str] | None:
    """The flags after `-a` of the critic's rsync in evidence.md, or None."""
    m = re.search(r"`rsync -a ([^`]*?) <worktree>/", text)
    return None if m is None else shlex.split(m.group(1))


def run_tests_excludes(text: str) -> list[str] | None:
    """The fixed flags after `-a` of `copy_command` in run-tests.jl, or None."""
    m = re.search(r"`rsync -a (.*?) \$\(", text)
    return None if m is None else shlex.split(m.group(1))


def copied(excludes: list[str], tmp: str, name: str) -> list[str]:
    """The files that rsync with `excludes` copies from the fixture, relative to the copy."""
    src, dst = pathlib.Path(tmp) / "pkg", pathlib.Path(tmp) / name
    if not src.exists():
        for f in KEPT + LEFT_OUT:
            (src / f).parent.mkdir(parents=True, exist_ok=True)
            (src / f).write_text("x\n")
    rsync = shutil.which("rsync") or "rsync"
    subprocess.run(
        [rsync, "-a", *excludes, f"{src}/", f"{dst}/"], check=True, capture_output=True, timeout=60
    )
    return sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file())


def spec_gate(tmp: str) -> tuple[dict[str, str], int, str]:
    """Run spec-gate.py on the fixture task file: {part: its line's verdict}, and the exit status."""
    root = pathlib.Path(tmp) / "Research"
    for d in ("Packages/Example/src", "Packages/Other/src", "Harness/scripts", "Tasks"):
        (root / d).mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"| **{p}** | `{r}` | §{k}, §V, §L | x | {t} | open |"
        for k, (p, r, t, _, _) in enumerate(SPEC_PARTS, 1)
    )
    sections = "\n\n".join(
        f"## {k} · part {p}\n\n1. **Done when** — x.\n2. **Decided at the edges** — x.\n"
        f"3. **Tests catch** — x.\n4. **Files** — {files}.\n5. **Not in this part** — x."
        for k, (p, _, _, files, _) in enumerate(SPEC_PARTS, 1)
    )
    task = root / "Tasks" / "plan.md"
    task.write_text(
        "# Plan\n\n## Parts\n\n| part | repository | sections | what it is | tier | state |\n"
        f"|:--|:--|:--|:--|:--|:--|\n{rows}\n\n{sections}\n\n## V\n\nx\n\n## L\n\nx\n"
    )
    env = {**os.environ, "RESEARCH_ROOT": str(root), "HOME": tmp}
    p = subprocess.run(
        [sys.executable, str(SPEC_GATE), str(task), *[s[0] for s in SPEC_PARTS]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    lines = dict(line.split("\t", 1) for line in p.stdout.splitlines() if "\t" in line)
    return {part: rest.split("\t")[0] for part, rest in lines.items()}, p.returncode, p.stderr


def spec_bundle(tmp: str, plan: str) -> tuple[str, str, int]:
    """Run spec-bundle.py for part P on `plan`: (the bundle's text, stderr, exit status)."""
    task = pathlib.Path(tmp) / "plan.md"
    task.write_text(plan)
    out = pathlib.Path(tmp) / "bundle.md"
    p = subprocess.run(
        [sys.executable, str(SPEC_BUNDLE), str(task), "P", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return (out.read_text() if out.exists() else ""), p.stderr, p.returncode


def write_spec(directory: pathlib.Path, **fields: str) -> pathlib.Path:
    """Write the fixture spec with `fields` over SPEC_OK, and its check, into `directory`."""
    (directory / "checks").mkdir(parents=True, exist_ok=True)
    (directory / "checks" / "sign.sh").write_text("true\n")
    spec = directory / "spec.md"
    spec.write_text(SPEC_MD.format(**{**SPEC_OK, **fields}))
    return spec


def spec_validate(spec: pathlib.Path, *args: str) -> tuple[str, int]:
    """Run spec-validate.py: (stdout, exit status)."""
    p = subprocess.run(
        [sys.executable, str(SPEC_VALIDATE), str(spec), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return p.stdout + p.stderr, p.returncode


def spec_format(check: Callable[[object, str], None]) -> None:
    """The cases of a spec in the spec-delta format: the validator, the gate and the bundle."""
    with tempfile.TemporaryDirectory(prefix="harness-spec-format-") as name:
        tmp = pathlib.Path(name)
        base = tmp / "base"
        base.mkdir()
        out, status = spec_validate(write_spec(tmp / "ok"), "--base", str(base))
        check(
            status == 0 and "premise: pass" in out,
            f"spec-validate.py passes the fixture spec -> {status} {out}",
        )
        # an --env name that the script sets itself is the script's own failure, exit 3, never
        # the exit 1 of a failed rule
        for pair in ("JULIA_PROJECT=@.", "BASE=abc1234"):
            out, status = spec_validate(write_spec(tmp / "ok"), "--base", str(base), "--env", pair)
            check(
                status == 3 and "spec-validate.py failed: TypeError" in out,
                f"--env {pair} is the script's own failure, exit 3 -> {status} {out}",
            )
        out, status = spec_validate(write_spec(tmp / "nodomain", domain=""), "--no-run")
        check(
            status == 1 and "rule 8" in out,
            f"a scenario that enforces a reference with no domain fails rule 8 -> {status} {out}",
        )
        out, status = spec_validate(write_spec(tmp / "premise", premise="false"), "--base", str(base))
        check(
            status == 1 and "rule 9" in out,
            f"a premise that fails on the base fails rule 9 -> {status} {out}",
        )
        spec = write_spec(tmp / "mutant")
        spec.write_text(spec.read_text().replace("| MU1 |", "| MU2 |"))
        out, status = spec_validate(spec, "--no-run")
        check(status == 1 and "rule 6" in out, f"a mutant with no row of §4 fails rule 6 -> {status} {out}")

        # a premise that needs a device runs only where --devices names it; elsewhere it is
        # unmeasured (exit 2), never a pass
        spec = write_spec(tmp / "device", premise="false")
        spec.write_text(spec.read_text().replace("- check: `false`", "- check: `false` (device: metal)"))
        out, status = spec_validate(spec, "--base", str(base))
        check(
            status == 2 and "not run (needs metal)" in out and "UNMEASURED" in out,
            f"a device premise with no --devices is unmeasured, exit 2 -> {status} {out}",
        )
        out, status = spec_validate(spec, "--base", str(base), "--devices", "metal")
        check(
            status == 1 and "rule 9" in out, f"with --devices metal the device premise runs -> {status} {out}"
        )

        # rule 10: a `git grep` without -P that uses \b in a check script fails; with -P it passes
        spec = write_spec(tmp / "escape")
        (spec.parent / "checks" / "names.sh").write_text("git grep -nE '\\bfoo\\b' -- src/\n")
        out, status = spec_validate(spec, "--no-run")
        check(
            status == 1 and "rule 10: checks/names.sh:1" in out,
            f"a git grep -E with \\b in a check script fails rule 10 -> {status} {out}",
        )
        (spec.parent / "checks" / "names.sh").write_text("git grep -nP '\\bfoo\\b' -- src/\n")
        out, status = spec_validate(spec, "--no-run")
        check(status == 0, f"the same pattern with -P passes -> {status} {out}")

        # the gate: the delta's checks run on a head; a failure, or a write into the head, fails it
        head = tmp / "head"
        head.mkdir()
        out, status = spec_validate(write_spec(tmp / "gate"), "--head", str(head), "--out", str(tmp / "out"))
        check(
            status == 0 and out.count("check: pass") == 2,
            f"the gate runs the delta's two checks -> {status} {out}",
        )
        out, status = spec_validate(
            write_spec(tmp / "gate-fail", check="false"), "--head", str(head), "--out", str(tmp / "out")
        )
        check(
            status == 1 and "gate:" in out, f"a check that fails on the head fails the gate -> {status} {out}"
        )
        subprocess.run([shutil.which("git") or "git", "init", "-q", str(head)], check=True, timeout=60)
        out, status = spec_validate(
            write_spec(tmp / "gate-write", check="touch written"),
            "--head",
            str(head),
            "--out",
            str(tmp / "out"),
        )
        check(
            status == 1 and "changed `git status" in out,
            f"a check that writes into the head fails the gate -> {status} {out}",
        )
        spec_cell(check, tmp)


def spec_cell(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """spec-gate.py and spec-bundle.py on a part whose cell names `spec`, below `tmp`."""
    git = shutil.which("git") or "git"
    root = tmp / "Research"
    (root / "Packages" / "Example").mkdir(parents=True)
    (root / "Tasks").mkdir()
    task = root / "Tasks" / "plan.md"
    task.write_text(
        "# Plan\n\n## Parts\n\n| part | repository | sections | what it is | tier | state |\n"
        "|:--|:--|:--|:--|:--|:--|\n| **S** | `Example` | spec, §V, §L | x | build | open |\n"
        "| **T** | `Example` | spec, §V, §L | x | build | open |\n\n"
        "## §V · Plan rules\n\nV-RULE.\n\n## §L · The loop\n\n- **The builder also reads:** nothing more.\n"
    )
    write_spec(root / "Tasks" / "Evidence" / "plan" / "S")
    env = {**os.environ, "RESEARCH_ROOT": str(root), "HOME": str(tmp)}
    p = subprocess.run(
        [sys.executable, str(SPEC_GATE), str(task), "S", "T", "--no-run"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    lines = dict(line.split("\t")[:2] for line in p.stdout.splitlines() if "\t" in line)
    check(
        lines.get("S") == "PASS" and lines.get("T") == "MISSING spec" and p.returncode == 1,
        f"spec-gate.py validates S and finds T's spec missing -> {lines} {p.returncode} {p.stderr.strip()}",
    )
    # a part whose device premise did not run is UNMEASURED, exit 2; the premises run on a
    # base exported from a git checkout of the fixture repository
    repo = root / "Packages" / "Example"
    for cmd in (
        ["init", "-q"],
        ["-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "--allow-empty", "-m", "base"],
    ):
        subprocess.run([git, *cmd], cwd=repo, check=True, capture_output=True, timeout=60)
    commit = subprocess.run(
        [git, "rev-parse", "--short=7", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    spec = root / "Tasks" / "Evidence" / "plan" / "S" / "spec.md"
    spec.write_text(
        spec.read_text()
        .replace("1234567", commit)
        .replace(
            "- check: `true`\n- catches: none — a premise",
            "- check: `true` (device: metal)\n- catches: none — a premise",
        )
    )
    p = subprocess.run(
        [sys.executable, str(SPEC_GATE), str(task), "S"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    lines = dict(line.split("\t")[:2] for line in p.stdout.splitlines() if "\t" in line)
    check(
        lines.get("S") == "UNMEASURED metal" and p.returncode == 2,
        f"spec-gate.py reports a device premise not run as UNMEASURED, exit 2 -> {lines} {p.returncode} "
        f"{p.stdout.strip()} {p.stderr.strip()}",
    )
    p = subprocess.run(
        [sys.executable, str(SPEC_GATE), str(task), "S", "--devices", "metal"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    lines = dict(line.split("\t")[:2] for line in p.stdout.splitlines() if "\t" in line)
    check(
        lines.get("S") == "PASS" and p.returncode == 0,
        f"with --devices metal the gate runs it and passes -> {lines} {p.returncode} {p.stdout.strip()}",
    )
    out = tmp / "bundle.md"
    p = subprocess.run(
        [sys.executable, str(SPEC_BUNDLE), str(task), "S", "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    text = out.read_text() if out.exists() else ""
    check(
        p.returncode == 0 and "## 3 · Delta" in text and "V-RULE" in text and "**$SPEC:**" in text,
        f"the bundle of S holds its spec, §V and $SPEC -> {p.returncode} {p.stderr.strip()}",
    )


def script(path: pathlib.Path) -> types.ModuleType:
    """The script at `path` as a module, which runs no `main`."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:  # a `.py` path always has a spec with a source loader
        raise ImportError(f"no module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def timeout_cases(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """A git of spec-validate.py and spec-bundle.py that runs past its timeout is the failure that
    each reports for a git that fails: no status, a rule-9 error, and no commit."""
    validate, bundle = script(SPEC_VALIDATE), script(SPEC_BUNDLE)

    def expired(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, cast("float", kwargs["timeout"]))

    with mock.patch.object(subprocess, "run", expired):
        got = (validate.status(str(tmp)), validate.export(str(tmp), "abc1234", str(tmp)))
        commit = bundle.last_commit(str(tmp / "plan.md"))
    check(
        got == (None, f"rule 9: `git archive abc1234` takes more than 60 s in {tmp}") and commit == "",
        f"a git past its 60 s: status None, the export's rule-9 error, the commit '' -> {got}, {commit!r}",
    )
    message = validate.export(str(tmp), "abc1234", str(tmp))
    check(
        isinstance(message, str) and message.startswith(f"rule 9: `git archive abc1234` fails in {tmp}: "),
        f"a git archive outside a repository fails with a rule-9 error -> {message!r}",
    )


def probe_home(tmp: pathlib.Path, config: dict[str, object], omit: tuple[str, ...] = ()) -> pathlib.Path:
    """A scratch home below `tmp` with every file that a probe names, the stubs in `tmp/stubs`
    (without the names in `omit`) and `config` for them; the home."""
    home, stubs = tmp / "home", tmp / "stubs"
    stubs.mkdir(parents=True)
    stub = PROBE_STUB.replace("{python}", sys.executable).replace("{dir}", str(stubs))
    (home / ".local" / "bin").mkdir(parents=True)
    places = [stubs / n for n in PROBE_STUBS if n not in omit]
    for path in [*places, home / ".local" / "bin" / "srt", home / ".local" / "bin" / "agentbox"]:
        path.write_text(stub)
        path.chmod(0o755)
    (stubs / "config.json").write_text(json.dumps({"git": shutil.which("git"), **config}))
    settings = home / ".config" / "research-harness" / "sandbox"
    settings.mkdir(parents=True)
    for name in PROBE_POLICY.values():
        (settings / f"{name}.json").write_text("{}\n")
    for rel in (*PROBE_READ, *PROBE_APPENDED):
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(f"{PROBE_MARKER}\n")
    for rel in (*PROBE_APPENDED, ".local/bin/agentbox"):
        os.utime(home / rel, (OLD, OLD))
    for rel in PROBE_DIRS:
        (home / rel).mkdir(parents=True, exist_ok=True)
    return home


def probe_run(
    home: pathlib.Path, *args: str, platform: str = "darwin", env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run probe-agentbox.py with `args`, the scratch home, the stubs first on the PATH, and
    sys.platform set to `platform`."""
    path = f"{home.parent / 'stubs'}:/usr/bin:/bin"
    return subprocess.run(
        [sys.executable, "-c", PROBE_RUNNER, platform, str(PROBE), *args],
        cwd=home,
        env={"HOME": str(home), "PATH": path, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )


def stub_log(home: pathlib.Path, name: str) -> list[list[str]]:
    """The lines of the log of the stub `name`, each split into its fields."""
    log = home.parent / "stubs" / f"{name}.log"
    return [line.split("\x1f") for line in log.read_text().splitlines()] if log.exists() else []


def stub_calls(home: pathlib.Path, name: str) -> list[tuple[float, list[str]]]:
    """The calls of the stub `name`: (time, arguments)."""
    return [(float(t), rest) for t, _, *rest in stub_log(home, name)]


def stub_dirs(home: pathlib.Path, name: str) -> set[str]:
    """The working directories of the calls of the stub `name`."""
    return {cwd for _, cwd, *_ in stub_log(home, name)}


def probe_rows(out: pathlib.Path) -> list[list[str]]:
    """The rows of report.tsv below `out`, without the header."""
    tsv = out / "report.tsv"
    return [line.split("\t") for line in tsv.read_text().splitlines()[1:]] if tsv.exists() else []


def probe_refusals(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """Each run that cannot measure the boundary exits 2, with one line that names its cause, and
    calls neither stub nor writes a report."""
    four = "claude, opencode, omp and agy"
    settings = pathlib.PurePosixPath(".config", "research-harness", "sandbox")
    cases: list[tuple[str, list[str], dict[str, str], str, str | None, list[str]]] = [
        ("SANDBOX_RUNTIME set", [], {"SANDBOX_RUNTIME": "1"}, "darwin", None, ["plain terminal"]),
        ("AGENTBOX set", [], {"AGENTBOX": "1"}, "darwin", None, ["plain terminal"]),
        ("AGENTBOX set empty", [], {"AGENTBOX": ""}, "darwin", None, ["plain terminal"]),
        ("the platform linux", [], {}, "linux", None, ["macOS"]),
        ("an unknown frontend", ["codex"], {}, "darwin", None, [four]),
        ("an unknown option", ["--bogus"], {}, "darwin", None, [four]),
        ("a --timeout of 0", ["--timeout", "0"], {}, "darwin", None, [four]),
        ("a --timeout that is no number", ["--timeout", "2s"], {}, "darwin", None, [four]),
        ("a --timeout of a non-ASCII digit", ["--timeout", "٣"], {}, "darwin", None, [four]),
        ("--out with no value", ["--out"], {}, "darwin", None, [four]),
        ("no srt", [], {}, "darwin", ".local/bin/srt", ["harness setup"]),
        ("srt not executable", [], {}, "darwin", "chmod .local/bin/srt", ["harness setup"]),
        ("no agentbox", [], {}, "darwin", ".local/bin/agentbox", ["agentbox", "harness install --apply"]),
        ("no claude.json", ["claude"], {}, "darwin", f"{settings}/claude.json", ["claude.json", "--apply"]),
        ("no antigravity.json", ["agy"], {}, "darwin", f"{settings}/antigravity.json", ["antigravity.json"]),
    ]
    for k, (label, args, env, platform, remove, words) in enumerate(cases):
        home = probe_home(tmp / f"refusal-{k}", {"srt": "refuse"})
        if remove is not None and remove.startswith("chmod "):
            (home / remove.removeprefix("chmod ")).chmod(0o644)
        elif remove is not None:
            (home / remove).unlink()
        out = home / "out"
        # --out last, so that the case of `--out` with no value keeps its own arguments
        argv = args if args == ["--out"] else [*args, "--out", str(out)]
        p = probe_run(home, *argv, platform=platform, env=env)
        lines = p.stderr.splitlines()
        called = [n for n in ("srt", "agentbox") if stub_calls(home, n)]
        check(
            p.returncode == 2
            and len(lines) == 1
            and all(w in lines[0] for w in words)
            and not called
            and not (out / "report.tsv").exists(),
            f"probe-agentbox: {label} exits 2 with one line naming {words}, calls no stub and writes "
            f"no report -> {p.returncode} {p.stderr.strip()!r} called {called}",
        )
    # agy reads antigravity.json: with that file and no agy.json, the run goes on
    home = probe_home(tmp / "refusal-agy", {"srt": "refuse"})
    p = probe_run(home, "--no-model", "agy", "--out", str(home / "out"))
    check(
        p.returncode == 1 and probe_rows(home / "out"),
        f"probe-agentbox: agy with antigravity.json and no agy.json runs -> {p.returncode} {p.stderr[-300:]}",
    )


def probe_refuse_all(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """Under a stub srt that refuses every call, each probe expected refused is match and each
    expected allowed is MISMATCH; srt gets its options before `--`; no agentbox call with --no-model;
    the report's files."""
    home = probe_home(tmp / "refuse", {"srt": "refuse", "lsof": ""})
    settings = home / ".config" / "research-harness" / "sandbox"
    out = home / "out"
    p = probe_run(home, "--no-model", "--out", str(out))
    rows = probe_rows(out)
    check(
        p.returncode == 1, f"probe-agentbox under a refusing srt exits 1 -> {p.returncode} {p.stderr[-300:]}"
    )
    for frontend, policy in PROBE_POLICY.items():
        ids = Counter(r[1] for r in rows if r[0] == frontend)
        want = Counter((*PROBE_SHELL_IDS, *PROBE_MODEL_IDS[frontend]))
        check(
            ids == want,
            f"the report lists each probe of {frontend} once -> {sorted((ids - want) | (want - ids))}",
        )
        wrong = [
            r[1]
            for r in rows
            if r[0] == frontend
            and r[1] in PROBE_SHELL_IDS
            and r[4] != {"refused": "match", "allowed": "MISMATCH"}[r[2]]
            and (r[1], r[4]) not in {("R8", "skipped"), ("X5", "skipped")}
        ]
        skipped = {r[1] for r in rows if r[0] == frontend and r[4] == "skipped"}
        check(
            not wrong
            and skipped == {"X5", *PROBE_MODEL_IDS[frontend], *(["R8"] if frontend == "agy" else [])},
            f"under a refusing srt, {frontend}: refused is match, allowed is MISMATCH -> wrong {wrong}, "
            f"skipped {sorted(skipped)}",
        )
        calls = [a for _, a in stub_calls(home, "srt") if len(a) > 1 and a[1].endswith(f"/{policy}.json")]
        bad = [
            a
            for a in calls
            if len(a) != 6 or a[:5] != ["--settings", str(settings / f"{policy}.json"), "--", "/bin/sh", "-c"]
        ]
        check(
            len(calls) == len(PROBE_SHELL_IDS) - 1 - (frontend == "agy") and not bad,
            f"each srt call of {frontend} is --settings {policy}.json -- /bin/sh -c <probe> -> "
            f"{len(calls)} calls, bad {bad[:2]}",
        )
        # W12 and W13 create in the frontend's own state and in another's; R8 reads its credential
        other = ".local/share/opencode" if frontend == "omp" else ".omp"
        targets = [f"{home}/{PROBE_STATE[frontend]}/agentbox-probe-", f"{home}/{other}/agentbox-probe-"]
        targets += [f"{home}/{c}" for c in PROBE_CREDENTIAL.get(frontend, ())]
        counts = [sum(t in a[-1] for a in calls) for t in targets]
        check(
            counts == [1] * len(targets),
            f"{frontend}: W12, W13 and R8 each name their path once -> {targets} {counts}",
        )
        # N4 asks github.com past srt's proxy: curl with `--noproxy '*'`, once per frontend
        n4 = [a[-1] for a in calls if "--noproxy" in a[-1]]
        words = shlex.split(n4[0]) if len(n4) == 1 else []
        check(
            words[:1] == ["curl"]
            and words[-1:] == ["https://github.com/"]
            and any(words[k : k + 2] == ["--noproxy", "*"] for k in range(len(words))),
            f"{frontend}: N4 is curl --noproxy '*' https://github.com/ -> {n4}",
        )
    r2 = {r[0]: r[4] for r in rows if r[1] == "R2"}
    check(
        r2.get("claude") == "MISMATCH" and r2.get("opencode") == "match",
        f"R2 expects allowed for claude and refused for opencode -> {r2}",
    )
    check(not stub_calls(home, "agentbox"), "with --no-model, agentbox gets no call")
    # no probe ran, so nothing is left to remove or unmount
    cleaning = [a[0] for _, a in stub_calls(home, "launchctl")] + [
        a[0] for _, a in stub_calls(home, "umount")
    ]
    check(
        cleaning == ["list"] * len(PROBE_POLICY),
        f"launchctl remove and umount run only for a job or a mount that is left -> {cleaning}",
    )
    dirs = stub_dirs(home, "srt")
    check(dirs == {str((home / "Research").resolve())}, f"srt runs from ~/Research -> {dirs}")
    lines = (out / "report.tsv").read_text().splitlines() if (out / "report.tsv").exists() else []
    md = (out / "report.md").read_text() if (out / "report.md").exists() else ""
    stdout = p.stdout.splitlines()
    check(
        lines
        and all(len(line.split("\t")) == 6 for line in lines)
        and "`match`: " in md
        and "`MISMATCH`: " in md
        and "agentbox omp" in md
        and "plain `opencode`" not in md
        and stdout[-1:] == [str(out / "report.md")],
        f"report.tsv has six columns, report.md the counts and the omp step (no F6 step with --no-model), "
        f"and stdout ends with its path -> {stdout[-1:]}",
    )


def probe_allow_all(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """Under a stub srt that runs every probe unconfined, each probe expected refused is MISMATCH,
    each expected allowed is match, and the probes leave nothing: no marker line in the report, no
    changed appended file, no probe file, no launchd job, no mount."""
    kaimon = f"julia {os.getpid()} u 3u IPv4 0x1 0t0 TCP 127.0.0.1:2828 (LISTEN)\n"
    home = probe_home(tmp / "allow", {"srt": "allow", "lsof": kaimon, "curl": {"2828": "401"}})
    out = home / "out"
    run = out.resolve() / "run"
    with mock.patch.dict(os.environ, {"HOME": str(home)}):
        script(PROBE).prepare(run)
    os.utime(run / "repo" / ".git" / "config", (OLD, OLD))
    appended = [home / rel for rel in (*PROBE_APPENDED, ".local/bin/agentbox")] + [run / "repo/.git/config"]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in appended}
    p = probe_run(home, "--no-model", "--out", str(out))
    rows = probe_rows(out)
    wrong = [
        f"{r[0]} {r[1]} {r[4]}"
        for r in rows
        if r[1] in PROBE_SHELL_IDS
        and r[4] != {"refused": "MISMATCH", "allowed": "match"}[r[2]]
        and (r[0], r[1]) != ("agy", "R8")
    ]
    check(
        p.returncode == 1 and len(rows) > len(PROBE_SHELL_IDS) and not wrong,
        f"under an srt that allows all, refused is MISMATCH and allowed is match -> {p.returncode} {wrong} "
        f"{p.stderr[-300:]}",
    )
    texts = [p.stdout] + [f.read_text() for f in (out / "report.tsv", out / "report.md") if f.exists()]
    marker = script(PROBE).MARKER.strip()
    check(
        not [t for t in texts if PROBE_MARKER in t or marker in t],
        "no report and no line of stdout holds a marker line",
    )
    changed = [str(p) for p in appended if (p.read_bytes(), p.stat().st_mtime_ns) != before[p]]
    check(not changed, f"each appended file keeps its bytes and its modification time -> {changed}")
    left = [str(x) for x in home.rglob("*agentbox-probe-*")] + [
        str(x) for x in [run / "repo/.git/hooks/pre-commit"] if x.exists()
    ]
    check(not left, f"no probe file is left in the scratch home -> {left}")
    launchctl = [a for _, a in stub_calls(home, "launchctl")]
    submitted = [a[a.index("-l") + 1] for a in launchctl if a[:1] == ["submit"]]
    removed = [a[1] for a in launchctl if a[:1] == ["remove"]]
    order = [a[0] for a in launchctl if a[:1] in (["submit"], ["remove"])]
    check(
        len(submitted) == len(PROBE_POLICY)
        and removed == submitted
        and order == ["submit", "remove"] * len(PROBE_POLICY),
        f"launchctl removes the job of X4 after each submit -> {order} {submitted} {removed}",
    )
    unmounted = [a for _, a in stub_calls(home, "umount")]
    check(
        unmounted == [[str(run / "mnt")]] * len(PROBE_POLICY),
        f"the devfs of X3 is unmounted after each frontend -> {unmounted}",
    )
    x5 = {r[0]: (r[3], r[4]) for r in rows if r[1] == "X5"}
    check(
        x5.get("claude") == ("allowed", "MISMATCH"),
        f"X5 sends kill -0 to the listener on 127.0.0.1:2828 -> {x5}",
    )


def probe_listeners(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """Loopback listeners that answer 401, 200, nothing and 403, and a listener on every interface,
    which is probed at 127.0.0.1; one address and port get one probe, whatever lines name them; a
    socket that does not listen is not probed; X5 takes Kaimon on every interface, not on ::1."""
    lsof = (
        "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
        "alpha 101 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7001 (LISTEN)\n"
        "beta 102 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7002 (LISTEN)\n"
        "gamma 103 u 3u IPv6 0x1 0t0 TCP [::1]:7003 (LISTEN)\n"
        "delta 104 u 3u IPv4 0x1 0t0 TCP *:7004 (LISTEN)\n"
        "epsilon 105 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7005 (LISTEN)\n"
        "eta 110 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7006 (LISTEN)\n"
        "theta 111 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7008 (LISTEN)\n"
        "alphatwo 106 u 4u IPv4 0x1 0t0 TCP 127.0.0.1:7001 (LISTEN)\n"
        "alphawild 108 u 5u IPv6 0x1 0t0 TCP *:7001 (LISTEN)\n"
        "deltasix 109 u 4u IPv6 0x1 0t0 TCP *:7004 (LISTEN)\n"
        "zeta 107 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7007 (CLOSED)\n"
        # no process has this pid, so a kill -0 of it fails
        "other 999999999 u 3u IPv6 0x1 0t0 TCP [::1]:2828 (LISTEN)\n"
        f"julia {os.getpid()} u 3u IPv4 0x1 0t0 TCP *:2828 (LISTEN)\n"
    )
    codes = {
        **{"7001": "401", "7002": "200", "7003": "none", "7004": "200", "7005": "403"},
        **{"7006": "407", "7008": "400", "2828": "401"},
    }
    home = probe_home(tmp / "listen", {"srt": "allow", "lsof": lsof, "curl": codes})
    out = home / "out"
    # claude twice: a frontend named twice runs once
    probe_run(home, "--no-model", "claude", "claude", "--out", str(out))
    rows = probe_rows(out)
    ids = Counter(r[1] for r in rows if r[1].startswith("L:"))
    got = {r[1]: (r[2], r[3], r[4], r[5]) for r in rows if r[1].startswith("L:")}
    check(
        got.get("L:7006", ())[:3] == ("401, 403 or 407", "407", "match")
        and got.get("L:7008", ())[:3] == ("401, 403 or 407", "400", "MISMATCH"),
        f"a listener that answers 407 is match and one that answers 400 is MISMATCH, against 401, 403 "
        f"or 407 -> {got.get('L:7006')} {got.get('L:7008')}",
    )
    got = {r[1]: (r[3], r[4], r[5]) for r in rows if r[1].startswith("L:")}
    l1, l2, l3, l4, l5 = (got.get(f"L:700{k}") for k in (1, 2, 3, 4, 5))
    check(
        ids
        == Counter(("L:7001", "L:7002", "L:7003", "L:7004", "L:7005", "L:7006", "L:7008", "L:2828", "L:2828"))
        and Counter(r[1] for r in rows)["R1"] == 1
        and l1 is not None
        and l1[:2] == ("401", "match")
        and "alpha 127.0.0.1:7001" in l1[2]
        and l5 is not None
        and l5[:2] == ("403", "match")
        and l2 is not None
        and l2[1] == "MISMATCH"
        and "beta 127.0.0.1:7002" in l2[2]
        and l3 is not None
        and l3[1] == "MISMATCH"
        and "gamma [::1]:7003" in l3[2]
        and l4 is not None
        and l4[:2] == ("200", "MISMATCH")
        and "delta 127.0.0.1:7004" in l4[2],
        f"one probe per listener address and port: 401 and 403 are match, 200 and no answer are "
        f"MISMATCH with the command and port -> {got}",
    )
    urls = [a[-1] for _, a in stub_calls(home, "curl") if a[-1].startswith("http://")]
    check(
        "http://[::1]:7003/" in urls
        and urls.count("http://127.0.0.1:7004/") == 1
        and urls.count("http://127.0.0.1:7001/") == 1
        and not [u for u in urls if "*" in u],
        f"an IPv6 listener is asked in brackets, and a listener on every interface once at 127.0.0.1 "
        f"-> {urls}",
    )
    x5 = [(r[3], r[5]) for r in rows if r[1] == "X5"]
    check(
        [g for g, _ in x5] == ["allowed"],
        f"X5 sends kill -0 to Kaimon on *:2828, not to the listener on [::1]:2828 -> {x5}",
    )


def probe_routes(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """An `opencode` listener is asked at `/` and at `/path`, each with a row of its own; a `node`
    listener only at `/`."""
    lsof = (
        "opencode 201 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:4096 (LISTEN)\n"
        "node 202 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7001 (LISTEN)\n"
    )
    codes = {"4096": "200", "4096/path": "401", "7001": "200", "7001/path": "401"}
    home = probe_home(tmp / "routes", {"srt": "allow", "lsof": lsof, "curl": codes})
    out = home / "out"
    probe_run(home, "--no-model", "claude", "--out", str(out))
    got = {r[1]: (r[3], r[4], r[5]) for r in probe_rows(out) if r[1].startswith("L:")}
    check(
        sorted(got) == ["L:4096", "L:4096/path", "L:7001"]
        and got["L:4096"][:2] == ("200", "MISMATCH")
        and got["L:4096/path"][:2] == ("401", "match")
        and got["L:4096/path"][2].startswith("opencode 127.0.0.1:4096")
        and got["L:7001"][:2] == ("200", "MISMATCH"),
        f"opencode has a row at / (200, MISMATCH) and at /path (401, match); node one row at / -> {got}",
    )
    urls = [a[-1] for _, a in stub_calls(home, "curl") if a[-1].startswith("http://")]
    check(
        sorted(urls) == ["http://127.0.0.1:4096/", "http://127.0.0.1:4096/path", "http://127.0.0.1:7001/"],
        f"curl asks opencode at / and /path, node at / only -> {urls}",
    )


def probe_summary(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """report.md gives the listener rows as `## Listeners`, one line per command, status and
    verdict, with the ports in numeric order and the frontends; its table holds no `L:` row, and
    report.tsv holds every one."""
    lsof = (
        "alpha 101 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:56925 (LISTEN)\n"
        "alpha 102 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7001 (LISTEN)\n"
        "alpha 103 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7002 (LISTEN)\n"
        "beta 104 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:7003 (LISTEN)\n"
    )
    codes = {"56925": "401", "7001": "401", "7002": "200", "7003": "403"}
    home = probe_home(tmp / "summary", {"srt": "allow", "lsof": lsof, "curl": codes})
    out = home / "out"
    probe_run(home, "--no-model", "omp", "claude", "--out", str(out))
    tsv = [r for r in probe_rows(out) if r[1].startswith("L:")]
    check(
        Counter((r[0], r[1]) for r in tsv)
        == Counter((f, f"L:{p}") for f in ("omp", "claude") for p in ("56925", "7001", "7002", "7003")),
        f"report.tsv holds every L: row of both frontends -> {sorted((r[0], r[1]) for r in tsv)}",
    )
    md = (out / "report.md").read_text() if (out / "report.md").exists() else ""
    head, _, rest = md.partition("## Listeners\n")
    section = rest.partition("\n## ")[0]
    lines = [line for line in section.splitlines() if line.startswith("- ")]
    want = [
        "- `alpha` answers `401`, `match`: 2 ports (7001, 56925), under omp and claude",
        "- `alpha` answers `200`, `MISMATCH`: 1 port (7002), under omp and claude",
        "- `beta` answers `403`, `match`: 1 port (7003), under omp and claude",
    ]
    check(
        "| L:" not in head and lines == want and "## Counts" in rest,
        f"report.md's table holds no L: row, and ## Listeners one line per command, status and "
        f"verdict, ports in numeric order -> table L: rows {head.count('| L:')}, {lines}",
    )
    counts = rest.partition("## Counts\n")[2].partition("\n## ")[0]
    total = sum(int(line.rpartition(" ")[2]) for line in counts.splitlines() if line.startswith("- `"))
    check(
        total == len(probe_rows(out)) and total > len(tsv),
        f"## Counts counts every row, the L: rows included -> {total} of {len(probe_rows(out))}",
    )


def probe_model(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """The frontend probes call agentbox with the frontend's non-interactive form."""
    opencode = "opencode 201 u 3u IPv4 0x1 0t0 TCP 127.0.0.1:4096 (LISTEN)\n"
    answer = "OK SR=1 AB=1 KAIMON-OK"
    home = probe_home(
        tmp / "model", {"srt": "refuse", "lsof": "", "lsof_opencode": opencode, "answer": answer}
    )
    out = home / "out"
    probe_run(home, "--out", str(out))
    rows = {(r[0], r[1]): (r[3], r[4]) for r in probe_rows(out) if r[1].startswith("F")}
    calls = [a for _, a in stub_calls(home, "agentbox")]
    forms = {
        "claude": [
            ["-p"],
            ["-p", "--allowedTools", "Bash(echo *)"],
            ["-p", "--allowedTools", "Read"],
            ["-p", "--allowedTools", "mcp__kaimon__ping"],
        ],
        "opencode": [["run", "--auto"]] * 5,
        "omp": [["-p"]] * 4,
        "agy": [["--dangerously-skip-permissions", "-p"]] * 4
        + [["--dangerously-skip-permissions", "--sandbox", "-p"]],
    }
    dirs = stub_dirs(home, "agentbox")
    check(dirs == {str((home / "Research").resolve())}, f"agentbox runs from ~/Research -> {dirs}")
    for frontend, want in forms.items():
        mine = [a[1:] for a in calls if a[:1] == [frontend]]
        # the prompt is the one argument that holds a space
        shapes = [[x for x in a if " " not in x or x.startswith("Bash(")] for a in mine]
        prompts = [[x for x in a if " " in x and not x.startswith("Bash(")] for a in mine]
        check(
            shapes == want and all(len(x) == 1 for x in prompts),
            f"agentbox {frontend} gets its non-interactive form and one prompt -> {mine}",
        )
        # the shapes drop the prompt, so they do not show where it stands: `-p` takes it as its value
        after = [a[a.index("-p") + 1 : a.index("-p") + 2] for a in mine if "-p" in a]
        check(
            after == (prompts if "-p" in want[0] else []),
            f"agentbox {frontend}: the argument after -p is the prompt -> {after}",
        )
        check(
            rows.get((frontend, "F2")) == ("holds SR=1 AB=1", "match"),
            f"a canned SR=1 AB=1 makes F2 of {frontend} match -> {rows.get((frontend, 'F2'))}",
        )
        verdicts = [rows.get((frontend, i), ("", ""))[1] for i in ("F1", "F3", "F4")]
        check(
            verdicts == ["match"] * 3,
            f"a canned answer with OK and KAIMON-OK and no READABLE makes F1, F3 and F4 of {frontend} "
            f"match -> {verdicts}",
        )
    check(
        rows.get(("omp", "F7")) == ("unchanged", "unchanged")
        and rows.get(("agy", "F5")) == ("exit 0", "exit 0")
        and rows.get(("opencode", "F6")) == ("holds SR=1 AB=1", "match"),
        f"F5, F6 and F7 -> {[rows.get(k) for k in (('agy', 'F5'), ('opencode', 'F6'), ('omp', 'F7'))]}",
    )


def probe_void(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """Under an agentbox whose answer holds no OK, F1 is MISMATCH, so F3, which expects READABLE to
    be missing, is void; void counts in report.md and does not set the exit status itself."""
    home = probe_home(tmp / "void", {"srt": "refuse", "lsof": "", "lsof_opencode": "", "answer": "no"})
    out = home / "out"
    p = probe_run(home, "--out", str(out))
    rows = {(r[0], r[1]): (r[2], r[4], r[5]) for r in probe_rows(out) if r[1].startswith("F")}
    for frontend in PROBE_POLICY:
        got = [rows.get((frontend, i)) for i in ("F1", "F2", "F3", "F4")]
        check(
            got[0] is not None
            and got[0][1] == "MISMATCH"
            and got[2] == ("lacks READABLE", "void", "F1 shows no start")
            and [g[1] if g else None for g in (got[1], got[3])] == ["MISMATCH", "MISMATCH"],
            f"with an answer without OK, F3 of {frontend} is void and F2 and F4 stay MISMATCH -> {got}",
        )
    md = (out / "report.md").read_text() if (out / "report.md").exists() else ""
    check(
        p.returncode == 1 and f"- `void`: {len(PROBE_POLICY)}" in md,
        f"void counts in report.md -> {p.returncode} {[x for x in md.splitlines() if 'void' in x]}",
    )


def probe_timeout(check: Callable[[object, str], None], tmp: pathlib.Path) -> None:
    """A frontend probe past --timeout is killed with its process group and is `timeout`; the next
    probe runs; a probe whose file is missing is absent; F6 with no opencode listener and a
    frontend with no program are skipped; the exit status."""
    config: dict[str, object] = {
        "srt": "refuse",
        "lsof": "",
        "lsof_opencode": "",
        "answer": "OK SR=1 AB=1",
        "sleep": "claude",
    }
    home = probe_home(tmp / "timeout", config, omit=("omp",))
    # the targets of R1, W6 and W11 are missing: each probe is absent and runs no srt call
    (home / ".ssh" / "config").unlink()
    (home / ".zshrc").unlink()
    (home / ".omp" / "agent" / "extensions").rmdir()
    out = home / "out"
    p = probe_run(home, "--timeout", "2", "claude", "opencode", "omp", "--out", str(out))
    rows = {(r[0], r[1]): (r[4], r[5]) for r in probe_rows(out)}
    absent = [rows.get(("claude", i), ("",))[0] for i in ("R1", "W6", "W11")]
    ran = [a[-1] for _, a in stub_calls(home, "srt") if ".zshrc" in a[-1] or "/extensions/" in a[-1]]
    check(
        absent == ["absent"] * 3 and not ran,
        f"a probe whose file or directory is missing is absent and does not run -> {absent} {ran}",
    )
    starts = [t for t, a in stub_calls(home, "agentbox") if a[:1] == ["claude"]]
    took = starts[1] - starts[0] if len(starts) > 1 else None
    check(
        rows.get(("claude", "F3")) == ("void", "F1 shows no start"),
        f"F3 after an F1 past --timeout is void -> {rows.get(('claude', 'F3'))}",
    )
    check(
        p.returncode == 1
        and rows.get(("claude", "F1"), ("",))[0] == "timeout"
        and rows.get(("claude", "F2"), ("",))[0] == "match"
        and took is not None
        and took < 10,
        f"F1 past --timeout 2 is timeout within 10 s, and F2 runs -> {p.returncode} "
        f"{rows.get(('claude', 'F1'))} {rows.get(('claude', 'F2'))} {took}",
    )
    md = (out / "report.md").read_text() if (out / "report.md").exists() else ""
    check(
        rows.get(("opencode", "F6")) == ("skipped", "start a plain opencode in another terminal")
        and "plain `opencode` in another terminal" in md,
        f"F6 with no opencode listener is skipped; report.md asks for it -> {rows.get(('opencode', 'F6'))}",
    )
    omp = [rows.get(("omp", i)) for i in PROBE_MODEL_IDS["omp"]]
    check(
        omp == [("skipped", "no omp on the PATH")] * 5 and ("omp", "R7") in rows,
        f"omp with no program: its frontend probes are skipped, its shell probes run -> {omp}",
    )
    module = script(PROBE)
    row = module.Row
    status = {
        name: module.exit_status([row("claude", "F1", "", "", v, "") for v in verdicts])
        for name, verdicts in (
            ("timeout", ["match", "timeout"]),
            ("MISMATCH", ["match", "MISMATCH"]),
            ("clean", ["match", "skipped", "absent", "unchanged", "exit 0", "void"]),
        )
    }
    check(
        status == {"timeout": 1, "MISMATCH": 1, "clean": 0},
        f"the exit status is 1 with a timeout or a MISMATCH, 0 otherwise -> {status}",
    )
    probe_units(check, module)


def probe_units(check: Callable[[object, str], None], module: types.ModuleType) -> None:
    """The edges of the judges of curl's statuses, the detail's cut, F7's observation, a shell
    probe and a listener probe past their time limit, and a | in a cell of report.md."""
    judged = {
        (judge, out): getattr(module, judge)(0, out)
        for judge, out in (
            ("reached", "200"),
            ("reached", "399"),
            ("reached", "400"),
            ("reached", "199"),
            ("reached", "000"),
            ("reached", ""),
            ("denied_host", "200 000"),
            ("denied_host", "000 403"),
            ("denied_host", "403 000"),
            ("denied_host", "503 403"),
            ("denied_host", "000 000"),
            ("denied_host", ""),
            ("answered", "200"),
            ("answered", "000"),
            ("answered", ""),
        )
    }
    allowed = {k for k, v in judged.items() if v == "allowed"}
    check(
        allowed == {("reached", "200"), ("reached", "399"), ("denied_host", "200 000"), ("answered", "200")},
        f"N1/N2 reach 200-399; N3 is refused by a 403 in either status or no answer; N4 by no answer "
        f"-> allowed {sorted(allowed)}",
    )
    trace = "SQLiteError: database is locked\n" + "  at frame\n" * 90 + "    at omp-darwin-arm64\n"
    trace = trace[:976] + trace[-24:]
    cut, whole = module.detail(trace), module.detail("b " * 75)
    flat = " ".join(trace.split())
    check(
        len(trace) == 1000
        and len(cut) == 203
        and cut == f"{flat[:100]} … {flat[-100:]}"
        and "SQLiteError" in cut
        and "omp-darwin-arm64" in cut,
        f"a detail of 1000 characters keeps its first and last 100, joined by ' … ' -> {len(cut)} {cut!r}",
    )
    check(
        whole == " ".join(("b " * 75).split()) and len("b " * 75) == 150,
        f"a detail of 150 characters comes back whole, on one line -> {whole!r}",
    )
    edge = [len(module.detail("c" * n)) for n in (200, 201)]
    check(edge == [200, 203], f"a detail of 200 characters is whole, of 201 cut -> {edge}")
    seen = [module.change(*pair) for pair in ((None, None), ("x", "x"), ("x", "y"), (None, "x"), ("x", None))]
    check(
        seen == ["absent", "unchanged", "changed", "changed", "changed"],
        f"F7 records absent, unchanged or changed -> {seen}",
    )

    def expired(_command: str) -> tuple[int | None, str, str]:
        return None, "partial", ""

    row = module.shell_row("claude", module.Probe("W1", "refused", "true"), expired)
    listener = module.listener_row("claude", module.Listener("beta", "102", "127.0.0.1", "7002"), expired)
    check(
        (row.got, row.verdict, listener.verdict) == ("timeout", "timeout", "timeout"),
        f"a shell probe and a listener probe past their limit are timeout -> {row} {listener}",
    )
    with tempfile.TemporaryDirectory(prefix="harness-probe-report-") as name:
        md = module.write_reports(
            pathlib.Path(name), [module.Row("claude", "F1", "holds OK", "lacks OK", "MISMATCH", "a|b")]
        ).read_text()
    check("| a\\|b |" in md, f"a | in a cell of report.md is escaped -> {md.splitlines()[2:3]}")
    check(
        "## Listeners\n\n- none\n" in md,
        f"with no listener row, ## Listeners says none -> {md.partition('## Listeners')[2][:40]!r}",
    )


def probe_cases(check: Callable[[object, str], None]) -> None:
    """The cases of scripts/probe-agentbox.py, each in a scratch home of its own."""
    with tempfile.TemporaryDirectory(prefix="harness-probe-agentbox-") as name:
        tmp = pathlib.Path(name)
        for case in (
            probe_refusals,
            probe_refuse_all,
            probe_allow_all,
            probe_listeners,
            probe_routes,
            probe_summary,
            probe_model,
            probe_void,
            probe_timeout,
        ):
            case(check, tmp)


def selftest() -> tuple[int, int]:
    """The copies leave out `.env` and `.env.*`, and the spec gate refuses a part that spans
    repositories: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok: object, label: str) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  scripts: {label}")

    sources = [
        ("the critic's copy in evidence.md", critic_excludes(EVIDENCE.read_text())),
        ("copy_command in run-tests.jl", run_tests_excludes(RUN_TESTS.read_text())),
    ]
    with tempfile.TemporaryDirectory(prefix="harness-copies-") as tmp:
        # the control: without the flags, the fixture's `.env` files are copied
        control = copied([], tmp, "control")
        check(".env.ts" in control, f"a copy with no flag holds .env.ts -> {control}")
        for k, (label, excludes) in enumerate(sources):
            if excludes is None:
                check(ok=False, label=f"{label}: no rsync command found")
                continue
            files = copied(excludes, tmp, f"copy-{k}")
            check(files == sorted(KEPT), f"{label} leaves out .git, .claude, .env and .env.* -> {files}")
            # rsync writes the temporary copy of `env.ts` as `.env.ts.XXXXXX`, a name the sandbox
            # denies below a session's working directory; no test can set up that deny, so the
            # flag that writes each file under its own name is checked
            check(
                "--inplace" in excludes,
                f"{label} copies env.ts in place, with no temporary .env.* name -> {excludes}",
            )
    with tempfile.TemporaryDirectory(prefix="harness-spec-gate-") as tmp:
        verdicts, status, stderr = spec_gate(tmp)
        check(
            status == 1, f"spec-gate.py exits 1 on a file with a part that spans -> {status} {stderr.strip()}"
        )
        for part, _, tier, files, expected in SPEC_PARTS:
            got = verdicts.get(part, "no line")
            want = expected.split()[0]
            ok = got.startswith(want)
            if ok and want == "SPANS":
                # the line names each repository of the expected pair
                ok = all(name in got for name in expected.split()[1].split("-"))
            check(ok, f"part {part} ({tier}) with {files}: expected {expected} -> {got}")
    with tempfile.TemporaryDirectory(prefix="harness-spec-bundle-") as tmp:
        text, stderr, status = spec_bundle(tmp, BUNDLE_PLAN)
        check(status == 0, f"spec-bundle.py exits 0 when every name resolves -> {status} {stderr.strip()}")
        missing = [s for s in BUNDLE_IN if s not in text]
        check(
            not missing,
            f"the bundle holds the part's sections, §V, §L and what §L names -> missing {missing}",
        )
        leaked = [s for s in BUNDLE_OUT if s in text]
        check(
            not leaked, f"the bundle leaves out other parts, handovers and the state's narration -> {leaked}"
        )
        # the control: a heading that §L names and the file lacks is unresolved
        text, stderr, status = spec_bundle(tmp, BUNDLE_PLAN.replace("## Traps", "## Pitfalls"))
        check(
            status == 1 and "unresolved: *Traps*" in stderr,
            f"a name that matches nothing is unresolved, exit 1 -> {status} {stderr.strip()}",
        )
    spec_format(check)
    probe_cases(check)
    with tempfile.TemporaryDirectory(prefix="harness-script-timeouts-") as tmp:
        timeout_cases(check, pathlib.Path(tmp))
    problems = fix_round_mutants(lambda path: (REPO / path).read_text())
    check(not problems, f"a fix round runs only the mutants that its fix touches -> {problems or 'holds'}")
    # the control: without the section, the case finds the gap
    gap = fix_round_mutants(lambda path: "" if path.endswith("evidence.md") else (REPO / path).read_text())
    check(bool(gap), f"evidence.md without the section is a problem -> {gap}")
    builders = sorted(f"agents/{p.name}" for p in (REPO / "agents").glob("*-builder.md"))
    missing = [b for b in builders if b not in FIX_ROUND_FILES]
    check(
        len(builders) > 1 and not missing,
        f"each builder of agents/ is in FIX_ROUND_FILES: {builders} -> {missing or 'holds'}",
    )
    return total, wrong
