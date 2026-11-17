"""The cases of the dependents workflow and of `harness workflows`, on fixture research roots below
a temporary directory. No subcommand of its own; `githooks.selftest` runs them.

- `harness dependents`: on a root whose base has a dependent through `[deps]` with an origin that
  ends in `.git` and one with an origin that does not, beside a package with the base only in
  `[weakdeps]`, one with it only in `test/Project.toml` and an experiment with it in `[deps]`, the
  written `.github/dependents.toml` is byte for byte the expected one; the dry run writes nothing
  and exits 1, and exits 0 after `--apply`. A base whose own UUID is in its `[deps]` is not its own
  dependent, and a `[deps]` value that is not a string does not stop the census. A dependent
  whose origin is on another host, or that has no origin, and a listed name that is no git
  repository with a `Project.toml` (a missing name, a directory with no `.git`, a git repository
  with no Project.toml, `..` and a name with a `/`), are each refused with a line that names
  them. So are a dependent's Project.toml that is not TOML, a dependent whose directory name
  holds a space, and a base with no string uuid; a refusal in the census of the second of two
  bases writes the file of neither. An old `.github/dependents.toml` that is not UTF-8, a
  directory or a symbolic link, or below a `.github` that is a file or a dangling symbolic link,
  is refused in the dry run and with `--apply`, and changes nothing. The profile loads the key,
  and `harness get` prints it.
- `githooks.github_name`: the GitHub `owner/name` of a URL of each of the five schemes and of the
  scp form, with or without a user, with a port, `.git`, a final `/` or the scheme or host in
  capitals; None for another host or scheme, a local path (`github.com/o/A.jl` too), a query, a
  fragment, a port that is not a number, a URL user that holds `@`, `?` or `#`, an scp user that
  holds `/` or `:`, an owner that holds `.`, the name `.` or `..`, and a path of one or three
  parts.
- `harness workflows`: Dependents.yml and dependents.jl go into the listed base only, byte for
  byte; a dry run names the two files in an unlisted repository and keeps them, and `--apply`
  removes them; a listed name that does not exist and a missing Dependents.yml or Downgrade.yml
  template are refused. Without `dependents_bases`, the subcommand writes only the files of the
  other templates, Downgrade.yml among them, and names neither file.
- githooks/workflows/CI.yml: which job waits for which, so that test-other starts only after test
  and prerelease waits for nothing; that test-other runs after no failure; the matrix, the name and
  the continue-on-error of each job; the coverage of test alone; the triggers with the weekly cron,
  and the concurrency group with the event. The script of its `groups` job, run for each event
  without a group file and with groups, `split` and `once`: the groups of the downgrade job, and the
  rows of `test` and `test-other`, with macOS and Windows on `1` for a pull request and a push to a
  branch and on `min` and `1` for a tag, the schedule, a run by hand and `merge_group`; one row per
  entry with `split = false`, and the groups of `once` on Ubuntu with `1` alone on a pull request
  and a push to a branch. A group twice, and each value of `split` and `once` that it refuses, writes
  nothing and is refused with the text that names the key.
- githooks/workflows/Downgrade.yml: its name, its triggers with their paths, the tags and the cron,
  the concurrency group of CI.yml, the `groups` job of CI.yml, and its downgrade job; `actionlint`
  passes on it, and without shellcheck on CI.yml, where it is on the PATH.
- githooks/workflows/Dependents.yml: its trigger, concurrency group, permissions, jobs and matrix,
  the actions of its `uses:` lines, a second checkout of the dependent for the run against the
  default branch, a setup step and a test step against the head and against the default branch
  with their conditions and their order, the four outcomes that the row step passes, and
  `persist-credentials: false` on every checkout; `actionlint` passes on it, where it is on the
  PATH.
- every workflow template of githooks/workflows/: each `actions/checkout` step sets
  `persist-credentials: false`, and the templates hold at least one such step.
- githooks/workflows/dependents.jl, where `julia` is on the PATH: `excluded` on a head inside the
  dependent's `[compat]` entry, outside it, against an entry with two specifiers, and with no
  entry; `excluded` refuses a base or a dependent Project.toml that is not TOML, a base version
  that is no version number and a `[compat]` entry that is no version specifier; `row` on the five
  rows, with the summary it appends and its exit status, on a cancelled step in each of the four
  places, on an excluded dependent with a cancelled step, on ten combinations that are none of
  them and on the two outcomes of a run without a setup step; `list` on a file of two dependents,
  on a missing file, on a file that is not TOML and on two entries that the JSON of the matrix
  cannot hold.
- githooks/workflows/dependents.jl, where `julia` is on the PATH and the harness's Julia
  environment holds a Project.toml: JuliaFormatter's SciML style finds it formatted, as the
  pre-commit hook of a base checks its installed copy.
- githooks/verify-workflows.jl, where `julia` is on the PATH and the harness's Julia environment
  holds a Project.toml: a clean fixture passes, and prints the required checks of
  `protection.REQUIRED_CHECKS`, and for a repository with the groups `core` and `slow`, alone, with
  `split = false`, with `once`, and with both, those of `protection.required_checks`; a group file
  with `once = ["core"]` fails check 6 and prints no list; a drifted Downgrade.yml, a CI.yml whose
  test-other job has another name, a CI.yml without a test-other job, a drifted Dependents.yml, a
  missing dependents.jl, a Dependents.yml in an unlisted repository and a listed base without
  dependents.toml each fail with a line that names the repository; an experiment that
  `dependents_bases` names is no base; without `dependents_bases`, the fixture of the other
  templates passes, and so it does with a profile without `docs_exceptions` and
  `docs_additions`.
"""

import argparse
import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Generator, Mapping
from typing import cast
from unittest import mock

from . import REPO, HarnessError, githooks, install, jsonio, protection, wikilint
from . import profile as profile_module
from .sweep import GIT

type Check = Callable[[object, str], None]

TIMEOUT = 120  # seconds for one run of julia, actionlint or git
REFUSED = 2  # the exit status of dependents.jl on a refusal
TIMEOUT_MINUTES = 60  # the timeout of a test job of Dependents.yml
DEPENDENTS_JL = REPO / "githooks" / "workflows" / "dependents.jl"
DEPENDENTS_YML = REPO / "githooks" / "workflows" / "Dependents.yml"
VERIFY = REPO / "githooks" / "verify-workflows.jl"
CI_YML = REPO / "githooks" / "workflows" / "CI.yml"
DOWNGRADE_YML = REPO / "githooks" / "workflows" / "Downgrade.yml"
# The weekly trigger and the concurrency group of CI.yml and Downgrade.yml.
WEEKLY = [{"cron": "17 3 * * 1"}]
CONCURRENCY = "${{ github.workflow }}-${{ github.ref }}-${{ github.event_name }}"
# The matrix values that the outputs of the `groups` job give: the groups of the downgrade job, and
# the rows of `test` and of `test-other`.
GROUPS_LIST = "${{ fromJSON(needs.groups.outputs.list) }}"
GROUPS_TEST = "${{ fromJSON(needs.groups.outputs.test) }}"
GROUPS_OTHER = "${{ fromJSON(needs.groups.outputs.other) }}"
# The keys of a row of the outputs `test` and `other`, sorted.
ROW_KEYS = ["arch", "args", "group", "os", "version"]
# The Julia version and the system of each matrix entry of `test` and `test-other`.
UBUNTU_MIN, UBUNTU_1 = ("min", "ubuntu-latest"), ("1", "ubuntu-latest")
OTHER_1 = [("1", "macOS-latest"), ("1", "windows-latest")]
OTHER_MIN = [("min", "macOS-latest"), ("min", "windows-latest")]
# The names of the Julia jobs of CI.yml, which are the names of the required checks.
TEST_NAME = (
    "Julia ${{ matrix.version }} - ${{ matrix.os }} - ${{ matrix.arch }}"
    "${{ matrix.group && format(' - {0}', matrix.group) || '' }}"
)
PRERELEASE_NAME = "Julia ${{ matrix.version }} - ${{ matrix.os }} - ${{ matrix.arch }}"
# The two projects that the downgrade job resolves, which Downgrade.yml watches.
PROJECTS = ["Project.toml", "test/Project.toml"]
# The standard libraries that the downgrade job of Downgrade.yml keeps at their bundled versions.
DOWNGRADE_SKIP = ",".join(
    [
        *("ArgTools", "Artifacts", "Base64", "CRC32c", "Dates", "DelimitedFiles", "Distributed"),
        *("Downloads", "FileWatching", "Future", "InteractiveUtils", "LazyArtifacts", "LibCURL"),
        *("LibGit2", "Libdl", "LinearAlgebra", "Logging", "Markdown", "Mmap", "NetworkOptions", "Pkg"),
        *("Printf", "Profile", "REPL", "Random", "SHA", "Serialization", "SharedArrays", "Sockets"),
        *("SparseArrays", "Statistics", "TOML", "Tar", "Test", "UUIDs", "Unicode"),
    ]
)
# The jobs of CI.yml that run the tests.
TESTED = ("test", "test-other", "prerelease")
BASE_UUID = "00000000-0000-0000-0000-00000000000b"
# The installed paths of the two files, relative to a repository.
INSTALLED = (".github/workflows/Dependents.yml", ".github/dependents.jl")
# The file that `harness dependents --apply` writes for the fixture base, byte for byte.
EXPECTED = (
    "# Written by `harness dependents --apply` from the Project.toml files below Packages/ of the\n"
    "# research tree; run it again rather than edit this file. Dependents.yml reads it into the\n"
    "# matrix of its test job.\n"
    "\n"
    "[[dependent]]\n"
    'name = "Alpha"\n'
    'repository = "example-org/Alpha.jl"\n'
    "\n"
    "[[dependent]]\n"
    'name = "Beta"\n'
    'repository = "example-org/Beta.jl"\n'
)


