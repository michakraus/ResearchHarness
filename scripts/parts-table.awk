# Extract the parts table and the file-collision map from a task file.
#
# The `build-part` skill runs this instead of reading the task file. The largest
# file in the queue is about 33 000 tokens; this output is about 200.
#
#   awk -f parts-table.awk "Tasks/<file>.md"
#
# Two record types, tab separated, in the file's own order:
#
#   PART       part  repository  sections  tier  state
#   COLLISION  repository  file  parts
#
# **The columns are mapped by name, never by position.** The tables in the queue
# carry three different column sets — with and without `repository`, with and
# without `sections`, and one with no `tier` at all — so a positional reader
# silently returns the wrong cell. A column the table does not have comes back
# empty. An empty `tier` is a real answer: that part has no tier assigned.
#
# A table without a `part` column, or a collision map without a `parts` column,
# is not one of these tables and is skipped. That is what keeps an unrelated
# table inside the same section from being read as parts.
#
# A file with no "## Parts" section produces no output. That is the answer "this
# task is not decomposed", not a failure.
#
# Markdown emphasis and code ticks are stripped from every cell, so a part reads
# as `A` rather than `**A**`. The state cell is passed through whole: it carries
# the pull-request link once a part is built.
#
# The source file is never modified. Output goes to stdout.

BEGIN { BAR = sprintf("%c", 1) }

function trim(s)  { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
function clean(s) { gsub(/\*\*/, "", s); gsub(/`/, "", s); gsub(BAR, "|", s)
                    return trim(s) }

# Hide a "|" that sits inside a code span, so it is not read as a column break.
# `Tasks/Rewrite the reduced basis packages.md` writes a cell as ``max|r|``, and
# a plain split on "|" shifts every later column of that row by two.
function mask(s,   i, c, incode, out) {
    if (index(s, "`") == 0) return s
    incode = 0
    out = ""
    for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (c == "`") incode = !incode
        else if (c == "|" && incode) c = BAR
        out = out c
    }
    return out
}

# Read a row as the header of the table that follows, and index it by name.
function map_header(line,   n, f, i, name) {
    split("", col)
    n = split(mask(line), f, "|")
    for (i = 2; i < n; i++) {
        name = tolower(clean(f[i]))
        if (name != "") col[name] = i
    }
    have = 1
}

function cell(name,   i) {
    if (!(name in col)) return ""
    i = col[name]
    return (i <= nf) ? clean(fld[i]) : ""
}

# --- section tracking ---------------------------------------------------------
# "### File collisions" sits inside "## Parts", so it is tested first. Every
# other heading ends the region — "## Parts index" is prose about the parts, not
# a table to parse.

/^## Parts[ \t]*$/     { mode = "parts";      have = 0; next }
/^### File collisions/ { mode = "collisions"; have = 0; next }
/^#/                   { mode = "";           have = 0; next }

mode == "" { next }

# A blank line ends a table. The region can hold more than one, so the column
# map is rebuilt from each table's own header rather than carried across.
/^[ \t]*$/ { have = 0; next }

# --- table rows ---------------------------------------------------------------

$0 !~ /^[ \t]*\|/                  { next }   # not a table row
$0 ~ /^[ \t]*\|[ \t:|-]+\|[ \t]*$/ { next }   # the |:--|:--| separator

have == 0 { map_header($0); next }            # the table's header row

{
    nf = split(mask($0), fld, "|")

    if (mode == "parts") {
        if (!("part" in col)) next
        printf "PART\t%s\t%s\t%s\t%s\t%s\n",
               cell("part"), cell("repository"), cell("sections"),
               cell("tier"), cell("state")
    } else {
        if (!("parts" in col)) next
        printf "COLLISION\t%s\t%s\t%s\n",
               cell("repository"), cell("file"), cell("parts")
    }
}
