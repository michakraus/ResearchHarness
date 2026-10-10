"""The adapter of OpenCode: its part of `harness install`, and the generators of the agents, the
permission block and the skill links.

    harness permissions [--apply]    # the permission block of opencode.jsonc and guard-paths.json
    harness install [--apply] [--force]

`harness install` installs into OpenCode's configuration directory, $OPENCODE_CONFIG_DIR, else
~/.config/opencode, which must exist:

  adapters/opencode/opencode.jsonc -> opencode.jsonc       (REPLACED, after a backup; rendered)
  adapters/opencode/OPENCODE-DELTA.md -> AGENTS.md         (OpenCode's global instruction file)
  agents/*.md                      -> agents/               (rendered with the model tables, below)
  adapters/opencode/agents/*.md    -> agents/               (the agents with no Claude Code source)
  adapters/opencode/plugins/*.ts   -> plugins/              (added; other plugins untouched)
  adapters/opencode/plugins/guard-paths.json -> plugins/    (the path guard's deny list; rendered)
  ~/.agents/skills/<name>          -> ~/.claude/skills/<name>, links to the curated skills, after
                                      the Claude Code layer, so that they see the skills it installs

opencode.jsonc and guard-paths.json hold {home} and {opencode_providers}, rendered with the
private profile. The agents are rendered from their neutral source in agents/, not from the
installed copies, with the [opencode] tables of the model tables. OpenCode reads AGENTS.md of its
configuration directory in place of ~/.claude/CLAUDE.md, and RTK.md, the core and the tree
instructions through `instructions` in opencode.jsonc. An installed agent or plugin with no copy
here is reported, with the command that removes it.

The installed opencode.jsonc can hold a secret that the repository's copy must never contain. If
it holds a literal `Authorization` value, the install refuses to replace it, unless `--force`,
and exits 2: replacing it would remove a working credential.

`harness install` renders the agents and the skill links on every run; nothing of them is
committed. The permission block and `plugins/guard-paths.json` hold no profile value, so they
stay committed, and `harness permissions` regenerates them from the settings template.

THE AGENTS. Each agent of agents/ becomes an OpenCode agent; a rendered
copy has one source, so it cannot drift from it. What changes in the port, and nothing else does:

1. The frontmatter. The `description:` line is copied as raw text. The neutral `tools:` (`shell`
   is `bash`, `agent` is `task`, `mcp/kaimon/<tool>` is `kaimon_<tool>`), `skills:` and
   `permissionMode:` have no OpenCode key, so all three become `permission:`. The tier of `model:`
   maps through [opencode.models] of the model tables (`models.toml`), unless `model_overrides`
   names the agent; an agent
   with no `model:` inherits its caller's model in both harnesses. `councils` adds copies of an
   agent on other models. `effort:`, `omitClaudeMd:`, `cacheTtl:` and `isolation:` have no
   OpenCode equivalent and are dropped; the last one becomes a rule in the preamble.
2. MCP tool names. OpenCode names an MCP tool `<server>_<tool>`, so `mcp__kaimon__ex` in the body
   becomes `kaimon_ex`.
3. A preamble, "Under OpenCode", before the body. It replaces each Claude Code mechanism the agent
   depends on: preloaded skills, worktree isolation, the `Agent` tool and background runs. An
   agent that uses none of them gets only the sandbox line.

THE PERMISSION BLOCK translates the `deny` and `ask` rules of the settings template. A
hand-copied list is where a typo becomes a silent hole, so the translation round-trips: every
input rule is emitted or listed in the report with the reason it was dropped, and the counts add
up. Three semantic differences:

1. Claude resolves by category (deny beats ask beats allow) and ignores order; OpenCode takes the
   last matching rule within one object. So `ask` is emitted first and `deny` after it.
2. Claude's `allow` list is not ported. Under Claude Code `autoAllowBashIfSandboxed` approves any
   sandboxed command, so most of that list is inert; OpenCode has no sandbox and defaults to
   allow, so porting it would add untested patterns that can only produce false prompts.
3. Claude writes `Bash(cmd *)`, `Read(//abs/path)` and `mcp__server__tool`. OpenCode keys by tool
   name, and MCP tools are `<server>_<tool>`. The `//` prefix of Claude's absolute paths is
   reduced to one slash.

THE SKILL LINKS. ~/.agents/skills/ holds a link to each curated skill: every directory directly
below ~/.claude/skills/ that holds a SKILL.md, except a dot directory and
`sources.EXCLUDED_SKILLS`. Every link there that points into
~/.claude/skills/ is this generator's own; anything else is reported with the command that
removes it, and left in place.
"""

import argparse
import contextlib
import difflib
import io
import json
import os
import pathlib
import re
import stat
import tempfile
from unittest import mock

from harness import REPO, HarnessError, changing, frontends, frontmatter, install, outcome, sources
from harness import profile as profile_module

NAME = "opencode"
TEMPLATES = ["adapters/opencode/opencode.jsonc", "adapters/opencode/plugins/guard-paths.json"]

SOURCE = REPO / "adapters" / "opencode"
SETTINGS = REPO / "settings" / "settings.proposal.json"
FIXTURES = SOURCE / "fixtures"

# The agents of adapters/opencode/agents/: written by hand, with no Claude Code source.
OPENCODE_ONLY = ["local", "qwen-worker"]

# Narrower than the tool list can say. OpenCode's `edit` covers edit, write and patch together,
# so an agent whose Claude body confines it to one file gets that file as a path rule.
EDIT_OVERRIDES = {
    "changelog-scribe": [("*", "deny"), ("**/CHANGELOG.md", "allow")],
}

MCP_PREFIX = "mcp__kaimon__"

# The sub-tables of [opencode] in models.toml; every one is optional.
MODEL_TABLES = ["models", "model_overrides", "model_variants", "variants", "reasoning_effort", "councils"]

# The number of critics of a council, its agent and its seats, as the preamble writes it; a
# council has one to eight seats.
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}

# MCP servers configured for OpenCode. A rule naming any other server is dropped: the tool
# cannot be called, so a permission for it is dead weight in every prompt.
OPENCODE_MCP_SERVERS = ["kaimon"]

# Kaimon tools already disabled server-side in ~/Research/.kaimon/tools.json. That file governs
# the server, which serves BOTH harnesses, so these are unreachable here regardless of any
# permission rule. Re-stating them would imply a control that is actually applied elsewhere.
KAIMON_SERVER_SIDE_DISABLED = [
    "connect_tcp", "set_tty", "format_code", "lint_package",
    "code_typed", "code_lowered", "profile_code",
]

