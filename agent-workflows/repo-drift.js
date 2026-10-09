export const meta = {
  name: 'repo-drift',
  description: 'Audit package repositories against the canonical hooks and workflows in githooks/',
  whenToUse: 'When asked whether the shared hooks, workflows, .gitignore or CHANGELOG have drifted across the tree. Read-only.',
  phases: [
    { title: 'Audit', detail: 'one cheap agent per repository, read-only' },
    { title: 'Confirm', detail: 'only where the audit reported drift' },
  ],
}

// Invoke with ABSOLUTE repository paths as args:
//   Workflow({scriptPath: '<home>/Research/Harness/agent-workflows/repo-drift.js',
//             args: ['<home>/Research/Packages/Example', ...]})
//
// The installer that generates these workflows skips Experiments/, so include repositories from
// there deliberately — that is where drift is expected and where verify-workflows.jl does not look.
//
// Read-only by construction: every prompt forbids editing, and no agent is given a worktree.
// Grade the result against githooks/verify-workflows.jl rather than trusting it — see
// ../Dynamic-Workflows.md, worked example 1.

const DRIFT = {
  type: 'object',
  properties: {
    repo:      { type: 'string' },
    drifted:   { type: 'boolean' },
    files:     { type: 'array', items: { type: 'string' } },
    hooksPath: { type: 'string', description: 'value of core.hooksPath, or "unset"' },
    missing:   { type: 'array', items: { type: 'string' },
                 description: 'expected files absent entirely, e.g. .gitignore, CHANGELOG.md' },
    evidence:  { type: 'string', description: 'first differing line, quoted, or "" if identical' },
  },
  required: ['repo', 'drifted', 'files', 'hooksPath', 'missing'],
}

// Narrow verdict for the confirm pass. Deliberately NOT the DRIFT schema — see stage 2.
const VERDICT = {
  type: 'object',
  properties: {
    confirmed:  { type: 'array', items: { type: 'string' },
                  description: 'files that genuinely differ' },
    overturned: { type: 'array', items: { type: 'string' },
                  description: 'files the earlier pass flagged that are in fact identical' },
    evidence:   { type: 'string', description: 'first genuinely differing line, quoted' },
  },
  required: ['confirmed', 'overturned'],
}

if (!Array.isArray(args) || args.length === 0) {
  throw new Error('repo-drift: pass repository paths as args, e.g. args: ["~/Research/Packages/Example"]')
}

// Absolute, not ~: sub-agents pass these straight to Read, which does not expand a tilde. The
// research tree's root comes from the first repository path, so the script names no home.
const ROOT = args[0].match(/^(.*\/Research)\//)
if (!ROOT) {
  throw new Error(`repo-drift: ${args[0]} is not below a Research/ directory`)
}
const CANON = `${ROOT[1]}/Harness/githooks`

phase('Audit')
log(`auditing ${args.length} repositories against ${CANON} — read-only`)

const results = await pipeline(
  args,

  // Stage 1 — cheap, mechanical, one per repository. haiku/low: this is diffing, not judging.
  repo => agent(
    `Repository: ${repo}

     Compare against the canonical sources in ${CANON}:
       .githooks/pre-commit                    vs ${CANON}/pre-commit
       .githooks/pre-push                      vs ${CANON}/pre-push
       .github/workflows/CI.yml                vs ${CANON}/workflows/CI.yml
       .github/dependabot.yml                  vs ${CANON}/workflows/dependabot.yml
       .github/workflows/Documenter.yml        vs ${CANON}/workflows/Documenter.yml
       .github/workflows/TagBot.yml            vs ${CANON}/workflows/TagBot.yml
       codecov.yml  ← AT THE REPOSITORY ROOT, not under .github/workflows/
                                               vs ${CANON}/workflows/codecov.yml

     That last path is the one to get right: codecov.yml is a Codecov *configuration* file, not a
     GitHub workflow. harness workflows copies it to the repository root even though it is
     stored beside the workflows in the canonical directory. Checking it under .github/workflows/
     reports it missing in every repository — twelve false positives, measured 2026-09-01.

     Also report:
       - the value of "git -C ${repo} config core.hooksPath", or "unset"
       - whether .gitignore and CHANGELOG.md exist

     A file that is absent goes in "missing", not in "files". "files" is for files that exist and
     differ. If everything matches and nothing is missing, return drifted=false with empty arrays —
     that is a real and expected result, not a failure.

     READ ONLY. Do not edit, create or stage anything.`,
    { schema: DRIFT, label: `audit:${basename(repo)}`, phase: 'Audit',
      model: 'haiku', effort: 'low' }),

  // Stage 2 — verify ONLY the differing files, and return ONLY a verdict on them.
  //
  // It must not return the DRIFT schema. Measured 2026-09-01: when it did, and was handed only
  // r.files, it filled the other required fields from nothing — wiping every "missing" finding to
  // [] and inventing hooksPath="unset" where stage 1 had correctly read ".githooks". Stage 1 was
  // 4/5 against ground truth; stage 2 replaced its record wholesale and dragged the run to 2/5
  // plus two fabrications.
  //
  // The rule this cost: a verify stage NARROWS a finding, it does not REPLACE the record. Never
  // give it a schema with required fields it was not asked about — the model will fill them in.
  (r, repo) => (!r || !r.drifted || r.files.length === 0) ? r
    : agent(
    `Repository: ${repo}
     A previous pass reported these files as differing from ${CANON}: ${JSON.stringify(r.files)}

     Re-read both sides of each one and decide, per file, whether it genuinely differs.
     Quote the first genuinely differing line. If a file is in fact identical — whitespace and all —
     put it in "overturned". Overturning the earlier report is a correct outcome; do not confirm it
     to be agreeable.

     Report on these files ONLY. Say nothing about missing files, hooks paths, or any other
     repository property — they are not yours to judge in this pass and a previous pass has them.

     READ ONLY.`,
    { schema: VERDICT, label: `confirm:${basename(repo)}`, phase: 'Confirm', model: 'sonnet' })
      // Merge, never replace: stage 1 owns missing/hooksPath, stage 2 owns which files really differ.
      .then(v => {
        if (!v) return r                                  // verifier died — keep the unverified finding
        const confirmed = v.confirmed ?? []
        return { ...r, files: confirmed,
                 drifted: confirmed.length > 0 || (r.missing ?? []).length > 0,
                 evidence: v.evidence ?? r.evidence,
                 overturned: v.overturned ?? [] }
      }),
)

function basename(p) {
  const parts = String(p).split('/').filter(Boolean)
  return parts[parts.length - 1] ?? String(p)
}

// null means the agent died or was skipped — an unchecked repository, never a clean one.
const unreported = args.filter((_, i) => !results[i])
const reported   = results.filter(Boolean)
const drifted    = reported.filter(r => r.drifted)
const missing    = reported.filter(r => (r.missing ?? []).length > 0)
const noHookPath = reported.filter(r => r.hooksPath === 'unset')

log(`${drifted.length} drifted · ${missing.length} with missing files · ${noHookPath.length} without core.hooksPath`)
if (unreported.length) log(`WARNING: ${unreported.length} repositories returned nothing and were NOT checked`)

return {
  checked: reported.length,
  unreported: unreported.map(basename),   // named, not counted — a silent gap is the failure mode
  drifted,
  missing,
  hooksPathUnset: noHookPath.map(r => r.repo),
}
