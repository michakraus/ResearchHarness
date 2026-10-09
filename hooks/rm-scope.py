#!/usr/bin/env python3
"""Refuse a recursive `rm` outside the scratch zones, and ask for a `git rm` outside a worktree.

A `PreToolUse` hook on the `Bash` matcher. It reads the tool call on stdin, follows the
working directory through each `cd` in the command, and resolves every operand.

  * **`rm`** — exit 0, no output, when every operand lies strictly below a worktree,
    `~/Research/.worktrees/<name>/`, or strictly below `~/Research/.scratch/`. Exit 2 for a
    **recursive** `rm` of any other path under `/Users`, or of `/` or `/Users` themselves:
    a worktree root, `.worktrees`, `.scratch`, a package checkout, `~/.julia`. A worktree
    goes through `git worktree remove`. A plain `rm` outside the zones, and an operand the
    hook cannot resolve — a variable other than `$HOME`, a command substitution — get no
    decision: the sandbox and the rules decide, as they do without the hook.
  * **`git rm`** — no output when the working directory lies in a worktree and no
    `-f`/`--force` is given. Else "ask". Without `-f`, `git rm` refuses a file with local
    changes, so what it removes is recoverable from `HEAD`.

No `permissions` rule can state this. The matcher expands no `~`, cannot see the working
directory, and its `*` crosses `..`. So `Bash(rm -rf /Users*)` refuses a worktree's
`build/` by its absolute path and lets `rm -rf ../Packages` through. This hook supersedes
the twelve `rm` denies over `/Users*` and `~/*`; the denies of exact `/` and `~` stay.

**It fails closed, to a prompt.** A command that mentions `rm` and cannot be read gets
"ask". Claude Code treats a crashed hook as non-blocking, so a crash loses the refusal; the
denies of exact `/` and `~` and the sandbox remain.

Test it without installing:

    echo '{"tool_input":{"command":"rm -rf ../x"},"cwd":"/Users/me/Research/Packages/A"}' | ./rm-scope.py
"""

import json
import os
import re
import shlex
import sys

HOME = os.path.realpath(os.path.expanduser("~"))
ROOT = os.path.realpath(os.path.join(HOME, "Research"))
WORKTREES = os.path.join(ROOT, ".worktrees")
SCRATCH = os.path.join(ROOT, ".scratch")
USERS = os.path.dirname(HOME)

PUNCTUATION = "();<>|&\n"
HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
LEADING_HOME = re.compile(r"^\$(?:HOME|\{HOME\})(?=/|$)")
GLOB = set("*?[{")

# `git` global options that consume the token after them.
TAKES_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"}
# Global options that point `git` at another repository than the working directory's.
ELSEWHERE = {"-C", "--git-dir", "--work-tree"}

MESSAGE = """Refused: {segment}

`{operand}` resolves to {path}, outside the zones where a recursive `rm` runs: below a
worktree, `~/Research/.worktrees/<name>/`, and below `~/Research/.scratch/`.

  * A worktree itself: `git worktree remove <path>` from the main checkout.
  * Build output in a checkout: remove it in a worktree, or name the files with a plain `rm`.
  * A probe environment: put it under `~/Research/.scratch/<task>/` and remove it there.
"""


def cut_heredocs(command):
    """Return the command without its heredoc bodies, which are data, not commands."""
    kept, pending = [], []
    for line in command.split("\n"):
        if pending:
            tabs, delimiter = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            continue
        for match in HEREDOC.finditer(line):
            pending.append((match.group(1) == "-", match.group(3)))
        kept.append(line)
    return "\n".join(kept)


