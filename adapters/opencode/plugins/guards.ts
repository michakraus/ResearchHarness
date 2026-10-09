// The Claude Code guard hooks for OpenCode.
//
// Four `PreToolUse` hooks on Claude Code's Bash matcher refuse what a permission glob cannot
// express. This plugin runs the same scripts, from ~/.claude/hooks/, on every `shell` call:
//
//     no-blind-stage.py       a `git add` that stages more than the paths it names
//     no-shell-file-write.py  a shell command that writes a file inside a git working tree
//     gh-api-writes.py        a `gh api` write, and a `glab api` DELETE
//     rm-scope.py             a recursive `rm` outside a worktree and `~/Research/.scratch/`,
//                             and a `git rm` outside a worktree or with `--force`
//
// They matter more here than under Claude Code: OpenCode has no sandbox, so nothing stands
// behind them. The scripts are not copied, so there is one source for both harnesses.
//
// THE PLUGIN API is OpenCode v2's: a default export `{id, setup(ctx)}`, and a hook on the tool
// registry's `execute.before`, which gets one mutable event `{tool, sessionID, agent, messageID,
// id, input}`. The shell tool is named `shell`; its `input` holds `command`, `workdir`, `timeout`
// and `background`. A throw in the hook fails the tool call with its message. The plugin imports
// no module: OpenCode resolves `@opencode/plugin` from its binary only, and the Node built-ins
// come from `process.getBuiltinModule`.
//
// THE CONTRACT is Claude Code's. The plugin sends `{"tool_input": {"command": …}, "cwd": …}`
// on stdin and reads the answer:
//
//     exit 2                                -> refuse; stderr is the reason the model sees
//     exit 0, an "ask" or "deny" decision   -> refuse too, with the reason (see below)
//     exit 0, no output or another decision -> the command runs
//     another exit, output that is not JSON,
//     a script that cannot start, a timeout -> refuse
//
// IT FAILS CLOSED, where Claude Code lets a failed hook pass: Claude Code's sandbox stands behind
// its hooks, and nothing stands behind this plugin. A path list beside this file that is missing
// or not JSON refuses every `shell` call too. One case stays open: a plugin whose `setup` throws, or that
// does not load, is logged as `failed to load plugin`, and the session starts without it. So
// `setup` never throws, and hooks/probe.py loads this file before an install.
//
// "ASK" BECOMES A REFUSAL. The plugin does not make OpenCode prompt the user, and an "ask" that
// let the command run would remove the control. So the model is told to ask in chat and to
// leave the command for the user.
//
// ORDER. OpenCode activates the plugins of a directory in the order of their paths, and runs the
// hooks of one event in that order: env.ts, then guards.ts, then rtk.ts. The order follows the
// file names, so the guards still check a command both as given and with a leading `rtk `
// removed: the guard scripts do not know `rtk`.
//
// THE PATH GUARD. A `read` deny and `external_directory` bind the file tools only: `cat` of
// the same path runs. So the absolute and home paths a command names are checked against
// `guard-paths.json` beside this file — the `read` denies, written by
// `harness permissions --apply` — and against `$OPENCODE_CONFIG_DIR/guard-paths.json`
// when that exists. A list with `allow` refuses every path outside it, as `external_directory`
// with `"*": deny` does. A path is checked as named; a directory that holds a denied path is
// refused too when the command recurses (`grep -r`, `find`, `rg`, …), globs it, or `cd`s into it.
// It is a text check: a path that the command builds at run time (`joinpath(homedir(), …)`),
// or a relative path, passes it. Only an OS sandbox closes that.
//
// THE IN-PLACE EDIT MESSAGE. `sed -i`, `perl -pi` and their kin are already `deny` rules. A deny
// returns OpenCode's list of matching rules, about 18,800 characters, into the context. The
// guard refuses the same commands first, with a short message.
//
// JAVASCRIPT SYNTAX ONLY. hooks/probe.py loads a copy of this file as a module under `node`, which
// may have no TypeScript support, so a type annotation here fails the probe.

const { spawn } = process.getBuiltinModule('node:child_process');
const { readFileSync } = process.getBuiltinModule('node:fs');
const { homedir } = process.getBuiltinModule('node:os');
const { dirname, join, posix } = process.getBuiltinModule('node:path');
const { fileURLToPath } = process.getBuiltinModule('node:url');

