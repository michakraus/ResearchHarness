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
  directory or a symbolic link, or below a `.github` that is a file, is refused in the dry run and
  with `--apply`, and changes nothing. The profile loads the key, and `harness get` prints it.
- `githooks.github_name`: the GitHub `owner/name` of an HTTPS, SSH or `git@host:path` origin, with
  a user, a port, `.git`, a final `/` or the host in capitals; None for another host, a local
  path, and a path of one or three parts.
- `harness workflows`: Dependents.yml and dependents.jl go into the listed base only, byte for
  byte; a dry run names the two files in an unlisted repository and keeps them, and `--apply`
  removes them; a listed name that does not exist and a missing Dependents.yml template are
  refused. Without `dependents_bases`, the subcommand writes only the files of the other templates
  and names neither file.
- githooks/workflows/Dependents.yml: its trigger, concurrency group, permissions, jobs and matrix,
  and the actions of its `uses:` lines; `actionlint` passes on it, where it is on the PATH.
- githooks/workflows/dependents.jl, where `julia` is on the PATH: `excluded` on a head inside the
  dependent's `[compat]` entry, outside it, against an entry with two specifiers, and with no
  entry; `excluded` refuses a base or a dependent Project.toml that is not TOML, a base version
  that is no version number and a `[compat]` entry that is no version specifier; `row` on the four
  rows, with the summary it appends and its exit status, and on two combinations that are none of
  them; `list` on a file of two dependents, on a missing file, on a file that is not TOML and on
  two entries that the JSON of the matrix cannot hold.
- githooks/verify-workflows.jl, where `julia` is on the PATH and the harness's Julia environment
  holds a Project.toml: a clean fixture passes, and a drifted Dependents.yml, a missing
  dependents.jl, a Dependents.yml in an unlisted repository and a listed base without
  dependents.toml each fail with a line that names the repository; an experiment that
  `dependents_bases` names is no base; without `dependents_bases`, the fixture of the other
  templates passes, and so it does with a profile without `docs_exceptions` and `docs_additions`.
"""

import argparse
import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Generator, Mapping
from typing import cast
from unittest import mock

from . import REPO, HarnessError, githooks, install, wikilint
from . import profile as profile_module
from .sweep import GIT

type Check = Callable[[object, str], None]

TIMEOUT = 120  # seconds for one run of julia, actionlint or git
REFUSED = 2  # the exit status of dependents.jl on a refusal
TIMEOUT_MINUTES = 60  # the timeout of a test job of Dependents.yml
DEPENDENTS_JL = REPO / "githooks" / "workflows" / "dependents.jl"
DEPENDENTS_YML = REPO / "githooks" / "workflows" / "Dependents.yml"
VERIFY = REPO / "githooks" / "verify-workflows.jl"
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
    that is not UTF-8, a directory, a symbolic link, and a `.github` that is a file. Each refusal,
    of the dry run and of `--apply`, names the path and changes nothing; a refusal for the second
    of two bases writes the file of neither."""
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
    ):
        if label.startswith("below"):
            github.write_text("not a directory\n")
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
        ("https://gitlab.example.org/o/A.jl.git", None),
        ("https://github.com.example.org/o/A.jl.git", None),
        ("git@gitlab.example.org:o/A.jl.git", None),
        ("file:///srv/git/o/A.jl", None),
        ("/srv/git/o/A.jl", None),
        ("https://github.com/o", None),
        ("https://github.com/o/A.jl/tree", None),
        ("", None),
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
    # YAML 1.1 reads the key `on` as True.
    on = cast("dict[str, object]", data.get(True) or data.get("on") or {})
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
    steps = cast("list[dict[str, object]]", test.get("steps") or [])
    uses = {
        str(s["uses"])
        for job in jobs.values()
        for s in cast("list[dict[str, object]]", job.get("steps") or [])
        if "uses" in s
    }
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
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        print("skip  githooks: no actionlint on the PATH; Dependents.yml is not linted")
        return
    p = run([actionlint, str(DEPENDENTS_YML)])
    check(
        p.returncode == 0, f"actionlint passes on Dependents.yml -> {p.returncode} {p.stdout.strip()[-300:]}"
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
    for excluded, head, main, want, status in (
        ("false", "success", "", "green", 0),
        ("false", "failure", "success", "regression", 1),
        ("false", "failure", "failure", "known red", 0),
        ("true", "", "", "excluded", 0),
    ):
        summary = tmp / f"summary-{want}"
        p = julia_script(julia, "row", "Dep", excluded, head, main, env={"GITHUB_STEP_SUMMARY": str(summary)})
        text = summary.read_text() if summary.is_file() else ""
        check(
            p.returncode == status
            and p.stdout.splitlines() == [f"| Dep | {want} |"]
            and text == f"| dependent | result |\n|:--|:--|\n| Dep | {want} |\n",
            f"row: excluded {excluded}, head {head or '-'}, main {main or '-'} is {want}, exit {status} -> "
            f"{p.returncode}, {p.stdout.strip()!r}, {text!r}",
        )
    for excluded, head, label in (
        ("false", "cancelled", "a head outcome that is neither success nor failure"),
        ("", "", "an empty excluded, as after a failed compat step"),
    ):
        p = julia_script(julia, "row", "Dep", excluded, head, "")
        check(
            p.returncode == REFUSED and "Dep" in p.stderr and not p.stdout.strip(),
            f"row: {label} exits 2 -> {p.returncode}, {p.stderr.strip()[-200:]!r}",
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


def verify(julia: str, root: pathlib.Path, profile: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """verify-workflows.jl --quiet on the research root `root` with the profile `profile`."""
    env = dict(os.environ) | GIT | {"RESEARCH_ROOT": str(root), "RESEARCH_HARNESS_PROFILE": str(profile)}
    return run([julia, "--startup-file=no", str(VERIFY), "--quiet"], env=env)


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
    workflow = repos["Base"] / ".github" / "workflows" / "Dependents.yml"
    for label, path, text, repo, phrase in (
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
        if julia is None:
            print("skip  githooks: no julia on the PATH; dependents.jl and verify-workflows.jl do not run")
            return
        (tmp / "script").mkdir()
        script_cases(check, tmp / "script", julia)
        if not (install.JULIA_ENV / "Project.toml").is_file():
            print(f"skip  githooks: no Julia environment at {install.JULIA_ENV}; verify-workflows.jl skipped")
            return
        d = tmp / "verify"
        d.mkdir()
        with mock.patch.dict(os.environ, GIT | {"RESEARCH_ROOT": str(d / "Research")}):
            verify_cases(check, d, julia)
