"""The adapter of Antigravity: its permission layer, the guard hook and the CLI's permission
settings. Antigravity has no subcommand of its own.

`harness install` writes these files below ~/.gemini/, after the Claude Code layer is planned,
whose guard scripts it copies. With no ~/.gemini/, Antigravity's directory, the plan holds no file
and one warning:

  config/hooks.json              one named hook, `harness-guards`, with one `PreToolUse` group,
                                 matcher `*`, which runs hooks/guard.py with a timeout of 15 s
                                 (render_hooks); the matcher names no tool, so no tool is missed,
                                 and guard.py decides by the name of the tool
  config/hooks/guard.py          adapters/antigravity/guard.py, byte for byte: the guard scripts
                                 and the path list on every tool call, failing closed
  config/hooks/<script>          the guard scripts of frontends.GUARDS, copies of the Claude Code
                                 layer's
  config/guard-paths.json        the path list of guard.py (guard_paths): under `deny` that of
                                 adapters/opencode/plugins/guard-paths.json, MCP_CONFIG and the
                                 files of this layer, LAYER; under `edit` and `ask` the template's
                                 Edit denies and asks, which guard.py applies to the tools that
                                 write
  antigravity-cli/settings.json  the keys `permissions`, `toolPermission` and
                                 `enableTerminalSandbox` of the CLI's settings, set in the file
                                 as it is, every other key kept, after a backup (merge_settings);
                                 a file that is not a JSON object exits 2 before any write

THE POSTURE is Claude Code's: the terminal sandbox on, and `toolPermission` `proceed-in-sandbox`,
the counterpart of `autoAllowBashIfSandboxed`. `allowNonWorkspaceAccess` is not written, so it
keeps its default, `false`. The desktop app reads neither `permissions` nor `toolPermission` from
the CLI's file.

THE RULES are the settings template's, rendered with the profile and the network lists as Claude
Code's settings are (render_permissions); each stays in its list, `deny`, `ask` or `allow`, in the
template's order:

  Bash(x *)              command(x): a prefix matches word by word
  Bash(…) any other form command(regex:^…$), each `*` as `.*` and the rest literal, which matches
                         the lines that the entry matches
  Read(p), Edit(p)       read_file(p), write_file(p): a leading `//` as `/`, and a trailing `/**`
                         removed, because a path covers its subtree. A path with any other glob,
                         `**/X` among them, has no form in Antigravity and is dropped
  WebFetch(domain:X)     read_url(X), for each allow host of settings/network.toml and its overlay

MCP_CONFIG is a `read_file` deny after the template's, and LAYER and MCP_CONFIG are `write_file`
denies after that. Every other entry is dropped, with its reason. A dropped `Read(**/X)` deny is
still in the `deny` list of guard.py, and a dropped Edit entry in its `edit` or `ask` list. A
command with `$(…)` or a backtick matches only a full-line rule in Antigravity, so a `deny` does
not reach it; guard.py still reads the whole line, and is the boundary.
"""

import json
import pathlib
import re
import tempfile

from harness import REPO, HarnessError, frontends
from harness import profile as profile_module

NAME = "antigravity"
TEMPLATES = []
RESTART = "Restart Antigravity and agy: their hooks and permission settings changed."

SOURCE = REPO / "adapters" / "antigravity"
GUARD_PATHS = REPO / "adapters" / "opencode" / "plugins" / "guard-paths.json"
HOOK = "harness-guards"
HOOK_TIMEOUT = 15
# The MCP configuration of Antigravity, which holds the Kaimon token in plain text.
MCP_CONFIG = "{home}/.gemini/config/mcp_config.json"
# The files of this layer, which an agent that rewrites them could use to switch off its guard.
LAYER = ("{home}/.gemini/config/hooks.json", "{home}/.gemini/config/hooks/**", "{home}/.gemini/config/guard-paths.json",
         "{home}/.gemini/antigravity-cli/settings.json")
