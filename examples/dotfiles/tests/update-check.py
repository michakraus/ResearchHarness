#!/usr/bin/env python3
"""Test dotfiles-update and dotfiles-merge against scratch remotes, never against the home directory.

Run it with Python 3.11 or later, from any directory:

    python3 tests/update-check.py

It needs chezmoi, git, bash, ssh-keygen and shellcheck. Both scripts are rendered with `chezmoi
execute-template` for the template host (their own --config, --source, --destination and
--persistent-state under $TMPDIR), dotfiles-merge with the world's own signing_key and
sk_provider as host data. Each case builds a world under $TMPDIR: a bare remote; an author clone
that commits and pushes; a scratch HOME whose ~/.local/share/chezmoi is a clone of the remote,
with ~/.config/git/allowed_signers, ~/.gitconfig and both scripts in ~/.local/bin; a `chezmoi`
stub that logs each call; and a gpg.ssh.program that logs the SSH_SK_PROVIDER of each signature
before it runs ssh-keygen. The keys are throwaway ed25519 keys that ssh-keygen makes in the run,
under $TMPDIR: "listed" is in the applied allowed_signers, "other" is not. A script runs with
standard input on a pseudo-terminal, where the test writes the answers (^D is the end of input),
or on a pipe for the cases without a terminal.

Checks:
  1. An unsigned commit on main stops dotfiles-update: exit non-zero, a message that names the
     commit, no chezmoi call, HEAD of the source unchanged.
  2. A commit signed by the other key stops it the same way, and so does a good OpenPGP or X.509
     signature that the host's gpg or gpgsm (a stand-in that trusts every key) reads as G.
  3. A signed tip over an unsigned first-parent commit stops it the same way.
  4. A main that is not a fast-forward of HEAD stops it the same way.
  5. All first-parent commits signed by the listed key (also a signed --no-ff merge of unsigned
     branch commits, and a gitconfig with gpg.minTrustLevel = ultimate or log.showSignature =
     true): `chezmoi diff` runs, then `chezmoi apply` only after the answer y; n, an empty line,
     the end of input and yes apply nothing.
  6. Standard input not a terminal: the script stops before `git fetch` (origin/main of the source
     does not move).
  7. An incoming commit that adds the other key to the source's allowed_signers does not make a
     commit signed by the other key pass, in one commit or in two.
  The decided edges: a fetch that fails, HEAD equal to origin/main, and a missing, empty or
  comment-only allowed_signers (the guard's message, and no commit's). And a remote main that
  moves to an unsigned commit right after the fetch: the checked commit is merged.
  9. bash -n and shellcheck -S warning pass on both scripts, rendered for every host that
     receives them.
  11. dotfiles-merge <branch>: it stops without a terminal, with local changes (a modified and an
      untracked file), and when HEAD is not main at origin/main (main moved on the remote, a local
      commit, or a detached HEAD), each with no merge and no push. Otherwise it prints the log and
      the diff and asks; on y it prints the line that names the key, the branch and its commit,
      makes a --no-ff merge whose %G? is G for the listed key, pushes main, and runs the step of
      clause 5; on n, an empty line or the end of input the remote's main is unchanged. The
      decided edges: a branch the remote lacks, never or no longer after the source fetched it
      (stops before the question), a branch main contains (exit 0), a conflict (merge aborted), a
      signing key that does not exist and one that allowed_signers does not list (no merge commit
      stays), and a refused push (the local merge stays, named, and nothing is applied).
  12. `chezmoi diff` and `chezmoi apply` are called once in the source, in the shared template,
      and both scripts include it.
  13. dotfiles-merge reads the signing key and SSH_SK_PROVIDER from the host data: with an empty
      signing_key, or a host entry without one (rendered from a copy of the source whose
      machines.toml lacks the line), it stops before the fetch with one line that names
      signing_key; a signing_key under ~ signs; an empty or absent sk_provider leaves
      SSH_SK_PROVIDER unset for the signature, and a non-empty one sets it; a quote, a $ or a
      backtick in either value stays text in the script.
  14. .chezmoitemplates/gitconfig-signing gives the template host gpg.format ssh, the applied
      allowed_signers and user.signingkey from the host data, and another host no signing key.
  15. .chezmoiignore keeps kit.toml and tests/ from every machine and dotfiles-merge from every
      host but the template host, and ends with the lines of .chezmoitemplates/chezmoiignore.local.
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
UPDATE = SOURCE / "dot_local" / "bin" / "executable_dotfiles-update.tmpl"
MERGE = SOURCE / "dot_local" / "bin" / "executable_dotfiles-merge.tmpl"
SHARED = SOURCE / ".chezmoitemplates" / "dotfiles-update-steps.sh"
SIGNING = SOURCE / ".chezmoitemplates" / "gitconfig-signing"
SHARED_INCLUDE = '{{ template "dotfiles-update-steps.sh" . }}'
SIGNERS_SOURCE = "dot_config/git/allowed_signers"
PRINCIPAL = "owner@example.org"
BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
EOF = "\x04"  # ^D on a pseudo-terminal; on a pipe, the end of the written answers
TERMINAL_TEST = "if [ ! -t 0 ]; then"
UNSET = "<unset>"  # what the logging gpg.ssh.program writes for an unset SSH_SK_PROVIDER
PTY = False  # whether a pseudo-terminal opens here; set in main

failures = []
ROOT = None  # the scratch directory of the whole run
KEYS = {}  # name -> private key path
SCRIPTS = {}  # script name -> rendered text for the template host, with the listed key


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


# ---------------------------------------------------------------- helpers ----

def scratch(name):
    return pathlib.Path(tempfile.mkdtemp(prefix=f"{name}-", dir=ROOT))


def must(cmd, env, cwd=None):
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))}: {result.stderr.strip()}")
    return result.stdout.strip()


def render(template, host, entry=None, source=SOURCE):
    """Render a template of `source` for a host with chezmoi; `entry` adds to the host's data.
    Return the text."""
    os_name = DATA["machines"].get(host, {}).get("os") or (entry or {}).get("os", "linux")
    work = scratch("chezmoi")
    (work / "chezmoi.toml").write_text("")
    home = "/Users/me" if os_name == "darwin" else "/home/example"
    data = {"chezmoi": {"hostname": host, "os": os_name, "homeDir": home}}
    if entry is not None:
        data["machines"] = {host: entry}
    cmd = [
        "chezmoi",
        "--config", str(work / "chezmoi.toml"),
        "--source", str(source),
        "--destination", str(work / "home"),
        "--persistent-state", str(work / "state.boltdb"),
        "--no-tty",
        "--override-data", json.dumps(data),
        "execute-template",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, input=template.read_text())
    if result.returncode != 0:
        raise RuntimeError(f"{template.name} does not render for {host}: {result.stderr.strip()}")
    return result.stdout


def signing_data(key, sk_provider=""):
    return {"signing_key": key, "sk_provider": sk_provider}


def source_without(key):
    """A copy of the source whose machines.toml has no line `key = ...`, so the template host's
    entry has no `key`: --override-data adds to the data and cannot remove a key."""
    copy = scratch("source") / "source"
    shutil.copytree(SOURCE, copy, ignore=shutil.ignore_patterns("tests", ".git"))
    machines = copy / ".chezmoidata" / "machines.toml"
    machines.write_text("".join(line for line in machines.read_text().splitlines(keepends=True)
                                if line.split("=")[0].strip() != key))
    with open(machines, "rb") as handle:
        if key in tomllib.load(handle)["machines"][TEMPLATE_HOST]:
            raise RuntimeError(f"{machines}: the template host still has {key}")
    return copy


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


def base_env(home, gitconfig=None):
    env = {
        "HOME": str(home),
        "PATH": BASE_PATH,
        "LANG": "C",
        "TMPDIR": str(ROOT),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if gitconfig is not None:
        env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    return env


class World:
    """A bare remote, an author clone, and a scratch HOME with the applied source. `signingkey`
    is the signing_key of the host data that dotfiles-merge is rendered with: a key name, a path
    below the world's root, or the text itself when `literal` is true."""

    def __init__(self, name, signingkey="listed", sk_provider="", literal=False):
        self.root = scratch(name)
        self.remote = self.root / "remote.git"
        self.author = self.root / "author"
        self.home = self.root / "home"
        self.source = self.home / ".local" / "share" / "chezmoi"
        self.bindir = self.root / "bin"
        self.log = self.root / "chezmoi.log"
        self.providers = self.root / "sk-provider.log"
        self.signers = self.home / ".config" / "git" / "allowed_signers"

        author_home = self.root / "author-home"
        author_home.mkdir()
        author_config = self.root / "author.gitconfig"
        author_config.write_text("[user]\n\tname = Author\n\temail = author@test\n"
                                 "[gpg]\n\tformat = ssh\n")
        self.author_env = base_env(author_home, author_config)

        must(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], self.author_env)
        must(["git", "clone", "-q", str(self.remote), str(self.author)], self.author_env)
        must(["git", "switch", "-q", "-c", "main"], self.author_env, self.author)
        self.commit("initial", key="listed",
                    files={SIGNERS_SOURCE: signer_line(KEYS["listed"]), "dot_zshrc": "# zshrc\n"})
        self.push()

        self.signers.parent.mkdir(parents=True)
        self.signers.write_text(signer_line(KEYS["listed"]))
        # The program that signs and verifies SSH signatures: it logs the SSH_SK_PROVIDER of each
        # signature, then runs ssh-keygen.
        program = self.root / "ssh-program"
        program.write_text(
            "#!/bin/sh\n"
            'case " $* " in *" -Y sign "*) '
            f'echo "${{SSH_SK_PROVIDER-{UNSET}}}" >> "{self.providers}" ;; esac\n'
            'exec ssh-keygen "$@"\n')
        program.chmod(0o755)
        (self.home / ".gitconfig").write_text(
            "[user]\n\tname = Owner\n\temail = owner@test\n"
            "[gpg]\n\tformat = ssh\n"
            f'[gpg "ssh"]\n\tallowedSignersFile = ~/.config/git/allowed_signers\n'
            f"\tprogram = {program}\n")
        self.env = base_env(self.home)
        self.env["PATH"] = f"{self.bindir}:{BASE_PATH}"
        must(["git", "clone", "-q", str(self.remote), str(self.source)], self.env)

        self.bindir.mkdir()
        stub = self.bindir / "chezmoi"
        stub.write_text(f'#!/bin/sh\necho "$*" >> "{self.log}"\n')
        stub.chmod(0o755)
        if literal:
            key = signingkey
        elif signingkey in KEYS:
            key = str(KEYS[signingkey])
        else:
            key = str(self.root / signingkey)
        self.scripts = dict(SCRIPTS)
        if (key, sk_provider) != (str(KEYS["listed"]), ""):
            self.scripts["dotfiles-merge"] = render(MERGE, TEMPLATE_HOST,
                                                    signing_data(key, sk_provider))
        local_bin = self.home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        for name, text in self.scripts.items():
            path = local_bin / name
            path.write_text(text)
            path.chmod(0o755)

    # -- the author's side
    def commit(self, message, key=None, files=None, cwd=None):
        cwd = cwd or self.author
        env = self.author_env if cwd == self.author else self.env
        for path, text in (files or {}).items():
            target = cwd / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            must(["git", "add", path], env, cwd)
        cmd = ["git"]
        if key is not None:
            cmd += ["-c", f"user.signingkey={KEYS[key]}"]
        cmd += ["commit", "-q", "-m", message]
        if key is not None:
            cmd.append("-S")
        if not files:
            cmd.append("--allow-empty")
        must(cmd, env, cwd)
        return must(["git", "rev-parse", "HEAD"], env, cwd)

    def push(self, ref="main", force=False):
        cmd = ["git", "push", "-q"] + (["--force"] if force else []) + ["origin", f"HEAD:refs/heads/{ref}"]
        must(cmd, self.author_env, self.author)

    def author_git(self, *args):
        return must(["git", *args], self.author_env, self.author)

    # -- the machine's side
    def head(self):
        return must(["git", "rev-parse", "HEAD"], self.env, self.source)

    def origin_main(self):
        return must(["git", "rev-parse", "refs/remotes/origin/main"], self.env, self.source)

    def remote_main(self):
        return must(["git", "--git-dir", str(self.remote), "rev-parse", "main"], self.env)

    def sync(self):
        """Bring the source to the remote's main, as an earlier verified update would."""
        must(["git", "fetch", "-q", "origin"], self.env, self.source)
        must(["git", "merge", "-q", "--ff-only", "origin/main"], self.env, self.source)

    def signature(self, rev):
        return must(["git", "-c", f"gpg.ssh.allowedSignersFile={self.signers}", "log", "-1",
                     "--format=%G? %GS", rev], self.env, self.source)

    def calls(self):
        if not self.log.exists():
            return []
        return [line.split()[0] for line in self.log.read_text().splitlines() if line.strip()]

    def install(self, name, text):
        """Install `text` as the script `name` in place of its render with the world's key."""
        self.scripts[name] = text
        path = self.home / ".local" / "bin" / name
        path.write_text(text)
        path.chmod(0o755)

    def sk_providers(self):
        """The SSH_SK_PROVIDER of each signature that the world's machine made."""
        if not self.providers.exists():
            return []
        return self.providers.read_text().splitlines()

    def run(self, script, *args, answers="", terminal=True):
        """Run an installed script. With terminal=False, or where no pseudo-terminal opens, the
        answers go to a pipe; in the second case the script that runs is the copy whose terminal
        test is `false` (see answering_copy)."""
        path = self.home / ".local" / "bin" / script
        if terminal and not PTY:
            path = answering_copy(self.root, script, self.scripts[script])
        cmd = ["/bin/bash", str(path), *args]
        if not terminal or not PTY:
            result = subprocess.run(cmd, input=answers.replace(EOF, ""), capture_output=True,
                                    text=True, env=self.env, cwd=self.home, timeout=120)
            return result.returncode, result.stdout + result.stderr
        master, slave = os.openpty()
        try:
            proc = subprocess.Popen(cmd, stdin=slave, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=self.env, cwd=self.home)
            os.close(slave)
            slave = None
            if answers:
                os.write(master, answers.encode())
            out, _ = proc.communicate(timeout=120)
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)
        return proc.returncode, out.decode(errors="replace")


