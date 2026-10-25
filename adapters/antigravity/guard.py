#!/usr/bin/env python3
"""The `PreToolUse` hook of Antigravity: the shared guard scripts and the path list, on every tool call.

Antigravity runs it for each tool call (`hooks.json`, matcher `*`) with `sh -c`, by the absolute
path that `hooks.json` names, and gives it the call as JSON on stdin: `toolCall.name`,
`toolCall.args` and `workspacePaths`. It answers with one JSON object on stdout:

    {"decision": "deny", "reason": …}       a guard, the path list or a Bash deny refuses the call
    {"decision": "force_ask", "reason": …}  a guard, the `ask` list or a Bash ask asks the user
    {"decision": "ask"}                     every check passes

`ask` leaves Antigravity's own policy in force: its permission rules and its preset decide, as with
no hook. It never answers `{}`, which Antigravity reads as a deny with an empty reason.

A `run_command` that it does not deny also gets `"overwrite": {"BypassSandbox": …}`, which replaces
that argument of the call: true only when Claude Code would run the command outside its sandbox, by
the rule `top_level` of the sandbox-semantics.py beside this file (every part led by git, gh, glab
or ps, and no file redirected), and none of the guard's screens applies (`lifted`), else false. So
the guard, not the agent, decides the sandbox of a command, as Claude Code's
`sandbox.excludedCommands` does, and an agent's own `BypassSandbox` on any other command is
dropped. A deny, and a call of any other tool, carries no `overwrite`.

THE CHECKS, by the name of the tool:

    every tool     the `deny` list on each argument of PATH_KEYS
    WRITE_TOOLS    then the `edit` list, whose match gives `deny`, and the `ask` list, whose match
                   gives `force_ask`, on the path that the tool writes
    run_command    the `deny` list on each word of `CommandLine`; then the template's Bash rules,
                   `bash_deny` and `bash_ask`, on each segment of it (segments), where a deny
                   refuses at once and an ask gives `force_ask` unless a guard refuses; then the
                   five shell guards of SHELL and `sandbox-semantics.py --work-tree`
    call_mcp_tool  with `ServerName` kaimon and `ToolName` ex or manage_repl: kaimon-session.py,
                   with `Arguments` as the tool input; `Arguments` that are not a JSON object
                   give `deny`

A tool that no check names, such as `send_message`, passes as `ask`.

The scripts are the copies in hooks/ beside this file, which `harness install` writes from the
same source as Claude Code's, and each runs with this interpreter. Each gets Claude Code's payload
on stdin: `{"tool_name": "Bash", "tool_input": {"command": CommandLine}, "cwd": …}`, with the
`Cwd` of the call when it has one (a subagent's call has it, the main agent's does not), its home
form expanded and resolved against the first of `workspacePaths`, else that first path;
kaimon-session.py gets `{"tool_name": "mcp__kaimon__<ToolName>", "tool_input": Arguments}`. A
script's answer is read as Claude Code reads it: exit 2 refuses with its stderr; exit 0 with no
output passes; exit 0 with a `permissionDecision` of `deny` or `ask` refuses or asks.

IT FAILS CLOSED. A script that is missing or cannot start, exits with another status than 0 or 2,
prints output that is not JSON, or takes longer than TIMEOUT gives `deny`; so does a payload that
this hook cannot read, a path list that is missing or holds no list of strings under `deny`, one
that holds none under `edit` or `ask` for a tool of WRITE_TOOLS, none under `bash_deny` or
`bash_ask` for `run_command`, and an error of this hook itself. When `python3` itself is missing,
`sh -c` fails, and Antigravity blocks a call whose hook fails.

THE PATH LIST is guard-paths.json beside hooks/, as `harness install` renders it: `deny` for
every tool, `edit` and `ask` for the tools that write, `bash_deny` and `bash_ask` for
`run_command`. A path that `edit` and `ask` both match gets `deny`. Its globs are
OpenCode's: `**` any depth, `*` and `?` within one segment; `X/**` covers X too; the match ignores
case. A path is checked as an absolute path: a leading `~`, `~user`, `$HOME` or `${HOME}` expanded,
a relative path joined to the working directory of the call. A command is split into words as the
shell splits them, and each word, and each part of a word that `=`, `:` or `,` separates, is
checked as a path. A path with a glob character, GLOB, is checked as it is and again cut to its
directory before that character. That cut path is wide, and so is every word of a command that
RECURSIVE matches, the word after `cd` or `pushd`, and the arguments of WIDE_KEYS: a wide path is
refused when it holds the literal prefix of an absolute `deny` glob (literal_prefix), as
OpenCode's guard refuses it. It is a text check: a path that a command builds at run time passes
it.
"""