# Claude tool name -> OpenCode permission key. OpenCode's `edit` covers edit, write and patch
# together, so Claude's Edit and Write both land there.
CLAUDE_TO_OPENCODE_TOOL = {
    "Bash": "bash", "Read": "read", "Edit": "edit", "Write": "edit",
    "Glob": "glob", "Grep": "grep", "WebFetch": "webfetch", "WebSearch": "websearch",
}

# Rules with no Claude counterpart, because they guard files that only OpenCode reads. They are
# appended last so they win over anything above them.
#
# Claude Code denies an edit of the installed ~/.claude/agents/** and puts ~/.claude/skills/**
# behind `ask`. The OpenCode equivalents are installed into ~/.config/opencode, itself `deny`
# through Claude's ~/.config/** rule; without these the same files are guarded under one harness
# and not the other.
#
# OpenCode's own credentials have no Claude rule either: `auth.json` holds the API key of every
# provider. Claude Code's sandbox never lets a command read it; OpenCode has no sandbox, so a
# `read` deny and the path guard are what is left.
#
# `kill` and `pkill` ask here and not in Claude Code. There the sandbox lets a signal reach only
# the same command; OpenCode has no sandbox, so `kill` reaches every process of the user.
#
# `external_directory` allows the paths outside the session root that the instructions send an
# agent to: ~/Research for a session rooted in a worktree, the rule, skill and agent files, the
# installed OpenCode configuration, the installed Julia package sources, and /tmp. Edits there
# stay gated: ~/.config/** and the installed agents and skills are denied, other skills ask, the
# rules get their own `edit` ask below, which wins over the template's deny (K10), and
# ~/.julia/packages/** is denied, because no other rule gates an edit there.
OPENCODE_ONLY_RULES = [
    ("read", [("{home}/.local/share/opencode/**", "deny")]),
    ("bash", [("kill *", "ask"), ("pkill *", "ask")]),
    ("edit", [
        ("{harness}/adapters/opencode/**", "ask"),
        ("{home}/.claude/rules/**", "ask"),
        ("{home}/.julia/packages/**", "deny"),
    ]),
    ("external_directory", [
        ("{home}/.julia/packages/*", "allow"),
        ("{home}/Research/*", "allow"),
        ("{home}/.claude/rules/*", "allow"),
        ("{home}/.claude/skills/*", "allow"),
        ("{home}/.claude/agents/*", "allow"),
        ("{home}/.config/opencode/*", "allow"),
        ("/tmp/*", "allow"),
    ]),
]

RESTART = "Restart OpenCode: its installed files changed, and it reads its configuration once, at startup."


# ---------------------------------------------------------------------------------------------
# The model tables


def load_models(path):
    """The [opencode] tables of the models.toml at `path`, every sub-table present."""
    path = pathlib.Path(path)
    table = profile_module.read_models(path).get("opencode")
    if not isinstance(table, dict):
        raise HarnessError(f"{path} has no [opencode] table — examples/models.toml shows it")
    unknown = sorted(set(table) - set(MODEL_TABLES))
    if unknown:
        raise HarnessError(f"{path}: [opencode] has no sub-table {', '.join(unknown)}; "
                           f"it has {', '.join(MODEL_TABLES)}")
    models = {name: table.get(name, {}) for name in MODEL_TABLES}
    for name in MODEL_TABLES:
        if not isinstance(models[name], dict):
            raise HarnessError(f"{path}: [opencode.{name}] is not a table")
        if name != "councils" and not all(isinstance(v, str) for v in models[name].values()):
            raise HarnessError(f"{path}: a value of [opencode.{name}] is not a string")
    # Each seat is installed as `<name>.md`, so a second seat of one name would replace the first.
    seen = {}
    for agent, seats in models["councils"].items():
        if not (isinstance(seats, list) and all(isinstance(s, dict) and set(s) == {"name", "model"}
                                                for s in seats)):
            raise HarnessError(f"{path}: councils.{agent} is a list of {{ name = …, model = … }}")
        if len(seats) + 1 not in NUMBER_WORDS:
            raise HarnessError(f"{path}: councils.{agent} has {len(seats)} seats; a council has 1 to 8")
        for seat in seats:
            if not isinstance(seat["name"], str):
                raise HarnessError(f"{path}: the seat name {seat['name']!r} of councils.{agent} is not a string")
            if seat["name"] in seen:
                raise HarnessError(f"{path}: the seat {seat['name']!r} of councils.{agent} is also a seat "
                                   f"of councils.{seen[seat['name']]}")
            seen[seat["name"]] = agent
    models["path"] = path
    return models


# ---------------------------------------------------------------------------------------------
# The agents


def generated_comment(source):
    return (f"<!-- Generated by `harness install` from ~/.claude/agents/{source}.md. Do not edit "
            f"this file: edit the source and run `harness install --apply`. -->")


def permission_block(name, meta):
    tools = set(meta.get("tools", []))
    lines = ["permission:"]
    if name in EDIT_OVERRIDES:
        lines.append("  edit:")
        lines += [f'    "{pattern}": {action}' for pattern, action in EDIT_OVERRIDES[name]]
    elif meta.get("permissionMode") == "plan" or not tools & {"edit", "write"}:
        lines.append("  edit: deny")
    for tool, key in (("shell", "bash"), ("agent", "task"), ("web_fetch", "webfetch"), ("web_search", "websearch")):
        if tool not in tools:
            lines.append(f"  {key}: deny")
    # OpenCode takes the last matching rule, so the allows follow the deny.
    lines.append("  kaimon_*: deny")
    lines += [f"  kaimon_{t[len(frontmatter.MCP):]}: allow"
              for t in sorted(t for t in tools if t.startswith(frontmatter.MCP))]
    lines += ["  skill:", '    "*": deny']
    lines += [f"    {skill}: allow" for skill in meta.get("skills", [])]
    return "\n".join(lines)


