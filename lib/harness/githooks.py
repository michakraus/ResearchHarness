"""Install the shared git hooks and GitHub workflows into the research tree's repositories.

    harness githooks [--apply]          # pre-commit, pre-push, test-layout.jl into every
                                        # repository under Packages/ and Experiments/
    harness wiki-lint-hook [--apply]    # pre-commit-wiki into the five prose repositories
    harness workflows [--apply]         # the canonical workflows from githooks/workflows/

Every copy is byte-identical in every repository: a hook reads the package name from
Project.toml, and CI.yml does the same at run time. That makes drift a file comparison, which is
what `githooks/verify-workflows.jl` relies on. The research root is $RESEARCH_ROOT, else
~/Research.

`core.hooksPath` is local config: it is set per clone and does not travel with a push, so a fresh
clone needs `harness githooks --apply` again. A sandboxed session cannot write `.git/config`;
such a repository is reported with the command to run.

The copies are TRACKED in each repository, so a run leaves a modified file there rather than an
untracked one. Commit `.githooks/<hook>` or the workflow by name, directly to `main`.

WHAT `workflows` DOES NOT INSTALL, AND WHY.

  Documenter.yml   only where a tracked docs/make.jl exists — `git ls-files`, because a runner
                   checks out tracked files only. Two kinds of repository keep their own, named
                   in the private profile. `docs_exceptions`: the docs are a multi-job pipeline,
                   which the template does not describe. `docs_additions`: docs/make.jl needs a
                   step the template does not have, such as a TeX toolchain that compiles figures
                   from tracked TikZ sources before Documenter checks links. A `docs_additions`
                   repository keeps the canonical body and only adds a step, so
                   verify-workflows.jl still checks that body. Keep one repository for TeX
                   figures, and let the others link them from its site.
  TagBot.yml       packages only. The experiment repositories are not registered in General, so
                   a tag-watching workflow there has nothing to watch.
  extra workflows  a repository that needs a job the canonical CI.yml does not have gets its own
                   file, such as Metal.yml for a GPU job. Never a local edit to CI.yml: that is
                   the drift this verb exists to prevent.

RETIRED lists files the template set no longer covers. Copying alone never removes a file, so
`--apply` deletes each one that is present. CompatHelper.yml is there because dependabot.yml opens
the [compat] bumps; two bots would open each bump twice.
"""

import os
import pathlib
import shutil
import subprocess

from . import REPO, HarnessError, changing, outcome
from . import profile as profile_module

HOOKS = REPO / "githooks"
WORKFLOWS = HOOKS / "workflows"
WIKI_REPOSITORIES = ["Knowledge", "Environment", "Tasks", "Bibliography", "Library"]
RETIRED = [".github/workflows/CompatHelper.yml"]


def research_root():
    return pathlib.Path(os.environ.get("RESEARCH_ROOT") or pathlib.Path.home() / "Research")


def repositories(require_project=False):
    """(directory, kind) of every git repository under Packages/ and Experiments/, by name."""
    found = []
    for group, kind in (("Packages", "package"), ("Experiments", "experiment")):
        base = research_root() / group
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if (d / ".git").is_dir() and (not require_project or (d / "Project.toml").is_file()):
                found.append((d, kind))
    return found


