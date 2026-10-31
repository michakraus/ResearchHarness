"""OpenCode's table: the message of the guard plugin `plugins/guards.ts` as a `Call`, the checks of
each tool, and a `Verdict` as the answer that the plugin applies.

The plugin sends each `tool.execute.before` event of OpenCode as one JSON object on stdin,
`{"event": {tool, sessionID, agent, messageID, id, input}, "directory": <the session's directory>}`,
and reads one object on stdout, `{"block": <bool>, "reason": <text>}`, after exit 0. It throws the
reason of a block, which refuses the call. OpenCode has no way for a plugin to ask the user, so an
`ask` is a block whose reason tells the model to ask the user in chat.

THE LISTS. The table reads `guard-paths.json` beside the plugin, its `deny`, and the optional list
`$OPENCODE_CONFIG_DIR/guard-paths.json`, a further `deny` and an `allow`, before it reads the tool:
a list that is missing or cannot be used refuses every call. The path list reads OpenCode's form of
a command: each word, and each path that TEXT_PATH finds.

THE CALLS. `shell` is a shell call: `input.command`, in `input.workdir` resolved against the
session's directory, else in that directory; the `workdir` is also a path that the call reads
below. The command is checked as given and again with a leading `rtk ` removed, as the rtk plugin
rewrites it, and the stricter verdict holds. `kaimon_ex` and `kaimon_manage_repl` are the `mcp`
calls `kaimon.ex` and `kaimon.manage_repl`. Every other tool passes.

A message that the table cannot read is refused: bytes that are not UTF-8, a text that `jsonio`
refuses, no object `event`, no string `tool`, an `input` that is no object, a `shell` call without a
string `command` or with one of more than MAX_COMMAND bytes of UTF-8.
"""

import functools
import json
import os
import re
from collections.abc import Callable
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
    sandbox_semantics,
)
from guard.contract import PASS, Call, Verdict, strongest
from guard.jsonio import JsonValue, loads

type Check = Callable[[Call], Verdict]

# The longest command the guard reads: 1 MiB of UTF-8.
MAX_COMMAND = 1024 * 1024
# The path list that `harness install` renders beside the plugin, in `plugins/` beside `hooks/`.
PATH_LIST = str(Path(__file__).parents[3] / "plugins" / "guard-paths.json")
# The Kaimon tools, by OpenCode's name, and their neutral names.
KAIMON = {"kaimon_ex": "kaimon.ex", "kaimon_manage_repl": "kaimon.manage_repl"}
# A leading `rtk `, which the rtk plugin puts before a command that RTK rewrites.
RTK = re.compile(r"^\s*rtk\s+")
READING = path_list.Reading(text_paths=True)
ASK_USER = (
    "This call needs the approval of the user, and OpenCode cannot ask for it from a plugin. Do not "
    "run it in another form. Ask the user in chat, and give the user the command to run."
)


@functools.cache
def lists() -> path_list.Lists | str:
    """The rules of the plugin's path list and of the one in `$OPENCODE_CONFIG_DIR`, or the reason to
    refuse every call."""
    deny = path_list.path_rules(PATH_LIST, "deny")
    if isinstance(deny, str):
        return deny
    directory = os.environ.get("OPENCODE_CONFIG_DIR")
    local = path_list.local_rules(str(Path(directory, "guard-paths.json"))) if directory else ((), None)
    if isinstance(local, str):
        return local
    return path_list.Lists((*deny, *local[0]), (), (), local[1], READING)


def listed(call: Call) -> Verdict:
    """The path list's verdict on `call`."""
    found = lists()
    return Verdict("deny", found) if isinstance(found, str) else path_list.check_paths(call, found)


SHELL: tuple[Check, ...] = (
    listed,
    path_list.in_place,
    no_blind_stage.check,
    no_shell_file_write.check,
    gh_api_writes.check,
    rm_scope.check,
    git_archive_output.check,
    sandbox_semantics.work_tree_check,
)


def read(data: bytes) -> tuple[str, dict[str, JsonValue], str | None]:
    """The tool, the input and the session's directory of the message bytes `data`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessError(f"the message is not UTF-8: {error.reason} at byte {error.start}") from None
    message = loads(text, where="the message")
    event = message.get("event")
    if not isinstance(event, dict):
        raise HarnessError("the message has no object event")
    tool = event.get("tool")
    if not isinstance(tool, str):
        raise HarnessError("the event has no string tool")
    tool_input = event.get("input", {})
    if not isinstance(tool_input, dict):
        raise HarnessError(f"the input of {tool} is no object")
    directory = message.get("directory")
    if isinstance(directory, str) and PurePosixPath(directory).is_absolute():
        return tool, tool_input, directory
    return tool, tool_input, None


def shell_calls(tool_input: dict[str, JsonValue], directory: str | None) -> list[Call]:
    """The shell call of a `shell` input, and the same call with a leading `rtk ` removed."""
    command = tool_input.get("command")
    if not isinstance(command, str):
        raise HarnessError("the shell call holds no string command")
    try:
        size = len(command.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise HarnessError(f"the command is no UTF-8 text: {error.reason} at {error.start}") from None
    if size > MAX_COMMAND:
        raise HarnessError(
            f"the command holds {size} bytes, more than the {MAX_COMMAND} that the guard reads"
        )
    workdir = tool_input.get("workdir")
    cwd, wide = directory, ()
    if isinstance(workdir, str):
        given = path_list.expanded(workdir)
        if PurePosixPath(given).is_absolute():
            cwd = path_list.kept(given)
        else:
            cwd = None if directory is None else path_list.kept(directory + "/" + given)
        wide = (workdir if cwd is None else cwd,)
    forms = dict.fromkeys((command, RTK.sub("", command, count=1)))
    return [Call("shell", form, (), cwd, "main", wide=wide) for form in forms]


def decide(data: bytes) -> Verdict:
    """The guard's verdict on the message bytes `data`: the strongest verdict of the checks of the
    tool on each form of the call; a pass for a tool that the table does not name."""
    found = lists()
    if isinstance(found, str):
        return Verdict("deny", found)
    tool, tool_input, directory = read(data)
    if tool == "shell":
        return strongest(check(call) for call in shell_calls(tool_input, directory) for check in SHELL)
    if tool in KAIMON:
        arguments = tuple((key, value) for key, value in tool_input.items() if isinstance(value, str))
        return kaimon_session.check(Call("mcp", KAIMON[tool], (), directory, "main", arguments))
    return PASS


def render(verdict: Verdict) -> dict[str, object]:
    """The verdict as the plugin reads it: a block for `deny` and `ask`, an `ask` with ASK_USER."""
    if verdict.decision == "deny":
        return {"block": True, "reason": verdict.reason}
    if verdict.decision == "ask":
        return {"block": True, "reason": f"{verdict.reason.rstrip()}\n\n{ASK_USER}"}
    return {"block": False, "reason": ""}


def answer(verdict: Verdict, stdout: TextIO) -> int:
    """Write the verdict as the plugin reads it, and return the exit status, 0."""
    stdout.write(json.dumps(render(verdict)) + "\n")
    return 0
