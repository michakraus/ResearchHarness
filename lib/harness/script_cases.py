"""The cases of scripts in scripts/ that need no Julia. No verb of its own; `harness test` runs them.

- The two package copies, the critic's copy in skills/build-part/evidence.md and `copy_command` in
  scripts/run-tests.jl: each is read from its source file and run with rsync on a fixture tree
  that holds a `.env` and `.env.*` files. The sandbox denies those files, so a copy of one leaves
  a temporary file that no one can remove; each copy leaves them out.
- scripts/spec-gate.py on a fixture task file: a part whose **Files** span two repositories is
  SPANS, and one whose files lie in its repository is not.
- The fix round's mutants: skills/build-part/evidence.md defines them in one section, with its
  four rules, and both builders and both build skills point at it.
"""

import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile

from . import REPO

EVIDENCE = REPO / "skills" / "build-part" / "evidence.md"
RUN_TESTS = REPO / "scripts" / "run-tests.jl"
SPEC_GATE = REPO / "scripts" / "spec-gate.py"

# The fixture tree of the copies: what each copy holds, and what it leaves out.
KEPT = ["src/A.jl", "test/runtests.jl", "env.jl"]
LEFT_OUT = [".env", ".env.ts", "test/.env.local", ".git/HEAD", ".claude/scratch/x"]

# The files whose fix round runs only the mutants that the fix touches.
FIX_ROUND_FILES = ["agents/julia-builder.md", "agents/part-builder.md",
                   "skills/build-part/SKILL.md", "skills/build-reviewed/SKILL.md"]

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


def fix_round_mutants(read):
    """The problems of the fix round's mutant rule, with `read(relpath)` giving a file's text: the
    section in evidence.md with its four rules, and a pointer to it in each builder and skill."""
    problems = []
    evidence = read("skills/build-part/evidence.md")
    section = re.search(r"^### A fix round's mutants\n(.*?)(?=^#)", evidence, re.S | re.M)
    if section is None:
        return ["evidence.md has no section `### A fix round's mutants`"]
    for phrase in ("**Round 1 runs the full set**", "**Own**", "**Function**", "**Test**", "**Survivor**",
                   "do not run the earlier lists again"):
        if phrase not in section.group(1):
            problems.append(f"the section lacks {phrase}")
    for path in FIX_ROUND_FILES:
        if "*A fix round's mutants*" not in " ".join(read(path).split()):
            problems.append(f"{path} names no *A fix round's mutants*")
    return problems


def critic_excludes(text):
    """The `--exclude` flags of the critic's rsync in evidence.md, or None."""
    m = re.search(r"`rsync -a ([^`]*?) <worktree>/", text)
    return None if m is None else shlex.split(m.group(1))


def run_tests_excludes(text):
    """The fixed `--exclude` flags of `copy_command` in run-tests.jl, or None."""
    m = re.search(r"`rsync -a (.*?) \$\(", text)
    return None if m is None else shlex.split(m.group(1))


def copied(excludes, tmp, name):
    """The files that rsync with `excludes` copies from the fixture, relative to the copy."""
    src, dst = pathlib.Path(tmp) / "pkg", pathlib.Path(tmp) / name
    if not src.exists():
        for f in KEPT + LEFT_OUT:
            (src / f).parent.mkdir(parents=True, exist_ok=True)
            (src / f).write_text("x\n")
    subprocess.run(["rsync", "-a", *excludes, f"{src}/", f"{dst}/"], check=True, capture_output=True)
    return sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file())


def spec_gate(tmp):
    """Run spec-gate.py on the fixture task file: {part: its line's verdict}, and the exit status."""
    root = pathlib.Path(tmp) / "Research"
    for d in ("Packages/Example/src", "Packages/Other/src", "Harness/scripts", "Tasks"):
        (root / d).mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| **{p}** | `{r}` | §{k}, §V, §L | x | {t} | open |"
                     for k, (p, r, t, _, _) in enumerate(SPEC_PARTS, 1))
    sections = "\n\n".join(f"## {k} · part {p}\n\n1. **Done when** — x.\n2. **Decided at the edges** — x.\n"
                           f"3. **Tests catch** — x.\n4. **Files** — {files}.\n5. **Not in this part** — x."
                           for k, (p, _, _, files, _) in enumerate(SPEC_PARTS, 1))
    task = root / "Tasks" / "plan.md"
    task.write_text("# Plan\n\n## Parts\n\n| part | repository | sections | what it is | tier | state |\n"
                    f"|:--|:--|:--|:--|:--|:--|\n{rows}\n\n{sections}\n\n## V\n\nx\n\n## L\n\nx\n")
    env = {**os.environ, "RESEARCH_ROOT": str(root), "HOME": tmp}
    p = subprocess.run([sys.executable, str(SPEC_GATE), str(task), *[s[0] for s in SPEC_PARTS]],
                       capture_output=True, text=True, env=env)
    lines = dict(line.split("\t", 1) for line in p.stdout.splitlines() if "\t" in line)
    return {part: rest.split("\t")[0] for part, rest in lines.items()}, p.returncode, p.stderr


def selftest():
    """The copies leave out `.env` and `.env.*`, and the spec gate refuses a part that spans
    repositories: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  scripts: {label}")

    sources = [("the critic's copy in evidence.md", critic_excludes(EVIDENCE.read_text())),
               ("copy_command in run-tests.jl", run_tests_excludes(RUN_TESTS.read_text()))]
    with tempfile.TemporaryDirectory(prefix="harness-copies-") as tmp:
        # the control: without the flags, the fixture's `.env` files are copied
        control = copied([], tmp, "control")
        check(".env.ts" in control, f"a copy with no flag holds .env.ts -> {control}")
        for k, (label, excludes) in enumerate(sources):
            if excludes is None:
                check(False, f"{label}: no rsync command found")
                continue
            files = copied(excludes, tmp, f"copy-{k}")
            check(files == sorted(KEPT), f"{label} leaves out .git, .claude, .env and .env.* -> {files}")
    with tempfile.TemporaryDirectory(prefix="harness-spec-gate-") as tmp:
        verdicts, status, stderr = spec_gate(tmp)
        check(status == 1, f"spec-gate.py exits 1 on a file with a part that spans -> {status} {stderr.strip()}")
        for part, _, tier, files, expected in SPEC_PARTS:
            got = verdicts.get(part, "no line")
            want = expected.split()[0]
            ok = got.startswith(want)
            if ok and want == "SPANS":
                # the line names each repository of the expected pair
                ok = all(name in got for name in expected.split()[1].split("-"))
            check(ok, f"part {part} ({tier}) with {files}: expected {expected} -> {got}")
    problems = fix_round_mutants(lambda path: (REPO / path).read_text())
    check(not problems, f"a fix round runs only the mutants that its fix touches -> {problems or 'holds'}")
    # the control: without the section, the case finds the gap
    gap = fix_round_mutants(lambda path: "" if path.endswith("evidence.md") else (REPO / path).read_text())
    check(bool(gap), f"evidence.md without the section is a problem -> {gap}")
    return total, wrong
