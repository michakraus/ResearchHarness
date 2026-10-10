// The guard extension of oh-my-pi: the Claude Code guard hooks, and the path list.
//
// oh-my-pi's `bash.patterns` in config.yml refuse what a glob can express. This extension checks
// what a glob cannot, on each `tool_call`:
//
//     bash   the four guard scripts below, and the path list on the words of the command, on
//            its `cwd` and on the working directory
//     read   the path list on its `path`
//     grep   the path list on its `path`, and on a directory that holds a denied path
//     edit   the edit list, then the ask list, on each path it names: `path`, a `rename`, the
//            file headers of `input`
//     write  the edit list, then the ask list, on its `path`, and on the path of a hashline
//            header `[path#TAG]` in it
//
//     no-blind-stage.py       a `git add` that stages more than the paths it names
//     no-shell-file-write.py  a shell command that writes a file inside a git working tree
//     gh-api-writes.py        a `gh api` write, and a `glab api` DELETE
//     rm-scope.py             a recursive `rm` outside the scratch zones, and a `git rm` outside a
//                             worktree
//
// The scripts run from oh-my-pi's own copy in hooks/ beside extensions/, which `harness install`
// writes from the same source as Claude Code's. Each runs with `python3` from PATH and gets Claude Code's payload on stdin,
// `{"tool_input": {"command": …}, "cwd": …}`.
//
// IT FAILS CLOSED, as OpenCode's guards.ts does, where Claude Code lets a failed hook pass:
//
//     exit 2                                       -> blocked; stderr is the reason the model sees
//     exit 0, an "ask" or "deny" decision          -> blocked, with the reason (see below)
//     exit 0, no output or another decision        -> the call runs
//     another exit, output that is not JSON,
//     a script that cannot run, or a timeout       -> blocked
//
// A path list that is missing, or whose `deny` is not a list of strings, blocks every call that
// the extension checks; an `edit` or an `ask` that is not a list of strings blocks every `edit`
// and `write` call. An error of the handler itself blocks the call. oh-my-pi also blocks the call
// when a handler throws or exceeds `extensionHandlers.toolCallTimeoutMs`. One case stays open: an
// extension that does not load, a syntax error say, is reported by oh-my-pi and skipped, and then
// no line of this file runs. The probe in hooks/probe.py loads this file, so it catches that
// before an install.
//
// "ASK" BECOMES A REFUSAL, as in OpenCode's guards.ts: the model is told to ask in chat and to
// leave the command to the user. So does an `edit` or `write` path that the ask list matches.
//
// THE PATH LIST is guard-paths.json beside this file, as `harness install` renders it: under
// `deny` the `read` denies of the settings template, under `edit` its `Edit` and `Write` denies,
// under `ask` its `Edit` and `Write` asks. `edit` gets ~/.omp/**, oh-my-pi's own directory, where
// its credentials and this file lie, and `deny` the same but the copies of the skills, the rules
// and the instructions. A path that both `edit` and `ask` match is
// refused as a deny. oh-my-pi has no path policy of its own. A tool path is checked as named,
// after `@`, `file://`, `~` and a selector suffix `:…` are removed, relative to the working
// directory; each part of a path list that `,`, `;` or a space separates is checked too. A bash
// command is split into words as the shell splits them, quotes removed, and each word is checked
// as a path relative to its `cwd`, else the working directory, and so is each part of a word that
// `=`, `:` or `,` separates. The match ignores case, as the default macOS file system does. For
// `grep`, and for a command that recurses, globs or `cd`s, a directory that holds a denied path is
// refused as well.
//
// It is a text check, with known gaps: a path that a command builds at run time passes it;
// a `grep` or a recursive command reaches the files below a directory that a `**/` rule, such as
// `**/.env`, covers; the `find` and `ast_grep` tools are not checked; and the forms that
// KNOWN_ISSUES.md K13, K14 and K16 name pass it. So this check prevents accidents and does not
// contain. oh-my-pi is not used before the sandbox launcher exists; the launcher's profile then
// checks the real path.
//
// JAVASCRIPT SYNTAX ONLY. hooks/probe.py loads a copy of this file as a module under `node`, which
// may have no TypeScript support, so a type annotation here fails the probe.

