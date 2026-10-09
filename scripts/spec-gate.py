"""The spec gate of the build-part skill: does a build part carry its edges and its mutants?

    python3 spec-gate.py "<task file>" [<part> ...]

A `build` part in `Packages/` or `Experiments/` passes when the sections that its `sections` cell
names hold a **Decided at the edges** and a **Tests catch**. With no part named, every open `build`
part of the file is checked: not merged, declined, done or in review. A named part is checked
whatever its state. A part elsewhere — `Environment`, `Library`, the instruction files — is exempt.

One line per part: PASS, MISSING <labels>, or EXEMPT <why>. A section key that matches no heading
is printed as unresolved, because its text cannot be searched. The exit status is 0 when every
checked part passes or is exempt, 1 when one misses a label, and 3 when this script fails.
The parts table comes from `parts-table.awk`, beside this script.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.expanduser("~/Research")
LABELS = ("Decided at the edges", "Tests catch")
CLOSED = re.compile(r"merged|declined|done|PR #")
HEADING = re.compile(r"^(#{2,4})\s+§?([0-9A-Z][0-9A-Za-z.]*)")


def parts(path):
    out = subprocess.run(["awk", "-f", os.path.join(HERE, "parts-table.awk"), path],
                         capture_output=True, text=True, check=True).stdout
    for row in out.splitlines():
        f = row.split("\t")
        if f[0] == "PART" and len(f) >= 6:
            yield f[1], f[2], f[3], f[4], f[5]


def sections(lines):
    """Map each heading key, such as `5V.P14`, `G6` or `4`, to the text up to the next heading of
    the same or a higher level."""
    heads = [(i, len(m.group(1)), m.group(2).rstrip("."))
             for i, l in enumerate(lines) if (m := HEADING.match(l))]
    text = {}
    for j, (i, level, key) in enumerate(heads):
        end = next((k for k, lv, _ in heads[j + 1:] if lv <= level), len(lines))
        text.setdefault(key, "\n".join(lines[i:end]))
    return text


def applies(repository):
    """True for a cell that names a directory of Packages/ or Experiments/, or that describes a
    group of them in words, such as "the packages already in form"."""
    for name in (t.strip(" `()") for t in repository.split(",")):
        first = name.split()[0] if name.split() else ""
        if any(os.path.isdir(os.path.join(RESEARCH, tree, first))
               for tree in ("Packages", "Experiments")) and first:
            return True, ""
    if repository.strip(" `").lower().startswith("the "):
        return True, f"a group in words: {repository!r}"
    return False, repository


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[2].strip())
        return 3
    path, wanted = argv[0], set(argv[1:])
    text = sections(open(path, encoding="utf-8").read().split("\n"))
    seen, failed = set(), False
    for part, repository, cell, tier, state in parts(path):
        if wanted and part not in wanted:
            continue
        if not wanted and (tier != "build" or CLOSED.search(state)):
            continue
        seen.add(part)
        gate, note = applies(repository)
        if not gate:
            print(f"{part}\tEXEMPT\tnot in Packages/ or Experiments/: {note}")
            continue
        keys = [k.strip().lstrip("§") for k in cell.split(",")]
        keys = [k.split()[0] for k in keys if k and k.split()[0] not in ("V", "L")]
        found = [k for k in keys if k in text]
        body = "\n".join(text[k] for k in found)
        missing = [lab for lab in LABELS if lab not in body]
        verdict = "PASS" if not missing else "MISSING " + ", ".join(missing)
        failed |= bool(missing)
        extra = [f"unresolved: {', '.join(k for k in keys if k not in text)}"] if len(found) < len(keys) else []
        if note:
            extra.append(note)
        print("\t".join([part, verdict] + extra))
    for part in sorted(wanted - seen):
        print(f"{part}\tNOT FOUND in the parts table")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # the script's own failure, told apart from a missing label
        print(f"spec-gate.py failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)