def run(command: list[str], env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """`command`, its output captured as text, whatever its exit status."""
    return subprocess.run(
        command,
        env=None if env is None else dict(env),
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT,
    )


def project(name: str, uuid: str, *, deps: str = "", extra: str = "") -> str:
    """The text of a Project.toml: `name`, `uuid`, version 0.1.0, `[deps]` with the lines `deps`,
    then `extra` as it is."""
    return f'name = "{name}"\nuuid = "{uuid}"\nversion = "0.1.0"\n\n[deps]\n{deps}{extra}'


def repository(root: pathlib.Path, rel: str, text: str, origin: str | None) -> pathlib.Path:
    """A git repository at `root / rel` with the Project.toml `text` and, where given, the remote
    `origin`."""
    d = root / rel
    d.mkdir(parents=True)
    (d / "Project.toml").write_text(text)
    for command in (["init", "-q", "-b", "main"], *([["remote", "add", "origin", origin]] if origin else [])):
        p = run(["git", "-C", str(d), *command])
        if p.returncode != 0:
            raise HarnessError(f"git {command[0]} in {d}: {p.stderr.strip()}")
    return d


def fixture(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """The research root of the cases, by repository name: the base `Base`, its dependents `Alpha`
    and `Beta`, `Weak` with the base in `[weakdeps]`, `TestOnly` with it in `test/Project.toml`,
    `Other` with no dependency, and the experiment `Lab` with the base in `[deps]`."""
    base = f'Base = "{BASE_UUID}"\n'
    repos = {
        "Base": repository(
            root, "Packages/Base", project("Base", BASE_UUID), "https://github.com/example-org/Base.jl.git"
        ),
        "Alpha": repository(
            root,
            "Packages/Alpha",
            project("Alpha", "00000000-0000-0000-0000-0000000000a1", deps=base),
            "https://github.com/example-org/Alpha.jl.git",
        ),
        "Beta": repository(
            root,
            "Packages/Beta",
            project("Beta", "00000000-0000-0000-0000-0000000000b1", deps=base),
            "git@github.com:example-org/Beta.jl",
        ),
        "Weak": repository(
            root,
            "Packages/Weak",
            project("Weak", "00000000-0000-0000-0000-0000000000c1", extra=f"\n[weakdeps]\n{base}"),
            "https://github.com/example-org/Weak.jl.git",
        ),
        "TestOnly": repository(
            root,
            "Packages/TestOnly",
            project("TestOnly", "00000000-0000-0000-0000-0000000000d1"),
            "https://github.com/example-org/TestOnly.jl.git",
        ),
        "Other": repository(
            root,
            "Packages/Other",
            project("Other", "00000000-0000-0000-0000-0000000000e1"),
            "https://github.com/example-org/Other.jl.git",
        ),
        "Lab": repository(
            root,
            "Experiments/Lab",
            project("Lab", "00000000-0000-0000-0000-0000000000f1", deps=base),
            "https://github.com/example-org/Lab.git",
        ),
    }
    (repos["TestOnly"] / "test").mkdir()
    (repos["TestOnly"] / "test" / "Project.toml").write_text(f"[deps]\n{base}")
    return repos


def profile_file(path: pathlib.Path, bases: str | None) -> pathlib.Path:
    """A profile at `path` with the TOML list `bases` as `dependents_bases`, or without the key for
    None, and empty `docs_exceptions` and `docs_additions`, which verify-workflows.jl reads."""
    keys = {"docs_exceptions": "[]", "docs_additions": "[]"} | (
        {} if bases is None else {"dependents_bases": bases}
    )
    path.write_text(profile_module.profile_text(**keys))
    return path


def quiet(
    command: Callable[[argparse.Namespace], int], profile: pathlib.Path, *, apply: bool
) -> tuple[object, str]:
    """`command` with the profile `profile` and `--apply` when `apply`: its exit status, or the
    message of its HarnessError, and what it printed."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            code: object = command(argparse.Namespace(profile=str(profile), apply=apply))
        except HarnessError as e:
            code = f"error: {e}"
    return code, out.getvalue()


@contextlib.contextmanager
def changed_file(path: pathlib.Path, text: str | None) -> Generator[None]:
    """`path` with the text `text`, or removed for None, for the length of the block; then as it
    was."""
    before = path.read_bytes() if path.is_file() else None
    if text is None:
        path.unlink()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    try:
        yield
    finally:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(before)


def dependents_cases(check: Check, tmp: pathlib.Path) -> None:
    """`harness dependents` on the fixture root."""
    repos = fixture(tmp / "Research")
    written = repos["Base"] / ".github" / "dependents.toml"
    listed = profile_file(tmp / "listed.toml", '["Base"]')
    loaded = profile_module.load(listed)
    check(
        loaded.dependents_bases == ("Base",) and profile_module.get(loaded, "dependents_bases") == ["Base"],
        f"the profile loads dependents_bases, and harness get prints it -> {loaded.dependents_bases}",
    )
    code, out = quiet(githooks.cmd_dependents, listed, apply=False)
    check(
        code == 1 and not written.exists() and "would write" in out,
        f"the dry run of dependents plans the file, writes nothing and exits 1 -> {code}, "
        f"{out.strip()[-200:]!r}",
    )
    code, out = quiet(githooks.cmd_dependents, listed, apply=True)
    got = written.read_text() if written.is_file() else None
    check(
        code == 0 and got == EXPECTED,
        f"dependents --apply writes Alpha and Beta, sorted, and no other repository -> {code}, {got!r}",
    )
    code, out = quiet(githooks.cmd_dependents, listed, apply=False)
    check(code == 0, f"the dry run after --apply exits 0 -> {code}, {out.strip()[-200:]!r}")
    with changed_file(
        repos["Base"] / "Project.toml", project("Base", BASE_UUID, deps=f'Base = "{BASE_UUID}"\n')
    ):
        rows = githooks.census(repos["Base"])
    check(
        [name for name, _ in rows] == ["Alpha", "Beta"],
        f"a base that names its own UUID in [deps] is not its own dependent -> {rows}",
    )
    with changed_file(
        repos["Alpha"] / "Project.toml",
        project("Alpha", "00000000-0000-0000-0000-0000000000a1", deps=f'Base = "{BASE_UUID}"\nOdd = ["x"]\n'),
    ):
        rows = githooks.census(repos["Base"])
    check(
        [name for name, _ in rows] == ["Alpha", "Beta"],
        f"a [deps] value that is not a string does not stop the census -> {rows}",
    )
    for label, origin in (
        ("an origin on another host", "https://gitlab.example.org/example-org/Far.jl.git"),
        ("no origin", None),
    ):
        far = repository(
            tmp / "Research",
            "Packages/Far",
            project("Far", "00000000-0000-0000-0000-0000000000ff", deps=f'Base = "{BASE_UUID}"\n'),
            origin,
        )
        code, _ = quiet(githooks.cmd_dependents, listed, apply=True)
        check(
            isinstance(code, str)
            and code.startswith("error: ")
            and "Far" in code
            and written.read_text() == EXPECTED,
            f"a dependent with {label} is refused, naming it, and the file stays -> {code}",
        )
        shutil.rmtree(far)
    refused_census_cases(check, tmp, repos)
    old_file_cases(check, tmp, repos)
    research = tmp / "Research"
    plain = research / "Packages" / "Plain"
    plain.mkdir()
    (plain / "Project.toml").write_text(project("Plain", "00000000-0000-0000-0000-000000000011"))
    (repository(research, "Packages/Bare", "", None) / "Project.toml").unlink()
    # The research root as a git repository with a Project.toml, so that `..` passes every other
    # test of a base.
    (research / ".git").mkdir()
    (research / "Project.toml").write_text(project("Root", "00000000-0000-0000-0000-000000000012"))
    for name in ("Nope", "Plain", "Bare", "..", "../Packages/Alpha"):
        code, _ = quiet(
            githooks.cmd_dependents, profile_file(tmp / "missing.toml", f'["{name}"]'), apply=True
        )
        check(
            isinstance(code, str) and code.startswith("error: ") and name in code,
            f"dependents refuses the listed name {name}, no git repository with a Project.toml -> {code}",
        )


def refused_census_cases(check: Check, tmp: pathlib.Path, repos: dict[str, pathlib.Path]) -> None:
    """The census refusals that name a repository: a dependent's Project.toml that is not TOML, a
    dependent whose directory name dependents.toml cannot hold, and a base with no uuid or a uuid
    that is not a string. A refusal
    in the census of the second of two bases writes the file of neither."""
    listed = profile_file(tmp / "listed.toml", '["Base"]')
    written = repos["Base"] / ".github" / "dependents.toml"
    with changed_file(repos["Alpha"] / "Project.toml", "name = \n"):
        code, _ = quiet(githooks.cmd_dependents, listed, apply=True)
    check(
        isinstance(code, str) and "Alpha" in code and "TOML" in code and written.read_text() == EXPECTED,
        f"dependents refuses a dependent's Project.toml that is not TOML, naming it -> {code}",
    )
    odd = repository(
        tmp / "Research",
        "Packages/Odd Name",
        project("Odd", "00000000-0000-0000-0000-000000000013", deps=f'Base = "{BASE_UUID}"\n'),
        "git@github.com:example-org/Odd.jl",
    )
    code, _ = quiet(githooks.cmd_dependents, listed, apply=True)
    check(
        isinstance(code, str) and "Odd Name" in code and written.read_text() == EXPECTED,
        f"dependents refuses a dependent whose directory name holds a space, naming it -> {code}",
    )
    shutil.rmtree(odd)
    for label, text in (
        ("no uuid", 'name = "Base"\nversion = "0.1.0"\n'),
        ("a uuid that is not a string", 'name = "Base"\nuuid = 11\nversion = "0.1.0"\n'),
    ):
        with changed_file(repos["Base"] / "Project.toml", text):
            code, _ = quiet(githooks.cmd_dependents, listed, apply=True)
        check(
            isinstance(code, str) and code.startswith("error: ") and "uuid" in code and "Base" in code,
            f"dependents refuses a base with {label}, naming it -> {code}",
        )
    second = repository(
        tmp / "Research",
        "Packages/Second",
        project("Second", "00000000-0000-0000-0000-000000000014"),
        "https://github.com/example-org/Second.jl.git",
    )
    repository(
        tmp / "Research",
        "Packages/Far",
        project(
            "Far",
            "00000000-0000-0000-0000-0000000000ff",
            deps='Second = "00000000-0000-0000-0000-000000000014"\n',
        ),
        None,
    )
    with changed_file(written, "stale\n"):
        code, _ = quiet(
            githooks.cmd_dependents, profile_file(tmp / "two.toml", '["Base", "Second"]'), apply=True
        )
        kept = written.read_text()
    check(
        isinstance(code, str) and "Far" in code and kept == "stale\n" and not (second / ".github").exists(),
        f"a refusal in the census of the second base writes the file of neither -> {code}, {kept!r}",
    )
    shutil.rmtree(second)
    shutil.rmtree(tmp / "Research" / "Packages" / "Far")


def old_file_cases(check: Check, tmp: pathlib.Path, repos: dict[str, pathlib.Path]) -> None:
    """The refusals of an old `.github/dependents.toml` that is not a UTF-8 regular file: a file
    that is not UTF-8, a directory, a symbolic link, and a `.github` that is a file or a dangling
    symbolic link. Each refusal, of the dry run and of `--apply`, names the path and changes
    nothing; a refusal for the second of two bases writes the file of neither."""
    listed = profile_file(tmp / "listed.toml", '["Base"]')
    github = repos["Base"] / ".github"
    path = github / "dependents.toml"
    target = tmp / "target.toml"
    target.write_text("stale\n")
    saved = tmp / "github-saved"
    shutil.move(github, saved)
    for label, make in (
        ("a file that is not UTF-8", lambda: path.write_bytes(b"# caf\xe9\n")),
        ("a directory", path.mkdir),
        ("a symbolic link", lambda: path.symlink_to(target)),
        ("below a .github that is a file", lambda: None),
        ("below a .github that is a dangling symbolic link", lambda: None),
    ):
        if label == "below a .github that is a file":
            github.write_text("not a directory\n")
        elif label.startswith("below"):
            github.symlink_to(tmp / "nowhere")
        else:
            github.mkdir()
            make()
        before = sorted((p.name, p.is_dir()) for p in github.iterdir()) if github.is_dir() else None
        for apply in (False, True):
            code, _ = quiet(githooks.cmd_dependents, listed, apply=apply)
            check(
                isinstance(code, str) and code.startswith("error: ") and "dependents.toml" in code,
                f"dependents{' --apply' if apply else ''} refuses an old dependents.toml that is {label}, "
                f"naming it -> {code}",
            )
        after = sorted((p.name, p.is_dir()) for p in github.iterdir()) if github.is_dir() else None
        same = before == after and target.read_text() == "stale\n"
        if label == "a file that is not UTF-8":
            same = same and path.read_bytes() == b"# caf\xe9\n"
        check(same, f"the refusal of an old dependents.toml that is {label} changes no file")
        if github.is_dir():
            shutil.rmtree(github)
        else:
            github.unlink()
    shutil.move(saved, github)
    second = repository(
        tmp / "Research",
        "Packages/Second",
        project("Second", "00000000-0000-0000-0000-000000000014"),
        "https://github.com/example-org/Second.jl.git",
    )
    (second / ".github" / "dependents.toml").mkdir(parents=True)
    with changed_file(path, "stale\n"):
        code, _ = quiet(
            githooks.cmd_dependents, profile_file(tmp / "two.toml", '["Base", "Second"]'), apply=True
        )
        kept = path.read_text()
    check(
        isinstance(code, str) and "Second" in code and kept == "stale\n",
        f"a refusal of the old file of the second base writes the file of neither -> {code}, {kept!r}",
    )
    shutil.rmtree(second)


def origin_cases(check: Check) -> None:
    """`githooks.github_name` on the origins that `git remote get-url origin` can print."""
    for url, want in (
        ("https://github.com/o/A.jl.git", "o/A.jl"),
        ("https://github.com/o/A.jl", "o/A.jl"),
        ("https://github.com/o/A.jl/", "o/A.jl"),
        ("https://GitHub.com/o/A.jl.git", "o/A.jl"),
        ("https://user@github.com/o/A.jl.git", "o/A.jl"),
        ("git@github.com:o/A.jl", "o/A.jl"),
        ("git@github.com:o/A.jl.git", "o/A.jl"),
        ("ssh://git@github.com/o/A.jl.git", "o/A.jl"),
        ("ssh://git@github.com:22/o/A.jl.git", "o/A.jl"),
        ("github.com:o/A.jl", "o/A.jl"),
        ("HTTPS://github.com/o/A.jl", "o/A.jl"),
        ("git+ssh://git@github.com/o/A.jl", "o/A.jl"),
        ("ssh+git://git@github.com/o/A.jl", "o/A.jl"),
        ("http://github.com/o/A.jl", "o/A.jl"),
        ("git@GITHUB.COM:o/A.jl", "o/A.jl"),
        ("https://gitlab.example.org/o/A.jl.git", None),
        ("https://github.com.example.org/o/A.jl.git", None),
        ("git@gitlab.example.org:o/A.jl.git", None),
        ("file:///srv/git/o/A.jl", None),
        ("/srv/git/o/A.jl", None),
        ("https://github.com/o", None),
        ("https://github.com/o/A.jl/tree", None),
        ("https://github.com/o/A.jl//", None),
        ("", None),
        ("github.com/o/A.jl", None),
        ("github.com/o/A.jl.git", None),
        ("file://github.com/o/A.jl", None),
        ("ftp://github.com/o/A.jl", None),
        ("https://github.com/o/A.jl?x=1", None),
        ("https://github.com/o/A.jl#f", None),
        ("https://github.com/o/..", None),
        ("https://github.com/o/.", None),
        ("https://github.com/o.x/A.jl", None),
        ("https://github.com:abc/o/A.jl", None),
        ("https://a@b@github.com/o/A.jl", None),
        ("https://a?b@github.com/o/A.jl", None),
        ("https://a#b@github.com/o/A.jl", None),
        ("dir/git@github.com:o/A.jl", None),
        ("a:b@github.com:o/A.jl", None),
    ):
        got = githooks.github_name(url)
        check(got == want, f"github_name({url!r}) is {want} -> {got}")


def installed(repo: pathlib.Path) -> list[str]:
    """The paths of INSTALLED that exist in `repo`."""
    return [rel for rel in INSTALLED if (repo / rel).exists()]


def workflow_cases(check: Check, tmp: pathlib.Path) -> None:
    """`harness workflows` on the fixture root, with and without `dependents_bases`."""
    repos = fixture(tmp / "Research")
    listed = profile_file(tmp / "listed.toml", '["Base"]')
    code, out = quiet(githooks.cmd_workflows, listed, apply=True)
    identical = all(
        (repos["Base"] / rel).read_bytes() == source.read_bytes()
        for rel, source in zip(INSTALLED, (DEPENDENTS_YML, DEPENDENTS_JL), strict=True)
        if (repos["Base"] / rel).is_file()
    )
    others = {name: installed(d) for name, d in repos.items() if name != "Base" and installed(d)}
    check(
        code == 0 and installed(repos["Base"]) == list(INSTALLED) and identical and not others,
        f"workflows --apply installs both files byte-identical into the listed base only -> {code}, "
        f"{installed(repos['Base'])}, identical {identical}, elsewhere {others}",
    )
    for rel, source in zip(INSTALLED, (DEPENDENTS_YML, DEPENDENTS_JL), strict=True):
        (repos["Other"] / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, repos["Other"] / rel)
    code, out = quiet(githooks.cmd_workflows, listed, apply=False)
    check(
        code == 1
        and out.count("would remove .github/") == len(INSTALLED)
        and installed(repos["Other"]) == list(INSTALLED),
        f"the dry run names both files of an unlisted repository and keeps them -> {code}, "
        f"{[line.strip() for line in out.splitlines() if 'remove' in line]}",
    )
    code, out = quiet(githooks.cmd_workflows, listed, apply=True)
    check(
        code == 0 and not installed(repos["Other"]) and installed(repos["Base"]) == list(INSTALLED),
        f"workflows --apply removes both files from an unlisted repository -> {code}, "
        f"{installed(repos['Other'])}",
    )
    code, _ = quiet(githooks.cmd_workflows, profile_file(tmp / "missing.toml", '["Nope"]'), apply=True)
    check(
        isinstance(code, str) and code.startswith("error: ") and "Nope" in code,
        f"workflows refuses a listed name that does not exist, naming it -> {code}",
    )
    templates = tmp / "templates"
    shutil.copytree(githooks.WORKFLOWS, templates)
    (templates / "Dependents.yml").unlink()
    with mock.patch.object(githooks, "WORKFLOWS", templates):
        code, _ = quiet(githooks.cmd_workflows, listed, apply=True)
    check(
        isinstance(code, str) and "missing template" in code and "Dependents.yml" in code,
        f"workflows refuses a missing Dependents.yml template, naming it -> {code}",
    )
    shutil.copyfile(DEPENDENTS_YML, templates / "Dependents.yml")
    (templates / "Downgrade.yml").unlink(missing_ok=True)
    with mock.patch.object(githooks, "WORKFLOWS", templates):
        # An installer that does not check the template first fails later, on the copy.
        try:
            code, _ = quiet(githooks.cmd_workflows, listed, apply=True)
        except FileNotFoundError as e:
            code = f"FileNotFoundError: {e}"
    check(
        isinstance(code, str) and "missing template" in code and "Downgrade.yml" in code,
        f"workflows refuses a missing Downgrade.yml template, naming it -> {code}",
    )
    bare = fixture(tmp / "bare" / "Research")
    with mock.patch.dict(os.environ, RESEARCH_ROOT=str(tmp / "bare" / "Research")):
        code, out = quiet(githooks.cmd_workflows, profile_file(tmp / "none.toml", None), apply=True)
    files = sorted(
        str(p.relative_to(bare["Base"]))
        for p in bare["Base"].rglob("*")
        if p.is_file() and ".git" not in p.parts
    )
    check(
        code == 0
        and files
        == [
            ".github/dependabot.yml",
            ".github/workflows/CI.yml",
            ".github/workflows/Downgrade.yml",
            ".github/workflows/TagBot.yml",
            "Project.toml",
            "codecov.yml",
        ]
        and "ependents" not in out,
        f"without dependents_bases, workflows writes the other templates alone and names neither file "
        f"-> {code}, {files}",
    )


def yaml_cases(check: Check) -> None:
    """The settings of Dependents.yml, read with the YAML reader of `harness wiki-lint`, and
    `actionlint` on it."""
    read = wikilint.yaml_reader()(DEPENDENTS_YML.read_text())
    check(
        not read.refused, f"Dependents.yml is YAML with no repeated key -> line {read.line}, {read.duplicate}"
    )
    data = cast("dict[object, object]", read.data if isinstance(read.data, dict) else {})
    on = triggers(data)
    pull = cast("dict[str, object]", on.get("pull_request") or {})
    check(
        sorted(on) == ["pull_request", "workflow_dispatch"]
        and pull.get("paths") == ["src/**", "ext/**", "Project.toml"],
        f"Dependents.yml runs on a pull request that changes src/, ext/ or Project.toml, and by hand -> {on}",
    )
    concurrency = cast("dict[str, object]", data.get("concurrency") or {})
    check(
        "github.ref" in str(concurrency.get("group")) and concurrency.get("cancel-in-progress") is True,
        f"one concurrency group per ref, with cancel-in-progress -> {concurrency}",
    )
    check(
        data.get("permissions") == {"contents": "read"},
        f"permissions: contents: read -> {data.get('permissions')}",
    )
    jobs = cast("dict[str, dict[str, object]]", data.get("jobs") or {})
    test = jobs.get("test", {})
    strategy = cast("dict[str, object]", test.get("strategy") or {})
    matrix = cast("dict[str, object]", strategy.get("matrix") or {})
    check(
        sorted(jobs) == ["list", "test"]
        and test.get("needs") == "list"
        and test.get("runs-on") == "ubuntu-latest"
        and test.get("timeout-minutes") == TIMEOUT_MINUTES
        and strategy.get("fail-fast") is False
        and matrix == {"dependent": "${{ fromJSON(needs.list.outputs.dependents) }}"},
        f"a list job, and a test job per dependent on ubuntu-latest, 60 minutes, fail-fast false -> "
        f"{ {k: test.get(k) for k in ('needs', 'runs-on', 'timeout-minutes')} }, {strategy}",
    )
    steps = job_steps(test)
    uses = {str(s["uses"]) for job in jobs.values() for s in job_steps(job) if "uses" in s}
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    versions = [
        cast("dict[str, object]", s.get("with") or {}).get("version")
        for s in steps
        if str(s.get("uses", "")).startswith("julia-actions/setup-julia")
    ]
    check(
        uses == {"actions/checkout@v7", "julia-actions/setup-julia@v3", "julia-actions/cache@v3"}
        and versions == ["1"]
        and 'Pkg.test(test_args = ["core"])' in runs
        and "Pkg.develop(path = " in runs
        and "dependents.jl excluded" in runs
        and "dependents.jl row" in runs,
        f"the test job checks the compat, develops the base, runs `core` on Julia 1 and writes the row "
        f"-> {sorted(uses)}, {versions}",
    )
    by_id = {str(s.get("id")): s for s in steps if "id" in s}
    projects = [str(by_id.get(name, {}).get("run", "")).split()[2:3] for name in ("head_setup", "main_setup")]
    paths = [
        str(cast("dict[str, object]", s.get("with") or {}).get("path"))
        for s in steps
        if "repository" in cast("dict[str, object]", s.get("with") or {})
    ]
    fresh = next(
        (
            i
            for i, s in enumerate(steps)
            if cast("dict[str, object]", s.get("with") or {}).get("path") == "dependent-main"
        ),
        len(steps),
    )
    main = next((i for i, s in enumerate(steps) if s.get("id") == "main_setup"), -1)
    check(
        projects == [["--project=dependent"], ["--project=dependent-main"]]
        and paths == ["dependent", "dependent-main"]
        and fresh < main,
        f"the run against the default branch tests a second checkout of the dependent, made before it, "
        f"not the one that the run against the head resolved -> projects {projects}, checkouts {paths}, "
        f"steps {fresh} and {main}",
    )
    step_cases(check, steps)
    keeps = [
        (name, i)
        for name, job in jobs.items()
        for i, s in enumerate(job_steps(job))
        if str(s.get("uses", "")).startswith("actions/checkout@")
        and given(s).get("persist-credentials") is not False
    ]
    check(
        not keeps,
        f"no checkout keeps the token, since the dependents' tests run code of other repositories -> "
        f"checkouts without persist-credentials false (job, step) {keeps}",
    )
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        print("skip  githooks: no actionlint on the PATH; Dependents.yml is not linted")
        return
    p = run([actionlint, str(DEPENDENTS_YML)])
    check(
        p.returncode == 0, f"actionlint passes on Dependents.yml -> {p.returncode} {p.stdout.strip()[-300:]}"
    )


def step_cases(check: Check, steps: list[dict[str, object]]) -> None:
    """The setup and test steps of the test job of Dependents.yml, their conditions and their
    order, and the four outcomes that the row step passes to dependents.jl."""
    failed = "steps.head_setup.outcome == 'failure' || steps.head_test.outcome == 'failure'"
    # id or checkout path: the condition, and the Pkg call, project and path of its julia run.
    want: dict[str, tuple[str, str]] = {
        "head_setup": ("steps.compat.outputs.excluded == 'false'", 'develop dependent abspath("base")'),
        "head_test": ("steps.head_setup.outcome == 'success'", "test dependent"),
        "main": (failed, ""),
        "dependent-main": (failed, ""),
        "main_setup": (failed, 'develop dependent-main abspath("main")'),
        "main_test": ("steps.main_setup.outcome == 'success'", "test dependent-main"),
    }

    def key(s: dict[str, object]) -> str:
        return str(s.get("id") or cast("dict[str, object]", s.get("with") or {}).get("path"))

    def call(s: dict[str, object]) -> str:
        """The Pkg call of a julia run, its project, and the path it develops."""
        run = str(s.get("run", ""))
        if not run:
            return ""
        project = next((w.removeprefix("--project=") for w in run.split() if w.startswith("--project=")), "?")
        calls = [c for c in ("develop", "test") if f"Pkg.{c}(" in run]
        path = run.partition("Pkg.develop(path = ")[2].partition(")")[0] + ")" if "develop" in calls else ""
        return " ".join([*calls, project, *([path] if path else [])])

    got = {
        key(s): (str(s.get("if")), call(s), s.get("continue-on-error") is True)
        for s in steps
        if key(s) in want
    }
    expected = {k: (cond, run, bool(run)) for k, (cond, run) in want.items()}
    check(
        got == expected,
        f"a setup step and a test step against the head and against the default branch, each with "
        f"continue-on-error; a test step only after its setup succeeded; the default branch only "
        f"after a failed head setup or head test -> {got}",
    )
    order = [key(s) for s in steps if key(s) in want]
    check(
        order == ["head_setup", "head_test", "main", "dependent-main", "main_setup", "main_test"],
        f"the steps run in the order head setup, head test, the two checkouts, main setup, main test "
        f"-> {order}",
    )
    none: dict[str, object] = {}
    row = next((s for s in steps if "dependents.jl row" in str(s.get("run", ""))), none)
    env = cast("dict[str, object]", row.get("env") or {})
    check(
        row.get("if") == "always()"
        and env
        == {
            "NAME": "${{ matrix.dependent.name }}",
            "EXCLUDED": "${{ steps.compat.outputs.excluded }}",
            "HEAD_SETUP": "${{ steps.head_setup.outcome }}",
            "HEAD_TEST": "${{ steps.head_test.outcome }}",
            "MAIN_SETUP": "${{ steps.main_setup.outcome }}",
            "MAIN_TEST": "${{ steps.main_test.outcome }}",
        }
        and str(row.get("run", "")).endswith(
            'row "$NAME" "$EXCLUDED" "$HEAD_SETUP" "$HEAD_TEST" "$MAIN_SETUP" "$MAIN_TEST"'
        ),
        f"the row step always runs and passes the compat result and the four outcomes -> "
        f"{row.get('if')}, {env}, {row.get('run')}",
    )


def checkout_cases(check: Check) -> None:
    """No checkout of any workflow template keeps the token in the git configuration, where every
    later step of its job, the package's build, tests and docs among them, could read it."""
    checkouts = 0
    keeps: list[tuple[str, str, int]] = []
    for path in sorted(githooks.WORKFLOWS.glob("*.yml")):
        read = wikilint.yaml_reader()(path.read_text())
        check(
            not read.refused,
            f"{path.name} is YAML with no repeated key -> line {read.line}, {read.duplicate}",
        )
        data = cast("dict[object, object]", read.data if isinstance(read.data, dict) else {})
        jobs = cast("dict[str, dict[str, object]]", data.get("jobs") or {})
        for name, job in jobs.items():
            for i, s in enumerate(cast("list[dict[str, object]]", job.get("steps") or [])):
                if not str(s.get("uses", "")).startswith("actions/checkout@"):
                    continue
                checkouts += 1
                if cast("dict[str, object]", s.get("with") or {}).get("persist-credentials") is not False:
                    keeps.append((path.name, name, i))
    check(
        checkouts > 0 and not keeps,
        f"no checkout of a workflow template keeps the token -> {checkouts} checkouts, "
        f"without persist-credentials false (file, job, step) {keeps}",
    )


def template(path: pathlib.Path) -> tuple[dict[object, object], dict[str, dict[str, object]]]:
    """A workflow template, read with the YAML reader of `harness wiki-lint`, and its jobs."""
    read = wikilint.yaml_reader()(path.read_text())
    data = cast("dict[object, object]", read.data if isinstance(read.data, dict) else {})
    return data, cast("dict[str, dict[str, object]]", data.get("jobs") or {})


def triggers(data: dict[object, object]) -> dict[str, object]:
    """The `on:` table of a workflow, which YAML 1.1 reads under the key True."""
    return cast("dict[str, object]", data.get(True) or data.get("on") or {})


def job_steps(job: dict[str, object]) -> list[dict[str, object]]:
    """The steps of a job."""
    return cast("list[dict[str, object]]", job.get("steps") or [])


def given(step: dict[str, object]) -> dict[str, object]:
    """The `with:` table of a step."""
    return cast("dict[str, object]", step.get("with") or {})


def given_to(job: dict[str, object], action: str) -> dict[str, object]:
    """The `with:` table of the first step of a job that uses `action`, or an empty table."""
    found = [given(s) for s in job_steps(job) if str(s.get("uses", "")).startswith(f"{action}@")]
    return found[0] if found else {}


def matrix(job: dict[str, object]) -> object:
    """The matrix of a job, or None."""
    return cast("dict[str, object]", job.get("strategy") or {}).get("matrix")


def ci_cases(check: Check) -> None:
    """The jobs of CI.yml: which job waits for which, the matrix, the name and the
    continue-on-error of each, the coverage, the triggers and the concurrency group."""
    data, jobs = template(CI_YML)
    needs = {name: job.get("needs") for name, job in jobs.items()}
    check(
        sorted(jobs) == ["doctest", "groups", "prerelease", "test", "test-other"]
        and needs
        == {
            "groups": None,
            "test": "groups",
            "test-other": ["groups", "test"],
            "prerelease": None,
            "doctest": None,
        },
        f"CI.yml: test-other waits for test, and prerelease and doctest wait for no job -> {needs}",
    )
    other = jobs.get("test-other", {})
    conditions = [str(other.get("if", "")), *(str(s.get("if", "")) for s in job_steps(other))]
    after = [c for c in conditions if any(w in c for w in ("always()", "failure()", "cancelled()"))]
    check(not after, f"CI.yml: test-other and its steps never run after a failure of test -> {after}")
    matrices = {name: matrix(job) for name, job in jobs.items()}
    check(
        matrices
        == {
            "groups": None,
            "test": {"include": GROUPS_TEST},
            "test-other": {"include": GROUPS_OTHER},
            "prerelease": {"version": ["pre", "nightly"], "os": ["ubuntu-latest"], "arch": ["default"]},
            "doctest": {"os": ["ubuntu-latest"]},
        },
        f"CI.yml: test and test-other read the rows test and other of the groups job, pre and "
        f"nightly on Ubuntu, the doctests on Ubuntu -> {matrices}",
    )
    names = {name: (job.get("name"), job.get("continue-on-error")) for name, job in jobs.items()}
    check(
        names
        == {
            "groups": ("Test groups", None),
            "test": (TEST_NAME, None),
            "test-other": (TEST_NAME, None),
            "prerelease": (PRERELEASE_NAME, True),
            "doctest": ("Doctests - ${{ matrix.os }}", None),
        },
        f"CI.yml: test and test-other have the names of the required checks, and prerelease alone "
        f"continues on error -> {names}",
    )
    codecov = sorted(
        name
        for name, job in jobs.items()
        for s in job_steps(job)
        if str(s.get("uses", "")).startswith("codecov/")
    )
    coverage = {
        name: given(s).get("coverage")
        for name, job in jobs.items()
        for s in job_steps(job)
        if str(s.get("uses", "")).startswith("julia-actions/julia-runtest")
    }
    env = cast("dict[str, object]", jobs.get("test", {}).get("env") or {})
    check(
        codecov == ["test"]
        and coverage == {"test": "${{ env.COVERAGE }}", "test-other": False, "prerelease": False}
        and env.get("COVERAGE") == "${{ matrix.version == '1' && matrix.os == 'ubuntu-latest' }}",
        f"CI.yml: only test, on Ubuntu with 1, measures and uploads the coverage -> codecov in {codecov}, "
        f"coverage {coverage}",
    )
    entry = {"version": "${{ matrix.version }}", "arch": "${{ matrix.arch }}"}
    setup = {name: given_to(jobs.get(name, {}), "julia-actions/setup-julia") for name in TESTED}
    runtest = {name: given_to(jobs.get(name, {}), "julia-actions/julia-runtest") for name in TESTED}
    check(
        setup == dict.fromkeys(TESTED, entry)
        and runtest
        == {
            "test": {
                "check_bounds": "auto",
                "coverage": "${{ env.COVERAGE }}",
                "test_args": "${{ matrix.args }}",
            },
            "test-other": {"check_bounds": "auto", "coverage": False, "test_args": "${{ matrix.args }}"},
            "prerelease": {"check_bounds": "auto", "coverage": False},
        },
        f"CI.yml: test, test-other and prerelease set up the Julia and the architecture of their matrix "
        f"entry, and test and test-other run the test arguments of their row -> setup {setup}, "
        f"runtest {runtest}",
    )
    on = triggers(data)
    concurrency = cast("dict[str, object]", data.get("concurrency") or {})
    check(
        on
        == {
            "push": {"branches": ["main", "master"], "tags": ["*"]},
            "pull_request": None,
            "workflow_dispatch": None,
            "schedule": WEEKLY,
        }
        and concurrency.get("group") == CONCURRENCY,
        f"CI.yml runs on a push to main or master, a tag, a pull request, by hand and weekly, in one "
        f"concurrency group per ref and event -> {on}, {concurrency.get('group')}",
    )


def scratch_repository(tmp: pathlib.Path, text: str | None) -> pathlib.Path:
    """A new directory below `tmp` whose test/ci-groups.toml holds `text`, or which has none for
    None."""
    root = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    if text is not None:
        (root / "test").mkdir()
        (root / "test" / "ci-groups.toml").write_text(text)
    return root


def groups_output(root: pathlib.Path, event: str, ref: str) -> tuple[int, list[str], str]:
    """The script of the `groups` job of CI.yml, run as a runner runs it for `event` on `ref` in the
    repository `root`: its exit status, the lines that it writes to GITHUB_OUTPUT, and the last line
    of its standard error."""
    _, jobs = template(CI_YML)
    script = next((str(s["run"]) for s in job_steps(jobs.get("groups", {})) if s.get("id") == "read"), "")
    out = root / "github_output"
    out.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")} | {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_OUTPUT": str(out),
    }
    p = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT,
    )
    error = p.stderr.strip().splitlines()
    return p.returncode, out.read_text().splitlines(), error[-1] if error else ""


