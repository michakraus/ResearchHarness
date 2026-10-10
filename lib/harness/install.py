"""Install the configuration of each frontend that lib/harness/frontends.py names, and the Julia
environment of the scripts.

    harness install [--apply] [--force]

`--force` replaces a file that a plan refuses to replace; the adapter that refuses says which.

The installed configuration is deny-write from a session on purpose. The canonical copies therefore
live in this repository, and this verb installs them — the same arrangement as githooks/ and
launchagents/.

What it installs:
  Project.toml                     -> ~/.local/share/research-harness/julia/ ($RESEARCH_HARNESS_JULIA),
                                      instantiated: the packages the Julia scripts load
  each frontend's files            -> as the docstring of its adapters/<frontend>/adapter.py says

It loads the profile and the model tables, `--models F`, else $RESEARCH_HARNESS_MODELS, else
models.toml beside the profile; examples/models.toml shows them. Then it plans each frontend, in
the order of FRONTENDS. A plan writes nothing, so each refusal that exits 2 at once does
so before anything is written. Then it installs the Julia environment and the files of each plan in
that order, prints the warnings, and runs the steps of each plan that follow the files. It prints
the installed files with no source, then the count line. After an `--apply`, it prints the restart
line of each frontend whose files or steps changed something, in that order; the Julia environment
belongs to no frontend. A plan's own refusal exits 2 after these lines, once the rest is installed.

A file that differs from the plan, in its bytes or in its mode, is a change. The plan's checks of
a layer that mirrors its sources (`source_files`, `check_targets`) and the stamp (`stamp_bytes`),
which the `SessionStart` hook hooks/install-drift.py computes again at each session start, are
here, for the adapter that installs such a layer.
"""

import datetime
import importlib.util
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unicodedata

from . import REPO, HarnessError, changing, frontends, outcome, sources
from . import profile as profile_module

# The stamp that the `SessionStart` hook hooks/install-drift.py compares, at the top of the layer
# whose sources it names; a hidden name, so it is neither a source nor EXTRA.
STAMP = ".harness-install.json"
JULIA = ["julia", "--startup-file=no"]
# The installed copy of the repository's Project.toml, which every Julia script puts in its
# LOAD_PATH. A session cannot write below ~/.local, so it cannot change what the unsandboxed
# updater installs there.
JULIA_ENV = pathlib.Path(os.environ.get("RESEARCH_HARNESS_JULIA")
                         or pathlib.Path.home() / ".local" / "share" / "research-harness" / "julia")


def warn(*lines):
    print()
    print("WARNING: " + "\n         ".join(lines))


def install_file(apply, data, dst, label, backup=False, mode=None):
    """Install `data` (bytes) at `dst`, with `mode` when given; 1 when either differs, after the
    change under `apply`."""
    same = dst.is_file() and dst.read_bytes() == data
    old = stat.S_IMODE(dst.stat().st_mode) if dst.is_file() else None
    if same and mode in (None, old):
        print(f"{label:<34} already identical")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    note = f" (backup: {dst.name}.bak-{stamp})" if backup and dst.is_file() and not same else ""
    if same:
        print(f"{label:<34} MODE {old:04o} -> {mode:04o}")
    else:
        print(f"{label:<34} {'REPLACE' if dst.is_file() else 'INSTALL'}{note}")
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if note:
            shutil.copy(dst, dst.with_name(f"{dst.name}.bak-{stamp}"))
        if not same:
            dst.write_bytes(data)
        if mode is not None:
            dst.chmod(mode)
    return 1


def hidden(name):
    """A name that is neither a source nor reported as EXTRA."""
    return name.startswith(".") or name == "__pycache__"


def fold(dst):
    """`dst` with case and Unicode form folded, on every platform, as the default macOS volume
    compares names."""
    return unicodedata.normalize("NFC", dst).casefold()