import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, posix } from 'node:path';
import { fileURLToPath } from 'node:url';

const HOME = homedir();
const HOOKS = join(dirname(fileURLToPath(import.meta.url)), '..', 'hooks');
const GUARDS = ['no-blind-stage.py', 'no-shell-file-write.py', 'gh-api-writes.py', 'rm-scope.py'];
const TIMEOUT_MS = 10_000;
const LIST = join(dirname(fileURLToPath(import.meta.url)), 'guard-paths.json');
const CLOSED = 'The guard extension fails closed. Tell the user, and do not run the call in another form.';
const ASK_USER = 'Ask the user in chat';

// The reason `script` refuses `payload`, or null when it lets the call run.
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
    const failed = (why) => finish(`The guard ${script} ${why}, so the call is blocked. ${CLOSED}`);
    const timer = setTimeout(() => {
      try {
        child?.kill('SIGKILL');
      } catch {
        /* already gone */
      }
      failed(`did not answer within ${TIMEOUT_MS / 1000} s`);
    }, TIMEOUT_MS);
    // python3 exits 2 on a script it cannot open, which reads as the script's own refusal.
    if (!existsSync(join(HOOKS, script))) return failed(`is missing from ${HOOKS}`);
    try {
      child = spawn('python3', [join(HOOKS, script)], { stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (e) {
      return failed(`could not run (${e?.message ?? e})`);
    }
    let out = '';
    let err = '';
    child.stdout.on('data', (d) => (out += d.toString()));
    child.stderr.on('data', (d) => (err += d.toString()));
    child.on('error', (e) => failed(`could not run (${e?.message ?? e})`));
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
            'This command needs the approval of the user, and this extension does not ask for it. ' +
            `Do not run it in another form. ${ASK_USER}, and give the user the command to run.`,
        );
      finish(null);
    });
    child.stdin.on('error', () => {
      /* the script exited before it read its input; its exit status decides */
    });
    child.stdin.end(payload);
  });
}

// OpenCode's path globs: `**` any depth, `*` and `?` within one segment. `X/**` covers X too.
// The match ignores case. `kind` names the list in a refusal: "deny" or "ask".
function rule(glob, kind = 'deny') {
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
  return { glob, re: new RegExp('^' + re + '$', 'i'), prefix, kind };
}

// oh-my-pi's own directory as a `deny` rule, except the copies that `harness install` writes for
// the model to read: agent/skills/, agent/rules/, agent/instructions/ and agent/RTK.md. `edit` and
// `write` get the whole directory.
const OWN = posix.join(HOME, '.omp');
const OWN_READABLE = {
  glob: `${OWN}/** but agent/skills, agent/rules, agent/instructions and agent/RTK.md`,
  re: new RegExp(
    '^' + OWN.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
      '(?:/(?!agent/(?:(?:skills|rules|instructions)(?:/|$)|RTK\\.md$)).*)?$',
    'i',
  ),
  prefix: OWN,
  kind: 'deny',
};

// The rules of the path list, read once when oh-my-pi loads the extension: `deny` for `read`,
// `grep` and `bash`, `edit` for `edit` and `write`, each with oh-my-pi's own directory added, and
// `ask` for `edit` and `write`; a string in place of a list that cannot be used.
function pathRules() {
  const unusable = (why) =>
    `The path list ${LIST} cannot be used (${why}), so the call is blocked. ${CLOSED} Run harness install --apply.`;
  let list;
  try {
    list = JSON.parse(readFileSync(LIST, 'utf8'));
  } catch (e) {
    const why = unusable(e?.message ?? e);
    return { deny: why, edit: why, ask: why };
  }
  const rules = (key, kind = 'deny', own = [rule(posix.join(HOME, '.omp', '**'), kind)]) => {
    const globs = list?.[key];
    if (!Array.isArray(globs) || !globs.every((g) => typeof g === 'string'))
      return unusable(`it holds no list of strings under "${key}"`);
    return [...globs.map((g) => rule(g, kind)), ...own];
  };
  const deny = rules('deny', 'deny', [OWN_READABLE]);
  if (typeof deny === 'string') return { deny, edit: deny, ask: deny };
  return { deny, edit: rules('edit'), ask: rules('ask', 'ask', []) };
}

