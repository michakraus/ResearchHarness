#!/usr/bin/env python3
"""Tell a main session that its context has passed MARK tokens, and that it hands off.

Claude Code runs this hook on `UserPromptSubmit` and, with no matcher, on `PostToolUse`. It reads
the size of the context from the transcript that the payload names: the `usage` of the last model
call of the main chain, `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
Each model call reads the whole context again, so a session above MARK pays for it on every call.

At MARK or more it adds TEXT to the session's context as `additionalContext`:

  UserPromptSubmit  on every prompt;
  PostToolUse       only on the call whose context crosses MARK or a further STEP above it, so a
                    long turn gets the line once per STEP and not after each tool.

A sub-agent's call, whose payload holds `agent_id`, gets nothing: its caller bounds its context.

It reads the transcript from its end, in blocks of BLOCK bytes, and stops at the second model
call, or after TAIL bytes. **It never blocks.** A payload it cannot read, a transcript it cannot
read and a transcript with no model call give no output and exit 0: a hook that fails here would
show an error after every tool call.

Test it without installing:

    echo '{"hook_event_name":"UserPromptSubmit","transcript_path":"t.jsonl"}' | ./context-handoff.py
"""

import contextlib
import json
import os
import sys
from pathlib import Path

from guard import HarnessError
from guard.jsonio import JsonValue, loads

MARK = 400_000
STEP = 100_000
BLOCK = 1 << 18
TAIL = 1 << 24
# The model calls that the hook reads: the last, and the one before it.
CALLS = 2
# The record of a model call, as Claude Code writes it: compact JSON, so a line without this text
# is no model call and is not parsed.
ASSISTANT = b'"type":"assistant"'
USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")

TEXT = (
    "Context: {k}k tokens, above the hand-off mark of {mark}k. Each model call reads the whole "
    "context again. Finish the current step, and start no new body of work in this session. Write "
    "the state of the work where the work lives: the task file, or a hand-off note. Then propose a "
    "new session with a short brief that names that file, and stop."
)


def size_of(line: bytes) -> tuple[str, int] | None:
    """(message id, context size) of a model call of the main chain, or None for any other line."""
    if ASSISTANT not in line:
        return None
    try:
        record = loads(line.decode("utf-8"), where="a transcript line")
    except UnicodeDecodeError, HarnessError:
        return None
    message = record.get("message")
    if (
        record.get("type") != "assistant"
        or record.get("isSidechain") is True
        or not isinstance(message, dict)
    ):
        return None
    usage: JsonValue = message.get("usage")
    ident = message.get("id")
    if not isinstance(usage, dict) or not isinstance(ident, str):
        return None
    counts = [usage.get(key) for key in USAGE]
    return ident, sum(c for c in counts if isinstance(c, int))


def sizes(path: Path) -> list[int]:
    """The context sizes of the last two model calls of the main chain in the transcript at
    `path`, the newest first; fewer when the last TAIL bytes hold fewer."""
    found: list[tuple[str, int]] = []
    with path.open("rb") as transcript:
        size = transcript.seek(0, os.SEEK_END)
        start = size
        rest = b""
        while start > 0 and size - start < TAIL and len(found) < CALLS:
            end, start = start, max(0, start - BLOCK)
            transcript.seek(start)
            lines = (transcript.read(end - start) + rest).split(b"\n")
            # The first piece may begin inside a line: keep it for the next block, unless the file
            # starts here.
            rest = lines.pop(0) if start > 0 else b""
            for line in reversed(lines):
                call = size_of(line)
                if call is not None and call[0] not in (f[0] for f in found):
                    found.append(call)
                    if len(found) == CALLS:
                        break
    return [f[1] for f in found]


def crossed(now: int, before: int | None) -> bool:
    """Whether a call of context `now` after one of `before` crosses MARK or a further STEP."""
    if now < MARK:
        return False
    return before is None or before < MARK or (now - MARK) // STEP > (before - MARK) // STEP


def main() -> int:
    with contextlib.suppress(OSError, HarnessError):
        payload = loads(sys.stdin.read(), where="the payload")
        event = payload.get("hook_event_name")
        transcript = payload.get("transcript_path")
        if "agent_id" in payload or not isinstance(transcript, str) or not transcript:
            return 0
        if event not in ("UserPromptSubmit", "PostToolUse"):
            return 0
        found = sizes(Path(transcript))
        if not found or found[0] < MARK:
            return 0
        if event == "PostToolUse" and not crossed(found[0], found[1] if len(found) > 1 else None):
            return 0
        text = TEXT.format(k=found[0] // 1000, mark=MARK // 1000)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
