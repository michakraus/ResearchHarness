"""Allow three `git` writes when the repository shows that nothing is lost; ask otherwise.

The check allows only a command that is one `git` call and nothing else: no operator, no
redirection, no second part, no global option before the subcommand. It reads the state of the
repository with `git` in the call's working directory, the payload's `cwd`.

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
    command, so also `git fetch && git push --force-with-lease origin main`. A push names a
    default branch when an argument after `push` names `main`, `master` or the branch that
    `refs/remotes/origin/HEAD` names as its target (`<branch>`, `+<branch>`, `<src>:<branch>`,
    each also with `refs/heads/` or `heads/`). It names no branch, and can reach a default one,
    with `--all`, `--branches` or `--mirror`, with no refspec after the remote, or with a refspec
    whose target is `HEAD`, `@` or empty, or that holds a glob, `$` or a backtick. The value of
    `-o`, `--push-option`, `--repo`, `--receive-pack` or `--exec` is no refspec.

The check finds the subcommand as `git` does, after its global options. It takes a `worktree
remove` with any option as forced, since `git` reads `-ff` and a prefix of `--force` as force, and a
`push` with an option that begins with `--force-w` as a lease push. In the `<branch>` form the
branch must be a local one, and `origin` must have no `remote.origin.push` refspec, which can map
the branch onto another remote branch. Any other command that holds one of these writes asks:
`-C`, a `cd` before it, a pipeline, `-f` twice, a lease after the remote, a second refspec. A
`deny` rule of the settings template still refuses those it names, such as a plain `--force`.
`git` that cannot be run, or that fails, asks.

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
from pathlib import PurePosixPath

from .contract import PASS, Call, Verdict, strongest
from .gh_api_writes import own_organisations
from .paths import Place, place
from .rm_scope import WORKTREES, below, git_subcommand, resolve
from .shell import Tokens, parts, readings

# Seconds for each `git` the check runs.
TIMEOUT = 5

# A GitHub URL, with the owner as group 1.
GITHUB = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([A-Za-z0-9-]+)/[A-Za-z0-9._-]+?(?:\.git)?/?$"
)
# The quotes and the backslashes, each with the newline after it, that the pre-filter removes.
JOINS = re.compile(r"[\"']|\\\n?")
# A branch name the check reads; anything else asks.
BRANCH = re.compile(r"^(?!-)(?!HEAD$)[A-Za-z0-9._/-]+$")
DEFAULTS = frozenset({"main", "master"})
# The options of `git push` that push branches that no refspec names.
SPREAD = frozenset({"--all", "--branches", "--mirror"})
# The options of `git push` that take the next word as their value.
VALUED = frozenset({"-o", "--push-option", "--repo", "--receive-pack", "--exec"})
LEASE = "--force-with-lease"
SHAPE = "`git push --force-with-lease[=<ref>[:<expect>]] origin <branch>`, or with `HEAD:refs/heads/<branch>`"
# The changed files that a reason names.
NAMED = 5

DENY_DEFAULT = """Refused: {command}

A lease push that names `{target}`, a default branch of `origin`, is refused in any form. Give
the user the command to run in their own terminal.
"""

DENY_UNNAMED = """Refused: {command}

