"""The scratch HOMEs on which the `selftest` of each adapter runs `harness install` end to end, and
the helpers of its cases.
"""

import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys

from . import REPO
from . import profile as profile_module

# The frontmatter of a rule that the cases write: oh-my-pi's rendering needs a `description`.
RULE_HEAD = '---\npaths: ["**/*.x"]\ndescription: A rule of the scratch tree.\n---\n'


def scratch_profile(path, tree, raw=None):
    """The dummy profile with `harness` set to this checkout, so that the `SessionStart` hook reads
    the sources that the stamp names, and `tree_agents` set to `tree`, or without the key for None;
    `raw` is the key's TOML value as written, in place of `tree`."""
    line = f"tree_agents = {raw}" if raw is not None else "" if tree is None else f'tree_agents = "{tree}"'
    text = re.sub(r"(?m)^harness = .*$", lambda _: f'harness = "{REPO}"', profile_module.DUMMY.read_text())
    path.write_text(re.sub(r"(?m)^tree_agents = .*$", line, text))
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

    @staticmethod
    def snapshot(base):
        """Every path below `base`, with its mode, and its bytes or the target of a link."""
        out = {}
        for path, dirs, files in os.walk(base):
            for name in dirs + files:
                p = pathlib.Path(path, name)
                st = p.lstat()
                out[str(p)] = (stat.S_IMODE(st.st_mode), os.readlink(p) if p.is_symlink()
                               else p.read_bytes() if stat.S_ISREG(st.st_mode) else None)
        return out


COUNT_LINE = re.compile(r"^\d+ change\(s\) (made|to make)\.$", re.M)
# The tools on the PATH of the precondition cases with no `julia`. Measured: the dry run and --apply
# of these cases start no tool from the PATH, and pass with an empty directory. git and sh are linked
# all the same, so that a later change of the install that starts one of them still finds it.
NO_JULIA_TOOLS = ["git", "sh"]


def precondition_cases(check, tmp):
    """`harness install` on a scratch HOME that lacks one thing, with the other preconditions of a
    scratch install: no ~/.claude/skills/, then no `julia` that starts while the Julia environment
    has a change pending, then a `julia` that starts and fails."""
    scratch = Scratch(check, tmp / "preconditions")
    case, run = scratch.case, scratch.run

    base, claude, _ = scratch.fresh()
    (claude / "skills").rmdir()
    code, text = run(base)
    found = [m.group(1) for m in COUNT_LINE.finditer(text)]
    case(lambda: code == 1 and found == ["to make"] and "Traceback" not in text and not (claude / "skills").exists(),
         f"with no ~/.claude/skills/, the dry run exits 1 with the count line N change(s) to make.: "
         f"{code}, {found}, {scratch.tail(text)!r}")

    # A PATH with no `julia`: one scratch directory of links to the tools of NO_JULIA_TOOLS, so that a
    # `julia` beside them, as in /usr/bin, takes no tool away; then one with a `julia` that cannot be
    # executed, or one that exits 1.
    tools = tmp / "preconditions" / "tools"
    tools.mkdir(parents=True)
    missing = [tool for tool in NO_JULIA_TOOLS if shutil.which(tool) is None]
    if missing:
        check(False, f"the precondition cases with no julia need {', '.join(missing)} on the PATH; they do not run")
        return
    for tool in NO_JULIA_TOOLS:
        (tools / tool).symlink_to(shutil.which(tool))
    path = [str(tools)]
    stubs = tmp / "preconditions" / "bin"
    stubs.mkdir()
    base, _, _ = scratch.fresh()
    (base / "julia" / "Manifest.toml").unlink()
    code, text = run(base, extra_env={"PATH": os.pathsep.join(path)})
    case(lambda: code == 1 and "INSTANTIATE" in text and "Traceback" not in text
         and "julia cannot be started" not in text,
         f"no julia on the PATH, a change pending in the Julia environment: the dry run exits 1 and prints "
         f"INSTANTIATE: {code}, {scratch.tail(text)!r}")
    for directories, stub, label in [
        (path, None, "no julia on the PATH"),
        ([str(stubs), *path], 0o644, "a julia on the PATH that is not executable"),
    ]:
        base, _, _ = scratch.fresh()
        (base / "julia" / "Manifest.toml").unlink()
        if stub is not None:
            (stubs / "julia").write_text("#!/bin/sh\nexit 0\n")
            (stubs / "julia").chmod(stub)
        code, text = run(base, "--apply", extra_env={"PATH": os.pathsep.join(directories)})
        last = scratch.tail(text)
        case(lambda: scratch.refused(code, text) and shutil.which("julia", path=os.pathsep.join(directories)) is None
             and text.count("julia cannot be started") == 1
             and all(w in last for w in ["julia", "not found on the PATH", "juliaup"]),
             f"{label}, a change pending in the Julia environment: --apply exits 2 with one line that names julia, "
             f"the PATH and juliaup: {code}, {last!r}")

    base, _, _ = scratch.fresh()
    (base / "julia" / "Manifest.toml").unlink()
    (stubs / "julia").write_text("#!/bin/sh\nexit 1\n")
    (stubs / "julia").chmod(0o755)
    code, text = run(base, "--apply", extra_env={"PATH": os.pathsep.join([str(stubs), *path])})
    last = scratch.tail(text)
    case(lambda: scratch.refused(code, text) and f"Pkg.instantiate failed in {base / 'julia'}" in last,
         f"a julia that starts and exits 1: --apply exits 2 with Pkg.instantiate failed: {code}, {last!r}")


