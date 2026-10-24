"""The adapter of Antigravity: its permission layer, the guard hook and the CLI's permission
settings. Antigravity has no subcommand of its own.

`harness install` writes these files below ~/.gemini/, after the Claude Code layer is planned,
whose guard scripts it copies. With no ~/.gemini/, Antigravity's directory, the plan holds no file
and one warning:

  config/hooks.json              one named hook, `harness-guards`, with one `PreToolUse` group,
                                 matcher `*`, which runs config/hooks/guard.py by its absolute
                                 path with a timeout of 15 s (render_hooks); the matcher names no
                                 tool, so no tool is missed, and guard.py decides by the name of
                                 the tool
  config/hooks/guard.py          adapters/antigravity/guard.py, byte for byte: the guard scripts
                                 and the path list on every tool call, failing closed
  config/hooks/<script>          the guard scripts of frontends.GUARDS, copies of the Claude Code
                                 layer's
  config/guard-paths.json        the path list of guard.py (guard_paths): under `deny` that of
                                 adapters/opencode/plugins/guard-paths.json, MCP_CONFIG and the
                                 files of this layer, LAYER; under `edit` and `ask` the template's
                                 Edit denies and asks, which guard.py applies to the tools that
                                 write; under `bash_deny` and `bash_ask` the bodies of its Bash
                                 denies and asks, which guard.py applies to each segment of a
                                 command
  antigravity-cli/settings.json  the keys `permissions`, `toolPermission` and
                                 `enableTerminalSandbox` of the CLI's settings, set in the file
                                 as it is, every other key kept, after a backup (merge_settings);
                                 a file that is not a regular file or not a JSON object exits 2
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

MCP_CONFIG is a `read_file` deny after the template's, and LAYER and MCP_CONFIG are `write_file`
denies after that. Every other entry is dropped, with its reason. A dropped `Read(**/X)` deny is
still in the `deny` list of guard.py, and a dropped Edit entry in its `edit` or `ask` list. A
command with `$(…)` or a backtick matches only a full-line rule in Antigravity, so a `deny` does
not reach it; guard.py applies the Bash denies and asks to each segment of the line, the bodies of
`$(…)`, backticks and `( … )` included, and is the boundary. The desktop app reads no
`permissions`, so there guard.py alone applies them.
"""

import json
import os
import pathlib
import random
import re
import shlex
import stat
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
# The text of a `*` in an `allow` regex rule: no character that ends a segment, opens a
# substitution or redirects, so that an allow rule never matches across a segment.
SEGMENT_TEXT = r"[^;&|\n`$()<>]*"


def gemini_dir():
    """Antigravity's directory, ~/.gemini."""
    return pathlib.Path.home() / ".gemini"


def render(path, profile):
    """The path template `path` rendered with `profile`."""
    return profile_module.render_line(path, profile)


def render_hooks(root):
    """The text of hooks.json for Antigravity's directory `root`: the hook HOOK, which runs
    guard.py on every tool call by its absolute path, so that it runs from any directory."""
    handler = {"type": "command", "command": "python3 " + shlex.quote(str(root / "config" / "hooks" / "guard.py")),
               "timeout": HOOK_TIMEOUT}
    return json.dumps({HOOK: {"PreToolUse": [{"matcher": "*", "hooks": [handler]}]}}, indent=2) + "\n"


def guard_paths(profile):
    """The text of guard-paths.json, rendered with `profile`: under `deny` the `deny` list of
    OpenCode's path list, then MCP_CONFIG and LAYER; under `edit` every `Edit` deny of the
    settings template, and under `ask` every `Edit` ask, each with a leading `//` as `/`; under
    `bash_deny` and `bash_ask` the body of every `Bash` deny and ask of the template."""
    deny = json.loads(profile_module.render_file(GUARD_PATHS, profile))["deny"]
    permissions = json.loads(profile_module.render_file(SETTINGS, profile))["permissions"]
    bodies = {(tool, key): [m.group(1) for e in permissions.get(key, [])
                            if (m := re.fullmatch(rf"{tool}\((.*)\)", e, re.S))]
              for tool in ("Edit", "Bash") for key in ("deny", "ask")}
    return json.dumps({"deny": [*deny, render(MCP_CONFIG, profile), *(render(p, profile) for p in LAYER)],
                       "edit": [re.sub(r"^//+", "/", p) for p in bodies["Edit", "deny"]],
                       "ask": [re.sub(r"^//+", "/", p) for p in bodies["Edit", "ask"]],
                       "bash_deny": bodies["Bash", "deny"], "bash_ask": bodies["Bash", "ask"]},
                      indent=2, ensure_ascii=False) + "\n"


