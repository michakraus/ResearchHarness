"""Antigravity's table: its `PreToolUse` payload as a `Call`, the checks of each tool, and a
`Verdict` as Antigravity's answer.

Antigravity runs the guard for each tool call (`hooks.json`, matcher `*`) and gives it the call as
JSON on stdin: `toolCall.name`, `toolCall.args` and `workspacePaths`. The guard answers with one
JSON object on stdout and exit 0:

    {"decision": "deny", "reason": …}       a check refuses the call
    {"decision": "force_ask", "reason": …}  a check asks the user
    {"decision": "ask"}                     every check passes

`ask` leaves Antigravity's own policy in force: its permission rules and its preset decide, as with
no hook. A neutral `allow` is answered as a pass, so the guard grants nothing beyond that policy.
It never answers `{}`, which Antigravity reads as a deny with an empty reason.

A `run_command` that it does not deny also gets `"overwrite": {"BypassSandbox": …}`, which replaces
that argument of the call: true only when the check `sandbox_lift` lifts the command, else false.
So the guard, not the agent, decides the sandbox of a command, as Claude Code's
`sandbox.excludedCommands` does, and an agent's own `BypassSandbox` on any other command is dropped.
A deny, and a call of any other tool, carries no `overwrite`.

THE CALL. The working directory is the call's `Cwd`, its home form expanded and resolved against
the first of `workspacePaths`, else that first path (a sub-agent's `run_command` has a `Cwd`, the
main agent's does not); with neither, the call names none, and a check that must place a relative
path refuses it. The paths of a call are its arguments of PATH_KEYS; those of WIDE_KEYS, and the
working directory that a `Cwd` names, are paths that the call reads below. Each tool of ACTIONS has
its neutral action; `call_mcp_tool` is the `mcp` call `<ServerName>.<ToolName>`, whose `Arguments`,
an object or the JSON text of one, a Kaimon `ex` or `manage_repl` call must hold; any other tool is
an `mcp` call by its own name, which only the path list checks.

THE CHECKS: the path list, `guard-paths.json` two directories above this package, as
`harness install` renders it, on every call (`path_list`); on a shell call also the five shell
checks and the work-tree check of `sandbox_semantics`, whose other shapes describe Claude Code's
sandbox alone; on an `mcp` call also the Kaimon check.

A payload that the table cannot read is refused: bytes that are not UTF-8, a text that `jsonio`
refuses, no object `toolCall`, no string `name`, `args` that are no object, a `run_command` without
a string `CommandLine`, with one that no UTF-8 encodes (a lone surrogate) or with one of more than
MAX_COMMAND bytes of UTF-8, and a Kaimon call without an object of `Arguments`.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import TextIO

# The table imports its package by its absolute name `guard`: `__main__` puts the package's parent
# directory first on `sys.path`, and the `OWN` entry of `lib/harness/strict.py` allows the name here.
from guard import (
    HarnessError,
    gh_api_writes,
    git_archive_output,
    kaimon_session,
    no_blind_stage,
    no_shell_file_write,
    path_list,
    rm_scope,
    sandbox_lift,
    sandbox_semantics,
)
from guard.contract import Action, Call, Verdict, strongest
from guard.jsonio import JsonValue, loads

type Check = Callable[[Call], Verdict]

# The longest command the guard reads: 1 MiB of UTF-8.
MAX_COMMAND = 1024 * 1024
# The path list that `harness install` renders beside the `hooks/` directory that holds the package.
PATH_LIST = str(Path(__file__).parent.parent.parent.parent / "guard-paths.json")
# The neutral action of each tool, of both tool families: the main agent's `read_file`,
# `write_file` and `edit_file`, and a sub-agent's `view_file`, `write_to_file`,
# `replace_file_content`, `multi_replace_file_content`, `grep_search`, `find_by_name` and
# `list_dir`.
ACTIONS: dict[str, Action] = {
    "run_command": "shell",
    "view_file": "read",
    "read_file": "read",
    "list_dir": "read",
    "find_by_name": "read",
    "grep_search": "read",
    "codebase_search": "read",
    "write_to_file": "write",
    "write_file": "write",
    "replace_file_content": "edit",
    "multi_replace_file_content": "edit",
    "edit_file": "edit",
    "call_mcp_tool": "mcp",
    "invoke_subagent": "subagent",
}
# The arguments that hold a path, and those that hold a path below which the call reads.
PATH_KEYS = ("Path", "AbsolutePath", "TargetFile", "SearchDirectory", "DirectoryPath")
WIDE_KEYS = ("SearchPath",)
# The Kaimon tools whose check reads `Arguments`.
KAIMON = "kaimon"
KAIMON_TOOLS = ("ex", "manage_repl")


def listed(call: Call) -> Verdict:
    """The path list's verdict on `call`."""
    return path_list.check(call, PATH_LIST)


SHELL: tuple[Check, ...] = (
    listed,
    no_blind_stage.check,
    no_shell_file_write.check,
    gh_api_writes.check,
    rm_scope.check,
    git_archive_output.check,
    sandbox_semantics.work_tree_check,
)
CHECKS: dict[Action, tuple[Check, ...]] = {
    "shell": SHELL,
    "read": (listed,),
    "write": (listed,),
    "edit": (listed,),
    "mcp": (listed, kaimon_session.check),
    "subagent": (listed,),
}


