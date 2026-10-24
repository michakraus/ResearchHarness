"""The adapter of Claude Code: its layer of `harness install`, the settings and the trust.

THE LAYER. `harness install` installs into ~/.claude/:

  settings/settings.proposal.json  -> ~/.claude/settings.json (merged: OWNED, and the keys it lacks)
  agents/, skills/, rules/,
  instructions/, commands/ **      -> ~/.claude/**          (the same relative path)
  adapters/claude/**               -> ~/.claude/**          (the path relative to adapters/claude/)
  hooks/*                          -> ~/.claude/hooks/      (not probe.py, the hooks' own cases)
  the tree instructions, **        -> ~/.claude/**          (the same relative path; not README.md)
  the stamp                        -> ~/.claude/.harness-install.json

Sources. The layer reads the five neutral directories agents/, skills/, rules/, instructions/
and commands/, and adapters/claude/ and hooks/ of this repository. It also reads the tree
instructions: the private directory that the profile key `tree_agents` names. Each neutral
directory installs at its own path below ~/.claude/, and adapters/claude/ at the top of it. The
tree instructions mirror the layout of ~/.claude/. These are not sources: the code of this
adapter, adapter.py, and fixtures/ of adapters/claude/, a name that starts with `.`, and
__pycache__. A file below agents/ or hooks/ of the tree instructions is not installed, because
agents and hooks install from this repository only. Each such file is a SKIP line and does not
count as a change.

Files. A file is copied byte for byte, unless CLAUDE_TEMPLATES lists its installed path; a
template is rendered with the profile. An agent of agents/ and a SKILL.md of skills/ are copied
with three changes (`render_source`):

  * the model tier of `model:` becomes its Claude Code model from the [claude] table of
    models.toml (`load_models`);
  * each `tools:` item becomes its Claude Code name from TOOLS;
  * a `cacheTtl:` line moves below a new `experimental:` line, the only key from which Claude
    Code reads the TTL of an agent.

A hook keeps the mode of its source. Every other file is installed with mode 0644.

Refusals. The install exits with status 2, before anything is written, on a wrong `tree_agents`
value, on a source that it cannot use, on a path that two sources hold, and on an installed path
that it cannot write. The docstring of `plan` lists each case.

Extra files. An installed file with no source, below a top-level directory that the layer
writes into, is reported as EXTRA with its removal command. skills/synced/ and the hidden names
are not searched. A directory there that cannot be read exits with status 2, before anything
is written.

Settings. The Claude Code settings, ~/.claude/settings.json, are the first file of the layer,
so that a new deny rule is in place before the files it protects. The settings template is
rendered with the profile and with the network rules of settings/network.toml and its overlay
(`network.py`). The rendered template replaces the sections of OWNED: `permissions`, `hooks`,
`sandbox` and `modelSettings`. Each other key of the template that the file lacks is added.
Every other key stays as the app and the user wrote it. The old file is kept as a backup. The
dry run prints the unified diff of those sections and keys after the line of the file
(`settings_file`). A key of the template that the user removes comes back at the next install;
another value in the file stays. A settings file that cannot be merged exits with status 2
before anything is written.

The install merges because the app rewrites settings.json at each change of model or effort in
the UI. A `cp` of the proposal would revert each value set in the UI since the proposal last
changed. `modelSettings` is owned all the same, so that the effort and the auto-compact window
of each model come from the template, as those of the other frontends come from models.toml. An
`/effort` or `/autocompact` in the UI holds until the next install, which shows it in its diff
and replaces it. The merge reads the live file when it plans, so a change that the app writes
between the plan and the write is lost. Run `--apply` while no session changes its model.

The permission rules of the other settings files of the research tree give a warning
(`stray_warnings`). The install reads those files and never writes them. It neither reads nor
writes ~/.claude.json.

Stamp. After the layer, the install writes the stamp: the sources and a digest over their
files. The `SessionStart` hook hooks/install-drift.py computes the digest again at each session
start and compares it, so that a session warns when the installation is behind the sources. The
digest is a function of that hook, not a commit. It covers the paths, the modes and the source
bytes of the plan that the apply installs, before `render_source` rewrites an agent or a skill.
So an uncommitted edit that the apply installed counts, and a source edited while the apply runs
is drift. An edit of the [claude] table is no drift. A stamp that differs is a change, like any
installed file.

THE TRUST. `harness trust [--apply]` marks the research root and every git repository under it
as trusted in `~/.claude.json`. Claude Code keys workspace trust on the root of the git
repository. A trusted parent folder does not cover a git repository nested inside it, so each
repository raises its own trust dialog. A worktree uses the trust of its main checkout, so
`.worktrees/` needs no entry. A clone under `.scratch/` is a throwaway probe, so it gets no entry
either. No setting pre-trusts a tree; the documented route is
`projects["<root>"].hasTrustDialogAccepted = true`. The user runs the subcommand, because a
session cannot read or write `~/.claude.json`. Run it after a clone: a new repository is
untrusted until then. A running Claude Code writes the file too. So run `harness trust` again
after `--apply`, and if keys are missing again, quit the app and apply again.

THE SETTINGS. The subcommands of `settings` measure ~/.claude/settings.json against real
traffic. They count the permission prompts that a settings file causes, per command.

They read the session transcripts under ~/.claude/projects/. They split each Bash command into
the segments that the permission matcher evaluates. They classify each segment as Claude Code
does: deny, then ask, then allow, then the sandbox auto-allow.

    harness settings surface [--settings F] [--days N] [--head N]
    harness settings compare OLD NEW [--days N]
    harness settings selftest
    harness settings twins [--settings F] [--list allow|ask|deny]

The proposal is a template: `{home}`, `{org}` and the other placeholders take their values
from the private profile (`harness --profile F`). Every subcommand renders a file that holds a
placeholder before it reads it. It generates the network rules from settings/network.toml and
the overlay beside the profile.

`twins` emits the `git -C * <sub>` patterns for a `git` rule set. `-C` precedes the
subcommand, so `Bash(git status *)` never matches `git -C /path status`. The twin goes in the
same list as its plain form; otherwise the flag changes a verdict.

Caveats of the measurement:

  * The matcher expands nothing: no variables, no ~, no symbolic links. `$TMPDIR/x` and
    `/tmp/claude-<pid>/x` are different strings and need different patterns.
  * `autoAllowBashIfSandboxed` is on, so a segment that matches no rule is approved
    automatically, unless one of the commands excluded from the sandbox leads it. Those
    commands fall through to the ordinary handling, so they prompt. The set is read from the
    settings file under analysis, because a hardcoded copy goes stale when the list changes.
  * An `ask` prompts in `default` mode, but goes to the auto-mode classifier in `auto`. This
    script counts the gate, not what a classifier did with it.
  * `rule_matches` reproduces the Bash matcher of Claude Code 2.1.282, read from its binary,
    because `fnmatch` differs from it: a trailing `:*` makes a prefix rule, not a glob; `[`,
    `]` and `?` are literal; a lone trailing ` *` also matches the bare command. Run
    `selftest` after a Claude Code update. It is not established whether the Bash path
    collapses whitespace or ignores case; this module models neither.
"""

import argparse
import collections
import contextlib
import errno
import functools
import io
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from unittest import mock

from harness import REPO, HarnessError, changing, frontends, frontmatter, install, network, outcome
from harness import profile as render_profile
from harness import sources as neutral
from harness.githooks import research_root
from harness.sources import NEUTRAL

NAME = "claude"
TEMPLATES = ["launchagents/claude-autocommit.plist"]
RESTART = "Restart Claude Code: its installed files changed, and a running session keeps the files it has read."

# The Claude Code layer's sources in this repository, each (directory, installed prefix): the
# neutral directories at their own path below ~/.claude/, and adapters/claude/ at its top.
CLAUDE_ADAPTER = REPO / "adapters" / "claude"
CLAUDE_SOURCES = [*((REPO / d, d) for d in NEUTRAL), (CLAUDE_ADAPTER, "")]
# The top-level names of adapters/claude/ that are no source: this adapter's code and its fixtures.
ADAPTER_CODE = {"adapter.py", "fixtures"}
# The installed paths, relative to ~/.claude/, that are rendered with the profile. Every other
# file is copied byte for byte, so a `{home}` in its prose stays as it is.
CLAUDE_TEMPLATES = frozenset()
# The installed paths that no source may hold: the Claude Code settings, which `harness install`
# merges from the settings template (`settings_file`).
CLAUDE_SETTINGS = frozenset({"settings.json", "settings.local.json"})
# The Claude Code name of each neutral tool of frontmatter.TOOLS; the Kaimon tool
# `mcp/kaimon/<tool>` is MCP_PREFIX followed by `<tool>`.
TOOLS = {"read": "Read", "edit": "Edit", "write": "Write", "grep": "Grep", "glob": "Glob", "shell": "Bash",
         "agent": "Agent", "web_search": "WebSearch", "web_fetch": "WebFetch"}
MCP_PREFIX = "mcp__kaimon__"
# A model of [claude] that render_source writes as it is into `model:`: a plain YAML scalar that
# reads as this string. Any other model is written as JSON writes a string, a YAML double-quoted
# scalar. A word of YAML_WORDS, which YAML reads as a boolean or null, and a model that holds a
# control character of MODEL_CONTROL exit 2.
MODEL = re.compile(r"[A-Za-z][A-Za-z0-9._\[\]-]*")
YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "y", "n", "null"}
MODEL_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")

CONFIG = os.path.expanduser("~/.claude.json")
SKIP = {".git", ".scratch", ".worktrees", "node_modules"}

PROJECTS = pathlib.Path.home() / ".claude" / "projects"
LIVE = pathlib.Path.home() / ".claude" / "settings.json"
PROPOSAL = REPO / "settings" / "settings.proposal.json"
PROFILE = None  # `harness --profile`; None lets the profile module choose


def read_settings(path):
    """A settings file parsed, and rendered with the profile when it holds a placeholder.

    The proposal is a template (`{home}`, `{org}`, …); the live file is its render, with the
    network rules that `network.apply` generates. Every command reads through here, so a proposal
    and a live file compare as the same thing. A file that is missing, cannot be read, or is not
    UTF-8, not JSON (`json_object`) or not a JSON object, or whose `permissions` is not an object,
    exits 2.
    """
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise HarnessError(f"no settings file at {path}") from e
    except OSError as e:
        raise HarnessError(f"cannot read {path}: {e.strerror}") from e
    except UnicodeDecodeError as e:
        raise HarnessError(f"{path} is not UTF-8: {e.reason} at byte {e.start}") from None
    cfg = json_object(path, text)
    if not isinstance(cfg.get("permissions", {}), dict):
        raise HarnessError(f"{path}: the value of permissions is not a JSON object")
    if render_profile.PLACEHOLDER.search(text):
        profile = render_profile.load(PROFILE)
        cfg = network.apply(render_profile.render_data(cfg, profile), profile, render_profile.network_path(PROFILE))
    return cfg


def json_object(path, text):
    """`text`, the contents of the file at `path`, parsed; exits 2 when it is not JSON, is nested
    deeper than the parser reads, or is not a JSON object."""
    try:
        cfg = json.loads(text)
    except ValueError as e:
        raise HarnessError(f"{path} is not JSON: {e}") from None
    except RecursionError:  # Python 3.11's recursion limit, or the stack limit of 3.12 and later
        raise HarnessError(f"{path} is JSON nested too deep for the parser") from None
    if not isinstance(cfg, dict):
        raise HarnessError(f"{path} is not a JSON object")
    return cfg

# The matcher evaluates each segment of a compound command separately.
SEGMENT = re.compile(r"(?:&&|\|\||;|\||\n)")

def load_rules(path):
    """Return a settings file's Bash patterns as (allow, ask, deny, excluded).

    `excluded` is the leading words of `sandbox.excludedCommands` — the commands the
    sandbox does not confine, which reach the permission layer even when they match no
    rule, so that a missing grant on one of them is a prompt. It is read from the file
    rather than hardcoded, because a hardcoded mirror of a list in the file is a list
    that goes stale without failing.
    """
    cfg = read_settings(path)
    perms = cfg.get("permissions", {})

    def bash_patterns(kind):
        out = []
        for rule in perms.get(kind, []):
            m = re.match(r"^Bash\((.*)\)$", rule)
            if m:
                out.append(m.group(1))
        return out

    excluded = tuple(
        dict.fromkeys(
            pattern.split()[0]
            for pattern in cfg.get("sandbox", {}).get("excludedCommands", [])
            if pattern.split()
        )
    )
    return bash_patterns("allow"), bash_patterns("ask"), bash_patterns("deny"), excluded


