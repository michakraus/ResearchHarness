"""Protect the default branch of every package and experiment, and of the Harness itself, with a
repository ruleset.

    harness ci-protection [--apply]                    # ruleset `main`, auto-merge, delete merged heads
    harness ci-protection --remove-classic [--apply]   # delete classic protection where the ruleset is right

Run the ruleset first and `--remove-classic` afterwards. `--remove-classic` reads each ruleset
back and deletes classic protection only in a repository whose ruleset passes every check, so a
branch is never left unprotected. Both read the current state first: a repository whose ruleset
and flags are right is not written, so a run with nothing to do changes nothing.

Where to run it. Run this yourself, not from an agent shell. In the agent sandbox only the first
`gh` call of a process succeeds; every later one dies with `x509: OSStatus -26276`, a keychain
XPC failure, not a certificate problem. A call that fails that way is retried four times.

Required checks. There are two static lists of required checks. The packages and experiments
with a CI.yml and no test/ci-groups.toml require REQUIRED_CHECKS. CI.yml is byte-identical in
every repository, its matrix is `version: [min, 1]` rather than version numbers, and its job
names carry no event suffix. `min` resolves each package's own `[compat] julia` floor, so one
matrix tests the right versions everywhere, and the check names never change. A required check
that never reports leaves every pull request pending, unmergeable, with no error anywhere; so the
list is correct only while the workflows are canonical, and the subcommand refuses to run unless
`verify-workflows.jl` passes.

A repository with test/ci-groups.toml runs each test job once per group, and CI.yml then ends
each job name with ` - <group>`. Its matrix is an expression that reads the file at run time,
which `workflow_checks` does not read, so `required_checks` reads the file of the working tree
instead. The pull request that adds or changes the file still runs against the old list, so
merge it with the admin bypass and run this subcommand after the merge.

`pre` and `nightly` are not required: they are `experimental: true`, and requiring them would block
merges whenever an unreleased Julia breaks upstream.

The Harness, the repository that runs the command, comes last and requires HARNESS_CHECKS: each
job of its .github/workflows/test.yml that reports on every pull request and is not a warning.
A case reads test.yml with `workflow_checks` and fails when the list differs from it, so a renamed
or an added job fails `harness test` rather than leave every pull request pending.

Rulesets. Each repository has one ruleset, named `main`, matched by name and updated in place;
one that matches no branch is repaired, not duplicated. More than one named `main` is an error; rulesets of other
names are left alone. Rulesets need a public repository on the Free plan, and organisation-level
rulesets need the Team plan, which a free organisation does not have.

Admin bypass. The admin bypass is load-bearing. `bypass_actors` gives the repository-admin role
(actor_id 5) the `always` mode, so the owner can push the narrow direct-to-main commits: a release
commit, a typo fix, a sync of the shared git hooks. No review rule: in a single-author tree a
required review is self-review.

Classic protection and rulesets. The two have separate endpoints, and each hides the other.
`repos/<slug>/branches/<branch>/protection` answers 404 `Branch not protected` when only a ruleset
guards the branch, and `repos/<slug>/rules/branches/<branch>` answers `[]` when only classic
protection does. An `enforcement: active` ruleset whose `conditions.ref_name.include` is empty
matches no branch. For a repository the account does not own, GraphQL returns empty lists rather
than an error, so an empty answer means unknown. Until `--remove-classic` runs, both mechanisms
apply, and the stricter rule of each wins.

Stale remotes. The slug is resolved through the API, not taken from `origin`. A stale remote is
invisible until a write: after a rename or a move, GitHub redirects reads and pushes, but the
REST write endpoint for protection does not follow the redirect. Protection needs admin rights
and, on a free plan, a public repository. Both are per-run facts: a repository skipped today is
not skipped forever.
"""

import argparse
import contextlib
import io
import itertools
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable
from typing import Any, cast
from unittest import mock

from . import REPO, HarnessError, changing, fmt, jsonio, outcome
from .githooks import git, repositories

# The required status checks of a repository without test/ci-groups.toml: the non-experimental
# jobs of the canonical CI.yml, `test` over version x os with `arch: default`, and the single pinned
# `doctest` entry. verify-workflows.jl prints the same list from the template. `required_checks`
# gives a repository with test groups its own list.
REQUIRED_CHECKS = [
    "Julia min - ubuntu-latest - default",
    "Julia min - macOS-latest - default",
    "Julia min - windows-latest - default",
    "Julia 1 - ubuntu-latest - default",
    "Julia 1 - macOS-latest - default",
    "Julia 1 - windows-latest - default",
    "Doctests - ubuntu-latest",
]

# The required status checks of the Harness itself: the contexts of its .github/workflows/test.yml
# that report on every pull request and are not warnings. `workflow_checks` reads them from the
# file, and a case holds this list equal to it. julia.yml and docs.yml are not here: their path
# filters leave a pull request outside their paths with no report from them.
HARNESS_CHECKS = [
    "Python 3.14",
    "harness test with an empty HOME",
    "changelog fragment",
    "systemd-analyze verify",
    "dotfiles",
    "lint",
    "leaks",
    "ruff and basedpyright",
]


