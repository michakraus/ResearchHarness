"""Changelog fragments: each branch adds its entry as a file of `changelog.d/`, and a release joins
them into `CHANGELOG.md`. Two pull requests then never edit the same lines.

    harness changelog [--apply]
    harness changelog --check BASE

A fragment is a file `changelog.d/*.md` other than `README.md`. The dry run prints the
`## Unreleased` block that the fragments make, newest first by the committer date of the commit
that added each fragment; a fragment that no commit holds comes first, and ties go by file name.
`--apply` puts the block at the top of the `## Unreleased` section of `CHANGELOG.md` and deletes
the fragments. A fragment that is empty, holds only whitespace, holds a carriage return or is not
UTF-8 stops both with exit 2, and nothing is written.

`--check BASE` reads `git diff --name-status BASE...HEAD`: a branch that changes a path below one
of CODE and adds no fragment exits 1, and names that path.
"""

import contextlib
import io
import os
import pathlib
import subprocess
import tempfile

from . import REPO, HarnessError, outcome

DIRECTORY = "changelog.d"
HEADING = "## Unreleased"
# The directories whose change needs a changelog entry.
CODE = ("lib/", "hooks/", "adapters/", "bin/", "scripts/", "githooks/", "agents/", "skills/", "rules/")


def git(root, args, env=None):
    """One git command in `root`; the caller reads its exit status."""
    return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True, check=False)


def fragments(root):
    """The fragments of `root`'s changelog.d/, by file name."""
    return sorted(p for p in (root / DIRECTORY).glob("*.md") if p.name != "README.md" and p.is_file())


def entry(path, root):
    """The text of one fragment, with a final newline; a fragment that is not one entry raises."""
    rel = path.relative_to(root)
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise HarnessError(f"{rel}: not UTF-8") from None
    if "\r" in text:
        raise HarnessError(f"{rel}: holds a carriage return")
    if not text.strip():
        raise HarnessError(f"{rel}: holds no entry")
    return text if text.endswith("\n") else text + "\n"


def added(path, root, env=None):
    """The committer date, in seconds, of the last commit that added `path`, or None when no commit
    holds it."""
    p = git(root, ["log", "-1", "--diff-filter=A", "--format=%ct", "--", str(path.relative_to(root))], env)
    if p.returncode != 0:
        raise HarnessError(f"git log: {p.stderr.strip()}")
    return int(p.stdout) if p.stdout.strip() else None


def newest_first(dated):
    """The paths of (path, date) pairs: no date first, then the newest date, then by file name."""
    return [path for path, date in sorted(dated, key=lambda e: (e[1] is not None, -(e[1] or 0), e[0].name))]


def join(texts):
    """The entries, each ending in a newline, separated by one blank line."""
    return "\n".join(texts)


def insert(changelog, block):
    """`changelog` with `block` at the top of its `## Unreleased` section; without that heading, a
    new section above the first `## ` heading, or at the end."""
    lines = changelog.splitlines(keepends=True)
    heading = next((i for i, line in enumerate(lines) if line.rstrip() == HEADING), None)
    if heading is not None:
        rest = next((i for i in range(heading + 1, len(lines)) if lines[i].strip()), len(lines))
        after = ["\n", *lines[rest:]] if rest < len(lines) else []
        return "".join([*lines[:heading], f"{HEADING}\n\n", block, *after])
    section = f"{HEADING}\n\n{block}"
    first = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
    if first is not None:
        return "".join([*lines[:first], section, "\n", *lines[first:]])
    return changelog.rstrip("\n") + "\n\n" + section if changelog else section


def plan(root, env=None):
    """The fragments in the order of the block, and the block; a bad fragment raises."""
    paths = fragments(root)
    texts = {path: entry(path, root) for path in paths}
    ordered = newest_first([(path, added(path, root, env)) for path in paths])
    return ordered, join([texts[path] for path in ordered])


def write(root, apply, env=None):
    """The dry run, or with `apply` the join; prints what it does and returns the number of
    fragments."""
    ordered, block = plan(root, env)
    if not ordered:
        print("no fragments")
        return 0
    if not apply:
        print(f"{HEADING}\n\n{block}", end="")
        return len(ordered)
    target = root / "CHANGELOG.md"
    if not target.is_file():
        raise HarnessError(f"{target.name}: no such file")
    target.write_bytes(insert(target.read_bytes().decode("utf-8"), block).encode("utf-8"))
    for path in ordered:
        path.unlink()
    print(f"CHANGELOG.md: {len(ordered)} entries added to {HEADING}; removed "
          + ", ".join(str(path.relative_to(root)) for path in ordered))
    return len(ordered)


