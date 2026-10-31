"""Refuse a call that reaches a path of a frontend's path list, and refuse or ask for a command that
a Bash rule of the list names.

The path list is a JSON object of five lists of strings, which `harness install` renders for the
frontend: `deny` for every call, `edit` and `ask` for a call that writes or edits a file,
`bash_deny` and `bash_ask` for a shell call. The check reads it once per process, through
`paths.contents`, and refuses the call when the file is missing, is no JSON object, or holds no list
of strings under a key that the call needs.

THE PATHS. Each path of the call (`Call.paths`), each path that it reads below (`Call.wide`) and
each word of a shell command meets the `deny` list; each path of a call that writes or edits a file
meets the `edit` list, whose match refuses, and then the `ask` list, whose match asks. A path that
`edit` and `ask` both match is refused. Its globs are OpenCode's: `**` any depth, `*` and `?` within
one segment; `X/**` covers X too; the match ignores case. A path is checked as an absolute path: a
leading `~`, `~user`, `$HOME` or `${HOME}` expanded, a relative path joined to the working directory
of the call and normalised as text, so no file is read. A relative path of a call that names no
working directory is refused, since the check cannot place it. A path with a glob character, GLOB,
is checked as it is and again cut to its directory before that character. That cut path is wide,
and so is every path of `Call.wide`, every word of a command that RECURSIVE matches, and the word
after `cd` or `pushd`: a wide path is refused when it holds the literal prefix of an absolute rule
(literal_prefix).

THE WORDS of a command are those of each reading of `shell.readings`, and each part of a word that
`=`, `:`, `,` or `#` separates (zsh's `extendedglob` reads `a#` as a pattern that matches `a`); a
command that no reading reads, as one with a quote that does not close, gives the text between
blanks, quotes and control characters (FALLBACK). A word that any of them gives is checked, so a
reading cannot hide one.

THE BASH RULES apply to each segment of the command (segments), in each of its two lines: as
written, and with each backslash-newline read as a line break. A rule matches the words of a
segment from any of its words (bash_matcher): those of each reading of the segment, those of the
reading that takes no `#` as a comment, or, when no reading reads it, the text between blanks. A
`bash_deny` rule refuses, a `bash_ask` rule asks. A rule meets only the word lists that hold each of
its needed texts (needed), which one search of the joined word lists per needed text finds.

A TABLE WITHOUT BASH RULES (check_paths) takes its lists as `Lists`: `deny`, `edit` and `ask`, any
rules that the table adds, and an `allow` list, which refuses each path outside it that ALLOW_PATH
reads. Its `Reading` adds to the words of a command: each home path and each absolute path below a
directory of user data that TEXT_PATH finds in the text, wherever it stands; every word of a part
that runs `cd` or `pushd`, as a wide path, and the home, wide, for a `cd` with no directory or with
`-`; and it lets a glob path reach only the names that its glob segment matches (segment_glob).

It is a text check: a path that a command builds at run time passes it.
"""

import bisect
import functools
import pwd
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from . import HarnessError
from .contract import PASS, Call, Verdict, needs_cwd
from .jsonio import loads
from .paths import contents
from .shell import lex, readings

type Rule = tuple[str, re.Pattern[str], str]
type Matcher = Callable[[list[str], str], bool]
type BashRule = tuple[str, Matcher, tuple[str, ...]]

