"""Run githooks/format-tree.jl until it completes, surviving files that crash JuliaFormatter.

    harness format [--apply]

JuliaFormatter can take the whole Julia process down on a pathological file — not a catchable
exception. format-tree.jl records the file it is about to touch in a marker; when the process
dies, this moves that file into the skiplist and resumes. What is left in the skiplist at the end
is the set of files JuliaFormatter cannot handle in this tree, which is worth keeping. The marker,
the skiplist and the log go to $FMT_OUT, else $TMPDIR.

The dry run counts the files that format-tree.jl would reformat, from its summary line.
"""

import os
import pathlib
import re
import subprocess

from . import REPO, HarnessError, changing, outcome

ATTEMPTS = 40


def cmd_format(args):
    out = pathlib.Path(os.environ.get("FMT_OUT") or os.environ.get("TMPDIR") or "/tmp")
    marker, skiplist, log = out / "format-marker", out / "format-skiplist", out / "format-tree.log"
    env = dict(os.environ, FMT_MARKER=str(marker), FMT_SKIPLIST=str(skiplist))
    log.write_text("")
    skiplist.touch()
    marker.unlink(missing_ok=True)
    command = ["julia", str(REPO / "githooks" / "format-tree.jl")]
    command += ["--apply"] if args.apply else []
    for attempt in range(1, ATTEMPTS + 1):
        with log.open("a") as f:
            f.write(f"\n---------- attempt {attempt} ----------\n")
            f.flush()
            rc = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
        if rc == 0:
            break
        if not marker.is_file() or not marker.read_text().strip():
            raise HarnessError(f"died with rc={rc} and no marker — see {log}")
        bad = marker.read_text().strip()
        print(f"CRASHED on {bad} (rc={rc}) — skipping it and resuming")
        with skiplist.open("a") as f:
            f.write(bad + "\n")
        marker.unlink()
    else:
        raise HarnessError(f"too many crashes ({ATTEMPTS}) — see {log}")
    print(f"\ncompleted after {attempt} attempt(s)\nlog:      {log}")
    skipped = skiplist.read_text().split()
    if skipped:
        print(f"files JuliaFormatter could not handle ({skiplist}):")
        for f in skipped:
            print("    " + f)
    last = log.read_text().split("---------- attempt")[-1]
    print("\n".join(last.splitlines()[-6:]))
    m = re.search(r"(?:would reformat|reformatted): (\d+) of", last)
    if not m:
        raise HarnessError(f"format-tree.jl printed no summary — see {log}")
    return outcome(args, int(m.group(1)))


def register(sub):
    changing(sub.add_parser("format", help="run JuliaFormatter over every tracked .jl file of the tree")
             ).set_defaults(run=cmd_format)
