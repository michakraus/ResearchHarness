// Environment variables for shell commands — the OpenCode equivalent of Claude Code's
// `env` block in ~/.claude/settings.json.
//
// OpenCode has NO `env` key in its configuration. The shell's `create.before` plugin hook is the
// only place to set a variable that every shell command should see, so the one setting that
// matters here lives in this file. The hook gets one mutable event `{command, cwd, timeout,
// shell, env}`, with `env` a copy of the process environment, and the spawn uses `event.env`.
//
// JULIA_PKG_USE_CLI_GIT=true
//   Pkg uses the `git` binary instead of libgit2. libgit2 fails against some GitLab
//   remotes with a credential error that reads like an authentication problem but is a TLS
//   negotiation one. Claude Code sets this in settings.json; without it here, a `Pkg.add`
//   or `Pkg.instantiate` against those remotes behaves differently under the two harnesses.
//
// NOT ported: CLAUDE_CODE_MAX_OUTPUT_TOKENS. It configures Claude Code's own model call and
// has no meaning for OpenCode, which uses `tool_output.max_lines` / `max_bytes` instead.
//
// THE PLUGIN API is OpenCode v2's: a default export `{id, setup(ctx)}`. JAVASCRIPT SYNTAX ONLY:
// hooks/probe.py loads a copy of this file as a module under `node`.

export default {
  id: 'research-harness.env',
  async setup(ctx) {
    await ctx.shell.hook('create.before', async (event) => {
      event.env.JULIA_PKG_USE_CLI_GIT = 'true';
    });
  },
};
