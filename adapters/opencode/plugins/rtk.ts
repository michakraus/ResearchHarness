// RTK for OpenCode — the token-optimised shell proxy.
//
// RTK ships hook processors for Claude Code, Cursor, Gemini, Copilot, Droid and Vibe,
// but NOT for OpenCode. This plugin supplies the missing one. It uses the documented
// dry-run, `rtk hook check <command>`, whose contract is:
//
//     exit 0  -> stdout is the rewritten command      e.g. `cat f.txt` -> `rtk read f.txt`
//     exit 1  -> stdout is "No rewrite for: <command>"
//
// The rewrite set is RTK's own configuration, not this file's. Read it with
// `rtk hook check '<cmd>'` rather than from any list, because it changes without notice.
//
// THE PLUGIN API is OpenCode v2's: a default export `{id, setup(ctx)}`, and a hook on the tool
// registry's `execute.before`. The shell tool is named `shell`, and it reads `event.input` back
// after the hooks, so the rewrite is an assignment to `event.input.command`. The plugin imports
// no module; the Node built-ins come from `process.getBuiltinModule`.
//
// The plugin never fails a command. If RTK is absent, errors, or is slow, the original
// command runs unchanged.
//
// JAVASCRIPT SYNTAX ONLY. hooks/probe.py loads a copy of this file as a module under `node`, which
// may have no TypeScript support, so a type annotation here fails the probe.

const { spawn } = process.getBuiltinModule('node:child_process');

const RTK = 'rtk'; // found on the PATH, as Claude Code's hook runs `rtk hook claude`
const TIMEOUT_MS = 10_000; // the same budget Claude Code gives `rtk hook claude`

function rewrite(command) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => {
      if (!done) {
        done = true;
        resolve(v);
      }
    };

    let child;
    try {
      child = spawn(RTK, ['hook', 'check', command], {
        stdio: ['ignore', 'pipe', 'ignore'],
      });
    } catch {
      return finish(null);
    }

    const timer = setTimeout(() => {
      try {
        child.kill('SIGKILL');
      } catch {
        /* already gone */
      }
      finish(null);
    }, TIMEOUT_MS);

    let out = '';
    child.stdout?.on('data', (d) => (out += d.toString()));
    child.on('error', () => {
      clearTimeout(timer);
      finish(null); // rtk not installed, or not executable
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const text = out.trim();
      // Exit 0 is the only signal that a rewrite happened. The "No rewrite" line
      // comes with exit 1, but test the text too, so a future exit-code change
      // cannot turn that message into a command.
      if (code === 0 && text && !text.startsWith('No rewrite')) finish(text);
      else finish(null);
    });
  });
}

export default {
  id: 'research-harness.rtk',
  async setup(ctx) {
    await ctx.tool.hook('execute.before', async (event) => {
      if (event?.tool !== 'shell') return;
      const command = event.input?.command;
      if (typeof command !== 'string' || command.trim() === '') return;
      const next = await rewrite(command);
      if (next) event.input.command = next;
    });
  },
};