# The home directory, as the shell expands a `~`.
HOME = str(Path.home())
# A leading `$HOME` or `${HOME}`, which the shell expands as `~`.
HOME_VARIABLE = re.compile(r"(?:\$HOME|\$\{HOME\})(?=/|$)")
# A command that reads below its paths: OpenCode's guard's `RECURSIVE`.
RECURSIVE = re.compile(
    r"\b(?:find|rg|tree|du|tar|zip|rsync|walkdir|readdir)\b"
    r"|\b(?:grep|egrep|ls|cp|chmod|chown)\b[^|;&\n]*\s(?:--recursive\b|-[A-Za-z]*[rR])"
)
# The characters of a shell glob or a brace expansion.
GLOB = re.compile(r"[*?\[{]")
# The words of a command that no reading reads: the text between blanks, quotes and control characters.
FALLBACK = re.compile(r"[\s;&|()<>`'\"]+")
# The words that make the next word of a command wide.
INTO = frozenset({"cd", "pushd"})
# The text between two words of a segment when a Bash rule matches them: a NUL, which no argument
# of a command can hold, so that a blank inside a quoted word is no boundary.
WORD_BREAK = "\0"
CLOSED = "The guard fails closed. Tell the user, and do not run the call in another form."
# A home path, or an absolute path below a directory that holds user data, wherever it stands in a
# command: the union of the path forms of OpenCode's and oh-my-pi's guard plugins.
TEXT_PATH = re.compile(
    r"""(?:^|[\s'"`=(:,\[{<>])((?:~|\$HOME|\$\{HOME\})(?=[/\s'"`;|&)]|$)[^\s'"`;|&<>(){}\[\],]*"""
    r"""|/(?:Users|Volumes|private|var|tmp|etc|home)(?:/[^\s'"`;|&<>(){}\[\],]*)?)"""
)
# The paths that an `allow` list reads: those of TEXT_PATH but below `/home`.
ALLOW_PATH = re.compile(
    r"""(?:^|[\s'"`=(:,\[{<>])((?:~|\$HOME|\$\{HOME\})(?=[/\s'"`;|&)]|$)[^\s'"`;|&<>(){}\[\],]*"""
    r"""|/(?:Users|Volumes|private|var|tmp|etc)(?:/[^\s'"`;|&<>(){}\[\],]*)?)"""
)
# The words before a command name that leave it the command name, as `cd` in `then cd x`.
LEAD = frozenset({"{", "!", "then", "do", "else", "builtin", "command", "time"})
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# A shell edit of a file in place: OpenCode's `deny` rules name these, and the refusal is short.
IN_PLACE = re.compile(r"^(?:rtk\s+)?(?:(?:sed|gsed)\s+(?:-i|--in-place)|awk\s+-i|perl\s+-p?i)")
IN_PLACE_PART = re.compile(r"&&|\|\||[;|\n]")


class NeedsCwdError(Exception):
    """A relative path of a call that names no working directory."""


@dataclass(frozen=True, slots=True)
class Reading:
    """What a table's path list reads in a command beyond the words of each reading: `text_paths`,
    each path that TEXT_PATH finds; `cd_parts`, every word of a part that runs `cd` or `pushd` as a
    wide path, and the home for a `cd` with no directory or with `-`; `segment_glob`, a glob path
    that reaches only the names that its glob segment matches."""

    text_paths: bool = False
    cd_parts: bool = False
    segment_glob: bool = False


@dataclass(frozen=True, slots=True)
class Lists:
    """The rules of a table that runs no Bash rules: `deny` for every path of a call, `edit` and
    then `ask` for each path of a call that writes or edits, `allow`, when not None, for each path
    that ALLOW_PATH reads, and the `Reading` of a command."""

    deny: tuple[Rule, ...]
    edit: tuple[Rule, ...]
    ask: tuple[Rule, ...]
    allow: tuple[Rule, ...] | None
    reading: Reading


@functools.cache
def loaded(location: str) -> dict[str, object] | str:
    """The path list at `location`, read once per process, or the reason that it cannot be used."""
    try:
        return dict(loads(contents(location), where=location))
    except (OSError, ValueError, HarnessError) as error:
        return f"{type(error).__name__}: {error}"


def listed(location: str, key: str) -> list[str] | str:
    """The list `key` of the path list at `location`, or the reason to refuse the call."""
    found = loaded(location)
    if isinstance(found, str):
        return f"The path list {location} cannot be used ({found}), so the call is blocked. {CLOSED}"
    if key not in found:
        return (
            f"The path list {location} cannot be used (it has no {key!r}), so the call is blocked. {CLOSED}"
        )
    items = cast("list[object]", found[key]) if isinstance(found[key], list) else None
    strings = [] if items is None else [item for item in items if isinstance(item, str)]
    if items is None or len(strings) != len(items):
        return (
            f'The path list {location} holds no list of strings under "{key}", so the call is blocked. '
            + CLOSED
        )
    return strings


def rule(glob: str, *, ignore_case: bool = True) -> re.Pattern[str]:
    """The path glob `glob` as a regular expression, for `fullmatch`, that ignores case unless
    `ignore_case` is false."""
    out, index = "", 0
    while index < len(glob):
        if glob.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
        elif glob.startswith("**", index):
            out, index = out + ".*", index + 2
        else:
            char = glob[index]
            out += "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char)
            index += 1
    if out.endswith("/.*"):
        out = out[:-3] + "(?:/.*)?"
    return re.compile(out, re.IGNORECASE if ignore_case else re.NOFLAG)


