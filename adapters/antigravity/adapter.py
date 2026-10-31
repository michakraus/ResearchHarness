"""The adapter of Antigravity: its permission layer, the guard hook, the CLI's permission
settings, the instructions, rules and skills, the agents and Kaimon. Antigravity has no subcommand
of its own.

`harness install` writes these files below ~/.gemini/, after the Claude Code layer is planned,
whose guard package, install-drift.py, instructions, rules and skills it copies. With no
~/.gemini/, Antigravity's directory, the plan holds no file and one warning:

  config/hooks.json              one named hook, `harness-guards`, with one `SessionStart`
                                 handler, which runs config/hooks/install-drift.py and gives its
                                 warning as an `injectSteps` system message, `{}` when the install
                                 is current, and a warning that names the script when it exits
                                 with an error or its output is not a JSON object with a text
                                 `systemMessage` (TRANSLATE); and one `PreToolUse` group, matcher
                                 `*`, which runs config/hooks/guard `--from antigravity`; each by
                                 its absolute path, on the Python environment's interpreter, with
                                 a timeout of 15 s (render_hooks). The matcher names no tool, so
                                 no tool is missed, and the guard decides by the name of the tool
  config/hooks/guard/            the Claude Code layer's copy of the guard package, each file
                                 byte for byte with its mode: its Antigravity table runs the checks
                                 and the path list on every tool call, failing closed
  config/hooks/install-drift.py  the Claude Code layer's copy, with its mode; it checks the stamp
                                 of ~/.claude/ alone, and this layer writes no stamp of its own
  config/GEMINI.md               adapters/antigravity/ANTIGRAVITY-DELTA.md, byte for byte:
                                 Antigravity's global instruction file, in place of
                                 ~/.claude/CLAUDE.md
  config/rules/<name>.md         RTK.md and each `.md` file of instructions/, not of a
                                 subdirectory, as the Claude Code layer installs them, each a rule
                                 with `trigger: always_on` (always_on); and each rule of rules/,
                                 not of a subdirectory, that the Claude Code layer installs,
                                 its `paths` as `trigger: glob` and `globs` (render_rule).
                                 Antigravity does not load a glob rule of this global directory,
                                 so the delta lists each rule with its scope, and the model reads
                                 it
  config/skills/<name>/<file>    each file of the Claude Code layer's skills, with its mode; a
                                 SKILL.md without `model:` (render_skill)
  config/agents/<name>.md        each agent of agents/, its `model` the word that the table
                                 [antigravity] of models.toml gives its tier, its tools mapped by
                                 TOOLS, and an "Under Antigravity" section from
                                 adapters/antigravity/UNDER-ANTIGRAVITY.md (render_agent); the
                                 table is checked first (load_models). A council of models.toml
                                 is one warning for each agent it names, and writes no seat
                                 (council_warnings)
  config/mcp_config.json         the file as it is with `mcpServers.kaimon` set, the token of
                                 ~/.config/kaimon/auth-token written out, every other server
                                 and key kept, mode 600 and no backup (render_mcp, merge_mcp); a
                                 file that is not a JSON object exits 2 before any write. With no
                                 token, the file is neither read nor written, and one warning says
                                 so

Each .md file but GEMINI.md names Antigravity's copies, not Claude Code's, RTK.md and the files of
instructions/ in config/rules/ (relocate). A path of two sources, compared as `install.fold`
compares names, exits 2; so does an instruction file or a rule that holds an include,
`@[label](path)`, or of FILE_CAP bytes or more, and a global file and always-on rules of BUDGET
bytes or more together (check_sizes): Antigravity would cut the file, or demote rules to path
pointers. An installed
file with no source below config/rules/, config/skills/, config/hooks/ and config/agents/ is
EXTRA, with its removal command (extras); every other file below ~/.gemini/, Antigravity's own
antigravity/, the app's per-project grants in config/projects/ and plugins/ among them, is neither
listed nor touched. The other files:

  config/guard-paths.json        the guard's path list (guard_paths): under `deny` that of
                                 adapters/opencode/plugins/guard-paths.json, MCP_CONFIG and the
                                 files of this layer, LAYER; under `edit` and `ask` the template's
                                 Edit denies and asks, then the same rules for this layer's copies
                                 of the files that frontends.SHARED_ROOTS names (relocate), and
                                 under `edit` the global instruction files that Antigravity loads,
                                 config/GEMINI.md, config/AGENTS.md and ~/.gemini/GEMINI.md, the
                                 installed agents, config/agents/, and the app's grants,
                                 config/config.json (APP_CONFIG); the guard applies `edit`
                                 and `ask` to the tools that write; under `bash_deny` and
                                 `bash_ask` the bodies of its Bash denies and asks, which the guard
                                 applies to each segment of a command
  antigravity-cli/settings.json  the keys `permissions`, `toolPermission` and
                                 `enableTerminalSandbox` of the CLI's settings, set in the file
                                 as it is, every other key kept, after a backup (merge_settings);
                                 a file that is not a regular file or not a JSON object exits 2
                                 before any write
  config/config.json             the desktop app's settings: each rule added once to its list,
                                 `allow`, `deny` or `ask`, of `userSettings.globalPermissionGrants`,
                                 after the entries there, every other key and entry kept in its
                                 place, after a backup (merge_grants); a file that is not a regular
                                 file or not a JSON object, or a `userSettings`,
                                 `globalPermissionGrants` or list there of the wrong type, exits 2
                                 before any write

THE POSTURE is Claude Code's: the terminal sandbox on, and `toolPermission` `proceed-in-sandbox`,
the counterpart of `autoAllowBashIfSandboxed`. `allowNonWorkspaceAccess` is not written, so it
keeps its default, `false`. The desktop app reads neither `permissions` nor `toolPermission` from
the CLI's file.

THE RULES are the settings template's, rendered with the profile and the network lists as Claude
Code's settings are (render_permissions); each stays in its list, `deny`, `ask` or `allow`, in the
template's order:

  Bash(x *)              command(x): a prefix matches word by word
  Bash(…) any other form command(regex:^…$), each `*` as `.*` and the rest literal, a trailing
                         ` *` as no text too, which matches the lines that the entry matches; in
                         `allow`, a `*` as SEGMENT_TEXT, so that the rule matches no line that
                         crosses a segment
  Read(p), Edit(p)       read_file(p), write_file(p): a leading `//` as `/`, and a trailing `/**`
                         removed, because a path covers its subtree. A path with any other glob,
                         `**/X` among them, has no form in Antigravity and is dropped
  WebFetch(domain:X)     read_url(X), for each allow host of settings/network.toml and its overlay
  mcp__kaimon__<tool>    mcp(kaimon/<tool>), after the other rules of its list; in `deny`, after
                         the denies below
  sandbox.excludedCommands
                         command(<first word>) in `allow`, after the Kaimon rules, unless the
                         list holds it: Claude Code runs these commands outside its sandbox. No
                         unsandboxed(…) rule is written: the CLI checks a command(…) rule as
                         unsandboxed(…)
  sandbox.filesystem.denyWrite
                         for an entry at or below the research root, read_file(p) in `deny`,
                         after every other deny, unless the list holds it, `~` the home
                         directory (deny_write): a `write_file` deny hides far more of the app's
                         sandbox than its path. An entry outside the root renders nothing: the
                         app's sandbox mounts only the workspace. An entry `<prefix>/**/<rest>`
                         is one rule for each clone (clones) at or below the prefix; any other
                         wildcard entry whose directory before the wildcard is the root, above
                         it or below it, is a warning and no rule. One warning names the number
                         of clones covered

MCP_CONFIG is a `read_file` deny after the template's, and LAYER and MCP_CONFIG are `write_file`
denies after that. The app needs one grant per Kaimon tool, and no wildcard covers them, so each
Kaimon tool of the template is its own rule. Every other entry is dropped, with its reason. A
dropped `Read(**/X)` deny is still in the `deny` list of the guard, and a dropped Edit entry in its
`edit` or `ask` list. A command with `$(…)` or a backtick matches only a full-line rule in
Antigravity, so a `deny` does not reach it; the guard applies the Bash denies and asks to each
segment of the line, the bodies of `$(…)`, backticks and `( … )` included, and is the boundary.
The desktop app reads no `permissions`; it keeps its grants in config/config.json, which gets the
same rules.
"""

import argparse
import contextlib
import importlib
import io
import json
import os
import pathlib
import random
import re
import shlex
import stat
import sys
import tempfile
import types
from collections.abc import Callable
from typing import Any, cast

from harness import REPO, HarnessError, frontends, frontmatter, fsutil, install, sources, units
from harness import jsonio, ownedjson
from harness import profile as profile_module
from harness.jsonio import JsonValue
from harness.githooks import research_root

NAME = "antigravity"
TEMPLATES = []
RESTART = "Restart Antigravity and agy: their hooks and permission settings changed."

SOURCE = REPO / "adapters" / "antigravity"
GUARD_PATHS = REPO / "adapters" / "opencode" / "plugins" / "guard-paths.json"
HOOK = "harness-guards"
HOOK_TIMEOUT = 15
# The guard package of the Claude Code layer, by the label of its files in that layer's plan.
GUARD_PACKAGE = "~/.claude/hooks/guard/"
# The MCP configuration of Antigravity, which holds the Kaimon token in plain text.
MCP_CONFIG = "{home}/.gemini/config/mcp_config.json"
# The files of this layer, which an agent that rewrites them could use to switch off its guard.
LAYER = (
    "{home}/.gemini/config/hooks.json",
    "{home}/.gemini/config/hooks/**",
    "{home}/.gemini/config/guard-paths.json",
    "{home}/.gemini/antigravity-cli/settings.json",
)
SETTINGS = REPO / "settings" / "settings.proposal.json"
POSTURE = {"toolPermission": "proceed-in-sandbox", "enableTerminalSandbox": True}
# The lists of the template's `permissions` and of Antigravity's, in the order the rules render.
LISTS = ("deny", "ask", "allow")
REGEX_SPECIAL = re.compile(r"[\\.^$|?*+()\[\]{}]")
# The text of a `*` in an `allow` regex rule: no character that ends a segment, opens a
# substitution or redirects, so that an allow rule never matches across a segment.
SEGMENT_TEXT = r"[^;&|\n`$()<>]*"
DELTA = SOURCE / "ANTIGRAVITY-DELTA.md"
# Antigravity cuts an instruction file or a rule at 24,000 bytes, its includes expanded, and the
# always-on and global rules share 20,000 tokens, counted here at 4 bytes a token.
FILE_CAP = 24000
BUDGET = 20000 * 4
# The first lines of a rule that render_rule gives `trigger: glob`.
GLOB_RULE = b"---\ntrigger: glob\n"
# Antigravity's include of another file, `@[label](path)`.
INCLUDE = re.compile(rb"@\[[^\]\n]*\]\(")
# The `SessionStart` handler: it runs install-drift.py, its path the first argument, and turns its
# JSON, Claude Code's form, into Antigravity's: the `systemMessage` as one `injectSteps` system
# message, and no output or an empty `systemMessage` as `{}`. An exit other than 0, or output that
# is not a JSON object with a text `systemMessage`, is a warning that names the script, so that a
# check that did not run never reads as a current install.
TRANSLATE = """import json, subprocess, sys
path = sys.argv[1]
try:
    p = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr.strip()[-300:]}")
    t = p.stdout.strip()
    m = json.loads(t)["systemMessage"] if t else None
    if t and not isinstance(m, str):
        raise TypeError("its systemMessage is no text")
except Exception as e:
    m = f"{path} failed ({type(e).__name__}: {e}); the installation is not checked."
print(json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": m}}]} if m else {}))
"""
FIXTURES = SOURCE / "fixtures"
# The rules of the "Under Antigravity" section of an agent, one `## <mechanism>` section each.
UNDER = SOURCE / "UNDER-ANTIGRAVITY.md"
# The values of an agent's `model`: Antigravity's tiers. `inherit` runs a subagent on the session
# model.
WORDS = ("inherit", "flash", "flash_lite", "pro")
# The Antigravity names of each neutral tool of frontmatter.TOOLS: the family of a subagent's
# default set, so that an agent keeps the tools that Antigravity gives a subagent by itself. A
# `tools:` list only restricts an agent. Kaimon is reached through `call_mcp_tool`, which every
# agent has and `tools:` refuses, so a Kaimon tool gives `inheritMcp: true` and no name.
TOOLS = {
    "read": ("view_file", "list_dir"),
    "edit": ("replace_file_content",),
    "write": ("write_to_file",),
    "grep": ("grep_search",),
    "glob": ("find_by_name",),
    "shell": ("run_command",),
    "agent": ("invoke_subagent",),
    "web_search": ("search_web",),
    "web_fetch": ("read_url_content",),
}
KAIMON_URL = "http://127.0.0.1:2828/"
# Kaimon's bearer token, below the home directory. Antigravity expands no shell form in a header,
# so mcp_config.json holds the token itself.
KAIMON_TOKEN = pathlib.Path(".config", "kaimon", "auth-token")
# The installed agents, which an agent that rewrites them could use to widen its own tools.
AGENTS = "{home}/.gemini/config/agents/**"
# The desktop app's settings, whose userSettings.globalPermissionGrants holds its grants, in the
# lists of LISTS and in the rule form of the CLI.
APP_CONFIG = "{home}/.gemini/config/config.json"
# A Kaimon tool of the settings template, `mcp__kaimon__<tool>`.
KAIMON_TOOL = re.compile(r"mcp__kaimon__(\w+)")


def gemini_dir():
    """Antigravity's directory, ~/.gemini."""
    return pathlib.Path.home() / ".gemini"


def render(path, profile):
    """The path template `path` rendered with `profile`."""
    return profile_module.render_line(path, profile)


def render_hooks(root: pathlib.Path, python: str | None = None) -> str:
    """The text of hooks.json for Antigravity's directory `root`: the hook HOOK, which runs
    install-drift.py at the start of a session, its warning translated by TRANSLATE, and the guard
    package with `--from antigravity` on every tool call, each by its absolute path, so that it runs
    from any directory, and each on
    the interpreter `python`, by default the Python environment's (`install.python_interpreter`),
    not on the `python3` of the `PATH`. Each path is one shell word (`shlex.quote`)."""
    hooks = root / "config" / "hooks"
    python = shlex.quote(install.python_interpreter() if python is None else python)

    def handler(command):
        return {"type": "command", "command": command, "timeout": HOOK_TIMEOUT}

    start = python + " -c " + shlex.quote(TRANSLATE) + " " + shlex.quote(str(hooks / "install-drift.py"))
    return (
        json.dumps(
            {
                HOOK: {
                    "SessionStart": [handler(start)],
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                handler(f"{python} {shlex.quote(str(hooks / 'guard'))} --from antigravity")
                            ],
                        }
                    ],
                }
            },
            indent=2,
        )
        + "\n"
    )


def relocate(data, root):
    """`data` with each path below ~/.claude/ that this layer copies rewritten to its copy below
    `root`, Antigravity's config directory in its home form: ~/.claude/RTK.md and the files of
    ~/.claude/instructions/ to rules/, where the always-on files load, and the other roots of
    frontends.SHARED_ROOTS to the same path (frontends.relocate)."""
    data = data.replace(b"~/.claude/RTK.md", f"{root}/rules/RTK.md".encode())
    data = data.replace(b"~/.claude/instructions/", f"{root}/rules/".encode())
    return frontends.relocate(data, root)


def always_on(data):
    """The always-on Antigravity rule of the instruction text `data`."""
    return b"---\ntrigger: always_on\n---\n\n" + data


def render_rule(src, data):
    """The Antigravity rule of `data`, the Claude Code rule from the source `src`: `trigger: glob`
    and its `paths` as `globs:`, joined by `, `, when it has `paths`, else `trigger: always_on`, as
    Claude Code loads a rule with no `paths` at the start; then its `description` and its body.
    oh-my-pi's render_rule reads the frontmatter, and exits 2 on one outside its grammar; it keeps
    the source's closing line, `---` or `---\\r`."""
    lines = frontends.adapter("omp").render_rule(src, data).split(b"\n")
    end = next(i for i, line in enumerate(lines) if i and line in (b"---", b"---\r"))
    fields = dict(line.split(b": ", 1) for line in lines[1:end])
    if b"globs" in fields:
        globs = ", ".join(json_value(fields[b"globs"].decode(), "globs"))
        trigger = [b"trigger: glob", b"globs: " + json.dumps(globs, ensure_ascii=False).encode()]
    else:
        trigger = [b"trigger: always_on"]
    return b"\n".join([b"---", *trigger, b"description: " + fields[b"description"], *lines[end:]])


def render_skill(data):
    """The SKILL.md `data` without the `model:` lines of its frontmatter: a skill runs on the
    session model. A text with no frontmatter stays as it is. A line may end in `\\r\\n`."""
    lines = data.split(b"\n")
    fences = [i for i, line in enumerate(lines) if line in (b"---", b"---\r")]
    if fences[:1] != [0] or len(fences) < 2:
        return data
    end = fences[1]
    return b"\n".join(
        line for i, line in enumerate(lines) if not (0 < i < end and line.startswith(b"model:"))
    )


def check_sizes(texts: list[tuple[str, bytes]]) -> None:
    """Exit 2 when a text of `texts`, [(label, bytes)], holds an include, `@[label](path)`, whose
    expanded size is not known here; when one has FILE_CAP bytes or more; or when the global file
    and the always-on rules among them, every text but a `trigger: glob` rule, have BUDGET bytes or
    more together: Antigravity would cut the file, or demote rules to path pointers. A glob rule
    loads only for a matching file, so it is not in the budget."""
    included = [label for label, data in texts if INCLUDE.search(data)]
    if included:
        raise HarnessError(
            f"{', '.join(included)} holds an include, `@[…](…)`, which Antigravity expands before it "
            "cuts the file at 24,000 bytes; the install measures no expanded size, so it writes no "
            "include"
        )
    over = [f"{label}: {len(data)} bytes" for label, data in texts if len(data) >= FILE_CAP]
    if over:
        raise HarnessError(
            f"{'; '.join(over)}. Antigravity cuts an instruction file or a rule at 24,000 bytes, so "
            "the install writes none of that size"
        )
    total = sum(len(data) for _, data in texts if not data.startswith(GLOB_RULE))
    if total >= BUDGET:
        raise HarnessError(
            f"the global file and the always-on rules hold {total} bytes together. Antigravity's "
            f"always-on and global rules share 20,000 tokens, {BUDGET} bytes at 4 bytes a token, and a "
            "rule over the budget becomes a path pointer, so the install writes none over it"
        )


def extras(root, files):
    """The text of each installed file with no source below config/rules/, config/skills/,
    config/hooks/ and config/agents/ of `root`, as `files`, [(path relative to `root`, …)], holds
    them, with its removal command: a directory of skills/ with no file of `files` as one, every
    other file on its own. A hidden name is not listed, and nothing outside those directories is."""
    config = root / "config"
    ours = {install.fold(rel) for rel, *_ in files}
    found = [
        (d, "rm -r")
        for d in (
            sorted(p for p in (config / "skills").iterdir() if p.is_dir())
            if (config / "skills").is_dir()
            else []
        )
        if not install.hidden(d.name)
        and not any(o.startswith(install.fold(f"config/skills/{d.name}/")) for o in ours)
    ]
    for top in ("rules", "skills", "hooks", "agents"):
        for path, dirs, names in (
            os.walk(config / top, onerror=install.unreadable) if (config / top).is_dir() else []
        ):
            dirs[:] = sorted(
                d for d in dirs if not install.hidden(d) and (pathlib.Path(path, d), "rm -r") not in found
            )
            found += [
                (pathlib.Path(path, n), "rm")
                for n in sorted(names)
                if not install.hidden(n)
                and install.fold(pathlib.Path(path, n).relative_to(root).as_posix()) not in ours
            ]
    return [
        f"\nEXTRA: {p} is installed and has no source here; the install leaves it.\n"
        f"       To remove it:  {command} '{p}'"
        for p, command in found
    ]


