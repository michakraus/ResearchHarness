#!/usr/bin/env python3
"""The `PreToolUse` hook of Antigravity: the shared guard scripts and the path list, on every tool call.

Antigravity runs it for each tool call (`hooks.json`, matcher `*`) with `sh -c` in the directory
of `hooks.json`, and gives it the call as JSON on stdin: `toolCall.name`, `toolCall.args` and
`workspacePaths`. It answers with one JSON object on stdout:

    {"decision": "deny", "reason": …}       a guard or the path list refuses the call
    {"decision": "force_ask", "reason": …}  a guard, or the `ask` list, asks the user
    {"decision": "ask"}                     every check passes

`ask` leaves Antigravity's own policy in force: its permission rules and its preset decide, as with
no hook. It never answers `{}`, which Antigravity reads as a deny with an empty reason.

THE CHECKS, by the name of the tool:

    every tool     the `deny` list on each argument of PATH_KEYS
    WRITE_TOOLS    then the `edit` list, whose match gives `deny`, and the `ask` list, whose match
                   gives `force_ask`, on the path that the tool writes
    run_command    the `deny` list on each word of `CommandLine`, then the five shell guards of
                   SHELL and `sandbox-semantics.py --work-tree`
    call_mcp_tool  with `ServerName` kaimon and `ToolName` ex or manage_repl: kaimon-session.py,
                   with `Arguments` as the tool input

A tool that no check names, such as `send_message`, passes as `ask`.

The scripts are the copies in hooks/ beside this file, which `harness install` writes from the
same source as Claude Code's, and each runs with this interpreter. Each gets Claude Code's payload
on stdin: `{"tool_name": "Bash", "tool_input": {"command": CommandLine}, "cwd": …}`, with the
`Cwd` of the call when it has one (a subagent's call has it, the main agent's does not), else the
first of `workspacePaths`; kaimon-session.py gets `{"tool_name": "mcp__kaimon__<ToolName>",
"tool_input": Arguments}`. A script's answer is read as Claude Code reads it: exit 2 refuses with
its stderr; exit 0 with no output passes; exit 0 with a `permissionDecision` of `deny` or `ask`
refuses or asks.

IT FAILS CLOSED. A script that is missing or cannot start, exits with another status than 0 or 2,
prints output that is not JSON, or takes longer than TIMEOUT gives `deny`; so does a payload that
this hook cannot read, a path list that is missing or holds no list of strings under `deny`, one
that holds none under `edit` or `ask` for a tool of WRITE_TOOLS, and an error of this hook
itself. When `python3` itself is missing, `sh -c` fails, and Antigravity blocks a call whose hook
fails.

THE PATH LIST is guard-paths.json beside hooks/, as `harness install` renders it: `deny` for
every tool, `edit` and `ask` for the tools that write. A path that `edit` and `ask` both match
gets `deny`. Its globs are
OpenCode's: `**` any depth, `*` and `?` within one segment; `X/**` covers X too; the match ignores
case. A path is checked as an absolute path: a leading `~`, `$HOME` or `${HOME}` expanded, a
relative path joined to the working directory of the call. A command is split into words as the
shell splits them, and each word, and each part of a word that `=`, `:` or `,` separates, is
checked as a path. It is a text check: a path that a command builds at run time passes it.
"""

import concurrent.futures
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

HOOKS = pathlib.Path(__file__).resolve().parent
LIST = HOOKS.parent / "guard-paths.json"
# The shell guards, the work-tree check of sandbox-semantics.py, and the Kaimon guard: the scripts
# of `frontends.GUARDS`, in its order.
SHELL = ("no-blind-stage.py", "no-shell-file-write.py", "gh-api-writes.py", "rm-scope.py", "git-archive-output.py")
WORK_TREE = "sandbox-semantics.py"
KAIMON = "kaimon-session.py"
KAIMON_SERVER = "kaimon"
KAIMON_TOOLS = ("ex", "manage_repl")
# The arguments that hold a path, in both tool families of Antigravity: the main agent's
# `read_file`, `write_file` and `edit_file`, and a subagent's `view_file`, `write_to_file`,
# `replace_file_content`, `grep_search`, `find_by_name` and `list_dir`; `Cwd` of `run_command`.
PATH_KEYS = ("Path", "AbsolutePath", "TargetFile", "SearchPath", "SearchDirectory", "DirectoryPath", "Cwd")
# The tools that write a file, of both families, and the argument that names the file.
WRITE_TOOLS = {"write_file": "Path", "edit_file": "Path", "write_to_file": "TargetFile",
               "replace_file_content": "TargetFile"}
# Seconds that each script may take. The scripts of one call run at once, so the call takes about as
# long; `hooks.json` gives the hook 15 s.
TIMEOUT = 10
CLOSED = "The guard hook fails closed. Tell the user, and do not run the call in another form."


def deny(reason):
    return {"decision": "deny", "reason": reason}


