"""A duplicate shortlist for the open issues: which entries of two repositories say the same thing?

    python3 known-issues-similar.py --model <name> [--threshold <cos>] [--out <file>]
                                    [--pair <repo> <needle> <repo> <needle>] ...

Reads the root `CHANGELOG.md` (its `## Open Issues` section) and the root `KNOWN_ISSUES.md` (the
whole file) of every repository in `Packages/` and `Experiments/`, and splits them into entries. A
subsection whose heading carries an ID (`#### A5.`) is one entry; outside one, a top-level `- `
bullet with its continuation lines is one entry; a subsection with neither bullets nor IDs is one
entry; preamble prose is none. Each entry is embedded with Ollama `/api/embed`, and every pair of
entries, inside a repository and across repositories, gets its cosine.

A `--pair` names a labelled pair: each side is a repository and a substring of the entry's first
line. The script prints the rank of each labelled pair, and the best unlabelled pair, to stderr.
With `--threshold` and `--out`, it writes every pair at or above the threshold, sorted by cosine
and then by repository and line, with both texts. The design is in `Decision-Models.md`, *Details
of proposals 2 and 3*. It only proposes; whether a pair is one issue is the reader's call.

Exit status 0 on success; 1 when Ollama fails, a model is missing, an embedding has zero norm, or a
`--pair` needle matches no entry or more than one. Nothing is written on a failure.
"""
import argparse
import json
import math
import os
import re
import sys
import urllib.request

RESEARCH = os.path.expanduser("~/Research")
OLLAMA = "http://localhost:11434/api/embed"
HEADING = re.compile(r"^(#{1,6}) ")
ID_HEADING = re.compile(r"^#{3,6} [A-Z]+\d+[a-z]?(\.| ·) ")
FENCE = re.compile(r"^\s*(```|~~~)")


def fenced(lines):
    """For each line, whether it is a fence delimiter or inside a fence."""
    out, inside = [], False
    for line in lines:
        if FENCE.match(line):
            out.append(True)
            inside = not inside
        else:
            out.append(inside)
    return out


def bullets(seg, fen):
    """Split a run of (index, line) into top-level bullet entries."""
    entries, cur, prev_blank, attached = [], None, False, False
    for (i, line), f in zip(seg, fen):
        if f and not FENCE.match(line):
            if attached:
                cur[1].append(line)
            continue
        if f:  # a delimiter
            if attached:  # closes a fence that belongs to the entry
                cur[1].append(line)
                attached = False
                continue
            if cur is not None and (line[:1] in " \t" or not prev_blank):
                cur[1].append(line)
                attached = True
            else:
                cur = None
            prev_blank = False
            continue
        if line.startswith("- "):
            cur = (i, [line])
            entries.append(cur)
        elif cur is not None:
            if not line.strip() or line[:1] in " \t" or not prev_blank:
                cur[1].append(line)
            else:
                cur = None
        prev_blank = not line.strip()
    return [(i, "\n".join(b).rstrip()) for i, b in entries]


def split(text, whole=False):
    """Entries of one file, as (line number, text): the `## Open Issues` section, or the whole."""
    lines = text.split("\n")
    fen = fenced(lines)
    start = 0
    if not whole:
        hits = [k for k, l in enumerate(lines) if not fen[k] and l.rstrip() == "## Open Issues"]
        if not hits:
            return []
        start = hits[0] + 1
    end = len(lines)
    heads = []  # (index, level)
    for k in range(start, len(lines)):
        m = not fen[k] and HEADING.match(lines[k])
        if m:
            if not whole and len(m.group(1)) <= 2:
                end = k
                break
            heads.append((k, len(m.group(1))))
    bounds = [k for k, _ in heads] + [end]
    segs = [(start, 0)] + heads  # a leading segment of preamble, level 0
    segs_end = [bounds[0]] + bounds[1:]
    entries, skip_until = [], -1
    for n, ((k, level), stop) in enumerate(zip(segs, segs_end)):
        body_from = k + 1 if level else k
        if level and ID_HEADING.match(lines[k]):
            entries.append((k, "\n".join(lines[k:stop]).rstrip()))
            continue
        seg = list(enumerate(lines[body_from:stop], body_from))
        found = bullets(seg, fen[body_from:stop])
        entries.extend(found)
        if found or level == 0 or k < skip_until:
            continue
        # a subsection with no bullet: one entry, unless its span holds bullets or IDs
        span_end = end
        for k2, l2 in heads:
            if k2 > k and l2 <= level:
                span_end = k2
                break
        span = range(k, span_end)
        if any(ID_HEADING.match(lines[j]) and not fen[j] for j in span):
            continue
        if bullets(list(enumerate(lines[k + 1:span_end], k + 1)), fen[k + 1:span_end]):
            continue
        entries.append((k, "\n".join(lines[k:span_end]).rstrip()))
        skip_until = span_end
    return [(k + 1, t) for k, t in sorted(entries)]


