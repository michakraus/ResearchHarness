"""Refuse a recursive `rm` outside the scratch zones; ask for a `git rm` or `git merge` outside a worktree.

The check follows the working directory through each `cd` of the command and resolves every
operand.

  * **`rm`**: pass when every operand lies strictly below a worktree, `~/Research/.worktrees/<name>/`,
    or strictly below `~/Research/.scratch/`. Deny a **recursive** `rm` of any other path under the
    parent of the home directory (`/Users` on macOS, `/home` on Linux), or of `/` or that parent
    itself. A plain `rm` outside the zones, and an operand the check cannot resolve (a variable
    other than `$HOME`, a command substitution), pass: the sandbox and the rules decide.
  * **`git rm`**: pass when the working directory lies in a worktree and no `-f`/`--force` is
    given; otherwise ask.
  * **`git merge`**: pass when the working directory lies in a worktree. Elsewhere, or aimed at
    another repository, ask, except for a `--ff-only` or `--no-edit` merge with none of `--no-ff`,
    `--squash`, `--no-commit` and `-m`. `--abort` is left to its `ask` rule.

A command that mentions `rm` or `merge` and cannot be read asks. An operand or a `git rm` or
`git merge` that only the call's working directory resolves is denied when the call names none.
"""

import functools
import re
from pathlib import Path, PurePosixPath

from .contract import PASS, Call, Verdict, needs_cwd, strongest
from .paths import Place, place
from .shell import Tokens, readings

HOME = str(Path.home().resolve())
ROOT = Path(HOME, "Research").resolve()
WORKTREES = ROOT.joinpath(".worktrees").parts
SCRATCH = ROOT.joinpath(".scratch").parts
USERS = PurePosixPath(HOME).parent.parts

HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
LEADING_HOME = re.compile(r"^\$(?:HOME|\{HOME\})(?=/|$)")
GLOB = frozenset("*?[{")

# `git` global options that consume the token after them.
TAKES_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"})
# Global options that point `git` at another repository than the working directory's.
ELSEWHERE = frozenset({"-C", "--git-dir", "--work-tree"})

MESSAGE = """Refused: {segment}

`{operand}` resolves to {path}, outside the zones where a recursive `rm` runs: below a
worktree, `~/Research/.worktrees/<name>/`, and below `~/Research/.scratch/`.

  * A worktree itself: `git worktree remove <path>` from the main checkout.
  * Build output in a checkout: remove it in a worktree, or name the files with a plain `rm`.
  * A probe environment: put it under `~/Research/.scratch/<task>/` and remove it there.
"""

UNREADABLE = "rm-scope could not read a command that mentions rm or merge."


class Missing:
    """The working directory of a call that names none."""


MISSING = Missing()
type Cwd = Place | Missing | None  # None: a `cd` went to a directory that cannot be known


class NeedsCwdError(Exception):
    """An operand or a `git` command that only the call's missing working directory resolves."""


def cut_heredocs(command: str) -> str:
    """The command without its heredoc bodies, which are data, not commands."""
    kept: list[str] = []
    pending: list[tuple[bool, str]] = []
    for line in command.split("\n"):
        if pending:
            tabs, delimiter = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            continue
        pending.extend((match.group(1) == "-", match.group(3)) for match in HEREDOC.finditer(line))
        kept.append(line)
    return "\n".join(kept)


def segments(tokens: Tokens) -> list[list[str]]:
    """The command's segments as word lists; redirections and their targets dropped."""
    result: list[list[str]] = []
    current: list[str] = []
    skip = False
    for kind, token in tokens:
        if kind == "op":
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


def expand(word: str) -> str | None:
    """The word with a leading `~` or `$HOME` expanded; None when anything else is left for the
    shell."""
    if word == "~" or word.startswith("~/"):
        word = HOME + word[1:]
    word = LEADING_HOME.sub(lambda _: HOME, word)
    if "$" in word or "`" in word or word.startswith("~"):
        return None
    return word


def normalised(path: PurePosixPath) -> tuple[int, list[str]]:
    """(ups, downs): the names `..` that a relative `path` climbs, then the names it descends, after
    each `..` dropped the name before it."""
    ups, downs = 0, list[str]()
    for name in path.parts[1 if path.is_absolute() else 0 :]:
        if name != "..":
            downs.append(name)
        elif downs:
            downs.pop()
        else:
            ups += 1
    return ups, downs


def resolve(word: str, cwd: Cwd) -> Place | None:
    """The absolute path an operand names, without following its last name.

    A glob is replaced by the literal directory before it, plus one placeholder name for each name
    from the glob on: every match lies at least that deep. None when the operand or the working
    directory is unknown.
    """
    path = expand(word)
    if path is None:
        return None
    pure = PurePosixPath(path)
    if pure.is_absolute():
        base = Place.anchor()
    elif isinstance(cwd, Missing):
        raise NeedsCwdError
    elif cwd is None:
        return None
    else:
        base = cwd
    names = path.split("/")
    index = next((index for index, name in enumerate(names) if GLOB & set(name)), None)
    if index is not None:
        found = base.go(str(PurePosixPath(*names[:index])), "real")
        for _ in range(len([name for name in names[index:] if name])):
            found = found.joined("*")
        return found
    # The operand is normalised as text first, so a `..` drops the name before it, link or not.
    ups, downs = normalised(pure)
    found = base
    for _ in range(ups):
        found = found.parent()
    if not downs:
        return found
    if len(downs) > 1:
        found = found.go(str(PurePosixPath(*downs[:-1])), "real")
    return found.child(downs[-1], "real") if word.endswith("/") else found.joined(downs[-1])


