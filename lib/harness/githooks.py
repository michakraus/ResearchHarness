"""Install the shared git hooks and GitHub workflows into the research tree's repositories.

    harness githooks [--apply]          # pre-commit, pre-commit.jl, pre-push, pre-push.jl,
                                        # test-layout.jl into every repository under
                                        # Packages/ and Experiments/
    harness wiki-lint-hook [--apply]    # pre-commit-wiki into the prose repositories
    harness workflows [--apply]         # the canonical workflows from githooks/workflows/
    harness dependents [--apply]        # .github/dependents.toml into each base of the
                                        # profile's dependents_bases

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
  Dependents.yml   with dependents.jl, only into the bases of the profile's `dependents_bases`,
                   and out of every other repository. Its jobs read .github/dependents.toml,
                   which `dependents` writes: one [[dependent]] table per repository below
                   Packages/ whose Project.toml has the base's UUID in [deps], with the GitHub
                   owner/name of its origin.
  extra workflows  a repository that needs a job the canonical CI.yml does not have gets its own
                   file, such as Metal.yml for a GPU job. Never a local edit to CI.yml: that is
                   the drift this subcommand exists to prevent.

RETIRED lists files the template set no longer covers. Copying alone never removes a file, so
`--apply` deletes each one that is present. CompatHelper.yml is there because dependabot.yml opens
the [compat] bumps; two bots would open each bump twice.
"""

import argparse
import difflib
import os
import pathlib
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from typing import cast

# `githooks_cases` imports this module too, and reads its names only when a case runs, so the
# cycle resolves at import.
from . import REPO, HarnessError, changing, githooks_cases, outcome
from . import profile as profile_module
from .fmt import Subcommands

HOOKS = REPO / "githooks"
WORKFLOWS = HOOKS / "workflows"
WIKI_REPOSITORIES = ["Knowledge", "Environment", "Tasks", "Library"]
RETIRED = [".github/workflows/CompatHelper.yml"]
# The templates that `workflows` installs into each base of the profile's `dependents_bases`, and
# removes from every other repository, with their installed paths.
DEPENDENT_FILES = [
    ("Dependents.yml", ".github/workflows/Dependents.yml"),
    ("dependents.jl", ".github/dependents.jl"),
]
# The list of a base's dependents that `dependents` writes, and its header.
DEPENDENTS_TOML = ".github/dependents.toml"
DEPENDENTS_HEADER = (
    "# Written by `harness dependents --apply` from the Project.toml files below Packages/ of the\n"
    "# research tree; run it again rather than edit this file. Dependents.yml reads it into the\n"
    "# matrix of its test job.\n"
)
# A repository name below Packages/.
NAME = re.compile(r"[A-Za-z0-9._-]+")
# A GitHub origin as git prints it: a URL of one of five schemes, or the scp form, whose user and
# host hold no `/` before the `:`. The name is the shortest one, so a final `.git` is not part of it.
GITHUB_ORIGIN = re.compile(
    r"(?:(?i:https?|ssh|git\+ssh|ssh\+git)://(?:[^@/?#]+@)?(?i:github\.com)(?::[0-9]+)?/"
    r"|(?:[^@/:]+@)?(?i:github\.com):)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?/?"
)


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


