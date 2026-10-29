"""Refuse `git archive -o` and `--output`, and name the commands that need no guarded write.

The check finds each top-level `git … archive` call and denies one that writes its archive with
`-o` or `--output`. An agent writes the archive to read the unmodified tree of a commit; `git`
runs outside the sandbox, so `-o` can write any path, and the refusal sends the agent to a read
that needs no prompt. Git takes the option clustered behind other short options (`-vo out.tar`),
with its value attached (`-oout.tar`), as any unique prefix of `--output` (`--out=x`), and after
global options (`git -C repo archive`), so no `permissions` glob can state it.
"""

from .contract import PASS, Call, Verdict
from .shell import parts, readings

# Global options of `git` that consume the token after them.
GLOBAL_VALUE = frozenset(
    {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
        "--super-prefix",
        "--config-env",
    }
)

# The short options of `git archive` that take no value, so that `o` may follow them in a cluster.
SHORT_FLAGS = frozenset("lv0123456789")

MESSAGE = """Refused: git archive {option} writes its file outside the sandbox.

To read the tree of a commit, use a command that needs no guarded write:

  - the tree, or some paths of it, in a new or empty directory:
      julia --startup-file=no ~/Research/Harness/scripts/base-tree.jl <checkout> <rev> <dir> [<path> ...]
  - one file:           git show <rev>:<path>
  - the list of files:  git ls-tree -r --name-only <rev>

If the tar file itself is the result, give the user the command to run.
"""


def archive_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `archive` when `words` is a `git … archive` call, else None."""
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]  # a leading VAR=value assignment
    if not words or words[0].rsplit("/", 1)[-1] != "git":
        return None
    index = 1
    while index < len(words):
        word = words[index]
        if word in GLOBAL_VALUE:
            index += 2
        elif word.startswith("-"):
            index += 1
        else:
            return words[index + 1 :] if word == "archive" else None
    return None


def output_option(arguments: list[str]) -> str | None:
    """The spelling of the output option among `arguments`, or None."""
    for word in arguments:
        if word == "--":
            return None
        if word.startswith("--"):
            name = word[2:].split("=", 1)[0]
            if name and "output".startswith(name):
                return word.split("=", 1)[0]
        elif word.startswith("-") and word != "-":
            for char in word[1:]:
                if char == "o":
                    return word
                if char not in SHORT_FLAGS:
                    break
    return None


def check(call: Call) -> Verdict:
    """Deny a `git archive` that writes its file with `-o` or `--output`."""
    if "archive" not in call.command:
        return PASS
    for tokens in readings(call.command) or []:
        for words in parts(tokens):
            arguments = archive_arguments(words)
            option = output_option(arguments) if arguments is not None else None
            if option is not None:
                return Verdict("deny", MESSAGE.format(option=option))
    return PASS