def target_cases(check, tmp):
    """The targets that `harness install` cannot write, each on a fresh scratch HOME: a symlink and a
    directory at the OpenCode AGENTS.md and at ~/.claude/CLAUDE.md, a settings.json of mode 0444
    with a change, and a directory of mode 0555 where a new target goes. The dry run and --apply
    each exit 2 with one line that names the target once and what it is, and no file changes; for a
    target that cannot be written, the dry run prints its plan and count line before it. Then the
    mode of a backup, a mode change of a target that another user owns, an OSError in the write
    itself, and a stray rule with a lone surrogate."""
    import errno
    from unittest import mock

    from . import HarnessError, install

    scratch = Scratch(check, tmp / "targets")
    case, run, snapshot = scratch.case, scratch.run, scratch.snapshot

    def refusals(base, target, what, label, shown=None):
        """The dry run and --apply on `base`, each refused with one line that names `target`; with
        `shown`, the label of a planned line, the dry run prints its plan first, that line and the
        count line among it, and the refusal last."""
        before = snapshot(base)
        for argv in ([], ["--apply"]):
            code, text = run(base, *argv)
            lines = text.strip().splitlines()
            plan = shown is not None and not argv
            case(lambda: scratch.refused(code, text) and lines[-1].count(str(target)) == 1 and what in lines[-1]
                 and (len(lines) == 1 if not plan else
                      any(l.startswith(shown) for l in lines[:-1]) and len(COUNT_LINE.findall(text)) == 1
                      and COUNT_LINE.search(text).group(1) == "to make"
                      and not any(str(target) in l for l in lines[:-1]))
                 and snapshot(base) == before,
                 f"{label}: {' '.join(['install', *argv])} exits 2, "
                 + ("prints its plan with its count line, then one line that names it" if plan
                    else "with one line that names it")
                 + f", and no file changes: {code}, {len(lines)} line(s), {scratch.tail(text)!r}")

    for where, rel in [("opencode", "AGENTS.md"), ("home/.claude", "CLAUDE.md")]:
        for kind, what in [("a symlink", "is a symlink"), ("a directory", "is a directory")]:
            base, _, _ = scratch.fresh()
            target = base / where / rel
            if kind == "a symlink":
                (base / "outside.md").write_text("outside\n")
                target.symlink_to(base / "outside.md")
            else:
                target.mkdir()
            refusals(base, target, what, f"{kind} at {where}/{rel}")

    base, claude, _ = scratch.fresh()
    live = claude / "settings.json"
    live.write_text('{"model": "x"}\n')
    live.chmod(0o444)
    try:
        refusals(base, live, "cannot be written", "a settings.json of mode 0444 with a change",
                 shown="~/.claude/settings.json")
    finally:
        live.chmod(0o644)

    base, _, _ = scratch.fresh()
    (base / "opencode").chmod(0o555)
    try:
        refusals(base, base / "opencode" / "opencode.jsonc", "cannot be written",
                 "a new opencode.jsonc in a directory of mode 0555", shown="opencode.jsonc")
    finally:
        (base / "opencode").chmod(0o755)

    # A backup never keeps the mode of the file it backs up: the file's 0644 becomes 0600.
    base, claude, _ = scratch.fresh()
    (claude / "settings.json").write_text('{"model": "x"}\n')
    (claude / "settings.json").chmod(0o644)
    code, text = run(base, "--apply")
    backups = sorted(claude.glob("settings.json.bak-*"))
    case(lambda: code == 0 and len(backups) == 1 and scratch.mode(backups[0]) == 0o600
         and backups[0].read_text() == '{"model": "x"}\n',
         f"the backup of a settings.json of mode 0644 has mode 0600: {code}, "
         f"{[oct(scratch.mode(b)) for b in backups]}, {scratch.tail(text)!r}")

    # A target whose bytes stay and whose mode changes is a chmod, which needs the owner: one that
    # another user owns is refused before anything is written, and one of mode 0444 that the user
    # owns is not.
    owned = tmp / "targets" / "owned.md"
    owned.write_bytes(b"x\n")
    owned.chmod(0o444)
    files = [(owned, b"x\n", 0o644, "owned.md")]
    with mock.patch.object(os, "geteuid", return_value=owned.stat().st_uid + 1):
        other = install.check_files(files)
    mine = install.check_files(files)
    owned.chmod(0o644)
    case(lambda: other is not None and other.count(str(owned)) == 1 and "owner" in other and mine is None,
         f"a mode change of a target another user owns is refused, and of a 0444 target the user owns is not: "
         f"{other!r}, {mine!r}")
    # A writable target whose bytes change, with a mode in the plan, is followed by a chmod too.
    with mock.patch.object(os, "geteuid", return_value=owned.stat().st_uid + 1):
        other = install.check_files([(owned, b"y\n", 0o644, "owned.md")])
        unnamed = install.check_files([(owned, b"y\n", None, "owned.md")])
    case(lambda: other is not None and "owner" in other and unnamed is None,
         f"a byte change with a mode in the plan, of a writable target another user owns, is refused, and one "
         f"with no mode is not: {other!r}, {unnamed!r}")

    # An OSError in the write itself, after the checks, as a full disk gives it: exit 2 with the target.
    target = tmp / "targets" / "full" / "x.md"
    full = OSError(errno.ENOSPC, "No space left on device", str(target))
    with mock.patch.object(pathlib.Path, "write_bytes", side_effect=full):
        try:
            install.install_file(True, b"x\n", target, "x.md")
            raised = None
        except (HarnessError, OSError) as e:  # an OSError is the defect that the case looks for
            raised = e
    case(lambda: isinstance(raised, HarnessError) and str(target) in str(raised)
         and "No space left on device" in str(raised),
         f"an OSError in the write is a HarnessError that names the target: {raised!r}")

    # A stray rule with a lone surrogate prints it escaped, and the dry run exits as it does without it.
    base, _, _ = scratch.fresh()
    without, _ = run(base)
    stray = base / "home" / "Research" / ".claude" / "settings.local.json"
    stray.parent.mkdir(parents=True)
    stray.write_text('{"permissions": {"allow": ["Bash(\\ud800)"]}}\n')
    code, text = run(base)
    case(lambda: code == without and "Traceback" not in text and f"{stray}  allow  Bash(\\ud800)" in text,
         f"a stray rule with a lone surrogate prints it as \\ud800, and the dry run exits {without} as without it: "
         f"{code}, {scratch.tail(text)!r}")


