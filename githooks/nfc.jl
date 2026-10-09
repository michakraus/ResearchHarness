#!/usr/bin/env julia
#
# Report or apply Unicode NFC normalisation to source files.
#
#   julia --startup-file=no nfc.jl                     # check every tracked source file here
#   julia --startup-file=no nfc.jl --apply             # rewrite them
#   julia --startup-file=no nfc.jl a.jl b.md           # check just these paths
#   julia --startup-file=no nfc.jl --apply src/x.jl    # rewrite just this one
#
# Exit status is 0 when everything checked is already NFC, 1 when something is not (check mode)
# or when a file could not be read. `--apply` exits 0 once it has rewritten what it found.
#
# Much of this tree is NFD-normalised, inherited from macOS: `ẋ`, `ṗ`, `ū`, `ḡ` stored as a base
# letter plus a combining mark. Julia's parser normalises identifiers to NFC, so an NFD source
# file compiles to byte-identical symbols and there is no runtime difference to recover. The cost
# is entirely in tooling: every byte-matching tool -- grep, ripgrep, an editor's search, an
# agent's string replacement, Documenter's doctest comparison -- sees bytes, and a pattern typed
# in NFC matches nothing in an NFD file.
#
# String literals are the one place where normalising changes behaviour, because they are *not*
# parser-normalised: in an NFD file `:ẋ` is normalised but `Symbol("ẋ")` is not, so the two
# compare unequal while looking identical on screen. Check what consumes a changed literal --
# a doctest, a `sprint(show, …)` assertion, a symbol comparison -- before applying this to a file
# that has any.
#
# Not every combining mark composes. `q̇`, `v̄` and `f̄` have no precomposed codepoint, so they
# remain two codepoints in NFC and a file containing only those is already normalised.
#
# Tracked files only when no paths are given, and **every** tracked file rather than a list of
# extensions. Anything that is valid UTF-8 is a candidate and anything that is not is skipped
# silently, so an image costs nothing and a text file cannot be missed for want of a suffix.
#
# An extension list such as `.jl`, `.md`, `.toml` misses `docs/src/*.jmd` -- Weave documents that
# `docs/make.jl` executes. A whitelist only ever covers the file types somebody thought of.
#
# It does *not* exclude `obsolete/`, `legacy/` or `prototyping/` the way `format-tree.jl` does.
# Those are tracked files and the invariant applies to them, but they are also work nobody is
# reviewing -- name the paths explicitly when a change is meant to stay surgical.
#
# A path given explicitly that is not valid UTF-8 *is* reported, and exits 1: naming a file and
# having it silently skipped is the failure this whole tool exists to prevent.

using Unicode

const APPLY = "--apply" in ARGS
const PATHS = filter(a -> !startswith(a, "--"), ARGS)

function targets()
    isempty(PATHS) || return PATHS
    out = readchomp(`git ls-files`)
    isempty(out) ? String[] : split(out, '\n')
end

changed = String[]
unreadable = String[]

for path in targets()
    isfile(path) || continue
    source = try
        read(path, String)
    catch
        push!(unreadable, path)
        continue
    end
    if !isvalid(source)
        isempty(PATHS) || push!(unreadable, path)
        continue
    end
    normalised = Unicode.normalize(source, :NFC)
    source == normalised && continue
    push!(changed, path)
    APPLY && write(path, normalised)
end

for path in unreadable
    println(stderr, "not valid UTF-8, skipped: ", path)
end

if !isempty(changed)
    verb = APPLY ? "normalised" : "not NFC"
    println(stderr, verb, ":\n", join("    " .* changed, "\n"))
end

exit(isempty(unreadable) && (APPLY || isempty(changed)) ? 0 : 1)
