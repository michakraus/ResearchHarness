- **A Python part runs on `python-builder` and `python-critic`, and `rules/python-code.md` loads
  on every `.py` file.** `build-part` picks the pair by the `**Language:**` line of the part's spec
  header, which `plan-parts` writes for every `build` part beside `**Tier:**`; without the line, a
  repository with a `Project.toml` gets `julia-builder` and `julia-critic`, one with only a
  `pyproject.toml` the Python pair, and one with neither `part-builder` and `part-critic`. The
  Python pair has the Julia pair's tiers; its gate is `harness test`, ruff and basedpyright, and
  its named mutants run with `harness mutate`. The rule names each idiom of the strict profile with
  the tool that enforces it, and `docs/src/development.md` gives the reasons. `python-critic` has a
  council in `examples/models.toml`, which the round-1 text of OpenCode and oh-my-pi names, and
  the OpenCode and Antigravity rule tables list the rule.
  `plan-parts` gives a facts section longer than 150 lines a summary that the spec bundle copies
  in place of the section. A case of the `docs` part reads the skill's dispatch table for each set
  of manifests. Run `harness install --apply` to install the two agents and the rule.
