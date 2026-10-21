#!/usr/bin/env python3
"""Test the scripts of .chezmoiscripts/ in scratch directories, never against the home directory.

Run it with Python 3.11 or later, from any directory:

    python3 tests/script-check.py

It needs chezmoi, git, bash and shellcheck. Each script is rendered with `chezmoi
execute-template` (its own --config, --source, --destination and --persistent-state under
$TMPDIR) for a host, and run with /bin/bash in a process whose HOME is a scratch directory.
Besides each host of .chezmoidata/machines.toml, the cases name template_host, the first Linux
host there that is not template_host, and hosts of the test's own, added as data. The remotes
are scratch repositories that a scratch git configuration puts in place of the URLs of [remotes]
in machines.toml (`url.<path>.insteadOf`).
launchctl, systemctl, juliaup, julia, chsh, curl and sudo are stubs that log their arguments; the
stubs come first on the PATH. The services test runs the real `harness render` of a scratch clone
of a harness checkout (read-only): when this source is examples/dotfiles/ of a harness checkout,
as in CI, that checkout at its HEAD, which the test renders as harness_commit; otherwise
~/Research/Harness at the harness_commit of machines.toml.

Checks, numbered as the section banners and the `== check N` lines of the output:
  1. The tool check exits 1 and names exactly the missing tools, for each tool alone and for all
     at once, on darwin and on linux; python3 older than 3.11 counts as missing; it installs
     nothing.
  2. The clones: a fresh home gets all four clones with the remotes of machines.toml, and the
     meta repository's work tree is ~/Research; a second run skips all four; each directory that
     exists and is not a clone of its remote (non-empty, empty, another remote) stops the run
     before the first clone and stays unchanged; a file in the way of the meta checkout stops the
     run, and a second run completes once it is gone; a remote that does not answer fails the
     run.
  3. The harness: the pin is fetched and checked out, then `harness install --apply` runs; a
     modified or an untracked file stops the run before the checkout; a pin the remote lacks and
     a remote that does not answer fail the run with no install. On the template host the
     checkout never moves: with HEAD containing the pin the install runs over local changes;
     without it the run stops with no install.
  4. Julia: .chezmoidata/julia.toml holds the package set and its minimum channels. Per GPU
     (metal, cuda, amdgpu, none), juliaup adds each missing channel and sets the default; each
     X.Y channel gets one Pkg.add of the packages of the set whose minimum is at most the
     channel, and the GPU package, minus those in the [deps] of its Project.toml (a name under
     [compat] or in a comment counts as missing); nightly, release, lts and 1.13.1 get none; with
     every package present no Pkg.add runs; the Kaimon app is installed; a failing julia stops
     the run at its channel and names it; a minimum that is not X.Y fails the render.
  5. The services: the copies in ~/.local/bin; on linux the five units, each equal to `harness
     render`, then daemon-reload and enable --now; on macOS the plists, each equal to `harness
     render`, bootout of a loaded job and bootstrap of each; a bootout that finishes late and a
     failed first bootstrap still load every job, and a mutant with no wait stops; the script's
     text changes with the pin and with the profile.
  6. Every script, rendered for every host of machines.toml, passes `bash -n` and `shellcheck`;
     no script names sudo, a pipe into a shell, or a key file.
"""

import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib

SOURCE = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = SOURCE / ".chezmoiscripts"
# The harness checkout that holds this source when the source is its examples/dotfiles/.
KIT_HARNESS = SOURCE.parent.parent
HOME_HARNESS = pathlib.Path.home() / "Research" / "Harness"

TOOL_CHECK = "run_before_00-check-tools.sh.tmpl"
CLONES = "run_once_after_10-clones.sh.tmpl"
JULIA = "run_onchange_after_20-julia.sh.tmpl"
HARNESS = "run_onchange_after_30-harness.sh.tmpl"
SERVICES = "run_onchange_after_50-services.sh.tmpl"

COMMON_TOOLS = ["git", "zsh", "curl", "python3", "lsof", "rtk", "juliaup", "gh", "glab"]
LINUX_TOOLS = ["bwrap", "socat", "secret-tool"]

# Each clone's directory below HOME and its key in the [remotes] table of machines.toml.
CLONE_KEYS = {
    ".claude": "claude",
    "Research/Environment": "environment",
    "Research/Harness": "harness",
    "Research/.meta": "meta",
}
UNITS = ["kaimon.service", "julia-update.service", "julia-update.timer",
         "claude-autocommit.service", "claude-autocommit.timer"]
JOBS = ["kaimon", "julia-update", "claude-autocommit"]
GPU_PACKAGE = {"metal": "Metal", "cuda": "CUDA", "amdgpu": "AMDGPU", "none": None}

failures = []
ROOT = None  # the scratch directory of the whole run


def fail(message):
    failures.append(message)
    print(f"  FAIL: {message}")


def ok(message):
    print(f"  ok: {message}")


def check(condition, message):
    if condition:
        ok(message)
    else:
        fail(message)
    return condition


def machines_data():
    with open(SOURCE / ".chezmoidata" / "machines.toml", "rb") as handle:
        return tomllib.load(handle)


DATA = machines_data()
TEMPLATE_HOST = DATA["template_host"]
# A Linux host that is not the template host, from machines.toml.
LINUX_HOST = next((host for host, entry in DATA["machines"].items()
                   if entry["os"] == "linux" and host != TEMPLATE_HOST), None)


def harness_source():
    """The harness checkout that the services test clones, and the commit it checks out: this
    source's own harness checkout at its HEAD when the source is its examples/dotfiles/,
    otherwise ~/Research/Harness at the harness_commit of machines.toml."""
    if (SOURCE == KIT_HARNESS / "examples" / "dotfiles"
            and (KIT_HARNESS / "bin" / "harness").is_file() and (KIT_HARNESS / ".git").exists()):
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=KIT_HARNESS, capture_output=True,
                              text=True, check=True).stdout.strip()
        return KIT_HARNESS, head
    return HOME_HARNESS, DATA["harness_commit"]


# ---------------------------------------------------------------- scratch helpers ----

