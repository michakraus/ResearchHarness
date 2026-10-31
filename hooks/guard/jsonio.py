"""The reader of JSON text: `loads` and `load` return the top-level value of a JSON text, and
refuse with `HarnessError` what Python's `json` accepts but another program reads otherwise.

`json` keeps the last value of a key that an object holds twice, reads `NaN`, `Infinity` and
`-Infinity`, reads a number that overflows as infinity, and raises `RecursionError` on a deep
nesting. Here each of them is refused with a message that names the text's `where` and the line of
the offence, as is a nesting deeper than MAX_DEPTH, where the top-level value is depth 1. An empty
text, a text that starts with a byte order mark, and a top level of another type than `top` names
(an object by default; `list`, `str`, or `object` for any value) are refused with a message that
names `where`. No other exception leaves `loads` or `load`.

The module imports only the standard library and `HarnessError` of its package, so that it runs in
any package that defines a `HarnessError`.
"""

import json
import math
import os
import pathlib
import re
import stat
import tempfile
import time
from typing import NoReturn, Protocol, cast, overload

from . import HarnessError

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None

MAX_DEPTH = 200
BOM = chr(0xFEFF)
# JSON's whitespace; a text of these alone is empty.
WHITESPACE = " \t\r\n"
# A string up to its closing quote, in a form that matches in one pass without backtracking.
STRING = r'"[^"\\]*(?:\\.[^"\\]*)*"'
# A string, the rest of a string that no quote closes, or a bracket: the depth scan counts the
# brackets outside the strings, in time linear in the text.
BRACKET = re.compile(STRING + r"?|[\[\]{}]", re.DOTALL)
# The tokens that locate a refused value: a string, a number, a constant and the punctuation. The
# letters of `true`, `false` and `null` match nothing and are skipped.
TOKEN = re.compile(
    rf"(?P<string>{STRING})"
    r"|(?P<number>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
    r"|(?P<constant>-?Infinity|NaN)"
    r"|(?P<punctuation>[{}\[\]:,])",
    re.DOTALL,
)
# Decodes the key of an object, which the parser has read.
DECODER = json.JSONDecoder()
# The types that the `top` of `loads` names, with the kind of the top level that each takes.
TOPS: dict[type[object], str] = {
    dict: "a JSON object",
    list: "a JSON array",
    str: "a JSON string",
    object: "a JSON value",
}


class OffenceError(Exception):
    """An offence that a hook of `json.loads` meets: `duplicate`, `constant` or `overflow`."""

    def __init__(self, kind: str, token: str) -> None:
        super().__init__(kind, token)
        self.kind, self.token = kind, token


