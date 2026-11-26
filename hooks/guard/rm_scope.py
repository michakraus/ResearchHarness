"""Refuse a recursive `rm` outside the scratch zones; ask for a `git rm` or `git merge` outside a worktree.

The check follows the working directory through each `cd` of the command and resolves every
operand. A `cd` that can fail, and one that one shell runs as its own and another in a child,
leave either directory, and the check reads the commands after it in both (`moved_to`). A sure
`cd` (`shell.flow`) leaves only the new one up to the end of its scope: the rest of its `&&`
list, every command after `cd x || exit`, or the `then` of `if cd x`. A `popd` returns to the
directory before its `pushd`, and a `pushd` alone swaps the two (`moved_by`). Past DIRECTORIES,
the check reads the first directory and an unknown one. A recursive `rm` of a relative operand
after a `cd` to a directory that the check cannot know asks, and so does one whose operands need
more than EXTRA further resolutions (TOO_MANY).

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
from .shell import Simple, Tokens, builtin_commands, cut_heredocs, flow, joined, program, readings

HOME = str(Path.home().resolve())
ROOT = Path(HOME, "Research").resolve()
WORKTREES = ROOT.joinpath(".worktrees").parts
SCRATCH = ROOT.joinpath(".scratch").parts
USERS = PurePosixPath(HOME).parent.parts

LEADING_HOME = re.compile(r"^\$(?:HOME|\{HOME\})(?=/|$)")
GLOB = frozenset("*?[{")
RECURSIVE = "--recursive"
# The directories in which `moved_to` follows a command; a `cd` that can fail doubles them.
DIRECTORIES = 4
# The resolutions of `rm` operands that `decide` makes besides one per operand, in the other
# directories where an `rm` can run, so that a command of 1 MiB costs it a bounded time.
EXTRA = 4096

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
  * After a `cd`: the check also reads the directory before it, past the `&&` list that the `cd`
    starts, since the shell runs a command there where it was when the `cd` fails. Join the
    commands to the `cd` with `&&`, or write `cd <dir> || exit` first.
"""

UNREADABLE = "rm-scope could not read a command that mentions rm or merge."

UNKNOWN_DIRECTORY = (
    "`{segment}` removes a relative path after a `cd` to a directory that the check cannot know, "
    "such as `cd $X` or `cd -`, or after more `cd`s that can fail than the check follows, so it "
    "cannot tell what the removal reaches. Join each `cd` with `&&`."
)

TOO_MANY = (
    "`{segment}` can run in several directories, after a `cd` that can fail, and its operands are "
    "too many for the check to read in each. Join each `cd` with `&&`."
)


class Missing:
    """The working directory of a call that names none."""


MISSING = Missing()
type Cwd = Place | Missing | None  # None: a `cd` went to a directory that cannot be known


class NeedsCwdError(Exception):
    """An operand or a `git` command that only the call's missing working directory resolves."""


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
            # GNU `rm` takes a unique prefix of a long option; `--r` is one of `--recursive`.
            recursive = recursive or (len(word) > len("--") and RECURSIVE.startswith(word))
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


def moved_to(simple: Simple, cwds: list[Cwd], *, sure: bool) -> list[Cwd]:
    """The directories in which the commands after the `cd` or `pushd` `simple` can run, from the
    directories `cwds` before it, the one in which every `cd` succeeded first. A `sure` move
    (`shell.flow`) leaves only the new directories; one that can fail, or that one shell runs
    as its own and another in a child (`shell.Runs`), leaves either; one that a child runs leaves
    the directories as they were."""
    if simple.runs == "child":
        return cwds
    moved = [change_directory(simple.words, cwd) for cwd in cwds]
    return distinct(moved if sure else [*moved, *cwds])


def moved_by(simple: Simple, cwds: list[Cwd], stack: list[list[Cwd]], *, sure: bool) -> list[Cwd]:
    """The directories after the `cd`, `pushd` or `popd` `simple` from `cwds` (`moved_to`), with
    the stack of `pushd` in `stack`. A `pushd` with no operand swaps the top two directories of the
    stack, and a `popd` returns to the top one; with no `pushd` before it in the command, the
    directory cannot be known. A child's `pushd` or `popd` leaves both as they were."""
    head = program(simple.words[0])
    if head == "cd" or simple.runs == "child":
        return moved_to(simple, cwds, sure=sure)
    unknown: list[Cwd] = [None]
    if head == "popd":
        return stack.pop() if stack else unknown
    if len(simple.words) == 1:
        top = stack.pop() if stack else unknown
        stack.append(cwds)
        return top if sure else distinct([*top, *cwds])
    stack.append(cwds)
    return moved_to(simple, cwds, sure=sure)


