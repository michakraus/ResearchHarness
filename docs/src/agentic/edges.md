# Edges

An edge is an input at the border of what a part does: a `NaN`, an empty list, a path with a
space, the other floating-point precision. A spec that does not decide an edge leaves the answer to
the builder, and a critic that probes the edge finds the gap as a blocking defect. With several
open edges, each round of the loop finds one more, and the loop does not close. The harness
therefore keeps a catalogue of the edges that critics found, by the kind of part, and the planner
decides each one before the build. This page describes the catalogue and how it grows.

## The edge catalogue

The catalogue is one file of the harness, `skills/build-part/edges.md`. It has about 260 one-line
entries in seven sections, one for each kind of part:

| kind of part | entries |
|:--|--:|
| a part that predicts what another tool reads or does | 28 |
| a numerical method | 44 |
| a type or an interface | 33 |
| a tool that reads files or a tree | 61 |
| a step that runs a user's script | 15 |
| a lint cleanup | 4 |
| a migration of tests or of text | 75 |

An entry names the class of input, the mechanism of the failure, the remedy, and the part that
found it. Two entries of the section for a numerical method:

```markdown
- a subnormal input; a result that underflows to zero; an anchor value near `floatmin`
- a tie that round-off decides, for example a safeguard of the form `w <= wprev / 2`
```

The first section is a design rule more than a list. A guard or a renderer predicts what another
program reads, and each gap between the prediction and the program is a defect. Its first entry
says: fail closed or emit a canonical form, never emulate the other program.

## The cycle

<EdgesFigure />

*How the catalogue grows.* The planner writes the spec's *Decided at the edges* from the
catalogue. The builder builds to the spec, and the critic probes every edge of the part's kind that
the spec does not decide. A defect outside every clause of the spec, in a class that the catalogue
does not hold, becomes a new entry after the loop, and the next spec of that kind decides it. The critic
also reads the catalogue directly.

Each role uses the catalogue:

- **The planner** writes *Decided at the edges* from the section of the part's kind: one line per
  edge, with the answer. An edge that it cannot decide makes the part a `decision` part, which
  waits for you ([`plan-parts`](../components/skills.md#plan-parts)).
- **The spec gate** refuses to start a `build` part whose spec has no *Decided at the edges*
  ([Specs and gates](specs-and-gates.md#the-gates)).
- **The critic** of round 1 probes every edge of the part's kind that the section does not decide,
  then inputs that the builder did not try.
- **A fix builder** that adds a guard, an exit or a status reads the section first, and tests its
  new rule on each class of edge that the rule can reach. A fix for one reproducer changes the
  result on other inputs too.
- **The arbitrator** reads it when a loop does not converge, because a run of defects of one class
  points at an edge that nobody decided.

## How an entry is added

Each clause of a spec has a *domain*: the finite set of inputs that it names, such as the decided
edges or the named mutants. A failure inside the domain fails the clause and blocks the round. A
failure outside every domain is an other defect of the kind *found late*: the critic records it
with its reproducer, and it does not block. A verify round also records a defect outside the fix
diff as found late. A found-late defect shows an input class that the spec did not reach.

After the loop, `build-part` records each class of a found-late defect that the catalogue does not
hold, as one line in the section of the part's kind, with the part that found it. The line goes
into the source of the catalogue in the harness, through a pull request of the harness with a
changelog fragment `changelog.d/edges-<name>.md`. The next `harness install --apply` installs it.

## The limits

- **The catalogue only grows.** No rule removes an entry yet. **Planned:** an entry goes when a
  deterministic check catches its class, or when it duplicates another entry. A class that a
  [static check](static-checks.md) catches no longer needs a line that the planner reads.
- **An entry names a class, not a test.** The planner still decides what the code does at the edge,
  and the builder still writes the test.
- **The catalogue is written for the packages of one tree.** Its entries name packages by their
  role, such as "the integrator package", so the text stays true when a package is renamed.

**In another language.** The sections are by the kind of part, not by the language. The sections
of a tool that reads files and of a migration apply to any language; the section of a numerical
method applies wherever floating point does.
