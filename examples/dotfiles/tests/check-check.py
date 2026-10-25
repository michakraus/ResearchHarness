#!/usr/bin/env python3
"""Test dotfiles-check in scratch homes with stub commands, never against the home directory.

Run it with Python 3.11 or later, from any directory:

    python3 tests/check-check.py

It needs chezmoi, git, bash, ssh-keygen and shellcheck. The script is rendered with `chezmoi
execute-template` for a host (its own --config, --source, --destination and --persistent-state
under $TMPDIR), with the scratch harness checkout's first commit as harness_commit. Besides the
hosts of .chezmoidata/machines.toml, it renders for two hosts of its own, added as data: a Linux
host with an AMD GPU and a host with gpu none. Each case builds a machine under $TMPDIR: a bare
remote of the source and an author clone that commits and pushes; a scratch HOME whose
~/.local/share/chezmoi is a clone of the remote, with ~/.config/git/allowed_signers and a
~/Research/Harness of two commits, whose first holds a small kit in examples/dotfiles/ that the
source copies and whose second changes that kit; and stubs for `harness`, `chezmoi` and
~/.juliaup/bin/julia, which log their arguments outside HOME and print what the real programs
print. The keys are throwaway ed25519 keys that ssh-keygen makes in the run: "listed" is in the
applied allowed_signers, "other" is not.
Standard input is /dev/null.

Checks:
  2. The output has the form of `harness doctor`: check lines `STATUS  name  detail`, an empty
     line, and the count line that counts them. `harness doctor`'s lines come first, unchanged,
     and `--full` reaches it. Then `chezmoi verify --exclude=scripts`, an empty `chezmoi diff
     --exclude=scripts`, the signature of the source's HEAD by the applied allowed_signers, HEAD
     at origin/main as the last fetch saw it, the Harness checkout, the kit, and with --full
     Revise on each X.Y channel and the host's GPU package. The exit status is 0 without a FAIL
     line, 1 with one, 2 on a usage error. With standard input on an open pipe that nobody
     writes, it finishes and no program it runs gets that standard input; it writes nothing below
     HOME and fetches nothing.
  3. Each check PASS and FAIL; the template host (HEAD contains the pin) and another host (HEAD is
     the pin); an unsigned and a foreign-signed head; a source behind its origin (WARN); --full
     and not; a host with gpu none; the GPU answer read from standard output only; bash -n and
     shellcheck -S warning on the render for every host; a gpu outside metal, cuda, amdgpu and
     none stops the render.
  5. The kit line, on the template host (HEAD after the pin) and another host (HEAD the pin): PASS
     when every code file of the kit.toml at harness_commit equals the source's copy, and a seed
     that differs does not count; WARN that names each code file that differs or that the source
     lacks; WARN when that kit.toml has no line `"<path>" = "code"`; SKIP when harness_commit has
     no examples/dotfiles/kit.toml, and when the Harness checkout lacks harness_commit.
  6. kit.toml, where the source has one (the kit itself): each entry is a file of the kit with the
     class code or seed, each code entry is a line `"<path>" = "code"`, and every file outside
     tests/ and kit.toml that git tracks or would track is an entry.
  The decided edges: `harness` not on the PATH (a FAIL line, and the other checks still run);
  `harness doctor` exiting 1 (its FAIL lines count, exit 1); a command that the sandbox refuses
  (SKIP with the reason under $SANDBOX_RUNTIME, FAIL without); and the applied allowed_signers
  only, never the source's copy.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

SOURCE = pathlib.Path(__file__).resolve().parent.parent
CHECK = SOURCE / "dot_local" / "bin" / "executable_dotfiles-check.tmpl"
KIT_TOML = SOURCE / "kit.toml"
SIGNERS_SOURCE = "dot_config/git/allowed_signers"
PRINCIPAL = "owner@example.org"
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
WIDTH = 24  # the width of a check's name in `harness doctor`'s lines
COUNT = re.compile(r"(\d+) PASS, (\d+) WARN, (\d+) FAIL, (\d+) SKIP")
GPU_PACKAGE = {"metal": "Metal", "cuda": "CUDA", "amdgpu": "AMDGPU", "none": None}
OWN = ["chezmoi verify", "chezmoi diff", "source signature", "source origin/main",
       "Harness checkout", "kit"]
# What chezmoi prints when the session's sandbox denies its configuration directory.
CHEZMOI_DENIED = ("chezmoi: open /home/example/.config/chezmoi/chezmoi.toml: "
                  "operation not permitted")
REVISE_MISSING = "ERROR: ArgumentError: Package Revise not found in current path."
# The kit of the scratch Harness checkout, at harness_commit: two code files and a seed, which
# the source copies.
KIT = {
    "dot_local/bin/executable_tool": ("code", "#!/bin/sh\necho tool\n"),
    ".chezmoitemplates/part.sh": ("code", "# a part\n"),
    ".chezmoidata/data.toml": ("seed", "value = 1\n"),
}
# The kit of the commit after the pin, on which the template host's checkout is: one code file
# changed and one added, so a kit read at HEAD or from the work tree is not the kit of the pin.
LATER = "dot_local/bin/executable_later"
KIT_AFTER_PIN = KIT | {
    ".chezmoitemplates/part.sh": ("code", "# a part, changed after the pin\n"),
    LATER: ("code", "#!/bin/sh\necho later\n"),
}

failures = []
ROOT = None  # the scratch directory of the whole run
KEYS = {}  # name -> private key path


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
OTHER_HOST = "test-other"
NO_GPU_HOST = "test-no-gpu"
CHANNELS = ["1.10", "1.11", "1.12", "nightly", "release"]
# The hosts that the test adds to the data of .chezmoidata/machines.toml.
TEST_MACHINES = {
    OTHER_HOST: {"os": "linux", "arch": "x86_64", "gpu": "amdgpu", "julia_channels": CHANNELS,
                 "julia_default": "1.12"},
    NO_GPU_HOST: {"os": "linux", "arch": "aarch64", "gpu": "none", "julia_channels": CHANNELS,
                  "julia_default": "1.12"},
}
MACHINES = DATA["machines"] | TEST_MACHINES


def xy_channels(host):
    return [c for c in MACHINES[host]["julia_channels"] if re.fullmatch(r"\d+\.\d+", c)]


# ---------------------------------------------------------------- helpers ----

def scratch(name):
    return pathlib.Path(tempfile.mkdtemp(prefix=f"{name}-", dir=ROOT))


def must(cmd, env, cwd=None):
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))}: {result.stderr.strip()}")
    return result.stdout.strip()


def render(host, extra=None):
    """Render dotfiles-check for a host with chezmoi; return (returncode, text, stderr)."""
    extra = dict(extra or {})
    machines = TEST_MACHINES | extra.pop("machines", {})
    entry = (DATA["machines"] | machines).get(host, {"os": "linux"})
    work = scratch("chezmoi")
    (work / "chezmoi.toml").write_text("")
    home = "/Users/me" if entry["os"] == "darwin" else "/home/example"
    data = {"chezmoi": {"hostname": host, "os": entry["os"], "homeDir": home},
            "machines": machines}
    data.update(extra)
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
    result = subprocess.run(cmd, capture_output=True, text=True, input=CHECK.read_text())
    return result.returncode, result.stdout, result.stderr


def rendered(host, extra=None):
    code, text, err = render(host, extra)
    if code != 0:
        raise RuntimeError(f"dotfiles-check does not render for {host}: {err.strip()}")
    return text


def make_key(name):
    directory = ROOT / "keys"
    directory.mkdir(exist_ok=True)
    path = directory / name
    must(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(path)],
         dict(os.environ))
    return path


def signer_line(key):
    kind, blob = pathlib.Path(f"{key}.pub").read_text().split()[:2]
    return f'{PRINCIPAL} namespaces="git" {kind} {blob}\n'


def kit_toml(kit):
    """The kit.toml of `kit`, in the form of examples/dotfiles/kit.toml."""
    return "[files]\n" + "".join(f'"{path}" = "{cls}"\n' for path, (cls, _) in kit.items())


def doctor_line(status, name, detail):
    """A line as `harness doctor` prints it (lib/harness/doctor.py, run_checks)."""
    return f"{status:<4}  {name:<{WIDTH}}  {detail}"


def doctor_output(lines):
    counts = {s: sum(line.startswith(s + " ") for line in lines)
              for s in ("PASS", "WARN", "FAIL", "SKIP")}
    return "\n".join(lines) + "\n\n" + ", ".join(f"{n} {s}" for s, n in counts.items()) + "\n"


DOCTOR = [
    doctor_line("PASS", "system", "macOS 27.0.1 arm64"),
    doctor_line("PASS", "git", "2.54.0 (/usr/bin/git)"),
    doctor_line("WARN", "install warning 1",
                "/home/example/.config/kaimon/auth-token does not exist"),
    doctor_line("SKIP", "harness test", "run with --full"),
    doctor_line("SKIP", "Revise", "run with --full"),
]
DOCTOR_FULL = DOCTOR[:3] + [
    doctor_line("PASS", "harness test", "412 cases, 0 wrong"),
    doctor_line("PASS", "Revise", "julia -e 'using Revise' loads it (/home/example/.juliaup/bin/julia)"),
]
DOCTOR_FAIL = doctor_line("FAIL", "actionlint",
                          "actionlint not found (fix: setup-linux.md, The dependencies)")


# The stubs. Each logs `<program> <arguments>` to $STUBS/calls.log, logs its name to
# $STUBS/stdin-pipe.log when its standard input is a pipe (the caller's standard input, which a
# program could read), and answers from files in $STUBS, which is outside HOME. The harness stub
# writes bytecode below ~/Research/Harness, as Python does, unless PYTHONDONTWRITEBYTECODE is set.
HARNESS_STUB = r'''echo "harness $*" >> "$STUBS/calls.log"
if [ -z "${PYTHONDONTWRITEBYTECODE:-}" ]; then
    mkdir -p "$HOME/Research/Harness/lib/__pycache__"
    echo bytecode > "$HOME/Research/Harness/lib/__pycache__/doctor.cpython-314.pyc"
fi
case "$*" in
    doctor) cat "$STUBS/doctor.out"; exit "$(cat "$STUBS/doctor.code")" ;;
    "doctor --full") cat "$STUBS/doctor-full.out"; exit "$(cat "$STUBS/doctor.code")" ;;
esac
echo "usage: harness [-h] {install,doctor,...} ..." >&2
exit 2
'''
CHEZMOI_STUB = r'''echo "chezmoi $*" >> "$STUBS/calls.log"
for arg; do
    case $arg in
        verify|diff)
            [ -f "$STUBS/$arg.out" ] && cat "$STUBS/$arg.out"
            [ -f "$STUBS/$arg.err" ] && cat "$STUBS/$arg.err" >&2
            exit "$(cat "$STUBS/$arg.code" 2>/dev/null || echo 0)" ;;
    esac
done
exit 0
'''
JULIA_STUB = r'''echo "julia $*" >> "$STUBS/calls.log"
channel=${1#+}
if [ "$3" = "using Revise" ]; then
    if grep -qxF "$channel" "$STUBS/revise-fails" 2>/dev/null; then
        echo "ERROR: ArgumentError: Package Revise not found in current path." >&2
        exit 1
    fi
    exit 0
fi
cat "$STUBS/gpu.out"
[ -f "$STUBS/gpu.err" ] && cat "$STUBS/gpu.err" >&2
exit "$(cat "$STUBS/gpu.code")"
'''


def stub(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\n[ -p /dev/stdin ] && echo "${0##*/}" >> "$STUBS/stdin-pipe.log"\n'
                    + body)
    path.chmod(0o755)


class Machine:
    """A scratch HOME for one host, with the applied source, the Harness checkout and the stubs,
    every check of which passes until a case changes it. With kit=False, harness_commit has no
    examples/dotfiles/kit.toml; a string as `kit` is the text of its kit.toml."""

    def __init__(self, name, host, sandbox=False, kit=True):
        self.host = host
        self.root = scratch(name)
        self.home = self.root / "home"
        self.bindir = self.root / "bin"
        self.stubs = self.root / "stubs"
        self.remote = self.root / "remote.git"
        self.author = self.root / "author"
        self.source = self.home / ".local" / "share" / "chezmoi"
        self.harness = self.home / "Research" / "Harness"
        self.signers = self.home / ".config" / "git" / "allowed_signers"
        self.stubs.mkdir()

        author_home = self.root / "author-home"
        author_home.mkdir()
        author_config = self.root / "author.gitconfig"
        author_config.write_text("[user]\n\tname = Author\n\temail = author@test\n"
                                 "[gpg]\n\tformat = ssh\n[advice]\n\tdetachedHead = false\n")
        self.author_env = {"HOME": str(author_home), "PATH": BASE_PATH, "LANG": "C",
                           "TMPDIR": str(ROOT), "GIT_CONFIG_NOSYSTEM": "1",
                           "GIT_CONFIG_GLOBAL": str(author_config)}
        self.env = {"HOME": str(self.home), "PATH": f"{self.bindir}:{BASE_PATH}", "LANG": "C",
                    "TMPDIR": str(ROOT), "GIT_CONFIG_NOSYSTEM": "1", "STUBS": str(self.stubs)}
        if sandbox:
            self.env["SANDBOX_RUNTIME"] = "1"

        must(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], self.author_env)
        must(["git", "clone", "-q", str(self.remote), str(self.author)], self.author_env)
        must(["git", "switch", "-q", "-c", "main"], self.author_env, self.author)
        files = {path: text for path, (_, text) in KIT.items()}
        files[SIGNERS_SOURCE] = signer_line(KEYS["listed"])
        self.commit("initial", key="listed", files=files)
        self.push()
        self.signers.parent.mkdir(parents=True)
        self.signers.write_text(signer_line(KEYS["listed"]))
        must(["git", "clone", "-q", str(self.remote), str(self.source)], self.author_env)

        # The Harness checkout: the pin, which holds the kit, and one commit after it, which
        # changes the kit. The template host's checkout is the development checkout on the later
        # commit; every other host's is the pin.
        must(["git", "init", "-q", "-b", "main", str(self.harness)], self.author_env)
        if kit:
            self.harness_kit(KIT, kit if isinstance(kit, str) else kit_toml(KIT))
        self.pin = self.harness_commit("the pin")
        if kit:
            self.harness_kit(KIT_AFTER_PIN, kit_toml(KIT_AFTER_PIN))
        self.after_pin = self.harness_commit("after the pin")
        if host != TEMPLATE_HOST:
            self.harness_git("checkout", "-q", "--detach", self.pin)

        stub(self.bindir / "harness", HARNESS_STUB)
        stub(self.bindir / "chezmoi", CHEZMOI_STUB)
        stub(self.home / ".juliaup" / "bin" / "julia", JULIA_STUB)
        self.answer("doctor.out", doctor_output(DOCTOR))
        self.answer("doctor-full.out", doctor_output(DOCTOR_FULL))
        self.answer("doctor.code", "0\n")
        self.answer("gpu.out", "true\n")
        self.answer("gpu.code", "0\n")

        self.script = self.root / "dotfiles-check"
        self.render(self.pin)

    def render(self, pin):
        """Render the script with `pin` as harness_commit."""
        self.script.write_text(rendered(self.host, {"harness_commit": pin}))
        self.script.chmod(0o755)

    # -- the author's side of the source
    def commit(self, message, key=None, files=None, cwd=None):
        cwd = cwd or self.author
        for path, text in (files or {}).items():
            target = cwd / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            must(["git", "add", path], self.author_env, cwd)
        cmd = ["git"]
        if key is not None:
            cmd += ["-c", f"user.signingkey={KEYS[key]}"]
        cmd += ["commit", "-q", "-m", message]
        if key is not None:
            cmd.append("-S")
        if not files:
            cmd.append("--allow-empty")
        must(cmd, self.author_env, cwd)
        return must(["git", "rev-parse", "HEAD"], self.author_env, cwd)

    def push(self):
        must(["git", "push", "-q", "origin", "HEAD:refs/heads/main"], self.author_env, self.author)

    def source_git(self, *args):
        return must(["git", *args], self.author_env, self.source)

    def harness_git(self, *args):
        return must(["git", *args], self.author_env, self.harness)

    def harness_kit(self, kit, toml):
        """Write `kit` and its kit.toml `toml` into examples/dotfiles/ of the Harness checkout,
        and stage them."""
        files = {f"examples/dotfiles/{path}": text for path, (_, text) in kit.items()}
        files["examples/dotfiles/kit.toml"] = toml
        for path, text in files.items():
            target = self.harness / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        self.harness_git("add", "examples")

    def harness_commit(self, message):
        self.harness_git("commit", "-q", "--allow-empty", "-m", message)
        return self.harness_git("rev-parse", "HEAD")

    # -- the stubs
    def answer(self, name, text):
        (self.stubs / name).write_text(text)

    def calls(self, program):
        log = self.stubs / "calls.log"
        if not log.exists():
            return []
        return [line.split(" ", 1)[1] if " " in line else ""
                for line in log.read_text().splitlines() if line.split(" ", 1)[0] == program]

    def run(self, *args, stdin=subprocess.DEVNULL):
        result = subprocess.run(["/bin/bash", str(self.script), *args], stdin=stdin,
                                capture_output=True, text=True, env=self.env, cwd=self.home,
                                timeout=120)
        return result.returncode, result.stdout, result.stderr


def parse(out):
    """The check lines of a run as [(status, name, detail)], and the defects of its form: the
    check lines in the form of `harness doctor`, an empty line, and the count line that counts
    them, which is the last line."""
    lines = out.splitlines()
    defects = []
    if len(lines) < 3 or lines[-2] != "" or not COUNT.fullmatch(lines[-1]):
        return [], [f"the output does not end in an empty line and a count line: {lines[-2:]}"]
    checks = []
    for line in lines[:-2]:
        m = re.fullmatch(r"(PASS|WARN|FAIL|SKIP)  (.{%d})  (.*)" % WIDTH, line)
        if m is None or m.group(2).startswith(" "):
            defects.append(f"not a check line: {line!r}")
            continue
        checks.append((m.group(1), m.group(2).rstrip(), m.group(3)))
    counts = [sum(c[0] == s for c in checks) for s in ("PASS", "WARN", "FAIL", "SKIP")]
    if [int(n) for n in COUNT.fullmatch(lines[-1]).groups()] != counts:
        defects.append(f"the count line {lines[-1]!r} does not count the lines {counts}")
    return checks, defects


def own(checks, doctor_lines):
    """The lines that follow the lines of `harness doctor`, by name."""
    return {name: (status, detail) for status, name, detail in checks[len(doctor_lines):]}


def statuses(checks, doctor_lines):
    return {name: status for name, (status, _) in own(checks, doctor_lines).items()}


def expected_names(host):
    return OWN + [f"Revise +{c}" for c in xy_channels(host)] + ["GPU"]


# ---------------------------------------------------------------- clause 2 ----

def test_all_pass():
    print("\n== 2 and 3: every check passes, on the template host and another host, with --full and not")
    for host in (TEMPLATE_HOST, OTHER_HOST):
        for args in ((), ("--full",)):
            label = f"{host} {' '.join(args) or '(no option)'}"
            m = Machine("pass", host)
            code, out, err = m.run(*args)
            checks, defects = parse(out)
            check(not defects, f"{label}: the form of harness doctor {defects}")
            doctor = DOCTOR_FULL if args else DOCTOR
            text = [doctor_line(*c) for c in checks]
            check(text[:len(doctor)] == doctor,
                  f"{label}: harness doctor's lines come first, unchanged")
            check(m.calls("harness") == [" ".join(("doctor",) + args)],
                  f"{label}: harness called as {m.calls('harness')}")
            names = [c[1] for c in checks[len(doctor):]]
            check(names == expected_names(host), f"{label}: the checks {names}")
            got = statuses(checks, doctor)
            package = GPU_PACKAGE[MACHINES[host]["gpu"]]
            want = {name: "PASS" for name in expected_names(host)}
            if not args:
                want.update({n: "SKIP" for n in want if n.startswith("Revise") or n == "GPU"})
            if package is None:
                want["GPU"] = "SKIP"
            check(got == want, f"{label}: the statuses {got}")
            check(code == 0, f"{label}: exit {code}, 0 ({err.strip()!r})")
            chezmoi = m.calls("chezmoi")
            check(len(chezmoi) == 2 and "verify" in chezmoi[0].split() and "diff" in chezmoi[1].split()
                  and all("--exclude=scripts" in c.split() for c in chezmoi),
                  f"{label}: chezmoi verify and diff, both --exclude=scripts: {chezmoi}")
            julia = m.calls("julia")
            if args:
                default = MACHINES[host]["julia_default"]
                want_julia = [f"+{c} -e using Revise" for c in xy_channels(host)]
                if package is not None:
                    want_julia.append(f"+{default} -e using {package}; println({package}.functional())")
                check(julia == want_julia, f"{label}: julia {julia}")
            else:
                check(julia == [], f"{label}: no julia without --full ({julia})")


def test_read_only():
    print("\n== 2: no terminal, no question, no write below HOME, no fetch")
    m = Machine("read-only", OTHER_HOST)
    newer = m.commit("newer, not fetched", key="listed")
    m.push()
    before = tree(m.home)
    origin = m.source_git("rev-parse", "refs/remotes/origin/main")
    # Standard input is an open pipe that nobody writes: a read waits until the timeout.
    reader, writer = os.pipe()
    try:
        code, out, err = m.run("--full", stdin=reader)
    except subprocess.TimeoutExpired:
        code, out, err = None, "", "timeout"
    finally:
        os.close(reader)
        os.close(writer)
    check(code == 0, f"standard input open and silent: it finishes, exit {code} ({err.strip()!r})")
    pipe = m.stubs / "stdin-pipe.log"
    check(not pipe.exists(), "no program it runs gets its standard input "
          f"({pipe.read_text().split() if pipe.exists() else []})")
    after_tree = tree(m.home)
    check(after_tree == before, "nothing below HOME is written, changed or removed "
          f"({sorted(set(after_tree) ^ set(before))})")
    after = m.source_git("rev-parse", "refs/remotes/origin/main")
    check(after == origin and after != newer,
          "no fetch: origin/main of the source stays where the last fetch left it")
    checks, _ = parse(out)
    check(own(checks, DOCTOR_FULL).get("source origin/main", ("",))[0] == "PASS",
          "a commit that no fetch has seen does not count")


def tree(path):
    """Every path below `path` with its mode, modification time and contents."""
    snapshot = {}
    for dirpath, dirnames, names in os.walk(path):
        for name in dirnames + names:
            full = pathlib.Path(dirpath, name)
            st = full.lstat()
            content = full.read_bytes() if full.is_file() and not full.is_symlink() else None
            snapshot[str(full.relative_to(path))] = (st.st_mode, st.st_mtime_ns, content)
    return snapshot


def test_usage():
    print("\n== 2: a usage error exits 2 and checks nothing")
    for args in (("--bogus",), ("--full", "--full"), ("",), ("full",)):
        m = Machine("usage", OTHER_HOST)
        code, out, err = m.run(*args)
        check(code == 2 and "usage: dotfiles-check [--full]" in err and out == ""
              and (m.stubs / "calls.log").exists() is False,
              f"arguments {list(args)}: exit {code}, the usage line, no output, no call")


# ---------------------------------------------------------------- harness doctor ----

def test_doctor():
    print("\n== harness doctor: its FAIL lines count; missing; an exit with no FAIL line")
    m = Machine("doctor-fail", OTHER_HOST)
    lines = DOCTOR[:2] + [DOCTOR_FAIL] + DOCTOR[2:]
    m.answer("doctor.out", doctor_output(lines))
    m.answer("doctor.code", "1\n")
    code, out, err = m.run()
    checks, defects = parse(out)
    check(not defects and [doctor_line(*c) for c in checks[:len(lines)]] == lines,
          f"doctor exits 1: its lines, the FAIL line among them, pass through {defects}")
    count = COUNT.fullmatch(out.splitlines()[-1])
    check(count is not None and count.group(3) == "1",
          f"doctor exits 1: its FAIL line counts in the total ({out.splitlines()[-1]!r})")
    check(all(s == "PASS" for s in statuses(checks, lines).values() if s != "SKIP"),
          "doctor exits 1: the tree's checks still pass")
    check(code == 1, f"doctor exits 1: dotfiles-check exits {code}, 1")

    m = Machine("doctor-missing", OTHER_HOST)
    (m.bindir / "harness").unlink()
    code, out, err = m.run()
    checks, defects = parse(out)
    got = {name: (status, detail) for status, name, detail in checks}
    check(got.get("harness doctor", ("",))[0] == "FAIL" and "not found" in got["harness doctor"][1],
          f"harness not on the PATH: a FAIL line ({got.get('harness doctor')})")
    rest = [c[1] for c in checks[1:]]
    check(not defects and rest == expected_names(OTHER_HOST) and len(m.calls("chezmoi")) == 2,
          f"harness not on the PATH: the tree's checks still run ({rest})")
    check(code == 1, f"harness not on the PATH: exit {code}, 1")

    for label, text, status in (("exits 2 and prints nothing", "", "2"),
                                ("exits 1 with no FAIL line", doctor_output(DOCTOR), "1")):
        m = Machine("doctor-exit", OTHER_HOST)
        m.answer("doctor.out", text)
        m.answer("doctor.code", status + "\n")
        code, out, err = m.run()
        checks, defects = parse(out)
        got = {name: (s, detail) for s, name, detail in checks}
        check(not defects and got.get("harness doctor", ("",))[0] == "FAIL"
              and f"exits {status}" in got["harness doctor"][1] and code == 1,
              f"harness doctor {label}: a FAIL line that names the exit, exit {code}, 1 "
              f"({got.get('harness doctor')}, {defects})")


# ---------------------------------------------------------------- chezmoi ----

def test_chezmoi():
    print("\n== chezmoi verify and chezmoi diff: PASS and FAIL; refused in a sandbox")
    for sandbox in (False, True):
        m = Machine("verify", OTHER_HOST, sandbox=sandbox)
        m.answer("verify.code", "1\n")
        code, out, err = m.run()
        got = statuses(parse(out)[0], DOCTOR)
        check(got["chezmoi verify"] == "FAIL" and got["chezmoi diff"] == "PASS" and code == 1,
              f"chezmoi verify exits 1, silent{', in a sandbox' if sandbox else ''}: FAIL, "
              f"exit {code} ({got})")

    m = Machine("diff", OTHER_HOST)
    m.answer("diff.out", "diff --git a/.zshrc b/.zshrc\nindex 1111111..2222222 100644\n"
                         "--- a/.zshrc\n+++ b/.zshrc\n@@ -1 +1 @@\n-# old\n+# new\n")
    code, out, err = m.run()
    checks, _ = parse(out)
    got = own(checks, DOCTOR)
    check(got["chezmoi diff"][0] == "FAIL" and "7 lines" in got["chezmoi diff"][1]
          and got["chezmoi verify"][0] == "PASS" and code == 1,
          f"chezmoi diff prints a diff: FAIL with its length, exit {code} ({got['chezmoi diff']})")

    for sandbox, want, want_code in ((False, "FAIL", 1), (True, "SKIP", 0)):
        m = Machine("chezmoi-refused", OTHER_HOST, sandbox=sandbox)
        for verb in ("verify", "diff"):
            m.answer(f"{verb}.err", CHEZMOI_DENIED + "\n")
            m.answer(f"{verb}.code", "1\n")
        code, out, err = m.run()
        got = own(parse(out)[0], DOCTOR)
        label = "in a sandbox" if sandbox else "outside a sandbox"
        check(all(got[v][0] == want and CHEZMOI_DENIED in got[v][1]
                  for v in ("chezmoi verify", "chezmoi diff")) and code == want_code,
              f"chezmoi gives no answer {label}: {want} with the reason, exit {code} "
              f"({got['chezmoi verify']})")
        if sandbox:
            check("sandbox" in got["chezmoi verify"][1], "the SKIP names the sandbox")

    m = Machine("chezmoi-missing", OTHER_HOST, sandbox=True)
    (m.bindir / "chezmoi").unlink()
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(all(got[v][0] == "FAIL" and "not found" in got[v][1]
              for v in ("chezmoi verify", "chezmoi diff")) and code == 1,
          f"chezmoi not on the PATH, even in a sandbox: FAIL, exit {code} ({got['chezmoi verify']})")


# ---------------------------------------------------------------- the source ----

def test_signature():
    print("\n== the signature of the source's HEAD, by the applied allowed_signers")
    m = Machine("signed", OTHER_HOST)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(got["source signature"][0] == "PASS" and PRINCIPAL in got["source signature"][1],
          f"signed by the listed key: PASS, with the principal ({got['source signature']})")

    cases = (("unsigned", None, None), ("signed by the other key", "other", None),
             ("signed by the other key, which the source's allowed_signers lists", "other",
              signer_line(KEYS["listed"]) + signer_line(KEYS["other"])))
    for label, key, source_signers in cases:
        m = Machine("head", OTHER_HOST)
        files = {SIGNERS_SOURCE: source_signers} if source_signers else None
        head = m.commit(label, key=key, files=files)
        m.push()
        m.source_git("pull", "-q", "--ff-only")
        if source_signers:
            # A git configuration that names the source's copy: only the applied one counts.
            (m.home / ".gitconfig").write_text(
                '[gpg]\n\tformat = ssh\n[gpg "ssh"]\n'
                f"\tallowedSignersFile = {m.source / SIGNERS_SOURCE}\n")
        code, out, err = m.run()
        got = own(parse(out)[0], DOCTOR)
        check(got["source signature"][0] == "FAIL" and head[:7] in got["source signature"][1]
              and got["source origin/main"][0] == "PASS" and code == 1,
              f"a head {label}: FAIL that names {head[:7]}, exit {code} ({got['source signature']})")

    for label, content in (("missing", None), ("comment-only", "# no key\n")):
        m = Machine("signers", OTHER_HOST)
        if content is None:
            m.signers.unlink()
        else:
            m.signers.write_text(content)
        code, out, err = m.run()
        got = own(parse(out)[0], DOCTOR)
        check(got["source signature"][0] == "FAIL"
              and "missing or lists no key" in got["source signature"][1] and code == 1,
              f"a {label} allowed_signers: FAIL, exit {code} ({got['source signature']})")


def test_origin():
    print("\n== the source's HEAD and origin/main as the last fetch saw it")
    m = Machine("behind", OTHER_HOST)
    tip = m.commit("on the remote", key="listed")
    m.push()
    m.source_git("fetch", "-q", "origin")
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(got["source origin/main"][0] == "WARN" and tip[:7] in got["source origin/main"][1]
          and "1 commit" in got["source origin/main"][1] and code == 0,
          f"behind origin/main: WARN with the count, exit {code} ({got['source origin/main']})")

    m = Machine("ahead", OTHER_HOST)
    m.commit("a local commit", key="listed", cwd=m.source)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(got["source origin/main"][0] == "FAIL" and got["source signature"][0] == "PASS"
          and code == 1, f"ahead of origin/main: FAIL, exit {code} ({got['source origin/main']})")

    m = Machine("no-origin", OTHER_HOST)
    m.source_git("update-ref", "-d", "refs/remotes/origin/main")
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["source origin/main"]
    check(status == "FAIL" and "has no origin/main" in detail and code == 1,
          f"no origin/main: FAIL, exit {code} ({got['source origin/main']})")

    m = Machine("no-source", OTHER_HOST)
    shutil.rmtree(m.source)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(all(got[n][0] == "FAIL" and "not a git repository" in got[n][1]
              for n in ("source signature", "source origin/main")) and code == 1,
          f"no source: both FAIL, exit {code} ({got['source signature']})")


# ---------------------------------------------------------------- the Harness checkout ----

def test_harness_checkout():
    print("\n== the Harness checkout: the pin on another host, containing it on the template host")
    for host, at, want in ((OTHER_HOST, "pin", "PASS"), (OTHER_HOST, "after", "FAIL"),
                           (TEMPLATE_HOST, "after", "PASS"), (TEMPLATE_HOST, "pin", "PASS"),
                           (TEMPLATE_HOST, "before", "FAIL")):
        m = Machine("harness", host)
        if at == "before":
            # A checkout whose HEAD is an earlier commit, so it does not contain the pin.
            m.harness_git("checkout", "-q", "--orphan", "earlier")
            m.harness_git("commit", "-q", "--allow-empty", "-m", "earlier")
        else:
            m.harness_git("checkout", "-q", "--detach", m.pin if at == "pin" else m.after_pin)
        code, out, err = m.run()
        got = own(parse(out)[0], DOCTOR)
        check(got["Harness checkout"][0] == want and code == (0 if want == "PASS" else 1),
              f"{host}, HEAD {at} the pin: {want}, exit {code} ({got['Harness checkout']})")

    m = Machine("harness-missing", OTHER_HOST)
    shutil.rmtree(m.harness)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["Harness checkout"]
    check(status == "FAIL" and "not a git repository" in detail and code == 1,
          f"no Harness checkout: FAIL, exit {code} ({got['Harness checkout']})")


# ---------------------------------------------------------------- the kit ----

def test_kit():
    print("\n== 5: the kit, each code file of kit.toml against the harness at harness_commit")
    code_files = [path for path, (cls, _) in KIT.items() if cls == "code"]
    seed = next(path for path, (cls, _) in KIT.items() if cls == "seed")
    # The template host's checkout is on the commit after the pin, whose kit differs from the
    # pin's: its kit line still compares with the pin.
    for host in (TEMPLATE_HOST, OTHER_HOST):
        m = Machine("kit-pass", host)
        code, out, err = m.run()
        got = own(parse(out)[0], DOCTOR)
        check(got["kit"][0] == "PASS" and m.pin[:7] in got["kit"][1] and code == 0,
              f"{host}, every code file equals the kit: PASS, exit {code} ({got['kit']})")

    # Drift: a code file that differs, in the work tree and in a commit, and a seed that differs.
    for host in (TEMPLATE_HOST, OTHER_HOST):
        m = Machine("kit-drift", host)
        (m.source / code_files[0]).write_text("#!/bin/sh\necho changed\n")
        (m.source / seed).write_text("value = 2\n")
        code, out, err = m.run()
        got = own(parse(out)[0], DOCTOR)
        status, detail = got["kit"]
        check(status == "WARN" and code_files[0] in detail and code_files[1] not in detail
              and LATER not in detail and seed not in detail and code == 0,
              f"{host}, a code file that differs: WARN that names it alone, exit {code} ({got['kit']})")

    m = Machine("kit-drift-both", TEMPLATE_HOST)
    for path in code_files:
        (m.source / path).write_text("# changed\n")
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["kit"]
    check(status == "WARN" and all(path in detail for path in code_files) and LATER not in detail
          and code == 0,
          f"two code files that differ: WARN that names each of them, exit {code} ({got['kit']})")

    m = Machine("kit-drift-commit", OTHER_HOST)
    m.commit("change a code file", key="listed", files={code_files[1]: "# changed\n"})
    m.push()
    m.source_git("pull", "-q", "--ff-only")
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(got["kit"][0] == "WARN" and code_files[1] in got["kit"][1] and code == 0,
          f"a committed change of a code file: WARN that names it ({got['kit']})")

    m = Machine("kit-seed", OTHER_HOST)
    (m.source / seed).write_text("value = 2\n")
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(got["kit"][0] == "PASS", f"a seed that differs: PASS ({got['kit']})")

    m = Machine("kit-missing", OTHER_HOST)
    (m.source / code_files[1]).unlink()
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["kit"]
    check(status == "WARN" and f"{code_files[1]} (missing)" in detail
          and code_files[0] not in detail and code == 0,
          f"a code file that the source lacks: WARN that names it as missing ({got['kit']})")

    m = Machine("kit-none", OTHER_HOST, kit=False)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["kit"]
    check(status == "SKIP" and "examples/dotfiles/kit.toml" in detail and m.pin[:7] in detail
          and code == 0,
          f"harness_commit without examples/dotfiles/kit.toml: SKIP that names it ({got['kit']})")

    # A kit.toml in another TOML spelling has no line `"<path>" = "code"`, so the check reads no
    # code file; that is a WARN, not a PASS.
    m = Machine("kit-form", OTHER_HOST, kit=kit_toml(KIT).replace('" = "', '"="'))
    (m.source / code_files[0]).write_text("# changed\n")
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["kit"]
    check(status == "WARN" and "no line" in detail and m.pin[:7] in detail and code == 0,
          f"a kit.toml with no code line in the form of the kit: WARN that says so ({got['kit']})")

    m = Machine("kit-unknown-pin", OTHER_HOST)
    unknown = "1234567" + "0" * 33
    m.render(unknown)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    status, detail = got["kit"]
    check(status == "SKIP" and unknown[:7] in detail and "lacks" in detail,
          f"a Harness checkout that lacks harness_commit: SKIP with that reason ({got['kit']})")

    m = Machine("kit-no-harness", OTHER_HOST)
    shutil.rmtree(m.harness)
    code, out, err = m.run()
    got = own(parse(out)[0], DOCTOR)
    check(got["kit"][0] == "SKIP" and "lacks" in got["kit"][1],
          f"no Harness checkout: SKIP ({got['kit']})")


def test_kit_toml():
    print("\n== 6: kit.toml names every file of the kit with its class")
    if not KIT_TOML.exists():
        print(f"  skip: {SOURCE} has no kit.toml; it is a copy of the kit, not the kit")
        return
    with open(KIT_TOML, "rb") as handle:
        entries = tomllib.load(handle).get("files", {})
    check(bool(entries), f"kit.toml has a [files] table ({len(entries)} entries)")
    wrong = {path: cls for path, cls in entries.items() if cls not in ("code", "seed")}
    check(not wrong, f"each entry is code or seed {wrong}")
    # dotfiles-check reads the code files with sed, one line `"<path>" = "code"` each.
    code = {path for path, cls in entries.items() if cls == "code"}
    lines = set(re.findall(r'^"([^"]*)" = "code"$', KIT_TOML.read_text(), re.MULTILINE))
    check(lines == code, f"each code entry is a line in the form that dotfiles-check reads "
                         f"{sorted(code ^ lines)}")
    absent = sorted(path for path in entries if not (SOURCE / path).is_file())
    check(not absent, f"each entry is a file of the kit {absent}")
    unlisted = [rel for rel in kit_files()
                if rel != "kit.toml" and not rel.startswith("tests/") and rel not in entries]
    check(not unlisted, f"every file outside tests/ and kit.toml is in kit.toml {unlisted}")


def kit_files():
    """The files of the kit, relative to it: in a git work tree, the files that git tracks or
    would track, without the ignored ones such as .DS_Store; outside one, every file."""
    p = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       cwd=SOURCE, capture_output=True, text=True)
    if p.returncode == 0:
        return sorted({rel for rel in p.stdout.split("\0") if rel and (SOURCE / rel).is_file()})
    return sorted(path.relative_to(SOURCE).as_posix() for path in SOURCE.rglob("*") if path.is_file())


# ---------------------------------------------------------------- --full ----

def test_full():
    print("\n== --full: Revise on each X.Y channel, and the GPU package")
    channels = xy_channels(OTHER_HOST)
    for sandbox, want, want_code in ((False, "FAIL", 1), (True, "SKIP", 0)):
        m = Machine("revise", OTHER_HOST, sandbox=sandbox)
        m.answer("revise-fails", channels[1] + "\n")
        code, out, err = m.run("--full")
        got = own(parse(out)[0], DOCTOR_FULL)
        others = [got[f"Revise +{c}"][0] for c in channels if c != channels[1]]
        bad = got[f"Revise +{channels[1]}"]
        check(bad[0] == want and REVISE_MISSING in bad[1] and set(others) == {"PASS"}
              and code == want_code,
              f"Revise fails on {channels[1]} {'in a sandbox' if sandbox else ''}: {want} on that "
              f"channel only, exit {code} ({bad})")

    for label, gpu_out, gpu_code in (("false", "false\n", "0"),
                                     ("an error", "ERROR: ArgumentError: Package AMDGPU not "
                                                  "found in current path.\n", "1"),
                                     ("true, but julia exits 1", "true\n", "1")):
        m = Machine("gpu", OTHER_HOST)
        m.answer("gpu.out", gpu_out)
        m.answer("gpu.code", gpu_code + "\n")
        code, out, err = m.run("--full")
        got = own(parse(out)[0], DOCTOR_FULL)
        check(got["GPU"][0] == "FAIL" and "AMDGPU" in got["GPU"][1] and code == 1,
              f"AMDGPU.functional() gives {label}: FAIL, exit {code} ({got['GPU']})")

    # The answer is read from standard output only: a warning on standard error after it does
    # not change it, and a "true" on standard error alone is no answer.
    for label, gpu_out, gpu_err, want, want_code in (
            ("true, then a warning on stderr", "true\n",
             "WARNING: AMDGPU: a device library is older than the driver\n", "PASS", 0),
            ("false, then true on stderr", "false\n", "true\n", "FAIL", 1)):
        m = Machine("gpu-stderr", OTHER_HOST)
        m.answer("gpu.out", gpu_out)
        m.answer("gpu.err", gpu_err)
        code, out, err = m.run("--full")
        got = own(parse(out)[0], DOCTOR_FULL)
        check(got["GPU"][0] == want and code == want_code and err == "",
              f"AMDGPU.functional() gives {label}: {want}, exit {code}, julia's stderr not "
              f"passed on ({got['GPU']}, {err.strip()!r})")

    m = Machine("julia-missing", OTHER_HOST, sandbox=True)
    (m.home / ".juliaup" / "bin" / "julia").unlink()
    code, out, err = m.run("--full")
    got = own(parse(out)[0], DOCTOR_FULL)
    check(all(got[n][0] == "FAIL" and "not found" in got[n][1]
              for n in got if n.startswith("Revise") or n == "GPU")
          and code == 1, f"no julia, even in a sandbox: Revise and GPU FAIL, exit {code}")

    for args in ((), ("--full",)):
        m = Machine("no-gpu", NO_GPU_HOST)
        code, out, err = m.run(*args)
        doctor = DOCTOR_FULL if args else DOCTOR
        got = own(parse(out)[0], doctor)
        julia = m.calls("julia")
        check(got["GPU"][0] == "SKIP" and "none" in got["GPU"][1] and code == 0
              and all("functional" not in c for c in julia),
              f"gpu none {' '.join(args)}: SKIP, no GPU call, exit {code} ({got['GPU']})")


# ---------------------------------------------------------------- the render ----

def test_render():
    print("\n== 3: bash -n and shellcheck on the render for every host; an unknown gpu")
    for host in MACHINES:
        path = scratch("lint") / "dotfiles-check"
        path.write_text(rendered(host))
        syntax = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        check(syntax.returncode == 0, f"bash -n dotfiles-check ({host}) {syntax.stderr.strip()}")
        lint = subprocess.run(["shellcheck", "-S", "warning", str(path)], capture_output=True, text=True)
        check(lint.returncode == 0, f"shellcheck dotfiles-check ({host}) {lint.stdout.strip()}")

    machines = {"machines": {"test-tpu": dict(TEST_MACHINES[OTHER_HOST], gpu="tpu")}}
    code, text, err = render("test-tpu", machines)
    check(code != 0 and '"tpu"' in err, f"a gpu outside the four stops the render ({err.strip()!r})")


def main():
    global ROOT
    for tool in ("chezmoi", "git", "bash", "ssh-keygen", "shellcheck"):
        if shutil.which(tool) is None:
            print(f"check-check: {tool} is not on the PATH")
            return 1
    with tempfile.TemporaryDirectory(prefix="check-check-") as tmp:
        ROOT = pathlib.Path(tmp).resolve()
        KEYS["listed"] = make_key("listed")
        KEYS["other"] = make_key("other")
        for case in (test_all_pass, test_read_only, test_usage, test_doctor, test_chezmoi,
                     test_signature, test_origin, test_harness_checkout, test_kit, test_kit_toml,
                     test_full, test_render):
            try:
                case()
            except Exception as error:  # a broken fixture is a failure, not a crash
                fail(f"{case.__name__}: {type(error).__name__}: {error}")
    if failures:
        print(f"\ncheck-check: {len(failures)} failure(s)")
        return 1
    print("\ncheck-check: all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
