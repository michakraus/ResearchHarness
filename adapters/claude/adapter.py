"""The adapter of Claude Code: its layer of `harness install`, the settings and the trust.

THE LAYER. `harness install` installs into ~/.claude/:

  agents/, skills/, rules/,
  instructions/, commands/ **      -> ~/.claude/**          (the same relative path)
  adapters/claude/**               -> ~/.claude/**          (the path relative to adapters/claude/)
  hooks/*                          -> ~/.claude/hooks/      (not probe.py, the hooks' own cases)
  the tree instructions, **        -> ~/.claude/**          (the same relative path; not README.md)
  the stamp                        -> ~/.claude/.harness-install.json

The Claude Code layer has these sources: the five neutral directories agents/, skills/, rules/,
instructions/ and commands/, adapters/claude/ and hooks/ in this repository, and the tree
instructions, the private directory that the profile key `tree_agents` names. Each neutral
directory installs at its own path below ~/.claude/, adapters/claude/ at the top of it, and the
tree instructions mirror the layout of ~/.claude/. The code of this adapter, adapter.py, and
fixtures/ of adapters/claude/ are not sources. A file is copied byte for byte, unless
CLAUDE_TEMPLATES lists its installed path; a template is rendered with the profile. An agent of
agents/ and a SKILL.md of skills/ are copied with two values rewritten in place (`render_source`):
the tier of `model:` becomes its Claude Code model from the [claude] table of models.toml
(`load_models`), and each `tools:` item its Claude Code name from TOOLS. A hook keeps
its source's mode, and every other file is installed 0644. A name that starts with `.`, and
__pycache__, is not a source. A file below agents/ or hooks/ in the tree instructions is not
installed: agents and hooks install from this repository only, so each such file is a SKIP line,
not counted as a change. Before anything is written, it exits 2 on a missing `tree_agents` key, on a
value that is not the absolute path of a directory, on a source that holds the Claude Code
settings, a symlink, an entry that is neither a file nor a directory, or a directory or file
that cannot be read, on a file of adapters/claude/ below a directory that a neutral directory or
hooks/ installs, on a path that two sources hold (compared with case and Unicode form
folded, on every platform, as the default macOS volume compares them), on an installed path, or
a directory above one, that is a symlink, and on an installed path that is not a readable file
below directories. An installed file with no source, below a top-level directory that the layer
writes into, is reported as EXTRA with its removal command; skills/synced/ and the hidden names
are not searched, and a directory there that cannot be read exits 2, before anything is
written. It writes neither the Claude Code settings nor ~/.claude.json, which it does not read
either; when `harness settings install` would change the settings, or cannot compare them, it
warns. After the layer, it writes the stamp: the sources and the digest over their files,
which the `SessionStart` hook hooks/install-drift.py computes again at each session start and
compares, so that a session warns when the installation is behind the sources. The digest is that
hook's own function, over the paths, the modes and the source bytes of the plan that the apply
installs, before `render_source` rewrites an agent or a skill, not a commit, so an uncommitted
edit that the apply installed counts, and a source edited while the apply runs is drift; an edit
of the [claude] table is no drift. A stamp that differs is a change like any installed file.

THE TRUST. `harness trust [--apply]` marks the research root and every git repository under it as
trusted in `~/.claude.json`. Claude Code keys workspace trust on the git repository root, and a
trusted parent folder does not cover a git repository nested inside it, so each repository raises
its own trust dialog. A worktree uses its main checkout's trust, so `.worktrees/` needs no entry.
No setting pre-trusts a tree; the documented route is
`projects["<root>"].hasTrustDialogAccepted = true`. The user runs it: a session cannot read or
write `~/.claude.json`. Run it after a clone; a new repository is untrusted until then. A running
Claude Code writes the file too, so run the dry run once more after `--apply`, and if keys are
missing again, quit the app and apply again.

THE SETTINGS. Measure the permission-prompt surface of ~/.claude/settings.json against real
traffic.

The question every settings round has to answer is "how many prompts does this actually
cost, and which commands are they" — and until now that was counted by hand, at least
seven times. This module is the instrument.

It reads the session transcripts under ~/.claude/projects/, splits every Bash command
into the segments the permission matcher evaluates, and classifies each one exactly as
the harness does: deny, then ask, then allow, then the sandbox auto-allow.

    harness settings surface [--settings F] [--days N] [--head N]
    harness settings compare OLD NEW [--days N]
    harness settings selftest
    harness settings twins [--settings F] [--list allow|ask|deny]
    harness settings domains [--settings F] [--emit]
    harness settings install [--proposal F] [--settings F] [--apply]

The proposal is a template: `{home}`, `{org}` and the other placeholders take their values
from the private profile (`harness --profile F`). Every command renders a file that holds a
placeholder before it reads it.

`twins` emits the `git -C * <sub>` patterns for a `git` rule set. `-C` precedes the
subcommand, so `Bash(git status *)` never matches `git -C /path status`; the twin has to
go in the same list as its plain form or the flag changes a verdict.

`domains` holds the one invariant across the file's two domain lists: every host granted
to the WebFetch tool must also be reachable by a shell subprocess, or a script that
retrieves what a session can read is blocked by the proxy with no rule saying so. It
checks by default and exits non-zero on a gap; `--emit` prints the block to install. Two
hand-maintained copies of one list is this directory's oldest failure mode.

`install --apply` merges the three sections a round owns -- permissions, hooks, sandbox --
onto the live file, and its dry run shows what such a merge would change. It exists because the
app rewrites settings.json on every UI model or effort change, so a `cp` of the proposal
reverts whatever was set in the UI since the proposal was last touched. Measured twice in
opposite directions on 2026-09-05.

Caveats the numbers rest on, all measured 2026-09-05:

  * The matcher expands nothing — no variables, no ~, no symlinks. `$TMPDIR/x` and
    `/tmp/claude-<pid>/x` are different strings and need different patterns.
  * `autoAllowBashIfSandboxed` is on, so a segment matching no rule is auto-approved
    unless it is led by one of the sandbox-excluded commands, which fall through to
    ordinary handling and therefore prompt. That set is read from the settings file
    being analysed rather than hardcoded here — it was hardcoded as (git, gh, ps) until
    2026-09-08, and went stale the moment `glab` joined it.
  * An `ask` prompts in `default` mode but routes to the auto-mode classifier in `auto`.
    This script counts the gate, not what a classifier did with it.
  * `rule_matches` copies Claude Code 2.1.282's own Bash matcher, read from the binary on
    2026-09-26, because `fnmatch` differs from it: a trailing `:*` is a prefix rule, not a
    glob; `[`, `]` and `?` are literal; a lone trailing ` *` also matches the bare
    command. Run `selftest` after a Claude Code update. Whether the Bash path collapses
    whitespace or ignores case is not established; this models neither.
"""

