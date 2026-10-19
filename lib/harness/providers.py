"""The model providers of OpenCode and oh-my-pi, generated from one file, `providers.toml`.

`providers.toml` beside the profile holds each model server and account beyond the frontends'
built-in providers once. It may be missing; `examples/providers.toml` shows it. `harness install`
writes each provider as an entry of the `provider` object of OpenCode's opencode.jsonc (`opencode`)
and of oh-my-pi's models.yml (`omp`). A provider is a top-level table, named as models.toml names
it in `<provider>/<model>`:

  api        "anthropic" or "openai-compatible": OpenCode's `npm`, oh-my-pi's `api`
  url        the base URL, up to and with its `/v1`: OpenCode's `options.baseURL`; oh-my-pi's
             `baseUrl`, without the `/v1` for "anthropic", whose client appends `/v1/messages`
  name       optional: OpenCode's `name`
  key        optional: `{env:VAR}` or `{file:PATH}`, OpenCode's `options.apiKey` as written,
             oh-my-pi's `apiKey` as `VAR` or `!cat PATH`. A literal key is refused.
  frontends  optional: the frontends that get the provider, by default FRONTENDS
  models     optional: a table of model tables, keyed by the model id, each with
               name       optional: the model's `name` in both
               reasoning  optional: `reasoning` in both; oh-my-pi gets `false` without it, as
                          OpenCode's default is, or it sends the agent's effort
               context    optional, with `output`: OpenCode's `limit.context`, oh-my-pi's
                          `contextWindow`
               output     optional, with `context`: OpenCode's `limit.output`, oh-my-pi's
                          `maxTokens`
               effort     optional: the reasoning effort that the model always gets, such as
                          "none" or "medium": OpenCode's `options.reasoningEffort`; for oh-my-pi
                          `reasoning = true`, a `compat.reasoningEffortMap` that maps each
                          thinking level of LEVELS to it, and `compat.reasoningDisableMode =
                          "none-effort"`, so that a request sends `reasoning_effort` in every
                          thinking format, and "none" when an agent turns thinking off
               opencode, omp  optional: the frontend's own keys of the model, merged over the rest
  opencode, omp  optional: the frontend's own keys of the provider, merged over the rest

A frontend's own table merges table by table; any other value replaces the generated one. Any
other key, a value of the wrong type, and a profile that still holds `opencode_providers` or
`omp_providers`, exit 2 and name the file.

The module has no verb; its cases run in `harness test`.
"""

import pathlib
import re
import tempfile
import tomllib

from . import HarnessError

FRONTENDS = ("opencode", "omp")
# The `api` of a provider -> (OpenCode's `npm`, oh-my-pi's `api`).
APIS = {"anthropic": ("@ai-sdk/anthropic", "anthropic-messages"),
        "openai-compatible": ("@ai-sdk/openai-compatible", "openai-completions")}
PROVIDER_KEYS = ("api", "url", "name", "key", "frontends", "models", *FRONTENDS)
MODEL_KEYS = ("name", "reasoning", "context", "output", "effort", *FRONTENDS)
# The thinking levels of oh-my-pi 18.12.0, the keys of a model's `compat.reasoningEffortMap`.
LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max")
# A `key`: an environment variable, or a file whose path oh-my-pi's shell reads as written.
ENV_KEY = re.compile(r"\{env:([A-Z_][A-Z0-9_]*)\}")
FILE_KEY = re.compile(r"\{file:([A-Za-z0-9_./~+-]+)\}")
# The profile keys that providers.toml replaces.
OLD_KEYS = ("opencode_providers", "omp_providers")


def load(path, profile=None):
    """The provider tables of `path`, checked as the docstring says; {} when the file is missing.
    `profile`, the loaded profile, must not hold a key of OLD_KEYS."""
    path = pathlib.Path(path)
    if old := [k for k in OLD_KEYS if k in (profile or {})]:
        raise HarnessError(f"the profile holds {', '.join(old)}, which {path} replaces: write each provider "
                           "once there, as examples/providers.toml shows, and remove the key from the profile")
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        raise HarnessError(f"{path} is not UTF-8") from None
    except tomllib.TOMLDecodeError as e:
        raise HarnessError(f"{path} is not TOML: {e}") from None
    for name, provider in data.items():
        check(path, name, provider)
    return data


