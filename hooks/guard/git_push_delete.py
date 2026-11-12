"""Ask before a `git push` whose refspec has an empty source, which deletes the remote ref.

A refspec `:<ref>`, also `+:<ref>`, deletes `<ref>` on the remote; a lone `:` pushes the matching
branches. The check finds each `git` call of each part of the command, after the global options of
`git` such as `-C`, also behind another command as in `find -exec`, and reads each refspec of a
`push`: each argument after the remote that is neither an option nor the value of one
(`git_writes.positional`). A refspec whose source is empty asks. A command that holds `push` and
that the check cannot read asks too. It reads the command as `shell.readings` does with `nested`,
so a push in the script of `sh -c`, `bash -c` or `eval` is read as well.

A permission rule cannot state this without a warning of Claude Code: a literal `:` followed by a
wildcard is a `:*` that is not at the end of the rule, which Claude Code reports at each start. The
`ask` rules of the settings template keep `--delete`, `-d` and `--prune`.
"""

from pathlib import PurePosixPath

from .contract import PASS, Call, Verdict, strongest
from .git_writes import positional
from .rm_scope import TAKES_VALUE
from .shell import Tokens, joined, parts, readings

REASON = (
    "The refspec `{refspec}` has an empty source, so the push deletes `{target}` on the remote. A "
    "deletion on a remote is the user's decision."
)

MATCHING = (
    "The refspec `{refspec}` pushes every matching branch, so it can update a branch that the "
    "command does not name."
)

UNREAD = "The check cannot read a command that may hold a `git push` with a deleting refspec."


def pushed(words: list[str]) -> list[list[str]]:
    """The arguments after `push` of each `git push` call in the part `words`; each call's
    arguments run to the end of the part."""
    found: list[list[str]] = []
    for index, word in enumerate(words):
        if PurePosixPath(word).name != "git":
            continue
        at = index + 1
        while at < len(words) and words[at].startswith("-"):
            at += 2 if words[at] in TAKES_VALUE else 1
        if words[at : at + 1] == ["push"]:
            found.append(words[at + 1 :])
    return found


def deleting(arguments: list[str]) -> str | None:
    """The first refspec after the remote of `git push <arguments>` whose source is empty, or None."""
    return next(
        (refspec for refspec in positional(arguments)[1:] if refspec.lstrip("+").startswith(":")), None
    )


def verdict_of(tokens: Tokens) -> Verdict:
    """The verdict on one reading of the command."""
    for words in parts(tokens):
        for arguments in pushed(words):
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
    if call.action != "shell" or "push" not in keywords or ":" not in keywords:
        return PASS
    found = readings(command, nested=True)
    if found is None:
        return Verdict("ask", UNREAD)
    return strongest(verdict_of(tokens) for tokens in found)
