"""Refuse every call of a session that runs outside `agentbox`, the launcher whose sandbox holds a
frontend's file tools, hooks and MCP servers.

The check tests behaviour, not a variable, which anyone can set: under `agentbox` the sandbox of
each frontend denies `~/.ssh`, and the guard, a child of the frontend, cannot list it. So on macOS
a listing of `<home>/.ssh` that raises `PermissionError` passes, one that raises another `OSError`,
such as `FileNotFoundError` for a home with no `~/.ssh`, is refused because the guard cannot tell,
and one that returns is refused: the session runs outside `agentbox`. Only Claude Code's own
sandbox counts in its place, in the Code tab of the Claude desktop app: `CLAUDE_CODE_ENTRYPOINT`
is `claude-desktop` and `~/.claude/settings.json` holds `sandbox.enabled` as `true`; a settings
file that is missing or cannot be read counts as no sandbox. On another platform the check passes:
there is no launcher there. The check reads the file system at each call and keeps nothing.
"""

from collections.abc import Mapping
from pathlib import Path

from . import HarnessError
from .contract import PASS, Verdict
from .jsonio import loads

# The name of each frontend whose table runs the check.
NAMES = {"claude": "Claude Code", "opencode": "OpenCode", "omp": "oh-my-pi"}
# The value of `CLAUDE_CODE_ENTRYPOINT` in the Code tab of the Claude desktop app.
CODE_TAB = "claude-desktop"

OUTSIDE = """Refused: this {name} session runs outside `agentbox`, with `~/.ssh` readable, so no sandbox
holds its file tools, its hooks and its MCP servers.{tab}

Stop, and ask the user to start the session again with `agentbox {frontend}`.
"""

TAB = """ Claude Code's own sandbox counts only in the Code tab of the Claude desktop app, with
`sandbox.enabled` set to `true` in `~/.claude/settings.json`."""

UNKNOWN = """Refused: the guard cannot tell whether a sandbox holds this {name} session: the listing of
`~/.ssh` fails with {error}, where under `agentbox` it fails with PermissionError.

Stop, and ask the user to check that `~/.ssh` is a directory, and to start the session again with
`agentbox {frontend}`.
"""


def code_tab(home: str, environ: Mapping[str, str]) -> bool:
    """True in the Code tab of the Claude desktop app with Claude Code's sandbox on: the entrypoint
    is CODE_TAB and `<home>/.claude/settings.json` holds `sandbox.enabled` as `true`."""
    if environ.get("CLAUDE_CODE_ENTRYPOINT") != CODE_TAB:
        return False
    try:
        text = Path(home, ".claude", "settings.json").read_text(encoding="utf-8")
        settings = loads(text, where="~/.claude/settings.json")
    except OSError, UnicodeDecodeError, HarnessError:
        return False
    sandbox = settings.get("sandbox")
    return isinstance(sandbox, dict) and sandbox.get("enabled") is True


def outside(frontend: str, home: str, environ: Mapping[str, str], platform: str) -> Verdict:
    """The refusal of a call of `frontend`, a key of NAMES, from a session that no sandbox holds,
    with the home `home`, the environment `environ` and the platform `platform`, as `sys.platform`
    names it; `PASS` when a sandbox holds it, and on another platform than macOS."""
    if platform != "darwin":
        return PASS
    name = NAMES[frontend]
    try:
        # `next` takes the first entry, so that the directory is listed whatever `iterdir` defers.
        next(Path(home, ".ssh").iterdir(), None)
    except PermissionError:
        return PASS
    except OSError as error:
        return Verdict("deny", UNKNOWN.format(name=name, error=type(error).__name__, frontend=frontend))
    if frontend == "claude" and code_tab(home, environ):
        return PASS
    tab = TAB if frontend == "claude" else ""
    return Verdict("deny", OUTSIDE.format(name=name, tab=tab, frontend=frontend))