SETTINGS = REPO / "settings" / "settings.proposal.json"
POSTURE = {"toolPermission": "proceed-in-sandbox", "enableTerminalSandbox": True}
# The lists of the template's `permissions` and of Antigravity's, in the order the rules render.
LISTS = ("deny", "ask", "allow")
REGEX_SPECIAL = re.compile(r"[\\.^$|?*+()\[\]{}]")


def gemini_dir():
    """Antigravity's directory, ~/.gemini."""
    return pathlib.Path.home() / ".gemini"


def render_hooks():
    """The text of hooks.json: the hook HOOK, which runs guard.py on every tool call."""
    handler = {"type": "command", "command": "python3 hooks/guard.py", "timeout": HOOK_TIMEOUT}
    return json.dumps({HOOK: {"PreToolUse": [{"matcher": "*", "hooks": [handler]}]}}, indent=2) + "\n"


def guard_paths(profile):
    """The text of guard-paths.json, rendered with `profile`: under `deny` the `read` denies of
    OpenCode's path list, then MCP_CONFIG and LAYER; under `edit` every `Edit` deny of the
    settings template, and under `ask` every `Edit` ask, each with a leading `//` as `/`."""
    render = lambda path: profile_module.render_line(path, profile)  # noqa: E731
    deny = json.loads(profile_module.render_file(GUARD_PATHS, profile))["deny"]
    permissions = json.loads(profile_module.render_file(SETTINGS, profile))["permissions"]
    edits = {key: [re.sub(r"^//+", "/", m.group(1)) for e in permissions.get(key, [])
                   if (m := re.fullmatch(r"Edit\((.*)\)", e, re.S))] for key in ("deny", "ask")}
    return json.dumps({"deny": [*deny, render(MCP_CONFIG), *map(render, LAYER)], "edit": edits["deny"],
                       "ask": edits["ask"]}, indent=2, ensure_ascii=False) + "\n"


def command_rule(body):
    """The Antigravity rule of the Claude Code rule `Bash(body)`."""
    m = re.fullmatch(r"([^*]*[^*\s]) \*", body)
    if m:
        return f"command({m.group(1)})"
    return "command(regex:^" + ".*".join(REGEX_SPECIAL.sub(lambda c: "\\" + c.group(0), part)
                                         for part in body.split("*")) + "$)"


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


def render_permissions(cfg, profile):
    """({list: [rule]}, [(list, entry, reason)]) of the `permissions` of `cfg`, the rendered
    settings template: the Antigravity rules in the template's lists and order, MCP_CONFIG as a
    `read_file` deny after them, and each entry that has no rule, with its reason."""
    rules, dropped = {key: [] for key in LISTS}, []
    for key in LISTS:
        for entry in cfg["permissions"].get(key, []):
            rule, reason = None, None
            if m := re.fullmatch(r"Bash\((.*)\)", entry, re.S):
                rule = command_rule(m.group(1))
            elif m := re.fullmatch(r"(Read|Edit)\((.*)\)", entry, re.S):
                rule, reason = path_rule({"Read": "read_file", "Edit": "write_file"}[m.group(1)], m.group(2))
            elif (m := re.fullmatch(r"WebFetch\(domain:(.*)\)", entry)) and key == "allow":
                rule = f"read_url({m.group(1)})"
            else:
                reason = "no Antigravity rule renders it: the rules come from the Bash, Read and Edit entries and " \
                         "the allow hosts"
            if rule is None:
                dropped.append((key, entry, reason))
            else:
                rules[key].append(rule)
    render = lambda path: profile_module.render_line(path, profile)  # noqa: E731
    rules["deny"] += [f"read_file({render(MCP_CONFIG)})",
                      *(f"write_file({render(p).removesuffix('/**')})" for p in (*LAYER, MCP_CONFIG))]
    return rules, dropped