def literal_prefix(glob: str) -> str:
    """The part of `glob` that names one directory or file: up to the last `/` before its first
    `*` or `?`, or the whole glob."""
    found = re.search(r"[*?]", glob)
    return glob if found is None else glob[: max(glob.rfind("/", 0, found.start()), 0)]


@functools.cache
def path_rules(location: str, key: str) -> tuple[Rule, ...] | str:
    """(glob, pattern, literal prefix in lower case) of each glob of the list `key`, or the reason to
    refuse the call."""
    globs = listed(location, key)
    if isinstance(globs, str):
        return globs
    return tuple((glob, rule(glob), literal_prefix(glob).lower()) for glob in globs)


@functools.cache
def user_home(user: str) -> str | None:
    """The home directory of `user`, or None when there is no such user."""
    try:
        return pwd.getpwnam(user).pw_dir
    except KeyError:
        return None


def expanded(raw: str) -> str:
    """`raw` with a leading `~`, `~user`, `$HOME` or `${HOME}` expanded as the shell expands it."""
    found = HOME_VARIABLE.match(raw)
    if found is not None:
        return HOME + raw[found.end() :]
    if not raw.startswith("~"):
        return raw
    user = raw[1:].partition("/")[0]
    home = HOME if not user else user_home(user)
    if home is None:
        return raw
    return home.rstrip("/") + raw[1 + len(user) :] or "/"


def normal(path: str) -> str:
    """The absolute path `path` with each empty name, `.` and `..` resolved as text."""
    names: list[str] = []
    for name in path.split("/"):
        if name == "..":
            if names:
                names.pop()
        elif name not in ("", "."):
            names.append(name)
    return "/" + "/".join(names)


def kept(path: str) -> str:
    """The absolute path `path` normalised as text, as `posixpath.normpath` does: a leading `//`
    kept, which POSIX leaves to the system."""
    lead = "//" if path.startswith("//") and not path.startswith("///") else "/"
    return lead + normal(path)[1:]


def absolute(raw: str, cwd: str | None) -> str:
    """`raw` as an absolute, normalised path: a home form expanded, a relative path joined to `cwd`."""
    path = expanded(raw)
    if not path.startswith("/"):
        if cwd is None:
            raise NeedsCwdError(raw)
        path = cwd + "/" + path
    return normal(path)


def segment_glob(segment: str) -> re.Pattern[str] | None:
    """The shell glob `segment`, one name of a path, as a pattern that ignores case: `*` any text, a
    leading dot too, `?` one character, `[…]` a bracket expression, `\\x` the character x. None for a
    segment that it cannot read, a brace expansion included, which then reaches every name."""
    out: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        end = segment.find("]", index + 2) if char == "[" else -1
        if char == "\\" and index + 1 < len(segment):
            out.append(re.escape(segment[index + 1]))
            index += 1
        elif char == "{":
            return None
        elif char in "*?":
            out.append(".*" if char == "*" else ".")
        elif end >= 0:
            body = segment[index + 1 : end]
            out.append("[" + ("^" + body[1:] if body.startswith("!") else body).replace("\\", "\\\\") + "]")
            index = end
        else:
            out.append(re.escape(char))
        index += 1
    try:
        return re.compile("".join(out), re.IGNORECASE)
    except re.error:
        return None


def refused_path(
    raw: str, cwd: str | None, listed: tuple[str, tuple[Rule, ...]], *, wide: bool, by_segment: bool = False
) -> str | None:
    """The reason that the rules of `listed`, (the name of the list, its rules), refuse the path
    `raw`, or None. A path with a glob character is checked as it is, and again cut to its directory
    before the first glob character, which is wide. A wide path, one that the call reads below, is
    refused when it holds the literal prefix of an absolute rule; with `by_segment`, the cut path
    holds only the prefixes whose name below it the glob segment matches (segment_glob)."""
    kind, rules = listed
    raw = expanded(raw)
    paths: list[tuple[str, bool, re.Pattern[str] | None]] = [(absolute(raw, cwd), wide, None)]
    glob = GLOB.search(raw)
    if glob is not None:
        cut = raw.rfind("/", 0, glob.start())
        after = raw.find("/", glob.start())
        segment = segment_glob(raw[cut + 1 : len(raw) if after < 0 else after]) if by_segment else None
        paths.append((absolute((raw[:cut] or "/") if cut >= 0 else ".", cwd), True, segment))
    for path, reads_below, segment in paths:
        under = "/" if path == "/" else path.lower() + "/"
        for name, pattern, prefix in rules:
            if pattern.fullmatch(path):
                return f"{path} matches the {kind} rule {name}"
            if (
                reads_below
                and prefix.startswith(under)
                and (segment is None or segment.fullmatch(prefix[len(under) :].split("/")[0]))
            ):
                return (
                    f"the call reads below {path}, which holds {prefix}, which the {kind} rule {name} covers"
                )
    return None


