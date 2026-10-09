#!/usr/bin/env python3
"""Refuse a shell command that writes a file inside a git working tree.

A `PreToolUse` hook on the `Bash` matcher. It reads the tool call on stdin, parses the
command, and exits 2 when a segment would write a file that belongs to the internal edit
tools. Exit 2 refuses the call and shows this script's stderr to the model.

It exists for the half of the global `CLAUDE.md` rule *Never edit files through the
shell* that a `permissions.deny` glob cannot express:

  * a **redirection** — `>`, `>>`, `>|`, `&>`, `>&` — which can follow any command at all,
    so no pattern on the leading word can see it; and `tee`, which writes without one;
  * an **in-place flag cluster** — `sed -Ei`, `perl -ni` — which is the `git add -nA`
    shape: a glob wide enough to catch the cluster also catches innocent flags;
  * a **Python one-off** — `python3 -c`, `python3 - <<'EOF'` — whose code calls `open(p, 'w')`
    or `Path(p).write_text` on a path it can read: a literal, or a name bound once to one.

The command is read with its quotes, so a quoted `>` is text and never a redirection:
`grep 'a > b'`, `julia -e 'x -> x > 1'` and `git commit -m "a > b"` pass. A heredoc body is
cut out before the command is read, so its lines are not segments.

A **target** is resolved against the hook's `cwd`, every `cd` before it in the command, and
a leading variable that an earlier segment set on its own (`S=/x; cd $S`). A scratch root
passes first, whatever is below it: `$TMPDIR`, `/tmp/`, `/private/tmp/`, `/var/folders/`,
`/dev/`, and `~/Research/.scratch/`. Then:

  * **in a git working tree** — a `.git` at or above it — every file is refused, whatever
    its suffix, unless `git check-ignore` says git ignores it: a log under `runs/` passes;
  * **outside one** — `Talks/`, `Notes/`, and the files of the bare meta repository — a file
    with a source suffix is refused, and so is a relative one whose directory is unknown.

A `>&2`-style duplication writes no file. An in-place edit passes when its last operand is
under a scratch root.

The suffix spellings `sed -i.bak` and `perl -i.bak` are glob-closable and belong in the
deny list. This hook does not depend on them being there.

**It fails open.** Any input it does not understand exits 0. Out of its reach:

  * a computed target — `> $OUT`, `open(f"{d}/x.jl", 'w')`, a name bound twice or in a loop;
  * a **Julia** one-off — `julia -e 'write("f.jl", s)'`. Python is parsed with `ast`; Julia
    has no parser here, and a pattern over the code would read strings and comments;
  * any other writer inside a string argument: `perl -e`, `node -e`, `shutil.copy`, a
    heredoc body fed to `bash`. These stay a prose rule;
  * a `cd` inside a subshell is taken to persist after the `)`.

Test it without installing:

    echo '{"tool_input":{"command":"echo x > src/Foo.jl"},"cwd":"/path/in/a/repo"}' | ./no-shell-file-write.py
"""

import json
import os
import re
import sys

# `ast` and `subprocess` are imported where they are used: at module level they add about
# 6 ms to every Bash call, and only a Python one-off or a refusal needs them.

# The fallback split, for text whose quotes do not balance. `harness settings` splits
# on the same set.
SEGMENT = re.compile(r"(?:&&|\|\||;|\||\n)")

# Characters that make an operator when they are not quoted.
OPERATOR = set(";&|<>()\n")

# The redirection at the end of an operator run, and what comes before it is a separator:
# `)>` closes a subshell and redirects it. `<` forms read, and are kept only to find the
# heredoc placeholder and to skip their target.
REDIRECT = re.compile(r"(&>>?|>>?[|&]?|<<<|<<-?|<>|<&?)$")

# `<<'EOF'`, `<<-EOF`, `<< "EOF"`; not `<<<`, a here-string.
HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
PLACEHOLDER = "__heredoc_{}__"

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# The file kinds this tree edits with Read/Edit/Write: the rule outside a git working
# tree, and for a relative target whose directory is unknown.
SOURCE_SUFFIXES = (
    ".jl", ".md", ".toml", ".tex", ".bib", ".sty", ".cls",
    ".yml", ".yaml", ".json", ".py", ".sh", ".ipynb",
)

