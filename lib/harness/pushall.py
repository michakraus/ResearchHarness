"""Push every package and experiment that is ahead of its upstream.

    harness push-all [--apply] [--skip-hooks] [--include-topic-branches]

RUN THIS YOURSELF, IN YOUR OWN TERMINAL, AND EXPECT IT TO TAKE HOURS. Not from an agent session:
a tool call is capped at ten minutes, and the pre-push hook runs a full suite per repository — a
few minutes in most, 10–30 in the large packages. Killing it mid-test orphans the Julia child,
which then invalidates precompile caches for days.

SEQUENTIAL, NEVER PARALLEL. The packages depend on each other, and two test runs that load the same
package with different CacheFlags invalidate each other's precompiled images. The failure reads
as a cascade of MethodErrors that look exactly like broken code. "Different repository" is not
"disjoint packages".

WHEN --skip-hooks IS HONEST. The pre-push hook runs the full suite when pushing to main or master:
the right gate for a source change. For a change that touches no Julia source — a workflow, a
README, a CHANGELOG — the suite says nothing about the change, and CI runs on the push anyway. It
is NOT honest when the push contains Julia source or a [compat] change. The dry run names the
`.jl` files of each push. A repository whose main does not load cannot pass its suite, and
without --skip-hooks its push is refused.

A commit on a topic branch does not reach the default branch, so it does not reach the required
checks; such a repository is skipped unless --include-topic-branches.

A push is checked against the remote ref, not its exit status: `git ls-remote` is the ground truth
for whether the objects arrived.
"""

from . import HarnessError, changing, outcome
from .githooks import git, repositories


def cmd_push_all(args):
    planned = pushed = uptodate = skipped = failed = 0
    for repo, _ in repositories():
        name = repo.name
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
        if not upstream:
            print(f"{name:<26} SKIP   {branch} has no upstream")
            skipped += 1
            continue
        ahead = int(git(repo, "rev-list", "--count", f"{upstream}..HEAD").stdout.strip() or 0)
        behind = int(git(repo, "rev-list", "--count", f"HEAD..{upstream}").stdout.strip() or 0)
        if ahead == 0:
            print(f"{name:<26} up to date")
            uptodate += 1
            continue
        if behind:
            print(f"{name:<26} SKIP   {behind} commits behind {upstream} - rebase first")
            skipped += 1
            continue
        default = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD").stdout.strip()
        default = default.removeprefix("origin/")
        if default and branch != default and not args.include_topic_branches:
            print(f"{name:<26} SKIP   on {branch}, not the default branch {default}")
            print(f"{'':<27}{ahead} commit(s) would land on a topic branch; pass --include-topic-branches to push anyway")
            skipped += 1
            continue
        src = " ".join(git(repo, "diff", "--name-only", f"{upstream}..HEAD", "--", "*.jl").stdout.split()[:3])
        planned += 1
        if not args.apply:
            print(f"{name:<26} push {ahead} commit(s) to {upstream}" + (f"   .jl touched: {src}" if src else ""))
            continue
        if src and args.skip_hooks:
            print(f"{name:<26} NOTE   .jl files in this push, and hooks are being skipped: {src}")
        print(f"{name:<26} pushing {ahead} commit(s)...", end="", flush=True)
        p = git(repo, "push", *(["--no-verify"] if args.skip_hooks else []))
        local = git(repo, "rev-parse", "HEAD").stdout.strip()
        remote = git(repo, "ls-remote", "origin", f"refs/heads/{branch}").stdout.split("\t")[0].strip()
        if local == remote:
            print(" done")
            pushed += 1
        else:
            print(f" FAILED (rc={p.returncode})")
            for line in (p.stdout + p.stderr).splitlines()[-12:]:
                print("      " + line)
            failed += 1
    if args.apply:
        print(f"\n{pushed} pushed, {uptodate} already up to date, {skipped} skipped, {failed} failed.")
        print("Next: harness ci-protection --apply, which needs the new CI.yml on each default branch.")
    else:
        print(f"\n{planned} to push, {uptodate} up to date, {skipped} skipped.")
    if failed:
        raise HarnessError(f"{failed} pushes failed")
    return outcome(args, planned)


def register(sub):
    p = changing(sub.add_parser("push-all", help="push every package and experiment ahead of its upstream"))
    p.add_argument("--skip-hooks", action="store_true", help="push with --no-verify: no pre-push suite")
    p.add_argument("--include-topic-branches", action="store_true", help="also push a repository on a topic branch")
    p.set_defaults(run=cmd_push_all)
