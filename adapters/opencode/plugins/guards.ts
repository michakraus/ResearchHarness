// OpenCode's guard plugin: each tool call goes to the guard of the Harness, and the plugin applies
// its answer. On each `execute.before` event it runs `<python> <plugins>/../hooks/guard --from
// opencode`, `python` read from guard-paths.json beside this file, sends `{event, directory}` as JSON
// on stdin, and throws the `reason` of an answer that blocks, which refuses the call. The guard holds
// every check: hooks/guard/frontends/opencode.py says what it reads and how it answers. IT FAILS
// CLOSED: a list that is missing or holds no string `python`, a guard that cannot start, exits with
// a status other than 0, prints no valid answer or does not answer within 10 s refuses the call.
// `setup` never throws, since OpenCode skips a plugin whose `setup` throws. JavaScript syntax and no
// import: hooks/probe.py loads a copy of this file under `node`.

const { spawn } = process.getBuiltinModule('node:child_process');
const { readFileSync } = process.getBuiltinModule('node:fs');
const { dirname, join } = process.getBuiltinModule('node:path');
const { fileURLToPath } = process.getBuiltinModule('node:url');
const ID = 'research-harness.guards';
const HERE = dirname(fileURLToPath(import.meta.url));
const TIMEOUT_MS = 10_000;
const CLOSED = `The guard plugin ${ID} (guards.ts) fails closed. Tell the user, and do not run the call in another form.`;

// The guard's answer to `message`: the reason to refuse the call, or null to let it run.
function answer(message) {
  return new Promise((resolve) => {
    const fail = (why) => resolve(`The guard ${why}, so the call is refused. ${CLOSED}`);
    const payload = JSON.stringify(message); // a throw here rejects, which the hook refuses
    let child, got;
    try {
      const python = JSON.parse(readFileSync(join(HERE, 'guard-paths.json'), 'utf8'))?.python;
      if (typeof python !== 'string') return fail('has no interpreter: guard-paths.json holds no string "python"');
      child = spawn(python, [join(HERE, '..', 'hooks', 'guard'), '--from', 'opencode'], { stdio: 'pipe' });
    } catch (e) {
      return fail(`could not start (${e?.message ?? e}); run harness install --apply`);
    }
    const timer = setTimeout(() => (child.kill('SIGKILL'), fail(`did not answer within ${TIMEOUT_MS / 1000} s`)), TIMEOUT_MS);
    let [out, err] = ['', ''];
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err += d));
    child.on('error', (e) => (clearTimeout(timer), fail(`could not start (${e?.message ?? e})`)));
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      if (code !== 0) return fail(signal ? `was stopped by ${signal}` : `exited with status ${code}: ${err.trim().slice(-300)}`);
      try { got = JSON.parse(out); } catch {}
      if (got?.block === false) return resolve(null);
      if (got?.block === true && typeof got.reason === 'string' && got.reason !== '') return resolve(got.reason);
      fail('printed no valid answer');
    });
    child.stdin.on('error', () => {}); // the guard exited before it read; its status decides
    child.stdin.end(payload);
  });
}

export default {
  id: ID,
  async setup(ctx) {
    const directory = typeof ctx?.location?.directory === 'string' ? ctx.location.directory : process.cwd();
    await ctx.tool.hook('execute.before', async (event) => {
      const reason = await answer({ event, directory }).catch((e) => `The guard plugin failed (${e?.message ?? e}). ${CLOSED}`);
      if (reason) throw new Error(reason);
    });
  },
};