def command_rule(body, allow=False):
    """The Antigravity rule of the Claude Code rule `Bash(body)`, in the list `allow` or another.
    A regex rule matches a trailing ` *` with no text, as the prefix rule does; in an `allow` rule a
    `*` matches no text that ends a segment (SEGMENT_TEXT)."""
    m = re.fullmatch(r"([^*]*[^*\s]) \*", body)
    if m:
        return f"command({m.group(1)})"
    star = SEGMENT_TEXT if allow else ".*"
    head, tail = (body[:-2], f"(?: {star})?") if body.endswith(" *") else (body, "")
    return "command(regex:^" + star.join(REGEX_SPECIAL.sub(lambda c: "\\" + c.group(0), part)
                                         for part in head.split("*")) + tail + "$)"


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
    `read_file` deny and LAYER and MCP_CONFIG as `write_file` denies after them, and each entry that
    has no rule, with its reason."""
    rules, dropped = {key: [] for key in LISTS}, []
    for key in LISTS:
        for entry in cfg["permissions"].get(key, []):
            rule, reason = None, None
            if m := re.fullmatch(r"Bash\((.*)\)", entry, re.S):
                rule = command_rule(m.group(1), key == "allow")
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
    rules["deny"] += [f"read_file({render(MCP_CONFIG, profile)})",
                      *(f"write_file({render(p, profile).removesuffix('/**')})" for p in (*LAYER, MCP_CONFIG))]
    return rules, dropped


def merge_settings(path, rules):
    """The bytes of the CLI's settings at `path` with `permissions` set to `rules` and the keys of
    POSTURE set, every other key kept in its place, with the file's indent and with no character
    escaped but a lone surrogate, as Claude Code's merge writes them; a missing file holds no key.
    Exits 2, before anything is written, on a file that is not a regular file, cannot be read, is
    not UTF-8, is not a JSON object (`json_object`), is nested deeper than json writes, or holds a
    number outside the three keys that json writes in other text (`rewritten_numbers`)."""
    claude = frontends.adapter("claude")
    refused = "; the install sets three keys of a JSON object in a regular file there, and writes nothing"
    # One lstat, so that a link, a FIFO or a directory is refused before it is opened.
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        st = None
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    settings, indent = {}, 2
    if st is not None:
        if not stat.S_ISREG(st.st_mode):
            raise HarnessError(f"{path} is not a regular file{refused}")
        try:
            text = path.read_bytes().decode("utf-8")
        except OSError as e:
            raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
        except UnicodeDecodeError as e:
            raise HarnessError(f"{path} is not UTF-8: {e.reason} at byte {e.start}{refused}") from None
        settings, indent = claude.json_object(path, text), claude.indent_of(text)
        numbers = claude.rewritten_numbers(text, ("permissions", *POSTURE))
        if numbers:
            raise HarnessError(f"{path} holds numbers that JSON would write in other text: "
                               f"{', '.join(f'{k}: {old} as {new}' for k, old, new in numbers)}{refused}")
    settings.update(permissions=rules, **POSTURE)
    try:
        return (claude.dumps(settings, indent=indent) + "\n").encode()
    except RecursionError:  # a nesting that json.loads reads and json.dumps cannot write
        raise HarnessError(f"{path} is JSON nested too deep to write again{refused}") from None


def plan(ctx):
    """Antigravity's part of `harness install`, as the docstring of this module says; the guard
    scripts are those of the Claude Code layer's plan in `ctx.plans`."""
    root = gemini_dir()
    if not root.is_dir():
        state = "is not a directory" if root.exists() else "does not exist"
        return frontends.Plan(warnings=[(f"{root} {state}, so the Antigravity layer is not installed.",
                                         "Install Antigravity, then run `harness install` again.")])
    claude = frontends.adapter("claude")
    cfg = claude.settings_template(ctx.profile, profile_module.network_path(ctx.args.profile))
    rules, _ = render_permissions(cfg, ctx.profile)
    scripts = {f"hooks/{g}" for g in frontends.GUARDS}
    files = [("config/hooks.json", render_hooks(root).encode(), None),
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
    (base / "home" / ".gemini").write_text("x")
    code, dry = run(base)
    warned = [w for w in dry.split("WARNING: ")[1:] if ".gemini" in w]
    case(lambda: line.findall(dry) == [] and len(warned) == 1 and "is not a directory" in warned[0],
         f"with a file at ~/.gemini, the one warning says that it is not a directory: {warned}")

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
    handler = "python3 " + shlex.quote(str(config / "hooks" / "guard.py"))
    case(lambda: json.loads(hooks)
         == {HOOK: {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": handler,
                                                                "timeout": 15}]}]}},
         f"hooks.json holds the one hook {HOOK}: one PreToolUse group, matcher *, guard.py by its absolute path "
         f"with a timeout of 15 s: {hooks!r}")
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
    bash = {key: [e[len("Bash("):-1] for e in template[key] if e.startswith("Bash(")] for key in ("deny", "ask")}
    lists = config / "guard-paths.json"
    written = json.loads(lists.read_text()) if lists.is_file() else {}
    case(lambda: written == {"deny": [*opencode, f"{h}/.gemini/config/mcp_config.json", f"{h}/.gemini/config/hooks.json",
                                      f"{h}/.gemini/config/hooks/**", f"{h}/.gemini/config/guard-paths.json",
                                      f"{h}/.gemini/antigravity-cli/settings.json"],
                             "edit": edits["deny"], "ask": edits["ask"],
                             "bash_deny": bash["deny"], "bash_ask": bash["ask"]}
         and len(edits["deny"]) >= 54 and len(edits["ask"]) >= 4
         and len(bash["deny"]) >= 187 and len(bash["ask"]) >= 105,
         f"guard-paths.json is OpenCode's deny list, then mcp_config.json and the files of the layer; `edit` is "
         f"every Edit deny of the template and `ask` every Edit ask; `bash_deny` and `bash_ask` are the bodies "
         f"of every Bash deny and ask, entry by entry: { {k: len(v) for k, v in written.items()} }")
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
    examples = {("deny", "Bash(sed -i* *)"): r"command(regex:^sed -i.*(?: .*)?$)",
                ("deny", "Bash(git push * -f)"): r"command(regex:^git push .* -f$)",
                ("deny", "Bash(git -C * add .)"): r"command(regex:^git -C .* add \.$)",
                ("allow", "Bash(git status)"): r"command(regex:^git status$)",
                ("allow", "Bash(git log *)"): "command(git log)",
                ("allow", "Bash(git branch * -f)"): r"command(regex:^git branch [^;&|\n`$()<>]* -f$)",
                ("deny", r"Bash(x * \.^$|?+()[]{} *)"): r"command(regex:^x .* \\\.\^\$\|\?\+\(\)\[\]\{\}(?: .*)?$)"}
    case(lambda: all(command_rule(e[len("Bash("):-1], key == "allow") == want for (key, e), want in examples.items()),
         f"the decided forms: {[(e, command_rule(e[len('Bash('):-1], key == 'allow')) for (key, e) in examples]}")
    case(lambda: rule_matches("command(git push --force)", "git push --force origin x")
         and not rule_matches("command(git push --force)", "git push --force-with-lease")
         and rule_matches(command_rule("git push --force*"), "git push --force-with-lease"),
         "a prefix rule matches whole words, and a regex rule any text in place of a *")
    branch, sed = command_rule("git branch * -f", allow=True), command_rule("sed -i* *")
    case(lambda: rule_matches(branch, "git branch topic -f") and not rule_matches(branch, "git branch x -f; rm -rf ~/y")
         and not rule_matches(branch, "git branch $(rm -rf ~/x) -f") and rule_matches(sed, "sed -i 's/a;b/c/' f")
         and rule_matches(command_rule("git -C * reset --hard *"), "git -C . reset --hard"),
         "an allow regex rule stays in one segment, a deny regex rule does not, and a trailing * matches nothing too")
    lists = json.loads(guard_paths(profile))
    # `git push  *` is a body of one literal part with a trailing ` *`, a form that no template body
    # has: each such body is a prefix body.
    matcher_cases(case, [*lists["bash_deny"], *lists["bash_ask"], "git push  *"])


