"""Refuse an outgoing call that holds a token of a known form.

A token typed into a command, a URL or a tool argument leaves the machine with the call. The check
reads each text as it is and percent-decoded, with the case kept, and refuses:

  * a shell call whose command holds a token of FORMS;
  * an `mcp` call, such as a Kaimon or a web call, any of whose string arguments holds one.

A form counts only where no letter, digit, `_` or `-` stands right before its prefix, so a word
such as `task-…` holds no `sk-` key. A prefix alone, a shorter body, an upper-case prefix and a
reference such as `$GH_TOKEN` pass. The check prevents an accident and is no boundary: a token that
is encoded otherwise, split, given without its prefix, or read by a script from a file passes it.
"""

import re
from urllib.parse import unquote

from .contract import PASS, Call, Verdict

# What stands right before a prefix: no letter, digit, `_` or `-`.
BOUNDARY = r"(?<![A-Za-z0-9_-])"

# (form, pattern): the published token forms of GitHub, GitLab and the providers of `sk-` keys.
FORMS = (
    ("gh[pousr]_", re.compile(BOUNDARY + r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("github_pat_", re.compile(BOUNDARY + r"github_pat_[A-Za-z0-9_]{22,}")),
    ("glpat-", re.compile(BOUNDARY + r"glpat-[A-Za-z0-9_-]{20,}")),
    ("sk-", re.compile(BOUNDARY + r"sk-[A-Za-z0-9_-]{20,}")),
)

REFUSED = """Refused: the call holds a token of the form `{form}`.

A token in a command, a URL or a tool argument leaves the machine with the call. Name the token
by the variable that holds it, such as `$GH_TOKEN`, or let the tool read it from its own
configuration. Do not send the token in another form.
"""


def form_in(text: str) -> str | None:
    """The form of the first token of FORMS that `text` holds, as it is or percent-decoded."""
    for value in dict.fromkeys((text, unquote(text))):
        for form, pattern in FORMS:
            if pattern.search(value):
                return form
    return None


def check(call: Call) -> Verdict:
    """Deny a shell command, or an `mcp` call's string argument, that holds a token of FORMS."""
    if call.action == "shell":
        texts: tuple[str, ...] = (call.command,)
    elif call.action == "mcp":
        texts = tuple(value for _, value in call.arguments)
    else:
        return PASS
    form = next((found for text in texts if (found := form_in(text)) is not None), None)
    return PASS if form is None else Verdict("deny", REFUSED.format(form=form))