# A row of the output `test` or `other`: its version, its system, its group and its test arguments.
type Row = tuple[str, str, str, str]


def groups_rows(root: pathlib.Path, event: str, ref: str) -> tuple[int, dict[str, object], str]:
    """`groups_output`, with each output by its name: `list` as its value, and `test` and `other` as
    their rows, sorted, each a Row, or its text where its keys are not ROW_KEYS or its `arch` is not
    `default`."""
    code, lines, error = groups_output(root, event, ref)
    outputs: dict[str, object] = {}
    for line in lines:
        name, _, text = line.partition("=")
        value = jsonio.loads(text, where=f"the output {name}", top=object)
        if name in {"test", "other"} and isinstance(value, list):
            rows: list[Row | str] = []
            for r in value:
                row = r if isinstance(r, dict) else {}
                fields = [str(row.get(k)) for k in ("version", "os", "group", "args")]
                good = sorted(row) == ROW_KEYS and row.get("arch") == "default"
                rows.append((fields[0], fields[1], fields[2], fields[3]) if good else repr(r))
            outputs[name] = sorted(rows, key=str)
        else:
            outputs[name] = value
    return code, outputs, error


def per_group(entries: list[tuple[str, str]], groups: list[str]) -> list[Row]:
    """The rows of one job per group on each of `entries`, (version, os), with the group as the
    test argument."""
    return [(version, system, g, g) for version, system in entries for g in groups]


