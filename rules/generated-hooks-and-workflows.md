---
paths: ["**/.githooks/**", "**/.github/workflows/**", "**/Harness/githooks/**"]
description: Hooks and CI workflows are generated; never edit an installed copy.
---

# These files are generated

The canonical copies live in `~/Research/Harness/githooks/` — the hooks at the top level,
the GitHub workflows in `githooks/workflows/`. They are installed byte-identical into every
package and experiment repository.

**Edit the canonical copy and re-run the installer. Never edit a copy inside a repository.** The
next install overwrites it, and until then that repository is silently the only one that differs.

```bash
harness githooks --apply
harness workflows --apply
julia --startup-file=no ~/Research/Harness/githooks/verify-workflows.jl
```

A change here is a change to all of them, so it earns an entry in `Harness/CHANGELOG.md` even
when it looks like a one-line edit. **Push `Harness/` afterwards** — nothing pushes it for you.

## Five things that bite

**`core.hooksPath` is local config and does not travel with a push.** A fresh clone has no hooks
until the installer runs again.

**The shared copies are tracked, not untracked.** So `--apply` leaves a modified file in every
repository, which you then commit by name.

**`pre-commit` filters to `*.jl` and exits 0 when none match.** A Markdown-only commit is therefore
checked by nothing. Run `Harness/githooks/nfc.jl` yourself on such a commit. It and
`fatou lint` report on **stderr** and signal by **exit status**, so counting stdout lines calls
every file clean. Before you report a silent sweep as a pass, prove it detects a positive:
`nfc.jl` exits 1 on a decomposed file.

**From a session, `harness githooks --apply` cannot set `core.hooksPath`**; the hook copies
still land, and it exits 2 with one command per repository. **A session cannot set
`core.hooksPath` or `core.fsmonitor`**: `.git/config` is denied for those keys, because each names
a program that the next top-level `git` runs (`settings/settings.json.md`). A top-level
`git config` of either fails with `could not lock config file`, while a neutral key writes. Give
the user the commands it prints, to run in their terminal.

**A repository in the profile's `docs_exceptions` is skipped by both the installer and the drift
check.** Both report success whatever its `Documenter.yml` holds, so read the file. A repository
that keeps its own docs workflow goes into `docs_exceptions` (a multi-job pipeline) or
`docs_additions` (the canonical body plus a step) in `~/.config/research-harness/profile.toml`,
which the user edits. An unlisted one gets the template installed over its own workflow.

A push to `main` or `master` runs the full suite through `pre-push`, which is silent for as long as
the suite takes — **10–30 minutes in the large packages**. A topic branch does not run it.

Mechanism and measurements: `Environment/Notes/Git-and-GitHub.md`.
