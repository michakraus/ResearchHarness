"""The guard's command line: `guard --from <frontend>`, the payload on stdin, for the frontends
`claude` and `antigravity`.

A payload that the frontend's table cannot read is denied with the reason. A guard that raises
blocks too: it writes the reason on stderr and exits 2 with nothing on stdout, which Claude Code
reads as a denial and Antigravity as a hook that failed, so no defect of the guard lets a call
through.
"""

import sys
from typing import BinaryIO, TextIO

from . import HarnessError
from .contract import Verdict
from .frontends import antigravity, claude

USAGE = "usage: guard --from claude|antigravity\n"


def unreadable(error: HarnessError) -> Verdict:
    """The denial of a payload that the table cannot read."""
    return Verdict("deny", f"Refused: the guard cannot read the call: {error}.\n")


def main(argv: list[str], stdin: BinaryIO, stdout: TextIO, stderr: TextIO) -> int:
    """Decide the payload on `stdin` for the frontend that `argv` names; return the exit status."""
    if argv == ["--from", "claude"]:
        try:
            verdict = claude.decide(stdin.read())
        except HarnessError as error:
            verdict = unreadable(error)
        return claude.answer(verdict, stdout, stderr)
    if argv == ["--from", "antigravity"]:
        try:
            verdict, shell = antigravity.decide(stdin.read())
        except HarnessError as error:
            verdict, shell = unreadable(error), False
        return antigravity.answer(verdict, stdout, shell=shell)
    stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    try:
        status = main(sys.argv[1:], sys.stdin.buffer, sys.stdout, sys.stderr)
    except Exception as error:
        sys.stderr.write(f"Refused: the guard raised {type(error).__name__}: {error}\n")
        raise SystemExit(2) from error
    sys.exit(status)
