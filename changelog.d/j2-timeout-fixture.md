- **The test set "a side past its time gives no verdict" of `scripts/dispatch-delta-test.jl` names
  its fixture after the test process, and removes the fixture's compiled cache at the end.** The
  fixed name `DDSlow` gave every run the same UUID, so two runs at the same time shared one
  precompile lock file, and the precompilations that the set kills left temporary `jl_*` files in
  the depot's `compiled/` directory of that name. The fixture is now `DDSlow<pid>`, and its
  directory below `compiled/` goes with the run directories at the end of the file.
