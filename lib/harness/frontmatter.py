"""The strict frontmatter parser of the agents' and skills' Markdown files.

The frontmatter is the block between a `---` on line 1 and the next `---` line. It holds ten
keys (KEYS), each once, in one of two forms:

    key: value          a value plain or in double quotes, `\\\\` and `\\"` the only escapes
    key:                a block list of plain strings, one `  - item` line each, at least one
      - item

`tools` and `skills` take a block list, and every other key a value. `true` and `false` are
booleans for `disable-model-invocation` only, which takes no other value; every other value is a
string. Spaces at the edges of a value or an item are dropped, and a tab there is an error,
except inside double quotes. Anything else — a flow list, a block scalar, a continuation line,
a comment, an anchor or an alias, a duplicate or an unknown key, a control character up to the
closing `---` (C0 U+0000–U+001F except tab, a CR included; DEL U+007F; C1 U+0080–U+009F; LS
U+2028 and PS U+2029) — is an error that names the file and the line, and `harness` exits 2.
YAML would accept most of these and convert types on its own; this parser accepts only what the
sources write.

`parse_file`, the reader of a source, also checks two values against the neutral vocabulary that
each adapter maps to its frontend: `model` is a tier of TIERS, and each `tools` item is a tool of
TOOLS or a Kaimon tool `mcp/kaimon/<tool>`, one tool, no wildcard. In a SKILL.md it also checks
the `description`: at most 1,024 characters, and no `<` or `>`. Any other value exits 2, naming
the file.
"""

import pathlib
import re
import tempfile

from . import HarnessError

KEYS = {
    "name", "description", "model", "tools", "skills", "effort", "isolation",
    "disable-model-invocation", "omitClaudeMd", "permissionMode",
}
BOOLEAN = "disable-model-invocation"
LISTS = {"tools", "skills"}

KEY_LINE = re.compile(r"([A-Za-z][A-Za-z0-9-]*):(.*)")
ITEM_LINE = re.compile(r"  - (.*)")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")

# The neutral vocabulary of the sources: the tiers of `model`, and the tools of `tools`. A Kaimon
# tool is MCP followed by the name of one tool.
TIERS = ("large", "medium", "small")
TOOLS = ("read", "edit", "write", "grep", "glob", "shell", "agent", "web_search", "web_fetch")
MCP = "mcp/kaimon/"
MCP_TOOL = re.compile(r"mcp/kaimon/[A-Za-z0-9_]+")

# The longest `description` of a skill, in characters.
DESCRIPTION_MAX = 1024


class Frontmatter:
    """The parsed frontmatter of one file: `meta` maps a key to its value, `lines` to its raw
    line, and `body` is the text after the closing `---` line."""

    def __init__(self, meta, lines, body):
        self.meta, self.lines, self.body = meta, lines, body


def scalar(text, where):
    """The value of a plain or double-quoted scalar; `where` prefixes every error."""
    if text.startswith('"'):
        out, i = [], 1
        while i < len(text):
            c = text[i]
            if c == '"':
                if text[i + 1:]:
                    raise HarnessError(f"{where}: text after the closing quote")
                return "".join(out)
            if c == "\\":
                if text[i + 1:i + 2] not in ("\\", '"'):
                    raise HarnessError(f"{where}: an escape other than \\\\ and \\\"")
                out.append(text[i + 1])
                i += 2
                continue
            out.append(c)
            i += 1
        raise HarnessError(f"{where}: an unterminated quote")
    if text[:1] == "\t" or text[-1:] == "\t":
        raise HarnessError(f"{where}: a tab at the edge of a plain value; quote it with \"")
    first = text[:1]
    if first in "[{":
        raise HarnessError(f"{where}: a flow list or mapping; write a block list")
    if first in "|>":
        raise HarnessError(f"{where}: a block scalar")
    if first in "&*":
        raise HarnessError(f"{where}: an anchor or an alias")
    if first in "!'%@`#":
        raise HarnessError(f"{where}: a value that starts with {first!r}; quote it with \"")
    if " #" in text:
        raise HarnessError(f"{where}: a plain value that holds ' #'; quote it with \"")
    if ": " in text or text.endswith(":"):
        raise HarnessError(f"{where}: a plain value that holds ':'; quote it with \"")
    return text


