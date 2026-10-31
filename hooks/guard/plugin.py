"""What the tables of the two plugin frontends, OpenCode and oh-my-pi, share: the reading of a
plugin's message, the size check of its shell command, and the answer that the plugin applies.

A plugin sends one JSON object on stdin, whose object `event` holds the tool call, and reads one
object on stdout, `{"block": <bool>, "reason": <text>}`, after exit 0. Neither plugin can ask the
user, so an `ask` is a block whose reason tells the model to ask the user in chat.
"""

import json
from typing import TextIO

from . import HarnessError
from .contract import Verdict
from .jsonio import JsonValue, loads


def message(data: bytes) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """The message of the bytes `data` and its object `event`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessError(f"the message is not UTF-8: {error.reason} at byte {error.start}") from None
    found = loads(text, where="the message")
    event = found.get("event")
    if not isinstance(event, dict):
        raise HarnessError("the message has no object event")
    return found, event


def tool_input(event: dict[str, JsonValue], tool: str) -> dict[str, JsonValue]:
    """The object `input` of the event `event` of the tool `tool`; an empty one when it has none."""
    found = event.get("input", {})
    if not isinstance(found, dict):
        raise HarnessError(f"the input of {tool} is no object")
    return found


def command(tool_input: dict[str, JsonValue], tool: str, limit: int) -> str:
    """The string `command` of the input of a shell tool `tool`, of at most `limit` bytes of UTF-8."""
    found = tool_input.get("command")
    if not isinstance(found, str):
        raise HarnessError(f"the {tool} call holds no string command")
    try:
        size = len(found.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise HarnessError(f"the command is no UTF-8 text: {error.reason} at {error.start}") from None
    if size > limit:
        raise HarnessError(f"the command holds {size} bytes, more than the {limit} that the guard reads")
    return found


def answer(verdict: Verdict, stdout: TextIO, ask_user: str) -> int:
    """Write the verdict as the plugin reads it, a block for `deny` and `ask` and an `ask` with
    `ask_user`, and return the exit status, 0."""
    if verdict.decision == "deny":
        found = {"block": True, "reason": verdict.reason}
    elif verdict.decision == "ask":
        found = {"block": True, "reason": f"{verdict.reason.rstrip()}\n\n{ask_user}"}
    else:
        found = {"block": False, "reason": ""}
    stdout.write(json.dumps(found) + "\n")
    return 0
