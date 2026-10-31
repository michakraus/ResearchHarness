"""The contract sweep of `harness test`: every subcommand's dry run, on a fixture `HOME`.

The fixture is one temporary directory: a `HOME` with the dummy profile and model tables
rendered for it, the files the subcommands read below `~/.claude` and `~/.config`, and a research
root, $RESEARCH_ROOT, with one package, one prose repository and the tree instructions. For each
subcommand of `SUBCOMMANDS`:

  * with its preconditions met, the dry run exits 0 or 1, prints no traceback, and changes no
    file below the fixture — a hash of every file, `.git/` excluded, before and after;
  * with each precondition of `PRECONDITIONS` removed alone, it exits 2 with one line on stderr
    and no traceback.

`settings twins` gives each of the two messages of `read_settings` once: with no settings file,
and with one of mode 000. A settings file that is not JSON, not UTF-8, JSON but not an object,
nested deeper than the parser reads, or an object whose `permissions` is a list makes each
subcommand of `settings` that reads it exit 2 with one line that names it; so does such a
`~/.claude.json`, or one whose `projects` is a list, for `trust`.

For each subcommand of `APPLY`, `--apply` and then the dry run again: the second run exits 0.

A subcommand's run that takes more than `TIMEOUT` seconds exits `timeout`, a wrong case; one case
runs the runner on a child that outlives a timeout of 1 s and passes the result through each check
of the sweep: `dry_run_ok`, `refused_ok` and `applied_ok`.

Not swept: `format` runs Julia over the tree, `ci-protection` needs `gh` with a login,
`skill-triggers` runs its dry run and its `--apply` in its own cases, and `mutate` needs a SPEC
and runs `harness test`.
`install --apply` instantiates a Julia environment, `clone --apply` clones and `repos push --apply`
pushes. `setup` installs packages; its own cases run its plan with fake programs. `update`
fetches the harness checkout itself; its own cases run it on a scratch remote.
"""

import dataclasses
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

from . import REPO
from .profile import DUMMY

HARNESS = [sys.executable, str(REPO / "bin" / "harness")]
PROPOSAL = str(REPO / "settings" / "settings.proposal.json")

# (subcommand, its arguments); the argument `{live}` is the fixture's ~/.claude/settings.json, and
# `{kit}` its chezmoi source ~/dotfiles, an empty directory.
SUBCOMMANDS = [
    ("install", ["install"]),
    ("permissions", ["permissions"]),
    ("settings surface", ["settings", "surface"]),
    ("settings compare", ["settings", "compare", "{live}", PROPOSAL]),
    ("settings selftest", ["settings", "selftest"]),
    ("settings twins", ["settings", "twins"]),
    ("githooks", ["githooks"]),
    ("wiki-lint-hook", ["wiki-lint-hook"]),
    ("wiki-lint", ["wiki-lint", "Knowledge"]),
    ("workflows", ["workflows"]),
    ("clone", ["clone"]),
    ("repos status", ["repos", "status", "--no-prs"]),
    ("repos pull", ["repos", "pull"]),
    ("repos push", ["repos", "push"]),
    ("repos sync", ["repos", "sync"]),
    ("trust", ["trust"]),
    ("render", ["render", PROPOSAL]),
    ("get", ["get", "home"]),
    ("leaks", ["leaks"]),
    ("dotfiles-kit", ["dotfiles-kit", "{kit}"]),
]

# (precondition, its path below the fixture HOME, the subcommands that need it). The profile is
# a precondition of every subcommand that reads it; `settings compare` reads it to render the
# proposal.
PRECONDITIONS = [
    (
        "the profile file",
        ".config/research-harness/profile.toml",
        ["install", "settings compare", "workflows", "render", "get", "leaks"],
    ),
    ("the model tables", ".config/research-harness/models.toml", ["install"]),
    ("~/.config/opencode", ".config/opencode", ["install"]),
    ("the tree instructions", "Research/Environment/Agents", ["install"]),
    ("~/.claude.json", ".claude.json", ["trust"]),
    ("~/.claude/settings.json", ".claude/settings.json", ["settings surface", "settings twins"]),
    ("a repository_roots entry", "Research/Experiments", ["leaks"]),
    ("the repository table", ".config/research-harness/repositories.toml", ["clone"]),
    ("the chezmoi source", "dotfiles", ["dotfiles-kit"]),
]

APPLY = ["githooks", "wiki-lint-hook", "workflows", "trust"]

# The variables that would point a subcommand past the fixture.
UNSET = [
    "RESEARCH_HARNESS_PROFILE",
    "RESEARCH_HARNESS_MODELS",
    "RESEARCH_HARNESS_JULIA",
    "RESEARCH_HARNESS_REPOSITORIES",
    "OPENCODE_CONFIG_DIR",
    "PI_CODING_AGENT_DIR",
    "FMT_OUT",
]


# No user or system git configuration, and an identity: a CI runner has none. These replace every
# `GIT_*` variable of the caller: a `GIT_DIR`, as git exports it to a hook, would send the
# fixture's git commands to the caller's repository.
GIT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "sweep",
    "GIT_AUTHOR_EMAIL": "sweep@example.org",
    "GIT_COMMITTER_NAME": "sweep",
    "GIT_COMMITTER_EMAIL": "sweep@example.org",
}