def parse(text, path):
    """The `Frontmatter` of `text`, read from `path`, which every error names."""
    lines = text.split("\n")
    for number, line in enumerate(lines, 1):
        control = CONTROL.search(line)
        if control:
            c = control.group()
            raise HarnessError(f"{path}:{number}: a control character {c!r} (U+{ord(c):04X})")
        if line == "---" and number > 1:
            break
    else:
        number = None
    if lines[0] != "---":
        raise HarnessError(f"{path}:1: the frontmatter does not open on line 1")
    if number is None:
        raise HarnessError(f"{path}:1: the frontmatter does not close with a `---` line")
    if number == len(lines):
        raise HarnessError(f"{path}:{number}: no newline after the closing `---`")
    meta, raw, open_list, list_line = {}, {}, None, 0
    for n, line in enumerate(lines[1:number - 1], 2):
        where = f"{path}:{n}"
        item = ITEM_LINE.fullmatch(line)
        if item:
            if open_list is None:
                raise HarnessError(f"{where}: a list item with no `key:` before it")
            value = item.group(1).strip(" ")
            if value == "":
                raise HarnessError(f"{where}: an empty list item")
            if value.startswith('"'):
                raise HarnessError(f"{where}: a list item is a plain string")
            meta[open_list].append(scalar(value, where))
            continue
        if open_list is not None and line[:1] in (" ", "\t"):
            raise HarnessError(f"{where}: not a `  - item` line")
        if open_list is not None and not meta[open_list]:
            raise HarnessError(f"{path}:{list_line}: a `key:` with no list item after it")
        open_list = None
        if line.lstrip(" ").startswith("#"):
            raise HarnessError(f"{where}: a comment line")
        if line[:1] in (" ", "\t"):
            raise HarnessError(f"{where}: a continuation line")
        m = KEY_LINE.fullmatch(line)
        if not m:
            raise HarnessError(f"{where}: not a `key: value` line")
        key, rest = m.group(1), m.group(2)
        if key not in KEYS:
            raise HarnessError(f"{where}: the key {key!r} is not one of {', '.join(sorted(KEYS))}")
        if key in meta:
            raise HarnessError(f"{where}: a duplicate key {key!r}")
        raw[key] = line
        if rest.strip(" ") == "":
            if key == BOOLEAN:
                raise HarnessError(f"{where}: {BOOLEAN} is true or false")
            if key not in LISTS:
                raise HarnessError(f"{where}: {key} takes a value, not a block list")
            meta[key], open_list, list_line = [], key, n
            continue
        if key in LISTS:
            raise HarnessError(f"{where}: {key} takes a block list of `  - item` lines")
        if not rest.startswith(" "):
            raise HarnessError(f"{where}: no space after the colon")
        value = scalar(rest.strip(" "), where)
        if key == BOOLEAN:
            if rest.strip(" ") not in ("true", "false"):
                raise HarnessError(f"{where}: {BOOLEAN} is true or false")
            value = rest.strip(" ") == "true"
        meta[key] = value
    if open_list is not None and not meta[open_list]:
        raise HarnessError(f"{path}:{list_line}: a `key:` with no list item after it")
    return Frontmatter(meta, raw, "\n".join(lines[number:]))


def check_values(meta, path):
    """Exit 2, naming `path`, on a `model` that is not a tier of TIERS, and on a `tools` item that is
    neither a tool of TOOLS nor `mcp/kaimon/<tool>`."""
    if "model" in meta and meta["model"] not in TIERS:
        raise HarnessError(f"{path}: the model {meta['model']!r} is not a tier; a `model:` is "
                           f"{', '.join(TIERS)}")
    for tool in meta.get("tools", []):
        if tool not in TOOLS and not MCP_TOOL.fullmatch(tool):
            raise HarnessError(f"{path}: the tool {tool!r} is not a neutral tool; a `tools:` item is "
                               f"{', '.join(TOOLS)} or {MCP}<tool>")