def pty_available():
    try:
        master, slave = os.openpty()
    except OSError:
        return False
    os.close(master)
    os.close(slave)
    return True


def answering_copy(root, script, text):
    """The rendered script with its terminal test replaced by `false`, for a run whose answers
    come on a pipe because no pseudo-terminal opens (Claude Code's sandbox refuses one). Clause 6
    always runs the script itself."""
    if text.count(TERMINAL_TEST) != 1:
        raise RuntimeError(f"{script}: the terminal test {TERMINAL_TEST!r} is not there once")
    path = root / "answering" / script
    path.parent.mkdir(exist_ok=True)
    path.write_text(text.replace(TERMINAL_TEST, "if false; then"))
    return path


def stopped(world, label, code, out, commit, head):
    """The stop of clauses 1-4: exit non-zero, the commit named, no chezmoi call, HEAD kept."""
    check(code != 0, f"{label}: exit {code}, non-zero")
    check(commit in out, f"{label}: the output names {commit[:7]}")
    check(world.calls() == [], f"{label}: no chezmoi call (log {world.calls()})")
    check(world.head() == head, f"{label}: HEAD of the source unchanged")


# ---------------------------------------------------------------- dotfiles-update ----

def clause_1():
    print("\n== 1: an unsigned commit on main")
    w = World("c1")
    head = w.head()
    bad = w.commit("unsigned")
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n")
    stopped(w, "unsigned", code, out, bad, head)