def guard_paths(profile):
    """The text of guard-paths.json, rendered with `profile`: under `deny` the `deny` list of
    OpenCode's path list, then MCP_CONFIG and LAYER; under `edit` every `Edit` deny of the
    settings template, and under `ask` every `Edit` ask, each with a leading `//` as `/`, then the
    path of this layer's copy (relocate) of each such path below a root of frontends.SHARED_ROOTS,
    and `edit` then the global instruction files that Antigravity loads: config/GEMINI.md, the
    counterpart of ~/.claude/CLAUDE.md, config/AGENTS.md and ~/.gemini/GEMINI.md, which the install
    does not write; then the installed agents, AGENTS, and the app's settings, APP_CONFIG, whose
    grants an agent could widen; under `bash_deny` and `bash_ask` the body of every `Bash` deny and
    ask of the template."""
    deny = json_value(profile_module.render_file(GUARD_PATHS, profile), str(GUARD_PATHS))["deny"]
    permissions = json_value(profile_module.render_file(SETTINGS, profile), str(SETTINGS))["permissions"]
    bodies = {
        (tool, key): [
            m.group(1) for e in permissions.get(key, []) if (m := re.fullmatch(rf"{tool}\((.*)\)", e, re.S))
        ]
        for tool in ("Edit", "Bash")
        for key in ("deny", "ask")
    }
    home = render("{home}", profile)
    roots = tuple(home + root.removeprefix("~") for root in frontends.SHARED_ROOTS)
    edits = {key: [re.sub(r"^//+", "/", p) for p in bodies["Edit", key]] for key in ("deny", "ask")}
    edits["ask"] += [render(p, profile) for p in frontends.EDIT_SCOPE_ASKS]  # pyright: ignore[reportUnknownArgumentType]
    copies = {
        key: [
            home + relocate(("~" + p[len(home) :]).encode(), "~/.gemini/config").decode()[1:]
            for p in paths
            if p.startswith(roots)
        ]
        for key, paths in edits.items()
    }
    globals_ = [
        render(p, profile)
        for p in (
            "{home}/.gemini/config/GEMINI.md",
            "{home}/.gemini/config/AGENTS.md",
            "{home}/.gemini/GEMINI.md",
            AGENTS,
            APP_CONFIG,
        )
    ]
    return (
        json.dumps(
            {
                "deny": [*deny, render(MCP_CONFIG, profile), *(render(p, profile) for p in LAYER)],
                "edit": [*edits["deny"], *copies["deny"], *globals_],
                "ask": [*edits["ask"], *copies["ask"]],
                "bash_deny": bodies["Bash", "deny"],
                "bash_ask": bodies["Bash", "ask"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def command_rule(body, allow=False):
    """The Antigravity rule of the Claude Code rule `Bash(body)`, in the list `allow` or another.
    A regex rule matches a trailing ` *` with no text, as the prefix rule does; in an `allow` rule a
    `*` matches no text that ends a segment (SEGMENT_TEXT)."""
    m = re.fullmatch(r"([^*]*[^*\s]) \*", body)
    if m:
        return f"command({m.group(1)})"
    star = SEGMENT_TEXT if allow else ".*"
    head, tail = (body[:-2], f"(?: {star})?") if body.endswith(" *") else (body, "")
    return (
        "command(regex:^"
        + star.join(REGEX_SPECIAL.sub(lambda c: "\\" + c.group(0), part) for part in head.split("*"))
        + tail
        + "$)"
    )


def path_rule(action, body):
    """(the Antigravity rule `action(path)` of the Claude Code path `body`, None), or (None, the
    reason it has none)."""
    path = re.sub(r"^//+", "/", body)
    if path.endswith("/**"):
        path = path[:-3]
    if path.startswith("**/"):
        return None, "a `**/` glob, which no Antigravity path rule expresses"
    if re.search(r"[*?\[]", path):
        return None, "a glob inside the path; an Antigravity path rule names a path and its subtree"
    if not path.startswith("/"):
        return None, "a path that is not absolute"
    return f"{action}({path})", None


def render_permissions(
    cfg: dict[str, Any], profile: profile_module.Profile
) -> tuple[dict[str, list[str]], list[tuple[str, str, str | None]]]:
    """({list: [rule]}, [(list, entry, reason)]) of the `permissions` of `cfg`, the rendered
    settings template: the Antigravity rules in the template's lists and order, MCP_CONFIG as a
    `read_file` deny and LAYER and MCP_CONFIG as `write_file` denies after them, then each Kaimon
    tool of a list (KAIMON_TOOL) as `mcp(kaimon/<tool>)` after them, in the template's order, then
    in `allow` the first word of each command of the template's `sandbox.excludedCommands` as
    `command(<word>)`, each rule once; and each entry that has no rule, with its reason. The app
    needs one grant per Kaimon tool, and no wildcard covers them. Claude Code runs the commands of
    `excludedCommands` outside its sandbox, and these rules let Antigravity run them with no
    prompt; the guard applies the template's Bash denies and asks to each of them before
    Antigravity's rules."""
    rules, dropped = {key: [] for key in LISTS}, []
    kaimon = {key: [] for key in LISTS}
    for key in LISTS:
        for entry in cfg["permissions"].get(key, []):
            rule, reason = None, None
            if m := KAIMON_TOOL.fullmatch(entry):
                kaimon[key].append(f"mcp(kaimon/{m.group(1)})")
                continue
            if m := re.fullmatch(r"Bash\((.*)\)", entry, re.S):
                rule = command_rule(m.group(1), key == "allow")
            elif m := re.fullmatch(r"(Read|Edit)\((.*)\)", entry, re.S):
                rule, reason = path_rule({"Read": "read_file", "Edit": "write_file"}[m.group(1)], m.group(2))
            elif (m := re.fullmatch(r"WebFetch\(domain:(.*)\)", entry)) and key == "allow":
                rule = f"read_url({m.group(1)})"
            else:
                reason = (
                    "no Antigravity rule renders it: the rules come from the Bash, Read and Edit entries, "
                    "the allow hosts and the Kaimon tools"
                )
            if rule is None:
                dropped.append((key, entry, reason))
            else:
                rules[key].append(rule)
    rules["deny"] += [
        f"read_file({render(MCP_CONFIG, profile)})",
        *(f"write_file({render(p, profile).removesuffix('/**')})" for p in (*LAYER, MCP_CONFIG)),
    ]
    for key in LISTS:
        rules[key] += kaimon[key]
    for command in cfg.get("sandbox", {}).get("excludedCommands", []):
        rule = f"command({command.split()[0]})"
        if rule not in rules["allow"]:
            rules["allow"].append(rule)
    return rules, dropped


def deny_write(entries, home, root, found, taken=()):
    """([rule], [(line, …)]) of `entries`, the template's `sandbox.filesystem.denyWrite`: each
    entry at or below the research root `root` a `read_file(<path>)` deny, in the template's order,
    each rule once and none of the rules `taken`, `~` the home directory `home`. A `read_file` deny
    keeps a sandboxed command from reading and writing its path, and a `write_file` deny hides far
    more of the sandbox than its path, so the deny is a `read_file` one. An entry outside the root
    renders nothing and no warning: the app's sandbox mounts only the workspace, so a sandboxed
    command cannot write there. Paths are compared by their real paths, as the clones of `found`
    are. An entry `<prefix>/**/<rest>`, its prefix the root or below it, is one rule
    `<clone>/<rest>` for each clone of `found` at or below the prefix; a worktree's `.git` is a
    file, and its main repository's rules cover it. Any other entry with a wildcard whose directory
    before the first wildcard is the root, above it or below it, and one that is not absolute,
    gives a warning that names it and no rule. When an entry is expanded over the clones, a last
    warning names the number of clones that the expanded entries cover."""
    rules, warnings, covered, expanded = [], [], [], False
    top = pathlib.Path(os.path.realpath(root))
    for entry in entries:
        path = units.expand(entry, home)
        if not path.startswith("/"):
            warnings.append(
                (
                    f"The settings template's `denyWrite` entry {entry} is not an absolute path, so it "
                    f"renders no Antigravity `read_file` deny.",
                )
            )
            continue
        head = re.split(r"[*?\[]", cast(str, path), maxsplit=1)[0]
        if head == path:
            if not pathlib.Path(os.path.realpath(path)).is_relative_to(top):
                continue
            paths = [path]
        else:
            # The directory that every match of the entry lies in: the text before the first
            # wildcard, up to its last `/`.
            base = pathlib.Path(os.path.realpath(head[: head.rindex("/") + 1]))
            if not base.is_relative_to(top) and not top.is_relative_to(base):
                continue
            if (m := re.fullmatch(r"[^*?\[]*/\*\*/([^*?\[]+)", path)) and base.is_relative_to(top):
                paths = [f"{c}/{m.group(1)}" for c in found if c.is_relative_to(base)]
                covered += [c for c in found if c.is_relative_to(base) and c not in covered]
                expanded = True
            else:
                warnings.append(
                    (
                        f"The settings template's `denyWrite` entry {entry} has a wildcard that no "
                        f"Antigravity rule expresses, so it renders no `read_file` deny.",
                    )
                )
                continue
        rules += [r for r in (f"read_file({p})" for p in paths) if r not in rules and r not in taken]
    if expanded:
        n = len(covered)
        warnings.append(
            (
                f"The `read_file` denies of the template's `denyWrite` entries with `**` cover {n} "
                f"{'repository' if n == 1 else 'repositories'}: each directory at or below the "
                f"research root that holds a `.git` directory.",
                "A repository cloned later is covered at the next `harness install --apply`.",
            )
        )
    return rules, warnings


def clones():
    """Each directory at or below the research root that holds a `.git` directory, by its real
    path, walked as `harness trust` walks it: a worktree's `.git` is a file."""
    return [
        pathlib.Path(p) for p in frontends.adapter("claude").roots() if os.path.isdir(os.path.join(p, ".git"))
    ]


def json_value(text: str, where: str) -> Any:
    """The JSON value of `text`, of any type, read by `jsonio`; a refusal raises HarnessError, which
    names `where`. Each caller reads the keys of the value as its own code checks them."""
    return jsonio.loads(text, where=where, top=object)


def read_regular(path, refused):
    """The text of the file at `path`, None when it does not exist. Exits 2 on a file that is not a
    regular file, cannot be read, or is not UTF-8, its message ended by `refused`. One lstat, so
    that a link, a FIFO or a directory is refused before it is opened."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    if not stat.S_ISREG(st.st_mode):
        raise HarnessError(f"{path} is not a regular file{refused}")
    try:
        return path.read_bytes().decode("utf-8")
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    except UnicodeDecodeError as e:
        raise HarnessError(f"{path} is not UTF-8: {e.reason} at byte {e.start}{refused}") from None


def merge_settings(path, rules):
    """The bytes of the CLI's settings at `path` with `permissions` set to `rules` and the keys of
    POSTURE set, and every other byte of the file kept (`ownedjson.merged`); a missing file holds
    no key. Exits 2, before anything is written, on a file that is not a regular file, cannot be
    read, is not UTF-8, or is not a JSON object that `jsonio` reads (`json_object`)."""
    claude = frontends.adapter("claude")
    refused = "; the install sets three keys of a JSON object in a regular file there, and writes nothing"
    text = read_regular(path, refused)
    content, file = cast("str | None", text), cast("pathlib.Path", path)
    if content is not None:
        claude.json_object(file, content)

    def change(settings: dict[str, JsonValue]) -> dict[str, JsonValue]:
        settings.update(permissions=cast("JsonValue", rules), **POSTURE)
        return settings

    return ownedjson.merged(content or "", change, where=str(file)).encode()


def merge_grants(path, rules):
    """The bytes of the app's settings at `path` with each rule of `rules` added once to its list,
    `allow`, `deny` or `ask`, of `userSettings.globalPermissionGrants`, after the entries that the
    list holds: every other key, every entry and every other byte of the file stays
    (`ownedjson.merged`), and a missing key is created. A missing file holds no key. Exits 2,
    before anything is written, on a file that is not a regular file, cannot be read, is not UTF-8,
    is not a JSON object that `jsonio` reads (`json_object`: a key twice in one object is refused),
    or has a `userSettings` or a `globalPermissionGrants` that is not an object or one of the three
    lists that is not a list. The install removes no entry, so a rule that it wrote once stays."""
    claude = frontends.adapter("claude")
    refused = (
        "; the install adds its rules to userSettings.globalPermissionGrants of a JSON object in a regular "
        "file there, and writes nothing"
    )
    text = read_regular(path, refused)
    content, file = cast("str | None", text), cast("pathlib.Path", path)
    settings: dict[str, Any] = {}
    if content is not None:
        settings = claude.json_object(file, content)
    node = cast("object", settings)
    where: list[str] = []
    for key in ("userSettings", "globalPermissionGrants"):
        node, where = cast("dict[str, Any]", node).get(key, {}), [*where, key]
        if not isinstance(node, dict):
            raise HarnessError(f"{path}: its {'.'.join(where)} is not a JSON object{refused}")
    for key in ("allow", "deny", "ask"):
        if not isinstance(cast("dict[str, Any]", node).get(key, []), list):
            raise HarnessError(f"{path}: its {'.'.join(where)}.{key} is not a JSON list{refused}")
    wanted = cast("dict[str, list[str]]", rules)

    def change(merged: dict[str, JsonValue]) -> dict[str, JsonValue]:
        grants = merged
        for key in ("userSettings", "globalPermissionGrants"):
            grants = cast("dict[str, JsonValue]", grants.setdefault(key, {}))
        for key in ("allow", "deny", "ask"):
            entries = cast("list[JsonValue]", grants.setdefault(key, []))
            for rule in wanted[key]:
                if rule not in entries:
                    entries.append(rule)
        return merged

    return ownedjson.merged(content or "", change, where=str(file)).encode()


def load_models(
    path: str | pathlib.Path, agents: str | pathlib.Path
) -> tuple[dict[str, str], dict[str, str]]:
    """({tier: word}, {agent: word}) of the table [antigravity] of the model tables at `path`
    (profile.read_models, which refuses any other key and a value that is not a string): the
    tiers of frontmatter.TIERS, each one of WORDS, and its optional sub-table `model_overrides`,
    each key an agent of the directory `agents` and each value one of WORDS. The table is read on
    its own, as [claude] is, and its overrides are not merged with the shared [model_overrides],
    whose values are provider models. A missing table or tier, and any other value, exit 2,
    naming the table and the key."""
    models = profile_module.read_models(path)
    table, overrides = models.antigravity, models.antigravity_overrides
    tiers, words = frontmatter.TIERS, ", ".join(WORDS)
    if not table and not overrides:
        raise HarnessError(
            f"{path} has no [antigravity] table, which maps the tiers {', '.join(tiers)} to "
            f"Antigravity's tiers {words} — examples/models.toml shows it"
        )
    if missing := [t for t in tiers if t not in table]:
        raise HarnessError(
            f"{path}: [antigravity] holds the tiers {', '.join(tiers)} and model_overrides; "
            f"it has no {', '.join(missing)}"
        )
    wrong = [f"[antigravity] {t} = {table[t]!r}" for t in tiers if table[t] not in WORDS] + [
        f"[antigravity.model_overrides] {a} = {v!r}" for a, v in overrides.items() if v not in WORDS
    ]
    if wrong:
        raise HarnessError(f"{path}: {'; '.join(wrong)} is not an Antigravity tier; a tier is {words}")
    names = {p.stem for p in pathlib.Path(agents).glob("*.md")}
    if strangers := sorted(set(overrides) - names):
        raise HarnessError(
            f"{path}: [antigravity.model_overrides] {', '.join(strangers)} is no agent of {agents}"
        )
    return {t: table[t] for t in tiers}, dict(overrides)


def sections(text):
    """{name: text} of each level-2 section `## <name>` of `text`, its text stripped."""
    return {
        m.group(1): m.group(2).strip() for m in re.finditer(r"(?m)^## (\w+)\n(.*?)(?=^## |\Z)", text, re.S)
    }


def under_antigravity(meta, body, text=None):
    """The "Under Antigravity" section of an agent with frontmatter `meta` and `body`: the intro and
    the rule of `text`, UNDER's text by default, for each Claude Code mechanism that it uses — a
    preloaded skill, worktree isolation (`isolation: worktree` in its frontmatter or its body), the
    `Agent` tool, a background run, a Kaimon tool, opening a pull request; "" when it uses none. A
    section that it needs and that `text` lacks exits 2."""
    rules = sections(UNDER.read_text() if text is None else text)
    tools, skills = meta.get("tools", []), meta.get("skills", [])
    used = [
        key
        for key, uses in [
            ("skills", bool(skills)),
            (
                "worktree",
                meta.get("isolation") == "worktree" or re.search(r'isolation: "?worktree', body) is not None,
            ),
            ("agent", "agent" in tools),
            ("background", "run_in_background" in body),
            ("mcp", any(t.startswith(frontmatter.MCP) for t in tools)),
            # `gh pr create` can need a grant, so the caller runs it.
            ("pr", re.search(r"(?i)open (?:the|a) pull request", body) is not None),
        ]
        if uses
    ]
    if not used:
        return ""
    if missing := [k for k in ["intro", *used] if k not in rules]:
        raise HarnessError(f"{UNDER}: no section `## {missing[0]}`")
    named = f"{sources.code_list(skills)} skill{'s' * (len(skills) > 1)}" if skills else ""
    lines = [rules[k].replace("{skills}", named) for k in used]
    return (
        "## Under Antigravity\n\n" + rules["intro"] + "\n\n" + "\n".join("- " + line for line in lines) + "\n"
    )


def render_agent(
    path: str | os.PathLike[str],
    tiers: dict[str, str],
    overrides: dict[str, str],
    root: str = "~/.gemini/config",
) -> bytes:
    """The bytes of the Antigravity agent of the agent at `path`, with `tiers` and `overrides` of
    load_models: the frontmatter `name`, `description`, `model` (its override, else the word of its
    tier, else `inherit`), `tools` (each neutral tool by TOOLS, `[]` for none), `subagent: true`,
    and `inheritMcp: true` for an agent with a Kaimon tool, each value as JSON, which YAML reads as
    the same value; then the generated-by comment, the "Under Antigravity" section and the body,
    its shared paths relocated to `root` (relocate). `effort`, `isolation` and `skills` are not
    written: no agent sets an effort under Antigravity, and the section replaces the other two. A
    tool that TOOLS does not map, no description, and a `name:` that is not the file name exit 2."""
    path = pathlib.Path(path)
    name = path.name.removesuffix(".md")
    fm = frontmatter.parse_file(path)
    meta = fm.meta
    if meta.get("name", name) != name:
        raise HarnessError(f"{path}: the name {meta['name']!r} is not the file name {name!r}")
    if "description" not in meta:
        raise HarnessError(f"{path}: no `description:` line")
    tools = []
    for tool in meta.get("tools", []):
        if tool.startswith(frontmatter.MCP):
            continue
        if tool not in TOOLS:
            raise HarnessError(
                f"{path}: the tool {tool!r} has no Antigravity name; TOOLS of "
                f"adapters/antigravity/adapter.py maps {', '.join(TOOLS)} and Kaimon's tools"
            )
        tools += [n for n in TOOLS[tool] if n not in tools]
    model = overrides.get(name, tiers[meta["model"]] if "model" in meta else "inherit")
    head = {
        "name": name,
        "description": meta["description"],
        "model": model,
        "tools": tools,
        "subagent": True,
    }
    if any(t.startswith(frontmatter.MCP) for t in meta.get("tools", [])):
        head["inheritMcp"] = True
    section = under_antigravity(meta, fm.body)
    rest = (
        f"<!-- Generated by `harness install` from agents/{name}.md of the harness repository. Do not "
        "edit this file: edit the source and run `harness install --apply`. -->\n\n"
        + (section + "\n" if section else "")
        + fm.body.lstrip("\n")
    )
    return (
        "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in head.items()) + "---\n\n"
    ).encode() + relocate(rest.encode(), root)


def render_mcp(home, config):
    """(the bytes of the MCP configuration at `config` with `mcpServers.kaimon` set to Kaimon at
    KAIMON_URL, with the token of KAIMON_TOKEN below `home` as its bearer, None); or (None, a
    warning) when the token file does not exist, is not a regular file, cannot be read, is not
    UTF-8, or holds no token: the configuration is then neither read nor written. The token is read
    first, and the configuration is merged as merge_mcp says."""
    path = home / KAIMON_TOKEN
    none = "; the install writes no Kaimon entry and leaves ~/.gemini/config/mcp_config.json as it is"
    try:
        # A FIFO would block the read, so the file's type is checked first.
        if not stat.S_ISREG(path.stat().st_mode):
            return None, (
                f"{path} is not a regular file{none}.",
                "Make it a file, mode 600, with Kaimon's token alone.",
            )
        token = path.read_bytes().decode("utf-8").strip()
    except FileNotFoundError:
        return None, (f"{path} does not exist{none}.", "Create it, mode 600, with Kaimon's token alone.")
    except OSError as e:
        return None, (f"{path} cannot be read: {e.strerror}{none}.",)
    except UnicodeDecodeError:
        return None, (f"{path} is not UTF-8{none}.",)
    if not token:
        return None, (f"{path} is empty{none}.", "Write Kaimon's token into it.")
    kaimon = {"url": KAIMON_URL, "headers": {"Authorization": f"Bearer {token}"}}
    return merge_mcp(config, kaimon), None


def merge_mcp(path, kaimon):
    """The bytes of the MCP configuration at `path` with `mcpServers.kaimon` set to `kaimon`, and
    every other byte of the file kept (`ownedjson.merged`). A missing file, an empty one, or one of
    whitespace only holds no key. Exits 2, before anything is written and without the file's text,
    on a file that is not a regular file, cannot be read, is not UTF-8, is not a JSON object that
    `jsonio` reads (`json_object`: a key twice in one object, inside the Kaimon entry too, is
    refused with its line and its name), or has a `mcpServers` that is not an object. No error
    prints a value of the file."""
    claude = frontends.adapter("claude")
    refused = (
        "; the install sets mcpServers.kaimon of a JSON object in a regular file there, and writes nothing"
    )
    text = read_regular(path, refused)
    content, file = cast("str | None", text), cast("pathlib.Path", path)
    if content is not None and content.strip():
        cfg = claude.json_object(file, content)
        if not isinstance(cfg.get("mcpServers", {}), dict):
            raise HarnessError(f"{path}: its mcpServers is not a JSON object{refused}")

    def change(merged: dict[str, JsonValue]) -> dict[str, JsonValue]:
        cast("dict[str, JsonValue]", merged.setdefault("mcpServers", {}))["kaimon"] = cast(
            "JsonValue", kaimon
        )
        return merged

    return ownedjson.merged(content or "", change, where=str(file)).encode()


def council_warnings(path: str | pathlib.Path) -> list[tuple[str]]:
    """[(line, …)]: one warning for each agent that a council of the model tables at `path` names,
    in [councils] or in [<frontend>.councils] of a frontend of profile.SHARING. Antigravity runs
    the agent alone and writes no seat."""
    models = profile_module.read_models(path)
    agents = sorted({a for t in (models.shared, models.opencode, models.omp) for a in t.councils})
    return [
        (f"{path} gives {a} a council. Antigravity runs {a} alone, on its own tier, and writes no seat.",)
        for a in agents
    ]


def guard_package(files: list[tuple[object, ...]]) -> list[tuple[str, object, object]]:
    """(path below ~/.gemini/, bytes, mode) of each file of the Claude Code layer's plan `files`
    below ~/.claude/hooks/guard/, at the same path below config/hooks/guard/."""
    return [
        (f"config/hooks/guard/{label.removeprefix(GUARD_PACKAGE)}", data, mode)
        for _, data, mode, label, *_ in files
        if isinstance(label, str) and label.startswith(GUARD_PACKAGE)
    ]


def plan(ctx: types.SimpleNamespace | argparse.Namespace):
    """Antigravity's part of `harness install`, as the docstring of this module says; the guard
    package, install-drift.py, the instruction files, the rules and the skills are those of the
    Claude Code layer's plan in `ctx.plans`."""
    root = gemini_dir()
    if not root.is_dir():
        state = "is not a directory" if root.exists() else "does not exist"
        return frontends.Plan(
            warnings=[
                (
                    f"{root} {state}, so the Antigravity layer is not installed.",
                    "Install Antigravity, then run `harness install` again.",
                )
            ]
        )
    tiers, overrides = load_models(ctx.models, ctx.agents)
    claude = frontends.adapter("claude")
    cfg = claude.settings_template(ctx.profile, profile_module.network_path(ctx.args.profile))
    rules, _ = render_permissions(cfg, ctx.profile)
    # Claude Code's sandbox keeps a command from writing these paths, and the guard lifts git out
    # of Antigravity's sandbox, where it would run a hook or an alias that a sandboxed command planted.
    denies, notes = deny_write(
        cfg.get("sandbox", {}).get("filesystem", {}).get("denyWrite", []),
        str(pathlib.Path.home()),
        research_root(),
        clones(),
        rules["deny"],
    )
    rules["deny"] += denies
    layer = ctx.plans["claude"]
    drift = next((f[1], f[2]) for f in layer.files if f[3] == "~/.claude/hooks/install-drift.py")
    files = [
        ("config/hooks.json", render_hooks(root).encode(), None),
        *guard_package(layer.files),
        ("config/hooks/install-drift.py", *drift),
        ("config/guard-paths.json", guard_paths(ctx.profile).encode(), None),
    ]
    # The texts name Antigravity's copies, not Claude Code's; the global file names them itself.
    home = frontends.home_form(root / "config")
    texts = [
        ("config/GEMINI.md", DELTA.read_bytes(), DELTA),
        *(
            (f"config/rules/{dst.split('/')[-1]}", always_on(relocate(data, home)), f"~/.claude/{dst}")
            for dst, data, _ in layer.shared
            if re.fullmatch(r"RTK\.md|instructions/[^/]+\.md", dst)
        ),
        *(
            (f"config/rules/{dst.split('/')[-1]}", render_rule(src, relocate(data, home)), src)
            for dst, src, data in layer.rules
            if re.fullmatch(r"rules/[^/]+\.md", dst)
        ),
    ]
    owner = {}
    for rel, _, src in texts:
        if install.fold(rel) in owner:
            raise HarnessError(f"~/.gemini/{rel} has two sources, {owner[install.fold(rel)]} and {src}")
        owner[install.fold(rel)] = src
    check_sizes([(f"~/.gemini/{rel}", data) for rel, data, _ in texts])
    files += [(rel, data, None) for rel, data, _ in texts]
    files += [
        (
            f"config/{dst}",
            relocate(render_skill(data) if re.fullmatch(r"skills/[^/]+/SKILL\.md", dst) else data, home)
            if dst.endswith(".md")
            else data,
            mode,
        )
        for dst, data, mode in layer.shared
        if dst.startswith("skills/")
    ]
    files += [
        (f"config/agents/{p.name}", render_agent(p, tiers, overrides, home), None)
        for p in sorted(pathlib.Path(ctx.agents).glob("*.md"))
    ]
    warnings = [*notes, *council_warnings(ctx.models)]
    # The file holds the token, so it is written with mode 600 and never backed up: a backup beside
    # it is outside the deny rules of MCP_CONFIG.
    mcp, warning = render_mcp(pathlib.Path.home(), root / "config" / "mcp_config.json")
    if mcp is None:
        warnings.append(warning)
    else:
        files.append(("config/mcp_config.json", mcp, 0o600))
    settings, app = root / "antigravity-cli" / "settings.json", root / "config" / "config.json"
    # The CLI's and the app's settings hold the user's own keys, so a replaced file is backed up first.
    return frontends.Plan(
        files=[
            *((root / rel, data, mode, f"antigravity/{rel}") for rel, data, mode in files),
            (
                settings,
                merge_settings(settings, rules),
                None,
                "antigravity/antigravity-cli/settings.json",
                True,
            ),
            (app, merge_grants(app, rules), None, "antigravity/config/config.json", True),
        ],
        extra=extras(root, files),
        warnings=warnings,
    )


def register(sub):
    """Antigravity has no subcommand of its own."""


def rule_matches(rule, command):
    """Whether the Antigravity rule `rule` matches the command line `command`, as the permission
    rules match: `command(prefix)` word by word, `command(regex:…)` by the regular expression. The
    cases read the rendered rules with it."""
    m = re.fullmatch(r"command\((regex:)?(.*)\)", rule, re.S)
    if m is None:
        return False
    if m.group(1):
        return re.search(m.group(2), command) is not None
    return command.split()[: len(m.group(2).split())] == m.group(2).split()


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`


def selftest():
    """The Antigravity layer of `harness install`, end to end on scratch HOMEs."""
    from harness.install_cases import Scratch, source_name_cases

    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  antigravity: {label}")

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Scratch(check, tmp)
        source_name_cases(scratch.case, tmp)
        layer_cases(scratch)
        instruction_cases(scratch)
        rule_cases(scratch.case)
        merge_cases(scratch)
        grants_cases(scratch)
        deny_write_cases(scratch)
        model_cases(scratch)
        agent_cases(scratch)
        council_cases(scratch)
        kaimon_cases(scratch)
    return total, wrong


def guard_sources() -> list[str]:
    """Each file of the guard package of this repository, hooks/guard/, relative to it, without a
    hidden name or a __pycache__ that a run leaves."""
    root = REPO / "hooks" / "guard"
    found = (path.relative_to(root) for path in root.rglob("*") if path.is_file())
    return sorted(
        path.as_posix()
        for path in found
        if not any(part.startswith(".") or part == "__pycache__" for part in path.parts)
    )


def layer_cases(scratch):
    """The files of the layer, the warning with no ~/.gemini/, hooks.json and the copies."""
    scratch = cast("Any", scratch)
    from harness.install_cases import rule_names, skill_names

    case, run, tail = scratch.case, scratch.run, scratch.tail
    line = re.compile(r"^antigravity/(\S+)\s+(\S+)", re.M)
    rules = sorted([*rule_names(REPO / "rules"), "meta-repository.md"])
    texts = [
        "config/GEMINI.md",
        *(f"config/rules/{n}" for n in ["RTK.md", "core.md", "research-tree.md", *rules]),
        *(f"config/skills/{f}" for f in skills_files()),
        *(f"config/agents/{p.name}" for p in (REPO / "agents").glob("*.md")),
    ]
    package = guard_sources()
    want = sorted(
        [
            "config/hooks.json",
            "config/guard-paths.json",
            *(f"config/hooks/guard/{f}" for f in package),
            "config/hooks/install-drift.py",
            "antigravity-cli/settings.json",
            "config/config.json",
            *texts,
        ]
    )

    base, claude, _ = scratch.fresh()
    code, dry = run(base)
    warned = [w for w in dry.split("WARNING: ")[1:] if ".gemini" in w]
    case(
        lambda: (
            code in (0, 1)
            and line.findall(dry) == []
            and len(warned) == 1
            and str(base / "home" / ".gemini") in warned[0]
            and not (base / "home" / ".gemini").exists()
        ),
        f"with no ~/.gemini/, the dry run lists no file of the layer and gives one warning that names the "
        f"directory: {code}, {line.findall(dry)}, {warned}",
    )

    base, claude, _ = scratch.fresh()
    (base / "home" / ".gemini").write_text("x")
    code, dry = run(base)
    warned = [w for w in dry.split("WARNING: ")[1:] if ".gemini" in w]
    case(
        lambda: line.findall(dry) == [] and len(warned) == 1 and "is not a directory" in warned[0],
        f"with a file at ~/.gemini, the one warning says that it is not a directory: {warned}",
    )

    base, claude, _ = scratch.fresh(["instructions/research-tree.md", "rules/meta-repository.md"])
    gemini = base / "home" / ".gemini"
    gemini.mkdir()
    code, dry = run(base)
    listed = dict(line.findall(dry))
    case(
        lambda: (
            sorted(listed) == want
            and set(listed.values()) == {"INSTALL"}
            and sorted(p.relative_to(gemini).as_posix() for p in gemini.rglob("*")) == []
        ),
        f"the dry run lists hooks.json, guard-paths.json, each file of the guard package below hooks/guard/, "
        f"hooks/install-drift.py, antigravity-cli/settings.json, config/config.json, the instruction files, rules "
        f"and skills, and one "
        f"agents/<name>.md for each agent of agents/, each INSTALL, and writes nothing: {code}, "
        f"{sorted(set(listed) ^ set(want))}",
    )
    planned = {p.split("/")[2] for p in listed if p.startswith("config/skills/")}
    case(
        lambda: (
            "config/GEMINI.md" in listed
            and sorted(p for p in listed if re.fullmatch(r"config/rules/(RTK|core|research-tree)\.md", p))
            == ["config/rules/RTK.md", "config/rules/core.md", "config/rules/research-tree.md"]
            and sorted(
                p.removeprefix("config/rules/")
                for p in listed
                if p.startswith("config/rules/")
                and p not in ("config/rules/RTK.md", "config/rules/core.md", "config/rules/research-tree.md")
            )
            == rules
            and sorted(planned) == skill_names(REPO / "skills")
        ),
        f"the dry run lists the global file, the three always-on files, one rule file for each of the {len(rules)} "
        f"rules and one skills/<name>/ for each of the {len(planned)} skills: {sorted(listed)}",
    )
    code, text = run(base, "--apply")
    if code != 0:
        case(
            lambda: False,
            f"the setup install --apply of the Antigravity cases exits {code}: {tail(text)!r}; "
            f"the cases after it do not run",
        )
        return
    installed = sorted(p.relative_to(gemini).as_posix() for p in gemini.rglob("*") if p.is_file())
    case(
        lambda: installed == want,
        f"--apply installs those files below ~/.gemini/, and nothing else: {installed}",
    )
    config = gemini / "config"
    hooks = (config / "hooks.json").read_text() if (config / "hooks.json").is_file() else None
    python = shlex.quote(str(base / "python" / "bin" / "python"))
    handler = f"{python} {shlex.quote(str(config / 'hooks' / 'guard'))} --from antigravity"
    start = (
        python
        + " -c "
        + shlex.quote(TRANSLATE)
        + " "
        + shlex.quote(str(config / "hooks" / "install-drift.py"))
    )
    case(
        lambda: (
            hooks is not None
            and json_value(cast(str, hooks), "hooks.json")
            == {
                HOOK: {
                    "SessionStart": [{"type": "command", "command": start, "timeout": 15}],
                    "PreToolUse": [
                        {"matcher": "*", "hooks": [{"type": "command", "command": handler, "timeout": 15}]}
                    ],
                }
            }
        ),
        f"hooks.json holds the one hook {HOOK}: one SessionStart handler, which runs install-drift.py and turns its "
        f"warning into injectSteps, and one PreToolUse group, matcher *, the guard package by its "
        f"absolute path with --from antigravity, each on the environment's interpreter with a timeout of "
        f"15 s: {hooks!r}",
    )

    def commands_of(value):
        """Every string value of a key `command` in the JSON value `value`."""
        if isinstance(value, dict):
            return [
                c
                for k, v in value.items()
                for c in ([v] if k == "command" and isinstance(v, str) else commands_of(v))
            ]
        return [c for v in value for c in commands_of(v)] if isinstance(value, list) else []

    # Every command that the install writes for a .py hook or the guard package, in either frontend's
    # file, runs it on the scratch environment's interpreter.
    runs_py = [
        c
        for c in commands_of(json_value((claude / "settings.json").read_text(), "settings.json")["hooks"])
        + (commands_of(json_value(cast(str, hooks), "hooks.json")) if hooks is not None else [])
        if ".py" in c or "/hooks/guard " in c
    ]
    case(
        lambda: (
            len(runs_py) > 2
            and all(shlex.split(c)[0] == str(base / "python" / "bin" / "python") for c in runs_py)
        ),
        f"each command of ~/.claude/settings.json and hooks.json that runs a .py hook or the guard "
        f"package starts with the environment's interpreter: {runs_py}",
    )
    case(
        lambda: (
            (config / "hooks" / "install-drift.py").read_bytes()
            == (claude / "hooks" / "install-drift.py").read_bytes()
            and scratch.mode(config / "hooks" / "install-drift.py")
            == scratch.mode(claude / "hooks" / "install-drift.py")
        ),
        "hooks/install-drift.py is the Claude Code layer's copy, with its mode",
    )
    copies = [
        f
        for f in package
        if (config / "hooks" / "guard" / f).read_bytes() != (claude / "hooks" / "guard" / f).read_bytes()
        or scratch.mode(config / "hooks" / "guard" / f) != scratch.mode(claude / "hooks" / "guard" / f)
    ]
    case(
        lambda: package != [] and copies == [],
        f"each file of hooks/guard/ is the Claude Code layer's copy, with its mode: {copies}",
    )
    hooks = sorted(p.name for p in (config / "hooks").iterdir())
    case(
        lambda: hooks == ["guard", "install-drift.py"],
        f"hooks/ holds the guard package and install-drift.py, and no other file: {hooks}",
    )
    profile = profile_module.load(base / "profile.toml")
    opencode = json_value(profile_module.render_file(GUARD_PATHS, profile), str(GUARD_PATHS))["deny"]
    h = profile.home
    template = json_value(profile_module.render_file(SETTINGS, profile), str(SETTINGS))["permissions"]
    edits = {
        key: [re.sub(r"^//+", "/", e[len("Edit(") : -1]) for e in template[key] if e.startswith("Edit(")]
        for key in ("deny", "ask")
    }
    # The asks that the template leaves to Claude Code's hook edit-scope.py follow its own.
    edits["ask"] += [f"{h}/Research/**/.githooks/**", f"{h}/Research/**/.github/workflows/**"]
    bash = {
        key: [e[len("Bash(") : -1] for e in template[key] if e.startswith("Bash(")] for key in ("deny", "ask")
    }
    # The Edit rules of Claude Code's copied files, below Antigravity's copies, written out: RTK.md and
    # the files of instructions/ are in rules/, the other roots at the same path.
    copied = ("RTK.md", "instructions/", "hooks/", "rules/", "skills/")

    def moved(p):
        rest = p[len(h + "/.claude/") :]
        rest = (
            "rules/RTK.md"
            if rest == "RTK.md"
            else "rules/" + rest.removeprefix("instructions/")
            if rest.startswith("instructions/")
            else rest
        )
        return f"{h}/.gemini/config/{rest}"

    copies = {
        key: [moved(p) for p in edits[key] if p.startswith(tuple(f"{h}/.claude/{c}" for c in copied))]
        for key in ("deny", "ask")
    }
    globals_ = [
        f"{h}/.gemini/config/GEMINI.md",
        f"{h}/.gemini/config/AGENTS.md",
        f"{h}/.gemini/GEMINI.md",
        f"{h}/.gemini/config/agents/**",
        f"{h}/.gemini/config/config.json",
    ]
    lists = config / "guard-paths.json"
    written = json_value(lists.read_text(), "guard-paths.json") if lists.is_file() else {}
    case(
        lambda: (
            written["edit"][len(edits["deny"]) :] == [*copies["deny"], *globals_]
            and written["ask"][len(edits["ask"]) :] == copies["ask"]
            and {
                f"{h}/.gemini/config/rules/RTK.md",
                f"{h}/.gemini/config/rules/**",
                f"{h}/.gemini/config/skills/build-part/**",
                f"{h}/.gemini/config/hooks/**",
            }
            <= set(copies["deny"])
            and len(
                [p for p in edits["deny"] if p in (f"{h}/.claude/RTK.md", f"{h}/.claude/instructions/**")]
            )
            == 2
            and not {f"{h}/.gemini/config/RTK.md", f"{h}/.gemini/config/instructions/**"}
            & set(written["edit"])
            and copies["ask"] == [f"{h}/.gemini/config/skills/**"]
        ),
        f"after the template's Edit rules, `edit` holds each Edit deny of a copied path below ~/.claude/ as "
        f"the path of its copy below ~/.gemini/config/, RTK.md and instructions/ in rules/, then GEMINI.md, "
        f"AGENTS.md, ~/.gemini/GEMINI.md, the installed agents and the app's config.json, and `ask` each such "
        f"Edit ask: "
        f"{written.get('edit', [])[len(edits['deny']) :]}, {written.get('ask', [])[len(edits['ask']) :]}",
    )
    case(
        lambda: (
            written
            == {
                "deny": [
                    *opencode,
                    f"{h}/.gemini/config/mcp_config.json",
                    f"{h}/.gemini/config/hooks.json",
                    f"{h}/.gemini/config/hooks/**",
                    f"{h}/.gemini/config/guard-paths.json",
                    f"{h}/.gemini/antigravity-cli/settings.json",
                ],
                "edit": [*edits["deny"], *copies["deny"], *globals_],
                "ask": [*edits["ask"], *copies["ask"]],
                "bash_deny": bash["deny"],
                "bash_ask": bash["ask"],
            }
            and len(edits["deny"]) >= 54
            and len(edits["ask"]) >= 4
            and len(bash["deny"]) >= 187
            and len(bash["ask"]) >= 97
        ),
        f"guard-paths.json is OpenCode's deny list, then mcp_config.json and the files of the layer; `edit` is "
        f"every Edit deny of the template and `ask` every Edit ask, each then with Antigravity's copies; "
        f"`bash_deny` and `bash_ask` are the bodies "
        f"of every Bash deny and ask, entry by entry: { {k: len(v) for k, v in written.items()} }",
    )
    new = gemini / "antigravity-cli" / "settings.json"
    settings = json_value(new.read_text(), "settings.json") if new.is_file() else {}
    case(
        lambda: (
            settings["toolPermission"] == "proceed-in-sandbox"
            and settings["enableTerminalSandbox"] is True
            and "allowNonWorkspaceAccess" not in settings
            and sorted(settings) == sorted(["permissions", *POSTURE])
        ),
        f"a new settings.json holds the three keys, with the sandbox on and proceed-in-sandbox, and no "
        f"allowNonWorkspaceAccess: {sorted(settings)}",
    )
    kaimon = {
        key: [
            "mcp(kaimon/" + e.removeprefix("mcp__kaimon__") + ")"
            for e in template[key]
            if e.startswith("mcp__kaimon__")
        ]
        for key in LISTS
    }
    cli = settings.get("permissions", {})
    rendered = json_value(profile_module.render_file(SETTINGS, profile), str(SETTINGS))
    excluded = rendered["sandbox"]["excludedCommands"]
    unsandboxed = [f"command({w})" for w in dict.fromkeys(e.split()[0] for e in excluded)]

    def before_unsandboxed(key):
        """The list `key` of the CLI's permissions up to the rules of excludedCommands at its end, and
        `deny` up to the `read_file` denies of the template's denyWrite at its end."""
        rules = cli.get(key, [])
        while key == "allow" and rules and rules[-1] in unsandboxed:
            rules = rules[:-1]
        while key == "deny" and rules and rules[-1].startswith("read_file("):
            rules = rules[:-1]
        return rules

    case(
        lambda: (
            all(
                kaimon[key]
                and before_unsandboxed(key)[-len(kaimon[key]) :] == kaimon[key]
                and not [r for r in before_unsandboxed(key)[: -len(kaimon[key])] if r.startswith("mcp(")]
                for key in LISTS
            )
            and "mcp(kaimon/*)" not in cli["allow"]
        ),
        f"the CLI's settings.json holds each Kaimon tool of the template as mcp(kaimon/<tool>) after the other "
        f"rules of its list, in `allow` before the rules of excludedCommands, and no mcp(kaimon/*): "
        f"{ {key: before_unsandboxed(key)[-2:] for key in LISTS} }",
    )
    case(
        lambda: (
            len(unsandboxed) >= 4
            and cli["allow"][len(before_unsandboxed("allow")) :]
            == [r for r in unsandboxed if r not in before_unsandboxed("allow")]
            and all(cli["allow"].count(r) == 1 for r in unsandboxed)
        ),
        f"the CLI's settings.json ends its allow list with each rule of excludedCommands, {unsandboxed}, that "
        f"the list does not hold, and holds each once: {cli.get('allow', [])[-4:]}",
    )
    app = config / "config.json"
    grants = json_value(app.read_text(), "config.json") if app.is_file() else {}
    case(
        lambda: all(
            grants["userSettings"]["globalPermissionGrants"]["allow"].count(r) == 1 for r in unsandboxed
        ),
        f"the app's config.json holds each rule of excludedCommands once in its allow grants: "
        f"{grants.get('userSettings', {}).get('globalPermissionGrants', {}).get('allow', [])[-4:]}",
    )
    case(
        lambda: (
            grants
            == {"userSettings": {"globalPermissionGrants": {k: cli[k] for k in ("allow", "deny", "ask")}}}
            and list(grants["userSettings"]["globalPermissionGrants"]) == ["allow", "deny", "ask"]
            and not list(config.glob("config.json.bak-*"))
        ),
        f"a new config/config.json holds userSettings.globalPermissionGrants alone, its allow, deny and ask the "
        f"rules of the CLI's permissions, and no backup is made: {list(grants)}",
    )
    code, text = run(base, "--apply")
    case(
        lambda: (
            code == 0
            and dict(line.findall(text)) == dict.fromkeys(want, "already")
            and not list((gemini / "antigravity-cli").glob("settings.json.bak-*"))
            and not list(config.glob("config.json.bak-*"))
        ),
        f"a second --apply finds every file identical and makes no backup: {code}, {dict(line.findall(text))}",
    )


def instruction_cases(scratch):
    """The global file, the always-on files, the rules and the skills: their sizes, their paths,
    their frontmatter, the delta, the files with no source, and the refusals."""
    from harness.install_cases import RULE_HEAD, rule_names, skill_names

    case, run, tail, mode = scratch.case, scratch.run, scratch.tail, scratch.mode
    base, claude, tree = scratch.fresh(["instructions/research-tree.md", "rules/meta-repository.md"])
    gemini = base / "home" / ".gemini"
    gemini.mkdir()
    # Under a umask of 077 a file written with no mode is 0600, where the Claude Code layer writes its
    # skill files 0644, so the mode case below sees a mode that the plan drops.
    umask = os.umask(0o077)
    try:
        code, text = run(base, "--apply")
    finally:
        os.umask(umask)
    if code != 0:
        case(
            lambda: False,
            f"the setup install --apply of the Antigravity instruction cases exits {code}: "
            f"{tail(text)!r}; the cases after it do not run",
        )
        return
    config = gemini / "config"
    if not (config / "GEMINI.md").is_file():
        case(
            lambda: False,
            "the setup install --apply of the Antigravity instruction cases writes "
            "~/.gemini/config/GEMINI.md; the cases after it do not run",
        )
        return
    rules = sorted((config / "rules").glob("*.md"))
    sizes = {p.name: len(p.read_bytes()) for p in [config / "GEMINI.md", *rules]}
    case(
        lambda: (
            len(sizes) == 5 + len(rule_names(REPO / "rules"))
            and max(sizes.values()) < 24000
            and sum(sizes.values()) < 20000 * 4
            and not [
                n
                for n in sizes
                if b"@[" in (config / "rules" / n if n != "GEMINI.md" else config / n).read_bytes()
            ]
        ),
        f"each installed instruction file and rule is below 24,000 bytes, holds no include, and their sum is below "
        f"20,000 tokens at 4 bytes a token: {sum(sizes.values())} bytes, {sizes}",
    )

    # Each text but the global file names Antigravity's copies; a ~/.claude/ path that is left names
    # Claude Code itself, outside the roots that Antigravity copies.
    texts = [p for p in config.rglob("*.md") if p != config / "GEMINI.md"]
    hits = [
        (p.relative_to(config).as_posix(), line)
        for p in texts
        for line in p.read_text(encoding="utf-8").splitlines()
        if "~/.claude/" in line
    ]
    shared = [h for h in hits if any(root in h[1] for root in frontends.SHARED_ROOTS)]
    moved = [p for p in texts if "~/.gemini/config/rules/" in p.read_text(encoding="utf-8")]
    case(
        lambda: not shared and hits and moved,
        f"a grep of the rendered set for ~/.claude/ finds only the lines that name Claude Code itself, "
        f"{len(hits)} of them, and none of frontends.SHARED_ROOTS; {len(moved)} texts name ~/.gemini/config/rules/: "
        f"{shared[:3]}",
    )

    # A rule's `paths` becomes Antigravity's glob trigger, and the delta lists the rule with its scope.
    source = (REPO / "rules" / "julia-code.md").read_bytes()
    end = source.index(b"\n---\n", 3)
    description = re.findall(rb"^description: (.*)$", source[:end], re.M)[0].decode()
    installed = (config / "rules" / "julia-code.md").read_bytes()
    case(
        lambda: (
            installed
            == (
                f'---\ntrigger: glob\nglobs: "**/*.jl"\ndescription: {json.dumps(description)}'.encode()
                + relocate(source[end:], "~/.gemini/config")
            )
        ),
        f"rules/julia-code.md reads back as trigger: glob, globs **/*.jl, its description and its body: "
        f"{installed[:120]!r}",
    )
    several = (config / "rules" / "instruction-files.md").read_text().split("\n")[:3]
    case(
        lambda: (
            several
            == [
                "---",
                "trigger: glob",
                'globs: "**/CLAUDE.md, **/SKILL.md, **/agents/*.md, **/rules/*.md, **/AGENTS.md"',
            ]
        ),
        f"a rule of several paths has them as one `globs`, joined by `, `: {several}",
    )
    delta = (SOURCE / "ANTIGRAVITY-DELTA.md").read_text()
    unlisted = [n for n in rule_names(REPO / "rules") if f"| `{n}` |" not in delta]
    case(
        lambda: not unlisted and "| `meta-repository.md` |" in delta and "~/.gemini/config/rules/" in delta,
        f"ANTIGRAVITY-DELTA.md lists each rule of rules/ and meta-repository.md with its scope: {unlisted}",
    )
    core = (config / "rules" / "core.md").read_bytes()
    case(
        lambda: (
            core
            == b"---\ntrigger: always_on\n---\n\n"
            + relocate((REPO / "instructions" / "core.md").read_bytes(), "~/.gemini/config")
            and (config / "rules" / "RTK.md")
            .read_bytes()
            .startswith(b"---\ntrigger: always_on\n---\n\n# RTK")
            and (config / "rules" / "research-tree.md").read_bytes()
            == b"---\ntrigger: always_on\n---\n\n" + (tree / "instructions" / "research-tree.md").read_bytes()
        ),
        f"the core, RTK.md and the tree instructions are rules with trigger: always_on: {core[:60]!r}",
    )

    # A skill keeps `name` and `description` and drops `model`; its own files go beside it, with their modes.
    skill = (config / "skills" / "build-part" / "SKILL.md").read_text()
    head = skill.split("\n---\n", 1)[0].splitlines()[1:]
    keys = [l.split(":", 1)[0] for l in head if not l.startswith(" ")]
    case(
        lambda: keys == ["name", "description"] and head[0] == "name: build-part",
        f"skills/build-part/SKILL.md keeps name and description and drops model: {keys}",
    )
    heads = {
        p.parent.name: p.read_text().split("\n---\n", 1)[0] for p in (config / "skills").glob("*/SKILL.md")
    }
    case(
        lambda: (
            sorted(heads) == skill_names(REPO / "skills")
            and all(
                re.search(r"(?m)^name: ", h)
                and re.search(r"(?m)^description: ", h)
                and not re.search(r"(?m)^model:", h)
                for h in heads.values()
            )
            and "disable-model-invocation: true" in heads["wait-what"]
        ),
        f"every SKILL.md keeps name and description, drops model, and keeps every other key: {sorted(heads)}",
    )
    own = [f for f in skills_files() if not f.endswith("/SKILL.md")]
    case(
        lambda: (
            own
            and all(
                (config / "skills" / f).read_bytes()
                == relocate((claude / "skills" / f).read_bytes(), "~/.gemini/config")
                and mode(config / "skills" / f) == mode(claude / "skills" / f)
                for f in own
            )
        ),
        f"a skill's own files install beside its SKILL.md, with their modes: {own}",
    )

    # The delta states Antigravity's facts, is the global file, and is no larger than OpenCode's.
    size = len((SOURCE / "ANTIGRAVITY-DELTA.md").read_bytes())
    case(
        lambda: (
            size <= len((REPO / "adapters" / "opencode" / "OPENCODE-DELTA.md").read_bytes())
            and (config / "GEMINI.md").read_bytes() == (SOURCE / "ANTIGRAVITY-DELTA.md").read_bytes()
            and all(
                s in delta
                for s in [
                    "sandbox",
                    "config/hooks/guard",
                    "No RTK rewrite",
                    "git worktree add",
                    "~/Research/.worktrees/",
                    "invoke_subagent",
                    "effort",
                    "CLAUDE.md",
                ]
            )
        ),
        f"ANTIGRAVITY-DELTA.md is ~/.gemini/config/GEMINI.md, states the facts of the delta, and is no larger "
        f"than OPENCODE-DELTA.md: {size} bytes",
    )

    # An installed file with no source below the paths that the layer owns is EXTRA; Antigravity's
    # own files are neither listed nor touched.
    strays = [
        config / "rules" / "stray.md",
        config / "skills" / "gone" / "SKILL.md",
        config / "skills" / "build-part" / "old.md",
        config / "hooks" / "old.py",
        config / "skills" / "loose.md",
        config / "agents" / "gone.md",
    ]
    theirs = [
        gemini / "antigravity" / "x.json",
        config / "projects" / "p.json",
        config / "plugins" / "p" / "x.md",
        config / "rules" / ".DS_Store",
    ]
    for p in strays + theirs:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    code, text = run(base)
    extra = re.findall(r"^EXTRA: (\S+) .*\n\s+To remove it:\s+(.*)$", text, re.M)
    case(
        lambda: (
            code == 0
            and sorted(extra)
            == sorted(
                [
                    (str(config / "rules" / "stray.md"), f"rm '{config / 'rules' / 'stray.md'}'"),
                    (str(config / "skills" / "gone"), f"rm -r '{config / 'skills' / 'gone'}'"),
                    (
                        str(config / "skills" / "build-part" / "old.md"),
                        f"rm '{config / 'skills' / 'build-part' / 'old.md'}'",
                    ),
                    (str(config / "hooks" / "old.py"), f"rm '{config / 'hooks' / 'old.py'}'"),
                    (str(config / "skills" / "loose.md"), f"rm '{config / 'skills' / 'loose.md'}'"),
                    (str(config / "agents" / "gone.md"), f"rm '{config / 'agents' / 'gone.md'}'"),
                ]
            )
            and all(p.read_text() == "x\n" for p in strays + theirs)
        ),
        f"a file with no source below rules/, skills/, hooks/ or agents/ is EXTRA with its removal command, and "
        f"antigravity/, projects/, plugins/ and a hidden file are not listed: {code}, {extra}",
    )
    case(
        lambda: (
            render_skill(b"---\nname: s\nmodel: large\n---\n\nmodel: kept\n")
            == b"---\nname: s\n---\n\nmodel: kept\n"
            and render_skill(b"no frontmatter\nmodel: kept\n") == b"no frontmatter\nmodel: kept\n"
        ),
        "render_skill drops a `model:` line of the frontmatter only, and leaves a text with no frontmatter",
    )
    case(
        lambda: (
            render_skill(b"---\r\nname: s\r\nmodel: large\r\n---\r\n\r\nmodel: kept\r\n")
            == b"---\r\nname: s\r\n---\r\n\r\nmodel: kept\r\n"
            and render_skill(b"---\nmodel: kept\n") == b"---\nmodel: kept\n"
            and render_skill(b"x\n---\nmodel: kept\n---\n") == b"x\n---\nmodel: kept\n---\n"
        ),
        "render_skill drops the `model:` line of a SKILL.md with CRLF line ends too, and leaves a text whose "
        "frontmatter does not close or does not open on line 1",
    )
    crlf = [
        ("glob", b'---\r\npaths: ["**/*.jl"]\r\ndescription: A CRLF rule.\r\n---\r\n\r\nbody\r\n'),
        ("always", b"---\r\ndescription: A CRLF rule.\r\n---\r\n\r\nbody\r\n"),
    ]
    case(
        lambda: (
            [render_rule(pathlib.Path(f"{name}.md"), data) for name, data in crlf]
            == [
                b'---\ntrigger: glob\nglobs: "**/*.jl"\ndescription: "A CRLF rule."\n---\r\n\r\nbody\r\n',
                b'---\ntrigger: always_on\ndescription: "A CRLF rule."\n---\r\n\r\nbody\r\n',
            ]
        ),
        "a rule with CRLF line ends, which oh-my-pi's grammar accepts, renders with the trigger of one with LF "
        "and keeps its closing line and body",
    )
    # RTK.md and the files of instructions/ are rules of rules/, so a text names them there.
    case(
        lambda: (
            relocate(
                b"~/.claude/RTK.md ~/.claude/instructions/core.md ~/.claude/rules/x.md "
                b"~/.claude/skills/a/SKILL.md",
                "~/.gemini/config",
            )
            == b"~/.gemini/config/rules/RTK.md ~/.gemini/config/rules/core.md ~/.gemini/config/rules/x.md "
            b"~/.gemini/config/skills/a/SKILL.md"
        ),
        "relocate names RTK.md and a file of instructions/ in rules/, and the other roots at the same path",
    )
    base, claude, tree = scratch.fresh(["rules/names.md", "instructions/names-too.md"])
    named = "see ~/.claude/RTK.md and ~/.claude/instructions/core.md\n"
    (tree / "rules" / "names.md").write_text(RULE_HEAD + named)
    (tree / "instructions" / "names-too.md").write_text(named)
    (base / "home" / ".gemini").mkdir()
    code, text = run(base, "--apply")
    out = base / "home" / ".gemini" / "config" / "rules"
    got = [(out / n).read_text() if (out / n).is_file() else None for n in ("names.md", "names-too.md")]
    case(
        lambda: (
            code == 0
            and all(
                g is not None
                and g.endswith("see ~/.gemini/config/rules/RTK.md and ~/.gemini/config/rules/core.md\n")
                for g in got
            )
        ),
        f"an installed rule and an always-on file name RTK.md and instructions/core.md in rules/: {code}, {got}",
    )
    # A skill of the tree instructions: its SKILL.md loses `model:`, its other files keep their
    # frontmatter, and a text that is no `.md` keeps its ~/.claude/ paths.
    base, claude, tree = scratch.fresh(["skills/s/SKILL.md", "skills/s/notes.md", "skills/s/run.sh"])
    (tree / "skills" / "s" / "SKILL.md").write_text(
        "---\nname: s\nmodel: large\ndescription: d\n---\n~/.claude/rules/x.md\n"
    )
    (tree / "skills" / "s" / "notes.md").write_text(
        "---\nmodel: kept\n---\n~/.claude/rules/x.md ~/.claude/RTK.md\n"
    )
    (tree / "skills" / "s" / "run.sh").write_text("cat ~/.claude/rules/x.md\n")
    (base / "home" / ".gemini").mkdir()
    code, text = run(base, "--apply")
    s = base / "home" / ".gemini" / "config" / "skills" / "s"
    got = [(s / n).read_text() if (s / n).is_file() else None for n in ("SKILL.md", "notes.md", "run.sh")]
    case(
        lambda: (
            code == 0
            and got
            == [
                "---\nname: s\ndescription: d\n---\n~/.gemini/config/rules/x.md\n",
                "---\nmodel: kept\n---\n~/.gemini/config/rules/x.md ~/.gemini/config/rules/RTK.md\n",
                "cat ~/.claude/rules/x.md\n",
            ]
        ),
        f"a tree skill's SKILL.md drops model:, its own .md file keeps its frontmatter, each .md names "
        f"Antigravity's copies, and a script stays as it is: {code}, {got}",
    )
    # A file in a subdirectory of instructions/ and a file of rules/ that is no `.md` are neither
    # always-on files nor rules.
    base, claude, tree = scratch.fresh(["instructions/sub/x.md", "rules/tool.sh"])
    (base / "home" / ".gemini").mkdir()
    code, text = run(base)
    listed = re.findall(r"^antigravity/config/rules/(\S+)\s", text, re.M)
    case(
        lambda: (
            code == 1
            and (claude / "instructions" / "sub" / "x.md").exists() is False
            and re.search(r"^~/.claude/instructions/sub/x\.md\s+INSTALL$", text, re.M)
            and "x.md" not in listed
            and "tool.sh" not in listed
            and "core.md" in listed
        ),
        f"instructions/sub/x.md and rules/tool.sh install no Antigravity rule: {code}, {listed}",
    )

    # The refusals, before anything is written: a rule of 25,000 bytes, and a rule whose name is
    # that of an always-on file.
    for name, data, why in [
        ("rules/big.md", RULE_HEAD + "x" * 25000 + "\n", "24,000 bytes"),
        ("rules/core.md", RULE_HEAD + "a rule named as the core\n", "two sources"),
    ]:
        base, claude, tree = scratch.fresh([name])
        (tree / name).write_text(data)
        (base / "home" / ".gemini").mkdir()
        snapshot = scratch.snapshot(base / "home")
        code, text = run(base, "--apply")
        case(
            lambda: (
                scratch.refused(code, text)
                and why in text
                and "rules/" + name.split("/")[1] in text
                and scratch.snapshot(base / "home") == snapshot
            ),
            f"a tree rule {name} of {len(data)} bytes exits 2 with `{why}`, and nothing is written: {code}, "
            f"{tail(text)!r}",
        )
    # A rule with no `paths` loads always, as in Claude Code.
    base, claude, tree = scratch.fresh(["rules/always.md"])
    (tree / "rules" / "always.md").write_text("---\ndescription: A rule with no paths.\n---\n\nbody\n")
    (base / "home" / ".gemini").mkdir()
    code, text = run(base, "--apply")
    installed = base / "home" / ".gemini" / "config" / "rules" / "always.md"
    case(
        lambda: (
            code == 0
            and installed.read_text()
            == '---\ntrigger: always_on\ndescription: "A rule with no paths."\n---\n\nbody\n'
        ),
        f"a rule with no paths is installed with trigger: always_on: {code}, {tail(text)!r}",
    )

    # The bounds of the size check, exactly at the cap and at the budget.
    def refused(texts):
        try:
            check_sizes(texts)
            return None
        except HarnessError as e:
            return str(e)

    glob = GLOB_RULE + b'globs: "**/*.py"\n---\n'
    on = b"---\ntrigger: always_on\n---\n"
    cases = [
        ([("a", b"x" * 23999)], None),
        ([("a", b"x" * 24000)], "a: 24000 bytes"),
        ([(str(i), b"x" * 19999) for i in range(4)] + [("e", b"x" * 3)], None),
        ([(str(i), b"x" * 20000) for i in range(4)], "80000 bytes"),
        ([(str(i), on + b"x" * (20000 - len(on))) for i in range(4)], "80000 bytes"),
        ([(str(i), b"x" * 20000) for i in range(3)] + [("g", glob + b"x" * 20000)], None),
        ([("g", glob + b"x" * (24000 - len(glob)))], "g: 24000 bytes"),
        ([("a", b"x @[label](path) y")], "a holds an include"),
        ([("g", glob + b"x @[label](path) y")], "g holds an include"),
        ([("a", b"x @[label] (path) y")], None),
    ]
    got = [refused(t) for t, _ in cases]
    case(
        lambda: all(
            (g is None) if w is None else (g is not None and w in g) for g, (_, w) in zip(got, cases)
        ),
        f"a file of 23,999 bytes passes and one of 24,000 exits 2; a sum of 79,999 bytes passes and one of 80,000 "
        f"exits 2, always-on rules counted; a glob rule is not in the sum, and one of 24,000 bytes or with an "
        f"include exits 2; a text with an include `@[…](…)` exits 2, and one with `@[…]` alone passes: {got}",
    )
    src = REPO / "rules" / "python-code.md"
    rendered = render_rule(src, src.read_bytes())
    case(
        lambda: rendered.startswith(GLOB_RULE),
        f"render_rule gives a rule with paths the first lines that check_sizes leaves out: {rendered[:40]!r}",
    )


def skills_files():
    """The files of skills/ of this repository, relative to it."""
    return [f.as_posix() for f in install.source_files(REPO / "skills")]


def _path_list() -> types.ModuleType:
    """The guard's path-list check, hooks/guard/path_list.py, as a module of the package `guard`,
    imported with the directory that holds the package first on `sys.path` for the import alone."""
    sys.path.insert(0, str(REPO / "hooks"))
    try:
        return importlib.import_module("guard.path_list")
    finally:
        sys.path.remove(str(REPO / "hooks"))


def rule_cases(case):
    """The rules against their sources, entry by entry, with the dummy profile."""
    from harness.install_cases import scratch_profile

    claude = frontends.adapter("claude")
    with tempfile.TemporaryDirectory() as tmp:
        profile = profile_module.load(scratch_profile(pathlib.Path(tmp) / "profile.toml", tmp))
        cfg = claude.settings_template(profile, pathlib.Path(tmp) / "network.toml")
    rules, dropped = render_permissions(cfg, profile)
    reasons = {(key, entry): reason for key, entry, reason in dropped}
    h = profile.home
    extras = [
        f"read_file({h}/.gemini/config/mcp_config.json)",
        f"write_file({h}/.gemini/config/hooks.json)",
        f"write_file({h}/.gemini/config/hooks)",
        f"write_file({h}/.gemini/config/guard-paths.json)",
        f"write_file({h}/.gemini/antigravity-cli/settings.json)",
        f"write_file({h}/.gemini/config/mcp_config.json)",
    ]
    # Each Kaimon tool of the template, `mcp__kaimon__<tool>`, as the rule `mcp(kaimon/<tool>)`.
    kaimon = {
        key: [
            "mcp(kaimon/" + e.removeprefix("mcp__kaimon__") + ")"
            for e in cfg["permissions"][key]
            if e.startswith("mcp__kaimon__")
        ]
        for key in LISTS
    }
    # The first word of each command that Claude Code runs outside its sandbox, once each, in the
    # template's order, as a `command(<word>)` rule.
    unsandboxed = []
    for e in cfg["sandbox"]["excludedCommands"]:
        if f"command({e.split()[0]})" not in unsandboxed:
            unsandboxed.append(f"command({e.split()[0]})")
    wrong = []
    for key in LISTS:
        out = iter(rules[key])
        for entry in cfg["permissions"][key]:
            if (key, entry) in reasons or entry.startswith("mcp__kaimon__"):
                continue
            got = next(out, None)
            if m := re.fullmatch(r"Bash\((.*)\)", entry, re.S):
                body = m.group(1)
                sample = body.replace("*", "zz")
                ok = got is not None and rule_matches(got, sample) and not rule_matches(got, "zz" + sample)
                if p := re.fullmatch(r"([^*]*[^*\s]) \*", body):
                    ok = ok and got == f"command({p.group(1)})"
                elif "*" not in body:
                    ok = ok and not rule_matches(got, sample + " zz")
                if got is not None and got.startswith("command(regex:"):
                    ok = ok and bash_rule_cases(key, body, got)
            elif m := re.fullmatch(r"(Read|Edit)\((.*)\)", entry, re.S):
                path = re.sub(r"^//+", "/", m.group(2)).removesuffix("/**")
                ok = got == f"{'read_file' if m.group(1) == 'Read' else 'write_file'}({path})"
            else:
                host = re.fullmatch(r"WebFetch\(domain:(.*)\)", entry)
                ok = host is not None and key == "allow" and got == f"read_url({host.group(1)})"
            if not ok:
                wrong.append((key, entry, got))
        rest = list(out)
        held = rules[key][: len(rules[key]) - len(rest)]
        after = [r for r in unsandboxed if r not in held] if key == "allow" else []
        if rest != [*{"deny": extras}.get(key, []), *kaimon[key], *after]:
            wrong.append((key, "after the template's entries", rest))
    case(
        lambda: not wrong and rules["allow"] and rules["ask"] and rules["deny"],
        f"each Bash, Read and Edit entry and each allow host is one rule in its list, in order, that matches the "
        f"entry's lines or names its path; after them, mcp_config.json is a read_file deny, the files of the "
        f"layer and mcp_config.json are write_file denies, then each Kaimon tool of the list is its "
        f"mcp(kaimon/<tool>) rule, in the template's order, and last in `allow` each command(<word>) of the "
        f"template's excludedCommands that the list does not hold: {wrong[:5]}",
    )
    case(
        lambda: (
            unsandboxed[:3] == ["command(gh)", "command(git)", "command(glab)"]
            and all(rules["allow"].count(r) == 1 for r in unsandboxed)
            and not [r for key in ("deny", "ask") for r in rules[key] if r in unsandboxed]
            and not [r for key in LISTS for r in rules[key] if r.startswith("unsandboxed(")]
        ),
        f"each first word of the template's excludedCommands, {unsandboxed}, is one command(<word>) rule of "
        f"`allow`, and no deny, ask or unsandboxed(…) rule: {rules['allow'][-6:]}",
    )
    case(
        lambda: (
            {key: len(kaimon[key]) for key in LISTS} == {"deny": 7, "ask": 5, "allow": 27}
            and {"mcp(kaimon/ping)", "mcp(kaimon/ex)"} <= set(rules["allow"])
            and not [r for key in LISTS for r in rules[key] if r.startswith("mcp(") and "*" in r]
        ),
        f"the template's 27 Kaimon allows, 7 denies and 5 asks are rules, ping and ex among the allows, and no "
        f"mcp rule is a wildcard: { {key: [r for r in rules[key] if r.startswith('mcp(')][:3] for key in LISTS} }",
    )
    bash = {key: [e for e in cfg["permissions"][key] if e.startswith("Bash(")] for key in LISTS}
    # The rules of excludedCommands that no Bash allow of the template, `Bash(<word> *)`, renders.
    added = {
        "deny": 0,
        "ask": 0,
        "allow": len([r for r in unsandboxed if f"Bash({r[len('command(') : -1]} *)" not in bash["allow"]]),
    }
    case(
        lambda: (
            not [d for d in dropped if d[1].startswith("Bash(")]
            and all(
                sum(r.startswith("command(") for r in rules[key]) == len(bash[key]) + added[key]
                for key in LISTS
            )
        ),
        f"every Bash entry becomes a command rule, and `allow` holds the rules of excludedCommands besides: "
        f"{ {key: (len(bash[key]), added[key], sum(r.startswith('command(') for r in rules[key])) for key in LISTS} }",
    )
    recursive = [e for key, e, _ in dropped if key == "deny" and e.startswith("Read(**/")]
    paths = json_value(guard_paths(profile), "guard-paths.json")["deny"]
    case(
        lambda: recursive and all(e[len("Read(") : -1] in paths for e in recursive),
        f"each dropped Read(**/X) deny is in the guard's path list: {recursive}",
    )
    lists = json_value(guard_paths(profile), "guard-paths.json")
    covered = [
        (key, e)
        for key, e, _ in dropped
        if e.startswith("Edit(")
        and re.sub(r"^//+", "/", e[len("Edit(") : -1]) not in lists["edit" if key == "deny" else "ask"]
    ]
    case(
        lambda: not covered and any(e.startswith("Edit(") for _, e, _ in dropped),
        f"each dropped Edit deny is in the guard's `edit` list, and each dropped Edit ask in its `ask` list: "
        f"{covered}",
    )
    others = [(key, e) for key, e, _ in dropped if not re.match(r"(Bash|Read|Edit)\(", e)]
    case(
        lambda: (
            all(not re.fullmatch(r"WebFetch\(domain:.*\)", e) or key != "allow" for key, e in others)
            and all(reasons[d] for d in reasons)
        ),
        f"every entry that is dropped has a reason, and no allow host is among them: {others[:3]}",
    )
    expected = [
        (key, e)
        for key in LISTS
        for e in cfg["permissions"][key]
        if (m := re.fullmatch(r"(?:Read|Edit)\(/*(.*?)(?:/\*\*)?\)", e, re.S))
        and re.search(r"[*?\[]", m.group(1))
    ]
    got_drops = [(key, e) for key, e, _ in dropped if re.match(r"(Read|Edit)\(", e)]
    case(
        lambda: got_drops == expected,
        f"the dropped Read and Edit entries are exactly those whose path keeps a glob: {got_drops}",
    )
    globbed = [r for key in LISTS for r in rules[key] if re.match(r"(read_file|write_file)\(.*[*?\[]", r)]
    case(lambda: not globbed, f"no read_file or write_file rule holds a glob: {globbed[:3]}")
    small = {
        "permissions": {
            "deny": ["WebFetch(domain:x.org)", "Read(src/x)", "Edit(//a/*.py)", "Edit(//a/b/**)"],
            "allow": [
                "mcp__kaimon__ex",
                "WebFetch(domain:y.org)",
                "mcp__k__ping",
                "mcp__kaimon",
                "mcp__kaimon__*",
            ],
            "ask": ["mcp__kaimon__debug_eval"],
        }
    }
    rendered = render_permissions(small, profile)
    case(
        lambda: (
            rendered[0]
            == {
                "deny": ["write_file(/a/b)", *extras],
                "ask": ["mcp(kaimon/debug_eval)"],
                "allow": ["read_url(y.org)", "mcp(kaimon/ex)"],
            }
            and [e for _, e, _ in rendered[1]]
            == [
                "WebFetch(domain:x.org)",
                "Read(src/x)",
                "Edit(//a/*.py)",
                "mcp__k__ping",
                "mcp__kaimon",
                "mcp__kaimon__*",
            ]
        ),
        f"a WebFetch deny, a relative path, a glob in a path, another server's MCP tool and a Kaimon entry that "
        f"names no tool are dropped; an allow host is a read_url rule, and a Kaimon tool is its mcp rule after "
        f"the others, in its list: {rendered}",
    )
    allows = {"allow": ["Bash(ps *)", "mcp__kaimon__ex"]}
    sandboxes = [
        ({}, []),
        ({"sandbox": {}}, []),
        ({"sandbox": {"excludedCommands": []}}, []),
        (
            {"sandbox": {"excludedCommands": ["git *", "gh", "git", "ps", "ps *", "glab x"]}},
            ["command(git)", "command(gh)", "command(glab)"],
        ),
    ]
    got = [
        render_permissions({"permissions": allows, **extra}, profile)[0]["allow"] for extra, _ in sandboxes
    ]
    case(
        lambda: got == [["command(ps)", "mcp(kaimon/ex)", *after] for _, after in sandboxes],
        f"with no sandbox, no excludedCommands or an empty one, `allow` gets no rule; else each first word once, "
        f"in the order of excludedCommands, after the Kaimon rules, and none that the list holds: {got}",
    )
    examples = {
        ("deny", "Bash(sed -i* *)"): r"command(regex:^sed -i.*(?: .*)?$)",
        ("deny", "Bash(git push * -f)"): r"command(regex:^git push .* -f$)",
        ("deny", "Bash(git -C * add .)"): r"command(regex:^git -C .* add \.$)",
        ("allow", "Bash(git status)"): r"command(regex:^git status$)",
        ("allow", "Bash(git log *)"): "command(git log)",
        ("allow", "Bash(git branch * -f)"): r"command(regex:^git branch [^;&|\n`$()<>]* -f$)",
        ("deny", r"Bash(x * \.^$|?+()[]{} *)"): r"command(regex:^x .* \\\.\^\$\|\?\+\(\)\[\]\{\}(?: .*)?$)",
    }
    case(
        lambda: all(
            command_rule(e[len("Bash(") : -1], key == "allow") == want for (key, e), want in examples.items()
        ),
        f"the decided forms: {[(e, command_rule(e[len('Bash(') : -1], key == 'allow')) for (key, e) in examples]}",
    )
    case(
        lambda: (
            rule_matches("command(git push --force)", "git push --force origin x")
            and not rule_matches("command(git push --force)", "git push --force-with-lease")
            and rule_matches(command_rule("git push --force*"), "git push --force-with-lease")
        ),
        "a prefix rule matches whole words, and a regex rule any text in place of a *",
    )
    branch, sed = command_rule("git branch * -f", allow=True), command_rule("sed -i* *")
    case(
        lambda: (
            rule_matches(branch, "git branch topic -f")
            and not rule_matches(branch, "git branch x -f; rm -rf ~/y")
            and not rule_matches(branch, "git branch $(rm -rf ~/x) -f")
            and rule_matches(sed, "sed -i 's/a;b/c/' f")
            and rule_matches(command_rule("git -C * reset --hard *"), "git -C . reset --hard")
        ),
        "an allow regex rule stays in one segment, a deny regex rule does not, and a trailing * matches nothing too",
    )
    lists = json_value(guard_paths(profile), "guard-paths.json")
    # `git push  *` is a body of one literal part with a trailing ` *`, a form that no template body
    # has: each such body is a prefix body.
    matcher_cases(case, [*lists["bash_deny"], *lists["bash_ask"], "git push  *"])


def reference_matcher(body, word_break):
    """The matcher of `Bash(body)` that the cases hold the path list's against, a regular expression:
    `Bash(x *)` when the words of `x` are a run of the words, any other body when its pattern
    full-matches the words from one of them to the last, joined by `word_break`, with `*` as any
    text and a trailing ` *` as no text too. Its cost grows with the square of the number of words,
    so the cases give it short lists only."""
    if m := re.fullmatch(r"([^*]*[^*\s]) \*", body, re.S):
        x = m.group(1).split()
        return lambda w: any(w[i : i + len(x)] == x for i in range(len(w)))
    head, tail = (body[:-2], f"(?:{word_break}.*)?") if body.endswith(" *") else (body, "")
    literal = (word_break.join(map(re.escape, re.split(r"\s+", part))) for part in head.split("*"))
    pattern = re.compile(".*".join(literal) + tail, re.S)
    return lambda w: any(pattern.fullmatch(word_break.join(w[i:])) for i in range(len(w)))


def matcher_cases(case, bodies):
    """The path list's matcher of each Bash body against reference_matcher, on a fixed set of word lists
    of up to 8 words for each body: the body with each `*` filled by nothing, `x`, `zz` or one of
    the body's own literal words, with up to two words put before it and after it and at times one
    word replaced; and lists drawn from the body's literal words, each also with `zz` before or
    after it, `x`, `zz` and the empty word."""
    try:
        total, matching, differ = compare_matchers(bodies)
    except (
        OSError,
        ImportError,
        SyntaxError,
        AttributeError,
        LookupError,
        TypeError,
        ValueError,
        re.error,
    ) as e:  # a case that crashes is BAD, and the next case still runs
        case(
            lambda: False, f"the path list's matcher of each Bash deny and ask runs: {type(e).__name__}: {e}"
        )
        return
    case(
        lambda: not differ and 0 < matching < total,
        f"the path list's matcher of each Bash deny and ask decides as the reference regex on each of "
        f"{total} word "
        f"lists, {matching} of them matching: {differ[:3]}",
    )


def compare_matchers(bodies):
    """(lists, lists that match, [(body, words, the reference's answer)] where the path list's matcher
    differs) of matcher_cases."""
    guard = _path_list()
    total = matching = 0
    differ = []
    for body in bodies:
        rng = random.Random(body)
        pieces = [p for p in re.split(r"[\s*]+", body) if p]
        tokens = sorted({*pieces, *(p + "zz" for p in pieces), *("zz" + p for p in pieces), "x", "zz", ""})
        fills = ["", "x", "zz", " x ", " zz ", *(f" {p} " for p in pieces)]
        lists = [body.replace("*", "zz").split(), body.replace("*", "").split()]
        for _ in range(300):
            w = re.sub(r"\*", lambda _: rng.choice(fills), body).split()
            w = [rng.choice(tokens) for _ in range(rng.randint(0, 2))] + w
            w += [rng.choice(tokens) for _ in range(rng.randint(0, 2))]
            if rng.random() < 0.3:
                w[rng.randrange(len(w))] = rng.choice(tokens)
            lists.append(w)
        lists += [[rng.choice(tokens) for _ in range(rng.randint(1, 8))] for _ in range(100)]
        new, old = guard.bash_matcher(body), reference_matcher(body, guard.WORD_BREAK)
        for w in (w for w in lists if len(w) <= 8):
            want = old(w)
            total, matching = total + 1, matching + want
            if new(w, guard.WORD_BREAK.join(w)) != want:
                differ.append((body, w, want))
    return total, matching, differ


# The characters that a regular expression reads as special, but `*`, written out here so that the
# cases do not take them from the code that they check.
SPECIAL = "\\.^$|?+()[]{}"


def escaped_rule(key, body):
    """The regex rule of the Bash entry `body` in the list `key`, built from SPECIAL: each literal
    part with every character of SPECIAL escaped, the parts joined by `.*`, or in `allow` by the
    class of SEGMENT_TEXT, written out, and a trailing ` *` as an optional space and text."""
    star = r"[^;&|\n`$()<>]*" if key == "allow" else ".*"
    head, tail = (body[:-2], f"(?: {star})?") if body.endswith(" *") else (body, "")
    parts = ("".join("\\" + c if c in SPECIAL else c for c in part) for part in head.split("*"))
    return f"command(regex:^{star.join(parts)}{tail}$)"


def bash_rule_cases(key, body, rule):
    """Whether the regex rule `rule` of the Bash entry `body` in the list `key` is the text that
    escaped_rule gives, and matches as the entry does: with nothing in place of a trailing ` *`,
    never with another character in place of a character of SPECIAL, and, in `allow`, never across
    a segment; in `deny` and `ask` across one."""
    if rule != escaped_rule(key, body):
        return False
    head = body[:-2] if body.endswith(" *") else None
    if head is not None and (
        not rule_matches(rule, head.replace("*", "zz"))
        or (not head.endswith("*") and rule_matches(rule, head.replace("*", "zz") + "zz"))
    ):
        return False
    for i, c in enumerate(body):
        other = (body[:i] + "Q" + body[i + 1 :]).replace("*", "zz")
        if c in SPECIAL and rule_matches(rule, other):
            return False
    if "*" in body:
        crossing = body.replace("*", "zz; rm x", 1).replace("*", "zz")
        return rule_matches(rule, crossing) == (key != "allow")
    return True


def merge_cases(scratch):
    """The merge of the CLI's settings: the three keys only, the rest kept, a backup, a missing
    file created, and exit 2 before any write on a file that is not a JSON object."""
    case, run, tail = scratch.case, scratch.run, scratch.tail
    base, _, _ = scratch.fresh()
    cli = base / "home" / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    settings = cli / "settings.json"
    own = {
        "theme": "dark",
        "permissions": {"allow": ["command(ls)"]},
        "toolPermission": "always-ask",
        "nested": {"a": [1, 2]},
        "allowNonWorkspaceAccess": False,
    }
    settings.write_text(json.dumps(own, indent=4) + "\n")
    before = settings.read_bytes()
    code, text = run(base, "--apply")
    merged = json_value(settings.read_text(), "settings.json")
    backups = list(cli.glob("settings.json.bak-*"))
    case(
        lambda: (
            code == 0
            and list(merged) == list(own) + ["enableTerminalSandbox"]
            and {k: merged[k] for k in ("theme", "nested", "allowNonWorkspaceAccess")}
            == {k: own[k] for k in ("theme", "nested", "allowNonWorkspaceAccess")}
            and merged["toolPermission"] == "proceed-in-sandbox"
            and merged["permissions"]["allow"] != ["command(ls)"]
        ),
        f"--apply sets the three keys, keeps every other key and the order of the keys: {code}, {list(merged)}, "
        f"{tail(text)}",
    )
    case(
        lambda: len(backups) == 1 and backups[0].read_bytes() == before,
        f"--apply keeps a backup of the file it replaces, with its bytes: {backups}",
    )
    text = settings.read_text()
    case(
        lambda: text.split("\n")[1].startswith('    "theme"'),
        f"--apply keeps the file's indent of 4: {text.split(chr(10))[1]!r}",
    )

    base, _, _ = scratch.fresh()
    cli = base / "home" / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    (cli / "settings.json").write_text('{"name": "\\ud800", "dash": "—"}\n', encoding="utf-8")
    code, text = run(base, "--apply")
    written = (cli / "settings.json").read_text(encoding="utf-8")
    case(
        lambda: code == 0 and '"name": "\\ud800"' in written and '"dash": "—"' in written,
        f"a lone surrogate stays an escape, and a non-ASCII character stays as it is: {code}, {tail(text)!r}",
    )

    def fifo(path):
        os.mkfifo(path)

    def link(path):
        (path.parent / "real.json").write_text("{}\n")
        path.symlink_to("real.json")

    for data, label in [
        (b"", "is empty"),
        (b"[1, 2]\n", "holds a JSON array"),
        (b"not json\n", "holds text that is not JSON"),
        (b'"x"\n', "holds a JSON string"),
        (b"\xff\n", "holds bytes that are not UTF-8"),
        (b"[" * 100000 + b"]" * 100000, "holds a JSON array nested 100000 deep"),
        (b'{"a": ' * 100000 + b"1" + b"}" * 100000, "holds a JSON object nested 100000 deep"),
        (b'{"limit": 1e400}\n', "holds a number that JSON writes in other text"),
        (fifo, "is a FIFO"),
        (link, "is a symlink"),
        (os.mkdir, "is a directory"),
    ]:
        base, _, _ = scratch.fresh()
        cli = base / "home" / ".gemini" / "antigravity-cli"
        cli.mkdir(parents=True)
        if callable(data):
            data(cli / "settings.json")
        else:
            (cli / "settings.json").write_bytes(data)
        snapshot = scratch.snapshot(base)
        code, text = run(base, "--apply")
        case(
            lambda: (
                scratch.refused(code, text)
                and str(cli / "settings.json") in text
                and scratch.snapshot(base) == snapshot
            ),
            f"a settings.json that {label} exits 2, names the file, and nothing is written: {code}, "
            f"{tail(text)!r}",
        )


def grants_cases(scratch):
    """The merge of the app's config.json: the rules added to userSettings.globalPermissionGrants
    once, every other key and every entry of the user's kept in its place, a backup, and exit 2
    before any write on a file or a key of the wrong type."""
    scratch = cast("Any", scratch)
    case, run, tail = scratch.case, scratch.run, scratch.tail
    base, _, _ = scratch.fresh()
    config = base / "home" / ".gemini" / "config"
    config.mkdir(parents=True)
    app = config / "config.json"
    own: dict[str, Any] = {
        "permissionGrantsV2Migrated": True,
        "remoteControlHostname": "host—1",
        "userSettings": {
            "theme": "dark",
            "globalPermissionGrants": {
                "allow": ["read_file(/u/notes)", "mcp(kaimon/*)", "mcp(kaimon/ping)", "command(git)"],
                "deny": ["command(rm)"],
                "other": [1, 2],
            },
            "last": {"a": [1.5]},
        },
        "sandboxEnabledAtV2Migration": False,
    }
    app.write_text(json.dumps(own, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    before = app.read_bytes()
    code, dry = run(base)
    listed = re.findall(r"^antigravity/config/config\.json\s+(\S+)", dry, re.M)
    case(
        lambda: code in (0, 1) and listed == ["REPLACE"] and app.read_bytes() == before,
        f"the dry run lists config/config.json as REPLACE and writes nothing: {code}, {listed}",
    )
    code, text = run(base, "--apply")
    merged = json_value(app.read_text(encoding="utf-8"), "config.json") if app.is_file() else {}
    cli_settings = (base / "home" / ".gemini" / "antigravity-cli" / "settings.json").read_text()
    cli = json_value(cli_settings, "settings.json")["permissions"]
    grants = merged.get("userSettings", {}).get("globalPermissionGrants", {})
    mine = own["userSettings"]["globalPermissionGrants"]

    def added(key):
        out = []
        for rule in cli[key]:
            if rule not in mine.get(key, []) and rule not in out:
                out.append(rule)
        return out

    case(
        lambda: (
            code == 0
            and list(merged) == list(own)
            and {k: v for k, v in merged.items() if k != "userSettings"}
            == {k: v for k, v in own.items() if k != "userSettings"}
            and list(merged["userSettings"]) == list(own["userSettings"])
            and merged["userSettings"]["theme"] == "dark"
            and merged["userSettings"]["last"] == {"a": [1.5]}
            and list(grants) == ["allow", "deny", "other", "ask"]
            and grants["other"] == [1, 2]
        ),
        f"--apply keeps every other key of config.json, of userSettings and of globalPermissionGrants, in its "
        f"place, and adds ask after them: {code}, {list(merged)}, {list(grants)}, {tail(text)!r}",
    )
    case(
        lambda: (
            all(grants[key] == [*mine.get(key, []), *added(key)] for key in ("allow", "deny", "ask"))
            and grants["allow"].count("mcp(kaimon/ping)") == 1
            and "mcp(kaimon/ex)" in grants["allow"]
            and set(cli["deny"]) <= set(grants["deny"])
            and set(cli["ask"]) <= set(grants["ask"])
        ),
        f"each list keeps the user's entries first, mcp(kaimon/*) among them, then holds each rule of the "
        f"CLI's permissions once: {[grants.get(k, [])[:4] for k in ('allow', 'deny', 'ask')]}",
    )
    case(
        lambda: (
            grants["allow"].count("command(git)") == 1
            and grants["allow"][3] == "command(git)"
            and {"command(gh)", "command(git)", "command(glab)"} <= set(cli["allow"])
            and all(grants["allow"].count(r) == 1 for r in ("command(gh)", "command(glab)", "command(ps)"))
        ),
        f"the user's own command(git) stays in its place and is not added again, and command(gh), command(glab) "
        f"and command(ps) are added once: {grants.get('allow', [])[:4]}, "
        f"{[r for r in grants.get('allow', []) if r in ('command(gh)', 'command(git)', 'command(glab)')]}",
    )
    backups = list(config.glob("config.json.bak-*"))
    written = app.read_text(encoding="utf-8")
    case(
        lambda: (
            len(backups) == 1
            and backups[0].read_bytes() == before
            and written.split("\n")[1].startswith('    "permissionGrantsV2Migrated"')
            and '"host—1"' in written
        ),
        f"--apply keeps a backup of the file it replaces, with its bytes, and the file's indent of 4 and its "
        f"characters: {backups}, {written.split(chr(10))[1]!r}",
    )
    after = app.read_bytes()
    code, text = run(base, "--apply")
    case(
        lambda: (
            code == 0
            and app.read_bytes() == after
            and len(list(config.glob("config.json.bak-*"))) == 1
            and re.findall(r"^antigravity/config/config\.json\s+(\S+)", text, re.M) == ["already"]
        ),
        f"a second --apply adds no rule again and makes no backup: {code}, {tail(text)!r}",
    )

    def fifo(path):
        os.mkfifo(path)

    def link(path):
        (path.parent / "real.json").write_text("{}\n")
        path.symlink_to("real.json")

    for data, label in [
        (b"", "is empty"),
        (b"[1, 2]\n", "holds a JSON array"),
        (b"not json\n", "holds text that is not JSON"),
        (b"\xff\n", "holds bytes that are not UTF-8"),
        (b'{"a": ' * 100000 + b"1" + b"}" * 100000, "holds a JSON object nested 100000 deep"),
        (b'{"limit": 1e400}\n', "holds a number that JSON writes in other text"),
        (b'{"userSettings": []}\n', "has a userSettings that is a list"),
        (
            b'{"userSettings": {"globalPermissionGrants": "x"}}\n',
            "has a globalPermissionGrants that is a string",
        ),
        (b'{"userSettings": {"globalPermissionGrants": {"allow": {}}}}\n', "has an allow that is an object"),
        (
            b'{"userSettings": {"globalPermissionGrants": {"deny": "command(rm)"}}}\n',
            "has a deny that is a string",
        ),
        (b'{"userSettings": {"globalPermissionGrants": {"ask": null}}}\n', "has an ask that is null"),
        (fifo, "is a FIFO"),
        (link, "is a symlink"),
        (os.mkdir, "is a directory"),
    ]:
        base, _, _ = scratch.fresh()
        config = base / "home" / ".gemini" / "config"
        config.mkdir(parents=True)
        if callable(data):
            data(config / "config.json")
        else:
            (config / "config.json").write_bytes(data)
        snapshot = scratch.snapshot(base)
        code, text = run(base, "--apply")
        case(
            lambda: (
                scratch.refused(code, text)
                and str(config / "config.json") in text
                and scratch.snapshot(base) == snapshot
            ),
            f"a config.json that {label} exits 2, names the file, and nothing is written: {code}, {tail(text)!r}",
        )
    # K101: a key twice in one object is refused with the file and the key, before anything is written.
    base, _, _ = scratch.fresh()
    config = base / "home" / ".gemini" / "config"
    config.mkdir(parents=True)
    (config / "config.json").write_bytes(b'{"userSettings": {"theme": "dark", "theme": "light"}}\n')
    snapshot = scratch.snapshot(base)
    code, text = run(base, "--apply")
    case(
        lambda: (
            scratch.refused(code, text)
            and str(config / "config.json") in text
            and '"theme"' in text
            and scratch.snapshot(base) == snapshot
        ),
        f"K101: a config.json with a key twice in one object exits 2, names the file and the key, and "
        f"nothing is written: {code}, {tail(text)!r}",
    )
    # K102: a minified config.json whose rule is present comes back byte for byte, and the plan finds it
    # identical.
    minified = (
        b'{"a":1,"userSettings":{"globalPermissionGrants":'
        b'{"allow":["command(git status)"],"deny":[],"ask":[]}}}'
    )
    (config / "config.json").write_bytes(minified)
    again = merge_grants(config / "config.json", {"allow": ["command(git status)"], "deny": [], "ask": []})
    out, install_file = io.StringIO(), cast("Callable[..., int]", install.install_file)
    with contextlib.redirect_stdout(out):
        changes = install_file(
            apply=False, data=again, dst=config / "config.json", label="config.json", backup=True
        )
    case(
        lambda: again == minified and changes == 0 and "already identical" in out.getvalue(),
        f"K102: a minified config.json whose rule is present is merged byte for byte and planned as "
        f"identical: {again[:60]!r}, {changes}, {out.getvalue().strip()!r}",
    )


def deny_write_cases(scratch):
    """The `read_file` denies of the template's `sandbox.filesystem.denyWrite`: the entries below the
    research root, entry by entry, the `**` entries expanded over the clones, an entry outside the
    root silent, any other wildcard refused with a warning, the clones that the walk of the research
    root finds, and both files read back after an install, with the count line."""
    case, run, tail = scratch.case, scratch.run, scratch.tail
    template = json_value(SETTINGS.read_text(), str(SETTINGS))["sandbox"]["filesystem"]["denyWrite"]
    home, root = "/h", pathlib.Path("/h/Research")
    clones_ = [pathlib.Path("/h/Research/Packages/A.jl"), pathlib.Path("/h/Research/Knowledge")]
    got = deny_write(template, home, root, clones_)
    expected = []
    for entry in template:
        if entry.startswith("~/Research/**/"):
            expected += [f"read_file({c}/{entry[len('~/Research/**/') :]})" for c in clones_]
        elif entry == "~/Research" or entry.startswith("~/Research/"):
            expected.append(f"read_file({home}{entry[1:]})")
    case(
        lambda: got[0] == expected and len(expected) >= 6 and not [r for r in got[0] if "*" in r or "~" in r],
        f"each denyWrite entry of the template below the research root is a read_file deny, in the template's "
        f"order, and each `~/Research/**/X` one rule per clone: {len(got[0])} of {len(expected)}, "
        f"{[r for r in got[0] if r not in expected][:3]}, {[r for r in expected if r not in got[0]][:3]}",
    )
    case(
        lambda: (
            {
                "read_file(/h/Research/Packages/A.jl/.git/hooks)",
                "read_file(/h/Research/Packages/A.jl/.git/config)",
                "read_file(/h/Research/Knowledge/.git/hooks)",
                "read_file(/h/Research/Knowledge/.git/config)",
            }
            <= set(got[0])
            and all(r.startswith("read_file(/h/Research/") for r in got[0])
            and [w for w in got[1] if " cover " not in w[0]] == []
        ),
        f"the rules hold the .git/hooks and .git/config of each clone, none outside the research root, and "
        f"the template's entries outside it (~/.gitconfig, juliaup/julia-*) give no warning: {got}",
    )
    counted = [w for w in got[1] if " cover " in w[0]]
    case(
        lambda: len(counted) == 1 and "cover 2 repositories" in counted[0][0],
        f"one warning names the number of clones that the rules cover: {counted}",
    )

    entries = [
        "/h/Research/abs",
        "~/Research/x",
        "~/x",
        "/abs/p",
        "~",
        "~/Research/**/.git/hooks",
        "~/Research/Packages/**/.git/config",
        "~/Other/**/y",
        "~/.julia/juliaup/julia-*",
        "~/Research/**/z*",
        "~/Research/**",
        "~/Research/**/a/**/b",
        "~/*/x",
        "~/Research*/x",
        "rel/p",
        "~user/p",
        "~/Research/x",
        "~/Research/a/b?",
        "~/Research/a/[bc]",
        "~/Research",
        "/h/Researcher/y",
        "~/Res*/x",
        "~/**/q",
    ]
    clones_ = [
        pathlib.Path("/h/Research/Packages/A.jl"),
        pathlib.Path("/h/Research/Packages2/B"),
        pathlib.Path("/h/Research/Knowledge"),
    ]
    rules, warnings = deny_write(entries, home, root, clones_)
    case(
        lambda: (
            rules
            == [
                "read_file(/h/Research/abs)",
                "read_file(/h/Research/x)",
                "read_file(/h/Research/Packages/A.jl/.git/hooks)",
                "read_file(/h/Research/Packages2/B/.git/hooks)",
                "read_file(/h/Research/Knowledge/.git/hooks)",
                "read_file(/h/Research/Packages/A.jl/.git/config)",
                "read_file(/h/Research)",
            ]
        ),
        f"an entry below the research root stays, `~` is the home directory, an entry outside the root renders "
        f"nothing, a `**` entry covers each clone at or below its prefix, a prefix is compared by path, not by "
        f"text, and a rule repeats not: {rules}",
    )
    named = [
        e
        for e in (
            "~/Research/**/z*",
            "~/Research/**",
            "~/Research/**/a/**/b",
            "~/*/x",
            "~/Research*/x",
            "rel/p",
            "~user/p",
            "~/Research/a/b?",
            "~/Research/a/[bc]",
            "~/Res*/x",
            "~/**/q",
        )
        if [w for w in warnings if e in w[0]]
    ]
    silent = [
        e
        for e in ("~/x", "/abs/p", "~/Other/", "julia-*", "/h/Researcher/y")
        if [w for w in warnings if e in w[0]]
    ]
    case(
        lambda: (
            len(named) == 11
            and len(warnings) == 12
            and silent == []
            and "cover 3 repositories" in warnings[-1][0]
        ),
        f"below the research root a wildcard after or beside `**`, a trailing `**`, two `**`, `?` and `[…]`, a "
        f"wildcard or a `**` whose prefix holds the root, a relative path and `~user` each give one warning and no "
        f"rule; an entry outside the root gives none, and the count is the last: {warnings}",
    )
    case(
        lambda: (
            deny_write(["~/Research/x"], home, root, clones_)[1] == []
            and "cover 1 repository:" in deny_write(["~/Research/**/c"], home, root, clones_[:1])[1][0][0]
            and "cover 1 repository:"
            in deny_write(["~/Research/Packages/**/c"], home, root, clones_)[1][0][0]
        ),
        "with no `**` entry, no count line; the count is of the clones that a `**` entry covers, and says "
        "`1 repository` for one",
    )
    case(
        lambda: deny_write(["~/Other/**/c", "~/x"], home, root, clones_) == ([], []),
        "a `**` entry outside the research root expands over no clone and adds no count line",
    )

    # The home is a symbolic link, as /tmp is on macOS: the walk gives the clones' real paths.
    real = pathlib.Path(scratch.tmp, "deny-write-real")
    (real / "Research" / "A").mkdir(parents=True)
    link = pathlib.Path(scratch.tmp, "deny-write-link")
    link.symlink_to(real)
    case(
        lambda: (
            deny_write(
                ["~/Research/**/c", "~/Research/d"],
                str(link),
                link / "Research",
                [pathlib.Path(os.path.realpath(real / "Research" / "A"))],
            )[0]
            == [f"read_file({os.path.realpath(real)}/Research/A/c)", f"read_file({link}/Research/d)"]
        ),
        "a home or research root reached through a symbolic link is compared by its real path",
    )

    tree = pathlib.Path(scratch.tmp, "deny-write-tree")
    for d in (
        "Packages/A.jl/.git",
        "Packages/plain",
        "Papers/P/.git",
        "Papers/P/inner/.git",
        "Knowledge/.git",
        "Harness/.git",
        "Experiments/W",
        ".scratch/S/.git",
        ".worktrees/T/.git",
        "Lib/node_modules/N/.git",
    ):
        (tree / d).mkdir(parents=True)
    (tree / "Experiments" / "W" / ".git").write_text("gitdir: /elsewhere\n")
    saved = os.environ.get("RESEARCH_ROOT")
    os.environ["RESEARCH_ROOT"] = str(tree)
    try:
        found = clones()
    except (HarnessError, OSError) as e:
        # Recorded, so that the environment is restored and the case reports it.
        found = e
    finally:
        if saved is None:
            os.environ.pop("RESEARCH_ROOT", None)
        else:
            os.environ["RESEARCH_ROOT"] = saved
    t = pathlib.Path(os.path.realpath(tree))
    case(
        lambda: (
            found
            == [
                t / "Harness",
                t / "Knowledge",
                t / "Packages" / "A.jl",
                t / "Papers" / "P",
                t / "Papers" / "P" / "inner",
            ]
        ),
        f"the clones are the directories below the research root with a `.git` directory, nested ones too; a "
        f"worktree's `.git` file, a directory with no `.git`, .scratch, .worktrees and node_modules left out: "
        f"{found}",
    )

    case(
        lambda: (
            deny_write(
                ["~/Research/x", "~/Research/y", "~/Research/**/z"],
                home,
                root,
                clones_[:1],
                ["read_file(/h/Research/x)", "read_file(/h/Research/Packages/A.jl/z)"],
            )[0]
            == ["read_file(/h/Research/y)"]
        ),
        "a rule that the deny list already holds is not added again",
    )

    base, _, _ = scratch.fresh()
    h = base / "home"
    research = h / "Research"
    (research / "Packages" / "A.jl" / ".git").mkdir(parents=True)
    (research / "Packages" / "W").mkdir(parents=True)
    (research / "Packages" / "W" / ".git").write_text("gitdir: /elsewhere\n")
    config = h / ".gemini" / "config"
    config.mkdir(parents=True)
    a = pathlib.Path(os.path.realpath(research / "Packages" / "A.jl"))
    mine = f"read_file({a}/.git/hooks)"
    (config / "config.json").write_text(
        json.dumps({"userSettings": {"globalPermissionGrants": {"deny": [mine]}}})
    )
    env = {"RESEARCH_ROOT": None}
    code, dry = run(base, extra_env=env)
    count = [w for w in dry.split("WARNING: ")[1:] if "denyWrite" in w and " cover " in w]
    case(
        lambda: code in (0, 1) and len(count) == 1 and "cover 1 repository:" in count[0],
        f"the dry run names the number of clones in one warning: {code}, {count}, {tail(dry)!r}",
    )
    code, text = run(base, "--apply", extra_env=env)
    cli = json_value((h / ".gemini" / "antigravity-cli" / "settings.json").read_text(), "settings.json")[
        "permissions"
    ]["deny"]
    grants = json_value((config / "config.json").read_text(), "config.json")["userSettings"][
        "globalPermissionGrants"
    ]["deny"]
    ours = deny_write(template, str(h), research, [a])[0]
    after = max(i for i, r in enumerate(cli) if r.startswith("mcp(")) + 1
    case(
        lambda: (
            code == 0
            and cli[after:] == ours
            and len(ours) == 3
            and ours
            == [f"read_file({a}/.git/hooks)", f"read_file({a}/.git/config)", f"read_file({a}/.claude)"]
            and not [r for r in cli if "/W/" in r]
            and len(cli) == len(set(cli))
        ),
        f"--apply writes the rules into the CLI's permissions.deny after the other denies, each once, and none "
        f"for the worktree: {code}, {cli[after:]}, {[r for r in cli if cli.count(r) > 1][:2]}, {tail(text)!r}",
    )
    case(
        lambda: (
            grants == [mine, *[r for r in cli if r != mine]]
            and grants.count(mine) == 1
            and f"read_file({a}/.git/config)" in grants
        ),
        f"--apply adds each rule once to the app's deny grants, after the user's own, which is not added again: "
        f"{grants[:2]}, {grants.count(mine)}",
    )
    (research / "Knowledge" / ".git").mkdir(parents=True)
    code, dry = run(base, extra_env=env)
    count = [w for w in dry.split("WARNING: ")[1:] if "denyWrite" in w and " cover " in w]
    case(
        lambda: (
            "cover 2 repositories" in count[0]
            and re.findall(r"^antigravity/config/config\.json\s+(\S+)", dry, re.M) == ["REPLACE"]
        ),
        f"a new clone changes the count and the app's grants at the next dry run: {count}",
    )


# The tiers of [antigravity] in examples/models.toml, written out here.
EXAMPLE_TIERS = {"large": "inherit", "medium": "flash", "small": "flash_lite"}
# The table [antigravity] and its sub-tables in a models.toml text, up to the next table.
ANTIGRAVITY_TABLE = re.compile(r"(?ms)^\[antigravity(?:\.[A-Za-z_]+)?\]\n.*?(?=^\[|\Z)")


def models_text(tiers=None, extra=""):
    """examples/models.toml with its [antigravity] table replaced by `tiers`, the lines of the
    table, or with none for None, then the text `extra`."""
    text = ANTIGRAVITY_TABLE.sub("", (REPO / "examples" / "models.toml").read_text())
    return text + ("" if tiers is None else "\n[antigravity]\n" + tiers) + extra


def model_cases(scratch):
    """The table [antigravity] of models.toml: each refusal exits 2 before any write, naming the
    table and the key; the four words; its overrides, read on their own; and the plans of OpenCode
    and oh-my-pi of a models file with the table, which are those of the same file without it."""
    import tomllib

    case, run, tail = scratch.case, scratch.run, scratch.tail
    example = tomllib.loads((REPO / "examples" / "models.toml").read_text())
    case(
        lambda: example["antigravity"] == EXAMPLE_TIERS and "antigravity" not in tomllib.loads(models_text()),
        f"examples/models.toml holds [antigravity] with large = inherit, medium = flash, small = flash_lite: "
        f"{example.get('antigravity')}",
    )
    tiers = 'large = "inherit"\nmedium = "flash"\nsmall = "flash_lite"\n'

    def written(name, text):
        path = scratch.tmp / f"models-{name}.toml"
        path.write_text(text)
        return path

    refusals = [
        ("no table [antigravity]", models_text(), ["[antigravity]"]),
        (
            "a key antigravity that is no table",
            'antigravity = "inherit"\n' + models_text(),
            ["[antigravity]"],
        ),
        (
            "a key antigravity that is a list of the tiers",
            'antigravity = ["large", "medium", "small"]\n' + models_text(),
            ["[antigravity]"],
        ),
        ("no tier small", models_text('large = "inherit"\nmedium = "flash"\n'), ["[antigravity]", "small"]),
        (
            "overrides and no tier",
            models_text("", '\n[antigravity.model_overrides]\nreader = "flash"\n'),
            ["[antigravity]", "it has no large, medium, small"],
        ),
        (
            "a model name as a tier",
            models_text(tiers.replace('"inherit"', '"gemini-4-argon"')),
            ["[antigravity]", "large", "gemini-4-argon"],
        ),
        ("a number as a tier", models_text(tiers.replace('"flash"', "1")), ["[antigravity]", "medium"]),
        ("a key that is no tier", models_text(tiers + 'effort = "high"\n'), ["[antigravity]", "effort"]),
        (
            "an override outside the four words",
            models_text(tiers, '\n[antigravity.model_overrides]\nreader = "fast"\n'),
            ["[antigravity.model_overrides]", "reader", "fast"],
        ),
        (
            "an override of no agent",
            models_text(tiers, '\n[antigravity.model_overrides]\nnosuch = "flash"\n'),
            ["[antigravity.model_overrides]", "nosuch"],
        ),
        (
            "overrides that are no table",
            models_text(tiers + 'model_overrides = "flash"\n'),
            ["[antigravity.model_overrides]"],
        ),
    ]
    for i, (label, text, words) in enumerate(refusals):
        base, _, _ = scratch.fresh()
        (base / "home" / ".gemini").mkdir()
        snapshot = scratch.snapshot(base)
        code, out = run(base, "--apply", models=written(f"refused-{i}", text))
        case(
            lambda: (
                scratch.refused(code, out)
                and all(w in out for w in words)
                and scratch.snapshot(base) == snapshot
            ),
            f"with ~/.gemini/, {label} exits 2 before any write and names {words}: {code}, {tail(out)!r}",
        )
    base, _, _ = scratch.fresh()
    code, out = run(base, models=written("no-table", models_text()))
    case(
        lambda: code in (0, 1) and "[antigravity]" not in out,
        f"with no ~/.gemini/, a models file with no [antigravity] installs the other layers: {code}, {tail(out)!r}",
    )

    words = written(
        "words",
        models_text(
            'large = "pro"\nmedium = "flash_lite"\nsmall = "inherit"\n',
            '\n[antigravity.model_overrides]\njulia-builder = "flash"\n',
        ),
    )
    try:
        got = load_models(words, REPO / "agents")
    except HarnessError as e:
        got = str(e)
    case(
        lambda: (
            got == ({"large": "pro", "medium": "flash_lite", "small": "inherit"}, {"julia-builder": "flash"})
        ),
        f"each of the four words is a tier, and an override names an agent of agents/: {got}",
    )
    case(
        lambda: all(
            profile_module.model_tables(cast("pathlib.Path", words), f).model_overrides
            == {"builder": "provider-b/medium-model"}
            for f in profile_module.SHARING
        ),
        "the overrides of [antigravity.model_overrides] are not merged with the shared [model_overrides]",
    )
    base, _, _ = scratch.fresh()
    (base / "home" / ".gemini").mkdir()
    code, out = run(base, "--apply", models=words)
    agents = base / "home" / ".gemini" / "config" / "agents"
    got = {
        n: rendered_head((agents / f"{n}.md").read_bytes())["model"]
        if (agents / f"{n}.md").is_file()
        else None
        for n in ("julia-builder", "julia-critic", "changelog-scribe", "reader")
    }
    case(
        lambda: (
            code == 0
            and got
            == {
                "julia-builder": "flash",
                "julia-critic": "pro",
                "changelog-scribe": "inherit",
                "reader": "inherit",
            }
        ),
        f"--apply installs each agent on the word of its tier, its override over it: {code}, {got}, {tail(out)!r}",
    )

    # The OpenCode and oh-my-pi layers that an install writes with the table and without it.
    def tree(base, top):
        return {
            p[len(str(base)) :]: (m, d.replace(str(base).encode(), b"BASE") if isinstance(d, bytes) else d)
            for p, (m, d) in scratch.snapshot(base / top).items()
        }

    installed = []
    for name, text in [("with", models_text(tiers)), ("without", models_text())]:
        base, _, _ = scratch.fresh()
        code, out = run(base, "--apply", models=written(f"plans-{name}", text))
        installed.append((code, {top: tree(base, top) for top in ("opencode", "omp")}))
    case(
        lambda: (
            installed[0][0] == installed[1][0] == 0
            and installed[0][1] == installed[1][1]
            and all(installed[0][1].values())
        ),
        f"the OpenCode and oh-my-pi layers of a models file with [antigravity] are those of the same file without "
        f"it: {[c for c, _ in installed]}, {[{k: len(v) for k, v in t.items()} for _, t in installed]}",
    )


# The names that Antigravity accepts in a subagent's `tools:`, both families, written out here so
# that the cases do not take them from TOOLS.
ROUND5 = {
    "read_file",
    "write_file",
    "edit_file",
    "view_file",
    "write_to_file",
    "replace_file_content",
    "grep_search",
    "find_by_name",
    "list_dir",
    "run_command",
    "search_web",
    "read_url_content",
}


def rendered_head(data):
    """{key: value} of the frontmatter of the rendered agent `data`, each value read as JSON."""
    lines = data.decode().split("\n---\n", 1)[0].split("\n")[1:]
    return dict((k, json_value(v, k)) for k, v in (line.split(": ", 1) for line in cast("list[str]", lines)))


def agent_cases(scratch):
    """The rendered agents: four against their fixtures, every agent's frontmatter, the tool names,
    the overrides, an agent with no `tools:`, and the "Under Antigravity" section of each
    mechanism."""
    case = scratch.case
    want_tools = {
        "read": ["view_file", "list_dir"],
        "edit": ["replace_file_content"],
        "write": ["write_to_file"],
        "grep": ["grep_search"],
        "glob": ["find_by_name"],
        "shell": ["run_command"],
        "agent": ["invoke_subagent"],
        "web_search": ["search_web"],
        "web_fetch": ["read_url_content"],
    }
    case(
        lambda: {k: list(v) for k, v in TOOLS.items()} == want_tools,
        f"TOOLS maps each neutral tool to the names of a subagent's default family: {TOOLS}",
    )

    def attempt[T](f: Callable[[], T]) -> T | HarnessError:
        try:
            return f()
        except HarnessError as e:
            return e

    for name in ("julia-builder", "julia-critic", "reader", "changelog-scribe"):
        src = REPO / "agents" / f"{name}.md"
        got = attempt(lambda: render_agent(src, EXAMPLE_TIERS, {}))
        body = relocate(frontmatter.parse_file(src).body.lstrip("\n").encode(), "~/.gemini/config")
        want = (FIXTURES / f"{name}.md").read_bytes() + body
        case(
            lambda: got == want,
            f"agents/{name}.md renders as fixtures/{name}.md, then its body: "
            f"{got[: len(want) - len(body)].decode() if isinstance(got, bytes) else got!r}",
        )

    heads, wrong = {}, []
    for src in sorted((REPO / "agents").glob("*.md")):
        meta = frontmatter.parse_file(src).meta
        head = rendered_head(render_agent(src, EXAMPLE_TIERS, {}))
        heads[src.stem] = head
        kaimon = any(t.startswith(frontmatter.MCP) for t in meta["tools"])
        tools = list(dict.fromkeys(n for t in meta["tools"] if t in want_tools for n in want_tools[t]))
        if (
            list(head) != ["name", "description", "model", "tools", "subagent", *["inheritMcp"] * kaimon]
            or head["name"] != src.stem
            or head["description"] != meta["description"]
            or head["model"] != EXAMPLE_TIERS.get(meta.get("model", ""), "inherit")
            or head["tools"] != tools
            or head["subagent"] is not True
            or head.get("inheritMcp", True) is not True
        ):
            wrong.append((src.stem, head))
    case(
        lambda: heads and not wrong,
        f"each agent of agents/ renders name, description, its tier's model or inherit, its tools by TOOLS, "
        f"subagent: true, and inheritMcp: true with a Kaimon tool; no effort, no isolation: {wrong[:2]}",
    )
    names = {n for h in heads.values() for n in h["tools"]}
    case(
        lambda: (
            names <= ROUND5 | {"invoke_subagent"}
            and "call_mcp_tool" not in names
            and all("tools" in h for h in heads.values())
        ),
        f"every rendered tool name is one of round 5 or invoke_subagent, none is call_mcp_tool, and every agent "
        f"has a tools key: {sorted(names - ROUND5)}",
    )
    builder = REPO / "agents" / "julia-builder.md"
    reader = REPO / "agents" / "reader.md"
    got = [
        rendered_head(render_agent(builder, EXAMPLE_TIERS, {"julia-builder": "flash"}))["model"],
        rendered_head(render_agent(reader, EXAMPLE_TIERS, {"reader": "pro"}))["model"],
        rendered_head(render_agent(builder, {**EXAMPLE_TIERS, "large": "pro"}, {}))["model"],
    ]
    case(
        lambda: got == ["flash", "pro", "pro"],
        f"an override replaces the tier of an agent, with a `model:` or without one, and the tier follows the "
        f"table: {got}",
    )

    agents = scratch.tmp / "g3-agents"
    agents.mkdir()

    def agent(name: str, head: str = "", body: str = "Do the work.\n") -> pathlib.Path:
        path = agents / f"{name}.md"
        path.write_text(f"---\nname: {name}\ndescription: An agent of the cases.\n{head}---\n\n{body}")
        return path

    bare = attempt(lambda: render_agent(agent("bare"), EXAMPLE_TIERS, {}))
    case(
        lambda: (
            isinstance(bare, bytes)
            and rendered_head(bare)["tools"] == []
            and b"Under Antigravity" not in bare
        ),
        f"an agent with no tools: renders tools: [], and with no mechanism no section: {bare!r}",
    )
    twice = attempt(lambda: render_agent(agent("twice", "tools:\n  - read\n  - read\n"), EXAMPLE_TIERS, {}))
    case(
        lambda: rendered_head(twice)["tools"] == ["view_file", "list_dir"],
        f"a tool listed twice renders its names once: {twice!r}",
    )
    saved = TOOLS.pop("web_fetch")
    try:
        missing = attempt(lambda: render_agent(agent("fetch", "tools:\n  - web_fetch\n"), EXAMPLE_TIERS, {}))
    finally:
        TOOLS["web_fetch"] = saved
    renamed = agents / "renamed.md"
    renamed.write_text("---\nname: other\ndescription: An agent of the cases.\n---\n\nDo the work.\n")
    blank = agents / "blank.md"
    blank.write_text("---\nname: blank\n---\n\nDo the work.\n")
    refused = [attempt(lambda: render_agent(p, EXAMPLE_TIERS, {})) for p in (renamed, blank)]
    case(
        lambda: (
            all(isinstance(e, HarnessError) for e in refused)
            and "'other'" in str(refused[0])
            and "description" in str(refused[1])
        ),
        f"an agent whose name: is not its file name, and one with no description, exit 2: {refused}",
    )
    unknown = attempt(lambda: render_agent(agent("odd", "tools:\n  - telepathy\n"), EXAMPLE_TIERS, {}))
    case(
        lambda: (
            isinstance(missing, HarnessError)
            and "web_fetch" in str(missing)
            and "fetch.md" in str(missing)
            and isinstance(unknown, HarnessError)
            and "telepathy" in str(unknown)
        ),
        f"a neutral tool outside TOOLS exits 2, naming the tool and the file, and so does a tool outside the "
        f"neutral ones: {missing!r}, {unknown!r}",
    )

    text = UNDER.read_text()
    rules = sections(text)
    mechanisms = {
        "skills": ("skills:\n  - build-part\n", "Do the work.\n"),
        "worktree": ("isolation: worktree\n", "Do the work.\n"),
        "agent": ("tools:\n  - agent\n", "Do the work.\n"),
        "background": ("", "Never set `run_in_background`.\n"),
        "mcp": ("tools:\n  - mcp/kaimon/ping\n", "Do the work.\n"),
        "pr": ("", "Then open the pull request.\n"),
    }
    parts = {}
    for key, (front, prose) in mechanisms.items():
        data = attempt(lambda: render_agent(agent(f"uses-{key}", front, prose), EXAMPLE_TIERS, {}))
        parts[key] = (
            data.decode().split("## Under Antigravity\n\n", 1)[-1].split("\n\n")
            if isinstance(data, bytes)
            else data
        )
    filled = {k: rules.get(k, "").replace("{skills}", "`build-part` skill") for k in mechanisms}
    case(
        lambda: all(parts[k][:2] == [rules["intro"], "- " + filled[k]] for k in mechanisms),
        f"an agent that uses one mechanism gets the intro and that mechanism's rule of UNDER-ANTIGRAVITY.md: "
        f"{ {k: v if isinstance(v, HarnessError) else v[:2] for k, v in parts.items()} }",
    )
    combined = attempt(lambda: render_agent(builder, EXAMPLE_TIERS, {}))
    order = [
        k
        for k in mechanisms
        if isinstance(combined, bytes) and "- " + rules[k].split("{")[0][:40] in combined.decode()
    ]
    case(
        lambda: order == list(mechanisms),
        f"julia-builder, which uses each mechanism, gets each rule: {order}",
    )
    gone = [
        (
            k,
            attempt(
                lambda: under_antigravity(
                    {}, "Then open the pull request.\n", text.replace(f"## {k}\n", "## nothing\n")
                )
            ),
        )
        for k in ("pr", "intro")
    ]
    case(
        lambda: all(
            isinstance(e, HarnessError) and "UNDER-ANTIGRAVITY.md" in str(e) and f"## {k}" in str(e)
            for k, e in gone
        ),
        f"a section of UNDER-ANTIGRAVITY.md that an agent needs and that is missing exits 2, naming it: {gone}",
    )
    worker = attempt(lambda: render_agent(REPO / "agents" / "worker.md", EXAMPLE_TIERS, {}))
    case(
        lambda: isinstance(worker, bytes) and ("- " + rules["pr"]).encode() in worker,
        f"worker, whose body names opening a pull request, gets the rule of `pr`: "
        f"{worker[:300] if isinstance(worker, bytes) else worker!r}",
    )
    got = {
        body: [k for k in mechanisms if "- " + filled[k] in under_antigravity({}, body)]
        for body in (
            "Open a pull request when the prompt says so.\n",
            'Spawn it with `isolation: "worktree"`.\n',
            "Spawn it with isolation: worktree.\n",
            "This agent needs no isolation of any kind.\n",
            "It reads the pull request.\n",
        )
    }
    case(
        lambda: list(got.values()) == [["pr"], ["worktree"], ["worktree"], [], []],
        f"a body that says to open a pull request gets the rule of `pr`, one that names `isolation: worktree`, "
        f"quoted or not, the rule of `worktree`, and the bare word isolation or a pull request that is not "
        f"opened gets no rule: {got}",
    )

    delta = DELTA.read_text()
    case(
        lambda: (
            "two critics" in delta
            and "build-part" in delta
            and "session model" in delta
            and all(w in delta for w in ("`inherit`", "`flash`", "`flash_lite`", "[antigravity]"))
        ),
        "ANTIGRAVITY-DELTA.md states that round 1 of build-part runs two critics on the session model, and the "
        "agents' tiers",
    )


def council_cases(scratch):
    """A council of [councils] or of a frontend's [<frontend>.councils] gives one warning for each
    agent it names, and no seat file."""
    case, run, tail = scratch.case, scratch.run, scratch.tail
    path = scratch.tmp / "models-councils.toml"
    path.write_text(
        models_text(
            'large = "inherit"\nmedium = "flash"\nsmall = "flash_lite"\n',
            '\n[opencode.councils]\njulia-critic = [{ name = "critic-x", model = "provider-c/other-model" }]\n'
            'reader = [{ name = "reader-b", model = "provider-c/other-model" }]\n',
        )
    )
    base, _, _ = scratch.fresh()
    (base / "home" / ".gemini").mkdir()
    code, text = run(base, models=path)
    warned = [w for w in cast("str", text).split("WARNING: ")[1:] if "council" in w and "Antigravity" in w]
    listed = re.findall(r"^antigravity/config/agents/(\S+)\s", text, re.M)
    case(
        lambda: (
            code in (0, 1)
            and len(warned) == 3
            and sum("julia-critic" in w for w in warned) == 1
            and sum("python-critic" in w for w in warned) == 1
            and sum("reader" in w for w in warned) == 1
            and not {
                "critic-b.md",
                "critic-c.md",
                "critic-x.md",
                "python-critic-b.md",
                "python-critic-c.md",
                "reader-b.md",
            }
            & set(listed)
            and {"julia-critic.md", "python-critic.md"} <= set(listed)
        ),
        f"julia-critic, in [councils] and [opencode.councils], python-critic, in [councils], and reader, in "
        f"[opencode.councils], give one warning each, and no seat file is listed: {code}, {warned}, "
        f"{tail(text)!r}",
    )


def kaimon_cases(scratch):
    """mcp_config.json: the Kaimon entry with the token of the token file, mode 600, the token never
    in the output; no entry and one warning with no token; and the permission allow of Kaimon."""
    scratch = cast("Any", scratch)
    case, run, tail = scratch.case, scratch.run, scratch.tail
    line = re.compile(r"^antigravity/config/mcp_config\.json\s+(\S+)", re.M)
    base, _, _ = scratch.fresh()
    home = base / "home"
    (home / ".gemini").mkdir()
    token = home / ".config" / "kaimon" / "auth-token"
    token.parent.mkdir(parents=True)
    fsutil.write_private(cast("pathlib.Path", token), b"fake-token-of-the-cases\n")
    code, dry = run(base)
    case(
        lambda: line.findall(dry) == ["INSTALL"] and "fake-token-of-the-cases" not in dry,
        f"with a token file, the dry run lists mcp_config.json and never prints the token: {line.findall(dry)}",
    )
    config = home / ".gemini" / "config" / "mcp_config.json"

    def entry(value):
        return {
            "mcpServers": {
                "kaimon": {"url": "http://127.0.0.1:2828/", "headers": {"Authorization": f"Bearer {value}"}}
            }
        }

    code, out = run(base, "--apply")
    # Each case below binds `got` to the file's parsed JSON or its text, and its lambda reads it.
    got: Any
    got = json_value(config.read_text(), "mcp_config.json") if config.is_file() else None
    case(
        lambda: (
            code == 0
            and got == entry("fake-token-of-the-cases")
            and scratch.mode(config) == 0o600
            and "fake-token-of-the-cases" not in out
        ),
        f"--apply writes the Kaimon entry with the token of the file, mode 600: {code}, {got}, {tail(out)!r}",
    )
    token.write_text("another-token\n")
    code, out = run(base, "--apply")
    got = json_value(config.read_text(), "mcp_config.json") if config.is_file() else None
    case(
        lambda: (
            code == 0
            and got == entry("another-token")
            and scratch.mode(config) == 0o600
            and not list(config.parent.glob("mcp_config.json.bak-*"))
        ),
        f"a new token in the file is the token of the entry, and no backup holds the old one: {code}, {got}",
    )

    def fresh(token_text="fake-token-of-the-cases\n"):
        base, _, _ = scratch.fresh()
        token = base / "home" / ".config" / "kaimon" / "auth-token"
        token.parent.mkdir(parents=True)
        if token_text is not None:
            token.write_text(token_text)
        config = base / "home" / ".gemini" / "config" / "mcp_config.json"
        config.parent.mkdir(parents=True)
        return base, config

    # A file of the user's is merged: every other server and key stays, in its place, with its indent.
    base, config = fresh()
    config.write_text(
        json.dumps({"mcpServers": {"other": {"command": "x", "args": []}}, "extra": 1}, indent=4) + "\n"
    )
    code, out = run(base, "--apply")
    text = config.read_text()
    got = json_value(text, "mcp_config.json")
    case(
        lambda: (
            code == 0
            and got
            == {
                "mcpServers": {
                    "other": {"command": "x", "args": []},
                    "kaimon": entry("fake-token-of-the-cases")["mcpServers"]["kaimon"],
                },
                "extra": 1,
            }
            and list(got) == ["mcpServers", "extra"]
            and list(got["mcpServers"]) == ["other", "kaimon"]
            and text.split("\n")[1].startswith('    "mcpServers"')
            and scratch.mode(config) == 0o600
        ),
        f"--apply adds kaimon to the user's mcpServers and keeps every other server and key, in place, with the "
        f"file's indent, mode 600: {code}, {got}",
    )
    base, config = fresh("new-token\n")
    other = {"command": "y", "args": ["z"], "env": {"K": "v"}}
    config.write_text(
        json.dumps(
            {"mcpServers": {"kaimon": entry("old-token")["mcpServers"]["kaimon"], "other": other}}, indent=2
        )
        + "\n"
    )
    code, out = run(base, "--apply")
    got = json_value(config.read_text(), "mcp_config.json")
    case(
        lambda: (
            code == 0
            and got["mcpServers"] == {"kaimon": entry("new-token")["mcpServers"]["kaimon"], "other": other}
            and not list(config.parent.glob("mcp_config.json.bak-*"))
            and "old-token" not in out
        ),
        f"--apply replaces a stale Kaimon token, keeps the other server, and makes no backup: {code}, {got}",
    )
    for label, data in [("is empty", b""), ("holds a newline only", b"\n")]:
        base, config = fresh()
        config.write_bytes(data)
        code, out = run(base, "--apply")
        got = config.read_text()
        case(
            lambda: (
                code == 0
                and json_value(got, "mcp_config.json") == entry("fake-token-of-the-cases")
                and scratch.mode(config) == 0o600
            ),
            f"a mcp_config.json that {label} becomes Kaimon alone: {code}, {got!r}, {tail(out)!r}",
        )
    base, config = fresh()
    overflow = '{"mcpServers": {"kaimon": {"timeout": 1e400}, "other": {"timeout": 1.5}}}\n'
    config.write_text(overflow)
    code, out = run(base, "--apply")
    got = config.read_text()
    case(
        lambda: scratch.refused(code, out) and "1e400" in out and got == overflow,
        f"a number that overflows to infinity, in the Kaimon entry too, exits 2 and names it: {code}, "
        f"{tail(out)!r}",
    )
    new = entry("fake-token-of-the-cases")["mcpServers"]["kaimon"]
    base, config = fresh()
    config.write_text('{"extra": {"u": 1}}\n')
    code, out = run(base, "--apply")
    got = config.read_text()
    case(
        lambda: (
            code == 0
            and json_value(got, "mcp_config.json") == {"extra": {"u": 1}, "mcpServers": {"kaimon": new}}
        ),
        f"a file with no mcpServers gains it, with Kaimon alone: {code}, {got!r}, {tail(out)!r}",
    )
    # A key twice, inside the Kaimon entry that the merge replaces too, and an entry twice, are refused
    # with exit 2: `jsonio` reads no object that holds a key twice, and the error names the key, not a value.
    for label, text in [
        (
            "a key twice in the Kaimon entry",
            '{"mcpServers": {"kaimon": {"u": 1, "u": 2}, "other": {"command": "x"}}}\n',
        ),
        (
            "a Kaimon entry twice in mcpServers",
            '{"mcpServers": {"kaimon": {"url": "a"}, "kaimon": {"url": "b"}}}\n',
        ),
        ("a key twice in a server", '{"mcpServers": {"a": {"url": "secret-u", "url": "secret-v"}}}\n'),
    ]:
        base, config = fresh()
        config.write_text(text)
        code, out = run(base, "--apply")
        case(
            lambda: (
                scratch.refused(code, out)
                and str(config) in out
                and "occurs twice" in out
                and "secret-" not in out
                and config.read_text() == text
            ),
            f"{label} exits 2, names the file and the key, prints no value, and writes nothing: {code}, "
            f"{tail(out)!r}",
        )
    # A number keeps its text: the merge writes only the Kaimon entry again.
    for text in [
        '{"mcpServers": {"other": {"args": ["x", 1.10]}}}\n',
        '{"mcpServers": {"kaimon[0]": {"timeout": 1.10}}}\n',
    ]:
        base, config = fresh()
        config.write_text(text)
        code, out = run(base, "--apply")
        got = config.read_text()
        case(
            lambda: code == 0 and "1.10" in got and '"kaimon": {' in got,
            f"a mcp_config.json with 1.10 outside the Kaimon entry keeps its text: {code}, {got!r}, "
            f"{tail(out)!r}",
        )
    truncated = b'{"mcpServers": {"kaimon": {"headers": {"Authorization": "Bearer fake-old'
    for label, make in [
        ("holds a JSON array", lambda p: p.write_bytes(b"[]\n")),
        ("holds a JSON string", lambda p: p.write_bytes(b'"x"\n')),
        ("has an mcpServers that is a list", lambda p: p.write_bytes(b'{"mcpServers": []}\n')),
        ("is cut off inside a token", lambda p: p.write_bytes(truncated)),
        (
            "holds a number that JSON writes in other text",
            lambda p: p.write_bytes(b'{"mcpServers": {"other": {"timeout": 1e400}}}\n'),
        ),
        (
            "holds such a number in a server named kaimon.x",
            lambda p: p.write_bytes(b'{"mcpServers": {"kaimon.x": {"timeout": 1e400}}}\n'),
        ),
        (
            "holds such a number in a top-level key named mcpServers.kaimon",
            lambda p: p.write_bytes(b'{"mcpServers.kaimon": 1e400, "mcpServers": {}}\n'),
        ),
        (
            "holds the key mcpServers twice",
            lambda p: p.write_bytes(b'{"mcpServers": {"a": {"url": "u"}}, "mcpServers": {"b": {}}}\n'),
        ),
        (
            "holds a key of a server twice",
            lambda p: p.write_bytes(b'{"mcpServers": {"a": {"url": "u", "url": "v"}}}\n'),
        ),
        (
            "holds a key twice in a top-level key named kaimon",
            lambda p: p.write_bytes(b'{"kaimon": {"u": 1, "u": 2}, "mcpServers": {}}\n'),
        ),
        (
            "holds a key twice in a server named kaimon.x",
            lambda p: p.write_bytes(b'{"mcpServers": {"kaimon.x": {"u": 1, "u": 2}}}\n'),
        ),
        (
            "holds a key twice in a key named kaimon of a server",
            lambda p: p.write_bytes(b'{"mcpServers": {"o": {"kaimon": {"u": 1, "u": 2}}}}\n'),
        ),
        ("is not UTF-8", lambda p: p.write_bytes(b"\xff\n")),
        ("is a directory", lambda p: p.mkdir()),
        ("is a FIFO", os.mkfifo),
    ]:
        base, config = fresh()
        make(config)
        snapshot = scratch.snapshot(base)
        code, out = run(base, "--apply")
        case(
            lambda: (
                scratch.refused(code, out)
                and str(config) in out
                and "fake-old" not in out
                and scratch.snapshot(base) == snapshot
            ),
            f"a mcp_config.json that {label} exits 2, names the file, prints none of its text, and nothing is "
            f"written: {code}, {tail(out)!r}",
        )
    for label, token_text, data in [
        (
            "no token file, and a file with another server and a stale Kaimon entry",
            None,
            json.dumps({"mcpServers": {"other": {"command": "x"}, "kaimon": {"url": "u"}}}) + "\n",
        ),
        (
            "an empty token file, and that file",
            "\n",
            json.dumps({"mcpServers": {"other": {"command": "x"}, "kaimon": {"url": "u"}}}) + "\n",
        ),
        ("no token file, and a file that is not JSON", None, "not json\n"),
    ]:
        base, config = fresh(token_text)
        config.write_text(data)
        config.chmod(0o644)
        code, out = run(base, "--apply")
        warned = [w for w in out.split("WARNING: ")[1:] if "writes no Kaimon entry" in w]
        case(
            lambda: (
                code == 0
                and config.read_text() == data
                and scratch.mode(config) == 0o644
                and len(warned) == 1
                and line.findall(out) == []
            ),
            f"with {label}, --apply leaves the file as it is, with one warning and no line of it: {code}, "
            f"{warned}, {tail(out)!r}",
        )

    for label, make in [
        ("does not exist", lambda p: None),
        ("is empty", lambda p: p.write_text("\n")),
        ("is a directory", lambda p: p.mkdir()),
        ("is a FIFO", os.mkfifo),
        ("is not UTF-8", lambda p: p.write_bytes(b"\xff\n")),
    ]:
        base, _, _ = scratch.fresh()
        (base / "home" / ".gemini").mkdir()
        token = base / "home" / ".config" / "kaimon" / "auth-token"
        token.parent.mkdir(parents=True)
        make(token)
        code, text = run(base, "--apply")
        warned = [w for w in text.split("WARNING: ")[1:] if "writes no Kaimon entry" in w]
        case(
            lambda: (
                code == 0
                and line.findall(text) == []
                and len(warned) == 1
                and "auth-token" in warned[0]
                and not (base / "home" / ".gemini" / "config" / "mcp_config.json").exists()
            ),
            f"a token file that {label} writes no Kaimon entry and gives one warning: {code}, {warned}",
        )
