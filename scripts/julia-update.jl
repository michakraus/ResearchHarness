#!/usr/bin/env julia
#
# Keep the Julia installation, the default environments and the Kaimon MCP server current.
#
# Four steps, in this order, because each one depends on the one before:
#
# 1. `juliaup update`. It installs the newest release of every channel and deletes each release
#    that no channel names any more — including, possibly, the one this process and the Kaimon
#    server run from. A running process keeps working from a deleted release, but nothing new can
#    start from it. So every later step runs as a subprocess of the juliaup launcher, never of
#    `Sys.BINDIR`.
# 2. `Pkg.update()` in the default environment `@v#.#` of every `X.Y` channel. The channel
#    `release`, `nightly` and a pinned patch channel such as `1.12.6` are skipped: the first two
#    duplicate or have no stable environment, and a patch channel shares `@v1.12` with `1.12`.
#    Then `Pkg.update()` in the installed harness environment, when it exists.
# 3. `Pkg.Apps.update("Kaimon")`, and a check that Kaimon still loads under the server's load path.
#    An update reports a precompilation failure and still returns, so the load is the check.
# 4. The server check. If the Kaimon server runs from a Julia binary that no longer exists, it
#    cannot start a session and never recovers, so the job restarts it. That stops every live
#    session, which have lost nothing that a restart could keep. Any other reason for a restart —
#    a new Kaimon version, a new default release — is reported and left to a person.
#
# The job runs on macOS under launchd and on Linux under `systemd --user`. What differs between the
# two — the service manager, the restart, the notifier, the log and how the server's binary is
# read — is in one branch on the system below. The tools are found on the PATH, which the job's
# plist or unit fixes to directories that no session can write.
#
# The app environment at ~/.julia/environments/apps/Kaimon is a derived artefact: every upgrade
# regenerates its Project.toml from Kaimon's own, so nothing added there survives. Tools reach
# JuliaFormatter and Aqua through a session, whose load path carries @v#.#.
#
# Every Kaimon update reinstalls the `kaimon` shim, and Pkg pins one absolute juliaup release
# inside it. The Kaimon LaunchAgent overrides that with JULIA_APPS_JULIA_CMD, so
# only a bare shim call reads it.
#
# A failure or a due restart also sends a desktop notification, because nobody reads the log.

using Dates
using TOML

const JULIA = joinpath(homedir(), ".juliaup", "bin", "julia")
const JULIAUP = joinpath(homedir(), ".juliaup", "bin", "juliaup")
const JULIAUP_JSON = joinpath(homedir(), ".julia", "juliaup", "juliaup.json")
const APP = joinpath(homedir(), ".julia", "environments", "apps", "Kaimon")
# The harness's Julia environment, installed by `harness install --apply`.
const HARNESS_ENV = get(ENV, "RESEARCH_HARNESS_JULIA",
                        joinpath(homedir(), ".local", "share", "research-harness", "julia"))
const KAIMON_PORT = 2828

"""The path of the tool `name` on the PATH, or an error that names it."""
function tool(name)
    path = Sys.which(name)
    path === nothing && error("no $name on the PATH")
    return path
end

# The system's own parts, in this one branch: the service manager, the restart of the Kaimon
# server and the line that names it, the log, the notifier, and how the server's binary is read.
if Sys.isapple()
    # The Kaimon job's label is `<launchd_prefix>.kaimon`, from the private profile, as in
    # launchagents/kaimon.plist.
    const PROFILE = get(ENV, "RESEARCH_HARNESS_PROFILE",
                        joinpath(homedir(), ".config", "research-harness", "profile.toml"))
    const KAIMON_JOB = TOML.parsefile(PROFILE)["launchd_prefix"] * ".kaimon"
    const SERVICE_MANAGER = "launchd"
    const RESTART_HINT = "launchctl kickstart -k gui/\$(id -u)/$KAIMON_JOB"
    const LOG = "~/Library/Logs/julia-update/"
    const NOTIFIER = "osascript"
    restart_cmd() = `$(tool("launchctl")) kickstart -k gui/$(Libc.getuid())/$KAIMON_JOB`
    notify_cmd(notifier, message) =
        `$notifier -e $("display notification \"$message\" with title \"julia-update\"")`
    """
    The binary of process `pid` from `ps -o comm=`, which prints its full path on macOS, or
    `:ended` when the process has ended.
    """
    function binary_of(pid)
        comm = readchomp(ignorestatus(`$(tool("ps")) -o comm= -p $pid`))
        return isempty(comm) ? :ended : comm
    end
elseif Sys.islinux()
    const SERVICE_MANAGER = "systemd"
    const RESTART_HINT = "systemctl --user restart kaimon.service"
    const LOG = "journalctl --user -u julia-update.service"
    const NOTIFIER = "notify-send"
    restart_cmd() = `$(tool("systemctl")) --user restart kaimon.service`
    notify_cmd(notifier, message) = `$notifier julia-update $message`
    """
    The binary of process `pid` from `/proc/<pid>/exe`, or `:ended` when the process has ended.
    `ps -o comm=` prints only a 15-character name on Linux. The link of a deleted binary ends in
    ` (deleted)`, which is removed, so a binary written again at the same path exists.
    """
    function binary_of(pid)
        exe = try
            readlink("/proc/$pid/exe")
        catch e
            e isa Base.IOError || rethrow()
            return :ended
        end
        return chopsuffix(exe, " (deleted)")
    end