import argparse
import collections
import contextlib
import functools
import io
import json
import os
import pathlib
import re
import stat
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from unittest import mock

from harness import REPO, HarnessError, changing, frontends, frontmatter, install, outcome
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
# The installed paths that no source may hold: the Claude Code settings, which
# `harness settings install` owns.
CLAUDE_SETTINGS = frozenset({"settings.json", "settings.local.json"})
# The Claude Code name of each neutral tool of frontmatter.TOOLS; the Kaimon tool
# `mcp/kaimon/<tool>` is MCP_PREFIX followed by `<tool>`.
TOOLS = {"read": "Read", "edit": "Edit", "write": "Write", "grep": "Grep", "glob": "Glob", "shell": "Bash",
         "agent": "Agent", "web_search": "WebSearch", "web_fetch": "WebFetch"}
MCP_PREFIX = "mcp__kaimon__"
# A model of [claude], which render_source writes as it is into `model:`: a plain YAML scalar
# that reads as this string, and no word of YAML_WORDS, which YAML reads as a boolean or null.
MODEL = re.compile(r"[A-Za-z][A-Za-z0-9._\[\]-]*")
YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "y", "n", "null"}

CONFIG = os.path.expanduser("~/.claude.json")
SKIP = {".git", ".worktrees", "node_modules"}

PROJECTS = pathlib.Path.home() / ".claude" / "projects"
LIVE = pathlib.Path.home() / ".claude" / "settings.json"
PROPOSAL = REPO / "settings" / "settings.proposal.json"
PROFILE = None  # `harness --profile`; None lets the profile module choose


