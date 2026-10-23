# The spec-delta format of a part

The spec of a part of tier `build` or `reviewed` in a new plan. A plan whose parts already have
their spec sections keeps them.

## Where it lives

`Tasks/Evidence/<task file's name>/<part>/spec.md`, with its check scripts in `checks/` beside it.
The part's `sections` cell is `spec, §V, §L`: `spec-bundle.py` copies the file whole into the
bundle and names its directory as `$SPEC`, and `spec-gate.py` runs `spec-validate.py` on it.
The task file keeps the row, the collision map, §V, §L and the state; the spec keeps the rest.

## The header

```markdown
# <part> · <repository>: <one line>

**Base.** <Repository> `<commit>` (`origin/main`). <Each other repository a check reads, at its commit.>

**Running a check.** Every `check:` runs from the root of a <Repository> tree: the base for §1, the
head for §3. `$SPEC` is the directory of this file. <What else a check needs.>

**Tier:** <tier>. **Collision row:** <the files> | <part>; <the other parts that touch them, or none>.
```

## The four sections

| section | holds |
|:--|:--|
| `## 1 · Living spec — <Repository> at <commit>` | each fact of the base that the change relies on, as a requirement with scenarios whose `check:` passes on the base |
| `## 2 · Change proposal` | **Why**, **In scope**, **Out of scope** (with the part that owns each item), **Files**, **Commits**, **Seams**, **Reads** |
| `## 3 · Delta` | `### MODIFIED Requirements`, `### ADDED Requirements`, `### REMOVED Requirements`, each with its requirements |
| `## 4 · What stays from the plan` | the named mutants as a table `\| MU<n> \| change \| kept test \|`, the decisions that bind the part, the decisions of the spec's writer, *Traps* |

A requirement and its scenarios:

```markdown
### Requirement: <name>

<The statement, with SHALL or MUST.>

#### Scenario: <name>

- WHEN <concrete inputs>
- THEN <the observable result>
- domain: <the inputs and parameters where the reference's property holds; only where a reference is named>
- check: `<command>`; `<command>`
- catches: MU<n>, <the mutant>: <the kept test that kills it> | none — <reason>
```

## What each block must do

- **A premise for each fact, and for each API convention a clause depends on.** An argument's
  meaning (an order or a degree, a size or a count), an index base, a unit, a sign or a scaling
  convention: the premise's check reads the convention from the code of the base. A spec that says
  "spline degree 3" for a constructor that takes the order `p + 1` builds degree 2; a premise that
  reads the basis's `p` stops it before a build.
- **A domain for every qualitative clause that a check enforces.** A requirement that names a
  reference output — `reference:` in its heading or statement — states in each scenario the
  domain where the reference's property holds: the parameters, the defaults, the range. A sign
  taken from a reference without the reference's parameter range fails at the parameters the
  script uses.
- **Each decided edge is a scenario** of the delta, from the list for the part's kind in
  `~/.claude/skills/build-part/edges.md`. An edge you cannot decide is a question to the user now.
- **A named mutant is killed by a kept test**, never by a one-time command. A scenario whose check
  is its own evidence, such as a run's output, says `catches: none —` with the reason.
- **A MODIFIED requirement keeps every scenario of its living requirement**, with the new THEN.
- **A block stands on its own.** A WHEN, a THEN or a domain that says "as in §", "unchanged" or
  "see" fails the validator.
- **A check writes only under `$OUT`.** A check that needs a clean clone or a run directory makes it
  there. The delta's checks run in the order of the file and share one `$OUT`, so a check that
  produces the outputs comes before the checks that read them.
- **A check that reads another repository** pins its commit itself, from `$RESEARCH_ROOT`.

## The decisions and the loop

The loop writes into the spec, below the four sections, under `## Decisions`: each
`**Decided (…)**` and `**Recommendation (…)**` line and the `**The loop:**` line, in the forms
that `build-part` and `build-reviewed` give. The validator reads only the four sections.

## The validator

```bash
cd ~/Research && python3 Harness/scripts/spec-validate.py "Tasks/Evidence/<file>/<part>/spec.md" --repo <main checkout of the part's repository>
```

Its header lists the rules. **Planning ends when it passes**: the structure, and every premise run
on the base commit. A failing premise is a false fact of the plan: fix the spec, or ask the user.
`spec-gate.py` runs the same check for every part whose cell names `spec`.