def reference_matcher(body, word_break):
    """The matcher of `Bash(body)` that the cases hold guard.py's against, a regular expression:
    `Bash(x *)` when the words of `x` are a run of the words, any other body when its pattern
    full-matches the words from one of them to the last, joined by `word_break`, with `*` as any
    text and a trailing ` *` as no text too. Its cost grows with the square of the number of words,
    so the cases give it short lists only."""
    if m := re.fullmatch(r"([^*]*[^*\s]) \*", body, re.S):
        x = m.group(1).split()
        return lambda w: any(w[i:i + len(x)] == x for i in range(len(w)))
    head, tail = (body[:-2], f"(?:{word_break}.*)?") if body.endswith(" *") else (body, "")
    literal = (word_break.join(map(re.escape, re.split(r"\s+", part))) for part in head.split("*"))
    pattern = re.compile(".*".join(literal) + tail, re.S)
    return lambda w: any(pattern.fullmatch(word_break.join(w[i:])) for i in range(len(w)))


def matcher_cases(case, bodies):
    """guard.py's matcher of each Bash body against reference_matcher, on a fixed set of word lists
    of up to 8 words for each body: the body with each `*` filled by nothing, `x`, `zz` or one of
    the body's own literal words, with up to two words put before it and after it and at times one
    word replaced; and lists drawn from the body's literal words, each also with `zz` before or
    after it, `x`, `zz` and the empty word."""
    try:
        total, matching, differ = compare_matchers(bodies)
    except Exception as e:  # a case that crashes is BAD, and the next case still runs
        case(lambda: False, f"guard.py's matcher of each Bash deny and ask runs: {type(e).__name__}: {e}")
        return
    case(lambda: not differ and 0 < matching < total,
         f"guard.py's matcher of each Bash deny and ask decides as the reference regex on each of {total} word "
         f"lists, {matching} of them matching: {differ[:3]}")


