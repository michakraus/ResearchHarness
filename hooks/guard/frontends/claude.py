"""Claude Code's table: its `PreToolUse` payload as a `Call`, the checks of each tool, and a
`Verdict` as Claude Code's answer.

The payload is a JSON object with `tool_name`, `tool_input` and, as a rule, `cwd`; a sub-agent's
payload also holds `agent_id`. A payload that the table cannot read is refused: bytes that are not
UTF-8, a text that `jsonio` refuses, a top level that is no object, and no string `tool_name`. A
tool that no entry of `TABLE` names then passes, its `tool_input` unread. For a tool that an entry
names, a `tool_input` that is no object is refused, and so is a `Bash` call without a string
`command` or with a command of more than `MAX_COMMAND` bytes of UTF-8.

Claude Code reads exit 2 as a denial and shows stderr to the model; exit 0 with a JSON
`permissionDecision` on stdout as that decision; exit 0 with no output as no decision.
"""

import json
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TextIO

# The table imports its package by its absolute name `guard`: `__main__` puts the package's parent
# directory first on `sys.path`, and the `OWN` entry of `lib/harness/strict.py` allows the name here.
from guard import (
    HarnessError,
    directory_scope,
    gh_api_writes,
    git_archive_output,
    kaimon_session,
    no_blind_stage,
    no_shell_file_write,
    rm_scope,
    sandbox_semantics,
)
from guard.contract import PASS, Call, Caller, Verdict, strongest
from guard.jsonio import JsonValue, loads

type Check = Callable[[Call], Verdict]

# The longest command the guard reads: 1 MiB of UTF-8.
MAX_COMMAND = 1024 * 1024

# The checks of a `Bash` call, in the order of their reasons when two give one decision.
SHELL: tuple[Check, ...] = (
    no_blind_stage.check,
    no_shell_file_write.check,
    sandbox_semantics.check,
    gh_api_writes.check,
    rm_scope.check,
    git_archive_output.check,
)

# (matcher, checks): the matchers of the settings template's `PreToolUse` groups that run the guard,
# each read as a whole tool name.
TABLE: tuple[tuple[re.Pattern[str], tuple[Check, ...]], ...] = (
    (re.compile(r"Bash"), SHELL),
    (re.compile(r"mcp__ccd_directory__.*|EnterWorktree|ExitWorktree"), (directory_scope.check,)),
    (re.compile(r"mcp__kaimon__ex|mcp__kaimon__manage_repl"), (kaimon_session.check,)),
)

# The neutral names of Claude Code's own worktree tools; an MCP tool's is `<server>.<tool>`.
WORKTREE_TOOLS = {"EnterWorktree": "worktree.enter", "ExitWorktree": "worktree.exit"}
MCP_SERVERS = {"mcp__kaimon__": "kaimon.", "mcp__ccd_directory__": "directory."}


def checks_of(tool: str) -> tuple[Check, ...]:
    """The checks of every entry of `TABLE` whose matcher matches the whole tool name."""
    return tuple(check for matcher, checks in TABLE if matcher.fullmatch(tool) for check in checks)


def read(data: bytes) -> tuple[str, dict[str, JsonValue]]:
    """The tool name and the payload object of the bytes `data`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessError(f"the payload is not UTF-8: {error.reason} at byte {error.start}") from None
    payload = loads(text, where="the payload")
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        raise HarnessError("the payload has no string tool_name")
    return tool, payload


def neutral_name(tool: str) -> str:
    """The neutral name of a tool that is no shell tool."""
    if tool in WORKTREE_TOOLS:
        return WORKTREE_TOOLS[tool]
    for prefix, server in MCP_SERVERS.items():
        if tool.startswith(prefix):
            return server + tool.removeprefix(prefix)
    return tool


def mcp_arguments(tool_input: dict[str, JsonValue]) -> tuple[tuple[str, str], ...]:
    """The arguments that the checks of an `mcp` call read: each string argument, and
    `discard_changes` as `true` when it holds a value that is true."""
    found = [
        (key, value)
        for key, value in tool_input.items()
        if isinstance(value, str) and key != "discard_changes"
    ]
    if tool_input.get("discard_changes"):
        found.append(("discard_changes", "true"))
    return tuple(found)


def call_of(tool: str, payload: dict[str, JsonValue]) -> Call:
    """The `Call` of a payload whose tool an entry of `TABLE` names."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise HarnessError(f"the {tool} payload has no object tool_input")
    given = payload.get("cwd")
    cwd = given if isinstance(given, str) and PurePosixPath(given).is_absolute() else None
    caller: Caller = "sub" if "agent_id" in payload else "main"
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            raise HarnessError("the Bash payload has no string command")
        size = len(command.encode("utf-8"))
        if size > MAX_COMMAND:
            raise HarnessError(
                f"the command holds {size} bytes, more than the {MAX_COMMAND} that the guard reads"
            )
        return Call("shell", command, (), cwd, caller)
    path = tool_input.get("path")
    # A path that is no string resolves nowhere, as the empty path.
    paths = () if "path" not in tool_input else (path if isinstance(path, str) else "",)
    return Call("mcp", neutral_name(tool), paths, cwd, caller, mcp_arguments(tool_input))


def decide(data: bytes) -> Verdict:
    """The guard's verdict on the payload bytes `data`: the strongest verdict of the tool's checks."""
    tool, payload = read(data)
    checks = checks_of(tool)
    if not checks:
        return PASS
    call = call_of(tool, payload)
    return strongest(check(call) for check in checks)


def answer(verdict: Verdict, stdout: TextIO, stderr: TextIO) -> int:
    """Write the verdict as Claude Code reads it, and return the exit status."""
    if verdict.decision == "deny":
        stderr.write(verdict.reason)
        return 2
    if verdict.decision in ("ask", "allow"):
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": verdict.decision,
                "permissionDecisionReason": verdict.reason,
            }
        }
        stdout.write(json.dumps(output) + "\n")
    return 0
