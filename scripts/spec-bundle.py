"""The spec bundle of a part: every text of a task file that the part's builder and critics read.

    python3 spec-bundle.py "<task file>" <part> [--out <file>]

A builder or a critic of the builder-critic loop reads one file, not line ranges of the task file.
The bundle holds, in this order:

1. the part's `PART` row and the `COLLISION` rows that name it, from `parts-table.awk`;
2. each section that the part's `sections` cell names, by its heading key (`§M5`, `§5V.P38b`,
   `§6`), and for a key with no heading, such as a T-number, each table row whose first cell is
   the key, under its table's header; for the key `spec`, the part's spec in the spec-delta format,
   `Evidence/<task file's name>/<part>/spec.md` beside the task file, whole, and the header names
   its directory as `$SPEC`;
3. §V and §L;
4. each section that §L's two lines **The builder also reads:** and **The critic also reads:**
   name: a key (`§6`), a heading in italics (`*Traps*`), or the preamble of a key (`the preamble
   of §10`, the text up to its first subheading). A phrase that starts with "the part's", "its",
   "the publish task" or names no key or heading refers to the cell or to another file, and adds
   nothing; "nothing more" adds nothing.

A section is included once, at its first place. The header gives the task file, the commit of the
task file's repository, the line range of each section, the size, and a SHA-256 of the body, so a
report can name the bundle it read. Every decision line of the part (`**Decided (…)**`) is in its
section and so in the bundle.

One line on stdout: the output path, the line count and the hash. Each name that matches nothing is
printed on stderr as `unresolved: <name>`. The exit status is 0 when every name resolves, 1 when
one does not or the part is not in the table, and 3 when this script fails. With no `--out`, the
bundle goes to stdout and the summary to stderr.
"""

import hashlib
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("spec_gate", os.path.join(HERE, "spec-gate.py"))
spec_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spec_gate)

HEADING = re.compile(r"^(#{1,4})\s+(.*?)\s*$")
KEY = spec_gate.HEADING
ALSO = re.compile(r"^\s*-\s*\*\*The (builder|critic) also reads:\*\*\s*(.*)$")
RELATIVE = re.compile(r"^(the part's|its|the publish task|nothing more)\b", re.I)
PREAMBLE = re.compile(r"the preamble of §([0-9A-Z](?:[0-9A-Za-z.]*[0-9A-Za-z])?)")
SECTION_KEY = re.compile(r"§([0-9A-Z](?:[0-9A-Za-z.]*[0-9A-Za-z])?)")
ITALIC = re.compile(r"\*([^*]+)\*")
# The state itself, without the narration that a state cell gathers over the builds.
STATE = re.compile(
    r"^(open|in progress|waiting for the user|merged|declined|blocked by [^—.;(]*|"
    r"PR (?:\[#\d+\]\([^)]*\)|#\d+) in review)"
)


def headings(lines):
    """Each heading of level 2–4: (line index, level, key or None, title)."""
    out = []
    fence = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fence = not fence
        if fence:
            continue
        m = HEADING.match(line)
        if not m or len(m.group(1)) < 2:
            continue
        k = KEY.match(line)
        key = k.group(2).rstrip(".") if k else None
        title = re.sub(r"^§?[0-9A-Z][0-9A-Za-z.]*\s+·\s+", "", m.group(2))
        out.append((i, len(m.group(1)), key, title))
    return out


def span(heads, j, n, preamble=False):
    """The line range [start, end) of heading j: to the next heading of the same or a higher
    level, or, for its preamble, to its next heading of any level."""
    i, level = heads[j][0], heads[j][1]
    for k, lv, _, _ in heads[j + 1 :]:
        if preamble or lv <= level:
            return i, k
    return i, n


def by_key(heads, key):
    return next((j for j, h in enumerate(heads) if h[2] == key), None)


def by_title(heads, title):
    want = title.strip().lower()
    return next((j for j, h in enumerate(heads) if h[3].strip().lower() == want), None)


def table_rows(lines, key):
    """The rows of a table whose first cell is `key` (bold or not), each under its table's header:
    a list of (start, end) ranges, header first."""
    row = re.compile(r"^\|\s*\**" + re.escape(key) + r"\**\s*\|")
    out = []
    for i, line in enumerate(lines):
        if row.match(line):
            h = i
            while h > 0 and lines[h - 1].startswith("|"):
                h -= 1
            out.append((h, min(h + 2, i)))
            out.append((i, i + 1))
    return out


def also_reads(text):
    """The names that §L's two *also reads* lines give: ('key', k), ('preamble', k), ('title', t),
    and the phrases that name nothing, for the report."""
    names, skipped = [], []
    for line in text.split("\n"):
        m = ALSO.match(line)
        if not m:
            continue
        for phrase in re.split(r",\s*|\s+and\s+|;\s*", m.group(2).rstrip(". ")):
            phrase = re.sub(r"^and\s+", "", phrase.strip())
            if not phrase or phrase in skipped:
                continue
            if RELATIVE.match(phrase):
                skipped.append(phrase)
                continue
            found = False
            for p in PREAMBLE.findall(phrase):
                names.append(("preamble", p))
                found = True
            if not found:
                for k in SECTION_KEY.findall(phrase):
                    names.append(("key", k))
                    found = True
                for t in ITALIC.findall(phrase):
                    names.append(("title", t))
                    found = True
            if not found:
                skipped.append(phrase)
    return names, skipped