def ruleset_for(checks: list[str]) -> dict[str, Any]:
    """The ruleset `main` that requires `checks`. `~DEFAULT_BRANCH`, so a repository whose default
    branch is `master` is covered too."""
    return {
        "name": "main",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [{"context": c} for c in checks],
                },
            },
        ],
    }


# What GitHub allows in an owner or a repository name, and in a branch name as read here. On
# failure `gh` prints its error to stdout, and an error that mentions a URL holds slashes, so the
# shape is checked, not only the presence of a slash.
SLUG = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
BRANCH = re.compile(r"[A-Za-z0-9._/-]+")


class GhError(Exception):
    """A `gh` call that failed; the message is its first line of output."""


def gh(*args: str, payload: str | None = None) -> str:
    """Run `gh args` and return its stdout; retry the keychain XPC failure four times."""
    out = ""
    for attempt in range(4):
        p = subprocess.run(
            ["gh", *args],  # noqa: S607 -- gh runs from PATH, where the user installs it
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if p.returncode == 0:
            return p.stdout
        out = (p.stdout + p.stderr).strip()
        if "OSStatus -26276" not in out and "tls: failed to verify certificate" not in out:
            break
        time.sleep(2 * (attempt + 1))
    raise GhError((out.splitlines() or ["no output"])[0][:100])


def gh_object(*args: str) -> dict[str, Any]:
    """The JSON object that `gh args` prints; a refusal of `jsonio` names the command."""
    return jsonio.loads(gh(*args), where=f"gh {' '.join(args[:2])}")


def gh_array(*args: str) -> list[Any]:
    """The JSON array that `gh args` prints; a refusal of `jsonio` names the command."""
    return jsonio.loads(gh(*args), where=f"gh {' '.join(args[:2])}", top=list)


def ruleset_problem(ruleset: dict[str, Any], contexts: list[str]) -> str | None:
    """The first reason a ruleset read back from GitHub is not `ruleset_for(contexts)`, or None
    when it is."""
    rules = ruleset.get("rules", [])
    types = [r.get("type") for r in rules]
    checks = [r.get("parameters", {}) for r in rules if r.get("type") == "required_status_checks"]
    include = ruleset.get("conditions", {}).get("ref_name", {}).get("include")
    if ruleset.get("enforcement") != "active":
        return f"enforcement is {ruleset.get('enforcement')}"
    if include != ["~DEFAULT_BRANCH"]:
        return f"branch list is {include}"
    if ruleset.get("current_user_can_bypass") != "always":
        return f"admin bypass is {ruleset.get('current_user_can_bypass')}"
    if "deletion" not in types or "non_fast_forward" not in types:
        return "deletion or force-push is not blocked"
    if [c.get("strict_required_status_checks_policy") for c in checks] != [True]:
        return "required checks missing or not strict"
    required = sorted(c.get("context") for c in checks[0].get("required_status_checks", []))
    return None if required == sorted(contexts) else "required checks differ"


def verify_workflows():
    """Refuse unless the workflows are canonical: REQUIRED_CHECKS depends on it."""
    print("verifying that the workflows are canonical...", flush=True)
    verifier = REPO / "githooks" / "verify-workflows.jl"
    p = subprocess.run(  # no timeout: a Julia process, which compiles before it checks
        ["julia", "--startup-file=no", str(verifier), "--quiet"],  # noqa: S607 -- julia runs from PATH
        check=False,
    )
    if p.returncode != 0:
        raise HarnessError(
            "workflows have drifted; protection not touched — run `harness workflows --apply` first"
        )
    print("workflows are canonical.\n")


def resolve(repo: pathlib.Path) -> tuple[str, str]:
    """(slug, branch) of a repository that can be protected; a skip or a failure otherwise."""
    url = git(repo, "remote", "get-url", "origin").stdout.strip()
    m = re.match(r"(?:git@github\.com:|https://github\.com/)(.+?)(?:\.git)?$", url)
    if not m or "/" not in m.group(1):
        return "skip", "no github origin"
    slug = m.group(1)
    owner, name = slug.split("/", 1)
    query = (
        "query($o:String!, $n:String!) { repository(owner:$o, name:$n) "
        "{ nameWithOwner isPrivate viewerPermission defaultBranchRef { name } } }"
    )
    data = gh_object("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"n={name}")
    meta = (data.get("data") or {}).get("repository") or {}
    canonical = meta.get("nameWithOwner") or ""
    branch = (meta.get("defaultBranchRef") or {}).get("name") or ""
    if not SLUG.fullmatch(canonical):
        raise GhError(f"cannot resolve {slug}")
    if canonical != slug:
        raise GhError(
            f"STALE REMOTE: origin says {slug}, GitHub says {canonical}; fix it with "
            f"`cd {repo} && git remote set-url origin https://github.com/{canonical}`"
        )
    if meta.get("viewerPermission") != "ADMIN":
        return "skip", f"viewer permission is {meta.get('viewerPermission')}, protection needs ADMIN"
    if meta.get("isPrivate"):
        return "skip", "repository is private; protected branches need a paid plan"
    if not BRANCH.fullmatch(branch):
        raise GhError(f"cannot read the default branch of {slug}")
    return slug, branch


def ruleset_id(slug):
    """The id of the repository's own branch ruleset named `main`, or None."""
    ids = [
        r["id"]
        for r in gh_array("api", f"repos/{slug}/rulesets")
        if r.get("name") == "main" and r.get("target") == "branch" and r.get("source_type") == "Repository"
    ]
    if len(ids) > 1:
        raise GhError(f"more than one ruleset named main ({ids}); delete all but one")
    return ids[0] if ids else None


def plan_ruleset(slug: str, rid: int | None, checks: list[str]) -> list[str]:
    """What the ruleset step would change: a list of short descriptions."""
    todo: list[str] = []
    if rid is None:
        todo.append("create ruleset main")
    else:
        problem = ruleset_problem(gh_object("api", f"repos/{slug}/rulesets/{rid}"), checks)
        if problem:
            todo.append(f"update ruleset {rid} ({problem})")
    flags = gh_object("api", f"repos/{slug}")
    if not (flags.get("allow_auto_merge") and flags.get("delete_branch_on_merge")):
        todo.append("turn on auto-merge and the deletion of merged branches")
    return todo


def apply_ruleset(slug: str, rid: int | None, todo: list[str], checks: list[str]) -> None:
    body = json.dumps(ruleset_for(checks))
    if any(t.startswith(("create", "update")) for t in todo):
        if rid is None:
            gh("api", "--method", "POST", f"repos/{slug}/rulesets", "--input", "-", payload=body)
        else:
            gh("api", "--method", "PUT", f"repos/{slug}/rulesets/{rid}", "--input", "-", payload=body)
    if any(t.startswith("turn on") for t in todo):
        gh(
            "api",
            "--method",
            "PATCH",
            f"repos/{slug}",
            "-F",
            "allow_auto_merge=true",
            "-F",
            "delete_branch_on_merge=true",
        )


def plan_classic(slug: str, branch: str, rid: int | None, checks: list[str]) -> list[str]:
    """What `--remove-classic` would change; a GhError when the ruleset is not right yet."""
    if rid is None:
        raise GhError("no ruleset named main; run `harness ci-protection --apply` first")
    problem = ruleset_problem(gh_object("api", f"repos/{slug}/rulesets/{rid}"), checks)
    if problem:
        raise GhError(f"classic protection kept: ruleset {rid}: {problem}")
    try:
        gh("api", f"repos/{slug}/branches/{branch}/protection")
    except GhError as e:
        if "Branch not protected" in str(e):
            return []
        raise
    return ["remove classic protection"]


# A group of test/ci-groups.toml, as CI.yml's `groups` job accepts it.
GROUP_NAME = re.compile(r"[a-z][a-z0-9]*")


def ci_groups(repo: pathlib.Path) -> list[str] | None:
    """The groups of the repository's test/ci-groups.toml, or None where it has none. A file whose
    `groups` is not a list of distinct group names, which CI.yml's `groups` job refuses too, is a
    HarnessError."""
    path = repo / "test" / "ci-groups.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path}: not valid TOML: {e}") from e
    value: object = data.get("groups")
    items = cast("list[object]", value) if isinstance(value, list) else []
    groups = [g for g in items if isinstance(g, str) and GROUP_NAME.fullmatch(g)]
    if not groups or len(groups) != len(items) or len(set(groups)) != len(groups):
        raise HarnessError(f"{path}: `groups` is not a list of distinct group names")
    return groups


def required_checks(repo: pathlib.Path) -> list[str]:
    """The required checks of a package or an experiment: REQUIRED_CHECKS without a group file, and
    with one, each `Julia` check once per group, ` - <group>` at its end, as CI.yml names its jobs,
    and the doctest check."""
    groups = ci_groups(repo)
    if groups is None:
        return REQUIRED_CHECKS
    julia = [c for c in REQUIRED_CHECKS if c.startswith("Julia ")]
    return [f"{c} - {g}" for c in julia for g in groups] + [c for c in REQUIRED_CHECKS if c not in julia]


def targets() -> list[tuple[pathlib.Path, list[str]]]:
    """The repositories that `ci-protection` protects, in order, each with its required checks:
    each package and experiment with a CI.yml, with `required_checks`, then the Harness that runs
    the command, REPO, with HARNESS_CHECKS. The Harness comes last, so that the failure of a
    package does not hide it."""
    found = [
        (repo, required_checks(repo))
        for repo, _ in cast("list[tuple[pathlib.Path, str]]", repositories())
        if (repo / ".github" / "workflows" / "CI.yml").is_file()
    ]
    return [*found, (REPO, HARNESS_CHECKS)]


# A whole value `${{ matrix.<key> }}`, and one such reference in a longer text.
MATRIX_VALUE = re.compile(r"\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}")
# The one `if:` that a required job may carry: it runs on every pull request.
PULL_REQUESTS = "github.event_name == 'pull_request'"


def table(value: object, where: str, what: str) -> dict[str, object]:
    """`value` as a table with text keys; a HarnessError that names `what` otherwise."""
    if not isinstance(value, dict):
        raise HarnessError(f"{where}: {what}")
    items = cast("dict[object, object]", value).items()
    if not all(isinstance(k, str) for k, _ in items):
        raise HarnessError(f"{where}: {what}")
    return {str(k): v for k, v in items}


def matrix_rows(job: dict[str, object], where: str) -> list[dict[str, object]]:
    """The combinations of a job's matrix, as GitHub forms them: the product of its lists, then
    each `include` entry added to every combination whose original values it keeps, or as a
    combination of its own where it keeps none. A job without a matrix has one empty combination.
    A matrix that is an expression, or that has `exclude`, is refused."""
    strategy = job.get("strategy")
    matrix = None if strategy is None else table(strategy, where, "the strategy is not a table").get("matrix")
    if matrix is None:
        return [{}]
    axes = table(matrix, where, "the matrix is not a table of lists")
    include = axes.pop("include", [])
    if "exclude" in axes or not isinstance(include, list):
        raise HarnessError(f"{where}: the matrix is not a table of lists")
    entries = [table(e, where, "an include entry is not a table") for e in cast("list[object]", include)]
    lists: list[list[object]] = []
    for value in axes.values():
        if not isinstance(value, list):
            raise HarnessError(f"{where}: the matrix is not a table of lists")
        lists.append(cast("list[object]", value))
    if not axes:
        return entries
    originals = [dict(zip(axes, values, strict=True)) for values in itertools.product(*lists)]
    rows = [dict(o) for o in originals]
    for entry in entries:
        fits = [i for i, o in enumerate(originals) if all(o[k] == v for k, v in entry.items() if k in axes)]
        for i in fits:
            rows[i] |= entry
        if not fits:
            rows.append(dict(entry))
    return rows


def matrix_text(value: object, where: str) -> str:
    """A matrix value as GitHub writes it into a name: text and a number as they are, a boolean in
    lower case."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    raise HarnessError(f"{where}: the matrix value {value!r} is not text, a number or a boolean")


def context(name: str, row: dict[str, object], where: str) -> str:
    """The context of one combination of a job: its name with each matrix reference replaced."""

    def value(m: re.Match[str]) -> str:
        if m.group(1) not in row:
            raise HarnessError(f"{where}: matrix.{m.group(1)} is not a key of the combination {row}")
        return matrix_text(row[m.group(1)], where)

    text = MATRIX_VALUE.sub(value, name)
    if "${{" in text:
        raise HarnessError(f"{where}: the name {name!r} holds an expression that this list does not read")
    return text


def warns(flag: object, row: dict[str, object], where: str) -> bool:
    """Whether `continue-on-error: flag` makes one combination a warning: `true`, `false`, or one
    matrix value that is a boolean."""
    if isinstance(flag, bool):
        return flag
    m = MATRIX_VALUE.fullmatch(flag) if isinstance(flag, str) else None
    value = row.get(m.group(1)) if m else None
    if not isinstance(value, bool):
        raise HarnessError(f"{where}: continue-on-error {flag!r} is not true, false or one matrix value")
    return value


def workflow_checks(path: pathlib.Path) -> list[str]:
    """The sorted contexts of the workflow at `path` that a ruleset can require: for each job and
    each combination of its matrix, the job's name, or its ID without one, with each matrix value
    filled in, unless `continue-on-error` makes the combination a warning. A job may carry no `if:`
    but `github.event_name == 'pull_request'`; one with another is refused with its ID, and a file
    that is not YAML is refused with the parser's reason. It reads
    `jobs` only, because YAML 1.1 reads the key `on` as `True`."""
    try:
        import yaml  # noqa: PLC0415 -- only this function needs PyYAML
    except ImportError as e:
        raise HarnessError(
            "PyYAML is not in the harness's Python environment; run harness install --apply"
        ) from e
    try:
        data: object = yaml.safe_load(path.read_text())
    except yaml.MarkedYAMLError as e:
        line = f" at line {e.problem_mark.line + 1}" if e.problem_mark else ""
        raise HarnessError(f"{path}: not valid YAML{line}: {e.problem}") from e
    except yaml.YAMLError as e:
        raise HarnessError(f"{path}: not valid YAML: {str(e).splitlines()[0]}") from e
    jobs = cast("dict[object, object]", data).get("jobs") if isinstance(data, dict) else None
    if not jobs:
        raise HarnessError(f"{path}: no jobs")
    found: set[str] = set()
    for job_id, value in table(jobs, str(path), "no jobs").items():
        where = f"{path}: job {job_id}"
        job = table(value, where, "the job is not a table")
        condition = job.get("if")
        if condition is not None and condition != PULL_REQUESTS:
            raise HarnessError(f"{where}: `if: {condition}` is not a condition that this list reads")
        name = job.get("name", job_id)
        if not isinstance(name, str):
            raise HarnessError(f"{where}: the name {name!r} is not text")
        rows = matrix_rows(job, where)
        if rows != [{}] and not MATRIX_VALUE.search(name):
            raise HarnessError(f"{where}: a matrix job whose name names no matrix value")
        found |= {
            context(name, row, where)
            for row in rows
            if not warns(job.get("continue-on-error", False), row, where)
        }
    return sorted(found)


def cmd_ci_protection(args):
    verify_workflows()
    changes = failed = 0
    for repo, checks in targets():
        try:
            slug, branch = resolve(repo)
            if slug == "skip":
                print(f"{repo.name:<28} SKIP   {branch}")
                continue
            rid = ruleset_id(slug)
            todo = (
                plan_classic(slug, branch, rid, checks)
                if cast("bool", args.remove_classic)
                else plan_ruleset(slug, rid, checks)
            )
            if not todo:
                print(f"{repo.name:<28} {branch}: up to date")
                continue
            if args.apply:
                if args.remove_classic:
                    gh("api", "--method", "DELETE", f"repos/{slug}/branches/{branch}/protection")
                else:
                    apply_ruleset(slug, rid, todo, checks)
            changes += len(todo)
            print(f"{repo.name:<28} {branch}: {'done' if args.apply else 'would'}: {'; '.join(todo)}")
        except GhError as e:
            print(f"{repo.name:<28} FAILED {e}")
            failed += 1
    print(f"\n{changes} change(s) {'made' if args.apply else 'to make'}, {failed} failed.")
    if failed:
        raise HarnessError(f"{failed} repositories failed")
    return outcome(args, changes)


def as_read(checks: list[str]) -> dict[str, Any]:
    """The ruleset that requires `checks`, as GitHub returns it to its admin."""
    return jsonio.loads(json.dumps(ruleset_for(checks)), where="ruleset") | {
        "current_user_can_bypass": "always"
    }


def ruleset_cases() -> tuple[int, int]:
    """`ruleset_problem`: the ruleset as GitHub returns it, one break of each check, and the
    ruleset of each list judged against the other list."""
    good = as_read(REQUIRED_CHECKS)

    def broken(change: Callable[[dict[str, Any]], object], base: dict[str, Any] = good) -> dict[str, Any]:
        r = jsonio.loads(json.dumps(base), where="ruleset")
        change(r)
        return r

    cases = [
        (good, REQUIRED_CHECKS, None),
        (broken(lambda r: r.update(enforcement="disabled")), REQUIRED_CHECKS, "enforcement is disabled"),
        (
            broken(lambda r: r["conditions"]["ref_name"].update(include=[])),
            REQUIRED_CHECKS,
            "branch list is []",
        ),
        (
            broken(lambda r: r.update(current_user_can_bypass="never")),
            REQUIRED_CHECKS,
            "admin bypass is never",
        ),
        (broken(lambda r: r["rules"].pop(1)), REQUIRED_CHECKS, "deletion or force-push is not blocked"),
        (
            broken(lambda r: r["rules"][2]["parameters"].update(strict_required_status_checks_policy=False)),
            REQUIRED_CHECKS,
            "required checks missing or not strict",
        ),
        (
            broken(lambda r: r["rules"][2]["parameters"]["required_status_checks"].pop()),
            REQUIRED_CHECKS,
            "required checks differ",
        ),
        (as_read(HARNESS_CHECKS), HARNESS_CHECKS, None),
        (as_read(HARNESS_CHECKS), REQUIRED_CHECKS, "required checks differ"),
        (as_read(REQUIRED_CHECKS), HARNESS_CHECKS, "required checks differ"),
        (
            broken(
                lambda r: r["rules"][2]["parameters"]["required_status_checks"].pop(), as_read(HARNESS_CHECKS)
            ),
            HARNESS_CHECKS,
            "required checks differ",
        ),
    ]
    wrong = 0
    for ruleset, checks, expected in cases:
        got = ruleset_problem(ruleset, checks)
        wrong += got != expected
        against = "HARNESS_CHECKS" if checks is HARNESS_CHECKS else "REQUIRED_CHECKS"
        print(f"{'ok ' if got == expected else 'BAD'}  ruleset against {against} -> {got!r}")
    return len(cases), wrong


def scratch_root(root: pathlib.Path) -> None:
    """A research root with the packages A (a CI.yml) and B (none) and the experiment C (a
    CI.yml), each a directory with a `.git`, as `repositories()` reads it."""
    for group, name, ci in (("Packages", "A", True), ("Packages", "B", False), ("Experiments", "C", True)):
        repo = root / group / name
        (repo / ".git").mkdir(parents=True)
        if ci:
            (repo / ".github" / "workflows").mkdir(parents=True)
            (repo / ".github" / "workflows" / "CI.yml").write_text("name: CI\n")


# The required checks of a repository whose test/ci-groups.toml lists `core` and `long`.
GROUPED_CHECKS = [
    "Julia min - ubuntu-latest - default - core",
    "Julia min - ubuntu-latest - default - long",
    "Julia min - macOS-latest - default - core",
    "Julia min - macOS-latest - default - long",
    "Julia min - windows-latest - default - core",
    "Julia min - windows-latest - default - long",
    "Julia 1 - ubuntu-latest - default - core",
    "Julia 1 - ubuntu-latest - default - long",
    "Julia 1 - macOS-latest - default - core",
    "Julia 1 - macOS-latest - default - long",
    "Julia 1 - windows-latest - default - core",
    "Julia 1 - windows-latest - default - long",
    "Doctests - ubuntu-latest",
]


def target_cases() -> tuple[int, int]:
    """`targets()` on a scratch research root: the repositories with a CI.yml, each with the list
    of its group file or REQUIRED_CHECKS, then the Harness; and `required_checks` on group files
    that CI.yml's `groups` job refuses."""
    wrong = 0

    def check(label: str, got: object, expected: object) -> None:
        nonlocal wrong
        ok = got == expected
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  {label}")
        if not ok:
            print(f"     got {got!r}")

    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"RESEARCH_ROOT": tmp}):
        root = pathlib.Path(tmp)
        scratch_root(root)
        got = [(repo.name if repo != REPO else "REPO", checks) for repo, checks in targets()]
        check(
            "targets: A and C with REQUIRED_CHECKS, then REPO last with HARNESS_CHECKS",
            got,
            [("A", REQUIRED_CHECKS), ("C", REQUIRED_CHECKS), ("REPO", HARNESS_CHECKS)],
        )
        (root / "Packages" / "A" / "test").mkdir()
        groups = root / "Packages" / "A" / "test" / "ci-groups.toml"
        groups.write_text('# The groups.\ngroups = ["core", "long"]\n')
        got = [(repo.name if repo != REPO else "REPO", checks) for repo, checks in targets()]
        check(
            "targets: A with the checks of its group file, C with REQUIRED_CHECKS",
            got,
            [("A", GROUPED_CHECKS), ("C", REQUIRED_CHECKS), ("REPO", HARNESS_CHECKS)],
        )
        refused = {
            "a list that is empty": "groups = []\n",
            "a group twice": 'groups = ["core", "core"]\n',
            "a name with an upper-case letter": 'groups = ["core", "Long"]\n',
            "a name that is not text": 'groups = ["core", 3]\n',
            "a text in place of a list": 'groups = "core"\n',
            "no `groups`": 'group = ["core"]\n',
            "a file that is not TOML": "groups = [\n",
        }
        for label, text in refused.items():
            groups.write_text(text)
            try:
                got = required_checks(root / "Packages" / "A")
            except HarnessError as e:
                got = str(e).removeprefix(f"{groups}: ").split(":")[0]
            expected = (
                "not valid TOML"
                if label == "a file that is not TOML"
                else ("`groups` is not a list of distinct group names")
            )
            check(f"required_checks: a group file with {label} is refused", got, expected)
    return 2 + len(refused), wrong