def read_settings(path):
    """A settings file parsed, and rendered with the profile when it holds a placeholder.

    The proposal is a template (`{home}`, `{org}`, …); the live file is its render. Every
    command reads through here, so a proposal and a live file compare as the same thing.
    """
    try:
        text = pathlib.Path(path).read_text()
    except FileNotFoundError as e:
        raise HarnessError(f"no settings file at {path}") from e
    except OSError as e:
        raise HarnessError(f"cannot read {path}: {e.strerror}") from e
    cfg = json.loads(text)
    if render_profile.PLACEHOLDER.search(text):
        cfg = render_profile.render_data(cfg, render_profile.load(PROFILE))
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
    """The regex Claude Code builds for a Bash wildcard rule (`q4` in 2.1.282)."""
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
    """Whether a pattern ends in an unescaped `*` (`mzn` in 2.1.282)."""
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
    """The matcher against the recorded harness cases: (number of cases, number wrong)."""
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


# Suffixes under which the registrable domain is three labels, not two. Only the ones
# this file's own entries need; a general public-suffix list would be a dependency.
MULTI_LABEL_SUFFIXES = ("ac.uk", "co.uk", "org.uk", "gov.uk")


def registrable(host):
    """The registrable domain of a host — nature.com for www.nature.com, core.ac.uk for itself."""
    labels = host.split(".")
    n = 3 if host.endswith(MULTI_LABEL_SUFFIXES) else 2
    return ".".join(labels[-n:]) if len(labels) >= n else host


def webfetch_domains(path):
    """The domains of the WebFetch(domain:…) grants in a settings file, in file order."""
    cfg = read_settings(path)
    out = []
    for rule in cfg.get("permissions", {}).get("allow", []):
        m = re.match(r"^WebFetch\(domain:(.*)\)$", rule)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def mirror_domains(path):
    """What sandbox.network.allowedDomains must contain for the WebFetch grants to work.

    The two lists do not match the same way. WebFetch is given a domain; the sandbox list
    is matched by the proxy against the hostname a request actually goes to, so a bare
    `nature.com` there does not cover the `www.nature.com` the traffic uses. Hence: an
    entry that *is* its own registrable domain is a site and emits the pair `X` and `*.X`
    — the idiom the file already uses for `pkg.julialang.org`; an entry below its
    registrable domain is one exact host and emits only itself.
    """
    out = []
    for host in webfetch_domains(path):
        out.append(host)
        if host == registrable(host):
            out.append("*." + host)
    return out


def cmd_domains(args):
    required = mirror_domains(args.settings)
    cfg = read_settings(args.settings)
    current = cfg.get("sandbox", {}).get("network", {}).get("allowedDomains", [])

    if args.emit:
        # Entries that no WebFetch grant implies are the infrastructure hosts — package
        # registries, the code host. They are not derivable and are kept at the head.
        infra = [d for d in current if d not in required]
        block = infra + [d for d in required if d not in infra]
        print(json.dumps(block, indent=8)[1:-1].rstrip())
        return 0

    missing = [d for d in required if d not in current]
    if missing:
        print(f"  {len(missing)} WebFetch domains unreachable from a shell subprocess, {args.settings}:")
        for d in missing:
            print(f"    {d}")
        return 1
    print(f"  the sandbox allowlist covers all {len(webfetch_domains(args.settings))} "
          f"WebFetch domains ({len(current)} entries, {len(current) - len(required)} infrastructure)")
    return 0


# The sections a settings round owns. Everything else in the live file belongs to the app
# — model, modelSettings, env — and a round must leave it exactly as it found it.
OWNED = ("permissions", "hooks", "sandbox")


def indent_of(path):
    """The live file's own indentation, so a merge does not reformat it."""
    for line in pathlib.Path(path).read_text().splitlines()[1:]:
        stripped = line.lstrip(" ")
        if stripped and stripped != line:
            return len(line) - len(stripped)
    return 2


def owned_diff(live_path, proposal_path):
    import difflib

    live = read_settings(live_path)
    proposal = read_settings(proposal_path)
    a = json.dumps({k: live.get(k) for k in OWNED}, indent=2, sort_keys=True).splitlines()
    b = json.dumps({k: proposal.get(k) for k in OWNED}, indent=2, sort_keys=True).splitlines()
    return list(difflib.unified_diff(a, b, "live", "proposal", lineterm="")), live, proposal