def preamble(name, meta, body, models):
    tools = set(meta.get("tools", []))
    rules = [
        "There is no sandbox here. Where the text below gives a rule that exists only because of "
        "the Claude Code sandbox or its permission matcher, the global `AGENTS.md` overrides it.",
    ]
    if name in models["councils"]:
        critics = [f"1{chr(ord('a') + i)}" for i in range(len(models["councils"][name]) + 1)]
        dirs = [f"`round-{c}/`" for c in critics]
        rules.append(
            f"**Round 1 has {NUMBER_WORDS[len(critics)]} critics here, {sources.code_list(critics)}**, each on a "
            f"different model, and your probe directory is {', '.join(dirs[:-1])} or {dirs[-1]}. Judge "
            "as the text below says; the text names only two because Claude Code runs two.")
    skills = meta.get("skills", [])
    if skills:
        rules.append(
            f"**Load the {sources.code_list(skills)} skill{'s' if len(skills) > 1 else ''} with the "
            "`skill` tool before you start.** Claude Code loads them for you; OpenCode does not. "
            "You may load no other skill.")
    if meta.get("isolation") == "worktree" or "isolation" in body:
        rules.append(
            "**Nothing makes a worktree for you.** OpenCode has no `isolation: worktree`. If your "
            "caller names an existing worktree, work in it and make none. Otherwise make it "
            "yourself before anything else, in the repository your caller names, with a short "
            "slug of your own:\n\n"
            "  ```bash\n"
            "  cd ~/Research/<Packages or Experiments>/<Repository>\n"
            "  git fetch origin\n"
            "  git worktree add --detach ~/Research/.worktrees/<Repository>-agent-<slug> origin/HEAD\n"
            "  ```\n\n"
            "  Then pass the worktree as `workdir` on every command. Where the text below says that your "
            "caller made the worktree, or that `pwd` is already in it, read it as the worktree that "
            "you made. Report its path; your caller removes it.")
    if "agent" in tools:
        rules.append(
            "The `Agent` tool is the `task` tool here. A `task` call returns when the child returns. "
            "Ignore each instruction about `run_in_background` for an agent call.")
    # Every agent with `shell`, not only those whose text names `run_in_background`: the default
    # `timeout` is short, and a full suite under julia-test-runner runs for 20–100 minutes.
    if "shell" in tools:
        rules.append(
            "The `bash` tool has no background mode, and its default `timeout` is short. Every "
            "command runs in the foreground until it ends or its `timeout` expires, so give a "
            "test suite, a precompile or any other long run a `timeout` that covers it.")
    return ("## Under OpenCode\n\nThis agent is ported from Claude Code. Where the text below names "
            "a Claude Code mechanism, these rules replace it:\n\n" + "\n".join("- " + r for r in rules) + "\n")


def port(path, models):
    """The OpenCode agent for one Claude Code agent, then its council copies: [(name, text), …].
    A copy differs from the agent in its name, its model, `hidden: true` and its description."""
    path = pathlib.Path(path)
    source = path.name.removesuffix(".md")
    fm = frontmatter.parse_file(path)
    meta = fm.meta
    if "description" not in fm.lines:
        raise HarnessError(f"{path}: no `description:` line")
    model = None
    if "model" in meta:
        tier = meta["model"]
        if not isinstance(tier, str) or tier not in models["models"]:
            raise HarnessError(f"{path}: the tier {tier!r} has no entry in [opencode.models] of {models['path']}")
        model = models["models"][tier]
    model = models["model_overrides"].get(source, model)
    body = fm.body.replace(MCP_PREFIX, "kaimon_")
    rest = preamble(source, meta, body, models) + "\n" + body.lstrip("\n")

    def render(name, description, model, hidden):
        head = ["---", description, "mode: subagent"]
        if hidden:
            head.append("hidden: true")
        if model is not None:
            head.append(f"model: {model}")
        variant = models["variants"].get(name, models["model_variants"].get(model))
        if variant is not None:
            head.append(f"variant: {variant}")
        if name in models["reasoning_effort"]:
            head.append(f"reasoningEffort: {models['reasoning_effort'][name]}")
        head += [permission_block(source, meta), "---"]
        return "\n".join(head) + "\n\n" + generated_comment(source) + "\n\n" + rest

    agents = [(source, render(source, fm.lines["description"], model, False))]
    for seat in models["councils"].get(source, []):
        description = (f'description: "A member of the round-1 critic council of build-part under '
                       f'OpenCode, on {seat["model"]}. The same agent as {source}, which has the full '
                       f'description. Spawn it only as the build-part dispatcher."')
        agents.append((seat["name"], render(seat["name"], description, seat["model"], True)))
    return agents


def render_agents(source_dir, models):
    """Every agent of `source_dir` and its council copies, ported: [(name, text), …]. A council
    keyed by a name that no agent of `source_dir` has exits 2."""
    paths = sorted(pathlib.Path(source_dir).glob("*.md"))
    sources = {p.stem: p for p in paths}
    clash = sorted(set(sources) & set(OPENCODE_ONLY))
    if clash:
        raise HarnessError(f"{source_dir}: more than one agent named {', '.join(clash)}")
    taken = {**sources, **{name: SOURCE / "agents" / f"{name}.md" for name in OPENCODE_ONLY}}
    for agent, seats in models["councils"].items():
        if agent not in sources:
            raise HarnessError(f"{models['path']}: councils.{agent} names no agent of {source_dir}; "
                               "a council is keyed by the agent it copies")
        for seat in seats:
            if seat["name"] in taken:
                raise HarnessError(f"{models['path']}: the seat {seat['name']!r} of councils.{agent} has the "
                                   f"name of the agent {taken[seat['name']]}")
    return [a for path in paths for a in port(path, models)]


# ---------------------------------------------------------------------------------------------
# The permission block


def parse_rule(rule):
    """(kind, key, pattern) of one Claude rule, `kind` "tool" or "mcp"; None for another form."""
    m = re.fullmatch(r"([A-Za-z]+)\((.*)\)", rule)
    if m:
        tool, pattern = m.groups()
        # Claude writes an absolute path as //abs/path; one slash is the real path. In the
        # template that is /{home}/..., and OpenCode's pattern is {home}/....
        pattern = re.sub(r"^/\{home\}", "{home}", re.sub(r"^//", "/", pattern))
        key = CLAUDE_TO_OPENCODE_TOOL.get(tool)
        return None if key is None else ("tool", key, pattern)
    if rule.startswith("mcp__"):
        return ("mcp", rule, "")
    return None


