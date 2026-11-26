"""Ask before a `git push` whose refspec has an empty source, which deletes the remote ref.

A refspec `:<ref>`, also `+:<ref>`, deletes `<ref>` on the remote; a lone `:` pushes the matching
branches. The check finds each `git` call of each part of the command, after the global options of
`git` such as `-C`, also behind another command as in `find -exec`, as `git_writes.is_git` and
`git_writes.subcommand` find them: `GIT` and `git 2>&1 push` count, and a subcommand that the
check cannot know, as in `git pus{h,}` or an alias of the git configuration of the part's
repository that can run a write, is read as a `push`. It reads each refspec of a
`push`: each argument after the remote that is neither an option nor the value of one
(`git_writes.positional`). A refspec whose source is empty asks. A command that holds `push` and
that the check cannot read asks too when it can hold a `git push`, as `git_writes.unread_write`
finds it; a Julia heredoc with `push!` and a range `1:n` passes. It reads the command as
`shell.readings` does with `nested`, so a push in the script of `sh -c`, `bash -c` or `eval` is
read as well.

A permission rule cannot state this without a warning of Claude Code: a literal `:` followed by a
wildcard is a `:*` that is not at the end of the rule, which Claude Code reports at each start. The
`ask` rules of the settings template keep `--delete`, `-d` and `--prune`.
"""

from .contract import PASS, Call, Verdict, strongest
from .git_writes import configuring, is_git, located, may_be_unknown, positional, subcommand, unread_write
from .shell import Tokens, joined, readings

REASON = (
    "The refspec `{refspec}` has an empty source, so the push deletes `{target}` on the remote. A "
    "deletion on a remote is the user's decision."
)

MATCHING = (
    "The refspec `{refspec}` pushes every matching branch, so it can update a branch that the "
    "command does not name."
)

UNREAD = "The check cannot read a command that may hold a `git push` with a deleting refspec."


def pushed(words: list[str], directory: str | None = None) -> list[list[str]]:
    """The arguments after `push` of each `git push` call in the part `words`, and after the
    subcommand of each `git` call whose subcommand the check cannot know
    (`git_writes.subcommand`, which looks up an alias in `directory`); each call's arguments run
    to the end of the part."""
    found: list[list[str]] = []
    configured = configuring(words)
    for index, word in enumerate(words):
        if not is_git(word):
            continue
        at, unknown = subcommand(words, index, directory, configured)
        if unknown or words[at : at + 1] == ["push"]:
            found.append(words[at + 1 :])
    return found


def deleting(arguments: list[str]) -> str | None:
    """The first refspec after the remote of `git push <arguments>` whose source is empty, or None."""
    return next(
        (refspec for refspec in positional(arguments)[1:] if refspec.lstrip("+").startswith(":")), None
    )


def verdict_of(tokens: Tokens, cwd: str | None = None) -> Verdict:
    """The verdict on one reading of the command, whose working directory is `cwd`."""
    for words, directory in located(tokens, cwd):
        for arguments in pushed(words, directory):
            refspec = deleting(arguments)
            if refspec is not None:
                target = refspec.lstrip("+")[1:]
                text = (
                    REASON.format(refspec=refspec, target=target)
                    if target
                    else MATCHING.format(refspec=refspec)
                )
                return Verdict("ask", text)
    return PASS


def check(call: Call) -> Verdict:
    """Ask before a `git push` with a refspec whose source is empty."""
    command = call.command
    keywords = joined(command)
    if call.action != "shell" or ":" not in keywords or not ("push" in keywords or may_be_unknown(keywords)):
        return PASS
    found = readings(command, nested=True)
    if found is None:
        return Verdict("ask", UNREAD) if unread_write(command, keywords) else PASS
    return strongest(verdict_of(tokens, call.cwd) for tokens in found)