def cd_words(sequence: list[tuple[bool, str]]) -> dict[tuple[str, bool], None]:
    """(word, True) of each word of a part of `sequence` that runs `cd` or `pushd`, and ("~", True)
    for each such `cd` with no directory or with `-`, which moves home."""
    found: dict[tuple[str, bool], None] = {}
    part: list[str] = []
    for is_word, text in [*sequence, (False, ";")]:
        if is_word:
            part.append(text)
            continue
        for index, word in enumerate(part):
            before = part[index - 1] if index else None
            if word in INTO and (before is None or before in LEAD or ASSIGNMENT.match(before)):
                found.update(dict.fromkeys((w, True) for w in part))
                to = [w for w in part[index + 1 :] if not (w.startswith("-") and len(w) > 1)]
                if not to or to[0] == "-":
                    found["~", True] = None
        part = []
    return found


def command_words(command: str, reading: Reading | None = None) -> dict[tuple[str, bool], None]:
    """(word, wide) of each word of `command` in any reading, and of each part of a word that `=`,
    `:`, `,` or `#` separates, in their first order. Every word is wide in a command that RECURSIVE
    matches, and the word after `cd` or `pushd` is. `reading` adds the words of TEXT_PATH and of the
    parts that run `cd` (cd_words)."""
    reading = reading or Reading()
    recursive = RECURSIVE.search(command) is not None
    read = readings(command)
    sequences: list[list[tuple[bool, str]]] = (
        [[(True, word) for word in FALLBACK.split(command) if word]]
        if read is None
        else [[(kind == "word", text) for kind, text in tokens] for tokens in read]
    )
    found: dict[tuple[str, bool], None] = {}
    for sequence in sequences:
        before = ""
        for is_word, text in sequence:
            if is_word:
                wide = recursive or before in INTO
                for part in (text, *re.split(r"[=:,#]", text)):
                    if part:
                        found[part, wide] = None
            before = text if is_word else ""
        if reading.cd_parts:
            found.update(cd_words(sequence))
    if reading.text_paths:
        for match in TEXT_PATH.finditer(command):
            raw = match.group(1)
            cd = re.search(r"\bcd\s+['\"]?" + re.escape(raw), command) is not None
            found[raw, recursive or cd] = None
    return found


def segments(line: str) -> list[str]:
    """The segments of the command line `line`, as Claude Code checks a Bash rule on them: the line
    split at `;`, `&&`, `||`, `|`, `&` and a newline outside quotes, and the body of each `$(…)`,
    backtick and `( … )` a segment of its own, split the same way; a backslash-newline outside
    single quotes dropped; each stripped, none empty."""
    found: list[str] = []

    def scan(index: int, close: str | None) -> int:
        """Scan `line` from `index` to the `close` of this level; the index after it. The text of a
        segment collects as pieces, joined once, so that the scan is linear in the length of `line`."""
        pieces: list[str] = []
        quoted = False
        while index < len(line):
            char = line[index]
            if char == "\\":  # a backslash-newline joins two lines, as in the shell
                pieces.append("" if line.startswith("\n", index + 1) else line[index : index + 2])
                index += 2
            elif char == "'" and not quoted:
                end = line.find("'", index + 1)
                end = len(line) if end < 0 else end + 1
                pieces.append(line[index:end])
                index = end
            elif char == close and not quoted:
                found.append("".join(pieces))
                return index + 1
            elif line.startswith("$(", index) or char == "`" or (char == "(" and not quoted):
                end = scan(index + (2 if char == "$" else 1), "`" if char == "`" else ")")
                pieces.append(line[index:end])
                index = end
            elif char == '"':
                pieces.append(char)
                quoted, index = not quoted, index + 1
            elif not quoted and char in ";|&\n":  # `&&` and `||` leave an empty segment, which is dropped
                found.append("".join(pieces))
                pieces, index = [], index + 1
            else:
                pieces.append(char)
                index += 1
        found.append("".join(pieces))
        return index

    scan(0, None)
    return [segment.strip() for segment in found if segment.strip()]