def below(path: Place, root: tuple[str, ...]) -> bool:
    """True when the path lies strictly below `root`, a root other than `/`."""
    return len(root) > 1 and path.below(root)


def in_zone(path: Place) -> bool:
    """True when the path lies strictly below a worktree, or strictly below `.scratch`."""
    if below(path, SCRATCH):
        return True
    return below(path, WORKTREES) and path.size > len(WORKTREES) + 1


def guarded(path: Place) -> bool:
    """True when a recursive `rm` of the path is refused."""
    return path.size == 1 or (path.size == len(USERS) and path.starts(USERS)) or below(path, USERS)


def rm_arguments(words: list[str]) -> tuple[bool, list[str]]:
    """(recursive, operands) for an `rm` invocation."""
    recursive, flags_done = False, False
    operands: list[str] = []
    for word in words[1:]:
        if not flags_done and word == "--":
            flags_done = True
        elif not flags_done and word.startswith("--"):
            recursive = recursive or word == "--recursive"
        elif not flags_done and word.startswith("-") and word != "-":
            recursive = recursive or "r" in word or "R" in word
        else:
            operands.append(word)
    return recursive, operands


def git_subcommand(words: list[str]) -> tuple[str | None, list[str], bool]:
    """(subcommand, its arguments, points elsewhere) for a `git` invocation."""
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
    if index >= len(words):
        return None, [], elsewhere
    return words[index], words[index + 1 :], elsewhere


def options(arguments: list[str]) -> list[str]:
    """The arguments before `--`."""
    return arguments[: arguments.index("--")] if "--" in arguments else arguments


def git_rm_forced(arguments: list[str]) -> bool:
    """True when a `git rm` carries `-f` or `--force`, also in a short cluster."""
    return any(
        word == "--force" or (word.startswith("-") and not word.startswith("--") and "f" in word)
        for word in options(arguments)
    )


def git_merge_asks(arguments: list[str]) -> bool:
    """True when a `git merge` outside a worktree asks: anything but a plain `--ff-only` or
    `--no-edit` merge."""
    words = options(arguments)
    if "--abort" in words:
        return False
    named = any(
        word in ("--no-ff", "--squash", "--no-commit")
        or word.startswith("--message")
        or (word.startswith("-m") and not word.startswith("--"))
        for word in words
    )
    return named or not any(word in ("--ff-only", "--no-edit") for word in words)


def in_worktree(cwd: Cwd) -> bool:
    if isinstance(cwd, Missing):
        raise NeedsCwdError
    return cwd is not None and below(cwd, WORKTREES)


@functools.cache
def home() -> Place:
    """The home directory, where a `cd` with no operand goes."""
    return place(HOME, "real")


def change_directory(words: list[str], cwd: Cwd) -> Cwd:
    """The working directory after `cd`: None when it cannot be known, MISSING when it is relative
    to the call's missing working directory."""
    if len(words) == 1:
        return home()
    target = expand(words[1])
    if target is None or target == "-":
        return None
    if PurePosixPath(target).is_absolute():
        return place(target, "real")
    if cwd is None or isinstance(cwd, Missing):
        return cwd
    return cwd.go(target, "real")


def decide(tokens: Tokens, cwd: Cwd) -> Verdict:
    """The verdict on one reading of the command."""
    for found in segments(tokens):
        words = found
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
                    return Verdict(
                        "deny", MESSAGE.format(segment=" ".join(words), operand=operand, path=path.text())
                    )
        elif head == "git":
            subcommand, arguments, elsewhere = git_subcommand(words)
            if subcommand not in ("rm", "merge"):
                continue
            local = not elsewhere and in_worktree(cwd)
            if subcommand == "rm" and (not local or git_rm_forced(arguments)):
                return Verdict(
                    "ask", "`git rm` outside a worktree, with --force, or aimed at another repository."
                )
            if subcommand == "merge" and not local and git_merge_asks(arguments):
                return Verdict("ask", "`git merge` outside a worktree, or aimed at another repository.")
    return PASS


def check(call: Call) -> Verdict:
    """Deny a recursive `rm` outside the zones; ask for a `git rm` or `git merge` outside a worktree."""
    command = call.command
    if "rm" not in command and "merge" not in command:
        return PASS
    read = readings(cut_heredocs(command))
    if read is None:
        return Verdict("ask", UNREADABLE)
    cwd: Cwd = MISSING if call.cwd is None else place(call.cwd, "real")
    try:
        return strongest(decide(tokens, cwd) for tokens in read)
    except NeedsCwdError:
        return needs_cwd("rm", command)