def git(repo, *args):
    """Run `git -C repo args`; the completed process, never raising."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def differs(src, dst, executable=False):
    """True when `dst` is absent, not byte-identical to `src`, or lacks a wanted execute bit."""
    if not dst.is_file() or dst.read_bytes() != src.read_bytes():
        return True
    return executable and not os.access(dst, os.X_OK)


def copy(src, dst, executable=False):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    if executable:
        dst.chmod(dst.stat().st_mode | 0o111)


def set_hooks_path(repo, unset):
    """Set `core.hooksPath=.githooks`; on failure, remember the repository for the report."""
    if git(repo, "config", "core.hooksPath", ".githooks").returncode != 0:
        unset.append(repo)
        return False
    return True


def report_unset(unset):
    """Name each repository whose `core.hooksPath` could not be set; True when there is one."""
    if not unset:
        return False
    print("\ncore.hooksPath could not be set in these repositories: a sandboxed session cannot")
    print("write .git/config. Run each command yourself; until then the hook does not run.\n")
    for repo in unset:
        print(f"    cd {repo} && git config core.hooksPath .githooks")
    return True


def install_hooks(args, targets, files):
    """Copy `files` [(source, name in .githooks/, executable)] into each target repository."""
    changes, unset = 0, []
    for repo in targets:
        todo = [(s, repo / ".githooks" / n, x) for s, n, x in files if differs(s, repo / ".githooks" / n, x)]
        path = git(repo, "config", "core.hooksPath").stdout.strip() or "(unset)"
        if not todo and path == ".githooks":
            continue
        changes += len(todo) + (path != ".githooks")
        verb = "wrote" if args.apply else "would write"
        for src, dst, executable in todo:
            if args.apply:
                copy(src, dst, executable)
            print(f"{repo.name:<28} {verb} .githooks/{dst.name}")
        if path != ".githooks":
            if not args.apply:
                print(f"{repo.name:<28} would set core.hooksPath: {path} -> .githooks")
            elif set_hooks_path(repo, unset):
                print(f"{repo.name:<28} set core.hooksPath: {path} -> .githooks")
    print(f"\n{len(targets)} repositories, {changes} change(s) {'made' if args.apply else 'to make'}.")
    if args.apply and changes:
        print("Review the diff, then commit each .githooks/ file by name, directly to main.")
    if report_unset(unset):
        raise HarnessError(f"core.hooksPath not set in {len(unset)} repositories")
    return outcome(args, changes)


def cmd_githooks(args):
    files = [
        (HOOKS / "pre-commit", "pre-commit", True),
        (HOOKS / "pre-push", "pre-push", True),
        (REPO / "scripts" / "test-layout.jl", "test-layout.jl", False),
    ]
    return install_hooks(args, [d for d, _ in repositories()], files)


def cmd_wiki_lint_hook(args):
    targets = []
    for name in WIKI_REPOSITORIES:
        d = research_root() / name
        if (d / ".git").is_dir():
            targets.append(d)
        else:
            print(f"{name:<28} skipped — not a git repository")
    return install_hooks(args, targets, [(HOOKS / "pre-commit-wiki", "pre-commit", True)])


def cmd_workflows(args):
    for f in ("CI.yml", "dependabot.yml", "TagBot.yml", "Documenter.yml", "codecov.yml"):
        if not (WORKFLOWS / f).is_file():
            raise HarnessError(f"missing template: {WORKFLOWS / f}")
    profile = profile_module.load(args.profile)
    own_docs = set(profile_module.get(profile, "docs_exceptions")) | set(profile_module.get(profile, "docs_additions"))
    written = removed = skipped = 0
    for repo, kind in repositories(require_project=True):
        print(f"{repo.name:<28} {kind}")
        plan = [("CI.yml", ".github/workflows/CI.yml"), ("dependabot.yml", ".github/dependabot.yml"),
                ("codecov.yml", "codecov.yml")]
        if kind == "package":
            plan.append(("TagBot.yml", ".github/workflows/TagBot.yml"))
        if repo.name in own_docs:
            print("      skipped Documenter.yml - kept per repository (docs_exceptions, docs_additions)")
            skipped += 1
        elif git(repo, "ls-files", "--", "docs/make.jl").stdout.strip():
            plan.append(("Documenter.yml", ".github/workflows/Documenter.yml"))
        else:
            print("      skipped Documenter.yml - no tracked docs/make.jl")
            skipped += 1
        for template, rel in plan:
            if differs(WORKFLOWS / template, repo / rel):
                if args.apply:
                    copy(WORKFLOWS / template, repo / rel)
                print(f"      {'wrote' if args.apply else 'would write'} {rel}")
                written += 1
        for rel in RETIRED:
            if (repo / rel).is_file():
                if args.apply:
                    (repo / rel).unlink()
                print(f"      {'removed' if args.apply else 'would remove'} {rel}")
                removed += 1
    print(f"\n{written} file(s) {'written' if args.apply else 'to write'}, {removed} retired file(s) "
          f"{'removed' if args.apply else 'to remove'}, {skipped} documentation workflow(s) skipped.")
    if not args.apply and written + removed:
        print("Re-run with --apply, then run verify-workflows.jl.")
    return outcome(args, written + removed)


def register(sub):
    changing(sub.add_parser("githooks", help="install the shared git hooks into every package and experiment")
             ).set_defaults(run=cmd_githooks)
    changing(sub.add_parser("wiki-lint-hook", help="install the wiki-lint hook into the prose repositories")
             ).set_defaults(run=cmd_wiki_lint_hook)
    changing(sub.add_parser("workflows", help="install the canonical GitHub workflows")
             ).set_defaults(run=cmd_workflows)