def bash_matcher(body: str) -> Matcher:
    """`matches(words, text)`: whether `Bash(body)` matches a segment with the words `words`, `text`
    being those words joined by WORD_BREAK, from any of its words, so that an assignment, a wrapper
    such as `env` or a keyword such as `then` before the command does not hide it: `Bash(x *)` when
    the words of `x` are a run of `words`, any other body when it matches the words from one of them
    to the last, with `*` as any text and a trailing ` *` as no text too. A blank of the body matches
    only the boundary between two words, so that a quoted word such as the message of
    `git commit -m "git push --force"` matches no rule. The cost is linear in the length of `text`."""
    prefix = re.fullmatch(r"([^*]*[^*\s]) \*", body, re.DOTALL)
    if prefix is not None:
        run = prefix.group(1).split()
        return lambda words, _text: any(words[i : i + len(run)] == run for i in range(len(words)))
    trailing = body.endswith(" *")
    parts = [WORD_BREAK.join(re.split(r"\s+", part)) for part in (body[:-2] if trailing else body).split("*")]
    return lambda _words, text: placed(parts, text, trailing=trailing)


def placed(parts: list[str], text: str, *, trailing: bool) -> bool:
    """Whether the literal parts `parts` of a Bash body, with a `*` between each two, match `text`
    from one of its word starts to its end: the first part at a word start (the start of `text`, or
    just after a WORD_BREAK), each later part after the one before it, and the last part at the end
    of `text`, or, when the body has a `trailing` ` *`, also before a WORD_BREAK. Each part takes
    the earliest place that it can: a `*` matches any text, so an earlier place leaves the later
    parts all the text that a later place leaves them, and one `str.find` for each part decides."""
    if len(parts) == 1:
        if trailing:
            return (WORD_BREAK + text + WORD_BREAK).find(WORD_BREAK + parts[0] + WORD_BREAK) >= 0
        return (WORD_BREAK + text).endswith(WORD_BREAK + parts[0])
    first, *middle, last = parts
    at = (WORD_BREAK + text).find(WORD_BREAK + first)
    if at < 0:
        return False
    at += len(first)
    for part in middle:
        at = text.find(part, at)
        if at < 0:
            return False
        at += len(part)
    if text.endswith(last) and len(text) - len(last) >= at:
        return True
    return trailing and text.find(last + WORD_BREAK, at) >= 0


def needed(body: str) -> tuple[str, ...]:
    """The texts that a segment's words, joined by WORD_BREAK, hold whenever `Bash(body)` matches
    them: the run of words of `Bash(x *)`, or each literal part of any other body."""
    prefix = re.fullmatch(r"([^*]*[^*\s]) \*", body, re.DOTALL)
    if prefix is not None:
        return (WORD_BREAK.join(prefix.group(1).split()),)
    trailing = body.endswith(" *")
    parts = (WORD_BREAK.join(re.split(r"\s+", part)) for part in (body[:-2] if trailing else body).split("*"))
    return tuple(part for part in parts if part)


@functools.cache
def bash_rules(location: str, key: str) -> tuple[BashRule, ...] | str:
    """(body, bash_matcher(body), needed(body)) of each Bash body of the list `key`, or the reason to
    refuse."""
    bodies = listed(location, key)
    if isinstance(bodies, str):
        return bodies
    return tuple((body, bash_matcher(body), needed(body)) for body in bodies)


def segment_words(segment: str) -> list[list[str]]:
    """The word lists of `segment` that a Bash rule is matched on: the words of each reading, and of
    the reading that takes no `#` as a comment; the text between blanks when no reading reads it."""
    read = readings(segment)
    if read is None:
        return [segment.split()]
    found = [[text for kind, text in tokens if kind == "word"] for tokens in read]
    if "#" in segment:
        # An empty quote before each `#` puts it inside a word, where it starts no comment.
        tokens = lex(segment.replace("#", "''#"))
        if tokens is not None:
            found.append([text for kind, text in tokens if kind == "word"])
    return found


