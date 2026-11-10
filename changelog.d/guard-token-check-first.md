- **The guard's token check stands first in each list of checks that holds it, on every
  frontend.** A call in which the token check finds a token gets the token check's reason, which
  names the token's form and does not show the token, also where the web check, the `gh api` check
  or the Kaimon check refuses the call too; before, such a check's reason could quote the token.
