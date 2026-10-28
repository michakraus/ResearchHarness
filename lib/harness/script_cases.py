"""The cases of scripts in scripts/ that need no Julia. No subcommand of its own; `harness test`
runs them.

- The two package copies, the critic's copy in skills/build-part/evidence.md and `copy_command` in
  scripts/run-tests.jl: each is read from its source file and run with rsync on a fixture tree
  that holds a `.env` and `.env.*` files. The sandbox denies those files, so a copy of one leaves
  a temporary file that no one can remove; each copy leaves them out.
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
- The fix round's mutants: skills/build-part/evidence.md defines them in one section, with its
  four rules, and both builders and both build skills point at it.
"""

import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable

from . import REPO

EVIDENCE = REPO / "skills" / "build-part" / "evidence.md"
RUN_TESTS = REPO / "scripts" / "run-tests.jl"
SPEC_GATE = REPO / "scripts" / "spec-gate.py"
SPEC_BUNDLE = REPO / "scripts" / "spec-bundle.py"
SPEC_VALIDATE = REPO / "scripts" / "spec-validate.py"

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
KEPT = ["src/A.jl", "test/runtests.jl", "env.jl"]
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
    """The `--exclude` flags of the critic's rsync in evidence.md, or None."""
    m = re.search(r"`rsync -a ([^`]*?) <worktree>/", text)
    return None if m is None else shlex.split(m.group(1))


def run_tests_excludes(text: str) -> list[str] | None:
    """The fixed `--exclude` flags of `copy_command` in run-tests.jl, or None."""
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
    subprocess.run([rsync, "-a", *excludes, f"{src}/", f"{dst}/"], check=True, capture_output=True)
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
        [sys.executable, str(SPEC_VALIDATE), str(spec), *args], capture_output=True, text=True, check=False
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
        subprocess.run([shutil.which("git") or "git", "init", "-q", str(head)], check=True)
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
        subprocess.run([git, *cmd], cwd=repo, check=True, capture_output=True)
    commit = subprocess.run(
        [git, "rev-parse", "--short=7", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
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
        [sys.executable, str(SPEC_GATE), str(task), "S"], capture_output=True, text=True, env=env, check=False
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
    )
    text = out.read_text() if out.exists() else ""
    check(
        p.returncode == 0 and "## 3 · Delta" in text and "V-RULE" in text and "**$SPEC:**" in text,
        f"the bundle of S holds its spec, §V and $SPEC -> {p.returncode} {p.stderr.strip()}",
    )


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
    problems = fix_round_mutants(lambda path: (REPO / path).read_text())
    check(not problems, f"a fix round runs only the mutants that its fix touches -> {problems or 'holds'}")
    # the control: without the section, the case finds the gap
    gap = fix_round_mutants(lambda path: "" if path.endswith("evidence.md") else (REPO / path).read_text())
    check(bool(gap), f"evidence.md without the section is a problem -> {gap}")
    return total, wrong
