"""Lift a shell command out of the frontend's sandbox only where Claude Code's sandbox would lift it.

The check gives `sandbox: lift` to a shell call when `top_level` of `sandbox_semantics`, Claude
Code's rule for `sandbox.excludedCommands`, finds no reason to keep it inside (every part led by
`git`, `gh`, `glab` or `ps`, and no file redirected), in every reading of `shell.readings`, and
none of the screens below applies; else `keep`. Its decision is always `pass`: it grants no call,
and the table of a frontend with a sandbox of its own reads its `sandbox` alone.

The first screen lifts only text whose reading is certain in sh, bash and zsh: the whole line
matches the closed grammar PLAIN, else it stays inside. The three shells split such a line into
the same commands, though a word can still expand in one of them alone, as zsh's `=ls` does. So no
quote, expansion or glob that the rule reads in another way than a shell can hide a program from
the rule, except a word in front of the program: zsh runs `ls` for `=ls git status`, where the rule
reads `git`, and the screen of an assignment below keeps that line inside. A line that no reading
reads stays inside.

The other screens keep inside a command that the rule lifts but whose program is not the one it
reads: a `#`, which starts a comment where a shell reads one and hides what follows; a NUL, which
no shell runs; a part that `exposed` or `path_screened` refuses; an assignment or a path in front
of a program, unless the part is a `cd` to the working directory; and a git option before the
subcommand that takes a value, `-C` aside, or `--config-env`, which can name a program to run or
another repository.
"""

import re

from .contract import PASS, Call, Verdict
from .paths import Place, place
from .sandbox_semantics import TAKES_VALUE, exposed, into_cwd, part_head, parts, path_screened, top_level
from .shell import Tokens, readings

# A command line that sh, bash and zsh split into the same commands: commands joined by `&&`, `||`,
# `;` or `|`, each of words separated by blanks. A word is `2>&1`, or pieces: a character of the set
# below, a single-quoted text with no `'`, or a double-quoted text with none of `"`, `$`, the
# backtick, `\` and `!`. No piece holds a NUL or a character outside ASCII. A word can still expand
# in one shell and not in another, as zsh's `=ls` and bash's `a=~/x` do.
WORD = r"""(?:2>&1|(?:[A-Za-z0-9_./:@%+,=~^-]|'[^'\x00\x80-\U0010ffff]*'|"[^"$`\\!\x00\x80-\U0010ffff]*")+)"""
COMMAND = rf"{WORD}(?:[ \t]+{WORD})*"
PLAIN = re.compile(rf"[ \t]*{COMMAND}(?:[ \t]*(?:&&|\|\||;|\|)[ \t]*{COMMAND})*[ \t]*")
# The git options before the subcommand that keep a command inside: each that takes a value but
# `-C`, and `--config-env`.
VALUED = (TAKES_VALUE - {"-C"}) | {"--config-env"}
LIFT = Verdict("pass", sandbox="lift")


def lifted(command: str, tokens: Tokens, cwd: Place | None) -> bool:
    """Whether the rule lifts the reading `tokens` of `command`, and no screen of a reading applies."""
    classified = top_level(tokens, cwd)
    heads, reason = classified
    if reason is not None:
        return False
    if exposed(command, classified) is not None or path_screened(heads) is not None:
        return False
    for words in parts(tokens)[0]:
        head, arguments = part_head(words)
        if words[0] != head and not into_cwd(head, arguments, cwd):
            return False
    for head, arguments in heads:
        index = 0
        while head == "git" and index < len(arguments) and arguments[index].startswith("-"):
            option = arguments[index]
            if option in VALUED or option.startswith(tuple(name + "=" for name in VALUED)):
                return False
            index += 2 if option in TAKES_VALUE else 1
    return True


def check(call: Call) -> Verdict:
    """`pass` with `sandbox: lift` for a shell call that the rule lifts and no screen keeps inside,
    else `pass` with `keep`."""
    command = call.command
    if call.action != "shell" or PLAIN.fullmatch(command) is None or "#" in command or "\0" in command:
        return PASS
    read = readings(command)
    if read is None:
        return PASS
    cwd = None if call.cwd is None else place(call.cwd, "real")
    return LIFT if all(lifted(command, tokens, cwd) for tokens in read) else PASS
