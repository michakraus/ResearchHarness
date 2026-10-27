"""The spec gate of the build-part skill: does a build part carry its edges and its mutants?

    python3 spec-gate.py "<task file>" [<part> ...] [--no-run] [--devices <d,…>]

A `build` part in `Packages/` or `Experiments/` passes when the sections that its `sections` cell
names hold a **Decided at the edges** and a **Tests catch**. With no part named, every open `build`
part of the file is checked: not merged, declined, done or in review. A named part is checked
whatever its state. A part elsewhere — `Environment`, `Library`, the instruction files — is exempt.

A part whose `sections` cell names `spec` has a spec in the spec-delta format, at
`Evidence/<task file's name>/<part>/spec.md` beside the task file, and is checked wherever it
lies: it passes when `spec-validate.py` passes it, with its premises run on the base commit of its
repository's main checkout (`--no-run`: the structure only). Otherwise it is MISSING spec, or
INVALID <n> errors, with the validator's lines below it, indented. A premise that needs a device
(`(device: metal)`) runs only where `--devices` names it; where it does not, the part is
UNMEASURED <devices>, which is no pass: run the gate again from a Kaimon session, which has the
GPU, with `--devices`.

Every checked part, exempt or not, has its **Files** in one repository: a path in the **Files**
of its sections that lies in another repository of the tree (`Tasks/…`, `Harness/…`,
`Packages/<Other>/…`, `~/.claude/…`) is SPANS <repositories>. An isolated builder cannot write
outside its own worktree, so such a file is a dispatcher step of its own, named in the part. A
`direct` part runs in the main session or a workflow, with no isolated builder, and is not checked
for it. A section that several parts name gives each of them its **Files**.

One line per part: PASS, MISSING <labels>, INVALID <n> errors, UNMEASURED <devices>,
SPANS <repositories>, or EXEMPT <why>. A section key
that matches no heading is printed as unresolved, because its text cannot be searched. The exit
status is 0 when every checked part passes or is exempt, 1 when one misses a label, is invalid
or spans repositories, 2 when none of those holds and a part is unmeasured, and 3 when this
script fails. The parts table comes from `parts-table.awk`, beside
this script. The research root is $RESEARCH_ROOT, else ~/Research.
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.environ.get("RESEARCH_ROOT") or os.path.expanduser("~/Research")
# The trees whose directories are each a repository; any other top-level directory is one.
TREES = ("Packages", "Experiments", "Papers", "Books", "Projects")
# A **Files** label, up to the next numbered or bold label, or the next heading.
FILES = re.compile(r"\*\*Files[:.]?\*\*:?(.*?)(?=\n\s*\d+\.\s+\*\*|\n\s*\*\*|\n#|\Z)", re.DOTALL)
PATH = re.compile(r"`([^`\s]*/[^`\s]*)`")
LABELS = ("Decided at the edges", "Tests catch")
CLOSED = re.compile(r"merged|declined|done|PR #")
HEADING = re.compile(r"^(#{2,4})\s+§?([0-9A-Z][0-9A-Za-z.]*)")


def parts(path):
    out = subprocess.run(
        ["awk", "-f", os.path.join(HERE, "parts-table.awk"), path], capture_output=True, text=True, check=True
    ).stdout
    for row in out.splitlines():
        f = row.split("\t")
        if f[0] == "PART" and len(f) >= 6:
            yield f[1], f[2], f[3], f[4], f[5]


def sections(lines):
    """Map each heading key, such as `5V.P14`, `G6` or `4`, to the text up to the next heading of
    the same or a higher level."""
    heads = [
        (i, len(m.group(1)), m.group(2).rstrip(".")) for i, l in enumerate(lines) if (m := HEADING.match(l))
    ]
    text = {}
    for j, (i, level, key) in enumerate(heads):
        end = next((k for k, lv, _ in heads[j + 1 :] if lv <= level), len(lines))
        text.setdefault(key, "\n".join(lines[i:end]))
    return text


def applies(repository):
    """True for a cell that names a directory of Packages/ or Experiments/, or that describes a
    group of them in words, such as "the packages already in form"."""
    for name in (t.strip(" `()") for t in repository.split(",")):
        first = name.split()[0] if name.split() else ""
        if (
            any(os.path.isdir(os.path.join(RESEARCH, tree, first)) for tree in ("Packages", "Experiments"))
            and first
        ):
            return True, ""
    if repository.strip(" `").lower().startswith("the "):
        return True, f"a group in words: {repository!r}"
    return False, repository


def home(repository):
    """The repository of a part's `repository` cell, as a key such as `Packages/Example`; a group
    in words, such as "the 16 repositories with …", is its own key."""
    if repository.strip(" `").lower().startswith("the "):
        return repository.strip(" `")
    name = repository.strip(" `").split(",")[0].strip(" `()")
    first = name.split()[0] if name.split() else ""
    for tree in ("Packages", "Experiments"):
        if first and os.path.isdir(os.path.join(RESEARCH, tree, first)):
            return f"{tree}/{first}"
    return first


def repository_of(path, own):
    """The repository key of a path in a part's **Files**; `own` for a path inside the part's own."""
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        rel = os.path.relpath(expanded, RESEARCH)
        if rel.startswith(".."):
            outside = os.path.relpath(expanded, os.path.expanduser("~"))
            return "~/" + outside.split("/")[0] if not outside.startswith("..") else expanded
    else:
        rel = path
        first = rel.split("/")[0]
        own_dir = os.path.join(RESEARCH, own)
        if not os.path.isdir(os.path.join(RESEARCH, first)) or os.path.exists(os.path.join(own_dir, first)):
            return own
    segments = rel.split("/")
    return "/".join(segments[:2]) if segments[0] in TREES and len(segments) > 2 else segments[0]


def spans(body, own):
    """The repositories that the **Files** of a part's text name, when there are more than one."""
    keys = {own}
    for m in FILES.finditer(body):
        keys |= {repository_of(p, own) for p in PATH.findall(m.group(1))}
    return sorted(keys) if len(keys) > 1 else []