def one_job(entries: list[tuple[str, str]], args: str = "") -> list[Row]:
    """The rows of one job with no group on each of `entries`, (version, os), with the test
    arguments `args`."""
    return [(version, system, "", args) for version, system in entries]


# A group file with three groups, and the group files whose `split` or `once` both CI.yml's `groups`
# job and `protection.required_checks` refuse: a label, the file, and the text after its path.
THREE_GROUPS = 'groups = ["core", "slow", "long"]\n'
ONCE_REFUSAL = "`once` is not a list of distinct groups of `groups` other than core"
REFUSED_PLANS = [
    ('split = "false"', THREE_GROUPS + 'split = "false"\n', "`split` is not true or false"),
    ('once = ["core"]', THREE_GROUPS + 'once = ["core"]\n', ONCE_REFUSAL),
    ('once = ["huge"]', THREE_GROUPS + 'once = ["huge"]\n', ONCE_REFUSAL),
    ('once = ["long", "long"]', THREE_GROUPS + 'once = ["long", "long"]\n', ONCE_REFUSAL),
    ('once = "long"', THREE_GROUPS + 'once = "long"\n', ONCE_REFUSAL),
    ("once = [1]", THREE_GROUPS + "once = [1]\n", ONCE_REFUSAL),
    ('once = ""', THREE_GROUPS + 'once = ""\n', ONCE_REFUSAL),
    ("once = 3", THREE_GROUPS + "once = 3\n", ONCE_REFUSAL),
    (
        "a once that holds every group",
        'groups = ["slow", "long"]\nsplit = false\nonce = ["slow", "long"]\n',
        "`once` holds every group of `groups`",
    ),
]


