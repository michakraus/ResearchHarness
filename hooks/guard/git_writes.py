"""Allow three `git` writes when the repository shows that nothing is lost; ask otherwise.

The check allows only a command that is one `git` call and nothing else: no operator, no
redirection, no second part, no global option before the subcommand. Its text must also be plain
(`sandbox_lift.PLAIN`): no `$`, backslash, backtick, `#` or `!` outside a single quote, so that
bash and zsh run the words that the check read; any other text that it would allow asks. It
reads the state of the repository with `git` in the call's working directory, the payload's
`cwd`.

  * **`git worktree remove --force <path>`**, or `-f`, given once: allow when the path, resolved
    without following its last name, lies below `~/Research/.worktrees/`, a remote-tracking ref
    contains the worktree's HEAD (`git for-each-ref --contains HEAD refs/remotes`), and no tracked
    file is modified or staged (`git status --porcelain --untracked-files=no`). Untracked and
    ignored files may go. Otherwise ask, with a reason that names what would be lost. A ref that
    contains HEAD holds every commit of HEAD; `origin/main` is one, so a HEAD that `origin/main`
    contains needs no test of its own.
  * **`git cherry-pick`**, with any arguments: allow when the working directory lies below
    `~/Research/.worktrees/<name>/`, or in a checkout whose `origin` is a GitHub repository of an
    own organisation. Otherwise ask.
  * **`git push --force-with-lease[=<ref>[:<expect>]] origin <branch>`**, or with the refspec
    `HEAD:refs/heads/<branch>`: allow when every push URL of `origin` is a GitHub repository
    of an own organisation and the lease names no ref, or names `<branch>` (`<branch>` or
    `refs/heads/<branch>`). Otherwise ask. A bare lease takes the expected value from the
    remote-tracking ref; an explicit `<expect>` is checked by `git` on the remote.
  * **A lease push that names a default branch, or no branch**: deny, in each part of the
    command, so also `git fetch && git push --force-with-lease origin main`, and after another
    write in the same part, as in a `find` with two `-exec`. A push names a
    default branch when an argument after `push`, the value of an option aside, names `main`,
    `master` or the branch that `refs/remotes/origin/HEAD` names as its target (`<branch>`,
    `+<branch>`, `<src>:<branch>`, each also with `refs/heads/` or `heads/`). `origin/HEAD` is
    read in the call's working directory and, where they differ, in the repository that the push
    works on: the directory after each `cd` before it and each `-C` or `--git-dir` of its `git`. A
    directory that the shell would expand is unknown, and only the call's own default counts for it.
    It names no branch, and can reach a default one,
    with no refspec after the remote (as with `--all` or `--mirror`, which `git` takes with no
    refspec only), or with a refspec whose target is `HEAD`, `@` or empty, or that holds a glob
    (`*`, `?`, `[`), a brace, `$` or a backtick. The value of `-o`, also at the end of a cluster
    such as `-vo`, and of `--push-option`, `--repo`, `--receive-pack`, `--exec` and
    `--recurse-submodules`, also of a prefix of each, is no refspec.

The check finds the subcommand as `git` does, after its global options (`subcommand`). It reads a
program whose last name is `git` in any case as `git` (`is_git`), since a file system that ignores
case runs git for `GIT`, and it reads no redirection's target as a word of a call
(`shell.unredirected`), so `git 2>&1 push` is a push. A subcommand that the shell expands, as in
`git pus{h,}`, or that a `-c alias.*` or `--config-env=alias.*` option or an assignment of a
`GIT_CONFIG_*` variable before it can make an alias, is unknown, and so is a subcommand that is no
builtin (BUILTINS) and that the git configuration of the repository of the call's part makes an
alias that can run a write (`alias_writes`): the call asks, and a lease push with it is read for a
default branch as any other. An alias such as `lg = log --oneline` passes. It
takes a `worktree remove` with any option as forced, since `git` reads `-ff` and a prefix of
`--force` as force, and a `push` with an option that begins with `--force-w` as a lease push, as
well as an option that the shell expands, where the text before the expansion begins as a lease
does (`--force-$w`, `--$x`).
It reads the command as `shell.readings` does with `nested`, so a write in the script of
`sh -c`, `bash -c` or `eval` is read as well; such a write is never alone. In the `<branch>` form the
branch must be a local one, and `origin` must have no `remote.origin.push` refspec, which can map
the branch onto another remote branch. Any other command that holds one of these writes asks:
`-C`, a `cd` before it, a pipeline, `-f` twice, a lease after the remote, a second refspec. A
`deny` rule of the settings template still refuses those it names, such as a plain `--force`.
`git` that cannot be run, or that fails, asks. A command that `shell.readings` cannot read, such as
one with an open quote in a heredoc body, asks when it holds a word that ends in `git`, in any
case, and after it `push`, `worktree` or `cherry-pick` as a word of its own, an alias option or a
lease option; when the subcommand of such a `git`, after its global options and redirections,
holds `$`, a backtick or a brace; or when it holds a `$` before a quote or a backslash, which can
open an ANSI-C quote that decodes into either (`unread_write`). Without them it passes, as Julia's
`push!`, `git -C $dir log` or a path below `.worktrees/` do; it looks up no alias there.

The own organisations are the `org` list of the profile, as `gh_api_writes.own_organisations` reads
it. Each `git` runs with `core.fsmonitor` off, so that `git status` starts no monitor program that
a repository's configuration names; a clean filter of the repository can still run. It runs with
`--no-optional-locks`, so that `git status` takes no index lock from a `git` of another session.

A permission rule cannot state this: it sees neither the working directory nor the worktree's
state. And a hook's `allow` does not lift a matching `ask` or `deny` rule, so the template holds no
rule for these forms and the check answers both ways.
"""