def scratch(name):
    """A new empty directory below the run's scratch root."""
    path = pathlib.Path(tempfile.mkdtemp(prefix=f"{name}-", dir=ROOT))
    return path


def render(script, host, os_name, home, extra=None):
    """Render a script for a host with chezmoi; return (returncode, text, stderr)."""
    work = scratch("chezmoi")
    (work / "chezmoi.toml").write_text("")
    data = {"chezmoi": {"hostname": host, "os": os_name, "homeDir": str(home)}}
    for key, value in (extra or {}).items():
        data[key] = value
    cmd = [
        "chezmoi",
        "--config", str(work / "chezmoi.toml"),
        "--source", str(SOURCE),
        "--destination", str(work / "home"),
        "--persistent-state", str(work / "state.boltdb"),
        "--no-tty",
        "--override-data", json.dumps(data),
        "execute-template",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, input=(SCRIPTS / script).read_text())
    return result.returncode, result.stdout, result.stderr


def rendered(script, host, os_name, home, extra=None):
    code, text, err = render(script, host, os_name, home, extra)
    if code != 0:
        raise RuntimeError(f"{script} does not render for {host}: {err.strip()}")
    return text


def stub(directory, name, body):
    """An executable /bin/sh stub."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return path


# The launchctl stub. $HOME/loaded names the jobs launchd has. `print LABEL` succeeds while the
# label is there; bootout removes it, but when $HOME/linger holds N, `print` still succeeds N more
# times for that label, as for a bootout that has not finished. A bootstrap fails while the label
# is listed, and the first N bootstraps fail when $HOME/bootstrap-failures holds N; one that does
# not fail adds the label.
LAUNCHCTL = r'''count() { cat "$1" 2>/dev/null || echo 0; }
case "$1" in
print)
    label=${2##*/}
    n=$(count "$HOME/linger.$label")
    if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$HOME/linger.$label"; exit 0; fi
    grep -qxF "$label" "$HOME/loaded" 2>/dev/null
    exit $? ;;
bootout)
    label=${2##*/}
    grep -vxF "$label" "$HOME/loaded" > "$HOME/loaded.new" 2>/dev/null
    mv "$HOME/loaded.new" "$HOME/loaded"
    if [ -f "$HOME/linger" ]; then cp "$HOME/linger" "$HOME/linger.$label"; fi
    exit 0 ;;
bootstrap)
    label=$(basename "$3" .plist)
    f=$(count "$HOME/bootstrap-failures")
    if [ "$f" -gt 0 ] || [ "$(count "$HOME/linger.$label")" -gt 0 ] \
        || grep -qxF "$label" "$HOME/loaded" 2>/dev/null; then
        if [ "$f" -gt 0 ]; then echo $((f - 1)) > "$HOME/bootstrap-failures"; fi
        echo "Bootstrap failed: 5: Input/output error" >&2
        exit 5
    fi
    echo "$label" >> "$HOME/loaded"
    exit 0 ;;
esac
'''


def logging_stubs(home, bindir):
    """Stubs for every program that must not reach the machine: each logs to $HOME/<name>.log."""
    for name in ("launchctl", "systemctl", "chsh", "curl", "sudo"):
        exit_code = 1 if name in ("chsh", "curl", "sudo") else 0
        body = f'echo "$*" >> "$HOME/{name}.log"\n'
        if name == "launchctl":
            body += LAUNCHCTL
        stub(bindir, name, body + f"exit {exit_code}")
    # python3 >= 3.11 for the scripts and for the harness.
    (bindir / "python3").symlink_to(sys.executable)


def environment(home, bindir, gitconfig=None):
    """The whole environment of a script: no variable of this process leaks into it."""
    assert str(home).startswith(str(ROOT)), home
    env = {
        "HOME": str(home),
        "PATH": f"{bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(ROOT),
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if gitconfig is not None:
        env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    else:
        env["GIT_CONFIG_GLOBAL"] = str(home / ".gitconfig-test")
    return env


def run_script(text, env, cwd=None):
    path = scratch("script") / "script.sh"
    path.write_text(text)
    return subprocess.run(["/bin/bash", str(path)], capture_output=True, text=True, env=env,
                          cwd=cwd or env["HOME"])


def git(env, *args, cwd=None):
    result = subprocess.run(["git", *args], capture_output=True, text=True, env=env, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def git_env(base):
    """An environment for the test's own git calls, with a scratch global configuration."""
    config = base / "gitconfig"
    if not config.exists():
        config.write_text("[user]\n\tname = test\n\temail = test@example.invalid\n"
                          "[init]\n\tdefaultBranch = master\n")
    return {"HOME": str(base), "PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C"}


def make_remote(base, env, rel, files, branch="master"):
    """A bare repository at base/rel with one commit of `files`; return its commit."""
    work = scratch("work")
    git(env, "init", "-q", "-b", branch, str(work))
    for name, content in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if name.startswith("bin/"):
            path.chmod(0o755)
    git(env, "add", "-A", cwd=work)
    git(env, "commit", "-qm", "first", cwd=work)
    bare = base / rel
    bare.parent.mkdir(parents=True, exist_ok=True)
    git(env, "clone", "-q", "--bare", str(work), str(bare))
    return git(env, "rev-parse", "HEAD", cwd=work), work


def add_commit(env, work, bare, name, content, message="next"):
    (work / name).write_text(content)
    git(env, "add", name, cwd=work)
    git(env, "commit", "-qm", message, cwd=work)
    git(env, "push", "-q", str(bare), "HEAD", cwd=work)
    return git(env, "rev-parse", "HEAD", cwd=work)


def write_gitconfig(path, rewrites):
    lines = ["[user]", "\tname = test", "\temail = test@example.invalid",
             "[init]", "\tdefaultBranch = master",
             "[advice]", "\tdetachedHead = false"]
    for local, url in rewrites.items():
        lines += [f'[url "{local}"]', f"\tinsteadOf = {url}"]
    path.write_text("\n".join(lines) + "\n")
    return path


def tree(path):
    """Every path below `path`, relative, with file contents: a snapshot to compare."""
    snapshot = {}
    for dirpath, dirnames, names in os.walk(path):
        for name in dirnames + names:
            full = pathlib.Path(dirpath, name)
            rel = str(full.relative_to(path))
            snapshot[rel] = full.read_bytes() if full.is_file() and not full.is_symlink() else None
    return snapshot