def groups_cases(check: Check, tmp: pathlib.Path) -> None:
    """The `groups` job of CI.yml for each event: the groups of the downgrade job, and the rows of
    `test` and `test-other`. A pull request and a push to a branch run macOS and Windows on `1`, and
    every other event on `min` and `1`; `split = false` runs all groups of an entry in one job; on a
    pull request and a push to a branch, the groups of `once` run on Ubuntu with `1` alone. A group
    file that it refuses writes nothing, and its error names the key."""
    pr, main, tag = (
        ("pull_request", "refs/pull/1/merge"),
        ("push", "refs/heads/main"),
        ("push", "refs/tags/v1"),
    )
    weekly, hand = ("schedule", "refs/heads/main"), ("workflow_dispatch", "refs/heads/main")
    merge = ("merge_group", "refs/heads/gh-readonly-queue/main/x")
    two, three = ["core", "long"], ["core", "slow", "long"]
    # With `split = false` a row names every group it runs, so no row passes an empty ARGS, which
    # adds the device groups of the platform line of `runtests.jl`.
    all3 = " ".join(three)
    groups_two, groups_three = 'groups = ["core", "long"]\n', THREE_GROUPS
    once = groups_three + 'once = ["long"]\n'
    split = groups_three + "split = false\n"
    both = groups_three + 'split = false\nonce = ["slow", "long"]\n'
    ubuntu, full = [UBUNTU_MIN, UBUNTU_1], OTHER_1 + OTHER_MIN

    def want(listed: list[str], test: list[Row], other: list[Row]) -> dict[str, object]:
        return {"list": listed, "test": sorted(test, key=str), "other": sorted(other, key=str)}

    # the rows of a pull request, which a push to a branch writes too
    short = (
        (
            "with the groups core and long",
            groups_two,
            want(two, per_group(ubuntu, two), per_group(OTHER_1, two)),
        ),
        (
            'with once = ["long"]',
            once,
            want(
                three,
                per_group([UBUNTU_MIN], ["core", "slow"]) + per_group([UBUNTU_1], three),
                per_group(OTHER_1, ["core", "slow"]),
            ),
        ),
    )
    for label, (event, ref), text, expected in (
        ("without a group file", pr, None, want([""], one_job(ubuntu), one_job(OTHER_1))),
        *((label, on, text, expected) for on in (pr, main) for label, text, expected in short),
        (
            "without a group file",
            ("push", "refs/heads/master"),
            None,
            want([""], one_job(ubuntu), one_job(OTHER_1)),
        ),
        ("without a group file", tag, None, want([""], one_job(ubuntu), one_job(full))),
        (
            "with the groups core and long",
            weekly,
            groups_two,
            want(two, per_group(ubuntu, two), per_group(full, two)),
        ),
        ("without a group file", hand, None, want([""], one_job(ubuntu), one_job(full))),
        ("without a group file", merge, None, want([""], one_job(ubuntu), one_job(full))),
        ('with once = ["long"]', tag, once, want(three, per_group(ubuntu, three), per_group(full, three))),
        ('with once = ["long"]', weekly, once, want(three, per_group(ubuntu, three), per_group(full, three))),
        (
            "with once = []",
            pr,
            groups_three + "once = []\n",
            want(three, per_group(ubuntu, three), per_group(OTHER_1, three)),
        ),
        ("with split = false", pr, split, want([""], one_job(ubuntu, all3), one_job(OTHER_1, all3))),
        ("with split = false", weekly, split, want([""], one_job(ubuntu, all3), one_job(full, all3))),
        (
            "with split = true",
            pr,
            groups_two + "split = true\n",
            want(two, per_group(ubuntu, two), per_group(OTHER_1, two)),
        ),
        (
            'with split = false and once = ["slow", "long"]',
            pr,
            both,
            want([""], one_job([UBUNTU_MIN], "core") + one_job([UBUNTU_1], all3), one_job(OTHER_1, "core")),
        ),
        (
            'with split = false and once = ["slow", "long"]',
            hand,
            both,
            want([""], one_job(ubuntu, all3), one_job(full, all3)),
        ),
        (
            'with split = false and once = ["long"]',
            pr,
            split + 'once = ["long"]\n',
            want(
                [""],
                one_job([UBUNTU_MIN], "core slow") + one_job([UBUNTU_1], all3),
                one_job(OTHER_1, "core slow"),
            ),
        ),
    ):
        got = groups_rows(scratch_repository(tmp, text), event, ref)
        check(
            got == (0, expected, ""),
            f"the groups job for {event} on {ref} {label} writes {expected} -> {got}",
        )
    names = "`groups` is not a list of distinct group names"
    for label, text, expected in (
        ("a group twice", 'groups = ["core", "core"]\n', f"{names}: ['core', 'core']"),
        *REFUSED_PLANS,
        ('groups = "core" beside a once', 'groups = "core"\nonce = ["long"]\n', f"{names}: 'core'"),
    ):
        got = groups_output(scratch_repository(tmp, text), *pr)
        check(
            got[0] != 0 and not got[1] and got[2] == f"test/ci-groups.toml: {expected}",
            f"the groups job refuses a group file with {label}, writes nothing, and names the key -> {got}",
        )