import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import PurePosixPath

from .contract import PASS, Call, Verdict, strongest
from .gh_api_writes import own_organisations
from .paths import Place, place
from .rm_scope import TAKES_VALUE, WORKTREES, below, expand, resolve
from .sandbox_lift import PLAIN
from .shell import Tokens, joined, parts, program, readings, unredirected

# Seconds for each `git` the check runs.
TIMEOUT = 5

# A GitHub URL, with the owner as group 1.
GITHUB = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([A-Za-z0-9-]+)/[A-Za-z0-9._-]+?(?:\.git)?/?$"
)
# A branch name the check reads; anything else asks.
BRANCH = re.compile(r"^(?!-)(?!HEAD$)[A-Za-z0-9._/-]+$")
DEFAULTS = frozenset({"main", "master"})
# The long options of `git push` that take the next word as their value; `git` also takes a unique
# prefix of each.
VALUED = ("--push-option", "--repo", "--receive-pack", "--exec", "--recurse-submodules")
# A cluster of short options that ends in `-o`, which takes the next word as its value: `-o`, `-vo`.
SHORT_VALUED = re.compile(r"-[^-o]*o")
LEASE = "--force-with-lease"
# The characters by which the shell expands a word into a text that the check cannot read.
EXPANSIONS = frozenset("$`{*?[")
# The global options of `git` that name the repository it works on.
REPOSITORY = ("-C", "--git-dir")
SHAPE = "`git push --force-with-lease[=<ref>[:<expect>]] origin <branch>`, or with `HEAD:refs/heads/<branch>`"
# The changed files that a reason names.
NAMED = 5
# A word that ends in `git`, such as `git` or a path to it (`unread_write`). It has no left
# boundary: `joined` removes each backslash-newline, also one that the shell keeps as two lines (a
# `\\` or a `\` that ends a comment), and then glues the `git` of the next line to the word before.
# In any case, since a file system that ignores case, as macOS's does, runs git for `GIT`.
GIT_WORD = re.compile(r"git(?![\w.-])", re.IGNORECASE)
# A keyword of the check as a word of its own: one inside a longer word, such as Julia's `push!`
# or the path `.worktrees/`, is none (`unread_write`).
KEYWORD_WORD = re.compile(r"(?<![\w./-])(?:push|worktree|cherry-pick)(?![\w./!-])")
# A `$` before a quote or a backslash, which opens an ANSI-C quote, also one that the script of
# `eval` or `sh -c` forms, as `\$\'` does (`unread_write`).
ANSI_C_OPENER = re.compile(r"\$[\\'\"]")
# A word that ends in `git` and, in the subcommand's place, a word that the shell expands
# (`unread_write`): after at most eight global options, each of `VALUED_GLOBAL` with its value, and
# redirections, as in `git -C . pus{h,}` or `git 2>&1 pus{h,}`. The value of an option such as the
# `$dir` of `git -C $dir log` is no subcommand.
VALUED_GLOBAL = r"(?:-C|-c|--git-dir|--work-tree|--namespace|--exec-path|--config-env)"
GIT_EXPANDED = re.compile(
    r"git(?![\w.-])"
    rf"(?:[ \t]+(?:{VALUED_GLOBAL}[ \t]+\S+|(?!{VALUED_GLOBAL}(?:[ \t]|$))-\S*"
    r"|\d*[<>]+[&|]?(?:[ \t]+)?\S+)){0,8}"
    r"[ \t]+[^\s-]\S*?[$`{]",
    re.IGNORECASE,
)
# A word that ends in `git` and, in the subcommand's place after the global options as
# GIT_EXPANDED reads them, a name that git can read as an alias, as group 1 (`may_be_unknown`).
GIT_NAMED = re.compile(
    r"git(?![\w.-])"
    rf"(?:[ \t]+(?:{VALUED_GLOBAL}[ \t]+\S+|(?!{VALUED_GLOBAL}(?:[ \t]|$))-\S*"
    r"|\d*[<>]+[&|]?(?:[ \t]+)?\S+)){0,8}"
    r"[ \t]+([A-Za-z0-9][A-Za-z0-9-]*)(?![^\s;&|)])",
    re.IGNORECASE,
)
# A lease option, which only `git push` takes (`unread_write`).
LEASE_WORD = re.compile(r"(?<![\w-])--force-w")
# An option that defines a git alias, `-c alias.<name>=…` or `--config-env=alias.<name>=…`; git
# reads the names of a configuration key in any case.
ALIAS = re.compile(r"alias\.", re.IGNORECASE)
# The global options of `git` that set a configuration value, `<key>=<value>` in the next word.
CONFIGURING = ("-c", "--config-env")
# An assignment of a variable that gives git configuration, and so can define an alias:
# `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_<n>`, `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_GLOBAL`, ….
CONFIG_VARIABLE = re.compile(r"GIT_CONFIG\w*=")
# The subcommands that git builds in (`git --list-cmds=builtins`, git 2.54). git takes no alias of
# such a name, so only another subcommand can be an alias (`alias_writes`).
BUILTINS = frozenset(
    [
        "add",
        "am",
        "annotate",
        "apply",
        "archive",
        "backfill",
        "bisect",
        "blame",
        "branch",
        "bugreport",
        "bundle",
        "cat-file",
        "check-attr",
        "check-ignore",
        "check-mailmap",
        "check-ref-format",
        "checkout",
        "checkout--worker",
        "checkout-index",
        "cherry",
        "cherry-pick",
        "clean",
        "clone",
        "column",
        "commit",
        "commit-graph",
        "commit-tree",
        "config",
        "count-objects",
        "credential",
        "credential-cache",
        "credential-cache--daemon",
        "credential-store",
        "describe",
        "diagnose",
        "diff",
        "diff-files",
        "diff-index",
        "diff-pairs",
        "diff-tree",
        "difftool",
        "fast-export",
        "fast-import",
        "fetch",
        "fetch-pack",
        "fmt-merge-msg",
        "for-each-ref",
        "for-each-repo",
        "format-patch",
        "fsck",
        "fsck-objects",
        "fsmonitor--daemon",
        "gc",
        "get-tar-commit-id",
        "grep",
        "hash-object",
        "help",
        "history",
        "hook",
        "index-pack",
        "init",
        "init-db",
        "interpret-trailers",
        "last-modified",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "mailinfo",
        "mailsplit",
        "maintenance",
        "merge",
        "merge-base",
        "merge-file",
        "merge-index",
        "merge-ours",
        "merge-recursive",
        "merge-recursive-ours",
        "merge-recursive-theirs",
        "merge-subtree",
        "merge-tree",
        "mktag",
        "mktree",
        "multi-pack-index",
        "mv",
        "name-rev",
        "notes",
        "pack-objects",
        "pack-redundant",
        "pack-refs",
        "patch-id",
        "pickaxe",
        "prune",
        "prune-packed",
        "pull",
        "push",
        "range-diff",
        "read-tree",
        "rebase",
        "receive-pack",
        "reflog",
        "refs",
        "remote",
        "remote-ext",
        "remote-fd",
        "repack",
        "replace",
        "replay",
        "repo",
        "rerere",
        "reset",
        "restore",
        "rev-list",
        "rev-parse",
        "revert",
        "rm",
        "send-pack",
        "shortlog",
        "show",
        "show-branch",
        "show-index",
        "show-ref",
        "sparse-checkout",
        "stage",
        "stash",
        "status",
        "stripspace",
        "submodule--helper",
        "switch",
        "symbolic-ref",
        "tag",
        "unpack-file",
        "unpack-objects",
        "update-index",
        "update-ref",
        "update-server-info",
        "upload-archive",
        "upload-archive--writer",
        "upload-pack",
        "var",
        "verify-commit",
        "verify-pack",
        "verify-tag",
        "version",
        "whatchanged",
        "worktree",
        "write-tree",
    ]
)
# A name that git can read as an alias.
ALIAS_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
# The aliases that `alias_writes` follows through, `pp` to `p` to `push`, and the lookups it makes
# in one process, so that a command of 1 MiB with many names costs a bounded number of `git` runs.
ALIAS_DEPTH = 4
ALIAS_LOOKUPS = 16

