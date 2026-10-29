"""Refuse a command whose shape makes the sandbox answer something other than the truth.

`sandbox.excludedCommands` exempts a command only when every part of it is led by `git`, `gh`,
`glab` or `ps`, and nothing is redirected to or from a file. A `2>&1` is not a file redirection. A
`cd` to the working directory is dropped before the match. Any other command runs sandboxed, where
`gh` and `glab` cannot reach the network and `git` cannot write `.git`. The check denies five
shapes that fail silently or misleadingly:

  * a `gh`, `glab` or `git` write nested below the top level, inside `$( … )`, backticks or a
    loop body;
  * a top-level `gh`, `glab` or `git` write in a command that is not exempt, and a `gh` or `glab`
    command that holds a backtick or a `$(`, even inside single quotes;
  * a `$?` in a command that runs sandboxed;
  * a path argument to `git init`, `git clone`, `git worktree add`, `git worktree move` or
    `git bundle create` that starts with `/`, `\\`, `~` or `$`, is a drive letter, or holds `..`;
  * a `git init` or `git clone` whose working directory is inside an existing working tree.

The `cd` to the working directory and the working tree of a `git init` or `git clone` need the
call's working directory. When the call names none, every `cd` stays a part of the command, and a
`git init` or `git clone` is denied.
"""

import os
import re
from pathlib import Path

from .contract import PASS, Call, Verdict, needs_cwd, strongest
from .paths import Place, place
from .shell import SEGMENT, SEPARATORS, Tokens, readings, words

# `$( … )` and `` ` … ` ``. Neither nests here: a substitution inside a substitution is read as
# the outer one, which is enough to find the command word.
SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")

# The body of a `for`/`while`/`until` loop, and the condition of a `while`/`until` one.
LOOP_BODY = re.compile(r"\bdo\b(.*?)\bdone\b", re.DOTALL)
LOOP_CONDITION = re.compile(r"\b(?:while|until)\b(.*?)\bdo\b", re.DOTALL)
LOOP_HEAD = re.compile(r"\b(for|while|until)\b")
DO = re.compile(r"\bdo\b")
DONE = re.compile(r"\bdone\b")

# The commands `sandbox.excludedCommands` lifts, and only when every part is one of them.
EXCLUDED = frozenset({"git", "gh", "glab", "ps"})

# `git` subcommands that need to write `.git` or reach the network. `$(git rev-parse HEAD)` and
# `$(git branch --show-current)` work sandboxed, so the read-only ones are left out.
GIT_WRITES = frozenset(
    {
        "add",
        "commit",
        "push",
        "merge",
        "rebase",
        "cherry-pick",
        "revert",
        "am",
        "apply",
        "reset",
        "stash",
        "clone",
        "init",
        "fetch",
        "pull",
        "update-ref",
        "gc",
        "prune",
        "restore",
        "mv",
        "rm",
        "checkout",
        "switch",
    }
)

# `git` global options that consume the token after them.
TAKES_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"})

# The `git` commands whose path arguments Claude Code screens, as (subcommand, action).
PATH_SCREENED = frozenset(
    {("init", None), ("clone", None), ("worktree", "add"), ("worktree", "move"), ("bundle", "create")}
)
DRIVE = re.compile(r"^[A-Za-z]:")
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

HOME = str(Path.home())

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

# The harness reads a backtick or a `$(` in a `gh` command as a command substitution even inside
# single quotes, so it runs the whole command sandboxed. The reading here is quote-aware and would
# call the command exempt, so both are checked on the raw text.
SUBSTITUTED = "it holds a backtick or a `$(`"

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

WORK_TREE_MESSAGE = """Refused: {found} in {cwd}

This directory is inside the work tree {root}, so the command leaves a repository in a work
tree. Under Claude Code, a `cd` outside the agent's working directories is reset before the
next call, so the command runs in the agent's root, which is often not the directory you meant.

A probe needs no repository. Compare two copies with `git diff --no-index <a> <b>`, and read
a worktree with `cd <worktree> && git <read> …` in one call.

To make a repository, `cd` in a call of its own into a directory that is no work tree, such
as `~/Research/.scratch/<name>`, and give a relative name there:

    git init <name>
    git clone <url> <name>
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

type Head = tuple[str | None, list[str]]


class NeedsCwdError(Exception):
    """A shape that only the call's missing working directory decides."""


def substituted(command: str) -> bool:
    """True when the raw text holds what Claude Code reads as a command substitution."""
    return "`" in command or "$(" in command