def classify_mcp(rule):
    """("emit", name) or ("drop", reason)."""
    parts = rule.split("__")
    if len(parts) < 3:
        return ("drop", "unparseable MCP rule")
    server, tool = parts[1], "__".join(parts[2:])
    if server not in OPENCODE_MCP_SERVERS:
        return ("drop", f"server '{server}' is not configured for OpenCode")
    if server == "kaimon" and tool in KAIMON_SERVER_SIDE_DISABLED:
        return ("drop", "already disabled server-side in ~/Research/.kaimon/tools.json")
    return ("emit", f"{server}_{tool}")


def collect_rules(settings=SETTINGS):
    """(emitted, dropped, permissions): `emitted` maps an OpenCode key to [(pattern, action)],
    `dropped` is [(rule, action, reason)], `permissions` the template's own object."""
    permissions = json.loads(pathlib.Path(settings).read_text())["permissions"]
    emitted, dropped = {}, []
    # `ask` first, then `deny`: OpenCode takes the last matching rule, so deny beats ask.
    for action in ("ask", "deny"):
        for rule in permissions.get(action, []):
            parsed = parse_rule(rule)
            if parsed is None:
                dropped.append((rule, action, "not a recognised rule form"))
                continue
            kind, key, pattern = parsed
            if kind == "mcp":
                verdict, payload = classify_mcp(key)
                if verdict == "drop":
                    dropped.append((rule, action, payload))
                    continue
                # An MCP tool has no sub-pattern: the key is the tool.
                emitted.setdefault(payload, []).append(("*", action))
            else:
                emitted.setdefault(key, []).append((pattern, action))
    for key, rules in OPENCODE_ONLY_RULES:
        emitted.setdefault(key, []).extend(rules)
    return emitted, dropped, permissions


