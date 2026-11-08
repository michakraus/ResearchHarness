"""Refuse a web request that identifies the user: one that carries the user's email address, or a
query parameter by which a service identifies its client.

A web request leaves the machine. A literature index such as OpenAlex or Crossref asks an
automated client for an email address (`mailto=`) or a key (`api_key=`), and a fetched page can
ask an agent to create a key with the user's email. Neither is the agent's to give. The check
reads each text percent-decoded and without case, and refuses:

  * a web call, the neutral `web.fetch` or `web.search`, any of whose string arguments holds a
    query parameter of IDENTIFYING or the user's email address;
  * a shell call whose command holds a query parameter of IDENTIFYING, or holds `://` and the
    user's email address.

A parameter counts after `?` or `&` only, so a word such as `mailto=` in prose or in a pattern
passes. The user's email address is the value of `git config --get user.email`, read at most once
per process in the guard's working directory; without git or without the key, the check reads the
parameters alone. A request that a script builds from a file, and a request of any other tool, are
beyond the check's reach.
"""

import functools
import re
import shutil
import subprocess
from urllib.parse import unquote

from .contract import PASS, Call, Verdict
from .jsonio import JsonValue

# The neutral names of the web tools of every frontend.
WEB_TOOLS = ("web.fetch", "web.search")
# A query parameter by which a service identifies its client.
IDENTIFYING = re.compile(r"[?&](mailto|e-?mail|api[_-]?key|access_token)=", re.IGNORECASE)
# The longest wait for `git config`, in seconds.
TIMEOUT = 2

REFUSED = """Refused: {what}

The request carries {problem}. Send every web request anonymously: no name, email address,
`mailto=` parameter, API key or token of the user, and no placeholder address in their place.
Create no account or key. An index that rate-limits an anonymous request, or asks for contact
details or a key, is a failed source: report it and use another one.
"""


def string_arguments(tool_input: dict[str, JsonValue]) -> tuple[tuple[str, str], ...]:
    """Each string argument of a tool call, by name."""
    return tuple((key, value) for key, value in tool_input.items() if isinstance(value, str))


@functools.cache
def own_email() -> str | None:
    """The user's email address in lower case, `git config --get user.email`, read once per
    process; None when git is missing, times out, or gives no address."""
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "config", "--get", "user.email"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    email = result.stdout.strip().lower()
    return email if result.returncode == 0 and "@" in email else None


def problem(text: str, *, web: bool) -> str | None:
    """What in `text` identifies the user, or None. A shell command needs `://` beside the email
    address; a web call's argument does not."""
    decoded = unquote(text)
    found = IDENTIFYING.search(decoded)
    if found is not None:
        return f"the query parameter `{found.group(1)}=`, by which a service identifies its client"
    if not web and "://" not in decoded:
        return None
    email = own_email()
    if email is not None and email in decoded.lower():
        return "the user's email address"
    return None


def check(call: Call) -> Verdict:
    """Deny a web call or a shell command that identifies the user."""
    if call.action == "shell":
        why = problem(call.command, web=False)
        what = call.command
    elif call.action == "mcp" and call.command in WEB_TOOLS:
        found = ((value, problem(value, web=True)) for _, value in call.arguments)
        value, why = next(((value, why) for value, why in found if why is not None), ("", None))
        what = f"{call.command} {value}"
    else:
        return PASS
    if why is None:
        return PASS
    return Verdict("deny", REFUSED.format(what=what, problem=why))