def clause_2():
    print("\n== 2: a commit signed by a key that allowed_signers does not list")
    w = World("c2")
    head = w.head()
    bad = w.commit("signed by other", key="other")
    w.push()
    check("\ngpgsig " in w.author_git("cat-file", "commit", bad), "the commit carries a signature")
    code, out = w.run("dotfiles-update", answers="y\n")
    stopped(w, "other key", code, out, bad, head)


# A stand-in for gpg or gpgsm that the host's git config names: it signs anything, and it reports
# every signature good, from a key at ultimate trust, as a keyring that trusts the key would.
FAKE_GPG = """#!/bin/sh
mode=verify
for arg; do [ "$arg" = -bsau ] && mode=sign; done
cat >/dev/null
if [ "$mode" = sign ]; then
    echo '[GNUPG:] SIG_CREATED D 22 8 00 1700000000 0123456789ABCDEF0123456789ABCDEF01234567' >&2
    printf -- '-----BEGIN HEADER-----\\n\\nZmFrZQ==\\n-----END HEADER-----\\n'
    exit 0
fi
echo '[GNUPG:] NEWSIG'
echo '[GNUPG:] GOODSIG 0123456789ABCDEF Eve <eve@test>'
echo '[GNUPG:] VALIDSIG 0123456789ABCDEF0123456789ABCDEF01234567 2026-10-15 1700000000 0 4 0 22 8 00 0123456789ABCDEF0123456789ABCDEF01234567'
echo '[GNUPG:] TRUST_ULTIMATE 0 pgp'
"""