def check_skill(meta, path):
    """Exit 2, naming `path`, on a skill's `description` of more than DESCRIPTION_MAX characters or
    with a `<` or a `>`."""
    description = meta.get("description", "")
    if len(description) > DESCRIPTION_MAX:
        raise HarnessError(f"{path}: the description has {len(description):,} characters; a skill's "
                           f"description has at most {DESCRIPTION_MAX:,} characters")
    if "<" in description or ">" in description:
        raise HarnessError(f"{path}: the description holds a `<` or a `>`; a skill's description holds "
                           f"no `<` or `>`")


def parse_file(path, data=None):
    """The `Frontmatter` of the file at `path`, read with its line endings unchanged, or of `data`,
    its bytes, when given; its values checked by `check_values`, and by `check_skill` in a
    SKILL.md."""
    data = pathlib.Path(path).read_bytes() if data is None else data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        line = data[:e.start].count(b"\n") + 1
        raise HarnessError(f"{path}:{line}: not UTF-8") from None
    fm = parse(text, path)
    check_values(fm.meta, path)
    if pathlib.Path(path).name == "SKILL.md":
        check_skill(fm.meta, path)
    return fm


# (frontmatter lines, the line the error names); each is one rejected form of the spec.
REJECTED = [
    ("skills: [a, b]", 2),                       # a flow list
    ("description: |", 2),                       # a block scalar
    ("description: >", 2),                       # a folded block scalar
    ('description: "one"\n  two', 3),            # a continuation line
    ("# a comment", 2),                          # a comment line
    ("model: opus # the tier", 2),               # a plain value that holds ' #'
    ("model: &tier opus", 2),                    # an anchor
    ("model: *tier", 2),                         # an alias
    ("model: opus\nmodel: sonnet", 3),           # a duplicate key
    ("color: blue", 2),                          # a key outside the ten
    (r'description: "a \n b"', 2),               # an escape other than \\ and \"
    ('description: "open', 2),                   # an unterminated quote
    ("tools:\nmodel: opus", 2),                  # a `key:` with no list item after it
    ("tools:", 2),                               # the same, at the end
    ("disable-model-invocation: yes", 2),        # a boolean key with another value
    ('disable-model-invocation: "true"', 2),     # a quoted boolean is a string
    ("disable-model-invocation:\n  - true", 2),  # a boolean key with a block list
    ('tools:\n  - "Read"', 3),                   # a quoted list item
    ("tools:\n\t- Read", 3),                     # a tab-indented line under a `key:`
    ("tools:\n   - Read", 3),                    # an item indented by three spaces
    ("name: \tx", 2),                            # a tab at the start of a plain value
    ("name: x\t", 2),                            # a tab at the end of a plain value
    ("tools:\n  - \tRead", 3),                   # a tab at the start of an item
    ("tools:\n  - Read\t", 3),                   # a tab at the end of an item
    ("tools: Read, Bash", 2),                    # a list key with a scalar value
    ("skills: julia-structure", 2),              # the same, one skill
    ("description:\n  - x", 2),                  # a scalar key with a block list
]

ACCEPTED = [
    # (frontmatter lines, the parsed meta)
    ("name: x\nmodel: true", {"name": "x", "model": "true"}),
    ("disable-model-invocation: false", {"disable-model-invocation": False}),
    (r'description: "say \"hi\" \\ #1: ok"', {"description": 'say "hi" \\ #1: ok'}),
    ("tools:\n  - Read\n  - mcp__kaimon__ex\nomitClaudeMd: true",
     {"tools": ["Read", "mcp__kaimon__ex"], "omitClaudeMd": "true"}),
    ("permissionMode: plan", {"permissionMode": "plan"}),
    ("description: a\tb", {"description": "a\tb"}),
    ('description: "\ta\t"', {"description": "\ta\t"}),
    ("tools:\n  -  Read", {"tools": ["Read"]}),
    ("tools:\n  - Read  ", {"tools": ["Read"]}),
    ("name: a\N{NO-BREAK SPACE}b\N{ZERO WIDTH SPACE}c\N{ZERO WIDTH NO-BREAK SPACE}d",
     {"name": "a\N{NO-BREAK SPACE}b\N{ZERO WIDTH SPACE}c\N{ZERO WIDTH NO-BREAK SPACE}d"}),
]


