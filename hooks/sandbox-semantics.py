#!/usr/bin/env python3
"""Refuse a command whose shape makes the sandbox answer something other than the truth.

A `PreToolUse` hook on the `Bash` matcher. It reads the tool call on stdin and exits 2
when the command carries one of four shapes the global `CLAUDE.md` forbids. Exit 2
refuses the call and shows this script's stderr to the model.

`sandbox.excludedCommands` exempts a command only when **every** part of it is led by
`git`, `gh`, `glab` or `ps`, and nothing is redirected to or from a file. A `2>&1` is
not a file redirection. A `cd` to the working directory is dropped before the match.
Any other command runs sandboxed, where `gh` and `glab` cannot reach the network and
`git` cannot write `.git`.

All four shapes fail **silently or misleadingly**, which is what makes them worth a hook:

  * **A `gh`, `glab` or `git` write nested below the top level** — inside `$( … )`,
    backticks or a loop body. The caller reads the failure as a negative result: "no
    checks yet", or a 403 that looks like a VPN fault. Reads still work, which hides it.
  * **A top-level `gh`, `glab` or `git` write in a command that is not exempt** —
    `cd other && git fetch`, `gh pr list | cat`, `gh api x > out.json`, and a `gh` or
    `glab` command that holds a backtick or a `$(`, even inside single quotes. `gh` reports
    `x509: OSStatus -26276`, which reads as a certificate problem.
  * **A `$?` in a command that will run sandboxed.** In `auto` mode the whole call is
    refused before it runs, and the refusal reads as a permission problem.
  * **A path argument to `git init`, `git clone`, `git worktree add`, `git worktree move`
    or `git bundle create`** that starts with `/`, `\\`, `~` or `$`, is a drive letter, or
    holds `..`. The harness then withdraws the exemption, and the `Operation not permitted`
    reads as a path problem, so sessions retry another spelling of the same path.

The first three are not expressible as a `permissions.deny` glob. The matcher sees no
nesting, cannot require every part of a command to match, and reads `?` as a wildcard, so
no glob can name `$?` literally. The fourth needs a glob for each position of the path
among the flags, and a deny message cannot name the fix.

**It fails open.** Any input it does not understand exits 0. The `$?` half duplicates a
refusal the harness already makes, so failing open there loses only the message.

Test it without installing:

    echo '{"tool_input":{"command":"echo $(gh run view 1)"}}' | ./sandbox-semantics.py ; echo "exit $?"
"""

import json
import os
import re
import shlex
import sys

SEGMENT = re.compile(r"(?:&&|\|\||;|\||\n)")

# `$( … )` and `` ` … ` ``. Neither nests here: a substitution inside a substitution is
# read as the outer one, which is enough to find the command word.
SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")

# The body of a `for`/`while`/`until` loop, and the condition of a `while`/`until` one.
# A `for` list is words rather than a command, so it has no condition to read.
LOOP_BODY = re.compile(r"\bdo\b(.*?)\bdone\b", re.DOTALL)
LOOP_CONDITION = re.compile(r"\b(?:while|until)\b(.*?)\bdo\b", re.DOTALL)
LOOP_HEAD = re.compile(r"\b(for|while|until)\b")

# The commands `sandbox.excludedCommands` lifts, and only when every part is one of them.
EXCLUDED = {"git", "gh", "glab", "ps"}

# The shell's punctuation. A run of these is one token; a token of separators ends a part.
PUNCTUATION = "();<>|&\n"
SEPARATORS = set(";|&\n")

# `git` subcommands that need to write `.git` or reach the network. The read-only ones
# are left out on purpose: `$(git rev-parse HEAD)` and `$(git branch --show-current)` are
# ordinary idioms that work sandboxed, and refusing them would be a false positive.
GIT_WRITES = {
    "add", "commit", "push", "merge", "rebase", "cherry-pick", "revert", "am", "apply",
    "reset", "stash", "clone", "init", "fetch", "pull", "update-ref", "gc", "prune",
    "restore", "mv", "rm", "checkout", "switch",
}

# `git` global options that consume the token after them.
TAKES_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"}

# The `git` commands whose path arguments the harness screens, as (subcommand, action).
# An argument after them that is not a flag and reads as a path outside the working
# directory withdraws the exemption, so the command runs sandboxed and cannot create `.git`.
PATH_SCREENED = {
    ("init", None), ("clone", None),
    ("worktree", "add"), ("worktree", "move"), ("bundle", "create"),
}
DRIVE = re.compile(r"^[A-Za-z]:")