def check(path, name, provider):
    """Exit 2, naming `path` and the provider `name`, unless `provider` is a provider table."""
    where = f"{path}: [{name}]"
    if not isinstance(provider, dict):
        raise HarnessError(f"{where} is not a table")
    if unknown := sorted(set(provider) - set(PROVIDER_KEYS)):
        raise HarnessError(f"{where} has no key {', '.join(unknown)}; it has {', '.join(PROVIDER_KEYS)}")
    if provider.get("api") not in APIS:
        raise HarnessError(f"{where}: `api` is one of {', '.join(map(repr, APIS))}")
    url = provider.get("url")
    if not (isinstance(url, str) and re.fullmatch(r"https?://\S+", url)):
        raise HarnessError(f"{where}: `url` is the base URL, http:// or https://")
    if provider["api"] == "anthropic" and not url.rstrip("/").endswith("/v1"):
        raise HarnessError(f"{where}: the `url` of an \"anthropic\" provider ends in /v1")
    if "name" in provider and not isinstance(provider["name"], str):
        raise HarnessError(f"{where}: `name` is not a string")
    # The message never holds the value: a `key` that is no form may be the key itself.
    if "key" in provider and not (isinstance(provider["key"], str)
                                  and (ENV_KEY.fullmatch(provider["key"]) or FILE_KEY.fullmatch(provider["key"]))):
        raise HarnessError(f"{where}: `key` is {{env:VARIABLE}} or {{file:PATH}}, never the key itself")
    frontends = provider.get("frontends", list(FRONTENDS))
    if not (isinstance(frontends, list) and frontends and set(frontends) <= set(FRONTENDS)
            and len(set(frontends)) == len(frontends)):
        raise HarnessError(f"{where}: `frontends` is a list of {', '.join(map(repr, FRONTENDS))}, each once")
    for own in FRONTENDS:
        if not isinstance(provider.get(own, {}), dict):
            raise HarnessError(f"{where}: `{own}` is not a table")
    models = provider.get("models", {})
    if not (isinstance(models, dict) and all(isinstance(m, dict) for m in models.values())):
        raise HarnessError(f"{where}: `models` is a table of model tables, [{name}.models.\"<id>\"]")
    for model, table in models.items():
        at = f"{where} model {model!r}"
        if unknown := sorted(set(table) - set(MODEL_KEYS)):
            raise HarnessError(f"{at} has no key {', '.join(unknown)}; it has {', '.join(MODEL_KEYS)}")
        if "name" in table and not isinstance(table["name"], str):
            raise HarnessError(f"{at}: `name` is not a string")
        if "reasoning" in table and not isinstance(table["reasoning"], bool):
            raise HarnessError(f"{at}: `reasoning` is not true or false")
        if ("context" in table) != ("output" in table):
            raise HarnessError(f"{at}: `context` and `output` come together")
        if [k for k in ("context", "output") if k in table and not (type(table[k]) is int and table[k] > 0)]:
            raise HarnessError(f"{at}: `context` and `output` are positive integers")
        if "effort" in table and not (isinstance(table["effort"], str) and table["effort"].strip()):
            raise HarnessError(f"{at}: `effort` is not a string that names an effort, such as \"none\"")
        for own in FRONTENDS:
            if not isinstance(table.get(own, {}), dict):
                raise HarnessError(f"{at}: `{own}` is not a table")


