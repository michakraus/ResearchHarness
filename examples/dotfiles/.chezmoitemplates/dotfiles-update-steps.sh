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

# dotfiles_review_apply <name>: show `chezmoi diff` for the source as it is, ask, and apply only
# after the answer y.
dotfiles_review_apply() {
    chezmoi diff
    if dotfiles_confirm "$1: apply this diff to the home directory?"; then
        chezmoi apply
    else
        echo "$1: nothing applied; the source stays at $(git rev-parse --short HEAD)."
    fi
}