def commands(days):
    """Yield every Bash command string issued in the last `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for path in PROJECTS.rglob("*.jsonl"):
        if path.stat().st_mtime < (datetime.now().timestamp() - days * 86400):
            continue
        with path.open(errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec.get("timestamp"), str) or rec["timestamp"] < cutoff:
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("name") == "Bash"
                    ):
                        cmd = (block.get("input") or {}).get("command")
                        if isinstance(cmd, str):
                            yield cmd


def segments(command):
    """Split a command the way the permission matcher does."""
    for raw in SEGMENT.split(command):
        seg = raw.strip().lstrip("(").strip()
        if seg:
            yield seg


ESCAPED_STAR, ESCAPED_BACKSLASH, GLOBSTAR = "\x00S\x00", "\x00B\x00", "\x00G\x00"


@functools.lru_cache(maxsize=None)
def wildcard_regex(pattern):
    """The regex Claude Code 2.1.282 builds for a Bash wildcard rule."""
    source, text, index = pattern.strip(), "", 0
    while index < len(source):
        if source[index] == "\\" and index + 1 < len(source) and source[index + 1] in "*\\":
            text += ESCAPED_STAR if source[index + 1] == "*" else ESCAPED_BACKSLASH
            index += 2
            continue
        text += source[index]
        index += 1
    stars = text.count("*")
    regex = re.sub(r"[.+?^${}()|[\]\\'\"]", lambda m: "\\" + m.group(), text)
    regex = re.sub(r"/(?:\*\*/)+", GLOBSTAR, regex).replace("*", ".*")
    regex = regex.replace(GLOBSTAR, "/(?:.*/)?").replace(ESCAPED_STAR, r"\*")
    regex = regex.replace(ESCAPED_BACKSLASH, r"\\")
    if regex.endswith(" .*") and stars == 1:
        regex = regex[:-3] + "( .*)?"
    return re.compile(regex, re.S)


def escaped_at(pattern, index):
    """Whether the character at `index` follows an odd run of backslashes."""
    before = pattern[:index]
    return (len(before) - len(before.rstrip("\\"))) % 2 == 1


def unescaped_star(pattern):
    """Whether a pattern holds a `*` that no backslash escapes."""
    return any(char == "*" and not escaped_at(pattern, i) for i, char in enumerate(pattern))


def ends_in_star(pattern):
    """Whether a pattern ends in an unescaped `*`."""
    text = pattern.rstrip()
    return text.endswith("*") and not escaped_at(text, len(text) - 1)


def rule_matches(segment, rule, kind):
    """Whether one Bash rule matches one segment, as Claude Code 2.1.282 decides it.

    A rule ending in `:*` is a prefix rule: the segment equals the prefix, or starts with
    it and a space, and the prefix is literal, `*` included. Otherwise a rule with an
    unescaped `*` is a wildcard and anything else is exact. An `ask` or `deny` rule also
    matches the segment behind `xargs `, and so does an `allow` wildcard ending in `*`.
    """
    if "\x00" in segment:
        return False
    shape, *parts = parse_rule(rule)
    if shape == "prefix":
        command = re.sub(r"[ \t]+", " ", segment)
        return any(command == p or command.startswith(p + " ") for p in parts)
    if shape == "wildcard":
        plain, via_xargs, star_at_end = parts
        if plain.fullmatch(segment):
            return True
        if kind == "allow" and not star_at_end:
            return False
        return bool(via_xargs.fullmatch(segment))
    return segment == rule


@functools.lru_cache(maxsize=None)
def parse_rule(rule):
    """A rule's shape and what `rule_matches` needs for it, computed once per rule."""
    prefix = re.fullmatch(r"(.+):\*", rule)
    if prefix:
        text = re.sub(r"[ \t]+", " ", prefix.group(1))
        return ("prefix", text, "xargs " + text)
    if unescaped_star(rule):
        return ("wildcard", wildcard_regex(rule), wildcard_regex("xargs " + rule), ends_in_star(rule))
    return ("exact",)


def verdict(segment, allow, ask, deny, excluded):
    """Classify one segment: deny, ask, allow, or the sandbox auto-allow.

    `excluded` has no default on purpose: the caller passes the list that came out of
    the settings file it loaded, so the fallthrough cannot be measured against a
    different file's sandbox than the rules it is testing.
    """
    if any(rule_matches(segment, p, "deny") for p in deny):
        return "deny"
    if any(rule_matches(segment, p, "ask") for p in ask):
        return "ask"
    if any(rule_matches(segment, p, "allow") for p in allow):
        return "allow"
    head = segment.split()[0] if segment.split() else ""
    return "ask" if head in excluded else "sandbox"


def survey(rules, cmds):
    """Return (counter by leading word, counter of prompting segment shapes)."""
    allow, ask, deny, excluded = rules
    by_head = collections.Counter()
    shapes = collections.Counter()
    for cmd in cmds:
        for seg in segments(cmd):
            if verdict(seg, allow, ask, deny, excluded) != "ask":
                continue
            words = seg.split()
            by_head[words[0]] += 1
            shapes[" ".join(words[:3])] += 1
    return by_head, shapes


def twin(pattern):
    """The `git -C <path>` spelling of a plain `git` pattern, or None."""
    m = re.match(r"^git (?!-C\b)(?!-c\b)(?!--)(\S+)(.*)$", pattern)
    return "git -C * " + m.group(1) + m.group(2) if m else None


def cmd_surface(args):
    rules = load_rules(args.settings)
    cmds = list(commands(args.days))
    by_head, shapes = survey(rules, cmds)
    print(f"{len(cmds)} Bash calls in the last {args.days} days, {args.settings}")
    print(f"segments reaching a prompt: {sum(by_head.values())}\n")
    for head, n in by_head.most_common():
        print(f"  {n:6d}  {head}")
    if args.head:
        print("\nmost frequent prompting shapes:")
        for shape, n in shapes.most_common(args.head):
            print(f"  {n:6d}  {shape}")


def cmd_compare(args):
    cmds = list(commands(args.days))
    before, _ = survey(load_rules(args.old), cmds)
    after, _ = survey(load_rules(args.new), cmds)
    heads = sorted(set(before) | set(after), key=lambda h: -before[h])
    print(f"{len(cmds)} Bash calls in the last {args.days} days\n")
    print(f"  {'':10s} {'before':>8s} {'after':>8s}  {'delta':>8s}")
    for head in heads:
        print(f"  {head:10s} {before[head]:8d} {after[head]:8d}  {after[head]-before[head]:+8d}")
    b, a = sum(before.values()), sum(after.values())
    print(f"  {'TOTAL':10s} {b:8d} {a:8d}  {a-b:+8d}")


# (rule, kind, segment, expected). Each is a reading of the 2.1.282 matcher or a probe of
# it on 2026-09-25/26; the probes ran `claude -p` in `default` mode.
MATCHER_CASES = [
    ("git push * :*", "ask", "git push origin :topic", False),  # probed: ran
    ("git push * :*", "ask", "git push * :topic", False),
    ("git push * :**", "ask", "git push origin :topic", True),  # probed: refused
    ("git push * :**", "ask", "git push origin HEAD:refs/heads/x", False),  # probed: ran
    ("git push * [:]*", "ask", "git push origin :topic", False),  # probed: ran
    ("git push * \\:*", "ask", "git push origin :topic", False),  # probed: ran
    ("npm run test:*", "allow", "npm run test", True),
    ("npm run test:*", "allow", "npm run test --watch", True),
    ("npm run test:*", "allow", "npm run testing", False),
    ("npm run test:*", "deny", "xargs npm run test x", True),
    ("git var *", "allow", "git var", True),  # probed 2026-09-26: ran; unmatched, it asked
    ("git status *", "allow", "git status", True),
    ("git status *", "allow", "git statusx", False),
    ("git tag * -d", "ask", "git tag", False),
    ("git tag ?", "allow", "git tag x", False),
    ("git branch -d *", "allow", "git branch -d my-feature", True),
    ("rm -rf *", "deny", "xargs rm -rf x", True),
    ("git status", "allow", "git status --short", False),
]


def matcher_cases():
    """The matcher against the recorded Claude Code cases: (number of cases, number wrong)."""
    wrong = 0
    for rule, kind, segment, expected in MATCHER_CASES:
        got = rule_matches(segment, rule, kind)
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  {kind:5s} Bash({rule}) vs {segment!r}: {got}")
    return len(MATCHER_CASES), wrong


def cmd_selftest(args):
    n, wrong = matcher_cases()
    print(f"\n{n} cases, {wrong} wrong")
    return 1 if wrong else 0


def cmd_twins(args):
    allow, ask, deny, _ = load_rules(args.settings)
    for name, patterns in (("allow", allow), ("ask", ask), ("deny", deny)):
        if args.list and args.list != name:
            continue
        made = [t for t in (twin(p) for p in patterns) if t]
        print(f"# {name} — {len(made)} twins")
        for t in made:
            print(f'"Bash({t})",')
        print()


# The sections of ~/.claude/settings.json that `harness install` merges from the settings
# template. `modelSettings` holds each model's effort and auto-compact window, which the other
# frontends get from models.toml, so the template keeps it too: a value that `/effort` or
# `/autocompact` writes into the live file is replaced by the next install. Everything else in the
# live file belongs to the app and the user — model, env, statusLine — and the install leaves it
# exactly as it found it; it only adds a key of the template that the live file lacks.
OWNED = ("permissions", "hooks", "sandbox", "modelSettings")


def indent_of(text):
    """The indentation of a settings file's `text`, as the `indent` of json.dumps, so that a merge
    does not reformat it: the spaces and tabs that open the first indented line after the first;
    None, one line, for a file of one line; 2 when no line after the first is indented."""
    # A line ends at "\n" only: JSON allows a raw U+2028 in a string, where splitlines breaks.
    lines = text.rstrip("\n").split("\n")
    if len(lines) == 1:
        return None
    for line in lines[1:]:
        stripped = line.lstrip(" \t")
        if stripped and stripped != line:
            return line[:len(line) - len(stripped)]
    return 2


class Number:
    """A number token of a JSON text, as `json.loads` gives it to `parse_int` and `parse_float`."""

    def __init__(self, text):
        self.text = text


def rewritten_numbers(text, skip):
    """[(key, source text, emitted text)] of each number in the JSON object `text`, outside its
    top-level keys `skip`, whose text json.dumps writes otherwise for its parsed value: `1.10` as
    `1.1`, `1e400` as `Infinity`. A key is named as a path, `env.list[1]`."""
    found, stack = [], [(k, v) for k, v in reversed(json.loads(text, parse_int=Number, parse_float=Number).items())
                        if k not in skip]
    while stack:
        key, value = stack.pop()
        if isinstance(value, dict):
            stack += [(f"{key}.{k}", v) for k, v in reversed(value.items())]
        elif isinstance(value, list):
            stack += [(f"{key}[{i}]", v) for i, v in reversed(list(enumerate(value)))]
        elif isinstance(value, Number):
            emitted = json.dumps(json.loads(value.text))
            if emitted != value.text:
                found.append((key, value.text, emitted))
    return found


LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


def escaped(text):
    """`text` with each lone surrogate written as its escape, `\\ud800` say, which UTF-8 can encode."""
    return LONE_SURROGATE.sub(lambda m: f"\\u{ord(m[0]):04x}", text)


def dumps(obj, **kwargs):
    """`obj` as JSON text in which no character is escaped but a lone surrogate.

    The merge leaves every key it does not own as the app wrote it, and the default
    `ensure_ascii=True` would write each non-ASCII character, an em-dash say, as `\\u2014`. A lone
    surrogate stays an escape, because UTF-8 cannot encode it: it comes from a `\\ud800` in the
    JSON text, which JavaScript's `JSON.stringify` writes for one.
    """
    return escaped(json.dumps(obj, ensure_ascii=False, **kwargs))


def settings_template(profile, overlay):
    """The settings template parsed, rendered with `profile` when it holds a placeholder, and with
    the network rules of settings/network.toml and the overlay at `overlay`, as `read_settings`
    renders it."""
    text = PROPOSAL.read_text()
    cfg = json.loads(text)
    if render_profile.PLACEHOLDER.search(text):
        try:
            cfg = render_profile.render_data(cfg, profile)
        except (KeyError, TypeError, ValueError) as e:
            raise HarnessError(f"{PROPOSAL}: {e.args[0]}") from e
    return network.apply(cfg, profile, overlay)


def settings_file(root, profile, overlay):
    """The file of the plan for `root`/settings.json, the Claude Code settings: (destination,
    bytes, mode, label, backup, the unified diff of the owned sections and the added keys);
    `overlay` is the path of the network overlay (`settings_template`).

    Each key of OWNED is replaced from the rendered template, or removed when the template lacks
    it. Each other key of the template that the file lacks is added after the file's keys, with
    the template's value, and so is each variable of the template's `env` that the file's `env`
    object lacks; every other key keeps its value and its place, the file keeps its indent
    (`indent_of`), and no character but a lone surrogate is escaped. Owned sections equal to the
    template's, in a file that holds every key and `env` variable of the template, leave the file
    as it is. A missing
    file is created with the keys of the template, indented by 2, mode 0644. Exits 2, before
    anything is written, on a file that is a symlink, is not a
    regular file, cannot be read, is not UTF-8 or JSON (`json_object`), is not a JSON object, or
    holds an owned key whose value is not an object, and, when the merge writes the file, on a
    number outside the owned sections that it would write in other text (`rewritten_numbers`).
    """
    import difflib

    live = root / "settings.json"
    # One lstat, so that a stat the sandbox denies is "cannot be read" on every Python, never "missing".
    try:
        st = os.lstat(live)
    except FileNotFoundError:
        st = None
    except OSError as e:
        raise HarnessError(f"{live} cannot be read: {e.strerror}") from None
    if st is not None and stat.S_ISLNK(st.st_mode):
        raise HarnessError(f"{live} is a symlink; `harness install` merges the settings into a file only")
    cfg, indent, old = {}, 2, None
    if st is not None:
        if stat.S_ISDIR(st.st_mode):
            raise HarnessError(f"{live} is a directory; `harness install` merges the settings into a file only")
        if not stat.S_ISREG(st.st_mode):
            raise HarnessError(f"{live} is not a file; `harness install` merges the settings into a file only")
        try:
            old = live.read_bytes()
        except OSError as e:
            raise HarnessError(f"{live} cannot be read: {e.strerror}") from None
        try:
            text = old.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HarnessError(f"{live} is not UTF-8: {e.reason} at byte {e.start}") from None
        cfg = json_object(live, text)
        wrong = [k for k in OWNED if k in cfg and not isinstance(cfg[k], dict)]
        if wrong:
            raise HarnessError(f"{live}: the value of {', '.join(wrong)} is not a JSON object")
        indent = indent_of(text)
    template = settings_template(profile, overlay)
    added =[k for k in template if k not in OWNED and k not in cfg]
    env = cfg.get("env")
    env_added = [k for k in template.get("env", {}) if k not in env] if isinstance(env, dict) else []

    def section(c):
        """The owned sections, the added keys and the added `env` variables of `c`."""
        s = {k: c.get(k) for k in [*OWNED, *added]}
        if env_added:
            s["env"] = {k: c["env"][k] for k in env_added if k in c["env"]}
        return s
    a, b = (dumps(section(c), indent=2, sort_keys=True).splitlines() for c in (cfg, template))
    diff = list(difflib.unified_diff(a, b, "~/.claude/settings.json", "settings/settings.proposal.json", lineterm=""))
    if diff or old is None:
        rewritten = rewritten_numbers(text, OWNED) if old is not None else []
        if rewritten:
            raise HarnessError(f"{live}: the merge would rewrite " + ", ".join(
                f"the number `{source}` of `{key}` as `{emitted}`" for key, source, emitted in rewritten)
                + "; write each as the merge writes it, then run the install again")
        for key in OWNED:
            if key in template:
                cfg[key] = template[key]
            else:
                cfg.pop(key, None)
        for key in added:
            cfg[key] = template[key]
        for key in env_added:
            cfg["env"][key] = template["env"][key]
        data = (dumps(cfg, indent=indent) + "\n").encode("utf-8")
    else:
        data = old
    return live, data, 0o644 if old is None else None, "~/.claude/settings.json", True, "\n".join(diff)


