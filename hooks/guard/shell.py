"""The reading of a shell command that the shell checks share.

`lex` splits a command into words and operators as the shell does for the forms the checks read:
a quoted character is never an operator, a `#` that starts a word starts a comment to the end of
the line, a backslash-newline joins two lines, and inside double quotes a backslash escapes only
`$`, a backtick, `"`, `\\` and a newline. An ANSI-C quote `$'…'` gives its text with the escapes
decoded as bash and zsh decode them, and a locale quote `$"…"` reads as a double quote. It runs no
expansion. It is no full shell grammar: each check documents the limits of its reading.

`readings` gives a check the readings that it decides on: the shell's; where a word consists of
operator characters only (`';'`), the reading that takes such a word as the operator; and where
the text holds a backslash-newline, the readings that take it as a line break. With `nested`, it
also gives each reading with the script of every `sh -c`, `bash -c`, `zsh -c` (and the other
shells of SHELLS) and `eval` spliced in as parts of their own (`scripts`). A check answers the
strongest decision of its readings, so a quoted operator, a joined line or a script in a string
cannot hide a part of a command from it.

`joined` is the text that a keyword pre-filter reads: the shell joins `r""m`, `r\\m` and `$'r'm`
into the word `rm`, so a pre-filter on the raw text would miss it.
"""

import functools
import re
import sys
from typing import Literal

type Kind = Literal["word", "op"]
type Token = tuple[Kind, str]
type Tokens = tuple[Token, ...]

# Characters that make an operator when they are not quoted.
OPERATOR = frozenset(";&|<>()\n")
# The separators of the parts of a command.
SEPARATORS = frozenset(";|&\n")
# The fallback split of a text whose quotes do not balance.
SEGMENT = re.compile(r"(?:&&|\|\||;|\||\n)")
# Escapes inside double quotes.
DOUBLE_ESCAPES = '$`"\\\n'
# The escapes of an ANSI-C quote that stand for one character.
ANSI_C = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
# The escapes of an ANSI-C quote that give a code point: the escape, then the digits that it reads
# after it. An octal escape is its own first digit.
CODE_POINTS = {
    **dict.fromkeys("01234567", re.compile(r"[0-7]{0,2}")),
    "x": re.compile(r"[0-9A-Fa-f]{1,2}"),
    "u": re.compile(r"[0-9A-Fa-f]{1,4}"),
    "U": re.compile(r"[0-9A-Fa-f]{1,8}"),
}
# An ANSI-C quote, as `joined` finds it.
ANSI_C_QUOTE = re.compile(r"\$'(?:[^'\\]|\\.)*'", re.DOTALL)
# The quotes, with a `$` that opens an ANSI-C or a locale quote, and the backslashes, each with the
# newline after it, that `joined` removes.
JOINS = re.compile(r"\$?[\"']|\\\n?")
# The shells whose `-c` option runs the next word as a script, by the name of the program.
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash"})
# The long options of these shells that take the next word as their value. A cluster of short
# options that ends in `o` or `O` takes it too, as `-o pipefail` does.
SHELL_VALUED = frozenset({"--rcfile", "--init-file"})
# The levels of scripts inside scripts that `scripts` reads.
DEPTH = 3


def ansi_c(text: str, index: int) -> tuple[str, int] | None:
    """The text of the ANSI-C quote whose `'` is at `index`, its escapes decoded, and the index
    after it; None when no quote closes it. An escape that bash does not know keeps its
    backslash."""
    piece: list[str] = []
    index += 1
    while index < len(text):
        char = text[index]
        if char == "'":
            return "".join(piece), index + 1
        if char != "\\" or index + 1 >= len(text):
            piece.append(char)
            index += 1
            continue
        escape, index = text[index + 1], index + 2
        if escape in ANSI_C:
            piece.append(ANSI_C[escape])
        elif escape in CODE_POINTS:
            digits = CODE_POINTS[escape].match(text, index)
            number = (escape if escape.isdigit() else "") + (digits.group() if digits else "")
            value = int(number, 8 if escape.isdigit() else 16) if number else None
            if value is None or value > sys.maxunicode:
                piece.append("\\" + escape)
            else:
                piece.append(chr(value))
                index = digits.end() if digits else index
        elif escape == "c" and index < len(text):
            piece.append(chr(ord(text[index]) & 0x1F))
            index += 1
        else:
            piece.append("\\" + escape)
    return None


def joined(text: str) -> str:
    """The text without its quotes and backslashes, each ANSI-C quote decoded: the text in which a
    keyword pre-filter looks for the name of a command or an option."""

    def decoded(found: re.Match[str]) -> str:
        quote = ansi_c(found.group(), 1)
        return found.group() if quote is None else quote[0]

    return JOINS.sub("", ANSI_C_QUOTE.sub(decoded, text))


def quoted(text: str, index: int) -> tuple[str, int] | None:
    """The text of the quote that opens at `index` and the index after it, or None when no quote
    closes it."""
    if text[index] == "'":
        end = text.find("'", index + 1)
        return None if end < 0 else (text[index + 1 : end], end + 1)
    piece: list[str] = []
    index += 1
    while index < len(text) and text[index] != '"':
        if text[index] == "\\" and index + 1 < len(text) and text[index + 1] in DOUBLE_ESCAPES:
            index += 1
        piece.append(text[index])
        index += 1
    return None if index >= len(text) else ("".join(piece), index + 1)


