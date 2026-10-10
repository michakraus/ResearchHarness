"""The adapter of OpenCode: its part of `harness install`, and the generators of the agents and
the permission block.

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
  the Claude Code layer's rules/, RTK.md, instructions/, hooks/ and skills/
                                   -> the same paths        (OpenCode's own copies; frontends.shared)

After the files, the links that an earlier install wrote to ~/.agents/skills/ are removed
(`skill_links`): OpenCode reads that directory too.

opencode.jsonc and guard-paths.json hold {home} and {opencode_providers}, rendered with the
private profile; each model of the context limits becomes a provider entry before the
profile's own (`context_providers`). The agents are rendered from their neutral source in agents/,
not from the installed copies, with the model tables that OpenCode shares with oh-my-pi and the
keys of [opencode] over them (profile.model_tables). OpenCode reads
AGENTS.md of its configuration directory in place of ~/.claude/CLAUDE.md, and its copies of RTK.md,
the core and the tree instructions through `instructions` in opencode.jsonc. Every text but
AGENTS.md names OpenCode's copies, not Claude Code's (frontends.relocate). An installed agent,
plugin or skill with no copy here is reported, with the command that removes it.

The installed opencode.jsonc can hold a secret that the repository's copy must never contain. If
it holds a literal `Authorization` value, the install refuses to replace it, unless `--force`,
and exits 2: replacing it would remove a working credential.

`harness install` renders the agents on every run; nothing of them is committed. The permission block and `plugins/guard-paths.json` hold no profile value, so they
stay committed, and `harness permissions` regenerates them from the settings template.

THE AGENTS. Each agent of agents/ becomes an OpenCode agent; a rendered
copy has one source, so it cannot drift from it. What changes in the port, and nothing else does:

1. The frontmatter. The `description:` line is copied as raw text. The neutral `tools:` (`shell`
   is `bash`, `agent` is `task`, `mcp/kaimon/<tool>` is `kaimon_<tool>`), `skills:` and
   `permissionMode:` have no OpenCode key, so all three become `permission:`. The tier of `model:`
   maps through `models` of the model tables (`models.toml`), unless `model_overrides`
   names the agent; an agent
   with no `model:` inherits its caller's model in both harnesses. `councils` adds copies of an
   agent on other models; the description of a seat with `verify = true` says that it also judges
   each verify round. `effort:`, `omitClaudeMd:`, `cacheTtl:` and `isolation:` have no
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
"""

import argparse
import contextlib
import difflib
import io
import json
import os
import pathlib
import re
import shutil
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

# The number of critics of a council, its agent and its seats, as the preamble writes it; a
# council has one to eight seats (profile.COUNCIL_SEATS).
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

# The `output` of a model's `limit` that a context limit writes: OpenCode's schema needs
# one, and OpenCode caps a request's output at 32,000 tokens by default.
OUTPUT_LIMIT = 32000


# ---------------------------------------------------------------------------------------------
# The model tables


def load_models(path):
    """OpenCode's model tables at `path`, the shared ones with [opencode]'s over them, every
    sub-table present (profile.model_tables)."""
    return profile_module.model_tables(path, "opencode")


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


def council_rule(seats):
    """The rule of the preamble of an agent with a council of `seats` seats: round 1 has one more
    critic than seats."""
    critics = [f"1{chr(ord('a') + i)}" for i in range(seats + 1)]
    dirs = [f"`round-{c}/`" for c in critics]
    return (f"**Round 1 has {NUMBER_WORDS[len(critics)]} critics here, {sources.code_list(critics)}**, each on a "
            f"different model, and your probe directory is {', '.join(dirs[:-1])} or {dirs[-1]}. Judge "
            "as the text below says; the text names only two because Claude Code runs two.")


def preamble(name, meta, body, models):
    tools = set(meta.get("tools", []))
    rules = [
        "There is no sandbox here. Where the text below gives a rule that exists only because of "
        "the Claude Code sandbox or its permission matcher, the global `AGENTS.md` overrides it.",
    ]
    if name in models["councils"]:
        rules.append(council_rule(len(models["councils"][name])))
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