def changes(output):
    """The (status, path) pairs of `git diff --name-status -z` output; a rename or copy gives a pair
    for each of its two paths."""
    fields = output.split("\0")
    pairs, i = [], 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        count = 2 if status[0] in "RC" else 1
        pairs += [(status, path) for path in fields[i + 1:i + 1 + count]]
        i += 1 + count
    return pairs


def is_fragment(path):
    """Whether a path of the repository is a fragment."""
    parent, _, name = path.rpartition("/")
    return parent == DIRECTORY and name.endswith(".md") and name != "README.md"


def unrecorded(pairs):
    """The first changed path below CODE when no fragment is added, else None."""
    if any(status == "A" and is_fragment(path) for status, path in pairs):
        return None
    return next((path for _, path in pairs if path.startswith(CODE)), None)


def check(root, base, env=None):
    """Exit 1 when the branch changes code since `base` and adds no fragment, else 0."""
    p = git(root, ["diff", "--name-status", "-z", f"{base}...HEAD"], env)
    if p.returncode != 0:
        raise HarnessError(f"git diff {base}...HEAD: {p.stderr.strip()}")
    path = unrecorded(changes(p.stdout))
    if path is None:
        print(f"ok: a fragment is added below {DIRECTORY}/, or no path below {', '.join(CODE)} changes")
        return 0
    print(f"{path} changes and no fragment is added below {DIRECTORY}/; changelog.d/README.md gives its form")
    return 1


def cmd_changelog(args):
    if args.check is not None:
        return check(REPO, args.check)
    return outcome(args, write(REPO, args.apply))


def register(sub):
    p = sub.add_parser("changelog", help="join the fragments of changelog.d/ into CHANGELOG.md, or check that a branch "
                                         "adds one",
                       description="Print the ## Unreleased block that the fragments of changelog.d/ make, newest "
                                   "first, and exit 1 when there is one. --apply puts the block into CHANGELOG.md "
                                   "and deletes the fragments. --check BASE exits 1 when the branch changes code "
                                   "since BASE and adds no fragment.")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="write the block into CHANGELOG.md and delete the fragments")
    modes.add_argument("--check", metavar="BASE", help="exit 1 when the branch changes code since BASE and adds no "
                                                       "fragment")
    p.set_defaults(run=cmd_changelog)


