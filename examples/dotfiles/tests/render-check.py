#!/usr/bin/env python3
"""Render this chezmoi source once per host of .chezmoidata/machines.toml, and check the render
of each target of the kit.

Run it with Python 3.11 or later (it needs tomllib), from any directory:

    python3 tests/render-check.py

Every chezmoi call gets its own --config, --source, --destination and --persistent-state in a
scratch directory under $TMPDIR. The check never reads ~/.config/chezmoi and never writes the
home directory; it reads the live files only to compare them with the render of this machine.

The checks read the targets of the kit alone, KIT_TARGETS and dotfiles-merge: a source that
copies the kit may render more targets, and the check allows them.

Checks, per host, numbered as the comments that open each check in the code:
  1. `chezmoi managed` lists every target of the kit for the host, and they render;
     dotfiles-merge only on template_host.
  2. The render of the machine that runs the check equals its live files, for the kit's targets.
  3. A Linux render of a kit target holds no "/Users/" and no "/opt/homebrew"; a macOS render
     holds no "/home/".
  4. The rendered profile.toml, models.toml, network.toml, providers.toml and repositories.toml
     parse with tomllib, and the profile names autocommit_branch `memory/<host>` on every host
     but template_host, which names none.
  5. SSH_SK_PROVIDER appears in no rendered kit target but .local/bin/dotfiles-merge, which only
     template_host receives; the scripts in .local/bin are executable.
And: template_host is a host of machines.toml.
And: a hostname that machines.toml does not list makes chezmoi fail with a message that names it,
in the whole render and in every template that reads the host data.
"""

import difflib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib

SOURCE = pathlib.Path(__file__).resolve().parent.parent
FAKE_HOST = "not-a-listed-host"
HOST_LOOKUP = 'includeTemplate "host"'

KIT_TARGETS = [
    ".config/research-harness/profile.toml",
    ".config/research-harness/models.toml",
    ".config/research-harness/network.toml",
    ".config/research-harness/providers.toml",
    ".config/research-harness/repositories.toml",
    ".config/git/allowed_signers",
    ".local/bin/dotfiles",
    ".local/bin/dotfiles-update",
    ".local/bin/dotfiles-check",
]
MERGE_SCRIPT = ".local/bin/dotfiles-merge"
SK_PROVIDER = "SSH_SK_PROVIDER"
FORBIDDEN = {"darwin": ["/home/"], "linux": ["/Users/", "/opt/homebrew"]}
TOML_TARGETS = [
    ".config/research-harness/profile.toml",
    ".config/research-harness/models.toml",
    ".config/research-harness/network.toml",
    ".config/research-harness/providers.toml",
    ".config/research-harness/repositories.toml",
]

failures = []


def fail(message):
    failures.append(message)
    print(f"  FAIL: {message}")


def expected_files(host, template_host):
    files = list(KIT_TARGETS)
    if host == template_host:
        files.append(MERGE_SCRIPT)
    return files


def expected_managed(files):
    """The files and every directory above them, as `chezmoi managed` lists them."""
    entries = set(files)
    for f in files:
        parent = pathlib.PurePosixPath(f).parent
        while str(parent) != ".":
            entries.add(str(parent))
            parent = parent.parent
    return entries


def chezmoi(work, args, data=None, stdin=None):
    """Run chezmoi with every state path in the scratch directory `work`.

    `apply` and `managed` exclude the scripts of .chezmoiscripts: a script acts on $HOME, which
    is the real home directory here, and tests/script-check.py tests the scripts on their own."""
    if args and args[0] in ("apply", "managed"):
        args = [args[0], "--exclude=scripts", *args[1:]]
    cmd = [
        "chezmoi",
        "--config",
        str(work / "chezmoi.toml"),
        "--source",
        str(SOURCE),
        "--destination",
        str(work / "home"),
        "--persistent-state",
        str(work / "state.boltdb"),
        "--no-tty",
    ]
    if data is not None:
        cmd += ["--override-data", json.dumps(data)]
    return subprocess.run(cmd + args, capture_output=True, text=True, input=stdin, check=False, timeout=60)


def scratch(root, name):
    work = root / name
    (work / "home").mkdir(parents=True)
    (work / "chezmoi.toml").write_text("")
    return work


def override(host, os_name, home):
    return {"chezmoi": {"hostname": host, "os": os_name, "homeDir": home}}


