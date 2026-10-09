#!/usr/bin/env python3
"""Create and remove a Claude Code worktree at `~/Research/.worktrees/<Repository>-<slug>`.

One script for two hook events, told apart by `hook_event_name`:

  * **`WorktreeCreate`** — input `{"cwd": …, "name": …}`. Fetches `origin`, then runs
    `git worktree add --no-track -b <name> <path> origin/<default>` in the repository that
    owns `cwd`, and prints `<path>` on stdout. That one line is the whole of stdout; git's
    own output goes to stderr. An existing branch is checked out rather than recreated,
    and a path that is already a worktree of this repository is printed as it is.
    A name `agent-<hex>` is a sub-agent's `isolation: "worktree"`: that worktree is
    detached at the base and gets no branch, so nothing is left behind but the worktree.
    The agent makes its own branch with `git switch -c`. Either way the main checkout's
    gitignored `Manifest.toml` is copied in, so the pre-commit load test can run.
  * **`WorktreeRemove`** — input `{"worktree_path": …}`. Runs `git worktree remove <path>`
    from the owning repository. Without `--force`, so git refuses a worktree with changes.
    The branch stays: it may carry an open pull request.

Why a hook: Claude Code runs a `git worktree add` whose path is absolute, starts with `~`
or holds `..` inside the sandbox, whatever `excludedCommands` says, and the sandbox
denies every write under `.git`. Every spelling of a path under `~/Research/.worktrees/`
is one of those. `worktree.md` has the evidence.

**It fails closed.** Every error exits 1 with the reason on stderr, and Claude Code then
reports the hook as failed. No worktree is better than one in the wrong place or on the
wrong base.

Test the parts that need no repository:

    echo '{"hook_event_name":"WorktreeCreate","cwd":"/","name":"x"}' | ./worktree.py ; echo "exit $?"
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / "Research" / ".worktrees"
SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
AGENT = re.compile(r"^agent-[0-9a-f]+$")


class Refusal(Exception):
    pass


def git(*args, cwd):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise Refusal(f"`git {' '.join(args)}` in {cwd} exited {proc.returncode}")
    return proc.stdout.strip()


def owning_repository(start):
    """The main checkout of the repository that `start` belongs to, also from a linked worktree."""
    if not Path(start).is_dir():
        raise Refusal(f"{start} is not a directory")
    probe = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=start, capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise Refusal(f"{start} is not inside a git repository; `cd` into the repository first")
    common = Path(probe.stdout.strip())
    if common.name != ".git":
        raise Refusal(f"{common} is not a `.git` directory; a bare repository has no checkout to branch from")
    return common.parent


def slug(name):
    segments = name.split("/")
    if not name or any(s in ("", ".", "..") or not SEGMENT.match(s) for s in segments):
        raise Refusal(f"worktree name {name!r}: each `/`-separated segment must be letters, digits, `.`, `_` or `-`")
    return "-".join(segments)


def registered(repo, path):
    listing = git("worktree", "list", "--porcelain", cwd=repo)
    return f"worktree {path}" in listing.splitlines()


def base_ref(repo):
    head = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        cwd=repo, capture_output=True, text=True,
    )
    if head.returncode == 0:
        return head.stdout.strip()
    main = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"],
        cwd=repo, capture_output=True, text=True,
    )
    if main.returncode == 0:
        return "origin/main"
    raise Refusal(f"{repo} has neither `origin/HEAD` nor `origin/main`; run `git remote set-head origin --auto` there")


def create(payload):
    repo = owning_repository(payload.get("cwd", ""))
    name = payload.get("name", "")
    path = ROOT / f"{repo.name}-{slug(name)}"

    if path.exists():
        if registered(repo, path):
            return path
        raise Refusal(f"{path} exists and is not a worktree of {repo}; look at it before removing it")

    git("fetch", "--quiet", "origin", cwd=repo)
    if AGENT.match(name):
        git("worktree", "add", "--detach", str(path), base_ref(repo), cwd=repo)
        copy_manifest(repo, path)
        return path
    branch_exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
        cwd=repo, capture_output=True, text=True,
    ).returncode == 0
    if branch_exists:
        git("worktree", "add", str(path), name, cwd=repo)
    else:
        git("worktree", "add", "--no-track", "-b", name, str(path), base_ref(repo), cwd=repo)
    copy_manifest(repo, path)
    return path


def copy_manifest(repo, path):
    """Copy the main checkout's `Manifest.toml` into a worktree that has none.

    The manifest is gitignored, so a new worktree has none, and the pre-commit load test
    `julia --project=. -e "using <Package>"` then fails with "is required but does not seem
    to be installed". The main checkout's copy names packages already in the depot, so no
    resolve and no network is needed. A dependency the branch adds is still missing, and
    the load test still says so.
    """
    source, target = repo / "Manifest.toml", path / "Manifest.toml"
    if source.is_file() and not target.exists():
        shutil.copy2(source, target)


def remove(payload):
    path = Path(payload.get("worktree_path", "")).resolve()
    if path.parent != ROOT.resolve():
        raise Refusal(f"{path} is not directly under {ROOT}; this hook removes only the worktrees it creates")
    repo = owning_repository(path)
    if not registered(repo, path):
        raise Refusal(f"{path} is not a registered worktree of {repo}")
    git("worktree", "remove", str(path), cwd=repo)


def main():
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise Refusal("hook input is not a JSON object")
        event = payload.get("hook_event_name")
        if event == "WorktreeCreate":
            print(create(payload))
        elif event == "WorktreeRemove":
            remove(payload)
        else:
            raise Refusal(f"unexpected hook_event_name {event!r}")
    except (Refusal, json.JSONDecodeError) as err:
        sys.stderr.write(f"worktree hook: {err}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