def git(repo: str | os.PathLike[str], *args: str, timeout: int = 60):
    """Run `git -C repo args`; the completed process, whatever its exit status. A git that runs
    longer than `timeout` seconds raises subprocess.TimeoutExpired."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],  # noqa: S607 -- git runs from PATH
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


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
        (HOOKS / "pre-commit.jl", "pre-commit.jl", False),
        (HOOKS / "pre-push", "pre-push", True),
        (HOOKS / "pre-push.jl", "pre-push.jl", False),
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


def cmd_workflows(args: argparse.Namespace) -> int:
    for f in (
        "CI.yml",
        "dependabot.yml",
        "TagBot.yml",
        "Documenter.yml",
        "codecov.yml",
        *dict(DEPENDENT_FILES),
    ):
        if not (WORKFLOWS / f).is_file():
            raise HarnessError(f"missing template: {WORKFLOWS / f}")
    profile = profile_module.load(args.profile)
    listed = bases(profile)
    own_docs = set(profile.docs_exceptions) | set(profile.docs_additions)
    written = removed = skipped = 0
    for repo, kind in repositories(require_project=True):
        print(f"{repo.name:<28} {kind}")
        plan = [
            ("CI.yml", ".github/workflows/CI.yml"),
            ("dependabot.yml", ".github/dependabot.yml"),
            ("codecov.yml", "codecov.yml"),
        ]
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
        # The dependents workflow goes into a listed base, and out of every other repository.
        plan += [f for f in DEPENDENT_FILES if repo in listed]
        unlisted = [rel for _, rel in DEPENDENT_FILES if repo not in listed]
        for template, rel in plan:
            if differs(WORKFLOWS / template, repo / rel):
                if args.apply:
                    copy(WORKFLOWS / template, repo / rel)
                print(f"      {'wrote' if args.apply else 'would write'} {rel}")
                written += 1
        for rel in [*RETIRED, *unlisted]:
            if (repo / rel).is_file():
                if args.apply:
                    (repo / rel).unlink()
                print(f"      {'removed' if args.apply else 'would remove'} {rel}")
                removed += 1
    print(
        f"\n{written} file(s) {'written' if args.apply else 'to write'}, {removed} retired file(s) "
        f"{'removed' if args.apply else 'to remove'}, {skipped} documentation workflow(s) skipped."
    )
    if not args.apply and written + removed:
        print("Re-run with --apply, then run verify-workflows.jl.")
    return outcome(args, written + removed)


def bases(profile: profile_module.Profile) -> list[pathlib.Path]:
    """The repositories that the profile's `dependents_bases` names, each below Packages/ of the
    research root. A name that is not a git repository with a Project.toml there raises."""
    packages = research_root() / "Packages"
    bad = [
        name
        for name in profile.dependents_bases
        if not (
            NAME.fullmatch(name)
            and name not in {".", ".."}
            and (packages / name / ".git").is_dir()
            and (packages / name / "Project.toml").is_file()
        )
    ]
    if bad:
        raise HarnessError(
            f"dependents_bases names {', '.join(bad)}, which is no git repository with a Project.toml "
            f"in {packages}"
        )
    return [packages / name for name in profile.dependents_bases]


@dataclass(frozen=True)
class Project:
    """The keys of a Project.toml that the census reads: the `uuid`, None without one, and the
    string values of `[deps]`."""

    uuid: str | None
    deps: frozenset[str]


def read_project(path: pathlib.Path) -> Project:
    """The Project.toml at `path`; one that is not UTF-8 or not TOML raises, naming it."""
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise HarnessError(f"{path} is not a TOML file: {e}") from None
    uuid, deps = data.get("uuid"), data.get("deps")
    values = cast("dict[str, object]", deps).values() if isinstance(deps, dict) else ()
    return Project(
        uuid if isinstance(uuid, str) else None, frozenset(v for v in values if isinstance(v, str))
    )


def github_name(url: str) -> str | None:
    """The GitHub `owner/name` of the remote URL `url`, in one of two forms:
    `<scheme>://[user@]github.com[:port]/owner/name[.git][/]`, with the scheme `https`, `http`,
    `ssh`, `git+ssh` or `ssh+git`, or `[user@]github.com:owner/name[.git][/]`. Scheme and host
    match in any case. None for every other string, such as another scheme or host, a local path, a
    query or a fragment, or a name `.` or `..`."""
    match = GITHUB_ORIGIN.fullmatch(url)
    if match is None or match["name"] in {".", ".."}:
        return None
    return f"{match['owner']}/{match['name']}"


def github_repository(repo: pathlib.Path) -> str:
    """The GitHub `owner/name` of the origin of `repo`. No origin, or an origin of neither form of
    `github_name`, raises, naming the repository: the dependents workflow checks it out from
    GitHub."""
    url = git(repo, "remote", "get-url", "origin").stdout.strip()
    name = github_name(url)
    if name is None:
        raise HarnessError(
            f"{repo.name}: the origin {url or '(none)'} is no GitHub URL of a form that "
            "harness dependents reads"
        )
    return name


def census(base: pathlib.Path) -> list[tuple[str, str]]:
    """(name, GitHub `owner/name`) of each direct dependent of `base`, sorted by name as
    `repositories` lists them: each other repository below Packages/ whose Project.toml has the
    base's UUID among the values of `[deps]`. `[weakdeps]`, `[extras]`, test/Project.toml and
    Experiments/ do not count."""
    uuid = read_project(base / "Project.toml").uuid
    if uuid is None:
        raise HarnessError(f"{base / 'Project.toml'} has no uuid, so {base.name} is no package")
    found: list[tuple[str, str]] = []
    for repo, kind in cast("list[tuple[pathlib.Path, str]]", repositories(require_project=True)):
        if kind != "package" or repo == base:
            continue
        if uuid in read_project(repo / "Project.toml").deps:
            if not NAME.fullmatch(repo.name):
                raise HarnessError(f"{repo}: the name {repo.name!r} is not one that dependents.toml can hold")
            found.append((repo.name, github_repository(repo)))
    return found


def dependents_text(rows: list[tuple[str, str]]) -> str:
    """The text of `.github/dependents.toml` for the (name, repository) `rows`: the header, then one
    `[[dependent]]` table per row."""
    return DEPENDENTS_HEADER + "".join(
        f'\n[[dependent]]\nname = "{n}"\nrepository = "{r}"\n' for n, r in rows
    )


def old_text(path: pathlib.Path) -> str:
    """The text of the file at `path`, or "" when nothing is there. A path that holds something
    other than a regular file, a file that is not UTF-8, and a parent that is a symbolic link or not
    a directory each raise, naming the path: `dependents --apply` writes there."""
    if path.parent.is_symlink() or (path.parent.exists() and not path.parent.is_dir()):
        raise HarnessError(
            f"{path.parent} is a symbolic link or not a directory, so {path} cannot be written"
        )
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise HarnessError(f"{path} is not a regular file; remove it, then run harness dependents again")
    if not path.exists():
        return ""
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        raise HarnessError(f"{path} is not UTF-8: {e}") from None


def cmd_dependents(args: argparse.Namespace) -> int:
    """Write `.github/dependents.toml` into each base of `dependents_bases`, after the census of
    every base and the read of every old file succeed; print the diff of each file that
    changes."""
    listed = bases(profile_module.load(args.profile))
    texts = {base: dependents_text(census(base)) for base in listed}
    olds = {base: old_text(base / DEPENDENTS_TOML) for base in listed}
    changes = 0
    for base, text in texts.items():
        path = base / DEPENDENTS_TOML
        old = olds[base]
        if old == text:
            print(f"{base.name:<28} {DEPENDENTS_TOML} is current")
            continue
        changes += 1
        print(f"{base.name:<28} {'wrote' if args.apply else 'would write'} {DEPENDENTS_TOML}")
        diff = difflib.unified_diff(old.splitlines(), text.splitlines(), "before", "after", lineterm="")
        print("".join(f"      {line}\n" for line in diff), end="")
        if args.apply:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    print(f"\n{len(listed)} base(s), {changes} file(s) {'written' if args.apply else 'to write'}.")
    if args.apply and changes:
        print(f"Review the diff, then commit {DEPENDENTS_TOML} by name in each base.")
    return outcome(args, changes)


def selftest() -> tuple[int, int]:
    """The cases of `githooks_cases`: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok: object, label: str) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  githooks: {label}")

    githooks_cases.cases(check)
    return total, wrong


