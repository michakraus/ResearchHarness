- **No required CI job fetches the uv release from GitHub.** The `empty-home` job installs uv
  with `setup-uv`, which fetches it from the Astral mirror, and the `dotfiles` job makes the
  harness's environment once with it; `script-check.py` passes that environment to the services
  scripts as `$RESEARCH_HARNESS_PYTHON`, so `harness render` in a scratch home starts no uv. A
  slow GitHub release host timed out both jobs, and on macOS the services test failed at once
  with no uv on its `PATH`.
