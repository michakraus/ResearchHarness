"""`<python> <path>/guard --from <frontend>`: run the guard's command line as a module of the
package `guard`, so that its relative imports resolve. Python puts the package's own directory
first on `sys.path` when it runs a directory; that entry becomes the directory that holds the
package, so that no module of the package shadows one of the standard library.
"""

import runpy
import sys
from pathlib import Path

sys.path[0] = str(Path(__file__).resolve().parent.parent)
runpy.run_module("guard.cli", run_name="__main__", alter_sys=True)
