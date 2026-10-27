"""The repositories of the research tree: clone them from a table, and pull, push, sync and report
them as one set.

    harness clone [SELECTION ...] [--apply]
    harness repos status [SELECTION ...] [--no-fetch] [--no-prs]
    harness repos pull [SELECTION ...] [--apply]
    harness repos push [SELECTION ...] [--apply] [--no-verify] [--include-topic-branches]
    harness repos sync [SELECTION ...] [--apply] [--no-verify] [--include-topic-branches]

The table. `repositories.toml` beside the profile, else $RESEARCH_HARNESS_REPOSITORIES, names
each repository of the tree and its clone URL; `examples/repositories.toml` shows the form. A
top-level key of FIXED names a fixed repository, whose directory is the key in title case:
`knowledge = "<url>"` is `Knowledge/`. A table of GROUPS names a group directory the same way, and
each key in it a directory there: `[papers]` with `"A Title" = "<url>"` is `Papers/A Title/`. The
research root is $RESEARCH_ROOT, else ~/Research. Only `clone` needs the table: without it, the
other subcommands take each git repository directly below the group directories, and the fixed
repositories that exist.

The selection is a group (`packages`) or a fixed name (`knowledge`), in any case, one or more.
Without one, `clone`, `status` and `pull` take every group and every fixed repository, and `push`
and `sync` take Packages and Experiments only.

clone. Clones each repository of the table that has no directory yet. A directory that exists
and is not a clone of its URL stops the run before the first clone; nothing is cloned. Two URLs
are the same when they agree without a trailing `/` and `.git`. A new clone has no git hooks and
no workspace trust: the subcommand names the `--apply` runs that give them.

status. Fetches every repository with an origin, in parallel, then prints one line each: the
branch, the commits ahead of and behind its upstream, the changed tracked files, and the open
pull requests (`gh` for github.com, `glab` for any other host). It also names a repository of the
table that is not cloned, a git repository in a group directory that the table does not list, a
repository with no origin, and an origin that is not the table's URL. `--no-fetch` reads the
remote-tracking refs as the last fetch left them; `--no-prs` asks no host.

pull. Fetches, then fast-forwards each branch that is behind its upstream (`git merge
--ff-only`). It skips a branch with no upstream, one that has diverged from it, and one whose
incoming commits change a file with local changes; a local change to any other file stays as it
is. The dry run fetches too: a fetch changes no working tree.

push. Fetches, then pushes each branch that is ahead of its upstream, one repository at a time,
and checks each push against the remote ref (`git ls-remote`), not its exit status. It skips a
branch that is also behind, and a branch that is not the default branch unless
--include-topic-branches: a commit on a topic branch does not reach the required checks.

Where to run push. Run it yourself, in your own terminal, and expect it to take hours. Not from
an agent session: a tool call is capped at ten minutes, and the pre-push hook runs a full suite
per repository — a few minutes in most, 10–30 in the large packages. Killing it mid-test orphans
the Julia child, which then invalidates precompile caches for days. The pushes run in sequence,
never in parallel: the packages depend on each other, and two test runs that load the same
package with different CacheFlags invalidate each other's precompiled images. The failure reads
as a cascade of MethodErrors that look exactly like broken code.

When to use --no-verify. The pre-push hook runs the full suite when pushing to main or master:
the right gate for a source change. For a change that touches no Julia source — a workflow, a
README, a CHANGELOG — the suite says nothing about the change, and CI runs on the push anyway. It
is NOT appropriate when the push contains Julia source or a [compat] change. The dry run names the
`.jl` files of each push. A repository whose main does not load cannot pass its suite, and
without --no-verify its push is refused.

sync. pull, then push, with the same selection and options.
"""

import concurrent.futures
import os
import pathlib
import subprocess
import tomllib
import unicodedata
from urllib.parse import urlparse

from . import HarnessError, changing, outcome
from . import profile as profile_module
from .githooks import WIKI_REPOSITORIES, git, research_root

GROUPS = ["packages", "experiments", "papers", "books", "talks", "projects"]
FIXED = [name.lower() for name in WIKI_REPOSITORIES]
PUSH_DEFAULT = ["packages", "experiments"]
# The parallel fetches and pull-request queries.
WORKERS = 8