def merge_settings(path, rules):
    """The bytes of the CLI's settings at `path` with `permissions` set to `rules` and the keys of
    POSTURE set, every other key kept in its place; a missing file holds no key. A file that cannot
    be read, or is not a JSON object, exits 2."""
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        settings = {}
    except (OSError, UnicodeDecodeError) as e:
        raise HarnessError(f"{path} cannot be read: {getattr(e, 'strerror', None) or e}") from None
    else:
        try:
            settings = json.loads(text)
        except ValueError as e:
            raise HarnessError(f"{path} is not JSON ({e}); the install sets three keys of a JSON object there, "
                               "and writes nothing") from None
        if not isinstance(settings, dict):
            raise HarnessError(f"{path} holds JSON that is not an object; the install sets three keys of a JSON "
                               "object there, and writes nothing")
    settings.update(permissions=rules, **POSTURE)
    return (json.dumps(settings, indent=2, ensure_ascii=False) + "\n").encode()


def plan(ctx):
    """Antigravity's part of `harness install`, as the docstring of this module says; the guard
    scripts are those of the Claude Code layer's plan in `ctx.plans`."""
    root = gemini_dir()
    if not root.is_dir():
        return frontends.Plan(warnings=[(f"{root} does not exist, so the Antigravity layer is not installed.",
                                         "Install Antigravity, then run `harness install` again.")])
    claude = frontends.adapter("claude")
    cfg = claude.settings_template(ctx.profile, profile_module.network_path(ctx.args.profile))
    rules, _ = render_permissions(cfg, ctx.profile)
    scripts = {f"hooks/{g}" for g in frontends.GUARDS}
    files = [("config/hooks.json", render_hooks().encode(), None),
             ("config/hooks/guard.py", (SOURCE / "guard.py").read_bytes(), None),
             *((f"config/{dst}", data, mode) for dst, data, mode in ctx.plans["claude"].shared if dst in scripts),
             ("config/guard-paths.json", guard_paths(ctx.profile).encode(), None)]
    settings = root / "antigravity-cli" / "settings.json"
    # The CLI's settings hold the user's own keys, so a replaced file is backed up first.
    return frontends.Plan(files=[*((root / rel, data, mode, f"antigravity/{rel}") for rel, data, mode in files),
                                 (settings, merge_settings(settings, rules), None,
                                  "antigravity/antigravity-cli/settings.json", True)])


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
    return command.split()[:len(m.group(2).split())] == m.group(2).split()


# ---------------------------------------------------------------------------------------------
# The cases of `harness test`


def selftest():
    """The Antigravity layer of `harness install`, end to end on scratch HOMEs."""
    from harness.install_cases import Scratch

    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  antigravity: {label}")

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Scratch(check, tmp)
        layer_cases(scratch)
        rule_cases(scratch.case)
        merge_cases(scratch)
    return total, wrong


