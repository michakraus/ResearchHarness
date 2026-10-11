# Put the tree of one commit of a package into a directory, to run a probe on the unmodified tree:
#
#   julia --startup-file=no base-tree.jl <package> <ref> <dest> [<path> ...]
#
# <ref> is a git ref of <package>, such as origin/main. <dest> must not exist or must be empty. With
# paths, only those paths of the tree are written. One call, no tar file and no permission prompt:
# a worktree-isolated agent cannot pipe `git archive` into `tar`, and `git archive -o` asks.

"Write the tree of `ref` of `pkg`, or only its `paths`, into the new or empty directory `dest`."
function base_tree(pkg, ref, dest, paths = String[])
    isdir(dest) && !isempty(readdir(dest)) && error("$dest is not empty")
    mkpath(dest)
    run(pipeline(`git -C $pkg archive $ref -- $paths`, `tar -x -C $dest`))
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
