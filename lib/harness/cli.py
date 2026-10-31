"""The argument parser of `harness`: one subparser per subcommand."""

import argparse
import sys

from . import HarnessError, __doc__ as CONTRACT
from . import docs, fmt, frontends, frontmatter, githooks, install, network, profile, protection, repos
from . import doctor, dotfiles_kit, providers, script_cases, skill_triggers, units, update
from . import changelog, environment, mutate, strict, testrun
from . import autocommit, fsutil, jsonio, ownedjson
from . import wikilint
from . import setup

# The modules of lib/harness/; the adapters of lib/harness/frontends.py follow `install`.
MODULES = [install, update, frontmatter, githooks, repos, protection, fmt, profile]
MODULES.append(skill_triggers)
MODULES.append(docs)
MODULES.append(units)
MODULES.append(script_cases)
MODULES.append(network)
MODULES.append(providers)
MODULES.append(doctor)
MODULES.append(dotfiles_kit)
MODULES.append(changelog)
MODULES.append(mutate)
MODULES.append(wikilint)
MODULES.append(environment)
MODULES.append(strict)
MODULES.append(jsonio)
MODULES.append(ownedjson)
MODULES.append(fsutil)
MODULES.append(autocommit)
MODULES.append(setup)
MODULES.append(testrun)


def modules():
    """The modules that register a subcommand or hold test cases (MODULES), with each adapter
    after `install`."""
    return [MODULES[0], *frontends.load(), *MODULES[1:]]


def main(argv=None):
    # An adapter that fails to load exits 2 before any subcommand runs.
    try:
        frontends.load()
    except HarnessError as e:
        print(f"harness: {e}", file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser(
        prog="harness", description=CONTRACT, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--profile", metavar="F", help="the private profile, instead of the default path")
    ap.add_argument(
        "--models", metavar="F", help="the model tables, instead of models.toml beside the profile"
    )
    sub = ap.add_subparsers(dest="subcommand", metavar="<subcommand>", required=True)
    for module in modules():
        # A module with no subcommand of its own; its cases run in `harness test`. `testrun`
        # registers `harness test` below, with the list of the modules.
        if module not in (
            frontmatter,
            docs,
            units,
            script_cases,
            network,
            providers,
            environment,
            strict,
            jsonio,
            ownedjson,
            fsutil,
            autocommit,
            testrun,
        ):
            module.register(sub)
    testrun.register(sub, modules)
    args = ap.parse_args(argv)
    try:
        return args.run(args)
    except HarnessError as e:
        print(f"harness {args.subcommand}: {e}", file=sys.stderr)
        return 2