def unique(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """The object of `pairs`; a key that occurs twice is an offence."""
    found = dict(pairs)
    if len(found) < len(pairs):
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise OffenceError("duplicate", key)
            seen.add(key)
    return found


def constant(token: str) -> NoReturn:
    """`NaN`, `Infinity` and `-Infinity`, which JSON does not allow, are an offence."""
    raise OffenceError("constant", token)


def finite(token: str) -> float:
    """The value of a number with a fraction or an exponent; one that overflows is an offence."""
    value = float(token)
    if math.isinf(value):
        raise OffenceError("overflow", token)
    return value


def overflows(number: str) -> bool:
    """Whether a number token with a fraction or an exponent reads as infinity; an integer reads as
    an `int`, which does not overflow."""
    return any(c in number for c in ".eE") and math.isinf(float(number))


def line_of(text: str, index: int) -> int:
    """The line of `text`, from 1, that holds the character at `index`."""
    return text.count("\n", 0, index) + 1


def too_deep(text: str) -> int | None:
    """The index of the first bracket outside a string that opens depth MAX_DEPTH + 1, or None."""
    depth = 0
    for m in BRACKET.finditer(text):
        if m.group() in ("[", "{"):
            depth += 1
            if depth > MAX_DEPTH:
                return m.start()
        elif m.group() in ("]", "}"):
            depth -= 1
    return None


def located(text: str) -> int:
    """The index in `text` of the offence that the parser meets first. The parser reads the text in
    order: it raises at a constant or an overflow where it reads one, and at a key twice where the
    object that holds the key ends, naming the first key of that object that repeats. The tokens up
    to the offence are valid JSON."""
    keys: list[set[str] | None] = []  # per open bracket: the keys of an object, None for an array
    repeats: list[int] = []  # per open bracket: the index of its first key that repeats, or -1
    expect_key = False
    for m in TOKEN.finditer(text):
        piece, kind = m.group(), m.lastgroup
        if kind == "constant" or (kind == "number" and overflows(piece)):
            return m.start()
        if piece in ("{", "["):
            keys.append(set() if piece == "{" else None)
            repeats.append(-1)
            expect_key = piece == "{"
        elif piece in ("}", "]"):
            keys.pop()
            if (repeat := repeats.pop()) >= 0:
                return repeat
            expect_key = False
        elif piece in (",", ":"):
            expect_key = piece == ","
        elif kind == "string" and expect_key and (seen := keys[-1]) is not None:
            key: str = DECODER.raw_decode(piece)[0]
            if key in seen and repeats[-1] < 0:
                repeats[-1] = m.start()
            seen.add(key)
            expect_key = False
    raise AssertionError(f"no offence in {len(text)} characters that the parser refused")


def kind_of(value: object) -> str:
    """The JSON kind of a top-level value."""
    if isinstance(value, dict):
        return "a JSON object"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, bool):
        return "a boolean"
    return "null" if value is None else "a number"


@overload
def loads(text: str, *, where: str, top: type[dict[str, object]] = ...) -> dict[str, JsonValue]: ...
@overload
def loads(text: str, *, where: str, top: type[list[object]]) -> list[JsonValue]: ...
@overload
def loads(text: str, *, where: str, top: type[str]) -> str: ...
@overload
def loads(text: str, *, where: str, top: type[object]) -> JsonValue: ...
def loads(text: str, *, where: str, top: type[object] = dict) -> JsonValue:
    """The JSON value of `text`, whose top level is of the type `top`: an object by default,
    `list` or `str`, or any value for `object`; `where` names the text in a refusal."""
    if text.startswith(BOM):
        raise HarnessError(f"{where}: starts with a byte order mark (U+FEFF), which JSON does not allow")
    if not text.strip(WHITESPACE):
        raise HarnessError(f"{where}: empty, where {TOPS[top]} belongs")
    deep = too_deep(text)
    if deep is not None:
        raise HarnessError(f"{where}: line {line_of(text, deep)}: nested deeper than {MAX_DEPTH}")
    try:
        value: object = json.loads(
            text, object_pairs_hook=unique, parse_constant=constant, parse_float=finite
        )
    except OffenceError as e:
        what = {
            "duplicate": f"the key {json.dumps(e.token, ensure_ascii=False)} occurs twice in one object",
            "constant": f"{e.token} is not a JSON number",
            "overflow": f"the number {e.token} overflows to infinity",
        }[e.kind]
        raise HarnessError(f"{where}: line {line_of(text, located(text))}: {what}") from None
    except json.JSONDecodeError as e:
        raise HarnessError(f"{where}: line {e.lineno}: not JSON: {e.msg}") from None
    except ValueError as e:  # an integer of more digits than `int` reads
        raise HarnessError(f"{where}: not JSON: {e}") from None
    if top is not object and not isinstance(value, top):
        raise HarnessError(f"{where}: the top level is {kind_of(value)}, not {TOPS[top]}")
    return cast("JsonValue", value)