def setup_guard_cases(check, tmp):
    """The groups of cases that edit or read the files of a setup install — `layer_cases` of the
    Claude Code adapter, `install_cases` of the OpenCode adapter, `omp_cases` of the oh-my-pi
    adapter — and `drift_cases` of the hook probe, each run with every `harness install` failing:
    each reports the failed setup install as one wrong case with the exit status and the last line,
    raises nothing, and runs no case after it."""
    from unittest import mock

    from . import frontends

    failure = "harness install: an injected failure of the setup install"

    def failing(base, *argv, extra_env=None, models=None):
        return 2, failure

    def omp(record, where):
        scratch = Scratch(record, where)
        frontends.adapter("omp").omp_cases(scratch.case, scratch.fresh, failing)

    groups = [("claude", frontends.adapter("claude").layer_cases),
              ("opencode", frontends.adapter("opencode").install_cases), ("omp", omp)]
    for n, (name, group) in enumerate(groups):
        where = tmp / f"guard{n}"
        where.mkdir(parents=True)
        labels = []
        try:
            with mock.patch.object(Scratch, "run", staticmethod(failing)):
                group(lambda ok, label: labels.append((ok, label)), where)
            raised = None
        except Exception as e:  # the defect that the case looks for: reported, and the next group runs
            raised = f"{type(e).__name__}: {e}"
        setup = [i for i, (ok, label) in enumerate(labels)
                 if not ok and "the setup install --apply" in label and "exits 2" in label and failure in label]
        check(raised is None and len(setup) == 1 and setup[0] == len(labels) - 1,
              f"{name}: a failed setup install is one wrong case with its exit status and last line, and the "
              f"group stops there: raised {raised}, {len(setup)} such line(s), "
              f"{len(labels) - 1 - (setup[0] if setup else -1)} case(s) after it")

    # The `[inst-drif]` group of the hook probe, hooks/probe.py, loaded in this process, with its
    # install failing.
    import contextlib
    import importlib.util
    import io

    spec = importlib.util.spec_from_file_location("harness_probe", REPO / "hooks" / "probe.py")
    probe = importlib.util.module_from_spec(spec)
    out = io.StringIO()
    try:
        spec.loader.exec_module(probe)
        with contextlib.redirect_stdout(out):
            result = probe.drift_cases(lambda base, env: (2, f"some output\n{failure}\n"))
        raised = None
    except Exception as e:  # the defect that the case looks for: reported
        result, raised = None, f"{type(e).__name__}: {e}"
    finally:
        if hasattr(probe, "FIXTURE"):
            probe.FIXTURE.cleanup()
    lines = [line for line in out.getvalue().splitlines() if "[inst-drif]" in line]
    check(raised is None and result == (1, 1) and len(lines) == 1 and lines[0].startswith("BAD")
          and "exits 2" in lines[0] and failure in lines[0],
          f"probe [inst-drif]: a failed setup install is one wrong case with its exit status and last line, and "
          f"the group stops there: raised {raised}, {result}, {lines}")


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
    # The cases below edit the files that this install writes: a failed one leaves them unwritten.
    if code != 0:
        check(False, f"the setup install --apply of the restart cases exits {code}: {scratch.tail(text)!r}; "
                     f"the restart cases after it do not run")
        return
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