HOME = os.path.expanduser("~")

# Writing under a scratch root is not editing the tree. `$TMPDIR/x` is recognised as the
# literal text it is. `~/Research/.scratch/` holds probe scripts and environments and no
# checkout, so it is a scratch root in each spelling, and a probe `git init` below it
# does not make it a work tree.
SCRATCH_PREFIXES = (
    "$TMPDIR", "${TMPDIR}", "/tmp/", "/private/tmp/", "/var/folders/", "/dev/",
    "~/Research/.scratch/", "$HOME/Research/.scratch/", "${HOME}/Research/.scratch/",
    HOME + "/Research/.scratch/", (os.environ.get("TMPDIR") or "/tmp").rstrip("/") + "/",
)

# In-place editing is a flag on these, and the flag is what this hook reads.
INPLACE_TOOLS = {"sed", "gsed", "perl", "awk", "gawk"}

# Letters that consume the rest of their cluster as an argument. `perl -Ilib` holds an
# `i` that is not the in-place flag, and stopping at `I` is what keeps it from refusing.
TAKES_ATTACHED = {
    "sed": set("efl"),
    "gsed": set("efl"),
    "perl": set("IeEMmFD"),
    "awk": set("fvF"),
    "gawk": set("fvF"),
}

PYTHON = re.compile(r"^python(3(\.[0-9]+)?)?$")

MESSAGE = """Refused: {segment}

`{detail}` writes a file in a git working tree through the shell. A shell rewrite reports
success whether or not it matched anything, and BSD `sed` differs from GNU in ways that
corrupt silently on macOS.

Use the internal edit tools instead:

    Edit    one file, one region
    Write   a new file, or a full replacement you have read first

For a mechanical change over many files, use Kaimon's `rename_symbol` or `edit_code`:
both abort the whole batch untouched on one failure and return the diff.

A scratch file is not this rule: write it under `$TMPDIR` or `~/Research/.scratch/` and it
passes. A log redirect there, `> ~/Research/.scratch/<task>/run.log 2>&1`, passes too.
"""


def cut_heredocs(command):
    """Return the command with each heredoc body removed, and the bodies in order."""
    kept, bodies, pending = [], [], []
    for line in command.split("\n"):
        if pending:
            tabs, delimiter = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            else:
                bodies[len(bodies) - len(pending)].append(line)
            continue

        def mark(match):
            pending.append((match.group(1) == "-", match.group(3)))
            bodies.append([])
            return "<< " + PLACEHOLDER.format(len(bodies) - 1)

        kept.append(HEREDOC.sub(mark, line))
    return "\n".join(kept), ["\n".join(body) for body in bodies]


def lex(text):
    """Return the text as ("word", w) and ("op", o) tokens, or None if a quote is open.

    A quoted character is never an operator. Inside double quotes a backslash escapes
    only `$`, a backtick, `"`, `\\` and a newline, as in the shell.
    """
    tokens, word, in_word = [], [], False
    index, length = 0, len(text)

    def finish():
        nonlocal word, in_word
        if in_word:
            tokens.append(("word", "".join(word)))
        word, in_word = [], False

    while index < length:
        char = text[index]
        if char == "'":
            end = text.find("'", index + 1)
            if end < 0:
                return None
            word.append(text[index + 1:end])
            in_word, index = True, end + 1
        elif char == '"':
            index += 1
            while index < length and text[index] != '"':
                if text[index] == "\\" and index + 1 < length and text[index + 1] in '$`"\\\n':
                    index += 1
                word.append(text[index])
                index += 1
            if index >= length:
                return None
            in_word, index = True, index + 1
        elif char == "\\":
            if index + 1 < length and text[index + 1] != "\n":
                word.append(text[index + 1])
                in_word = True
            index += 2
        elif char in " \t\r":
            finish()
            index += 1
        elif char == "#" and not in_word:
            end = text.find("\n", index)
            index = length if end < 0 else end
        elif char in OPERATOR:
            # `2>` names a file descriptor, not a word of the command.
            if char in "<>" and in_word and "".join(word).isdigit():
                word, in_word = [], False
            finish()
            end = index
            while end < length and text[end] in OPERATOR:
                end += 1
            tokens.append(("op", text[index:end]))
            index = end
        else:
            word.append(char)
            in_word, index = True, index + 1
    finish()
    return tokens