def load(path: str | os.PathLike[str]) -> dict[str, JsonValue]:
    """The JSON object of the UTF-8 file at `path`; a refusal names the path."""
    p = pathlib.Path(path)
    try:
        # A read of a FIFO or a device can block, so only a regular file is read.
        regular = stat.S_ISREG(p.stat().st_mode)
        data = p.read_bytes() if regular else b""
    except OSError as e:
        raise HarnessError(f"cannot read {p}: {e.strerror}") from None
    except ValueError as e:  # a NUL character in the path
        raise HarnessError(f"cannot read {p}: {e}") from None
    if not regular:
        raise HarnessError(f"cannot read {p}: not a regular file")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HarnessError(f"{p} is not UTF-8: {e.reason} at byte {e.start}") from None
    return loads(text, where=str(p))


# The cases. Every fixture of a refusal puts its offence on line 7, and no other 7 is in it.
WHERE = "the-where-text"
# The seconds that a refusal of a text of 400 KB takes at most; a linear scan takes milliseconds.
SLOW = 10
# Line 3 holds a finite number, so an overflow is told from the first number of the text.
HEAD = '{\n  "a": true,\n  "b": 1.5,\n  "c": true,\n  "o": {\n    "x": true,\n'  # lines 1-6
TAIL = "\n  }\n}\n"
DUPLICATE = (
    '{\n  "a": true,\n  "b": true,\n  "c": true,\n  "o": {\n    "k": "first",\n    "k": "second"\n  }\n}\n'
)


def at_seven(value: str) -> str:
    """A text whose line 7 is `    "k": <value>`, inside the object "o" at depth 2."""
    return f'{HEAD}    "k": {value}{TAIL}'


def refusal(text: str) -> str:
    """The message of the HarnessError that `loads(text)` raises, or `accepted`."""
    try:
        loads(text, where=WHERE)
    except HarnessError as e:
        return str(e)
    return "accepted"


def load_refusal(path: pathlib.Path) -> str:
    """The message of the HarnessError that `load(path)` raises, or `accepted`."""
    try:
        load(path)
    except HarnessError as e:
        return str(e)
    return "accepted"


def on_line_seven(message: str, where: str = WHERE) -> bool:
    """Whether `message` names `where` and line 7."""
    return where in message and "line 7" in message.replace(where, "")


class Case(Protocol):
    """The recorder of one case: its label and its verdict."""

    def __call__(self, label: str, *, ok: bool) -> None: ...


def top_refusal(text: str, top: type[object]) -> str:
    """The message of the HarnessError that `loads(text, top=top)` raises, or `accepted`."""
    try:
        loads(text, where=WHERE, top=top)
    except HarnessError as e:
        return str(e)
    return "accepted"


def top_cases(case: Case) -> None:
    """Each type that `top` names takes its kind of top level and refuses every other kind."""
    texts = {"object": '{"a": 1}', "array": "[1]", "string": '"s"', "number": "1", "null": "null"}
    takes: dict[type[object], set[str]] = {
        dict: {"object"},
        list: {"array"},
        str: {"string"},
        object: set(texts),
    }
    for top, kinds in takes.items():
        for kind, text in texts.items():
            message = top_refusal(text, top)
            want = "accepted" if kind in kinds else "refused"
            got = "accepted" if message == "accepted" else "refused"
            case(
                f"top={top.__name__}: a top-level {kind} is {want} -> {message}",
                ok=got == want and (got == "accepted" or (WHERE in message and TOPS[top] in message)),
            )
    for text, top, value in (
        ('[1, {"b": null}]', list, [1, {"b": None}]),
        ('"s"', str, "s"),
        ("2.5", object, 2.5),
        ("null", object, None),
    ):
        got: JsonValue = loads(text, where=WHERE, top=top)
        case(f"top={top.__name__}: {text} -> {got!r}", ok=got == value and type(got) is type(value))
    for label, text in (
        ("a key twice inside the array", '[{"k": 1, "k": 2}]'),
        ("NaN in the array", "[NaN]"),
        ("the empty text", ""),
        ("a text that starts with U+FEFF", BOM + "[1]"),
    ):
        message = top_refusal(text, list)
        case(f"top=list: {label} is refused and names where -> {message}", ok=WHERE in message)