def stray_warnings():
    """The warnings, [(line, …)], of the permission rules outside ~/.claude/settings.json, which
    a settings round neither proposes nor sees, of each such file that cannot be read, and of each
    `allow`, `ask` or `deny` there that is not a list; a lone surrogate in a line is written as its
    escape.

    "Yes, don't ask again" writes its grant to the settings.local.json of the working
    directory. Such a grant adds to every session started there and can undo a narrowing of the
    template: for example, a local `Bash(gh issue *)` allows `gh issue comment` again after the
    template has narrowed it.
    """
    home = pathlib.Path.home()
    paths = [home / ".claude" / "settings.local.json"]
    for root in (home / "Research", *sorted((home / "Research").glob("*"))):
        paths += [root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]
    found, warnings = [], []
    for path in paths:
        # stat() in the try, because Path.is_file() raises on Python 3.11 where a directory cannot
        # be searched, and returns False on 3.12 and later.
        try:
            if not stat.S_ISREG(path.stat().st_mode):
                continue
            permissions = json.loads(path.read_text(encoding="utf-8")).get("permissions", {})
            for kind in ("allow", "ask", "deny"):
                rules = permissions.get(kind, [])
                if isinstance(rules, list):
                    found += [(path, kind, rule) for rule in rules]
                else:
                    warnings.append((escaped(f"{path}: the value of permissions.{kind} is not a list, so its "
                                             "rules are not listed"),))
        except (FileNotFoundError, NotADirectoryError):
            continue
        except (OSError, ValueError, AttributeError, TypeError, RecursionError) as e:
            warnings.append((escaped(f"{path} cannot be read as a settings file: {type(e).__name__}: {e}"),))
    if found:
        warnings.insert(0, (f"{len(found)} permission rule(s) outside ~/.claude/settings.json — fold them into the "
                            "settings template or delete them; `harness settings` does not measure them:",
                            *(escaped(f"  {path}  {kind}  {rule}") for path, kind, rule in found)))
    return warnings


def run(args):
    """Set the profile for `read_settings`, then run the subcommand of `settings`."""
    global PROFILE
    PROFILE = args.profile
    return args.func(args)


def register(sub):
    register_settings(sub)
    changing(sub.add_parser("trust", help="trust the research root and every repository in it for Claude Code",
                            description="Mark the research root and every git repository under it as trusted in "
                                        "~/.claude.json, so that Claude Code shows no trust dialog. Without --apply "
                                        "it lists the untrusted roots and exits 1 when there is one; --apply writes "
                                        "~/.claude.json. Run it outside a session, which cannot read that file.")
             ).set_defaults(run=cmd_trust)


def register_settings(sub):
    top = sub.add_parser("settings", help="measure and check the Claude Code settings",
                         description="Measure and check the Claude Code settings against the Bash commands of the "
                                     "recent session transcripts in ~/.claude/projects/. Each subcommand of "
                                     "`settings` is read-only: it prints a report and changes no file.")
    top.set_defaults(run=run)
    sub = top.add_subparsers(dest="cmd", metavar="<sub>", required=True)

    s = sub.add_parser("surface", help="prompt surface of one settings file",
                       description="Count the segments of the recent Bash commands that reach a permission prompt "
                                   "under one settings file, by leading word. Read-only.")
    s.add_argument("--settings", default=str(LIVE), metavar="F",
                   help="the settings file to measure (default: ~/.claude/settings.json)")
    s.add_argument("--days", type=int, default=5, metavar="N",
                   help="read the Bash commands of the last N days (default: 5)")
    s.add_argument("--head", type=int, default=0, metavar="N",
                   help="also print the N most frequent prompting segments (default: 0, none)")
    s.set_defaults(func=cmd_surface)

    c = sub.add_parser("compare", help="prompt surface of two settings files, side by side",
                       description="Count the segments of the recent Bash commands that reach a permission prompt "
                                   "under two settings files, by leading word, side by side and with the difference. "
                                   "Read-only.")
    c.add_argument("old", help="the settings file before the change")
    c.add_argument("new", help="the settings file after the change")
    c.add_argument("--days", type=int, default=5, metavar="N",
                   help="read the Bash commands of the last N days (default: 5)")
    c.set_defaults(func=cmd_compare)

    m = sub.add_parser("selftest", help="check the matcher against the recorded Claude Code cases",
                       description="Check the Bash matcher of this module against the recorded cases of Claude "
                                   "Code. Read-only; exits 1 when a case fails. Run it after a Claude Code update.")
    m.set_defaults(func=cmd_selftest)

    t = sub.add_parser("twins", help="emit the git -C twins of a rule set",
                       description="Print the `git -C * <sub>` twin of each plain `git` rule of a settings file, as "
                                   "lines for its rule lists: `Bash(git status *)` does not match "
                                   "`git -C /path status`. Read-only.")
    t.add_argument("--settings", default=str(LIVE), metavar="F",
                   help="the settings file to read (default: ~/.claude/settings.json)")
    t.add_argument("--list", choices=("allow", "ask", "deny"),
                   help="print the twins of this list only (default: all three)")
    t.set_defaults(func=cmd_twins)


# ---------------------------------------------------------------------------------------------
# The trust


def roots():
    """The research root and every directory under it that holds a `.git` directory."""
    root = os.path.realpath(research_root())
    found = [root]
    for path, dirs, _ in os.walk(root):
        if os.path.isdir(os.path.join(path, ".git")) and path != root:
            found.append(path)
        dirs[:] = [d for d in dirs if d not in SKIP and not os.path.islink(os.path.join(path, d))]
    return sorted(found)


def cmd_trust(args):
    try:
        with open(CONFIG, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise HarnessError(f"cannot read {CONFIG}: {e.strerror} — run it outside a session") from e
    except UnicodeDecodeError as e:
        raise HarnessError(f"{CONFIG} is not UTF-8: {e.reason} at byte {e.start}") from None
    config = json_object(CONFIG, text)
    projects = config.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise HarnessError(f"{CONFIG}: the value of projects is not a JSON object")
    missing = [p for p in roots() if not projects.get(p, {}).get("hasTrustDialogAccepted")]
    for path in missing:
        print(("trust  " if args.apply else "untrusted  ") + path)
    print(f"{len(missing)} untrusted" + (", now trusted" if args.apply and missing else ""))
    if args.apply and missing:
        for path in missing:
            projects.setdefault(path, {})["hasTrustDialogAccepted"] = True
        mode = os.stat(CONFIG).st_mode & 0o777
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CONFIG), prefix=".claude.json.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.chmod(tmp, mode)
        os.replace(tmp, CONFIG)
    return outcome(args, len(missing))


# ---------------------------------------------------------------------------------------------
# The layer of `harness install`


def tree_agents(profile):
    """The tree instructions, the directory that the profile key `tree_agents` names."""
    value = render_profile.get(profile, "tree_agents")
    if not isinstance(value, str) or not pathlib.Path(value).is_absolute():
        raise HarnessError(f"tree_agents: {value!r} is not an absolute path")
    tree = pathlib.Path(value)
    if not tree.is_dir():
        raise HarnessError(f"tree_agents: {tree} is not a directory")
    return tree


def harness_checkout(profile):
    """The checkout of this repository that the profile key `harness` names, which the stamp names
    the sources below; None with no such key, and the stamp then names this checkout."""
    if "harness" not in profile:
        return None
    value = profile["harness"]
    if not isinstance(value, str) or not pathlib.Path(value).is_absolute():
        raise HarnessError(f"harness: {value!r} is not an absolute path")
    return pathlib.Path(value)


def claude_sources(profile):
    """Each source of ~/.claude/: (directory, installed prefix, top-level names not installed,
    top-level directories whose files are skipped with a SKIP line)."""
    return [*((d, prefix, ADAPTER_CODE if d == CLAUDE_ADAPTER else set(), set()) for d, prefix in CLAUDE_SOURCES),
            (REPO / "hooks", "hooks", {"probe.py"}, set()),
            (tree_agents(profile), "", {"README.md"}, {"agents", "hooks"})]


def source_of(sources, dst):
    """The source files of the installed path `dst` in `sources`, as claude_sources gives them."""
    path = pathlib.PurePosixPath(dst)
    return [d / path.relative_to(prefix) for d, prefix, _, _ in sources
            if path.is_relative_to(prefix) and (d / path.relative_to(prefix)).is_file()]


def claude_plan(profile, sources=None, templates=None):
    """[(installed path relative to ~/.claude, bytes, mode)] of the Claude Code layer; `templates`
    defaults to CLAUDE_TEMPLATES. A file below a top-level name that its source does not install,
    as the source's third element names it, is not planned; a file below a skipped top-level
    directory of its source, as the source's fourth element names it (compared as `fold` does), is
    printed as a SKIP line and not planned.

    Exits 2, through HarnessError and before anything is written, on a source that holds the
    Claude Code settings or a file that cannot be read, on a file of adapters/claude/ below a
    directory that a neutral directory or hooks/ installs, and on a path that two sources hold.
    The installed paths are checked by `install.check_files`, as every frontend's are.
    """
    templates = CLAUDE_TEMPLATES if templates is None else templates
    owner, plan = {}, []
    for directory, prefix, skip, skipped in claude_sources(profile) if sources is None else sources:
        for rel in install.source_files(directory):
            if rel.parts[0] in skip:
                continue
            if install.fold(rel.parts[0]) in skipped:
                print(f"SKIP {directory / rel} — agents and hooks install from this repository only")
                continue
            if directory == CLAUDE_ADAPTER and install.fold(rel.parts[0]) in {*NEUTRAL, "hooks"}:
                raise HarnessError(f"{directory / rel}: a file of ~/.claude/{install.fold(rel.parts[0])}/ has its source "
                                   f"in {install.fold(rel.parts[0])}/ of this repository, not in {directory}")
            src, dst = directory / rel, pathlib.PurePosixPath(prefix, rel).as_posix()
            if install.fold(dst) in CLAUDE_SETTINGS:
                raise HarnessError(f"{src}: ~/.claude/{dst} is the Claude Code settings, which `harness install` "
                                   "merges from the settings template; no source of this install holds it")
            if install.fold(dst) in owner:
                raise HarnessError(f"~/.claude/{dst} has two sources, {owner[install.fold(dst)]} and {src}")
            owner[install.fold(dst)] = src
            try:
                data = render_profile.render_file(src, profile).encode() if dst in templates else src.read_bytes()
                mode = stat.S_IMODE(src.stat().st_mode) if dst.startswith("hooks/") else 0o644
            except (OSError, ValueError) as e:
                raise HarnessError(f"{src} cannot be read: {e}") from None
            plan.append((dst, data, mode))
    return sorted(plan)


def claude_extras(root, plan):
    """The installed files with no source, below each top-level directory that `plan` writes
    into; skills/synced/, a hidden name and the rest of `root` are not searched. A directory
    that cannot be read exits 2."""
    ours = {install.fold(dst) for dst, _, _ in plan}
    extra = []
    for top in sorted({dst.split("/")[0] for dst, _, _ in plan if "/" in dst}):
        if not (root / top).is_dir():
            continue
        for path, dirs, files in os.walk(root / top, onerror=install.unreadable):
            rel = pathlib.Path(path).relative_to(root)
            dirs[:] = sorted(d for d in dirs if not install.hidden(d) and (rel / d).as_posix() != "skills/synced")
            extra += [pathlib.Path(path, f) for f in sorted(files)
                      if not install.hidden(f) and install.fold((rel / f).as_posix()) not in ours]
    return extra


def load_models(path):
    """{tier: model} of the [claude] table of the models.toml at `path`: exactly the tiers of
    frontmatter.TIERS, each a model with no control character of MODEL_CONTROL that is not a word
    of YAML_WORDS; any other table exits 2 (profile.tier_table)."""
    models = render_profile.tier_table(path, "claude", "Claude Code")
    wrong = [t for t in frontmatter.TIERS if MODEL_CONTROL.search(models[t]) or models[t].lower() in YAML_WORDS]
    if wrong:
        raise HarnessError(f"{path}: the tier {', '.join(wrong)} of [claude] is "
                           + ", ".join(repr(models[t]) for t in wrong) + ", which the install does not write "
                           "into `model:`: a model holds no control character and is no word that YAML reads "
                           "as a boolean or null")
    return models