def layer_cases(scratch):
    """The files of the layer, the warning with no ~/.gemini/, hooks.json and the copies."""
    case, run, tail = scratch.case, scratch.run, scratch.tail
    line = re.compile(r"^antigravity/(\S+)\s+(\S+)", re.M)
    want = sorted(["config/hooks.json", "config/guard-paths.json", "config/hooks/guard.py",
                   *(f"config/hooks/{g}" for g in frontends.GUARDS), "antigravity-cli/settings.json"])

    base, claude, _ = scratch.fresh()
    code, dry = run(base)
    warned = [w for w in dry.split("WARNING: ")[1:] if ".gemini" in w]
    case(lambda: code in (0, 1) and line.findall(dry) == [] and len(warned) == 1
         and str(base / "home" / ".gemini") in warned[0] and not (base / "home" / ".gemini").exists(),
         f"with no ~/.gemini/, the dry run lists no file of the layer and gives one warning that names the "
         f"directory: {code}, {line.findall(dry)}, {warned}")

    base, claude, _ = scratch.fresh()
    gemini = base / "home" / ".gemini"
    gemini.mkdir()
    code, dry = run(base)
    listed = dict(line.findall(dry))
    case(lambda: sorted(listed) == want and set(listed.values()) == {"INSTALL"}
         and sorted(p.relative_to(gemini).as_posix() for p in gemini.rglob("*")) == [],
         f"the dry run lists hooks.json, guard-paths.json, hooks/guard.py, the seven scripts of frontends.GUARDS and "
         f"antigravity-cli/settings.json, each INSTALL, and writes nothing: {code}, {listed}")
    code, text = run(base, "--apply")
    if code != 0:
        case(lambda: False, f"the setup install --apply of the Antigravity cases exits {code}: {tail(text)!r}; "
                            f"the cases after it do not run")
        return
    installed = sorted(p.relative_to(gemini).as_posix() for p in gemini.rglob("*") if p.is_file())
    case(lambda: installed == want, f"--apply installs those files below ~/.gemini/, and nothing else: {installed}")
    config = gemini / "config"
    hooks = (config / "hooks.json").read_text() if (config / "hooks.json").is_file() else None
    case(lambda: json.loads(hooks)
         == {HOOK: {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python3 hooks/guard.py",
                                                                "timeout": 15}]}]}},
         f"hooks.json holds the one hook {HOOK}: one PreToolUse group, matcher *, guard.py with a timeout of 15 s: "
         f"{hooks!r}")
    case(lambda: (config / "hooks" / "guard.py").read_bytes() == (SOURCE / "guard.py").read_bytes()
         and all((config / "hooks" / g).read_bytes() == (claude / "hooks" / g).read_bytes() for g in frontends.GUARDS),
         "hooks/guard.py is adapters/antigravity/guard.py, and each guard script is the Claude Code layer's copy")
    case(lambda: (lambda g: (*g.SHELL, g.WORK_TREE, g.KAIMON))(_guard_module()) == frontends.GUARDS,
         f"guard.py runs the scripts of frontends.GUARDS, in its order: {frontends.GUARDS}")
    profile = profile_module.load(base / "profile.toml")
    opencode = json.loads(profile_module.render_file(GUARD_PATHS, profile))["deny"]
    h = profile["home"]
    template = json.loads(profile_module.render_file(SETTINGS, profile))["permissions"]
    edits = {key: [re.sub(r"^//+", "/", e[len("Edit("):-1]) for e in template[key] if e.startswith("Edit(")]
             for key in ("deny", "ask")}
    lists = config / "guard-paths.json"
    written = json.loads(lists.read_text()) if lists.is_file() else {}
    case(lambda: written == {"deny": [*opencode, f"{h}/.gemini/config/mcp_config.json", f"{h}/.gemini/config/hooks.json",
                                      f"{h}/.gemini/config/hooks/**", f"{h}/.gemini/config/guard-paths.json",
                                      f"{h}/.gemini/antigravity-cli/settings.json"],
                             "edit": edits["deny"], "ask": edits["ask"]}
         and len(edits["deny"]) >= 54 and len(edits["ask"]) >= 4,
         f"guard-paths.json is OpenCode's deny list, then mcp_config.json and the files of the layer; `edit` is "
         f"every Edit deny of the template and `ask` every Edit ask, entry by entry: "
         f"{ {k: len(v) for k, v in written.items()} }")
    new = gemini / "antigravity-cli" / "settings.json"
    settings = json.loads(new.read_text()) if new.is_file() else {}
    case(lambda: settings["toolPermission"] == "proceed-in-sandbox" and settings["enableTerminalSandbox"] is True
         and "allowNonWorkspaceAccess" not in settings and sorted(settings) == sorted(["permissions", *POSTURE]),
         f"a new settings.json holds the three keys, with the sandbox on and proceed-in-sandbox, and no "
         f"allowNonWorkspaceAccess: {sorted(settings)}")
    code, text = run(base, "--apply")
    case(lambda: code == 0 and dict(line.findall(text)) == {k: "already" for k in want}
         and not list((gemini / "antigravity-cli").glob("settings.json.bak-*")),
         f"a second --apply finds every file identical and makes no backup: {code}, {dict(line.findall(text))}")