def check_host(root, data, live_home, template_host):
    """The checks of one host, whose `override` is `data`."""
    host, os_name, home = (data["chezmoi"][k] for k in ("hostname", "os", "homeDir"))
    print(f"\n== {host} ({os_name}, home {home})")
    work = scratch(root, host)

    applied = chezmoi(work, ["apply"], data)
    if applied.returncode != 0:
        fail(f"{host}: chezmoi apply exited {applied.returncode}: {applied.stderr.strip()}")
        return

    files = expected_files(host, template_host)
    dest = work / "home"
    if not check_managed(work, data, files, template_host):
        return
    check_other_os(host, os_name, dest, files)
    check_toml(host, dest, template_host)
    check_provider(host, dest, files, template_host)
    if live_home is not None:
        check_live(host, dest, files, live_home)


def check_managed(work, data, files, template_host):
    """Check 1: the managed targets of the kit, and they render. A target outside the kit is
    allowed. False when `chezmoi managed` fails."""
    host = data["chezmoi"]["hostname"]
    managed = chezmoi(work, ["managed"], data)
    if managed.returncode != 0:
        fail(f"{host}: chezmoi managed exited {managed.returncode}: {managed.stderr.strip()}")
        return False
    listed = [line for line in managed.stdout.splitlines() if line]
    print("  chezmoi managed:")
    for line in listed:
        print(f"    {line}")
    want = expected_managed(files)
    got = set(listed)
    if not want <= got:
        fail(f"{host}: chezmoi managed lacks the kit's targets {sorted(want - got)}")
    if host != template_host and MERGE_SCRIPT in got:
        fail(f"{host}: chezmoi managed lists {MERGE_SCRIPT} on a host that is not template_host")
    dest = work / "home"
    for f in files:
        if not (dest / f).is_file():
            fail(f"{host}: {f} is not rendered")
    return True


def check_other_os(host, os_name, dest, files):
    """Check 3: no path of the other OS."""
    hits = []
    for f in files:
        path = dest / f
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            hits.extend(f"{f}:{number}: {bad}" for bad in FORBIDDEN[os_name] if bad in line)
    if hits:
        fail(f"{host}: the render names a path of the other OS: {hits}")
    else:
        print(f"  no {' or '.join(FORBIDDEN[os_name])} in the kit's targets")


def check_toml(host, dest, template_host):
    """Check 4: the TOML files parse, and the profile names the host's autocommit branch."""
    parsed = {}
    for f in TOML_TARGETS:
        try:
            with (dest / f).open("rb") as handle:
                parsed[f] = tomllib.load(handle)
            print(f"  {f} parses")
        except (OSError, tomllib.TOMLDecodeError) as error:
            fail(f"{host}: {f} does not parse: {error}")

    # claude-autocommit pushes `main` on the template host and `memory/<host>` elsewhere. The
    # template host's profile names no branch, so the harness's default `main` applies.
    profile = parsed.get(TOML_TARGETS[0])
    if profile is not None:
        want = None if host == template_host else f"memory/{host}"
        got = profile.get("autocommit_branch")
        if got != want:
            fail(f"{host}: the profile's autocommit_branch is {got!r}, expected {want!r}")
        else:
            print(f"  autocommit_branch: {got or 'none, so main'}")


def check_provider(host, dest, files, template_host):
    """Check 5: SSH_SK_PROVIDER only in dotfiles-merge; the scripts are executable."""
    provider = [
        f for f in files if (dest / f).is_file() and SK_PROVIDER in (dest / f).read_text(errors="replace")
    ]
    want_provider = [MERGE_SCRIPT] if host == template_host else []
    if sorted(provider) != want_provider:
        fail(f"{host}: {SK_PROVIDER} appears in {sorted(provider)}, expected {want_provider}")
    else:
        print(f"  {SK_PROVIDER} appears in {want_provider or 'no rendered kit target'}")
    for f in files:
        if f.startswith(".local/bin/") and (dest / f).is_file() and not os.access(dest / f, os.X_OK):
            fail(f"{host}: {f} is not executable")


