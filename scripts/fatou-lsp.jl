#!/usr/bin/env julia
#
# A minimal LSP client for `fatou lsp`, shared by `julia-methods.jl` and `probe-fatou-lsp.jl`.
#
# Fatou is the only static tool here that lists every method of a Julia name separately, including
# a module-qualified definition such as `Base.length(x::Problem) = …`. It never runs Julia, so it
# works on a package that does not load. Measurements and the
# comparison against the code graph are in `Environment/Notes/Helpers-and-MCPs.md`.
#
# Two things about driving it that cost an afternoon each:
#
#   * LSP headers end with CRLF and `readline` strips only the LF, so the blank separator line
#     arrives as "\r". A bare `isempty` test never fires, the reader eats the body as headers, and
#     the client hangs rather than failing.
#   * Stopping the server needs the LSP `shutdown`/`exit` handshake, and **`kill` is not a
#     substitute**. An npm install puts a node wrapper on `PATH` that spawns the real binary as a
#     grandchild (`fatou_binary` finds the binary itself): `close` leaves both running, and
#     `kill` reaches the wrapper while orphaning the binary. Sixteen accumulated at about 1 GB
#     during one afternoon, and the "fix" that followed was verified with an unguarded
#     `ps | grep -c` — which reports 0 when `ps` itself fails, so it read as clean while eight more
#     piled up. `lsp_close` returns whether it worked; do not ignore it, and never treat a failed
#     `ps` as a zero.

# The harness's Julia environment, which `harness install --apply` instantiates from
# Project.toml; first in LOAD_PATH, so no caller needs `--project`.
let env = get(ENV, "RESEARCH_HARNESS_JULIA", joinpath(homedir(), ".local", "share", "research-harness", "julia"))
    env in LOAD_PATH || pushfirst!(LOAD_PATH, env)
end

module FatouLSP

using JSON

export lsp_open, lsp_close, initialize, did_open, document_symbol, references, flatten

const CL = "Content-Length: "

function send(io, id, method, params)
    body = JSON.json(isnothing(id) ?
                     Dict("jsonrpc" => "2.0", "method" => method, "params" => params) :
                     Dict("jsonrpc" => "2.0", "id" => id, "method" => method, "params" => params))
    write(io, CL, string(sizeof(body)), "\r\n\r\n", body)
    flush(io)
end

"""
    recv(io; timeout = 20.0)

One LSP message: headers, blank line, then exactly `Content-Length` bytes. Returns `nothing` on
timeout instead of blocking — a notification produces no reply at all, and a blocking read there
hangs the caller.
"""
function recv(io; timeout = 20.0)
    result = Ref{Any}(nothing)
    task = @async begin
        len = 0
        while true
            line = rstrip(readline(io), '\r')   # see the CRLF note in this file's header
            isempty(line) && break
            startswith(line, CL) && (len = parse(Int, strip(line[(length(CL) + 1):end])))
        end
        result[] = len == 0 ? nothing : JSON.parse(String(read(io, len)))
    end
    timedwait(() -> istaskdone(task), timeout) === :ok || return nothing
    return result[]
end

"Await the response carrying this `id`, discarding notifications that arrive first."
function await(io, id; timeout = 20.0)
    for _ in 1:200
        msg = recv(io; timeout)
        msg === nothing && return nothing
        get(msg, "id", nothing) == id && return msg
    end
    return nothing
end

"""
    fatou_binary() -> String

The **real** fatou executable. The Homebrew formula (`jolars/tap`) puts it on `PATH` directly.

The npm package `fatou-cli` instead puts a node script on `PATH`, which spawns the platform binary
as a child. Driving the wrapper means the LSP server is a *grandchild*: `process_running` then
watches the wrapper, which exits on cue whatever the server does, and `kill` reaches the wrapper
while orphaning the server.
Measured 2026-09-15 — five servers leaked from one probe run while it reported all five stopped,
because the report could not see them.

Spawning the binary directly makes `io` the server itself, so both of those become truthful.
`FATOU_LSP_BIN` overrides the search.
"""
function fatou_binary()
    haskey(ENV, "FATOU_LSP_BIN") && return ENV["FATOU_LSP_BIN"]
    wrapper = Sys.which("fatou")
    if wrapper !== nothing
        endswith(realpath(wrapper), ".js") || return wrapper   # a native binary, as from Homebrew
        prefix = dirname(dirname(wrapper))          # /opt/homebrew/bin/fatou -> /opt/homebrew
        pattern = joinpath(prefix, "lib", "node_modules", "fatou-cli",
            "node_modules", "@fatou-cli")
        if isdir(pattern)
            for arch in readdir(pattern)
                candidate = joinpath(pattern, arch, "fatou")
                isfile(candidate) && return candidate
            end
        end
    end
    @warn """
        Could not find the platform fatou binary; falling back to the `fatou` wrapper on PATH.
        The wrapper spawns the server as a grandchild, so it WILL be orphaned on close and this
        script cannot detect that. Set FATOU_LSP_BIN to the real binary. Check for strays with
        `lsof -c fatou -t`, which works here where `ps` and `pgrep` do not.
        """
    return "fatou"