def neutral_source(src):
    """Whether `src` is an agent of agents/ or a SKILL.md of skills/ in this repository, whose
    `model:` and `tools:` `render_source` rewrites."""
    return src.parent == neutral.AGENTS or (src.name == "SKILL.md" and src.parent.parent == neutral.SKILLS)


def render_source(src, data, models):
    """`data`, the bytes of the agent or skill at `src`, with the value of `model:` replaced by its
    model in `models`, load_models' table, each `tools:` item by its name in TOOLS, and the
    `cacheTtl:` line indented below a new `experimental:` line; every other byte as it is. A model
    is written bare where MODEL matches it and the source's value is not quoted, else as JSON
    writes it. A value outside the neutral vocabulary exits 2 (frontmatter.parse_file)."""
    fm = frontmatter.parse_file(src, data)
    lines = data.decode("utf-8").split("\n")
    key = None
    for i in range(1, lines.index("---", 1)):
        line = lines[i]
        item = frontmatter.ITEM_LINE.fullmatch(line)
        if item is None:
            key = line.split(":", 1)[0]
            if key == "model":
                rest = line.split(":", 1)[1]
                value = rest.strip(" ")
                model = models[fm.meta["model"]]
                bare = MODEL.fullmatch(model) and not value.startswith('"')
                lines[i] = "model:" + rest.replace(value, model if bare else json.dumps(model), 1)
            elif key == "cacheTtl":
                # Claude Code reads an agent's prompt-cache TTL from `experimental:` alone, and
                # ignores a top-level `cacheTtl:`.
                lines[i] = "experimental:\n  " + line
        elif key == "tools":
            tool = item.group(1).strip(" ")
            name = TOOLS[tool] if tool in TOOLS else MCP_PREFIX + tool.removeprefix(frontmatter.MCP)
            lines[i] = "  - " + item.group(1).replace(tool, name, 1)
    return "\n".join(lines).encode("utf-8")


