"""The reading of a shell command that the shell checks share.

`lex` splits a command into words and operators as the shell does for the forms the checks read:
a quoted character is never an operator, a `#` that starts a word starts a comment to the end of
the line, a backslash-newline joins two lines, and inside double quotes a backslash escapes only
`$`, a backtick, `"` and `\\`, and a backslash-newline is removed. An ANSI-C quote `$'…'` gives
its text with the escapes decoded (`ansi_c`), and a locale quote `$"…"` reads as a double quote,
each in a dialect: bash's, zsh's, or `plain`, which reads the `$` as a character. It runs no
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

import functools
import re
import sys
from dataclasses import dataclass
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
    `nested`, also each reading with its scripts spliced in (`scripts`)."""
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


# The wrapper, spelled exactly, after which every shell runs its own builtin: `builtin cd` moves
# the shell (`builtin_commands`).
KEEPS_BUILTIN = frozenset({"builtin"})
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
    runs its command word if that is a builtin (`Runs`), and the operator after it (`then`): `&&`,
    `;`, `|`, a parenthesis, a newline, a backtick, or empty at the end."""

    words: list[str]
    runs: Runs
    then: str


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


def builtin_commands(tokens: Tokens) -> list[Simple]:
    """Each simple command of `tokens` (`Simple`), with the words that `commands` gives, where the
    shell runs its command word if that is a builtin (`runs_of`), and the operator after it."""
    found: list[Simple] = []
    current: list[str] = []

    def close(then: str) -> None:
        nonlocal current
        at = command_word(current)
        if at is not None:
            found.append(Simple(current[at:], runs_of(current[:at], current[at]), then))
        current = []

    for kind, text in unredirected(tokens):
        if kind == "op":
            redirection = REDIRECTION.fullmatch(text) is not None
            if not redirection and (not SEPARATORS.isdisjoint(text) or "(" in text or ")" in text):
                close(text)
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
    return found


def words(text: str) -> list[str] | None:
    """The words of `text`, its operators left out, or None when a quote is open."""
    tokens = lex(text)
    return None if tokens is None else [value for kind, value in tokens if kind == "word"]
