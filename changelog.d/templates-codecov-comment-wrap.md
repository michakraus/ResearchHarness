- **The `codecov.yml` template wraps its coverage comment at 100 columns.** One line of the
  comment ran to about 170 characters. The words and the configuration are unchanged, but the
  template is copied byte for byte, so `harness workflows --apply` rewrites `codecov.yml` in every
  repository, and `verify-workflows.jl` reports drift until it does.
