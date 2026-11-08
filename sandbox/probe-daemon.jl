# The probes of the Kaimon server under its Seatbelt profile, sandbox/daemon.toml rendered by
# `harness render sandbox/kaimon.sb`. A session runs them through Kaimon's `ex` after
# `harness setup` has written the profile and the server has restarted under it:
#
#     include(joinpath(homedir(), "Research", "Harness", "sandbox", "probe-daemon.jl"))
#     ProbeDaemon.run_all()
#
# Each probe returns `:allowed`, or the name of the exception class that the attempt raised, as a
# Symbol: never a file's content. `run_all` returns one `name => result` pair per probe, the
# positive probes first. The profile is at work when every positive probe gives `:allowed`, `metal`
# included, and every negative probe gives the name of an exception class: `:SystemError` or an
# `IOError` class, `lsopen` and `appleevent` `:ProcessFailedException`. A write probe deletes what
# it created; the probe of ~/.zshrc opens the file to append and writes nothing.
#
# `OPEN_GAPS` names the negative probes that the profile does not stop, which report `:allowed`
# under the real profile: none. The event of `appleevent` is `name of startup disk` of the Finder,
# because AppleScript answers `name` of an application from the script itself and sends no event.
#
# Each probe takes the home directory as its argument, so that `harness test` runs every probe
# against a scratch tree (lib/harness/jobsandbox.py).
module ProbeDaemon

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

const POSITIVE = (:read_research, :write_research, :write_tempdir, :list_packages, :metal)
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
)
const OPEN_GAPS = ()

"""Every probe with `home`, the positive ones first: one `name => result` pair each."""
run_all(home = homedir()) = [name => getfield(ProbeDaemon, name)(home) for name in (POSITIVE..., NEGATIVE...)]

end