def collect(root):
    """Every entry: (repository, relative path, line, text)."""
    out = []
    for group in ("Packages", "Experiments"):
        base = os.path.join(root, group)
        if not os.path.isdir(base):
            continue
        for repo in sorted(os.listdir(base)):
            for name, whole in (("CHANGELOG.md", False), ("KNOWN_ISSUES.md", True)):
                path = os.path.join(base, repo, name)
                if not os.path.isfile(path):
                    continue
                with open(path, encoding="utf-8", newline="") as f:
                    text = f.read()
                rel = os.path.join(group, repo, name)
                out += [(repo, rel, line, t) for line, t in split(text, whole)]
    return out


def embed(model, texts):
    vecs = []
    for k in range(0, len(texts), 16):
        body = json.dumps({"model": model, "input": texts[k:k + 16], "truncate": False}).encode()
        req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            vecs += json.load(r)["embeddings"]
    if len(vecs) != len(texts):
        raise RuntimeError(f"{len(vecs)} embeddings for {len(texts)} entries")
    out = []
    for v, t in zip(vecs, texts):
        n = math.sqrt(sum(x * x for x in v))
        if n == 0:
            raise RuntimeError("an embedding of zero norm: " + t.split("\n")[0])
        out.append([x / n for x in v])
    return out


def find(entries, repo, needle):
    hits = [k for k, e in enumerate(entries) if e[0] == repo and needle in e[3].split("\n")[0]]
    if len(hits) != 1:
        raise RuntimeError(f"--pair {repo} {needle!r} matches {len(hits)} entries")
    return hits[0]


def fence_for(text):
    run = max([len(m) for m in re.findall(r"`+", text)] + [2])
    return "`" * (run + 1)


def write(path, model, threshold, entries, pairs, labelled):
    counts = {}
    for e in entries:
        counts[e[0]] = counts.get(e[0], 0) + 1
    kept = [p for p in pairs if p[0] >= threshold]
    out = [f"# Duplicate shortlist — `{model}`, threshold {threshold:.4f}", "",
           "Written by `Harness/scripts/known-issues-similar.py`. A pair is a candidate,",
           "not a finding: the builder that moves the entry decides whether it is one issue.", "",
           "## Entries per repository", "", "| repository | entries |", "|:--|--:|"]
    out += [f"| {r} | {n} |" for r, n in sorted(counts.items())]
    out += ["", "## Labelled pairs", "", "| rank | cosine | a | b |", "|--:|--:|:--|:--|"]
    for rank, (c, i, j) in enumerate(pairs, 1):
        if (i, j) in labelled:
            out.append(f"| {rank} | {c:.4f} | {loc(entries[i])} | {loc(entries[j])} |")
    out += ["", f"## Pairs at or above {threshold:.4f}", "",
            "| rank | cosine | a | b |", "|--:|--:|:--|:--|"]
    for rank, (c, i, j) in enumerate(kept, 1):
        mark = " (labelled)" if (i, j) in labelled else ""
        out.append(f"| {rank} | {c:.4f} | {loc(entries[i])} | {loc(entries[j])}{mark} |")
    out += ["", "## Texts", ""]
    for rank, (c, i, j) in enumerate(kept, 1):
        out += [f"### {rank} · {c:.4f}", ""]
        for e in (entries[i], entries[j]):
            fn = fence_for(e[3])
            out += [f"{loc(e)}:", "", fn + "markdown", e[3], fn, ""]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(out))


def loc(e):
    return f"{e[0]} `{e[1]}:{e[2]}`"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--out")
    ap.add_argument("--root", default=RESEARCH)
    ap.add_argument("--pair", nargs=4, action="append", default=[],
                    metavar=("REPO", "NEEDLE", "REPO", "NEEDLE"))
    a = ap.parse_args()
    if (a.threshold is None) != (a.out is None):
        ap.error("--threshold and --out go together")
    try:
        entries = collect(a.root)
        order = sorted(range(len(entries)), key=lambda k: (entries[k][0], entries[k][1], entries[k][2]))
        entries = [entries[k] for k in order]
        labelled = set()
        for r1, n1, r2, n2 in a.pair:
            i, j = sorted((find(entries, r1, n1), find(entries, r2, n2)))
            labelled.add((i, j))
        vecs = embed(a.model, [e[3] for e in entries])
    except Exception as err:  # every failure is fatal, and nothing is written
        print(f"known-issues-similar: {err}", file=sys.stderr)
        return 1
    pairs = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            pairs.append((sum(x * y for x, y in zip(vecs[i], vecs[j])), i, j))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    best = next(((r, p) for r, p in enumerate(pairs, 1) if (p[1], p[2]) not in labelled), None)
    for r, (c, i, j) in enumerate(pairs, 1):
        if (i, j) in labelled:
            print(f"labelled rank {r}: {c:.4f}  {loc(entries[i])}  {loc(entries[j])}", file=sys.stderr)
    if best:
        r, (c, i, j) = best
        print(f"best unlabelled rank {r}: {c:.4f}  {loc(entries[i])}  {loc(entries[j])}",
              file=sys.stderr)
    print(f"{len(entries)} entries, {len(pairs)} pairs", file=sys.stderr)
    if a.out:
        write(a.out, a.model, a.threshold, entries, pairs, labelled)
    return 0


if __name__ == "__main__":
    sys.exit(main())