def workflow_cases() -> tuple[int, int]:
    """`workflow_checks` on the Harness's own test.yml and on small workflows, one rule each."""
    own = REPO / ".github" / "workflows" / "test.yml"
    matrix = "    strategy:\n      matrix:\n"
    cases: list[tuple[str, str | None, list[str] | str]] = [
        ("the Harness's test.yml gives HARNESS_CHECKS", None, sorted(HARNESS_CHECKS)),
        (
            "test.yml with `ruff and basedpyright` renamed differs",
            own.read_text().replace("name: ruff and basedpyright", "name: ruff and pyright"),
            sorted([*(c for c in HARNESS_CHECKS if c != "ruff and basedpyright"), "ruff and pyright"]),
        ),
        ("a job without a name reports its ID", "jobs:\n  lint:\n    runs-on: x\n", ["lint"]),
        (
            "a job of pull requests only is required",
            "jobs:\n  c:\n    name: fragment\n    if: github.event_name == 'pull_request'\n",
            ["fragment"],
        ),
        (
            "a job with another `if:` is refused with its ID",
            "jobs:\n  c:\n    if: github.event_name == 'push'\n",
            "job c: `if: github.event_name == 'push'` is not a condition that this list reads",
        ),
        (
            "a job with continue-on-error true is a warning",
            "jobs:\n  a:\n    runs-on: x\n  b:\n    continue-on-error: true\n",
            ["a"],
        ),
        (
            "a job with continue-on-error false is required",
            "jobs:\n  b:\n    continue-on-error: false\n",
            ["b"],
        ),
        (
            "a matrix name is expanded for each value",
            "jobs:\n  t:\n    name: T ${{ matrix.v }} - ${{ matrix.os }}\n"
            + matrix
            + "        v: ['1', '2']\n        os: [u]\n",
            ["T 1 - u", "T 2 - u"],
        ),
        (
            "an include that matches no combination adds one, and its warn makes it a warning",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n    continue-on-error: ${{ matrix.warn }}\n"
            + matrix
            + "        v: ['1']\n        warn: [false]\n        include:\n          - v: '2'\n"
            + "            warn: true\n          - v: '3'\n            warn: false\n",
            ["T 1", "T 3"],
        ),
        (
            "an include that matches a combination extends it",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n    continue-on-error: ${{ matrix.warn }}\n"
            + matrix
            + "        v: ['1', '2']\n        include:\n          - v: '1'\n            warn: true\n"
            + "          - v: '2'\n            warn: false\n",
            ["T 2"],
        ),
        (
            "a matrix of include entries only has one combination each",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n"
            + matrix
            + "        include:\n          - v: a\n          - v: b\n",
            ["T a", "T b"],
        ),
        (
            "a boolean and a number of the matrix read as GitHub writes them",
            "jobs:\n  t:\n    name: T ${{ matrix.f }} ${{ matrix.n }}\n"
            + matrix
            + "        f: [true]\n        n: [3]\n",
            ["T true 3"],
        ),
        (
            "a matrix job whose name names no matrix value is refused",
            "jobs:\n  t:\n    name: T\n" + matrix + "        v: ['1']\n",
            "job t: a matrix job whose name names no matrix value",
        ),
        (
            "a name that names a value outside the combination is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.w }}\n" + matrix + "        v: ['1']\n",
            "job t: matrix.w is not a key of the combination {'v': '1'}",
        ),
        (
            "a name with another expression is refused",
            "jobs:\n  t:\n    name: T ${{ github.ref }}\n",
            "job t: the name 'T ${{ github.ref }}' holds an expression that this list does not read",
        ),
        (
            "a matrix of an expression is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n    strategy:\n      matrix: ${{ fromJSON(x) }}\n",
            "job t: the matrix is not a table of lists",
        ),
        (
            "a matrix with exclude is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n"
            + matrix
            + "        v: ['1']\n        exclude:\n          - v: '1'\n",
            "job t: the matrix is not a table of lists",
        ),
        (
            "continue-on-error of another expression is refused",
            "jobs:\n  t:\n    continue-on-error: ${{ github.x }}\n",
            "job t: continue-on-error '${{ github.x }}' is not true, false or one matrix value",
        ),
        (
            "continue-on-error on a matrix value that is not a boolean is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n    continue-on-error: ${{ matrix.v }}\n"
            + matrix
            + "        v: ['1']\n",
            "job t: continue-on-error '${{ matrix.v }}' is not true, false or one matrix value",
        ),
        (
            "a matrix whose list is a single value is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n" + matrix + "        v: '1'\n",
            "job t: the matrix is not a table of lists",
        ),
        (
            "a matrix with a key that is not text is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n" + matrix + "        v: ['1']\n        2: ['3']\n",
            "job t: the matrix is not a table of lists",
        ),
        (
            "a matrix whose include is not a list is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n" + matrix + "        v: ['1']\n        include: x\n",
            "job t: the matrix is not a table of lists",
        ),
        (
            "an include that matches a combination adds none of its own",
            "jobs:\n  t:\n    name: T ${{ matrix.v }} ${{ matrix.os }}\n"
            + matrix
            + "        v: ['1']\n        os: [a]\n"
            + "        include:\n          - os: a\n            extra: e\n",
            ["T 1 a"],
        ),
        (
            "a matrix value that is a list is refused",
            "jobs:\n  t:\n    name: T ${{ matrix.v }}\n" + matrix + "        v: [[1, 2]]\n",
            "job t: the matrix value [1, 2] is not text, a number or a boolean",
        ),
        ("a job that is not a table is refused", "jobs:\n  a: 3\n", "job a: the job is not a table"),
        (
            "a job whose name is not text is refused",
            "jobs:\n  t:\n    name: 3\n",
            "job t: the name 3 is not text",
        ),
        ("a workflow with no jobs is refused", "on: push\n", "no jobs"),
        ("a workflow with an empty table of jobs is refused", "jobs: {}\n", "no jobs"),
        ("a workflow that is not a table is refused", "- a\n", "no jobs"),
        (
            "a workflow that is not YAML is refused",
            "jobs: [\n",
            "not valid YAML at line 2: expected the node content, but found '<stream end>'",
        ),
        (
            "a workflow with a character that YAML refuses is refused",
            "jobs: \x01\n",
            "not valid YAML: unacceptable character #x0001: special characters are not allowed",
        ),
    ]
    wrong = 0
    with tempfile.TemporaryDirectory() as tmp:
        for label, text, expected in cases:
            path = own
            if text is not None:
                path = pathlib.Path(tmp) / "w.yml"
                path.write_text(text)
            try:
                got: list[str] | str = workflow_checks(path)
            except HarnessError as e:
                got = str(e).removeprefix(f"{path}: ")
            ok = got == expected
            wrong += not ok
            print(f"{'ok ' if ok else 'BAD'}  workflow: {label}")
            if not ok:
                print(f"     got {got!r}")
    return len(cases), wrong