const { deny: DENY, edit: EDIT, ask: ASK } = pathRules();

// `raw` as an absolute, normalised path: a home form expanded, a relative path joined to `cwd`.
function absolute(raw, cwd) {
  let p = raw;
  if (/^(?:~|\$HOME|\$\{HOME\})(?=\/|$)/.test(p)) p = p.replace(/^(?:~|\$HOME|\$\{HOME\})/, HOME);
  else if (!p.startsWith('/')) p = posix.join(cwd, p);
  const n = posix.normalize(p);
  return n.length > 1 ? n.replace(/\/+$/, '') : n;
}

// The rule of `rules` that refuses `path`, absolute, with the reason; null when none does. `wide`:
// the call reaches below `path`, so a directory that holds a denied path is refused too.
function refusedAt(path, wide, rules = DENY) {
  const g = path.search(/[*?[]/);
  if (g >= 0) {
    path = path.slice(0, path.lastIndexOf('/', g)) || '/';
    wide = true;
  }
  const under = (path === '/' ? '/' : path + '/').toLowerCase();
  for (const d of rules) {
    if (d.re.test(path)) return `${path} — it matches the ${d.kind} rule ${d.glob}`;
    if (wide && d.prefix.startsWith('/') && d.prefix.toLowerCase().startsWith(under))
      return `${path} — the call reaches into it, and it holds ${d.prefix}, which the ${d.kind} rule ${d.glob} covers`;
  }
  return null;
}

// An absolute path under a directory that holds user data, or a home path.
const PATH = /(?:^|[\s'"`=(:,[{<>])((?:~|\$HOME|\$\{HOME\})(?=[/\s'"`;|&)]|$)[^\s'"`;|&<>(){}[\],]*|\/(?:Users|Volumes|private|var|tmp|etc|home)(?:\/[^\s'"`;|&<>(){}[\],]*)?)/g;
const RECURSIVE = /\b(?:find|rg|tree|du|tar|zip|rsync|walkdir|readdir)\b|\b(?:grep|egrep|ls|cp|chmod|chown)\b[^|;&\n]*\s(?:--recursive\b|-[A-Za-z]*[rR])/;

// The first path of `command` that the list refuses, with the rule; null when every path passes.
function refusedCommand(command) {
  const recursive = RECURSIVE.test(command);
  for (const m of command.matchAll(PATH)) {
    const raw = m[1];
    const cd = new RegExp(`\\bcd\\s+['"]?${raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`).test(command);
    const refused = refusedAt(absolute(raw, '/'), recursive || cd);
    if (refused) return refused;
  }
  return null;
}

// The words of `command` as the shell splits them, quotes and backslashes removed, each with the
// word before it in its simple command and the number of that simple command. A redirection ends a
// word; a control operator, a parenthesis, a backquote and a newline also end the simple command.
function words(command) {
  const out = [];
  let word = null;
  let prev = null;
  let seg = 0;
  const end = () => {
    if (word !== null) {
      out.push({ word, prev, seg });
      prev = word;
    }
    word = null;
  };
  for (let i = 0; i < command.length; i++) {
    const c = command[i];
    if (c === "'") {
      const j = command.indexOf("'", i + 1);
      const k = j < 0 ? command.length : j;
      word = (word ?? '') + command.slice(i + 1, k);
      i = k;
    } else if (c === '"') {
      let s = '';
      for (i++; i < command.length && command[i] !== '"'; i++)
        s += command[i] === '\\' && i + 1 < command.length ? command[++i] : command[i];
      word = (word ?? '') + s;
    } else if (c === '\\' && i + 1 < command.length) word = (word ?? '') + command[++i];
    else if (c === '\n' || ';&|()`'.includes(c)) {
      end();
      prev = null;
      seg++;
    } else if (/\s/.test(c) || c === '<' || c === '>') end();
    else word = (word ?? '') + c;
  }
  end();
  return out;
}

