"""The `harness` command: one front door to the harness tooling.

Every subcommand keeps one contract. A subcommand that changes something is dry by default: it
prints its plan and exits 1 when something would change, 0 when nothing would. `--apply` makes
the change. Exit 2 is a usage error or a failure. A read-only subcommand takes no mode flag.
"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent


class HarnessError(Exception):
    """A failure the subcommand reports in one line; `harness` exits 2."""


def changing(parser, help="make the change; without it, print the plan"):
    """Give a subcommand that changes something its `--apply` flag, with `help` as its help."""
    parser.add_argument("--apply", action="store_true", help=help)
    return parser


def outcome(args, changes):
    """The exit status of a subcommand that changes files, given its number of `changes`,
    planned or made."""
    return 0 if args.apply or not changes else 1
