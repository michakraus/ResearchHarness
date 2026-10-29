"""The reader of JSON text: `loads` and `load` return the top-level object of a JSON text, and
refuse with `HarnessError` what Python's `json` accepts but another program reads otherwise.

`json` keeps the last value of a key that an object holds twice, reads `NaN`, `Infinity` and
`-Infinity`, reads a number that overflows as infinity, and raises `RecursionError` on a deep
nesting. Here each of them is refused with a message that names the text's `where` and the line of
the offence, as is a nesting deeper than MAX_DEPTH, where the top-level value is depth 1. An empty
text, a text that starts with a byte order mark, and a top level that is not an object are refused
with a message that names `where`. No other exception leaves `loads` or `load`.

The module imports only the standard library and `HarnessError` of its package, so that it runs in
any package that defines a `HarnessError`.
"""

import inspect
import json
import math
import os
import pathlib
import re
import tempfile
from typing import NoReturn, cast

from . import HarnessError

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None

MAX_DEPTH = 200
# JSON's whitespace; a text of these alone is empty.
WHITESPACE = " \t\r\n"
# A string or a bracket: the depth scan counts the brackets outside the strings.
BRACKET = re.compile(r'"(?:[^"\\]|\\.)*"|[\[\]{}]', re.DOTALL)
# The tokens that locate a refused value: a string, a number, a constant and the punctuation. The
# letters of `true`, `false` and `null` match nothing and are skipped.
TOKEN = re.compile(
    r'(?P<string>"(?:[^"\\]|\\.)*")'
    r"|(?P<number>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
    r"|(?P<constant>-?Infinity|NaN)"
    r"|(?P<punctuation>[{}\[\]:,])",
    re.DOTALL,
)
# Decodes the key of an object, which the parser has read.
DECODER = json.JSONDecoder()


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


def located(text: str, error: OffenceError) -> int | None:
    """The index of the first offence of the kind of `error` in `text`, or None. The parser has read
    the text up to its offence, so the tokens up to there are valid JSON."""
    keys: list[set[str] | None] = []  # per open bracket: the keys of an object, None for an array
    expect_key = False
    for m in TOKEN.finditer(text):
        piece, kind = m.group(), m.lastgroup
        if kind == "constant" and error.kind == "constant":
            return m.start()
        if kind == "number" and error.kind == "overflow" and math.isinf(float(piece)):
            return m.start()
        if piece in ("{", "["):
            keys.append(set() if piece == "{" else None)
            expect_key = piece == "{"
        elif piece in ("}", "]"):
            if keys:
                keys.pop()
            expect_key = False
        elif piece in (",", ":"):
            expect_key = piece == "," and bool(keys) and keys[-1] is not None
        elif kind == "string" and expect_key and keys and (seen := keys[-1]) is not None:
            key: str = DECODER.raw_decode(piece)[0]
            if key in seen and error.kind == "duplicate":
                return m.start()
            seen.add(key)
            expect_key = False
    return None


def kind_of(value: object) -> str:
    """The JSON kind of a top-level value that is not an object."""
    if isinstance(value, list):
        return "an array"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, bool):
        return "a boolean"
    return "null" if value is None else "a number"


def loads(text: str, *, where: str) -> dict[str, JsonValue]:
    """The JSON object of `text`; `where` names the text in a refusal."""
    if text.startswith("﻿"):
        raise HarnessError(f"{where}: starts with a byte order mark (U+FEFF), which JSON does not allow")
    if not text.strip(WHITESPACE):
        raise HarnessError(f"{where}: empty, where a JSON object belongs")
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
        index = located(text, e)
        at = "" if index is None else f"line {line_of(text, index)}: "
        raise HarnessError(f"{where}: {at}{what}") from None
    except json.JSONDecodeError as e:
        raise HarnessError(f"{where}: line {e.lineno}: not JSON: {e.msg}") from None
    except ValueError as e:  # an integer of more digits than `int` reads
        raise HarnessError(f"{where}: not JSON: {e}") from None
    if not isinstance(value, dict):
        raise HarnessError(f"{where}: the top level is {kind_of(value)}, not a JSON object")
    return cast("dict[str, JsonValue]", value)


