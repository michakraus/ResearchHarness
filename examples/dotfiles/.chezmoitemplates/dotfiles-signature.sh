# The signature test of one commit (.chezmoitemplates/dotfiles-signature.sh), which
# dotfiles-update and dotfiles-merge use through .chezmoitemplates/dotfiles-update-steps.sh, and
# dotfiles-check uses on the head of the source.

DOTFILES_SOURCE="$HOME/.local/share/chezmoi"
# The allowed_signers file as applied before the update, never the one in the incoming source:
# an incoming commit must not name its own key.
DOTFILES_SIGNERS="$HOME/.config/git/allowed_signers"

# dotfiles_signers_listed: true when the applied allowed_signers exists and lists a key.
dotfiles_signers_listed() {
    grep -qvE '^[[:space:]]*(#|$)' "$DOTFILES_SIGNERS" 2>/dev/null
}

# dotfiles_signature <commit>: print "%G? %GS" of <commit> in the repository of the working
# directory, as the applied allowed_signers reads its signature. Only an SSH signature counts,
# because only SSH verification reads allowed_signers: the OpenPGP and X.509 programs are `false`,
# so a key that the host's gpg or gpgsm trusts never gives G. --no-show-signature keeps a
# log.showSignature of the host out of %G?.
dotfiles_signature() {
    git -c gpg.ssh.allowedSignersFile="$DOTFILES_SIGNERS" \
        -c gpg.openpgp.program=false -c gpg.x509.program=false \
        log -1 --no-show-signature --format='%G? %GS' "$1"
}

# dotfiles_good <verdict>: true when a verdict of dotfiles_signature is a good signature (%G? =
# G) by a principal.
dotfiles_good() {
    [ "${1%% *}" = G ] && [ -n "${1#* }" ]
}
