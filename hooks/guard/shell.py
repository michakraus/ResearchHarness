"""The reading of a shell command that the shell checks share.

`lex` splits a command into words and operators as the shell does for the forms the checks read:
a quoted character is never an operator, a `#` that starts a word starts a comment to the end of
the line, a backslash-newline joins two lines, and inside double quotes a backslash escapes only
`$`, a backtick, `"` and `\\`, and a backslash-newline is removed. An ANSI-C quote `$'…'` gives
its text with the escapes decoded (`ansi_c`), and a locale quote `$"…"` reads as a double quote,
each in a dialect: bash's, zsh's, or `plain`, which reads the `$` as a character. A word that
holds a quote or an escape is `Quoted`: the same text, which the reader of reserved words
(`cached_commands`) reads as no reserved word, as the shell does. It runs no
expansion. It is no full shell grammar: each check documents the limits of its reading.

`readings` gives a check the readings that it decides on: the shell's, in each dialect where the
text holds `$'` or `$"`; where a word consists of operator characters only (`';'`), the reading
that takes such a word as the operator; and where the text holds a backslash-newline, the
readings that take it as a line break; and where the text holds `<<`, the readings of the text
without its heredoc bodies (`cut_heredocs`), with an open quote closed at its end
(`script_tokens`), since `lex` reads a heredoc body as words, and a quote in it can hide the lines
after it. With `nested`, it
also gives each reading with the script of every `sh -c`, `bash -c`, `zsh -c` (and the other
shells of SHELLS) and `eval` spliced in as parts of their own (`scripts`). A check answers the
strongest decision of its readings, so a quoted operator, a joined line or a script in a string
cannot hide a part of a command from it.

`joined` is the text that a keyword pre-filter reads: the shell joins `r""m`, `r\\m` and `$'r'm`
into the word `rm`, so a pre-filter on the raw text would miss it.
"""

import bisect
import functools
import itertools
import re
import sys
from dataclasses import dataclass
from typing import Literal


class Quoted(str):
    """A word of `lex` that holds a quoted or an escaped character, as `"}"`, `\\}` or `''fi`:
    the shell reads no such word as a reserved word. A backslash-newline quotes nothing, so the
    `fi` of `f\\` and a newline before `i` stays reserved. Everywhere else it is the same text as a
    plain `str`, as a path or the name of a program: the shell runs `"rm"` as `rm`."""

    __slots__ = ()


class Unreserved(Quoted):
    """A quoted word whose text is one of KEYWORDS, as the reader of `cached_commands` holds it: it
    equals only another `Unreserved` of the same text, so no test of the reader against a reserved
    word, a set of them or a list of words matches it, and the reader reads it as the shell does,
    as the name of a program or an argument."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Unreserved) and str.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        return not self == other

    __hash__ = str.__hash__


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
# A variable assignment before a command word, `X=1` or `X+=1`.
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
# The reserved words after which the next word stands in a command word's place: `! cmd`,
# `{ cmd; }`, `if cmd; then cmd; fi`, `while cmd; do cmd; done`.
RESERVED = frozenset({"!", "{", "}", "if", "then", "elif", "else", "fi", "while", "until", "do", "done"})
# A heredoc operator, with `-` as group 1 and its delimiter as group 3 (`cut_heredocs`).
HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


@dataclass(frozen=True, slots=True)
class Wrapper:
    """A command that runs the command after its own words: the options that take the next word as
    their value, the number of operands after its options, and the letters of a short option that
    makes it run nothing. The assignments after `env` are skipped as those before a command word
    are."""

    valued: frozenset[str] = frozenset()
    operands: int = 0
    runs_nothing: str = ""


# The wrappers, by program name (`program`), that `command_word` reads past.
WRAPPERS = {
    "env": Wrapper(frozenset({"-u", "-C", "-P", "-S", "--unset", "--chdir", "--split-string"})),
    "timeout": Wrapper(frozenset({"-k", "-s", "--kill-after", "--signal"}), operands=1),
    "time": Wrapper(),
    "nice": Wrapper(frozenset({"-n", "--adjustment"})),
    "nohup": Wrapper(),
    "setsid": Wrapper(),
    "exec": Wrapper(frozenset({"-a"})),
    "command": Wrapper(runs_nothing="vV"),
    "builtin": Wrapper(),
    # zsh's precommand modifiers; bash finds no such program, so the command fails there.
    "noglob": Wrapper(),
    "nocorrect": Wrapper(),
    "-": Wrapper(),
    "sudo": Wrapper(
        frozenset(
            {"-u", "-g", "-h", "-p", "-C", "-U", "-r", "-t", "-T", "-D", "-R"}
            | {"--user", "--group", "--host", "--prompt", "--close-from", "--other-user"}
            | {"--role", "--type", "--command-timeout", "--chdir", "--chroot"}
        ),
        runs_nothing="lVe",
    ),
    "doas": Wrapper(frozenset({"-u", "-C"})),
    "xargs": Wrapper(
        frozenset(
            {"-I", "-L", "-n", "-P", "-d", "-E", "-s", "-a"}
            | {"--max-args", "--max-lines", "--max-procs", "--delimiter", "--max-chars", "--arg-file"}
        )
    ),
    "stdbuf": Wrapper(frozenset({"-i", "-o", "-e"})),
    "caffeinate": Wrapper(frozenset({"-t", "-w"})),
    "chronic": Wrapper(),
    "unbuffer": Wrapper(),
    "rtk": Wrapper(),
}

# An operator of a redirection, whose target is the next word: `>`, `>>`, `<`, `<<`, `<<<`, `<>`,
# `>&`, `<&`, `>|`, `&>`, `&>>`. A process substitution `<(` or `>(` is none.
REDIRECTION = re.compile(r"&>>?|[<>]{1,3}[&|]?")
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
# The body of an ANSI-C quote, to the `'` that ends it: a backslash escapes the next character.
ANSI_C_BODY = re.compile(r"(?:[^'\\]|\\.)*", re.DOTALL)
# An ANSI-C quote, as `joined` finds it.
ANSI_C_QUOTE = re.compile(rf"\$'{ANSI_C_BODY.pattern}'", re.DOTALL)
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
# The texts that close an open quote at the end of a script: a second character where the last one
# is a backslash that escapes the first.
CLOSERS = ("'", "''", '"', '""')


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


def escape(body: str, index: int, dialect: Decoding) -> tuple[str, int]:
    """The text of the escape of the body of an ANSI-C quote whose letter is at `index`, as
    `dialect` decodes it, and the index after it. Both keep the low eight bits of an octal escape
    (`\\562` is `r`). bash keeps the backslash of an escape that it does not know and reads `\\cX`
    as a control character; zsh drops that backslash (`\\w` is `w`, `\\c` is `c`) and reads `\\x`,
    `\\u` and `\\U` with no digit as a NUL. zsh's `\\C` and `\\M`, each with an optional `-`, are
    flags that `ansi_c` applies to the next character. The body ends where the shell's parser ends
    the quote (`ansi_c`), so no escape reaches past it."""
    letter, index = body[index], index + 1
    if letter in ANSI_C:
        return ANSI_C[letter], index
    if letter in CODE_POINTS:
        return code_point(body, index, letter, dialect)
    if dialect == "bash":
        if letter == "c" and index < len(body):
            return chr(ord(body[index]) & 0x1F), index + 1
        return "\\" + letter, index
    return letter, index


def ansi_c(text: str, index: int, dialect: Decoding) -> tuple[str, int] | None:
    """The text of the ANSI-C quote whose `'` is at `index`, its escapes decoded as `dialect`
    decodes them (`escape`), and the index after it; None when no quote closes it. The quote ends
    where the shell's parser ends it, at the first `'` that no backslash escapes, before any
    escape is decoded, so no decoding moves the end. In bash a NUL ends the text of the quote
    (`$'r\\0x'm` is `rm`); zsh keeps it, and `lex` cuts the word there, as `exec` does. zsh reads
    `\\C` and `\\M`, each with an optional `-`, as a control and a meta flag that it applies to the
    next character, except a `\\u` or `\\U` character, and drops when no character follows
    (`r$'\\C'm` is `rm`)."""
    found = ANSI_C_BODY.match(text, index + 1)
    end = found.end() if found else index + 1
    if end >= len(text) or text[end] != "'":
        return None
    body, piece, at = text[index + 1 : end], list[str](), 0
    control = meta = False
    while at < len(body):
        if dialect == "zsh" and body[at] == "\\" and body[at + 1 : at + 2] in ("C", "M"):
            control, meta = control or body[at + 1] == "C", meta or body[at + 1] == "M"
            at += 3 if body[at + 2 : at + 3] == "-" else 2
            continue
        letter = body[at + 1] if body[at] == "\\" and at + 1 < len(body) else ""
        decoded, at = escape(body, at + 1, dialect) if letter else (body[at], at + 1)
        if decoded and (control or meta) and letter not in ("u", "U"):
            code = (0x7F if decoded[0] == "?" else ord(decoded[0]) & 0x9F) if control else ord(decoded[0])
            decoded, control, meta = chr(code | 0x80 if meta else code) + decoded[1:], False, False
        if dialect == "bash" and "\x00" in decoded:
            piece.append(decoded.split("\x00", 1)[0])
            break
        piece.append(decoded)
    return "".join(piece), end + 1


def dialects(text: str) -> tuple[Dialect, ...]:
    """The dialects in which `text` is read: DIALECTS when it holds an ANSI-C or a locale quote,
    which they read in different ways, else bash's alone."""
    return DIALECTS if "$'" in text or '$"' in text else ("bash",)


@functools.lru_cache(maxsize=8)
def joined(text: str) -> str:
    """The text in which a keyword pre-filter looks for the name of a command or an option: the text
    without its quotes and backslashes, as written and with each ANSI-C quote decoded in each
    dialect, and the words of `lex` in each dialect, joined by newlines. A `$'` inside a quote
    opens no ANSI-C quote, and its decoding would turn the `\\r` of `echo '$';\\rm` into a carriage
    return, so the text as written is kept as well; the words of `lex` read each quote where the
    shell does. Each check of a call reads it, so it is kept for the next."""
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
    closes it. Inside double quotes a backslash-newline is removed, as the shell removes it."""
    if text[index] == "'":
        end = text.find("'", index + 1)
        return None if end < 0 else (text[index + 1 : end], end + 1)
    piece: list[str] = []
    index += 1
    while index < len(text) and text[index] != '"':
        if text[index] == "\\" and index + 1 < len(text) and text[index + 1] in DOUBLE_ESCAPES:
            index += 1
            if text[index] == "\n":
                index += 1
                continue
        piece.append(text[index])
        index += 1
    return None if index >= len(text) else ("".join(piece), index + 1)


