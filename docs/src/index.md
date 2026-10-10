---
layout: home

hero:
  name: Research Harness
  tagline: One configuration for the coding agents that work on your research software.
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
    title: One set of sources for three frontends
    details: Claude Code, OpenCode and oh-my-pi read one set of agents, skills, rules, commands and instructions. <code>harness install</code> writes the configuration of each.
    link: /architecture
  - icon: rule
    title: Instructions that load when they apply
    details: The core instructions load in every session. A rule loads when the agent reads a matching file, and a skill when your request matches its description.
    link: /components/rules
  - icon: guard
    title: Safety in layers
    details: One settings template gives the permission and sandbox settings. Guard hooks refuse unsafe shell commands before they run.
    link: /security
  - icon: workflow
    title: Long work goes to a sub-agent
    details: A test run or a review runs in its own context and returns a short report, so your session keeps its context for the work.
    link: /agents-at-work
  - icon: private
    title: Private values stay private
    details: A private profile holds every value that names a person, an institution or a machine, and a check keeps them out of the repository.
    link: /profile
  - icon: code
    title: Ideas for any language
    details: Its own tools are for Julia code, but most of its ideas transfer to any language. The dependencies page says what needs Julia.
    link: /dependencies
---

## How the parts fit together

<OverviewFigure />

*The harness and its three layers.* The research tree is where the work is, the components are
what the harness supplies, and the frontends are the agents that read them. The research-tree
layer shows the tree of the harness's author, as an example; your tree holds your own directories.
[An example tree](example-tree.md) describes the six directories and the components that serve
each.

<FlowFigure />

*From the sources to the frontends.* `harness install` writes the configuration of each frontend
from the sources and your private files. [Architecture](architecture.md) describes the layers and
what each frontend receives.

<HomeEditLink />