def plan(ctx):
    """The Claude Code layer of `harness install`, as the docstring of this module says. Its
    `rules` are [(installed path, source, bytes)] of each planned file below rules/, for oh-my-pi
    and Antigravity, and its `shared` the [(installed path, rendered bytes, mode)] of each file that
    frontends.shared names, which OpenCode, oh-my-pi and Antigravity copy.

    Exits 2 before anything is written: on a missing `tree_agents` key, or a value that is not
    the absolute path of a directory; on a source that holds the Claude Code settings, a symbolic
    link, an entry that is neither a file nor a directory, or a directory or file that cannot be
    read; on a file of adapters/claude/ below a directory that a neutral directory or hooks/
    installs; on a path that two sources hold, compared with case and Unicode form folded on
    every platform, as the default macOS volume compares them; on an installed path, or a
    directory above one, that is a symbolic link; and on an installed path that is not a readable
    file below directories."""
    root = pathlib.Path.home() / ".claude"
    # The settings go first, so that a new deny rule is in place before the files it protects.
    settings = settings_file(root, ctx.profile, render_profile.network_path(ctx.args.profile))
    models = load_models(ctx.models)
    layer_sources = claude_sources(ctx.profile)
    layer = claude_plan(ctx.profile, layer_sources)
    files = [settings]
    for dst, data, mode in layer:
        src = source_of(layer_sources, dst)[0]
        files.append((root / dst, render_source(src, data, models) if neutral_source(src) else data, mode,
                      f"~/.claude/{dst}"))
    # The stamp goes after the layer, so that an apply that stops before its end leaves the old one.
    # It is over the source bytes of `layer`, which the hook reads again, not over the rendered ones.
    files.append((root / install.STAMP, install.stamp_bytes(layer_sources, layer, harness_checkout(ctx.profile)), 0o644,
                  f"~/.claude/{install.STAMP}"))
    extra = [f"\nEXTRA: {f} is installed and has no source here; the install leaves it.\n"
             f"       To remove it:  rm '{f}'" for f in claude_extras(root, layer)]
    rules = [(dst, source_of(layer_sources, dst)[0], data) for dst, data, _ in layer if dst.startswith("rules/")]
    rendered = {str(f[0].relative_to(root)): f[1] for f in files}
    shared = [(dst, rendered[dst], mode) for dst, _, mode in layer if frontends.shared(dst)]
    return frontends.Plan(files=files, warnings=stray_warnings(), extra=extra, rules=rules, shared=shared)


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`

# The installed paths whose source is in this repository: in agents/, skills/, rules/,
# instructions/, commands/ or adapters/claude/. The tree instructions hold
# instructions/research-tree.md and rules/meta-repository.md.
MOVED = ["CLAUDE.md", "RTK.md", "instructions/core.md",
         *(f"agents/{a}.md" for a in [
             "advisor", "arbitrator", "changelog-scribe", "ci-triage", "exhaustive-auditor", "git-hook-triage",
             "julia-branch-verifier", "julia-builder", "julia-critic", "julia-load-doctor",
             "julia-perf-analyst", "julia-pr-reviewer", "julia-pr-shepherd", "julia-test-runner",
             "latex-verifier", "literature-scout", "part-builder", "part-critic", "reader", "worker"]),
         "commands/merge-pr.md", "commands/review-pr.md",
         *(f"rules/{r}.md" for r in [
             "changelog", "generated-hooks-and-workflows", "instruction-files", "julia-code", "julia-docs",
             "julia-tests", "known-issues"]),
         "skills/build-part/SKILL.md", "skills/build-part/edges.md", "skills/build-part/evidence.md",
         "skills/build-reviewed/SKILL.md",
         *(f"skills/{s}/SKILL.md" for s in [
             "julia-package-audit", "julia-performance", "julia-release", "julia-structure",
             "julia-surgical-fix", "latex-revision", "math-verify", "plan-parts", "wait-what", "which-model"]),
         "skills/plan-parts/plan-sections.md"]


def selftest():
    """The matcher of the settings, then the Claude Code layer of `harness install`, end to end on
    scratch HOMEs."""
    total, wrong = matcher_cases()

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  claude: {label}")

    with tempfile.TemporaryDirectory() as tmp:
        layer_cases(check, pathlib.Path(tmp))
    return total, wrong


def layer_cases(check, tmp):
    """One case per decided edge of the Claude Code layer; `check(ok, label)` counts each."""
    from harness import sources as neutral
    from harness.install_cases import RULE_HEAD, Scratch

    this = sys.modules[__name__]
    scratch = Scratch(check, tmp)
    fresh, run, case, refused, tail, mode = (scratch.fresh, scratch.run, scratch.case, scratch.refused,
                                             scratch.tail, scratch.mode)
    hooks = sorted(f.name for f in (REPO / "hooks").iterdir() if f.is_file() and f.name != "probe.py")

    # A scratch source holds no agent that a council could copy, so its model tables have none.
    no_council = tmp / "models-no-council.toml"
    no_council.write_text(re.sub(r"(?ms)^julia-critic = \[$.*?^\]\n", "",
                                 (REPO / "examples" / "models.toml").read_text()))

    def inproc(base, source, apply=False, templates=None):
        """`harness install` in this process, as `run` does, with `source`, when given, as the one
        source in this repository, which mirrors ~/.claude/, the example model tables with no
        council, and `templates`, when given, as CLAUDE_TEMPLATES; (exit status, output)."""
        out = io.StringIO()
        args = argparse.Namespace(profile=str(base / "profile.toml"), models=str(no_council), apply=apply, force=False)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, HOME=str(base / "home"),
                                                OPENCODE_CONFIG_DIR=str(base / "opencode"),
                                                PI_CODING_AGENT_DIR=str(base / "omp")))
            stack.enter_context(mock.patch.object(install, "JULIA_ENV", base / "julia"))
            if source is not None:
                stack.enter_context(mock.patch.object(this, "CLAUDE_SOURCES", [(source, "")]))
                stack.enter_context(mock.patch.object(neutral, "AGENTS", source / "agents"))
                stack.enter_context(mock.patch.object(neutral, "SKILLS", source / "skills"))
            if templates is not None:
                stack.enter_context(mock.patch.object(this, "CLAUDE_TEMPLATES", frozenset(templates)))
            stack.enter_context(contextlib.redirect_stdout(out))
            try:
                code = install.cmd_install(args)
            except HarnessError as e:
                code = 2
                out.write(f"\n{e}")
        return code, out.getvalue()

    # The layout, byte for byte, the modes, and a second dry run after the apply. The code of this
    # adapter, adapters/claude/adapter.py, is not installed.
    base, claude, tree = fresh(["instructions/research-tree.md", "rules/tool.sh", "README.md"])
    (tree / "rules" / "tool.sh").chmod(0o755)
    code, text = run(base, "--apply")
    # The cases below read the files that this install writes: a failed one leaves them unwritten.
    if code != 0:
        check(False, f"the setup install --apply of the layer cases exits {code}: {tail(text)!r}; "
                     f"the layer cases after it do not run")
        return
    again, text2 = run(base)
    case(lambda: code == 0 and again == 0,
         f"after an --apply, a second dry run exits 0: {code}, {again}, {tail(text2)}")
    case(lambda: all((claude / "hooks" / h).read_bytes() == (REPO / "hooks" / h).read_bytes() for h in hooks)
         and not (claude / "hooks" / "probe.py").exists() and not (claude / "README.md").exists()
         and (claude / "rules" / "tool.sh").is_file()
         and not (claude / "adapter.py").exists() and "adapter.py" not in text + text2,
         "hooks/ installs into hooks/, the tree instructions at their own path; probe.py, README.md and "
         "adapters/claude/adapter.py do not")
    case(lambda: (claude / "instructions" / "research-tree.md").read_bytes()
         == (tree / "instructions" / "research-tree.md").read_bytes(),
         "a file that is not a template and holds {home} is copied byte for byte")
    case(lambda: all(mode(claude / "hooks" / h) == mode(REPO / "hooks" / h) for h in hooks)
         and mode(claude / "rules" / "tool.sh") == 0o644,
         "a hook keeps its source's mode, and every other file is installed 0644")
    if (claude / "hooks" / hooks[0]).is_file():
        (claude / "hooks" / hooks[0]).chmod(0o644)
    code, text = run(base)
    case(lambda: code == 1 and f"~/.claude/hooks/{hooks[0]}" in text and "MODE" in text,
         f"a hook whose mode alone differs is a change: {code}, {tail(text)}")

    # The neutral vocabulary: the Claude Code renders of two agents are the installed files of
    # 2f31fee, byte for byte, and every agent and skill differs from its source in the value of
    # `model:`, the `tools:` items and the place of `cacheTtl:` alone.
    example = load_models(REPO / "examples" / "models.toml")
    for name in ["julia-builder", "literature-scout"]:
        src = REPO / "agents" / f"{name}.md"
        case(lambda: render_source(src, src.read_bytes(), example)
             == (CLAUDE_ADAPTER / "fixtures" / f"{name}.md").read_bytes(),
             f"the Claude Code render of agents/{name}.md is fixtures/{name}.md, the installed file of 2f31fee")
    quoted = tmp / "quoted.md"
    quoted.write_text('---\nname: q\ndescription: "d"\nmodel: "large"\n---\nbody\n')
    case(lambda: render_source(quoted, quoted.read_bytes(), example)
         == b'---\nname: q\ndescription: "d"\nmodel: "opus"\n---\nbody\n',
         'a quoted `model: "large"` renders as the quoted model, `model: "opus"`')
    ttl = tmp / "ttl.md"
    ttl.write_text('---\nname: t\ndescription: "d"\ncacheTtl: 1h\nmodel: small\n---\ncacheTtl: 1h\n')
    case(lambda: render_source(ttl, ttl.read_bytes(), example)
         == b'---\nname: t\ndescription: "d"\nexperimental:\n  cacheTtl: 1h\nmodel: haiku\n---\ncacheTtl: 1h\n',
         "`cacheTtl: 1h` renders below a new `experimental:` line, and the same text in the body stays")
    case(lambda: sorted(TOOLS) == sorted(frontmatter.TOOLS),
         f"TOOLS maps exactly the neutral tools of frontmatter.TOOLS: {sorted(set(TOOLS) ^ set(frontmatter.TOOLS))}")
    base, claude, tree = fresh()
    code, text = run(base, "--apply")

    def changed_lines(src):
        """The lines in which the installed copy of `src` differs from it, as (source, installed).
        An installed `experimental:` line and the line after it count as one line."""
        old = src.read_text().split("\n")
        new = (claude / src.relative_to(REPO)).read_text().replace("\nexperimental:\n", "\nexperimental:\0")
        new = [line.replace("\0", "\n") for line in new.split("\n")]
        count = [("line count", len(old), len(new))] * (len(old) != len(new))
        return [(a, b) for a, b in zip(old, new) if a != b] + count

    names = set(TOOLS.values())
    wrong = {str(src.relative_to(REPO)): [(a, b) for a, b in changed_lines(src)
                                         if not (re.fullmatch(r"model: (large|medium|small)", a)
                                                 and b == f"model: {example[a[len('model: '):]]}")
                                         and not (re.fullmatch(r"  - [a-z_]+|  - mcp/kaimon/\w+", a)
                                                  and (b[4:] in names or b[4:].startswith(MCP_PREFIX)))
                                         and not (a.startswith("cacheTtl:") and b == "experimental:\n  " + a)]
             for src in neutral.listing()}
    def owed(src):
        """The number of lines that the render changes in `src`: its `model:`, its `tools:` items and
        its `cacheTtl:`."""
        meta = frontmatter.parse_file(src).meta
        return ("model" in meta) + len(meta.get("tools", [])) + ("cacheTtl" in meta)

    # Each `model:`, each `tools:` item and each `cacheTtl:` of a source changes, so a source
    # installed as it is fails.
    unchanged = [str(src.relative_to(REPO)) for src in neutral.listing() if len(changed_lines(src)) != owed(src)]
    case(lambda: code == 0 and len(wrong) > 25 and not any(wrong.values()) and not unchanged
         and any(s.name == "SKILL.md" and changed_lines(s) for s in neutral.listing()),
         f"every agent and skill is installed with its `model:` mapped by [claude], its `tools:` items by TOOLS "
         f"and its `cacheTtl:` below `experimental:`, and every other byte as in its source: {code}, "
         f"{[(k, v) for k, v in wrong.items() if v][:3]}, "
         f"not rewritten: {unchanged}")

    # [claude] is required, with exactly the three tiers, each a model; any other table exits 2 and
    # writes nothing.
    text0 = (REPO / "examples" / "models.toml").read_text()
    for label, models_text in [
        ("no [claude] table", re.sub(r'(?m)^\[claude\]\n(?:\w+ = "\w+"\n)+', "", text0)),
        ("no small tier in [claude]", text0.replace('small = "haiku"\n', "", 1)),
        ("a blank tier in [claude]", text0.replace('small = "haiku"\n', 'small = " "\n', 1)),
        ("a tier that is a number in [claude]", text0.replace('small = "haiku"\n', "small = 5\n", 1)),
        ("a fourth key in [claude]", text0.replace('small = "haiku"\n', 'small = "haiku"\nhuge = "x"\n', 1)),
        # A newline or another control character, and a word that YAML reads as a boolean or null.
        *((f"the model {value} in [claude]", text0.replace('small = "haiku"\n', f'small = "{value}"\n', 1))
          for value in [r"haiku\npermissionMode: bypassPermissions", r"hai\tku", r"haiku\r", r"haiku\u0007",
                        *(r"haiku\u%04x" % c for c in (0x7F, 0x85, 0x2028, 0x2029)), "null", "Yes"]),
    ]:
        base, claude, tree = fresh(["rules/x.md"])
        models = base / "models.toml"
        models.write_text(models_text)
        code, text = run(base, "--apply", models=models)
        case(lambda: models_text != text0 and refused(code, text) and str(models) in text and "[claude]" in text
             and not (claude / "rules").exists() and not (base / "opencode" / "opencode.jsonc").exists(),
             f"a models.toml with {label} exits 2, names the file and [claude], and writes nothing: "
             f"{code}, {tail(text)}")

    # A model of [claude] loads, a Bedrock and a Vertex model ID among them, and the rendered agent's
    # `model:` reads as that string: a plain YAML scalar of MODEL, else a YAML double-quoted scalar
    # with JSON's escapes, also for a source whose value is quoted.
    def model_line(src, models):
        """The `model:` line of the agent `src` rendered with the [claude] table of `models`, or the
        error that the load or the render raises."""
        try:
            return render_source(src, src.read_bytes(), load_models(models)).decode().split("\n")[3]
        except Exception as e:  # a refusal is the case's failure, not the end of `harness test`
            return f"raised {type(e).__name__}: {e}"

    agent = tmp / "agent-small.md"
    agent.write_text('---\nname: a\ndescription: "d"\nmodel: small\n---\nbody\n')
    for value in ["opus", "claude-opus-4-1", "claude-3.5-haiku", "opus[1m]", "inherit",
                  "us.anthropic.claude-opus-4-1-20250805-v1:0", "claude-opus-4-1@20250805", "a: b", "haiku #1",
                  " haiku", "haiku ", "[haiku]", 'hai"ku', "hai\\ku", "1", "-haiku", "hai ku", "modèle"]:
        models = tmp / "models-value.toml"
        models.write_text(text0.replace('small = "haiku"\n', f"small = {json.dumps(value)}\n", 1))

        line = model_line(agent, models)
        written = line.removeprefix("model: ")
        case(lambda: load_models(models)["small"] == value and line.startswith("model: ")
             and (written == value if MODEL.fullmatch(value) else written[:1] == '"' and json.loads(written) == value),
             f"the model {value!r} of [claude] loads, and the rendered `model:` reads as it: {line!r}")
    agent.write_text('---\nname: a\ndescription: "d"\nmodel: "small"\n---\nbody\n')
    models.write_text(text0.replace('small = "haiku"\n', 'small = "us.anthropic.claude-opus-4-1-20250805-v1:0"\n', 1))
    line = model_line(agent, models)
    case(lambda: line == 'model: "us.anthropic.claude-opus-4-1-20250805-v1:0"',
         f'a quoted `model: "small"` renders a Bedrock model ID quoted once: {line!r}')

    # A source with a value outside the neutral vocabulary exits 2, names the file, and writes nothing.
    for rel, lines in [("agents/x.md", "model: opus"), ("agents/x.md", "tools:\n  - Read"),
                       ("agents/x.md", "tools:\n  - mcp/kaimon/*"), ("skills/x/SKILL.md", "model: opus")]:
        base, claude, tree = fresh(["rules/x.md"])
        source = base / "claude"
        (source / rel).parent.mkdir(parents=True)
        (source / "skills").mkdir(exist_ok=True)
        (source / rel).write_text(f'---\nname: x\ndescription: "d"\n{lines}\n---\nbody\n')
        code, text = inproc(base, source, apply=True)
        case(lambda: refused(code, text) and str(source / rel) in text
             and not (claude / rel).exists() and not (claude / "rules").exists()
             and not (base / "opencode" / "opencode.jsonc").exists(),
             f"{rel} with {lines!r} exits 2, names the file and writes nothing: {code}, {tail(text)}")

    # A file with no source, in a directory the install writes, is EXTRA; nothing else is.
    base, claude, tree = fresh(["skills/mine/SKILL.md"])
    run(base, "--apply")
    # skills/other/ holds no installed file and no SKILL.md, so it is searched and is no skill.
    for rel in ["hooks/old.py", "skills/other/notes.md", "hooks/.hidden", "hooks/.claude/.cc-writes/x",
                "skills/synced/s/SKILL.md", "projects/p.jsonl"]:
        (claude / rel).parent.mkdir(parents=True, exist_ok=True)
        (claude / rel).write_text("x\n")
    expected = [claude / "hooks" / "old.py", claude / "skills" / "other" / "notes.md"]
    code, text = run(base)
    applied, text2 = run(base, "--apply")
    extra = [[l for l in t.splitlines() if "EXTRA" in l] for t in (text, text2)]
    case(lambda: code == 0 and applied == 0
         and all(len(e) == 2 and all(str(f) in " ".join(e) for f in expected) for e in extra)
         and all(f"rm '{f}'" in t for f in expected for t in (text, text2)) and all(f.is_file() for f in expected),
         "an installed file with no source is EXTRA, with its removal, not counted and not removed by an --apply; "
         "a hidden name, skills/synced/ and a directory the layer does not write are not: "
         f"{code}, {applied}, {extra}")

    # A directory that cannot be read below a top-level directory the layer writes into exits 2,
    # before anything is written.
    base, claude, tree = fresh(["rules/x.md"])
    (claude / "rules" / "sub").mkdir(parents=True)
    (claude / "rules" / "sub").chmod(0)
    code, text = run(base, "--apply")
    (claude / "rules" / "sub").chmod(0o755)
    case(lambda: refused(code, text) and str(claude / "rules" / "sub") in text
         and not (claude / "rules" / "x.md").exists() and not (base / "opencode" / "opencode.jsonc").exists(),
         f"an installed directory that cannot be read exits 2 and writes nothing: {code}, {tail(text)}")

    # A path in both sources, also when the names differ in case or in Unicode form only:
    # ~/.claude is on a volume that folds both, where they are one installed file. The Julia
    # environment is stale, so that a write of it before the check shows.
    nfc, nfd = (unicodedata.normalize(form, "é.md") for form in ("NFC", "NFD"))
    for mine, name in (("x.md", "x.md"), ("x.md", "X.md"), (nfc, nfd)):
        base, claude, tree = fresh([f"rules/{name}"])
        source = base / "claude"
        (source / "rules").mkdir(parents=True)
        (source / "rules" / mine).write_text("x\n")
        (base / "julia" / "Project.toml").write_text("stale\n")
        code, text = inproc(base, source, apply=True)
        case(lambda: refused(code, text) and "two sources" in text and str(source / "rules" / mine) in text
             and str(tree / "rules" / name) in text and not (claude / "rules").exists()
             and not (claude / "hooks").exists() and not (base / "opencode" / "opencode.jsonc").exists()
             and (base / "julia" / "Project.toml").read_text() == "stale\n",
             f"a path in both sources, as rules/{mine} and rules/{ascii(name)[1:-1]}, exits 2, names both and "
             f"writes nothing: {code}, {tail(text)}")

    # A source at prefix "" mirrors ~/.claude/, a path in it and in the tree instructions exits 2,
    # and a file that the install lists as a template is rendered with the profile.
    base, claude, tree = fresh(["rules/x.md"])
    source = base / "claude"
    for name in ["rules/julia-code.md", "rules/t.md"]:
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(f"{RULE_HEAD}{name}: written at {{home}}\n")
    code, text = inproc(base, source, apply=True, templates={"rules/t.md"})
    home = render_profile.load(base / "profile.toml")["home"]
    case(lambda: code == 0 and (claude / "rules" / "julia-code.md").read_bytes()
         == (source / "rules" / "julia-code.md").read_bytes()
         and (claude / "rules" / "t.md").read_text() == f"{RULE_HEAD}rules/t.md: written at {home}\n"
         and not (claude / "claude").exists(),
         f"a source at prefix \"\" installs at its own path, and a template is rendered with the profile: "
         f"{code}, {tail(text)}")
    case(lambda: (base / "omp" / "rules" / "t.md").read_text()
         == '---\nglobs: ["**/*.x"]\ndescription: "A rule of the scratch tree."\n---\n'
         + f"rules/t.md: written at {home}\n",
         "oh-my-pi's copy of a template rule is rendered with the profile too")
    (source / "rules" / "x.md").write_text("x\n")
    code, text = inproc(base, source)
    case(lambda: code == 2 and str(source / "rules" / "x.md") in text and str(tree / "rules" / "x.md") in text,
         f"a path in a source of this repository and in the tree instructions exits 2 and names both: {code}, {tail(text)}")

    # The same on the sources of this repository as they are: a neutral directory at its own
    # prefix, at one depth and at two, also when the names differ in case, and adapters/claude/.
    for name, mine in [("rules/julia-code.md", "rules/julia-code.md"), ("rules/Julia-Code.md", "rules/julia-code.md"),
                       ("skills/build-part/SKILL.md", "skills/build-part/SKILL.md"),
                       ("RTK.md", "adapters/claude/RTK.md")]:
        base, claude, tree = fresh([name])
        code, text = run(base)
        case(lambda: refused(code, text) and "two sources" in text and str(REPO / mine) in text
             and str(tree / name) in text,
             f"{name} in the tree instructions and {mine} in this repository exit 2 and name both: {code}, {tail(text)}")

    # A file of adapters/claude/ below a directory that another source of this repository installs
    # exits 2, at any depth and in any case: the neutral directories and hooks/ are the only sources
    # of those paths, and OpenCode and oh-my-pi render their agents from agents/ alone.
    def adapter(rel, also=(), apply=False):
        """The install, an --apply under `apply`, with a scratch adapters/claude/ that holds `rel`,
        and the files `also`, beside the repository's own neutral directories; (exit status,
        output, the scratch file)."""
        base, _, _ = fresh()
        source = base / "adapter"
        for name in (rel, *also):
            (source / name).parent.mkdir(parents=True, exist_ok=True)
            (source / name).write_text("x\n")
        layer = [(d, p) for d, p in CLAUDE_SOURCES if d != CLAUDE_ADAPTER] + [(source, "")]
        with mock.patch.object(this, "CLAUDE_ADAPTER", source), mock.patch.object(this, "CLAUDE_SOURCES", layer):
            return *inproc(base, None, apply=apply), source / rel

    for rel in ["agents/x.md", "Agents/x.md", "skills/s/SKILL.md", "skills/s/t/x.md", "rules/x.md",
                "instructions/x.md", "commands/x.md", "hooks/x.sh"]:
        code, text, src = adapter(rel)
        case(lambda: refused(code, text) and f"{src}: a file of ~/.claude/{rel.split('/')[0].lower()}/" in text,
             f"adapters/claude/{rel} exits 2 and names the directory it belongs in: {code}, {tail(text)}")
    # The code of the adapter and its fixtures are not sources: the dry run lists neither.
    code, text, src = adapter("agents.md", also=["adapter.py", "fixtures/x.md", "fixtures/agents/y.md"])
    case(lambda: code == 1 and "~/.claude/agents.md" in text
         and "~/.claude/adapter.py" not in text and "~/.claude/fixtures/" not in text,
         f"a file of adapters/claude/ beside those directories installs, and adapter.py and fixtures/ do not: "
         f"{code}, {tail(text)}")
    # The `SessionStart` hook skips them too: after the --apply, its digest is the stamp's.
    code, text, src = adapter("agents.md", also=["adapter.py", "fixtures/x.md", "fixtures/agents/y.md"], apply=True)
    warning = install.drift_hook().check(str(src.parents[1] / "home"))
    case(lambda: code == 0 and warning is None,
         f"the hook skips adapter.py and fixtures/ of adapters/claude/, as the plan does: {code}, {warning!r}")

    # A settings.json or a settings.local.json in a source, in any case, is refused and not
    # installed; ~/.claude/settings.json comes from the settings template only.
    for name in ["settings.json", "settings.local.json", "Settings.json"]:
        base, claude, tree = fresh([name])
        (claude / name).write_text("{}\n")
        code, text = run(base, "--apply")
        case(lambda: refused(code, text) and name in text and (claude / name).read_text() == "{}\n",
             f"a {name} in the tree instructions exits 2 and is not written: {code}, {tail(text)}")
    base, claude, tree = fresh()
    source = base / "claude"
    source.mkdir()
    (source / "settings.json").write_text('{"permissions": {}}\n')
    code, text = inproc(base, source, apply=True)
    case(lambda: code == 2 and "settings.json" in text and not (claude / "settings.json").exists(),
         f"a settings.json in a source of this repository exits 2 and is not written: {code}, {tail(text)}")

    # A symlink in a source, to a file, to a directory, or to nothing, exits 2.
    for label, make in [("a file", lambda t, o: (t / "rules" / "l.md").symlink_to(o / "x.md")),
                        ("a directory", lambda t, o: (t / "more").symlink_to(o)),
                        ("nothing", lambda t, o: (t / "rules" / "l.md").symlink_to(o / "missing.md"))]:
        base, claude, tree = fresh(["rules/x.md"])
        outside = base / "outside"
        outside.mkdir()
        (outside / "x.md").write_text("x\n")
        make(tree, outside)
        code, text = run(base)
        case(lambda: refused(code, text) and "symlink" in text,
             f"a symlink to {label} in the tree instructions exits 2: {code}, {tail(text)}")

    # An entry in a source that is neither a file nor a directory, a FIFO, exits 2 and is not read.
    base, claude, tree = fresh(["rules/x.md"])
    os.mkfifo(tree / "rules" / "pipe.md")
    code, text = run(base, "--apply")
    case(lambda: refused(code, text) and str(tree / "rules" / "pipe.md") in text
         and not (claude / "rules").exists(),
         f"a FIFO in the tree instructions exits 2 and writes nothing: {code}, {tail(text)}")

    # A source directory or file that cannot be read exits 2 and names it; a directory of mode 0444
    # can be listed, but its entries cannot be examined.
    for rel, bits in [("rules", 0), ("rules", 0o444), ("rules/x.md", 0)]:
        base, claude, tree = fresh(["rules/x.md"])
        (tree / rel).chmod(bits)
        code, text = run(base)
        (tree / rel).chmod(0o755)
        case(lambda: refused(code, text) and str(tree / rel) in text,
             f"{rel} of mode {bits:04o} in the tree instructions cannot be read and exits 2: {code}, {tail(text)}")

    # An installed path that is not what the install writes: a file where a directory goes, a
    # directory where a file goes, and a file that cannot be read.
    for label, make in [("hooks/ that is a file", lambda c: (c / "hooks").write_text("x\n")),
                        (f"hooks/{hooks[0]} that is a directory",
                         lambda c: (c / "hooks" / hooks[0]).mkdir(parents=True)),
                        (f"hooks/{hooks[0]} that cannot be read", lambda c: (
                            (c / "hooks").mkdir(), (c / "hooks" / hooks[0]).write_text("x\n"),
                            (c / "hooks" / hooks[0]).chmod(0)))]:
        base, claude, tree = fresh()
        make(claude)
        code, text = run(base, "--apply")
        case(lambda: refused(code, text) and str(claude / "hooks") in text
             and not (base / "opencode" / "opencode.jsonc").exists(),
             f"an installed {label} exits 2 and writes nothing: {code}, {tail(text)}")
        if (claude / "hooks" / hooks[0]).is_file():
            (claude / "hooks" / hooks[0]).chmod(0o644)

    # A symlink on an installed path: a file, and a directory above one.
    base, claude, tree = fresh(["rules/x.md"])
    outside = base / "outside"
    outside.mkdir()
    (outside / hooks[0]).write_text("outside\n")
    (claude / "hooks").mkdir()
    (claude / "hooks" / hooks[0]).symlink_to(outside / hooks[0])
    code, text = run(base, "--apply")
    case(lambda: code == 2 and "symlink" in text and (outside / hooks[0]).read_text() == "outside\n",
         f"an installed file that is a symlink exits 2, and nothing is written through it: {code}, {tail(text)}")
    base, claude, tree = fresh(["rules/x.md"])
    outside = base / "outside"
    outside.mkdir()
    (claude / "rules").symlink_to(outside)
    code, text = run(base, "--apply")
    case(lambda: code == 2 and "symlink" in text and not (outside / "x.md").exists(),
         f"an installed directory that is a symlink exits 2, and nothing is written through it: {code}, {tail(text)}")

    # The tree instructions: a missing key, a missing directory, an empty directory, an agent, a hook.
    base, claude, tree = fresh(key=False)
    code, text = run(base)
    case(lambda: code == 2 and "tree_agents" in text, f"a profile with no tree_agents exits 2: {code}, {tail(text)}")
    base, claude, tree = fresh()
    tree.rmdir()
    code, text = run(base)
    case(lambda: code == 2 and str(tree) in text,
         f"a tree_agents directory that does not exist exits 2: {code}, {tail(text)}")
    # The value must name an absolute directory. The run's working directory, `base`, holds the
    # directory Agents/, so "", "." and a relative "Agents" each name an existing directory.
    for raw in ['""', '"."', '"Agents"', "1"]:
        base, claude, tree = fresh(["rules/x.md"], raw=raw)
        code, text = run(base, "--apply")
        case(lambda: refused(code, text) and "tree_agents" in text and not (claude / "rules").exists(),
             f"tree_agents = {raw} exits 2 and writes nothing: {code}, {tail(text)}")
    base, claude, tree = fresh()
    code, text = run(base)
    case(lambda: code == 1 and re.search(r"^\d+ change\(s\) to make\.$", text, re.M) is not None,
         f"an empty tree_agents directory is valid: {code}, {tail(text)}")
    # An agent or a hook in the tree instructions is not installed: one SKIP line per file, not
    # counted, and the exit status does not change. A hook with the name of one in hooks/ is no
    # second source, and a name that differs in case only is skipped too.
    # The count line of the first dry run is that of the same tree without the skipped file.
    count = re.compile(r"^\d+ change\(s\) to make\.$", re.M)
    without = count.findall(run(fresh(["rules/x.md"])[0])[1])
    for rel in ["agents/private.md", "Agents/private.md", "hooks/private.py", f"hooks/{hooks[0]}"]:
        base, claude, tree = fresh([rel, "rules/x.md"])
        first, text0 = run(base)
        code, text = run(base, "--apply")
        again, text2 = run(base)
        skip = f"SKIP {tree / rel} — agents and hooks install from this repository only"
        top = rel.split("/")[0].lower()
        case(lambda: first == 1 and len(without) == 1 and count.findall(text0) == without
             and code == 0 and again == 0 and all(t.count(skip) == 1 for t in (text0, text, text2))
             and re.search(r"^0 change\(s\) to make\.$", text2, re.M) is not None
             and (claude / "rules" / "x.md").is_file()
             and ((claude / rel).read_bytes() == (REPO / rel).read_bytes() if rel == f"hooks/{hooks[0]}"
                  else not (claude / top / rel.split("/")[1]).exists()),
             f"{rel} in the tree instructions is a SKIP line, not installed and not counted: "
             f"{first}, {code}, {again}, {tail(text2)}")

    # The Claude Code settings: `harness install` merges the sections of OWNED from the rendered
    # settings template into ~/.claude/settings.json, as one file of the plan, adds each other key
    # of the template that the file lacks, and keeps every other key; ~/.claude.json, unreadable
    # here, is neither read nor written.
    settings_line = re.compile(r"^~/\.claude/settings\.json\s+(.*)$", re.M)
    home = fresh()[0]
    profile = render_profile.load(home / "profile.toml")
    template = settings_template(profile, home / "network.toml")
    owned = {k: template[k] for k in OWNED}
    others = {k: v for k, v in template.items() if k not in OWNED}

    def lacked(cfg):
        """The keys of `others` that `cfg` lacks, with the template's values, in its order."""
        return {k: v for k, v in others.items() if k not in cfg}
    base, claude, tree = fresh()
    state = base / "home" / ".claude.json"
    state.write_text('{"state": 1}\n')
    state.chmod(0)
    first, _ = run(base, "--apply")
    live = {"model": "opus", "permissions": {"allow": ["Bash(rm *)"], "deny": []}, "env": {"X": "{home} — é"},
            "statusLine": {"type": "command", "command": "x"}, "hooks": {}, "someFutureKey": [1, {"a": None}]}
    old = json.dumps(live, indent=4, ensure_ascii=False) + "\n"
    (claude / "settings.json").write_text(old)
    (claude / "settings.json").chmod(0o600)
    code, text = run(base)
    lines = text.splitlines()
    at = [i for i, line in enumerate(lines) if settings_line.fullmatch(line)]
    case(lambda: first == 0 and code == 1 and len(at) == 1 and settings_line.fullmatch(lines[at[0]]).group(1)
         .startswith("REPLACE (backup: settings.json.bak-") and lines[at[0] + 1].startswith("--- ")
         and lines[at[0] + 2].startswith("+++ ") and lines[at[0] + 3].startswith("@@ ")
         and any(l.startswith("-") and "Bash(rm *)" in l for l in lines)
         and re.search(r"^1 change\(s\) to make\.$", text, re.M) is not None
         and (claude / "settings.json").read_text() == old,
         f"a settings.json whose owned sections differ is one REPLACE line, then the unified diff of the owned "
         f"sections, one change, exit 1, and the dry run writes nothing: {first}, {code}, {at}, {tail(text)}")
    code, text = run(base, "--apply")
    merged = json.loads((claude / "settings.json").read_text())
    backups = sorted(claude.glob("settings.json.bak-*"))
    expected = {"model": "opus", "permissions": owned["permissions"], "env": {"X": "{home} — é", **others["env"]},
                "statusLine": {"type": "command", "command": "x"}, "hooks": owned["hooks"],
                "someFutureKey": [1, {"a": None}], "sandbox": owned["sandbox"],
                "modelSettings": owned["modelSettings"], **lacked(live)}
    case(lambda: code == 0 and merged == expected and list(merged) == list(expected) and len(lacked(live)) > 5
         and (claude / "settings.json").read_text() == json.dumps(expected, indent=4, ensure_ascii=False) + "\n",
         f"--apply replaces the owned sections from the rendered template, adds the template's other keys that the "
         f"file lacks after its keys and the template's `env` variables that its `env` lacks after its variables, "
         f"keeps every other key, its value and its order, and the live file's indent "
         f"of 4: {code}, {list(merged)}, {tail(text)}")
    case(lambda: len(backups) == 1 and backups[0].read_text() == old,
         f"--apply keeps the old settings.json as a backup: {[b.name for b in backups]}")
    case(lambda: mode(claude / "settings.json") == 0o600 and len(backups) == 1 and mode(backups[0]) == 0o600,
         f"--apply keeps the mode 0600 of a settings.json it replaces, in the file and in its backup: "
         f"{oct(mode(claude / 'settings.json'))}, {[oct(mode(b)) for b in backups]}")
    again, text2 = run(base)
    # An unchanged settings.json prints its line and nothing after it, not even a blank line.
    after = [b for a, b in zip(text2.splitlines(), text2.splitlines()[1:]) if settings_line.fullmatch(a)]
    case(lambda: again == 0 and [m.group(1) for m in settings_line.finditer(text2)] == ["already identical"]
         and len(after) == 1 and after[0].strip() != ""
         and re.search(r"^0 change\(s\) to make\.$", text2, re.M) is not None,
         f"the dry run after the --apply finds settings.json identical, prints no blank line after it, 0 changes, "
         f"exit 0: {again}, {after[:1]}, {tail(text2)}")
    state.chmod(0o600)
    case(lambda: state.read_text() == '{"state": 1}\n', "~/.claude.json is neither read nor written")
    # Owned sections equal to the template's in another layout, in a file that holds every key of the
    # template, are no change: the file is left as it is, and a key with another value than the
    # template's keeps it.
    (claude / "settings.json").write_text(json.dumps({"hooks": owned["hooks"], "sandbox": owned["sandbox"],
                                                      "modelSettings": owned["modelSettings"],
                                                      "permissions": owned["permissions"], **others,
                                                      "model": "x", "cleanupPeriodDays": 7}) + "\n")
    kept = (claude / "settings.json").read_bytes()
    code, text = run(base, "--apply")
    case(lambda: code == 0 and [m.group(1) for m in settings_line.finditer(text)] == ["already identical"]
         and (claude / "settings.json").read_bytes() == kept and others["cleanupPeriodDays"] != 7,
         f"a settings.json whose owned sections equal the template's, in another layout, and that holds every key "
         f"of the template, some with other values, is not rewritten: {code}, {tail(text)}")
    # A key of the template that the file lacks is in the dry run's diff, and --apply adds it after the
    # file's keys and changes no other key.
    lacking = json.loads(kept)
    del lacking["cleanupPeriodDays"]
    (claude / "settings.json").write_text(json.dumps(lacking) + "\n")
    dry, text = run(base)
    code, _ = run(base, "--apply")
    merged = json.loads((claude / "settings.json").read_text())
    case(lambda: dry == 1
         and any(l.rstrip(",") == f'+  "cleanupPeriodDays": {others["cleanupPeriodDays"]}' for l in text.splitlines())
         and any(l.rstrip(",") == '-  "cleanupPeriodDays": null' for l in text.splitlines())
         and code == 0 and merged == {**lacking, "cleanupPeriodDays": others["cleanupPeriodDays"]}
         and list(merged)[-1] == "cleanupPeriodDays",
         f"a key of the template that settings.json lacks is in the dry run's diff, and --apply adds it last and "
         f"changes no other key: {dry}, {code}, {list(merged)[-3:]}, {tail(text)}")
    # An effort or an auto-compact window that the UI wrote into modelSettings is in the diff, and
    # --apply replaces the section with the template's.
    ui = json.loads(kept)
    ui["modelSettings"] = {**ui["modelSettings"], "claude-ui-model": {"effortLevel": "low"}}
    (claude / "settings.json").write_text(json.dumps(ui) + "\n")
    dry, text = run(base)
    code, _ = run(base, "--apply")
    case(lambda: dry == 1 and any(l.startswith("-") and "claude-ui-model" in l for l in text.splitlines())
         and code == 0 and json.loads((claude / "settings.json").read_text())["modelSettings"]
         == owned["modelSettings"],
         f"a modelSettings entry that the UI wrote is in the dry run's diff, and --apply replaces the section "
         f"with the template's: {dry}, {code}, {tail(text)}")

    # An `env` variable that the file sets keeps its value; one that the file lacks is added.
    base, claude, tree = fresh()
    first = next(iter(others["env"]))
    (claude / "settings.json").write_text(json.dumps({**owned, **others, "env": {first: "own"}}, indent=2) + "\n")
    dry, text = run(base)
    code, _ = run(base, "--apply")
    again, _ = run(base)
    env = json.loads((claude / "settings.json").read_text())["env"]
    case(lambda: dry == 1 and code == 0 and again == 0 and len(others["env"]) > 1
         and env == {first: "own", **{k: v for k, v in others["env"].items() if k != first}} and list(env)[0] == first,
         f"--apply adds the template's `env` variables that the file lacks and keeps the file's value of {first}; "
         f"the next dry run has nothing to do: {dry}, {code}, {again}, {env}, {tail(text)}")

    # A missing settings.json is created with the keys of the template, indented by 2, mode 0644.
    base, claude, tree = fresh()
    code, text = run(base)
    case(lambda: code == 1 and [m.group(1) for m in settings_line.finditer(text)] == ["INSTALL"]
         and not (claude / "settings.json").exists(),
         f"the dry run prints INSTALL for a missing settings.json and counts it: {code}, {tail(text)}")
    # Under a umask of 077 only an explicit mode gives 0644; the process inherits the umask.
    umask = os.umask(0o077)
    try:
        code, text = run(base, "--apply")
    finally:
        os.umask(umask)
    case(lambda: code == 0 and list(json.loads((claude / "settings.json").read_text())) == [*owned, *others]
         and (claude / "settings.json").read_text()
         == json.dumps({**owned, **others}, indent=2, ensure_ascii=False) + "\n"
         and mode(claude / "settings.json") == 0o644,
         f"--apply writes a missing settings.json with the owned sections, then the template's other keys, "
         f"indented by 2, mode 0644 under a umask of 077: {code}, {tail(text)}")

    # Each owned key that the template lacks is removed from the live file; the other keys stay.
    # The template keeps `sandbox`, which holds the slot of the network lists, and lacks `hooks`.
    base, claude, tree = fresh()
    lacking = tmp / "settings-without-hooks.json"
    lacking.write_text(json.dumps({k: v for k, v in json.loads(PROPOSAL.read_text()).items() if k != "hooks"},
                                  indent=2, ensure_ascii=False) + "\n")
    (claude / "settings.json").write_text(json.dumps({"model": "x", "hooks": {"Stop": []}}, indent=2) + "\n")
    with mock.patch.object(this, "PROPOSAL", lacking):
        code, text = inproc(base, None, apply=True)
    merged = json.loads((claude / "settings.json").read_text())
    case(lambda: code == 0 and list(merged)[:4] == ["model", "permissions", "sandbox", "modelSettings"]
         and "hooks" not in merged and merged["model"] == "x",
         f"an owned key that the template lacks is removed from settings.json: {code}, {list(merged)}, {tail(text)}")

    # A template that cannot be rendered exits 2 and names the template, before anything is written.
    for label, key, value in [("an undefined placeholder", "allow", [*template["permissions"]["allow"],
                                                                     "Bash(x {no_such_key})"]),
                              ("a list placeholder in a string that is not a list item", "defaultMode", "{org}")]:
        base, claude, tree = fresh()
        broken = tmp / "settings-unrenderable.json"
        cfg = json.loads(PROPOSAL.read_text())
        cfg["permissions"][key] = value
        broken.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        with mock.patch.object(this, "PROPOSAL", broken):
            code, text = inproc(base, None, apply=True)
        case(lambda: code == 2 and str(broken) in text and "Traceback" not in text
             and not (claude / "settings.json").exists(),
             f"a settings template with {label} exits 2, names the template and writes nothing: {code}, {tail(text)}")

    # A lone surrogate escape, which JavaScript's JSON.stringify can write, stays an escape: in a key
    # the merge keeps, and in the printed diff of an owned section.
    base, claude, tree = fresh()
    (claude / "settings.json").write_bytes(b'{\n  "note": "\\ud800",\n  "permissions": {"allow": ["\\udfff"]}\n}\n')
    code, text = run(base)
    applied, text2 = run(base, "--apply")
    written = (claude / "settings.json").read_text()
    case(lambda: code == 1 and applied == 0 and "Traceback" not in text + text2 and "\\udfff" in text
         and '"note": "\\ud800"' in written and json.loads(written)["note"] == "\ud800",
         f"a lone surrogate escape in settings.json stays an escape in the diff and in the merged file: {code}, "
         f"{applied}, {tail(text + text2)}")

    # The merge keeps a tab indent, and writes a one-line file on one line.
    for label, data, indent in [("tab-indented", '{\n\t"model": "x",\n\t"env": {\n\t\t"A": "1"\n\t}\n}\n', "\t"),
                                ("one-line", '{"model": "x", "env": {"A": "1"}}\n', None),
                                ("one-line (a raw U+2028 in a string)",
                                 '{"model": "x' + chr(0x2028) + 'y", "env": {"A": "1"}}\n', None)]:
        base, claude, tree = fresh()
        (claude / "settings.json").write_text(data)
        code, text = run(base, "--apply")
        written = (claude / "settings.json").read_text()
        cfg = json.loads(data)
        expected = json.dumps({**cfg, "env": {**cfg["env"], **others["env"]}, **owned, **lacked(cfg)},
                              indent=indent, ensure_ascii=False) + "\n"
        case(lambda: code == 0 and written == expected and written.count("\n") == (1 if indent is None else
                                                                                   expected.count("\n")),
             f"a {label} settings.json is written in the same form: {code}, {written[:60]!r}, {tail(text)}")

    # A number outside the owned sections that the merge would write in other text exits 2, the dry run
    # and --apply, with one line that names the key, and no file changes.
    def number_file(body):
        return "{\n" + body + ',\n  "permissions": {"allow": ["Bash(rm *)"]}\n}\n'

    for body, key, literal in [('  "x": 1.10', "x", "1.10"), ('  "y": 1e400', "y", "1e400"), ('  "z": 1E5', "z", "1E5"),
                               ('  "env": {"list": [1, 2.50]}', "env.list[1]", "2.50")]:
        for argv in [(), ("--apply",)]:
            base, claude, tree = fresh(["rules/x.md"])
            live = claude / "settings.json"
            live.write_text(number_file(body))
            before = scratch.snapshot(base)
            code, text = run(base, *argv)
            lines = text.strip().splitlines()
            case(lambda: refused(code, text) and len(lines) == 1 and str(live) in lines[0] and f"`{key}`" in lines[0]
                 and f"`{literal}`" in lines[0] and scratch.snapshot(base) == before,
                 f"a settings.json with {body.strip()} exits 2 {'under --apply' if argv else 'in the dry run'} with "
                 f"one line that names {key}, and no file changes: {code}, {lines[-3:]}")
    # `1.5`, `10` and `-0.0` are written as their source text, and a number in an owned section is replaced.
    base, claude, tree = fresh(["rules/x.md"])
    live = claude / "settings.json"
    live.write_text(number_file('  "x": 1.5,\n  "y": 10,\n  "z": [-0.0],\n  "sandbox": {"n": 1.10}'))
    dry, text = run(base)
    code, text2 = run(base, "--apply")
    written = live.read_text()
    case(lambda: dry == 1 and code == 0 and '"x": 1.5,' in written and '"y": 10,' in written and "-0.0" in written
         and json.loads(written)["sandbox"] == owned["sandbox"],
         f"the numbers 1.5, 10 and -0.0 pass unchanged, and one in an owned section is replaced: {dry}, {code}, "
         f"{tail(text + text2)}")
    # A file that the merge leaves as it is keeps its numbers: there is nothing to check.
    kept = json.dumps({**owned, **others}, indent=2, ensure_ascii=False)[:-2] + ',\n  "x": 1.10\n}\n'
    live.write_text(kept)
    code, text = run(base, "--apply")
    case(lambda: code == 0 and live.read_text() == kept,
         f"a settings.json whose owned sections equal the template's keeps 1.10, unchecked: {code}, {tail(text)}")

    # The order: settings.json is the first file line of the Claude Code layer, the stamp the last.
    base, claude, tree = fresh(["rules/x.md"])
    code, text = run(base)
    labels = re.findall(r"^(~/\.claude/\S+)\s", text, re.M)
    case(lambda: len(labels) > 50 and labels[0] == "~/.claude/settings.json"
         and labels[-1] == f"~/.claude/{install.STAMP}" and labels.count("~/.claude/settings.json") == 1,
         f"settings.json is the first file line of the Claude Code layer, the stamp the last: "
         f"{labels[:2]}, {labels[-1:]}")

    # A settings.json that cannot be merged exits 2 with one line naming it and the reason, before
    # anything of any frontend is written.
    def snapshot(base):
        """Every path below `base`, with its mode, and its bytes or the target of a link."""
        out = {}
        for path, dirs, files in os.walk(base):
            for name in dirs + files:
                p = pathlib.Path(path, name)
                st = p.lstat()
                out[str(p)] = (stat.S_IMODE(st.st_mode), os.readlink(p) if p.is_symlink()
                               else p.read_bytes() if stat.S_ISREG(st.st_mode) else None)
        return out

    for label, data, reason in [("not JSON", b"{\n", "is not JSON"), ("not UTF-8", b'{"x": "\xff"}\n', "is not UTF-8"),
                                ("JSON after a UTF-8 BOM", b"\xef\xbb\xbf{}\n", "is not JSON"),
                                ("JSON that is not an object", b"[]\n", "is not a JSON object"),
                                ("JSON nested 400000 deep", b"[" * 400000 + b"]" * 400000 + b"\n", "nested too deep"),
                                ("an owned key that is a list", b'{"permissions": []}\n', "permissions"),
                                ("an owned key that is null", b'{"model": "x", "sandbox": null}\n', "sandbox"),
                                ("a symlink", None, "symlink"), ("a directory", None, "is a directory"),
                                ("unreadable, of mode 000", b"{}\n", "cannot be read")]:
        base, claude, tree = fresh(["rules/x.md"])
        live = claude / "settings.json"
        if label == "a symlink":
            (base / "outside.json").write_text("{}\n")
            live.symlink_to(base / "outside.json")
        elif label == "a directory":
            live.mkdir()
        else:
            live.write_bytes(data)
        before = snapshot(base)
        if label.startswith("unreadable"):
            live.chmod(0)
        code, text = run(base, "--apply")
        if label.startswith("unreadable"):
            live.chmod(0o644)
        lines = text.strip().splitlines()
        case(lambda: refused(code, text) and len(lines) == 1 and str(live) in lines[0] and reason in lines[0]
             and snapshot(base) == before,
             f"a settings.json that is {label} exits 2 with one line that names it and the reason, and no file "
             f"changes: {code}, {lines[-3:]}")

    # A settings.json whose stat the sandbox denies (EPERM) is a file that cannot be read, not a
    # missing one: Path.exists() returns False there on Python 3.12 and later, and raises on 3.11.
    base, claude, tree = fresh(["rules/x.md"])
    live = claude / "settings.json"
    live.write_text('{"model": "opus", "env": {"X": "1"}}\n')
    before = snapshot(base)

    def denied(real):
        def call(path, *a, **k):
            if os.fspath(path) == str(live):
                raise PermissionError(errno.EPERM, "Operation not permitted", str(live))
            return real(path, *a, **k)
        return call

    with mock.patch.object(os, "stat", denied(os.stat)), mock.patch.object(os, "lstat", denied(os.lstat)):
        code, text = inproc(base, None, apply=True)
    lines = text.strip().splitlines()
    case(lambda: code == 2 and len(lines) == 1 and str(live) in lines[0] and "cannot be read" in lines[0]
         and snapshot(base) == before,
         f"a settings.json whose stat is denied exits 2 with one line that names it, and no file changes: "
         f"{code}, {lines[-3:]}")

    # `harness settings install` and `harness settings domains` are gone; the subcommands of
    # `settings` that measure stay. The network lists are generated, so no command checks a mirror of them.
    p = subprocess.run([sys.executable, str(REPO / "bin" / "harness"), "settings", "--help"], capture_output=True,
                       text=True)
    gone = [subprocess.run([sys.executable, str(REPO / "bin" / "harness"), "settings", subcommand],
                           capture_output=True, text=True) for subcommand in ("install", "domains")]
    case(lambda: p.returncode == 0 and "install" not in p.stdout and "domains" not in p.stdout
         and all(g.returncode == 2 for g in gone)
         and all(s in p.stdout for s in ["surface", "compare", "selftest", "twins"]),
         f"`harness settings --help` lists no install and no domains, and each exits 2: {p.returncode}, "
         f"{[g.returncode for g in gone]}, {gone[-1].stderr.strip()[-120:]!r}")

    # The permission rules of the other settings files are a warning of `harness install`; one that
    # cannot be read as JSON is a warning too, not a traceback.
    base, claude, tree = fresh()
    research = base / "home" / "Research"
    for rel, data in [("Research/.claude/settings.local.json", '{"permissions": {"allow": ["Bash(gh issue *)"]}}\n'),
                      ("Research/Knowledge/.claude/settings.json", '{"permissions": {"deny": ["Read(x)"]}}\n'),
                      ("Research/Broken/.claude/settings.local.json", "{\n")]:
        (base / "home" / rel).parent.mkdir(parents=True)
        (base / "home" / rel).write_text(data)
    code, text = run(base)
    case(lambda: code == 1 and "Traceback" not in text and "WARNING: 2 permission rule(s) outside" in text
         and f"{research / '.claude' / 'settings.local.json'}  allow  Bash(gh issue *)" in text
         and f"{research / 'Knowledge' / '.claude' / 'settings.json'}  deny  Read(x)" in text
         and f"{research / 'Broken' / '.claude' / 'settings.local.json'} cannot be read as a settings file" in text,
         f"`harness install` warns about the permission rules outside ~/.claude/settings.json: {code}, {tail(text)}")
    # A directory of ~/Research that cannot be searched is a warning too, on every Python.
    base, claude, tree = fresh()
    locked = base / "home" / "Research" / "Locked"
    (locked / ".claude").mkdir(parents=True)
    (locked / ".claude" / "settings.json").write_text('{"permissions": {"allow": ["Bash(x)"]}}\n')
    locked.chmod(0)
    try:
        code, text = run(base)
    finally:
        locked.chmod(0o755)
    case(lambda: code == 1 and "Traceback" not in text
         and f"{locked / '.claude' / 'settings.json'} cannot be read as a settings file" in text,
         f"a directory of ~/Research that cannot be searched is a warning of `harness install`: {code}, {tail(text)}")
    # A stray allow, ask or deny that is not a list is one warning line that names the file and the key, and
    # lists no rule of it.
    for kind, value in [("allow", '"Bash(x)"'), ("ask", '{"Bash(y)": 1}'), ("deny", "5")]:
        base, claude, tree = fresh()
        stray = base / "home" / "Research" / ".claude" / "settings.local.json"
        stray.parent.mkdir(parents=True)
        stray.write_text(f'{{"permissions": {{"{kind}": {value}}}}}\n')
        code, text = run(base)
        lines = [l for l in text.splitlines() if str(stray) in l]
        case(lambda: code == 1 and "Traceback" not in text and len(lines) == 1 and f"permissions.{kind}" in lines[0]
             and "permission rule(s)" not in text,
             f"a stray {kind} of {value} is one warning line that names the file and the key: {code}, {lines}")

    # Each installed path whose source is in this repository is planned from there: an installed
    # copy of it is a change, never EXTRA. A path in a subdirectory has its source at the same path
    # in the repository, and a path at the top of ~/.claude/ in adapters/claude/.
    def repo_source(rel):
        return REPO / rel if "/" in rel else REPO / "adapters" / "claude" / rel

    base, claude, tree = fresh()
    for rel in MOVED:
        (claude / rel).parent.mkdir(parents=True, exist_ok=True)
        (claude / rel).write_text("an installed copy\n")
    code, text = run(base)
    case(lambda: code == 1 and all(re.search(rf"^~/\.claude/{re.escape(rel)}\s+REPLACE$", text, re.M) for rel in MOVED)
         and not any(f"EXTRA: {claude / rel} " in text for rel in MOVED),
         f"each of the {len(MOVED)} moved paths has its source in this repository, and none is EXTRA: "
         f"{[rel for rel in MOVED if not repo_source(rel).is_file()]}, {tail(text)}")

    # The tree instructions' file is research-tree.md: CLAUDE.md imports it, and OpenCode lists it.
    def imports():
        return re.findall(r"(?m)^@(\S+)$", (REPO / "adapters" / "claude" / "CLAUDE.md").read_text())

    jsonc = (REPO / "adapters" / "opencode" / "opencode.jsonc").read_text()
    case(lambda: "instructions/research-tree.md" in imports() and "instructions/profile.md" not in imports()
         and '"~/.claude/instructions/research-tree.md"' in jsonc and "instructions/profile.md" not in jsonc,
         "CLAUDE.md imports research-tree.md, and opencode.jsonc lists it")

    # Each `@` import of CLAUDE.md has a source in the plan: an import with none loads nothing.
    base, claude, tree = fresh(["instructions/research-tree.md"])
    with contextlib.redirect_stdout(io.StringIO()):
        planned = {dst for dst, _, _ in claude_plan(render_profile.load(base / "profile.toml"))}
    case(lambda: "RTK.md" in imports() and all(i in planned for i in imports()),
         f"each @ import of CLAUDE.md has a source in the plan: {imports()}, "
         f"{[i for i in imports() if i not in planned]} with none")

    # The stamp: --apply writes the sources and the digest of the `SessionStart` hook,
    # hooks/install-drift.py, over their files; an edit in a source is a change of the stamp.
    hook = install.drift_hook()
    stamp_line = re.compile(rf"^~/\.claude/{re.escape(install.STAMP)}\s+(\S+)", re.M)
    base, claude, tree = fresh(["rules/x.md", "README.md", "agents/private.md"])
    code, text = run(base, "--apply")
    again, text2 = run(base)

    def stamp():
        return json.loads((claude / install.STAMP).read_text())

    sources = [*([str(REPO / d), d, [], []] for d in ["agents", "skills", "rules", "instructions", "commands"]),
               [str(REPO / "adapters" / "claude"), "", ["adapter.py", "fixtures"], []],
               [str(REPO / "hooks"), "hooks", ["probe.py"], []],
               [str(tree), "", ["README.md"], ["agents", "hooks"]]]
    case(lambda: code == 0 and again == 0 and stamp()["sources"] == sources
         and stamp()["digest"] == hook.digest(sources) and stamp_line.findall(text) == ["INSTALL"]
         and stamp_line.findall(text2) == ["already"] and mode(claude / install.STAMP) == 0o644,
         f"--apply writes the stamp over the five neutral directories, adapters/claude/, hooks/ and the tree "
         f"instructions, and the dry run after it "
         f"finds it identical: {code}, {again}, {stamp_line.findall(text)}, {stamp_line.findall(text2)}")
    (tree / "rules" / "x.md").write_text(f"{RULE_HEAD}an edit\n")
    code, text = run(base)
    case(lambda: code == 1 and stamp_line.findall(text) == ["REPLACE"],
         f"an edit in the tree instructions makes the stamp a change: {code}, {stamp_line.findall(text)}")
    # The hook's files are the planned files, and its digest of the sources is the digest of the
    # planned bytes and modes, which the stamp records.
    profile = render_profile.load(base / "profile.toml")
    with mock.patch.dict(os.environ, HOME=str(base / "home")), contextlib.redirect_stdout(io.StringIO()):
        plan = claude_plan(profile)
    planned = [dst for dst, _, _ in plan]
    case(lambda: [dst for dst, _, _ in hook.files(sources)] == planned and len(planned) > 50
         and hook.digest(sources) == hook.digest_of(plan),
         f"the hook's files are the {len(planned)} planned files, in the same order, with the planned bytes and "
         f"modes: {sorted(set(planned) ^ {dst for dst, _, _ in hook.files(sources)})}")
    # The stamp is over the bytes that --apply installs, not over the sources read again after the
    # layer: a source edited while the apply runs is installed with its old bytes, and the hook warns.
    base, claude, tree = fresh(["rules/x.md"])

    def julia_env_and_an_edit(apply):
        (tree / "rules" / "x.md").write_text("an edit made while the apply runs\n")
        return 0

    with mock.patch.object(install, "install_julia_env", julia_env_and_an_edit):
        code, text = inproc(base, None, apply=True)
    warning = hook.check(str(base / "home")) or ""
    case(lambda: code == 0 and (claude / "rules" / "x.md").read_text() != (tree / "rules" / "x.md").read_text()
         and "behind its sources" in warning,
         f"a source edited after the plan is read, while --apply runs, leaves a stamp that the hook warns on: "
         f"{code}, {warning[:80]!r}")

    # The stamp names each source of this repository below the profile's `harness` path, whatever
    # checkout runs the apply: a second checkout with the same sources finds the stamp identical and
    # writes the same bytes, and the hook reads the profile's checkout. The scratch profile names this one.
    other = tmp / "checkout-2"
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, env=git_env).stdout
    for rel in filter(None, listed.split("\0")):
        if (REPO / rel).is_file():
            (other / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, other / rel)
    base, claude, tree = fresh(["rules/x.md"])
    code, text = run(base, "--apply")
    first = (claude / install.STAMP).read_bytes() if code == 0 else b""

    def run_other(*argv):
        p = subprocess.run([sys.executable, str(other / "bin" / "harness"), "--profile", str(base / "profile.toml"),
                            "--models", str(REPO / "examples" / "models.toml"), "install", *argv],
                           capture_output=True, text=True, env=scratch.env(base), cwd=base, timeout=60)
        return p.returncode, p.stdout + p.stderr

    dry, text2 = run_other()
    applied, text3 = run_other("--apply")
    second = (claude / install.STAMP).read_bytes() if (claude / install.STAMP).is_file() else b""
    named = [s[0] for s in json.loads(second)["sources"]] if second else []
    warning = hook.check(str(base / "home"))
    case(lambda: code == 0 and stamp_line.findall(text2) == ["already"] and applied == 0 and second == first
         and named == [s[0] for s in sources[:-1]] + [str(tree)] and warning is None,
         f"a dry run and an --apply from a second checkout find the stamp identical, and it names the profile's "
         f"checkout: {code}, {dry}, {applied}, {stamp_line.findall(text2)}, {named[:1]}, {warning!r}, {tail(text3)}")

    # In the adapter's plan: the profile's `harness` path names the repository's sources; with no
    # `harness` key the running checkout does; a value that is not an absolute path exits 2.
    def planned_stamp(value):
        """The source directories of the planned stamp with the profile's `harness` set to `value`,
        or with no such key for None, or the message of a refusal."""
        prof = {k: v for k, v in render_profile.load(base / "profile.toml").items() if k != "harness"}
        if value is not None:
            prof["harness"] = value
        ctx = argparse.Namespace(profile=prof, models=REPO / "examples" / "models.toml",
                                 args=argparse.Namespace(profile=str(base / "profile.toml")))
        try:
            with mock.patch.dict(os.environ, HOME=str(base / "home")), contextlib.redirect_stdout(io.StringIO()):
                files = this.plan(ctx).files
        except HarnessError as e:
            return str(e)
        return [s[0] for s in json.loads(next(f[1] for f in files if f[0].name == install.STAMP))["sources"]]

    repository = [str(REPO / d) for d in NEUTRAL] + [str(CLAUDE_ADAPTER), str(REPO / "hooks")]
    elsewhere = ["/elsewhere/Harness/" + d for d in NEUTRAL] + ["/elsewhere/Harness/adapters/claude",
                                                               "/elsewhere/Harness/hooks"]
    for value, expected in [("/elsewhere/Harness", elsewhere + [str(tree)]), ("/elsewhere/Harness/", elsewhere + [str(tree)]),
                            (None, repository + [str(tree)])]:
        got = planned_stamp(value)
        case(lambda: got == expected,
             f"the planned stamp with harness = {value!r} names the sources {got if isinstance(got, str) else got[:1]}")
    for value in ["relative/Harness", ["/elsewhere/Harness"], ""]:
        got = planned_stamp(value)
        case(lambda: isinstance(got, str) and got.startswith("harness: ") and "absolute path" in got,
             f"a profile with harness = {value!r} exits 2 and names the key: {got if isinstance(got, str) else got[:1]}")

    # Every installed path, the stamp included, is an `Edit` deny of the settings template, and the
    # paths the desktop app and the sessions write below ~/.claude stay writable.
    def edit_rule(pattern):
        """The regular expression of an `Edit` rule's absolute path: `**` any path, `*` one name."""
        parts = re.split(r"(\*\*/?|\*)", pattern)
        return re.compile("".join(".*" if p.startswith("**") else "[^/]*" if p == "*" else re.escape(p)
                                  for p in parts) + r"\Z")

    proposal = json.loads(render_profile.render_file(REPO / "settings" / "settings.proposal.json", profile))
    denies = [edit_rule(r[len("Edit("):-1]) for r in proposal["permissions"]["deny"] if r.startswith("Edit(")]
    root = "/" + profile["home"] + "/.claude/"
    open_paths = ["skills/synced/s/SKILL.md", f"projects/{profile['memory_project']}/memory/m.md", "plans/p.md",
                  "workflows/w.md", "skills/.claude/.cc-writes/x", "history.jsonl"]
    for rel in planned + [install.STAMP]:
        case(lambda: any(d.match(root + rel) for d in denies), f"~/.claude/{rel} is an Edit deny of the settings template")
    for rel in open_paths:
        case(lambda: not any(d.match(root + rel) for d in denies),
             f"~/.claude/{rel} is not an Edit deny of the settings template")
