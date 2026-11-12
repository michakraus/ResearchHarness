# The probes of the Kaimon server under its sandbox, sandbox/daemon.toml rendered by
# `harness render sandbox/kaimon.sb` on macOS and `harness render sandbox/kaimon.bwrap` on Linux.
# A session runs them through Kaimon's `ex` after `harness setup` has written the profile or the
# arguments and the server has restarted under them:
#
#     include(joinpath(homedir(), "Research", "Harness", "sandbox", "probe-daemon.jl"))
#     ProbeDaemon.run_all()
#
# On Linux a person can run them from a terminal under the job's `bwrap`, too:
#
#     ~/.local/bin/jobbox kaimon ~/.juliaup/bin/julia --startup-file=no -e 'include(joinpath(homedir(),
#         "Research", "Harness", "sandbox", "probe-daemon.jl")); display(ProbeDaemon.run_all())'
#
# Each probe returns `:allowed`, or the name of the exception class that the attempt raised, as a
# Symbol: never a file's content. `run_all` returns one `name => result` pair per probe of this
# system (`probe_names`), the positive probes first. The sandbox is at work when every positive
# probe gives `:allowed`, `metal`, `connect_loopback` and `pkg_offline` included on macOS, and
# every negative probe gives the name of an exception class: `:SystemError` or an `IOError` class;
# on macOS `lsopen` and `appleevent` `:ProcessFailedException`, `connect_remote` an `IOError` class
# and `resolve_name` `:DNSError`; on Linux, where the job sees no /run/user/<uid>, `systemd_run`
# and `session_bus` `:ProcessFailedException`. A write probe deletes what it created; the probe of
# ~/.zshrc opens the file to append and writes nothing. `connect_loopback` connects to Kaimon's
# own port, 127.0.0.1:2828, and `connect_remote` to 1.1.1.1:443, an address that answers, so a
# profile that lets it through gives `:allowed` and not a timeout.
#
# `OPEN_GAPS` names the negative probes that the sandbox does not stop, which report `:allowed`
# under it: none on macOS; on Linux, none recorded. The event of `appleevent` is
# `name of startup disk` of the Finder, because AppleScript answers `name` of an application from
# the script itself and sends no event.
#
# Each probe takes the home directory as its argument, so that `harness test` runs every probe
# against a scratch tree (lib/harness/jobsandbox.py).
module ProbeDaemon

using Sockets: Sockets, @ip_str

# The UUID of Metal.jl in the General registry.
const METAL = Base.PkgId(Base.UUID("dde4c033-4e86-420c-a63e-0dd931031962"), "Metal")

"""Raised by `metal` when `Metal.functional()` is false."""
struct NotFunctional <: Exception end

"""`:allowed` when `f()` returns, else the name of the class of the exception that it throws."""
function attempt(f)
    try
        f()
        return :allowed
    catch e
        return nameof(typeof(e))
    end
end

"""The first regular file of `dir`, in the order of `readdir`; an error when it holds none."""
function first_file(dir)
    for name in readdir(dir)
        path = joinpath(dir, name)
        isfile(path) && return path
    end
    error("$dir holds no file")
end

"""Read `path` whole and drop its bytes."""
read_only(path) = (read(path); nothing)

"""Create the file `path`, then delete it."""
function create_delete(path)
    write(path, "probe\n")
    rm(path)
    return nothing
end

"""A name below a directory that no other probe run uses at the same time."""
scratch_name() = "probe-daemon-$(getpid())-$(time_ns())"

# ----------------------------------------------------------------------- positive probes ----

read_research(home = homedir()) = attempt(() -> read_only(first_file(joinpath(home, "Research"))))
write_research(home = homedir()) = attempt(() -> create_delete(joinpath(home, "Research", scratch_name())))
write_tempdir(home = homedir()) = attempt(() -> create_delete(joinpath(tempdir(), scratch_name())))
list_packages(home = homedir()) = attempt(() -> readdir(joinpath(home, ".julia", "packages")))

"""
`Metal.functional()`, with `module_of()` the Metal module: `NotFunctional` when it is false. The
module is loaded after this function was compiled, so its binding is read in the latest world.
"""
function metal(home = homedir(); module_of = () -> Base.require(METAL))
    return attempt() do
        m = module_of()
        Base.invokelatest(() -> getfield(m, :functional)()) || throw(NotFunctional())
    end