def downgrade_cases(check: Check) -> None:
    """Downgrade.yml: its name, its triggers, its concurrency group, its `groups` job equal to the
    one of CI.yml, and its downgrade job."""
    data, jobs = template(DOWNGRADE_YML)
    ci_data, ci_jobs = template(CI_YML)
    on = triggers(data)
    check(
        data.get("name") == "Downgrade"
        and on
        == {
            "push": {"branches": ["main", "master"], "tags": ["*"], "paths": PROJECTS},
            "pull_request": {"paths": PROJECTS},
            "workflow_dispatch": None,
            "schedule": WEEKLY,
        },
        f"Downgrade.yml runs on a pull request and a push to main or master that change a "
        f"Project.toml of the package or of its tests, on a tag, by hand and weekly -> {on}",
    )
    check(
        data.get("concurrency") == ci_data.get("concurrency")
        and sorted(jobs) == ["downgrade", "groups"]
        and jobs.get("groups") == ci_jobs.get("groups"),
        f"Downgrade.yml has the concurrency group of CI.yml, and its groups job is the one of CI.yml "
        f"-> {data.get('concurrency')}, {sorted(jobs)}",
    )
    job = jobs.get("downgrade", {})
    setup = given_to(job, "julia-actions/setup-julia")
    compat = given_to(job, "julia-actions/julia-downgrade-compat")
    runtest = given_to(job, "julia-actions/julia-runtest")
    check(
        job.get("needs") == "groups"
        and job.get("continue-on-error") is True
        and matrix(job) == {"group": GROUPS_LIST}
        and setup == {"version": "min"}
        and compat
        == {"mode": "forcedeps", "julia_version": "min", "projects": "., test", "skip": DOWNGRADE_SKIP}
        and runtest
        == {
            "check_bounds": "auto",
            "allow_reresolve": False,
            "force_latest_compatible_version": False,
            "test_args": "${{ matrix.group }}",
        },
        f"the downgrade job runs each group at the lower bounds of both projects, as information -> "
        f"{ {k: job.get(k) for k in ('needs', 'continue-on-error')} }, {matrix(job)}, {setup}, {compat}, "
        f"{runtest}",
    )


def lint_cases(check: Check) -> None:
    """actionlint on CI.yml without shellcheck, whose doctest step has a finding of its own, and on
    Downgrade.yml with it."""
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        print("skip  githooks: no actionlint on the PATH; CI.yml and Downgrade.yml are not linted")
        return
    for path, flags in ((CI_YML, ["-shellcheck="]), (DOWNGRADE_YML, [])):
        p = run([actionlint, *flags, str(path)])
        check(
            p.returncode == 0,
            f"actionlint {' '.join(flags)} passes on {path.name} -> {p.returncode} {p.stdout.strip()[-300:]}",
        )


