"""The adapter of oh-my-pi: its config.yml, its guard extension, its AGENTS.md, its rules, its
agents and its mcp.json. oh-my-pi has no verb of its own.

`harness install` writes these files into oh-my-pi's agent directory, $PI_CODING_AGENT_DIR, else
~/.omp/agent, after the Claude Code layer is planned, whose rules it renders. An installed rule or
agent with no source is EXTRA, with its removal command; the install leaves it:

  config.yml                  the approval mode and `bash.patterns`, from the settings template,
                              and `modelRoles` from the [omp] table of models.toml (load_models)
  extensions/guards.ts        adapters/omp/guards.ts: the shared guard scripts on every `bash` call,
                              and the path list on the paths of `read`, `grep`, `bash`, `edit` and
                              `write`
  extensions/guard-paths.json the path list (`guard_paths`): the `deny` of
                              adapters/opencode/plugins/guard-paths.json, the template's Edit
                              denies, and its Edit asks
  AGENTS.md                   adapters/omp/OMP-DELTA.md, byte for byte; its first lines import
                              RTK.md, the core and the tree instructions from ~/.claude
  rules/<name>.md             each rule that the Claude Code layer installs, as it renders it, with
                              its `paths` and `description` written as the JSON values `globs` and
                              `description` (`render_rule`); a rule source outside that grammar
                              exits 2, and so does one in a subdirectory of rules/
  mcp.json                    the Kaimon server alone, over HTTP (`render_mcp`)
  agents/<name>.md            each agent of agents/, its tools mapped by TOOLS, its tier as
                              the role `@<role>` that ROLES names, and an "Under oh-my-pi"
                              section from adapters/omp/UNDER-OMP.md (`render_agent`); no
                              council copy

oh-my-pi auto-discovers only `.ts` and `.js` files below extensions/, so the path list there is
data for guards.ts and no extension of its own. It lists a rule by its name, `globs` and
`description`, and the model reads the body through `rule://<name>`; a rule with no `description`
that YAML reads as a non-blank string, and no `alwaysApply`, is never used, so a rule source
outside the grammar of `render_rule` exits 2. Nothing is written below skills/:
oh-my-pi reads the links of ~/.agents/skills/ by default.

THE MODES. `tools.approvalMode: write` runs a read and an edit, and prompts for an `exec` call,
such as `bash`, that no rule allows. `tools.approval.edit` and `write` are `allow`, as Claude Code
edits inside its working directories without a prompt; the guard extension refuses the paths of
the template's Edit denies, and those of its Edit asks, which it cannot ask for: it tells the model
to ask the user in chat. `tools.approval.eval` is `deny`:
`bash.patterns` does not reach the `eval` tool, which can spawn a shell.

THE PATTERNS are the template's Bash entries, rendered with the profile: every `deny` as `deny`,
then every `ask` as `prompt`, then every `allow` as `allow`, each list in the template's order. Claude
Code resolves by category, deny before ask before allow; oh-my-pi takes the first rule that
matches, so this order keeps Claude Code's precedence. oh-my-pi's glob has one wildcard, `*`, which
matches any text, as Claude Code's does. Two forms of Claude Code's have no direct glob: the prefix
suffix `:*` renders to `*` after the same prefix, and a bare `Bash` to `*`; `bash_patterns` lists
each such entry.
`deny` and `prompt` also match each segment of a compound command, and `allow` only a whole
command, so no rule is split, and `bash.allowCompoundCommands` stays off.

THE MODELS. Each tier of TIERS is the role of `modelRoles` that ROLES names, on the model of the
tier in [omp], and `default` is the model of DEFAULT_TIER, so that oh-my-pi picks no model by
itself. config.yml opts no foreign configuration source in (`enabledProviders`), so oh-my-pi
imports neither ~/.claude.json nor OpenCode's MCP servers.

config.yml is JSON below a comment header: JSON is YAML, and the cases read it back with the
standard library.
"""

import json
import os
import pathlib
import re
import tempfile

from harness import REPO, HarnessError, frontends, frontmatter, install, sources
from harness import profile as profile_module

NAME = "omp"
TEMPLATES = []
RESTART = "Restart oh-my-pi: its installed files changed, and a running session keeps the files it has read."

SOURCE = REPO / "adapters" / "omp"
SETTINGS = REPO / "settings" / "settings.proposal.json"
GUARD_PATHS = REPO / "adapters" / "opencode" / "plugins" / "guard-paths.json"
# The template's lists, in the order oh-my-pi must see them, with oh-my-pi's approval for each.
APPROVAL = [("deny", "deny"), ("ask", "prompt"), ("allow", "allow")]

HEADER = """\
# Generated by `harness install` from settings/settings.proposal.json of the harness
# repository and the [omp] table of models.toml; an edit here is replaced by the next install.
# JSON is YAML.
"""

# The neutral tool name of frontmatter.TOOLS -> oh-my-pi's, from
# packages/coding-agent/src/tools/builtin-names.ts of oh-my-pi at d9ee5e6. oh-my-pi's `read` also
# reads a URL, so web_fetch is `read`.
TOOLS = {"read": "read", "edit": "edit", "write": "write", "grep": "grep", "glob": "glob", "shell": "bash",
         "agent": "task", "web_search": "web_search", "web_fetch": "read"}
# Kaimon is the one server of mcp.json, and oh-my-pi names its tool `mcp__<server>_<tool>`.
MCP_PREFIX, OMP_MCP_PREFIX = frontmatter.MCP, "mcp__kaimon_"
KAIMON_URL = "http://127.0.0.1:2828/"
KAIMON_TOKEN = "~/.config/kaimon/opencode-token"
# The tiers, the keys of [omp] in models.toml; DEFAULT_TIER is also the default model. ROLES names
# the role of `modelRoles` of each tier, the name that an agent's `model: @<role>` reads.
TIERS = frontmatter.TIERS
DEFAULT_TIER = "medium"
ROLES = {"large": "opus", "medium": "sonnet", "small": "haiku"}
# oh-my-pi's thinking levels that an agent's `effort` can name; any other effort is dropped.
THINKING_LEVELS = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
# The names oh-my-pi reserves for the top-level session and an unnamed subagent.
RESERVED = {"main", "sub"}


def agent_dir():
    """oh-my-pi's agent directory: $PI_CODING_AGENT_DIR, else ~/.omp/agent."""
    return pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR") or pathlib.Path.home() / ".omp" / "agent")


