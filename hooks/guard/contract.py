"""The neutral contract between a frontend's table and the checks.

A table turns a frontend's payload into a `Call`; each check reads the `Call` and returns a
`Verdict`; `strongest` combines the verdicts, and the table turns the result into the frontend's
answer. No check reads a frontend's payload.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

# `shell` runs `command` in a shell. `mcp` calls a tool that is no shell, file or sub-agent tool,
# such as an MCP tool or a frontend's own worktree tool; `command` then names the tool, such as
# `kaimon.ex`, and `arguments` holds its arguments of interest.
type Action = Literal["shell", "read", "write", "edit", "mcp", "subagent"]
type Caller = Literal["main", "sub"]
type Decision = Literal["deny", "ask", "allow", "pass"]
type Sandbox = Literal["lift", "keep"]

# The order of the decisions: the first of `deny`, `ask`, `allow` and `pass` that a check gives wins.
RANK: dict[Decision, int] = {"pass": 0, "allow": 1, "ask": 2, "deny": 3}


@dataclass(frozen=True, slots=True)
class Call:
    """One tool call, as a check reads it."""

    action: Action
    command: str
    paths: tuple[str, ...]
    # The absolute working directory of the call, or None when the payload names none.
    cwd: str | None
    caller: Caller
    # The arguments of an `mcp` call that its check reads, by name, each as a string.
    arguments: tuple[tuple[str, str], ...] = ()

    def argument(self, name: str) -> str | None:
        """The argument `name`, or None when the call has none."""
        return next((value for key, value in self.arguments if key == name), None)


@dataclass(frozen=True, slots=True)
class Verdict:
    """The answer of a check, or of the guard: the decision, the reason that the agent reads, and
    whether the call runs outside the sandbox."""

    decision: Decision
    reason: str = ""
    sandbox: Sandbox = "keep"


PASS = Verdict("pass")


def strongest(verdicts: Iterable[Verdict]) -> Verdict:
    """The first verdict whose decision ranks highest, so that its reason is the reason of the
    check that gave the winning decision; `PASS` when there is none. It reads no verdict after the
    first `deny`, which nothing outranks, so a lazy `verdicts` runs no check after it."""
    best = PASS
    for verdict in verdicts:
        if RANK[verdict.decision] > RANK[best.decision]:
            best = verdict
        if best.decision == "deny":
            break
    return best


def needs_cwd(check: str, command: str) -> Verdict:
    """The denial of a check that must resolve a path of `command` against a working directory
    that the payload does not name."""
    return Verdict(
        "deny",
        f"Refused: {command}\n\nThe {check} check resolves a path of this command against the working "
        "directory, and the call names none. Run the command from a session that has one.\n",
    )