// The words before a command name that leave it the command.
const LEAD = new Set([null, '{', '!', 'then', 'do', 'else', 'builtin', 'command']);

// The first word of `command`, or part of a word, that the list refuses as a path relative to
// `dir`; null when every word passes. Each argument of a `cd` or `pushd` is checked wide. One with
// no directory, or with `-`, moves home or to a directory the command does not name, so the home
// directory is checked wide.
function refusedWords(command, dir) {
  const recursive = RECURSIVE.test(command);
  const list = words(command);
  const cds = new Set();
  for (const [i, { word, prev, seg }] of list.entries()) {
    if ((word !== 'cd' && word !== 'pushd') || !LEAD.has(prev)) continue;
    cds.add(seg);
    const to = list.slice(i + 1).filter((w) => w.seg === seg && !/^-./.test(w.word));
    const refused = (to.length === 0 || to[0].word === '-') && refusedAt(absolute('~', dir), true);
    if (refused) return `${refused} (a ${word} with no directory, or with -, goes there)`;
  }
  for (const { word, prev, seg } of list) {
    const wide = recursive || cds.has(seg) || prev === 'cd' || prev === 'pushd';
    for (const part of new Set([word, ...word.split(/[=:,]/)])) {
      const refused = part && refusedAt(absolute(part, dir), wide);
      if (refused) return refused;
    }
  }
  return null;
}

// A header path as oh-my-pi's hashline parser reads it: trimmed, a `#TAG` removed, then one pair
// of quotes around it removed.
function headerPath(s) {
  const t = s.trim();
  const tag = /#[0-9A-Fa-f]{4}$/.exec(t);
  const p = tag ? t.slice(0, tag.index) : t;
  return p.length >= 2 && (p[0] === '"' || p[0] === "'") && p[0] === p[p.length - 1] ? p.slice(1, -1) : p;
}

