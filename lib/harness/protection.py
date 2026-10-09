"""Protect the default branch of every package and experiment with a repository ruleset.

    harness ci-protection [--apply]                    # ruleset `main`, auto-merge, delete merged heads
    harness ci-protection --remove-classic [--apply]   # delete classic protection where the ruleset is right

Run the ruleset first and `--remove-classic` afterwards. `--remove-classic` reads each ruleset
back and deletes classic protection only in a repository whose ruleset passes every check, so a
branch is never left unprotected. Both read the current state first: a repository whose ruleset
and flags are right is not written, so a run with nothing to do changes nothing.

RUN THIS YOURSELF, NOT FROM AN AGENT SHELL. In the agent sandbox only the first `gh` call of a
process succeeds; every later one dies with `x509: OSStatus -26276`, a keychain XPC failure, not a
certificate problem. A call that fails that way is retried four times.

ONE STATIC LIST OF REQUIRED CHECKS. CI.yml is byte-identical in every repository, its matrix is
`version: [min, 1]` rather than version numbers, and its job names carry no event suffix. `min`
resolves each package's own `[compat] julia` floor, so one matrix tests the right versions
everywhere, and the check names never change. A required check that never reports leaves every
pull request pending, unmergeable, with no error anywhere; so the list is correct only while the
workflows are canonical, and the verb refuses to run unless `verify-workflows.jl` passes.

`pre` and `nightly` are not required: they are `experimental: true`, and requiring them would block
merges whenever an unreleased Julia breaks upstream.

ONE RULESET PER REPOSITORY, named `main`, matched by name and updated in place; one that matches
no branch is repaired, not duplicated. More than one named `main` is an error; rulesets of other
names are left alone. Rulesets need a public repository on the Free plan, and organisation-level
rulesets need the Team plan, which a free organisation does not have.

THE ADMIN BYPASS IS LOAD-BEARING. `bypass_actors` gives the repository-admin role (actor_id 5)
the `always` mode, so the owner can push the narrow direct-to-main commits: a release commit, a
typo fix, a sync of the shared git hooks. No review rule: in a single-author tree a required review
is self-review.

CLASSIC PROTECTION AND RULESETS HAVE SEPARATE ENDPOINTS, AND EACH HIDES THE OTHER.
`repos/<slug>/branches/<branch>/protection` answers 404 `Branch not protected` when only a ruleset
guards the branch, and `repos/<slug>/rules/branches/<branch>` answers `[]` when only classic
protection does. An `enforcement: active` ruleset whose `conditions.ref_name.include` is empty
matches no branch. For a repository the account does not own, GraphQL returns empty lists rather
than an error, so an empty answer means unknown. Until `--remove-classic` runs, both mechanisms
apply, and the stricter rule of each wins.

The slug is resolved through the API, not taken from `origin`. A STALE REMOTE IS INVISIBLE UNTIL
A WRITE: after a rename or a move, GitHub redirects reads and pushes, but the REST write endpoint
for protection does not follow the redirect. PROTECTION NEEDS ADMIN AND, on a free plan, A PUBLIC
REPOSITORY. Both are per-run facts: a repository skipped today is not skipped forever.
"""

import json
import re
import subprocess
import time

from . import REPO, HarnessError, changing, outcome
from .githooks import git, repositories

# The required status checks: the non-experimental jobs of the canonical CI.yml, `test` over
# version x os with `arch: default`, and the single pinned `doctest` entry. verify-workflows.jl
# prints the same list from the template.
REQUIRED_CHECKS = [
    "Julia min - ubuntu-latest - default",
    "Julia min - macOS-latest - default",
    "Julia min - windows-latest - default",
    "Julia 1 - ubuntu-latest - default",
    "Julia 1 - macOS-latest - default",
    "Julia 1 - windows-latest - default",
    "Doctests - ubuntu-latest",
]

# `~DEFAULT_BRANCH`, so a repository whose default branch is `master` is covered too.
RULESET = {
    "name": "main",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": True,
            "do_not_enforce_on_create": False,
            "required_status_checks": [{"context": c} for c in REQUIRED_CHECKS],
        }},
    ],
}