def make_fixture(home: pathlib.Path, env: dict[str, str]) -> None:
    """The fixture below `home`; the dummy profile and model tables copied as they are, so that
    each `~` of the profile is `home`."""
    research = home / "Research"
    for directory in (
        ".claude/agents",
        ".claude/skills",
        ".config/opencode",
        ".config/research-harness",
        "dotfiles",
        "Research/Packages/Example",
        "Research/Experiments",
        "Research/Knowledge",
        "Research/Environment/Agents",
    ):
        (home / directory).mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{\n  "model": "fixture"\n}\n')
    (home / ".claude.json").write_text("{}\n")
    for name, source in (
        ("profile.toml", DUMMY),
        ("models.toml", REPO / "examples" / "models.toml"),
        ("providers.toml", REPO / "examples" / "providers.toml"),
    ):
        (home / ".config" / "research-harness" / name).write_bytes(source.read_bytes())
    # One repository to clone, at a URL that the dry run never reaches.
    (home / ".config" / "research-harness" / "repositories.toml").write_text(
        '[packages]\nOther = "https://example.org/Other.jl.git"\n'
    )
    package = research / "Packages" / "Example"
    (package / "Project.toml").write_text('name = "Example"\n')
    git = shutil.which("git") or "git"
    for repository, files in ((package, ["Project.toml"]), (research / "Knowledge", [])):
        commands = [["init", "-q", "-b", "main"]]
        if files:
            commands += [["add", "--", *files], ["commit", "-q", "-m", "fixture"]]
        for command in commands:
            subprocess.run(
                [git, "-C", str(repository), *command], env=env, check=True, capture_output=True, timeout=60
            )


def digest(root):
    """A hash of every file, link and directory below `root`, `.git/` excluded."""
    h = hashlib.sha256()
    for path, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(dirs + files):
            p = os.path.join(path, name)
            h.update(p.encode() + b"\0")
            if os.path.islink(p):
                h.update(os.readlink(p).encode())
            elif os.path.isfile(p):
                with open(p, "rb") as f:
                    h.update(f.read())
            h.update(b"\0")
    return h.hexdigest()


# The seconds that one subcommand's run of the sweep may take.
TIMEOUT = 120


@dataclasses.dataclass(frozen=True)
class Run:
    """The result of `run`, with the fields of `subprocess.CompletedProcess` that the checks read;
    `returncode` is the text `timeout` for a run that outlives its timeout."""

    args: list[str]
    returncode: int | str
    stdout: str
    stderr: str


