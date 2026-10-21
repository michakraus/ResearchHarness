---
layout: home

hero:
  name: Research Harness
  tagline: The configuration, the safety settings and the working environment for coding agents on research software.
  actions:
    - theme: brand
      text: Get started
      link: /concepts
    - theme: alt
      text: Tutorial
      link: /tutorial
    - theme: alt
      text: GitHub
      link: https://github.com/michakraus/ResearchHarness

features:
  - icon: harness
    title: One configuration for three frontends
    details: Claude Code, OpenCode and oh-my-pi read one set of agents, skills, rules and instructions. <code>harness install</code> writes the configuration of each. A rule or a skill loads only when it applies.
    link: /architecture
  - icon: private
    title: Private data across machines
    details: A private profile holds every value that names a person, an institution or a machine. A leak check keeps these values out of the repository. Signed dotfiles and git carry them to each machine.
    link: /private-data
  - icon: sandbox
    title: Sandbox and safety in layers
    details: The Claude Code sandbox limits the files that a shell command can write and the hosts that it can reach. Permission settings and guard hooks stop common mistakes before a call runs.
    link: /security
  - icon: tree
    title: A directory tree for research work
    details: The research tree is one directory for the packages, experiments, papers, notes and literature, each in its own repository. The harness clones and syncs them, and gives each directory its own rules.
    link: /research-tree
  - icon: knowledge
    title: Research memory
    details: A session starts with an empty context. Instruction files, task files, a knowledge base and project memory carry what earlier sessions learned into the next one.
    link: /memory
  - icon: workflow
    title: Agentic software engineering
    details: A plan splits a change into parts with checkable criteria. A builder writes each part, and a critic that has not seen its reasoning judges it. Sub-agents run the long tests and reviews.
    link: /agentic-engineering
---

The tools of the harness are for Julia, but most of its ideas apply to any language.
[Dependencies](dependencies.md) says what needs Julia.

## How the parts fit together

<OverviewFigure />

*The research tree, the components and the frontends.* The research tree is where the work is,
the components are what the harness supplies, and the frontends are the agents that read them.
The figure shows the tree of the harness's author, as an example; your tree holds your own
directories. [The research tree](research-tree.md) describes the six directories and the
components that serve each.

<FlowFigure />

*From the sources to the frontends.* `harness install` writes the configuration of each frontend
from the sources and your private files. [Architecture](architecture.md) describes the layers and
what each frontend receives.

<HomeEditLink />
