"""The reading of a shell command that the shell checks share.

`lex` splits a command into words and operators as the shell does for the forms the checks read:
a quoted character is never an operator, a `#` that starts a word starts a comment to the end of
the line, a backslash-newline joins two lines, and inside double quotes a backslash escapes only
`$`, a backtick, `"`, `\\` and a newline. It runs no expansion. It is no full shell grammar: each
check documents the limits of its reading.

`readings` gives a check the readings that it decides on: the shell's; where a word consists of
operator characters only (`';'`), the reading that takes such a word as the operator; and where
the text holds a backslash-newline, the readings that take it as a line break. A check answers the
strongest decision of its readings, so a quoted operator or a joined line cannot hide a part of a
command from it.
"""

import functools
import re
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
        if char in "'\"":
            found = quoted(text, index)
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


def readings(text: str) -> list[Tokens] | None:
    """The readings of `text` that a check decides on, or None when a quote of the shell's reading
    is open."""
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
    return found


def words(text: str) -> list[str] | None:
    """The words of `text`, its operators left out, or None when a quote is open."""
    tokens = lex(text)
    return None if tokens is None else [value for kind, value in tokens if kind == "word"]