def check_live(host, dest, files, live_home):
    """Check 2: the render of this machine equals its live files. Read-only on the live side."""
    before = len(failures)
    for f in files:
        rendered, live = dest / f, live_home / f
        if not live.is_file():
            fail(f"{host}: the live file {live} does not exist")
            continue
        if not rendered.is_file():
            continue
        if rendered.read_bytes() != live.read_bytes():
            diff = difflib.unified_diff(
                live.read_text(errors="replace").splitlines(keepends=True),
                rendered.read_text(errors="replace").splitlines(keepends=True),
                f"live/{f}",
                f"render/{f}",
            )
            fail(f"{host}: the render of {f} differs from the live file:\n{''.join(diff)}")
    if len(failures) == before:
        print(f"  the render equals the live files in {live_home} ({len(files)} files)")


def host_templates():
    """Every source template that reads the host data, and any that reads it around the lookup."""
    readers = []
    for dirpath, dirnames, names in os.walk(SOURCE):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".claude", "tests")]
        for name in names:
            path = pathlib.Path(dirpath, name)
            rel = path.relative_to(SOURCE)
            if rel.parts[0] == ".chezmoitemplates" or rel.parts[0] == ".chezmoidata":
                continue
            if not (name.endswith(".tmpl") or name == ".chezmoiignore"):
                continue
            text = path.read_text()
            if HOST_LOOKUP in text:
                readers.append(path)
            elif re.search(r"\.machines\b", text):
                fail(f"{rel} reads .machines without the host lookup, so an unknown host passes it")
    return sorted(readers)


def check_unknown_host(root):
    print(f"\n== unknown host {FAKE_HOST}")
    for os_name, home in (("darwin", "/Users/me"), ("linux", "/home/example")):
        work = scratch(root, f"{FAKE_HOST}-{os_name}")
        data = override(FAKE_HOST, os_name, home)
        for args in (["managed"], ["apply"]):
            result = chezmoi(work, args, data)
            if result.returncode == 0 or FAKE_HOST not in result.stderr:
                fail(
                    f"chezmoi {args[0]} ({os_name}) for {FAKE_HOST}: exit {result.returncode}, "
                    f"stderr does not name the host: {result.stderr.strip()!r}"
                )
            else:
                print(f"  chezmoi {args[0]} ({os_name}) fails: {result.stderr.strip()}")
    readers = host_templates()
    if not readers:
        fail("no template reads the host data through the lookup")
    work = scratch(root, f"{FAKE_HOST}-templates")
    data = override(FAKE_HOST, "linux", "/home/example")
    for path in readers:
        rel = path.relative_to(SOURCE)
        result = chezmoi(work, ["execute-template"], data, stdin=path.read_text())
        if result.returncode == 0 or FAKE_HOST not in result.stderr:
            fail(
                f"{rel} does not stop for {FAKE_HOST}: exit {result.returncode}, "
                f"stderr {result.stderr.strip()!r}"
            )
        else:
            print(f"  {rel} stops with chezmoi's fail")


def main():
    machines_file = SOURCE / ".chezmoidata" / "machines.toml"
    with machines_file.open("rb") as handle:
        data = tomllib.load(handle)
    machines = data["machines"]
    template_host = data.get("template_host")
    if template_host not in machines:
        fail(f"template_host {template_host!r} is not a host of machines.toml")

    with tempfile.TemporaryDirectory(prefix="render-check-") as tmp:
        root = pathlib.Path(tmp)
        probe = scratch(root, "probe")
        result = chezmoi(probe, ["execute-template", "{{ .chezmoi.hostname }}"])
        if result.returncode != 0:
            print(f"chezmoi does not run: {result.stderr.strip()}")
            return 1
        this_host = result.stdout.strip()
        live_home = pathlib.Path.home()
        user = live_home.name

        if this_host in machines:
            print(f"This machine is {this_host}: its render is compared with {live_home}.")
        else:
            print(
                f"This machine, {this_host}, is not in machines.toml: no render is compared with live files."
            )

        for host, entry in machines.items():
            os_name = entry["os"]
            if os_name not in FORBIDDEN:
                fail(f"{host}: os {os_name!r} is neither darwin nor linux")
                continue
            if host == this_host:
                home, live = str(live_home), live_home
            else:
                home = f"/Users/{user}" if os_name == "darwin" else f"/home/{user}"
                live = None
            check_host(root, override(host, os_name, home), live, template_host)

        check_unknown_host(root)

    if failures:
        print(f"\nrender-check: {len(failures)} failure(s)")
        return 1
    print(f"\nrender-check: all checks pass for {len(machines)} host(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