def bash_patterns(permissions):
    """([(match, approval)], [(rule, match)]) of the Bash entries of `permissions`: the patterns
    in oh-my-pi's order, and each entry whose `:*` suffix was rendered as `*`."""
    patterns, rewritten = [], []
    for action, approval in APPROVAL:
        for rule in permissions.get(action, []):
            m = re.fullmatch(r"Bash(?:\((.*)\))?", rule, re.S)
            if m is None:
                continue
            match = m.group(1)
            if match is None:  # a bare `Bash` is every command
                match = "*"
                rewritten.append((rule, match))
            elif match.endswith(":*"):
                match = match[:-2] + "*"
                rewritten.append((rule, match))
            patterns.append((match, approval))
    return patterns, rewritten


def render_config(profile, tiers):
    """The text of config.yml, with the settings template rendered with `profile`, and
    `modelRoles` from `tiers`, load_models' table: the role that ROLES names for each tier, and
    `default`, on the selector of DEFAULT_TIER."""
    permissions = json.loads(profile_module.render_file(SETTINGS, profile))["permissions"]
    patterns, _ = bash_patterns(permissions)
    config = {
        "tools": {"approvalMode": "write", "approval": {"eval": "deny", "edit": "allow", "write": "allow"}},
        "bash": {"allowCompoundCommands": False,
                 "patterns": [{"match": match, "approval": approval} for match, approval in patterns]},
        "modelRoles": {"default": tiers[DEFAULT_TIER], **{ROLES[t]: tiers[t] for t in TIERS}},
    }
    return HEADER + json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def guard_paths(profile):
    """The text of extensions/guard-paths.json, rendered with `profile`: under `deny` the `read`
    denies of OpenCode's path list, for `read`, `grep` and `bash`; under `edit` the template's
    `Edit` and `Write` denies, and under `ask` its `Edit` and `Write` asks, for `edit` and `write`,
    each `//` prefix of Claude Code's as `/`."""
    deny = json.loads(profile_module.render_file(GUARD_PATHS, profile))["deny"]
    permissions = json.loads(profile_module.render_file(SETTINGS, profile))["permissions"]
    lists = {"deny": [], "ask": []}
    for action, paths in lists.items():
        for rule in permissions.get(action, []):
            # The template holds no `Write(` rule; one added there would refuse the same tools, so
            # it is read here too.
            m = re.fullmatch(r"(?:Edit|Write)\((.*)\)", rule, re.S)
            if m is not None and (path := re.sub(r"^//+", "/", m.group(1))) not in paths:
                paths.append(path)
    out = {"deny": deny, "edit": lists["deny"], "ask": lists["ask"]}
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def render_rule(path, data=None):
    """The oh-my-pi rule of `data`, the Claude Code rule from the source at `path` (by default the
    bytes of that file): the frontmatter `---`, `globs: <the source's paths as a JSON list>` when
    the source has `paths`, `description: <the source's description as a JSON string>`, then the
    source from its closing `---` line on, byte for byte. oh-my-pi lists a rule only when YAML
    reads its `description` as a non-blank string, and YAML reads a JSON string as that string.
    The source must hold this closed grammar, and any other source exits 2, naming the line and
    the form:

    - the file is UTF-8; line 1 is exactly `---`, and the frontmatter ends at the first later line
      that is exactly `---`; each line may end in `\\r\\n`;
    - every line between is `paths: ["…", "…"]`, double-quoted items with no `"`, `\\` or control
      character, joined by `, `; or `description: <text>`, the text plain or in double quotes as
      `frontmatter.scalar` reads it, and not blank, a U+FEFF counted as blank;
    - `description` occurs once, `paths` at most once;
    - no line between holds a tab, or starts or ends with whitespace: the source's frontmatter is
      linted;
    - the frontmatter holds no `<!--`, which oh-my-pi strips before it reads YAML, and no
      character of `frontmatter.CONTROL` other than the `\\r` of a line end."""
    raw = path.read_bytes() if data is None else data
    suffix = "; a rule's frontmatter is `description: <text>` and at most `paths: [\"…\"]`, as oh-my-pi " \
             "never uses a rule without a description"
    try:
        lines = raw.decode("utf-8").split("\n")
    except UnicodeDecodeError as e:
        line = raw.count(b"\n", 0, e.start) + 1
        raise HarnessError(f"{path}:{line}: byte {e.start} is not UTF-8{suffix}") from None
    # The `\r` of a `\r\n` line end; any other `\r` is a control character.
    lines = [l[:-1] if l.endswith("\r") and i < len(lines) - 1 else l for i, l in enumerate(lines)]
    if lines[0] != "---":
        raise HarnessError(f"{path}:1: the frontmatter does not open with a line `---`{suffix}")
    end = next((i for i, l in enumerate(lines[1:], 1) if l == "---"), None)
    if end is None:
        raise HarnessError(f"{path}:1: the frontmatter does not close with a line `---`{suffix}")
    seen, values = {}, {}
    for n, line in enumerate(lines[1:end], 2):
        where = f"{path}:{n}"
        control = frontmatter.CONTROL.search(line)
        if control:
            raise HarnessError(f"{where}: a control character U+{ord(control.group()):04X}{suffix}")
        if "\t" in line:
            raise HarnessError(f"{where}: a tab; the source's frontmatter is linted{suffix}")
        if line[:1].isspace() or line[-1:].isspace():
            raise HarnessError(f"{where}: whitespace at the start or the end of the line{suffix}")
        if "<!--" in line:
            raise HarnessError(f"{where}: an HTML comment, which oh-my-pi removes before it reads the frontmatter"
                               f"{suffix}")
        if re.fullmatch(r'paths: \["[^"\\\x00-\x1f]*"(?:, "[^"\\\x00-\x1f]*")*\]', line):
            key, value = "paths", json.loads(line[len("paths: "):])
        elif line.startswith("description: "):
            key, value = "description", frontmatter.scalar(line[len("description: "):].strip(" "),
                                                           f"{where}: `description`")
            # JavaScript's trim(), which oh-my-pi applies, removes a U+FEFF too.
            if not value.replace("\N{ZERO WIDTH NO-BREAK SPACE}", "").strip():
                raise HarnessError(f"{where}: a blank `description`{suffix}")
        else:
            raise HarnessError(f"{where}: {line!r} is no line `paths: [\"…\"]` or `description: <text>`{suffix}")
        if key in seen:
            raise HarnessError(f"{where}: a second `{key}`, after line {seen[key]}{suffix}")
        seen[key], values[key] = n, value
    if "description" not in seen:
        raise HarnessError(f"{path}:{end + 1}: no `description` in the frontmatter, which closes here{suffix}")
    # oh-my-pi reads YAML, and a JSON list or string is YAML that reads as the same value.
    head = ["---"] + [f"{name}: {json.dumps(values[key], ensure_ascii=False)}"
                      for key, name in (("paths", "globs"), ("description", "description")) if key in values]
    return "\n".join(head).encode() + b"\n" + b"\n".join(raw.split(b"\n")[end:])


