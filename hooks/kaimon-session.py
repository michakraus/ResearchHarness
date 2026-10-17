#!/usr/bin/env python3
"""Refuse a Kaimon call that names no session.

A `PreToolUse` hook on the matcher `mcp__kaimon__ex|mcp__kaimon__manage_repl`. It exits 2,
which refuses the call and shows this script's stderr to the model, when an `ex` call has no
`ses`, or a `manage_repl` call has no `session`.

Without the key, Kaimon takes the session the agent is bound to, else the only connected one.
Under a builder-critic loop several agents hold sessions at once, so a call without the key
runs in another agent's session, or shuts it down. `ex` drops an unknown parameter silently, so
`session` in place of `ses` is refused too.

`check_eval` takes only `eval_id`, which names its job; it has no session parameter, and the
matcher leaves it out.

**It fails open.** Any input it does not understand exits 0.

Test it without installing:

    echo '{"tool_name":"mcp__kaimon__ex","tool_input":{"e":"1"}}' | ./kaimon-session.py ; echo "exit $?"
"""

import json
import sys

# The session parameter of each tool, by the last part of its name.
KEYS = {"ex": "ses", "manage_repl": "session"}

MESSAGE = """Refused: `{tool}` without `{key}`.

Pass the session key on every call: `{example}`. `start_session` returns the key, and `ping`
lists the sessions. Without it, the call runs in the session that Kaimon picks, which can be
another agent's. The rule is in `skills/build-part/evidence.md`, *A warm session for probes*:
one session for your tree, `ses` on every `ex`, and a shutdown with `session` before you return.
"""

EXAMPLES = {"ex": "ex(e = …, q = false, ses = <key>)", "manage_repl": 'manage_repl(command = "…", session = <key>)'}


def main():
    try:
        payload = json.load(sys.stdin)
        name = payload["tool_name"]
        arguments = payload["tool_input"]
        prefix = "mcp__kaimon__"
    except Exception:
        return 0
    if not isinstance(name, str) or not name.startswith(prefix):
        return 0
    tool = name[len(prefix):]
    key = KEYS.get(tool)
    if key is None or not isinstance(arguments, dict):
        return 0
    value = arguments.get(key)
    if isinstance(value, str) and value.strip():
        return 0
    sys.stderr.write(MESSAGE.format(tool=tool, key=key, example=EXAMPLES[tool]))
    return 2


if __name__ == "__main__":
    sys.exit(main())