NESTED_MESSAGE = """Refused: {found}

`{head}` is nested below the top level, inside {where}. `sandbox.excludedCommands` lifts
the sandbox for a **top-level** segment only. Nested, this runs sandboxed: it cannot
reach the network and cannot write `.git`, and the failure reads as a negative result
rather than as an error.

Give it a Bash call of its own, with `{head}` as the whole command:

    {head} …

Reach the repository first with `cd <repository>` as a separate Bash call. A `cd … &&` in
front puts the command back in the sandbox too.

To wait on a remote state, background the command that answers the question, so the
completion notification carries the verdict. Never put `gh` inside an `until` loop.
"""

EXPOSED_MESSAGE = """Refused: {found}

This command runs sandboxed, because {reason}. `sandbox.excludedCommands` exempts a
command only when **every** part is led by `git`, `gh`, `glab` or `ps` and nothing is
redirected to or from a file; `2>&1` is fine. Sandboxed, `{head}` cannot reach the
network (`gh` reports `x509: OSStatus -26276`) and cannot write `.git`.

Give it a Bash call of its own, with `{head}` as the whole command:

    {head} …

Reach the repository first with `cd <repository>` as a separate Bash call. To keep the
output, let it print and save it with the Write tool; do not pipe or redirect it.
"""

# The harness reads a backtick or a `$(` in a `gh` command as a command substitution even
# inside single quotes, so it runs the whole command sandboxed. This parser is quote-aware
# and would call the command exempt, so both are checked on the raw text.
SUBSTITUTED = "it holds a backtick or a `$(`"


def substituted(command):
    """True when the raw text holds what the harness reads as a command substitution."""
    return "`" in command or "$(" in command


BACKTICK_MESSAGE = """Refused: {found}

This command holds a backtick or a `$(`. The harness reads either as a command substitution,
even inside single quotes, so it runs the command sandboxed. Sandboxed, `{head}` cannot
reach the network and reports `x509: OSStatus -26276`. Markdown inline code in a `--body`
or a `--title`, and `--body "$(cat <<'EOF' …)"`, are the usual sources.

Write the text to a file with the Write tool, and pass the file by its absolute path:

    gh pr comment <n> -R <owner>/<repo> --body-file /absolute/path/body.md

Spell the path out. `$TMPDIR` names a different directory outside the sandbox, so
`--body-file "$TMPDIR/…"` finds no file.
"""

PATH_MESSAGE = """Refused: {found} {argument}

`{found}` loses the `sandbox.excludedCommands` exemption when an argument that is not a
flag starts with `/`, `\\`, `~` or `$`, is a drive letter, or holds a `..` segment. It then
runs sandboxed and fails with `.git: Operation not permitted`. Every other spelling of the
same path fails the same way.

Reach the parent directory with `cd <parent>` as a Bash call of its own, then give a
relative name:

    git init <name>
    git clone <url> <name>

For a worktree, call `EnterWorktree`; the `WorktreeCreate` hook makes it in
`~/Research/.worktrees/`.
"""

DOLLAR_MESSAGE = """Refused: {segment}

`$?` in a sandboxed command refuses the whole call before it runs, and the refusal reads
as a permission problem. Only a command whose every part is led by `git`, `gh`, `glab`
or `ps`, with no file redirection, escapes the sandbox; this one does not.

Let the command's own exit status stand. The Bash result already carries it: a non-zero
status arrives as `Exit code N` on the first line, and no such line means 0. So
`fatou lint src/Foo.jl` alone answers, with no `echo`.

A background task's notification reports the wrapper's exit code, not the job's, so log
the status without `$?`:

    julia script.jl > run.log 2>&1 && echo EXIT=0 >> run.log || echo EXIT=nonzero >> run.log
"""


def head_word(text):
    """Return the leading command word of a fragment, or None."""
    try:
        tokens = shlex.split(text)
    except ValueError:
        return None, []
    return part_head(tokens)


def git_subcommand(arguments):
    """Return the subcommand of a `git` invocation, or None."""
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in TAKES_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def path_screened(heads):
    """Return (command, argument) for a `git` path argument that withdraws the exemption."""
    for head, arguments in heads:
        if head != "git":
            continue
        sub = git_subcommand(arguments)
        if sub is None:
            continue
        rest = arguments[arguments.index(sub) + 1:]
        action = next((token for token in rest if not token.startswith("-")), None)
        if (sub, None) in PATH_SCREENED:
            found = "git " + sub
        elif (sub, action) in PATH_SCREENED:
            found = f"git {sub} {action}"
            rest = rest[rest.index(action) + 1:]
        else:
            continue
        if "--bare" in rest or "--mirror" in rest:
            continue                 # no `.git` directory, so the sandbox lets it write
        for token in rest:
            if token.startswith("-"):
                continue
            if (token[:1] in "/\\~$" or DRIVE.match(token)
                    or ".." in re.split(r"[/\\]", token)):
                return found, token
    return None


