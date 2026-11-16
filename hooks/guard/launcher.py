"""Refuse every call of a session that runs outside `agentbox`, the launcher whose sandbox holds a
frontend's file tools, hooks and MCP servers.

The check tests behaviour, not a variable, which anyone can set: under `agentbox` the sandbox of
each frontend denies `~/.ssh`, and the guard, a child of the frontend, cannot list it. So on macOS
a listing of `<home>/.ssh` that raises `PermissionError` passes, one that raises another `OSError`,
such as `FileNotFoundError` for a home with no `~/.ssh`, is refused because the guard cannot tell,
and one that returns is refused: the session runs outside `agentbox`. Only Claude Code's own
sandbox counts in its place, in two sessions. In the Code tab of the Claude desktop app,
`CLAUDE_CODE_ENTRYPOINT` is `claude-desktop` and `~/.claude/settings.json` holds `sandbox.enabled`
as `true`. In a session that `claudex` starts, `CLAUDE_CONFIG_DIR` is an absolute path that
resolves to `~/.config/claudex`, and `settings.json` there holds `sandbox.enabled` as `true`. A
settings file that is missing, no regular file, or cannot be read or parsed counts as no sandbox,
and a plain `claude` session stays refused. On another platform the check passes: there is no
launcher there. The check reads the file system at each call and keeps nothing.
"""

from collections.abc import Mapping
from pathlib import Path

from . import HarnessError
from .contract import PASS, Verdict
from .jsonio import load

# The name of each frontend whose table runs the check.
NAMES = {"claude": "Claude Code", "opencode": "OpenCode", "omp": "oh-my-pi"}
# The value of `CLAUDE_CODE_ENTRYPOINT` in the Code tab of the Claude desktop app.
CODE_TAB = "claude-desktop"

OUTSIDE = """Refused: this {name} session runs outside `agentbox`, with `~/.ssh` readable, so no sandbox
holds its file tools, its hooks and its MCP servers.{tab}

Stop, and ask the user to start the session again with `agentbox {frontend}`{own}.
"""

TAB = """

Claude Code's own sandbox counts only in the Code tab of the Claude desktop app, with
`sandbox.enabled` set to `true` in `~/.claude/settings.json`, and in a session that `claudex`
starts, with `CLAUDE_CONFIG_DIR` at `~/.config/claudex` and `sandbox.enabled` set to `true` in
`settings.json` there."""

OWN = ",\nor with `claudex` for Claude Code's own sandbox"

UNKNOWN = """Refused: the guard cannot tell whether a sandbox holds this {name} session: the listing of
`~/.ssh` fails with {error}, where under `agentbox` it fails with PermissionError.

Stop, and ask the user to check that `~/.ssh` is a directory, and to start the session again with
`agentbox {frontend}`.
"""


def sandbox_on(path: Path) -> bool:
    """True when the Claude Code settings file `path` holds `sandbox.enabled` as `true`. A file that is
    missing, no regular file, such as a FIFO whose read would block, or that cannot be read or parsed
    counts as no sandbox."""
    try:
        settings = load(path)
    except HarnessError:
        return False
    sandbox = settings.get("sandbox")
    return isinstance(sandbox, dict) and sandbox.get("enabled") is True


def code_tab(home: str, environ: Mapping[str, str]) -> bool:
    """True in the Code tab of the Claude desktop app with Claude Code's sandbox on: the entrypoint
    is CODE_TAB and `<home>/.claude/settings.json` holds `sandbox.enabled` as `true`."""
    if environ.get("CLAUDE_CODE_ENTRYPOINT") != CODE_TAB:
        return False
    return sandbox_on(Path(home, ".claude", "settings.json"))


def claudex(home: str, environ: Mapping[str, str]) -> bool:
    """True in a session that `claudex` starts, with Claude Code's sandbox on: `CLAUDE_CONFIG_DIR` is
    an absolute path that resolves to `<home>/.config/claudex`, and `settings.json` there holds
    `sandbox.enabled` as `true`. A relative value is refused, because Claude Code resolves it against
    a working directory that the guard does not know; both sides are resolved, so that another
    spelling of the home or a link to the directory counts and a `..` out of it does not."""
    value = environ.get("CLAUDE_CONFIG_DIR", "")
    if not Path(value).is_absolute():
        return False
    config = Path(value).resolve()
    if config != Path(home, ".config", "claudex").resolve():
        return False
    return sandbox_on(Path(config, "settings.json"))


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
    if frontend == "claude" and (code_tab(home, environ) or claudex(home, environ)):
        return PASS
    tab, own = (TAB, OWN) if frontend == "claude" else ("", "")
    return Verdict("deny", OUTSIDE.format(name=name, tab=tab, frontend=frontend, own=own))
