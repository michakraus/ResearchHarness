"""Refuse a Kaimon call that names no session, the wrong key, or a session that is not live.

Each Kaimon tool takes its session key under one name, or under none: `ex` takes `ses`, the tools
of SESSION take `session`, and the tools of NO_KEY take neither. Kaimon drops an unknown parameter
silently, so a key under the other name, such as `session` on `ex` or `ses` on `manage_repl`, runs
the call in the session that Kaimon picks: the one the agent is bound to, else the only connected
one, which under a builder-critic loop can be another agent's. The check refuses such a key and
names the tool's own. It also refuses an `ex` without `ses` and a `manage_repl` without `session`,
the two calls that run code in a session or stop it. A tool that no table names passes.

A key that is given must name a live session. A session's gate writes `<cache>/sock/<session
id>.json`, which holds its process id as `pid`, and its key is the first 8 characters of the
session id, which Kaimon matches as a prefix; the cache is `$KAIMON_CACHE_DIR`, else
`$XDG_CACHE_HOME/kaimon`, else `~/.cache/kaimon`, as KaimonGate resolves it. Kaimon removes the
file when the session shuts down or when it reaps a gone one; a process that dies before that
leaves it behind. Kaimon finds a gate only through its file, so a key without one names no session
that Kaimon routes. So a session is live when a file of the key is there and its process runs. The
socket files are no evidence: Kaimon leaves them behind when a session ends. The check reads the
files as they are at the call, and keeps nothing. When the directory does not exist, or a file
cannot be read or holds no integer `pid`, the check cannot tell and passes. A key `tcp-…` names a
remote gate, which writes no file, and passes. Under WSL, Kaimon also finds the gates of the
Windows side, through files in a directory that the check does not read, so the check refuses
their keys. `manage_repl` is not checked for a live session: its `shutdown` is how an agent removes
a session whose process has gone.
"""

import os
from pathlib import Path

from . import HarnessError, paths
from .contract import PASS, Call, Verdict
from .jsonio import loads

# The Kaimon tools that take the session key as `session`, and those that take none.
SESSION = (
    "code_lowered",
    "code_typed",
    "debug_ctrl",
    "debug_eval",
    "debug_exfiltrate",
    "debug_safehouse",
    "format_code",
    "goto_definition",
    "investigate_environment",
    "lint_package",
    "list_names",
    "macro_expand",
    "manage_repl",
    "pkg_add",
    "pkg_rm",
    "profile_code",
    "run_tests",
    "search_methods",
    "set_tty",
    "stress_test",
    "type_info",
    "workspace_symbols",
)
NO_KEY = (
    "cancel_eval",
    "check_eval",
    "check_tests",
    "connect_tcp",
    "document_symbols",
    "edit_code",
    "execute_vscode_command",
    "extension_info",
    "grep_code",
    "list_jobs",
    "list_vscode_commands",
    "manage_extension",
    "navigate_to_file",
    "ping",
    "rename_symbol",
    "search_code",
    "server_log",
    "start_session",
    "tool_help",
    "tui_screenshot",
    "usage_instructions",
    "usage_quiz",
)
# The session key of each Kaimon tool, by its neutral name; None for a tool that takes none.
KEYS: dict[str, str | None] = {
    "kaimon.ex": "ses",
    **{f"kaimon.{tool}": "session" for tool in SESSION},
    **{f"kaimon.{tool}": None for tool in NO_KEY},
}
# The tools that must name their session.
REQUIRED = ("kaimon.ex", "kaimon.manage_repl")

EXAMPLES = {
    "kaimon.ex": "ex(e = …, q = false, ses = <key>)",
    "kaimon.manage_repl": 'manage_repl(command = "…", session = <key>)',
}