def split(tokens, placeholders):
    """Group tokens into segments: (words, write targets, heredoc body indices)."""
    segments, words, writes, docs = [], [], [], []
    index = 0
    while index < len(tokens):
        kind, text = tokens[index]
        index += 1
        if kind == "word":
            words.append(text)
            continue
        match = REDIRECT.search(text)
        separator = text[: match.start()] if match else text
        if separator:
            segments.append((words, writes, docs))
            words, writes, docs = [], [], []
        if not match:
            continue
        operator = match.group(1)
        target = None
        if index < len(tokens) and tokens[index][0] == "word":
            target = tokens[index][1]
            index += 1
        if target is None:
            continue
        if operator.startswith("<"):
            if target in placeholders:
                docs.append(placeholders[target])
        elif operator.endswith("&") and (target.isdigit() or target == "-"):
            continue
        else:
            writes.append(target)
    segments.append((words, writes, docs))
    return [segment for segment in segments if any(segment)]


LEADING_VARIABLE = re.compile(r"^\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def expand(path, variables):
    """Expand a leading `~` or a leading variable the command set; None when anything is
    left that the shell computes."""
    if path == "~" or path.startswith("~/"):
        path = HOME + path[1:]
    match = LEADING_VARIABLE.match(path)
    if match and variables.get(match.group(1) or match.group(2)) is not None:
        path = variables[match.group(1) or match.group(2)] + path[match.end():]
    if any(char in path for char in "$*?`"):
        return None
    return path


def in_work_tree(path):
    """True when a `.git` lies at or above the directory of the path."""
    directory = os.path.dirname(path)
    while True:
        if os.path.exists(os.path.join(directory, ".git")):
            return True
        parent = os.path.dirname(directory)
        if parent == directory:
            return False
        directory = parent


def ignored(path):
    """True when git ignores the path: a log under `runs/`, not a source file."""
    import subprocess

    directory = os.path.dirname(path)
    while not os.path.isdir(directory):
        directory = os.path.dirname(directory)
    try:
        result = subprocess.run(["git", "-C", directory, "check-ignore", "-q", path],
                                capture_output=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def tree_write(target, cwd, variables):
    """True when writing the target writes a file inside a git working tree."""
    if not target or target.startswith(SCRATCH_PREFIXES):
        return False
    path = expand(target, variables)
    if path is None:
        return False
    if not os.path.isabs(path):
        if cwd is None:
            return path.lower().endswith(SOURCE_SUFFIXES)
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    if (path + "/").startswith(SCRATCH_PREFIXES):
        return False
    if in_work_tree(path):
        return not ignored(path)
    return path.lower().endswith(SOURCE_SUFFIXES)


def scratch_file(target, cwd, variables):
    """True when the target is known to lie under a scratch root."""
    if target.startswith(SCRATCH_PREFIXES):
        return True
    path = expand(target, variables)
    if path is None or (not os.path.isabs(path) and cwd is None):
        return False
    return (os.path.normpath(os.path.join(cwd or "/", path)) + "/").startswith(SCRATCH_PREFIXES)


def change_directory(words, cwd, variables):
    """Return the directory after `cd`, or None when it cannot be known."""
    if len(words) < 2:
        return HOME
    target = expand(words[1], variables)
    if target is None or target == "-":
        return None
    if not os.path.isabs(target):
        if cwd is None:
            return None
        target = os.path.join(cwd, target)
    return os.path.normpath(target)


def inplace(tool, tokens):
    """Return the in-place flag among the leading options, or None."""
    attached = TAKES_ATTACHED[tool]
    for token in tokens:
        if not token.startswith("-") or token == "-":
            return None
        if token.startswith("--"):
            if token.startswith("--in-place"):
                return token
            continue
        for letter in token[1:]:
            if letter == "i":
                return token
            if letter in attached:
                break
    return None


def python_code(words, bodies):
    """Return the code a `python3` segment runs from its command line, or None."""
    if "-c" in words:
        index = words.index("-c")
        return words[index + 1] if index + 1 < len(words) else None
    scripts = [word for word in words[1:] if not word.startswith("-")]
    if bodies and not scripts:
        return bodies[0]
    return None


def python_writes(code):
    """Return (path, detail) for each file the code opens for writing by a readable path."""
    import ast

    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return []
    bound, seen = {}, set()
    for node in ast.walk(tree):
        for target in getattr(node, "targets", None) or [getattr(node, "target", None)]:
            if not isinstance(target, ast.Name):
                continue
            value = getattr(node, "value", None)
            if target.id in seen or not isinstance(node, ast.Assign):
                bound.pop(target.id, None)
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                bound[target.id] = value.value
            seen.add(target.id)

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return bound.get(node.id)
        return None

    def name(node):
        return getattr(node, "id", None) or getattr(node, "attr", None)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if name(node.func) == "open" and node.args:
            mode = node.args[1] if len(node.args) > 1 else next(
                (keyword.value for keyword in node.keywords if keyword.arg == "mode"), None)
            mode = literal(mode) if mode is not None else "r"
            path = literal(node.args[0])
            if path and mode and set(mode) & set("wax+"):
                found.append((path, f"open({path!r}, {mode!r})"))
        elif (name(node.func) in ("write_text", "write_bytes")
              and isinstance(node.func, ast.Attribute)
              and isinstance(node.func.value, ast.Call)
              and name(node.func.value.func) == "Path"
              and node.func.value.args):
            path = literal(node.func.value.args[0])
            if path:
                found.append((path, f"Path({path!r}).{node.func.attr}"))
    return found


def offence(words, writes, bodies, cwd, variables):
    """Return the text that makes this segment a shell file write, or None."""
    for target in writes:
        if tree_write(target, cwd, variables):
            return "> " + target
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words:
        return None
    head = words[0].rsplit("/", 1)[-1]
    if head in INPLACE_TOOLS:
        flag = inplace(head, words[1:])
        if flag and not scratch_file(words[-1], cwd, variables):
            return flag
    if head == "tee":
        for word in words[1:]:
            if not word.startswith("-") and tree_write(word, cwd, variables):
                return "tee " + word
    if PYTHON.match(head):
        code = python_code(words, bodies)
        for path, detail in python_writes(code) if code else []:
            if tree_write(path, cwd, {}):
                return detail
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
    except Exception:
        return 0
    if not isinstance(command, str):
        return 0
    # A cheap reject for the commands this hook can never refuse. `-i` is not the test:
    # `sed -Ei` holds no `-i` substring, which is the whole reason the cluster case needs
    # a parser.
    if not (">" in command or "tee" in command or "python" in command
            or any(t in command for t in INPLACE_TOOLS)):
        return 0
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        cwd = os.getcwd()

    text, bodies = cut_heredocs(command)
    placeholders = {PLACEHOLDER.format(i): i for i in range(len(bodies))}
    tokens = lex(text)
    if tokens is not None:
        segments = split(tokens, placeholders)
    else:
        segments = []
        for raw in SEGMENT.split(text):
            part = lex(raw)
            if part is not None:
                segments.extend(split(part, placeholders))

    # A variable set by a segment of its own persists; `$TMPDIR` is a scratch root.
    variables = {"HOME": HOME, "TMPDIR": os.environ.get("TMPDIR") or "/tmp"}
    for words, writes, docs in segments:
        detail = offence(words, writes, [bodies[i] for i in docs], cwd, variables)
        if detail:
            segment = " ".join(words + [">" + target for target in writes])
            sys.stderr.write(MESSAGE.format(segment=segment, detail=detail))
            return 2
        if words and words[0] == "cd":
            cwd = change_directory(words, cwd, variables)
        elif words and all(ASSIGNMENT.match(word) for word in words):
            for word in words:
                name, value = word.split("=", 1)
                variables[name] = expand(value, variables)
    return 0


if __name__ == "__main__":
    sys.exit(main())