def read(data: bytes) -> tuple[str, dict[str, JsonValue], str | None]:
    """The tool name, the arguments and the first workspace path of the payload bytes `data`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessError(f"the payload is not UTF-8: {error.reason} at byte {error.start}") from None
    payload = loads(text, where="the payload")
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        raise HarnessError("the payload has no object toolCall")
    name = tool_call.get("name")
    if not isinstance(name, str):
        raise HarnessError("the tool call has no string name")
    args = tool_call.get("args", {})
    if not isinstance(args, dict):
        raise HarnessError(f"the args of {name} are no object")
    workspaces = payload.get("workspacePaths")
    first = workspaces[0] if isinstance(workspaces, list) and workspaces else None
    workspace = first if isinstance(first, str) and PurePosixPath(first).is_absolute() else None
    return name, args, workspace


def normalised(path: str) -> str:
    """The absolute path `path` normalised as text, as `posixpath.normpath` does: a leading `//`
    kept, which POSIX leaves to the system."""
    lead = "//" if path.startswith("//") and not path.startswith("///") else "/"
    return lead + path_list.normal(path)[1:]


def working_directory(args: dict[str, JsonValue], workspace: str | None) -> str | None:
    """The call's `Cwd`, its home form expanded and resolved against `workspace`, else `workspace`;
    None when neither places it."""
    given = args.get("Cwd")
    if not isinstance(given, str):
        return workspace
    path = path_list.expanded(given)
    if PurePosixPath(path).is_absolute():
        return normalised(path)
    return None if workspace is None else normalised(workspace + "/" + path)


def kaimon_arguments(args: dict[str, JsonValue]) -> tuple[tuple[str, str], ...]:
    """The string arguments of a Kaimon call's `Arguments`, an object or the JSON text of one."""
    given = args.get("Arguments")
    if isinstance(given, str):
        given = loads(given, where="the Kaimon Arguments")
    if not isinstance(given, dict):
        raise HarnessError("the Kaimon call holds no object of Arguments")
    return tuple((key, value) for key, value in given.items() if isinstance(value, str))


def call_of(name: str, args: dict[str, JsonValue], workspace: str | None) -> Call:
    """The `Call` of the tool `name` with the arguments `args`."""
    cwd = working_directory(args, workspace)
    paths = tuple(value for key in PATH_KEYS if isinstance(value := args.get(key), str))
    wide = tuple(value for key in WIDE_KEYS if isinstance(value := args.get(key), str))
    given = args.get("Cwd")
    if isinstance(given, str):
        # The directory that `Cwd` names, or `Cwd` itself when nothing places it.
        wide += (given if cwd is None else cwd,)
    action = ACTIONS.get(name, "mcp")
    if action == "shell":
        command = args.get("CommandLine")
        if not isinstance(command, str):
            raise HarnessError("the run_command call holds no string CommandLine")
        try:
            size = len(command.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise HarnessError(f"the command is no UTF-8 text: {error.reason} at {error.start}") from None
        if size > MAX_COMMAND:
            raise HarnessError(
                f"the command holds {size} bytes, more than the {MAX_COMMAND} that the guard reads"
            )
        return Call("shell", command, paths, cwd, "main", wide=wide)
    if name != "call_mcp_tool":
        return Call(action, name, paths, cwd, "main", wide=wide)
    server, tool = args.get("ServerName"), args.get("ToolName")
    if not isinstance(server, str) or not isinstance(tool, str):
        return Call("mcp", name, paths, cwd, "main", wide=wide)
    arguments = kaimon_arguments(args) if server == KAIMON and tool in KAIMON_TOOLS else ()
    return Call("mcp", f"{server}.{tool}", paths, cwd, "main", arguments, wide)


def decide(data: bytes) -> tuple[Verdict, bool]:
    """The guard's verdict on the payload bytes `data`, the strongest verdict of the tool's checks,
    with the `sandbox` of `sandbox_lift` on a shell call that it does not deny; and whether the call
    is a shell call."""
    name, args, workspace = read(data)
    call = call_of(name, args, workspace)
    verdict = strongest(check(call) for check in CHECKS[call.action])
    shell = call.action == "shell"
    if shell and verdict.decision != "deny":
        verdict = replace(verdict, sandbox=sandbox_lift.check(call).sandbox)
    return verdict, shell


def render(verdict: Verdict, *, shell: bool) -> dict[str, object]:
    """The verdict as Antigravity reads it: `deny` as `deny` with its reason, `ask` as `force_ask`
    with its reason, anything else as `ask`; on a shell call that it does not deny, the
    `BypassSandbox` that the verdict's `sandbox` gives."""
    if verdict.decision == "deny":
        return {"decision": "deny", "reason": verdict.reason}
    found: dict[str, object] = (
        {"decision": "force_ask", "reason": verdict.reason}
        if verdict.decision == "ask"
        else {"decision": "ask"}
    )
    if shell:
        found["overwrite"] = {"BypassSandbox": verdict.sandbox != "keep"}
    return found


def answer(verdict: Verdict, stdout: TextIO, *, shell: bool) -> int:
    """Write the verdict as Antigravity reads it, and return the exit status, 0."""
    stdout.write(json.dumps(render(verdict, shell=shell)) + "\n")
    return 0
