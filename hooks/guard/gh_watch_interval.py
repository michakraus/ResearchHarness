"""Deny a `gh` watcher that polls the GitHub API faster than once every MIN_INTERVAL seconds.

`gh run watch` refreshes every 3 seconds and `gh pr checks --watch` every 10 seconds unless
`-i` or `--interval` sets another refresh interval. Each refresh makes several API calls, and
every session and agent of one account shares one API limit. A watcher on a run of half an hour
at the default interval makes thousands of calls and trips GitHub's secondary rate limit, after
which the REST Actions endpoints answer 403 for every session of the account.

The check finds each top-level `gh run watch` call, and each `gh pr checks` call that carries
`--watch`, after any assignments such as `GH_REPO=…`, and reads its last `-i` or `--interval`
value, in each of the forms `-i 60`, `-i60`, `-i=60`, `--interval 60` and `--interval=60`:

  * **No interval**: deny. The reason names `--interval 60`.
  * **An interval that is not a whole number of at least MIN_INTERVAL seconds**: deny.
  * **An interval of at least MIN_INTERVAL seconds**: pass.

The last value counts, because `gh` takes the last one.
"""

from .contract import PASS, Call, Verdict, strongest
from .rm_scope import ASSIGNMENT
from .shell import Tokens, parts, readings

# The shortest refresh interval, in seconds, that a watcher may use.
MIN_INTERVAL = 30

TOO_FAST = """Refused: {command}

{problem} Every refresh makes several GitHub API calls, and all sessions and agents of the
account share one rate limit; a watcher at the default interval trips GitHub's secondary limit
on a long run. Add `--interval 60` and run it again.
"""


def interval(arguments: list[str]) -> str | None:
    """The last value of `-i` or `--interval` in the arguments after the subcommand, or None."""
    found: str | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        index += 1
        name, equals, value = argument.partition("=")
        if name in ("-i", "--interval"):
            if not equals:
                value = arguments[index] if index < len(arguments) else ""
                index += 1
            found = value
        elif argument.startswith("-i") and not argument.startswith("--"):
            found = argument[2:]
    return found


def problem(arguments: list[str]) -> str | None:
    """Why the watcher's interval is refused, or None when it is at least MIN_INTERVAL seconds."""
    value = interval(arguments)
    if value is None:
        return "The watcher sets no `--interval`, so it polls at `gh`'s default of 3 or 10 seconds."
    if not value.isdecimal() or int(value) < MIN_INTERVAL:
        return f"The interval `{value}` is not a whole number of at least {MIN_INTERVAL} seconds."
    return None


def verdict_of(tokens: Tokens) -> Verdict:
    """The strongest verdict of the watcher parts of one reading."""
    verdicts: list[Verdict] = []
    for found in parts(tokens):
        words = found
        while words and ASSIGNMENT.match(words[0]):
            words = words[1:]
        if not words or words[0].rsplit("/", 1)[-1] != "gh":
            continue
        watches = words[1:3] == ["run", "watch"] or (
            words[1:3] == ["pr", "checks"] and "--watch" in words[3:]
        )
        if not watches:
            continue
        why = problem(words[3:])
        if why is not None:
            verdicts.append(Verdict("deny", TOO_FAST.format(command=" ".join(words), problem=why)))
    return strongest(verdicts)


def check(call: Call) -> Verdict:
    """Deny a `gh run watch` or `gh pr checks --watch` with an interval below MIN_INTERVAL seconds."""
    command = call.command
    if "gh" not in command or "watch" not in command:
        return PASS
    return strongest(verdict_of(tokens) for tokens in readings(command) or [])
