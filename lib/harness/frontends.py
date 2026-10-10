"""The frontends that `harness` serves, and the loader of their adapters.

Each frontend of FRONTENDS has one module, adapters/<frontend>/adapter.py, which `load` loads by
path, as `install.drift_hook` loads hooks/install-drift.py; `bin/harness` and `sys.path` stay as
they are. FRONTENDS is also the order in which `harness install` plans and installs them. An
adapter defines:

  NAME               the frontend, as FRONTENDS names it; the label of its cases
  TEMPLATES          its templates, relative to the repository, that `harness leaks` renders
  register(sub)      its own verbs
  plan(ctx)          its part of `harness install`, a Plan; it reads the files and writes nothing
  selftest()         its cases, (number of cases, number wrong), each labelled with NAME
  RESTART            the one line, naming the frontend and what to restart, that `harness install`
                     prints after the count line of an --apply in which one of its plan's `files`
                     or `after` changed something

`ctx` holds `args`, the arguments, `--force` of `harness install` among them; `profile`, the
profile; `models`, the path of the model tables; `agents`, the directory of the neutral agents; and
`plans`, the Plan of each frontend planned before this one, by NAME.

An adapter that fails to load exits 2, with its path, its line and the exception's last line,
before any verb runs; so does one that lacks a member of MEMBERS, with its path. No adapter is
skipped.
"""

import importlib.util
import sys
import traceback
import types

from . import REPO, HarnessError

FRONTENDS = ("claude", "opencode", "omp")
MEMBERS = ("NAME", "TEMPLATES", "register", "plan", "selftest", "RESTART")


def Plan(**fields):
    """One frontend's part of `harness install`:

      files        [(destination, bytes, mode, label)], each installed by `install.install_file`;
                   a mode of None leaves the mode as it is, a fifth element True asks for a
                   backup of a file that is replaced, and a sixth is text printed after the
                   file's line when the file is a change
      warnings     [(line, …)], each printed as one WARNING after the files and before the steps
                   of `after`
      extra        the text of each installed file with no source, printed after the steps of
                   `after`
      refused      [((line, …), message)]: the lines are printed before the files, and the install
                   exits 2 with the messages after its count line
      after        [step], each called with `apply` after every frontend's files are installed;
                   it prints its lines and returns its number of changes

    A plan may hold more fields, which the install does not read and a later frontend reads
    through `ctx.plans`: `rules`, [(installed path, source, bytes)] of each file that the plan
    installs below rules/.
    """
    return types.SimpleNamespace(**{"files": [], "warnings": [], "extra": [], "refused": [], "after": [], **fields})


def load():
    """The adapter of each frontend of FRONTENDS, in that order; each is loaded once."""
    adapters = []
    for name in FRONTENDS:
        key = f"harness_adapter_{name}"
        if key not in sys.modules:
            path = REPO / "adapters" / name / "adapter.py"
            spec = importlib.util.spec_from_file_location(key, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            try:
                spec.loader.exec_module(module)
            except (Exception, SystemExit) as e:  # any failure of an adapter's code exits 2, naming the file
                del sys.modules[key]
                # The line in the adapter: a syntax error's own, else the last frame in the file. A
                # file that cannot be read has neither.
                lines = [e.lineno] if isinstance(e, SyntaxError) else [
                    f.lineno for f in traceback.extract_tb(e.__traceback__) if f.filename == str(path)]
                where = f"{path}:{lines[-1]}" if lines else str(path)
                raise HarnessError(f"{where}: {traceback.format_exception_only(e)[-1].strip()}") from None
            missing = [m for m in MEMBERS if not hasattr(module, m)]
            if missing:
                del sys.modules[key]
                raise HarnessError(f"{path}: defines no {', '.join(missing)}, which every adapter defines")
        adapters.append(sys.modules[key])
    return adapters


def adapter(name):
    """The adapter of the frontend `name`."""
    return load()[FRONTENDS.index(name)]