UNKNOWN = (
    "The check cannot tell the subcommand of this `git` call: the shell expands it, a `-c alias.*` "
    "option or a `GIT_CONFIG_*` variable can make it an alias, or the git configuration makes it "
    "an alias that can run a write. It can be a `push`, a `worktree` or a `cherry-pick`."
)

DENY_DEFAULT = """Refused: {command}

A lease push that names `{target}`, a default branch of `origin`, is refused in any form. Give
the user the command to run in their own terminal.
"""

DENY_UNNAMED = """Refused: {command}

A lease push through `{unnamed}` names no branch, so it can reach a default branch of `origin`.
Name the branch: `git push --force-with-lease origin <branch>`, or
`git push --force-with-lease origin HEAD:refs/heads/<branch>`.
"""

UNPLAIN = (
    "The guard allows a `git` write with no prompt only as plain text, which every shell reads the "
    "same way: no `$`, backslash, backtick, `#` or `!` outside a single quote."
)

ALONE = (
    "The guard allows `git {write}` only as a `git` command of its own, with no option before the "
    "subcommand and no operator: run it as a Bash call of its own, from the repository."
)


def git(directory: str, *arguments: str) -> str | None:
    """The stdout of `git -C <directory> <arguments>`, or None when git is missing, times out or
    exits with an error."""
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", directory, *arguments],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    return result.stdout if result.returncode == 0 else None