def stray_grants():
    """Permission rules outside the user file, which a round neither proposes nor sees.

    "Yes, don't ask again" writes its grant to the settings.local.json of the working
    directory. Such a grant adds to every session started there and can undo a round's
    narrowing: on 2026-10-03 `Bash(gh issue *)` in ~/Research/.claude/settings.local.json
    let `gh issue comment -R <any owner>` run after round fifty-two had narrowed it.
    """
    home = pathlib.Path.home()
    paths = [home / ".claude" / "settings.local.json"]
    for root in (home / "Research", *sorted((home / "Research").glob("*"))):
        paths += [root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]
    found = []
    for path in paths:
        if path.is_file():
            permissions = json.loads(path.read_text()).get("permissions", {})
            for kind in ("allow", "ask", "deny"):
                found += [(path, kind, rule) for rule in permissions.get(kind, [])]
    return found


def report_stray():
    found = stray_grants()
    if found:
        print(f"\n  WARNING: {len(found)} permission rule(s) outside the user file — fold them into the")
        print("  proposal or delete them; this tool's other measurements do not see them:")
        for path, kind, rule in found:
            print(f"    {path}  {kind}  {rule}")


def cmd_install(args):
    lines, live, proposal = owned_diff(args.settings, args.proposal)
    if not lines:
        print("  the owned sections are identical — nothing to install")
        report_stray()
        return 0
    if not args.apply:
        print("\n".join(lines))
        report_stray()
        return outcome(args, len(lines))
    preserved = [k for k in live if k not in OWNED]
    for key in OWNED:
        if key in proposal:
            live[key] = proposal[key]
        else:
            live.pop(key, None)
    # ensure_ascii=False, because this function promises to leave every key it does not own
    # exactly as the app left it. The default escapes each non-ASCII character, and round
    # twenty-four rewrote every em-dash inside `autoMode` as — — decoded values unchanged,
    # bytes not. A diff of an unowned key must stay empty.
    text = json.dumps(live, indent=indent_of(args.settings), ensure_ascii=False) + "\n"
    pathlib.Path(args.settings).write_text(text, encoding="utf-8")
    print(f"  installed {', '.join(OWNED)} into {args.settings}")
    print(f"  preserved untouched: {', '.join(preserved) or '(none)'}")
    print(f"  {sum(l.startswith('+') and not l.startswith('+++') for l in lines)} lines added, "
          f"{sum(l.startswith('-') and not l.startswith('---') for l in lines)} removed")
    print("  the live file is not tracked; commit the proposal in the harness repository")
    report_stray()
    return 0


def run(args):
    """Set the profile for `read_settings`, then run the settings sub-command."""
    global PROFILE
    PROFILE = args.profile
    return args.func(args)


def register(sub):
    register_settings(sub)
    changing(sub.add_parser("trust", help="trust the research root and every repository in it for Claude Code")
             ).set_defaults(run=cmd_trust)


def register_settings(sub):
    top = sub.add_parser("settings", help="measure, check and install the Claude Code settings")
    top.set_defaults(run=run)
    sub = top.add_subparsers(dest="cmd", metavar="<sub>", required=True)

    s = sub.add_parser("surface", help="prompt surface of one settings file")
    s.add_argument("--settings", default=str(LIVE))
    s.add_argument("--days", type=int, default=5)
    s.add_argument("--head", type=int, default=0)
    s.set_defaults(func=cmd_surface)

    c = sub.add_parser("compare", help="prompt surface of two settings files, side by side")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--days", type=int, default=5)
    c.set_defaults(func=cmd_compare)

    m = sub.add_parser("selftest", help="check the matcher against the recorded harness cases")
    m.set_defaults(func=cmd_selftest)

    t = sub.add_parser("twins", help="emit the git -C twins of a rule set")
    t.add_argument("--settings", default=str(LIVE))
    t.add_argument("--list", choices=("allow", "ask", "deny"))
    t.set_defaults(func=cmd_twins)

    d = sub.add_parser("domains", help="check, or emit, the sandbox mirror of the WebFetch grants")
    d.add_argument("--settings", default=str(LIVE))
    d.add_argument("--emit", action="store_true", help="print the allowedDomains block instead of checking")
    d.set_defaults(func=cmd_domains)

    p = changing(sub.add_parser("install", help="merge the proposal's owned sections onto the live file"))
    p.add_argument("--proposal", default=str(PROPOSAL))
    p.add_argument("--settings", default=str(LIVE))
    p.set_defaults(func=cmd_install)


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
            config = json.load(f)
    except OSError as e:
        raise HarnessError(f"cannot read {CONFIG}: {e.strerror} — run it outside a session") from e
    projects = config.setdefault("projects", {})
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