def clause_2_backends():
    print("\n== 2: a good OpenPGP or X.509 signature by a key that the host's keyring trusts")
    for label, fmt, header in (("OpenPGP", "openpgp", "PGP SIGNATURE"),
                               ("X.509", "x509", "SIGNED MESSAGE")):
        w = World(f"c2-{fmt}")
        fake = w.root / f"fake-{fmt}"
        fake.write_text(FAKE_GPG.replace("HEADER", header))
        fake.chmod(0o755)
        with open(w.home / ".gitconfig", "a") as handle:
            if fmt == "openpgp":
                handle.write(f"[gpg]\n\tprogram = {fake}\n")
            handle.write(f'[gpg "{fmt}"]\n\tprogram = {fake}\n')
        head = w.head()
        w.author_git("-c", f"gpg.format={fmt}", "-c", f"gpg.{fmt}.program={fake}",
                     "-c", "user.signingkey=eve@test",
                     "commit", "-q", "--allow-empty", "-S", "-m", f"signed with {label}")
        bad = w.author_git("rev-parse", "HEAD")
        w.push()
        must(["git", "fetch", "-q", "origin"], w.env, w.source)
        check(w.signature(bad) == "G Eve <eve@test>",
              f"{label}: the host's git reads the signature as G ({w.signature(bad)!r})")
        code, out = w.run("dotfiles-update", answers="y\n")
        stopped(w, label, code, out, bad, head)


def clause_3():
    print("\n== 3: a signed tip over an unsigned first-parent commit")
    w = World("c3")
    head = w.head()
    bad = w.commit("unsigned below")
    w.commit("signed tip", key="listed")
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n")
    stopped(w, "signed tip", code, out, bad, head)


def clause_4():
    print("\n== 4: a main that is not a fast-forward of HEAD")
    w = World("c4")
    w.commit("second", key="listed")
    w.push()
    w.sync()
    head = w.head()
    w.author_git("reset", "-q", "--hard", "HEAD~1")
    tip = w.commit("rewritten", key="listed")
    w.push(force=True)
    code, out = w.run("dotfiles-update", answers="y\n")
    stopped(w, "not a fast-forward", code, out, tip, head)


