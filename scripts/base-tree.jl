# Put the tree of one commit of a package into a directory, to run a probe on the unmodified tree:
#
#   julia --startup-file=no base-tree.jl <package> <ref> <dest> [<path> ...]
#
# <ref> is a git ref of <package>, such as origin/main. <dest> must not exist or must be empty. With
# paths, only those paths of the tree are written. One call, no tar file and no permission prompt:
# a worktree-isolated agent cannot pipe `git archive` into `tar`, and `git archive -o` asks.
#
# The tree leaves out every directory and file named `.githooks`, at any depth below <package>:
# the sandbox denies its write under ~/Research, and no caller runs a hook. A named path inside one
# is refused; `git show <ref>:<path>` prints such a file without writing it.

# Relative to the working directory of `git -C`, so they also hold for a package in a subdirectory
# of its repository: the first leaves out the content of each `.githooks` directory, the second a
# file of that name.
const LEFT_OUT = [":(exclude,glob)**/.githooks/**", ":(exclude,glob)**/.githooks"]

"""
Write the tree of `ref` of `pkg`, or only its `paths`, into the new or empty directory `dest`,
without any `.githooks`; refuse a path with a segment `.githooks` before anything is written.
"""
function base_tree(pkg, ref, dest, paths = String[])
    for p in paths
        ".githooks" in splitpath(normpath(p)) &&
            error("$p is inside a .githooks, which the tree leaves out; in $pkg, `git show $ref:./$(normpath(p))` prints it")
    end
    isdir(dest) && !isempty(readdir(dest)) && error("$dest is not empty")
    mkpath(dest)
    run(pipeline(`git -C $pkg archive $ref -- $paths $LEFT_OUT`, `tar -x -C $dest`))
    return sum(((_, _, files),) -> length(files), walkdir(dest); init = 0)
end

function main(args)
    length(args) >= 3 ||
        (println(stderr, "usage: base-tree.jl <package> <ref> <dest> [<path> ...]"); return 2)
    pkg, ref, dest = abspath(expanduser(args[1])), args[2], abspath(expanduser(args[3]))
    n = base_tree(pkg, ref, dest, args[4:end])
    sha = chomp(read(`git -C $pkg rev-parse --short $ref`, String))
    println("$dest: $n files of $ref at $sha")
    return 0
end

if abspath(PROGRAM_FILE) == @__FILE__
    exit(main(ARGS))
end