def expanded(word: str) -> str:
    """The word with its variables of the environment and a leading `~` expanded, as far as they
    are known; an unknown variable stays as it is."""

    def value(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1) or match.group(2), match.group(0))

    word = VARIABLE.sub(value, word)
    return HOME + word[1:] if word == "~" or word.startswith("~/") else word


def part_head(tokens: list[str]) -> Head:
    """The leading program of a part, and its arguments."""
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens = tokens[1:]  # a leading VAR=value assignment
    if not tokens:
        return None, []
    return tokens[0].rsplit("/", 1)[-1], tokens[1:]


def head_word(text: str) -> Head:
    """The leading command word of a fragment and its arguments, or (None, [])."""
    found = words(text)
    return (None, []) if found is None else part_head(found)


def git_subcommand(arguments: list[str]) -> str | None:
    """The subcommand of a `git` invocation, or None."""
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


def path_screened(heads: list[Head]) -> tuple[str, str] | None:
    """(command, argument) for a `git` path argument that withdraws the exemption."""
    for head, arguments in heads:
        if head != "git":
            continue
        sub = git_subcommand(arguments)
        if sub is None:
            continue
        rest = arguments[arguments.index(sub) + 1 :]
        action = next((token for token in rest if not token.startswith("-")), None)
        if (sub, None) in PATH_SCREENED:
            found = "git " + sub
        elif (sub, action) in PATH_SCREENED and action is not None:
            found = f"git {sub} {action}"
            rest = rest[rest.index(action) + 1 :]
        else:
            continue
        if "--bare" in rest or "--mirror" in rest:
            continue  # no `.git` directory, so the sandbox lets it write
        for token in rest:
            if token.startswith("-"):
                continue
            if token[:1] in "/\\~$" or DRIVE.match(token) or ".." in re.split(r"[/\\]", token):
                return found, token
    return None


def work_tree(path: Place) -> str | None:
    """The root of the working tree that holds the resolved `path`, or None. Only a directory that
    exists can hold a `.git`."""
    current: Place | None = path.existing()
    while current is not None:
        if Path(current.text(), ".git").exists(follow_symlinks=False):
            return current.text()
        current = current.up
    return None


def in_work_tree(heads: list[Head], cwd: Place | None) -> tuple[str, str, str] | None:
    """(command, root, directory) for a `git init` or `git clone` that lands in a work tree, or
    None. The target is the last argument that is not a flag, resolved against the working
    directory after each `cd` before it; without one it is that working directory. A clone's URL,
    read as the target, lies below the working directory too, so the verdict is the working
    directory's."""
    for head, arguments in heads:
        if head == "cd" and arguments:
            if cwd is not None:
                cwd = cwd.go(expanded(arguments[0]), "real")
            continue
        if head != "git":
            continue
        sub = git_subcommand(arguments)
        if sub not in ("init", "clone"):
            continue
        if cwd is None:
            raise NeedsCwdError
        rest = arguments[arguments.index(sub) + 1 :]
        operands = [token for token in rest if not token.startswith("-")]
        target = expanded(operands[-1]) if operands else "."
        root = work_tree(cwd.go(target, "real"))
        if root:
            return "git " + sub, root, cwd.text()
    return None


def offending(fragment: str) -> str | None:
    """The command word if this fragment holds a nested call that will fail."""
    for raw in SEGMENT.split(fragment):
        segment = raw.strip().lstrip("(").strip()
        if not segment:
            continue
        head, arguments = head_word(segment)
        if head in ("gh", "glab"):
            return head
        sub = git_subcommand(arguments)
        if head == "git" and sub in GIT_WRITES:
            return "git " + sub
    return None


def last_end(word: re.Pattern[str], text: str) -> int:
    """The index after the last match of `word` in `text`, or 0."""
    return max((match.end() for match in word.finditer(text)), default=0)


def nested(command: str) -> tuple[str, str] | None:
    """(command word, where) for the first nested call that will fail, or None."""
    for match in SUBSTITUTION.finditer(command):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        found = offending(inner)
        if found:
            return found, "a command substitution"
    if LOOP_HEAD.search(command):
        # Each search ends at the last word that can close a match, so that no lazy scan runs from
        # every opening word to the end of a text with no closing word after it.
        for match in LOOP_BODY.finditer(command, 0, last_end(DONE, command)):
            found = offending(match.group(1))
            if found:
                return found, "a loop body"
        for match in LOOP_CONDITION.finditer(command, 0, last_end(DO, command)):
            found = offending(match.group(1).lstrip("! "))
            if found:
                return found, "a loop condition"
    return None