def run(command: list[str], env: dict[str, str], cwd: str | pathlib.Path, timeout: float = TIMEOUT) -> Run:
    """One run of `command`; a run that outlives `timeout` exits `timeout`, which no check of the
    sweep accepts."""
    try:
        p = subprocess.run(
            command, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return Run(command, "timeout", "", "")
    return Run(command, p.returncode, p.stdout, p.stderr)


# The checks of the sweep, each on the result of `run`.


def dry_run_ok(p, changed):
    """A dry run: exit 0 or 1, no traceback, and no file below the fixture `changed`."""
    return p.returncode in (0, 1) and "Traceback" not in p.stdout + p.stderr and not changed


def refused_ok(p):
    """A refusal: exit 2 with one line on stderr and no traceback."""
    return (
        p.returncode == 2
        and len(p.stderr.strip().splitlines()) == 1
        and "Traceback" not in p.stdout + p.stderr
    )


def applied_ok(applied, again):
    """An --apply and the dry run after it: both exit 0."""
    return applied.returncode == 0 and again.returncode == 0


def selftest():
    """The sweep's cases: (number of cases, number wrong)."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  sweep: {label}")

    with tempfile.TemporaryDirectory(prefix="harness-sweep-") as tmp:
        home = pathlib.Path(tmp) / "home"
        env = {k: v for k, v in os.environ.items() if k not in UNSET and not k.startswith("GIT_")}
        env.update(GIT, HOME=str(home), RESEARCH_ROOT=str(home / "Research"))
        make_fixture(home, env)
        placeholders = {"{live}": str(home / ".claude" / "settings.json"), "{kit}": str(home / "dotfiles")}
        argv = {subcommand: [placeholders.get(a, a) for a in args] for subcommand, args in SUBCOMMANDS}

        def harness(args):
            """One subcommand's run; a subcommand that hangs exits `timeout`, which is a wrong
            case."""
            return run(HARNESS + args, env, tmp)

        # The runner on a child that outlives a timeout of 1 s: the run ends at the timeout, and each
        # check of the sweep counts its result as wrong. The refusal check gets the result with one
        # stderr line, and a run that exits 0 is the other run of the --apply check, so that only the
        # exit status can fail them; with the exit status of a good run, each check passes.
        start = time.monotonic()
        p = run([sys.executable, "-c", "import time; time.sleep(30)"], env, tmp, timeout=1)
        took = time.monotonic() - start

        def like(code, stderr=""):
            return subprocess.CompletedProcess(p.args, code, "", stderr)

        line = "harness: one line\n"
        verdicts = {
            "dry run": dry_run_ok(p, False),
            "refusal": refused_ok(like(p.returncode, line)),
            "--apply": applied_ok(p, like(0)),
            "dry run after --apply": applied_ok(like(0), p),
        }
        controls = [
            dry_run_ok(like(0), False),
            dry_run_ok(like(1), False),
            refused_ok(like(2, line)),
            applied_ok(like(0), like(0)),
        ]
        check(
            took < 15 and not any(verdicts.values()) and all(controls),
            f"a child that outlives the timeout exits {p.returncode!r} after {took:.1f} s, and the sweep's "
            f"checks accept it: {verdicts}, and the exits of good runs: {controls}; the sweep's own timeout "
            f"is {TIMEOUT} s",
        )

        for subcommand, _ in SUBCOMMANDS:
            before = digest(tmp)
            p = harness(argv[subcommand])
            changed = digest(tmp) != before
            traceback = "Traceback" in p.stdout + p.stderr
            check(
                dry_run_ok(p, changed),
                f"{subcommand}: dry run exits {p.returncode}, traceback {traceback}, a file changed {changed}"
                + (f": {p.stderr.strip()[-300:]!r}" if p.returncode not in (0, 1) or traceback else ""),
            )

        for precondition, rel, subcommands in PRECONDITIONS:
            path = home / rel
            aside = path.with_name(path.name + ".removed")
            path.rename(aside)
            try:
                for subcommand in subcommands:
                    p = harness(argv[subcommand])
                    lines = p.stderr.strip().splitlines()
                    check(
                        refused_ok(p),
                        f"{subcommand} without {precondition}: exit {p.returncode}, {len(lines)} stderr line(s)"
                        + (f": {lines[-1]!r}" if lines else ""),
                    )
            finally:
                aside.rename(path)

        # The two messages of `read_settings`: a settings file that is missing, and one that the
        # subcommand cannot read.
        live = home / ".claude" / "settings.json"
        for label, expect in (
            ("missing", f"no settings file at {live}"),
            ("mode 000", f"cannot read {live}: Permission denied"),
        ):
            aside = live.with_name(live.name + ".removed")
            if label == "missing":
                live.rename(aside)
            else:
                live.chmod(0)
            try:
                p = harness(argv["settings twins"])
            finally:
                if label == "missing":
                    aside.rename(live)
                else:
                    live.chmod(0o644)
            check(
                refused_ok(p) and p.stderr == f"harness settings: {expect}\n",
                f"settings twins, settings file {label}: exit {p.returncode}, stderr {p.stderr.strip()[-300:]!r}",
            )

        # A settings file, and ~/.claude.json, that is not JSON, not UTF-8, JSON but not an object,
        # nested deeper than the parser's recursion limit, or an object whose `permissions` or
        # `projects` is not an object: each subcommand that reads it exits 2 with one line that
        # names the file and what it is.
        settings_subcommands = ["settings surface", "settings compare", "settings twins"]
        # Python 3.11 stops at its recursion limit, 3.12 and later at a stack of 16 MB: 400000 levels
        # are past both.
        depth = 400000
        for label, data, reason, files in (
            ("not JSON", b"{ not json\n", "is not JSON", "both"),
            ("not UTF-8", b'{"x": "\xff"}\n', "is not UTF-8", "both"),
            ("JSON but not an object", b"[]\n", "is not a JSON object", "both"),
            (f"an array nested {depth} deep", b"[" * depth + b"]" * depth + b"\n", "nested too deep", "both"),
            (
                f"an object nested {depth} deep",
                b'{"a": ' * depth + b"0" + b"}" * depth + b"\n",
                "nested too deep",
                "both",
            ),
            ("an object whose permissions is a list", b'{"permissions": []}\n', "permissions", "settings"),
            ("an object whose projects is a list", b'{"projects": []}\n', "projects", "trust"),
        ):
            for path, subcommands in (
                (live, settings_subcommands if files != "trust" else []),
                (home / ".claude.json", ["trust"] if files != "settings" else []),
            ):
                if not subcommands:
                    continue
                old = path.read_bytes()
                path.write_bytes(data)
                try:
                    runs = [(subcommand, harness(argv[subcommand])) for subcommand in subcommands]
                finally:
                    path.write_bytes(old)
                for subcommand, p in runs:
                    lines = p.stderr.strip().splitlines()
                    check(
                        refused_ok(p) and str(path) in lines[0] and reason in lines[0],
                        f"{subcommand}, {path.name} {label}: exit {p.returncode}, {len(lines)} stderr line(s)"
                        + (f": {lines[-1][-300:]!r}" if lines else ""),
                    )

        for subcommand in APPLY:
            applied = harness(argv[subcommand] + ["--apply"])
            again = harness(argv[subcommand])
            check(
                applied_ok(applied, again),
                f"{subcommand} --apply exits {applied.returncode}, the dry run after it {again.returncode}"
                + (
                    f": {(applied.stderr + again.stderr).strip()[-300:]!r}"
                    if applied.stderr + again.stderr
                    else ""
                ),
            )
    return total, wrong