def command_cases() -> tuple[int, int]:
    """`cmd_ci_protection` on a scratch research root with `gh` replaced: each target is planned,
    written and read back with its own list of required checks."""
    harness_slug = f"o/{REPO.name}"
    written: list[tuple[str, ...]] = []

    def fake_gh(*argv: str, payload: str | None = None) -> str:
        written.append((*argv, payload or ""))
        if argv[-1].endswith("/A/branches/main/protection"):
            raise GhError("Branch not protected")
        return ""

    def fake_resolve(repo: pathlib.Path) -> tuple[str, str]:
        return f"o/{repo.name}", "main"

    def fake_object(*argv: str) -> dict[str, Any]:
        if argv[-1].endswith("/rulesets/1"):
            # Ruleset 1 is the packages' ruleset, and ruleset 2 the Harness's.
            return as_read(REQUIRED_CHECKS)
        if argv[-1].endswith("/rulesets/2"):
            return as_read(HARNESS_CHECKS)
        return {"allow_auto_merge": True, "delete_branch_on_merge": True}

    def required_in(calls: list[tuple[str, ...]]) -> list[str]:
        """The contexts of the one ruleset that `calls` write, or [] unless they write one."""
        if len(calls) != 1:
            return []
        body: dict[str, Any] = jsonio.loads(calls[0][-1], where="payload")
        return [c["context"] for c in body["rules"][2]["parameters"]["required_status_checks"]]

    def run(*, apply: bool, remove_classic: bool, rid: Callable[[str], int | None]) -> tuple[int, list[str]]:
        written.clear()
        out = io.StringIO()
        args = argparse.Namespace(apply=apply, remove_classic=remove_classic)
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"RESEARCH_ROOT": tmp}),
            mock.patch.multiple(
                sys.modules[__name__],
                verify_workflows=lambda: None,
                resolve=fake_resolve,
                ruleset_id=rid,
                gh=fake_gh,
                gh_object=fake_object,
            ),
            contextlib.redirect_stdout(out),
        ):
            scratch_root(pathlib.Path(tmp))
            try:
                status = cmd_ci_protection(args)
            except HarnessError:
                # A repository that failed: `harness` exits 2.
                status = 2
        return status, out.getvalue().splitlines()

    wrong = 0

    def check(label: str, seen: object, *, ok: bool) -> None:
        nonlocal wrong
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  ci-protection: {label}")
        if not ok:
            print(f"     got {seen!r}")

    status, lines = run(apply=False, remove_classic=False, rid=lambda _slug: 1)
    expected = [
        f"{'A':<28} main: up to date",
        f"{'C':<28} main: up to date",
        f"{REPO.name:<28} main: would: update ruleset 1 (required checks differ)",
    ]
    check(
        "the dry run plans the Harness last, against HARNESS_CHECKS",
        lines,
        ok=status == 1 and lines[:3] == expected,
    )

    status, lines = run(apply=True, remove_classic=False, rid=lambda _slug: 1)
    puts = [w for w in written if "PUT" in w]
    check(
        "--apply writes the Harness's ruleset with HARNESS_CHECKS, and no package's",
        (puts, lines),
        ok=status == 0
        and [w[3] for w in puts] == [f"repos/{harness_slug}/rulesets/1"]
        and required_in(puts) == HARNESS_CHECKS,
    )

    status, lines = run(apply=False, remove_classic=False, rid=lambda _slug: None)
    check(
        "the dry run creates the Harness's ruleset where it has none",
        lines,
        ok=status == 1 and lines[2:3] == [f"{REPO.name:<28} main: would: create ruleset main"],
    )

    status, lines = run(apply=True, remove_classic=False, rid=lambda _slug: None)
    posts = [w for w in written if "POST" in w and w[3] == f"repos/{harness_slug}/rulesets"]
    check(
        "--apply creates the Harness's ruleset with HARNESS_CHECKS",
        (posts, lines),
        ok=status == 0 and required_in(posts) == HARNESS_CHECKS,
    )

    status, lines = run(apply=False, remove_classic=True, rid=lambda slug: 2 if slug == harness_slug else 1)
    expected = [
        f"{'A':<28} main: up to date",
        f"{'C':<28} main: would: remove classic protection",
        f"{REPO.name:<28} main: would: remove classic protection",
    ]
    check(
        "--remove-classic reads each ruleset back against the list of its repository",
        lines,
        ok=status == 1 and lines[:3] == expected,
    )
    return 5, wrong


def selftest():
    """Cases for `ruleset_problem`, `targets`, `workflow_checks` and `cmd_ci_protection`."""
    total = wrong = 0
    for cases in (ruleset_cases, target_cases, workflow_cases, command_cases):
        n, w = cases()
        total += n
        wrong += w
    return total, wrong


def register(sub: fmt.Subcommands) -> None:
    p = changing(
        sub.add_parser(
            "ci-protection",
            help="protect every default branch with a ruleset",
            description="Protect the default branch of each repository that has a CI.yml, and "
            "then of the Harness itself with the jobs of its test.yml, with a "
            "GitHub ruleset named `main`, and turn on auto-merge and the deletion of "
            "merged branches. Without --apply it prints what would change and exits 1 "
            "when something would; --apply writes through `gh api`. It refuses unless "
            "verify-workflows.jl passes; run it in your own terminal.",
        )
    )
    p.add_argument(
        "--remove-classic",
        action="store_true",
        help="delete classic branch protection where the ruleset is right",
    )
    p.set_defaults(run=cmd_ci_protection)
