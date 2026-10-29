"""The guard's command line: `guard --from <frontend>`, the payload on stdin.

A payload that the frontend's table cannot read is denied with the reason. A guard that raises
denies too: it writes the reason on stderr and exits 2, which Claude Code reads as a denial, so no
defect of the guard lets a call through.
"""

import sys
from typing import BinaryIO, TextIO

from . import HarnessError
from .contract import Verdict
from .frontends import claude

USAGE = "usage: guard --from claude\n"


def main(argv: list[str], stdin: BinaryIO, stdout: TextIO, stderr: TextIO) -> int:
    """Decide the payload on `stdin` for the frontend that `argv` names; return the exit status."""
    if argv != ["--from", "claude"]:
        stderr.write(USAGE)
        return 2
    try:
        verdict = claude.decide(stdin.read())
    except HarnessError as error:
        verdict = Verdict("deny", f"Refused: the guard cannot read the call: {error}.\n")
    return claude.answer(verdict, stdout, stderr)


if __name__ == "__main__":
    try:
        status = main(sys.argv[1:], sys.stdin.buffer, sys.stdout, sys.stderr)
    except Exception as error:
        sys.stderr.write(f"Refused: the guard raised {type(error).__name__}: {error}\n")
        raise SystemExit(2) from error
    sys.exit(status)