def value_cases(case: Case) -> None:
    """The signature of `loads`, a value, CRLF line ends, and the refusals that name a line."""
    code = loads.__code__
    params = code.co_varnames[: code.co_argcount]
    keywords = code.co_varnames[code.co_argcount : code.co_argcount + code.co_kwonlyargcount]
    defaults = loads.__kwdefaults__
    case(
        f"loads(text, *, where, top=dict): {params}, keyword-only {keywords}, {defaults}",
        ok=params == ("text",) and keywords == ("where", "top") and defaults == {"top": dict},
    )
    top_cases(case)
    value: dict[str, JsonValue] = {"a": [1, 2.5, "x", True, None], "b": {"c": "é"}, "d": 0.0}
    text = '{"a": [1, 2.5, "x", true, null], "b": {"c": "é"}, "d": 1e-400}'
    got = loads(text, where=WHERE)
    case(f"an object of arrays, numbers, strings, true, null and 1e-400 -> {got}", ok=got == value)
    got = loads('{\r\n  "a": 1,\r\n  "b": [\r\n    2\r\n  ]\r\n}\r\n', where=WHERE)
    case(f"CRLF line ends -> {got}", ok=got == {"a": 1, "b": [2]})

    message = refusal(DUPLICATE)
    case(
        f"a key twice in a nested object, the second on line 7, names the key -> {message}",
        ok=on_line_seven(message) and '"k"' in message,
    )
    message = refusal(at_seven('{"\\u006b": 1, "k": 2}'))
    case(f"a key twice, once as an escape -> {message}", ok=on_line_seven(message))
    # The inner object's key "k" is no duplicate of the outer "k" on line 5.
    message = refusal('{\n  "o": {\n    "k": 1\n  },\n  "k": 2,\n  "z": 1,\n  "z": 2\n}\n')
    case(
        f"a key of a closed inner object and the outer one; the key twice is named -> {message}",
        ok=on_line_seven(message) and '"z"' in message,
    )
    # The parser names the first key of an object that repeats: "q" on line 7, not "r" on line 9.
    message = refusal('{\n  "q": 1,\n' + "\n" * 4 + '  "q": 2,\n  "r": 1,\n  "r": 2\n}\n')
    case(f"two keys twice in one object, the first on line 7 -> {message}", ok=on_line_seven(message))
    # The parser meets the key twice of the inner object first, where that object ends.
    for outer, inner in (("k", "x"), ("k", "k")):
        text = (
            f'{{\n  "{outer}": 1,\n  "{outer}": 2,\n  "o": {{\n    "a": 1,\n    "{inner}": 1,\n'
            f'    "{inner}": 2\n  }}\n}}\n'
        )
        message = refusal(text)
        case(
            f"a key twice on lines 2-3 and {inner!r} twice on lines 6-7 of an inner object -> {message}",
            ok=on_line_seven(message) and f'"{inner}"' in message,
        )
    for token in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
        message = refusal(at_seven(token))
        case(f"{token} on line 7 -> {message}", ok=on_line_seven(message))
    # The parser meets NaN before the object with the key twice ends, so NaN is the offence.
    message = refusal('{"k": 1, "k":' + "\n" * 6 + "NaN}")
    case(
        f"NaN on line 7 after a key twice on line 1 -> {message}",
        ok=on_line_seven(message) and "NaN" in message,
    )
    # Line 2 holds an integer of 400 digits, which `float` reads as infinity and JSON allows.
    message = refusal('{\n  "i": ' + "1" * 400 + ",\n" + "\n" * 4 + '  "f": 1e400\n}\n')
    case(f"1e400 on line 7 after an integer of 400 digits -> {message[:200]}", ok=on_line_seven(message))
    message = refusal(at_seven('"NaN Infinity 1e400 ' + "[" * (MAX_DEPTH + 1) + '"'))
    case(f"NaN, Infinity, 1e400 and 201 brackets inside a string -> {message}", ok=message == "accepted")