def offending(fragment):
    """Return the command word if this fragment holds a nested call that will fail."""
    for raw in SEGMENT.split(fragment):
        segment = raw.strip().lstrip("(").strip()
        if not segment:
            continue
        head, arguments = head_word(segment)
        if head in ("gh", "glab"):
            return head
        if head == "git" and git_subcommand(arguments) in GIT_WRITES:
            return "git " + git_subcommand(arguments)
    return None


def nested(command):
    """Return (command word, where) for the first nested call that will fail, or None."""
    for match in SUBSTITUTION.finditer(command):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        found = offending(inner)
        if found:
            return found, "a command substitution"
    if LOOP_HEAD.search(command):
        for match in LOOP_BODY.finditer(command):
            found = offending(match.group(1))
            if found:
                return found, "a loop body"
        for match in LOOP_CONDITION.finditer(command):
            found = offending(match.group(1).lstrip("! "))
            if found:
                return found, "a loop condition"
    return None


def parts(command):
    """Return (the top-level parts as token lists, whether a file is redirected), or None."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    result, current, redirected = [], [], False
    for index, token in enumerate(tokens):
        if not set(token) <= set(PUNCTUATION):
            current.append(token)
            continue
        bare = token.replace("(", "").replace(")", "")
        if "<" in bare or ">" in bare:
            target = tokens[index + 1] if index + 1 < len(tokens) else ""
            if not (bare in (">&", "<&") and (target.isdigit() or target == "-")):
                redirected = True
        elif bare and set(bare) <= SEPARATORS and current:
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result, redirected


def part_head(tokens):
    """Return the leading program of a part, and its arguments."""
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens = tokens[1:]          # a leading VAR=value assignment
    if not tokens:
        return None, []
    return tokens[0].rsplit("/", 1)[-1], tokens[1:]


def into_cwd(head, arguments, cwd):
    """True for a `cd` to the working directory, which the harness drops before matching."""
    if head != "cd" or len(arguments) != 1 or not cwd:
        return False
    target = os.path.expanduser(os.path.expandvars(arguments[0]))
    return os.path.realpath(os.path.join(cwd, target)) == os.path.realpath(cwd)


def top_level(command, cwd):
    """Return (the parts' (program, arguments), why it runs sandboxed or None), or None."""
    parsed = parts(command)
    if parsed is None:
        return None
    split, redirected = parsed
    heads = [part_head(tokens) for tokens in split]
    heads = [(head, arguments) for head, arguments in heads
             if head and not into_cwd(head, arguments, cwd)]
    others = [head for head, _ in heads if head not in EXCLUDED]
    if redirected:
        return heads, "it redirects a file"
    if others:
        return heads, f"`{others[0]}` leads another part of it"
    return heads, None


def exposed(command, cwd):
    """Return (command word, reason) for a top-level call the sandbox will catch, or None."""
    classified = top_level(command, cwd)
    if classified is None:
        # Text that does not parse, such as a body with an apostrophe, fails open, except
        # for a substitution behind a leading `gh` or `glab`: the harness sandboxes that
        # whatever the rest of the text holds.
        words = command.split(None, 1)
        if words and words[0] in ("gh", "glab") and substituted(command):
            return words[0], SUBSTITUTED
        return None
    heads, reason = classified
    if reason is None:
        # Only `gh` and `glab`: a `git commit -m "$(cat <<'EOF' …)"` and a heredoc message
        # holding backticks both committed, where `gh` in the same shapes failed.
        if substituted(command):
            for head, _ in heads:
                if head in ("gh", "glab"):
                    return head, SUBSTITUTED
        return None
    for head, arguments in heads:
        if head in ("gh", "glab"):
            return head, reason
        if head == "git" and git_subcommand(arguments) in GIT_WRITES:
            return "git " + git_subcommand(arguments), reason
    return None


def sandboxed(command, cwd):
    """True when the command runs inside the sandbox."""
    classified = top_level(command, cwd)
    return classified is not None and classified[1] is not None


def main():
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
    except Exception:
        return 0
    if not isinstance(command, str):
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None

    if any(name in command for name in ("gh", "glab", "git")):
        found = nested(command)
        if found:
            head, where = found
            sys.stderr.write(NESTED_MESSAGE.format(found=head, head=head, where=where))
            return 2
        found = exposed(command, cwd)
        if found:
            head, reason = found
            word = head.split()[0]
            message = BACKTICK_MESSAGE if reason == SUBSTITUTED else EXPOSED_MESSAGE
            sys.stderr.write(message.format(found=head, head=word, reason=reason))
            return 2
        classified = top_level(command, cwd)
        found = path_screened(classified[0]) if classified else None
        if found:
            sys.stderr.write(PATH_MESSAGE.format(found=found[0], argument=found[1]))
            return 2

    if "$?" in command and sandboxed(command, cwd):
        sys.stderr.write(DOLLAR_MESSAGE.format(segment=command.strip()))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