def _guard_module():
    """adapters/antigravity/guard.py as a module."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("harness_antigravity_guard", SOURCE / "guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rule_cases(case):
    """The rules against their sources, entry by entry, with the dummy profile."""
    from harness.install_cases import scratch_profile

    claude = frontends.adapter("claude")
    with tempfile.TemporaryDirectory() as tmp:
        profile = profile_module.load(scratch_profile(pathlib.Path(tmp) / "profile.toml", None))
        cfg = claude.settings_template(profile, pathlib.Path(tmp) / "network.toml")
    rules, dropped = render_permissions(cfg, profile)
    reasons = {(key, entry): reason for key, entry, reason in dropped}
    h = profile["home"]
    extras = [f"read_file({h}/.gemini/config/mcp_config.json)", f"write_file({h}/.gemini/config/hooks.json)",
              f"write_file({h}/.gemini/config/hooks)", f"write_file({h}/.gemini/config/guard-paths.json)",
              f"write_file({h}/.gemini/antigravity-cli/settings.json)",
              f"write_file({h}/.gemini/config/mcp_config.json)"]
    wrong = []
    for key in LISTS:
        out = iter(rules[key])
        for entry in cfg["permissions"][key]:
            if (key, entry) in reasons:
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
            elif m := re.fullmatch(r"(Read|Edit)\((.*)\)", entry, re.S):
                path = re.sub(r"^//+", "/", m.group(2)).removesuffix("/**")
                ok = got == f"{'read_file' if m.group(1) == 'Read' else 'write_file'}({path})"
            else:
                host = re.fullmatch(r"WebFetch\(domain:(.*)\)", entry)
                ok = host is not None and key == "allow" and got == f"read_url({host.group(1)})"
            if not ok:
                wrong.append((key, entry, got))
        rest = list(out)
        if rest != (extras if key == "deny" else []):
            wrong.append((key, "after the template's entries", rest))
    case(lambda: not wrong and rules["allow"] and rules["ask"] and rules["deny"],
         f"each Bash, Read and Edit entry and each allow host is one rule in its list, in order, that matches the "
         f"entry's lines or names its path; after them, mcp_config.json is a read_file deny, and the files of the "
         f"layer and mcp_config.json are write_file denies: {wrong[:5]}")
    bash = {key: [e for e in cfg["permissions"][key] if e.startswith("Bash(")] for key in LISTS}
    case(lambda: not [d for d in dropped if d[1].startswith("Bash(")]
         and all(sum(r.startswith("command(") for r in rules[key]) == len(bash[key]) for key in LISTS),
         f"every Bash entry becomes a command rule: "
         f"{ {key: (len(bash[key]), sum(r.startswith('command(') for r in rules[key])) for key in LISTS} }")
    recursive = [e for key, e, _ in dropped if key == "deny" and e.startswith("Read(**/")]
    paths = json.loads(guard_paths(profile))["deny"]
    case(lambda: recursive and all(e[len("Read("):-1] in paths for e in recursive),
         f"each dropped Read(**/X) deny is in the path list of guard.py: {recursive}")
    lists = json.loads(guard_paths(profile))
    covered = [(key, e) for key, e, _ in dropped if e.startswith("Edit(")
               and re.sub(r"^//+", "/", e[len("Edit("):-1]) not in lists["edit" if key == "deny" else "ask"]]
    case(lambda: not covered and any(e.startswith("Edit(") for _, e, _ in dropped),
         f"each dropped Edit deny is in the `edit` list of guard.py, and each dropped Edit ask in its `ask` list: "
         f"{covered}")
    others = [(key, e) for key, e, _ in dropped if not re.match(r"(Bash|Read|Edit)\(", e)]
    case(lambda: all(not re.fullmatch(r"WebFetch\(domain:.*\)", e) or key != "allow" for key, e in others)
         and all(reasons[d] for d in reasons),
         f"every entry that is dropped has a reason, and no allow host is among them: {others[:3]}")
    expected = [(key, e) for key in LISTS for e in cfg["permissions"][key]
                if (m := re.fullmatch(r"(?:Read|Edit)\(/*(.*?)(?:/\*\*)?\)", e, re.S))
                and re.search(r"[*?\[]", m.group(1))]
    got_drops = [(key, e) for key, e, _ in dropped if re.match(r"(Read|Edit)\(", e)]
    case(lambda: got_drops == expected,
         f"the dropped Read and Edit entries are exactly those whose path keeps a glob: {got_drops}")
    globbed = [r for key in LISTS for r in rules[key] if re.match(r"(read_file|write_file)\(.*[*?\[]", r)]
    case(lambda: not globbed, f"no read_file or write_file rule holds a glob: {globbed[:3]}")
    small = {"permissions": {"deny": ["WebFetch(domain:x.org)", "Read(src/x)", "Edit(//a/*.py)", "Edit(//a/b/**)"],
                             "allow": ["WebFetch(domain:y.org)", "mcp__k__ping"]}}
    got = render_permissions(small, profile)
    case(lambda: got[0] == {"deny": ["write_file(/a/b)", *extras], "ask": [], "allow": ["read_url(y.org)"]}
         and [e for _, e, _ in got[1]] == ["WebFetch(domain:x.org)", "Read(src/x)", "Edit(//a/*.py)", "mcp__k__ping"],
         f"a WebFetch deny, a relative path, a glob in a path and an MCP tool are dropped; an allow host is a "
         f"read_url rule: {got}")
    examples = {("deny", "Bash(sed -i* *)"): r"command(regex:^sed -i.* .*$)",
                ("deny", "Bash(git push * -f)"): r"command(regex:^git push .* -f$)",
                ("allow", "Bash(git status)"): r"command(regex:^git status$)",
                ("allow", "Bash(git log *)"): "command(git log)"}
    case(lambda: all(command_rule(e[len("Bash("):-1]) == want for (_, e), want in examples.items()),
         f"the decided forms: {[(e, command_rule(e[len('Bash('):-1])) for (_, e) in examples]}")
    case(lambda: rule_matches("command(git push --force)", "git push --force origin x")
         and not rule_matches("command(git push --force)", "git push --force-with-lease")
         and rule_matches(command_rule("git push --force*"), "git push --force-with-lease"),
         "a prefix rule matches whole words, and a regex rule any text in place of a *")


def merge_cases(scratch):
    """The merge of the CLI's settings: the three keys only, the rest kept, a backup, a missing
    file created, and exit 2 before any write on a file that is not a JSON object."""
    case, run, tail = scratch.case, scratch.run, scratch.tail
    base, _, _ = scratch.fresh()
    cli = base / "home" / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    settings = cli / "settings.json"
    own = {"theme": "dark", "permissions": {"allow": ["command(ls)"]}, "toolPermission": "always-ask",
           "nested": {"a": [1, 2]}, "allowNonWorkspaceAccess": False}
    settings.write_text(json.dumps(own, indent=4) + "\n")
    before = settings.read_bytes()
    code, text = run(base, "--apply")
    merged = json.loads(settings.read_text())
    backups = list(cli.glob("settings.json.bak-*"))
    case(lambda: code == 0 and list(merged) == list(own) + ["enableTerminalSandbox"]
         and {k: merged[k] for k in ("theme", "nested", "allowNonWorkspaceAccess")}
         == {k: own[k] for k in ("theme", "nested", "allowNonWorkspaceAccess")}
         and merged["toolPermission"] == "proceed-in-sandbox" and merged["permissions"]["allow"] != ["command(ls)"],
         f"--apply sets the three keys, keeps every other key and the order of the keys: {code}, {list(merged)}, "
         f"{tail(text)}")
    case(lambda: len(backups) == 1 and backups[0].read_bytes() == before,
         f"--apply keeps a backup of the file it replaces, with its bytes: {backups}")
    for data, label in [(b"[1, 2]\n", "a JSON array"), (b"not json\n", "text that is not JSON"),
                        (b'"x"\n', "a JSON string"), (b"\xff\n", "bytes that are not UTF-8")]:
        base, _, _ = scratch.fresh()
        cli = base / "home" / ".gemini" / "antigravity-cli"
        cli.mkdir(parents=True)
        (cli / "settings.json").write_bytes(data)
        snapshot = scratch.snapshot(base)
        code, text = run(base, "--apply")
        case(lambda: scratch.refused(code, text) and str(cli / "settings.json") in text
             and scratch.snapshot(base) == snapshot,
             f"a settings.json that holds {label} exits 2, names the file, and nothing is written: {code}, "
             f"{tail(text)!r}")
