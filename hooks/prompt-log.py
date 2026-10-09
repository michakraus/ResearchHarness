#!/usr/bin/env python3
"""Append each permission dialog to a log, and decide nothing.

A `PermissionRequest` hook with no matcher: Claude Code runs it when it is about to show a
permission dialog, for every tool. It writes one JSON line per dialog to `LOG` and prints
nothing, so the dialog appears exactly as it would without the hook.

It exists because an approved prompt leaves no record. The transcript holds the tool call
and its result, but not the fact that a person was asked. A week of this log answers which
prompts a person still answers, by tool, by command and by permission mode.

**It never blocks.** Every path exits 0 with no output, including a payload it cannot read
and a log it cannot write. A logging hook that failed closed would put a dialog, or a
refusal, in front of every call that already asks.

Test it without installing:

    echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | LOG=$TMPDIR/p.jsonl ./prompt-log.py
"""

import datetime
import json
import os
import sys

LOG = os.environ.get("LOG") or os.path.expanduser("~/.claude/logs/permission-requests.jsonl")

# A `Write` or `Edit` input carries whole file contents. The log needs the call's shape,
# not its payload, so every string in the input is cut to this length.
LIMIT = 400

# The fields kept from the payload. `transcript_path` follows from `session_id`.
FIELDS = ("session_id", "cwd", "permission_mode", "tool_name", "tool_use_id", "agent_id",
          "agent_type", "permission_suggestions")


def shorten(value):
    """Return `value` with every string in it cut to `LIMIT` characters."""
    if isinstance(value, str):
        return value if len(value) <= LIMIT else value[:LIMIT] + f"…[{len(value)} chars]"
    if isinstance(value, dict):
        return {key: shorten(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shorten(item) for item in value]
    return value


def main():
    try:
        payload = json.load(sys.stdin)
        record = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        record.update({key: shorten(payload[key]) for key in FIELDS if key in payload})
        record["tool_input"] = shorten(payload.get("tool_input"))
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