def selftest():
    """The rejected and accepted forms, the file-level forms, and the sources on this machine."""
    total = wrong = 0

    def check(ok, label):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'}  frontmatter: {label}")

    for lines, line in REJECTED:
        try:
            parse(f"---\n{lines}\n---\nbody\n", "f.md")
            check(False, f"{lines!r} rejected")
        except HarnessError as e:
            check(str(e).startswith(f"f.md:{line}: "), f"{lines!r} rejected: {e}")
    for lines, meta in ACCEPTED:
        try:
            got = parse(f"---\n{lines}\n---\nbody\n", "f.md").meta
        except HarnessError as e:
            got = str(e)
        check(got == meta and all(type(got[k]) is type(meta[k]) for k in meta), f"{lines!r} -> {got!r}")
    # The file-level forms, written to a file and read by parse_file: (bytes, the error's start).
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "f.md"
        for data, start in [
            (b"\n---\nname: x\n---\n", "1: the frontmatter does not open on line 1"),
            (b"---\nname: x\n", "1: the frontmatter does not close"),
            (b"---\nname: x\ndescription: d\n", "1: the frontmatter does not close"),
            (b"---\nname: x\n---", "3: no newline after the closing `---`"),
            (b"---\nname: x\r\n---\n", "2: a control character '\\r' (U+000D)"),
            (b"---\r\nname: x\r\n---\r\n", "1: a control character '\\r' (U+000D)"),
            (b"---\nname: a\rb\n---\n", "2: a control character '\\r' (U+000D)"),
            (b"---\rname: x\r---\r", "1: a control character '\\r' (U+000D)"),
            (b"---\nname: a\x00b\n---\n", "2: a control character '\\x00' (U+0000)"),
            (b"---\ntools:\n  -\tRead\n---\n", "3: not a `  - item` line"),
            (b"---\nname: \xff\n---\n", "2: not UTF-8"),
            (b"---\ntools:\n  - \n---\n", "3: an empty list item"),
            (b"---\nname: a\x7fb\n---\n", "2: a control character '\\x7f' (U+007F)"),
            (b"---\xc2\x80\nname: x\n---\n", "1: a control character '\\x80' (U+0080)"),
            (b"---\nna\xc2\x85me: x\n---\n", "2: a control character '\\x85' (U+0085)"),
            (b"---\ntools:\n  - Re\xc2\x9fad\n---\n", "3: a control character '\\x9f' (U+009F)"),
            (b"---\nname: a\xe2\x80\xa8b\n---\n", "2: a control character '\\u2028' (U+2028)"),
            (b"---\nname: x\n---\xe2\x80\xa9\n---\n", "3: a control character '\\u2029' (U+2029)"),
            (b"\xef\xbb\xbf---\nname: x\n---\n", "1: the frontmatter does not open on line 1"),
        ]:
            f.write_bytes(data)
            try:
                parse_file(f)
                check(False, f"{data!r} rejected")
            except HarnessError as e:
                check(str(e).startswith(f"{f}:{start}"), f"{data!r} rejected: {e}")
    fm = parse('---\ndescription: "d"\n---\n\nbody\n', "f.md")
    check(fm.body == "\nbody\n" and fm.lines["description"] == 'description: "d"', "body and raw line")

    # The values of `model` and `tools` that parse_file reads: the neutral vocabulary, and nothing else.
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "f.md"
        for lines in ["model: opus", "model: sonnet", "model: haiku", "model: Large", 'model: "large "',
                      "tools:\n  - Read", "tools:\n  - Bash", "tools:\n  - bash", "tools:\n  - task",
                      "tools:\n  - mcp__kaimon__ex", "tools:\n  - mcp/kaimon/*", "tools:\n  - mcp/kaimon/",
                      "tools:\n  - mcp/github/get_issue", "tools:\n  - kaimon_ex", "tools:\n  - read\n  - WebFetch"]:
            f.write_text(f"---\n{lines}\n---\nbody\n")
            try:
                parse_file(f)
                check(False, f"the value {lines!r} rejected")
            except HarnessError as e:
                check(str(e).startswith(f"{f}: "), f"the value {lines!r} rejected, naming the file: {e}")
        for lines, meta in [("model: large", {"model": "large"}), ('model: "medium"', {"model": "medium"}),
                            ("model: small", {"model": "small"}),
                            ("tools:\n" + "".join(f"  - {t}\n" for t in TOOLS)
                             + "  - mcp/kaimon/ex\n  - mcp/kaimon/grep_code",
                             {"tools": [*TOOLS, "mcp/kaimon/ex", "mcp/kaimon/grep_code"]})]:
            f.write_text(f"---\n{lines}\n---\nbody\n")
            try:
                got = parse_file(f).meta
            except HarnessError as e:
                got = str(e)
            check(got == meta, f"the value {lines!r} -> {got!r}")

    # A skill's description, which parse_file checks in a SKILL.md: at most 1,024 characters, no `<`
    # or `>`. `harness install` reads each skill through parse_file, in the Claude adapter's
    # render_source.
    from . import frontends

    render = frontends.adapter("claude").render_source
    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "a-skill" / "SKILL.md"
        f.parent.mkdir()
        for description, rule in [("x" * 1024, None), ("\N{GREEK CAPITAL LETTER OMEGA}" * 1024, None),
                                  ("x" * 1025, "at most 1,024 characters"),
                                  ("a <tag> b", "no `<` or `>`"), ("a -> b", "no `<` or `>`"),
                                  ("a < b", "no `<` or `>`")]:
            data = f'---\nname: a-skill\ndescription: "{description}"\n---\nbody\n'.encode("utf-8")
            f.write_bytes(data)
            for label, call in [("parse_file", lambda: parse_file(f)),
                                ("install's render_source", lambda: render(f, data, {}))]:
                try:
                    call()
                    got = None
                except HarnessError as e:
                    got = str(e)
                ok = got is None if rule is None else (got is not None and got.startswith(f"{f}: ") and rule in got)
                check(ok, f"{label} of a SKILL.md whose description is {description[:12]!r}… of "
                          f"{len(description)} characters: {got or 'accepted'}")
        # The same description in an agent is not a skill's.
        g = pathlib.Path(tmp) / "agent.md"
        g.write_text(f'---\nname: agent\ndescription: "{"x" * 1025} <x>"\n---\nbody\n')
        try:
            got = parse_file(g).meta["description"][-3:]
        except HarnessError as e:
            got = str(e)
        check(got == "<x>", f"an agent's description of 1,029 characters with `<` parses: {got!r}")

    # The sources in agents/ and skills/: every agent and every curated SKILL.md parses, a skill's
    # description within its rule.
    from . import REPO, sources as neutral

    skills = REPO / "skills"
    sources = neutral.listing()
    agents = [f for f in sources if f.parent.name == "agents"]
    inside = [f for f in sources if f.is_relative_to(REPO / "agents") or f.is_relative_to(skills)]
    check(len(agents) == 20 and inside == sources,
          f"the sources are the 20 agents of agents/ and the curated skills of skills/: {len(agents)} agents, "
          f"{[str(f) for f in sources if f not in inside]} outside")
    bad = []
    for f in sources:
        try:
            parse_file(f)
        except HarnessError as e:
            bad.append(str(e))
    check(sources and not bad, f"the {len(sources)} agents and curated skills of agents/ and skills/ parse" +
          "".join(f"\n       {b}" for b in bad))
    # No frontmatter line of a source holds a frontend's name: a list item with a capital, or `mcp__`.
    frontend = [f"{f}:{n}" for f in sources
                for n, line in enumerate(f.read_text().split("\n---\n", 1)[0].split("\n"), 1)
                if re.match(r"  - [A-Z]", line) or "mcp__" in line]
    check(sources and not frontend, f"no frontmatter of agents/ and skills/ names a frontend's tool: {frontend}")
    return total, wrong