def load(path: str | os.PathLike[str]) -> dict[str, JsonValue]:
    """The JSON object of the UTF-8 file at `path`; a refusal names the path."""
    p = pathlib.Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise HarnessError(f"cannot read {p}: {e.strerror}") from None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HarnessError(f"{p} is not UTF-8: {e.reason} at byte {e.start}") from None
    return loads(text, where=str(p))


# The cases. Every fixture of a refusal puts its offence on line 7, and no other 7 is in it.
WHERE = "the-where-text"
HEAD = '{\n  "a": true,\n  "b": true,\n  "c": true,\n  "o": {\n    "x": true,\n'  # lines 1-6
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


def selftest() -> tuple[int, int]:
    """The cases of the module docstring: (number of cases, number wrong)."""
    total = wrong = 0

    def case(label: str, *, ok: bool) -> None:
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  jsonio: {label}")

    params = inspect.signature(loads).parameters
    case(
        f"loads(text, *, where): {list(params)}",
        ok=list(params) == ["text", "where"] and params["where"].kind is inspect.Parameter.KEYWORD_ONLY,
    )
    value: dict[str, JsonValue] = {"a": [1, 2.5, "x", True, None], "b": {"c": "é"}, "d": 0.0}
    text = '{"a": [1, 2.5, "x", true, null], "b": {"c": "é"}, "d": 1e-400}'
    got = loads(text, where=WHERE)
    case(f"an object of arrays, numbers, strings, true, null and 1e-400 -> {got}", ok=got == value)
    got = loads('{\r\n  "a": 1,\r\n  "b": [\r\n    2\r\n  ]\r\n}\r\n', where=WHERE)
    case(f"CRLF line ends -> {got}", ok=got == {"a": 1, "b": [2]})

    message = refusal(DUPLICATE)
    case(f"a key twice in a nested object, the second on line 7 -> {message}", ok=on_line_seven(message))
    message = refusal(at_seven('{"\\u006b": 1, "k": 2}'))
    case(f"a key twice, once as an escape -> {message}", ok=on_line_seven(message))
    for token in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
        message = refusal(at_seven(token))
        case(f"{token} on line 7 -> {message}", ok=on_line_seven(message))
    message = refusal(at_seven('"NaN Infinity 1e400 [[["'))
    case(f"NaN, Infinity, 1e400 and brackets inside a string -> {message}", ok=message == "accepted")

    # Depth: the top-level object is 1, "o" is 2, and each bracket of line 7 one more.
    message = refusal(at_seven("[" * (MAX_DEPTH - 2) + "]" * (MAX_DEPTH - 2)))
    case(f"a nesting of depth {MAX_DEPTH} is read -> {message}", ok=message == "accepted")
    for depth in (MAX_DEPTH + 1, 100000):
        message = refusal(at_seven("[" * (depth - 2) + "]" * (depth - 2)))
        case(f"a nesting of depth {depth} on line 7 -> {message[:200]}", ok=on_line_seven(message))

    for label, text in (
        ("the empty text", ""),
        ("a text of whitespace only", " \n\t\r\n"),
        ("a top-level array", "[1, 2]\n"),
        ("a top-level string", '"x"\n'),
        ("a top-level null", "null"),
        ("a text that starts with U+FEFF", '﻿{"a": 1}\n'),
    ):
        message = refusal(text)
        case(f"{label} is refused and names where -> {message}", ok=WHERE in message)
    message = refusal('{\n  "a": 1,\n  "b": 2,\n  "c": 3,\n  "d": 4,\n  "e": 5,\n  "f": }\n')
    case(f"a syntax error on line 7 -> {message}", ok=on_line_seven(message))
    message = refusal('{"a": ' + "1" * 5000 + "}")
    case(f"an integer of 5000 digits is refused, not a ValueError -> {message[:200]}", ok=WHERE in message)

    with tempfile.TemporaryDirectory(prefix="harness-jsonio-") as tmp:
        path = pathlib.Path(tmp) / "a.json"
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
        missing = pathlib.Path(tmp) / "missing.json"
        message = load_refusal(missing)
        case(f"load: a missing file names the path -> {message}", ok=str(missing) in message)
    return total, wrong