const ID = 'research-harness.guards';
const HOOKS = join(homedir(), '.claude', 'hooks');
const GUARDS = ['no-blind-stage.py', 'no-shell-file-write.py', 'gh-api-writes.py', 'rm-scope.py'];
const TIMEOUT_MS = 10_000;
const CLOSED = `The guard plugin ${ID} (guards.ts) fails closed. Tell the user, and do not run the command in another form.`;

// The reason `script` refuses `payload`, or null when it lets the command run.
function run(script, payload) {
  return new Promise((resolve) => {
    let done = false;
    let child = null;
    const finish = (reason) => {
      if (!done) {
        done = true;
        clearTimeout(timer);
        resolve(reason);
      }
    };
    const failed = (why) => finish(`The guard ${script} ${why}, so the command is refused. ${CLOSED}`);

    const timer = setTimeout(() => {
      try {
        child?.kill('SIGKILL');
      } catch {
        /* already gone */
      }
      failed(`did not answer within ${TIMEOUT_MS / 1000} s`);
    }, TIMEOUT_MS);

    try {
      child = spawn(join(HOOKS, script), [], { stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (e) {
      return failed(`could not start (${e?.message ?? e})`);
    }

    let out = '';
    let err = '';
    child.stdout.on('data', (d) => (out += d.toString()));
    child.stderr.on('data', (d) => (err += d.toString()));
    child.on('error', (e) => failed(`could not start (${e?.message ?? e})`)); // missing, or not executable
    child.on('close', (code, signal) => {
      if (code === 2) return finish(err.trim() || `${script} refused the command.`);
      if (code !== 0)
        return failed(signal ? `was stopped by ${signal}` : `exited with status ${code}: ${err.trim().slice(-300)}`);
      if (out.trim() === '') return finish(null);
      let hook;
      try {
        hook = JSON.parse(out)?.hookSpecificOutput;
      } catch {
        return failed('printed output that is not JSON');
      }
      if (hook?.permissionDecision === 'ask' || hook?.permissionDecision === 'deny')
        return finish(
          `${hook.permissionDecisionReason ?? script}\n\n` +
            'This command needs the approval of the user, and OpenCode cannot ask for it ' +
            'from a plugin. Do not run it in another form. Ask the user in chat, and give ' +
            'the user the command to run.',
        );
      finish(null);
    });
    child.stdin.on('error', () => {
      /* the script exited before it read its input; its exit status decides */
    });
    child.stdin.end(payload);
  });
}

const HOME = homedir();

// OpenCode's path globs: `**` any depth, `*` and `?` within one segment. `X/**` covers X too.
function rule(glob) {
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*' && glob[i + 1] === '*') {
      i++;
      if (glob[i + 1] === '/') {
        i++;
        re += '(?:.*/)?';
      } else re += '.*';
    } else if (c === '*') re += '[^/]*';
    else if (c === '?') re += '[^/]';
    else re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  if (re.endsWith('/.*')) re = re.slice(0, -3) + '(?:/.*)?';
  const g = glob.search(/[*?]/);
  const prefix = g < 0 ? glob : glob.slice(0, glob.lastIndexOf('/', g));
  return { glob, re: new RegExp('^' + re + '$'), prefix };
}

function load(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

// Read once, when OpenCode loads the plugin. A list beside this file that cannot be used is an
// error text, which the hook throws on every `shell` call, rather than run with no credential
// guard. A list in `$OPENCODE_CONFIG_DIR` that is not JSON is ignored, as under v1 (K26).
function lists() {
  const here = dirname(fileURLToPath(import.meta.url));
  const global = load(join(here, 'guard-paths.json'));
  if (!Array.isArray(global?.deny))
    return `The path guard has no list: ${join(here, 'guard-paths.json')} is missing or not JSON. ${CLOSED} Run harness install --apply.`;
  const dir = process.env.OPENCODE_CONFIG_DIR;
  const local = dir ? load(join(dir, 'guard-paths.json')) : null;
  return {
    allow: local?.allow ? local.allow.map(rule) : null,
    deny: [...global.deny, ...(local?.deny ?? [])].map(rule),
  };
}

// An absolute path under a directory that holds user data, or a home path.
const PATH = /(?:^|[\s'"`=(:,[{<>])((?:~|\$HOME|\$\{HOME\})(?=[/\s'"`;|&)]|$)[^\s'"`;|&<>(){}[\],]*|\/(?:Users|Volumes|private|var|tmp|etc)(?:\/[^\s'"`;|&<>(){}[\],]*)?)/g;
const RECURSIVE = /\b(?:find|rg|tree|du|tar|zip|rsync|walkdir|readdir)\b|\b(?:grep|egrep|ls|cp|chmod|chown)\b[^|;&\n]*\s(?:--recursive\b|-[A-Za-z]*[rR])/;
const INPLACE = /^(?:rtk\s+)?(?:(?:sed|gsed)\s+(?:-i|--in-place)|awk\s+-i|perl\s+-p?i)/;

function absolute(raw) {
  const p = raw.replace(/^(?:~|\$HOME|\$\{HOME\})/, HOME);
  const n = posix.normalize(p);
  return n.length > 1 ? n.replace(/\/+$/, '') : n;
}

function within(p, path) {
  return p.re.test(path);
}

// The first path of `command` that `l` refuses, with the rule; null when every path passes.
function refusedPath(command, l) {
  const recursive = RECURSIVE.test(command);
  for (const m of command.matchAll(PATH)) {
    const raw = m[1];
    let path = absolute(raw);
    let wide = recursive || new RegExp(`\\bcd\\s+['"]?${raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`).test(command);
    const g = path.search(/[*?[]/);
    if (g >= 0) {
      path = path.slice(0, path.lastIndexOf('/', g)) || '/';
      wide = true;
    }
    const under = path === '/' ? '/' : path + '/';
    for (const d of l.deny) {
      if (within(d, path)) return `${path} — it matches the deny rule ${d.glob}`;
      if (wide && d.prefix.startsWith('/') && d.prefix.startsWith(under))
        return `${path} — the command reaches into it, and it holds ${d.prefix}, which the deny rule ${d.glob} covers`;
    }
    if (l.allow && !l.allow.some((a) => within(a, path)))
      return `${path} — it is outside the paths this session may use: ${l.allow.map((a) => a.glob).join(', ')}`;
  }
  return null;
}

function inPlaceEdit(command) {
  return command.split(/&&|\|\||[;|\n]/).some((part) => INPLACE.test(part.trim()));
}

// The reason to refuse the `shell` call of `event`, or null to let it run. `directory` is the
// session's directory, the working directory of a call with no `workdir`.
async function check(event, l, directory) {
  const command = event.input?.command;
  if (typeof command !== 'string' || command.trim() === '') return null;
  if (typeof l === 'string') return l;
  // A `workdir` is a `cd` the command does not spell.
  const workdir = event.input.workdir;
  const refused = refusedPath(typeof workdir === 'string' ? `cd '${workdir}' && ${command}` : command, l);
  if (refused)
    return `Refused by the path guard: ${refused}. Use only the paths your task names. Do not reach this path in another form.`;
  if (inPlaceEdit(command))
    return 'Refused: an in-place shell edit (sed -i, perl -pi, awk -i). Change a file with the edit tool, or write a new file with the write tool.';
  const cwd = typeof workdir === 'string' ? workdir : directory;
  const forms = [command];
  if (command.startsWith('rtk ')) forms.push(command.slice(4));
  for (const form of forms) {
    const payload = JSON.stringify({ tool_input: { command: form }, cwd });
    for (const script of GUARDS) {
      const reason = await run(script, payload);
      if (reason) return reason;
    }
  }
  return null;
}

export default {
  id: ID,
  async setup(ctx) {
    let l;
    try {
      l = lists();
    } catch (e) {
      l = `The path guard cannot use its list (${e?.message ?? e}). ${CLOSED} Run harness install --apply.`;
    }
    const location = ctx?.location?.directory;
    const directory = typeof location === 'string' ? location : process.cwd();
    await ctx.tool.hook('execute.before', async (event) => {
      if (event?.tool !== 'shell') return;
      let reason;
      try {
        reason = await check(event, l, directory);
      } catch (e) {
        reason = `The guard plugin failed (${e?.message ?? e}). ${CLOSED}`;
      }
      if (reason) throw new Error(reason);
    });
  },
};