def missing_named(stderr):
    """The tool names of the tool check's `missing tools:` line."""
    for line in stderr.splitlines():
        if "missing tools:" in line:
            return set(line.split("missing tools:", 1)[1].split())
    return None


# ----------------------------------------------------------------- check 1 ----

def test_tool_check():
    print("\n== check 1: the tool check")
    home = scratch("home")
    for os_name in ("darwin", "linux"):
        text = rendered(TOOL_CHECK, TEMPLATE_HOST, os_name, home)
        required = COMMON_TOOLS + (LINUX_TOOLS if os_name == "linux" else [])
        everything = COMMON_TOOLS + LINUX_TOOLS

        def run_with(present, old_python=False):
            bindir = scratch("bin")
            for tool in present:
                if tool == "python3":
                    stub(bindir, "python3", "exit 1" if old_python else "exit 0")
                else:
                    stub(bindir, tool, "exit 0")
            before = tree(bindir)
            env = {"HOME": str(home), "PATH": str(bindir), "LANG": "C"}
            result = run_script(text, env)
            if tree(bindir) != before:
                fail(f"{os_name}: the tool check changed its PATH directory")
            return result

        result = run_with(everything)
        check(result.returncode == 0 and missing_named(result.stderr) is None,
              f"{os_name}: every tool present: exit {result.returncode}")
        for tool in required:
            result = run_with([t for t in everything if t != tool])
            check(result.returncode == 1 and missing_named(result.stderr) == {tool},
                  f"{os_name}: without {tool}: exit {result.returncode}, named "
                  f"{sorted(missing_named(result.stderr) or [])}")
        result = run_with([])
        check(result.returncode == 1 and missing_named(result.stderr) == set(required),
              f"{os_name}: with no tool: exit {result.returncode}, every one of the "
              f"{len(required)} tools named")
        result = run_with(everything, old_python=True)
        check(result.returncode == 1 and missing_named(result.stderr) == {"python3>=3.11"},
              f"{os_name}: python3 older than 3.11: exit {result.returncode}, named "
              f"{sorted(missing_named(result.stderr) or [])}")
        if os_name == "darwin":
            result = run_with(COMMON_TOOLS)
            check(result.returncode == 0, "darwin: bwrap, socat, secret-tool not required")


# ----------------------------------------------------------------- check 2 ----

def clone_urls():
    """Each clone's directory below HOME and its remote, from the [remotes] table."""
    return {rel: DATA["remotes"][key] for rel, key in CLONE_KEYS.items()}


def clone_fixture():
    """Four bare remotes and a git configuration that puts them in place of the remotes."""
    base = scratch("remotes")
    env = git_env(base)
    files = {
        ".claude": {"plans/README": "plans\n"},
        "Research/Environment": {"README.md": "environment\n"},
        "Research/Harness": {"README.md": "harness\n"},
        "Research/.meta": {"Books/CLAUDE.md": "books\n", "Packages/CLAUDE.md": "packages\n",
                           ".kaimon/tools.json": "{}\n"},
    }
    heads = {}
    for rel, key in CLONE_KEYS.items():
        heads[rel], _ = make_remote(base, env, f"{key}.git", files[rel])
    rewrites = {f"{base}/{CLONE_KEYS[rel]}.git": url for rel, url in clone_urls().items()}
    return base, heads, rewrites


def clone_home(rewrites):
    home = scratch("home")
    bindir = home / ".test-bin"
    logging_stubs(home, bindir)
    gitconfig = write_gitconfig(home / ".gitconfig-test", rewrites)
    return home, environment(home, bindir, gitconfig)


def test_clones():
    print("\n== check 2: the clones")
    _, heads, rewrites = clone_fixture()
    text = rendered(CLONES, LINUX_HOST, "linux", "/home/example")

    home, env = clone_home(rewrites)
    result = run_script(text, env)
    if not check(result.returncode == 0, f"fresh home: exit {result.returncode}"):
        print(result.stderr)
    for rel, url in clone_urls().items():
        d = home / rel
        if not (d / ".git").is_dir():
            fail(f"fresh home: {rel} is not a clone")
            continue
        origin = git(env, "--git-dir", str(d / ".git"), "config", "--get", "remote.origin.url")
        head = git(env, "--git-dir", str(d / ".git"), "rev-parse", "HEAD")
        check(origin == url and head == heads[rel], f"fresh home: {rel} is a clone of {url}")
    meta = home / "Research/.meta/.git"
    check(git(env, "--git-dir", str(meta), "config", "--get", "core.worktree") == str(home / "Research"),
          "fresh home: the meta repository's work tree is ~/Research")
    check((home / "Research/Books/CLAUDE.md").read_text() == "books\n"
          and (home / "Research/.kaimon/tools.json").is_file(),
          "fresh home: the meta repository's files are in ~/Research")
    status = subprocess.run(["git", "--git-dir", str(meta), "status", "--porcelain",
                             "--untracked-files=no"], capture_output=True, text=True, env=env,
                            cwd=home / "Research")
    check(status.returncode == 0 and status.stdout == "", "fresh home: the meta checkout is clean")

    before = tree(home)
    result = run_script(text, env)
    after = tree(home)
    for log in ("chsh.log",):
        after.pop(log, None)
    check(result.returncode == 0 and result.stdout.count("skipped") == 3 and after == before,
          f"second run: exit {result.returncode}, the three clones skipped, nothing changed")

    # Each directory that exists and is not a clone of its remote stops the run before the first
    # clone, and stays as it was.
    for rel, url in clone_urls().items():
        for kind in ("non-empty", "empty", "another remote"):
            home, env = clone_home(rewrites)
            d = home / rel
            d.mkdir(parents=True)
            if kind == "non-empty":
                (d / "keep.txt").write_text("keep\n")
            elif kind == "another remote":
                git(env, "init", "-q", str(d))
                git(env, "--git-dir", str(d / ".git"), "remote", "add", "origin",
                    "https://example.invalid/other.git")
            before = tree(d)
            result = run_script(text, env)
            others = [r for r in CLONE_KEYS if r != rel and (home / r / ".git").exists()]
            check(result.returncode != 0
                  and f"{d} exists and is not a clone of {url}" in result.stderr
                  and tree(d) == before and not others,
                  f"{rel} {kind}: exit {result.returncode}, the stop names it, it is unchanged, "
                  f"no other clone made (made: {others})")

    # A file in the way of the meta checkout stops the run; once it is gone, a second run
    # completes the checkout.
    home, env = clone_home(rewrites)
    blocker = home / "Research/Books/CLAUDE.md"
    blocker.parent.mkdir(parents=True)
    blocker.write_text("mine\n")
    result = run_script(text, env)
    check(result.returncode != 0 and blocker.read_text() == "mine\n",
          f"a file in the way of the meta checkout: exit {result.returncode}, the file kept")
    blocker.unlink()
    result = run_script(text, env)
    check(result.returncode == 0 and blocker.read_text() == "books\n"
          and (home / "Research/Packages/CLAUDE.md").read_text() == "packages\n",
          f"the run after it: exit {result.returncode}, the meta checkout complete")

    # A remote that does not answer fails the run.
    home, env = clone_home({f"{ROOT}/no-such-remotes/{CLONE_KEYS[rel]}.git": url
                            for rel, url in clone_urls().items()})
    result = run_script(text, env)
    check(result.returncode != 0 and not (home / ".claude/.git").exists(),
          f"no remote: exit {result.returncode}, no clone")