def register(sub: Subcommands) -> None:
    changing(
        sub.add_parser(
            "githooks",
            help="install the shared git hooks into every package and experiment",
            description="Copy githooks/pre-commit, githooks/pre-commit.jl, githooks/pre-push, "
            "githooks/pre-push.jl and scripts/test-layout.jl "
            "into .githooks/ of each git repository below Packages/ and Experiments/, "
            "and set core.hooksPath. Without --apply it prints what would change and "
            "exits 1 when something would; --apply copies the files and sets the path. "
            "A path that cannot be set is printed with its command, and the subcommand "
            "exits with status 2.",
        )
    ).set_defaults(run=cmd_githooks)
    changing(
        sub.add_parser(
            "wiki-lint-hook",
            help="install the wiki-lint hook into the prose repositories",
            description="Copy githooks/pre-commit-wiki as .githooks/pre-commit into each prose "
            "repository of the research tree, and set core.hooksPath. Without --apply "
            "it prints what would change and exits 1 when something would; --apply "
            "copies the file and sets the path.",
        )
    ).set_defaults(run=cmd_wiki_lint_hook)
    changing(
        sub.add_parser(
            "workflows",
            help="install the canonical GitHub workflows",
            description="Copy the canonical files of githooks/workflows/ into each package and "
            "experiment that has a Project.toml, and remove the retired CompatHelper.yml. "
            "Dependents.yml and dependents.jl go into each base of the profile's "
            "dependents_bases only, and are removed from every other repository. "
            "Without --apply it prints what would change and exits 1 when something "
            "would; --apply writes and removes the files.",
        )
    ).set_defaults(run=cmd_workflows)
    changing(
        sub.add_parser(
            "dependents",
            help="write the list of direct dependents into each base of dependents_bases",
            description="Write .github/dependents.toml into each base that the profile's "
            "dependents_bases names: one [[dependent]] table per repository below Packages/ "
            "whose Project.toml has the base's UUID in [deps], with its name and its GitHub "
            "owner/name from the origin. Without --apply it prints the diff of each file "
            "that would change and exits 1 when one would; --apply writes the files. It "
            "does not commit.",
        )
    ).set_defaults(run=cmd_dependents)
