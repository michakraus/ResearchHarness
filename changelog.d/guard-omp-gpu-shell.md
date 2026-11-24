- **Under `agentbox`, oh-my-pi's guard refuses a shell `julia` run that names a GPU package.** The
  shell there has no GPU, so such a run cannot answer, and oh-my-pi ran shell `julia` device probes
  after Kaimon failed, although its rules give no shell route for GPU code. The new check
  `gpu_shell.py` reads the command and the first 1 MiB of each `.jl` file that the `julia` run
  names, and its reason names the Kaimon route and says to report the failure and stop when Kaimon
  does not answer. It runs in oh-my-pi's table alone. A shell `Pkg.test` of a package with a GPU
  dependency passes (K192), the check follows no `include` and no `cd` before a relative script
  path (K193), and it passes a `julia` run that shell syntax, a wrapper outside its list or
  `env -S` puts ahead of `julia` (K194).