@functools.lru_cache(maxsize=32)
def lex(text: str) -> Tokens | None:
    """The text as ("word", w) and ("op", o) tokens, or None when a quote is open. A digit word right
    before `<` or `>` names a file descriptor and is dropped."""
    tokens: list[Token] = []
    word: list[str] = []
    in_word = False
    index, length = 0, len(text)

    def finish() -> None:
        nonlocal word, in_word
        if in_word:
            tokens.append(("word", "".join(word)))
        word, in_word = [], False

    while index < length:
        char = text[index]
        if char in "'\"" or (char == "$" and text[index + 1 : index + 2] in ("'", '"')):
            start = index + 1 if char == "$" else index
            found = ansi_c(text, start) if text[start] == "'" and char == "$" else quoted(text, start)
            if found is None:
                return None
            word.append(found[0])
            in_word, index = True, found[1]
        elif char == "\\":
            # A backslash-newline joins the lines; any other backslash quotes the next character.
            if text[index + 1 : index + 2] not in ("", "\n"):
                word.append(text[index + 1])
                in_word = True
            index += 2
        elif char in " \t\r":
            finish()
            index += 1
        elif char == "#" and not in_word:
            end = text.find("\n", index)
            index = length if end < 0 else end
        elif char in OPERATOR:
            if char in "<>" and in_word and "".join(word).isdigit():
                word, in_word = [], False
            finish()
            end = index
            while end < length and text[end] in OPERATOR:
                end += 1
            tokens.append(("op", text[index:end]))
            index = end
        else:
            word.append(char)
            in_word, index = True, index + 1
    finish()
    return tuple(tokens)


def as_operator(token: Token) -> Token:
    """A word of operator characters only, read as the operator; any other token as it is."""
    kind, text = token
    return ("op", text) if kind == "word" and text and set(text) <= OPERATOR else token


def script_of(tokens: Tokens, index: int) -> tuple[str, int, int] | None:
    """(the script, the index of its first token, the index after its last) of the shell call or
    the `eval` whose name is the word at `index`, or None. The script of a shell of SHELLS is the
    first word after its options when one of them is `-c`, also in a cluster such as `-lc`; the
    script of `eval` is its words up to the next operator, joined by blanks, as `eval` joins them."""
    name = tokens[index][1]
    if name == "eval":
        end = index + 1
        while end < len(tokens) and tokens[end][0] == "word":
            end += 1
        script = " ".join(text for _, text in tokens[index + 1 : end])
        return (script, index + 1, end) if end > index + 1 else None
    if name.rsplit("/", 1)[-1] not in SHELLS:
        return None
    command, at = False, index + 1
    while at < len(tokens) and tokens[at][0] == "word":
        option = tokens[at][1]
        if option[:1] not in ("-", "+") or option in ("-", "+"):
            break
        if option == "--":
            at += 1
            break
        short = not option.startswith("--")
        command = command or (short and option[0] == "-" and "c" in option)
        at += 2 if option in SHELL_VALUED or (short and option[-1] in "oO") else 1
    if not command or at >= len(tokens) or tokens[at][0] != "word":
        return None
    return tokens[at][1], at, at + 1


def scripts(tokens: Tokens, depth: int = DEPTH) -> Tokens:
    """`tokens` with the script of each shell call and each `eval` (`script_of`) spliced in where
    it stands, as parts of their own between `;` operators; a script inside a script is read to
    `depth` levels. The words after a script, such as the arguments of `sh -c` or the `{} \\;` of a
    `find -exec`, form a part of their own. A script with an open quote runs nothing and is left as
    its word."""
    result: list[Token] = []
    index = 0
    while index < len(tokens):
        found = script_of(tokens, index) if tokens[index][0] == "word" and depth > 0 else None
        inner = lex(found[0]) if found is not None else None
        if found is None or inner is None:
            result.append(tokens[index])
            index += 1
            continue
        _, start, stop = found
        result.extend(tokens[index:start])
        result.extend((("op", ";"), *scripts(inner, depth - 1), ("op", ";")))
        index = stop
    return tuple(result)


def readings(text: str, *, nested: bool = False) -> list[Tokens] | None:
    """The readings of `text` that a check decides on, or None when a quote of the shell's reading
    is open. With `nested`, also each reading with its scripts spliced in (`scripts`)."""
    if lex(text) is None:
        return None
    found: list[Tokens] = []
    for variant in (text, text.replace("\\\n", "\n")):
        tokens = lex(variant)
        if tokens is None:
            continue
        for reading in (tokens, tuple(as_operator(token) for token in tokens)):
            if reading not in found:
                found.append(reading)
    if nested:
        for reading in list(found):
            spliced = scripts(reading)
            for extra in (spliced, tuple(as_operator(token) for token in spliced)):
                if extra not in found:
                    found.append(extra)
    return found


def parts(tokens: Tokens) -> list[list[str]]:
    """The top-level parts of a command as word lists."""
    result: list[list[str]] = []
    current: list[str] = []
    for kind, token in tokens:
        if kind == "op":
            bare = token.replace("(", "").replace(")", "")
            if bare and set(bare) <= SEPARATORS and current:
                result.append(current)
                current = []
            continue
        current.append(token)
    if current:
        result.append(current)
    return result


def words(text: str) -> list[str] | None:
    """The words of `text`, its operators left out, or None when a quote is open."""
    tokens = lex(text)
    return None if tokens is None else [value for kind, value in tokens if kind == "word"]
