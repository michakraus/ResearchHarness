"""The scratch HOMEs on which the `selftest` of each adapter runs `harness install` end to end, and
the helpers of its cases.
"""

import os
import pathlib
import re
import stat
import subprocess
import sys

from . import REPO
from . import profile as profile_module

# The frontmatter of a rule that the cases write: oh-my-pi's rendering needs a `description`.
RULE_HEAD = '---\npaths: ["**/*.x"]\ndescription: A rule of the scratch tree.\n---\n'


def scratch_profile(path, tree, raw=None):
    """The dummy profile with `tree_agents` set to `tree`, or without the key for None; `raw` is
    the key's TOML value as written, in place of `tree`."""
    line = f"tree_agents = {raw}" if raw is not None else "" if tree is None else f'tree_agents = "{tree}"'
    path.write_text(re.sub(r"(?m)^tree_agents = .*$", line, profile_module.DUMMY.read_text()))
    return path


class Scratch:
    """The scratch HOMEs below `tmp`, and the helpers of the cases on them; `check(ok, label)`
    counts each case."""

    def __init__(self, check, tmp):
        self.check, self.tmp, self.n = check, pathlib.Path(tmp), 0

    def fresh(self, tree_files=(), key=True, raw=None):
        """A scratch HOME, OpenCode and Julia directory, and tree instructions holding `tree_files`;
        `raw` is the value of `tree_agents` as written in the profile."""
        self.n += 1
        base = self.tmp / f"claude{self.n}"
        (base / "home" / ".claude" / "skills").mkdir(parents=True)
        (base / "opencode").mkdir()
        (base / "julia").mkdir()
        (base / "julia" / "Project.toml").write_bytes((REPO / "Project.toml").read_bytes())
        (base / "julia" / "Manifest.toml").touch()
        tree = base / "Agents"
        tree.mkdir()
        for name in tree_files:
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            # A rule carries the `description` without which oh-my-pi's rendering refuses it.
            head = RULE_HEAD if re.fullmatch(r"rules/[^/]+\.md", name) else ""
            (tree / name).write_text(f"{head}{name}: written at {{home}}, which stays as it is\n")
        scratch_profile(base / "profile.toml", tree if key else None, raw)
        return base, base / "home" / ".claude", tree

    @staticmethod
    def env(base):
        """The environment of a process with HOME and the destinations in `base`."""
        return dict(os.environ, HOME=str(base / "home"), OPENCODE_CONFIG_DIR=str(base / "opencode"),
                    RESEARCH_HARNESS_JULIA=str(base / "julia"), PI_CODING_AGENT_DIR=str(base / "omp"))

    @staticmethod
    def run(base, *argv, extra_env=None, models=REPO / "examples" / "models.toml"):
        """`harness install` in a process of its own, with HOME and the destinations in `base`, and
        `base` as the working directory, with the model tables `models`; `extra_env` sets variables
        of its environment, and removes each whose value is None. A run that takes more than 60 s is
        (None, "TIMEOUT")."""
        env = Scratch.env(base)
        for key, value in (extra_env or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        try:
            p = subprocess.run([sys.executable, str(REPO / "bin" / "harness"), "--profile", str(base / "profile.toml"),
                                "--models", str(models), "install", *argv],
                               capture_output=True, text=True, env=env, cwd=base, timeout=60)
        except subprocess.TimeoutExpired:
            return None, "TIMEOUT"
        return p.returncode, p.stdout + p.stderr

    @staticmethod
    def refused(code, text):
        """Exit 2 with a message, no traceback."""
        return code == 2 and "Traceback" not in text

    @staticmethod
    def tail(text):
        return (text.strip().splitlines() or ["no output"])[-1]

    def case(self, ok, label):
        try:
            ok = ok()
        except Exception as e:  # a case that crashes is BAD, and the next case still runs
            ok, label = False, f"{label}; raised {type(e).__name__}: {e}"
        self.check(ok, label)

    @staticmethod
    def mode(path):
        return stat.S_IMODE(path.stat().st_mode)


COUNT_LINE = re.compile(r"^\d+ change\(s\) (made|to make)\.$", re.M)


def restart_cases(check, tmp):
    """The restart lines of `harness install`, one case per row: only the Claude Code layer
    changes, only the OpenCode files, only an OpenCode step, only the oh-my-pi files, only the
    Julia environment, nothing, a refused file, a first --apply, and a dry run with changes
    pending. Each case checks the exact lines after the count line: the RESTART of each adapter
    whose files or steps changed something, in the order of FRONTENDS."""
    from . import frontends

    scratch = Scratch(check, tmp / "restart")
    case, run = scratch.case, scratch.run
    lines = {a.NAME: a.RESTART for a in frontends.load()}

    def after_count(text):
        """The lines after the count line, blank lines dropped; None with no count line."""
        found = list(COUNT_LINE.finditer(text))
        if len(found) != 1:
            return None
        return [l for l in text[found[0].end():].splitlines() if l.strip()]

    def expect(code, text, want, status=0):
        """Exit `status`, and exactly the restart lines of the frontends `want` after the count line."""
        return code == status and after_count(text) == [lines[n] for n in frontends.FRONTENDS if n in want]

    base, claude, _ = scratch.fresh()
    home, opencode, omp = base / "home", base / "opencode", base / "omp"
    code, text = run(base)
    case(lambda: expect(code, text, set(), status=1) and COUNT_LINE.search(text).group(1) == "to make",
         f"a dry run with changes pending prints no restart line: {code}, {after_count(text)}")
    code, text = run(base, "--apply")
    case(lambda: expect(code, text, set(frontends.FRONTENDS)),
         f"a first --apply prints the restart line of every frontend, once each: {code}, {after_count(text)}")
    code, text = run(base, "--apply")
    case(lambda: expect(code, text, set()) and "\n0 change(s) made." in text,
         f"an --apply with no change prints no restart line: {code}, {after_count(text)}")

    (claude / "CLAUDE.md").write_text("an edit of the installed copy\n")
    code, text = run(base, "--apply")
    case(lambda: expect(code, text, {"claude"}) and "\n1 change(s) made." in text,
         f"only the Claude Code layer changes: only its restart line: {code}, {after_count(text)}")

    (opencode / "opencode.jsonc").write_text("{}\n")
    code, text = run(base, "--apply")
    backups = sorted(opencode.glob("opencode.jsonc.bak-*"))
    case(lambda: expect(code, text, {"opencode"}) and "\n1 change(s) made." in text and len(backups) == 1,
         f"only the OpenCode files change, opencode.jsonc with its backup: only its restart line: {code}, "
         f"{after_count(text)}, {len(backups)} backup(s)")

    # A link that an earlier install wrote into ~/.agents/skills/, which the OpenCode step removes.
    links = home / ".agents" / "skills"
    links.mkdir(parents=True, exist_ok=True)
    (links / "old-skill").symlink_to(home / ".claude" / "skills" / "old-skill")
    code, text = run(base, "--apply")
    case(lambda: expect(code, text, {"opencode"}) and "\n1 change(s) made." in text
         and not (links / "old-skill").is_symlink(),
         f"only an OpenCode step changes, an old skill link removed: only its restart line: {code}, "
         f"{after_count(text)}")

    (omp / "AGENTS.md").write_text("an edit of the installed copy\n")
    code, text = run(base, "--apply")
    case(lambda: expect(code, text, {"omp"}) and "\n1 change(s) made." in text,
         f"only the oh-my-pi files change: only its restart line: {code}, {after_count(text)}")

    # The Julia environment belongs to no frontend; a stub `julia` stands in for Pkg.instantiate.
    stub = base / "bin" / "julia"
    stub.parent.mkdir()
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    (base / "julia" / "Project.toml").write_text("# an edit of the installed copy\n")
    code, text = run(base, "--apply", extra_env={"PATH": f"{stub.parent}{os.pathsep}{os.environ.get('PATH', '')}"})
    case(lambda: expect(code, text, set()) and "\n1 change(s) made." in text,
         f"only the Julia environment changes: no restart line: {code}, {after_count(text)}")

    # A refused file does not count: the frontend whose one difference is refused gets no line.
    (opencode / "opencode.jsonc").write_text('{"Authorization": "Bearer a-literal-token"}\n')
    code, text = run(base, "--apply")
    case(lambda: code == 2 and not any(l in text for l in lines.values()) and "\n0 change(s) made." in text,
         f"a refused opencode.jsonc, and nothing else different, prints no restart line: {code}, {after_count(text)}")