def load_models(path):
    """{tier: selector} of the [omp] table of the models.toml at `path`: exactly the keys of TIERS,
    each a string that is not blank, as a blank one leaves oh-my-pi to pick the model; any other
    table exits 2 (profile.tier_table)."""
    return profile_module.tier_table(path, "omp", "oh-my-pi")


def under_omp(meta, body):
    """The "Under oh-my-pi" section of an agent with frontmatter `meta` and `body`: the rules of
    adapters/omp/UNDER-OMP.md for each Claude Code mechanism that it uses; "" when it uses none."""
    text = (SOURCE / "UNDER-OMP.md").read_text()
    rules = {m.group(1): m.group(2).strip() for m in re.finditer(r"(?m)^## (\w+)\n(.*?)(?=^## |\Z)", text, re.S)}
    tools, skills = meta.get("tools", []), meta.get("skills", [])
    used = [key for key, uses in [
        ("skills", bool(skills)),
        ("worktree", meta.get("isolation") == "worktree" or "isolation" in body),
        ("agent", "agent" in tools),
        # oh-my-pi's default bash timeout is 300 s, and julia-test-runner runs suites of 10-30 minutes.
        ("bash", "shell" in tools),
        ("mcp", any(t.startswith(MCP_PREFIX) for t in tools))] if uses]
    if not used:
        return ""
    if missing := [k for k in ["intro", *used] if k not in rules]:
        raise HarnessError(f"{SOURCE / 'UNDER-OMP.md'}: no section `## {missing[0]}`")
    names = list(skills)
    named = sources.code_list(names) if names else ""
    lines = [rules[k].replace("{skills}", f"{named} skill{'s' * (len(names) > 1)}") for k in used]
    return "## Under oh-my-pi\n\n" + rules["intro"] + "\n\n" + "\n".join("- " + l for l in lines) + "\n"


def render_agent(path, tiers):
    """(name, bytes) of the oh-my-pi agent of the agent at `path`, with `tiers` from load_models:
    the frontmatter `name`, `description`, `tools` mapped by TOOLS, `model` the role `@<role>` that
    ROLES names for the tier, `thinking-level` the `effort` where oh-my-pi has that level, and
    `autoloadSkills` the `skills`, each value as JSON, which YAML reads as the same value; then the
    generated-by comment, the "Under oh-my-pi" section and the body. A tool with no oh-my-pi name,
    a wildcard among them, a tier that is not in `tiers`, no description, a `name:` that is not the
    file name, and the reserved names `main` and `sub` exit 2."""
    path = pathlib.Path(path)
    name = path.name.removesuffix(".md")
    if name.strip().lower() in RESERVED:
        raise HarnessError(f"{path}: the agent name {name!r} is reserved by oh-my-pi, which ignores such an agent")
    fm = frontmatter.parse_file(path)
    meta = fm.meta
    # Claude Code names the agent by `name:`, and the installed file by the file name.
    if meta.get("name", name) != name:
        raise HarnessError(f"{path}: the name {meta['name']!r} is not the file name {name!r}")
    if "description" not in meta:
        raise HarnessError(f"{path}: no `description:` line")
    head = {"name": name, "description": meta["description"]}
    if "tools" in meta:
        tools = []
        for tool in meta["tools"]:
            if tool in TOOLS:
                mapped = TOOLS[tool]
            # oh-my-pi reads a tool name literally, so a wildcard has no oh-my-pi name.
            elif tool.startswith(MCP_PREFIX) and tool != MCP_PREFIX and "*" not in tool:
                mapped = OMP_MCP_PREFIX + tool[len(MCP_PREFIX):]
            else:
                raise HarnessError(f"{path}: the tool {tool!r} has no oh-my-pi name; TOOLS of adapters/omp/adapter.py maps "
                                   f"{', '.join(TOOLS)} and the {MCP_PREFIX}<tool> tools")
            if mapped not in tools:
                tools.append(mapped)
        head["tools"] = tools
    if "model" in meta:
        if meta["model"] not in tiers:
            raise HarnessError(f"{path}: the tier {meta['model']!r} is none of the tiers of [omp], "
                               f"{', '.join(tiers)}")
        head["model"] = "@" + ROLES[meta["model"]]
    if meta.get("effort") in THINKING_LEVELS:
        head["thinking-level"] = meta["effort"]
    if "skills" in meta:
        head["autoloadSkills"] = meta["skills"]
    section = under_omp(meta, fm.body)
    text = ("---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in head.items()) + "---\n\n"
            f"<!-- Generated by `harness install` from agents/{name}.md of the harness repository. Do not "
            "edit this file: edit the source and run `harness install --apply`. -->\n\n"
            + (section + "\n" if section else "") + fm.body.lstrip("\n"))
    return name, text.encode()


def render_mcp():
    """The text of mcp.json: the Kaimon server alone, over HTTP, with its token read from
    KAIMON_TOKEN by a shell command when oh-my-pi connects, so that no secret is in the file."""
    kaimon = {"type": "http", "url": KAIMON_URL,
              "headers": {"Authorization": f"!printf 'Bearer %s' \"$(cat {KAIMON_TOKEN})\""}}
    return json.dumps({"mcpServers": {"kaimon": kaimon}}, indent=2) + "\n"


def render_files(profile, rules, tiers, agents):
    """[(path relative to the agent directory, bytes)] of the files: the permission layer with the
    model roles of `tiers`, AGENTS.md, rules/<name>.md for each (source path, rendered bytes) of a
    Claude Code rule in `rules`, mcp.json, and agents/<name>.md for each agent of `agents`."""
    return [("config.yml", render_config(profile, tiers).encode()),
            ("extensions/guards.ts", (SOURCE / "guards.ts").read_bytes()),
            ("extensions/guard-paths.json", guard_paths(profile).encode()),
            ("AGENTS.md", (SOURCE / "OMP-DELTA.md").read_bytes()),
            *((f"rules/{p.name}", render_rule(p, data)) for p, data in rules),
            ("mcp.json", render_mcp().encode()),
            *((f"agents/{n}.md", data) for n, data in (render_agent(p, tiers) for p in sorted(agents.glob("*.md"))))]