def julia_script(
    julia: str, *args: str, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """dependents.jl with `args`, in a fresh julia with `env` over the environment, without the
    variables of GitHub Actions that it writes to."""
    base = {k: v for k, v in os.environ.items() if k not in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")}
    return run([julia, "--startup-file=no", str(DEPENDENTS_JL), *args], env=base | dict(env or {}))


def script_cases(check: Check, tmp: pathlib.Path, julia: str) -> None:
    """dependents.jl's `excluded`, `row` and `list` on fixture files."""
    pair = tmp / "pair"
    for version, compat, want, label in (
        ("0.15.3", '"0.15"', "false", "a head inside the [compat] entry"),
        ("0.16.0", '"0.15.0"', "true", "a head outside the [compat] entry"),
        ("0.16.0", '"0.14, 0.16"', "false", "a head inside one of two specifiers"),
        ("0.15.0", '"0.14, 0.16"', "true", "a head outside both of two specifiers"),
        ("0.16.0", None, "false", "no [compat] entry for the base"),
    ):
        shutil.rmtree(pair, ignore_errors=True)
        (pair / "base").mkdir(parents=True)
        (pair / "dep").mkdir()
        (pair / "base" / "Project.toml").write_text(
            f'name = "Base"\nuuid = "{BASE_UUID}"\nversion = "{version}"\n'
        )
        entry = "" if compat is None else f"\n[compat]\nBase = {compat}\n"
        (pair / "dep" / "Project.toml").write_text(f'name = "Dep"\n\n[deps]\nBase = "{BASE_UUID}"\n{entry}')
        output = pair / "output"
        p = julia_script(
            julia, "excluded", str(pair / "base"), str(pair / "dep"), env={"GITHUB_OUTPUT": str(output)}
        )
        lines = p.stdout.splitlines()
        written = output.read_text() if output.is_file() else ""
        check(
            p.returncode == 0 and lines[:1] == [f"excluded={want}"] and written == f"excluded={want}\n",
            f"excluded: {label} ({version} against {compat}) gives excluded={want} -> {p.returncode}, "
            f"{lines}, {written!r} {p.stderr.strip()[-200:]}",
        )
    good_base = f'name = "Base"\nuuid = "{BASE_UUID}"\nversion = "0.15.0"\n'
    good_dep = f'name = "Dep"\n\n[deps]\nBase = "{BASE_UUID}"\n'
    for label, base_text, dep_text, culprit in (
        ("a dependent's Project.toml that is not TOML", good_base, "name = \n", "dep"),
        ("a base Project.toml that is not TOML", "version = \n", good_dep, "base"),
        ("a base version that is no version number", good_base.replace("0.15.0", "x.y"), good_dep, "base"),
        (
            "a [compat] entry that is no version specifier",
            good_base,
            good_dep + '\n[compat]\nBase = "not a spec"\n',
            "dep",
        ),
    ):
        (pair / "base" / "Project.toml").write_text(base_text)
        (pair / "dep" / "Project.toml").write_text(dep_text)
        p = julia_script(julia, "excluded", str(pair / "base"), str(pair / "dep"))
        check(
            p.returncode == REFUSED
            and str(pair / culprit / "Project.toml") in p.stderr
            and len(p.stderr.strip().splitlines()) == 1
            and not p.stdout.strip(),
            f"excluded refuses {label} with one line that names it -> {p.returncode}, "
            f"{p.stderr.strip()[-300:]!r}",
        )
    both = "inconclusive: the setup failed against the head and the default branch"
    default = "inconclusive: the setup failed against the default branch"
    # excluded, head setup, head test, main setup, main test; "" and "skipped" are a step that did
    # not run, as GitHub reports it.
    for outcomes, want, status in (
        (("true", "", "", "", ""), "excluded", 0),
        (("true", "success", "failure", "failure", "skipped"), "excluded", 0),
        (("false", "success", "success", "", ""), "green", 0),
        (("false", "success", "success", "skipped", "skipped"), "green", 0),
        (("false", "failure", "skipped", "success", "success"), "regression", 1),
        (("false", "failure", "", "success", "failure"), "regression", 1),
        (("false", "success", "failure", "success", "success"), "regression", 1),
        (("false", "success", "failure", "success", "failure"), "known red", 0),
        (("false", "failure", "skipped", "failure", "skipped"), both, 1),
        (("false", "failure", "", "failure", ""), both, 1),
        (("false", "success", "failure", "failure", "skipped"), default, 1),
        # A cancelled step, as after the job's timeout: inconclusive, naming the step; an excluded
        # dependent stays excluded.
        (("true", "cancelled", "", "", ""), "excluded", 0),
        (("false", "cancelled", "", "", ""), "inconclusive: the setup against the head was cancelled", 1),
        (
            ("false", "cancelled", "skipped", "skipped", "skipped"),
            "inconclusive: the setup against the head was cancelled",
            1,
        ),
        (
            ("false", "success", "cancelled", "", ""),
            "inconclusive: the test against the head was cancelled",
            1,
        ),
        (
            ("false", "failure", "skipped", "cancelled", "skipped"),
            "inconclusive: the setup against the default branch was cancelled",
            1,
        ),
        (
            ("false", "success", "failure", "cancelled", ""),
            "inconclusive: the setup against the default branch was cancelled",
            1,
        ),
        (
            ("false", "success", "failure", "success", "cancelled"),
            "inconclusive: the test against the default branch was cancelled",
            1,
        ),
    ):
        summary = tmp / f"summary-{'-'.join(o or '0' for o in outcomes)}"
        p = julia_script(julia, "row", "Dep", *outcomes, env={"GITHUB_STEP_SUMMARY": str(summary)})
        text = summary.read_text() if summary.is_file() else ""
        check(
            p.returncode == status
            and p.stdout.splitlines() == [f"| Dep | {want} |"]
            and text == f"| dependent | result |\n|:--|:--|\n| Dep | {want} |\n",
            f"row: excluded, head setup, head test, main setup, main test {outcomes} is {want!r}, "
            f"exit {status} -> {p.returncode}, {p.stdout.strip()!r}, {text!r} {p.stderr.strip()[-200:]}",
        )
    for outcomes, label in (
        (("false", "neutral", "", "", ""), "a head setup outcome that GitHub does not report"),
        (("", "", "", "", ""), "an empty excluded, as after a failed compat step"),
        (("yes", "success", "success", "", ""), "an excluded that is neither true nor false"),
        (("false", "success", "failure", "failure", "success"), "a main test after a failed main setup"),
        (("false", "success", "failure", "success", "skipped"), "a main test skipped after its setup"),
        (("false", "success", "success", "success", "success"), "a default-branch run after a green head"),
        (("false", "failure", "success", "success", "success"), "a head test after a failed head setup"),
        (("false", "cancelled", "failure", "success", "success"), "a head test after a cancelled setup"),
        (("false", "success", "cancelled", "success", ""), "a main setup after a cancelled head test"),
        (("false", "success", "success", "success", "cancelled"), "a main test cancelled after a green head"),
    ):
        p = julia_script(julia, "row", "Dep", *outcomes)
        check(
            p.returncode == REFUSED and "Dep" in p.stderr and not p.stdout.strip(),
            f"row: {label} {outcomes} exits 2 -> {p.returncode}, {p.stdout.strip()!r}, "
            f"{p.stderr.strip()[-200:]!r}",
        )
    p = julia_script(julia, "row", "Dep", "false", "failure", "success")
    check(
        p.returncode == REFUSED and "usage" in p.stderr and not p.stdout.strip(),
        f"row with a head and a main outcome alone exits 2 with the usage -> {p.returncode}, "
        f"{p.stderr.strip()[-200:]!r}",
    )
    listing = tmp / "dependents.toml"
    listing.write_text(EXPECTED)
    output = tmp / "list-output"
    p = julia_script(julia, "list", str(listing), env={"GITHUB_OUTPUT": str(output)})
    want = (
        '[{"name":"Alpha","repository":"example-org/Alpha.jl"},'
        '{"name":"Beta","repository":"example-org/Beta.jl"}]'
    )
    check(
        p.returncode == 0 and p.stdout.strip() == want and output.read_text() == f"dependents={want}\n",
        f"list gives the dependents as a JSON array for the matrix -> {p.returncode}, {p.stdout.strip()!r}",
    )
    p = julia_script(julia, "list", str(tmp / "absent.toml"))
    check(
        p.returncode == REFUSED and "harness dependents --apply" in p.stderr,
        f"list on a missing file exits 2 and names harness dependents --apply -> {p.returncode}, "
        f"{p.stderr.strip()[-200:]!r}",
    )
    listing.write_text("[[dependent]\n")
    p = julia_script(julia, "list", str(listing))
    check(
        p.returncode == REFUSED
        and str(listing) in p.stderr
        and len(p.stderr.strip().splitlines()) == 1
        and not p.stdout.strip(),
        f"list refuses a file that is not TOML with one line that names it -> {p.returncode}, "
        f"{p.stderr.strip()[-300:]!r}",
    )
    for label, entry in (
        ("a repository with no owner", 'name = "Alpha"\nrepository = "Alpha.jl"\n'),
        ("a name with a quote", 'name = "Al\\"pha"\nrepository = "example-org/Alpha.jl"\n'),
    ):
        listing.write_text(f"[[dependent]]\n{entry}")
        p = julia_script(julia, "list", str(listing))
        check(
            p.returncode == REFUSED and not p.stdout.strip(),
            f"list refuses {label}, which the JSON of the matrix cannot hold -> {p.returncode}, "
            f"{p.stderr.strip()[-200:]!r}",
        )


def format_case(check: Check, julia: str) -> None:
    """dependents.jl in the SciML style of the bases' `.JuliaFormatter.toml`."""
    code = (
        "pushfirst!(LOAD_PATH, ARGS[1]); using JuliaFormatter; "
        "exit(format_file(ARGS[2], SciMLStyle(); overwrite = false) ? 0 : 1)"
    )
    p = run([julia, "--startup-file=no", "-e", code, str(install.JULIA_ENV), str(DEPENDENTS_JL)])
    check(
        p.returncode == 0,
        f"dependents.jl is in the SciML style -> {p.returncode} {p.stderr.strip()[-300:]}",
    )


def verify(
    julia: str, root: pathlib.Path, profile: pathlib.Path, *, quiet: bool = True
) -> subprocess.CompletedProcess[str]:
    """verify-workflows.jl on the research root `root` with the profile `profile`, with `--quiet`
    unless `quiet` is False."""
    env = dict(os.environ) | GIT | {"RESEARCH_ROOT": str(root), "RESEARCH_HARNESS_PROFILE": str(profile)}
    return run([julia, "--startup-file=no", str(VERIFY), *(["--quiet"] if quiet else [])], env=env)


def renamed_other() -> str:
    """CI.yml with the name of its test-other job changed, and nothing else."""
    text = CI_YML.read_text()
    at = text.find("\n    test-other:\n")
    if at < 0:
        return text
    name = text.find("        name: Julia ", at)
    return text[:name] + text[name:].replace("name: Julia ", "name: Other Julia ", 1)


def printed_checks(out: str, heading_start: str = "Required status checks (") -> list[str]:
    """A list of required checks that verify-workflows.jl prints: the indented lines below the
    heading that starts with `heading_start`, up to the first blank line. The default heading is
    the one of a repository without test/ci-groups.toml."""
    lines = out.splitlines()
    heading = next((i for i, line in enumerate(lines) if line.startswith(heading_start)), None)
    if heading is None:
        return []
    found: list[str] = []
    for line in lines[heading + 1 :]:
        if not line.strip():
            break
        found.append(line.strip())
    return found


def verify_cases(check: Check, tmp: pathlib.Path, julia: str) -> None:
    """verify-workflows.jl on a fixture root that `harness workflows --apply` and `harness
    dependents --apply` set up, clean and with each finding."""
    root = tmp / "Research"
    repos = fixture(root)
    listed = profile_file(tmp / "listed.toml", '["Base"]')
    quiet(githooks.cmd_workflows, listed, apply=True)
    quiet(githooks.cmd_dependents, listed, apply=True)
    p = verify(julia, root, listed)
    check(
        p.returncode == 0 and "all canonical" in p.stdout,
        f"verify-workflows passes on a clean fixture with a listed base -> {p.returncode}, "
        f"{p.stdout.strip()[-300:]!r} {p.stderr.strip()[-300:]}",
    )
    p = verify(julia, root, listed, quiet=False)
    printed = printed_checks(p.stdout)
    check(
        p.returncode == 0 and sorted(printed) == sorted(protection.REQUIRED_CHECKS),
        f"verify-workflows prints the required checks of harness ci-protection -> {p.returncode}, {printed}",
    )
    grouped = repos["Other"]
    runtests = (
        "using SafeTestsets\n"
        'const GROUPS = isempty(ARGS) ? ["core", "slow"] : ARGS\n'
        'if "core" in GROUPS\n    @safetestset "A" include("a.jl")\nend\n'
        'if "slow" in GROUPS\n    @safetestset "B" include("b.jl")\nend\n'
    )
    with (
        changed_file(grouped / "test" / "ci-groups.toml", 'groups = ["core", "slow"]\n'),
        changed_file(grouped / "test" / "runtests.jl", runtests),
    ):
        p = verify(julia, root, listed, quiet=False)
        expected = protection.required_checks(grouped)
    printed = printed_checks(p.stdout, "Required status checks of Other,")
    check(
        p.returncode == 0 and bool(printed) and sorted(printed) == sorted(expected),
        f"verify-workflows prints the required checks of harness ci-protection for a repository with "
        f"the groups core and slow -> {p.returncode}, {printed}",
    )
    for label, keys in (
        ("split = false", "split = false\n"),
        ('once = ["slow"]', 'once = ["slow"]\n'),
        ('split = false and once = ["slow"]', 'split = false\nonce = ["slow"]\n'),
    ):
        with (
            changed_file(grouped / "test" / "ci-groups.toml", f'groups = ["core", "slow"]\n{keys}'),
            changed_file(grouped / "test" / "runtests.jl", runtests),
        ):
            p = verify(julia, root, listed, quiet=False)
            expected = protection.required_checks(grouped)
        printed = printed_checks(p.stdout, "Required status checks of Other,")
        check(
            p.returncode == 0 and bool(printed) and sorted(printed) == sorted(expected),
            f"verify-workflows prints the required checks of harness ci-protection for a repository with "
            f"{label} -> {p.returncode}, {printed}, expected {expected}",
        )
    with (
        changed_file(grouped / "test" / "ci-groups.toml", 'groups = ["core", "slow"]\nonce = ["core"]\n'),
        changed_file(grouped / "test" / "runtests.jl", runtests),
    ):
        p = verify(julia, root, listed, quiet=False)
    printed = printed_checks(p.stdout, "Required status checks of Other,")
    check(
        p.returncode == 1 and "`once` never holds core" in p.stdout and not printed,
        f'verify-workflows fails check 6 for once = ["core"] and prints no required checks of the '
        f"repository -> {p.returncode}, {printed}",
    )
    workflow = repos["Base"] / ".github" / "workflows" / "Dependents.yml"
    for label, path, text, repo, phrase in (
        (
            "a drifted Downgrade.yml",
            repos["Other"] / ".github" / "workflows" / "Downgrade.yml",
            DOWNGRADE_YML.read_text() + "# drift\n",
            "Other",
            "Downgrade.yml differs",
        ),
        (
            "a CI.yml whose test-other job has another name",
            repos["Other"] / ".github" / "workflows" / "CI.yml",
            renamed_other(),
            "Other",
            "CI.yml test-other job name is",
        ),
        (
            "a CI.yml without a test-other job",
            repos["Other"] / ".github" / "workflows" / "CI.yml",
            CI_YML.read_text().replace("\n    test-other:\n", "\n    test-others:\n"),
            "Other",
            "CI.yml has no `test-other` job",
        ),
        (
            "a drifted Dependents.yml",
            workflow,
            DEPENDENTS_YML.read_text() + "# drift\n",
            "Base",
            "Dependents.yml differs",
        ),
        (
            "a missing dependents.jl",
            repos["Base"] / ".github" / "dependents.jl",
            None,
            "Base",
            "dependents.jl missing",
        ),
        (
            "a Dependents.yml in an unlisted repository",
            repos["Other"] / ".github" / "workflows" / "Dependents.yml",
            DEPENDENTS_YML.read_text(),
            "Other",
            "Dependents.yml is present",
        ),
        (
            "a listed base without dependents.toml",
            repos["Base"] / ".github" / "dependents.toml",
            None,
            "Base",
            "dependents.toml",
        ),
    ):
        with changed_file(path, text):
            p = verify(julia, root, listed)
        lines = p.stdout.splitlines()
        at = lines.index(f"  {repo}") if f"  {repo}" in lines else None
        found = at is not None and any(phrase in line for line in lines[at + 1 : at + 8])
        check(
            p.returncode == 1 and found,
            f"verify-workflows finds {label} in {repo} -> {p.returncode}, "
            f"{[line.strip() for line in lines if phrase in line]}",
        )
    p = verify(julia, root, profile_file(tmp / "lab.toml", '["Base", "Lab"]'))
    check(
        p.returncode == 0 and "all canonical" in p.stdout,
        f"verify-workflows takes no experiment for a base, even when dependents_bases names it -> "
        f"{p.returncode}, {p.stdout.strip()[-300:]!r}",
    )
    bare = tmp / "bare" / "Research"
    fixture(bare)
    none = profile_file(tmp / "none.toml", None)
    with mock.patch.dict(os.environ, RESEARCH_ROOT=str(bare)):
        quiet(githooks.cmd_workflows, none, apply=True)
    p = verify(julia, bare, none)
    check(
        p.returncode == 0 and "all canonical" in p.stdout,
        f"without dependents_bases, verify-workflows passes on the other templates -> {p.returncode}, "
        f"{p.stdout.strip()[-300:]!r}",
    )
    minimal = tmp / "minimal.toml"
    minimal.write_text(profile_module.profile_text())
    p = verify(julia, bare, minimal)
    check(
        p.returncode == 0 and "all canonical" in p.stdout,
        f"verify-workflows reads a profile without docs_exceptions and docs_additions as two empty "
        f"lists -> {p.returncode}, {p.stdout.strip()[-300:]!r} {p.stderr.strip()[-300:]}",
    )


def cases(check: Check) -> None:
    """Every case of the module docstring; each group that builds a research root builds its own,
    with git's configuration and identity those of the sweep."""
    julia = shutil.which("julia")
    with tempfile.TemporaryDirectory(prefix="harness-githooks-") as name:
        tmp = pathlib.Path(name).resolve()
        bodies: list[Callable[[Check, pathlib.Path], None]] = [dependents_cases, workflow_cases]
        for body in bodies:
            d = tmp / body.__name__
            d.mkdir()
            with mock.patch.dict(os.environ, GIT | {"RESEARCH_ROOT": str(d / "Research")}):
                body(check, d)
        origin_cases(check)
        yaml_cases(check)
        checkout_cases(check)
        ci_cases(check)
        (tmp / "groups").mkdir()
        groups_cases(check, tmp / "groups")
        downgrade_cases(check)
        lint_cases(check)
        if julia is None:
            print("skip  githooks: no julia on the PATH; dependents.jl and verify-workflows.jl do not run")
            return
        (tmp / "script").mkdir()
        script_cases(check, tmp / "script", julia)
        if not (install.JULIA_ENV / "Project.toml").is_file():
            print(
                f"skip  githooks: no Julia environment at {install.JULIA_ENV}; "
                "the format of dependents.jl and verify-workflows.jl skipped"
            )
            return
        format_case(check, julia)
        d = tmp / "verify"
        d.mkdir()
        with mock.patch.dict(os.environ, GIT | {"RESEARCH_ROOT": str(d / "Research")}):
            verify_cases(check, d, julia)