# ----------------------------------------------------------------- check 3 ----

def test_harness():
    print("\n== check 3: the harness at its pin")
    harness_stub = '#!/bin/sh\necho "$*" >> "$HOME/harness.log"\n'

    def fixture():
        base = scratch("remotes")
        genv = git_env(base)
        first, work = make_remote(base, genv, "ResearchHarness.git",
                                  {"bin/harness": harness_stub, "README.md": "one\n"})
        home = scratch("home")
        bindir = home / ".test-bin"
        logging_stubs(home, bindir)
        env = environment(home, bindir, write_gitconfig(home / ".gitconfig-test", {}))
        checkout = home / "Research/Harness"
        checkout.parent.mkdir(parents=True)
        git(env, "clone", "-q", str(base / "ResearchHarness.git"), str(checkout))
        # The pin reaches the remote after the clone: only a fetch brings it.
        pin = add_commit(genv, work, base / "ResearchHarness.git", "README.md", "two\n")
        return home, env, checkout, first, pin

    def head(env, checkout):
        return git(env, "rev-parse", "HEAD", cwd=checkout)

    home, env, checkout, first, pin = fixture()
    text = rendered(HARNESS, LINUX_HOST, "linux", home, {"harness_commit": pin})
    result = run_script(text, env)
    log = home / "harness.log"
    check(result.returncode == 0 and head(env, checkout) == pin
          and log.read_text() == "install --apply\n",
          f"clean checkout: exit {result.returncode}, HEAD at the pin, `harness install --apply` ran")
    result = run_script(text, env)
    check(result.returncode == 0 and log.read_text() == "install --apply\n" * 2,
          f"second run at the pin: exit {result.returncode}, the install runs again")

    for kind in ("modified", "untracked"):
        home, env, checkout, first, pin = fixture()
        text = rendered(HARNESS, LINUX_HOST, "linux", home, {"harness_commit": pin})
        target = checkout / ("README.md" if kind == "modified" else "notes.txt")
        target.write_text("local work\n")
        result = run_script(text, env)
        check(result.returncode != 0 and "has local changes" in result.stderr
              and head(env, checkout) == first and target.read_text() == "local work\n"
              and not (home / "harness.log").exists(),
              f"{kind} file: exit {result.returncode}, stopped before the checkout, no install")

    home, env, checkout, first, pin = fixture()
    text = rendered(HARNESS, LINUX_HOST, "linux", home, {"harness_commit": "0" * 40})
    result = run_script(text, env)
    check(result.returncode != 0 and head(env, checkout) == first
          and not (home / "harness.log").exists(),
          f"a pin the remote lacks: exit {result.returncode}, no checkout, no install")

    # The template host: the development checkout, never moved.
    template = DATA["template_host"]
    template_os = DATA["machines"][template]["os"]
    home, env, checkout, first, pin = fixture()
    git(env, "config", "user.name", "test", cwd=checkout)
    git(env, "config", "user.email", "test@example.invalid", cwd=checkout)
    (checkout / "local.txt").write_text("committed here\n")
    git(env, "add", "local.txt", cwd=checkout)
    git(env, "commit", "-qm", "ahead of the pin", cwd=checkout)
    ahead = head(env, checkout)
    (checkout / "README.md").write_text("local work\n")
    (checkout / "notes.txt").write_text("untracked\n")
    text = rendered(HARNESS, template, template_os, home, {"harness_commit": first})
    result = run_script(text, env)
    check(result.returncode == 0 and head(env, checkout) == ahead
          and git(env, "symbolic-ref", "--short", "HEAD", cwd=checkout) == "master"
          and (checkout / "README.md").read_text() == "local work\n"
          and (checkout / "notes.txt").is_file()
          and (home / "harness.log").read_text() == "install --apply\n",
          f"template host, HEAD contains the pin, local changes: exit {result.returncode}, "
          "the install ran, HEAD and the branch unchanged, the changes kept")

    home, env, checkout, first, pin = fixture()
    text = rendered(HARNESS, template, template_os, home, {"harness_commit": pin})
    result = run_script(text, env)
    check(result.returncode == 1 and "does not contain the pin" in result.stderr
          and head(env, checkout) == first and not (home / "harness.log").exists(),
          f"template host, HEAD lacks the pin: exit {result.returncode}, stopped, no install, "
          "HEAD unchanged")

    home, env, checkout, first, pin = fixture()
    git(env, "remote", "set-url", "origin", str(ROOT / "no-such-remote.git"), cwd=checkout)
    text = rendered(HARNESS, LINUX_HOST, "linux", home, {"harness_commit": pin})
    result = run_script(text, env)
    check(result.returncode != 0 and head(env, checkout) == first
          and not (home / "harness.log").exists(),
          f"no remote: exit {result.returncode}, no checkout, no install")


