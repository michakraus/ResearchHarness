#!/usr/bin/env python3
"""`SessionStart` hook: warn when ~/.claude is behind the sources that `harness install` installs.

`harness install --apply` writes the stamp ~/.claude/.harness-install.json: the sources of the
Claude Code layer, each as [directory, installed prefix, top-level names not installed, top-level
directories not installed], and `digest`, a SHA-256 over the installed path, the installed mode and
the source bytes of each file that the apply installed, in sorted order. This hook computes the same
digest from the sources that the stamp names and compares the two. It runs no `harness install`:
it runs at every session start.

It warns, as a `systemMessage` for the user and as `additionalContext` for the session, when the
digests differ, when the stamp is missing or cannot be read, and when a source cannot be read,
naming the path; a source it cannot read is never a silent pass. It blocks nothing and exits 0,
whatever its input. `install.py` takes the stamp's digest from `digest_of` in this file, over the
source bytes and modes of what it installs, so that the stamp and the check are one computation.
The hook has no profile and no model tables, so it reads each file as its source: no file of the
layer is a template, and the rewrite of `model:` and `tools:` in an agent or a skill is not in the
digest, so an edit of the [claude] table of models.toml is no drift.
"""

import errno
import hashlib
import json
import os
import stat
import sys
import unicodedata

STAMP = ".harness-install.json"


def hidden(name):
    """A name that is not a source, as `harness install` reads its sources."""
    return name.startswith(".") or name == "__pycache__"


def fold(name):
    """`name` with case and Unicode form folded, as `harness install` compares names."""
    return unicodedata.normalize("NFC", name).casefold()


def raise_error(error):
    raise error


def files(sources):
    """[(installed path, source file, installed mode)] of `sources`, sorted by installed path; the
    mode is the source's below hooks/ and 0o644 elsewhere, as `harness install` installs it. A
    source that is not a directory, a directory that cannot be read, a symlink, and an entry that is
    neither a file nor a directory, such as a FIFO, raise OSError with its path, as each exits 2 in
    `harness install`."""
    found = []
    for directory, prefix, skip, skipped in sources:
        if not os.path.isdir(directory):
            raise FileNotFoundError(2, "not a directory", directory)
        skipped = {fold(s) for s in skipped}
        for path, dirs, names in os.walk(directory, onerror=raise_error):
            dirs[:] = [d for d in dirs if not hidden(d)]
            names = [n for n in names if not hidden(n)]
            for name in dirs + names:
                if os.path.islink(os.path.join(path, name)):
                    raise OSError(errno.ELOOP, "a symlink, which `harness install` refuses", os.path.join(path, name))
            for name in names:
                src = os.path.join(path, name)
                mode = os.stat(src).st_mode
                if not stat.S_ISREG(mode):
                    raise OSError(errno.EINVAL, "neither a file nor a directory, which `harness install` refuses", src)
                rel = os.path.relpath(src, directory).replace(os.sep, "/")
                if rel.split("/")[0] in skip or fold(rel.split("/")[0]) in skipped:
                    continue
                dst = "/".join(p for p in (prefix, rel) if p)
                found.append((dst, src, stat.S_IMODE(mode) if dst.startswith("hooks/") else 0o644))
    return sorted(found)


def digest_of(entries):
    """The SHA-256, as hex, of `entries`, [(installed path, bytes, installed mode)], in sorted order:
    the plan of `harness install`, whose digest the stamp records."""
    h = hashlib.sha256()
    for dst, data, mode in sorted(entries):
        h.update(dst.encode() + b"\0" + mode.to_bytes(2, "big") + len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


def digest(sources):
    """`digest_of` the files of `sources`, with the bytes that each holds now."""
    entries = []
    for dst, src, mode in files(sources):
        with open(src, "rb") as f:
            entries.append((dst, f.read(), mode))
    return digest_of(entries)


def check(home):
    """The warning for the installation below `home`, or None when it is current."""
    stamp = os.path.join(home, ".claude", STAMP)
    apply = "Run `harness install` to see the changes, then `harness install --apply`."
    try:
        with open(stamp, encoding="utf-8") as f:
            recorded = json.load(f)
        sources, expected = recorded["sources"], recorded["digest"]
    except FileNotFoundError:
        return f"{stamp} does not exist: no `harness install --apply` recorded what ~/.claude holds. {apply}"
    except (OSError, ValueError, KeyError, TypeError) as e:
        return f"{stamp} cannot be read ({type(e).__name__}: {e}); the installation is not checked. {apply}"
    try:
        current = digest(sources)
    except OSError as e:
        return f"{e.filename} cannot be read ({e.strerror}); the installation is not checked against it."
    except (ValueError, TypeError) as e:
        return f"{stamp} cannot be read ({type(e).__name__}: {e}); the installation is not checked. {apply}"
    if current != expected:
        sources = ", ".join(s[0] for s in sources)
        return f"~/.claude is behind its sources ({sources}): an edit there is not installed. {apply}"
    return None


def main():
    try:
        message = check(os.path.expanduser("~"))
    except Exception as e:  # the hook only warns: an error it did not foresee is a warning too
        message = f"install-drift.py failed ({type(e).__name__}: {e}); the installation is not checked."
    if message:
        print(json.dumps({"systemMessage": message,
                          "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
