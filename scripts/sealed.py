#!/usr/bin/env python3
"""gh, glab and git with a secret that only the user's Touch ID decrypts. One script with three
names; the base name of the path that it runs as chooses what it does:

    ghx <the arguments of gh>
    glabx <the arguments of glab>
    git-credential-sealed <name> https://<host> <action>

A secret is the file ~/.config/research-harness/sealed/<name>.age. The first `age` on the PATH
decrypts it, as `age -d -i ~/.config/research-harness/sealed/identity.txt <file>`, where the
identity is one of age-plugin-se in the Secure Enclave, so that each decryption asks for Touch ID.
Its plain text is the one line `https://<user>:<token>@<host>` of git's `credential-store`, the
user and the token percent-decoded. The decryption has a time limit, TIMEOUT seconds; past it the
script stops `age`. A Ctrl-C reaches `age` and gh or glab, in the same process group, and the
script waits for them.

- ghx decrypts the secret `github`, whose host must be github.com, and runs the real gh with the
  same arguments: the first `gh` on the PATH that is an executable file and does not start with
  `#!`, so that the wrapper ~/.local/bin/gh, a script, is skipped. gh gets GH_TOKEN, the secret's
  token, and a new empty GH_CONFIG_DIR, which ghx removes when gh ends; GITHUB_TOKEN, GH_HOST,
  GH_ENTERPRISE_TOKEN and GITHUB_ENTERPRISE_TOKEN are removed, so the token reaches only github.com.
- glabx decrypts the secret `gitlab` and runs the first `glab` on the PATH with the same arguments,
  GITLAB_TOKEN the token, GITLAB_HOST the secret's host, and a new empty GLAB_CONFIG_DIR, which it
  removes when glab ends; GITLAB_ACCESS_TOKEN, OAUTH_TOKEN, GITLAB_URI, GL_HOST, GITLAB_API_HOST and
  GITLAB_REPO are removed, since glab sends an environment token to the host of GITLAB_REPO and of
  its configuration too.
- git-credential-sealed is a git credential helper: git runs it for the line
  `credential.https://<host>.helper = sealed <name> https://<host>` and appends the action. For
  `get` it reads the request on stdin; only where the request's protocol is `https` and its host is
  the URL's, compared without case, does it decrypt the secret `<name>`, whose host must be the
  URL's too, and write `username=<user>` and `password=<token>` on stdout. For any other action, or
  another protocol or host, it reads stdin, decrypts nothing and writes nothing, exit 0, so that git
  can neither store nor erase a sealed secret, and another remote asks for no Touch ID.

ghx and glabx exit with the status of gh and glab, 128 and the signal's number where a signal ends
it. Every refusal exits 2 with one line `sealed: …` on stderr that names its cause, and runs no gh
or glab: a secret file that does not exist; no `age` on the PATH; an `age` that fails or runs past
the time limit; a plain text that is not one such line; a secret of another host; no gh or glab on
the PATH; helper arguments that are not exactly a name of letters, digits and `-`, not starting
with `-`, a URL `https://<host>` with no user, path, query or fragment, and an action; and a base
name that is none of the three. The token is in no argument, file or message. The standard library
only, and Python 3.9 or later, the python3 of macOS.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass

SEALED = pathlib.Path(".config", "research-harness", "sealed")
IDENTITY = "identity.txt"
GITHUB = "github.com"
HTTPS = "https"
# The seconds that a decryption may take, a Touch ID prompt included.
TIMEOUT = 120
# A secret's name: letters, digits and `-`, not starting with `-`.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
# The words of a helper line after the program: the name, the URL and the action.
HELPER_WORDS = 3
REFUSED = 2
# The exit status of a program that a signal ends is this plus the signal's number.
SIGNALLED = 128
GH_REMOVED = ("GITHUB_TOKEN", "GH_HOST", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
GLAB_REMOVED = (
    "GITLAB_ACCESS_TOKEN",
    "OAUTH_TOKEN",
    "GITLAB_URI",
    "GL_HOST",
    "GITLAB_API_HOST",
    "GITLAB_REPO",
)


class RefusedError(Exception):
    """A refusal: one line on stderr, exit status 2."""


@dataclass(frozen=True)
class Secret:
    """The user, the token and the host, in lower case, of a decrypted secret."""

    user: str
    token: str
    host: str


def status_of(code: int) -> int:
    """The exit status `code` of a program as a shell reports it, 128 and the signal's number where
    a signal ends it."""
    return code if code >= 0 else SIGNALLED - code


def parse(text: str, path: pathlib.Path) -> Secret:
    """The secret of the plain text `text` of the file `path`: exactly one line
    `https://<user>:<token>@<host>`. The message of a refusal names the file, not the text."""
    refused = RefusedError(f"{path} holds no one line https://<user>:<token>@<host>")
    lines = text.splitlines()
    if len(lines) != 1:
        raise refused
    try:
        url = urllib.parse.urlsplit(lines[0])
        hostname = url.hostname
    except ValueError:
        raise refused from None
    host = url.netloc.rpartition("@")[2].lower()
    if url.scheme != HTTPS or not url.username or not url.password or not hostname:
        raise refused
    return Secret(urllib.parse.unquote(url.username), urllib.parse.unquote(url.password), host)


def decrypt(name: str) -> Secret:
    """The secret `name`, decrypted by the first `age` on the PATH within TIMEOUT seconds."""
    sealed = pathlib.Path.home() / SEALED
    path = sealed / f"{name}.age"
    if not path.is_file():
        raise RefusedError(f"{path} does not exist")
    age = shutil.which("age")
    if age is None:
        raise RefusedError(f"no age on the PATH to decrypt {path}")
    command = [age, "-d", "-i", str(sealed / IDENTITY), str(path)]
    # age gets no stdin: the helper reads git's request from it. The time limit is communicate's.
    with subprocess.Popen(  # no timeout: communicate has it
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as p:
        # Ctrl-C reaches age, in the same process group, which decides; the script waits for it.
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            out, err = p.communicate(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            raise RefusedError(f"age takes more than {TIMEOUT} s to decrypt {path}; stopped it") from None
        finally:
            # gh and glab start with the default action again, so that a Ctrl-C ends them.
            signal.signal(signal.SIGINT, previous)
    if p.returncode != 0:
        last = next((line.strip() for line in reversed(err.splitlines()) if line.strip()), "")
        raise RefusedError(f"age exits {status_of(p.returncode)} on {path}" + (f": {last}" if last else ""))
    return parse(out, path)


def program(name: str, *, skip_scripts: bool) -> pathlib.Path:
    """The first `name` on the PATH that is an executable file, and, with `skip_scripts`, does not
    start with `#!`."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = pathlib.Path(entry or ".", name)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        if skip_scripts:
            try:
                with candidate.open("rb") as f:
                    if f.read(2) == b"#!":
                        continue
            except OSError:
                continue
        return candidate
    raise RefusedError(f"no {name} on the PATH" + (" but #! scripts" if skip_scripts else ""))