def matched(rules: tuple[BashRule, ...], command: str) -> str | None:
    """The body of the first of `rules` that matches a word list of a segment of `command`, as
    written or with each backslash-newline as a line break, or None; rule by rule, and word list by
    word list. A rule meets only the word lists that hold each of its needed texts: one search of the
    joined word lists for each distinct needed text finds the lists that hold it, by the offset of
    each hit, so a command of many segments costs each rule one matcher call per list that holds
    all its needed texts. A needed text holds no newline, the text between two joined lists."""
    lines = dict.fromkeys((command, command.replace("\\\n", "\n")))
    split = [
        (words, WORD_BREAK.join(words))
        for line in lines
        for segment in dict.fromkeys(segments(line))
        for words in segment_words(segment)
    ]
    joined = "\n".join(text for _words, text in split)
    starts: list[int] = []
    offset = 0
    for _words, text in split:
        starts.append(offset)
        offset += len(text) + 1
    holders: dict[str, frozenset[int]] = {}

    def holding(need: str) -> frozenset[int]:
        """The indices of the word lists that hold `need`, searched once per command."""
        if need not in holders:
            found: list[int] = []
            at = joined.find(need)
            while at >= 0:
                found.append(bisect.bisect_right(starts, at) - 1)
                after = found[-1] + 1
                at = joined.find(need, starts[after]) if after < len(starts) else -1
            holders[need] = frozenset(found)
        return holders[need]

    for body, matches, needs in rules:
        held = [holding(need) for need in needs]
        indices = sorted(held[0].intersection(*held[1:])) if held else range(len(split))
        if any(matches(*split[index]) for index in indices):
            return body
    return None


def refusal(reason: str) -> Verdict:
    """The denial of a path that the list `deny` or `edit` refuses."""
    return Verdict(
        "deny",
        f"Refused by the path guard: {reason}. Use only the paths your task names. "
        "Do not reach this path in another form.",
    )


def check(call: Call, location: str) -> Verdict:
    """Deny a call that reaches a path of the `deny` list, or a write to a path of the `edit` list,
    or a command that a `bash_deny` rule matches; ask for a write to a path of the `ask` list, and
    for a command that a `bash_ask` rule matches."""
    deny = path_rules(location, "deny")
    if isinstance(deny, str):
        return Verdict("deny", deny)
    try:
        refused = denied(call, deny)
        if refused is None and call.action in ("write", "edit"):
            return written(call, location)
    except NeedsCwdError as error:
        return needs_cwd("path list", call.command if call.action == "shell" else str(error))
    if refused is not None:
        return refusal(refused)
    return ruled(call.command, location) if call.action == "shell" else PASS


def denied(call: Call, deny: tuple[Rule, ...], reading: Reading | None = None) -> str | None:
    """The reason that the `deny` list refuses a path of the call, a path that it reads below, or a
    word of its shell command, read as `reading` says, or None."""
    reading = reading or Reading()
    words = command_words(call.command, reading) if call.action == "shell" else {}
    for raw, wide in (
        *((path, False) for path in call.paths),
        *((path, True) for path in call.wide),
        *words,
    ):
        refused = refused_path(raw, call.cwd, ("deny", deny), wide=wide, by_segment=reading.segment_glob)
        if refused is not None:
            return refused
    return None


def written(call: Call, location: str) -> Verdict:
    """The verdict of the `edit` and `ask` lists on each path of a call that writes or edits."""
    edit = path_rules(location, "edit")
    if isinstance(edit, str):
        return Verdict("deny", edit)
    ask = path_rules(location, "ask")
    if isinstance(ask, str):
        return Verdict("deny", ask)
    return edited(call, edit, ask)


def edited(call: Call, edit: tuple[Rule, ...], ask: tuple[Rule, ...]) -> Verdict:
    """Deny a path of the call that `edit` refuses, else ask for one that `ask` matches."""
    for raw in call.paths:
        refused = refused_path(raw, call.cwd, ("edit", edit), wide=False)
        if refused is not None:
            return Verdict(
                "deny", f"Refused by the path guard: {refused}. Do not make the change in another form."
            )
    for raw in call.paths:
        asked = refused_path(raw, call.cwd, ("ask", ask), wide=False)
        if asked is not None:
            return Verdict("ask", f"The path guard asks the user: {asked}.")
    return PASS