# What GitHub allows in an owner or a repository name, and in a branch name as read here. On
# failure `gh` prints its error to stdout, and an error that mentions a URL holds slashes, so the
# shape is checked, not only the presence of a slash.
SLUG = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
BRANCH = re.compile(r"[A-Za-z0-9._/-]+")


class GhError(Exception):
    """A `gh` call that failed; the message is its first line of output."""


def gh(*args, payload=None):
    """Run `gh args` and return its stdout; retry the keychain XPC failure four times."""
    for attempt in range(4):
        p = subprocess.run(["gh", *args], input=payload, capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout
        out = (p.stdout + p.stderr).strip()
        if "OSStatus -26276" not in out and "tls: failed to verify certificate" not in out:
            break
        time.sleep(2 * (attempt + 1))
    raise GhError((out.splitlines() or ["no output"])[0][:100])


def ruleset_problem(ruleset):
    """The first reason a ruleset read back from GitHub is not RULESET, or None when it is."""
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
    if sorted(c.get("context") for c in checks[0].get("required_status_checks", [])) != sorted(REQUIRED_CHECKS):
        return "required checks differ"
    return None


def verify_workflows():
    """Refuse unless the workflows are canonical: the static check list depends on it."""
    print("verifying that the workflows are canonical...", flush=True)
    verifier = REPO / "githooks" / "verify-workflows.jl"
    p = subprocess.run(["julia", "--startup-file=no", str(verifier), "--quiet"])
    if p.returncode != 0:
        raise HarnessError("workflows have drifted; protection not touched — run `harness workflows --apply` first")
    print("workflows are canonical.\n")


def resolve(repo):
    """(slug, branch) of a repository that can be protected; a skip or a failure otherwise."""
    url = git(repo, "remote", "get-url", "origin").stdout.strip()
    m = re.match(r"(?:git@github\.com:|https://github\.com/)(.+?)(?:\.git)?$", url)
    if not m or "/" not in m.group(1):
        return "skip", "no github origin"
    slug = m.group(1)
    owner, name = slug.split("/", 1)
    query = ("query($o:String!, $n:String!) { repository(owner:$o, name:$n) "
             "{ nameWithOwner isPrivate viewerPermission defaultBranchRef { name } } }")
    data = json.loads(gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"n={name}"))
    meta = (data.get("data") or {}).get("repository") or {}
    canonical = meta.get("nameWithOwner") or ""
    branch = (meta.get("defaultBranchRef") or {}).get("name") or ""
    if not SLUG.fullmatch(canonical):
        raise GhError(f"cannot resolve {slug}")
    if canonical != slug:
        raise GhError(f"STALE REMOTE: origin says {slug}, GitHub says {canonical}; fix it with "
                      f"`cd {repo} && git remote set-url origin https://github.com/{canonical}`")
    if meta.get("viewerPermission") != "ADMIN":
        return "skip", f"viewer permission is {meta.get('viewerPermission')}, protection needs ADMIN"
    if meta.get("isPrivate"):
        return "skip", "repository is private; protected branches need a paid plan"
    if not BRANCH.fullmatch(branch):
        raise GhError(f"cannot read the default branch of {slug}")
    return slug, branch


def ruleset_id(slug):
    """The id of the repository's own branch ruleset named `main`, or None."""
    ids = [r["id"] for r in json.loads(gh("api", f"repos/{slug}/rulesets"))
           if r.get("name") == "main" and r.get("target") == "branch" and r.get("source_type") == "Repository"]
    if len(ids) > 1:
        raise GhError(f"more than one ruleset named main ({ids}); delete all but one")
    return ids[0] if ids else None


def plan_ruleset(slug, rid):
    """What the ruleset step would change: a list of short descriptions."""
    todo = []
    if rid is None:
        todo.append("create ruleset main")
    else:
        problem = ruleset_problem(json.loads(gh("api", f"repos/{slug}/rulesets/{rid}")))
        if problem:
            todo.append(f"update ruleset {rid} ({problem})")
    flags = json.loads(gh("api", f"repos/{slug}"))
    if not (flags.get("allow_auto_merge") and flags.get("delete_branch_on_merge")):
        todo.append("turn on auto-merge and the deletion of merged branches")
    return todo