# ----------------------------------------------------------------- check 4 ----

# The package set of .chezmoidata/julia.toml, written out here so that the check does not take
# the set from the file it checks: each package and its minimum channel.
JULIA_PACKAGES = dict.fromkeys(
    ["Adapt", "Aqua", "Cthulhu", "DocumenterTools", "ExplicitImports", "JET", "JSON",
     "JuliaFormatter", "JuliaSyntax", "PkgTemplates", "Revise", "TestEnv", "YAML"], "1.10")
JULIA_PACKAGES["KaimonGate"] = "1.12"
UUID = '"00000000-0000-0000-0000-000000000000"'
PKG_ADD = re.compile(r"^julia \+(\S+) --startup-file=no -e using Pkg; Pkg\.add\((.*)\)$")


def julia_home(installed=(), envs=None, kaimon=False, julia_exit=0):
    """A scratch home with juliaup and julia stubs; `envs` maps a channel to its Project.toml."""
    home = scratch("home")
    bindir = home / ".test-bin"
    logging_stubs(home, bindir)
    jbin = home / ".juliaup/bin"
    stub(jbin, "juliaup", 'echo "juliaup $*" >> "$HOME/julia.log"')
    stub(jbin, "julia", f'echo "julia $*" >> "$HOME/julia.log"\nexit {julia_exit}')
    if installed:
        record = home / ".julia/juliaup/juliaup.json"
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({"Default": "release",
                                      "InstalledChannels": {c: {} for c in installed}}))
    for channel, text in (envs or {}).items():
        project = home / f".julia/environments/v{channel}/Project.toml"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_text(text)
    if kaimon:
        stub(home / ".julia/bin", "kaimon", "exit 0")
        (home / ".julia/environments/apps/Kaimon").mkdir(parents=True)
    return home, environment(home, bindir)


def project_toml(deps, compat=()):
    """A Project.toml whose [deps] table holds `deps` and whose [compat] table holds `compat`."""
    lines = ["[deps]"] + [f"{name} = {UUID}" for name in deps]
    if compat:
        lines += ["", "[compat]"] + [f'{name} = "1"' for name in compat]
    return "\n".join(lines) + "\n"


def julia_log(home):
    path = home / "julia.log"
    return path.read_text().splitlines() if path.exists() else []


def julia_calls(home):
    """The stubs' log, split: the juliaup lines, the Pkg.add calls by channel, the rest."""
    juliaup, adds, other = [], {}, []
    for line in julia_log(home):
        match = PKG_ADD.match(line)
        if line.startswith("juliaup "):
            juliaup.append(line)
        elif match:
            names = json.loads(match[2])
            adds.setdefault(match[1], []).append(sorted([names] if isinstance(names, str) else names))
        else:
            other.append(line)
    return juliaup, adds, other


def is_xy(channel):
    parts = channel.split(".")
    return len(parts) == 2 and all(p.isdigit() for p in parts)


def expected_adds(channels, package, present=None):
    """The one Pkg.add of each X.Y channel: the set up to the channel and the GPU package, minus
    the packages in `present[channel]`; no entry for a channel with nothing missing."""
    adds = {}
    for c in channels:
        if not is_xy(c):
            continue
        version = tuple(int(p) for p in c.split("."))
        wanted = {name for name, minimum in JULIA_PACKAGES.items()
                  if tuple(int(p) for p in minimum.split(".")) <= version}
        if package:
            wanted.add(package)
        wanted -= set((present or {}).get(c, ()))
        if wanted:
            adds[c] = [sorted(wanted)]
    return adds


def expected_juliaup(channels, default, skip_channels=()):
    return [f"juliaup add {c}" for c in channels if c not in skip_channels] + [
        f"juliaup default {default}"]


def kaimon_line(default):
    return f'julia +{default} --startup-file=no -e using Pkg; Pkg.Apps.add("Kaimon")'


def check_julia_run(label, result, home, channels, default, package, present=None,
                    skip_channels=(), kaimon=False):
    """The run exits 0; juliaup adds the missing channels and sets the default; each X.Y channel
    gets one Pkg.add of exactly its missing packages; the Kaimon app unless it is there."""
    juliaup, adds, other = julia_calls(home)
    want_adds = expected_adds(channels, package, present)
    want_other = [] if kaimon else [kaimon_line(default)]
    good = (result.returncode == 0
            and juliaup == expected_juliaup(channels, default, skip_channels)
            and adds == want_adds and other == want_other)
    got = "" if good else f"; got juliaup {juliaup}, adds {adds}, other {other}, {result.stderr.strip()}"
    check(good, f"{label}: exit {result.returncode}, one Pkg.add on "
                f"{sorted(want_adds) or 'no channel'}{got}")
    return adds


def test_julia_packages_file():
    print("\n== check 4: the package set of .chezmoidata/julia.toml")
    path = SOURCE / ".chezmoidata" / "julia.toml"
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    check(data.get("julia_packages") == JULIA_PACKAGES,
          f"julia_packages holds the 14 packages and their minimum channels: {data}")
    check(list(data) == ["julia_packages"] and not set(data) & set(DATA),
          "julia.toml has the one top-level key julia_packages, which machines.toml lacks")
    check(any(line.startswith("#") for line in path.read_text().splitlines()),
          "julia.toml carries a comment")