import concurrent.futures
import importlib.util
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
# The arguments whose path the call reads below, as a `cd` or a recursive read does.
WIDE_KEYS = ("Cwd", "SearchPath")
# A command that reads below its paths: OpenCode's guard's `RECURSIVE`.
RECURSIVE = re.compile(r"\b(?:find|rg|tree|du|tar|zip|rsync|walkdir|readdir)\b"
                       r"|\b(?:grep|egrep|ls|cp|chmod|chown)\b[^|;&\n]*\s(?:--recursive\b|-[A-Za-z]*[rR])")
# The characters of a shell glob or a brace expansion.
GLOB = re.compile(r"[*?\[{]")
# The text between two words of a segment when a Bash rule matches them: a NUL, which no argument
# of a command can hold, so that a blank inside a quoted word is no boundary.
WORD_BREAK = "\0"
# Seconds that each script may take. The scripts of one call run at once, so the call takes about as
# long; `hooks.json` gives the hook 15 s.
TIMEOUT = 10
# A command line whose reading is the same in sh, bash and zsh: commands joined by `&&`, `||`, `;`
# or `|`, each of words separated by blanks. A word is `2>&1`, or pieces: a character of the set
# below, a single-quoted text with no `'`, or a double-quoted text with none of `"`, `$`, the
# backtick, `\` and `!`. No piece holds a NUL or a character outside ASCII.
WORD = r"""(?:2>&1|(?:[A-Za-z0-9_./:@%+,=~^-]|'[^'\x00\x80-\U0010ffff]*'|"[^"$`\\!\x00\x80-\U0010ffff]*")+)"""
COMMAND = rf"{WORD}(?:[ \t]+{WORD})*"
PLAIN = re.compile(rf"[ \t]*{COMMAND}(?:[ \t]*(?:&&|\|\||;|\|)[ \t]*{COMMAND})*[ \t]*")
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


def listed(key):
    """The list `key` of the path list, a list of strings; a string, the reason to deny, when the
    list cannot be used."""
    try:
        items = json.loads(LIST.read_text(encoding="utf-8"))[key]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return f"The path list {LIST} cannot be used ({type(e).__name__}: {e}), so the call is blocked. {CLOSED}"
    if not isinstance(items, list) or not all(isinstance(g, str) for g in items):
        return f"The path list {LIST} holds no list of strings under \"{key}\", so the call is blocked. {CLOSED}"
    return items


def literal_prefix(glob):
    """The part of `glob` that names one directory or file: up to the last `/` before its first
    `*` or `?`, or the whole glob."""
    g = re.search(r"[*?]", glob)
    return glob if g is None else glob[:max(glob.rfind("/", 0, g.start()), 0)]


def path_rules(key="deny"):
    """[(glob, pattern, literal prefix)] of the list `key` of the path list; a string, the reason to
    deny, when the list cannot be used."""
    globs = listed(key)
    return globs if isinstance(globs, str) else [(g, rule(g), literal_prefix(g)) for g in globs]


def expanded(raw):
    """`raw` with a leading `~`, `~user`, `$HOME` or `${HOME}` expanded as the shell expands it."""
    m = re.match(r"(?:\$HOME|\$\{HOME\})(?=/|$)", raw)
    return os.path.expanduser("~") + raw[m.end():] if m else os.path.expanduser(raw)


def absolute(raw, cwd):
    """`raw` as an absolute, normalised path: a home form expanded, a relative path joined to `cwd`."""
    return re.sub(r"^/+", "/", os.path.normpath(os.path.join(cwd, expanded(raw))))


def refused_path(raw, cwd, rules, kind="deny", wide=False):
    """The reason that `rules`, the list `kind`, refuse the path `raw`, or None. A path with a glob
    character is checked as it is, and again cut to its directory before the first glob character,
    which is wide. A wide path, one that the call reads below, is refused when it holds the literal
    prefix of an absolute rule."""
    raw = expanded(raw)
    paths = [(absolute(raw, cwd), wide)]
    if g := GLOB.search(raw):
        cut = raw.rfind("/", 0, g.start())
        paths.append((absolute(raw[:cut] or "/" if cut >= 0 else ".", cwd), True))
    for path, wide in paths:
        under = "/" if path == "/" else path.lower() + "/"
        for glob, pattern, prefix in rules:
            if pattern.fullmatch(path):
                return f"{path} matches the {kind} rule {glob}"
            if wide and prefix.lower().startswith(under):
                return f"the call reads below {path}, which holds {prefix}, which the {kind} rule {glob} covers"
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
    """The reason that `rules` refuse a word of `command`, or a part of one, or None. Every word is
    wide in a command that RECURSIVE matches, and the word after `cd` or `pushd` is."""
    recursive = RECURSIVE.search(command) is not None
    split = words(command)
    for i, word in enumerate(split):
        wide = recursive or split[i - 1:i] in (["cd"], ["pushd"])
        for part in dict.fromkeys([word, *re.split(r"[=:,]", word)]):
            refused = part and refused_path(part, cwd, rules, wide=wide)
            if refused:
                return refused
    return None