def port(path, models, root="~/.config/opencode"):
    """The OpenCode agent for one Claude Code agent, then its council copies: [(name, text), …].
    A copy differs from the agent in its name, its model, `hidden: true` and its description. The
    body names the copies below `root`, the configuration directory (frontends.relocate)."""
    path = pathlib.Path(path)
    source = path.name.removesuffix(".md")
    fm = frontmatter.parse_file(path)
    meta = fm.meta
    if "description" not in fm.lines:
        raise HarnessError(f"{path}: no `description:` line")
    model = profile_module.agent_model(source, meta.get("model"), models, path)
    body = fm.body.replace(MCP_PREFIX, "kaimon_")
    rest = frontends.relocate((preamble(source, meta, body, models) + "\n" + body.lstrip("\n")).encode(),
                              root).decode()

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
        agents.append((seat["name"], render(seat["name"], "description: " + json.dumps(
            profile_module.council_description(source, seat, "OpenCode"), ensure_ascii=False), seat["model"], True)))
    return agents


def render_agents(source_dir, models, root="~/.config/opencode"):
    """Every agent of `source_dir` and its council copies, ported with `root` (port): [(name,
    text), …]. A council keyed by a name that no agent of `source_dir` has exits 2."""
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
    return [a for path in paths for a in port(path, models, root)]


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
    """Remove the links of `home`/.agents/skills into `home`/.claude/skills, which an earlier
    install wrote: each frontend holds its own copy of the skills, and OpenCode and oh-my-pi both
    read ~/.agents/skills. [(name, status, changes)]: `changes` is 1 for a link to remove, and 0 for
    anything else there, which is reported as EXTRA with its removal command."""
    source = pathlib.Path(home) / ".claude" / "skills"
    target = pathlib.Path(home) / ".agents" / "skills"
    out = []
    for name in sorted(os.listdir(target)) if target.is_dir() else []:
        link = target / name
        if link.is_symlink() and os.readlink(link).startswith(f"{source}/"):
            if apply:
                link.unlink()
            out.append((name, "removed" if apply else "REMOVE — each frontend holds its own copy", 1))
        else:
            out.append((name, f"EXTRA — OpenCode and oh-my-pi still read it. To remove it:  rm -r '{link}'", 0))
    return out