else
    error("julia-update.jl runs on macOS and Linux, not on $(Sys.KERNEL)")
end

"""
Run `cmd` with its output in the log, and return whether it succeeded.

Pkg reports on `stderr`, so the subprocess's `stderr` joins `stdout` and the log reads in order.
Julia buffers `stdout` when launchd points it at a file, so each header is flushed before the
subprocess writes to the same file.
"""
function step(name, cmd)
    println("--- ", name)
    flush(stdout)
    ok = success(run(pipeline(ignorestatus(cmd); stderr = stdout); wait = true))
    ok || println("FAILED: ", name)
    return ok
end

"""
The `X.Y` channels juliaup has installed.

`juliaup.json` is JSON and Base has no JSON parser, so the channel names are matched as the keys
`"X.Y": {`. A release key is `"1.13.1+0.aarch64…"` and never ends its quote after `X.Y`.
"""
function minor_channels()
    json = read(JULIAUP_JSON, String)
    channels = unique(m[1] for m in eachmatch(r"\"(\d+\.\d+)\"\s*:\s*\{", json))
    return sort(channels; by = VersionNumber)
end

"""The installed Kaimon version, read from the app project."""
function kaimon_version()
    project = joinpath(APP, "Project.toml")
    isfile(project) || return nothing
    return get(TOML.parsefile(project), "version", nothing)
end

"""
The Julia binary of the process that listens on the Kaimon port: its path, `:none` when no
process listens, `:ended` when the process ended before its binary was read, or `:nolsof` when no
`lsof` is on the PATH. A missing `lsof` is never "no server".
"""
function server_julia()
    lsof = Sys.which("lsof")
    lsof === nothing && return :nolsof
    pids = split(readchomp(ignorestatus(`$lsof -nP -iTCP:$KAIMON_PORT -sTCP:LISTEN -t`)))
    isempty(pids) && return :none
    return binary_of(first(pids))
end

"""The Julia binary that the launcher resolves for the default channel."""
default_julia() = joinpath(readchomp(`$JULIA --startup-file=no -e 'print(Sys.BINDIR)'`), "julia")

"""
Show a desktop notification, or only a log line when the notifier is not on the PATH.
`Base.notify` is a different function, hence the name.
"""
function alert(message)
    notifier = Sys.which(NOTIFIER)
    if notifier === nothing
        println("No $NOTIFIER on the PATH, so no notification: ", message)
    else
        run(ignorestatus(notify_cmd(notifier, message)))
    end
    return nothing
end

function main()
    println("=== julia-update ", Dates.format(now(), "yyyy-mm-dd HH:MM:SS"), " ===")
    failures = String[]

    step("juliaup update", `$JULIAUP update`) || push!(failures, "juliaup update")

    for channel in minor_channels()
        name = "Pkg.update() in @v$channel"
        cmd = `$JULIA +$channel --startup-file=no -e 'using Pkg; Pkg.update()'`
        step(name, cmd) || push!(failures, name)
    end

    # The installed copy of the harness environment, never the checkout's Project.toml: this job
    # runs unsandboxed, and a session can edit the checkout.
    if isfile(joinpath(HARNESS_ENV, "Project.toml"))
        name = "Pkg.update() in $HARNESS_ENV"
        cmd = `$JULIA --startup-file=no --project=$HARNESS_ENV -e 'using Pkg; Pkg.update()'`
        step(name, cmd) || push!(failures, name)
    end

    before = kaimon_version()
    before === nothing && error("no Kaimon app project at $APP")
    update = `$JULIA --startup-file=no -e 'using Pkg; Pkg.Apps.update("Kaimon")'`
    step("Pkg.Apps.update(\"Kaimon\")", update) || push!(failures, "Kaimon update")
    after = kaimon_version()
    loads = `$JULIA --startup-file=no -e 'using Kaimon'`
    if !step("using Kaimon", setenv(loads, merge(ENV, Dict("JULIA_LOAD_PATH" => APP))))
        push!(failures, "Kaimon $after does not load; reinstall with Pkg.Apps.add(\"Kaimon\")")
    end

    println("--- server check")
    server = server_julia()
    due = String[]
    if server === :nolsof
        println("FAILED: cannot read the server, because no lsof is on the PATH.")
        push!(failures, "cannot read the server")
    elseif server === :none
        println("No process listens on port $KAIMON_PORT; $SERVICE_MANAGER restarts the server.")
    elseif server === :ended
        println("The process on port $KAIMON_PORT ended before its binary was read; ",
                "$SERVICE_MANAGER restarts the server.")
    elseif !isfile(server)
        println("The server ran from $server, which juliaup deleted.")
        if step("restart the server", restart_cmd())
            println("RESTARTED: the server.")
        else
            push!(failures, "restart of the server")
        end
    else
        before == after || push!(due, "Kaimon $before -> $after; the server runs $before")
        server == default_julia() || push!(due, "the server runs $server, not the default release")
    end

    if isempty(due)
        println("Kaimon $after. No restart due.")
    else
        println("RESTART DUE: ", join(due, "; "), ". ",
            "Run: $RESTART_HINT — it stops every live session. ",
            "A new Kaimon version can advertise tools that ~/Research/.kaimon/tools.json has ",
            "never seen, so read the tool list after the restart.")
        alert("Kaimon restart due")
    end

    if !isempty(failures)
        println("FAILED: ", join(failures, "; "))
        alert("$(length(failures)) step(s) failed; see $LOG")
        return 1
    end
    return 0
end

exit(main())
