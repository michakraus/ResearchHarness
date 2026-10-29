"""Refuse a Kaimon call that names no session.

The check denies a Kaimon `ex` call without `ses`, and a `manage_repl` call without `session`.
Without the key, Kaimon takes the session the agent is bound to, else the only connected one; under
a builder-critic loop several agents hold sessions at once, so a call without the key runs in
another agent's session, or shuts it down. `ex` drops an unknown parameter silently, so `session`
in place of `ses` is refused too. `check_eval` takes only `eval_id`, which names its job, and no
table names it for this check.
"""

from .contract import PASS, Call, Verdict

# The session parameter of each tool, by its neutral name.
KEYS = {"kaimon.ex": "ses", "kaimon.manage_repl": "session"}

EXAMPLES = {
    "kaimon.ex": "ex(e = …, q = false, ses = <key>)",
    "kaimon.manage_repl": 'manage_repl(command = "…", session = <key>)',
}

MESSAGE = """Refused: `{tool}` without `{key}`.

Pass the session key on every call: `{example}`. `start_session` returns the key, and `ping`
lists the sessions. Without it, the call runs in the session that Kaimon picks, which can be
another agent's. The rule is in `skills/build-part/evidence.md`, *A warm session for probes*:
one session for your tree, `ses` on every `ex`, and a shutdown with `session` before you return.
"""


def check(call: Call) -> Verdict:
    """Deny a Kaimon `ex` or `manage_repl` call without its session key."""
    key = KEYS.get(call.command)
    if call.action != "mcp" or key is None:
        return PASS
    value = call.argument(key)
    if value is not None and value.strip():
        return PASS
    tool = call.command.split(".", 1)[1]
    return Verdict("deny", MESSAGE.format(tool=tool, key=key, example=EXAMPLES[call.command]))