def distinct(cwds: list[Cwd]) -> list[Cwd]:
    """Each directory of `cwds` once, in order. Past DIRECTORIES, the first one and a directory
    that the check cannot know stand for the others."""
    kept: list[Cwd] = []
    for cwd in cwds:
        if not any(same_cwd(cwd, other) for other in kept):
            kept.append(cwd)
    return kept if len(kept) <= DIRECTORIES else [kept[0], None]


def same_cwd(one: Cwd, other: Cwd) -> bool:
    """True when both are one directory, or both the same unknown or missing one. The memo of
    `paths.py` gives one `Place` for a walk, so most equal directories are one object, and the test
    of identity spares `Place.same` the text of a deep path."""
    if one is other:
        return True
    if isinstance(one, Place) and isinstance(other, Place):
        return one.same(other)
    return one is other


def unknown_operand(operand: str, cwd: Cwd) -> bool:
    """True when the operand `operand` is a path that the shell resolves against a directory that
    the check cannot know: a relative path, with no expansion, after a `cd` to such a directory."""
    path = expand(operand)
    return cwd is None and path is not None and not path.startswith("/")


def removal(words: list[str], operands: list[str], cwds: list[Cwd]) -> Verdict | None:
    """The verdict on the recursive `rm` `words` with `operands`, each read in each directory of
    `cwds`: deny for an operand outside the zones (`guarded`), ask for a relative operand in a
    directory that the check cannot know (`unknown_operand`), or None."""
    unknown = None
    for operand, here in ((operand, here) for operand in operands for here in cwds):
        path = resolve(operand, here)
        if path is not None and not in_zone(path) and guarded(path):
            return Verdict("deny", MESSAGE.format(segment=" ".join(words), operand=operand, path=path.text()))
        if unknown is None and unknown_operand(operand, here):
            unknown = Verdict("ask", UNKNOWN_DIRECTORY.format(segment=" ".join(words)))
    return unknown


def decide(tokens: Tokens, cwd: Cwd) -> Verdict:
    """The verdict on one reading of the command: each simple command from its command word on
    (`shell.commands`), so also an `rm` behind `sudo`, `env` or `then`, or spelled `RM`. A `cd`
    moves the directory as `moved_to` reads it, and each command after it is read in each
    directory where it can run: after a sure move (`shell.flow`), the directories before it come
    back where its scope ends. A `popd` returns to the directories before its `pushd`, or to one
    that the check cannot know. A recursive `rm` of a relative operand in a directory that the
    check cannot know asks, and so does one whose operands, read in every such directory, would
    take more than EXTRA resolutions besides one per operand: it is then read only where every
    `cd` succeeded."""
    cwds: list[Cwd] = [cwd]
    stack: list[list[Cwd]] = []
    unknown, extra = None, 0
    simples = builtin_commands(tokens)
    plan = flow(simples)
    returning: dict[int, list[list[Cwd]]] = {}
    for index, simple in enumerate(simples):
        for before in returning.pop(index, []):
            cwds = distinct([*cwds, *before])
        words = simple.words
        head = program(words[0])
        end = plan.ends[index]
        if end is not None:
            returning.setdefault(end, []).append(cwds)
        if head in ("cd", "pushd", "popd"):
            cwds = moved_by(simple, cwds, stack, sure=plan.sure[index])
        elif head == "rm":
            recursive, operands = rm_arguments(words)
            if not recursive:
                continue
            extra += (len(cwds) - 1) * len(operands)
            found = removal(words, operands, cwds if extra <= EXTRA else cwds[:1])
            if found is not None and found.decision == "deny":
                return found
            if extra > EXTRA:
                found = Verdict("ask", TOO_MANY.format(segment=" ".join(words)))
            unknown = unknown or found
        elif head == "git":
            subcommand, arguments, elsewhere = git_subcommand(words)
            if subcommand not in ("rm", "merge"):
                continue
            local = not elsewhere and all(in_worktree(here) for here in cwds)
            if subcommand == "rm" and (not local or git_rm_forced(arguments)):
                return Verdict(
                    "ask", "`git rm` outside a worktree, with --force, or aimed at another repository."
                )
            if subcommand == "merge" and not local and git_merge_asks(arguments):
                return Verdict("ask", "`git merge` outside a worktree, or aimed at another repository.")
    return unknown or PASS


def check(call: Call) -> Verdict:
    """Deny a recursive `rm` outside the zones; ask for a `git rm` or `git merge` outside a worktree."""
    command = call.command
    keywords = joined(command).lower()
    if "rm" not in keywords and "merge" not in keywords:
        return PASS
    read = readings(cut_heredocs(command), nested=True)
    if read is None:
        return Verdict("ask", UNREADABLE)
    cwd: Cwd = MISSING if call.cwd is None else place(call.cwd, "real")
    try:
        return strongest(decide(tokens, cwd) for tokens in read)
    except NeedsCwdError:
        return needs_cwd("rm", command)