def clause_5():
    print("\n== 5: every first-parent commit signed by the listed key")
    for answers, label, applies in (("y\n", "y", True), ("n\n", "n", False),
                                    ("\n", "an empty line", False), (EOF, "end of input", False),
                                    ("yes\n", "yes", False)):
        w = World("c5")
        w.commit("one", key="listed")
        tip = w.commit("two", key="listed")
        w.push()
        code, out = w.run("dotfiles-update", answers=answers)
        want = ["diff", "apply"] if applies else ["diff"]
        check(code == 0, f"answer {label}: exit {code}, 0")
        check(w.calls() == want, f"answer {label}: chezmoi calls {w.calls()}, expected {want}")
        check(w.head() == tip, f"answer {label}: HEAD is origin/main {tip[:7]}")

    w = World("c5-merge")
    w.author_git("switch", "-q", "-c", "topic")
    w.commit("unsigned branch commit")
    w.author_git("switch", "-q", "main")
    w.author_git("-c", f"user.signingkey={KEYS['listed']}", "merge", "-q", "--no-ff", "-S",
                 "-m", "signed merge", "topic")
    tip = w.author_git("rev-parse", "HEAD")
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n")
    check(code == 0 and w.calls() == ["diff", "apply"] and w.head() == tip,
          f"a signed --no-ff merge of an unsigned branch commit is applied (exit {code}, "
          f"calls {w.calls()})")

    w = World("c5-trust")
    with open(w.home / ".gitconfig", "a") as handle:
        handle.write("[gpg]\n\tminTrustLevel = ultimate\n")
    tip = w.commit("signed", key="listed")
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n")
    check(code == 0 and w.calls() == ["diff", "apply"] and w.head() == tip,
          "the check reads %G?, not git verify-commit's status: gpg.minTrustLevel = ultimate "
          f"changes nothing (exit {code}, calls {w.calls()})")

    w = World("c5-showsignature")
    with open(w.home / ".gitconfig", "a") as handle:
        handle.write("[log]\n\tshowSignature = true\n")
    tip = w.commit("signed", key="listed")
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n")
    check(code == 0 and w.calls() == ["diff", "apply"] and w.head() == tip,
          f"a gitconfig with log.showSignature = true changes nothing (exit {code}, "
          f"calls {w.calls()})")


def clause_6():
    print("\n== 6: standard input not a terminal")
    w = World("c6")
    head, before = w.head(), w.origin_main()
    w.commit("signed", key="listed")
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n", terminal=False)
    check(code != 0, f"exit {code}, non-zero")
    check(w.origin_main() == before, "origin/main of the source did not move: no git fetch ran")
    check(w.calls() == [] and w.head() == head, "no chezmoi call, HEAD unchanged")


def clause_7():
    print("\n== 7: the applied allowed_signers, never the incoming one")
    both = signer_line(KEYS["listed"]) + signer_line(KEYS["other"])
    w = World("c7-two")
    head = w.head()
    w.commit("add the other key", key="listed", files={SIGNERS_SOURCE: both})
    bad = w.commit("signed by the other key", key="other")
    w.push()
    applied = w.signers.read_text()
    code, out = w.run("dotfiles-update", answers="y\n")
    stopped(w, "two commits", code, out, bad, head)
    check(w.signers.read_text() == applied, "the applied allowed_signers is unchanged")

    w = World("c7-one")
    head = w.head()
    bad = w.commit("add and sign with the other key", key="other", files={SIGNERS_SOURCE: both})
    w.push()
    code, out = w.run("dotfiles-update", answers="y\n")
    stopped(w, "one commit", code, out, bad, head)


def update_edges():
    print("\n== dotfiles-update: the decided edges")
    w = World("edge-fetch")
    head = w.head()
    must(["git", "remote", "set-url", "origin", str(w.root / "missing.git")], w.env, w.source)
    code, out = w.run("dotfiles-update", answers="y\n")
    check(code != 0 and w.calls() == [] and w.head() == head,
          f"a fetch that fails: exit {code}, no chezmoi call, HEAD unchanged")

    w = World("edge-nothing")
    code, out = w.run("dotfiles-update", answers="y\n")
    check(code == 0 and "nothing new" in out and w.calls() == [],
          f"HEAD equal to origin/main: exit {code}, 'nothing new', no chezmoi call")

    for label, content in (("missing", None), ("empty", ""),
                           ("comment-only", "# no key here\n\n")):
        w = World(f"edge-signers-{label}")
        head = w.head()
        w.commit("signed", key="listed")
        w.push()
        if content is None:
            w.signers.unlink()
        else:
            w.signers.write_text(content)
        code, out = w.run("dotfiles-update", answers="y\n")
        check(code != 0 and "is missing or lists no key" in out
              and "has no good signature" not in out and w.calls() == [] and w.head() == head,
              f"a {label} allowed_signers stops before the check: exit {code}, the guard's "
              "message and no commit's, no chezmoi call, HEAD unchanged")

    # The remote's main moves to an unsigned commit right after the script's fetch: the script
    # merges the commit it checked, never a ref that it reads or fetches again.
    w = World("edge-race")
    tip = w.commit("signed", key="listed")
    w.push()
    late = w.commit("unsigned, after the fetch")
    w.push("late")
    marker = w.root / "race-fired"
    hook = w.source / ".git" / "hooks" / "reference-transaction"
    hook.write_text(
        "#!/bin/sh\n"
        '[ "$1" = committed ] || exit 0\n'
        f'[ -e "{marker}" ] && exit 0\n'
        "grep -q ' refs/remotes/origin/main$' || exit 0\n"
        f'touch "{marker}"\n'
        f'git --git-dir="{w.remote}" update-ref refs/heads/main {late}\n')
    hook.chmod(0o755)
    code, out = w.run("dotfiles-update", answers="y\n")
    check(marker.exists() and w.remote_main() == late,
          "the race: the remote's main moved to the unsigned commit after the fetch")
    check(code == 0 and w.head() == tip and w.calls() == ["diff", "apply"],
          f"the race: HEAD is the checked commit {tip[:7]}, not {late[:7]} (exit {code}, "
          f"calls {w.calls()})")


# ---------------------------------------------------------------- dotfiles-merge ----

