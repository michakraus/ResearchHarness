#!/usr/bin/env python3
"""Where the tokens go inside a session, read from the transcripts.

Companion to startup-tokens.py, which measures the start. Four reports:

1. Context size per API call, in bands. Each call re-reads the whole context, so the cost of a
   turn grows with the context, not with the prompt. The cost column is in input-token
   equivalents: input x1, cache write x2 (main, 1-hour cache) or x1.25 (subagent, 5-minute
   cache), cache read at the model's own multiplier (READ_PRICE; 0.1 where not listed).
2. Tool results by tool. A result is written to the cache once and read again by every later
   call in the same transcript, so its carried cost is
       tokens x (write price + the read prices of the later calls).
   This assumes the result stays in context to the end, which holds while nothing compacts;
   the compactions line says how often that assumption fails.
3. Waste patterns: a whole-file Read of a path already read whole and not edited since; a Bash
   command re-run with byte-identical output; the same call repeated after an error three or
   more times in a row; four or more errors in a row.
4. Compactions.

Tokens for tool results are estimated at 3.5 characters per token, the ratio Startup-Tokens.md
measured for this tree's text. Usage figures are the API's own.

    python3 session-tokens.py            # the last 7 days
    python3 session-tokens.py --days 30
"""
import argparse
import glob
import hashlib
import json
import os
from collections import defaultdict

CHARS_PER_TOKEN = 3.5
# Cache-read multiplier where it is not the standard 0.1: the pricing page, platform.claude.com.
READ_PRICE = {"claude-opus-5-5": 0.05, "claude-fable-5-1": 0.025}

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=float, default=7)
args = parser.parse_args()

root = os.path.expanduser("~/.claude/projects")
paths = glob.glob(f"{root}/**/*.jsonl", recursive=True)
newest = max(os.path.getmtime(p) for p in paths)
paths = [p for p in paths if os.path.getmtime(p) >= newest - args.days * 86400]

BANDS = [(0, 50_000), (50_000, 100_000), (100_000, 200_000), (200_000, 400_000), (400_000, 10**9)]
band_calls = defaultdict(int)
band_cost = defaultdict(float)
kind_cost = defaultdict(float)
tool_n = defaultdict(int)
tool_chars = defaultdict(int)
tool_carried = defaultdict(float)
tool_max = defaultdict(int)
waste = defaultdict(lambda: [0, 0])  # pattern -> [events, chars]
compactions = 0
transcripts = 0


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def tool_group(name):
    if name.startswith("mcp__"):
        return "mcp__" + name.split("__")[1]
    return name


def program(command):
    """The program a Bash command runs, past any leading `cd …`/`&&`/`;` segments."""
    for segment in command.replace("&&", ";").split(";"):
        words = segment.split()
        if words and words[0] != "cd":
            return os.path.basename(words[0])
    return "cd"