A lease push through `{unnamed}` names no branch, so it can reach a default branch of `origin`.
Name the branch: `git push --force-with-lease origin <branch>`, or
`git push --force-with-lease origin HEAD:refs/heads/<branch>`.
"""

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


def default_target(arguments: list[str], defaults: frozenset[str]) -> str | None:
    """The first argument after a lease push's `push` that names a branch of `defaults` as its
    target, `<branch>`, `+<branch>` or `<src>:<branch>`, each also with `refs/heads/` or with
    `heads/`, which `git` reads as `refs/heads/`; or None."""
    for argument in arguments:
        target = argument.lstrip("+").rsplit(":", 1)[-1]
        target = (
            target.removeprefix("refs/heads/")
            if target.startswith("refs/")
            else target.removeprefix("heads/")
        )
        if not argument.startswith("-") and target in defaults:
            return argument
    return None


def write_of(words: list[str]) -> tuple[str, int, list[str]] | None:
    """(the write, the index of its `git`, its arguments) for the first `git` call of `words` that
    holds a write of the check, or None: `cherry-pick`; `worktree remove` with any option, since
    `git` reads `-ff` and a prefix of `--force` as a force flag; or `push` with an option that
    begins as a lease does."""
    for index, word in enumerate(words):
        if PurePosixPath(word).name != "git":
            continue
        subcommand, arguments, _ = git_subcommand(words[index:])
        if subcommand == "cherry-pick":
            return "cherry-pick", index, arguments
        if (
            subcommand == "worktree"
            and arguments[:1] == ["remove"]
            and any(argument.startswith("-") for argument in arguments[1:])
        ):
            return "worktree remove", index, arguments[1:]
        if subcommand == "push" and any(argument.startswith("--force-w") for argument in arguments):
            return "push", index, arguments
    return None


def unnamed_target(arguments: list[str]) -> str | None:
    """The argument through which a lease push with `arguments` can reach a branch that it does not
    name, or None: `--all`, `--branches` or `--mirror`; no refspec after the remote (the text "no
    refspec"); or a refspec whose target is `HEAD`, `@` or empty, or that holds a glob, `$` or a
    backtick. The value of an option of VALUED is no refspec."""
    spread = next((argument for argument in arguments if argument in SPREAD), None)
    if spread is not None:
        return spread
    positional: list[str] = []
    for index, argument in enumerate(arguments):
        if not argument.startswith("-") and (index == 0 or arguments[index - 1] not in VALUED):
            positional.append(argument)
    if len(positional) < len(("remote", "refspec")):
        return "no refspec"
    for refspec in positional[1:]:
        target = refspec.lstrip("+").rsplit(":", 1)[-1]
        if target in ("HEAD", "@", "") or set(refspec) & set("*$`"):
            return refspec
    return None


def push_refusal(tokens: Tokens, cwd: str | None) -> Verdict | None:
    """The denial of a lease push in any part of the command that names a default branch as its
    target, or that can reach one without naming it; or None."""
    command = " ".join(text for _, text in tokens)
    for words in parts(tokens):
        found = write_of(words)
        if found is None or found[0] != "push":
            continue
        pushed = found[2]
        target = default_target(pushed, defaults_of(cwd))
        if target is not None:
            return Verdict("deny", DENY_DEFAULT.format(command=command, target=target))
        unnamed = unnamed_target(pushed)
        if unnamed is not None:
            return Verdict("deny", DENY_UNNAMED.format(command=command, unnamed=unnamed))
    return None


def decide(tokens: Tokens, cwd: str | None) -> Verdict:
    """The verdict on one reading of the command."""
    words = [text for kind, text in tokens if kind == "word"]
    found = write_of(words)
    if found is None:
        return PASS
    write, index, arguments = found
    refusal = push_refusal(tokens, cwd)
    if refusal is not None:
        return refusal
    alone = len(words) == len(tokens) and index == 0 and words[0] == "git" and words[1] == write.split()[0]
    if not alone or cwd is None:
        return Verdict(
            "ask",
            ALONE.format(write=write)
            if not alone
            else f"The check reads `git {write}` against the working directory, and the call names none.",
        )
    if write == "cherry-pick":
        return cherry_pick(cwd)
    if write == "worktree remove":
        return worktree_remove(arguments, cwd)
    return lease_push(arguments, cwd)


def check(call: Call) -> Verdict:
    """Allow a forced worktree removal, a cherry-pick and a lease push where nothing is lost; ask
    otherwise."""
    command = call.command
    # The shell joins `--force-""with-lease` and `--force-\<newline>with-lease` into one word.
    joined = JOINS.sub("", command)
    if call.action != "shell" or not any(key in joined for key in ("cherry-pick", "worktree", "--force-w")):
        return PASS
    found = readings(command)
    if found is None:
        return Verdict("ask", "The check cannot read a command that may hold a git write.")
    return strongest(decide(tokens, call.cwd) for tokens in found)
