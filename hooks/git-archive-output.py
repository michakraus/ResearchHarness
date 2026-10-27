#!/usr/bin/env python3
"""Refuse `git archive -o` and `--output`, and name the commands that need no guarded write.

A `PreToolUse` hook on the `Bash` matcher. It reads the tool call on stdin, finds each
top-level `git … archive` call, and exits 2 when the call writes its archive with `-o` or
`--output`. The message on stderr gives the commands that do the same work with no prompt:
`base-tree.jl` for the tree of a commit in a new directory, `git show` for one file, and
`git ls-tree` for the list of files.

An agent writes the archive to read the unmodified tree of a commit, usually the base of its
branch. `git` runs outside the sandbox, so `-o` can write any path and the `ask` rules on it
prompt. A prompt for a read is a prompt with nothing to protect; the refusal sends the agent to
the read that needs no prompt. A tar file that is itself the result goes to the user.

No `permissions` glob can state this. Git takes the option clustered behind other short
options (`-vo out.tar`), with its value attached (`-oout.tar`), as any unique prefix of
`--output` (`--out=x`), and after global options (`git -C repo archive`). A glob that caught
every spelling would also catch a path that holds `-o`.

**It fails open.** Input it does not understand exits 0 with no output.

Test it without installing:

    echo '{"tool_input":{"command":"git archive -o base.tar origin/main"}}' | ./git-archive-output.py
"""

import json
import shlex
import sys

PUNCTUATION = "();<>|&\n"
SEPARATORS = set(";|&\n")

# Global options of `git` that consume the token after them.
GLOBAL_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
    "--config-env",
}

# The short options of `git archive` that take no value, so that `o` may follow them in a cluster.
SHORT_FLAGS = set("lv0123456789")

MESSAGE = """Refused: git archive {option} writes its file outside the sandbox.

To read the tree of a commit, use a command that needs no guarded write:

  - the tree, or some paths of it, in a new or empty directory:
      julia --startup-file=no ~/Research/Harness/scripts/base-tree.jl <checkout> <rev> <dir> [<path> ...]
  - one file:           git show <rev>:<path>
  - the list of files:  git ls-tree -r --name-only <rev>

If the tar file itself is the result, give the user the command to run.
"""


def parts(command):
    """Return the top-level parts of a command as token lists, or None."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    result, current = [], []
    for token in tokens:
        if set(token) <= set(PUNCTUATION):
            bare = token.replace("(", "").replace(")", "")
            if bare and set(bare) <= SEPARATORS and current:
                result.append(current)
                current = []
            continue
        current.append(token)
    if current:
        result.append(current)
    return result


def archive_arguments(tokens):
    """Return the arguments after `archive` when `tokens` is a `git … archive` call, else None."""
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens = tokens[1:]  # a leading VAR=value assignment
    if not tokens or tokens[0].rsplit("/", 1)[-1] != "git":
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in GLOBAL_VALUE:
            index += 2
        elif token.startswith("-"):
            index += 1
        else:
            return tokens[index + 1 :] if token == "archive" else None
    return None


def output_option(arguments):
    """Return the spelling of the output option among `arguments`, or None."""
    for token in arguments:
        if token == "--":
            return None
        if token.startswith("--"):
            name = token[2:].split("=", 1)[0]
            if name and "output".startswith(name):
                return token.split("=", 1)[0]
        elif token.startswith("-") and len(token) > 1:
            for char in token[1:]:
                if char == "o":
                    return token
                if char not in SHORT_FLAGS:
                    break
    return None


def main():
    try:
        command = json.load(sys.stdin)["tool_input"]["command"]
    except Exception:
        return 0
    if not isinstance(command, str) or "archive" not in command:
        return 0
    split = parts(command)
    if split is None:
        return 0
    for tokens in split:
        arguments = archive_arguments(tokens)
        option = output_option(arguments) if arguments is not None else None
        if option is not None:
            sys.stderr.write(MESSAGE.format(option=option))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