def claude_plan(profile, root, sources=None, templates=None):
    """[(installed path relative to `root`, bytes, mode)] of the Claude Code layer; `templates`
    defaults to CLAUDE_TEMPLATES. A file below a top-level name that its source does not install,
    as the source's third element names it, is not planned; a file below a skipped top-level
    directory of its source, as the source's fourth element names it (compared as `fold` does), is
    printed as a SKIP line and not planned.

    Exits 2, through HarnessError and before anything is written, on a source that holds the
    Claude Code settings or a file that cannot be read, on a file of adapters/claude/ below a
    directory that a neutral directory or hooks/ installs, on a path that two sources hold, on an
    installed path, or a directory above one, that is a symlink, and on an installed path that is
    not a readable file below directories.
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
                raise HarnessError(f"{src}: ~/.claude/{dst} is the Claude Code settings, which "
                                   "`harness settings install` owns; no source of this install holds it")
            if install.fold(dst) in owner:
                raise HarnessError(f"~/.claude/{dst} has two sources, {owner[install.fold(dst)]} and {src}")
            owner[install.fold(dst)] = src
            try:
                data = render_profile.render_file(src, profile).encode() if dst in templates else src.read_bytes()
                mode = stat.S_IMODE(src.stat().st_mode) if dst.startswith("hooks/") else 0o644
            except (OSError, ValueError) as e:
                raise HarnessError(f"{src} cannot be read: {e}") from None
            plan.append((dst, data, mode))
    install.check_targets(root, "~/.claude", plan)
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


def settings_warning(root, profile_path):
    """The warnings, [(line, …)], when `harness settings install` would change the live settings,
    or when they cannot be compared; this verb does not write them."""
    live = root / "settings.json"
    if not live.is_file():
        return []
    # Parsed and rendered by the reader of `harness settings install` itself, so that a file it
    # cannot compare is the warning here and not a traceback.
    global PROFILE
    saved, PROFILE = PROFILE, profile_path
    try:
        if isinstance(read_settings(live), dict):
            problem, lines = None, owned_diff(live, PROPOSAL)[0]
        else:
            problem = "it is not a JSON object"
    except (HarnessError, ValueError, KeyError, TypeError) as e:
        problem = f"{type(e).__name__}: {e}"
    finally:
        PROFILE = saved
    if problem:
        return [(f"{live} cannot be compared with the settings template: {problem}",
                 "`harness install` does not write it.")]
    if lines:
        return [(f"{live} differs from the settings template in the sections a round owns.",
                 "`harness settings install` would change it; `harness install` does not write it.")]
    return []


def load_models(path):
    """{tier: model} of the [claude] table of the models.toml at `path`: exactly the tiers of
    frontmatter.TIERS, each a model of MODEL that is not a word of YAML_WORDS, which YAML reads as
    that string; any other table exits 2 (profile.tier_table)."""
    models = render_profile.tier_table(path, "claude", "Claude Code")
    wrong = [t for t in frontmatter.TIERS if not MODEL.fullmatch(models[t]) or models[t].lower() in YAML_WORDS]
    if wrong:
        raise HarnessError(f"{path}: the tier {', '.join(wrong)} of [claude] is "
                           + ", ".join(repr(models[t]) for t in wrong) + ", which the install cannot write "
                           "as a plain YAML string: a model is a letter, then letters, digits and . _ - [ ]")
    return models


def neutral_source(src):
    """Whether `src` is an agent of agents/ or a SKILL.md of skills/ in this repository, whose
    `model:` and `tools:` `render_source` rewrites."""
    return src.parent == neutral.AGENTS or (src.name == "SKILL.md" and src.parent.parent == neutral.SKILLS)


def render_source(src, data, models):
    """`data`, the bytes of the agent or skill at `src`, with the value of `model:` replaced by its
    model in `models`, load_models' table, and each `tools:` item by its name in TOOLS; every other
    byte as it is. A value outside the neutral vocabulary exits 2 (frontmatter.parse_file)."""
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
                lines[i] = "model:" + rest.replace(value, f'"{model}"' if value.startswith('"') else model, 1)
        elif key == "tools":
            tool = item.group(1).strip(" ")
            name = TOOLS[tool] if tool in TOOLS else MCP_PREFIX + tool.removeprefix(frontmatter.MCP)
            lines[i] = "  - " + item.group(1).replace(tool, name, 1)
    return "\n".join(lines).encode("utf-8")


def plan(ctx):
    """The Claude Code layer of `harness install`, as the docstring of this module says. Its
    `rules` are [(installed path, source, bytes)] of each planned file below rules/, for oh-my-pi."""
    root = pathlib.Path.home() / ".claude"
    models = load_models(ctx.models)
    layer_sources = claude_sources(ctx.profile)
    layer = claude_plan(ctx.profile, root, layer_sources)
    files = []
    for dst, data, mode in layer:
        src = source_of(layer_sources, dst)[0]
        files.append((root / dst, render_source(src, data, models) if neutral_source(src) else data, mode,
                      f"~/.claude/{dst}"))
    # The stamp goes after the layer, so that an apply that stops before its end leaves the old one.
    # It is over the source bytes of `layer`, which the hook reads again, not over the rendered ones.
    files.append((root / install.STAMP, install.stamp_bytes(layer_sources, layer), 0o644, f"~/.claude/{install.STAMP}"))
    extra = [f"\nEXTRA: {f} is installed and has no source here; the install leaves it.\n"
             f"       To remove it:  rm '{f}'" for f in claude_extras(root, layer)]
    rules = [(dst, source_of(layer_sources, dst)[0], data) for dst, data, _ in layer if dst.startswith("rules/")]
    return frontends.Plan(files=files, warnings=settings_warning(root, ctx.args.profile), extra=extra, rules=rules)


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
    # `model:` and the `tools:` items alone.
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
    case(lambda: sorted(TOOLS) == sorted(frontmatter.TOOLS),
         f"TOOLS maps exactly the neutral tools of frontmatter.TOOLS: {sorted(set(TOOLS) ^ set(frontmatter.TOOLS))}")
    base, claude, tree = fresh()
    code, text = run(base, "--apply")

    def changed_lines(src):
        """The lines in which the installed copy of `src` differs from it, as (source, installed)."""
        old = src.read_text().split("\n")
        new = (claude / src.relative_to(REPO)).read_text().split("\n")
        count = [("line count", len(old), len(new))] * (len(old) != len(new))
        return [(a, b) for a, b in zip(old, new) if a != b] + count

    names = set(TOOLS.values())
    wrong = {str(src.relative_to(REPO)): [(a, b) for a, b in changed_lines(src)
                                         if not (re.fullmatch(r"model: (large|medium|small)", a)
                                                 and b == f"model: {example[a[len('model: '):]]}")
                                         and not (re.fullmatch(r"  - [a-z_]+|  - mcp/kaimon/\w+", a)
                                                  and (b[4:] in names or b[4:].startswith(MCP_PREFIX)))]
             for src in neutral.listing()}
    def owed(src):
        """The number of lines that the render changes in `src`: its `model:` and its `tools:` items."""
        meta = frontmatter.parse_file(src).meta
        return ("model" in meta) + len(meta.get("tools", []))

    # Each `model:` and each `tools:` item of a source changes, so a source installed as it is fails.
    unchanged = [str(src.relative_to(REPO)) for src in neutral.listing() if len(changed_lines(src)) != owed(src)]
    case(lambda: code == 0 and len(wrong) > 25 and not any(wrong.values()) and not unchanged
         and any(s.name == "SKILL.md" and changed_lines(s) for s in neutral.listing()),
         f"every agent and skill is installed with its `model:` mapped by [claude] and its `tools:` items by TOOLS, "
         f"and every other byte as in its source: {code}, {[(k, v) for k, v in wrong.items() if v][:3]}, "
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
        *((f"the model {value} in [claude]", text0.replace('small = "haiku"\n', f'small = "{value}"\n', 1))
          for value in [r"haiku\npermissionMode: bypassPermissions", "a: b", "haiku #1", " haiku", "haiku ",
                        "[haiku]", r"hai\"ku", "null", "Yes", "1", "-haiku", "hai ku"]),
    ]:
        base, claude, tree = fresh(["rules/x.md"])
        models = base / "models.toml"
        models.write_text(models_text)
        code, text = run(base, "--apply", models=models)
        case(lambda: models_text != text0 and refused(code, text) and str(models) in text and "[claude]" in text
             and not (claude / "rules").exists() and not (base / "opencode" / "opencode.jsonc").exists(),
             f"a models.toml with {label} exits 2, names the file and [claude], and writes nothing: "
             f"{code}, {tail(text)}")

    # A model of [claude] that YAML reads as itself, a plain string, loads.
    for value in ["opus", "claude-opus-4-1", "claude-3.5-haiku", "opus[1m]", "inherit"]:
        models = tmp / "models-value.toml"
        models.write_text(text0.replace('small = "haiku"\n', f'small = "{value}"\n', 1))
        case(lambda: load_models(models)["small"] == value, f"the model {value!r} of [claude] loads")

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

    # settings.json and settings.local.json are not written, from any source and in any case.
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

    # settings.json is not written, and a change that `harness settings install` would make is a
    # warning; ~/.claude.json, unreadable here, is neither read nor written.
    base, claude, tree = fresh()
    (claude / "settings.json").write_text("{}\n")
    state = base / "home" / ".claude.json"
    state.write_text('{"state": 1}\n')
    state.chmod(0)
    code, text = run(base, "--apply")
    again, text2 = run(base)
    state.chmod(0o600)
    case(lambda: code == 0 and again == 0 and (claude / "settings.json").read_text() == "{}\n"
         and "harness settings install" in text2,
         f"settings.json is not written; its change is a warning, not counted: {code}, {again}, {tail(text2)}")
    case(lambda: code == 0 and state.read_text() == '{"state": 1}\n', "~/.claude.json is neither read nor written")
    profile = render_profile.load(base / "profile.toml")
    (claude / "settings.json").write_text(
        render_profile.render_file(REPO / "settings" / "settings.proposal.json", profile))
    code, text = run(base)
    case(lambda: code == 0 and "harness settings install" not in text,
         f"a settings.json equal to the template gives no warning: {code}, {tail(text)}")

    # A settings.json that cannot be compared is a warning; the run goes on to its count line.
    for label, data in [("not JSON", b"{\n"), ("not UTF-8", b'{"x": "\xff"}\n'), ("not an object", b"[]\n"),
                        ("JSON after a UTF-8 BOM", b"\xef\xbb\xbf{}\n"),
                        ("a template with a placeholder the profile does not define",b'{"env": {"X": "{no_such_key}"}}\n'),
                        ("a template with a list placeholder in a value", b'{"env": {"X": "{org}"}}\n'),
                        ("a template with a list placeholder in a key", b'{"{org}": 1}\n'),
                        ("unreadable, of mode 000", b"{}\n")]:
        base, claude, tree = fresh(["rules/x.md"])
        (claude / "settings.json").write_bytes(data)
        if label == "unreadable, of mode 000":
            (claude / "settings.json").chmod(0)
        code, text = run(base)
        applied, text2 = run(base, "--apply")
        (claude / "settings.json").chmod(0o644)
        case(lambda: code == 1 and applied == 0 and "Traceback" not in text + text2
             and all("cannot be compared" in t for t in (text, text2))
             and re.search(r"^\d+ change\(s\) made\.$", text2, re.M) is not None
             and (claude / "rules" / "x.md").is_file() and (claude / "settings.json").read_bytes() == data,
             f"a settings.json that is {label} is a warning, and the run reaches its count line: "
             f"{code}, {applied}, {tail(text)}")

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
        planned = {dst for dst, _, _ in claude_plan(render_profile.load(base / "profile.toml"), claude)}
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
        plan = claude_plan(profile, claude)
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