def segments(line):
    """The segments of the command line `line`, as Claude Code checks a Bash rule on them: the line
    split at `;`, `&&`, `||`, `|`, `&` and a newline outside quotes, and the body of each `$(…)`,
    backtick and `( … )` a segment of its own, split the same way; a backslash-newline outside
    single quotes dropped; each stripped, none empty."""
    found = []

    def scan(i, close):
        """Scan `line` from `i` to the `close` of this level; the index after it."""
        seg, quoted = "", False
        while i < len(line):
            c = line[i]
            if c == "\\":  # a backslash-newline joins two lines, as in the shell
                seg, i = seg + ("" if line.startswith("\n", i + 1) else line[i:i + 2]), i + 2
            elif c == "'" and not quoted:
                j = line.find("'", i + 1)
                j = len(line) if j < 0 else j + 1
                seg, i = seg + line[i:j], j
            elif c == close and not quoted:
                found.append(seg)
                return i + 1
            elif line.startswith("$(", i) or c == "`" or c == "(" and not quoted:
                j = scan(i + (2 if c == "$" else 1), "`" if c == "`" else ")")
                seg, i = seg + line[i:j], j
            elif c == '"':
                seg, quoted, i = seg + c, not quoted, i + 1
            elif not quoted and c in ";|&\n":  # `&&` and `||` leave an empty segment, which is dropped
                found.append(seg)
                seg, i = "", i + 1
            else:
                seg, i = seg + c, i + 1
        found.append(seg)
        return i

    scan(0, None)
    return [s.strip() for s in found if s.strip()]


def bash_rules(key):
    """[(body, bash_matcher(body))] of the Bash bodies under `key` of the path list; a string, the
    reason to deny, when the list cannot be used."""
    bodies = listed(key)
    return bodies if isinstance(bodies, str) else [(body, bash_matcher(body)) for body in bodies]


def bash_matcher(body):
    """`matches(words, text)`: whether `Bash(body)` matches a segment with the words `words`
    (segment_words), `text` being those words joined by WORD_BREAK, from any of its words, so that
    an assignment, a wrapper such as `env` or a keyword such as `then` before the command does not
    hide it: `Bash(x *)` when the words of `x` are a run of `words`, any other body when it matches
    the words from one of them to the last, with `*` as any text and a trailing ` *` as no text
    too. A blank of the body matches only the boundary between two words, so that a quoted word
    such as the message of `git commit -m "git push --force"` matches no rule. The cost is linear
    in the length of `text`."""
    if m := re.fullmatch(r"([^*]*[^*\s]) \*", body, re.S):
        x = m.group(1).split()
        return lambda w, text: any(w[i:i + len(x)] == x for i in range(len(w)))
    trailing = body.endswith(" *")
    parts = [WORD_BREAK.join(re.split(r"\s+", part)) for part in (body[:-2] if trailing else body).split("*")]
    return lambda w, text: placed(parts, trailing, text)


def placed(parts, trailing, text):
    """Whether the literal parts `parts` of a Bash body, with a `*` between each two, match `text`
    from one of its word starts to its end: the first part at a word start (the start of `text`, or
    just after a WORD_BREAK), each later part after the one before it, and the last part at the end
    of `text`, or, when the body has a `trailing` ` *`, also before a WORD_BREAK. Each part takes
    the earliest place that it can: a `*` matches any text, so an earlier place leaves the later
    parts all the text that a later place leaves them, and one `str.find` for each part decides."""
    if len(parts) == 1:
        if trailing:
            return (WORD_BREAK + text + WORD_BREAK).find(WORD_BREAK + parts[0] + WORD_BREAK) >= 0
        return (WORD_BREAK + text).endswith(WORD_BREAK + parts[0])
    first, *middle, last = parts
    at = (WORD_BREAK + text).find(WORD_BREAK + first)
    if at < 0:
        return False
    at += len(first)
    for part in middle:
        at = text.find(part, at)
        if at < 0:
            return False
        at += len(part)
    if text.endswith(last) and len(text) - len(last) >= at:
        return True
    return trailing and text.find(last + WORD_BREAK, at) >= 0


