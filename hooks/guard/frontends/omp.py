"""oh-my-pi's table: the message of the guard extension `extensions/guards.ts` as a `Call`, the checks
of each tool, and a `Verdict` as the answer that the extension returns.

The extension sends each `tool_call` event as one JSON object on stdin, `{"event": {type,
toolCallId, toolName, input}, "cwd": <the session's working directory>, "agent": {"kind": …}}`, and
reads one object on stdout, `{"block": <bool>, "reason": <text>}`, after exit 0, which is
oh-my-pi's own answer to a `tool_call` handler. The extension asks no user, so an `ask` is a block
whose reason tells the model to ask the user in chat.

THE LISTS. The table reads `guard-paths.json` beside the extension before it reads the tool: `deny`,
with oh-my-pi's own directory but the copies that it reads (OWN_READABLE), for every call; `edit`,
with the whole of that directory, and then `ask`, for an `edit` and a `write`. A list that is
missing or cannot be used refuses every call. The path list reads oh-my-pi's form of a command: each
word, each path that TEXT_PATH finds, every word of a part that runs `cd`, and a glob path as
reaching only the names that its glob segment matches.

THE CALLS. `bash` is a shell call: `input.command`, in `input.cwd` resolved against the session's
working directory, else in that directory; the working directory is a path of the call, which it
reads below when `input.cwd` is given or the command recurses. `read` and `grep` read `input.path`,
a `grep` with none the working directory, and a `grep` reads below its path. `edit` edits each path
that it names (edit_paths), and `write` writes `input.path` and the path of its hashline header
(write_path). Each tool path is checked in every form that oh-my-pi may read (path_forms).
`mcp__kaimon_ex` and `mcp__kaimon_manage_repl` are the `mcp` calls `kaimon.ex` and
`kaimon.manage_repl`. The caller is `sub` when the agent's kind is `sub`, and a sub-agent's write
to `agent://` is refused (agent_write). Every other tool passes.

A message that the table cannot read is refused: bytes that are not UTF-8, a text that `jsonio`
refuses, no object `event`, no string `toolName`, an `input` that is no object, a `bash` call
without a string `command` or with one of more than MAX_COMMAND bytes of UTF-8, and a `read`, `edit`
or `write` that names no path.
"""

import functools
import re
import urllib.parse
from collections.abc import Callable
from pathlib import Path
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
    plugin,
    rm_scope,
    sandbox_semantics,
)
from guard.contract import PASS, Action, Call, Caller, Verdict, strongest
from guard.jsonio import JsonValue

type Check = Callable[[Call], Verdict]

# The longest command the guard reads: 1 MiB of UTF-8.
MAX_COMMAND = 1024 * 1024
# The path list that `harness install` renders beside the extension, in `extensions/` beside `hooks/`.
PATH_LIST = str(Path(__file__).parents[3] / "extensions" / "guard-paths.json")
# oh-my-pi's own directory, where its credentials and the extension lie.
OWN = path_list.normal(path_list.HOME + "/.omp")
# The copies below OWN that `harness install` writes for the model to read.
OWN_READABLE: path_list.Rule = (
    f"{OWN}/** but agent/skills, agent/rules, agent/instructions and agent/RTK.md",
    re.compile(
        re.escape(OWN) + r"(?:/(?!agent/(?:(?:skills|rules|instructions)(?:/|\Z)|RTK\.md\Z)).*)?",
        re.IGNORECASE,
    ),
    OWN.lower(),
)
OWN_EDIT: path_list.Rule = (f"{OWN}/**", path_list.rule(f"{OWN}/**"), OWN.lower())
READING = path_list.Reading(text_paths=True, cd_parts=True, segment_glob=True)
# The Kaimon tools, by oh-my-pi's name, and their neutral names.
KAIMON = {"mcp__kaimon_ex": "kaimon.ex", "mcp__kaimon_manage_repl": "kaimon.manage_repl"}
FILE_TOOLS: dict[str, Action] = {"read": "read", "grep": "read", "edit": "edit", "write": "write"}
AGENT = re.compile(r"\s*agent://", re.IGNORECASE)
# A hashline header's tag: `#` and four hexadecimal digits at the end.
TAG = re.compile(r"#[0-9A-Fa-f]{4}\Z")
HEADER = (
    re.compile(r"\[(.*?)\]?"),
    re.compile(r"MV\s+(.+)"),
    re.compile(r"\*\*\*\s*(?:(?:Add|Update|Delete|Edit)\s+File|Move\s+to)\s*:\s*(.+)", re.IGNORECASE),
)
SUB_AGENT = (
    "Refused by the guard: a sub-agent writes to no other agent ({path}). A write to agent:// wakes a "
    "parked agent, which then returns stale output. Put what you need in your report to your caller, "
    "and let your caller spawn a new agent."
)
ASK_USER = (
    "This call needs the approval of the user, and this extension does not ask for it. Do not run it "
    "in another form. Ask the user in chat, and give the user the command or the change to make."
)