def text_cases(case: Case) -> None:
    """The depth, and the refusals of a whole text."""
    # Depth: the top-level object is 1, "o" is 2, and each bracket of line 7 one more.
    message = refusal(at_seven("[" * (MAX_DEPTH - 2) + "]" * (MAX_DEPTH - 2)))
    case(f"a nesting of depth {MAX_DEPTH} is read -> {message}", ok=message == "accepted")
    message = refusal(at_seven("[" + "[], " * (MAX_DEPTH + 1) + "[]]"))
    case(f"{MAX_DEPTH + 2} sibling arrays at depth 4 are read -> {message}", ok=message == "accepted")
    for depth in (MAX_DEPTH + 1, 100000):
        message = refusal(at_seven("[" * (depth - 2) + "]" * (depth - 2)))
        case(f"a nesting of depth {depth} on line 7 -> {message[:200]}", ok=on_line_seven(message))

    for label, text in (
        ("the empty text", ""),
        ("a text of whitespace only", " \n\t\r\n"),
        ("a top-level array", "[1, 2]\n"),
        ("a top-level string", '"x"\n'),
        ("a top-level null", "null"),
        ("a text that starts with U+FEFF", BOM + '{"a": 1}\n'),
    ):
        message = refusal(text)
        case(f"{label} is refused and names where -> {message}", ok=WHERE in message)
    message = refusal('{\n  "a": 1,\n  "b": 2,\n  "c": 3,\n  "d": 4,\n  "e": 5,\n  "f": }\n')
    case(f"a syntax error on line 7 -> {message}", ok=on_line_seven(message))
    message = refusal('{"a": ' + "1" * 5000 + "}")
    case(f"an integer of 5000 digits is refused, not a ValueError -> {message[:200]}", ok=WHERE in message)
    # A scan that tries each quote of an unclosed string as a string's start takes minutes here.
    start = time.perf_counter()
    message = refusal('{"a": "' + '\\"' * 200000)
    seconds = time.perf_counter() - start
    case(
        f"a string of 200000 escaped quotes that no quote closes is refused in {seconds:.2f} s -> "
        f"{message[:200]}",
        ok=WHERE in message and seconds < SLOW,
    )


def file_cases(case: Case, root: pathlib.Path) -> None:
    """The cases of `load`, on files below `root`."""
    path = root / "a.json"
    path.write_bytes(b'{"a": [1, 2.5, "x", true, null], "b": {"c": "\xc3\xa9"}}')
    got = load(path)
    case(f"load reads a file -> {got}", ok=got == {"a": [1, 2.5, "x", True, None], "b": {"c": "é"}})
    path.write_bytes(DUPLICATE.encode())
    message = load_refusal(path)
    case(f"load: a key twice on line 7 -> {message}", ok=on_line_seven(message, str(path)))
    path.write_bytes(b'\xef\xbb\xbf{"a": 1}\n')
    message = load_refusal(path)
    case(f"load: a file that starts with EF BB BF -> {message}", ok=str(path) in message)
    path.write_bytes(b'{"a": "\xff"}')
    message = load_refusal(path)
    case(
        f"load: a byte that is not UTF-8 names the path and the offset -> {message}",
        ok=str(path) in message and "byte 7" in message,
    )
    missing = root / "missing.json"
    message = load_refusal(missing)
    case(f"load: a missing file names the path -> {message}", ok=str(missing) in message)
    message = load_refusal(root / "a\0b.json")
    case(f"load: a path with a NUL character is refused -> {message!r}", ok="a\0b.json" in message)
    fifo = root / "fifo.json"
    os.mkfifo(fifo)
    message = load_refusal(fifo)
    case(
        f"load: a FIFO is refused, not read -> {message}",
        ok=str(fifo) in message and "not a regular file" in message,
    )


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  jsonio: {label}")

    value_cases(case)
    text_cases(case)
    with tempfile.TemporaryDirectory(prefix="harness-jsonio-") as tmp:
        file_cases(case, pathlib.Path(tmp))
    return total, wrong
