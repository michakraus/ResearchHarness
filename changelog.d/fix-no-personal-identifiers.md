- **Web requests carry no identity of the user, and the guard refuses one that does.**
  `literature-scout` gains a section that sends every request anonymously: no name, email
  address, institution, `mailto=` parameter, API key or token, not even a placeholder address, and
  no new account or key; a rate limit or a page that asks for contact details makes that index a
  failed source. `instructions/core.md` states the same rule for every agent that loads it,
  because the scout loads none. No instruction said this before: the user saw scouts use the
  user's name and email address, and an OpenAlex search page asked an agent to create an API key
  with the user's email. The new web check, `hooks/guard/web_identity.py`, refuses a web fetch or
  a web search that carries the user's email address (`git config --get user.email`, also
  percent-encoded) or a `mailto=`, `email=`, `api_key=` or `access_token=` query parameter, and a
  shell command that carries such a parameter, or a URL and the user's email address. It covers
  the web tools of all four frontends, and oh-my-pi's `read` of a URL. The settings template runs
  the guard on `WebFetch|WebSearch`, which `harness install --apply` installs. The probe gives
  every hook a fixture git configuration with a known address, and 27 new corpus records cover the
  check. The fixture of the scout's render follows the source.
