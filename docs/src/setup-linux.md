# Setup on Linux

This page gives the first step of the setup on Linux: the dependencies. The other steps for Linux
are coming. [setup-macos.md](setup-macos.md) gives all the steps for macOS.

## The dependencies

**What it does.** These commands install every required tool that the harness calls, on Debian
or Ubuntu. `apt-get` installs the tools that the distribution packages. actionlint, fatou and
Julia come from their own installers, which their projects give.
[Dependencies](dependencies.md) lists each tool, its minimum version and what the harness uses it
for.

```bash
sudo apt-get update
sudo apt-get install python3 git gh gitleaks nodejs npm shellcheck coreutils rsync curl
mkdir -p ~/.local/bin
bash <(curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) latest ~/.local/bin
curl --proto '=https' --tlsv1.2 -sSf https://fatou.dev/install | sh
curl -fsSL https://install.julialang.org | sh
```

**Without Julia code**, skip the fatou line: fatou checks Julia code only. You still need Julia,
because the first install of the harness runs it once.

The installers of actionlint and fatou put the program into a directory in your home directory;
the actionlint line uses `~/.local/bin`. That directory must be on the `PATH`. The installer of
`juliaup` asks you to confirm its settings; its default settings install `juliaup` and the current
Julia release, and add them to the `PATH` in your shell's start file. Open a new terminal after
it.

**Why.** Each tool has the job that [Dependencies](dependencies.md#what-each-tool-does) describes.
A release of a distribution can package an older version than the minimum that Dependencies
gives, for example of Python, Node.js or gitleaks. Then install that tool from its own site.

**Check.** Each command prints its version. Compare each version with the minimum of
[Dependencies](dependencies.md).

```bash
python3 --version
node --version
gitleaks version
actionlint --version
julia --version
```
