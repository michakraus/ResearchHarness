#!/usr/bin/env python3
r"""The strict validator of a part spec in the spec-delta format.

    python3 spec-validate.py <spec.md> [--repo <checkout> | --base <tree>] [--no-run] [--devices <d,…>] [--env NAME=VALUE ...]
    python3 spec-validate.py <spec.md> --head <tree> --out <dir> [--devices <d,…>] [--env NAME=VALUE ...]

The format is in `skills/plan-parts/spec-format.md`. Planning ends when the first form passes.
The second form is the gate of the build: it runs every `check:` of the delta on a head.

Structural rules, each an error:

1. The four sections exist and are not empty: `## 1 · Living spec`, `## 2 · Change proposal`,
   `## 3 · Delta`, `## 4 · What stays from the plan`.
2. Every `### Requirement:` states SHALL or MUST before its first scenario, and has one or more
   `#### Scenario:`.
3. Every scenario has a `- WHEN` and a `- THEN` bullet, neither of which refers to another block
   ("as in §", "unchanged", "see "), a `- check:` with one or more commands in backticks, and a
   `- catches:` that names a mutant or says `none —` with a reason.
4. A requirement of the delta's MODIFIED part keeps every scenario name of the living requirement
   of the same name, and each such requirement exists in §1.
5. Every file that a command names under `$SPEC/` exists.
6. Every mutant `MU<n>` that a `catches:` of the delta names is a row of §4's mutant table, and
   every row is named by a `catches:` of the delta.
7. The spec states its base: a `**Base.**` line with a commit in backticks.
8. Every scenario of a delta requirement that names a reference — `reference:` in its heading or
   its statement, or a `- reference:` bullet — has a `- domain:` bullet that does not refer to
   another block: the inputs and parameters where the reference's property holds.
9. Every command of §1 exits 0 on the base (not with `--no-run`). `--repo` exports the commit of
   rule 7 from that checkout with `git archive`; `--base` names a tree that holds it already.
10. No `git grep` without `-P`, in a command or in a file under `$SPEC/checks/`, uses `\b`, `\s`,
    `\w` or `\d` (or their capitals): Apple Git's `git grep` ignores them, so the pattern matches
    nothing and the check cannot fail. Use `-P`, or `[[:space:]]` and explicit boundaries.

With `--head`, rules 1–8 and 10 hold, and then every command of §3 runs on the head, in the order
of the file, each once, whichever scenarios name it: a failure is an error. A check writes only
under `$OUT`: where the head is a git tree, a change of `git status --porcelain --ignored` across
the checks is an error too.

A `- check:` bullet that ends in `(device: <name>[, <name>…])` needs that device, such as `metal`.
Its commands run only where `--devices` names every device the bullet needs; elsewhere each prints
`not run (needs <names>)` and counts as unmeasured, never as a pass. The Bash sandbox has no GPU,
so a device command runs from a Kaimon session (`skills/plan-parts/spec-format.md`).

Each command runs in bash from the root of the tree, with `SPEC` the directory of the spec, `OUT`
the `--out` directory (with `--head`) or a new temporary one, `BASE` the commit of rule 7,
`RESEARCH_ROOT` ($RESEARCH_ROOT, else ~/Research), each `--env` pair, and `JULIA_PROJECT` empty.

One line per command (`premise:` or `check:`, then `pass`, `exit <n>` or `not run (needs …)`), one
line per error, then `PASS`, `UNMEASURED (<n> commands need <devices>)` or `FAIL (<n> errors)`.
Exit 0 on a pass, 2 when every command that ran passed and a device command did not run, 1 on a
fail, and 3 when this script fails.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

SECTIONS = ["1 · Living spec", "2 · Change proposal", "3 · Delta", "4 · What stays from the plan"]
REQ = re.compile(r"^### Requirement: (.+?)\s*$")
SCEN = re.compile(r"^#### Scenario: (.+?)\s*$")
NOTE = re.compile(r"as in §|\bunchanged\b|\bsee\b", re.I)
MUTANT = re.compile(r"\bMU\d+\b")
BASE = re.compile(r"\*\*Base\.\*\*.*?`([0-9a-f]{7,40})`")
REFERENCE = re.compile(r"\breference:", re.I)
DEVICE = re.compile(r"\(device:\s*([A-Za-z0-9_]+(?:\s*,\s*[A-Za-z0-9_]+)*)\)\s*$")
GIT_GREP = re.compile(r"\bgit\s+grep\b")
PERL = re.compile(r"(?:^|\s)(?:-[A-Za-z]*P[A-Za-z]*|--perl-regexp)(?:\s|$)")
ESCAPE = re.compile(r"\\[bBsSwWdD]")


def grep_escape(line):
    """Rule 10: a line, not a comment, with a `git grep` that has no `-P` and uses an escape that
    Apple Git ignores. Each command of a pipeline or a list is read on its own, so a `\\s` in the
    `grep` after a pipe does not count."""
    if line.lstrip().startswith("#"):
        return False
    return any(
        GIT_GREP.search(seg) and not PERL.search(seg) and ESCAPE.search(seg)
        for seg in re.split(r"\||;|&&", line)
    )


RULE10 = "`git grep` without -P uses `\\b`, `\\s`, `\\w` or `\\d`, which this Git ignores"


def sections(lines):
    """{title: (start, end)} of each `## ` section."""
    heads = [(i, l[3:].strip()) for i, l in enumerate(lines) if l.startswith("## ")]
    out = {}
    for k, (i, t) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        # a title may go on after the section's name: `1 · Living spec — Example at …`
        key = next((s for s in SECTIONS if t == s or t.startswith(s + " ")), t)
        out[key] = (i, end)
    return out


def requirements(lines, start, end):
    """Each requirement of lines[start:end]: its heading's name, its kind (living, MODIFIED,
    ADDED, REMOVED), the text before its first scenario, and its scenarios as (name, body lines)."""
    reqs, kind = [], "living"
    i = start
    while i < end:
        l = lines[i]
        if l.startswith("### ") and not REQ.match(l):
            kind = (
                "MODIFIED"
                if "MODIFIED" in l
                else "ADDED"
                if "ADDED" in l
                else "REMOVED"
                if "REMOVED" in l
                else kind
            )
        m = REQ.match(l)
        if m:
            j = i + 1
            while j < end and not lines[j].startswith("### ") and not lines[j].startswith("## "):
                j += 1
            body = lines[i + 1 : j]
            first = next((k for k, b in enumerate(body) if SCEN.match(b)), len(body))
            scens, k = [], first
            while k < len(body):
                n = SCEN.match(body[k])
                if n is None:  # k is the first scenario line, or the one the inner loop stopped at
                    raise ValueError(f"line {i + k + 2}: no `#### Scenario:` heading")
                e = k + 1
                while e < len(body) and not SCEN.match(body[e]):
                    e += 1
                scens.append((n.group(1), body[k + 1 : e]))
                k = e
            reqs.append(
                {
                    "name": m.group(1),
                    "kind": kind,
                    "statement": "\n".join(body[:first]),
                    "scenarios": scens,
                    "line": i + 1,
                }
            )
            i = j
        else:
            i += 1
    return reqs


def bullet(body, key):
    """The text of the bullet `- <key>` with its continuation lines, or None."""
    for i, l in enumerate(body):
        if l.startswith(f"- {key}"):
            text = [l[len(f"- {key}") :]]
            for c in body[i + 1 :]:
                if not (c.startswith(" ") and c.strip()):
                    break
                text.append(c)
            return "\n".join(text).strip()
    return None


def commands(check):
    return [c.strip() for c in re.findall(r"`([^`]+)`", check or "")]


def structure(spec, lines):
    """Rules 1–8 and 10: (errors, the premise commands, the delta's commands, the base commit);
    each command maps to the set of devices it needs."""
    errors = []
    err = errors.append
    secs = sections(lines)
    for s in SECTIONS:
        if s not in secs:
            err(f"rule 1: no section `## {s}`")
        elif not any(x.strip() for x in lines[secs[s][0] + 1 : secs[s][1]]):
            err(f"rule 1: section `## {s}` is empty")
    base = next((m.group(1) for l in lines if (m := BASE.search(l))), None)
    if base is None:
        err("rule 7: no `**Base.**` line with a commit in backticks")
    if any(e.startswith("rule 1") for e in errors):
        return errors, [], [], base

    living = requirements(lines, *secs[SECTIONS[0]])
    delta = requirements(lines, *secs[SECTIONS[2]])

    used_mutants = set()
    # each command, in the order of the file, with the devices its bullets need
    premise_cmds, delta_cmds = {}, {}
    for r in living + delta:
        where = f"line {r['line']}, requirement `{r['name']}`"
        if not re.search(r"\b(SHALL|MUST)\b", r["statement"]):
            err(f"rule 2: {where} states no SHALL or MUST before its first scenario")
        if not r["scenarios"]:
            err(f"rule 2: {where} has no scenario")
        referenced = r["kind"] != "living" and bool(REFERENCE.search(r["name"] + "\n" + r["statement"]))
        for name, body in r["scenarios"]:
            w = f"{where}, scenario `{name}`"
            for key in ("WHEN", "THEN"):
                t = bullet(body, key)
                if t is None:
                    err(f"rule 3: {w} has no `- {key}`")
                elif NOTE.search(t):
                    err(f"rule 3: {w}: `- {key}` refers to another block: {t.splitlines()[0]}")
            check = bullet(body, "check:")
            cmds = commands(check)
            tag = DEVICE.search(check or "")
            devices = {d.strip().lower() for d in tag.group(1).split(",")} if tag else set()
            if not cmds:
                err(f"rule 3: {w} has no `- check:` with a command in backticks")
            catches = bullet(body, "catches:")
            if not catches:
                err(f"rule 3: {w} has no `- catches:`")
            elif catches.startswith("none") and not re.match(r"none\s+—\s+\S", catches):
                err(f"rule 3: {w}: `catches: none` gives no reason")
            elif not catches.startswith("none") and not MUTANT.search(catches):
                err(f"rule 3: {w}: `catches:` names no mutant MU<n>")
            if r["kind"] != "living":
                used_mutants |= set(MUTANT.findall(catches or ""))
                if referenced or bullet(body, "reference:") is not None:
                    domain = bullet(body, "domain:")
                    if not domain:
                        err(f"rule 8: {w} enforces a reference and has no `- domain:`")
                    elif NOTE.search(domain):
                        err(f"rule 8: {w}: `- domain:` refers to another block: {domain.splitlines()[0]}")
            for c in cmds:
                for f in re.findall(r'"?\$SPEC"?/([^\s"]+)', c):
                    if not (spec.parent / f).exists():
                        err(f"rule 5: {w}: `$SPEC/{f}` does not exist")
                if grep_escape(c):
                    err(f"rule 10: {w}: {RULE10}: {c}")
                into = premise_cmds if r["kind"] == "living" else delta_cmds
                into.setdefault(c, set()).update(devices)

    # a living name may end in its capability, `(`field-and-march`)`, which the delta omits
    def bare(name):
        return re.sub(r"\s*\([^()]*\)\s*$", "", name)

    by_name = {bare(r["name"]): r for r in living}
    for r in delta:
        if r["kind"] != "MODIFIED":
            continue
        old = by_name.get(bare(r["name"]))
        if old is None:
            err(f"rule 4: MODIFIED `{r['name']}` has no living requirement of that name")
            continue
        new_names = {n for n, _ in r["scenarios"]}
        for n, _ in old["scenarios"]:
            if n not in new_names:
                err(f"rule 4: MODIFIED `{r['name']}` drops the living scenario `{n}`")

    b, e = secs[SECTIONS[3]]
    table = {m for l in lines[b:e] if l.startswith("| MU") for m in MUTANT.findall(l.split("|")[1])}
    for m in sorted(used_mutants - table):
        err(f"rule 6: `{m}` is named by a `catches:` and is no row of §4's table")
    for m in sorted(table - used_mutants):
        err(f"rule 6: `{m}` is a row of §4's table and no `catches:` of the delta names it")

    checks = spec.parent / "checks"
    for f in sorted(p for p in checks.rglob("*") if p.is_file()) if checks.is_dir() else []:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if grep_escape(line):
                err(f"rule 10: {f.relative_to(spec.parent)}:{n}: {RULE10}: {line.strip()}")
    return errors, premise_cmds, delta_cmds, base


def status(tree: str) -> str | None:
    """`git status --porcelain --ignored` of a git tree, or None for any other tree and for a git
    that runs longer than 60 s."""
    try:
        p = subprocess.run(
            [shutil.which("git") or "git", "status", "--porcelain", "--ignored"],
            cwd=tree,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None
    return p.stdout if p.returncode == 0 else None


def export(repo: str, base: str, tree: str) -> str | None:
    """Write the files of the commit `base` of the checkout `repo` into `tree`; the error, or None.
    A `git archive` that fails or runs longer than 60 s is an error; a `tar` that fails raises."""
    try:
        archive = subprocess.run(
            [shutil.which("git") or "git", "archive", base],
            cwd=repo,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return f"rule 9: `git archive {base}` takes more than 60 s in {repo}"
    if archive.returncode != 0:
        return f"rule 9: `git archive {base}` fails in {repo}: {archive.stderr.decode().strip()}"
    subprocess.run(
        [shutil.which("tar") or "tar", "-x", "-C", tree], input=archive.stdout, check=True, timeout=60
    )
    return None


def run(cmds, tree, env, label, errors, rule, on, devices, unmeasured):
    """Run each command from `tree`; an error with the last 20 lines of each failure. A command
    that needs a device `devices` lacks is not run, and goes to `unmeasured`."""
    for c, needs in cmds.items():
        missing = sorted(needs - devices)
        if missing:
            print(f"{label}: not run (needs {', '.join(missing)}): {c}")
            unmeasured.append((c, missing))
            continue
        p = subprocess.run(  # no timeout: a check may run a whole suite, which bounds each part itself
            ["bash", "-c", cast("str", c)],  # noqa: S607 -- bash runs from PATH
            cwd=cast("str", tree),
            env=cast("dict[str, str]", env),
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"{label}: {'pass' if p.returncode == 0 else f'exit {p.returncode}'}: {c}")
        if p.returncode != 0:
            tail = (p.stdout + p.stderr).strip().splitlines()[-20:]
            errors.append(f"{rule}: `{c}` fails on the {on}:\n    " + "\n    ".join(tail))


def main():
    ap = argparse.ArgumentParser(description="The strict validator of a spec in the spec-delta format.")
    ap.add_argument("spec")
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--repo", help="a checkout that holds the base commit")
    where.add_argument("--base", help="a tree at the base commit")
    where.add_argument("--head", help="a tree at the head: run the delta's checks")
    ap.add_argument("--out", help="the directory of $OUT, with --head")
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--devices", default="", help="the devices present, such as metal")
    ap.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    a = ap.parse_args()
    if a.head and not a.out:
        ap.error("--head needs --out")
    if not (a.repo or a.base or a.head or a.no_run):
        ap.error("give --repo, --base or --head, or --no-run")

    spec = Path(a.spec).resolve()
    errors, premises, checks, base = structure(spec, spec.read_text(encoding="utf-8").splitlines())
    research = os.environ.get("RESEARCH_ROOT") or os.path.expanduser("~/Research")
    extra = dict(pair.split("=", 1) for pair in a.env)
    devices = {d.strip().lower() for d in a.devices.split(",") if d.strip()}
    unmeasured = []

    if not errors and not a.no_run:
        with tempfile.TemporaryDirectory(prefix="spec-validate-") as tmp:
            out = Path(a.out).resolve() if a.out else Path(tmp) / "out"
            out.mkdir(parents=True, exist_ok=True)
            env = dict(
                os.environ,
                SPEC=str(spec.parent),
                OUT=str(out),
                BASE=base,
                RESEARCH_ROOT=research,
                JULIA_PROJECT="",
                **extra,
            )
            if a.head:
                tree = str(Path(a.head).resolve())
                before = status(tree)
                run(checks, tree, env, "check", errors, "gate", "head", devices, unmeasured)
                after = status(tree)
                if before != after:
                    errors.append("gate: the checks changed `git status --porcelain --ignored` of the head")
            else:
                tree = a.base
                if a.repo:
                    tree = str(Path(tmp) / "base")
                    os.mkdir(tree)
                    error = export(cast("str", a.repo), cast("str", base), tree)
                    if error is not None:
                        cast("list[str]", errors).append(error)
                if not errors:
                    run(premises, tree, env, "premise", errors, "rule 9", "base", devices, unmeasured)

    for x in errors:
        print(x)
    if errors:
        print(f"FAIL ({len(errors)} errors)")
        return 1
    if unmeasured:
        needed = sorted({d for _, missing in unmeasured for d in missing})
        print(f"UNMEASURED ({len(unmeasured)} commands need {', '.join(needed)})")
        return 2
    print("PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,  # an --env name that the script sets itself: `dict()` gets it twice
    ) as e:  # the script's own failure, told apart from a failed rule
        print(f"spec-validate.py failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)