def merge_world(name, signingkey="listed", sk_provider="", literal=False):
    """A world with a branch `topic` on the remote: one unsigned commit that changes dot_zshrc."""
    w = World(name, signingkey, sk_provider, literal)
    w.author_git("switch", "-q", "-c", "topic")
    topic = w.commit("topic change", files={"dot_zshrc": "# zshrc\n# topic change\n"})
    w.push("topic")
    w.author_git("switch", "-q", "main")
    return w, topic


def merge_kept(w, label, code, head, main, want_zero=False):
    if want_zero:
        check(code == 0, f"{label}: exit {code}, 0")
    else:
        check(code != 0, f"{label}: exit {code}, non-zero")
    check(w.head() == head, f"{label}: no merge, HEAD unchanged")
    check(w.remote_main() == main, f"{label}: no push, the remote's main unchanged")
    check(w.calls() == [], f"{label}: no chezmoi call")
    check(not (w.source / ".git" / "MERGE_HEAD").exists(), f"{label}: no merge in progress")


def clause_11():
    print("\n== 11: dotfiles-merge <branch>")
    w, topic = merge_world("c11-tty")
    head, main = w.head(), w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n", terminal=False)
    merge_kept(w, "no terminal", code, head, main)

    for label, files in (("a modified file", {"dot_zshrc": "# local edit\n"}),
                         ("an untracked file", {"untracked": "x\n"})):
        w, topic = merge_world("c11-dirty")
        for path, text in files.items():
            (w.source / path).write_text(text)
        head, main = w.head(), w.remote_main()
        code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
        merge_kept(w, f"local changes, {label}", code, head, main)

    w, topic = merge_world("c11-behind")
    head = w.head()
    w.commit("main moved", key="listed")
    w.push()
    main = w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge_kept(w, "HEAD behind origin/main", code, head, main)

    w, topic = merge_world("c11-ahead")
    main = w.remote_main()
    w.commit("local commit", cwd=w.source)
    head = w.head()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge_kept(w, "HEAD ahead of origin/main", code, head, main)

    w, topic = merge_world("c11-detached")
    must(["git", "switch", "-q", "--detach", "origin/main"], w.env, w.source)
    head, main = w.head(), w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge_kept(w, "a detached HEAD at origin/main", code, head, main)

    w, topic = merge_world("c11-yes")
    base = w.head()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    check(code == 0, f"y: exit {code}, 0")
    check("topic change" in out and "+# topic change" in out,
          "y: the log and the diff of the branch are printed")
    check(f"dotfiles-merge: {KEYS['listed']} now signs the merge of origin/topic ({topic[:7]}) "
          "into main." in out,
          "y: the line before the signature names the key, the branch and its commit")
    merge = w.head()
    parents = must(["git", "rev-list", "--parents", "-n", "1", merge], w.env, w.source).split()[1:]
    check(parents == [base, topic], f"y: a --no-ff merge of {topic[:7]} on {base[:7]}")
    check(w.signature(merge) == f"G {PRINCIPAL}", f"y: %G? of the merge is G for the listed key "
          f"({w.signature(merge)!r})")
    check(w.remote_main() == merge, "y: the remote's main is the merge")
    check(w.calls() == ["diff", "apply"], f"y, y: chezmoi calls {w.calls()}, expected diff, apply")

    w, topic = merge_world("c11-yes-no")
    code, out = w.run("dotfiles-merge", "topic", answers="y\nn\n")
    check(code == 0 and w.remote_main() == w.head() and w.calls() == ["diff"],
          f"y, n: merged and pushed, chezmoi diff only (exit {code}, calls {w.calls()})")

    for answers, label in (("n\n", "n"), ("\n", "an empty line"), (EOF, "end of input")):
        w, topic = merge_world("c11-no")
        head, main = w.head(), w.remote_main()
        code, out = w.run("dotfiles-merge", "topic", answers=answers)
        merge_kept(w, f"answer {label}", code, head, main, want_zero=True)


def merge_edges():
    print("\n== dotfiles-merge: the decided edges")
    w, topic = merge_world("medge-missing")
    head, main = w.head(), w.remote_main()
    code, out = w.run("dotfiles-merge", "no-such-branch", answers="y\ny\n")
    merge_kept(w, "a branch the remote lacks", code, head, main)
    check("[y/N]" not in out, "a branch the remote lacks: no question is asked")

    w, topic = merge_world("medge-deleted")
    must(["git", "fetch", "-q", "origin"], w.env, w.source)
    w.author_git("push", "-q", "origin", "--delete", "topic")
    head, main = w.head(), w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge_kept(w, "a branch the remote deleted after the source fetched it", code, head, main)
    check("[y/N]" not in out, "a branch the remote deleted: no question is asked")

    w, topic = merge_world("medge-contained")
    w.author_git("merge", "-q", "--ff-only", "topic")
    w.push()
    w.sync()
    head, main = w.head(), w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge_kept(w, "a branch main contains", code, head, main, want_zero=True)
    check("nothing to merge" in out, "a branch main contains: 'nothing to merge'")

    w, topic = merge_world("medge-conflict")
    w.commit("main changes dot_zshrc", key="listed", files={"dot_zshrc": "# zshrc\n# main\n"})
    w.push()
    w.sync()
    head, main = w.head(), w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge_kept(w, "a conflict", code, head, main)
    check(must(["git", "status", "--porcelain"], w.env, w.source) == "",
          "a conflict: the merge is aborted, the work tree is clean")

    for label, key in (("a signing key that does not exist", "missing-key"),
                       ("a signing key that allowed_signers does not list", "other")):
        w, topic = merge_world("medge-sign", signingkey=key)
        head, main = w.head(), w.remote_main()
        code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
        merge_kept(w, label, code, head, main)
        check(must(["git", "status", "--porcelain"], w.env, w.source) == "",
              f"{label}: the work tree is clean")

    w, topic = merge_world("medge-refused")
    hook = w.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'refused by the test' >&2\nexit 1\n")
    hook.chmod(0o755)
    main = w.remote_main()
    code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
    merge = w.head()
    check(code != 0, f"a refused push: exit {code}, non-zero")
    check(w.remote_main() == main, "a refused push: the remote's main unchanged")
    check(merge != main and merge in out, f"a refused push: the local merge {merge[:7]} stays, named")
    check(w.calls() == [], "a refused push: no chezmoi call")