def spec_path(path, part):
    """The spec of a part in the spec-delta format: Evidence/<task file's name>/<part>/spec.md."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(path)), "Evidence", stem, part, "spec.md")


def validate(spec, own, no_run, devices):
    """Run spec-validate.py on a spec: (its exit status, 0, 1 or 2, and its lines)."""
    checkout = os.path.join(RESEARCH, own)
    where = ["--no-run"] if no_run or not os.path.isdir(checkout) else ["--repo", checkout]
    p = subprocess.run(
        [sys.executable, os.path.join(HERE, "spec-validate.py"), spec, *where, "--devices", devices],
        capture_output=True,
        text=True,
    )
    if p.returncode not in (0, 1, 2):
        raise RuntimeError(f"spec-validate.py exits {p.returncode}: {p.stderr.strip()}")
    lines = [
        l for l in p.stdout.splitlines() if not l.startswith(("premise: pass", "PASS", "FAIL", "UNMEASURED"))
    ]
    if where == ["--no-run"] and not no_run:
        lines.append(f"premises not run: no checkout at {checkout}")
    return p.returncode, lines


def main(argv):
    no_run = "--no-run" in argv
    argv = [a for a in argv if a != "--no-run"]
    devices = ""
    if "--devices" in argv:
        k = argv.index("--devices")
        devices, argv = argv[k + 1], argv[:k] + argv[k + 2 :]
    if not argv:
        print(__doc__.strip().splitlines()[2].strip())
        return 3
    path, wanted = argv[0], set(argv[1:])
    text = sections(open(path, encoding="utf-8").read().split("\n"))
    seen, failed, unmeasured = set(), False, False
    for part, repository, cell, tier, state in parts(path):
        if wanted and part not in wanted:
            continue
        if not wanted and (tier != "build" or CLOSED.search(state)):
            continue
        seen.add(part)
        keys = [k.strip().lstrip("§") for k in cell.split(",")]
        keys = [k.split()[0] for k in keys if k and k.split()[0] not in ("V", "L")]
        spec = spec_path(path, part) if "spec" in keys else None
        keys = [k for k in keys if k != "spec"]
        if spec and not os.path.isfile(spec):
            print(f"{part}\tMISSING spec\t{os.path.relpath(spec, os.path.dirname(os.path.abspath(path)))}")
            failed = True
            continue
        found = [k for k in keys if k in text]
        body = "\n".join([text[k] for k in found] + ([open(spec, encoding="utf-8").read()] if spec else []))
        across = spans(body, home(repository)) if tier != "direct" else []
        if across:
            print(
                f"{part}\tSPANS {', '.join(across)}\ta file in another repository is a dispatcher step of its own"
            )
            failed = True
            continue
        if spec:
            code, lines = validate(spec, home(repository), no_run, devices)
            errors = [l for l in lines if l.startswith("rule ")]
            needs = sorted(
                {
                    d.strip()
                    for l in lines
                    if (m := re.search(r"not run \(needs ([^)]*)\)", l))
                    for d in m.group(1).split(",")
                }
            )
            verdict = {0: "PASS", 1: f"INVALID {len(errors)} errors", 2: f"UNMEASURED {', '.join(needs)}"}
            print(f"{part}\t{verdict[code]}")
            for line in lines:
                print("  " + line)
            failed |= code == 1
            unmeasured |= code == 2
            continue
        gate, note = applies(repository)
        if not gate:
            print(f"{part}\tEXEMPT\tnot in Packages/ or Experiments/: {note}")
            continue
        missing = [lab for lab in LABELS if lab not in body]
        verdict = "PASS" if not missing else "MISSING " + ", ".join(missing)
        failed |= bool(missing)
        extra = (
            [f"unresolved: {', '.join(k for k in keys if k not in text)}"] if len(found) < len(keys) else []
        )
        if note:
            extra.append(note)
        print("\t".join([part, verdict] + extra))
    for part in sorted(wanted - seen):
        print(f"{part}\tNOT FOUND in the parts table")
        failed = True
    return 1 if failed else 2 if unmeasured else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # the script's own failure, told apart from a missing label
        print(f"spec-gate.py failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)