def rule(glob):
    """The path glob `glob` as a regular expression that ignores case, for `fullmatch`."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            c = glob[i]
            out, i = out + ("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)), i + 1
    if out.endswith("/.*"):
        out = out[:-3] + "(?:/.*)?"
    return re.compile(out, re.I)


def path_rules(key="deny"):
    """[(glob, pattern)] of the list `key` of the path list; a string, the reason to deny, when the
    list cannot be used."""
    try:
        globs = json.loads(LIST.read_text(encoding="utf-8"))[key]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return f"The path list {LIST} cannot be used ({type(e).__name__}: {e}), so the call is blocked. {CLOSED}"
    if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
        return f"The path list {LIST} holds no list of strings under \"{key}\", so the call is blocked. {CLOSED}"
    return [(g, rule(g)) for g in globs]


def absolute(raw, cwd):
    """`raw` as an absolute, normalised path: a home form expanded, a relative path joined to `cwd`."""
    home = os.path.expanduser("~")
    m = re.match(r"(?:~|\$HOME|\$\{HOME\})(?=/|$)", raw)
    path = home + raw[m.end():] if m else raw if raw.startswith("/") else os.path.join(cwd, raw)
    return re.sub(r"^/+", "/", os.path.normpath(path))


def refused_path(raw, cwd, rules, kind="deny"):
    """The reason that `rules`, the list `kind`, refuse the path `raw`, or None."""
    path = absolute(raw, cwd)
    for glob, pattern in rules:
        if pattern.fullmatch(path):
            return f"{path} matches the {kind} rule {glob}"
    return None


def words(command):
    """The words of `command` as the shell splits them, quotes removed; on a quote that does not
    close, the text between blanks and control characters."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return [w for w in re.split(r"[\s;&|()<>`'\"]+", command) if w]


def refused_command(command, cwd, rules):
    """The reason that `rules` refuse a word of `command`, or a part of one, or None."""
    for word in words(command):
        for part in dict.fromkeys([word, *re.split(r"[=:,]", word)]):
            refused = part and refused_path(part, cwd, rules)
            if refused:
                return refused
    return None


def run(script, payload, args=()):
    """('deny' | 'ask' | 'pass', reason) of the guard `script` on `payload`."""
    path = HOOKS / script
    failed = f"The guard {script} {{}}, so the call is blocked. {CLOSED}"
    if not path.is_file():
        return "deny", failed.format(f"is missing from {HOOKS}")
    try:
        p = subprocess.run([sys.executable, str(path), *args], input=payload, capture_output=True, text=True,
                           timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return "deny", failed.format(f"did not answer within {TIMEOUT} s")
    except OSError as e:
        return "deny", failed.format(f"could not start ({e.strerror or e})")
    if p.returncode == 2:
        return "deny", p.stderr.strip() or f"{script} refused the call."
    if p.returncode != 0:
        return "deny", failed.format(f"exited with status {p.returncode}: {p.stderr.strip()[-300:]}")
    if not p.stdout.strip():
        return "pass", None
    try:
        hook = json.loads(p.stdout)["hookSpecificOutput"]
        decision, reason = hook.get("permissionDecision"), hook.get("permissionDecisionReason")
    except (ValueError, KeyError, TypeError, AttributeError):
        return "deny", failed.format("printed output that is not a JSON answer")
    if decision in ("deny", "ask"):
        return decision, reason or f"{script} answered {decision}."
    return "pass", None


def guards(runs):
    """The answer of the guard runs `runs`, [(script, payload, args)], which run at once: the first
    deny, else the first ask as `force_ask`, else `ask`."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(runs)) as pool:
        verdicts = list(pool.map(lambda r: run(*r), runs))
    for wanted, decision in (("deny", "deny"), ("ask", "force_ask")):
        for verdict, reason in verdicts:
            if verdict == wanted:
                return {"decision": decision, "reason": reason}
    return {"decision": "ask"}


def answer(payload):
    """The answer to the Antigravity hook payload `payload`, parsed."""
    call = payload["toolCall"]
    name, args = call["name"], call.get("args", {})
    if not isinstance(name, str) or not isinstance(args, dict):
        return deny(f"The tool call is not one that the guard hook can read, so it is blocked. {CLOSED}")
    workspaces = payload.get("workspacePaths") or []
    cwd = args["Cwd"] if isinstance(args.get("Cwd"), str) else workspaces[0] if workspaces else os.getcwd()
    rules = path_rules()
    if isinstance(rules, str):
        return deny(rules)
    for key in PATH_KEYS:
        if isinstance(args.get(key), str):
            refused = refused_path(args[key], cwd, rules)
            if refused:
                return deny(f"Refused by the path guard: {refused}. Use only the paths your task names. "
                            "Do not reach this path in another form.")
    if name in WRITE_TOOLS:
        edit, ask = path_rules("edit"), path_rules("ask")
        for rules_of in (edit, ask):
            if isinstance(rules_of, str):
                return deny(rules_of)
        target = args.get(WRITE_TOOLS[name])
        if isinstance(target, str):
            refused = refused_path(target, cwd, edit, "edit")
            if refused:
                return deny(f"Refused by the path guard: {refused}. Do not make the change in another form.")
            asked = refused_path(target, cwd, ask, "ask")
            if asked:
                return {"decision": "force_ask", "reason": f"The path guard asks the user: {asked}."}
    if name == "run_command":
        command = args.get("CommandLine")
        if not isinstance(command, str):
            return deny(f"The run_command call holds no CommandLine, so the guards cannot check it. {CLOSED}")
        refused = refused_command(command, cwd, rules)
        if refused:
            return deny(f"Refused by the path guard: {refused}. Use only the paths your task names. "
                        "Do not reach this path in another form.")
        shell = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})
        return guards([*((s, shell, ()) for s in SHELL), (WORK_TREE, shell, ("--work-tree",))])
    if name == "call_mcp_tool" and args.get("ServerName") == KAIMON_SERVER and args.get("ToolName") in KAIMON_TOOLS:
        arguments = args.get("Arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        kaimon = json.dumps({"tool_name": f"mcp__kaimon__{args['ToolName']}", "tool_input": arguments})
        return guards([(KAIMON, kaimon, ())])
    return {"decision": "ask"}


def main():
    try:
        result = answer(json.loads(sys.stdin.read()))
    except Exception as e:  # any failure of this hook blocks the call
        result = deny(f"The guard hook failed ({type(e).__name__}: {e}), so the call is blocked. {CLOSED}")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