ALIASES: dict[tuple[str, str], bool] = {}


def alias_writes(directory: str, name: str) -> bool:
    """True when the subcommand `name`, in the repository of `directory`, is a git alias that can
    run a write of the check: one whose value, followed through at most ALIAS_DEPTH aliases, runs a
    shell (`!…`), holds `push`, `worktree` or `cherry-pick` as a word, or holds `$`, a backtick or
    a brace; also when the lookups of this process passed ALIAS_LOOKUPS. A builtin name is no alias,
    since git ignores an alias of it, and neither is a name for which git reports no alias."""
    key = (directory, name)
    if key in ALIASES:
        return ALIASES[key]
    if len(ALIASES) >= ALIAS_LOOKUPS:
        return True
    found, current = False, name
    for _ in range(ALIAS_DEPTH):
        if current in BUILTINS or ALIAS_NAME.fullmatch(current) is None:
            break
        value = git(directory, "config", "--get", f"alias.{current}")
        if value is None:
            break
        value = value.strip()
        if value.startswith("!") or KEYWORD_WORD.search(value) or not EXPANSIONS.isdisjoint(value):
            found = True
            break
        current = value.split(maxsplit=1)[0] if value else ""
    else:
        found = True
    ALIASES[key] = found
    return found


def in_worktree(path: Place) -> bool:
    """True when `path` lies below `~/Research/.worktrees/`: a worktree, or a directory in one."""
    return below(path, WORKTREES)


def own_origin(directory: str) -> bool:
    """True when `origin` has push URLs and each is a GitHub repository of an own organisation."""
    urls = git(directory, "remote", "get-url", "--push", "--all", "origin")
    if not urls or not urls.split():
        return False
    owners = [GITHUB.match(url) for url in urls.split()]
    return all(found is not None and found.group(1).lower() in own_organisations() for found in owners)


def worktree_path(arguments: list[str], cwd: str) -> str | None:
    """The path text of the worktree of `git worktree remove <arguments>`, or None: anything but one
    force flag and one path below `~/Research/.worktrees/`. The path is resolved against `cwd`
    without following its last name, as `rm_scope.resolve` does."""
    forces = [word for word in arguments if word in ("--force", "-f")]
    operands = [word for word in arguments if not word.startswith("-")]
    if len(forces) != 1 or len(operands) != 1 or len(forces) + len(operands) != len(arguments):
        return None
    found = resolve(operands[0], place(cwd, "real"))
    return found.text() if found is not None and in_worktree(found) else None