def compare_matchers(bodies):
    """(lists, lists that match, [(body, words, the reference's answer)] where guard.py's matcher
    differs) of matcher_cases."""
    guard = _guard_module()
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
    if head is not None and (not rule_matches(rule, head.replace("*", "zz"))
                             or not head.endswith("*") and rule_matches(rule, head.replace("*", "zz") + "zz")):
        return False
    for i, c in enumerate(body):
        other = (body[:i] + "Q" + body[i + 1:]).replace("*", "zz")
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
    text = settings.read_text()
    case(lambda: text.split("\n")[1].startswith('    "theme"'),
         f"--apply keeps the file's indent of 4: {text.split(chr(10))[1]!r}")

    base, _, _ = scratch.fresh()
    cli = base / "home" / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    (cli / "settings.json").write_text('{"name": "\\ud800", "dash": "—"}\n', encoding="utf-8")
    code, text = run(base, "--apply")
    written = (cli / "settings.json").read_text(encoding="utf-8")
    case(lambda: code == 0 and '"name": "\\ud800"' in written and '"dash": "—"' in written,
         f"a lone surrogate stays an escape, and a non-ASCII character stays as it is: {code}, {tail(text)!r}")

    def fifo(path):
        os.mkfifo(path)

    def link(path):
        (path.parent / "real.json").write_text("{}\n")
        path.symlink_to("real.json")

    for data, label in [(b"[1, 2]\n", "holds a JSON array"), (b"not json\n", "holds text that is not JSON"),
                        (b'"x"\n', "holds a JSON string"), (b"\xff\n", "holds bytes that are not UTF-8"),
                        (b"[" * 100000 + b"]" * 100000, "holds a JSON array nested 100000 deep"),
                        (b'{"a": ' * 100000 + b"1" + b"}" * 100000, "holds a JSON object nested 100000 deep"),
                        (b'{"limit": 1e400}\n', "holds a number that JSON writes in other text"),
                        (fifo, "is a FIFO"), (link, "is a symlink"), (os.mkdir, "is a directory")]:
        base, _, _ = scratch.fresh()
        cli = base / "home" / ".gemini" / "antigravity-cli"
        cli.mkdir(parents=True)
        if callable(data):
            data(cli / "settings.json")
        else:
            (cli / "settings.json").write_bytes(data)
        snapshot = scratch.snapshot(base)
        code, text = run(base, "--apply")
        case(lambda: scratch.refused(code, text) and str(cli / "settings.json") in text
             and scratch.snapshot(base) == snapshot,
             f"a settings.json that {label} exits 2, names the file, and nothing is written: {code}, "
             f"{tail(text)!r}")