def test_julia():
    print("\n== check 4: Julia")
    five = ["1.10", "1.11", "1.12", "1.13", "nightly"]
    hosts = {f"test-julia-{gpu}": {"os": "linux", "arch": "x86_64", "gpu": gpu,
                                   "julia_channels": five, "julia_default": "1.13"}
             for gpu in GPU_PACKAGE}
    odd = {"os": "linux", "arch": "x86_64", "gpu": "cuda", "julia_default": "1.12",
           "julia_channels": ["1.12", "release", "lts", "1.13.1", "nightly", "1.x"]}
    extra = {"machines": dict(hosts, **{"test-julia-odd": odd})}

    # Empty environments: 1.10 and 1.11 get the 13 packages of minimum 1.10, 1.12 and 1.13 the
    # 14, each with the GPU package; nightly nothing.
    for host, entry in hosts.items():
        package = GPU_PACKAGE[entry["gpu"]]
        home, env = julia_home()
        result = run_script(rendered(JULIA, host, "linux", home, extra), env)
        adds = check_julia_run(f"{host}, empty environments", result, home, five, "1.13", package)
        gpu = 1 if package else 0
        check([len(adds.get(c, [[]])[0]) for c in five] == [13 + gpu, 13 + gpu, 14 + gpu,
                                                             14 + gpu, 0],
              f"{host}: 1.10, 1.11, 1.12, 1.13, nightly get {13 + gpu}, {13 + gpu}, {14 + gpu}, "
              f"{14 + gpu}, 0 packages")
        check(all(package in adds[c][0] for c in five[:4]) if package
              else not any(n not in JULIA_PACKAGES for c in adds for n in adds[c][0]),
              f"{host}: {'the GPU package ' + package if package else 'no GPU package'} "
              "in each X.Y channel's call")
        check("chezmoi: KaimonGate needs Julia 1.12; skipped on Julia 1.10." in result.stdout
              and "skipped on Julia 1.12" not in result.stdout,
              f"{host}: the skip of KaimonGate below 1.12 names the package, the channel and "
              "the minimum")

    # Every host of machines.toml, with empty environments.
    for host, entry in DATA["machines"].items():
        home, env = julia_home()
        result = run_script(rendered(JULIA, host, entry["os"], home), env)
        check_julia_run(f"{host} (gpu {entry['gpu']}), empty environments", result, home,
                        entry["julia_channels"], entry["julia_default"], GPU_PACKAGE[entry["gpu"]])

    # A channel that is not X.Y gets no package.
    home, env = julia_home()
    result = run_script(rendered(JULIA, "test-julia-odd", "linux", home, extra), env)
    adds = check_julia_run("channels 1.12, release, lts, 1.13.1, nightly, 1.x", result, home,
                           odd["julia_channels"], "1.12", "CUDA")
    check(list(adds) == ["1.12"], f"only 1.12 gets a Pkg.add: {sorted(adds)}")

    # Some packages present in [deps]: only the rest.
    present = {"1.12": ["Aqua", "JET", "CUDA", "KaimonGate"], "1.10": ["Revise"]}
    home, env = julia_home(envs={c: project_toml(names) for c, names in present.items()})
    result = run_script(rendered(JULIA, "test-julia-cuda", "linux", home, extra), env)
    check_julia_run("some packages in [deps] of 1.10 and 1.12", result, home, five, "1.13",
                    "CUDA", present)

    # Every package present: no Pkg.add, and a skipped line per X.Y channel.
    every = {c: list(JULIA_PACKAGES) + ["CUDA"] for c in five[:4]}
    home, env = julia_home(envs={c: project_toml(names) for c, names in every.items()},
                           kaimon=True)
    result = run_script(rendered(JULIA, "test-julia-cuda", "linux", home, extra), env)
    check_julia_run("every package present", result, home, five, "1.13", "CUDA", every,
                    kaimon=True)
    check(not any("Pkg.add(" in line for line in julia_log(home))
          and all(f"global environment of Julia {c} holds every package; skipped." in result.stdout
                  for c in five[:4]),
          "every package present: no Pkg.add, a skipped line for each X.Y channel")

    # A name under [compat] only, or in a comment, counts as missing.
    text = project_toml(["Aqua"], compat=["Revise", "JET"]) + "# YAML = " + UUID + "\n"
    home, env = julia_home(envs={"1.13": text})
    result = run_script(rendered(JULIA, "test-julia-cuda", "linux", home, extra), env)
    adds = check_julia_run("1.13 with Aqua in [deps], Revise and JET in [compat], YAML in a "
                           "comment", result, home, five, "1.13", "CUDA", {"1.13": ["Aqua"]})
    check(all(n in adds.get("1.13", [[]])[0] for n in ("Revise", "JET", "YAML"))
          and "Aqua" not in adds.get("1.13", [[]])[0],
          "a package named only under [compat] or in a comment counts as missing")

    # The template host with some channels installed, its GPU package in 1.10, and the Kaimon app.
    entry = DATA["machines"][TEMPLATE_HOST]
    package = GPU_PACKAGE[entry["gpu"]]
    in_110 = {"1.10": [package]} if package else {}
    home, env = julia_home(installed=("1.10", "1.13", "release"),
                           envs={c: project_toml(names) for c, names in in_110.items()}, kaimon=True)
    result = run_script(rendered(JULIA, TEMPLATE_HOST, entry["os"], home), env)
    check_julia_run(f"{TEMPLATE_HOST} with 1.10, 1.13 and release installed, {package} in 1.10 and "
                    "Kaimon", result, home, entry["julia_channels"], entry["julia_default"], package,
                    in_110, skip_channels=("1.10", "1.13", "release"), kaimon=True)

    home, env = julia_home()
    shutil.rmtree(home / ".juliaup")
    result = run_script(rendered(JULIA, LINUX_HOST, "linux", home), env)
    check(result.returncode == 1 and ".juliaup/bin/juliaup does not exist" in result.stderr,
          f"no ~/.juliaup/bin/juliaup: exit {result.returncode}, the stop names it")

    # A failing julia stops the run at the first channel and names it.
    home, env = julia_home(julia_exit=1)
    result = run_script(rendered(JULIA, "test-julia-cuda", "linux", home, extra), env)
    juliaup, adds, other = julia_calls(home)
    check(result.returncode != 0 and "Julia 1.10" in result.stderr
          and list(adds) == ["1.10"] and len(adds["1.10"]) == 1 and not other,
          f"julia fails (as without a network): exit {result.returncode}, the stop names Julia "
          f"1.10, no later julia call: adds {sorted(adds)}, other {other}, "
          f"{result.stderr.strip()!r}")

    code, _, err = render(JULIA, "test-gpu-bad", "linux", "/home/example",
                          {"machines": {"test-gpu-bad": dict(odd, gpu="opencl")}})
    check(code != 0 and "opencl" in err, "an unknown gpu value fails the render")

    for minimum in ("1", "1.10.0", "latest", 1.1):
        code, _, err = render(JULIA, "test-julia-cuda", "linux", "/home/example",
                              dict(extra, julia_packages={"NotAPackage": minimum}))
        check(code != 0 and "NotAPackage" in err,
              f"a minimum {minimum!r} that is not X.Y fails the render and names the package: "
              f"{err.strip()!r}")


