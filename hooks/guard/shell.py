"""The reading of a shell command that the shell checks share.

`lex` splits a command into words and operators as the shell does for the forms the checks read:
a quoted character is never an operator, a `#` that starts a word starts a comment to the end of
the line, a backslash-newline joins two lines, and inside double quotes a backslash escapes only
`$`, a backtick, `"`, `\\` and a newline. An ANSI-C quote `$'…'` gives its text with the escapes
decoded (`ansi_c`), and a locale quote `$"…"` reads as a double quote, each in a dialect: bash's,
zsh's, or `plain`, which reads the `$` as a character. It runs no expansion. It is no full shell
grammar: each check documents the limits of its reading.

`readings` gives a check the readings that it decides on: the shell's, in each dialect where the
text holds `$'` or `$"`; where a word consists of operator characters only (`';'`), the reading
that takes such a word as the operator; and where the text holds a backslash-newline, the
readings that take it as a line break. With `nested`, it
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
# The shells whose reading of a quote `lex` follows: `plain` decodes no `$'…'` and no `$"…"`.
type Dialect = Literal["bash", "zsh", "plain"]
type Decoding = Literal["bash", "zsh"]

DIALECTS: tuple[Dialect, ...] = ("bash", "zsh", "plain")

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
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash", "csh", "tcsh", "fish"})
# The long options of these shells that take the next word as their value. A cluster of short
# options that ends in `o` or `O` takes it too, as `-o pipefail` does.
SHELL_VALUED = frozenset({"--rcfile", "--init-file"})
# The levels of scripts inside scripts that `scripts` reads.
DEPTH = 3


def code_point(text: str, index: int, letter: str, dialect: Decoding) -> tuple[str, int]:
    """The character of the escape `\\<letter>` of CODE_POINTS whose digits start at `index`, and
    the index after them (`escape`)."""
    octal = letter.isdigit()
    digits = CODE_POINTS[letter].match(text, index)
    number = (letter if octal else "") + (digits.group() if digits else "")
    if not number:
        return ("\x00" if dialect == "zsh" else "\\" + letter), index
    value = int(number, 8) & 0xFF if octal else int(number, 16)
    end = digits.end() if digits else index
    return (chr(value), end) if value <= sys.maxunicode else ("\\" + letter, index)


def escape(text: str, index: int, dialect: Decoding) -> tuple[str, int]:
    """The text of the escape of an ANSI-C quote whose letter is at `index`, as `dialect` decodes
    it, and the index after it. Both keep the low eight bits of an octal escape (`\\562` is `r`).
    bash keeps the backslash of an escape that it does not know and reads `\\cX` as a control
    character; zsh drops that backslash (`\\w` is `w`, `\\c` is `c`), reads `\\C-X` as a control and
    `\\M-X` as a meta character, and reads `\\x` and `\\u` with no digit as a NUL."""
    letter, index = text[index], index + 1
    if letter in ANSI_C:
        return ANSI_C[letter], index
    if letter in CODE_POINTS:
        return code_point(text, index, letter, dialect)
    if dialect == "bash":
        if letter == "c" and text[index : index + 1] not in ("", "'"):
            return chr(ord(text[index]) & 0x1F), index + 1
        return "\\" + letter, index
    if letter in "CM" and text[index : index + 1] == "-" and text[index + 1 : index + 2] not in ("", "'"):
        char = text[index + 1]
        return chr(ord(char) & 0x1F) if letter == "C" else chr(ord(char) | 0x80), index + 2
    return letter, index


def ansi_c(text: str, index: int, dialect: Decoding) -> tuple[str, int] | None:
    """The text of the ANSI-C quote whose `'` is at `index`, its escapes decoded as `dialect`
    decodes them (`escape`), and the index after it; None when no quote closes it. In bash a NUL
    ends the text of the quote (`$'r\\0x'm` is `rm`); zsh keeps it, and `lex` cuts the word there,
    as `exec` does."""
    piece: list[str] = []
    ended = False
    index += 1
    while index < len(text):
        char = text[index]
        if char == "'":
            return "".join(piece), index + 1
        if char == "\\" and index + 1 < len(text):
            found, index = escape(text, index + 1, dialect)
        else:
            found, index = char, index + 1
        if not ended:
            piece.append(found.split("\x00", 1)[0] if dialect == "bash" else found)
        ended = ended or (dialect == "bash" and "\x00" in found)
    return None


def dialects(text: str) -> tuple[Dialect, ...]:
    """The dialects in which `text` is read: DIALECTS when it holds an ANSI-C or a locale quote,
    which they read in different ways, else bash's alone."""
    return DIALECTS if "$'" in text or '$"' in text else ("bash",)


def joined(text: str) -> str:
    """The text in which a keyword pre-filter looks for the name of a command or an option: the text
    without its quotes and backslashes, as written and with each ANSI-C quote decoded in each
    dialect, and the words of `lex` in each dialect, joined by newlines. A `$'` inside a quote
    opens no ANSI-C quote, and its decoding would turn the `\\r` of `echo '$';\\rm` into a carriage
    return, so the text as written is kept as well; the words of `lex` read each quote where the
    shell does."""
    texts = [JOINS.sub("", text)]
    for dialect in dialects(text):
        if dialect != "plain":

            def decoded(found: re.Match[str], dialect: Decoding = dialect) -> str:
                quote = ansi_c(found.group(), 1, dialect)
                return found.group() if quote is None else quote[0]

            texts.append(JOINS.sub("", ANSI_C_QUOTE.sub(decoded, text)))
        texts.append(" ".join(word for _, word in lex(text, dialect) or ()))
    return "\n".join(texts)


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
def lex(text: str, dialect: Dialect = "bash") -> Tokens | None:
    """The text as ("word", w) and ("op", o) tokens in `dialect`, or None when a quote is open. A
    digit word right before `<` or `>` names a file descriptor and is dropped. bash reads `$'…'`
    and `$"…"` as quotes; zsh reads `$'…'` as a quote and the `$` of `$"…"` as a character; `plain`
    reads the `$` of both as a character. A word ends at a NUL, as `exec` reads it."""
    tokens: list[Token] = []
    word: list[str] = []
    in_word = False
    index, length = 0, len(text)
    opens = {"bash": ("'", '"'), "zsh": ("'",), "plain": ()}[dialect]

    def finish() -> None:
        nonlocal word, in_word
        if in_word:
            tokens.append(("word", "".join(word).split("\x00", 1)[0]))
        word, in_word = [], False

    while index < length:
        char = text[index]
        if char in "'\"" or (char == "$" and text[index + 1 : index + 2] in opens):
            start = index + 1 if char == "$" else index
            found = (
                ansi_c(text, start, dialect)
                if text[start] == "'" and char == "$" and dialect != "plain"
                else quoted(text, start)
            )
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
    first word after its options when one of them is `-c`, also in a cluster such as `-lc`, or
    fish's `--command`; the value of `--command=<script>`; the script of `eval` is its words up to
    the next operator, joined by blanks, as `eval` joins them."""
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
        if option.startswith("--command="):
            return option.removeprefix("--command="), at, at + 1
        if option in ("--", "--command"):
            command = command or option == "--command"
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
    """The readings of `text` that a check decides on, in each of its `dialects`, or None when a
    quote of bash's reading is open. With `nested`, also each reading with its scripts spliced in
    (`scripts`)."""
    if lex(text) is None:
        return None
    found: list[Tokens] = []
    for variant in (text, text.replace("\\\n", "\n")):
        for dialect in dialects(variant):
            tokens = lex(variant, dialect)
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