def merged(base, own):
    """`base` with `own` over it: a table that both hold merges, any other value of `own` replaces."""
    out = dict(base)
    for k, v in own.items():
        out[k] = merged(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def chosen(providers, frontend):
    """The providers of `providers` that `frontend` gets, in order."""
    return {n: p for n, p in providers.items() if frontend in p.get("frontends", FRONTENDS)}


def opencode(providers):
    """{name: entry} of the `provider` object of opencode.jsonc."""
    out = {}
    for name, p in chosen(providers, "opencode").items():
        entry = {"npm": APIS[p["api"]][0], **({"name": p["name"]} if "name" in p else {}),
                 "options": {"baseURL": p["url"], **({"apiKey": p["key"]} if "key" in p else {})}}
        if "models" in p:
            entry["models"] = {}
            for model, m in p["models"].items():
                base = {k: m[k] for k in ("name", "reasoning") if k in m}
                if "context" in m:
                    base["limit"] = {"context": m["context"], "output": m["output"]}
                if "effort" in m:
                    base["options"] = {"reasoningEffort": m["effort"]}
                entry["models"][model] = merged(base, m.get("opencode", {}))
        out[name] = merged(entry, p.get("opencode", {}))
    return out


def omp(providers):
    """{name: entry} of the `providers` of oh-my-pi's models.yml."""
    out = {}
    for name, p in chosen(providers, "omp").items():
        url = p["url"].rstrip("/").removesuffix("/v1") if p["api"] == "anthropic" else p["url"]
        entry = {"baseUrl": url, "api": APIS[p["api"]][1]}
        if "key" in p:
            env = ENV_KEY.fullmatch(p["key"])
            entry["apiKey"] = env.group(1) if env else "!cat " + FILE_KEY.fullmatch(p["key"]).group(1)
        if "models" in p:
            entry["models"] = []
            for model, m in p["models"].items():
                # A model without `reasoning` gets the agent's effort under oh-my-pi, and none under
                # OpenCode; `false` sends none.
                base = {"id": model, **({"name": m["name"]} if "name" in m else {}),
                        "reasoning": m.get("reasoning", False)}
                if "context" in m:
                    base |= {"contextWindow": m["context"], "maxTokens": m["output"]}
                # oh-my-pi sends no effort for a model without `reasoning`, and the default
                # disable mode of a Qwen model on a generic host sends `enable_thinking`, not
                # `reasoning_effort`.
                if "effort" in m:
                    base |= {"reasoning": True,
                             "compat": {"reasoningEffortMap": dict.fromkeys(LEVELS, m["effort"]),
                                        "reasoningDisableMode": "none-effort"}}
                entry["models"].append(merged(base, m.get("omp", {})))
        out[name] = merged(entry, p.get("omp", {}))
    return out


# (label, providers.toml, expected OpenCode entries, expected oh-my-pi entries); None for an exit 2.
CASES = [
    ("an anthropic provider with an env key, a model and an oh-my-pi key",
     '[a]\napi = "anthropic"\nurl = "https://h/anthropic/v1"\nname = "A"\nkey = "{env:A_KEY}"\n'
     '[a.models.m]\nname = "M"\nreasoning = true\ncontext = 100\noutput = 10\n',
     {"a": {"npm": "@ai-sdk/anthropic", "name": "A", "options": {"baseURL": "https://h/anthropic/v1",
                                                                  "apiKey": "{env:A_KEY}"},
            "models": {"m": {"name": "M", "reasoning": True, "limit": {"context": 100, "output": 10}}}}},
     {"a": {"baseUrl": "https://h/anthropic", "api": "anthropic-messages", "apiKey": "A_KEY",
            "models": [{"id": "m", "name": "M", "reasoning": True, "contextWindow": 100, "maxTokens": 10}]}}),
    ("an openai-compatible provider with a file key keeps its /v1 for oh-my-pi; a quoted model id stays",
     '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\nkey = "{file:~/.config/k}"\n'
     '[o.models."org/m:7b"]\n',
     {"o": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "https://h/v1", "apiKey": "{file:~/.config/k}"},
            "models": {"org/m:7b": {}}}},
     {"o": {"baseUrl": "https://h/v1", "api": "openai-completions", "apiKey": "!cat ~/.config/k",
            "models": [{"id": "org/m:7b", "reasoning": False}]}}),
    ("a frontend's own keys merge over the rest, of the provider and of a model",
     '[o]\napi = "openai-compatible"\nurl = "http://127.0.0.1:8080/v1"\nomp = { apiKey = "K" }\n'
     'opencode = { options = { timeout = 5 } }\n'
     '[o.models.m]\ncontext = 1\noutput = 1\nopencode = { tool_call = false, options = { reasoningEffort = "none" } }\n'
     'omp = { contextWindow = 2 }\n',
     {"o": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "http://127.0.0.1:8080/v1", "timeout": 5},
            "models": {"m": {"limit": {"context": 1, "output": 1}, "tool_call": False,
                             "options": {"reasoningEffort": "none"}}}}},
     {"o": {"baseUrl": "http://127.0.0.1:8080/v1", "api": "openai-completions", "apiKey": "K",
            "models": [{"id": "m", "reasoning": False, "contextWindow": 2, "maxTokens": 1}]}}),
    ("`frontends` limits a provider to OpenCode",
     '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\nfrontends = ["opencode"]\n',
     {"o": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "https://h/v1"}}}, {}),
    ("`effort` fixes the effort in both, and oh-my-pi's model reasons and sends it in every thinking format",
     '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n[o.models.m]\neffort = "none"\n',
     {"o": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "https://h/v1"},
            "models": {"m": {"options": {"reasoningEffort": "none"}}}}},
     {"o": {"baseUrl": "https://h/v1", "api": "openai-completions",
            "models": [{"id": "m", "reasoning": True, "compat": {
                "reasoningEffortMap": {"minimal": "none", "low": "none", "medium": "none", "high": "none",
                                       "xhigh": "none", "max": "none"},
                "reasoningDisableMode": "none-effort"}}]}}),
    ("a frontend's own keys merge over `effort`",
     '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n[o.models.m]\nreasoning = false\neffort = "medium"\n'
     'opencode = { options = { reasoningEffort = "low", x = 1 } }\nomp = { compat = { reasoningEffortMap = { max = "high" } } }\n',
     {"o": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "https://h/v1"},
            "models": {"m": {"reasoning": False, "options": {"reasoningEffort": "low", "x": 1}}}}},
     {"o": {"baseUrl": "https://h/v1", "api": "openai-completions",
            "models": [{"id": "m", "reasoning": True, "compat": {
                "reasoningEffortMap": {"minimal": "medium", "low": "medium", "medium": "medium", "high": "medium",
                                       "xhigh": "medium", "max": "high"},
                "reasoningDisableMode": "none-effort"}}]}}),
    ("an empty file", "", {}, {}),
    ("a blank effort", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n[o.models.m]\neffort = " "\n',
     None, None),
    ("an effort that is no string", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n[o.models.m]\neffort = 1\n',
     None, None),
    ("a literal key", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\nkey = "sk-LITERAL"\n', None, None),
    ("a file key with a shell character", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n'
     'key = "{file:~/k;rm}"\n', None, None),
    ("an unknown api", '[o]\napi = "openai"\nurl = "https://h/v1"\n', None, None),
    ("no url", '[o]\napi = "openai-compatible"\n', None, None),
    ("an anthropic url without /v1", '[a]\napi = "anthropic"\nurl = "https://h/anthropic"\n', None, None),
    ("OpenCode's key baseURL at the top level", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n'
     'baseURL = "https://h/v1"\n', None, None),
    ("an unknown frontend", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\nfrontends = ["pi"]\n', None, None),
    ("no frontend", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\nfrontends = []\n', None, None),
    ("a context without an output", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n'
     '[o.models.m]\ncontext = 1\n', None, None),
    ("OpenCode's model key limit", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n'
     '[o.models.m]\nlimit = { context = 1, output = 1 }\n', None, None),
    ("a context of zero", '[o]\napi = "openai-compatible"\nurl = "https://h/v1"\n'
     '[o.models.m]\ncontext = 0\noutput = 1\n', None, None),
    ("a provider that is no table", 'o = "x"\n', None, None),
]


def selftest():
    """CASES, the missing file, and the profile's old keys: (number of cases, number wrong)."""
    n = wrong = 0

    def report(ok, label):
        nonlocal n, wrong
        n, wrong = n + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  providers: {label}")

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "providers.toml"
        for label, text, expected_opencode, expected_omp in CASES:
            path.write_text(text)
            try:
                table = load(path)
                got = (opencode(table), omp(table))
                message = ""
            except HarnessError as e:
                got, message = None, str(e)
            if expected_opencode is None:
                report(got is None and str(path) in message and "LITERAL" not in message,
                       f"{label} exits 2, names the file and holds no key: {message or got}")
            else:
                report(got == (expected_opencode, expected_omp), f"{label}: {got}")
        report(load(pathlib.Path(tmp) / "missing.toml") == {}, "a missing file holds no provider")
        for key in OLD_KEYS:
            try:
                load(path, {key: {}})
                message = ""
            except HarnessError as e:
                message = str(e)
            report(key in message and str(path) in message and "examples/providers.toml" in message,
                   f"a profile with {key} exits 2 and names providers.toml: {message}")
    return n, wrong
