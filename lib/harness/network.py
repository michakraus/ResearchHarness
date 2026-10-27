"""The network lists of the Claude Code settings, generated from `settings/network.toml`.

The settings template holds no host. `harness install`, `harness render` of the template and the
subcommands of `harness settings` generate its network rules from two files with one schema: the
harness list `settings/network.toml`, and the overlay `network.toml` beside the profile, which may
be missing. Each file has the top-level arrays `allow`, `infrastructure` and `deny`, each optional,
and an optional table `[deny_reasons]`, keyed by a `deny` entry; nothing else. An entry is a host,
never a URL.

  * `allow` X: `WebFetch(domain:X)` after the template's `permissions.allow`, and X in
    `sandbox.network.allowedDomains`, with `*.X` when X is its own registrable domain. The proxy
    matches the host a request goes to, so a bare `nature.com` does not cover `www.nature.com`;
    a host below its registrable domain, `api.crossref.org`, is one host. An entry `*.X` exits 2.
  * `infrastructure` X: X in `allowedDomains` only, exactly as written; `*.X` is allowed.
  * `deny` X: `WebFetch(domain:X)` after the template's `permissions.deny`, and X in
    `sandbox.network.deniedDomains`; `[deny_reasons]` is `sandbox.network.deniedDomainReasons`.
    `*`, `*.X` and `X:port` are allowed. An entry with a port has no WebFetch rule: Claude Code
    matches a WebFetch rule against the host of the URL, so a rule with a port denies nothing.
    The sandbox checks `deniedDomains` before `allowedDomains`.

The two files are one union, the harness list's entries first. An `allow` or `infrastructure` entry
that a `deny` entry without a port matches — the same host, a host or a `*.` form below a `*.`
entry, or any host for `*` — is left out of every generated allow list, and so is the `*.X` form of
an `allow` host X that such an entry matches: a deny `*.X` keeps X and drops `*.X`. A `deny` entry
with a port leaves the host on the allow lists; the sandbox refuses that port alone. With no `deny`
entry the template gets no `deniedDomains` and no `deniedDomainReasons`.

Exit 2, naming the file and the key: an unknown key; a value of the wrong type; an entry that is
not a string, is a URL, or is no host name; a port outside `deny`; `*` outside `deny`; `*.` in
`allow`; a host in `allow` or `infrastructure` and in `deny` of the same file; a `deny_reasons` key
that is no `deny` entry of either file. So does a profile that still has the key `extra_domain`,
and a settings template that holds a network rule of its own or has no
`sandbox.network.allowedDomains`.

The other frontends read the template, not these lists: the lists are Claude Code's alone.

The module has no subcommand; its cases run in `harness test`.
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib
from typing import Any

from . import REPO, HarnessError

LIST = REPO / "settings" / "network.toml"
TEMPLATE = REPO / "settings" / "settings.proposal.json"
LISTS = ("allow", "infrastructure", "deny")
KEYS = (*LISTS, "deny_reasons")
LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
HOST = re.compile(rf"(?:\*\.)?{LABEL}(?:\.{LABEL})*")
WEBFETCH = "WebFetch(domain:"

# Suffixes under which the registrable domain is three labels, not two. Only the ones the
# harness list needs; a general public-suffix list would be a dependency.
MULTI_LABEL_SUFFIXES = ("ac.uk", "co.uk", "org.uk", "gov.uk")


def registrable(host):
    """The registrable domain of a host — nature.com for www.nature.com, core.ac.uk for itself."""
    labels = host.split(".")
    n = 3 if host.endswith(MULTI_LABEL_SUFFIXES) else 2
    return ".".join(labels[-n:]) if len(labels) >= n else host


def check_entry(path, key, entry):
    """Exit 2, naming `path` and `key`, unless `entry` is a host that `key` takes."""
    if not isinstance(entry, str):
        raise HarnessError(f"{path}: {key} holds {entry!r}, which is not a string")
    if re.search(r"://|[/?#@\s]", entry):
        raise HarnessError(f"{path}: {key} entry {entry!r} is a URL; write its host alone")
    host, colon, port = entry.rpartition(":") if ":" in entry else (entry, "", "")
    if colon and key != "deny":
        raise HarnessError(f"{path}: {key} entry {entry!r} has a port; only a deny entry takes one")
    if colon and not (port.isdigit() and 0 < int(port) < 65536):
        raise HarnessError(f"{path}: {key} entry {entry!r} has no port number after its colon")
    if host == "*":
        if key != "deny":
            raise HarnessError(f"{path}: {key} entry {entry!r} is every host; only a deny entry takes it")
        return
    if not HOST.fullmatch(host):
        raise HarnessError(f"{path}: {key} entry {entry!r} is not a host name")
    if key == "allow" and host.startswith("*."):
        raise HarnessError(
            f"{path}: allow entry {entry!r} is a wildcard; write {host[2:]!r}: WebFetch takes a "
            "domain, and the install adds the `*.` form to the sandbox list"
        )


def read(path, missing_ok):
    """{key: value} of the network list at `path`, every key of KEYS present; {} for a missing
    file when `missing_ok`. Exits 2 on a file that breaks the schema."""
    try:
        text = pathlib.Path(path).read_bytes().decode("utf-8")
    except FileNotFoundError:
        if missing_ok:
            return {}
        raise HarnessError(f"no network list at {path}") from None
    except OSError as e:
        raise HarnessError(f"{path} cannot be read: {e.strerror}") from None
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None
    if unknown := [k for k in data if k not in KEYS]:
        raise HarnessError(
            f"{path}: no key {', '.join(unknown)}; the keys are allow, infrastructure, deny and "
            "[deny_reasons]"
        )
    out = {}
    for key in LISTS:
        value = data.get(key, [])
        if not isinstance(value, list):
            raise HarnessError(f"{path}: {key} is not an array")
        for entry in value:
            check_entry(path, key, entry)
        out[key] = value
    reasons = data.get("deny_reasons", {})
    if not isinstance(reasons, dict):
        raise HarnessError(f"{path}: deny_reasons is not a table")
    for entry, reason in reasons.items():
        if not isinstance(reason, str) or not reason.strip():
            raise HarnessError(f"{path}: deny_reasons.{json.dumps(entry)} is not a non-empty string")
    out["deny_reasons"] = reasons
    for key in ("allow", "infrastructure"):
        if both := [h for h in out[key] if h in out["deny"]]:
            raise HarnessError(f"{path}: {both[0]!r} is in both {key} and deny")
    return out


def merged(overlay: str | pathlib.Path) -> dict[str, Any]:
    """The union of the harness list and the overlay at `overlay`, the harness list's entries first:
    {key: value} of every key of KEYS."""
    files: list[tuple[str | pathlib.Path, dict[str, Any]]] = [
        (LIST, read(LIST, missing_ok=False)),
        (overlay, read(overlay, missing_ok=True)),
    ]
    out: dict[str, Any] = {
        key: list(dict.fromkeys(e for _, data in files for e in data.get(key, []))) for key in LISTS
    }
    out["deny_reasons"] = {}
    for path, data in files:
        for entry, reason in data.get("deny_reasons", {}).items():
            if entry not in out["deny"]:
                raise HarnessError(
                    f"{path}: deny_reasons key {entry!r} is no deny entry of {LIST} or {overlay}"
                )
            out["deny_reasons"][entry] = reason
    return out


def denies(entry, host):
    """Whether the deny `entry`, which has no port, matches `host`, a host or a `*.` form."""
    entry, host = entry.lower(), host.lower()
    return entry in ("*", host) or (entry.startswith("*.") and host.endswith(entry[1:]))


def generate(lists):
    """(WebFetch allow rules, WebFetch deny rules, allowedDomains, deniedDomains,
    deniedDomainReasons) of the merged `lists`."""
    whole = [d for d in lists["deny"] if ":" not in d]

    def kept(hosts):
        return [h for h in hosts if not any(denies(d, h) for d in whole)]

    allow = kept(lists["allow"])
    mirror = kept(form for h in allow for form in ([h, "*." + h] if h == registrable(h) else [h]))
    return (
        [f"{WEBFETCH}{h})" for h in allow],
        [f"{WEBFETCH}{d})" for d in lists["deny"] if ":" not in d],
        list(dict.fromkeys(kept(lists["infrastructure"]) + mirror)),
        list(lists["deny"]),
        dict(lists["deny_reasons"]),
    )


def apply(cfg, profile, overlay):
    """`cfg`, the rendered settings template, with the network rules of the harness list and the
    overlay at `overlay` in place."""
    if "extra_domain" in profile:
        raise HarnessError(
            f"the profile key extra_domain is retired: move its hosts into the allow array of "
            f"{overlay} and remove the key"
        )
    permissions = cfg.get("permissions", {})
    network = cfg.get("sandbox", {}).get("network", {})
    if "allowedDomains" not in network:
        raise HarnessError(
            f"{TEMPLATE} has no sandbox.network.allowedDomains for the network lists of {LIST}"
        )
    own = [r for kind in ("allow", "deny") for r in permissions.get(kind, []) if r.startswith(WEBFETCH)]
    own += [
        *network["allowedDomains"],
        *network.get("deniedDomains", []),
        *network.get("deniedDomainReasons", {}),
    ]
    if own:
        raise HarnessError(f"{TEMPLATE} holds the network rule {own[0]!r}; a host goes into {LIST}")
    allow, deny, allowed, denied, reasons = generate(merged(overlay))
    permissions["allow"] = [*permissions.get("allow", []), *allow]
    permissions["deny"] = [*permissions.get("deny", []), *deny]
    network["allowedDomains"] = allowed
    if denied:
        network["deniedDomains"] = denied
    if reasons:
        network["deniedDomainReasons"] = reasons
    return cfg


def selftest():
    """The generation, the precedence, each exit 2, the missing overlay, and the other frontends'
    output, which no network list changes: (number of cases, number wrong)."""
    from . import frontends
    from . import profile as profile_module
    from .install_cases import Scratch

    n = wrong = 0

    def check(ok, label):
        nonlocal n, wrong
        n += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'}  network: {label}")

    def case(ok, label):
        try:
            ok = ok()
        except Exception as e:  # a case that crashes is BAD, and the next case still runs
            ok, label = False, f"{label}; raised {type(e).__name__}: {e}"
        check(ok, label)

    def refused(call):
        """The message of the HarnessError that `call` raises, or None."""
        try:
            call()
        except HarnessError as e:
            return str(e)
        return None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        harness_list = read(LIST, False)
        dummy = profile_module.load(profile_module.DUMMY)

        def overlay(text, name="network.toml"):
            path = tmp / name
            path.write_text(text)
            return path

        def rendered(text, profile=dummy):
            """The template rendered with `profile` and the overlay `text`."""
            cfg = json.loads(profile_module.render_file(TEMPLATE, profile))
            return apply(cfg, profile, overlay(text))

        def net(cfg):
            return cfg["sandbox"]["network"]

        def fetch(cfg, kind):
            return [r for r in cfg["permissions"][kind] if r.startswith(WEBFETCH)]

        base = rendered("")
        missing = apply(json.loads(profile_module.render_file(TEMPLATE, dummy)), dummy, tmp / "absent.toml")

        # The harness list itself, and the template that keeps no host.
        template = json.loads(TEMPLATE.read_text())
        case(
            lambda: (
                not [
                    r for k in ("allow", "deny") for r in template["permissions"][k] if r.startswith(WEBFETCH)
                ]
                and net(template) == {**net(template), "allowedDomains": []}
                and "deniedDomains" not in net(template)
            ),
            "the settings template holds no WebFetch(domain:…) rule and an empty allowedDomains",
        )
        case(
            lambda: (
                harness_list["deny"] == []
                and all(len(set(harness_list[k])) == len(harness_list[k]) for k in LISTS)
            ),
            "the harness list has no deny entry, and no entry twice",
        )
        case(
            lambda: missing == base,
            "a missing overlay gives the harness list alone, as an empty overlay does",
        )

        # The generation of each list.
        allow = fetch(base, "allow")
        case(
            lambda: (
                allow == [f"{WEBFETCH}{h})" for h in harness_list["allow"]]
                and base["permissions"]["allow"]
                == json.loads(profile_module.render_file(TEMPLATE, dummy))["permissions"]["allow"] + allow
            ),
            "each allow host is a WebFetch(domain:…) rule after the template's own allow rules",
        )
        case(
            lambda: (
                {"nature.com", "*.nature.com", "core.ac.uk", "*.core.ac.uk", "api.crossref.org"}
                <= set(net(base)["allowedDomains"])
                and "*.api.crossref.org" not in net(base)["allowedDomains"]
                and "*.ui.adsabs.harvard.edu" not in net(base)["allowedDomains"]
            ),
            "an allow host that is its own registrable domain gives X and *.X to allowedDomains, core.ac.uk "
            "under its three-label suffix too; a host below its registrable domain gives itself alone",
        )
        case(
            lambda: (
                net(base)["allowedDomains"][: len(harness_list["infrastructure"])]
                == harness_list["infrastructure"]
                and f"{WEBFETCH}api.anthropic.com)" not in allow
                and "*.github.io" in net(base)["allowedDomains"]
            ),
            "each infrastructure entry is in allowedDomains exactly as written, first, and is no WebFetch rule",
        )
        case(
            lambda: (
                "deniedDomains" not in net(base)
                and "deniedDomainReasons" not in net(base)
                and fetch(base, "deny") == []
            ),
            "with no deny entry, no deniedDomains, no deniedDomainReasons and no WebFetch deny",
        )
        denied = rendered(
            'deny = ["bad.example", "*.worse.example", "ssh.example:22", "*"]\n'
            '[deny_reasons]\n"bad.example" = "The host is retired."\n'
        )
        case(
            lambda: (
                fetch(denied, "deny")
                == [f"{WEBFETCH}bad.example)", f"{WEBFETCH}*.worse.example)", f"{WEBFETCH}*)"]
                and denied["permissions"]["deny"][:-3] == base["permissions"]["deny"]
            ),
            "each deny entry without a port is a WebFetch deny after the template's own deny rules, `*` and "
            "`*.X` too; an entry with a port is none",
        )
        case(
            lambda: (
                net(denied)["deniedDomains"] == ["bad.example", "*.worse.example", "ssh.example:22", "*"]
                and net(denied)["deniedDomainReasons"] == {"bad.example": "The host is retired."}
            ),
            "each deny entry is in deniedDomains as written, and deny_reasons is deniedDomainReasons",
        )

        # The precedence of deny over allow and infrastructure, over the union of both files.
        one = rendered('deny = ["nature.com", "*.julialang.org"]\n')
        case(
            lambda: (
                f"{WEBFETCH}nature.com)" not in fetch(one, "allow")
                and not {"nature.com", "*.nature.com"} & set(net(one)["allowedDomains"])
                and f"{WEBFETCH}nature.com)" in fetch(one, "deny")
            ),
            "an overlay deny of a harness allow host removes its WebFetch rule and both sandbox forms",
        )
        case(
            lambda: (
                not {
                    "pkg.julialang.org",
                    "*.pkg.julialang.org",
                    "julialang-s3.julialang.org",
                    "docs.julialang.org",
                }
                & set(net(one)["allowedDomains"])
                and f"{WEBFETCH}docs.julialang.org)" not in fetch(one, "allow")
                and "julialang.org" in net(one)["allowedDomains"]
            ),
            "a deny of *.X removes each host and *. form below X, and keeps X itself",
        )
        mirrored = rendered('deny = ["*.nature.com"]\n')
        case(
            lambda: (
                f"{WEBFETCH}nature.com)" in fetch(mirrored, "allow")
                and "nature.com" in net(mirrored)["allowedDomains"]
                and "*.nature.com" not in net(mirrored)["allowedDomains"]
            ),
            "a deny of *.X, with X in allow, keeps the WebFetch rule and X, and drops the mirror form *.X",
        )
        everything = rendered('deny = ["*"]\n')
        case(
            lambda: fetch(everything, "allow") == [] and net(everything)["allowedDomains"] == [],
            "a deny of * removes every allow and infrastructure host",
        )
        port = rendered('deny = ["github.com:22"]\n')
        case(
            lambda: (
                f"{WEBFETCH}github.com)" in fetch(port, "allow")
                and "github.com" in net(port)["allowedDomains"]
                and fetch(port, "deny") == []
            ),
            "a deny entry with a port leaves its host on the allow lists, and has no WebFetch rule",
        )
        extra = rendered(
            'allow = ["library.example.org", "nature.com"]\ninfrastructure = ["*.mirror.example.org"]\n'
        )
        case(
            lambda: (
                fetch(extra, "allow") == allow + [f"{WEBFETCH}library.example.org)"]
                and net(extra)["allowedDomains"]
                == net(base)["allowedDomains"][: len(harness_list["infrastructure"])]
                + ["*.mirror.example.org"]
                + net(base)["allowedDomains"][len(harness_list["infrastructure"]) :]
                + ["library.example.org"]
            ),
            "an overlay adds its entries after the harness list's, and an entry of both files once",
        )

        # Each exit 2 names the file and the key.
        for label, text, words in [
            ("an unknown key", 'ask = ["x.org"]\n', ["no key ask"]),
            ("an array that is a string", 'allow = "x.org"\n', ["allow is not an array"]),
            ("a non-string entry", "allow = [1]\n", ["allow holds 1"]),
            ("a URL with a scheme", 'allow = ["https://x.org"]\n', ["allow entry", "is a URL"]),
            ("a host with a path", 'infrastructure = ["x.org/a"]\n', ["infrastructure entry", "is a URL"]),
            ("a host with a query", 'deny = ["x.org?q=1"]\n', ["deny entry", "is a URL"]),
            ("a port in allow", 'allow = ["x.org:443"]\n', ["allow entry", "has a port"]),
            (
                "a port in infrastructure",
                'infrastructure = ["x.org:443"]\n',
                ["infrastructure entry", "has a port"],
            ),
            ("a colon with no port number", 'deny = ["x.org:ssh"]\n', ["deny entry", "no port number"]),
            ("* in infrastructure", 'infrastructure = ["*"]\n', ["infrastructure entry", "every host"]),
            ("*. in allow", 'allow = ["*.x.org"]\n', ["allow entry", "is a wildcard", "'x.org'"]),
            ("no host name", 'deny = ["x..org"]\n', ["deny entry", "is not a host name"]),
            ("a host in allow and deny", 'allow = ["x.org"]\ndeny = ["x.org"]\n', ["in both allow and deny"]),
            (
                "a host in infrastructure and deny",
                'infrastructure = ["x.org"]\ndeny = ["x.org"]\n',
                ["in both infrastructure and deny"],
            ),
            ("deny_reasons that is no table", 'deny_reasons = "x"\n', ["deny_reasons is not a table"]),
            (
                "an empty reason",
                'deny = ["x.org"]\n[deny_reasons]\n"x.org" = ""\n',
                ["deny_reasons", "not a non-empty string"],
            ),
            (
                "a reason for no deny entry",
                'deny = ["x.org"]\n[deny_reasons]\n"y.org" = "No."\n',
                ["deny_reasons key 'y.org'", "is no deny entry"],
            ),
            ("text that is not TOML", "allow = [\n", ["is not TOML"]),
        ]:
            message = refused(lambda: rendered(text))
            case(
                lambda: (
                    message is not None
                    and str(tmp / "network.toml") in message
                    and all(w in message for w in words)
                ),
                f"an overlay with {label} exits 2 and names the file and the key: {message!r}",
            )
        message = refused(lambda: rendered("", {**dummy, "extra_domain": ["x.org"]}))
        case(
            lambda: (
                message is not None and "extra_domain" in message and str(tmp / "network.toml") in message
            ),
            f"a profile with extra_domain exits 2 and names network.toml: {message!r}",
        )
        for label, edit in [
            ("a WebFetch(domain:…) rule", lambda c: c["permissions"]["allow"].append(f"{WEBFETCH}x.org)")),
            ("an allowedDomains entry", lambda c: net(c)["allowedDomains"].append("x.org")),
            ("no allowedDomains", lambda c: net(c).pop("allowedDomains")),
        ]:
            cfg = json.loads(profile_module.render_file(TEMPLATE, dummy))
            edit(cfg)
            message = refused(lambda: apply(cfg, dummy, tmp / "absent.toml"))
            case(
                lambda: message is not None and str(TEMPLATE) in message,
                f"a settings template with {label} exits 2 and names the template: {message!r}",
            )

        # The subcommands that render the template: `harness render`, and `harness settings` through
        # read_settings. A bad overlay exits 2 with one line.
        scratch = Scratch(check, tmp / "scratch")
        scratch.tmp.mkdir()
        home, _, _ = scratch.fresh()
        (home / "network.toml").write_text('allow = ["library.example.org"]\ndeny = ["bad.example"]\n')
        p = subprocess.run(
            [
                sys.executable,
                str(REPO / "bin" / "harness"),
                "--profile",
                str(home / "profile.toml"),
                "render",
                str(TEMPLATE),
            ],
            capture_output=True,
            text=True,
            env=Scratch.env(home),
            check=False,
        )
        out = json.loads(p.stdout) if p.returncode == 0 else {}
        case(
            lambda: (
                f"{WEBFETCH}library.example.org)" in fetch(out, "allow")
                and net(out)["deniedDomains"] == ["bad.example"]
            ),
            f"`harness render` of the settings template generates the network rules with the overlay: {p.returncode}",
        )
        # An adapter module whose PROFILE the case sets and restores.
        claude: Any = next(a for a in frontends.load() if a.NAME == "claude")
        saved, claude.PROFILE = claude.PROFILE, str(home / "profile.toml")
        try:
            cfg = claude.read_settings(TEMPLATE)
        finally:
            claude.PROFILE = saved
        case(
            lambda: (
                f"{WEBFETCH}library.example.org)" in fetch(cfg, "allow")
                and net(cfg)["deniedDomains"] == ["bad.example"]
            ),
            "`harness settings` reads the settings template with the generated network rules",
        )
        (home / "network.toml").write_text('allow = ["https://x.org"]\n')
        p = subprocess.run(
            [
                sys.executable,
                str(REPO / "bin" / "harness"),
                "--profile",
                str(home / "profile.toml"),
                "render",
                str(TEMPLATE),
            ],
            capture_output=True,
            text=True,
            env=Scratch.env(home),
            check=False,
        )
        case(
            lambda: (
                p.returncode == 2
                and len(p.stderr.strip().splitlines()) == 1
                and str(home / "network.toml") in p.stderr
                and "Traceback" not in p.stderr
            ),
            f"`harness render` with a bad overlay exits 2 with one line that names it: {p.returncode}, "
            f"{p.stderr.strip()[-200:]!r}",
        )

        # `harness install`: an overlay with allow, infrastructure and deny entries changes the Claude
        # Code settings and leaves every file of OpenCode and oh-my-pi as it is.
        def install(text):
            base, claude_dir, _ = scratch.fresh()
            if text is not None:
                (base / "network.toml").write_text(text)
            code, output = scratch.run(base, "--apply")
            # A file names its scratch HOME, which differs from one install to the next.
            files = {
                str(p.relative_to(base)): p.read_bytes().replace(str(base).encode(), b"BASE")
                for root in ("opencode", "omp")
                for p in sorted((base / root).rglob("*"))
                if p.is_file()
            }
            return code, output, files, json.loads((claude_dir / "settings.json").read_text())

        plain = install(None)
        changed = install(
            'allow = ["library.example.org"]\ninfrastructure = ["mirror.example.org"]\n'
            'deny = ["github.com", "*.example.net", "ssh.example:22"]\n'
            '[deny_reasons]\n"github.com" = "Not here."\n'
        )
        case(
            lambda: plain[0] == 0 and changed[0] == 0 and plain[2] and plain[2] == changed[2],
            f"`harness install --apply` writes the same OpenCode and oh-my-pi files with an overlay deny: "
            f"{plain[0]}, {changed[0]}, {len(plain[2])} files, {scratch.tail(plain[1] + changed[1])}",
        )
        case(
            lambda: (
                f"{WEBFETCH}github.com)" in fetch(changed[3], "deny")
                and net(changed[3])["deniedDomainReasons"] == {"github.com": "Not here."}
                and "deniedDomains" not in net(plain[3])
            ),
            "`harness install --apply` writes the overlay's deny into the Claude Code settings alone",
        )
    return n, wrong