def run(path: pathlib.Path, args: list[str], env: dict[str, str]) -> int:
    """The exit status of `path` with `args` and `env`, as a shell reports it."""
    with subprocess.Popen([str(path), *args], env=env) as p:  # no timeout: gh runs as long as its command
        # Ctrl-C reaches the program, in the same process group, which decides; the script waits.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        status = p.wait()
    return status_of(status)


def with_config(path: pathlib.Path, args: list[str], env: dict[str, str], variable: str) -> int:
    """Run `path` with `args`, `env` and `variable` a new empty directory, removed after the run."""
    with tempfile.TemporaryDirectory(prefix="sealed.") as config:
        env[variable] = config
        return run(path, args, env)


def ghx(args: list[str]) -> int:
    """Run the real gh with `args` and the token of the secret `github`."""
    gh = program("gh", skip_scripts=True)
    secret = decrypt("github")
    if secret.host != GITHUB:
        raise RefusedError(f"the secret github names the host {secret.host}, not {GITHUB}")
    env = {k: v for k, v in os.environ.items() if k not in GH_REMOVED}
    env["GH_TOKEN"] = secret.token
    return with_config(gh, args, env, "GH_CONFIG_DIR")


def glabx(args: list[str]) -> int:
    """Run the first glab with `args`, and the token and host of the secret `gitlab`."""
    glab = program("glab", skip_scripts=False)
    secret = decrypt("gitlab")
    env = {k: v for k, v in os.environ.items() if k not in GLAB_REMOVED}
    env["GITLAB_TOKEN"] = secret.token
    env["GITLAB_HOST"] = secret.host
    return with_config(glab, args, env, "GLAB_CONFIG_DIR")


def url_host(url: str) -> str:
    """The host, in lower case, of the helper's URL `https://<host>`."""
    refused = RefusedError(f"{url} is no URL https://<host> with no user, path, query or fragment")
    try:
        parts = urllib.parse.urlsplit(url)
        hostname = parts.hostname
    except ValueError:
        raise refused from None
    if parts.scheme != HTTPS or not hostname or "@" in parts.netloc:
        raise refused
    if parts.path or parts.query or parts.fragment or url.endswith(("?", "#")):
        raise refused
    return parts.netloc.lower()


def helper(args: list[str]) -> int:
    """git's credential-helper protocol for the secret `<name>` of the URL's host."""
    if len(args) != HELPER_WORDS:
        raise RefusedError(
            f"git-credential-sealed takes {HELPER_WORDS} arguments, <name> https://<host> <action>, "
            f"not {len(args)}"
        )
    name, url, action = args
    if not NAME.fullmatch(name):
        raise RefusedError(f"the name {name} is not letters, digits and -, not starting with -")
    host = url_host(url)
    request: dict[str, str] = {}
    for line in sys.stdin:
        key, _, value = line.rstrip("\n").partition("=")
        if not key:
            break
        request.setdefault(key, value)
    if action != "get" or request.get("protocol") != HTTPS or request.get("host", "").lower() != host:
        return 0
    secret = decrypt(name)
    if secret.host != host:
        raise RefusedError(f"the secret {name} names the host {secret.host}, not {host}")
    sys.stdout.write(f"username={secret.user}\npassword={secret.token}\n")
    return 0


def unknown(name: str) -> int:
    """Refuse a base name that is none of the three."""
    raise RefusedError(f"run as ghx, glabx or git-credential-sealed, not `{name}`")


def main(argv: list[str]) -> None:
    """Act as the name that `argv[0]` gives, and exit with its status."""
    name, args = pathlib.Path(argv[0]).name, argv[1:]
    actions = {"ghx": ghx, "glabx": glabx, "git-credential-sealed": helper}
    try:
        status = actions[name](args) if name in actions else unknown(name)
    except RefusedError as e:
        print(f"sealed: {e}", file=sys.stderr)
        sys.exit(REFUSED)
    sys.exit(status)


if __name__ == "__main__":
    main(sys.argv)