@functools.cache
def lists() -> path_list.Lists | str:
    """The rules of the extension's path list, with oh-my-pi's own directory, or the reason to refuse
    every call."""
    found: list[tuple[path_list.Rule, ...]] = []
    for key in ("deny", "edit", "ask"):
        rules = path_list.path_rules(PATH_LIST, key)
        if isinstance(rules, str):
            return rules
        found.append(rules)
    deny, edit, ask = found
    return path_list.Lists((*deny, OWN_READABLE), (*edit, OWN_EDIT), ask, None, READING)


def listed(call: Call) -> Verdict:
    """The path list's verdict on `call`."""
    found = lists()
    return Verdict("deny", found) if isinstance(found, str) else path_list.check_paths(call, found)


def agent_write(call: Call) -> Verdict:
    """Deny a sub-agent's write to `agent://<name>`, which messages that agent and wakes it when it
    is parked; a session's write passes."""
    if call.action == "write" and call.caller == "sub" and AGENT.match(call.command):
        return Verdict("deny", SUB_AGENT.format(path=call.command.strip()))
    return PASS


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
    "edit": (listed,),
    "write": (agent_write, listed),
    "mcp": (kaimon_session.check,),
}


def file_url(text: str) -> str | None:
    """The path of the `file://` URL `text`, as Node's `fileURLToPath` decodes it, or None for a URL
    with a host or an encoded `/`."""
    parts = urllib.parse.urlsplit(text)
    if parts.netloc not in ("", "localhost") or "%2f" in parts.path.lower():
        return None
    return urllib.parse.unquote(parts.path)


def path_forms(raw: str) -> list[str]:
    """Each form of the tool path `raw` that oh-my-pi may read: the whole text and each piece that `,`,
    `;` or a blank separates; a leading `@` or `:` removed; a `file://` URL decoded; and each with a
    selector suffix `:…` removed."""
    forms: list[str] = []
    for piece in dict.fromkeys((raw, *re.split(r"[,;\s]+", raw))):
        text = re.sub(r"^(?:[@:](?=[/~])|:(?=\.\.?/))", "", piece.strip())
        decoded = file_url(text) if re.match(r"file://", text, re.IGNORECASE) else None
        for form in (text, *(() if decoded is None else (decoded,))):
            forms += [form, re.sub(r":[^/]*\Z", "", form)]
    return [form for form in dict.fromkeys(forms) if form]


def header_path(text: str) -> str:
    """A header path as oh-my-pi's hashline parser reads it: trimmed, a tag removed, then one pair of
    quotes around it removed."""
    stripped = text.strip()
    tag = TAG.search(stripped)
    path = stripped[: tag.start()] if tag else stripped
    quoted = path[:1] in ('"', "'") and path[1:].endswith(path[:1])
    return path[1:-1] if quoted else path


def edit_paths(tool_input: dict[str, JsonValue]) -> list[str]:
    """The paths that an `edit` call names: `path`, the `rename` of each of its `edits`, and the file
    headers of a hashline or apply_patch `input`, each as written, with its tag removed, and as
    oh-my-pi reads it."""
    paths: list[str] = []
    if isinstance(path := tool_input.get("path"), str):
        paths.append(path)
    edits = tool_input.get("edits")
    paths.extend(
        rename
        for edit in (edits if isinstance(edits, list) else [])
        if isinstance(edit, dict) and isinstance(rename := edit.get("rename"), str)
    )
    text = tool_input.get("input")
    for line in text.split("\n") if isinstance(text, str) else []:
        found = next((m for header in HEADER if (m := header.fullmatch(line.strip()))), None)
        if found is not None:
            named = found.group(1)
            paths += [named, re.sub(r"#[^#/]*\Z", "", named), header_path(named)]
    return paths