def bundle(path, part):
    lines = open(path, encoding="utf-8").read().split("\n")
    heads = headings(lines)
    rows = subprocess.run(
        ["awk", "-f", os.path.join(HERE, "parts-table.awk"), path], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    mine = [r for r in rows if r.split("\t")[:2] == ["PART", part]]
    if not mine:
        return None, [f"part {part} is not in the parts table"]
    collisions = [
        r for r in rows if r.startswith("COLLISION") and part in re.split(r"[\s,()]+", r.split("\t")[-1])
    ]
    row = mine[0].split("\t")
    state = STATE.match(row[5].strip())
    mine = ["\t".join(row[:5] + [state.group(1).strip() if state else row[5][:80]])]
    cell = row[3]
    unresolved, ranges, labels, sources = [], [], [], []

    def add(rng, label, source=None):
        if (rng, source) not in zip(ranges, sources):
            ranges.append(rng)
            labels.append(label)
            sources.append(source)

    def section(key, preamble=False, label=None):
        j = by_key(heads, key)
        if j is not None:
            add(span(heads, j, len(lines), preamble), label or ("preamble of §" if preamble else "§") + key)
            return True
        rows_ = table_rows(lines, key)
        for k, rng in enumerate(rows_):
            add(rng, f"{key} ({'table header' if k % 2 == 0 else 'table row'})")
        return bool(rows_)

    keys = [k.strip().lstrip("§").split()[0] for k in cell.split(",") if k.strip()]
    for key in [k for k in keys if k not in ("V", "L")]:
        if key == "spec":
            spec = spec_gate.spec_path(path, part)
            if os.path.isfile(spec):
                add((0, len(open(spec, encoding="utf-8").read().split("\n"))), "spec", spec)
            else:
                unresolved.append(f"spec ({os.path.relpath(spec, os.path.dirname(os.path.abspath(path)))})")
            continue
        if not section(key):
            unresolved.append(f"§{key} (sections cell)")
    # §V and §L end at their next heading: a plan can file dated handovers below §L.
    for key in ("V", "L"):
        if not section(key, preamble=True, label=f"§{key}"):
            unresolved.append(f"§{key}")
    j = by_key(heads, "L")
    names, skipped = also_reads(
        "\n".join(lines[slice(*span(heads, j, len(lines), True))]) if j is not None else ""
    )
    for kind, name in names:
        if kind == "title":
            t = by_title(heads, name)
            if t is None:
                unresolved.append(f"*{name}* (§L)")
            else:
                add(span(heads, t, len(lines)), f"*{name}*")
        elif not section(name, preamble=(kind == "preamble")):
            unresolved.append(f"§{name} (§L)")
    return (lines, mine + collisions, ranges, labels, sources, skipped), unresolved


def render(path, part, lines, rows, ranges, labels, sources, skipped):
    body = []
    for (start, end), label, source in zip(ranges, labels, sources):
        if source:
            body.append(f"<!-- {label}: {source} -->")
            body.extend(open(source, encoding="utf-8").read().split("\n")[start:end])
        else:
            body.append(f"<!-- {label}: lines {start + 1}–{end} -->")
            body.extend(lines[start:end])
        body.append("")
    text = "\n".join(body)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%h", "--", os.path.basename(path)],
        cwd=os.path.dirname(os.path.abspath(path)),
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = [
        f"# Spec bundle — part {part}",
        "",
        f"- **Task file:** `{path}` at commit `{commit or 'unknown'}`",
        f"- **Body:** {text.count(chr(10)) + 1} lines, {len(text.split())} words, sha256 `{digest}`",
        "- **Rows:**",
        "",
        "```",
        *rows,
        "```",
        "",
        "- **Sections:** "
        + "; ".join(
            f"{l} ({src if src else f'{s + 1}–{e}'})" for (s, e), l, src in zip(ranges, labels, sources)
        ),
        *[
            f"- **$SPEC:** `{os.path.dirname(src)}`, the directory of the spec's checks"
            for src in sources
            if src
        ],
        "- **§L phrases that add nothing here:** " + ("; ".join(skipped) if skipped else "none"),
        "",
        "---",
        "",
    ]
    return "\n".join(head) + text, digest


def main(argv):
    out = None
    if "--out" in argv:
        k = argv.index("--out")
        out, argv = argv[k + 1], argv[:k] + argv[k + 2 :]
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 3
    path, part = argv
    parts, unresolved = bundle(path, part)
    for name in unresolved:
        print(f"unresolved: {name}", file=sys.stderr)
    if parts is None:
        return 1
    text, digest = render(path, part, *parts)
    lines = text.count("\n") + 1
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{out}\t{lines} lines\tsha256 {digest}")
    else:
        sys.stdout.write(text)
        print(f"{lines} lines\tsha256 {digest}", file=sys.stderr)
    return 1 if unresolved else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # the script's own failure, told apart from an unresolved name
        print(f"spec-bundle.py failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)