def segment_words(segment):
    """The words of `segment` as the shell splits them, quotes removed; on a quote that does not
    close, the text between blanks."""
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def matched(rules, parts):
    """The body of the first of `rules` that matches a segment of `parts`, or None."""
    split = [(w, WORD_BREAK.join(w)) for w in map(segment_words, parts)]
    return next((body for body, matches in rules for w, text in split if matches(w, text)), None)


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


def lifted(command, cwd):
    """Whether `command`, run in `cwd`, runs outside the sandbox: only when `top_level` of the
    sandbox-semantics.py beside this file, Claude Code's rule for `sandbox.excludedCommands`, finds
    no reason to keep it inside, and none of the guard's screens applies. A command that it cannot
    parse stays inside.

    The first screen lifts only text whose reading is certain in sh, bash and zsh: the whole line
    matches PLAIN, else it stays inside. So no quote, expansion or glob that the rule's shlex reads
    in another way than a shell can hide a program from the rule.

    The other screens keep inside a command that the rule lifts but whose program is not the one
    it reads: a `#`, which shlex reads as a comment up to the end of the line, so a next line joins
    the part before it; a NUL, which no shell runs and `os.path.realpath` refuses; a part that
    `exposed` or `path_screened` refuses; an assignment or a path in front of a program; and a git
    option before the subcommand that takes a value, `-C` aside, or `--config-env`, which can name
    a program to run or another repository."""
    sys.dont_write_bytecode = True  # no __pycache__ in the installed hooks/
    spec = importlib.util.spec_from_file_location("sandbox_semantics", HOOKS / WORK_TREE)
    semantics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(semantics)
    if PLAIN.fullmatch(command) is None:
        return False
    if "#" in command or "\0" in command:
        return False
    classified = semantics.top_level(command, cwd)
    if classified is None or classified[1] is not None:
        return False
    heads = classified[0]
    if semantics.exposed(command, cwd) is not None or semantics.path_screened(heads) is not None:
        return False
    for tokens in semantics.parts(command)[0]:
        head, arguments = semantics.part_head(tokens)
        if tokens[0] != head and not semantics.into_cwd(head, arguments, cwd):
            return False
    valued = (semantics.TAKES_VALUE - {"-C"}) | {"--config-env"}
    for head, arguments in heads:
        index = 0
        while head == "git" and index < len(arguments) and arguments[index].startswith("-"):
            option = arguments[index]
            if option in valued or option.startswith(tuple(name + "=" for name in valued)):
                return False
            index += 2 if option in semantics.TAKES_VALUE else 1
    return True


def answer(payload):
    """The answer to the Antigravity hook payload `payload`, parsed."""
    call = payload["toolCall"]
    name, args = call["name"], call.get("args", {})
    if not isinstance(name, str) or not isinstance(args, dict):
        return deny(f"The tool call is not one that the guard hook can read, so it is blocked. {CLOSED}")
    workspaces = payload.get("workspacePaths") or []
    workspace = workspaces[0] if workspaces else os.getcwd()
    cwd = os.path.normpath(os.path.join(workspace, expanded(args["Cwd"]))) if isinstance(args.get("Cwd"), str) \
        else workspace
    rules = path_rules()
    if isinstance(rules, str):
        return deny(rules)
    for key in PATH_KEYS:
        if isinstance(args.get(key), str):
            # `cwd` is `Cwd` resolved already, and joining `Cwd` to it again would name another path.
            refused = refused_path(cwd if key == "Cwd" else args[key], cwd, rules, wide=key in WIDE_KEYS)
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
        bash = {key: bash_rules(key) for key in ("bash_deny", "bash_ask")}
        for rules_of in bash.values():
            if isinstance(rules_of, str):
                return deny(rules_of)
        parts = segments(command)
        hit = matched(bash["bash_deny"], parts)
        if hit is not None:
            return deny(f"Refused by the settings template's rule Bash({hit}). Do not run the command in another "
                        "form.")
        asked = matched(bash["bash_ask"], parts)
        shell = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})
        result = guards([*((s, shell, ()) for s in SHELL), (WORK_TREE, shell, ("--work-tree",))])
        if result["decision"] == "deny":
            return result
        if asked is not None:
            result = {"decision": "force_ask", "reason": f"The settings template's rule Bash({asked}) asks the user."}
        return {**result, "overwrite": {"BypassSandbox": lifted(command, cwd)}}
    if name == "call_mcp_tool" and args.get("ServerName") == KAIMON_SERVER and args.get("ToolName") in KAIMON_TOOLS:
        arguments = args.get("Arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict):
            return deny(f"The Kaimon call holds no object of Arguments, so the Kaimon guard cannot check it. {CLOSED}")
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