def plan(ctx):
    """oh-my-pi's part of `harness install`, as the docstring of this module says; the rules are
    those of the Claude Code layer's plan in `ctx.plans`."""
    tiers = load_models(ctx.models)
    layer = ctx.plans["claude"].rules
    # oh-my-pi reads the files of its rules/ and no subdirectory, so a rule source in one is
    # refused before anything is written.
    for dst, src, _ in layer:
        if re.fullmatch(r"rules/.+/[^/]+\.md", dst):
            raise HarnessError(f"{src}: a rule in a subdirectory of rules/, which oh-my-pi "
                               "does not read; move it to rules/ itself")
    # oh-my-pi's rules are the rules that the Claude Code layer installs, as it renders them, each
    # with its source: the plan has checked the sources, and a source of rules/<name>.md exists in
    # one only.
    rules = [(src, data) for dst, src, data in layer if re.fullmatch(r"rules/[^/]+\.md", dst)]
    agent, files = agent_dir(), render_files(ctx.profile, rules, tiers, ctx.agents)
    # An installed oh-my-pi rule or agent with no source is left in place, and oh-my-pi still lists
    # it: a file of rules/ whose name ends in `.md` or `.mdc`, and a file of agents/ that ends in `.md`.
    ours = {install.fold(rel) for rel, _ in files}
    extra = [f"\nEXTRA: {f} is installed and has no source here. oh-my-pi still lists it.\n"
             f"       To remove it:  rm '{f}'"
             for kind, suffixes in (("rules", (".md", ".mdc")), ("agents", (".md",)))
             for f in sorted(f for f in (agent / kind).glob("*") if f.is_file() and f.suffix in suffixes
                             and install.fold(f"{kind}/{f.name}") not in ours)]
    return frontends.Plan(files=[(agent / rel, data, None, f"omp/{rel}") for rel, data in files], extra=extra)


def register(sub):
    """oh-my-pi has no verb of its own."""


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`


def selftest():
    """The oh-my-pi layer of `harness install`, end to end on scratch HOMEs."""
    from harness.install_cases import Scratch

    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  omp: {label}")

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Scratch(check, tmp)
        omp_cases(scratch.case, scratch.fresh, scratch.run)
    return total, wrong


def omp_config(path):
    """The config.yml of oh-my-pi at `path`, parsed: its `#` lines are comments, the rest JSON."""
    return json.loads("".join(l for l in path.read_text().splitlines(keepends=True) if not l.startswith("#")))