def json_key(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_block(emitted):
    """The `permission` block as JSONC, in a stable order; `bash`, the largest, goes last."""
    order = ["read", "edit", "external_directory", "glob", "grep", "webfetch", "websearch"]
    mcp = sorted(k for k in emitted if any(k.startswith(s + "_") for s in OPENCODE_MCP_SERVERS))
    keys = [k for k in order if k in emitted] + mcp + (["bash"] if "bash" in emitted else [])
    out = ['  "permission": {\n']
    for i, key in enumerate(keys):
        rules = emitted[key]
        # An MCP tool carries a single "*" rule; it renders as a bare action.
        if len(rules) == 1 and rules[0][0] == "*":
            out.append(f'    {json_key(key)}: "{rules[0][1]}"')
        else:
            out.append(f"    {json_key(key)}: {{\n")
            out += [f'      {json_key(p)}: "{a}"' + ("\n" if j == len(rules) - 1 else ",\n")
                    for j, (p, a) in enumerate(rules)]
            out.append("    }")
        out.append("\n" if i == len(keys) - 1 else ",\n")
    out.append("  }\n")
    return "".join(out)


def guard(emitted):
    """`plugins/guard-paths.json`: the `read` denies, for the path guard of `plugins/guards.ts`,
    which applies them to the paths a `bash` command names."""
    return json.dumps({"deny": [p for p, a in emitted["read"] if a == "deny"]}, indent=2, ensure_ascii=False) + "\n"


def report(emitted, dropped, permissions):
    """The audit: the counts, the round trip, the rules per key and the dropped rules."""
    n_in = len(permissions.get("deny", [])) + len(permissions.get("ask", []))
    n_out = sum(len(v) for v in emitted.values())
    n_new = sum(len(rules) for _, rules in OPENCODE_ONLY_RULES)
    # The OpenCode-only rules have no input counterpart, so they are subtracted before the
    # identity is checked; otherwise adding one would mask a rule that went missing.
    lines = [
        f"input rules (deny + ask): {n_in}",
        f"emitted:                  {n_out} ({n_new} OpenCode-only)",
        f"dropped:                  {len(dropped)}",
        f"round-trip:               {'OK' if (n_out - n_new) + len(dropped) == n_in else 'MISMATCH'}",
        "",
        "per permission key:",
        *(f"  {key.ljust(24)}{len(emitted[key])}" for key in sorted(emitted)),
        "",
        "dropped rules, with the reason:",
        *(f"  [{action}] {rule.ljust(44)}{reason}" for rule, action, reason in dropped),
        "",
        f"NOT PORTED BY DESIGN: the {len(permissions.get('allow', []))} `allow` rules. OpenCode has no sandbox and",
        "defaults to allow, so they would add untested patterns and no control.",
    ]
    return "\n".join(lines) + "\n"


BLOCK = re.compile(r'^  "permission": \{\n.*?^  \}\n', re.M | re.S)


def permission_files(emitted, source=SOURCE):
    """[(path, committed text, generated text)] of opencode.jsonc and plugins/guard-paths.json."""
    config = source / "opencode.jsonc"
    text = config.read_text()
    if not BLOCK.search(text):
        raise HarnessError(f'no `  "permission": {{` block in {config}')
    guard_path = source / "plugins" / "guard-paths.json"
    return [(config, text, BLOCK.sub(lambda m: render_block(emitted), text)),
            (guard_path, guard_path.read_text(), guard(emitted))]


def cmd_permissions(args):
    emitted, dropped, permissions = collect_rules()
    print(report(emitted, dropped, permissions))
    changes = 0
    for path, committed, generated in permission_files(emitted):
        label = str(path.relative_to(REPO))
        if committed == generated:
            print(f"{label:<34} already identical")
            continue
        changes += 1
        print(f"{label:<34} REPLACE")
        for line in difflib.unified_diff(committed.splitlines(), generated.splitlines(), lineterm="", n=0):
            if not line.startswith(("---", "+++")):
                print("    " + line)
        if args.apply:
            path.write_text(generated)
    print(f"\n{changes} change(s) {'made' if args.apply else 'to make'}.")
    return outcome(args, changes)


# ---------------------------------------------------------------------------------------------
# The skill links


def skill_links(home, apply):
    """Link each curated skill of `home`/.claude/skills into `home`/.agents/skills.

    [(name, status, changes)]: `changes` is 1 for a link to create, repoint or remove, and 0 for
    an identical link and for FOREIGN and EXTRA, which are reported with their removal command."""
    source = pathlib.Path(home) / ".claude" / "skills"
    target = pathlib.Path(home) / ".agents" / "skills"
    names = sources.curated_skills(source)

    def ours(p):
        return p.is_symlink() and os.readlink(p).startswith(f"{source}/")

    if apply:
        target.mkdir(parents=True, exist_ok=True)
    out = []
    for name in names:
        link, want = target / name, str(source / name)
        if link.is_symlink() and os.readlink(link) == want:
            out.append((name, "already identical", 0))
        elif (link.is_symlink() or link.exists()) and not ours(link):
            out.append((name, f"FOREIGN — not a link into {source}. To remove it:  rm -r '{link}'", 0))
        elif not apply:
            out.append((name, f"STALE -> {os.readlink(link)}" if link.is_symlink() else "MISSING", 1))
        else:
            existed = link.is_symlink()
            if existed:
                link.unlink()
            link.symlink_to(want)
            out.append((name, "updated" if existed else "created", 1))
    for name in sorted(os.listdir(target)) if target.is_dir() else []:
        if name in names:
            continue
        link = target / name
        if ours(link):
            if apply:
                link.unlink()
            out.append((name, "removed" if apply else "REMOVE — no longer a curated skill", 1))
        else:
            out.append((name, f"EXTRA — not a curated skill. To remove it:  rm -r '{link}'", 0))
    return out


# ---------------------------------------------------------------------------------------------
# The install


def destination():
    """OpenCode's configuration directory: $OPENCODE_CONFIG_DIR, else ~/.config/opencode."""
    return pathlib.Path(os.environ.get("OPENCODE_CONFIG_DIR") or pathlib.Path.home() / ".config" / "opencode")


def literal_secret(path):
    """True when the installed opencode.jsonc holds a literal Authorization value."""
    if not path.is_file():
        return False
    text = path.read_text()
    return ('"Authorization"' in text and not re.search(r"Authorization.*\{file:", text)
            and "FILL-IN-TOKEN" not in text)


def drift_checks():
    """The repository's generated files against their generators: [(line, …)], each a warning,
    not a change."""
    # The permission block is generated from the settings template. The round-trip proves the
    # generator accounts for every rule; only the comparison with opencode.jsonc proves that the
    # block in the file is the block it emits today. A stale deny list is the failure this
    # arrangement exists to prevent, so report it, and do not fix it: the regenerated block
    # belongs in a reviewed commit, through `harness permissions --apply`. The path guard's deny
    # list is the `read` denies of the same block; a stale copy leaves a credential readable
    # through `bash` that the `read` tool may not read.
    warnings = []
    emitted, dropped, permissions = collect_rules()
    if "round-trip:               OK" not in report(emitted, dropped, permissions):
        warnings.append(("the permission block does not round-trip against settings/settings.proposal.json.",
                         "The block in opencode.jsonc may be stale or incomplete. Run `harness permissions`",
                         "and read the dropped list."))
    for path, committed, generated in permission_files(emitted):
        if committed != generated:
            diff = [l for l in difflib.ndiff(committed.splitlines(), generated.splitlines()) if l[:1] in "-+"]
            warnings.append((f"{path.relative_to(REPO)} is not what the settings template gives today:",
                             *("  " + l for l in diff),
                             "'-' is in the committed file only, '+' is in the settings template only.",
                             "Run `harness permissions --apply`, read the diff, commit, then install."))
    return warnings


def plan(ctx):
    """OpenCode's part of `harness install`, as the docstring of this module says."""
    dest = destination()
    if not dest.is_dir():
        raise HarnessError(f"{dest} does not exist. Start OpenCode once, then re-run.")
    agents = render_agents(ctx.agents, load_models(ctx.models))
    committed = sorted(f.stem for f in (SOURCE / "agents").glob("*.md"))
    if committed != sorted(OPENCODE_ONLY):
        raise HarnessError(f"adapters/opencode/agents/ holds {', '.join(committed) or 'nothing'}; "
                           f"it must hold {', '.join(OPENCODE_ONLY)}, the agents with no Claude Code source")
    agents = sorted(agents + [(n, (SOURCE / "agents" / f"{n}.md").read_text()) for n in committed])
    files, refused, warnings = [], [], []

    config = dest / "opencode.jsonc"
    if literal_secret(config) and not ctx.args.force:
        refused.append((["opencode.jsonc                     REFUSED — the installed file holds a literal Authorization",
                         "                                   value, and replacing it would remove that credential. Move",
                         "                                   the token into ~/.config/kaimon/opencode-token, use",
                         '                                   "Authorization": "Bearer {file:~/.config/kaimon/opencode-token}",',
                         "                                   then re-run; --force overwrites anyway, after a backup."],
                        "opencode.jsonc not replaced: the installed file holds a literal credential"))
    else:
        files.append((config, profile_module.render_file(SOURCE / "opencode.jsonc", ctx.profile).encode(), None,
                      "opencode.jsonc", True))
    # OpenCode loads the first that exists of AGENTS.md in its configuration directory and
    # ~/.claude/CLAUDE.md, so this file replaces the Claude Code one and leaves the directory-scoped
    # CLAUDE.md files alone.
    files.append((dest / "AGENTS.md", (SOURCE / "OPENCODE-DELTA.md").read_bytes(), 0o644,
                  "AGENTS.md from OPENCODE-DELTA.md"))

    # The token file must exist before Kaimon is enabled, or OpenCode sends an empty bearer and
    # every request is refused with 401.
    token = pathlib.Path.home() / ".config" / "kaimon" / "opencode-token"
    if '"enabled": true' in (SOURCE / "opencode.jsonc").read_text():
        try:
            missing = not stat.S_ISREG(token.stat().st_mode)
        except FileNotFoundError:
            missing = True
        except OSError as e:  # a sandbox that denies the path; `is_file` would hide it on Python 3.14
            missing = False
            warnings.append((f"{token} cannot be checked: {e}",
                             "The Kaimon entry is enabled; if the file does not exist, Kaimon will answer 401."))
        if missing:
            warnings.append(("~/.config/kaimon/opencode-token does not exist, and the Kaimon entry is",
                             "enabled. Create it (mode 600, the token alone) or Kaimon will answer 401."))

    files += [(dest / "agents" / f"{name}.md", text.encode(), None, f"agents/{name}.md") for name, text in agents]
    files += [(dest / "plugins" / f.name, f.read_bytes(), None, f"plugins/{f.name}")
              for f in sorted((SOURCE / "plugins").glob("*.ts"))]
    guard_list = profile_module.render_file(SOURCE / "plugins" / "guard-paths.json", ctx.profile).encode()
    files.append((dest / "plugins" / "guard-paths.json", guard_list, None, "plugins/guard-paths.json"))

    # ~/.agents/skills/ holds links to the curated skills only. The links follow every frontend's
    # files, so that they see the skills that the Claude Code layer installs.
    def links(apply):
        changes = 0
        for name, status, change in skill_links(pathlib.Path.home(), apply):
            print(f"{'skills/' + name:<34} {status}")
            changes += change
        return changes

    if not os.access("/opt/homebrew/bin/rtk", os.X_OK):
        warnings.append(("/opt/homebrew/bin/rtk is not executable. The rtk plugin then leaves",
                         "every command unchanged. Correct the path in plugins/rtk.ts."))
    warnings += drift_checks()

    # An installed agent or plugin with no copy here is left in place, and OpenCode still loads it.
    ours = {"agents": {f"{name}.md" for name, _ in agents},
            "plugins": {f.name for f in (SOURCE / "plugins").glob("*.ts")}}
    extra = [f"\nEXTRA: {f} is installed and has no copy here. OpenCode still loads it.\n"
             f"       To remove it:  rm '{f}'"
             for kind, ext in (("agents", "md"), ("plugins", "ts"))
             for f in sorted((dest / kind).glob(f"*.{ext}")) if f.name not in ours[kind]]
    return frontends.Plan(files=files, warnings=warnings, extra=extra, refused=refused, after=[links])


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`


def selftest():
    """The fixture agents, the permission fixtures and the skill links on a scratch home."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  opencode: {label}")

    # The example's council is on an agent of agents/; the fixtures' council is on `critic`.
    example = load_models(REPO / "examples" / "models.toml")
    models = dict(example, councils={"critic": [{"name": "critic-b", "model": "provider-c/other-model"},
                                                {"name": "critic-c", "model": "provider-b/medium-model"}]})
    # The expected files are the base Julia generator's on the dummy tables, with its
    # generated-by line replaced by generated_comment(): the one allowed difference.
    try:
        rendered = dict(render_agents(FIXTURES / "agents", models))
    except HarnessError as e:
        rendered = {}
        check(False, f"the fixture agents render: {e}")
    expected = {p.stem: p.read_text() for p in (FIXTURES / "expected").glob("*.md")}
    check(sorted(rendered) == sorted(expected), f"the agents and the council copies: {sorted(rendered)}")
    for name in sorted(expected):
        what = {"bare": "the agent with no tools", "planner": "permissionMode: plan with Edit",
                "critic-b": "the council copy", "critic-c": "the council copy"}.get(name, "the fixture")
        check(rendered.get(name) == expected[name], f"{what} {name}.md")

    # The council preamble counts its seats; each expected line is written by hand.
    for seats, line in [
        (["critic-b"],
         "- **Round 1 has two critics here, `1a` and `1b`**, each on a different model, and your probe "
         "directory is `round-1a/` or `round-1b/`. Judge as the text below says; the text names only "
         "two because Claude Code runs two.\n"),
        (["critic-b", "critic-c", "critic-d"],
         "- **Round 1 has four critics here, `1a`, `1b`, `1c` and `1d`**, each on a different model, and "
         "your probe directory is `round-1a/`, `round-1b/`, `round-1c/` or `round-1d/`. Judge as the text "
         "below says; the text names only two because Claude Code runs two.\n"),
        ([f"critic-{c}" for c in "bcdefghi"],
         "- **Round 1 has nine critics here, `1a`, `1b`, `1c`, `1d`, `1e`, `1f`, `1g`, `1h` and `1i`**, each "
         "on a different model, and your probe directory is `round-1a/`, `round-1b/`, `round-1c/`, "
         "`round-1d/`, `round-1e/`, `round-1f/`, `round-1g/`, `round-1h/` or `round-1i/`. Judge as the "
         "text below says; the text names only two because Claude Code runs two.\n"),
    ]:
        council = dict(models, councils={"critic": [{"name": s, "model": "provider-c/other-model"} for s in seats]})
        try:
            ported = port(FIXTURES / "agents" / "critic.md", council)
        except HarnessError as e:
            ported = [("error", str(e))]
        check([n for n, _ in ported] == ["critic", *seats] and all(line in t for _, t in ported),
              f"a council of {len(seats)} seat(s): {line.strip()}")

    with tempfile.TemporaryDirectory() as tmp:
        clash = pathlib.Path(tmp) / "agents"
        clash.mkdir()
        for name in ("critic", "critic-b"):
            (clash / f"{name}.md").write_text((FIXTURES / "agents" / "critic.md").read_text())
        try:
            render_agents(clash, models)
            check(False, "a seat with the name of a source agent exits 2")
        except HarnessError as e:
            check("councils.critic" in str(e) and str(clash / "critic-b.md") in str(e),
                  f"a seat with the name of a source agent exits 2: {e}")
        local = dict(models, councils={"critic": [{"name": "local", "model": "provider-c/other-model"}]})
        try:
            render_agents(FIXTURES / "agents", local)
            check(False, "a seat with the name of an agent of adapters/opencode/agents/ exits 2")
        except HarnessError as e:
            check(str(models["path"]) in str(e) and "councils.critic" in str(e)
                  and "adapters/opencode/agents/local.md" in str(e),
                  f"a seat with the name of an agent of adapters/opencode/agents/ exits 2: {e}")
        twin = pathlib.Path(tmp) / "twin"
        twin.mkdir()
        (twin / "local.md").write_text((FIXTURES / "agents" / "bare.md").read_text())
        try:
            render_agents(twin, models)
            check(False, "a source agent with the name of an agent of adapters/opencode/agents/ exits 2")
        except HarnessError as e:
            check(str(twin) in str(e) and str(e).endswith(" local"),
                  f"a source agent with the name of an agent of adapters/opencode/agents/ exits 2: {e}")
        # A council keyed by an agent with no source would be dropped with no error.
        for key in ("nosuch", "local"):
            orphan = dict(models, councils={key: [{"name": "seat-x", "model": "provider-c/other-model"}]})
            try:
                render_agents(FIXTURES / "agents", orphan)
                check(False, f"a council keyed by {key}, an agent with no source, exits 2")
            except HarnessError as e:
                check(str(models["path"]) in str(e) and f"councils.{key}" in str(e) and str(FIXTURES / "agents") in str(e),
                      f"a council keyed by {key}, an agent with no source, exits 2: {e}")

    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "unknown-tier.md"
        bad.write_text('---\nname: x\nmodel: nosuch\ndescription: "d"\n---\nbody\n')
        try:
            port(bad, models)
            check(False, "an unknown tier exits 2")
        except HarnessError as e:
            check(str(bad) in str(e) and "'nosuch'" in str(e), f"an unknown tier exits 2: {e}")
        for case in [(None, "a missing models.toml"), ("[claude]\n", "a models.toml without [opencode]"),
                            ("[opencode.modles]\n", "an unknown sub-table"),
                            ("[opencode\nmodels = 1\n", "a malformed models.toml"),
                            ('[opencode]\nmodels = "x"\n', "a sub-table that is a string"),
                            ('[opencode]\ncouncils = "x"\n', "councils that is a string"),
                            ("[opencode.models.large]\nx = 1\n", "a tier that maps to a table"),
                            ("[opencode.councils]\ncritic = []\n", "a council with no seat", "councils.critic"),
                            ("[opencode.councils]\ncritic = [\n" + "".join(
                                f'  {{ name = "s{i}", model = "m" }},\n' for i in range(9)) + "]\n",
                             "a council of nine seats", "councils.critic"),
                            ('[opencode.councils]\ncritic = [{ name = "s", model = "m" }]\n'
                             'judge = [{ name = "s", model = "n" }]\n',
                             "a seat name in a second council", "councils.critic", "councils.judge"),
                            ('[opencode.councils]\ncritic = [{ name = "s", model = "m" }, { name = "s", model = "n" }]\n',
                             "a seat name twice in one council", "councils.critic"),
                            *((f'[opencode.councils]\ncritic = [{{ name = {v}, model = "m" }}]\n',
                               f"a seat whose name is {label}", "councils.critic", "name")
                              for v, label in [("5", "a number"), ("true", "a boolean"), ('["s"]', "a list"),
                                               ("{ x = 1 }", "a table")])]:
            text, label, *names = case
            path = pathlib.Path(tmp) / "models.toml"
            if text is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(text)
            try:
                load_models(path)
                check(False, f"{label} exits 2")
            except HarnessError as e:
                check(str(path) in str(e) and all(n in str(e) for n in names), f"{label} exits 2: {e}")
        path.write_text("[opencode.councils]\ncritic = [\n" + "".join(
            f'  {{ name = "s{i}", model = "m" }},\n' for i in range(8)) + "]\n")
        try:
            check(len(load_models(path)["councils"]["critic"]) == 8, "a council of eight seats loads")
        except HarnessError as e:
            check(False, f"a council of eight seats loads: {e}")

    # The lookup order of models.toml: --models, then $RESEARCH_HARNESS_MODELS, then the profile's directory.
    saved = os.environ.pop("RESEARCH_HARNESS_MODELS", None)
    try:
        bare = argparse.Namespace(models=None, profile="/p/profile.toml")
        flag = argparse.Namespace(models="/m/flag.toml", profile="/p/profile.toml")
        order = [profile_module.models_path(bare)]
        os.environ["RESEARCH_HARNESS_MODELS"] = "/m/env.toml"
        order += [profile_module.models_path(bare), profile_module.models_path(flag)]
    finally:
        os.environ.pop("RESEARCH_HARNESS_MODELS", None)
        if saved is not None:
            os.environ["RESEARCH_HARNESS_MODELS"] = saved
    check(order == [pathlib.Path(p) for p in ("/p/models.toml", "/m/env.toml", "/m/flag.toml")],
          f"the models.toml lookup order: {order}")

    emitted, dropped, permissions = collect_rules(FIXTURES / "settings.json")
    check(render_block(emitted) == (FIXTURES / "permission-block.txt").read_text(), "the permission block")
    check(guard(emitted) == (FIXTURES / "guard-paths.json").read_text(), "the guard list")
    check(report(emitted, dropped, permissions) == (FIXTURES / "report.txt").read_text(), "the report")

    with tempfile.TemporaryDirectory() as tmp:
        home = pathlib.Path(tmp)
        skills = home / ".claude" / "skills"
        for d in ("curated", "synced", "synced/claude-ai", ".trash", "notes"):
            (skills / d).mkdir(parents=True)
        for d in ("curated", "synced", "synced/claude-ai", ".trash"):
            (skills / d / "SKILL.md").write_text("")
        dry = skill_links(home, False)
        check(dry == [("curated", "MISSING", 1)] and not (home / ".agents").exists(),
              f"skill links, dry run with no ~/.agents/skills: {dry}")
        applied = skill_links(home, True)
        links = {p.name: os.readlink(p) for p in (home / ".agents" / "skills").iterdir()}
        check(applied == [("curated", "created", 1)] and links == {"curated": str(skills / "curated")},
              f"skill links, --apply on the scratch home: {links}")
        target = home / ".agents" / "skills"
        (target / "gone").symlink_to(skills / "gone")
        (target / "other").mkdir()
        # A curated skill whose name is taken in ~/.agents/skills/ by a directory, not a link.
        (skills / "busy").mkdir()
        (skills / "busy" / "SKILL.md").write_text("")
        (target / "busy").mkdir()
        again = [(n, s.split(" ")[0], c) for n, s, c in skill_links(home, False)]
        check(again == [("busy", "FOREIGN", 0), ("curated", "already", 0), ("gone", "REMOVE", 1),
                        ("other", "EXTRA", 0)],
              f"skill links: a foreign entry at a curated name, identical, a stale own link, an extra entry: {again}")
        # An own link at a curated name that points to another skill: STALE, then repointed.
        (target / "curated").unlink()
        (target / "curated").symlink_to(skills / "synced")
        stale = [e for e in skill_links(home, False) if e[0] == "curated"]
        repointed = [e for e in skill_links(home, True) if e[0] == "curated"]
        check(stale == [("curated", f"STALE -> {skills / 'synced'}", 1)]
              and repointed == [("curated", "updated", 1)]
              and os.readlink(target / "curated") == str(skills / "curated"),
              f"skill links: a stale link at a curated name, dry run {stale} and --apply {repointed}")

    with tempfile.TemporaryDirectory() as tmp:
        install_cases(check, pathlib.Path(tmp))
    return total, wrong


def install_cases(check, tmp):
    """OpenCode's part of `harness install`, on scratch HOMEs below `tmp`: a token that cannot be
    checked is a warning, and the dry run goes on to its count line; a token file that does not
    exist, or a directory in its place, is missing. The agents and AGENTS.md."""
    from harness.install_cases import Scratch, scratch_profile

    # A token that the sandbox denies: `stat` raises for that path only.
    home = tmp / "home"
    (home / ".claude" / "skills").mkdir(parents=True)
    token = home / ".config" / "kaimon" / "opencode-token"
    path_stat = pathlib.Path.stat

    def denied(self, **kwargs):
        if self == token:
            raise PermissionError(1, "Operation not permitted", str(self))
        return path_stat(self, **kwargs)

    empty = tmp / "tree"
    empty.mkdir()
    dummy = scratch_profile(tmp / "profile.toml", empty)

    def dry_run(patch=contextlib.nullcontext()):
        out = io.StringIO()
        args = argparse.Namespace(profile=str(dummy),
                                  models=str(REPO / "examples" / "models.toml"), apply=False, force=False)
        try:
            with (mock.patch.dict(os.environ, HOME=str(home), OPENCODE_CONFIG_DIR=str(tmp),
                                  PI_CODING_AGENT_DIR=str(tmp / "omp")), patch,
                  contextlib.redirect_stdout(out)):
                install.cmd_install(args)
        except Exception as e:  # the case reports a crash as BAD instead of stopping `harness test`
            out.write(f"\nraised {type(e).__name__}: {e}")
        text = out.getvalue()
        return text, (text.strip().splitlines() or ["no output"])[-1]

    text, last = dry_run(mock.patch.object(pathlib.Path, "stat", denied))
    check(f"WARNING: {token}" in text and "Operation not permitted" in text
          and re.search(r"^\d+ change\(s\) to make\.$", text, re.M) is not None,
          "a token that cannot be checked is a warning, and the run reaches its count line: " + last)
    text, last = dry_run()
    check("opencode-token does not exist" in text and "cannot be checked" not in text,
          "a token file that does not exist is missing, not unchecked: " + last)
    token.mkdir(parents=True)
    text, last = dry_run()
    check("opencode-token does not exist" in text,
          "a directory at the token path is missing: " + last)
    token.rmdir()
    # A HOME before its first install has no ~/.claude/skills/, so the skill links exit 2 in the dry
    # run; the warnings are printed before them.
    (home / ".claude" / "skills").rmdir()
    text, last = dry_run()
    (home / ".claude" / "skills").mkdir()
    check("opencode-token does not exist" in text and "raised HarnessError" in last and ".claude/skills" in last
          and text.index("opencode-token does not exist") < text.index("raised HarnessError"),
          "with no ~/.claude/skills/, the warnings are printed before the skill links exit 2: " + last)
    token.write_text("token\n")
    text, last = dry_run()
    check("opencode-token" not in text and re.search(r"^\d+ change\(s\) to make\.$", text, re.M) is not None,
          "a regular file at the token path is neither missing nor unchecked: " + last)

    scratch = Scratch(check, tmp / "scratch")
    fresh, run, case, tail, mode = scratch.fresh, scratch.run, scratch.case, scratch.tail, scratch.mode

    # The OpenCode agents render from agents/, not from the installed ~/.claude/agents/.
    base, claude, tree = fresh()
    (claude / "agents").mkdir()
    (claude / "agents" / "decoy.md").write_bytes((FIXTURES / "agents" / "bare.md").read_bytes())
    stems = sorted(p.stem for p in (REPO / "agents").glob("*.md"))
    code, text = run(base)
    case(lambda: code == 1 and len(stems) == 20
         and all(re.search(rf"^agents/{re.escape(s)}\.md\s+INSTALL$", text, re.M) for s in stems)
         and not re.search(r"^agents/decoy\.md\s", text, re.M),
         f"the OpenCode agents render from the {len(stems)} agents of agents/, not from ~/.claude/agents/: "
         f"{code}, {tail(text)}")

    # OpenCode's global instruction file is OPENCODE-DELTA.md, installed as AGENTS.md in its
    # configuration directory, where it takes the place of ~/.claude/CLAUDE.md; `instructions`
    # lists RTK.md, the core and the tree instructions, and not the delta.
    delta = (REPO / "adapters" / "opencode" / "OPENCODE-DELTA.md").read_bytes()
    line = re.compile(r"^AGENTS\.md from OPENCODE-DELTA\.md\s+(\S+)", re.M)
    base, claude, tree = fresh()
    code, text = run(base)
    applied, text2 = run(base, "--apply")
    again, text3 = run(base)
    installed = base / "opencode" / "AGENTS.md"

    def instructions():
        jsonc = (base / "opencode" / "opencode.jsonc").read_text()
        return re.findall(r'"([^"]*)"', re.search(r'"instructions":\s*\[(.*?)\]', jsonc, re.S).group(1))

    case(lambda: code == 1 and applied == 0 and again == 0
         and [m.group(1) for m in line.finditer(text)] == ["INSTALL"]
         and [m.group(1) for m in line.finditer(text3)] == ["already"]
         and installed.read_bytes() == delta and mode(installed) == 0o644,
         f"OPENCODE-DELTA.md installs as AGENTS.md in OpenCode's configuration directory: {code}, {applied}, "
         f"{again}, {line.findall(text)}, {tail(text2)}")
    case(lambda: instructions() == ["~/.claude/RTK.md", "~/.claude/instructions/core.md",
                                    "~/.claude/instructions/research-tree.md"],
         f"the rendered opencode.jsonc lists exactly RTK.md, the core and the tree instructions: {instructions()}")
    # A hand-made AGENTS.md that differs from the source is replaced, not merged.
    installed.write_text("mine\n")
    code, text = run(base)
    applied, text2 = run(base, "--apply")
    case(lambda: code == 1 and applied == 0 and [m.group(1) for m in line.finditer(text)] == ["REPLACE"]
         and installed.read_bytes() == delta,
         f"a hand-made AGENTS.md that differs from the source is REPLACE: {code}, {applied}, {line.findall(text)}")
    # The same bytes at mode 0600 are a mode change to 0644, so the install sets the mode itself.
    installed.chmod(0o600)
    code, text = run(base)
    applied, text2 = run(base, "--apply")
    case(lambda: code == 1 and applied == 0 and re.search(r"^AGENTS\.md from OPENCODE-DELTA\.md\s+MODE 0600 -> 0644$",
                                                          text, re.M) is not None
         and mode(installed) == 0o644,
         f"an AGENTS.md with the source's bytes at mode 0600 is MODE 0600 -> 0644: {code}, {applied}, {tail(text)}")


def register(sub):
    p = changing(sub.add_parser("permissions", help="regenerate the OpenCode permission block and guard list"))
    p.set_defaults(run=cmd_permissions)
