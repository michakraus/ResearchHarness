# The steps that dotfiles-update and dotfiles-merge share (.chezmoitemplates/dotfiles-update-steps.sh):
# the terminal test, the question, the signature check, and the review and apply.

{{ template "dotfiles-signature.sh" . }}
# dotfiles_require_terminal <name>: stop unless a person can answer on standard input.
dotfiles_require_terminal() {
    if [ ! -t 0 ]; then
        echo "$1: standard input is not a terminal; run $1 yourself, in a terminal." >&2
        exit 1
    fi
}

# dotfiles_confirm <question>: ask on the terminal; true only for the answer y or Y. An empty line
# and the end of input mean no.
dotfiles_confirm() {
    local answer=""
    printf '%s [y/N] ' "$1"
    read -r answer || answer=""
    [ "$answer" = y ] || [ "$answer" = Y ]
}

# dotfiles_check <name> <base> <tip>: <tip> is a fast-forward of <base>, and every commit on the
# first-parent path from <base> to <tip> carries a good signature (%G? = G) by a principal of
# the applied allowed_signers. It reads %G? and the principal, never the exit status of
# `git verify-commit` alone. It names each commit that fails, and returns 1.
dotfiles_check() {
    local name=$1 base=$2 tip=$3 commits commit verdict bad=0
    if ! dotfiles_signers_listed; then
        echo "$name: $DOTFILES_SIGNERS is missing or lists no key; no commit is verified." >&2
        return 1
    fi
    if ! git merge-base --is-ancestor "$base" "$tip"; then
        echo "$name: $tip is not a fast-forward of $base." >&2
        return 1
    fi
    commits=$(git rev-list --first-parent "$base..$tip") || return 1
    while read -r commit; do
        [ -n "$commit" ] || continue
        verdict=$(dotfiles_signature "$commit") || return 1
        if ! dotfiles_good "$verdict"; then
            echo "$name: commit $commit has no good signature by a key of $DOTFILES_SIGNERS (%G? = ${verdict%% *})." >&2
            bad=1
        fi
    done <<<"$commits"
    return "$bad"
}

# The review commands write into a pipe, so they colour their output only when standard output is
# a terminal, as they do when they page it themselves.
DOTFILES_COLOR=""
if [ -t 1 ]; then
    DOTFILES_COLOR=1
fi

# dotfiles_review <name> <stop> <command>...: show the output of <command> in git's pager, with
# LESS and LV as git sets them. A pager that quits before <command> has written all of its output
# breaks the pipe, and <command> exits 141: that stops the script with exit 1 and the line
# "<name>: you quit the review early; <stop>". Any other failure stops it with that status.
# chezmoi diff writes into its own pager through a pipe that it never closes, and hangs when the
# pager quits early, so no review uses the pager of git or chezmoi.
dotfiles_review() {
    local name=$1 stop=$2 pager status
    shift 2
    pager=$(git var GIT_PAGER)
    if "$@" | LESS=${LESS-FRX} LV=${LV--c} sh -c "$pager"; then
        return 0
    fi
    status=("${PIPESTATUS[@]}")
    if [ "${status[1]}" -ne 0 ]; then
        exit "${status[1]}"
    fi
    if [ "${status[0]}" -eq 141 ]; then
        echo "$name: you quit the review early; $stop" >&2
        exit 1
    fi
    exit "${status[0]}"
}

# dotfiles_review_apply <name> <state>: show `chezmoi diff` for the source as it is, ask, and apply
# only after the answer y. <state> says what is true of the source when the review is cut short.
dotfiles_review_apply() {
    dotfiles_review "$1" "$2 Run chezmoi diff, read it to its end, then run chezmoi apply." \
        chezmoi diff --no-pager ${DOTFILES_COLOR:+"--color=true"}
    if dotfiles_confirm "$1: apply this diff to the home directory?"; then
        chezmoi apply
    else
        echo "$1: nothing applied; the source stays at $(git rev-parse --short HEAD)."
    fi
}