def loss(path: str) -> str | None:
    """What a forced removal of the worktree `path` loses, as the reason to ask, or None: commits of
    HEAD on no remote-tracking ref, and tracked files that are modified or staged."""
    head = git(path, "rev-parse", "--verify", "HEAD")
    containing = git(path, "for-each-ref", "--contains", "HEAD", "--format=%(refname)", "refs/remotes")
    status = git(path, "status", "--porcelain", "--untracked-files=no")
    if head is None or containing is None or status is None:
        return f"The check cannot read the HEAD, the remote refs or the status of the worktree `{path}`."
    if not containing.strip():
        return (
            f"The forced removal would lose commits: HEAD {head.strip()[:12]} of `{path}` is on no "
            "remote ref. Push the branch first."
        )
    changed = [line[3:] for line in status.splitlines() if line.strip()]
    if changed:
        more = len(changed) - NAMED
        named = ", ".join(changed[:NAMED]) + (f" and {more} more" if more > 0 else "")
        return (
            f"The forced removal would lose changes to tracked files of `{path}`: {named}. Commit or "
            "discard them first."
        )
    return None


def worktree_remove(arguments: list[str], cwd: str) -> Verdict:
    """The verdict on `git worktree remove <arguments>`, whose arguments hold an option."""
    path = worktree_path(arguments, cwd)
    if path is None:
        return Verdict(
            "ask",
            "The check allows `git worktree remove` only with one `--force` or `-f` and one path "
            "below `~/Research/.worktrees/`.",
        )
    reason = loss(path)
    if reason is not None:
        return Verdict("ask", reason)
    return Verdict("allow", "The worktree's HEAD is on a remote ref, and no tracked file is changed.")


def cherry_pick(cwd: str) -> Verdict:
    """The verdict on `git cherry-pick` in the working directory `cwd`."""
    if in_worktree(place(cwd, "real")) or own_origin(cwd):
        return Verdict("allow", "A cherry-pick in a worktree or in a checkout of an own organisation.")
    return Verdict(
        "ask", "`git cherry-pick` outside a worktree and outside a checkout of an own organisation."
    )


def pushed_branch(arguments: list[str], cwd: str) -> tuple[str, str, str] | str:
    """(lease, refspec, branch) of `git push <arguments>`, or the reason to ask: anything but
    SHAPE, or a `<branch>` that names no local branch."""
    if len(arguments) != len(("lease", "origin", "refspec")) or not arguments[0].startswith(LEASE):
        return f"The check allows a lease push only as {SHAPE}."
    lease, remote, refspec = arguments
    branch = refspec.removeprefix("HEAD:refs/heads/")
    if remote != "origin" or not BRANCH.match(branch):
        return f"The check allows a lease push only as {SHAPE}."
    if branch == refspec:
        if git(cwd, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}") is None:
            return f"`{branch}` names no local branch, so the check cannot tell what the push updates."
        # A `remote.origin.push` refspec can map `<branch>` onto another remote branch.
        mapped = git(cwd, "config", "--default", "", "--get", "remote.origin.push")
        if mapped is None or mapped.strip():
            return (
                "`origin` has a `remote.origin.push` refspec, which can push the branch to another "
                f"remote branch: name the target as `HEAD:refs/heads/{branch}`."
            )
    return lease, refspec, branch


def lease_push(arguments: list[str], cwd: str) -> Verdict:
    """The verdict on `git push <arguments>`, whose arguments hold a lease."""
    found = pushed_branch(arguments, cwd)
    if isinstance(found, str):
        return Verdict("ask", found)
    lease, _, branch = found
    named = lease.removeprefix(LEASE)
    if named and named.removeprefix("=").split(":", 1)[0] not in (branch, f"refs/heads/{branch}"):
        return Verdict("ask", f"The lease `{lease}` does not name the pushed branch `{branch}`.")
    if not own_origin(cwd):
        return Verdict("ask", "`origin` is not a GitHub repository of an own organisation.")
    return Verdict("allow", "A lease push of a branch other than the default one, to an own organisation.")


