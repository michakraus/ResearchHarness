- **`harness test` runs its cases as parts, each in a process of its own, at most `--jobs N` at
  once, and can run a selection.** The parts are the modules and adapters with cases, seven
  groups of the hook probe (`probe:<group>`), five groups of `doctor`'s cases (`doctor:<group>`)
  and the contract sweep. `harness test NAME ...` runs the named parts, `--changed BASE` the parts
  that own a path of `git diff BASE...HEAD`, and `--list` prints a selection without running it;
  `docs` and `sweep` run in every selection. `--jobs` defaults to half the CPUs, and `--log FILE`
  keeps the full output in a file and prints only the `BAD` lines and the summary. A part that
  crashes or runs longer than 300 s counts as one failed case, and the run goes on. At most two
  runs share a machine, by two `flock` slot files; a third waits. `hooks/probe.py GROUP ...` runs
  single groups of the probe, and with no argument it still runs every group.