def omp_cases(case, fresh, run):
    """The oh-my-pi layer: config.yml, the guard extension, AGENTS.md and the rules, with the
    grammar of render_rule, under a scratch PI_CODING_AGENT_DIR; `case`, `fresh` and `run` are
    those of `install_cases.Scratch`."""
    from harness.install_cases import RULE_HEAD, Scratch

    opencode = frontends.adapter("opencode")
    tail = Scratch.tail

    line = re.compile(r"^omp/(\S+)\s+(\S+)", re.M)
    base, _, tree = fresh(["rules/meta-repository.md"])
    code, dry = run(base)
    listed = dict(line.findall(dry))
    case(lambda: listed.get("config.yml") == "INSTALL" and listed.get("extensions/guards.ts") == "INSTALL"
         and not (base / "omp").exists(),
         f"the dry run lists config.yml and extensions/guards.ts, and writes nothing: {code}, {listed}")
    delta = REPO / "adapters" / "omp" / "OMP-DELTA.md"
    imports = ["@~/.claude/RTK.md", "@~/.claude/instructions/core.md", "@~/.claude/instructions/research-tree.md"]
    case(lambda: listed.get("AGENTS.md") == "INSTALL" and delta.read_text().split("\n")[:3] == imports,
         f"the dry run lists AGENTS.md, from adapters/omp/OMP-DELTA.md, whose first lines import RTK.md, the core and the "
         f"tree instructions: {listed.get('AGENTS.md')}")
    case(lambda: len(delta.read_bytes()) <= 5114,
         "adapters/omp/OMP-DELTA.md is no larger than OPENCODE-DELTA.md at dbc4897, 5,114 bytes")
    # The rule sources: rules/ and the tree instructions' rules/, one rendered rule each.
    sources = sorted([*(REPO / "rules").glob("*.md"), tree / "rules" / "meta-repository.md"],
                     key=lambda p: p.name)
    case(lambda: all(listed.get(f"rules/{s.name}") == "INSTALL" for s in sources) and len(sources) == 8,
         f"the dry run lists one rules/<name>.md per rule source, 8: {sorted(k for k in listed if k.startswith('rules/'))}")
    code, text = run(base, "--apply")
    agent = base / "omp"
    profile = profile_module.load(base / "profile.toml")
    case(lambda: code == 0 and omp_config(agent / "config.yml")["tools"]
         == {"approvalMode": "write", "approval": {"eval": "deny", "edit": "allow", "write": "allow"}},
         f"config.yml sets approvalMode write, eval deny, edit and write allow: {code}, {tail(text)}")
    case(lambda: omp_config(agent / "config.yml")["bash"]["allowCompoundCommands"] is False,
         "config.yml keeps bash.allowCompoundCommands off")
    permissions = json.loads(profile_module.render_file(REPO / "settings" / "settings.proposal.json",
                                                        profile))["permissions"]
    # The path list: OpenCode's `read` denies under `deny`, the template's Edit and Write denies
    # under `edit` and its Edit and Write asks under `ask`, each `//` prefix as `/`, in the
    # template's order.
    guard_list = json.loads(profile_module.render_file(REPO / "adapters" / "opencode" / "plugins" / "guard-paths.json",
                                                       profile))["deny"]
    edit_list, ask_list = (list(dict.fromkeys(re.sub(r"^//+", "/", r[r.index("(") + 1:-1])
                                              for r in permissions[key] if r.startswith(("Edit(", "Write("))))
                           for key in ("deny", "ask"))
    case(lambda: (agent / "extensions" / "guards.ts").read_bytes() == (REPO / "adapters" / "omp" / "guards.ts").read_bytes()
         and ask_list
         and json.loads((agent / "extensions" / "guard-paths.json").read_text())
         == {"deny": guard_list, "edit": edit_list, "ask": ask_list}
         and sorted(p.relative_to(agent).as_posix() for p in agent.rglob("*") if p.is_file())
         == sorted(["AGENTS.md", "config.yml", "extensions/guard-paths.json", "extensions/guards.ts", "mcp.json",
                    *(f"rules/{s.name}" for s in sources),
                    *(f"agents/{a.name}" for a in (REPO / "agents").glob("*.md"))])
         and not (agent / "skills").exists(),
         "--apply installs AGENTS.md, config.yml, guards.ts, guard-paths.json, whose `deny` is OpenCode's list, "
         "whose `edit` is the template's Edit and Write denies and whose `ask` is its Edit and Write asks, "
         "mcp.json, the rules and the agents, and nothing else: nothing below skills/")
    case(lambda: (agent / "AGENTS.md").read_bytes() == delta.read_bytes(),
         "--apply installs AGENTS.md as adapters/omp/OMP-DELTA.md, byte for byte")

    def front(text):
        """({key: raw value} of the frontmatter, the text from the closing `---` on) of a rule."""
        lines = text.split("\n")
        end = lines.index("---", 1)
        return {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in lines[1:end])}, "\n".join(lines[end:])

    def rendered_rule(src):
        """Each difference of the rendered rule of `src` from its contract; none when it holds."""
        # The renderer writes each value as JSON; the sources hold a JSON list and a plain text.
        try:
            (meta, body), (got, got_body) = front(src.read_text()), front((agent / "rules" / src.name).read_text())
            globs, paths = json.loads(got.get("globs", "null")), json.loads(meta.get("paths", "null"))
            description = json.loads(got.get("description", "null"))
        except (OSError, ValueError) as e:
            return [f"{type(e).__name__}: {e}"]
        return [d for d, bad in [
            ("globs is not the source's paths", globs != paths or not globs),
            ("a paths key", "paths" in got),
            ("not the source's description", description != meta.get("description") or not description),
            ("the body differs", got_body != body)] if bad]

    case(lambda: {s.name: rendered_rule(s) for s in sources} == {s.name: [] for s in sources},
         "each of the 8 rules is rendered with globs equal to its paths, its description, no paths key, and the "
         "body byte for byte: " + ", ".join(f"{s.name} {rendered_rule(s)}" for s in sources if rendered_rule(s)))

    # An installed rule with no source is EXTRA, with its removal, and stays: oh-my-pi still lists it.
    # oh-my-pi names a rule by its `.md` or `.mdc` suffix, so another file there is no rule.
    stale, stale_mdc = agent / "rules" / "old.md", agent / "rules" / "old.mdc"
    others = [agent / "rules" / ".DS_Store", agent / "rules" / "notes.txt"]
    for f in (stale, stale_mdc, *others):
        f.write_text(RULE_HEAD)
    code, text = run(base)
    case(lambda: code == 0 and all(f"EXTRA: {f} " in text and f"rm '{f}'" in text and f.is_file()
                                   for f in (stale, stale_mdc))
         and not any(f"EXTRA: {agent / 'rules' / s.name} " in text for s in sources)
         and not any(f"EXTRA: {f} " in text for f in others),
         f"an installed oh-my-pi rule (.md or .mdc) with no source is EXTRA, with its removal, and the rendered "
         f"rules and a file of another suffix are not: {code}, {[l for l in text.splitlines() if 'EXTRA' in l]}")
    for f in (stale, stale_mdc, *others):
        f.unlink()

    # oh-my-pi uses a rule whose `description` YAML reads as a non-blank string. The renderer reads
    # a closed grammar: line 1 `---`, then only `paths: ["…", …]` and `description: <text>` lines,
    # up to the first `---` line, with no `<!--`, no tab, no control character and no whitespace at
    # the start or end of a line; it refuses the rest. It writes `globs` and `description` itself,
    # as JSON values, which YAML reads as the list and the string whatever the source's text.
    head = '---\npaths: ["**/*.x"]\n'
    # (label, source, the description that the rendered rule holds, or False for a refusal)
    forms = [
        ("a plain text", head + "description: A rule.\n---\nbody\n", "A rule."),
        ("a quoted text", head + 'description: "A rule: quoted."\n---\nbody\n', "A rule: quoted."),
        ("a quoted text with escapes", head + 'description: "say \\"hi\\" \\\\ ok"\n---\nbody\n',
         'say "hi" \\ ok'),
        ("CRLF line ends", head.replace("\n", "\r\n") + "description: A rule.\r\n---\r\nbody\r\n", "A rule."),
        ("a quoted text that starts with digits", head + 'description: "42 rules"\n---\nbody\n', "42 rules"),
        ("a quoted number", head + 'description: "42"\n---\nbody\n', "42"),
        ("no paths", "---\ndescription: A rule.\n---\nbody\n", "A rule."),
        ("two spaces after the colon", head + "description:  A rule.\n---\nbody\n", "A rule."),
        ("two globs", '---\npaths: ["**/*.x", "a b/*.y"]\ndescription: A rule.\n---\nbody\n', "A rule."),
        # A plain text that YAML would read as null, a boolean, a number or a list is written as a
        # JSON string, which YAML reads as that text.
        *((f"YAML's {v} as plain text", head + f"description: {v}\n---\nbody\n", v)
          for v in ["~", "null", "Null", "NULL", "true", "False", "yes", "42", "-1.5e3", "0x1F", ".inf", ".NaN",
                    "-", "- A rule.", "42 rules", "? x", "1:30"]),
        ("a non-ASCII text", head + "description: Ä rule — ☃ \N{GRINNING FACE}\n---\nbody\n",
         "Ä rule — ☃ \N{GRINNING FACE}"),
        # The source's frontmatter is linted: no tab, and no whitespace at the edge of a line.
        ("a plain text with a trailing space", head + "description: A rule. \n---\nbody\n", False),
        ("YAML's null with a trailing space", head + "description: null \n---\nbody\n", False),
        ("YAML's null with a tab and a space", head + "description: null\t \n---\nbody\n", False),
        ("YAML's true with a tab and a comment", head + "description: true\t# x\n---\nbody\n", False),
        ("YAML's false with a tab and an empty comment", head + "description: false\t#\n---\nbody\n", False),
        ("a tab inside a plain text", head + "description: A\trule.\n---\nbody\n", False),
        ("a tab inside quotes", head + 'description: "A\trule."\n---\nbody\n', False),
        ("a tab after the paths", '---\npaths: ["**/*.x"]\t\ndescription: A rule.\n---\nbody\n', False),
        ("a space after the paths", '---\npaths: ["**/*.x"] \ndescription: A rule.\n---\nbody\n', False),
        ("a space before the description", head + " description: A rule.\n---\nbody\n", False),
        ("a no-break space after the description", head + "description: A rule.\N{NO-BREAK SPACE}\n---\nbody\n",
         False),
        ("YAML's false with a trailing space and CRLF line ends",
         head.replace("\n", "\r\n") + "description: false \r\n---\r\nbody\r\n", False),
        # oh-my-pi's trim() removes a U+FEFF, which Python's strip() keeps.
        ("a U+FEFF in quotes", head + 'description: "\N{ZERO WIDTH NO-BREAK SPACE}"\n---\nbody\n', False),
        ("a plain U+FEFF", head + "description: \N{ZERO WIDTH NO-BREAK SPACE}\n---\nbody\n", False),
        ("two CRs before a LF", head + "description: A rule.\r\r\n---\nbody\n", False),
        ("an HTML comment as the value", head + "description: <!-- none -->\n---\nbody\n", False),
        ("an HTML comment around the description", head + "<!--\ndescription: A rule.\n-->\n---\nbody\n", False),
        # oh-my-pi strips the comment and reads `description: ""`.
        ("an HTML comment in quotes", head + 'description: "<!-- none -->"\n---\nbody\n', False),
        ("a ---- line above the description", head + "----\ndescription: A rule.\n---\nbody\n", False),
        ("a ---- line below the description", head + "description: A rule.\n----\n---\nbody\n", False),
        ("a second, empty description", head + "description: A rule.\ndescription:\n---\nbody\n", False),
        ("a second paths line", head + head[4:] + "description: A rule.\n---\nbody\n", False),
        ("an unknown key", head + "name: x\ndescription: A rule.\n---\nbody\n", False),
        ("a blank line", head + "\ndescription: A rule.\n---\nbody\n", False),
        ("a comment line", head + "# note\ndescription: A rule.\n---\nbody\n", False),
        ("a paths list continued on the next line", '---\npaths: ["**/*.x",\ndescription: x]\n---\nbody\n', False),
        ("a paths item in single quotes", "---\npaths: ['**/*.x']\ndescription: A rule.\n---\nbody\n", False),
        ("a lone CR", head + "description: A\rrule.\n---\nbody\n", False),
        ("a U+2028", head + "description: A\N{LINE SEPARATOR}rule.\n---\nbody\n", False),
        ("a BOM", "﻿" + head + "description: A rule.\n---\nbody\n", False),
        ("a ---- first line", "----\n" + head[4:] + "description: A rule.\n---\nbody\n", False),
        ("no valid UTF-8", (head + "description: A rule.\n---\n").encode() + b"\xff\n", False),
        ("no description", head + "---\nbody\n", False),
        ("no frontmatter", "description: A rule.\n", False),
        ("no closing ---", head + "description: A rule.\nbody\n", False),
        ("a description below the frontmatter", head + "---\ndescription: A rule.\n", False),
        ("an empty value", head + "description:\n---\nbody\n", False),
        ("an empty quoted value", head + 'description: ""\n---\nbody\n', False),
        ("a blank quoted value", head + 'description: "  "\n---\nbody\n', False),
        ("an empty single-quoted value", head + "description: ''\n---\nbody\n", False),
        ("a comment only", head + "description: # none\n---\nbody\n", False),
        ("a text with a comment", head + "description: A rule. # note\n---\nbody\n", False),
        ("an empty folded block", head + "description: >\n---\nbody\n", False),
        ("a folded block", head + "description: >-\n  A rule.\n---\nbody\n", False),
        ("a text on the next line", head + "description:\n  A rule.\n---\nbody\n", False),
        ("a flow list", head + "description: [a, b]\n---\nbody\n", False),
        ("a mapping", head + "description: a: b\n---\nbody\n", False),
        ("no space after the colon", head + "description:A rule.\n---\nbody\n", False),
        ("an unterminated quote", head + 'description: "A rule.\n---\nbody\n', False),
    ]

    p = base / "form.md"
    refusals = {}

    def renders(text):
        """The description of the rule that render_rule renders from `text`, read back from its
        frontmatter, which must be `---`, then `globs: <JSON list>` equal to the source's `paths`
        when it has one, then `description: <JSON string>`, then the source from its closing `---`
        line on, byte for byte; False when it refuses `text` with exit 2, its message then in
        `refusals`; else a description of what is wrong."""
        data = text if isinstance(text, bytes) else text.encode()
        p.write_bytes(data)
        try:
            out = render_rule(p, p.read_bytes())
        except HarnessError as e:
            refusals[text] = str(e)
            return False
        except Exception as e:  # noqa: BLE001 — a crash is a wrong form, and the next case still runs
            return type(e).__name__
        source, lines = data.split(b"\n"), out.split(b"\n")
        close = next(i for i, l in enumerate(source[1:], 1) if l in (b"---", b"---\r"))
        paths = [json.loads(l[len(b"paths: "):].rstrip(b"\r")) for l in source[1:close] if l.startswith(b"paths: ")]
        n = len(paths)  # the rendered rule: `---`, n globs lines, the description, the source's close on
        try:
            if lines[0] == b"---" and lines[n + 2:] == source[close:] \
                    and all(l.startswith(b"globs: ") for l in lines[1:n + 1]) \
                    and [json.loads(l[len(b"globs: "):]) for l in lines[1:n + 1]] == paths \
                    and lines[n + 1].startswith(b"description: "):
                return json.loads(lines[n + 1][len(b"description: "):])
        except ValueError:
            pass
        return f"not the rendered form: {out!r}"

    wrong = [label for label, text, want in forms if renders(text) != want]
    case(lambda: not wrong,
         f"the renderer takes the rule grammar, {sum(bool(w) for _, _, w in forms)} forms, each written with its "
         f"globs and its description as JSON, and refuses each of the {sum(not w for _, _, w in forms)} other "
         f"forms: wrong {wrong}")
    # Each refusal names the file and the line: the line of the byte that is not UTF-8, and the
    # closing `---` of a frontmatter with no description.
    unnamed = [label for label, text, ok in forms
               if not ok and not re.match(re.escape(str(p)) + r":\d+: ", refusals.get(text, ""))]
    lines = {label: refusals.get(text, "").removeprefix(f"{p}:").split(":")[0] for label, text, _ in forms
             if label in ("no valid UTF-8", "no description")}
    case(lambda: not unnamed and lines == {"no valid UTF-8": "5", "no description": "3"},
         f"each refusal of a form names the file and the line: unnamed {unnamed}, lines {lines}")

    # A rule source with no description is refused, before anything is written: oh-my-pi never
    # uses such a rule.
    for label, text in [("no description", '---\npaths: ["**/*.x"]\n---\nbody\n'), ("no frontmatter", "body\n"),
                        ("an empty description", '---\npaths: ["**/*.x"]\ndescription: ""\n---\nbody\n'),
                        ("a description below its frontmatter", '---\npaths: ["**/*.x"]\n---\ndescription: x\n')]:
        base2, _, tree2 = fresh(["rules/x.md"])
        (tree2 / "rules" / "x.md").write_text(text)
        code2, out = run(base2, "--apply")
        case(lambda: code2 == 2 and "Traceback" not in out and str(tree2 / "rules" / "x.md") in out
             and "description" in out and not (base2 / "omp").exists()
             and not (base2 / "opencode" / "opencode.jsonc").exists(),
             f"a rule source with {label} exits 2, names it, and writes nothing: {code2}, {tail(out)}")
    # oh-my-pi reads the `.md` and `.mdc` files of rules/ itself, and no subdirectory of it, so a
    # rule source in a subdirectory is refused, before anything is written.
    for rel in ["rules/sub/x.md", "rules/a/b/x.md"]:
        base2, _, tree2 = fresh([rel])
        (tree2 / rel).write_text(RULE_HEAD + "body\n")
        code2, out = run(base2, "--apply")
        case(lambda: code2 == 2 and "Traceback" not in out and str(tree2 / rel) in out
             and "subdirectory" in out and not (base2 / "omp").exists()
             and not (base2 / "opencode" / "opencode.jsonc").exists()
             and not (base2 / "home" / ".claude" / "rules").exists(),
             f"a rule source in a subdirectory of rules/, {rel}, exits 2, names it, and writes nothing: {code2}, "
             f"{tail(out)}")
    case(lambda: profile["home"] + "/.claude/hooks/**" in edit_list and profile["home"] + "/.config/**" in edit_list,
         f"the edit list holds ~/.claude/hooks/** and ~/.config/**: {edit_list[:3]}")
    case(lambda: not (base / ".omp").exists() and not (base / "home" / ".omp").exists(),
         "with PI_CODING_AGENT_DIR set, nothing is written to ~/.omp or to a project .omp/")

    # The patterns are the template's Bash entries, rendered with the profile: deny, then ask as
    # prompt, then allow, each in the template's order. oh-my-pi takes the first rule that
    # matches, so this order is Claude Code's precedence.
    expected = [{"match": r[len("Bash("):-1], "approval": approval}
                for action, approval in (("deny", "deny"), ("ask", "prompt"), ("allow", "allow"))
                for r in permissions[action] if r.startswith("Bash(")]

    def rendered():
        try:
            return omp_config(agent / "config.yml")["bash"]["patterns"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            return f"no patterns: {type(e).__name__}: {e}"

    got = rendered()
    first = next((i for i, (g, e) in enumerate(zip(got, expected)) if g != e), None)
    case(lambda: got == expected and len(expected) > 300,
         f"bash.patterns is the template's Bash entries, entry by entry: {len(got)} rendered, {len(expected)} in the "
         f"template, first difference at {first}")

    emitted, _, _ = opencode.collect_rules()
    own = [a for key, rules in opencode.OPENCODE_ONLY_RULES if key == "bash" for _, a in rules]
    oc = {a: sum(1 for _, x in emitted["bash"] if x == a) - own.count(a) for a in ("deny", "ask")}
    counted = {a: sum(1 for p in got if isinstance(p, dict) and p.get("approval") == b)
               for a, b in (("deny", "deny"), ("ask", "prompt"))}
    case(lambda: counted == oc,
         f"the deny and prompt counts equal the OpenCode block's bash deny and ask counts: oh-my-pi {counted}, "
         f"OpenCode {oc}")

    def suffix():
        return bash_patterns({"deny": ["Bash(npm run:*)", "Bash(ls *)", "Read(//x)"], "ask": ["Bash(git:*)"],
                              "allow": ["Bash(git status)", "Bash", "Bashful"]})

    case(lambda: suffix() == ([("npm run*", "deny"), ("ls *", "deny"), ("git*", "prompt"), ("git status", "allow"),
                               ("*", "allow")],
                              [("Bash(npm run:*)", "npm run*"), ("Bash(git:*)", "git*"), ("Bash", "*")]),
         "a `:*` suffix renders to the glob of the same prefix, a bare Bash to *, and each is listed")

    omp_agent_cases(case, fresh, run, agent)

    base, _, _ = fresh()
    code, text = run(base, "--apply", extra_env={"PI_CODING_AGENT_DIR": None})
    case(lambda: code == 0 and (base / "home" / ".omp" / "agent" / "config.yml").is_file(),
         f"with no PI_CODING_AGENT_DIR, config.yml goes to ~/.omp/agent: {code}, {tail(text)}")


def omp_head(text):
    """({key: value} of the frontmatter of a rendered oh-my-pi agent, each value read as JSON, the
    text after the closing `---` line); ({}, text) for a file in another form."""
    lines = text.split("\n")
    try:
        end = lines.index("---", 1)
        head = {k: json.loads(v) for k, v in (l.split(": ", 1) for l in lines[1:end])}
    except ValueError:
        return {}, text
    return (head, "\n".join(lines[end + 1:])) if lines[0] == "---" else ({}, text)


def omp_agent_cases(case, fresh, run, agent):
    """The agents, the model roles and mcp.json of oh-my-pi; `agent` is the agent directory of an
    --apply with examples/models.toml, and `case`, `fresh` and `run` are those of omp_cases."""
    import tomllib

    def tail(text):
        return (text.strip().splitlines() or ["no output"])[-1]

    # The neutral tool names and oh-my-pi's, read from its builtin-names.ts at d9ee5e6: web_fetch
    # is `read`, which reads a URL, and a Kaimon tool is `mcp__kaimon_<tool>`. The role of each tier.
    names = {"read": "read", "edit": "edit", "write": "write", "grep": "grep", "glob": "glob", "shell": "bash",
             "agent": "task", "web_search": "web_search", "web_fetch": "read"}
    role_of = {"large": "opus", "medium": "sonnet", "small": "haiku"}
    sources = sorted((REPO / "agents").glob("*.md"))

    def differences(src):
        """Each difference of the rendered agent of `src` from its contract; none when it holds."""
        fm = frontmatter.parse_file(src)
        meta = fm.meta
        try:
            head, rest = omp_head((agent / "agents" / src.name).read_text())
        except OSError as e:
            return [f"{type(e).__name__}: {e}"]
        tools = list(dict.fromkeys(names.get(t) or "mcp__kaimon_" + t.removeprefix("mcp/kaimon/")
                                   for t in meta["tools"]))
        want = {"name": src.stem, "description": meta["description"], "tools": tools}
        if "model" in meta:
            want["model"] = "@" + role_of[meta["model"]]
        if "effort" in meta:
            want["thinking-level"] = meta["effort"]
        if "skills" in meta:
            want["autoloadSkills"] = meta["skills"]
        worktree = meta.get("isolation") == "worktree" or "isolation" in fm.body
        kaimon = any(t.startswith("mcp/kaimon/") for t in meta["tools"])
        uses = bool(meta.get("skills")) or "agent" in meta["tools"] or "shell" in meta["tools"] or worktree or kaimon
        # The text before the body: the Under oh-my-pi section, which the body cannot stand in for.
        under = rest.removesuffix(fm.body.lstrip("\n"))
        comment = f"<!-- Generated by `harness install` from agents/{src.name} of the harness repository."
        return [d for d, bad in [
            (f"the frontmatter {head} is not {want}", head != want),
            ("no generated-by comment naming its source in agents/", comment not in under),
            ("the body is not the source's", not rest.endswith(fm.body.lstrip("\n")) or not fm.body.strip()),
            ("an Under oh-my-pi section where no mechanism is used, or none where one is",
             ("## Under oh-my-pi" in under) != uses),
            ("no skills rule naming each skill", any(f"`{s}` skill" not in under and f"`{s}`," not in under
                                                     and f"`{s}` and" not in under for s in meta.get("skills", []))),
            ("no `git worktree add` rule for isolation: worktree",
             worktree and ("Nothing makes a worktree" not in under or "git worktree add" not in under)),
            ("no `task` rule for the agent tool", "agent" in meta["tools"] and "`task` tool" not in under),
            ("no `timeout` rule for the shell tool", "shell" in meta["tools"] and "`timeout`" not in under),
            ("no `mcp__kaimon_` name for a Kaimon tool", kaimon and "`mcp__kaimon_ex`" not in under)] if bad]

    rendered = sorted(p.name for p in (agent / "agents").glob("*.md")) if (agent / "agents").is_dir() else []
    case(lambda: rendered == [s.name for s in sources] and len(sources) == 20,
         f"--apply renders one oh-my-pi agent per agent of agents/, 20, and no council copy: {rendered}")
    case(lambda: {s.stem: differences(s) for s in sources} == {s.stem: [] for s in sources},
         "each of the 20 agents has its name, its description, its tools mapped by the table, the role of its tier, "
         "its effort as thinking-level, its skills as autoloadSkills, and its body, with an Under oh-my-pi section "
         "where it uses a Claude Code mechanism: "
         + "; ".join(f"{s.stem} {differences(s)}" for s in sources if differences(s))[:1500])

    # The model roles: one per tier of [omp], under the role that the agents name, and the default
    # on the `medium` tier's selector.
    tiers = tomllib.loads((REPO / "examples" / "models.toml").read_text())["omp"]
    try:
        roles = omp_config(agent / "config.yml").get("modelRoles")
    except (OSError, ValueError) as e:
        roles = f"{type(e).__name__}: {e}"
    case(lambda: roles == {"default": tiers["medium"], **{role_of[t]: tiers[t] for t in tiers}}
         and sorted(tiers) == ["large", "medium", "small"] and len(set(tiers.values())) == 3,
         f"config.yml modelRoles holds one role per tier of [omp] and the default on the medium tier: {roles}")
    # A missing tier, no [omp], and a tier that is no string, blank or not a tier exit 2 and write
    # nothing.
    example = (REPO / "examples" / "models.toml").read_text()
    at = example.index("[omp]")
    for label, text, word in [
        ("no small tier", example[:at] + example[at:].replace('small = "provider-b/small-model"\n', "", 1), "small"),
        ("no [omp] table", example[:example.index("[omp]")], "[omp]"),
        ("a tier that is a number", example.rstrip("\n").rsplit("\n", 1)[0] + "\nsmall = 5\n", "small"),
        ("a blank tier", example.rstrip("\n").rsplit("\n", 1)[0] + '\nsmall = " "\n', "small"),
        ("a key that is no tier", example + 'gpt = "provider-c/other-model"\n', "gpt"),
    ]:
        base2, _, _ = fresh()
        models = base2 / "models.toml"
        models.write_text(text)
        code2, out = run(base2, "--apply", models=models)
        case(lambda: code2 == 2 and "Traceback" not in out and str(models) in out and word in out
             and not (base2 / "omp").exists() and not (base2 / "opencode" / "opencode.jsonc").exists(),
             f"a models.toml with {label} exits 2, names the file and {word}, and writes nothing: {code2}, {tail(out)}")

    # The MCP entry: Kaimon over HTTP, the token read by a command at connect time, no other
    # server, and no foreign configuration source opted in, so ~/.claude.json is not imported.
    url, token = "http://127.0.0.1:2828/", "~/.config/kaimon/opencode-token"
    want = {"mcpServers": {"kaimon": {"type": "http", "url": url, "headers": {
        "Authorization": f"!printf 'Bearer %s' \"$(cat {token})\""}}}}
    try:
        mcp = json.loads((agent / "mcp.json").read_text())
    except (OSError, ValueError) as e:
        mcp = f"{type(e).__name__}: {e}"
    oc = (REPO / "adapters" / "opencode" / "opencode.jsonc").read_text()
    case(lambda: mcp == want and f'"url": "{url}"' in oc and f"{{file:{token}}}" in oc,
         f"mcp.json holds the Kaimon entry alone, over HTTP, with the URL and the token file of opencode.jsonc: {mcp}")
    try:
        config = omp_config(agent / "config.yml")
    except (OSError, ValueError) as e:
        config = {"error": str(e)}
    case(lambda: "enabledProviders" not in config and "disabledProviders" not in config and "error" not in config,
         f"config.yml opts no foreign source in, so ~/.claude.json is not imported: {sorted(config)}")

    # An unmapped tool, a tool of another MCP server, a Kaimon wildcard, an unknown tier, a reserved
    # name and a name that is not its file name exit 2.
    scratch = agent.parent / "omp-sources"
    scratch.mkdir(exist_ok=True)
    head = '---\nname: {name}\nmodel: {model}\ndescription: "d"\ntools:\n  - read\n  - {tool}\n---\nbody\n'
    for label, name, model, tool, words in [
        ("an unmapped tool", "x", "large", "Frobnicate", ["Frobnicate"]),
        ("a tool of another MCP server", "x", "large", "mcp/github/get_issue", ["mcp/github/get_issue"]),
        ("a Kaimon wildcard", "x", "large", "mcp/kaimon/*", ["mcp/kaimon/*"]),
        ("an unknown tier", "x", "nosuch", "shell", ["nosuch"]),
        ("the reserved name main", "main", "large", "shell", ["main"]),
        ("the reserved name Sub", "Sub", "large", "shell", ["Sub"]),
        ("a name that is not its file name", "y", "large", "shell", ["'y'", "'x'"]),
    ]:
        src = scratch / ("x.md" if name == "y" else f"{name}.md")
        src.write_text(head.format(name=name, model=model, tool=tool))
        try:
            render_agent(src, tiers)
            refusal = None
        except HarnessError as e:
            refusal = str(e)
        except Exception as e:  # noqa: BLE001 — a crash is no refusal, and the next case still runs
            refusal = f"crash {type(e).__name__}: {e}"
        case(lambda: refusal is not None and not refusal.startswith("crash") and str(src) in refusal
             and all(w in refusal for w in words),
             f"an agent with {label} exits 2 and names the file and {words}: {refusal}")
        src.unlink()

    # An installed oh-my-pi agent with no source is EXTRA, with its removal, and stays: oh-my-pi
    # still lists it. It reads the `.md` files of agents/ only.
    base2, _, _ = fresh()
    run(base2, "--apply")
    stale, other = base2 / "omp" / "agents" / "old.md", base2 / "omp" / "agents" / "notes.txt"
    for f in (stale, other):
        f.write_text("---\nname: old\ndescription: d\n---\n")
    code2, out = run(base2)
    case(lambda: code2 == 0 and f"EXTRA: {stale} " in out and f"rm '{stale}'" in out and stale.is_file()
         and f"EXTRA: {other} " not in out and "julia-builder.md is installed" not in out,
         f"an installed oh-my-pi agent with no source is EXTRA, with its removal, and the rendered agents and a "
         f"file of another suffix are not: {code2}, {[l for l in out.splitlines() if 'EXTRA' in l]}")