def segments(command):
    """Return the command's segments as word lists; redirections and their targets dropped."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    result, current, skip = [], [], False
    for token in lexer:
        if set(token) <= set(PUNCTUATION):
            if "<" in token or ">" in token:
                if current and current[-1].isdigit():
                    current.pop()
                skip = True
                continue
            result.append(current)
            current = []
        elif skip:
            skip = False
        else:
            current.append(token)
    result.append(current)
    return [words for words in result if words]


def expand(word):
    """Expand a leading `~` or `$HOME`; None when anything else is left for the shell."""
    if word == "~" or word.startswith("~/"):
        word = HOME + word[1:]
    word = LEADING_HOME.sub(lambda _: HOME, word)
    if "$" in word or "`" in word or word.startswith("~"):
        return None
    return word


def resolve(word, cwd):
    """Return the absolute path an operand names, without following its last component.

    A glob is replaced by the literal directory before it, plus one placeholder component
    for each component from the glob on: every match lies at least that deep. None when
    the operand or the working directory is unknown.
    """
    path = expand(word)
    if path is None:
        return None
    if not os.path.isabs(path):
        if cwd is None:
            return None
        path = os.path.join(cwd, path)
    parts = path.split("/")
    for index, part in enumerate(parts):
        if GLOB & set(part):
            depth = len([p for p in parts[index:] if p])
            base = os.path.realpath("/".join(parts[:index]) or "/")
            return os.path.join(base, *(["*"] * depth))
    path = os.path.normpath(path)
    head, tail = os.path.split(path)
    if word.endswith("/") or tail in ("", ".", ".."):
        return os.path.realpath(path)
    return os.path.join(os.path.realpath(head), tail)


def below(path, root):
    return path.startswith(root + "/")


def in_zone(path):
    """True when the path lies strictly below a worktree, or strictly below `.scratch`."""
    if below(path, SCRATCH):
        return True
    if below(path, WORKTREES):
        return "/" in path[len(WORKTREES) + 1:]
    return False


def guarded(path):
    """True when a recursive `rm` of the path is refused."""
    return path == "/" or path == USERS or below(path, USERS)


def rm_arguments(words):
    """Return (recursive, operands) for an `rm` invocation."""
    recursive, operands, flags_done = False, [], False
    for word in words[1:]:
        if not flags_done and word == "--":
            flags_done = True
        elif not flags_done and word.startswith("--"):
            recursive = recursive or word == "--recursive"
        elif not flags_done and word.startswith("-") and len(word) > 1:
            recursive = recursive or "r" in word or "R" in word
        else:
            operands.append(word)
    return recursive, operands


def git_rm(words):
    """Return (is `git rm`, points elsewhere, forced) for a `git` invocation."""
    index, elsewhere = 1, False
    while index < len(words):
        word = words[index]
        if word.split("=")[0] in ELSEWHERE:
            elsewhere = True
        if word in TAKES_VALUE:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            break
    if index >= len(words) or words[index] != "rm":
        return False, False, False
    forced = False
    for word in words[index + 1:]:
        if word == "--":
            break
        if word == "--force" or (word.startswith("-") and not word.startswith("--") and "f" in word):
            forced = True
    return True, elsewhere, forced


def in_worktree(cwd):
    return cwd is not None and below(cwd, WORKTREES)


def change_directory(words, cwd):
    """Return the working directory after `cd`, or None when it cannot be known."""
    if len(words) < 2:
        return HOME
    target = expand(words[1])
    if target is None or target == "-":
        return None
    if not os.path.isabs(target):
        if cwd is None:
            return None
        target = os.path.join(cwd, target)
    return os.path.realpath(target)


def decide(command, cwd):
    """Return ("deny", message), ("ask", reason) or None."""
    cwd = os.path.realpath(cwd) if isinstance(cwd, str) and os.path.isabs(cwd) else None
    for words in segments(cut_heredocs(command)):
        while words and (ASSIGNMENT.match(words[0]) or words[0] in ("command", "nohup", "time")):
            words = words[1:]
        if not words:
            continue
        head = words[0]
        if head in ("cd", "pushd"):
            cwd = change_directory(words, cwd)
        elif head in ("rm", "/bin/rm"):
            recursive, operands = rm_arguments(words)
            if not recursive:
                continue
            for operand in operands:
                path = resolve(operand, cwd)
                if path is not None and not in_zone(path) and guarded(path):
                    return "deny", MESSAGE.format(segment=" ".join(words), operand=operand, path=path)
        elif head == "git":
            is_rm, elsewhere, forced = git_rm(words)
            if is_rm and (elsewhere or forced or not in_worktree(cwd)):
                return "ask", "`git rm` outside a worktree, with --force, or aimed at another repository."
    return None


def ask(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
        if not isinstance(command, str):
            raise TypeError
        if "rm" not in command:
            return 0
        verdict = decide(command, payload.get("cwd"))
    except Exception:
        return ask("rm-scope could not read a command that mentions rm.")
    if verdict is None:
        return 0
    if verdict[0] == "deny":
        sys.stderr.write(verdict[1])
        return 2
    return ask(verdict[1])


if __name__ == "__main__":
    sys.exit(main())