def write_path(raw: str) -> str:
    """The path that oh-my-pi's `write` tool writes for `raw`: a hashline header `[path]` or
    `[path#TAG]` unwrapped once; else `raw`."""
    text = raw.rstrip()
    if not (text.startswith("[") and text[1:].endswith("]")):
        return raw
    inner = text[1:-1]
    tag = TAG.search(inner)
    path = inner[: tag.start()] if tag else inner
    return raw if path == "" or (not tag and "#" in path) else path


def read(data: bytes) -> tuple[str, dict[str, JsonValue], str | None, Caller]:
    """The tool, the input, the working directory and the caller of the message bytes `data`."""
    found, event = plugin.message(data)
    tool = event.get("toolName")
    if not isinstance(tool, str):
        raise HarnessError("the event has no string toolName")
    given = found.get("cwd")
    cwd = path_list.kept(given) if isinstance(given, str) and given.startswith("/") else None
    agent = found.get("agent")
    caller: Caller = "sub" if isinstance(agent, dict) and agent.get("kind") == "sub" else "main"
    return tool, plugin.tool_input(event, tool), cwd, caller


def shell_call(tool_input: dict[str, JsonValue], cwd: str | None, caller: Caller) -> Call:
    """The shell call of a `bash` input. A relative `input.cwd` with no working directory to resolve
    it against has no place, so the call has none."""
    command = plugin.command(tool_input, "bash", MAX_COMMAND)
    given = tool_input.get("cwd")
    if isinstance(given, str):
        moved = path_list.expanded(given)
        absolute = moved.startswith("/")
        directory = path_list.kept(moved if absolute else f"{cwd}/{moved}") if absolute or cwd else None
    else:
        directory = cwd
    wide = isinstance(given, str) or path_list.recursive(command)
    held = () if directory is None else (directory,)
    return Call("shell", command, () if wide else held, directory, caller, wide=held if wide else ())


def call_of(tool: str, tool_input: dict[str, JsonValue], cwd: str | None, caller: Caller) -> Call | None:
    """The `Call` of the tool `tool` with the input `tool_input`, or None for a tool that the table
    does not name."""
    if tool == "bash":
        return shell_call(tool_input, cwd, caller)
    if tool in KAIMON:
        arguments = tuple((key, value) for key, value in tool_input.items() if isinstance(value, str))
        return Call("mcp", KAIMON[tool], (), cwd, caller, arguments)
    action = FILE_TOOLS.get(tool)
    if action is None:
        return None
    path = tool_input.get("path")
    if tool == "grep" and path is None:
        path = cwd or "."
    if tool == "edit":
        named = edit_paths(tool_input)
    else:
        named = [path, write_path(path)] if tool == "write" and isinstance(path, str) else []
        named = named or ([path] if isinstance(path, str) else [])
    if not named:
        raise HarnessError(f"the {tool} call names no path")
    forms = tuple(dict.fromkeys(form for name in named for form in path_forms(name)))
    first = named[0]
    if tool == "grep":
        return Call(action, first, (), cwd, caller, wide=forms)
    return Call(action, first, forms, cwd, caller)


def decide(data: bytes) -> Verdict:
    """The guard's verdict on the message bytes `data`: the strongest verdict of the checks of the
    tool; a pass for a tool that the table does not name."""
    found = lists()
    if isinstance(found, str):
        return Verdict("deny", found)
    call = call_of(*read(data))
    if call is None:
        return PASS
    return strongest(check(call) for check in CHECKS[call.action])


def answer(verdict: Verdict, stdout: TextIO) -> int:
    """Write the verdict as the extension reads it, an `ask` with ASK_USER, and return the exit
    status, 0."""
    return plugin.answer(verdict, stdout, ASK_USER)