def parts(tokens: Tokens) -> tuple[list[list[str]], bool]:
    """The top-level parts as word lists, and whether a file is redirected."""
    result: list[list[str]] = []
    current: list[str] = []
    redirected = False
    for index, (kind, token) in enumerate(tokens):
        if kind == "word":
            current.append(token)
            continue
        bare = token.replace("(", "").replace(")", "")
        if "<" in bare or ">" in bare:
            target = tokens[index + 1][1] if index + 1 < len(tokens) else ""
            if not (bare in (">&", "<&") and (target.isdigit() or target == "-")):
                redirected = True
        elif bare and set(bare) <= SEPARATORS and current:
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result, redirected


def into_cwd(head: str | None, arguments: list[str], cwd: Place | None) -> bool:
    """True for a `cd` to the working directory, which Claude Code drops before matching. Without
    a working directory no `cd` is known to go there, and each stays a part of the command; a part
    only makes a command run sandboxed, so this reading denies whatever a working directory would."""
    if head != "cd" or len(arguments) != 1 or cwd is None:
        return False
    return cwd.go(expanded(arguments[0]), "real").same(cwd)


def top_level(tokens: Tokens, cwd: Place | None) -> tuple[list[Head], str | None]:
    """The parts' (program, arguments), and why the command runs sandboxed or None."""
    split, redirected = parts(tokens)
    heads: list[Head] = [
        (head, arguments)
        for head, arguments in (part_head(words) for words in split)
        if head and not into_cwd(head, arguments, cwd)
    ]
    others = [head for head, _ in heads if head not in EXCLUDED]
    if redirected:
        return heads, "it redirects a file"
    if others:
        return heads, f"`{others[0]}` leads another part of it"
    return heads, None


def exposed(command: str, classified: tuple[list[Head], str | None] | None) -> tuple[str, str] | None:
    """(command word, reason) for a top-level call the sandbox will catch, or None."""
    if classified is None:
        # Text that does not parse passes, except for a substitution behind a leading `gh` or
        # `glab`: Claude Code sandboxes that whatever the rest of the text holds.
        first = command.split(None, 1)
        heads: list[Head] = [(first[0], [])] if first else []
        reason = None
    else:
        heads, reason = classified
    if reason is None:
        # Only `gh` and `glab`: a `git commit -m "$(cat <<'EOF' …)"` and a heredoc message holding
        # backticks both committed, where `gh` in the same shapes failed.
        found = next((head for head, _ in heads if head in ("gh", "glab")), None)
        return (found, SUBSTITUTED) if found is not None and substituted(command) else None
    for head, arguments in heads:
        if head in ("gh", "glab"):
            return head, reason
        sub = git_subcommand(arguments)
        if head == "git" and sub in GIT_WRITES:
            return "git " + sub, reason
    return None


def decide(command: str, tokens: Tokens | None, cwd: Place | None) -> Verdict:
    """The verdict on one reading of the command; `tokens` None for a text that does not read."""
    if any(name in command for name in ("gh", "glab", "git")):
        found = nested(command)
        if found:
            head, where = found
            return Verdict("deny", NESTED_MESSAGE.format(found=head, head=head, where=where))
        classified = None if tokens is None else top_level(tokens, cwd)
        found = exposed(command, classified)
        if found:
            head, reason = found
            message = BACKTICK_MESSAGE if reason == SUBSTITUTED else EXPOSED_MESSAGE
            return Verdict("deny", message.format(found=head, head=head.split()[0], reason=reason))
        screened = path_screened(classified[0]) if classified else None
        if screened:
            return Verdict("deny", PATH_MESSAGE.format(found=screened[0], argument=screened[1]))
        landed = in_work_tree(classified[0], cwd) if classified else None
        if landed:
            return Verdict("deny", WORK_TREE_MESSAGE.format(found=landed[0], cwd=landed[2], root=landed[1]))
    if "$?" in command and tokens is not None and top_level(tokens, cwd)[1] is not None:
        return Verdict("deny", DOLLAR_MESSAGE.format(segment=command.strip()))
    return PASS


def check(call: Call) -> Verdict:
    """Deny a command whose shape the sandbox misreports."""
    command = call.command
    if not (any(name in command for name in ("gh", "glab", "git")) or "$?" in command):
        return PASS
    read = readings(command)
    cwd = None if call.cwd is None else place(call.cwd, "real")
    try:
        return strongest(decide(command, tokens, cwd) for tokens in (read if read is not None else [None]))
    except NeedsCwdError:
        return needs_cwd("sandbox", command)