def unreadable(error):
    """The `onerror` of `os.walk`: a directory that cannot be read exits 2."""
    raise HarnessError(f"{error.filename} cannot be read: {error.strerror}")


def drift_hook():
    """The `SessionStart` hook hooks/install-drift.py as a module, for its `digest_of`."""
    spec = importlib.util.spec_from_file_location("install_drift", REPO / "hooks" / "install-drift.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stamp_bytes(sources, plan):
    """The stamp of `sources`, each (directory, installed prefix, top-level names not installed,
    top-level directories not installed), and of `plan`, [(installed path, bytes, mode)] of them:
    JSON with each source as [directory, installed prefix, sorted names not installed, sorted
    directories not installed], and the digest of hooks/install-drift.py over the planned paths,
    bytes and modes, which are what the apply installs, each file with the bytes of its source."""
    sources = [[str(d), prefix, sorted(skip), sorted(skipped)] for d, prefix, skip, skipped in sources]
    return (json.dumps({"sources": sources, "digest": drift_hook().digest_of(plan)}, indent=2) + "\n").encode()


def source_files(directory):
    """Every file below `directory`, relative to it, in sorted order; none when it is missing.
    A directory that cannot be read, a symlink, and an entry that is neither a file nor a
    directory, such as a FIFO, exit 2."""
    if not directory.is_dir():
        return []
    found = []
    for path, dirs, files in os.walk(directory, onerror=unreadable):
        dirs[:] = [d for d in dirs if not hidden(d)]
        files = [f for f in files if not hidden(f)]
        for name in dirs + files:
            link = os.path.join(path, name)
            if os.path.islink(link):
                raise HarnessError(f"{link} is a symlink; a source holds files and directories only")
        for name in files:
            entry = os.path.join(path, name)
            try:
                regular = stat.S_ISREG(os.stat(entry).st_mode)
            except OSError as e:
                raise HarnessError(f"{entry} cannot be read: {e.strerror}") from None
            if not regular:
                raise HarnessError(f"{entry} is neither a file nor a directory; a source holds files and directories only")
        found += [pathlib.Path(path, f).relative_to(directory) for f in files]
    return sorted(found)


def check_targets(root, shown, plan):
    """Exit 2 on an installed path of `plan`, [(path relative to `root`, …)], or a directory above
    one, that is a symlink, and on one that is not a readable file below directories; `shown` is
    `root` as the messages name it."""
    for dst, *_ in plan:
        parts = pathlib.PurePosixPath(dst).parts
        for i in range(len(parts) + 1):
            path = root.joinpath(*parts[:i])
            if path.is_symlink():
                raise HarnessError(f"{path} is a symlink; nothing is written through it")
            if i < len(parts) and path.exists() and not path.is_dir():
                raise HarnessError(f"{path} is not a directory, and {shown}/{dst} is installed below it")
        if path.exists() and not (path.is_file() and os.access(path, os.R_OK)):
            raise HarnessError(f"{path} is not a file that can be read, and {shown}/{dst} is installed there")


def install_julia_env(apply):
    """Copy Project.toml to JULIA_ENV and instantiate it there; the number of changes."""
    changes = install_file(apply, (REPO / "Project.toml").read_bytes(), JULIA_ENV / "Project.toml",
                           "julia/Project.toml")
    if not (JULIA_ENV / "Manifest.toml").is_file():
        print(f"{'julia/Manifest.toml':<34} INSTANTIATE")
        changes += 1
    if apply and changes:
        # `Pkg.resolve` adds no registry, so a new depot needs General first.
        p = subprocess.run([*JULIA, f"--project={JULIA_ENV}", "-e",
                            "using Pkg; isempty(Pkg.Registry.reachable_registries()) && "
                            "Pkg.Registry.add(\"General\"); Pkg.resolve(); Pkg.instantiate()"])
        if p.returncode != 0:
            raise HarnessError(f"Pkg.instantiate failed in {JULIA_ENV}")
    return changes


def cmd_install(args):
    adapters = frontends.load()
    profile = profile_module.load(args.profile)
    models = profile_module.models_path(args)
    profile_module.read_models(models)
    ctx = types.SimpleNamespace(args=args, profile=profile, models=models, agents=sources.AGENTS, plans={})
    for adapter in adapters:
        ctx.plans[adapter.NAME] = adapter.plan(ctx)
    plans = list(ctx.plans.values())
    # The Julia environment belongs to no frontend, so its changes count in no plan's.
    julia = install_julia_env(args.apply)
    changed = [0] * len(plans)

    for i, plan in enumerate(plans):
        for lines, _ in plan.refused:
            for line in lines:
                print(line)
        for dst, data, mode, label, *rest in plan.files:
            change = install_file(args.apply, data, dst, label, backup=bool(rest and rest[0]), mode=mode)
            if change and rest[1:]:
                print(rest[1])
            changed[i] += change
    # The warnings go before the steps after the files, so that a step that exits 2 leaves them printed.
    for plan in plans:
        for lines in plan.warnings:
            warn(*lines)
    for i, plan in enumerate(plans):
        for step in plan.after:
            changed[i] += step(args.apply)
    for plan in plans:
        for text in plan.extra:
            print(text)

    changes = julia + sum(changed)
    print(f"\n{changes} change(s) {'made' if args.apply else 'to make'}.")
    # `plans`, and so `changed`, are in the order of `adapters`.
    restarts = [adapter.RESTART for adapter, n in zip(adapters, changed) if n] if args.apply else []
    if restarts:
        print()
        for line in restarts:
            print(line)
    refused = [message for plan in plans for _, message in plan.refused]
    if refused:
        raise HarnessError("; ".join(refused))
    return outcome(args, changes)


def selftest():
    """A malformed profile or models.toml exits 2 with no traceback; then `load_cases` and
    `install_cases.restart_cases`."""
    from .install_cases import restart_cases

    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  install: {label}")

    harness = [sys.executable, str(REPO / "bin" / "harness")]
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "bad.toml"
        for data, argv, label in [
            (b"home = \n", ["--profile", str(bad), "get", "home"], "a profile that is not TOML"),
            (b'home = "\xff"\n', ["--profile", str(bad), "get", "home"], "a profile that is not UTF-8"),
            (b'[x]\n# \xff\n', ["--profile", str(profile_module.DUMMY), "--models", str(bad), "install"],
             "a models.toml that is not UTF-8"),
        ]:
            bad.write_bytes(data)
            p = subprocess.run(harness + argv, capture_output=True, text=True)
            check(p.returncode == 2 and str(bad) in p.stderr and "Traceback" not in p.stderr,
                  f"{label} exits 2 and names the file: {p.returncode}, {p.stderr.strip()[-200:]!r}")
        # A table of the tiers with an old key, Claude Code's name of a tier, exits 2 and names the rename.
        example = (REPO / "examples" / "models.toml").read_text()
        for table, old, new in [("[claude]", "opus", "large"), ("[opencode.models]", "opus", "large"),
                                ("[omp]", "opus", "large"), ("[omp]", "sonnet", "medium"), ("[omp]", "haiku", "small")]:
            at = example.index(table + "\n") + len(table) + 1
            bad.write_text(example[:at] + f'{old} = "provider-a/large-model"\n' + example[at:])
            p = subprocess.run(harness + ["--profile", str(profile_module.DUMMY), "--models", str(bad), "install"],
                               capture_output=True, text=True)
            check(p.returncode == 2 and str(bad) in p.stderr and f"rename {old} to {new}" in p.stderr
                  and table in p.stderr and "Traceback" not in p.stderr,
                  f"a models.toml with {old} = in {table} exits 2, names the file and {new}: {p.returncode}, "
                  f"{p.stderr.strip()[-200:]!r}")
        # Old keys in two tables, and no [claude]: one refusal names every rename and the table to add.
        text = example.replace('[claude]\nlarge = "opus"\nmedium = "sonnet"\nsmall = "haiku"\n', "", 1)
        for table, old in [("[opencode.models]", "sonnet"), ("[omp]", "haiku")]:
            at = text.index(table + "\n") + len(table) + 1
            text = text[:at] + f'{old} = "provider-a/large-model"\n' + text[at:]
        bad.write_text(text)
        p = subprocess.run(harness + ["--profile", str(profile_module.DUMMY), "--models", str(bad), "install"],
                           capture_output=True, text=True)
        check(p.returncode == 2 and all(w in p.stderr for w in ["[opencode.models]", "rename sonnet to medium",
                                                                 "[omp]", "rename haiku to small", "[claude]"]),
              f"old keys in [opencode.models] and [omp] and no [claude] exit 2 with one message that names all "
              f"three: {p.returncode}, {p.stderr.strip()[-300:]!r}")
        load_cases(check, pathlib.Path(tmp))
        restart_cases(check, pathlib.Path(tmp))
    return total, wrong


def load_cases(check, tmp):
    """An adapter that fails to load, or that lacks a member of the interface, makes `harness
    install --apply` exit 2 with its path, and its line where it has one, before any frontend
    writes; no adapter is skipped. The adapters load from a copy below `tmp`, with
    `frontends.REPO` set to it in the process of the install."""
    from .install_cases import Scratch

    scratch = Scratch(check, tmp / "homes")
    run =("import pathlib, sys; sys.path.insert(0, sys.argv[1]); from harness import cli, frontends; "
           "frontends.REPO = pathlib.Path(sys.argv[2]); sys.exit(cli.main(sys.argv[3:]))")
    first, middle, last = frontends.FRONTENDS[0], frontends.FRONTENDS[1], frontends.FRONTENDS[-1]
    for n, (name, code, said, label) in enumerate([
        (first, "def (:\n", "SyntaxError", "a syntax error"),
        (last, "raise RuntimeError('broken at import')\n", "RuntimeError: broken at import",
         "an exception at import"),
        (last, "raise SystemExit(3)\n", "SystemExit: 3", "a SystemExit at import"),
        (middle, "del plan\n", "plan", "no `plan`"),
        (middle, "del RESTART\n", "RESTART", "no `RESTART`"),
    ]):
        base, _, _ = scratch.fresh()
        repo = tmp / f"repo{n}"
        for frontend in frontends.FRONTENDS:
            (repo / "adapters" / frontend).mkdir(parents=True)
            text = (REPO / "adapters" / frontend / "adapter.py").read_text()
            (repo / "adapters" / frontend / "adapter.py").write_text(text + code * (frontend == name))
        path = repo / "adapters" / name / "adapter.py"
        line = len(path.read_text().splitlines())
        before = sorted(base.rglob("*"))
        env = scratch.env(base)
        p = subprocess.run([sys.executable, "-c", run, str(REPO / "lib"), str(repo),
                            "--profile", str(base / "profile.toml"), "--models", str(REPO / "examples" / "models.toml"),
                            "install", "--apply"], capture_output=True, text=True, env=env, cwd=base)
        after = sorted(base.rglob("*"))
        where = f"{path}:{line}: " if name != middle else f"{path}: "
        check(p.returncode == 2 and where in p.stderr and said in p.stderr and "Traceback" not in p.stderr
              and after == before,
              f"an adapter with {label} exits 2 with its path{' and line' * (name != middle)}, and nothing is "
              f"written: {p.returncode}, {len(after) - len(before)} new paths, {p.stderr.strip()[-200:]!r}")


def register(sub):
    p = changing(sub.add_parser("install", help="install the configuration of each frontend"))
    p.add_argument("--force", action="store_true", help="replace a file that the install refuses to replace")
    p.set_defaults(run=cmd_install)