def context_providers(models):
    """The JSONC lines of a `provider` entry for each context limit of `models`, each model's
    `limit` with `context` and `input` the limit and `output` OUTPUT_LIMIT, every entry ending in a
    comma; "" when `models` holds none. A model with no `<provider>/` exits 2."""
    providers = {}
    for selector, limit in models["context_limits"].items():
        provider, sep, model = selector.partition("/")
        if not (sep and provider and model):
            raise HarnessError(f"{models['path']}: the context limit of {selector!r} names no `<provider>/<model>`")
        providers.setdefault(provider, {})[model] = {"limit": {"context": limit, "input": limit,
                                                               "output": OUTPUT_LIMIT}}
    return "".join(f"    {json.dumps(p)}: {json.dumps({'models': m})},\n" for p, m in providers.items())


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
    root = frontends.home_form(dest)
    models = load_models(ctx.models)
    agents = render_agents(ctx.agents, models, root)
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
        # The context limits are provider entries before the profile's own, which must not name
        # the same provider: JSONC keeps the last of two equal keys.
        limits = context_providers(models)
        own = profile_module.get(ctx.profile, "opencode_providers")
        if clash := [p for p in re.findall(r'^    ("[^"]+"):', limits, re.M) if re.search(rf"^\s*{p}\s*:", own, re.M)]:
            raise HarnessError(f"{models['path']}: a context limit names the provider {', '.join(clash)}, "
                               "which `opencode_providers` of the profile defines too; put the limit there")
        profile = {**ctx.profile, "opencode_providers": limits + own}
        # The rendered file names OpenCode's copies of the instructions, not Claude Code's.
        text = profile_module.render_file(SOURCE / "opencode.jsonc", profile).encode()
        files.append((config, frontends.relocate(text, root), None, "opencode.jsonc", True))
    # OpenCode loads the first that exists of AGENTS.md in its configuration directory and
    # ~/.claude/CLAUDE.md, so this file replaces the Claude Code one and leaves the directory-scoped
    # CLAUDE.md files alone.
    files.append((dest / "AGENTS.md", (SOURCE / "OPENCODE-DELTA.md").read_bytes(), 0o644,
                  "AGENTS.md from OPENCODE-DELTA.md"))
    # OpenCode's own copies of the Claude Code layer's rules, instructions, guard scripts and skills.
    claude = ctx.plans["claude"]
    copies = [(dst, data, None) for dst, _, data in claude.rules] + claude.shared
    files += [(dest / dst, frontends.relocate(data, root) if dst.endswith(".md") else data, mode, dst)
              for dst, data, mode in copies]

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

    # The links that an earlier install wrote to ~/.agents/skills/ go, after every frontend's files.
    def links(apply):
        changes = 0
        for name, status, change in skill_links(pathlib.Path.home(), apply):
            print(f"{'skills/' + name:<34} {status}")
            changes += change
        return changes

    if shutil.which("rtk") is None:
        warnings.append(("rtk is not on the PATH. The rtk plugin then leaves every command unchanged.",
                         "Install RTK, or put its directory on the PATH that OpenCode runs with."))
    warnings += drift_checks()

    # An installed agent, plugin or skill with no copy here is left in place, and OpenCode still
    # loads it.
    ours = {"agents": {f"{name}.md" for name, _ in agents},
            "plugins": {f.name for f in (SOURCE / "plugins").glob("*.ts")}}
    skills = {dst.split("/")[1] for dst, _, _ in copies if dst.startswith("skills/")}
    extra = [f"\nEXTRA: {f} is installed and has no copy here. OpenCode still loads it.\n"
             f"       To remove it:  rm '{f}'"
             for kind, ext in (("agents", "md"), ("plugins", "ts"))
             for f in sorted((dest / kind).glob(f"*.{ext}")) if f.name not in ours[kind]]
    extra += [f"\nEXTRA: {d} is installed and has no copy here. OpenCode still loads it.\n"
              f"       To remove it:  rm -r '{d}'"
              for d in sorted((dest / "skills").glob("*")) if d.is_dir() and d.name not in skills]
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
        for case in [(None, "a missing models.toml"), ("[claude]\n[modles]\n", "an unknown top-level table", "modles"),
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
                            ('[opencode.councils]\ncritic = [{ name = "s", model = "m", verify = true }, '
                             '{ name = "t", model = "n", verify = true }]\n',
                             "two verify seats in one council", "councils.critic", "verify"),
                            ('[opencode.councils]\ncritic = [{ name = "s", model = "m", verify = "yes" }]\n',
                             "a verify that is not true or false", "councils.critic", "verify"),
                            ('[opencode.councils]\ncritic = [{ name = "s", model = "m", weight = 1 }]\n',
                             "a seat with another key", "councils.critic"),
                            ('[opencode.context_limits]\n"p/m" = "100k"\n', "a context limit that is a string",
                             "context_limits"),
                            ('[opencode.context_limits]\n"p/m" = 0\n', "a context limit of zero", "context_limits"),
                            ('[opencode]\nlarge = "p/m"\n', "a tier directly in [opencode]", "[opencode.models]"),
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
        # The shared tables hold for every frontend; a key of [opencode] or [omp] replaces one for
        # that frontend alone.
        path.write_text('[models]\nlarge = "a/l"\nsmall = "a/s"\n[variants]\njudge = "high"\n'
                        '[opencode.models]\nsmall = "b/s"\n[omp.variants]\njudge = "low"\n')
        try:
            oc, omp = load_models(path), profile_module.model_tables(path, "omp")
            check(oc["models"] == {"large": "a/l", "small": "b/s"} and oc["variants"] == {"judge": "high"}
                  and omp["models"] == {"large": "a/l", "small": "a/s"} and omp["variants"] == {"judge": "low"},
                  "the shared tables hold for both frontends, and each frontend's key replaces the shared one for "
                  "it alone")
        except HarnessError as e:
            check(False, f"the shared tables with a frontend's override load: {e}")

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
        skills, target = home / ".claude" / "skills", home / ".agents" / "skills"
        check(skill_links(home, False) == [] and not (home / ".agents").exists(),
              "skill links: nothing to remove with no ~/.agents/skills, and nothing made")
        target.mkdir(parents=True)
        (target / "own").symlink_to(skills / "own")
        (target / "elsewhere").symlink_to(home / "elsewhere")
        (target / "dir").mkdir()
        dry = [(n, s.split(" ")[0], c) for n, s, c in skill_links(home, False)]
        check(dry == [("dir", "EXTRA", 0), ("elsewhere", "EXTRA", 0), ("own", "REMOVE", 1)]
              and (target / "own").is_symlink(),
              f"skill links, dry run: an own link to remove, a foreign link and a directory left: {dry}")
        applied = [(n, s.split(" ")[0], c) for n, s, c in skill_links(home, True)]
        check(applied == [("dir", "EXTRA", 0), ("elsewhere", "EXTRA", 0), ("own", "removed", 1)]
              and sorted(p.name for p in target.iterdir()) == ["dir", "elsewhere"],
              f"skill links, --apply removes the own link only: {applied}")

    # The context limits: one provider entry per provider, each line ending in a comma.
    limits = dict(models, context_limits={"p/a": 100, "p/b": 200, "q/c": 300})
    check(context_providers(limits) == (
        '    "p": {"models": {"a": {"limit": {"context": 100, "input": 100, "output": 32000}}, '
        '"b": {"limit": {"context": 200, "input": 200, "output": 32000}}}},\n'
        '    "q": {"models": {"c": {"limit": {"context": 300, "input": 300, "output": 32000}}}},\n')
          and context_providers(dict(models, context_limits={})) == "",
          "the context limits as provider entries")
    try:
        context_providers(dict(models, context_limits={"bare": 100}))
        check(False, "a context limit of a model with no provider exits 2")
    except HarnessError as e:
        check("'bare'" in str(e), f"a context limit of a model with no provider exits 2: {e}")

    # A verify seat says so in its description; the other seats do not.
    verify = dict(models, councils={"critic": [{"name": "critic-b", "model": "provider-c/other-model", "verify": True},
                                               {"name": "critic-c", "model": "provider-b/medium-model"}]})
    ported = dict(port(FIXTURES / "agents" / "critic.md", verify))
    check("It also judges each verify round, alone." in ported["critic-b"]
          and "verify round, alone" not in ported["critic-c"] and ported["critic-c"] == expected.get("critic-c"),
          "the verify seat's description names the verify round, and only its own")

    # A text names OpenCode's copies, not Claude Code's.
    check(frontends.relocate(b"see ~/.claude/rules/x.md, ~/.claude/skills/s/e.md, ~/.claude/RTK.md and "
                             b"~/.claude/CLAUDE.md", "~/.config/opencode")
          == b"see ~/.config/opencode/rules/x.md, ~/.config/opencode/skills/s/e.md, ~/.config/opencode/RTK.md and "
             b"~/.claude/CLAUDE.md", "relocate rewrites the shared paths and leaves the others")

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
    token.write_text("token\n")
    text, last = dry_run()
    # The diff of the Claude Code settings names the token path in a deny rule, so the warnings are
    # looked for by their own text.
    check("opencode-token does not exist" not in text and f"{token} cannot be checked" not in text
          and re.search(r"^\d+ change\(s\) to make\.$", text, re.M) is not None,
          "a regular file at the token path is neither missing nor unchecked: " + last)

    # The rtk plugin finds `rtk` on the PATH, and so does the install: an `rtk` only in a fixture
    # directory on the PATH is found, and a PATH with none gives the warning. The exit status comes
    # from the count of changes alone, so the same count line in both runs is the same status.
    # The PATH keeps this one's directories, less each one that holds an `rtk`.
    fixture_bin = tmp / "rtk-bin"
    fixture_bin.mkdir()
    (fixture_bin / "rtk").write_text("#!/bin/sh\nexit 1\n")
    (fixture_bin / "rtk").chmod(0o755)
    rest = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not os.access(os.path.join(d, "rtk"), os.X_OK)]
    counts = []
    for label, path, warned in [("an rtk only in a fixture directory on the PATH", [str(fixture_bin)] + rest, False),
                                ("no rtk on the PATH", rest, True)]:
        text, last = dry_run(mock.patch.dict(os.environ, PATH=os.pathsep.join(path)))
        counts.append(re.findall(r"^\d+ change\(s\) to make\.$", text, re.M))
        check(("WARNING: rtk is not on the PATH" in text) == warned and len(counts[-1]) == 1,
              f"{label}: the warning {'is' if warned else 'is not'} given, and the run reaches its count line: "
              + last)
    check(counts[0] == counts[1], f"the rtk warning leaves the count line, and so the exit status, as it is: {counts}")

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
    shared = ("RTK.md", "instructions/core.md", "instructions/research-tree.md")
    own = [f"{base}/opencode/{p}" for p in shared]
    # A copy exists where the Claude Code layer installed the file; a scratch tree has no tree
    # instructions.
    copied = [(base / "opencode" / p).is_file() == (claude / p).is_file() for p in shared]
    case(lambda: instructions() == own and all(copied) and (claude / "RTK.md").is_file(),
         f"the rendered opencode.jsonc lists exactly OpenCode's own copies of RTK.md, the core and the tree "
         f"instructions, each installed where Claude Code's is: {instructions()}, {copied}")
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