for path in paths:
    subagent = "subagents" in path
    write_price = 1.25 if subagent else 2.0
    calls = []  # usage per API call, in order
    results = []  # (call index at the time, tool group, chars)
    seen_requests = set()
    uses = {}  # tool_use_id -> (name, input)
    whole_reads = {}  # path -> True while its last whole read is still current
    bash_last = {}  # command -> hash of its last output
    streak_key, streak_len, error_run = None, 0, 0
    transcripts += 1
    with open(path) as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = record.get("type")
            if kind == "system" and record.get("subtype") == "compact_boundary":
                compactions += 1
                whole_reads.clear()
                bash_last.clear()
            message = record.get("message") or {}
            content = message.get("content")
            if kind == "assistant":
                request = record.get("requestId")
                usage = message.get("usage")
                if usage and (request is None or request not in seen_requests):
                    seen_requests.add(request)
                    model = message.get("model", "")
                    read_price = next((p for m, p in READ_PRICE.items() if model.startswith(m)), 0.1)
                    calls.append((usage, read_price))
                for block in content if isinstance(content, list) else []:
                    if block.get("type") == "tool_use":
                        uses[block["id"]] = (block.get("name", "?"), block.get("input") or {})
            elif kind == "user" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    name, tool_input = uses.get(block.get("tool_use_id"), ("?", {}))
                    text = result_text(block.get("content"))
                    results.append((len(calls), tool_group(name), len(text)))
                    if name == "Bash":
                        results.append((len(calls), "Bash: " + program(tool_input.get("command", "")), len(text)))
                    is_error = bool(block.get("is_error"))
                    # waste: repeated whole-file Read of an unedited path
                    file_path = tool_input.get("file_path")
                    if name == "Read" and not is_error:
                        whole = "offset" not in tool_input and "limit" not in tool_input
                        if whole and whole_reads.get(file_path):
                            waste["re-read, unedited"][0] += 1
                            waste["re-read, unedited"][1] += len(text)
                        if whole:
                            whole_reads[file_path] = True
                    elif name in ("Edit", "Write", "NotebookEdit"):
                        whole_reads.pop(file_path, None)
                    # waste: Bash re-run with identical output
                    if name == "Bash" and not is_error:
                        command = tool_input.get("command", "")
                        digest = hashlib.sha1(text.encode()).hexdigest()
                        if bash_last.get(command) == digest and len(text) > 200:
                            waste["Bash re-run, same output"][0] += 1
                            waste["Bash re-run, same output"][1] += len(text)
                        bash_last[command] = digest
                    # waste: the same call repeated after an error
                    key = (name, json.dumps(tool_input, sort_keys=True)[:400])
                    if is_error:
                        streak_len = streak_len + 1 if key == streak_key else 1
                        streak_key = key
                        if streak_len == 3:
                            waste["same call after error, 3+"][0] += 1
                        error_run += 1
                        if error_run == 4:
                            waste["errors in a row, 4+"][0] += 1
                    else:
                        streak_key, streak_len, error_run = None, 0, 0

    for usage, read_price in calls:
        read = usage.get("cache_read_input_tokens", 0)
        write = usage.get("cache_creation_input_tokens", 0)
        plain = usage.get("input_tokens", 0)
        size = plain + read + write
        for low, high in BANDS:
            if low <= size < high:
                cost = plain + read_price * read + write_price * write
                band_calls[(low, high)] += 1
                band_cost[(low, high)] += cost
                kind_cost["subagents" if subagent else "main sessions"] += cost
    later_reads = [0.0] * (len(calls) + 1)  # later_reads[i]: sum of read prices of calls i..end
    for i in range(len(calls) - 1, -1, -1):
        later_reads[i] = later_reads[i + 1] + calls[i][1]
    for at, group, chars in results:
        tokens = chars / CHARS_PER_TOKEN
        tool_n[group] += 1
        tool_chars[group] += chars
        tool_max[group] = max(tool_max[group], chars)
        tool_carried[group] += tokens * (write_price + later_reads[min(at + 1, len(calls))])

print(f"{transcripts} transcripts over the last {args.days:g} days, {compactions} compactions\n")

total_calls = sum(band_calls.values())
total_cost = sum(band_cost.values())
print(f"{'context per call':<20}{'calls':>8}{'share':>8}{'input cost':>14}{'share':>8}")
for band in BANDS:
    low, high = band
    label = f"{low // 1000}k-{high // 1000}k" if high < 10**9 else f"{low // 1000}k+"
    n, cost = band_calls[band], band_cost[band]
    print(f"{label:<20}{n:>8}{n / total_calls:>8.1%}{cost / 1e6:>12.1f}M{cost / total_cost:>8.1%}")
print(", ".join(f"{kind} {cost / total_cost:.1%}" for kind, cost in sorted(kind_cost.items())))

total_carried = sum(v for g, v in tool_carried.items() if not g.startswith("Bash: "))


def table(title, groups):
    print(f"\n{title:<28}{'results':>8}{'Mchars':>9}{'max kchars':>12}{'carried':>10}{'share':>8}")
    for group in sorted(groups, key=lambda g: -tool_carried[g])[:12]:
        print(
            f"{group:<28}{tool_n[group]:>8}{tool_chars[group] / 1e6:>9.2f}{tool_max[group] / 1e3:>12.1f}"
            f"{tool_carried[group] / 1e6:>9.1f}M{tool_carried[group] / total_carried:>8.1%}"
        )


table("tool", [g for g in tool_carried if not g.startswith("Bash: ")])
table("Bash, by program", [g for g in tool_carried if g.startswith("Bash: ")])
print(f"carried cost of all tool results: {total_carried / 1e6:.1f}M of {total_cost / 1e6:.1f}M input cost")

print(f"\n{'waste pattern':<28}{'events':>8}{'kchars':>10}")
for pattern in ("re-read, unedited", "Bash re-run, same output", "same call after error, 3+", "errors in a row, 4+"):
    events, chars = waste[pattern]
    print(f"{pattern:<28}{events:>8}{chars / 1e3:>10.1f}")
