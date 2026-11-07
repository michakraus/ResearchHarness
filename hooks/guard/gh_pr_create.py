"""Decide `gh pr create` by the repository that it names.

The check finds each top-level `gh pr create` call and each call of its alias `gh pr new`, after
any assignments such as `GH_REPO=…`, and reads every `-R` and `--repo` value of it, in each of the
forms `-R x`, `-Rx`, `-R=x`, `--repo x` and `--repo=x`, also at the end of a cluster of
one-letter flags such as `-dR x`:

  * **No `-R` or `--repo`**: deny. `gh` then opens the pull request in the repository that the
    checkout or `GH_REPO` names, which the command text does not show. The reason tells the agent
    to add `--repo <owner>/<repo>`.
  * **A value whose owner is not an own organisation**: ask. The value is `<owner>/<repo>` or
    `<host>/<owner>/<repo>`; a value with a host, or of any other form, is not an own repository.
    The own organisations are the `org` list of the profile (`gh_api_writes.own_organisations`),
    compared without case. A missing or unreadable profile gives none, so every value asks.
  * **Every value names an own organisation**: pass, so `allow` lets the call run.

The check reads every value, not only the last one that `gh` takes, so a second `--repo` cannot
send a call that names an own repository first to another one.
"""

from .contract import PASS, Call, Verdict, strongest
from .gh_api_writes import own_organisations
from .rm_scope import ASSIGNMENT
from .shell import Tokens, parts, readings

NO_REPOSITORY = """Refused: {command}

`gh pr create` names no repository, so it opens the pull request in whatever repository the
checkout or `GH_REPO` names. Add `--repo <owner>/<repo>` and run it again.
"""


# The flags of `gh pr create` other than `-R` and `--repo` that consume the word after them.
TAKES_VALUE = frozenset(
    {
        "-a",
        "--assignee",
        "--attach",
        "-B",
        "--base",
        "-b",
        "--body",
        "-F",
        "--body-file",
        "-H",
        "--head",
        "-l",
        "--label",
        "-m",
        "--milestone",
        "-p",
        "--project",
        "--recover",
        "-r",
        "--reviewer",
        "-T",
        "--template",
        "-t",
        "--title",
    }
)


def repositories(arguments: list[str]) -> list[str]:
    """Every value of `-R` and `--repo` in the arguments after `gh pr create`, read as `gh` reads
    them: the value of a flag of TAKES_VALUE is no flag, and a cluster of one-letter flags such as
    `-dR x` ends at its first letter that takes a value, whose value is the rest of the word, after
    one `=`, or else the next word."""
    found: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        index += 1
        if argument.startswith("--"):
            name, equals, value = argument.partition("=")
            if name == "--repo":
                if not equals:
                    value = arguments[index] if index < len(arguments) else ""
                    index += 1
                found.append(value)
            elif argument in TAKES_VALUE:
                index += 1
            continue
        for at, letter in enumerate(argument[1:] if argument.startswith("-") else "", start=2):
            if letter == "R" or f"-{letter}" in TAKES_VALUE:
                value = argument[at:]
                if len(value) > 1 and value.startswith("="):
                    value = value[1:]
                elif not value:
                    value = arguments[index] if index < len(arguments) else ""
                    index += 1
                if letter == "R":
                    found.append(value)
                break
    return found


def own(repository: str) -> bool:
    """Whether `repository` is `<owner>/<repo>` with an owner of the own organisations."""
    owner, slash, name = repository.partition("/")
    return bool(slash and owner and name and "/" not in name and owner.lower() in own_organisations())


def verdict_of(tokens: Tokens) -> Verdict:
    """The strongest verdict of the `gh pr create` parts of one reading."""
    verdicts: list[Verdict] = []
    for found in parts(tokens):
        words = found
        while words and ASSIGNMENT.match(words[0]):
            words = words[1:]
        if (
            not words
            or words[0].rsplit("/", 1)[-1] != "gh"
            or words[1:3] not in (["pr", "create"], ["pr", "new"])
        ):
            continue
        named = repositories(words[3:])
        command = " ".join(words)
        if not named:
            verdicts.append(Verdict("deny", NO_REPOSITORY.format(command=command)))
        elif not all(own(repository) for repository in named):
            verdicts.append(
                Verdict("ask", f"`{command}` opens a pull request outside the own organisations.")
            )
    return strongest(verdicts)


def check(call: Call) -> Verdict:
    """Deny a `gh pr create` that names no repository; ask for one outside the own organisations."""
    command = call.command
    if "gh" not in command or ("create" not in command and "new" not in command):
        return PASS
    return strongest(verdict_of(tokens) for tokens in readings(command) or [])
