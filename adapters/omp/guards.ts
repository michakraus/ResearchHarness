// oh-my-pi's guard extension: each tool call goes to the guard of the Harness, and the extension
// returns its answer. On each `tool_call` event it runs `<python> <extensions>/../hooks/guard --from
// omp`, `python` read from guard-paths.json beside this file, sends `{event, cwd, agent: {kind}}` as
// JSON on stdin, and returns an answer that blocks, `{block: true, reason}`, which oh-my-pi applies.
// The guard holds every check: hooks/guard/frontends/omp.py says what it reads and how it answers.
// IT FAILS CLOSED: a list that is missing or holds no string `python`, a guard that cannot start,
// exits with a status other than 0, prints no valid answer or does not answer within 10 s blocks
// the call, and so does an error of the handler. An extension that does not load is skipped, so
// hooks/probe.py loads a copy of this file under `node`, which needs JavaScript syntax only.

import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const TIMEOUT_MS = 10_000;
const CLOSED = 'The guard extension fails closed. Tell the user, and do not run the call in another form.';

// The guard's answer to `message`: the reason to block the call, or null to let it run.
function answer(message) {
  return new Promise((resolve) => {
    const fail = (why) => resolve(`The guard ${why}, so the call is blocked. ${CLOSED}`);
    const payload = JSON.stringify(message); // a throw here rejects, which the handler blocks
    let child, got;
    try {
      const python = JSON.parse(readFileSync(join(HERE, 'guard-paths.json'), 'utf8'))?.python;
      if (typeof python !== 'string') return fail('has no interpreter: guard-paths.json holds no string "python"');
      child = spawn(python, [join(HERE, '..', 'hooks', 'guard'), '--from', 'omp'], { stdio: 'pipe' });
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

export default function guards(pi) {
  pi.on('tool_call', async (event, ctx) => {
    const message = { event, cwd: typeof ctx?.cwd === 'string' ? ctx.cwd : process.cwd(), agent: { kind: ctx?.agent?.kind } };
    const reason = await answer(message).catch((e) => `The guard extension failed (${e?.message ?? e}), so the call is blocked. ${CLOSED}`);
    return reason ? { block: true, reason } : undefined;
  });
}