end

lsp_open() = open(`$(fatou_binary()) lsp`, "r+")

const SHUTDOWN_ID = 99

"""
    lsp_close(io; timeout = 5.0) -> Bool

Stop the server, and return whether it actually stopped.

**The protocol handshake is the only reliable route, and `kill` is not a fallback for it.**
When `io` drives the npm node wrapper, the real binary is a **grandchild**.
`close(io)` leaves both running; `kill(io)` reaches the wrapper and **orphans the binary**. So the
server has to be asked to exit: `shutdown`, wait for its acknowledgement — otherwise `exit` races an
in-flight request — then `exit`.

Nothing here swallows a failure. If the process is still running at the end you get a warning and a
`false`, because the alternative is a silent leak: sixteen of these accumulated at about 1 GB during
one afternoon, and a later "verification" reported zero because `ps` had failed and an unguarded
`grep -c` turned that into a count.
"""
function lsp_close(io; timeout = 5.0)
    stopped = false
    try
        send(io, SHUTDOWN_ID, "shutdown", Dict())
        await(io, SHUTDOWN_ID; timeout)
        send(io, nothing, "exit", Dict())
        stopped = timedwait(() -> !process_running(io), timeout) === :ok
    catch e
        @warn "fatou lsp: shutdown handshake failed" exception = e
    end

    if !stopped
        try
            kill(io)
            stopped = timedwait(() -> !process_running(io), 3.0) === :ok
        catch e
            @warn "fatou lsp: kill failed" exception = e
        end
    end

    try
        close(io)
    catch
    end

    stopped || @warn """
        fatou lsp did not stop, and the real binary may now be orphaned — `kill` reaches only the
        node wrapper. Check and clear it by hand:
            ps -ax -o pid=,args= | grep '[f]atou lsp'
            pkill -f 'fatou lsp'
        A `ps` that fails prints nothing; `grep -c` then reports 0, which is UNKNOWN and not zero.
        """
    return stopped
end

"Handshake. Returns the server's advertised capabilities."
function initialize(io, root::String)
    send(io, 1, "initialize", Dict(
        "processId" => getpid(),
        "rootUri" => "file://" * root,
        "capabilities" => Dict("textDocument" => Dict("documentSymbol" =>
            Dict("hierarchicalDocumentSymbolSupport" => true)))))
    reply = await(io, 1)
    send(io, nothing, "initialized", Dict())
    return get(get(something(reply, Dict()), "result", Dict()), "capabilities", Dict())
end

did_open(io, path::String) = send(io, nothing, "textDocument/didOpen",
    Dict("textDocument" => Dict("uri" => "file://" * path, "languageId" => "julia",
        "version" => 1, "text" => read(path, String))))

"Every symbol in a DocumentSymbol tree, flattened."
function flatten(syms, out = Dict{String,Any}[])
    for s in something(syms, [])
        push!(out, s)
        haskey(s, "children") && s["children"] !== nothing && flatten(s["children"], out)
    end
    return out
end

"""
    document_symbol(io, path; id) -> Vector{Dict}

Every symbol Fatou finds in one file, flattened. This is the request that resolves per method:
`detail` carries the signature, and a qualified definition keeps its `Mod.name`.

The result holds struct fields, structs, constants, abstract types, strings and modules too, not
only methods. Keep LSP `SymbolKind` 12 (function) for methods, never 8 (field): a field named like
a function counts as a method otherwise. Only kind 12 carries `detail`: every kind-12 symbol has
one, and no field, struct, constant, abstract type, string or module has.
"""
function document_symbol(io, path::String; id::Int = 2)
    did_open(io, path)
    send(io, id, "textDocument/documentSymbol", Dict("textDocument" => Dict("uri" => "file://" * path)))
    reply = await(io, id)
    reply === nothing && return Dict{String,Any}[]
    return flatten(get(reply, "result", []))
end

"""
    references(io, path, line, col; id) -> Vector{String}

`textDocument/references` at a 1-based position, as `file:line`. **Fatou answers this only for an
unqualified name**: on a qualified definition it returns an empty list at any workspace root, while
the same request on an unqualified one returns every use in the package. Treat an empty result as
unknown.
"""
function references(io, path::String, line::Int, col::Int; id::Int = 3)
    did_open(io, path)
    send(io, id, "textDocument/references", Dict(
        "textDocument" => Dict("uri" => "file://" * path),
        "position" => Dict("line" => line - 1, "character" => col - 1),
        "context" => Dict("includeDeclaration" => true)))
    reply = await(io, id)
    reply === nothing && return String[]
    return [string(replace(l["uri"], "file://" => ""), ":", l["range"]["start"]["line"] + 1)
            for l in something(get(reply, "result", []), [])]
end

end # module
