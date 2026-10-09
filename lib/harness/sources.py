"""The neutral sources: the five directories of this repository that belong to no one frontend.

agents/, skills/, rules/, instructions/ and commands/ hold the instruction layer. Each adapter
reads them from here: one installs them, the others render their agents and rules from them.
`frontmatter.selftest` parses the agents and the curated skills that `listing` names.
"""

import os
import pathlib

from . import REPO, HarnessError

NEUTRAL = ("agents", "skills", "rules", "instructions", "commands")
AGENTS = REPO / "agents"
SKILLS = REPO / "skills"

# Directories below a skills directory that are not curated skills. `synced/` is the copy that a
# desktop app writes of the skills of its web service.
EXCLUDED_SKILLS = ["synced"]


def curated_skills(root):
    """The curated skills below `root`: a directory with a SKILL.md, no dot, not excluded."""
    root = pathlib.Path(root)
    if not root.is_dir():
        raise HarnessError(f"{root} is not a directory")
    return sorted(n for n in os.listdir(root)
                  if not n.startswith(".") and n not in EXCLUDED_SKILLS and (root / n / "SKILL.md").is_file())


def listing():
    """The agents of agents/, then the SKILL.md of each curated skill of skills/."""
    return sorted(AGENTS.glob("*.md")) + [SKILLS / name / "SKILL.md" for name in curated_skills(SKILLS)]


def code_list(names):
    """`names` as Markdown code, joined as a sentence lists them: `a`, `b` and `c`."""
    names = [f"`{n}`" for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
