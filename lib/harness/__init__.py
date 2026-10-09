"""The `harness` command: one front door to the harness tooling.

Every verb keeps one contract. A verb that changes something is dry by default: it prints its
plan and exits 1 when something would change, 0 when nothing would. `--apply` makes the change.
Exit 2 is a usage error or a failure. A read-only verb takes no mode flag.
"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent


class HarnessError(Exception):
    """A failure the verb reports in one line; `harness` exits 2."""


def changing(parser):
    """Give a verb that changes something its `--apply` flag."""
    parser.add_argument("--apply", action="store_true", help="make the change; without it, print the plan")
    return parser


def outcome(args, changes):
    """The exit status of a changing verb that planned or made `changes` changes."""
    return 0 if args.apply or not changes else 1