def apply_ruleset(slug, rid, todo):
    body = json.dumps(RULESET)
    if any(t.startswith(("create", "update")) for t in todo):
        if rid is None:
            gh("api", "--method", "POST", f"repos/{slug}/rulesets", "--input", "-", payload=body)
        else:
            gh("api", "--method", "PUT", f"repos/{slug}/rulesets/{rid}", "--input", "-", payload=body)
    if any(t.startswith("turn on") for t in todo):
        gh("api", "--method", "PATCH", f"repos/{slug}", "-F", "allow_auto_merge=true",
           "-F", "delete_branch_on_merge=true")


def plan_classic(slug, branch, rid):
    """What `--remove-classic` would change; a GhError when the ruleset is not right yet."""
    if rid is None:
        raise GhError("no ruleset named main; run `harness ci-protection --apply` first")
    problem = ruleset_problem(json.loads(gh("api", f"repos/{slug}/rulesets/{rid}")))
    if problem:
        raise GhError(f"classic protection kept: ruleset {rid}: {problem}")
    try:
        gh("api", f"repos/{slug}/branches/{branch}/protection")
    except GhError as e:
        if "Branch not protected" in str(e):
            return []
        raise
    return ["remove classic protection"]


def cmd_ci_protection(args):
    verify_workflows()
    changes = failed = 0
    for repo, _ in repositories():
        if not (repo / ".github" / "workflows" / "CI.yml").is_file():
            continue
        try:
            slug, branch = resolve(repo)
            if slug == "skip":
                print(f"{repo.name:<28} SKIP   {branch}")
                continue
            rid = ruleset_id(slug)
            todo = plan_classic(slug, branch, rid) if args.remove_classic else plan_ruleset(slug, rid)
            if not todo:
                print(f"{repo.name:<28} {branch}: up to date")
                continue
            if args.apply:
                if args.remove_classic:
                    gh("api", "--method", "DELETE", f"repos/{slug}/branches/{branch}/protection")
                else:
                    apply_ruleset(slug, rid, todo)
            changes += len(todo)
            print(f"{repo.name:<28} {branch}: {'done' if args.apply else 'would'}: {'; '.join(todo)}")
        except GhError as e:
            print(f"{repo.name:<28} FAILED {e}")
            failed += 1
    print(f"\n{changes} change(s) {'made' if args.apply else 'to make'}, {failed} failed.")
    if failed:
        raise HarnessError(f"{failed} repositories failed")
    return outcome(args, changes)


def selftest():
    """Cases for `ruleset_problem`: the RULESET as GitHub returns it, and one break of each check."""
    good = json.loads(json.dumps(RULESET)) | {"current_user_can_bypass": "always"}

    def broken(change):
        r = json.loads(json.dumps(good))
        change(r)
        return r

    cases = [
        (good, None),
        (broken(lambda r: r.update(enforcement="disabled")), "enforcement is disabled"),
        (broken(lambda r: r["conditions"]["ref_name"].update(include=[])), "branch list is []"),
        (broken(lambda r: r.update(current_user_can_bypass="never")), "admin bypass is never"),
        (broken(lambda r: r["rules"].pop(1)), "deletion or force-push is not blocked"),
        (broken(lambda r: r["rules"][2]["parameters"].update(strict_required_status_checks_policy=False)),
         "required checks missing or not strict"),
        (broken(lambda r: r["rules"][2]["parameters"]["required_status_checks"].pop()), "required checks differ"),
    ]
    wrong = 0
    for ruleset, expected in cases:
        got = ruleset_problem(ruleset)
        wrong += got != expected
        print(f"{'ok ' if got == expected else 'BAD'}  ruleset -> {got!r}")
    return len(cases), wrong


def register(sub):
    p = changing(sub.add_parser("ci-protection", help="protect every default branch with a ruleset"))
    p.add_argument("--remove-classic", action="store_true",
                   help="delete classic branch protection where the ruleset is right")
    p.set_defaults(run=cmd_ci_protection)