// The paths an `edit` call names: `path`, the `rename` of each of its `edits`, and the file
// headers of a hashline or apply_patch `input` — `[path#TAG]`, `MV path`, `*** Add File: path`
// and its kin, and `*** Move to: path`. A hashline header needs no closing `]`, as in oh-my-pi; it
// is checked as written, with its tag removed, and as oh-my-pi reads it.
function editPaths(input) {
  const paths = [];
  if (typeof input.path === 'string') paths.push(input.path);
  if (Array.isArray(input.edits))
    for (const e of input.edits) if (typeof e?.rename === 'string') paths.push(e.rename);
  if (typeof input.input === 'string')
    for (const line of input.input.split('\n')) {
      const t = line.trim();
      const m =
        /^\[(.*?)\]?$/.exec(t) ??
        /^MV\s+(.+)$/.exec(t) ??
        /^\*\*\*\s*(?:(?:Add|Update|Delete|Edit)\s+File|Move\s+to)\s*:\s*(.+)$/i.exec(t);
      if (m) paths.push(m[1], m[1].replace(/#[^#/]*$/, ''), headerPath(m[1]));
    }
  return paths;
}

// The path oh-my-pi's `write` tool writes for `raw`: a hashline header `[path]` or `[path#TAG]`
// unwrapped, as its unwrapHashlineHeaderPath does; else `raw`.
function writePath(raw) {
  const t = raw.trimEnd();
  if (t.length < 2 || t[0] !== '[' || t[t.length - 1] !== ']') return raw;
  const s = t.slice(1, -1);
  const tag = /#[0-9A-Fa-f]{4}$/.exec(s);
  const p = tag ? s.slice(0, tag.index) : s;
  return p === '' || (!tag && p.includes('#')) ? raw : p;
}

// The first form of the tool path `raw` that `rules` refuse; null when every form passes.
function refusedToolPath(raw, cwd, wide, rules = DENY) {
  for (const piece of new Set([raw, ...raw.split(/[,;\s]+/)])) {
    let p = piece.trim().replace(/^[@:](?=[/~])/, '');
    if (p === '') continue;
    if (/^file:\/\//i.test(p)) {
      try {
        p = fileURLToPath(p);
      } catch {
        /* not a file URL after all; checked as written */
      }
    }
    for (const form of new Set([p, p.replace(/:[^/]*$/, '')])) {
      const refused = form && refusedAt(absolute(form, cwd), wide, rules);
      if (refused) return refused;
    }
  }
  return null;
}

// The reason to block `event`, or null to let it run.
async function check(event, ctx) {
  const tool = event?.toolName;
  if (!['bash', 'read', 'grep', 'edit', 'write'].includes(tool)) return null;
  if (typeof DENY === 'string') return DENY;
  const input = event.input ?? {};
  const cwd = typeof ctx?.cwd === 'string' ? ctx.cwd : process.cwd();
  const pathRefusal = (refused) =>
    `Refused by the path guard: ${refused}. Use only the paths your task names. Do not reach this path in another form.`;

  if (tool === 'edit' || tool === 'write') {
    if (typeof EDIT === 'string') return EDIT;
    if (typeof ASK === 'string') return ASK;
    const paths =
      tool === 'edit' ? editPaths(input) : typeof input.path === 'string' ? [input.path, writePath(input.path)] : [];
    if (paths.length === 0) return `The ${tool} call names no path, so the path guard cannot check it. ${CLOSED}`;
    // Every path against the deny rules first, so that a path under a deny and an ask gets the deny.
    for (const path of paths) {
      const refused = refusedToolPath(path, cwd, false, EDIT);
      if (refused) return pathRefusal(refused);
    }
    for (const path of paths) {
      const refused = refusedToolPath(path, cwd, false, ASK);
      if (refused)
        return (
          `Refused by the path guard: ${refused}. This ${tool} needs the approval of the user, and this ` +
          'extension does not ask for it. Do not make the change in another form. ' +
          `${ASK_USER}, and give the user the change to make.`
        );
    }
    return null;
  }

  if (tool === 'read' || tool === 'grep') {
    const path = input.path ?? (tool === 'grep' ? cwd : undefined);
    if (typeof path !== 'string') return `The ${tool} call names no path, so the path guard cannot check it. ${CLOSED}`;
    const refused = refusedToolPath(path, cwd, tool === 'grep');
    return refused ? pathRefusal(refused) : null;
  }

  const command = input.command;
  if (typeof command !== 'string') return `The bash call holds no command, so the guards cannot check it. ${CLOSED}`;
  // A `cwd` is a `cd` the command does not spell, so the call reaches below it; the session's
  // working directory is reached below only by a command that recurses.
  const moved = typeof input.cwd === 'string';
  const dir = moved ? absolute(input.cwd, cwd) : absolute(cwd, '/');
  const refused =
    refusedAt(dir, moved || RECURSIVE.test(command)) ?? refusedCommand(command) ?? refusedWords(command, dir);
  if (refused) return pathRefusal(refused);
  const payload = JSON.stringify({ tool_input: { command }, cwd: moved ? dir : cwd });
  const verdicts = await Promise.all(GUARDS.map((script) => run(script, payload)));
  return verdicts.find((v) => v !== null) ?? null;
}

export default function guards(pi) {
  pi.on('tool_call', async (event, ctx) => {
    let reason;
    try {
      reason = await check(event, ctx);
    } catch (e) {
      reason = `The guard extension failed (${e?.message ?? e}), so the call is blocked. ${CLOSED}`;
    }
    return reason ? { block: true, reason } : undefined;
  });
}