def table_path(args):
    """The table: $RESEARCH_HARNESS_REPOSITORIES, else repositories.toml beside the profile."""
    if os.environ.get("RESEARCH_HARNESS_REPOSITORIES"):
        return pathlib.Path(os.environ["RESEARCH_HARNESS_REPOSITORIES"])
    return profile_module.location(args.profile).parent / "repositories.toml"


def directory(key):
    """The directory of a group or a fixed repository: its key in title case."""
    return key.capitalize()


def check_name(path, name):
    """Refuse a directory name that leaves its group directory or hides itself."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HarnessError(f"{path}: {name!r} is not a directory name")


def load_table(path):
    """[(selector, directory relative to the root, url)] of the table at `path`, in table order."""
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise HarnessError(f"{path}: {e}") from None
    rows = []
    for key, value in data.items():
        if key in FIXED and isinstance(value, str):
            rows.append((key, directory(key), value))
        elif key in GROUPS and isinstance(value, dict):
            for name, url in value.items():
                check_name(path, name)
                if not isinstance(url, str):
                    raise HarnessError(f"{path}: [{key}] {name!r} is not a URL string")
                rows.append((key, f"{directory(key)}/{name}", url))
        else:
            raise HarnessError(
                f"{path}: {key!r} is neither a fixed repository ({', '.join(FIXED)}) with a URL "
                f"nor a group ({', '.join(GROUPS)}) with a table"
            )
    return rows


def selectors(selection, default):
    """The selection in lower case, checked; `default` when it is empty."""
    chosen = [s.lower() for s in selection] or default
    for s in chosen:
        if s not in GROUPS + FIXED:
            raise HarnessError(f"unknown selection {s!r}; one of {', '.join(GROUPS + FIXED)}")
    return chosen


def is_clone(path):
    return (path / ".git").exists()


def same_url(a, b):
    def bare(url):
        url = url.rstrip("/")
        return url[:-4] if url.endswith(".git") else url

    return bare(a) == bare(b)


def origin(path):
    return git(path, "config", "--get", "remote.origin.url").stdout.strip()


class Entry:
    """One repository of the selection: `name` relative to the root, its `path`, the table's `url`
    (None when the table does not list it) and whether a table was read at all."""

    def __init__(self, name, url, tabled):
        self.name, self.url, self.tabled = name, url, tabled
        self.path = research_root() / name


def entries(args, selection, default):
    """The repositories of the selection: the table's rows, then each git repository of a selected
    group directory that the table does not list. Without a table, every git repository that
    exists in the selection."""
    chosen = selectors(selection, default)
    path = table_path(args)
    rows = load_table(path) if path.is_file() else []
    found = [Entry(name, url, True) for key, name, url in rows if key in chosen]
    # A file system can store a name decomposed (macOS keeps é as e and a combining accent), so
    # names compare in NFC.
    listed = {unicodedata.normalize("NFC", e.name) for e in found}
    for key in chosen:
        if key in FIXED:
            if directory(key) not in listed and is_clone(research_root() / directory(key)):
                found.append(Entry(directory(key), None, bool(rows)))
            continue
        base = research_root() / directory(key)
        if base.is_dir():
            for d in sorted(base.iterdir()):
                name = f"{directory(key)}/{d.name}"
                if d.is_dir() and is_clone(d) and unicodedata.normalize("NFC", name) not in listed:
                    found.append(Entry(name, None, bool(rows)))
    return found


def width(found):
    """The width of the name column: the longest name up to 48 characters; a longer name shifts its
    own line only."""
    return min(max([len(e.name) for e in found] + [20]), 48) + 2


def fetch_all(found):
    """Fetch every cloned repository with an origin, in parallel: {name: error line} of each failure."""
    targets = [e for e in found if is_clone(e.path) and origin(e.path)]

    def one(e):
        p = git(e.path, "fetch", "--quiet", "--prune", "origin")
        return e.name, (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[
            -1
        ] if p.returncode else None

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        return {name: error for name, error in pool.map(one, targets) if error}


def state(path):
    """(branch or None, upstream or None, ahead, behind, changed tracked files) of a clone."""
    branch = git(path, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() or None
    upstream = git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip() or None
    ahead = behind = 0
    if upstream:
        counts = git(path, "rev-list", "--left-right", "--count", "HEAD...@{u}").stdout.split()
        ahead, behind = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
    changed = len(git(path, "status", "--porcelain", "--untracked-files=no").stdout.splitlines())
    return branch, upstream, ahead, behind, changed


def overlap(path):
    """The changed tracked files of a clone that the commits of its upstream also change."""
    local = set(git(path, "diff", "--name-only", "HEAD").stdout.split("\n")) - {""}
    incoming = set(git(path, "diff", "--name-only", "HEAD", "@{u}").stdout.split("\n"))
    return sorted(local & incoming)


def default_branch(path):
    return (
        git(path, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
        .stdout.strip()
        .removeprefix("origin/")
    )


def open_prs(url):
    """The numbers of the open pull requests of `url`, as text: `gh` for github.com, `glab` for any
    other host. None when the host cannot be asked."""
    parsed = urlparse(url if "://" in url else "ssh://" + url.replace(":", "/", 1))
    project = parsed.path.strip("/").removesuffix(".git")
    if parsed.hostname == "github.com":
        command = [
            "gh",
            "pr",
            "list",
            "-R",
            f"github.com/{project}",
            "--state",
            "open",
            "--json",
            "number",
            "--jq",
            ".[].number",
        ]
    else:
        command = [
            "glab",
            "mr",
            "list",
            "-R",
            f"https://{parsed.hostname}/{project}",
            "-F",
            "json",
            "--jq",
            ".[].iid",
        ]
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except OSError, subprocess.TimeoutExpired:
        return None
    return p.stdout.split() if p.returncode == 0 else None


def cmd_clone(args):
    path = table_path(args)
    if not path.is_file():
        raise HarnessError(f"no repository table at {path}; examples/repositories.toml shows the form")
    found = [e for e in entries(args, args.selection, GROUPS + FIXED) if e.url]
    w = width(found)
    todo, blocked = [], []
    for e in found:
        if is_clone(e.path) and same_url(origin(e.path), e.url):
            continue
        if e.path.exists() or e.path.is_symlink():
            have = origin(e.path) if is_clone(e.path) else ""
            print(f"{e.name:<{w}} IN THE WAY: not a clone of {e.url}" + (f" (origin {have})" if have else ""))
            blocked.append(e)
        else:
            todo.append(e)
    if blocked:
        raise HarnessError(
            f"{len(blocked)} directories are in the way; move them, then run again. Nothing is cloned"
        )
    failed = 0
    for e in todo:
        if not args.apply:
            print(f"{e.name:<{w}} would clone {e.url}")
            continue
        print(f"{e.name:<{w}} cloning {e.url} ...", end="", flush=True)
        e.path.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run(["git", "clone", "--quiet", e.url, str(e.path)], capture_output=True, text=True)
        if p.returncode == 0:
            print(" done")
        else:
            print(f" FAILED (rc={p.returncode})")
            for line in p.stderr.splitlines()[-6:]:
                print("      " + line)
            failed += 1
    done = len(todo) - failed
    print(
        f"\n{len(found)} repositories in the table, {len(found) - len(todo)} cloned already, "
        f"{done if args.apply else len(todo)} {'cloned' if args.apply else 'to clone'}"
        + (f", {failed} failed." if failed else ".")
    )
    if args.apply and done:
        print(
            "Next: a new clone has no git hooks and no workspace trust. Run\n"
            "    harness githooks --apply\n    harness wiki-lint-hook --apply\n    harness trust --apply"
        )
    if failed:
        raise HarnessError(f"{failed} clones failed")
    return outcome(args, len(todo))


def cmd_status(args):
    found = entries(args, args.selection, GROUPS + FIXED)
    w = width(found)
    errors = {} if args.no_fetch else fetch_all(found)
    prs = {}
    if not args.no_prs:
        asked = [e for e in found if is_clone(e.path) and origin(e.path)]
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            prs = dict(zip([e.name for e in asked], pool.map(lambda e: open_prs(origin(e.path)), asked)))
    print(f"{'repository':<{w}} {'branch':<16} {'ahead':>5} {'behind':>6} {'changed':>7}  open PRs")
    for e in found:
        if not is_clone(e.path):
            print(f"{e.name:<{w}} MISSING: in the table, not cloned (harness clone --apply)")
            continue
        branch, upstream, ahead, behind, changed = state(e.path)
        notes = []
        url = origin(e.path)
        if not url:
            notes.append("no origin")
        elif e.url and not same_url(url, e.url):
            notes.append(f"origin {url} is not the table's {e.url}")
        if e.tabled and not e.url:
            notes.append("not in the table")
        if url and not upstream:
            notes.append("no upstream")
        if e.name in errors:
            notes.append(f"fetch failed: {errors[e.name]}")
        if args.no_prs or not url:
            numbers = ""
        else:
            numbers = "?" if prs.get(e.name) is None else " ".join(f"#{n}" for n in prs[e.name]) or "-"
        line = (
            f"{e.name:<{w}} {branch or '(detached)':<16} {ahead if upstream else '':>5} "
            f"{behind if upstream else '':>6} {changed or '':>7}  {numbers}"
        )
        print(line.rstrip() + ("   " + "; ".join(notes) if notes else ""))
    return 0


def pull(args, found):
    """Fast-forward each repository behind its upstream: (planned, failed)."""
    w = width(found)
    errors = fetch_all(found)
    planned = failed = uptodate = skipped = 0
    for e in found:
        if not is_clone(e.path):
            continue
        branch, upstream, ahead, behind, changed = state(e.path)
        if e.name in errors:
            print(f"{e.name:<{w}} SKIP   fetch failed: {errors[e.name]}")
            skipped += 1
        elif not upstream:
            print(f"{e.name:<{w}} SKIP   {branch or 'detached HEAD'} has no upstream")
            skipped += 1
        elif behind == 0:
            uptodate += 1
        elif ahead:
            print(f"{e.name:<{w}} SKIP   {ahead} ahead of and {behind} behind {upstream}: diverged")
            skipped += 1
        elif changed and (clash := overlap(e.path)):
            print(f"{e.name:<{w}} SKIP   the incoming commits change local changes: {' '.join(clash[:3])}")
            skipped += 1
        else:
            planned += 1
            if not args.apply:
                print(f"{e.name:<{w}} would fast-forward {behind} commit(s) from {upstream}")
                continue
            p = git(e.path, "merge", "--ff-only", "--quiet", "@{u}")
            if p.returncode == 0:
                print(f"{e.name:<{w}} fast-forwarded {behind} commit(s) from {upstream}")
            else:
                print(
                    f"{e.name:<{w}} FAILED (rc={p.returncode}): {(p.stderr.strip().splitlines() or [''])[-1]}"
                )
                failed += 1
    done = planned - failed
    print(
        f"\npull: {done if args.apply else planned} {'fast-forwarded' if args.apply else 'to fast-forward'}, "
        f"{uptodate} up to date, {skipped} skipped" + (f", {failed} failed." if failed else ".")
    )
    return planned, failed


def push(args, found):
    """Push each repository ahead of its upstream, one at a time: (planned, failed)."""
    w = width(found)
    errors = fetch_all(found)
    planned = pushed = uptodate = skipped = failed = 0
    for e in found:
        if not is_clone(e.path):
            continue
        branch, upstream, ahead, behind, _ = state(e.path)
        if e.name in errors:
            print(f"{e.name:<{w}} SKIP   fetch failed: {errors[e.name]}")
            skipped += 1
            continue
        if not upstream:
            print(f"{e.name:<{w}} SKIP   {branch or 'detached HEAD'} has no upstream")
            skipped += 1
            continue
        if ahead == 0:
            uptodate += 1
            continue
        if behind:
            print(f"{e.name:<{w}} SKIP   {behind} commits behind {upstream} - pull or rebase first")
            skipped += 1
            continue
        default = default_branch(e.path)
        if default and branch != default and not args.include_topic_branches:
            print(f"{e.name:<{w}} SKIP   on {branch}, not the default branch {default}")
            print(
                f"{'':<{w + 1}}{ahead} commit(s) would land on a topic branch; pass --include-topic-branches to push anyway"
            )
            skipped += 1
            continue
        src = " ".join(
            git(e.path, "diff", "--name-only", f"{upstream}..HEAD", "--", "*.jl").stdout.split()[:3]
        )
        planned += 1
        if not args.apply:
            print(
                f"{e.name:<{w}} would push {ahead} commit(s) to {upstream}"
                + (f"   .jl touched: {src}" if src else "")
            )
            continue
        if src and args.no_verify:
            print(f"{e.name:<{w}} NOTE   .jl files in this push, and the hooks are skipped: {src}")
        print(f"{e.name:<{w}} pushing {ahead} commit(s)...", end="", flush=True)
        p = git(e.path, "push", *(["--no-verify"] if args.no_verify else []))
        local = git(e.path, "rev-parse", "HEAD").stdout.strip()
        remote = git(e.path, "ls-remote", "origin", f"refs/heads/{branch}").stdout.split("\t")[0].strip()
        if local == remote:
            print(" done")
            pushed += 1
        else:
            print(f" FAILED (rc={p.returncode})")
            for line in (p.stdout + p.stderr).splitlines()[-12:]:
                print("      " + line)
            failed += 1
    print(
        f"\npush: {pushed if args.apply else planned} {'pushed' if args.apply else 'to push'}, "
        f"{uptodate} up to date, {skipped} skipped" + (f", {failed} failed." if failed else ".")
    )
    return planned, failed


def finish(args, planned, failed):
    if failed:
        raise HarnessError(f"{failed} failed")
    return outcome(args, planned)


def cmd_pull(args):
    return finish(args, *pull(args, entries(args, args.selection, GROUPS + FIXED)))


def cmd_push(args):
    return finish(args, *push(args, entries(args, args.selection, PUSH_DEFAULT)))


def cmd_sync(args):
    found = entries(args, args.selection, PUSH_DEFAULT)
    pulled, pull_failed = pull(args, found)
    pushed, push_failed = push(args, found)
    return finish(args, pulled + pushed, pull_failed + push_failed)


def register(sub):
    choices = ", ".join(GROUPS + FIXED)
    p = changing(
        sub.add_parser(
            "clone",
            help="clone the repositories of the research tree from repositories.toml",
            description="Clone each repository of repositories.toml (beside the profile) that "
            "has no directory yet. Without --apply it lists the clones and exits 1 "
            "when there is one; --apply clones. A directory in the way stops the "
            "run before the first clone.",
        )
    )
    p.add_argument(
        "selection",
        nargs="*",
        metavar="SELECTION",
        help=f"a group or fixed repository: {choices}; none means all",
    )
    p.set_defaults(run=cmd_clone)

    repos = sub.add_parser(
        "repos",
        help="report, pull, push or sync the repositories of the research tree",
        description="Work on the git repositories of the research tree as one set: those of "
        "repositories.toml, or each git repository below the group directories.",
    )
    actions = repos.add_subparsers(dest="action", metavar="<action>", required=True)

    def selection(parser, default):
        parser.add_argument(
            "selection",
            nargs="*",
            metavar="SELECTION",
            help=f"a group or fixed repository: {choices}; none means {default}",
        )
        return parser

    p = selection(
        actions.add_parser(
            "status",
            help="branch, ahead, behind, changes and open pull requests",
            description="Fetch every repository, then print its branch, the commits "
            "ahead of and behind its upstream, its changed tracked files and "
            "its open pull requests, and name each drift from the table.",
        ),
        "all",
    )
    p.add_argument("--no-fetch", action="store_true", help="read the remote-tracking refs of the last fetch")
    p.add_argument("--no-prs", action="store_true", help="ask no host for open pull requests")
    p.set_defaults(run=cmd_status)

    p = selection(
        changing(
            actions.add_parser(
                "pull",
                help="fast-forward every repository behind its upstream",
                description="Fetch, then fast-forward each branch that is behind "
                "its upstream. Without --apply it lists them and exits 1 "
                "when there is one; --apply merges --ff-only.",
            )
        ),
        "all",
    )
    p.set_defaults(run=cmd_pull)

    for name, run, text in (
        ("push", cmd_push, "push every repository ahead of its upstream, one at a time"),
        ("sync", cmd_sync, "pull, then push"),
    ):
        p = selection(
            changing(
                actions.add_parser(
                    name,
                    help=text,
                    description=f"{text[0].upper()}{text[1:]}. Without --apply it "
                    "lists the plan and exits 1 when there is something "
                    "to do; --apply does it. The pre-push hook can run a "
                    "full suite per repository, so run it in your own "
                    "terminal.",
                )
            ),
            "packages and experiments",
        )
        p.add_argument(
            "--no-verify",
            "--skip-hooks",
            dest="no_verify",
            action="store_true",
            help="push with --no-verify: no pre-push suite",
        )
        p.add_argument(
            "--include-topic-branches",
            action="store_true",
            help="also push a branch that is not the default branch",
        )
        p.set_defaults(run=run)


def selftest():
    """The table, the selection, `clone`, `status`, `pull`, `push` and the pull-request query, on
    scratch remotes below a temporary directory."""
    import argparse
    import contextlib
    import io
    import tempfile
    from unittest import mock

    from .sweep import GIT

    results = []

    def check(ok, label):
        results.append(ok)
        print(f"{'ok ' if ok else 'BAD'}  repos: {label}")

    def raises(f):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                f()
        except HarnessError:
            return True
        return False

    def quiet(f, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = f(*a)
        return code, out.getvalue()

    def args(**kw):
        return argparse.Namespace(
            **(
                {
                    "profile": None,
                    "selection": [],
                    "apply": False,
                    "no_fetch": False,
                    "no_prs": True,
                    "no_verify": False,
                    "include_topic_branches": False,
                }
                | kw
            )
        )

    def run(*command, cwd=None):
        subprocess.run(command, cwd=cwd, check=True, capture_output=True)

    with (
        tempfile.TemporaryDirectory() as tmp,
        mock.patch.dict(
            os.environ,
            GIT
            | {
                "RESEARCH_ROOT": f"{tmp}/Research",
                "RESEARCH_HARNESS_REPOSITORIES": f"{tmp}/repositories.toml",
            },
        ),
    ):
        tmp = pathlib.Path(tmp)
        root, table = tmp / "Research", tmp / "repositories.toml"

        def remote(name):
            """A bare remote with one commit on main; a work clone of it in tmp/work/<name>."""
            run("git", "init", "-q", "--bare", "-b", "main", str(tmp / "remotes" / f"{name}.git"))
            work = tmp / "work" / name
            run("git", "clone", "-q", str(tmp / "remotes" / f"{name}.git"), str(work))
            (work / "readme").write_text("readme")
            run("git", "add", "readme", cwd=work)
            commit(work, "one")
            run("git", "push", "-q", "origin", "HEAD:main", cwd=work)
            return str(tmp / "remotes" / f"{name}.git")

        def commit(repo, text):
            (repo / "file").write_text(text)
            run("git", "add", "file", cwd=repo)
            run("git", "commit", "-q", "-m", text, cwd=repo)

        urls = {name: remote(name) for name in ("knowledge", "alpha", "paper")}
        body = (
            f'knowledge = "{urls["knowledge"]}"\n\n[packages]\nAlpha = "{urls["alpha"]}"\n\n'
            f'[papers]\n"A Title" = "{urls["paper"]}"\n'
        )
        table.write_text(body)

        check(len(load_table(table)) == 3, "the table gives one row per repository")
        for bad, label in (
            ('wiki = "x"\n', "an unknown key"),
            ('[packages]\n"../up" = "x"\n', "a name with a /"),
            ("[packages]\nAlpha = 1\n", "a URL that is not a string"),
        ):
            (tmp / "bad.toml").write_text(bad)
            check(raises(lambda: load_table(tmp / "bad.toml")), f"{label} is refused")
        check(raises(lambda: selectors(["slides"], GROUPS)), "an unknown selection is refused")

        code, _ = quiet(cmd_clone, args())
        check(code == 1 and not root.exists(), "the clone dry run plans and writes nothing")
        code, _ = quiet(cmd_clone, args(selection=["Papers"], apply=True))
        check(
            code == 0 and is_clone(root / "Papers" / "A Title") and not (root / "Packages").exists(),
            "a selection clones its group only",
        )
        quiet(cmd_clone, args(apply=True))
        code, _ = quiet(cmd_clone, args())
        check(
            code == 0 and is_clone(root / "Knowledge") and is_clone(root / "Packages" / "Alpha"),
            "after --apply the dry run has nothing to do",
        )

        (root / "Packages" / "Beta").mkdir()
        table.write_text(
            body.replace("\n\n[papers]", f'\nBeta = "{urls["alpha"]}"\nGamma = "{urls["alpha"]}"\n\n[papers]')
        )
        check(
            raises(lambda: cmd_clone(args(apply=True))) and not (root / "Packages" / "Gamma").exists(),
            "a directory in the way stops the run before the first clone",
        )
        (root / "Packages" / "Beta").rmdir()
        table.write_text(body.replace("\n\n[papers]", '\nGone = "/nonexistent"\n\n[papers]'))

        commit(tmp / "work" / "alpha", "two")
        run("git", "push", "-q", "origin", "HEAD:main", cwd=tmp / "work" / "alpha")
        commit(root / "Knowledge", "local")
        run("git", "init", "-q", str(root / "Packages" / "Stray"))
        code, out = quiet(cmd_status, args())
        lines = {line.split()[0]: line for line in out.splitlines()[1:] if line.strip()}
        check(
            code == 0 and lines["Packages/Alpha"].split()[1:4] == ["main", "0", "1"],
            "status counts a commit behind",
        )
        check(lines["Knowledge"].split()[1:4] == ["main", "1", "0"], "status counts a commit ahead")
        check(
            "MISSING" in lines["Packages/Gone"]
            and "not in the table" in lines["Packages/Stray"]
            and "no origin" in lines["Packages/Stray"],
            "status names the drift from the table",
        )

        code, out = quiet(cmd_pull, args())
        check(
            code == 1 and "Packages/Alpha" in out and "Knowledge " not in out.split("pull:")[0],
            "the pull dry run plans the branch behind only",
        )
        code, _ = quiet(cmd_pull, args(apply=True))
        check(code == 0 and state(root / "Packages" / "Alpha")[3] == 0, "pull --apply fast-forwards")
        commit(tmp / "work" / "alpha", "three")
        run("git", "push", "-q", "origin", "HEAD:main", cwd=tmp / "work" / "alpha")
        (root / "Packages" / "Alpha" / "file").write_text("changed")
        code, out = quiet(cmd_pull, args(selection=["packages"]))
        check(
            code == 0 and "change local changes: file" in out,
            "pull skips incoming commits that change a local change",
        )
        run("git", "checkout", "-q", "--", "file", cwd=root / "Packages" / "Alpha")
        (root / "Packages" / "Alpha" / "readme").write_text("changed")
        code, _ = quiet(cmd_pull, args(selection=["packages"], apply=True))
        check(
            code == 0
            and state(root / "Packages" / "Alpha")[3] == 0
            and (root / "Packages" / "Alpha" / "readme").read_text() == "changed",
            "pull fast-forwards past a local change to another file, and keeps it",
        )
        run("git", "checkout", "-q", "--", "readme", cwd=root / "Packages" / "Alpha")

        code, out = quiet(cmd_push, args(selection=["knowledge"]))
        check(code == 1 and "would push 1 commit" in out, "the push dry run plans a branch ahead")
        code, _ = quiet(cmd_push, args(selection=["knowledge"], apply=True))
        local = git(root / "Knowledge", "rev-parse", "HEAD").stdout.strip()
        check(
            code == 0
            and git(root / "Knowledge", "ls-remote", "origin", "refs/heads/main").stdout.startswith(local),
            "push --apply lands on the remote",
        )
        alpha = root / "Packages" / "Alpha"
        run("git", "merge", "-q", "--ff-only", "@{u}", cwd=alpha)
        run("git", "switch", "-q", "-c", "topic", cwd=alpha)
        run("git", "push", "-q", "-u", "origin", "topic", cwd=alpha)
        commit(alpha, "topic")
        code, out = quiet(cmd_push, args())
        check(code == 0 and "not the default branch" in out, "push skips a topic branch")
        code, _ = quiet(cmd_push, args(include_topic_branches=True))
        check(code == 1, "--include-topic-branches plans the topic branch")
        check(
            "Knowledge" not in [e.name for e in entries(args(), [], PUSH_DEFAULT)],
            "push and sync default to the packages and experiments",
        )

        composed, decomposed = "Poincaré", "Poincaré"
        table.write_text(body + f'\n[projects]\n"{composed}" = "{urls["paper"]}"\n')
        run("git", "init", "-q", str(root / "Projects" / decomposed))
        names = [e.name for e in entries(args(), ["projects"], GROUPS)]
        check(
            names == [f"Projects/{composed}"],
            f"a decomposed directory name is the table's composed one: {names}",
        )

        calls = []
        with mock.patch.object(
            subprocess,
            "run",
            lambda c, **kw: calls.append(c) or subprocess.CompletedProcess(c, 0, "3\n7\n", ""),
        ):
            github = open_prs("https://github.com/Owner/Name.jl.git")
            gitlab = open_prs("git@gitlab.example.org:group/sub/name.git")
        check(
            github == ["3", "7"] and calls[0][:5] == ["gh", "pr", "list", "-R", "github.com/Owner/Name.jl"],
            "a github.com URL asks gh",
        )
        check(
            calls[1][:5] == ["glab", "mr", "list", "-R", "https://gitlab.example.org/group/sub/name"],
            "another host asks glab",
        )
    return len(results), results.count(False)