def clause_13():
    print("\n== 13: the signing key and SSH_SK_PROVIDER from the host data")
    # An empty signing_key, and a host entry with no signing_key at all.
    empty, _ = merge_world("c13-no-key", signingkey="", literal=True)
    absent, _ = merge_world("c13-absent-key")
    absent.install("dotfiles-merge", render(MERGE, TEMPLATE_HOST, source=source_without("signing_key")))
    for label, w in (("an empty signing_key", empty), ("no signing_key in the host entry", absent)):
        head, main, origin = w.head(), w.remote_main(), w.origin_main()
        code, out = w.run("dotfiles-merge", "topic", answers="y\ny\n")
        merge_kept(w, label, code, head, main)
        lines = out.strip().splitlines()
        check(len(lines) == 1 and "signing_key" in lines[0],
              f"{label}: one line that names signing_key ({lines})")
        fetched = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "refs/remotes/origin/topic"],
                                 capture_output=True, env=w.env, cwd=w.source).returncode == 0
        check(w.origin_main() == origin and not fetched, f"{label}: it stops before the fetch")

    # A signing_key under ~, as the host data writes it: git reads it below HOME.
    w, topic = merge_world("c13-tilde", signingkey="~/.ssh/signing", literal=True)
    (w.home / ".ssh").mkdir()
    for suffix in ("", ".pub"):
        shutil.copy(f"{KEYS['listed']}{suffix}", w.home / ".ssh" / f"signing{suffix}")
    (w.home / ".ssh" / "signing").chmod(0o600)
    code, out = w.run("dotfiles-merge", "topic", answers="y\nn\n")
    check(code == 0 and w.signature(w.head()) == f"G {PRINCIPAL}" and w.remote_main() == w.head(),
          f"a signing_key under ~: the merge is signed by the listed key and pushed (exit {code})")

    for provider, want in (("", UNSET), (str(ROOT / "no-such-provider.so"), None)):
        w, topic = merge_world("c13-provider", sk_provider=provider)
        code, out = w.run("dotfiles-merge", "topic", answers="y\nn\n")
        want = want or provider
        label = f"sk_provider {provider!r}"
        check(code == 0 and w.signature(w.head()) == f"G {PRINCIPAL}",
              f"{label}: the merge is signed (exit {code})")
        check(w.sk_providers() == [want],
              f"{label}: SSH_SK_PROVIDER of the signature is {want!r} ({w.sk_providers()})")

    # A host entry with no sk_provider at all signs as an empty one does.
    w, topic = merge_world("c13-absent-provider")
    w.install("dotfiles-merge", render(MERGE, TEMPLATE_HOST, {"signing_key": str(KEYS["listed"])},
                                       source=source_without("sk_provider")))
    code, out = w.run("dotfiles-merge", "topic", answers="y\nn\n")
    check(code == 0 and w.signature(w.head()) == f"G {PRINCIPAL}" and w.sk_providers() == [UNSET],
          f"no sk_provider in the host entry: the merge is signed, SSH_SK_PROVIDER unset "
          f"(exit {code}, {w.sk_providers()})")
    # A value with quotes, $ and a command substitution reaches the script as text.
    value = '~/.ssh/key"$(touch pwned)\'`touch pwned`'
    text = render(MERGE, TEMPLATE_HOST, signing_data(value, value))
    probe = scratch("quoting")
    path = probe / "lines.sh"
    path.write_text("".join(line + "\n" for line in text.splitlines()
                            if line.startswith(("SIGNING_KEY=", "SK_PROVIDER=")))
                    + 'printf "%s\\n" "$SIGNING_KEY" "$SK_PROVIDER"\n')
    result = subprocess.run(["/bin/bash", str(path)], capture_output=True, text=True, cwd=probe)
    check(result.stdout == f"{value}\n{value}\n" and not (probe / "pwned").exists(),
          f"signing_key and sk_provider with quotes and $( ): the script reads them as text "
          f"({result.stdout!r}, {result.stderr.strip()!r})")