# ----------------------------------------------------------------- check 5 ----

def harness_clone(home, env, checkout, pin):
    """A scratch clone of the harness checkout `checkout` at `pin`."""
    target = home / "Research/Harness"
    target.parent.mkdir(parents=True, exist_ok=True)
    git(env, "clone", "-q", "--no-hardlinks", "--no-checkout", str(checkout), str(target))
    git(env, "checkout", "-q", "--detach", pin, cwd=target)
    return target


def services_home(host, os_name, checkout, pin, extra=None):
    home = scratch("home")
    bindir = home / ".test-bin"
    logging_stubs(home, bindir)
    env = environment(home, bindir, write_gitconfig(home / ".gitconfig-test", {}))
    harness = harness_clone(home, env, checkout, pin)
    profile = rendered_profile(host, os_name, home, extra)
    path = home / ".config/research-harness/profile.toml"
    path.parent.mkdir(parents=True)
    path.write_text(profile)
    return home, env, harness


def rendered_profile(host, os_name, home, extra=None):
    work = scratch("chezmoi")
    (work / "chezmoi.toml").write_text("")
    data = {"chezmoi": {"hostname": host, "os": os_name, "homeDir": str(home)}}
    data.update(extra or {})
    result = subprocess.run([
        "chezmoi", "--config", str(work / "chezmoi.toml"), "--source", str(SOURCE),
        "--destination", str(work / "home"), "--persistent-state", str(work / "state.boltdb"),
        "--no-tty", "--override-data", json.dumps(data), "execute-template"],
        capture_output=True, text=True,
        input=(SOURCE / "dot_config/research-harness/profile.toml.tmpl").read_text())
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def launchd_prefix(home):
    """The launchd_prefix of the profile in the scratch home."""
    with open(home / ".config/research-harness/profile.toml", "rb") as handle:
        return tomllib.load(handle)["launchd_prefix"]


def harness_render(env, harness, template):
    result = subprocess.run([str(harness / "bin/harness"), "render", str(harness / template)],
                            capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"harness render {template}: {result.stderr.strip()}")
    return result.stdout


def log_lines(home, name):
    path = home / f"{name}.log"
    return path.read_text().splitlines() if path.exists() else []


def check_copies(home, harness, label):
    claude = home / ".local/bin/claude-autocommit"
    update = home / ".local/bin/julia-update.jl"
    good = (claude.is_file() and update.is_file()
            and claude.read_bytes() == (harness / "launchagents/claude-autocommit").read_bytes()
            and update.read_bytes() == (harness / "scripts/julia-update.jl").read_bytes()
            and stat.S_IMODE(claude.stat().st_mode) == 0o755
            and stat.S_IMODE(update.stat().st_mode) == 0o644)
    check(good, f"{label}: the copies of claude-autocommit (755) and julia-update.jl (644) "
                "in ~/.local/bin equal the pinned harness's")


