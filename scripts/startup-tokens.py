#!/usr/bin/env python3
"""Startup context size per session kind, read from the transcripts.

For each transcript under ~/.claude/projects, take the usage of the first API call:
    total = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    read  = cache_read_input_tokens   (a prefix shared with an earlier call, billed at 0.1x)
    write = cache_creation_input_tokens (written fresh, billed at 1.25x for 5m, 2x for 1h)
The first call includes the first prompt, so `total` is the startup cost plus that prompt.

Groups are main sessions by entry point, and subagents by agent type and entry point.

    python3 startup-tokens.py            # the last 7 days
    python3 startup-tokens.py --days 30
"""
import argparse
import glob
import json
import os
import statistics
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=float, default=7)
args = parser.parse_args()

root = os.path.expanduser("~/.claude/projects")
paths = glob.glob(f"{root}/**/*.jsonl", recursive=True)
newest = max(os.path.getmtime(p) for p in paths)
groups = defaultdict(list)

for path in paths:
    if os.path.getmtime(path) < newest - args.days * 86400:
        continue
    subagent = "subagents" in path
    agent_type = None
    if subagent:
        meta = path[: -len(".jsonl")] + ".meta.json"
        if os.path.exists(meta):
            agent_type = json.load(open(meta)).get("agentType")
    entrypoint = None
    with open(path) as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            entrypoint = entrypoint or record.get("entrypoint")
            usage = record.get("message", {}).get("usage") if record.get("type") == "assistant" else None
            if not usage:
                continue
            read = usage.get("cache_read_input_tokens", 0)
            write = usage.get("cache_creation_input_tokens", 0)
            total = usage.get("input_tokens", 0) + read + write
            if total:
                kind = f"sub:{agent_type}" if subagent else "main"
                groups[(kind, entrypoint)].append((total, read, write))
            break

print(f"{'kind':<34}{'entry':<16}{'n':>5}{'total':>9}{'read':>9}{'write':>9}   (medians)")
for (kind, entry), rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    med = [int(statistics.median(r[i] for r in rows)) for i in range(3)]
    print(f"{kind:<34}{str(entry):<16}{len(rows):>5}{med[0]:>9}{med[1]:>9}{med[2]:>9}")
