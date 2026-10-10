"""The contract sweep of `harness test`: every verb's dry run, on a fixture `HOME`.

The fixture is one temporary directory: a `HOME` with the dummy profile and model tables
rendered for it, the files the verbs read below `~/.claude` and `~/.config`, and a research root,
$RESEARCH_ROOT, with one package, one prose repository and the tree instructions,
`Environment/Agents`. For each verb of `VERBS`:

  * with its preconditions met, the dry run exits 0 or 1, prints no traceback, and changes no
    file below the fixture — a hash of every file, `.git/` excluded, before and after;
  * with each precondition of `PRECONDITIONS` removed alone, it exits 2 with one line on stderr
    and no traceback.

`settings domains` gives each of the two messages of `read_settings` once: with no settings file,
and with one of mode 000.

For each verb of `APPLY`, `--apply` and then the dry run again: the second run exits 0.

Not swept: `format` runs Julia over the tree, `ci-protection` needs `gh` with a login, and
`skill-triggers` runs its dry run and its `--apply` in its own cases.
`install --apply` instantiates a Julia environment, and `push-all --apply` pushes.
"""

import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

from . import REPO
from .profile import DUMMY

HARNESS = [sys.executable, str(REPO / "bin" / "harness")]
PROPOSAL = str(REPO / "settings" / "settings.proposal.json")

# (verb, its arguments); `{live}` is the fixture's ~/.claude/settings.json.
VERBS = [
    ("install", ["install"]),
    ("permissions", ["permissions"]),
    ("settings surface", ["settings", "surface"]),
    ("settings compare", ["settings", "compare", "{live}", PROPOSAL]),
    ("settings selftest", ["settings", "selftest"]),
    ("settings twins", ["settings", "twins"]),
    ("settings domains", ["settings", "domains"]),
    ("githooks", ["githooks"]),
    ("wiki-lint-hook", ["wiki-lint-hook"]),
    ("workflows", ["workflows"]),
    ("push-all", ["push-all"]),
    ("trust", ["trust"]),
    ("render", ["render", PROPOSAL]),
    ("get", ["get", "home"]),
    ("leaks", ["leaks"]),
]

# (precondition, its path below the fixture HOME, the verbs that need it). The profile is a
# precondition of every verb that reads it; `settings compare` reads it to render the proposal.
PRECONDITIONS = [
    ("the profile file", ".config/research-harness/profile.toml",
     ["install", "settings compare", "workflows", "render", "get", "leaks"]),
    ("the model tables", ".config/research-harness/models.toml", ["install"]),
    ("~/.config/opencode", ".config/opencode", ["install"]),
    ("the tree instructions", "Research/Environment/Agents", ["install"]),
    ("~/.claude.json", ".claude.json", ["trust"]),
    ("~/.claude/settings.json", ".claude/settings.json",
     ["settings surface", "settings twins", "settings domains"]),
    ("a repository_roots entry", "Research/Experiments", ["leaks"]),
]

APPLY = ["githooks", "wiki-lint-hook", "workflows", "trust"]

# The variables that would point a verb past the fixture.
UNSET = ["RESEARCH_HARNESS_PROFILE", "RESEARCH_HARNESS_MODELS", "RESEARCH_HARNESS_JULIA",
         "OPENCODE_CONFIG_DIR", "PI_CODING_AGENT_DIR", "FMT_OUT"]


# No user or system git configuration, and an identity: a CI runner has none. These replace every
# `GIT_*` variable of the caller: a `GIT_DIR`, as git exports it to a hook, would send the
# fixture's git commands to the caller's repository.
GIT = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "sweep", "GIT_AUTHOR_EMAIL": "sweep@example.org",
       "GIT_COMMITTER_NAME": "sweep", "GIT_COMMITTER_EMAIL": "sweep@example.org"}


def make_fixture(home, env):
    """The fixture below `home`; the dummy profile and model tables rendered for it."""
    research = home / "Research"
    for directory in (".claude/agents", ".claude/skills", ".config/opencode", ".config/research-harness",
                      "Research/Packages/Example", "Research/Experiments", "Research/Knowledge",
                      "Research/Environment/Agents"):
        (home / directory).mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{\n  "model": "fixture"\n}\n')
    (home / ".claude.json").write_text("{}\n")
    for name, source in (("profile.toml", DUMMY), ("models.toml", REPO / "examples" / "models.toml")):
        text = source.read_text().replace("/home/example", str(home))
        (home / ".config" / "research-harness" / name).write_text(text)
    package = research / "Packages" / "Example"
    (package / "Project.toml").write_text('name = "Example"\n')
    for repository, files in ((package, ["Project.toml"]), (research / "Knowledge", [])):
        commands = [["init", "-q", "-b", "main"]]
        if files:
            commands += [["add", "--", *files], ["commit", "-q", "-m", "fixture"]]
        for command in commands:
            subprocess.run(["git", "-C", str(repository), *command], env=env, check=True, capture_output=True)


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
        argv = {verb: [a.replace("{live}", str(home / ".claude" / "settings.json")) for a in args]
                for verb, args in VERBS}

        def harness(args):
            """One verb's run; a verb that hangs exits `timeout`, which is a wrong case."""
            try:
                return subprocess.run(HARNESS + args, env=env, cwd=tmp, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                return subprocess.CompletedProcess(args, "timeout", "", "")

        for verb, _ in VERBS:
            before = digest(tmp)
            p = harness(argv[verb])
            changed = digest(tmp) != before
            traceback = "Traceback" in p.stdout + p.stderr
            check(p.returncode in (0, 1) and not traceback and not changed,
                  f"{verb}: dry run exits {p.returncode}, traceback {traceback}, a file changed {changed}"
                  + (f": {p.stderr.strip()[-300:]!r}" if p.returncode not in (0, 1) or traceback else ""))

        for precondition, rel, verbs in PRECONDITIONS:
            path = home / rel
            aside = path.with_name(path.name + ".removed")
            path.rename(aside)
            try:
                for verb in verbs:
                    p = harness(argv[verb])
                    lines = p.stderr.strip().splitlines()
                    check(p.returncode == 2 and len(lines) == 1 and "Traceback" not in p.stdout + p.stderr,
                          f"{verb} without {precondition}: exit {p.returncode}, {len(lines)} stderr line(s)"
                          + (f": {lines[-1]!r}" if lines else ""))
            finally:
                aside.rename(path)

        # The two messages of `read_settings`: a settings file that is missing, and one that the
        # verb cannot read.
        live = home / ".claude" / "settings.json"
        for label, expect in (("missing", f"no settings file at {live}"),
                              ("mode 000", f"cannot read {live}: Permission denied")):
            aside = live.with_name(live.name + ".removed")
            if label == "missing":
                live.rename(aside)
            else:
                live.chmod(0)
            try:
                p = harness(argv["settings domains"])
            finally:
                if label == "missing":
                    aside.rename(live)
                else:
                    live.chmod(0o644)
            check(p.returncode == 2 and p.stderr == f"harness settings: {expect}\n",
                  f"settings domains, settings file {label}: exit {p.returncode}, stderr {p.stderr.strip()[-300:]!r}")

        for verb in APPLY:
            applied = harness(argv[verb] + ["--apply"])
            again = harness(argv[verb])
            check(applied.returncode == 0 and again.returncode == 0,
                  f"{verb} --apply exits {applied.returncode}, the dry run after it {again.returncode}"
                  + (f": {(applied.stderr + again.stderr).strip()[-300:]!r}" if applied.stderr + again.stderr else ""))
    return total, wrong
