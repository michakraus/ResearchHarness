"""The argument parser of `harness`: one subparser per subcommand."""

import argparse
import re
import subprocess
import sys

from . import REPO, HarnessError, __doc__ as CONTRACT
from . import docs, fmt, frontends, frontmatter, githooks, install, network, profile, protection, pushall, sweep
from . import doctor, providers, script_cases, skill_triggers, units

# The modules of lib/harness/; the adapters of lib/harness/frontends.py follow `install`.
MODULES = [install, frontmatter, githooks, pushall, protection, fmt, profile]
MODULES.append(skill_triggers)
MODULES.append(docs)
MODULES.append(units)
MODULES.append(script_cases)
MODULES.append(network)
MODULES.append(providers)
MODULES.append(doctor)

PROBE = REPO / "hooks" / "probe.py"
SUMMARY = re.compile(r"(\d+) cases, (\d+) wrong")


def probe():
    """Run the hook probe in a process of its own: (number of cases, number wrong).

    Its lines are printed and its summary line counted; a probe that ends with no summary line,
    or whose exit status disagrees with it, is one more wrong case."""
    p = subprocess.run([sys.executable, str(PROBE)], capture_output=True, text=True)
    lines = p.stdout.rstrip().splitlines()
    m = SUMMARY.fullmatch(lines[-1]) if lines else None
    print("\n".join(lines[:-1] if m else lines).rstrip())
    n, w = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if m is None or (p.returncode != 0) != (w > 0):
        print(f"BAD  probe: exit {p.returncode} with {'no summary line' if m is None else lines[-1]!r}")
        print(p.stderr.rstrip())
        n, w = n + 1, w + 1
    return n, w


def cmd_test(args):
    """Run every module's own cases, then the hook probe, then the contract sweep."""
    total = wrong = 0
    for selftest in [m.selftest for m in modules() if hasattr(m, "selftest")] + [probe, sweep.selftest]:
        n, w = selftest()
        total, wrong = total + n, wrong + w
    print(f"\n{total} cases, {wrong} wrong")
    return 1 if wrong else 0


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
    ap.add_argument("--models", metavar="F", help="the model tables, instead of models.toml beside the profile")
    sub = ap.add_subparsers(dest="verb", metavar="<subcommand>", required=True)
    for module in modules():
        # A module with no subcommand of its own; its cases run in `harness test`.
        if module not in (frontmatter, docs, units, script_cases, network, providers):
            module.register(sub)
    sub.add_parser("test", help="run the harness's own test cases",
                   description="Run the harness's own test cases: the cases of each module and adapter, the hook "
                               "probe and the contract sweep. It prints `<n> cases, <w> wrong` and exits 1 when a "
                               "case fails.").set_defaults(run=cmd_test)
    args = ap.parse_args(argv)
    try:
        return args.run(args)
    except HarnessError as e:
        print(f"harness {args.verb}: {e}", file=sys.stderr)
        return 2