def test_services():
    print("\n== check 5: the services")
    checkout, pin = harness_source()
    if not (checkout / ".git").exists():
        fail(f"{checkout} is not a clone; the services test needs it (read-only)")
        return
    print(f"  the harness: {checkout} at {pin}")
    pinned = {"harness_commit": pin}

    # Linux.
    host = LINUX_HOST
    home, env, harness = services_home(host, "linux", checkout, pin, pinned)
    text = rendered(SERVICES, host, "linux", home, pinned)
    result = run_script(text, env)
    check(result.returncode == 0, f"linux: exit {result.returncode} {result.stderr.strip()}")
    check_copies(home, harness, "linux")
    units = home / ".config/systemd/user"
    for unit in UNITS:
        path = units / unit
        check(path.is_file() and path.read_text() == harness_render(env, harness, f"systemd/{unit}"),
              f"linux: {unit} equals `harness render systemd/{unit}`")
    autocommit = (units / "claude-autocommit.service").read_text()
    check(f"CLAUDE_AUTOCOMMIT_BRANCH=memory/{host}" in autocommit,
          f"linux: claude-autocommit.service pushes to memory/{host}")
    check(log_lines(home, "systemctl") == [
        "--user daemon-reload",
        "--user enable --now kaimon.service julia-update.timer claude-autocommit.timer",
        "--user restart kaimon.service julia-update.timer claude-autocommit.timer"],
        "linux: daemon-reload, then enable --now and restart the service and the two timers")
    check(not log_lines(home, "launchctl") and not (home / "Library").exists(),
          "linux: no launchctl, no ~/Library")

    # macOS, the template host.
    host = TEMPLATE_HOST
    for loaded in (False, True):
        home, env, harness = services_home(host, "darwin", checkout, pin, pinned)
        prefix = launchd_prefix(home)
        labels = [f"{prefix}.{job}" for job in JOBS]
        if loaded:
            (home / "loaded").write_text("\n".join(labels) + "\n")
        text = rendered(SERVICES, host, "darwin", home, pinned)
        result = run_script(text, env)
        state = "loaded" if loaded else "not loaded"
        check(result.returncode == 0, f"macOS template host, jobs {state}: exit "
                                      f"{result.returncode} {result.stderr.strip()}")
        check_copies(home, harness, f"macOS, jobs {state}")
        agents = home / "Library/LaunchAgents"
        for job in JOBS:
            path = agents / f"{prefix}.{job}.plist"
            check(path.is_file()
                  and path.read_text() == harness_render(env, harness, f"launchagents/{job}.plist")
                  and (home / "Library/Logs" / job).is_dir(),
                  f"macOS: {path.name} equals `harness render launchagents/{job}.plist`, "
                  "its log directory exists")
        domain = f"gui/{os.getuid()}"
        want = []
        for label in labels:
            want.append(f"print {domain}/{label}")
            if loaded:
                want += [f"bootout {domain}/{label}", f"print {domain}/{label}"]
            want.append(f"bootstrap {domain} {agents / (label + '.plist')}")
        got = log_lines(home, "launchctl")
        then = "bootout, then " if loaded else ""
        check(got == want, f"macOS, jobs {state}: {then}bootstrap of each job"
                           f"{'' if got == want else f'; got {got}'}")
        check(sorted((home / "loaded").read_text().split()) == sorted(labels),
              f"macOS, jobs {state}: every job loaded at the end")
        check(not log_lines(home, "systemctl"), "macOS: no systemctl")
        autocommit = (agents / f"{prefix}.claude-autocommit.plist").read_text()
        check("<string>main</string>" in autocommit,
              "macOS template host: claude-autocommit pushes to main")

    # macOS, not the template host.
    mac = {"machines": {"test-second-mac": dict(DATA["machines"][TEMPLATE_HOST])}, **pinned}
    home, env, harness = services_home("test-second-mac", "darwin", checkout, pin, mac)
    prefix = launchd_prefix(home)
    result = run_script(rendered(SERVICES, "test-second-mac", "darwin", home, mac), env)
    check(result.returncode == 0 and len(log_lines(home, "launchctl")) == 2 * len(JOBS),
          f"macOS, another host: exit {result.returncode}, three jobs")
    autocommit = (home / f"Library/LaunchAgents/{prefix}.claude-autocommit.plist").read_text()
    check("<string>memory/test-second-mac</string>" in autocommit,
          "macOS, another host: claude-autocommit pushes to memory/test-second-mac")

    # A bootout that launchd finishes late: each job stays listed for three `print`s after its
    # bootout, and the first bootstrap fails. The script waits, tries again, and loads every job;
    # without the wait it bootstraps a listed job and stops.
    labels = [f"{prefix}.{job}" for job in JOBS]
    text = rendered(SERVICES, "test-second-mac", "darwin", home, mac)
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.strip() == "tries=0")
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "done")
    no_wait = "".join(lines[:start] + lines[end + 1:])
    for name, script in (("the script", text), ("a mutant with no wait", no_wait)):
        home, env, harness = services_home("test-second-mac", "darwin", checkout, pin, mac)
        (home / "loaded").write_text("\n".join(labels) + "\n")
        (home / "linger").write_text("3\n")
        (home / "bootstrap-failures").write_text("1\n")
        result = run_script(script, env)
        loaded = sorted((home / "loaded").read_text().split())
        if script is text:
            check(result.returncode == 0 and loaded == sorted(labels),
                  f"a late bootout and a failed first bootstrap, {name}: exit "
                  f"{result.returncode}, every job loaded {result.stderr.strip()}")
        else:
            check(result.returncode == 1 and labels[0] not in loaded
                  and f"bootstrap of {labels[0]} failed: Bootstrap failed: 5" in result.stderr,
                  f"a late bootout, {name}: exit {result.returncode}, {labels[0]} not loaded, "
                  f"the stop names it: {result.stderr.strip()}")

    # The run_onchange key: the text changes with the pin and with the profile.
    base = rendered(SERVICES, LINUX_HOST, "linux", "/home/example")
    other_pin = rendered(SERVICES, LINUX_HOST, "linux", "/home/example", {"harness_commit": "1" * 40})
    other_profile = rendered(SERVICES, LINUX_HOST, "linux", "/home/example/other")
    check(base != other_pin and base != other_profile,
          "the services script's text changes with harness_commit and with the profile")


# ----------------------------------------------------------------- check 6 ----

def test_lint():
    print("\n== check 6: bash -n and shellcheck on every script, for every host")
    scripts = sorted(p.name for p in SCRIPTS.iterdir())
    check(scripts == sorted([TOOL_CHECK, CLONES, JULIA, HARNESS, SERVICES]),
          f"the scripts are the five of the kit: {scripts}")
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        fail("shellcheck is not installed")
    forbidden = ["sudo", "| sh", "|sh", "| bash", "|bash", "api-keys", "id_ed25519", "id_rsa",
                 "secret-tool store", "add-generic-password"]
    for host, entry in DATA["machines"].items():
        home = "/Users/me" if entry["os"] == "darwin" else "/home/example"
        before = len(failures)
        for script in scripts:
            text = rendered(script, host, entry["os"], home)
            path = scratch("lint") / script.removesuffix(".tmpl")
            path.write_text(text)
            syntax = subprocess.run(["/bin/bash", "-n", str(path)], capture_output=True, text=True)
            lint = (subprocess.run([shellcheck, "-s", "bash", str(path)], capture_output=True,
                                   text=True) if shellcheck else None)
            hits = [f for f in forbidden if f in text]
            chsh = [line for line in text.splitlines()
                    if "chsh" in line and not line.lstrip().startswith(("#", "echo"))]
            good = (syntax.returncode == 0 and lint is not None and lint.returncode == 0
                    and text.startswith("#!/bin/bash\n") and not hits and not chsh
                    and "curl" not in text.replace('tools="git zsh curl', ""))
            if not good:
                detail = (syntax.stderr + (lint.stdout if lint else "")).strip()
                fail(f"{host} {script}: bash -n {syntax.returncode}, shellcheck "
                     f"{lint.returncode if lint else 'missing'}, forbidden {hits}, chsh {chsh}\n{detail}")
        if len(failures) == before:
            ok(f"{host}: {len(scripts)} scripts pass bash -n and shellcheck, name no sudo, "
               "no pipe into a shell, no key file, run no chsh")


def main():
    global ROOT
    if LINUX_HOST is None:
        fail(f"machines.toml lists no Linux host besides the template host {TEMPLATE_HOST}")
        print(f"\nscript-check: {len(failures)} failure(s)")
        return 1
    with tempfile.TemporaryDirectory(prefix="script-check-") as tmp:
        ROOT = pathlib.Path(tmp).resolve()
        for test in (test_tool_check, test_clones, test_harness, test_julia_packages_file,
                     test_julia, test_services, test_lint):
            try:
                test()
            except Exception as error:  # a broken fixture is a failure, not a crash
                fail(f"{test.__name__}: {type(error).__name__}: {error}")
    if failures:
        print(f"\nscript-check: {len(failures)} failure(s)")
        return 1
    print("\nscript-check: all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
