"""Decide `gh pr create` by the repository that it names.

The check finds each top-level `gh pr create` call, after any assignments such as `GH_REPO=…`,
and reads every `-R` and `--repo` value of it, in each of the forms `-R x`, `-Rx`, `--repo x` and
`--repo=x`:

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
from .shell import Tokens, parts, readings
from .rm_scope import ASSIGNMENT

NO_REPOSITORY = """Refused: {command}

`gh pr create` names no repository, so it opens the pull request in whatever repository the
checkout or `GH_REPO` names. Add `--repo <owner>/<repo>` and run it again.
"""


# The flags of `gh pr create` other than `-R` and `--repo` that consume the word after them.
TAKES_VALUE = frozenset(
    {
        "-a",
        "--assignee",
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
    """Every value of `-R` and `--repo` in the arguments after `gh pr create`; the value of a flag
    of TAKES_VALUE is no flag."""
    found: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in ("-R", "--repo"):
            found.append(arguments[index + 1] if index + 1 < len(arguments) else "")
            index += 2
            continue
        if argument.startswith("--repo="):
            found.append(argument.removeprefix("--repo="))
        elif argument.startswith("-R"):
            found.append(argument.removeprefix("-R"))
        index += 2 if argument in TAKES_VALUE else 1
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
        if not words or words[0].rsplit("/", 1)[-1] != "gh" or words[1:3] != ["pr", "create"]:
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
    if "gh" not in command or "create" not in command:
        return PASS
    return strongest(verdict_of(tokens) for tokens in readings(command) or [])
