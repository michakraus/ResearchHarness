---
name: julia-release
description: "Release and register a Julia package in the General registry. Triggers on: release this package, cut a release, tag a version, register the new version, bump the version, breaking release, @JuliaRegistrator, Registrator, TagBot, AutoMerge is blocking, the registry PR is stuck, close out the changelog, prepare the release notes. Covers the whole path from CHANGELOG close-out to a merged registry PR."
---

# Releasing a Julia package

**One path, for every release — breaking or not.** Commit the version bump yourself, push it,
then comment on that commit calling `@JuliaRegistrator` with the release notes in the same
comment.

Do **not** dispatch `.github/workflows/Register.yml`. Why not is at the bottom; it is not a
fallback for patch releases either.

**Contents**

- [The procedure](#the-procedure)
  1. [Close out the CHANGELOG](#1-close-out-the-changelog)
  2. [Set the version](#2-set-the-version)
  3. [Commit both together](#3-commit-both-together)
  4. [Push, and wait properly](#4-push-and-wait-properly)
  5. [Comment on the release commit](#5-comment-on-the-release-commit)
  6. [Watch the registry PR, then TagBot](#6-watch-the-registry-pr-then-tagbot)
- [Why the notes must be in that first comment](#why-the-notes-must-be-in-that-first-comment)
- [Why not `Register.yml`](#why-not-registeryml)
- [The General-registry rebase trap](#the-general-registry-rebase-trap)
- [Checking whether registration landed](#checking-whether-registration-landed)
- [Report](#report)

## The procedure

### 1. Close out the CHANGELOG

Feature PRs do not bump the version — their entries accumulate under
`## [Unreleased] — targeting X.Y.Z`. The close-out turns that heading into the released version.
What is known-broken is in the repository's `KNOWN_ISSUES.md`, not in the changelog.

Read the section's headline paragraphs against `Project.toml`'s `[compat]` floors and against the
section's own entries. No branch rewrites the headline, so it is where a stale claim survives.

The notes you write here are the notes that go in the Registrator comment and, via TagBot, into
the GitHub release. Write them once, properly.

### 2. Set the version

Edit `version = "X.Y.Z"` in `Project.toml` by hand. Any `0.x` **minor** bump is breaking.

### 3. Commit both together

`CHANGELOG.md` and `Project.toml` in **one commit** — that commit is the release, and its SHA is
what Registrator will be pointed at.

```
Release X.Y.Z
```

### 4. Push, and wait properly

`git push` runs the full suite through `.githooks/pre-push`: 10–30 minutes with no output.
Background it, watch the remote ref, do not kill it:

```bash
git ls-remote origin refs/heads/<branch>
```

Not `gh api`: `gh` only escapes the sandbox when every part of the command is excluded, so it
fails inside a loop, in `$( )`, after a `cd … &&` or before a pipe. A `git` inside a loop is
sandboxed too. It verifies against a CA file and reads a public remote, but it errors where the
remote needs credentials. Treat an error from a poll as UNKNOWN, never as "not pushed".

### 5. Comment on the release commit

**Every registration comment carries release notes**, and a breaking one carries a
breaking-changes section. Build the body rather than typing it:

```bash
julia --startup-file=no ~/Research/Harness/githooks/release-notes.jl <package-dir> > notes.json
gh api repos/<owner>/<repo>/commits/<SHA>/comments --input notes.json
```

Run `wc -c notes.json` before you post it. Registrator accepts about 3 kB and fails a 137 kB
comment with "An unexpected error occurred during registration" while GitHub takes the comment.
For a large section, write the body by hand in the shape below, and encode it with
`jq -Rs '{body: .}' notes.md > notes.json`. Shrink the notes, never the CHANGELOG section. `gh` runs
outside the sandbox, where `$TMPDIR` differs, so pass it the file by absolute path.

It reads the version from `Project.toml`, lifts that version's `CHANGELOG.md` section, and
**exits 1 with empty stdout** — no `notes.json` — if the release is breaking and the section has
no breaking-changes heading, or if the close-out was never done. Breaking here means what
Registrator labels `BREAKING`: any `0.0.z`, a `0.y.0` minor bump, an `x.0.0` major bump, or a
bump that skipped the `.0` because a version number was burned.

What it emits, and what to write by hand if the script is unavailable:

```
@JuliaRegistrator register

Release notes:

## Breaking Changes

- <what broke, and what a caller should do about it>

## New Features
...
```

The section names are the CHANGELOG's own, promoted one level — the notes *are* the section
just closed out, not a second thing written for the occasion.

**Never `-F body=@file`** — it mangles multi-line bodies. That, and forgetting the notes, are
the two reasons the body is assembled by script.

Release notes go in **from the start**. They are not something to add after AutoMerge
complains, because by then the registry PR body is already written.

### 6. Watch the registry PR, then TagBot

AutoMerge, then TagBot cutting the GitHub release. A release is not done when the registry PR
opens.

AutoMerge waits about 3 days only for the first registration of a new package. A new version of a
registered package, breaking or not, merges about 15 minutes after its checks pass. A breaking
version without the release-notes block is blocked, not delayed.

## Why the notes must be in that first comment

Registrator labels a breaking registry PR `BREAKING`, and RegistryCI's
`guideline_breaking_explanation` requires the PR body's `<!-- BEGIN RELEASE NOTES -->` block to
match `/breaking|changelog/i`. Without notes, AutoMerge blocks the PR and the release stalls.

If the PR is already open and the notes need changing, **re-trigger on the same release
commit** — that updates the open registry PR rather than opening a second one.

## Why not `Register.yml`

Recorded here so the workflow's presence in these repositories is not mistaken for the
sanctioned route:

- It uses `julia-actions/RegisterAction`, which has **no release-notes input**. Every breaking
  release it produces is blocked by AutoMerge.
- It **bumps the version itself**. Dispatching it after the close-out commit has already set
  `Project.toml` releases one version too high — a wasted version number that cannot be
  reclaimed.

The path above needs no workflow, and no repository here carries `Register.yml`. If you find one,
report it.

## The General-registry rebase trap

This trap applies to a **git-clone** registry. This machine holds `General.tar.zst`, so here it
applies only to CI runners, where `julia-actions/cache` keeps one clone per cache key. The key is
`workflow;job;os;version`, so a stuck clone affects one matrix entry only.

The two registry routes go stale independently. `JULIA_PKG_SERVER: ""` in a workflow forces the
git clone. The default fetches the tarball from `pkg.julialang.org`, which can lag registration
by hours. Check which route the workflow uses before you blame either.

`Pkg.Registry.update()` on a clone can fail to rebase. Such a clone **never recovers on its own**,
and Pkg only warns. Suspect it when a just-registered version appears not to exist on some matrix
jobs only. On a runner, clear that job's cache entry. On a local clone, from its directory:

```bash
git fetch origin
git reset --hard origin/master
```

## Checking whether registration landed

The local registry is compressed and TagBot lags, so neither is authoritative. A path under
`~/.julia/registries/General/` does not exist, so an `ls` or `grep` there reads as "not
registered". Read the local tarball, which can be behind:

```bash
cd ~/.julia/registries && tar --zstd -xOf General.tar.zst <X>/<Package>/Versions.toml <X>/<Package>/Compat.toml
```

Check the General repository over HTTP:

```bash
gh api repos/JuliaRegistries/General/contents/<X>/<Package>/Versions.toml -H 'Accept: application/vnd.github.raw'
```

A freshly registered version is **not installable immediately** — the registry cache has to
propagate. A resolve failure in the first minutes is expected and is not a bad release. CI
installs from the Pkg server, whose snapshot lags the registry repository by tens of minutes.
Probe it from a fresh depot before you re-run a CI job. A fresh depot fetches from the Pkg server,
so it sees what CI resolves; an existing depot can be ahead of the server:

```bash
JULIA_DEPOT_PATH=$(mktemp -d) julia --startup-file=no -e 'using Pkg; Pkg.Registry.add("General")
  for reg in Pkg.Registry.reachable_registries(), (u, p) in reg.pkgs
      p.name == "<Package>" && println(sort(collect(keys(Pkg.Registry.registry_info(reg, p).version_info))))
  end'
```

`registry_info` takes `(registry, entry)`, not the entry alone.

## Report

In this order: the version, breaking or not, the release commit SHA, the registry PR URL, the
AutoMerge verdict, and whether TagBot has cut the GitHub release. Name any step still pending.