def defaults_of(cwd: str | None) -> frozenset[str]:
    """`main`, `master` and the branch that `refs/remotes/origin/HEAD` of `cwd` names."""
    default = (
        None if cwd is None else git(cwd, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    )
    return DEFAULTS | ({default.strip().removeprefix("origin/")} if default else frozenset[str]())


def moved(directory: str | None, path: str) -> str | None:
    """The directory `path`, with a leading `~` or `$HOME` expanded, resolved against `directory`;
    None when the shell would expand anything else in it, or when a relative `path` meets an
    unknown `directory`."""
    found = expand(path)
    if found is None or (directory is None and not found.startswith("/")):
        return None
    return str(PurePosixPath(directory or "/", found))


def repository_of(words: list[str], directory: str | None) -> str | None:
    """The directory whose repository the `git` call `words` works on: `directory`, moved by each
    `-C <path>` and `--git-dir[=]<path>` before the subcommand, as `git` moves it."""
    index = 1
    while index < len(words) and words[index].startswith("-"):
        option, _, attached = words[index].partition("=")
        value = attached or (words[index + 1] if index + 1 < len(words) else "")
        if option in REPOSITORY:
            directory = moved(directory, value) if value else None
        index += 2 if words[index] in TAKES_VALUE else 1
    return directory


def positional(arguments: list[str]) -> list[str]:
    """The arguments of a `git push` that are neither an option nor the value of one (`valued`):
    the remote and the refspecs."""
    return [
        argument
        for index, argument in enumerate(arguments)
        if not argument.startswith("-") and (index == 0 or not valued(arguments[index - 1]))
    ]


def default_target(arguments: list[str], defaults: frozenset[str]) -> str | None:
    """The first argument after a lease push's `push`, an option's value aside (`positional`),
    that names a branch of `defaults` as its target, `<branch>`, `+<branch>` or `<src>:<branch>`,
    each also with `refs/heads/` or with `heads/`, which `git` reads as `refs/heads/`; or None."""
    for argument in positional(arguments):
        target = argument.lstrip("+").rsplit(":", 1)[-1]
        target = (
            target.removeprefix("refs/heads/")
            if target.startswith("refs/")
            else target.removeprefix("heads/")
        )
        if target in defaults:
            return argument
    return None


def lease_option(argument: str) -> bool:
    """True when `argument` is a lease option, or an option that the shell can expand into one: the
    text before its first expansion (EXPANSIONS) is a prefix of the lease, as in `--force-$w`."""
    if argument.startswith("--force-w"):
        return True
    cut = next((index for index, char in enumerate(argument) if char in EXPANSIONS), None)
    return argument.startswith("-") and cut is not None and LEASE.startswith(argument[:cut])


def is_git(word: str) -> bool:
    """True when the program `word` is `git`, by its last name in any case: a file system that
    ignores case, as macOS's does, runs git for `GIT` and `/usr/bin/Git`."""
    return program(word) == "git"


def configuring(words: list[str]) -> int:
    """The index of the first word of `words` that assigns a variable of git configuration
    (CONFIG_VARIABLE), also as the operand of `export`; `len(words)` without one."""
    return next((index for index, word in enumerate(words) if CONFIG_VARIABLE.match(word)), len(words))


def subcommand(
    words: list[str], index: int, directory: str | None = None, configured: int | None = None
) -> tuple[int, bool]:
    """(the index of the subcommand, whether the check cannot know it) of the `git` call at
    `index` of `words`. The subcommand follows the global options, as `git` reads them. It is
    unknown when its word holds a character by which the shell expands it (EXPANSIONS), as
    `pus{h,}` or `${x}push` do; when a `-c` or `--config-env` option defines an alias; when a word
    before `index` assigns a variable of git configuration (`configuring`, which `configured`
    gives when the caller has it); and, with a `directory`, when the subcommand is a name that is
    no builtin and that the configuration of the repository of the call makes an alias that can
    run a write (`alias_writes`)."""
    at, alias = index + 1, False
    while at < len(words) and words[at].startswith("-"):
        option, _, attached = words[at].partition("=")
        if option in CONFIGURING:
            value = attached if attached else (words[at + 1] if at + 1 < len(words) else "")
            alias = alias or ALIAS.match(value) is not None
            at += 1 if attached else 2
        else:
            at += 2 if words[at] in TAKES_VALUE else 1
    if at >= len(words):
        return at, alias
    name = words[at]
    if alias or not EXPANSIONS.isdisjoint(name):
        return at, True
    if (configuring(words[:index]) if configured is None else configured) < index:
        return at, True
    if directory is None or name in BUILTINS:
        return at, False
    repository = repository_of(words[index:at], directory)
    return at, repository is not None and alias_writes(repository, name)


def writes(words: list[str], directory: str | None = None) -> Iterator[tuple[str, int, int]]:
    """(the write, the index of its `git`, the index of its first argument) for each `git` call of
    `words` that holds a write of the check, in order: `cherry-pick`; `worktree remove` with any
    option after it, since `git` reads `-ff` and a prefix of `--force` as a force flag; or `push`
    with an option after it that begins as a lease does, or that can expand into one
    (`lease_option`). A call whose subcommand the check cannot know (`subcommand`) is a `push`
    when such an option follows it, and a `cherry-pick` otherwise, which takes any arguments. The
    arguments of a call run to the end of `words`. It reads each word once for the options, so
    that a long command costs it no time per `git`. `directory` is the working directory of
    `words`, in which `subcommand` looks up an alias."""
    options = [index for index, word in enumerate(words) if word.startswith("-")]
    last_option = options[-1] if options else -1
    last_lease = next((index for index in reversed(options) if lease_option(words[index])), -1)
    configured = configuring(words)
    for index, word in enumerate(words):
        if not is_git(word):
            continue
        at, unknown = subcommand(words, index, directory, configured)
        name = words[at] if at < len(words) else None
        if unknown:
            yield ("push" if last_lease > at else "cherry-pick"), index, at + 1
        elif name == "cherry-pick":
            yield "cherry-pick", index, at + 1
        elif name == "worktree" and words[at + 1 : at + 2] == ["remove"] and last_option > at + 1:
            yield "worktree remove", index, at + 2
        elif name == "push" and last_lease > at:
            yield "push", index, at + 1


def valued(word: str) -> bool:
    """True when `git push` takes the word after `word` as the value of an option: an option of
    VALUED or a prefix of one, or a cluster of short options that ends in `-o`."""
    if word.startswith("--"):
        return len(word) > len("--") and any(name.startswith(word) for name in VALUED)
    return SHORT_VALUED.fullmatch(word) is not None


def unnamed_target(arguments: list[str]) -> str | None:
    """The argument through which a lease push with `arguments` can reach a branch that it does not
    name, or None: no refspec after the remote (the text "no refspec"), as with `--all` or
    `--mirror`; or a refspec whose target is `HEAD`, `@` or empty, or that holds a glob, a brace,
    `$` or a backtick. The value of an option, as `valued` finds it, is no refspec."""
    named = positional(arguments)
    if len(named) < len(("remote", "refspec")):
        return "no refspec"
    for refspec in named[1:]:
        target = refspec.lstrip("+").rsplit(":", 1)[-1]
        if target in ("HEAD", "@", "") or set(refspec) & set("*?[{$`"):
            return refspec
    return None


def located(tokens: Tokens, cwd: str | None) -> Iterator[tuple[list[str], str | None]]:
    """(the words, the working directory) of each part of the command, the directory moved by each
    `cd` and `pushd` before the part (`moved`)."""
    directory = cwd
    for words in parts(unredirected(tokens)):
        if words[0] in ("cd", "pushd"):
            directory = moved(directory, words[1] if len(words) > 1 else "~")
        yield words, directory


def push_refusal(tokens: Tokens, cwd: str | None) -> Verdict | None:
    """The denial of a lease push in any part of the command that names a default branch as its
    target, or that can reach one without naming it; or None."""
    command = " ".join(text for _, text in tokens)
    for words, directory in located(tokens, cwd):
        # The first lease push of the part, also after another write, as in `find -exec`.
        found = next((write for write in writes(words, directory) if write[0] == "push"), None)
        if found is None:
            continue
        pushed = words[found[2] :]
        repository = repository_of(words[found[1] :], directory)
        defaults = defaults_of(cwd) | (defaults_of(repository) if repository != cwd else DEFAULTS)
        target = default_target(pushed, defaults)
        if target is not None:
            return Verdict("deny", DENY_DEFAULT.format(command=command, target=target))
        unnamed = unnamed_target(pushed)
        if unnamed is not None:
            return Verdict("deny", DENY_UNNAMED.format(command=command, unnamed=unnamed))
    return None


def moved_write(tokens: Tokens, cwd: str | None) -> Verdict:
    """The verdict on a command in which `writes`, in `cwd`, finds no write: a write in a part
    whose directory a `cd` moved (`located`) can only come from an alias of that directory, so it
    is unknown; PASS without one."""
    if not any(
        next(writes(part, directory), None) is not None
        for part, directory in located(tokens, cwd)
        if directory not in (cwd, None)
    ):
        return PASS
    return push_refusal(tokens, cwd) or Verdict("ask", UNKNOWN)


def decide(tokens: Tokens, cwd: str | None) -> Verdict:
    """The verdict on one reading of the command. A redirection's target is no word of a call
    (`unredirected`), but a redirection keeps the call from being alone. A write that only an alias
    of a directory that a `cd` moved to makes (`located`) is unknown and never alone."""
    words = [text for kind, text in unredirected(tokens) if kind == "word"]
    found = next(writes(words, cwd), None)
    if found is None:
        return moved_write(tokens, cwd)
    write, index, first = found
    arguments = words[first:]
    refusal = push_refusal(tokens, cwd)
    if refusal is not None:
        return refusal
    unknown = subcommand(words, index, cwd)[1]
    alone = len(words) == len(tokens) and index == 0 and words[0] == "git" and words[1] == write.split()[0]
    if unknown or not alone or cwd is None:
        return Verdict(
            "ask",
            UNKNOWN
            if unknown
            else ALONE.format(write=write)
            if not alone
            else f"The check reads `git {write}` against the working directory, and the call names none.",
        )
    if write == "cherry-pick":
        return cherry_pick(cwd)
    if write == "worktree remove":
        return worktree_remove(arguments, cwd)
    return lease_push(arguments, cwd)


def may_be_unknown(keywords: str) -> bool:
    """True when the `joined` text `keywords` holds a word that ends in `git` (GIT_WORD) and after
    it a character by which the shell expands a word (EXPANSIONS), an alias option (ALIAS), a
    variable of git configuration (CONFIG_VARIABLE), or, as the subcommand, a name that is no
    builtin (GIT_NAMED), so that a `git` call in it can have a subcommand that the check cannot
    know (`subcommand`)."""
    first_git = GIT_WORD.search(keywords)
    if first_git is None:
        return False
    rest = keywords[first_git.end() :]
    return (
        not EXPANSIONS.isdisjoint(rest)
        or ALIAS.search(rest) is not None
        or CONFIG_VARIABLE.search(keywords) is not None
        or any(found.group(1) not in BUILTINS for found in GIT_NAMED.finditer(keywords, first_git.start()))
    )


def unread_write(command: str, keywords: str) -> bool:
    """True when `command`, which `readings` cannot read, may hold a write of the check: a `$`
    before a quote or a backslash (ANSI_C_OPENER); or in its `joined` text `keywords` a word that
    ends in `git` (GIT_WORD), in any case, and after it, on any line, a keyword as a word of its
    own (KEYWORD_WORD) or an alias option (ALIAS); or such a word and right after it a word that
    the shell expands (GIT_EXPANDED), as `git pus{h,}` holds. A keyword in a heredoc body or a
    path with no `git` before it is none, and so is a `$` that does not follow `git` as its next
    word, as in the Julia line `s = "$x"`. An ANSI-C quote decodes its escapes into a word, as
    `$'\\x67it'` gives `git`, and `joined` decodes it only where its quotes pair as the shell pairs
    them. With no ANSI-C quote, a `git` call with a write of `writes` leaves in the `joined` text a
    word that ends in `git`, also where `joined` glues it to the line before, and its keyword after
    it, so the narrowing keeps each write that the check reads whose subcommand stands right after
    `git` or is a keyword."""
    if ANSI_C_OPENER.search(command) is not None or GIT_EXPANDED.search(keywords) is not None:
        return True
    first_git = GIT_WORD.search(keywords)
    if first_git is None:
        return False
    return (
        KEYWORD_WORD.search(keywords, first_git.end()) is not None
        or ALIAS.search(keywords, first_git.end()) is not None
        or LEASE_WORD.search(keywords, first_git.end()) is not None
    )


def check(call: Call) -> Verdict:
    """Allow a forced worktree removal, a cherry-pick and a lease push where nothing is lost; ask
    otherwise."""
    command = call.command
    keywords = joined(command)
    if call.action != "shell" or not (
        any(key in keywords for key in ("cherry-pick", "worktree", "push")) or may_be_unknown(keywords)
    ):
        return PASS
    found = readings(command, nested=True)
    if found is None:
        if not unread_write(command, keywords):
            return PASS
        return Verdict("ask", "The check cannot read a command that may hold a git write.")
    verdict = strongest(decide(tokens, call.cwd) for tokens in found)
    if verdict.decision == "allow" and PLAIN.fullmatch(command) is None:
        return Verdict("ask", UNPLAIN)
    return verdict