end

"""A TCP connection to `address` on `port`, closed at once."""
connect_tcp(address, port) = close(Sockets.connect(address, port))

"""A TCP connection to Kaimon's own port on the loopback address."""
connect_loopback(home = homedir(); address = ip"127.0.0.1", port = 2828) = attempt(() -> connect_tcp(address, port))
"""Pkg starts offline: `JULIA_PKG_OFFLINE` is `true`, which the plist of the server sets."""
pkg_offline(home = homedir()) = attempt(() -> ENV["JULIA_PKG_OFFLINE"] == "true" || error("JULIA_PKG_OFFLINE is not true"))

# ----------------------------------------------------------------------- negative probes ----

function read_ssh(home = homedir())
    return attempt() do
        key = joinpath(home, ".ssh", "id_ed25519")
        read_only(isfile(key) ? key : first_file(joinpath(home, ".ssh")))
    end
end
read_claude_json(home = homedir()) = attempt(() -> read_only(joinpath(home, ".claude.json")))
read_documents(home = homedir()) = attempt(() -> read_only(first_file(joinpath(home, "Documents"))))
read_gh_hosts(home = homedir()) = attempt(() -> read_only(joinpath(home, ".config", "gh", "hosts.yml")))
write_zshrc(home = homedir()) = attempt(() -> open(_ -> nothing, joinpath(home, ".zshrc"), "a"))
function write_git_hooks(home = homedir(); repository = joinpath(home, "Research", "Harness"))
    return attempt(() -> create_delete(joinpath(repository, ".git", "hooks", scratch_name())))
end
write_julia_config(home = homedir()) = attempt(() -> create_delete(joinpath(home, ".julia", "config", "x")))

"""`open -a TextEdit`, through Launch Services."""
lsopen(home = homedir(); command = `open -a TextEdit`) = attempt(() -> run(command))
"""An Apple Event to the Finder."""
function appleevent(home = homedir(); command = `osascript -e 'tell app "Finder" to get name of startup disk'`)
    return attempt(() -> run(pipeline(command; stdout = devnull)))
end
"""A transient unit of the user's service manager, which would run outside `bwrap`."""
function systemd_run(home = homedir(); command = `systemd-run --user --quiet true`)
    return attempt(() -> run(pipeline(command; stdout = devnull, stderr = devnull)))
end
"""The user's session bus, through which a program reaches the desktop and the service manager."""
function session_bus(home = homedir(); command = `busctl --user list`)
    return attempt(() -> run(pipeline(command; stdout = devnull, stderr = devnull)))
end
"""A TCP connection to an address on the network that answers."""
connect_remote(home = homedir(); address = ip"1.1.1.1", port = 443) = attempt(() -> connect_tcp(address, port))
"""A name lookup of a package host through the system's resolver."""
resolve_name(home = homedir(); host = "julialang.org", resolver = Sockets.getaddrinfo) = attempt(() -> resolver(host))

const POSITIVE = (:read_research, :write_research, :write_tempdir, :list_packages, :metal, :connect_loopback, :pkg_offline)
const NEGATIVE = (
    :read_ssh,
    :read_claude_json,
    :read_documents,
    :read_gh_hosts,
    :write_zshrc,
    :write_git_hooks,
    :write_julia_config,
    :lsopen,
    :appleevent,
    :connect_remote,
    :resolve_name,
)
const LINUX_POSITIVE = (:read_research, :write_research, :write_tempdir, :list_packages)
const LINUX_NEGATIVE = (
    :read_ssh,
    :read_claude_json,
    :read_gh_hosts,
    :write_zshrc,
    :write_git_hooks,
    :write_julia_config,
    :systemd_run,
    :session_bus,
)
const OPEN_GAPS = ()

"""The probes of `run_all` on Linux, with `linux`, else on macOS, the positive ones first."""
probe_names(linux = Sys.islinux()) = linux ? (LINUX_POSITIVE..., LINUX_NEGATIVE...) : (POSITIVE..., NEGATIVE...)

"""Every probe of this system with `home`, the positive ones first: one `name => result` pair each."""
run_all(home = homedir()) = [name => getfield(ProbeDaemon, name)(home) for name in probe_names()]

end