@functools.lru_cache(maxsize=32)
def lex(text: str, dialect: Dialect = "bash") -> Tokens | None:
    """The text as ("word", w) and ("op", o) tokens in `dialect`, or None when a quote is open. A
    digit word right before `<` or `>` names a file descriptor and is dropped. bash reads `$'…'`
    and `$"…"` as quotes; zsh reads `$'…'` as a quote and the `$` of `$"…"` as a character; `plain`
    reads the `$` of both as a character. A word ends at a NUL, as `exec` reads it. A word that
    holds a quote or a backslash other than a backslash-newline is `Quoted`."""
    tokens: list[Token] = []
    word: list[str] = []
    in_word = quotes = False
    index, length = 0, len(text)
    opens = {"bash": ("'", '"'), "zsh": ("'",), "plain": ()}[dialect]

    def finish() -> None:
        nonlocal word, in_word, quotes
        if in_word:
            found = "".join(word).split("\x00", 1)[0]
            tokens.append(("word", Quoted(found) if quotes else found))
        word, in_word, quotes = [], False, False

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
            in_word, quotes, index = True, True, found[1]
        elif char == "\\":
            # A backslash-newline joins the lines; any other backslash quotes the next character.
            if text[index + 1 : index + 2] not in ("", "\n"):
                word.append(text[index + 1])
                in_word = quotes = True
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
    the next operator, joined by blanks, as `eval` joins them; the script of `env` is the value of
    its `-S` or `--split-string` option (`split_string`)."""
    name = tokens[index][1]
    if name == "eval":
        end = index + 1
        while end < len(tokens) and tokens[end][0] == "word":
            end += 1
        script = " ".join(text for _, text in tokens[index + 1 : end])
        return (script, index + 1, end) if end > index + 1 else None
    called = program(name)
    if called == "env":
        return split_string(tokens, index)
    if called not in SHELLS:
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


def split_string(tokens: Tokens, index: int) -> tuple[str, int, int] | None:
    """(the string, the index of its token, the index after it) of the `-S <string>`,
    `-S<string>`, `--split-string <string>` or `--split-string=<string>` option of the `env` call
    at `index`, which `env` splits into a command and runs; None without one. `env` splits the
    string on blanks and reads its quotes, so the check reads it as a shell script, which can only
    find more."""
    at = index + 1
    while at < len(tokens) and tokens[at][0] == "word" and tokens[at][1].startswith("-"):
        option = tokens[at][1]
        if option in ("-S", "--split-string"):
            follows = at + 1 < len(tokens) and tokens[at + 1][0] == "word"
            return (tokens[at + 1][1], at + 1, at + 2) if follows else None
        if option.startswith("--split-string="):
            return option.removeprefix("--split-string="), at, at + 1
        if option.startswith("-S"):
            return option[2:], at, at + 1
        at += 2 if option in WRAPPERS["env"].valued else 1
    return None


def script_tokens(script: str, dialect: Dialect) -> Tokens | None:
    """The tokens of `script` in `dialect`. A script with an open quote is read with the quote
    closed at its end (CLOSERS), since sh, bash and dash, in `-c` and in `eval`, run the lines
    before the line on which the quote opens (zsh runs none); None when no closer closes it."""
    for closer in ("", *CLOSERS):
        tokens = lex(script + closer, dialect)
        if tokens is not None:
            return tokens
    return None


def scripts(tokens: Tokens, depth: int = DEPTH) -> Tokens:
    """`tokens` with the script of each shell call and each `eval` (`script_of`) spliced in where
    it stands, as parts of their own between `;` operators; a script inside a script is read to
    `depth` levels. A script is read in each of its `dialects`, and the readings follow one another
    as parts. The words after a script, such as the arguments of `sh -c` or the `{} \\;` of a
    `find -exec`, form a part of their own. A script with an open quote is read with the quote
    closed (`script_tokens`). With no script, it is `tokens` itself."""
    result: list[Token] = []
    index, spliced = 0, False
    while index < len(tokens):
        found = script_of(tokens, index) if tokens[index][0] == "word" and depth > 0 else None
        inner = [] if found is None else [script_tokens(found[0], dialect) for dialect in dialects(found[0])]
        read = list(dict.fromkeys(reading for reading in inner if reading is not None))
        if found is None or not read:
            result.append(tokens[index])
            index += 1
            continue
        _, start, stop = found
        result.extend(tokens[index:start])
        for reading in read:
            result.extend((("op", ";"), *scripts(reading, depth - 1)))
        result.append(("op", ";"))
        index, spliced = stop, True
    return tuple(result) if spliced else tokens


def cut_heredocs(command: str) -> str:
    """The command without its heredoc bodies, which are data, not commands."""
    kept: list[str] = []
    pending: list[tuple[bool, str]] = []
    for line in command.split("\n"):
        if pending:
            tabs, delimiter = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            continue
        pending.extend((match.group(1) == "-", match.group(3)) for match in HEREDOC.finditer(line))
        kept.append(line)
    return "\n".join(kept)


def readings(text: str, *, nested: bool = False) -> list[Tokens] | None:
    """The readings of `text` that a check decides on, in each of its `dialects`, or None when a
    quote of bash's reading is open. Where `text` holds `<<`, also the readings of the text without
    its heredoc bodies (`cut_heredocs`), each with an open quote closed (`script_tokens`). With
    `nested`, also each reading with its scripts spliced in (`scripts`). Each check of a call reads
    the same command, so the readings are made once (`cached_readings`); each caller gets a list of
    its own."""
    found = cached_readings(text, nested=nested)
    return None if found is None else list(found)


@functools.lru_cache(maxsize=4)
def cached_readings(text: str, *, nested: bool) -> tuple[Tokens, ...] | None:
    """The readings of `readings`, made once for each text."""
    if lex(text, "bash") is None:
        return None
    found: list[Tokens] = []

    def add(tokens: Tokens) -> None:
        for reading in (tokens, tuple(as_operator(token) for token in tokens)):
            if reading not in found:
                found.append(reading)

    for variant in (text, text.replace("\\\n", "\n")):
        for dialect in dialects(variant):
            tokens = lex(variant, dialect)
            if tokens is not None:
                add(tokens)
    cut = cut_heredocs(text) if "<<" in text else text
    if cut != text:
        for dialect in dialects(cut):
            tokens = script_tokens(cut, dialect)
            if tokens is not None:
                add(tokens)
    if nested:
        for reading in list(found):
            spliced = scripts(reading)
            if spliced is reading:
                # No script: the reading and its operator reading are in `found` already.
                continue
            for extra in (spliced, tuple(as_operator(token) for token in spliced)):
                if extra not in found:
                    found.append(extra)
    return tuple(found)


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


def unredirected(tokens: Tokens) -> Tokens:
    """`tokens` without the word after each operator of a redirection (REDIRECTION): its target,
    such as the `1` of `2>&1` or the delimiter of a heredoc. A redirection can stand between a
    program and its arguments, as in `git 2>&1 push`, and the shell passes its target to no
    program. The operators stay, so `parts` splits as before."""
    result: list[Token] = []
    target = False
    for kind, text in tokens:
        if kind == "word" and target:
            target = False
            continue
        target = kind == "op" and REDIRECTION.fullmatch(text) is not None
        result.append((kind, text))
    return tuple(result)


def program(word: str) -> str:
    """The name of the program that the command word `word` runs: its last path name, in lower
    case, since a file system that ignores case, as macOS's does, runs git for `GIT`. A string
    split, not `PurePosixPath`, since `scripts` asks it for every word of a command of 1 MiB."""
    return word.rstrip("/").rsplit("/", 1)[-1].lower()


# The wrappers, spelled exactly, after which a shell runs its own builtin or nothing: `builtin cd`
# moves the shell, and so does `noglob cd` in zsh, while bash finds no program `noglob`
# (`builtin_commands`).
KEEPS_BUILTIN = frozenset({"builtin", "noglob", "nocorrect", "-"})
# The wrappers, spelled exactly, after which one shell runs its builtin and another a program:
# `command cd` moves bash and not zsh, and `time cd` moves bash and not `"time" cd`, which `lex`
# reads as the same word (`builtin_commands`).
MAY_KEEP_BUILTIN = frozenset({"command", "time"})

# Where a simple command runs (`builtin_commands`): in the shell, as its own builtin; in the shell
# or in a child, by the shell that runs it; or in a child, as a program.
type Runs = Literal["shell", "either", "child"]


@dataclass(frozen=True, slots=True)
class Simple:
    """A simple command of `builtin_commands`: its words from its command word on, where the shell
    runs its command word if that is a builtin (`Runs`), the operators after it (`then`): `&&`,
    `;`, `|`, a parenthesis, a newline, a backtick, or empty at the end, with those of a part that
    runs nothing after it, as in `x; } && y`; the reserved words before it (`lead`), with those of
    such a part before it, as in `fi; y`; and the number of parentheses open before it (`depth`)."""

    words: list[str]
    runs: Runs
    then: str
    lead: tuple[str, ...] = ()
    depth: int = 0


def after_wrapper(words: list[str], at: int, wrapper: Wrapper) -> int | None:
    """The index of the first word after the wrapper at `at` with its options and operands, or
    None when a short option makes it run nothing. Each word that starts with `-` is an option,
    `--` too."""
    at += 1
    while at < len(words) and words[at].startswith("-"):
        short = not words[at].startswith("--")
        if short and any(letter in words[at][1:] for letter in wrapper.runs_nothing):
            return None
        at += 2 if words[at] in wrapper.valued else 1
    return at + wrapper.operands


def command_word(words: list[str]) -> int | None:
    """The index of the command word of the simple command `words`, or None when it runs nothing:
    the first word after the reserved words of RESERVED, the assignments, and each wrapper of
    WRAPPERS with its options and operands, as in `env X=1 sudo -u u git`."""
    at = 0
    while at < len(words):
        if words[at] in RESERVED or ASSIGNMENT.match(words[at]):
            at += 1
            continue
        wrapper = WRAPPERS.get(program(words[at]))
        if wrapper is None:
            return at
        found = after_wrapper(words, at, wrapper)
        if found is None:
            return None
        at = found
    return None


def commands(tokens: Tokens) -> list[list[str]]:
    """The words of each simple command of `tokens`, in order, from its command word on
    (`command_word`); a command that runs nothing is left out. A command ends at each separator and
    at each parenthesis, so the body of a subshell `( … )` or of a substitution `$( … )` is a
    command of its own, and so is the text between two backticks. The target of a redirection is
    no word of a command (`unredirected`). It reads a backtick in a quote as one too, which can
    only find more commands."""
    return [simple.words for simple in builtin_commands(tokens)]


def runs_of(prefix: list[str], word: str) -> Runs:
    """Where the shell runs the command word `word` after the words `prefix` if it is a builtin
    (`Runs`). The shell runs a builtin such as `cd` only for a command word spelled as its name, so
    `CD` and `/usr/bin/cd` run the program `/usr/bin/cd` in a child; behind a wrapper of WRAPPERS
    other than those of KEEPS_BUILTIN and MAY_KEEP_BUILTIN, spelled as theirs, as in `env cd` or
    `sudo cd`, a child runs it too. An assignment is no wrapper."""
    if word != program(word):
        return "child"
    wrappers = [found for found in prefix if ASSIGNMENT.match(found) is None and program(found) in WRAPPERS]
    if any(found not in KEEPS_BUILTIN | MAY_KEEP_BUILTIN for found in wrappers):
        return "child"
    return "either" if any(found in MAY_KEEP_BUILTIN for found in wrappers) else "shell"


# The builtins that end the shell, so that the commands after `cd x || exit` run only where the
# `cd` succeeded (`flow`). Not `return`: bash goes on after a `return` outside a function.
STOPS = frozenset({"exit"})
# The mark that `cached_commands` puts in the reserved words of each command of the body of a
# function that zsh's short form defines (`carried`), before the command's own reserved words, as
# for the `cd x` of `f() cd x && y`, which does not run there, so that `y` runs where the shell
# was (`sure_kind`); and in those of a command after a `repeat` and its count (`unrepeated`), as
# the `cd x` of `repeat 0 do cd x; done`, which bash passes to a program `repeat`.
DEFINED = "()"
# The operators of a `then` (`operators`): a newline is read as `;`.
OPERATORS = re.compile(r"&&|\|\||\|&|[|;&()`]")
# The newlines right after an operator, which only go on with the line (`operators`): bash and
# zsh read every blank line after `&&`, `||` or a pipe as part of it.
GOES_ON = re.compile(r"(&&|\|\||\|&|\|)[ \t\n]*\n")
# What stands for a part that runs nothing, such as an assignment, between the operators of a
# `then` (`cached_commands`).
PART = "\x1f"
# The operators after a command that keep the commands after it in its `&&` list: they run only
# when it succeeded, or in a pipeline with it.
IN_LIST = frozenset({"&&", "|", "|&", ""})


def operators(then: str) -> list[str]:
    """The operators of the `then` of a `Simple`, a newline as `;`, but none for the newlines right
    after an operator of GOES_ON, where they only go on with the line. A part that runs nothing
    stands between two operators as PART (`cached_commands`), so a newline after the assignment of
    `cd x && X=1` is a `;`."""
    return OPERATORS.findall(GOES_ON.sub(r"\1", then).replace("\n", ";"))


def last_operator(then: str) -> str:
    """The last operator of `then` that is no parenthesis, or empty."""
    return next((found for found in reversed(operators(then)) if found not in "()"), "")


@dataclass(frozen=True, slots=True)
class Flow:
    """The directories that the commands of a list of `Simple` run in, after each `cd` or `pushd`
    (`flow`): whether the commands after the one at an index run only where it moved to (`sure`),
    until the index of `ends` where the shell can be where it was before it again; past that
    index, a check reads the directories before it too. A `cd` that is not sure leaves either
    directory for every command after it."""

    sure: tuple[bool, ...]
    ends: tuple[int | None, ...]


# How a `cd` makes the commands after it run only where it moved to (`sure_kind`).
type Sure = Literal["list", "exit", "if"]


# The reserved words and command words that open or close a compound command or a body
# (`outermost`).
NESTING = {
    "{": 1,
    "if": 1,
    "do": 1,
    "case": 1,
    "foreach": 1,
    "}": -1,
    "fi": -1,
    "done": -1,
    "esac": -1,
    "end": -1,
}
# The reserved words that close a compound command, and so can stand right before `)` or a pipe
# (`cached_commands`).
CLOSING = frozenset({"}", "fi", "done"})


def outermost(simples: list[Simple]) -> list[bool]:
    """For each of `simples`, True when it stands in no compound command and no body: no `{ … }`,
    `if`, loop, `case` or function body holds it, so that an `exit` after it ends the shell for
    every command after it. A `cd x || exit` in a body that may not run, as in `if false; then cd x
    || exit; fi; y`, leaves `y` where the shell was. A `{` that is a word of a command opens a body
    too, as in `function f {`, `coproc {` or zsh's `repeat 0 {`. Inside a `case`, a closing word
    can be a pattern, as in `(fi)`, so there only an opening word counts. An `esac` or `end`
    closes only a `case` or `foreach` that is open, and only outside a pattern or a zsh glob group
    (`in_group`), as in `echo (end)`; bash runs `end` as a program."""
    found: list[bool] = []
    level, cases, loops = 0, 0, 0
    for at, simple in enumerate(simples):
        level += sum(step for word in simple.lead if (step := NESTING.get(word, 0)) > 0 or not cases)
        found.append(level == 0)
        level += simple.words[1:].count("{")
        head = simple.words[0]
        closing = at == 0 or not in_group(simples[at - 1].then, simple.then)
        if head == "case":
            level, cases = level + 1, cases + 1
        elif head == "foreach":
            level, loops = level + 1, loops + 1
        elif head == "esac" and cases and closing:
            level, cases = level - 1, cases - 1
        elif head == "end" and loops and closing:
            level, loops = level - 1, loops - 1
    return found


def in_group(before: str, then: str) -> bool:
    """True when the operators `before` and `then` around a part make it a pattern of a `case` or
    an alternative of a zsh glob group, as in `case a in (fi)`, `echo (end)` or `echo (x|if)`:
    `before` ends in `(` or a pipe, and `then` starts with `)` or a pipe. Its words are no
    reserved words, and a shell reads none of them as one that opens or closes a body."""
    return before.rstrip("\n")[-1:] in ("(", "|") and then[:1] in (")", "|")


def sure_kind(simples: list[Simple], index: int, outer: list[bool]) -> Sure | None:
    """How the commands after the `cd` or `pushd` `simples[index]` run only where it moved to, or
    None when they can run where the shell was. The shell runs it as its own (`Runs`), no `!`
    before it turns its failure into success, as in `! cd x && y`, and no `||`, `|` or backtick
    before it lets the commands after it run when it never ran, as in `true || cd x && y` or
    `echo | cd x && y`, which bash runs in a child. Then `list`: `&&`
    joins it to the next command, as in `cd x && y`; `exit`: `||` joins it to an `exit` that the
    shell runs as its own, outside a pipeline and not in the background (also `flow`), as in
    `cd x || exit 1; y` and unlike `cd x || (exit 1)` or `exit &`, in no compound command or body
    (`outer`, of `outermost`); `if`: it is the condition of an `if`, as in `if cd x; then y; fi`.
    A move in the body of zsh's short function definition, as in `f() cd x && y`, never runs
    there (`DEFINED`), so it is not sure; so neither is one in a group or an `if` of such a body,
    as in `f() { cd x && true } && y`, where zsh closes the group without a `;`."""
    simple = simples[index]
    moves = program(simple.words[0]) in ("cd", "pushd") and DEFINED not in simple.lead
    if simple.runs != "shell" or "!" in simple.lead or not moves:
        return None
    if index > 0:
        before = simples[index - 1].then
        if "`" in before or last_operator(before) in ("||", "|", "|&"):
            return None
    own = operators(simple.then)
    following = simples[index + 1] if index + 1 < len(simples) else None
    if last_operator(simple.then) == "&&":
        return "list"
    if own == ["||"] and following is not None:
        stops = following.words[0] in STOPS and following.runs == "shell" and following.depth == simple.depth
        after = [found for found in operators(following.then) if found not in "()"]
        stops = stops and "`" not in following.then and after[:1] not in (["|"], ["|&"], ["&"])
        if stops and outer[index]:
            return "exit"
    if (
        simple.lead[-1:] == ("if",)
        and own == [";"]
        and following is not None
        and following.lead[:1] == ("then",)
    ):
        return "if"
    return None


def ends_list(simple: Simple, depth: int) -> bool:
    """True when an operator after `simple`, open in `depth` parentheses, ends an `&&` list: one
    other than `&&` or a pipe, or a backtick. An operator inside a parenthesis opened after the list
    began, as the `;` of `cd x && (y; z)`, ends nothing."""
    level = simple.depth
    for operator in operators(simple.then):
        if operator == "`":
            return True
        if operator in "()":
            level += 1 if operator == "(" else -1
        elif level <= depth and operator not in IN_LIST:
            return True
    return False


def lowest(simple: Simple) -> int:
    """The lowest count of open parentheses right after a `)` after `simple`, or sys.maxsize when
    none follows it (`closes`)."""
    level = simple.depth
    found = sys.maxsize
    for operator in operators(simple.then):
        if operator in "()":
            level += 1 if operator == "(" else -1
            if operator == ")":
                found = min(found, level)
    return found


def closes(simple: Simple, depth: int) -> bool:
    """True when a parenthesis after `simple` closes one of the `depth` parentheses open before
    a command, also where another one opens right after it, as in `(cd x && y) && (z)`."""
    return lowest(simple) < depth


def scope_end(
    simples: list[Simple],
    index: int,
    kind: Literal["list", "exit"],
    known: tuple[int, int | None] | None = None,
) -> int | None:
    """The index of the first command after the sure move `simples[index]` of `kind` (`sure_kind`)
    that can run where the shell was before it, or None. Every kind ends where a parenthesis
    closes that was open before it (`closes`). A `list` ends after the `&&` list that it starts:
    after an operator other than `&&` or a pipe, such as `;`, `||` or `&`, or after a backtick. A
    move reads the commands after it only up to the next one of its kind in as many parentheses,
    whose index and end are `known`: from there on, both end alike, so a chain of `cd x &&` costs
    one pass (`flow`). An `if` move ends as `if_ends` gives."""
    depth = simples[index].depth
    for at in range(index + 1, len(simples)):
        if closes(simples[at - 1], depth):
            return at
        if kind == "list" and ends_list(simples[at - 1], depth):
            return at
        if known is not None and at == known[0]:
            return known[1]
    return None


def if_ends(simples: list[Simple]) -> list[int | None]:
    """For each of `simples` whose reserved words end in `if`, the index of the first command
    after it that can run where the shell was before it, else None: where a parenthesis closes
    that was open before it (`closes`), or at the `else`, `elif` or `fi` of its `if`, whichever
    comes first. One pass over the reserved words matches each `if`, and one pass from the last
    command keeps the commands whose parentheses can close one open before a command, so that a
    nesting of `if cd x; then` costs no time quadratic in its depth (`flow`)."""
    count = len(simples)
    ends: list[int | None] = [None] * count
    words = else_or_fi(simples)
    # From the last command to the first, the commands `after` whose `lowest` is below that of
    # every command between, nearest last, so that their levels rise from the start of `after` to
    # its end: the last of them below a depth is the nearest where it closes.
    after: list[tuple[int, int]] = []
    for at in reversed(range(count)):
        if at < count - 1:
            level = lowest(simples[at])
            while after and after[-1][1] >= level:
                after.pop()
            after.append((at, level))
        if simples[at].lead[-1:] != ("if",):
            continue
        depth = simples[at].depth
        below = bisect.bisect_left(after, depth, key=lambda entry: entry[1])
        shut = after[below - 1][0] + 1 if below > 0 else None
        word = words[at]
        ends[at] = shut if word is None else word if shut is None else min(shut, word)
    return ends


def else_or_fi(simples: list[Simple]) -> list[int | None]:
    """For each of `simples`, the index of the first command after it whose reserved words hold
    the `else`, `elif` or `fi` of the last `if` of its own reserved words, else None (`if_ends`).
    An `if` after the mark DEFINED opens none: in `if cd x; then true; repeat 1 if true; fi; y`,
    bash passes the `if` to a program `repeat`, and the `fi` ends the `if` of the `cd`. A move
    after the mark is never sure (`sure_kind`), and an `else`, `elif` or `fi` of such an `if`
    only ends an `if` around it early."""
    words: list[int | None] = [None] * len(simples)
    opened: list[int] = []
    for at, simple in enumerate(simples):
        marked = False
        for word in simple.lead:
            marked = marked or word == DEFINED
            if word == "if" and not marked:
                opened.append(at)
            elif word in ("else", "elif", "fi") and opened:
                owner = opened[-1]
                if words[owner] is None and owner != at:
                    words[owner] = at
                if word == "fi":
                    opened.pop()
    return words


def in_background(simples: list[Simple], starts: set[int]) -> set[int]:
    """The indexes of `starts` whose `&&` or `||` list, from the command at the index on, a `&`
    ends, as in `cd x || exit 1 && y & z`, where a child runs the whole list, or a backtick, which
    the check does not follow (`flow`). A list ends at the first operator other than `&&`, `||` or a
    pipe in as many parentheses as its command, or where a parenthesis open before it closes. One
    pass over the operators of `simples` decides every index."""
    found: set[int] = set()
    pending: list[tuple[int, int]] = []
    for at, simple in enumerate(simples):
        if at in starts:
            pending.append((at, simple.depth))
        level = simple.depth
        for operator in operators(simple.then):
            if operator == "(":
                level += 1
                continue
            if operator in ("&&", "||", "|", "|&"):
                continue
            if operator == ")":
                level -= 1
            # A `)` ends the lists inside it; any other operator ends those in as many parentheses.
            limit = level + 1 if operator == ")" else level
            while pending and pending[-1][1] >= limit:
                start, _ = pending.pop()
                if operator in ("&", "`"):
                    found.add(start)
    return found


# The commands that `flow` may read past the moves of a command, besides one pass over it: deeply
# nested moves, as in `cd x && (cd y && (…`, each read to their own end, which costs time
# quadratic in the nesting.
SCAN_STEPS = 65536


def flow(simples: list[Simple]) -> Flow:
    """The `Flow` of `simples`: for each `cd` or `pushd`, whether it is sure (`sure_kind`) and the
    index where that ends (`scope_end`, `if_ends`), from the last command to the first, so that
    each move reuses the end of the next one of its kind in as many parentheses. Once the `list`
    and `exit` moves have read SCAN_STEPS commands besides one pass, each such move before is read
    as one that can fail, which only makes the checks read more directories. An `exit` move whose
    list a `&` puts in the background (`in_background`) can fail too."""
    outer = outermost(simples)
    kinds: list[Sure | None] = [sure_kind(simples, index, outer) for index in range(len(simples))]
    if "exit" in kinds:
        # The `exit` after each `exit` move starts its list, so `background` holds only those.
        background = in_background(simples, {index + 1 for index, kind in enumerate(kinds) if kind == "exit"})
        kinds = [None if index + 1 in background else kind for index, kind in enumerate(kinds)]
    ends: list[int | None] = [None] * len(simples)
    conditions = if_ends(simples) if "if" in kinds else []
    nearest: dict[tuple[Sure, int], tuple[int, int | None]] = {}
    budget = len(simples) + SCAN_STEPS
    for index in reversed(range(len(simples))):
        kind = kinds[index]
        if kind is None:
            continue
        if kind == "if":
            ends[index] = conditions[index]
            continue
        if budget < 0:
            kinds[index] = None
            continue
        key = (kind, simples[index].depth)
        known = nearest.get(key)
        end = scope_end(simples, index, kind, known)
        # The commands that the scan read: up to the reused move, or up to its end.
        reach = known[0] if known is not None and end == known[1] else len(simples) if end is None else end
        budget -= reach - index
        ends[index] = end
        nearest[key] = (index, end)
    return Flow(tuple(kind is not None for kind in kinds), tuple(ends))


def builtin_commands(tokens: Tokens) -> list[Simple]:
    """Each simple command of `tokens` (`Simple`), with the words that `commands` gives, where the
    shell runs its command word if that is a builtin (`runs_of`), the operators after it, the
    reserved words before it and the parentheses open before it. Several checks read the same
    tokens, so the commands are made once (`cached_commands`); each caller gets lists of its own."""
    return [
        Simple(list(simple.words), simple.runs, simple.then, simple.lead, simple.depth)
        for simple in cached_commands(tokens)
    ]


def reserved_lead(words: list[str]) -> list[str]:
    """The reserved words at the start of `words`, where the shell reads them as reserved: before
    any word other than `time` and its `-p`, so that the `fi` of `X=1 fi` or `sudo fi` is the name
    of a program and closes nothing (`outermost`)."""
    return [word for word in itertools.takewhile(leads, words) if word in RESERVED]


def unreserved(token: Token) -> Token:
    """`token` as the reader of `cached_commands` holds it: a word is `Unreserved` when it is
    `Quoted` and its text is one of KEYWORDS, as the `"}"` of `{ true; "}"; }`, which the shell
    runs as a command."""
    kind, text = token
    return (kind, Unreserved(text)) if isinstance(text, Quoted) and text in KEYWORDS else token


def cached_commands(tokens: Tokens) -> tuple[Simple, ...]:
    """The simple commands of `builtin_commands`, made once for each reading. A `Quoted` word
    equals its plain text, so the reading of `"}"` equals that of `}`; the key of the cache holds
    which words are quoted, so that neither reading gets the commands of the other."""
    return commands_of(tokens, tuple(isinstance(text, Quoted) for _, text in tokens))


@functools.lru_cache(maxsize=4)
def commands_of(tokens: Tokens, _quoted: tuple[bool, ...]) -> tuple[Simple, ...]:
    """The simple commands of `cached_commands`, for the reading `tokens` whose quoted words
    `_quoted` marks; only the key of the cache reads it."""
    found: list[Simple] = []
    current: list[str] = []
    lead: list[str] = []
    depth = 0
    before = ""
    body = Defined()

    def close(then: str) -> None:
        nonlocal current, lead, depth, before, body
        body, (current, cut), short = unwaited(body, current), unrepeated(current), repeats(current, then)
        if (at := command_word(current)) is not None:
            # The body of a function that zsh's short form defines, or of a `repeat`, may run
            # nothing here, and bash runs the words after `repeat` as its arguments (`DEFINED`).
            lead += (
                ([DEFINED] if body.kind is not None or short is not None or cut else [])
                + reserved_lead(current[:at])
                + (kept_opens(current[at:]) if cut else [])
            )
            found.append(Simple(current[at:], runs_of(current[:at], current[at]), then, tuple(lead), depth))
            lead = []
        else:
            # A part that runs nothing, such as `}`, `fi` or an assignment, passes its reserved
            # words to the next command and its operators to the command before it, so that the
            # `;` of `cd x && X=1; y` and the `(` of `cd x || (exit 1)` reach the `cd` (`flow`).
            # Right before `)` or a pipe, only a closing word such as the `fi` of `fi)` is
            # reserved, since the `if` of `if)` is a pattern of a `case`; and none is in a pattern
            # or a zsh glob group such as `(fi)` (`in_group`).
            reserved = reserved_lead(current)
            if then[:1] in (")", "|"):
                reserved = [] if in_group(before, then) else [word for word in reserved if word in CLOSING]
            lead.extend(reserved)
            if found:
                last = found[-1]
                joined_then = last.then + (PART if current else "") + then
                found[-1] = Simple(last.words, last.runs, joined_then, last.lead, last.depth)
        body = carried(body, current, then, depth, short=short)
        depth += then.count("(") - then.count(")")
        current, before = [], then

    # A pattern of a `case` runs nothing, and its `(` and `)` open and close no parenthesis.
    pattern: Pattern = None
    for kind, text in map(unreserved, unredirected(tokens)):
        if pattern is not None:
            pattern, inside = in_pattern(pattern, kind, text)
            if inside:
                continue
        if kind == "word" and text == "in" and opens_case(unrepeated(current)[0]):
            current.append(text)
            close("")
            pattern = "start"
            continue
        if kind == "op":
            if REDIRECTION.fullmatch(text) is None and (
                not SEPARATORS.isdisjoint(text) or "(" in text or ")" in text
            ):
                close(text)
            if text.strip() in TERMINATORS:
                pattern = "start"
            continue
        if "`" not in text:
            current.append(text)
            continue
        for index, piece in enumerate(text.split("`")):
            if index > 0:
                close("`")
            if piece:
                current.append(piece)
    close("")
    return tuple(found)


# The body of a function that zsh's short form defines (`defines`): one command, or the whole
# `&&` or `||` list up to the next `;`, `&` or newline (`carried`).
type Body = Literal["simple", "list"] | None


def defines(current: list[str], text: str) -> Body:
    """The body of the function whose head the operator `text` after the words `current` ends, or
    None when it ends none. An operator that starts with `()` after a name, as in `f() cd x`,
    `f();cd x`, `f()() cd x`, `f g () ; cd x` or `env() cd x`, makes the next command the body
    (`simple`), so that zsh runs the `cd` of `f() X=1; cd x` and of `f() X=1 && cd x`. `;`, a
    newline or `()` after `function` and a name, as in `function f; cd x` or `function f() cd x`,
    makes the whole next list the body, so that zsh runs no `cd` in
    `function f; true && cd x || exit`. An anonymous `() cd x` has no name, nor have
    `function () cd x` and the `\n()` of `true\n() cd x`, and zsh runs each at once."""
    head = list(itertools.dropwhile(lambda word: word in RESERVED, current))
    # zsh reads `function` after `time` as reserved too, so `time function f() true && cd x` runs no `cd`.
    word = list(itertools.dropwhile(leads, current))
    named = word[:1] == ["function"] and bool(word[1:]) and "{" not in word
    if text.startswith("()") and head not in ([], ["function"]):
        return "list" if named else "simple"
    # `;` and newlines, then the body: `function f;(true)` and `function f; ;true` define `f` too.
    separators = itertools.takewhile(lambda operator: operator != "(", operators(text))
    return "list" if named and set(separators) <= {";"} else None


@dataclass(frozen=True, slots=True)
class Defined:
    """The body of a function that zsh's short form defines, as `cached_commands` reads it
    (`carried`): its `Body`, or None outside a body; whether a word of it came yet (`started`);
    the number of parentheses open before its head (`level`); whether it holds a word of
    OPENS or a backtick (`held`), whose `;`, `&` or newline can end no body; and whether it is the
    body of a short `repeat` that starts with the next part that holds a word (`waits`, of
    `repeats`)."""

    kind: Body = None
    started: bool = False
    level: int = 0
    held: bool = False
    waits: bool = False


# The words that open a compound command, whose `;`, `&` or newline end no body of a function
# (`carried`), as in `function f; if true; then true; fi && cd x`, or that take a whole list as
# their body in zsh, as `repeat` does in `f() repeat 1 true && cd x`.
OPENS = frozenset({"{", "if", "while", "until", "for", "foreach", "select", "case", "repeat", "coproc", "do"})
# The words that close a compound command or go on with one, which zsh refuses after the count of
# a `repeat` and bash passes to a program `repeat` as arguments (`unrepeated`): read as reserved,
# the `fi` of `if false; then repeat 1 fi; cd x || exit; fi` would close the `if` for bash.
ENDS = frozenset({"}", "then", "elif", "else", "fi", "done", "esac", "end"})


# The words that the reader of `cached_commands` reads as reserved somewhere; quoted, each is
# `Unreserved` there.
KEYWORDS = RESERVED | OPENS | ENDS | {"function", "in"}


def leads(word: str) -> bool:
    """True when `word` can stand before a reserved word and leave it reserved: a reserved word of
    RESERVED, or `time` and its `-p`, unquoted, as in `time repeat 1 rm x`; the `fi` of
    `"time" fi` is an argument of the program `time`."""
    return word in RESERVED or (word in ("time", "-p") and not isinstance(word, Quoted))


def unrepeated(current: list[str]) -> tuple[list[str], bool]:
    """The part `current` without each `repeat` and its count of zsh's `repeat` at its start, after
    the words that `leads` takes, where a word other than one of ENDS follows them: the command
    that `repeat` runs, as the `cd` of `repeat 1 cd ..`, `repeat 1 repeat 1 cd ..` or
    `time repeat 1 cd ..`, or the `do` or `{` that opens its body, as in `repeat 0 do true; done`,
    so that the checks read that command and that body as the shell runs them; and whether it
    dropped one. Where the rest runs nothing, as in `repeat 0 do X=1; done || cd x`, it keeps the
    part as it is, so that `repeat` stays a command and keeps the operators after the part."""
    kept: list[str] = []
    rest, cut = current, False
    while True:
        lead = list(itertools.takewhile(leads, rest))
        kept, rest = [*kept, *lead], rest[len(lead) :]
        if rest[:1] != ["repeat"] or not rest[2:] or rest[2] in ENDS:
            dropped = [*kept, *rest]
            return (current if cut and command_word(dropped) is None else dropped), cut
        rest, cut = rest[2:], True


def kept_opens(words: list[str]) -> list[str]:
    """The reserved words right after the count of the `repeat` that starts the command `words`,
    which `unrepeated` kept, as the `do` of `repeat 0 do X=1; done`, so that `outermost` counts the
    body that they open; not a `{`, which `outermost` counts as a word of the command. Empty where
    `words` starts with no `repeat`."""
    return [word for word in reserved_lead(words[2:]) if word != "{"] if words[:1] == ["repeat"] else []


# How a part opens zsh's short `repeat` (`repeats`): its body starts in that part, or it starts
# with the next part, after the `;` and newlines of that part.
type Repeat = Literal["here", "next"] | None


def repeats(current: list[str], then: str) -> Repeat:
    """How the part `current`, before the operators `then`, opens zsh's short `repeat`, whose body
    is the whole `&&`, `||` or `|` list after its count, or None when it opens none. `here`: the
    body starts in the part, as in `repeat 0 true && cd x || exit`, `repeat 0 (true) && cd x`,
    `repeat 0 if true; then true; fi && cd x` or `repeat 1 repeat 1 true`, which run no `cd`; also
    where a backtick, or `&&`, `||` or a pipe, follows the count, as in ``repeat 0 `true` && cd x``,
    since a redirection that the reader drops can start the body there.
    `next`: only `;` and newlines follow the count, so the body starts with the next part, as in
    `repeat 0;` and a newline before `true && cd x`, unless that part starts with `do` or `{`
    (`carried`). The long forms `repeat 0 do …; done` and `repeat 0 { … }` have bodies of their
    own."""
    head = list(itertools.dropwhile(leads, current))
    if head[:1] != ["repeat"] or not head[1:]:
        return None
    if head[2:]:
        return "here" if head[2] not in ("do", "{") else None
    if then.lstrip().startswith(("(", "`")):
        return "here"
    separators = list(itertools.takewhile(lambda operator: operator != "(", operators(then)))
    # A redirection, which `unredirected` drops, can start the body, as in `repeat 0 >/dev/null &&
    # cd x`, where zsh runs no `cd`; zsh runs the `cd` of `repeat 0 && cd x`, which is not sure either.
    if separators[:1] in (["&&"], ["||"], ["|"], ["|&"]):
        return "here"
    return "next" if separators and set(separators) <= {";"} else None


def unwaited(body: Defined, current: list[str]) -> Defined:
    """The body that `cached_commands` reads the part `current` in: none where `body` waits
    (`repeats`) and `current` starts with `do` or `{`, the long form `repeat 0; do …; done` or
    `repeat 0; { … }`, whose body is its own; else `body`."""
    return Defined() if body.waits and current[:1] in (["do"], ["{"]) else body


def carried(body: Defined, current: list[str], then: str, depth: int, *, short: Repeat) -> Defined:
    """The body that `cached_commands` reads after the part `current`, `depth` parentheses deep,
    and its operators `then`: while it is open, the next command belongs to it and gets the mark
    DEFINED before its own reserved words. A head (`defines`) starts a body, or
    goes on with the body that holds it: `function f; g() true && cd x` and `function f; true &&
    function g; cd x` run no `cd`, nor does `repeat 0 f() true && cd x`, whose short `repeat`
    makes the body a `list`. A `simple` body ends with the first operator after its first
    part that holds a word, also one that runs nothing, as the `X=1` of `f() X=1; cd x`, or after
    the `)` of a subshell, as in `f() (true) && cd x`. A `list` body ends with the first `;`, `&` or
    newline after its first word. Each counts only in as many parentheses as the head, so the `;`
    of `function f; (true; true) && cd x` ends nothing. A body that holds a word of OPENS before
    its command word, or a backtick, ends only where a parenthesis open before its head closes,
    which only makes the checks read more directories: the reader cannot tell zsh's `}` after a
    word, as in `f() { true }`, from the `}` that closes a group, so it reads no closing word as
    the end of a body. So do the reserved words before a head in a body or
    after a short `repeat`, as the `do` of `function f; repeat 0 do g() true; done && cd x`.
    zsh's short `repeat` (`short`, of
    `repeats`) runs a `list` body as many times as its count says, also never, so it opens one
    too, from the command of its own part on, which a word of OPENS there holds, as the `if` of
    `repeat 0 if true; then true; fi && cd x`; inside a body it holds that body. A `next` body
    outside a body waits for its first part that holds a word, and starts there; a `do` or `{` as
    the first word of that part closes it (`cached_commands`), since `repeat 0; do …; done` is the
    long form."""
    head = defines(current, then)
    if head is not None:
        nested = body.kind is not None
        kind: Body = "list" if "list" in (head, body.kind) or short is not None else "simple"
        level = min(body.level, depth) if nested else depth
        # The reserved words before a head in a body, or after a short `repeat`, belong to that body,
        # as the `do` of `function f; repeat 0 do g() true; done && cd x`.
        lead = list(itertools.takewhile(leads, current)) if nested or short else []
        held = (body.held and nested) or not OPENS.isdisjoint(lead)
        body = Defined(kind, head == "simple" and body.kind == "list", level, held)
    elif body.kind is not None or short:
        # A short `repeat` outside a body opens a `list` body at its own part; its own `repeat`,
        # dropped from `current` (`unrepeated`) or before a body that waits, does not hold that
        # body.
        fresh = body.kind is None
        waits = short == "next" if fresh else body.waits and not current
        at = command_word(current)
        opening = [] if waits else current if at is None else current[: at + 1]
        held = (
            (not fresh and (body.held or short is not None)) or not OPENS.isdisjoint(opening) or "`" in then
        )
        level = depth if fresh else body.level
        started = (body.started or bool(current)) and not waits
        body = Defined(body.kind or "list", started, level, held, waits)
        for operator in operators(then):
            depth += (operator == "(") - (operator == ")")
            at_head = operator != "(" and depth == body.level and body.started and not body.held
            if depth < body.level or (at_head and (body.kind == "simple" or operator in (";", "&"))):
                body = Defined()
                break
    return body


# Where the reader of `cached_commands` stands in a pattern of a `case` (`in_pattern`): before its
# first word, or after it.
type Pattern = Literal["start", "inside"] | None
# The operators that end a branch of a `case`, after which a pattern, `esac` or zsh's `}` follows;
# bash and zsh refuse each of them outside a `case`.
TERMINATORS = frozenset({";;", ";&", ";|", ";;&"})


def opens_case(current: list[str]) -> bool:
    """True when the word `in` after `current` opens the patterns of a `case`: `current` ends in
    `case` and its subject, after reserved words only, as in `then case $x`."""
    head = current[:-2]
    return current[-2:-1] == ["case"] and all(leads(word) for word in head)


def in_pattern(pattern: Pattern, kind: str, text: str) -> tuple[Pattern, bool]:
    """The step of a token in a pattern of a `case`, as in `case a in (b|c) …` or `b) …`: where
    the reader stands after it, and whether the token belongs to the pattern, which runs nothing
    and opens and closes no parenthesis. A newline or `(` before the first word, a word, and `|`
    belong to it, and `)` ends it, each with the blanks and newlines around it, as the `\n(` of
    `case a in\n(b)`. An `esac` or a `}` as its first word, any other operator, and a word with a
    backtick end the pattern before the token, which the reader then reads as before: zsh's
    `case a { … }` ends with `}` where the other form ends with `esac`."""
    if kind == "op":
        bare = text.strip()
        if pattern == "start" and bare in ("(", ""):
            return ("inside" if bare else "start"), True
        if bare in ("|", ")"):
            return ("inside" if bare == "|" else None), True
        return None, False
    if "`" in text or (pattern == "start" and text in ("esac", "}")):
        return None, False
    return "inside", True


def words(text: str) -> list[str] | None:
    """The words of `text`, its operators left out, or None when a quote is open."""
    tokens = lex(text)
    return None if tokens is None else [value for kind, value in tokens if kind == "word"]