MISSING = """Refused: `{tool}` without `{key}`.

Pass the session key on every call: `{example}`. `start_session` returns the key, and `ping`
lists the sessions. Without it, the call runs in the session that Kaimon picks, which can be
another agent's. The rule is in `skills/build-part/evidence.md`, *A warm session for probes*:
one session for your tree, `ses` on every `ex`, and a shutdown with `session` before you return.
"""

WRONG = """Refused: `{tool}` with `{given}`, which it does not take.

{takes} Kaimon drops a parameter that the tool does not take, so the call would run in the session
that Kaimon picks, which can be another agent's.
"""

GONE = """Refused: no live Kaimon session has the key `{value}`.

{live} The session has ended, or the key is stale. Call `ping`: reuse the live session of your
tree if it lists one, else start one with `start_session(project_path = <tree>)`. When a start
times out twice, or Kaimon is not connected, probe in a fresh process,
`julia --startup-file=no <file>`, and go on; the rule is in `skills/build-part/evidence.md`,
*A warm session for probes*.
"""


def gate_directory() -> Path:
    """The directory of the gates' files, `sock/` of Kaimon's cache, as KaimonGate resolves it."""
    explicit = os.environ.get("KAIMON_CACHE_DIR", "")
    if explicit:
        return Path(explicit) / "sock"
    cache = os.environ.get("XDG_CACHE_HOME", "") or str(Path.home() / ".cache")
    return Path(cache) / "kaimon" / "sock"


def runs(metadata: Path) -> bool | None:
    """True when the process that the gate file `metadata` names runs, False when it does not,
    None when the file cannot be read or names no process."""
    try:
        pid = loads(paths.contents(str(metadata)), where=str(metadata)).get("pid")
    except OSError, UnicodeDecodeError, HarnessError:
        return None
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process runs under another user.
        return True
    return True


def gone(value: str) -> Verdict:
    """A refusal when no live gate has the key `value`; `PASS` when one has, or when the check
    cannot tell."""
    if value.startswith("tcp-"):
        return PASS
    directory = gate_directory()
    try:
        names = paths.entries(str(directory))
    except OSError:
        return PASS
    found = {name.removesuffix(".json"): directory / name for name in names if name.endswith(".json")}
    if any(runs(path) is not False for sid, path in found.items() if sid.startswith(value)):
        return PASS
    live = [sid[:8] for sid, path in found.items() if runs(path)]
    listed = (
        "The live sessions are " + ", ".join(f"`{key}`" for key in live) + "."
        if live
        else "No session is live."
    )
    return Verdict("deny", GONE.format(value=value, live=listed))


def wrong_key(call: Call, tool: str, key: str | None) -> Verdict:
    """A refusal when `call` passes a session key under a name that its tool does not take."""
    for given in ("ses", "session"):
        if given != key and call.argument(given) is not None:
            takes = (
                f"`{tool}` takes the session key as `{key}`." if key else f"`{tool}` takes no session key."
            )
            return Verdict("deny", WRONG.format(tool=tool, given=given, takes=takes))
    return PASS


def named(call: Call, tool: str, key: str) -> Verdict:
    """A refusal when `call` lacks the key `key` that its tool must name, or names no live
    session with it."""
    # Kaimon matches the key as given, so a key with a blank around it names no session.
    value = call.argument(key) or ""
    if not value.strip():
        if call.command in REQUIRED:
            return Verdict("deny", MISSING.format(tool=tool, key=key, example=EXAMPLES[call.command]))
        return PASS
    return PASS if call.command == "kaimon.manage_repl" else gone(value)


def check(call: Call) -> Verdict:
    """Deny a Kaimon call with a session key that its tool does not take, an `ex` or a
    `manage_repl` without its key, and a key that names no live session."""
    if call.action != "mcp" or call.command not in KEYS:
        return PASS
    tool = call.command.split(".", 1)[1]
    key = KEYS[call.command]
    refused = wrong_key(call, tool, key)
    if refused.decision != "pass" or key is None:
        return refused
    return named(call, tool, key)