def ruled(command: str, location: str) -> Verdict:
    """The verdict of the `bash_deny` and `bash_ask` lists on the segments of `command`."""
    bash_deny = bash_rules(location, "bash_deny")
    if isinstance(bash_deny, str):
        return Verdict("deny", bash_deny)
    bash_ask = bash_rules(location, "bash_ask")
    if isinstance(bash_ask, str):
        return Verdict("deny", bash_ask)
    hit = matched(bash_deny, command)
    if hit is not None:
        return Verdict(
            "deny",
            f"Refused by the settings template's rule Bash({hit}). Do not run the command in another form.",
        )
    asked = matched(bash_ask, command)
    if asked is not None:
        return Verdict("ask", f"The settings template's rule Bash({asked}) asks the user.")
    return PASS


@functools.cache
def present(location: str) -> dict[str, object] | str | None:
    """The path list at `location`, read once per process; None when there is no file there, or the
    reason that it cannot be used."""
    try:
        text = contents(location)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        return f"{type(error).__name__}: {error}"
    try:
        return dict(loads(text, where=location))
    except (ValueError, HarnessError) as error:
        return f"{type(error).__name__}: {error}"


def local_rules(location: str) -> tuple[tuple[Rule, ...], tuple[Rule, ...] | None] | str:
    """The `deny` rules and the `allow` rules of an optional path list at `location`: none when there
    is no file there, and `allow` None when it holds no `allow`; the reason to refuse every call when
    the file cannot be used. An `allow` rule matches with case."""
    found = present(location)
    if found is None:
        return (), None
    if isinstance(found, str):
        return f"The path list {location} cannot be used ({found}), so the call is blocked. {CLOSED}"
    lists: dict[str, list[str]] = {}
    for key in ("deny", "allow"):
        items = cast("list[object]", found[key]) if isinstance(found.get(key), list) else None
        if key in found and (items is None or not all(isinstance(item, str) for item in items)):
            why = f'it holds no list of strings under "{key}"'
            return f"The path list {location} cannot be used ({why}), so the call is blocked. {CLOSED}"
        if items is not None:
            lists[key] = [item for item in items if isinstance(item, str)]
    deny = tuple((glob, rule(glob), literal_prefix(glob).lower()) for glob in lists.get("deny", []))
    if "allow" not in lists:
        return deny, None
    return deny, tuple((glob, rule(glob, ignore_case=False), literal_prefix(glob)) for glob in lists["allow"])


def outside(call: Call, allow: tuple[Rule, ...] | None) -> str | None:
    """The reason that a path of the call that ALLOW_PATH reads lies outside `allow`, or None: a path
    with a glob character is cut to its directory before it."""
    if allow is None:
        return None
    for text in (call.command if call.action == "shell" else "", *call.paths, *call.wide):
        for found in ALLOW_PATH.finditer(text):
            path = absolute(found.group(1), "/")
            glob = re.search(r"[*?\[]", path)
            if glob is not None:
                path = path[: path.rfind("/", 0, glob.start())] or "/"
            if not any(pattern.fullmatch(path) for _name, pattern, _prefix in allow):
                names = ", ".join(name for name, _pattern, _prefix in allow)
                return f"{path} is outside the paths this session may use: {names}"
    return None


def check_paths(call: Call, lists: Lists) -> Verdict:
    """Deny a call that reaches a path of `lists.deny` or one outside `lists.allow`, or a write to a
    path of `lists.edit`; ask for a write to a path of `lists.ask`."""
    try:
        refused = denied(call, lists.deny, lists.reading) or outside(call, lists.allow)
        if refused is None and call.action in ("write", "edit"):
            return edited(call, lists.edit, lists.ask)
    except NeedsCwdError as error:
        return needs_cwd("path list", call.command if call.action == "shell" else str(error))
    return PASS if refused is None else refusal(refused)


def in_place(call: Call) -> Verdict:
    """Deny a shell command that edits a file in place, such as `sed -i`, with a short reason."""
    parts = IN_PLACE_PART.split(call.command) if call.action == "shell" else []
    if any(IN_PLACE.match(part.strip()) for part in parts):
        return Verdict(
            "deny",
            "Refused: an in-place shell edit (sed -i, perl -pi, awk -i). Change a file with the edit tool, "
            "or write a new file with the write tool.",
        )
    return PASS
