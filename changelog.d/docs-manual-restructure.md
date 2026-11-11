- **The manual has two new sections, Agentic coding and Safeguards, between Use and Background.**
  Agentic coding explains the ideas of the builder-critic loop in eleven pages: the challenges,
  the agents and their roles, tasks, specs and gates, the loop, static checks, tests and CI,
  mutant testing, the edge catalogue, review and pull requests, and a worked example of a feature
  in a fictitious Julia package. Safeguards gives the risks, the security model, permissions with
  the principle of allow, ask and deny, the guard hooks, the sandboxes, git safety, and the leak
  checks. Four new figures draw the pipeline from a task to a merge, a mutant, the cycle of the
  edge catalogue and the three sandboxes, and the checks between an edit and a merge get a
  figure too. The two pages of the `harness` command are one page, *The `harness` command*, with
  its modules under *The implementation*. The pages `security`, `agentic-engineering` and
  `components/hooks` move to `safeguards/security-model`, `agentic/agents` and
  `safeguards/guard-hooks`, so their old URLs end; every link of the site, the README and the
  figure data names the new paths. The security model no longer says that OpenCode and oh-my-pi
  have no sandbox or that an outer sandbox is planned: `agentbox` runs any of the four CLIs under
  `srt`, and the page lists the safeguards that are planned. `docs:check` reads only the files of
  the figure directories, not a directory there such as `.claude/`.
