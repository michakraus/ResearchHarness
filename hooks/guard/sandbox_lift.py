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
reads: a `#` anywhere in the line, which PLAIN admits only inside quotes, kept inside so that no
reading of a comment can differ from a shell's; a part that `exposed` or `path_screened` refuses;
an assignment or a path in front of a program, unless the part is a `cd` to the working directory;
and a git option before the subcommand that takes a value, `-C` aside, or `--config-env`, which
can name a program to run or another repository.

One more line is lifted, which Claude Code's rule keeps inside: the installed worktree hook's
`add <name>` or `remove <path>` (`worktree_call`), so that Antigravity can make and remove a
worktree, whose git writes `.git` and `.githooks`, which its sandbox denies. The line is exactly

    /usr/bin/env -i HOME=<home> PATH=<WORKTREE_PATH> <python> -E -s <hook> add|remove <word>

single spaces, with `<home>` the home of this process, `<python>` the interpreter of the harness's
Python environment and `<hook>` the installed hook, each by its absolute path below that home, and
`<word>` of WORKTREE_WORD: no `cd`, other assignment, redirection, pipe, quote, `~` or second
argument. The lifted call runs with the environment of the agent's process: `env -i` clears every
inherited variable, so no PATH, HOME, XDG_CONFIG_HOME or GIT_* reaches the hook's git; `-E`
ignores the PYTHON* variables and `-s` the user site directory. Antigravity's sandbox cannot write
the interpreter, the hook or a directory of WORKTREE_PATH. Antigravity, the app and `agy` alike,
runs each `run_command` in a new shell, which keeps no variable, function or alias of an earlier
call, so no earlier call can define a function or an alias `/usr/bin/env`. Both together make the
lifted program the installed one; the hook itself checks the name, the path and the repository. A
frontend whose terminal keeps its shell between calls breaks this: there an earlier call can
define such a function, and the lift must not apply.
"""

import re
from pathlib import Path

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
# The one argument of a lifted worktree hook call: a branch name or a path of plain characters,
# which no shell expands.
WORKTREE_WORD = r"[A-Za-z0-9._/-]+"
# The PATH of a lifted worktree hook call, that of launchagents/worktree-sweep.plist: directories
# that no session can write.
WORKTREE_PATH = "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def worktree_call(command: str) -> bool:
    """Whether `command` is exactly `/usr/bin/env -i HOME=<home> PATH=<WORKTREE_PATH> <python> -E
    -s <hook> add <name>` or `... remove <path>`, with `<home>` the home of this process, with one
    leading `/`, and `<python>` and `<hook>` the interpreter of the harness's Python environment and
    the installed worktree hook, each by its absolute path below that home."""
    home = Path.home()
    if not home.is_absolute():
        return False
    home = Path("/" + str(home).lstrip("/"))
    python = home / ".local" / "share" / "research-harness" / "python" / "bin" / "python"
    hook = home / ".claude" / "hooks" / "worktree.py"
    env = f"/usr/bin/env -i HOME={home} PATH={WORKTREE_PATH}"
    line = (
        rf"{re.escape(env)} {re.escape(str(python))} -E -s {re.escape(str(hook))} "
        rf"(?:add|remove) {WORKTREE_WORD}"
    )
    return re.fullmatch(line, command) is not None


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
    or that is a worktree hook call (`worktree_call`), else `pass` with `keep`."""
    command = call.command
    if call.action == "shell" and worktree_call(command):
        return LIFT
    if call.action != "shell" or PLAIN.fullmatch(command) is None or "#" in command:
        return PASS
    read = readings(command)
    if read is None:
        return PASS
    cwd = None if call.cwd is None else place(call.cwd, "real")
    return LIFT if all(lifted(command, tokens, cwd) for tokens in read) else PASS