def clause_14():
    print("\n== 14: the signing settings of git, .chezmoitemplates/gitconfig-signing")
    key = "~/.ssh/the-signing-key"
    for host, entry, want_key in ((TEMPLATE_HOST, signing_data(key), key),
                                  ("test-other", {"os": "linux", "signing_key": key}, None)):
        path = scratch("gitconfig") / "gitconfig"
        path.write_text(render(SIGNING, host, entry))

        def get(name):
            result = subprocess.run(["git", "config", "--file", str(path), "--get", name],
                                    capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else None

        check(get("gpg.format") == "ssh"
              and get("gpg.ssh.allowedSignersFile") == "~/.config/git/allowed_signers",
              f"{host}: gpg.format ssh and the applied allowed_signers")
        check(get("user.signingkey") == want_key,
              f"{host}: user.signingkey is {want_key!r} ({get('user.signingkey')!r})")


def clause_15():
    print("\n== 15: .chezmoiignore")
    ignore = SOURCE / ".chezmoiignore"
    local = SOURCE / ".chezmoitemplates" / "chezmoiignore.local"
    check(ignore.read_text().rstrip("\n").endswith('{{ template "chezmoiignore.local" . }}'),
          ".chezmoiignore ends with the template chezmoiignore.local")
    for host, entry in ((TEMPLATE_HOST, None), ("test-other", {"os": "linux"})):
        lines = render(ignore, host, entry).splitlines()
        own = render(local, host, entry).splitlines()
        check(all(name in lines for name in ("kit.toml", "tests", "tests/**")),
              f"{host}: kit.toml and tests reach no machine")
        merge = ".local/bin/dotfiles-merge" in lines
        check(merge == (host != TEMPLATE_HOST),
              f"{host}: .local/bin/dotfiles-merge is {'ignored' if merge else 'applied'}")
        check(lines[len(lines) - len(own):] == own,
              f"{host}: the lines of chezmoiignore.local end it ({len(own)} lines)")


# ---------------------------------------------------------------- static checks ----

def receivers(name):
    """The hosts that receive ~/.local/bin/<name>."""
    if name == "dotfiles-merge":
        return [TEMPLATE_HOST]
    return list(DATA["machines"])


def clause_9():
    print("\n== 9: bash -n and shellcheck")
    env = dict(os.environ)
    for name, template in (("dotfiles-update", UPDATE), ("dotfiles-merge", MERGE)):
        for host in receivers(name):
            path = scratch("lint") / name
            path.write_text(render(template, host))
            syntax = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            check(syntax.returncode == 0, f"bash -n {name} ({host}) {syntax.stderr.strip()}")
            lint = subprocess.run(["shellcheck", "-S", "warning", str(path)], capture_output=True,
                                  text=True, env=env)
            check(lint.returncode == 0, f"shellcheck {name} ({host}) {lint.stdout.strip()}")


def clause_12():
    print("\n== 12: one code path")
    calls = {"diff": [], "apply": []}
    for path in SOURCE.rglob("*"):
        rel = path.relative_to(SOURCE)
        if not path.is_file() or rel.parts[0] in (".git", ".claude", "tests") or rel.name == "README.md":
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            match = re.match(r"\s*(?:if\s+)?(?:!\s*)?chezmoi\s+(diff|apply)\b", line)
            if match:
                calls[match.group(1)].append(f"{rel}:{number}")
    for verb, where in calls.items():
        check(len(where) == 1 and where[0].startswith(".chezmoitemplates/dotfiles-update-steps.sh"),
              f"chezmoi {verb} is called once, in the shared template: {where}")
    for template in (UPDATE, MERGE):
        check(template.read_text().count(SHARED_INCLUDE) == 1,
              f"{template.relative_to(SOURCE)} includes the shared template once")


def main():
    global ROOT, PTY
    PTY = pty_available()
    if PTY:
        print("The answers go to a pseudo-terminal.")
    else:
        print("No pseudo-terminal opens here: the runs with answers use a copy of each script "
              f"whose terminal test {TERMINAL_TEST!r} is `false`, and a pipe. Clause 6 runs the "
              "script itself.")
    for tool in ("chezmoi", "git", "bash", "ssh-keygen", "shellcheck"):
        if shutil.which(tool) is None:
            print(f"update-check: {tool} is not on the PATH")
            return 1
    with tempfile.TemporaryDirectory(prefix="update-check-") as tmp:
        ROOT = pathlib.Path(tmp)
        KEYS["listed"] = make_key("listed")
        KEYS["other"] = make_key("other")
        try:
            SCRIPTS["dotfiles-update"] = render(UPDATE, TEMPLATE_HOST)
            SCRIPTS["dotfiles-merge"] = render(MERGE, TEMPLATE_HOST,
                                               signing_data(str(KEYS["listed"])))
        except (OSError, RuntimeError) as error:
            print(f"update-check: the scripts do not render: {error}")
            return 1
        for case in (clause_1, clause_2, clause_2_backends, clause_3, clause_4, clause_5, clause_6,
                     clause_7, update_edges, clause_9, clause_11, merge_edges, clause_12,
                     clause_13, clause_14, clause_15):
            try:
                case()
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                fail(f"{case.__name__}: {error}")
    if failures:
        print(f"\nupdate-check: {len(failures)} failure(s)")
        return 1
    print("\nupdate-check: all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