def selftest():
    """The cases of the fragments, the join, the insertion and the check: (number of cases, number
    wrong)."""
    total = wrong = 0

    def check_(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  changelog: {label}")

    def raises(f):
        """The message of the HarnessError that `f()` raises, or None."""
        try:
            quiet(f)
        except HarnessError as e:
            return str(e)
        return None

    def quiet(f):
        """`f()` and what it prints."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = f()
        return result, out.getvalue()

    # The join and the insertion, without a repository.
    check_(join(["- **A.** a.\n", "- **B.** b.\n"]) == "- **A.** a.\n\n- **B.** b.\n",
           "two fragments join with one blank line between them")
    old = "# Changelog\n\n## Unreleased\n\n- **Old.** old.\n\n## 1.0\n\n- **First.** first.\n"
    check_(insert(old, "- **B.** b.\n\n- **A.** a.\n")
           == "# Changelog\n\n## Unreleased\n\n- **B.** b.\n\n- **A.** a.\n\n- **Old.** old.\n\n## 1.0\n\n"
              "- **First.** first.\n",
           "the block goes to the top of ## Unreleased, above its entries")
    check_(insert("# Changelog\n\n## Unreleased\n\n## 1.0\n\n- **First.** first.\n", "- **A.** a.\n")
           == "# Changelog\n\n## Unreleased\n\n- **A.** a.\n\n## 1.0\n\n- **First.** first.\n",
           "an empty ## Unreleased section followed by a heading gets the block")
    for tail in ("## Unreleased\n", "## Unreleased"):
        check_(insert(f"# Changelog\n\n{tail}", "- **A.** a.\n") == "# Changelog\n\n## Unreleased\n\n- **A.** a.\n",
               f"an ## Unreleased heading at the end of the file gets the block below it: {tail!r}")
    check_(insert("# Changelog\n\n## 1.0\n\n- **First.** first.\n", "- **A.** a.\n")
           == "# Changelog\n\n## Unreleased\n\n- **A.** a.\n\n## 1.0\n\n- **First.** first.\n",
           "without ## Unreleased, the section goes above the first ## heading")
    check_(insert("# Changelog\n\n### Unreleased\n\n## 1.0\n", "- **A.** a.\n")
           == "# Changelog\n\n### Unreleased\n\n## Unreleased\n\n- **A.** a.\n\n## 1.0\n",
           "a ### heading is neither the section nor the first ## heading")
    check_(insert("# Changelog\n", "- **A.** a.\n") == "# Changelog\n\n## Unreleased\n\n- **A.** a.\n",
           "without any ## heading, the section goes at the end")
    check_(insert("# Changelog", "- **A.** a.\n") == "# Changelog\n\n## Unreleased\n\n- **A.** a.\n",
           "a file without a final newline gets one before the section")
    check_(insert("# Changelog\n\n\n", "- **A.** a.\n") == "# Changelog\n\n## Unreleased\n\n- **A.** a.\n",
           "blank lines at the end of the file become one blank line before the section")
    check_(insert("", "- **A.** a.\n") == "## Unreleased\n\n- **A.** a.\n", "an empty file gets the section alone")

    # The order, without a repository.
    a, b, c = (pathlib.Path(f"changelog.d/{n}.md") for n in "abc")
    check_(newest_first([(a, 100), (b, 200), (c, None)]) == [c, b, a],
           "the order: a fragment no commit holds first, then the newest")
    check_(newest_first([(b, 100), (a, 100)]) == [a, b], "fragments of the same date go by file name")
    check_(newest_first([(b, None), (a, None)]) == [a, b], "fragments no commit holds go by file name")

    # The path classification, without a repository.
    code = ("M", "lib/harness/x.py")
    check_(unrecorded([("M", "docs/src/x.md"), ("A", "README.md"), ("M", "CHANGELOG.md")]) is None,
           "a branch that changes only docs/ and top-level files needs no fragment")
    check_(unrecorded([code, ("A", "changelog.d/topic.md")]) is None, "code with an added fragment passes")
    check_(unrecorded([("M", "docs/x.md"), code, ("M", "hooks/y.py")]) == "lib/harness/x.py",
           "code without a fragment names the first changed code path")
    for prefix in CODE:
        check_(unrecorded([("M", f"{prefix}x")]) == f"{prefix}x", f"a change below {prefix} is code")
    check_(unrecorded([("M", "library/x"), ("M", "binary"), ("M", "x/lib/y")]) is None,
           "a path that only starts with the name of a code directory is not code")
    for label, pair in [("a modified fragment", ("M", "changelog.d/topic.md")),
                        ("a deleted fragment", ("D", "changelog.d/topic.md")),
                        ("a renamed fragment", ("R100", "changelog.d/topic.md")),
                        ("an added README.md", ("A", "changelog.d/README.md")),
                        ("an added file that is not .md", ("A", "changelog.d/topic.txt")),
                        ("an added .md below a subdirectory", ("A", "changelog.d/sub/topic.md"))]:
        check_(unrecorded([code, pair]) == "lib/harness/x.py", f"{label} is no added fragment")
    pairs = changes("M\0docs/x.md\0R087\0lib/a.py\0lib/b.py\0A\0changelog.d/t.md\0")
    check_(pairs == [("M", "docs/x.md"), ("R087", "lib/a.py"), ("R087", "lib/b.py"), ("A", "changelog.d/t.md")],
           f"the -z output parses into (status, path) pairs, both paths of a rename -> {pairs}")
    check_(changes("") == [], "an empty diff has no pairs")

    # The verb on scratch repositories: a fixed identity and dates, no configuration of the caller,
    # and no GIT_* variable, which would send the commands to the caller's repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="changelog",
               GIT_AUTHOR_EMAIL="changelog@example.org", GIT_COMMITTER_NAME="changelog",
               GIT_COMMITTER_EMAIL="changelog@example.org")
    with tempfile.TemporaryDirectory(prefix="harness-changelog-") as tmp:
        # git looks for a repository no higher than the scratch directory.
        env["GIT_CEILING_DIRECTORIES"] = tmp
        counter = iter(range(1000))

        def repo(changelog=old):
            root = pathlib.Path(tmp) / f"r{next(counter)}"
            (root / DIRECTORY).mkdir(parents=True)
            (root / DIRECTORY / "README.md").write_text("How to write a fragment.\n")
            (root / "CHANGELOG.md").write_text(changelog)
            git(root, ["init", "-q", "-b", "main"], env)
            commit(root, "2025-12-01", "base")
            return root

        def commit(root, day, message, *paths):
            git(root, ["add", *(paths or ["."])], env)
            dated = dict(env, GIT_AUTHOR_DATE=f"{day}T12:00:00Z", GIT_COMMITTER_DATE=f"{day}T12:00:00Z")
            return git(root, ["commit", "-q", "-m", message], dated).returncode

        def fragment(root, name, text, day=None):
            path = root / DIRECTORY / name
            path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
            if day:
                commit(root, day, name, str(path.relative_to(root)))
            return path

        def state(root):
            return sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob("*")
                          if p.is_file() and ".git" not in p.relative_to(root).parts)

        root = repo()
        before = state(root)
        runs = [quiet(lambda: write(root, apply, env)) for apply in (False, True)]
        check_(plan(root, env) == ([], "") and runs == [(0, "no fragments\n")] * 2 and state(root) == before,
               f"with no fragment, the dry run and --apply print 'no fragments' and change nothing -> {runs}")

        root = repo()
        fa = fragment(root, "a.md", "- **A.** a.\n", "2026-01-01")
        fb = fragment(root, "b.md", "- **B.** b.\n", "2026-01-02")
        fc = fragment(root, "c.md", "- **C.** c.")
        (root / DIRECTORY / "notes.txt").write_text("not a fragment\n")
        (root / DIRECTORY / "sub").mkdir()
        (root / DIRECTORY / "sub" / "d.md").write_text("- **D.** d.\n")
        check_(fragments(root) == [fa, fb, fc], "the fragments are the .md files of changelog.d/ but README.md")
        ordered, block = plan(root, env)
        check_(ordered == [fc, fb, fa] and block == "- **C.** c.\n\n- **B.** b.\n\n- **A.** a.\n",
               f"the block: the uncommitted fragment first, then the newest, a final newline added -> {block!r}")
        before = state(root)
        dry = quiet(lambda: write(root, False, env))
        check_(dry == (3, f"## Unreleased\n\n{block}") and state(root) == before,
               "the dry run prints the block under ## Unreleased, counts 3 and changes no file")
        check_(quiet(lambda: write(root, True, env))[0] == 3 and not any(p.exists() for p in (fa, fb, fc))
               and (root / DIRECTORY / "README.md").is_file() and (root / DIRECTORY / "notes.txt").is_file()
               and (root / DIRECTORY / "sub" / "d.md").is_file(),
               "--apply deletes the fragments and keeps README.md and every other file")
        check_((root / "CHANGELOG.md").read_text()
               == "# Changelog\n\n## Unreleased\n\n- **C.** c.\n\n- **B.** b.\n\n- **A.** a.\n\n- **Old.** old.\n\n"
                  "## 1.0\n\n- **First.** first.\n",
               "--apply writes the block at the top of ## Unreleased")
        check_(plan(root, env) == ([], ""), "after --apply, no fragment is left")

        for label, text in [("an empty fragment", ""), ("a fragment of whitespace", "  \n\n"),
                            ("a fragment with a carriage return", "- **X.** y\r\n"),
                            ("a fragment that is not UTF-8", b"- **X.** \xff\n")]:
            root = repo()
            good = fragment(root, "a.md", "- **A.** a.\n", "2026-01-01")
            fragment(root, "bad.md", text)
            before = state(root)
            messages = [raises(lambda: write(root, apply, env)) for apply in (False, True)]
            check_(all(m and m.startswith("changelog.d/bad.md: ") for m in messages) and state(root) == before
                   and good.exists(),
                   f"{label} stops the dry run and --apply, named, and nothing changes -> {messages}")

        root = repo()
        (root / "CHANGELOG.md").unlink()
        fragment(root, "a.md", "- **A.** a.\n")
        check_(raises(lambda: write(root, True, env)) == "CHANGELOG.md: no such file"
               and (root / DIRECTORY / "a.md").exists(),
               "--apply without CHANGELOG.md stops and keeps the fragment")

        root = pathlib.Path(tmp) / "not-a-repository"
        (root / DIRECTORY).mkdir(parents=True)
        fragment(root, "a.md", "- **A.** a.\n")
        check_((raises(lambda: plan(root, env)) or "").startswith("git log: "),
               "outside a repository, the date of a fragment cannot be read, and the verb stops")

        # --check on branches of one repository.
        root = repo()
        git(root, ["switch", "-q", "-c", "code"], env)
        (root / "lib").mkdir()
        (root / "lib" / "x.py").write_text("x\n")
        commit(root, "2026-01-03", "code", "lib/x.py")
        status, out = quiet(lambda: check(root, "main", env))
        check_(status == 1 and out.startswith("lib/x.py changes"),
               f"--check: code without a fragment exits 1 and names the path -> {status}, {out!r}")
        fragment(root, "topic.md", "- **T.** t.\n", "2026-01-04")
        check_(quiet(lambda: check(root, "main", env))[0] == 0, "--check: code with an added fragment exits 0")
        git(root, ["switch", "-q", "-c", "docs", "main"], env)
        (root / "docs").mkdir()
        (root / "docs" / "x.md").write_text("x\n")
        commit(root, "2026-01-05", "docs", "docs/x.md")
        check_(quiet(lambda: check(root, "main", env))[0] == 0, "--check: docs only exits 0")
        check_((raises(lambda: check(root, "no-such-ref", env)) or "").startswith("git diff no-such-ref...HEAD: "),
               "--check: a base that git cannot resolve stops")
    return total, wrong
