#!/usr/bin/env python3
"""Run the case battery for the hooks in this directory, one subprocess call per case.

Each case is checked on its own and printed on its own line, so a passing total cannot
hide a case that went the wrong way. Exit status is 1 when any case is wrong.

    ./probe.py

A case is (script, command, expected exit). Exit 2 refuses the call; exit 0 lets it
through. The fail-open block at the end matters more than the refusals: a `PreToolUse`
hook on the `Bash` matcher runs before every shell command in every session, so an input
its author did not foresee must exit 0.

The hooks run against a fixture `HOME`, never the real one, so the cases mean the same on
every machine and in CI. Each Python hook runs with this interpreter, `sys.executable`, not
with its shebang, and each call has a timeout.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HOOKS = os.path.dirname(os.path.abspath(__file__)) + "/"

# The fixture: one temporary directory per run, removed on exit, also after a failure. The
# hooks get it as `HOME` with exactly two leading slashes. `no-shell-file-write.py` exempts
# every path whose text begins with `/tmp/`, `/var/folders/` or `$TMPDIR` as a scratch root,
# and so a fixture `HOME` spelt there with one slash; `os.path.normpath` keeps a leading `//`,
# so the hook sees the fixture `HOME` as it sees a real one. macOS and Linux resolve `//` as `/`.
# `HOME` is one level below the temporary directory, so its parent is that directory and never
# `/tmp` itself, which holds the scratch paths of the `rm-scope` cases.
FIXTURE = tempfile.TemporaryDirectory(prefix="harness-probe-")
HOME = "/" + FIXTURE.name + "/home"
R = HOME + "/Research"
WT = R + "/.worktrees/Foo-bar"
PKG = R + "/Packages/Example"
# The working directory of the cases: a git work tree of the fixture, whose `.gitignore` ignores
# `__pycache__/`, never this checkout. A checkout below `/tmp/` or `$TMPDIR` is scratch to
# `no-shell-file-write.py`, which would then let every write of the cases through.
TOOL = R + "/Harness"
CWD = TOOL + "/hooks/"
# No `GIT_*` variable of the caller: a `GIT_DIR`, as git exports it to a hook, would send the
# fixture's git commands and the hooks' to the caller's repository.
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV = {**CLEAN, "HOME": HOME}
q = shlex.quote  # a fixture path spliced into a command, for a `$TMPDIR` with a space
TIMEOUT = 30  # seconds per hook call; a timeout is a wrong case

WRITE = HOOKS + "no-shell-file-write.py"
SANDBOX = HOOKS + "sandbox-semantics.py"
STAGE = HOOKS + "no-blind-stage.py"
WORKTREE = HOOKS + "worktree.py"
GHAPI = HOOKS + "gh-api-writes.py"
DIRSCOPE = HOOKS + "directory-scope.py"

CASES = [
    (WRITE, "echo 'x = 1' > src/Foo.jl", 2),
    (WRITE, "cat template.jl >> src/Foo.jl", 2),
    (WRITE, "printf 'a' > CHANGELOG.md", 2),
    (WRITE, "cd ~/Research && echo x > Packages/Example/Project.toml", 2),
    (WRITE, "echo x >src/Foo.jl", 2),
    (WRITE, "sed -i.bak 's/a/b/' src/Foo.jl", 2),
    (WRITE, "sed -Ei 's/a/b/' src/Foo.jl", 2),
    (WRITE, "sed --in-place=.bak 's/a/b/' f.jl", 2),
    (WRITE, "perl -i.bak -pe 's/a/b/' src/Foo.jl", 2),
    (WRITE, "perl -ni -e 'print' src/Foo.jl", 2),
    (WRITE, "awk -i inplace '{print}' f.jl", 2),
    (WRITE, "julia x.jl | tee report.md", 2),
    (WRITE, "cat a.md b.md > combined.md", 2),
    (WRITE, "gh pr view 3 > notes.md", 2),
    (WRITE, "cat > docs/src/index.md <<'EOF'", 2),
    (WRITE, "julia script.jl > $TMPDIR/out.log", 0),
    (WRITE, "echo '{\"a\":1}' > $TMPDIR/x.json", 0),
    (WRITE, "gh pr view 3 > /tmp/claude/pr.json", 0),
    (WRITE, "julia x.jl > results.txt", 2),
    (WRITE, "ls -la > /dev/null", 0),
    (WRITE, "julia x.jl 2>&1 | tail -5", 0),
    (WRITE, "perl -Ilib -e 'print 1'", 0),
    (WRITE, "sed -n '5,10p' src/Foo.jl", 0),
    (WRITE, "sed -e 's/a/b/' src/Foo.jl", 0),
    (WRITE, "awk -f script.awk data.txt", 0),
    (WRITE, "git commit -m 'fix > bug in notes.md'", 0),
    (WRITE, "julia -e 'println(\"a > b.md\")'", 0),
    (WRITE, "grep -n pattern src/Foo.jl | tee $TMPDIR/hits.txt", 0),
    (WRITE, "cat src/Foo.jl", 0),
    (WRITE, "echo x > $OUT", 0),
    (WRITE, 'echo "unbalanced > f.jl', 0),
    (WRITE, "cat > ~/Research/.scratch/pr3/probe.jl <<'EOF'", 0),
    (WRITE, "cat > $HOME/Research/.scratch/probe.jl <<'EOF'", 0),
    (WRITE, "cat > " + q(HOME + "/Research/.scratch/probe.jl") + " <<'EOF'", 0),
    (WRITE, "cat > ~/Research/Packages/Example/src/Foo.jl <<'EOF'", 2),
    # The loop benchmark's builders, 2026-09-29, and the shapes around them. The cwd is `CWD`,
    # which is in the fixture's `Harness` work tree.
    (WRITE, "cat > static.jl <<'EOF'\nx = 1\nEOF", 2),
    (WRITE, "cd ~/Research/Packages/Example/src && cat > static.jl <<'EOF'\nx = 1\nEOF", 2),
    (WRITE, "cd ~/Research/Packages/Example; printf '%s\\n' '' '- floor τ / |φ′(0)|; `α > 0`' >> CHANGELOG.md", 2),
    (WRITE, "python3 - <<'EOF'\np='backtracking.jl'\ns=open(p).read()\nopen(p,'w').write(s)\nEOF", 2),
    (WRITE, "python3 - <<'EOF' 2>&1\nopen('src/x.jl', mode='a')\nEOF", 2),
    (WRITE, "python3 -c \"open('src/x.jl','w').write('x')\"", 2),
    (WRITE, "python3 -c \"from pathlib import Path; Path('README.md').write_text('x')\"", 2),
    (WRITE, "echo x &> out.log", 2),
    (WRITE, "echo x >| notes.txt", 2),
    (WRITE, "echo x >& notes.txt", 2),
    (WRITE, "echo x | tee -a CHANGELOG.md", 2),
    (WRITE, "(cd .. && echo x) > f.md", 2),
    (WRITE, "echo x > f.jl; echo \"it's", 2),
    (WRITE, "cd $W && echo x > src/Foo.jl", 2),
    (WRITE, "cd ~/Research/.scratch/loop-bench/l3/grade-1 && cat > probe_budget.jl <<'EOF'\nx > 1\nEOF", 0),
    (WRITE, "julia x.jl > ~/Research/.scratch/loop-bench/l1/run.log 2>&1", 0),
    (WRITE, "git show origin/main:src/X.jl > ~/Research/.scratch/l1/GS_main.jl", 0),
    (WRITE, "julia x.jl 2>&1 | tee /tmp/claude/test.log", 0),
    (WRITE, "cat > /private/tmp/claude/p.jl <<'EOF'\necho y > z.jl\nEOF", 0),
    (WRITE, "cd $W && echo x > out.log", 0),
    (WRITE, "cd \"$TMPDIR\" && jq '.a | .b; .c' s.json > clean.json", 0),
    (WRITE, "S=/private/tmp/claude/scratchpad; cd $S && python3 -c \"open('dump.jl','w')\"", 0),
    (WRITE, "cd " + q(TOOL) + " && julia x.jl > hooks/__pycache__/a3.log 2>&1", 0),
    (WRITE, "cd " + q(TOOL) + " && cat > .scratch/q.graphql <<'EOF'\nquery\nEOF", 2),
    (WRITE, "awk -F'include' '{split($1,a,\":\"); print a[1]}' f.txt", 0),
    (WRITE, "sed -i.bak 's/a/b/; s/c/d/' \"$TMPDIR/check.jl\"", 0),
    (WRITE, "cd \"$TMPDIR\" && sed -i '' -e 's|a|b|' seam_probe.jl", 0),
    (WRITE, "SP=/private/tmp/claude/x; sed -i.bak 's|a|b|' $SP/probe.jl", 0),
    (WRITE, "perl -pi -e 's/a/b/' *.jl", 2),
    (WRITE, "cd ~/Research/Packages/Example && sed -i '' 's|a|b|; s|c|d|' Project.toml", 2),
    (WRITE, "cd ~/.claude && printf '%s\\n' '- a; b' >> CLAUDE.md", 2),
    (WRITE, "cd ~/Research && echo x > census.txt", 0),
    (WRITE, "cd ~/Research && cat >> CLAUDE.md <<'EOF'\nx\nEOF", 2),
    (WRITE, "echo x >&2", 0),
    (WRITE, "julia x.jl 2>/dev/null", 0),
    (WRITE, "echo x # > f.jl", 0),
    (WRITE, "grep -n 'a > b' src/Foo.jl", 0),
    (WRITE, "julia -e 'f = x -> x > 1; println(f(2) >= 1)'", 0),
    (WRITE, 'git commit -m "a > b.md; echo x > c.jl"', 0),
    (WRITE, "git commit -m \"$(cat <<'EOF'\nfix: echo x > f.jl\nEOF\n)\"", 0),
    (WRITE, "python3 -c \"open('" + HOME + "/Research/.scratch/l1/sw_head.txt','w').write('x')\"", 0),
    (WRITE, "python3 - <<'EOF'\nprint(open('src/x.jl').read())\nEOF", 0),
    (WRITE, "python3 -c \"import sys; open(sys.argv[1],'w')\" f.jl", 0),
    (WRITE, "python3 - <<'EOF'\nfor p in ['a.jl']:\n    open(p, 'w')\nEOF", 0),
    (WRITE, "julia -e 'write(\"f.jl\", \"x\")'", 0),

    (SANDBOX, "echo $(gh run view 1)", 2),
    (SANDBOX, "for r in a b; do gh run list -R x/$r; done", 2),
    (SANDBOX, "until gh run view 1 --json status; do sleep 30; done", 2),
    (SANDBOX, "while ! glab ci status; do sleep 10; done", 2),
    (SANDBOX, "x=$(git commit -m msg)", 2),
    (SANDBOX, 'echo "$(cd repo && git push origin main)"', 2),
    (SANDBOX, "echo `gh api repos/x`", 2),
    (SANDBOX, 'julia x.jl ; echo "exit=$?"', 2),
    (SANDBOX, "julia x.jl; echo $?", 2),
    (SANDBOX, 'git commit -m msg ; echo "exit=$?"', 2),
    (SANDBOX, "ps aux ; echo $?", 2),
    (SANDBOX, "git status; echo $?", 2),
    (SANDBOX, "cd ~/Research/Packages/Foo && git add src/Foo.jl", 2),
    (SANDBOX, "cd ~/Research/Packages/Foo && gh pr create --fill", 2),
    (SANDBOX, "gh pr list | cat", 2),
    (SANDBOX, "gh run watch 1 --exit-status | tail -20", 2),
    (SANDBOX, "gh api rate_limit > out.json", 2),
    (SANDBOX, "gh api rate_limit 2>/dev/null", 2),
    (SANDBOX, "gh api rate_limit < /dev/null", 2),
    (SANDBOX, "gh pr create --body-file - <<'EOF'\nbody\nEOF", 2),
    (SANDBOX, "git fetch origin 2>&1 | tail -5", 2),
    (SANDBOX, "git fetch origin; echo done", 2),
    (SANDBOX, "gh pr comment 3 -R o/r --body 'see `f` here'", 2),
    (SANDBOX, "gh pr review 3 -R o/r --comment --body 'a\n\n`b`\n'", 2),
    (SANDBOX, "gh pr create --title \"Fix `f`\" --body 'it doesn't'", 2),
    (SANDBOX, "julia -e 'x = \"`\"' 'it doesn't", 0),
    (SANDBOX, 'gh pr view 34 -R "$(git remote get-url origin)" --json state', 2),
    (SANDBOX, "git commit -m \"$(cat <<'EOF'\nuse `f`\nEOF\n)\"", 0),
    (SANDBOX, "gh pr comment 3 -R o/r --body-file /tmp/claude/body.md", 0),
    (SANDBOX, "git log -1 --format='`%h`'", 0),
    (SANDBOX, "echo $(git rev-parse HEAD)", 0),
    (SANDBOX, "echo $(git branch --show-current)", 0),
    (SANDBOX, "gh pr view 3", 0),
    (SANDBOX, "gh api rate_limit 2>&1", 0),
    (SANDBOX, "gh pr view 3 >&2", 0),
    (SANDBOX, "git fetch origin 2>&1", 0),
    (SANDBOX, "git fetch origin && git status --short", 0),
    (SANDBOX, "git fetch origin | git status --short", 0),
    (SANDBOX, "cd " + q(CWD) + " && git fetch origin", 0),
    (SANDBOX, 'git commit -m "a; b > c"', 0),
    (SANDBOX, "git log --oneline | head -5", 0),
    (SANDBOX, "git status > $TMPDIR/status.txt", 0),
    (SANDBOX, "ps aux", 0),
    (SANDBOX, "for f in *.jl; do julia $f; done", 0),
    (SANDBOX, "echo $(ls -1 | wc -l)", 0),
    (SANDBOX, 'echo "what? $x"', 0),
    (SANDBOX, "git init ~/Research/.scratch/r48probe", 2),
    (SANDBOX, "git init -q -b main " + q(HOME + "/Research/.scratch/gitinit-probe"), 2),
    (SANDBOX, 'git init "$HOME/Research/.scratch/x"', 2),
    (SANDBOX, "git clone -q https://github.com/example-org/Example.jl.git " + q(HOME + "/Research/Packages/Example"), 2),
    (SANDBOX, "git clone " + q(HOME + "/Research/.worktrees/X-origin.git") + " X", 2),
    (SANDBOX, "git worktree add ~/Research/.worktrees/X-y -b fix/y origin/main", 2),
    (SANDBOX, "git worktree add --detach " + q(HOME + "/Research/.worktrees/X-probe") + " origin/main", 2),
    (SANDBOX, "git worktree add ../X-y -b y origin/main", 2),
    (SANDBOX, "git worktree move wt $HOME/wt", 2),
    (SANDBOX, "git bundle create /tmp/x.bundle main", 2),
    (SANDBOX, "git init", 0),
    (SANDBOX, "git init -q r48probe", 0),
    (SANDBOX, "git clone https://github.com/example-org/X.jl.git X", 0),
    (SANDBOX, "git clone git@github.com:example-org/X.jl.git", 0),
    (SANDBOX, "git worktree list", 0),
    (SANDBOX, "git worktree remove " + q(HOME + "/Research/.worktrees/X-y"), 0),
    (SANDBOX, "git bundle verify /tmp/x.bundle", 0),
    (SANDBOX, "git log -- ../x", 0),
    (SANDBOX, "git init --bare --initial-branch=main " + q(HOME + "/Research/.worktrees/X-origin.git"), 0),
    (SANDBOX, "git clone --mirror https://github.com/example-org/X.jl.git " + q(HOME + "/Research/.scratch/X.git"), 0),

    (STAGE, "git add -nA", 2),
    (STAGE, "git add src/Foo.jl src/Bar.jl", 0),
    (STAGE, "git add src/Abc.jl", 0),
    (STAGE, 'git commit -m "record the probes\ngit add -nA is still refused\n\nCo-Authored-By: x"', 0),
    (STAGE, "git commit -m 'a; git add -A | b'", 0),
    (STAGE, "git status && git add -nA", 2),
    (STAGE, "git status\ngit add -nA", 2),
    (STAGE, "(git add -nA)", 2),
    (STAGE, "git add -nA; echo \"it's", 2),
]

# `gh-api-writes.py` answers on stdout as well as by exit status: "ask" is a JSON decision
# with exit 0, "deny" is exit 2, and "pass" is exit 0 with no output.
GHAPI_CASES = [
    ("gh api -X GET search/code -f q=foo", "pass"),
    ("gh api search/issues -f q=is:open", "pass"),
    ("gh api repos/o/r/pulls/3", "pass"),
    ("gh api 'repos/o/r/pulls?state=open'", "pass"),
    ("gh api graphql -f query='{viewer{login}}'", "pass"),
    ("gh api repos/o/r/pulls/3/reviews --input review.json", "pass"),
    ("gh api -X PUT repos/o/r/pulls/3/reviews/77 -f body=x", "pass"),
    ("gh api repos/o/r/pulls/3/reviews/77/events -f event=COMMENT", "pass"),
    ("gh api repos/o/r/pulls/3/comments -F line=4 -f body=x", "pass"),
    ("gh api repos/o/r/pulls/3/comments/991/replies -f body=x", "pass"),
    ("gh api repos/{owner}/{repo}/pulls/3/comments/$ID/replies --input r.json", "pass"),
    ("gh api --method POST /repos/o/r/issues/3/comments -f body=x", "pass"),
    ("gh api repos/o/r/commits/abc123/comments --input notes.json", "pass"),
    ("gh api graphql -f query='query { search(query:\"is:pr\", type: ISSUE, first: 5) { issueCount } }'", "pass"),
    ("gh api graphql -f query='{ search(query:\"mutation\", type: ISSUE, first: 1) { issueCount } }'", "pass"),
    ("gh api graphql -F owner=o -f query='query($owner:String!){ repository(owner:$owner, name:\"r\"){ id } }'", "pass"),
    ("gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:\"T\", body:\"x\"}) { comment { id } } }'", "pass"),
    ("gh api graphql -f query='mutation($t:ID!){ a: resolveReviewThread(input:{threadId:$t}){ thread { id } } b: resolveReviewThread(input:{threadId:\"U\"}){ thread { id } } }' -f t=T", "pass"),
    ("gh api graphql -f query='mutation { mergePullRequest(input:{pullRequestId:\"P\"}) { clientMutationId } }'", "ask"),
    ("gh api graphql -f query='mutation { resolveReviewThread(input:{threadId:\"T\"}) { thread { id } } updateIssueComment(input:{id:\"C\", body:\"x\"}) { issueComment { id } } }'", "ask"),
    ("gh api graphql -f query='mutation { ...F }'", "ask"),
    ("gh api graphql -F query=@mutation.graphql", "ask"),
    ("gh api graphql --input request.json", "ask"),
    ("gh api graphql -f owner=o", "ask"),
    ("gh api repos/o/r/issues -f title=x", "ask"),
    ("gh api repos/o/r/issues --raw-field title=x", "ask"),
    ("gh api repos/o/r/issues --field=title=x", "ask"),
    ("gh api --method=PUT repos/o/r/branches/main/protection --input p.json", "ask"),
    ("gh api -XPATCH repos/o/r -F has_wiki=false", "ask"),
    ("gh api repos/o/r/contents/README.md -X PUT -f message=x", "ask"),
    ("gh api -X PATCH repos/o/r/issues/comments/5 -f body=x", "ask"),
    ("gh api repos/o/r/pulls/3/reviews -X DELETE", "deny"),
    ("cd /x && gh api repos/o/r/labels -f name=x", "ask"),
    ("gh api repos/o/r/git/refs/heads/x -X DELETE", "deny"),
    ("gh api -XDELETE repos/o/r/issues/comments/5", "deny"),
    ("gh api --method=delete repos/o/r/git/refs/heads/x", "deny"),
    ("gh api -X DELETE repos/o/r/branches/main/protection", "deny"),
    ("glab api -X DELETE projects/1/repository/branches/topic", "deny"),
    ("glab api projects/grp%2Fproj/repository/branches/fix%2Fx -X DELETE", "deny"),
    ("glab api -X DELETE projects/1", "deny"),
    ("glab api -XDELETE projects/1/protected_branches/main", "deny"),
    ("glab api --method delete projects/1/issues/4", "deny"),
    ("glab api projects/1/repository/branches", "pass"),
    ("glab api projects/1/issues -f title=x", "pass"),
    ("git commit -m 'gh api repos/o/r/issues -f title=x'", "pass"),
    ("echo gh api", "pass"),
]

# `worktree.py` is not a `PreToolUse` hook: it fails closed, so every case here expects 1.
# Creation needs an unsandboxed git and is probed by `EnterWorktree`, not here.
WORKTREE_CASES = [
    "not json at all",
    "[1]",
    '{"hook_event_name":"Other"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"/","name":"x"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"/nonexistent","name":"x"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"' + CWD + '","name":"a/../b"}',
    '{"hook_event_name":"WorktreeCreate","cwd":"' + CWD + '","name":""}',
    '{"hook_event_name":"WorktreeRemove","worktree_path":"' + CWD + '"}',
    '{"hook_event_name":"WorktreeRemove","worktree_path":"/nonexistent/.worktrees/x"}',
]

# `directory-scope.py` fails closed to "ask", so a payload it cannot read expects "ask".
# `LINK` is a symlink inside the tree that points out of it, made by `fixture`.
LINK = R + "/probe-link-out"
DIRSCOPE_CASES = [
    ('{"tool_input":{"path":"~/Research"}}', "pass"),
    ('{"tool_input":{"path":"~/Research/"}}', "pass"),
    ('{"tool_input":{"path":"~/Research/Packages/Other"}}', "pass"),
    ('{"tool_input":{"path":"~/Research/.worktrees/Foo-bar"}}', "pass"),
    ('{"tool_input":{"path":"' + PKG + '/src/"}}', "pass"),
    ('{"tool_input":{"path":"~/Research/does/not/exist"}}', "pass"),
    ('{"tool_input":{"path":"~/ResearchX"}}', "ask"),
    ('{"tool_input":{"path":"~/Research/../.ssh"}}', "ask"),
    ('{"tool_input":{"path":"~/Research/Packages/../../Downloads"}}', "ask"),
    ('{"tool_input":{"path":"' + LINK + '"}}', "ask"),
    ('{"tool_input":{"path":"' + LINK + '/etc"}}', "ask"),
    ('{"tool_input":{"path":"~"}}', "ask"),
    ('{"tool_input":{"path":"/"}}', "ask"),
    ('{"tool_input":{"path":"~/.claude"}}', "ask"),
    ('{"tool_input":{"path":"Research/Packages"}}', "ask"),
    ('{"tool_input":{"path":""}}', "ask"),
    ('{"tool_input":{"path":123}}', "ask"),
    ('{"tool_input":{}}', "ask"),
    ('{"other":1}', "ask"),
    ("not json at all", "ask"),
    ("", "ask"),
    ("[1]", "ask"),
    ('{"tool_name":"EnterWorktree","tool_input":{"name":"ci/metal"}}', "pass"),
    ('{"tool_name":"EnterWorktree","tool_input":{"path":"~/Research/.worktrees/Foo-bar"}}', "pass"),
    ('{"tool_name":"EnterWorktree","tool_input":{"path":"~/Downloads"}}', "ask"),
    ('{"tool_name":"EnterWorktree","tool_input":{}}', "ask"),
    ('{"tool_name":"EnterWorktree","tool_input":{"name":1}}', "ask"),
    ('{"tool_name":"ExitWorktree","tool_input":{"action":"keep"}}', "pass"),
    ('{"tool_name":"ExitWorktree","tool_input":{"action":"keep","discard_changes":true}}', "ask"),
    ('{"tool_name":"ExitWorktree","tool_input":{"action":"remove"}}', "ask"),
    ('{"tool_name":"ExitWorktree","tool_input":{"action":"remove","discard_changes":true}}', "ask"),
    ('{"tool_name":"ExitWorktree","tool_input":{}}', "ask"),
    ('{"tool_name":"mcp__ccd_directory__change_directory","tool_input":{"path":"~/Research/Tasks"}}', "pass"),
    ('{"tool_name":"mcp__ccd_directory__request_directory","tool_input":{}}', "ask"),
]

# `rm-scope.py` takes the working directory from the payload: (cwd, command, expected).
# A "deny" is exit 2, an "ask" a JSON decision, a "pass" exit 0 with no output.
RMSCOPE = HOOKS + "rm-scope.py"
RMSCOPE_CASES = [
    # Recursive, absolute or `~`, in the two zones: the twelve denies refuse these today.
    (PKG, "rm -rf " + q(WT + "/build"), "pass"),
    (PKG, "rm -rf ~/Research/.worktrees/Foo-bar/docs/build", "pass"),
    (PKG, "rm -r $HOME/Research/.worktrees/Foo-bar/x ${HOME}/Research/.scratch/y", "pass"),
    (PKG, "rm -rf ~/Research/.scratch/pr3", "pass"),
    (PKG, "rm -Rf -- ~/Research/.scratch/probe-env/", "pass"),
    (PKG, "rm -rf ~/Research/.scratch/pr3/* ~/Research/.worktrees/Foo-bar/build/*", "pass"),
    (PKG, "rm -fr " + q(WT + "/src/../build"), "pass"),
    # Recursive, relative, in the zones.
    (WT, "rm -rf build docs/build", "pass"),
    (WT, "rm -rf *", "pass"),
    (R + "/.scratch", "rm -rf pr3", "pass"),
    (PKG, "cd " + q(WT) + " && rm -rf build", "pass"),
    (PKG, "cd ~/Research/.scratch && rm -rf pr3 && cd -", "pass"),
    # The roots of the zones, and above them.
    (PKG, "rm -rf " + q(WT), "deny"),
    (PKG, "rm -rf " + q(WT + "/"), "deny"),
    (PKG, "rm -rf ~/Research/.worktrees", "deny"),
    (PKG, "rm -rf ~/Research/.worktrees/*", "deny"),
    (PKG, "rm -rf ~/Research/.scratch", "deny"),
    (WT, "rm -rf .", "deny"),
    (WT, "rm -rf ../Foo-baz", "deny"),
    (WT + "/src", "rm -rf ../../Foo-baz", "deny"),
    (WT + "/src", "rm -rf ../../Foo-baz/build", "pass"),
    # Elsewhere under the parent of `HOME`, `/Users` on macOS, relative spellings included.
    (PKG, "rm -rf ../Other", "deny"),
    (PKG, "rm -r docs/build", "deny"),
    (R, "rm -rf Packages/Example/docs/build", "deny"),
    (PKG, "rm -rf ~/.julia/compiled", "deny"),
    (PKG, "rm -fr ~", "deny"),
    (PKG, "rm -R " + q(os.path.dirname(HOME)), "deny"),
    (PKG, "rm -rf /", "deny"),
    (PKG, "rm --recursive --force ~/Research/Tasks", "deny"),
    (PKG, "cd ~/Research && rm -rf Packages", "deny"),
    (PKG, "/bin/rm -rf ~/Research/Papers", "deny"),
    (PKG, "X=1 rm -rf ~/Research/Papers", "deny"),
    (PKG, "ls && rm -rf " + q(WT + "/x") + " ~/Research/Books", "deny"),
    # Plain `rm` outside the zones, an unresolved operand, and paths outside `/Users`: no decision.
    (PKG, "rm docs/build/index.html", "pass"),
    (PKG, "rm -f Manifest.toml", "pass"),
    (PKG, "rm -rf $W/build", "pass"),
    (PKG, "rm -rf \"$TMPDIR/probe\"", "pass"),
    (PKG, "rm -rf $(mktemp -d)", "pass"),
    (PKG, "rm -rf /tmp/claude/x", "pass"),
    (PKG, "cd $W && rm -rf build", "pass"),
    (PKG, "rm -rf build 2>/dev/null", "deny"),
    (WT, "rm -rf build 2>/dev/null", "pass"),
    # Text that only mentions `rm`.
    (PKG, "git commit -m 'rm -rf ~/Research'", "pass"),
    (PKG, "echo rm -rf ~", "pass"),
    (PKG, "grep -rn 'rm -rf' .", "pass"),
    (PKG, "python3 - <<'EOF'\nrm -rf ~/Research\nEOF", "pass"),
    (PKG, "julia -e 'rm(\"x\"; recursive=true)'", "pass"),
    # `git rm`: free in a worktree without `-f`, else "ask".
    (WT, "git rm src/old.jl", "pass"),
    (WT, "git rm -r --cached docs/build", "pass"),
    (WT + "/src", "git rm old.jl", "pass"),
    (WT, "git rm -f src/old.jl", "ask"),
    (WT, "git rm -rf docs", "ask"),
    (WT, "git rm --force src/old.jl", "ask"),
    (WT, "git rm -- -f", "pass"),
    (PKG, "git rm src/old.jl", "ask"),
    (R + "/.worktrees", "git rm x", "ask"),
    (WT, "git -C " + q(PKG) + " rm src/old.jl", "ask"),
    (WT, "git --git-dir=" + q(PKG + "/.git") + " rm x", "ask"),
    (PKG, "cd " + q(WT) + " && git rm src/old.jl", "pass"),
    # Fail closed: an `rm` it cannot read asks.
    (WT, "rm -rf 'unbalanced", "ask"),
]
RMSCOPE_PAYLOADS = [
    ("not json at all", "ask"),
    ("", "ask"),
    ('{"tool_input":{}}', "ask"),
    ('{"tool_input":{"command":123}}', "ask"),
    ('{"tool_input":{"command":"ls"}}', "pass"),
    ('{"tool_input":{"command":"rm -rf build"}}', "pass"),
    ('{"tool_input":{"command":"rm -rf ~/Research/Papers"}}', "deny"),
]

# `prompt-log.py` decides nothing: every payload exits 0 with no output.
PROMPTLOG = HOOKS + "prompt-log.py"
PROMPTLOG_CASES = [
    '{"tool_name":"Bash","tool_input":{"command":"ls"},"permission_mode":"default"}',
    '{"tool_name":"Write","tool_input":{"file_path":"/x","content":"' + "a" * 5000 + '"}}',
    "not json at all",
    "",
    "[1]",
]

# `install-drift.py`, the `SessionStart` hook, runs against an installation that `harness install
# --apply` makes in a fixture of its own, with the dummy profile and tree instructions in the
# fixture. It decides nothing and exits 0: "quiet" is no output, "warn" a `systemMessage`.
DRIFT = HOOKS + "install-drift.py"
REPO = os.path.dirname(os.path.dirname(HOOKS))
STAMP = ".harness-install.json"

# oh-my-pi's guard extension, `adapters/omp/guards.ts`, runs under `node` with a stub of its
# extension API: the driver hands its `tool_call` handler one event, and the case reads the answer,
# "block" or "pass". The extension is copied into the fixture as `guards.mjs`, so that a `node`
# with no TypeScript support loads it too; `guards.ts` therefore holds JavaScript syntax only. Its
# guard scripts are the four of this directory, linked into the fixture's `~/.claude/hooks/`, and
# its path list is the one `harness install` writes, `omp.guard_paths`, rendered with the dummy
# profile and the fixture's home. A case runs in the probe's work tree, in the fixture home `~`, or
# in `~/Research` below it, so that a relative path reaches the home. A fail-closed case gets a
# fixture home of its own, with one guard script replaced or the path list changed; the timeout
# case runs a copy of the extension whose timeout is 0.3 s, so that it costs no 10 s.
#
# A bash case also gives the verdict of `config.yml`'s `bash.patterns`, rendered with the dummy
# profile, by oh-my-pi's matching (`src/tools/bash.ts` at v18.6.1): the first rule that matches
# wins; `allow` matches only a whole command with no shell control character; `deny` and `prompt`
# match the whole command or one of its segments. This port splits segments by text, so it stands
# for oh-my-pi on the simple commands below and is no evidence for a compound one.
OMP_DRIVER = """
const [ext, event, cwd, mode] = process.argv.slice(1);
let handler = null;
const mod = await import(ext);
await mod.default({ on: (name, h) => { if (name === 'tool_call') handler = h; } });
let ev = JSON.parse(event);
// "throw": reading the event's input throws, so the handler's own error path runs.
if (mode === 'throw') ev = new Proxy(ev, { get: (t, k) => { if (k === 'input') throw new Error('probe'); return t[k]; } });
const answer = await handler(ev, { cwd });
process.stdout.write(JSON.stringify(answer ?? null));
"""
OMP_HOME = FIXTURE.name + "/omp-home"
# (tool, input, the extension's verdict, the patterns' verdict for a bash command)
OMP_CASES = [
    ("bash", {"command": "git push --force origin x"}, "pass", "deny"),
    ("bash", {"command": "sed -i s/a/b/ f"}, "block", "deny"),
    ("bash", {"command": "cat ~/.local/share/opencode/auth.json"}, "block", "allow"),
    ("bash", {"command": "git status"}, "pass", "allow"),
    ("bash", {"command": "ls -la", "cwd": "~/.ssh"}, "block", "allow"),
    ("read", {"path": "~/.local/share/opencode/auth.json"}, "block", None),
    ("read", {"path": "~/.local/share/opencode/auth.json:1-5"}, "block", None),
    ("read", {"path": "@~/.ssh/id_ed25519"}, "block", None),
    ("read", {"path": "file://" + OMP_HOME + "/.netrc"}, "block", None),
    ("read", {"path": "src/Foo.jl"}, "pass", None),
    ("grep", {"pattern": "token", "path": "~/.local/share/opencode"}, "block", None),
    ("grep", {"pattern": "token", "path": "~"}, "block", None),
    ("grep", {"pattern": "token", "path": "src,~/.ssh"}, "block", None),
    ("grep", {"pattern": "token", "path": "src"}, "pass", None),
    ("write", {"path": "notes.md", "content": "x"}, "pass", None),
    # gh-api-writes.py answers exit 0 with an "ask" decision, which the extension turns into a block.
    ("bash", {"command": "gh api -X POST repos/a/b/issues"}, "block", None),
]
# (tool, input, the session's working directory, the extension's verdict): "tree" is the probe's
# work tree, "~" the fixture home, "~/Research" a directory below it.
OMP_PATH_CASES = [
    # A relative path of a bash command, and a relative `cwd`, resolve against the working directory.
    ("bash", {"command": "cat ../.local/share/opencode/auth.json"}, "~/Research", "block"),
    ("bash", {"command": "cat ../.netrc"}, "~/Research", "block"),
    ("bash", {"command": "cat .local/share/opencode/auth.json"}, "~", "block"),
    ("bash", {"command": "cat .ssh/id_ed25519"}, "~", "block"),
    ("bash", {"command": "cat id_ed25519", "cwd": ".ssh"}, "~", "block"),
    ("bash", {"command": "ls -la", "cwd": "../.ssh"}, "~/Research", "block"),
    ("bash", {"command": "ls"}, "~/.ssh", "block"),
    # A command that recurses, with no path, reaches below its working directory, which holds ~/.ssh.
    ("bash", {"command": "grep -r token", "cwd": "~"}, "tree", "block"),
    ("bash", {"command": "find -name x"}, "~", "block"),
    ("bash", {"command": "cat .env"}, "tree", "block"),
    ("bash", {"command": "cat config/.env.local"}, "tree", "block"),
    ("bash", {"command": "cat secrets/token"}, "tree", "block"),
    ("bash", {"command": "cat deploy.pem"}, "tree", "block"),
    ("bash", {"command": "cat tls.key"}, "tree", "block"),
    ("bash", {"command": "cat <.env"}, "tree", "block"),
    ("bash", {"command": "cat --file=../.netrc"}, "~/Research", "block"),
    # A `cd` with no directory, or with `-`, moves home; a `cd` reaches below each of its arguments.
    ("bash", {"command": "cd && cat .netrc"}, "~/Research", "block"),
    ("bash", {"command": "(cd && cat .local/share/opencode/auth.json)"}, "~/Research", "block"),
    ("bash", {"command": "cd - && cat .netrc"}, "~/Research", "block"),
    ("bash", {"command": "pushd; cat .netrc"}, "~/Research", "block"),
    ("bash", {"command": "cd -P .. && cat .netrc"}, "~/Research", "block"),
    # A brace expansion: the shell expands `{~/.netrc,x}` to `~/.netrc x`.
    ("bash", {"command": "cat {~/.netrc,x}"}, "tree", "block"),
    # Shell quotes are removed before the match, and the match ignores case (APFS does).
    ("bash", {"command": "cat ~/'.netrc'"}, "tree", "block"),
    ("bash", {"command": 'cat "$HOME/.netrc"'}, "tree", "block"),
    ("bash", {"command": "cat ~/.local/share/OpenCode/auth.json"}, "tree", "block"),
    ("read", {"path": "~/.SSH/config"}, "tree", "block"),
    # oh-my-pi's own directory, its credential store included.
    ("read", {"path": "~/.omp/agent/agent.db"}, "tree", "block"),
    ("bash", {"command": "cat ~/.omp/agent/agent.db"}, "tree", "block"),
    ("bash", {"command": "cat agent/agent.db"}, "~/.omp", "block"),
    ("grep", {"pattern": "token", "path": "~/.omp/agent"}, "tree", "block"),
    ("read", {"path": "~/.omp/agent/skillsx/a.md"}, "tree", "block"),
    ("read", {"path": "~/.omp/agent/hooks/rm-scope.py"}, "tree", "block"),
    # The copies of the skills, the rules and the instructions are readable; they are not editable.
    ("read", {"path": "~/.omp/agent/skills/build-part/edges.md"}, "tree", "pass"),
    ("read", {"path": "~/.omp/agent/rules/julia-code.md"}, "tree", "pass"),
    ("read", {"path": "~/.omp/agent/instructions/core.md"}, "tree", "pass"),
    ("read", {"path": "~/.omp/agent/RTK.md"}, "tree", "pass"),
    ("bash", {"command": "cat ~/.omp/agent/skills/build-part/SKILL.md"}, "tree", "pass"),
    ("grep", {"pattern": "x", "path": "~/.omp/agent/skills"}, "tree", "pass"),
    ("edit", {"path": "~/.omp/agent/skills/build-part/edges.md", "old_string": "a", "new_string": "b"}, "tree",
     "block"),
    ("write", {"path": "~/.omp/agent/rules/julia-code.md", "content": "x"}, "tree", "block"),
    # Commands that name no denied path still run.
    ("bash", {"command": "cat src/Foo.jl"}, "tree", "pass"),
    ("bash", {"command": "ls -la"}, "tree", "pass"),
    ("bash", {"command": "cd src && ls"}, "tree", "pass"),
    ("bash", {"command": "grep -rn token src"}, "tree", "pass"),
    ("bash", {"command": "git status"}, "~/Research", "pass"),
    ("bash", {"command": 'git commit -m "the .key rules"'}, "tree", "pass"),
    ("bash", {"command": "git commit -m cd"}, "~/Research", "pass"),
    # `edit` and `write`: the settings template's Edit and Write denies, and oh-my-pi's directory.
    ("edit", {"path": "~/.omp/agent/config.yml", "old_string": "a", "new_string": "b"}, "~/Research", "block"),
    ("write", {"path": "~/.omp/agent/config.yml", "content": "x"}, "~/Research", "block"),
    ("edit", {"path": "~/.omp/agent/extensions/guards.ts", "old_string": "a", "new_string": "b"}, "~/Research",
     "block"),
    ("write", {"path": "~/.omp/agent/extensions/guards.ts", "content": "x"}, "~/Research", "block"),
    ("edit", {"path": "~/.claude/hooks/no-shell-file-write.py", "old_string": "a", "new_string": "b"},
     "~/Research", "block"),
    ("write", {"path": "~/.claude/hooks/no-shell-file-write.py", "content": "x"}, "~/Research", "block"),
    ("write", {"path": "../.claude/hooks/no-shell-file-write.py", "content": "x"}, "~/Research", "block"),
    ("write", {"path": "~/.config/gh/config.yml", "content": "x"}, "~/Research", "block"),
    ("edit", {"path": ".git/config", "old_string": "a", "new_string": "b"}, "tree", "block"),
    ("edit", {"path": "Notes/plan.md", "old_string": "a", "new_string": "b"}, "~/Research", "pass"),
    ("write", {"path": "~/Research/Notes/plan.md", "content": "x"}, "tree", "pass"),
    # The write tool removes a hashline header, `[path]` or `[path#TAG]`, from its path.
    ("write", {"path": "[~/.omp/agent/config.yml]", "content": "x"}, "~/Research", "block"),
    ("write", {"path": "[~/.claude/hooks/no-shell-file-write.py#1A2B]", "content": "x"}, "~/Research", "block"),
    ("write", {"path": "[Notes/plan.md#1A2B]", "content": "x"}, "~/Research", "pass"),
    # The other edit modes: a patch's `rename`, and the paths of a hashline or apply_patch `input`.
    ("edit", {"path": "Notes/plan.md", "edits": [{"op": "update", "rename": "~/.config/x.md"}]}, "~/Research",
     "block"),
    ("edit", {"input": "*** Begin Patch\n[~/.omp/agent/config.yml#1A2B]\nPUT 1.=1:\n+x\n*** End Patch\n"},
     "~/Research", "block"),
    ("edit", {"input": "*** Begin Patch\n[Notes/plan.md#1A2B]\nMV ../.claude/hooks/x.py\n*** End Patch\n"},
     "~/Research", "block"),
    ("edit", {"input": "*** Begin Patch\n*** Update File: ../.claude/hooks/gh-api-writes.py\n@@\n-a\n+b\n"
                       "*** End Patch\n"}, "~/Research", "block"),
    # A hashline header in quotes, a header with no closing `]`, and an `MV` path in quotes.
    ("edit", {"input": '["~/.omp/agent/config.yml"#1A2B]\nPUT 1.=1:\n+x\n'}, "~/Research", "block"),
    ("edit", {"input": "[Notes/plan.md#1A2B]\nPUT 1.=1:\n+x\n[~/.omp/agent/config.yml#1A2B\nPUT 1.=1:\n+x\n"},
     "~/Research", "block"),
    ("edit", {"input": "[Notes/plan.md#1A2B]\nMV '../.claude/hooks/x.py'\n"}, "~/Research", "block"),
    ("edit", {"input": "*** Begin Patch\n[Notes/plan.md#1A2B]\nPUT 1.=1:\n+x\n*** End Patch\n"}, "~/Research",
     "pass"),
    ("edit", {"input": "PUT 1.=1:\n+x\n"}, "~/Research", "block"),
]
# (tool, input, the session's working directory, the extension's verdict, text the reason holds):
# the cases whose reason matters. "~/Research/P" is a main checkout of the fixture home.
ASK_USER = "Ask the user in chat"
OMP_REASON_CASES = [
    # rm-scope.py: a recursive `rm` outside the scratch zones is refused with its message, one inside
    # them runs, and a `git rm` in a main checkout is its "ask", which the extension refuses.
    ("bash", {"command": "rm -rf ~/Research/x"}, "~/Research", "block",
     "outside the zones where a recursive `rm` runs"),
    ("bash", {"command": "rm -rf ~/Research/.scratch/x"}, "~/Research", "pass", None),
    ("bash", {"command": "git rm f"}, "~/Research/P", "block", ASK_USER),
    # The template's Edit asks: refused, and the model is told to ask in chat. Every path form of
    # an edit or a write goes through the ask list too.
    ("edit", {"path": "~/Research/P/.githooks/pre-commit", "old_string": "a", "new_string": "b"}, "~/Research",
     "block", ASK_USER),
    ("edit", {"path": ".github/workflows/test.yml", "old_string": "a", "new_string": "b"}, "~/Research/P",
     "block", ASK_USER),
    ("write", {"path": "~/.claude/skills/x/SKILL.md", "content": "x"}, "~/Research", "block", ASK_USER),
    ("write", {"path": "[~/.claude/workflows/x.js#1A2B]", "content": "x"}, "~/Research", "block", ASK_USER),
    ("edit", {"input": "[Notes/plan.md#1A2B]\nMV ../.claude/skills/x/SKILL.md\n"}, "~/Research", "block",
     ASK_USER),
    ("edit", {"path": "~/Research/P/src/a.jl", "old_string": "a", "new_string": "b"}, "~/Research", "pass", None),
    ("write", {"path": "~/.claude/skills.md", "content": "x"}, "~/Research", "pass", None),
    # A path under a deny and an ask is refused with the deny text: the deny list is checked first.
    ("edit", {"path": "~/.claude/skills/build-part/SKILL.md", "old_string": "a", "new_string": "b"}, "~/Research",
     "block", "the deny rule"),
]


def omp_pattern(command, patterns):
    """The approval of the first rule of `patterns` that matches `command`, or "none"."""
    def norm(s):
        return re.sub(r"\s+", " ", s.strip())

    def matches(glob, text):
        return re.fullmatch(".*".join(re.escape(p) for p in norm(glob).split("*")), text) is not None

    whole = norm(command)
    segments = [norm(s) for s in re.split(r"&&|\|\||[;|&\n()]", command) if s.strip()]
    control = re.search(r"[;&|<>`$()\n]", command)
    for rule in patterns:
        if rule["approval"] == "allow":
            if not control and matches(rule["match"], whole):
                return "allow"
        elif matches(rule["match"], whole) or any(matches(rule["match"], s) for s in segments):
            return rule["approval"]
    return "none"


def omp_cases():
    """The cases of the oh-my-pi guard extension: (number of cases, number wrong)."""
    total = wrong = 0

    def report(ok, line):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    node = shutil.which("node")

    def home(name, scripts=None, paths=None, timeout=None):
        """A fixture home with the four guard scripts in hooks/, beside ext/, each one that
        `scripts` names replaced by its text there, or left out for None, and the extension with its
        path list in `ext/`: `paths`, for a function the text `paths(rendered list, home)`, else the
        rendered list. `timeout` replaces the extension's timeout in milliseconds."""
        scripts = scripts or {}
        h = FIXTURE.name + "/" + name
        os.makedirs(h + "/hooks")
        os.makedirs(h + "/ext")
        for script in ("no-blind-stage.py", "no-shell-file-write.py", "gh-api-writes.py", "rm-scope.py"):
            if script not in scripts:
                os.symlink(HOOKS + script, h + "/hooks/" + script)
            elif scripts[script] is not None:
                with open(h + "/hooks/" + script, "w") as f:
                    f.write(scripts[script])
        with open(REPO + "/adapters/omp/guards.ts") as f:
            source = f.read()
        if timeout is not None:
            line = "const TIMEOUT_MS = 10_000;"
            if line not in source:
                raise OSError(f"adapters/omp/guards.ts holds no line {line!r}, which the timeout case replaces")
            source = source.replace(line, f"const TIMEOUT_MS = {timeout};")
        with open(h + "/ext/guards.mjs", "w") as f:
            f.write(source)
        if paths is not False:
            rendered = omp.guard_paths({**dummy, "home": h})
            with open(h + "/ext/guard-paths.json", "w") as f:
                f.write(paths(rendered, h) if callable(paths) else paths if paths is not None else rendered)
        return h

    def verdict(h, tool, data, env=None, cwd=CWD, mode="", want=None):
        """'block', 'pass', or what went wrong, for one event of `tool` with input `data`; with
        `want`, a block whose reason lacks that text is wrong too."""
        event = json.dumps({"type": "tool_call", "toolCallId": "probe", "toolName": tool, "input": data})
        try:
            p = subprocess.run([node, "--input-type=module", "-e", OMP_DRIVER, h + "/ext/guards.mjs", event, cwd, mode],
                               capture_output=True, text=True, timeout=TIMEOUT,
                               env=env or {**CLEAN, "HOME": "/" + h})
        except subprocess.TimeoutExpired:
            return "timeout"
        if p.returncode != 0:
            return f"exit {p.returncode}: {p.stderr.strip()[-160:]!r}"
        try:
            answer = json.loads(p.stdout)
        except ValueError:
            return f"unreadable output {p.stdout[-80:]!r}"
        if answer is None:
            return "pass"
        if answer.get("block") is not True or not answer.get("reason"):
            return f"unreadable answer {answer!r}"
        if want is not None and want not in answer["reason"]:
            return f"block without {want!r}: {answer['reason'][:160]!r}"
        return "block"

    try:
        sys.path.insert(0, REPO + "/lib")
        from harness import frontends, profile

        omp = frontends.adapter("omp")
        dummy = profile.load(REPO + "/examples/profile.toml")
        config = omp.render_config(dummy, omp.load_models(REPO + "/examples/models.toml"))
        patterns = json.loads("".join(l for l in config.splitlines(keepends=True) if not l.startswith("#")))
        patterns = patterns["bash"]["patterns"]
    except Exception as e:  # the case reports it as wrong, and the probe goes on to its summary
        report(False, f"exp render got {type(e).__name__}  [omp-guard]  {e}")
        return total, wrong
    if node is None:
        report(False, "exp node got none  [omp-guard]  `node` is not on PATH, so no case of guards.ts runs")
        return total, wrong
    exit_with = "import sys\nsys.exit({})\n".format
    decide = ('import json\nprint(json.dumps({"hookSpecificOutput": {"permissionDecision": "deny", '
              '"permissionDecisionReason": "probe-deny"}}))\n')
    try:
        good = home("omp-home")
        os.makedirs(good + "/Research/P/.git")
        # A path list whose ask list also holds ~/.claude/hooks/**, which the edit list denies.
        both = home("omp-home-both", paths=lambda text, h: json.dumps(
            {**json.loads(text), "ask": [*json.loads(text).get("ask", []), h + "/.claude/hooks/**"]}))
        fail = {label: home("omp-home-" + str(i), **kw) for i, (label, kw) in enumerate([
            ("a guard exits 1", {"scripts": {"no-blind-stage.py": exit_with(1)}}),
            ("a guard script is missing", {"scripts": {"no-blind-stage.py": None}}),
            ("a guard prints output that is not JSON", {"scripts": {"no-blind-stage.py": "print('hello')\n"}}),
            ("a guard answers deny with exit 0", {"scripts": {"no-blind-stage.py": decide}}),
            ("a guard is killed by a signal",
             {"scripts": {"no-blind-stage.py": "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"}}),
            ("a guard takes longer than the timeout",
             {"scripts": {"no-blind-stage.py": "import time\ntime.sleep(20)\n"}, "timeout": 300}),
            ("the path list is missing", {"paths": False}),
            ("the deny list is not a list", {"paths": '{"deny": "x", "edit": []}'}),
            ("the edit list is missing", {"paths": '{"deny": []}'}),
            ("rm-scope.py exits 1", {"scripts": {"rm-scope.py": exit_with(1)}}),
            ("the ask list is not a list", {"paths": '{"deny": [], "edit": [], "ask": "x"}'}),
            ("the ask list is missing", {"paths": '{"deny": [], "edit": []}'}),
        ])}
    except OSError as e:
        report(False, f"exp fixture got {type(e).__name__}  [omp-guard]  {e}")
        return total, wrong
    for tool, data, expected, pattern in OMP_CASES:
        got = verdict(good, tool, data)
        report(got == expected, f"exp {expected} got {got}  [omp-guard]  {tool} {data}")
        if pattern is not None:
            got = omp_pattern(data["command"], patterns)
            report(got == pattern, f"exp {pattern} got {got}  [omp-patts]  {data['command']}")
    where = {"tree": CWD, "~": good, "~/Research": good + "/Research", "~/.ssh": good + "/.ssh",
             "~/.omp": good + "/.omp", "~/Research/P": good + "/Research/P"}
    for tool, data, cwd, expected in OMP_PATH_CASES:
        got = verdict(good, tool, data, cwd=where[cwd])
        report(got == expected, f"exp {expected} got {got}  [omp-guard]  {tool} {data}  in {cwd}")
    for tool, data, cwd, expected, want in OMP_REASON_CASES:
        got = verdict(good, tool, data, cwd=where[cwd], want=want)
        report(got == expected, f"exp {expected} got {got}  [omp-guard]  {tool} {data}  in {cwd}, with {want!r}")
    got = verdict(both, "edit", {"path": "~/.claude/hooks/x", "old_string": "a", "new_string": "b"},
                  cwd=good + "/Research", want="the deny rule")
    report(got == "block", f"exp block got {got}  [omp-guard]  a path under a deny and an ask: edit ~/.claude/hooks/x")
    # It fails closed: a guard that cannot run, exits with another status than 0 or 2, prints
    # output that is not JSON, answers "deny", is killed or times out; a path list that is missing
    # or malformed; and an error of the handler itself each block the call. (label, home, tool,
    # input, environment, driver mode, text the reason must hold)
    status = "git status"
    for label, h, tool, data, env, mode, want in [
        ("python3 is not on PATH", good, "bash", {"command": status},
         {**CLEAN, "HOME": "/" + good, "PATH": "/nonexistent"}, "", "fails closed"),
        *[(label, fail[label], "bash", {"command": status}, None, "", want) for label, want in [
            ("a guard exits 1", "exited with status 1"),
            ("a guard script is missing", "is missing"),
            ("a guard prints output that is not JSON", "not JSON"),
            ("a guard answers deny with exit 0", "probe-deny"),
            ("a guard is killed by a signal", "SIGKILL"),
            ("a guard takes longer than the timeout", "did not answer"),
            ("the path list is missing", "cannot be used"),
            ("the deny list is not a list", "cannot be used"),
        ]],
        ("the path list is missing", fail["the path list is missing"], "read", {"path": "src/Foo.jl"}, None, "",
         "cannot be used"),
        ("the edit list is missing", fail["the edit list is missing"], "edit",
         {"path": "src/Foo.jl", "old_string": "a", "new_string": "b"}, None, "", "cannot be used"),
        ("rm-scope.py exits 1", fail["rm-scope.py exits 1"], "bash", {"command": status}, None, "",
         "rm-scope.py exited with status 1"),
        ("the ask list is not a list", fail["the ask list is not a list"], "edit",
         {"path": "src/Foo.jl", "old_string": "a", "new_string": "b"}, None, "", "cannot be used"),
        ("the ask list is not a list", fail["the ask list is not a list"], "write",
         {"path": "src/Foo.jl", "content": "x"}, None, "", "cannot be used"),
        ("the ask list is missing", fail["the ask list is missing"], "edit",
         {"path": "src/Foo.jl", "old_string": "a", "new_string": "b"}, None, "", "cannot be used"),
        ("the handler throws", good, "bash", {"command": status}, None, "throw", "failed"),
    ]:
        got = verdict(h, tool, data, env, mode=mode, want=want)
        report(got == "block", f"exp block got {got}  [omp-guard]  fail-closed, {label}: {tool} {data}")
    # A missing edit list leaves the other tools to the deny list.
    got = verdict(fail["the edit list is missing"], "read", {"path": "src/Foo.jl"})
    report(got == "pass", f"exp pass got {got}  [omp-guard]  the edit list is missing: read src/Foo.jl")
    # A bad ask list leaves the other tools to the deny list.
    got = verdict(fail["the ask list is not a list"], "read", {"path": "src/Foo.jl"})
    report(got == "pass", f"exp pass got {got}  [omp-guard]  the ask list is not a list: read src/Foo.jl")
    return total, wrong


# OpenCode v2's plugins, `adapters/opencode/plugins/*.ts`, run under `node` with a stub of the
# plugin context: the driver imports a plugin, calls its `setup(ctx)`, keeps the callbacks that
# `ctx.tool.hook` and `ctx.shell.hook` register under one hook name, and calls them in order on one
# event, as OpenCode 2.0.25 does. The event of `execute.before` is the shape the binary builds,
# `{tool, sessionID, agent, messageID, id, input}`, with the shell tool named `shell`; that of the
# shell's `create.before` is `{command, cwd, timeout, shell, env}`; `ctx.location.directory` is the
# session's directory. A hook that throws refuses the call, and the driver prints the reason, the
# event after the hooks, the plugin's exports and its id. Each plugin is copied into a fixture home
# as `<name>.mjs`, so the plugins hold JavaScript syntax only. The guard scripts are the four of this
# directory, linked into the fixture's `~/.claude/hooks/`, each run through its own shebang as the
# plugin runs it, and the path list is `guard-paths.json` rendered with the dummy profile and the
# fixture's home. A fail-closed case gets a home of its own, with one guard script replaced or the
# path list left out; the timeout case lowers `TIMEOUT_MS` in its copy, and an rtk case replaces
# the `RTK` constant by a fixture `rtk`.
OC_DRIVER = """
const [plugin, kind, name, event, dir] = process.argv.slice(1);
const hooks = [];
const register = (k) => async (n, cb) => {
  if (k === kind && n === name) hooks.push(cb);
  return { dispose: async () => {} };
};
const mod = await import(plugin);
const out = { exports: Object.keys(mod).sort(), id: mod.default?.id };
try {
  await mod.default.setup({ location: { directory: dir }, tool: { hook: register('tool') },
                            shell: { hook: register('shell') } });
} catch (e) {
  out.setup = String(e?.message ?? e);
}
const ev = JSON.parse(event);
out.hooks = hooks.length;
try {
  for (const cb of hooks) await cb(ev);
  out.verdict = 'pass';
} catch (e) {
  out.verdict = 'refuse';
  out.reason = String(e?.message ?? e);
}
out.event = ev;
process.stdout.write(JSON.stringify(out));
"""
OC_SCRIPTS = ("no-blind-stage.py", "no-shell-file-write.py", "gh-api-writes.py", "rm-scope.py")
OC_PLUGINS = {"guards": "research-harness.guards", "rtk": "research-harness.rtk", "env": "research-harness.env"}
OC_GUARD = "research-harness.guards"  # each refusal of a guard that cannot answer names the plugin
OC_RTK = "const RTK = '/opt/homebrew/bin/rtk';"


def oc_event(command, tool="shell", **fields):
    """An `execute.before` event of OpenCode 2.0.25 for one call of `tool`, whose input holds
    `command`, unless it is None, and `fields`."""
    data = {"command": command, **fields} if command is not None else fields
    return {"tool": tool, "sessionID": "probe-session", "agent": "build", "messageID": "probe-message",
            "id": "probe-call", "input": data}


def oc_cases():
    """The cases of the OpenCode plugins: (number of cases, number wrong)."""
    total = wrong = 0

    def report(ok, line):
        nonlocal total, wrong
        total, wrong = total + 1, wrong + (not ok)
        print(f"{'ok ' if ok else 'BAD'} {line}")

    node = shutil.which("node")

    def home(name, scripts=None, paths=None, timeout=None, rtk=None):
        """A fixture home with the four guard scripts in hooks/, beside plugins/, each one that
        `scripts` names replaced by its text there, or left out for None, and the plugins with their
        path list in `plugins/`: `paths`, else the rendered list, or none for False. `timeout`
        replaces the guard's timeout in milliseconds; `rtk`, the text of a fixture `rtk`, or None
        for a path where none is."""
        scripts = scripts or {}
        h = FIXTURE.name + "/" + name
        for d in ("/hooks", "/plugins", "/bin", "/.ssh"):
            os.makedirs(h + d)
        for script in OC_SCRIPTS:
            if script not in scripts:
                os.symlink(HOOKS + script, h + "/hooks/" + script)
            elif scripts[script] is not None:
                with open(h + "/hooks/" + script, "w") as f:
                    f.write("#!/usr/bin/env python3\n" + scripts[script])
                os.chmod(h + "/hooks/" + script, 0o755)
        if rtk is not None:
            with open(h + "/bin/rtk", "w") as f:
                f.write(rtk)
            os.chmod(h + "/bin/rtk", 0o755)
        for plugin in OC_PLUGINS:
            with open(REPO + f"/adapters/opencode/plugins/{plugin}.ts") as f:
                source = f.read()
            for wanted, line, new in [(timeout is not None and plugin == "guards", "const TIMEOUT_MS = 10_000;",
                                       f"const TIMEOUT_MS = {timeout};"),
                                      (plugin == "rtk", OC_RTK, f"const RTK = {json.dumps(h + '/bin/rtk')};")]:
                if not wanted:
                    continue
                if line not in source:
                    raise OSError(f"adapters/opencode/plugins/{plugin}.ts holds no line {line!r}, "
                                  "which a case replaces")
                source = source.replace(line, new)
            with open(h + f"/plugins/{plugin}.mjs", "w") as f:
                f.write(source)
        if paths is not False:
            with open(h + "/plugins/guard-paths.json", "w") as f:
                f.write(paths if paths is not None else profile.render_file(
                    REPO + "/adapters/opencode/plugins/guard-paths.json", {**dummy, "home": h}))
        return h

    def drive(h, plugin, event, kind="tool", name="execute.before", cwd=CWD, process_cwd=None):
        """The driver's answer for one event, or the text of what went wrong. `cwd` is the
        session's directory, `ctx.location.directory`; `process_cwd`, the working directory of
        the `node` process, or None for this one's."""
        env = {k: v for k, v in CLEAN.items() if k != "OPENCODE_CONFIG_DIR"}
        try:
            p = subprocess.run([node, "--input-type=module", "-e", OC_DRIVER, h + f"/plugins/{plugin}.mjs", kind, name,
                                json.dumps(event), cwd], capture_output=True, text=True, timeout=TIMEOUT,
                               env={**env, "HOME": "/" + h}, cwd=process_cwd)
        except subprocess.TimeoutExpired:
            return "timeout"
        if p.returncode != 0:
            return f"exit {p.returncode}: {p.stderr.strip()[-160:]!r}"
        try:
            return json.loads(p.stdout)
        except ValueError:
            return f"unreadable output {p.stdout[-80:]!r}"

    def verdict(h, event, want=None, cwd=CWD, process_cwd=None):
        """'refuse' or 'pass' for the guard plugin on one event; with `want`, a refusal whose
        reason lacks that text is wrong, and without it, a refusal because a guard failed."""
        answer = drive(h, "guards", event, cwd=cwd, process_cwd=process_cwd)
        if isinstance(answer, str):
            return answer
        if "setup" in answer:
            return f"setup threw {answer['setup'][:120]!r}"
        if answer["verdict"] == "refuse" and want is not None and want not in answer["reason"]:
            return f"refuse without {want!r}: {answer['reason'][:160]!r}"
        if answer["verdict"] == "refuse" and want is None and OC_GUARD in answer["reason"]:
            return f"refuse as failed: {answer['reason'][:160]!r}"
        return answer["verdict"]

    try:
        sys.path.insert(0, REPO + "/lib")
        from harness import profile

        dummy = profile.load(REPO + "/examples/profile.toml")
    except Exception as e:  # the case reports it as wrong, and the probe goes on to its summary
        report(False, f"exp profile got {type(e).__name__}  [oc-plugin]  {e}")
        return total, wrong
    if node is None:
        report(False, "exp node got none  [oc-plugin]  `node` is not on PATH, so no case of the plugins runs")
        return total, wrong
    exit_with = "import sys\nsys.exit({})\n".format
    rewrite = ('#!/bin/sh\nif [ "$1 $2 $3" = "hook check git status" ]; then echo "rtk git status"; exit 0; fi\n'
               'echo "No rewrite for: $3"; exit 1\n')
    try:
        good = home("oc-home", rtk=rewrite)
        fail = {label: home("oc-home-" + str(i), **kw) for i, (label, kw) in enumerate([
            ("a guard script is missing", {"scripts": {"no-blind-stage.py": None}}),
            ("a guard exits 1", {"scripts": {"no-blind-stage.py": exit_with(1)}}),
            ("a guard prints {", {"scripts": {"no-blind-stage.py": "print('{')\n"}}),
            ("a guard takes longer than the timeout",
             {"scripts": {"no-blind-stage.py": "import time\ntime.sleep(20)\n"}, "timeout": 300}),
            ("the path list is missing", {"paths": False}),
            ("rtk exits 1", {"rtk": '#!/bin/sh\necho "rtk git status"\nexit 1\n'}),
            ("no rtk", {}),
        ])}
    except OSError as e:
        report(False, f"exp fixture got {type(e).__name__}  [oc-plugin]  {e}")
        return total, wrong

    # The v2 form: a default export {id, setup} and no other, and no module imported.
    for plugin, id in OC_PLUGINS.items():
        answer = drive(good, plugin, oc_event("true"))
        got = answer if isinstance(answer, str) else (answer["exports"], answer["id"], answer.get("setup"))
        report(got == (["default"], id, None), f"exp {(['default'], id, None)} got {got}  [oc-plugin]  {plugin}.ts")
        with open(REPO + f"/adapters/opencode/plugins/{plugin}.ts") as f:
            imports = [l.strip() for l in f if re.match(r"\s*import\b", l) or re.search(r"\b(?:import|require)\(", l)]
        report(imports == [], f"exp no import got {imports}  [oc-plugin]  {plugin}.ts")

    # The guard: (event, verdict, text the reason must hold).
    tree = FIXTURE.name + "/home/Research/Harness"
    for event, expected, want in [
        (oc_event("cat ~/.local/share/opencode/auth.json"), "refuse", "path guard"),
        (oc_event("sed -i s/a/b/ f"), "refuse", "in-place"),
        (oc_event("git add -A"), "refuse", None),
        (oc_event("gh api -X DELETE repos/o/r"), "refuse", None),
        (oc_event("rm -rf ~/Research/x"), "refuse", None),
        (oc_event("rtk cat ~/.local/share/opencode/auth.json"), "refuse", "path guard"),
        # The guard scripts do not know `rtk`, so only the form without it reaches no-blind-stage.py.
        (oc_event("rtk git add -A"), "refuse", None),
        (oc_event("git status"), "pass", None),
        (oc_event(None, tool="read", filePath="~/.local/share/opencode/auth.json"), "pass", None),
        # Only the `shell` tool is checked, whatever command another tool's input holds.
        (oc_event("git add -A", tool="bash"), "pass", None),
        # A background call is checked as any other; a `workdir` is a `cd` the command does not spell.
        (oc_event("cat ~/.local/share/opencode/auth.json", background=True), "refuse", "path guard"),
        (oc_event("ls -la", workdir=good + "/.ssh"), "refuse", "path guard"),
        (oc_event("git status", workdir=tree), "pass", None),
    ]:
        got = verdict(good, event, want)
        report(got == expected, f"exp {expected} got {got}  [oc-guards]  {event['tool']} {event['input']}")

    # An `ask` of a guard script refuses too (decision 2), and so does a write of
    # `no-shell-file-write.py`. The scripts get `input.workdir` as their working directory, else the
    # session's directory, never the `node` process's: each case runs `node` in a directory where
    # the other answer comes out. `scratch` is below $TMPDIR, so no script refuses anything there.
    scratch, wt, pkg = FIXTURE.name, "/" + good + "/Research/.worktrees/Foo-bar", "/" + good + "/Research/Packages/A"
    os.makedirs(wt[1:])
    os.makedirs(pkg[1:])
    asked = "OpenCode cannot ask for it"
    for label, event, directory, process_cwd, expected, want in [
        ("gh-api-writes.py asks", oc_event("gh api -X POST repos/o/r/issues"), CWD, None, "refuse", asked),
        ("rm-scope.py asks", oc_event("git rm f"), pkg, wt, "refuse", asked),
        ("no-shell-file-write.py refuses", oc_event("echo x > f"), PKG, scratch, "refuse", "git working tree"),
        ("workdir", oc_event("echo x > f", workdir=PKG), scratch, scratch, "refuse", "git working tree"),
        ("session directory", oc_event("rm -rf build"), wt, pkg, "pass", None),
        ("session directory", oc_event("rm -rf build"), pkg, wt, "refuse", None),
        ("workdir", oc_event("rm -rf build", workdir=wt), pkg, pkg, "pass", None),
        ("workdir", oc_event("rm -rf build", workdir=pkg), wt, wt, "refuse", None),
    ]:
        got = verdict(good, event, want, cwd=directory, process_cwd=process_cwd)
        report(got == expected, f"exp {expected} got {got}  [oc-guards]  {label}: {event['input']} in {directory}")

    # Fail closed: each refuses `git status`, with a reason that names the guard plugin.
    for label in ("a guard script is missing", "a guard exits 1", "a guard prints {",
                  "a guard takes longer than the timeout", "the path list is missing"):
        got = verdict(fail[label], oc_event("git status"), OC_GUARD)
        report(got == "refuse", f"exp refuse got {got}  [oc-guards]  fail-closed, {label}: git status")
    # With no path list, `setup` still resolves and registers its hook.
    answer = drive(fail["the path list is missing"], "guards", oc_event("git status"))
    got = answer if isinstance(answer, str) else (answer.get("setup"), answer["hooks"])
    report(got == (None, 1), f"exp {(None, 1)} got {got}  [oc-guards]  setup with no path list")

    # The rewrite: (home, command after the hook).
    for label, h, expected in [("rtk rewrites", good, "rtk git status"),
                               ("rtk exits 1", fail["rtk exits 1"], "git status"),
                               ("no rtk", fail["no rtk"], "git status")]:
        answer = drive(h, "rtk", oc_event("git status"))
        got = answer if isinstance(answer, str) else answer["event"]["input"]["command"]
        report(got == expected, f"exp {expected!r} got {got!r}  [oc-rtk   ]  {label}: git status")
    # Only the `shell` tool's command is rewritten.
    answer = drive(good, "rtk", oc_event("git status", tool="bash"))
    got = answer if isinstance(answer, str) else answer["event"]["input"]["command"]
    report(got == "git status", f"exp 'git status' got {got!r}  [oc-rtk   ]  rtk rewrites, a bash event: git status")

    # The environment of a shell command.
    event = {"command": "true", "cwd": CWD, "timeout": 0, "shell": "/bin/zsh", "env": {"A": "1"}}
    answer = drive(good, "env", event, kind="shell", name="create.before")
    got = answer if isinstance(answer, str) else answer["event"]["env"]
    expected = {"A": "1", "JULIA_PKG_USE_CLI_GIT": "true"}
    report(got == expected, f"exp {expected} got {got}  [oc-env   ]  create.before")
    return total, wrong


FAIL_OPEN = [
    "not json at all",
    "",
    '{"tool_input":{}}',
    '{"tool_input":{"command":123}}',
    '{"other":1}',
]


def call(script, payload, env=None):
    """Run a Python hook with this interpreter on the fixture; None after the timeout."""
    try:
        return subprocess.run([sys.executable, script], input=payload, capture_output=True, text=True,
                              env=env or ENV, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return None


def run(script, payload):
    proc = call(script, payload)
    return "timeout" if proc is None else proc.returncode


def decision(script, payload):
    """Return 'deny', 'ask' or 'pass' for a hook that may answer with a JSON decision."""
    proc = call(script, payload)
    if proc is None:
        return "timeout"
    if proc.returncode == 2:
        return "deny"
    if proc.returncode != 0:
        return f"exit {proc.returncode}"
    if not proc.stdout.strip():
        return "pass"
    try:
        return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError, TypeError):
        return "unreadable output"


def fixture():
    """Make the tree the cases assume below the fixture `HOME`.

    `Packages/Example`, `~/.claude` and `Harness`, the cases' working directory, are
    repositories with tracked files; git reads no user or system configuration, and the identity
    is the environment's, so a CI runner with none and a user's global configuration give one
    result.
    """
    home = FIXTURE.name + "/home"
    git_env = {**CLEAN, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_AUTHOR_NAME": "probe", "GIT_AUTHOR_EMAIL": "probe@example.org",
               "GIT_COMMITTER_NAME": "probe", "GIT_COMMITTER_EMAIL": "probe@example.org"}
    repositories = {
        home + "/Research/Packages/Example": ["Project.toml", "CHANGELOG.md", "src/Example.jl"],
        home + "/.claude": ["CLAUDE.md"],
        home + "/Research/Harness": [".gitignore", "hooks/probe.py"],
    }
    content = {".gitignore": "__pycache__/\n"}
    for directory in (home + "/Research/.scratch", home + "/Research/.worktrees"):
        os.makedirs(directory)
    open(home + "/Research/CLAUDE.md", "w").close()
    for repository, files in repositories.items():
        for name in files:
            os.makedirs(os.path.dirname(os.path.join(repository, name)), exist_ok=True)
            with open(os.path.join(repository, name), "w") as f:
                f.write(content.get(name, ""))
        for command in (["init", "-q", "-b", "main"], ["add", "--", *files], ["commit", "-q", "-m", "fixture"]):
            subprocess.run(["git", "-C", repository, *command], env=git_env, check=True, capture_output=True)
    os.symlink("/", LINK)


def drift(env, payload="{}"):
    """('quiet', '') or ('warn', message) for `install-drift.py`; any other result is its exit."""
    proc = call(DRIFT, payload, env)
    if proc is None:
        return "timeout", ""
    if proc.returncode != 0:
        return f"exit {proc.returncode}", proc.stderr[-200:]
    if not proc.stdout.strip():
        return "quiet", ""
    try:
        out = json.loads(proc.stdout)
        message = out["systemMessage"]
        context = out["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return "unreadable output", proc.stdout[-200:]
    return ("warn", message) if message == context and out["hookSpecificOutput"]["hookEventName"] == "SessionStart" \
        else ("unreadable output", proc.stdout[-200:])


def drift_cases():
    """The cases of `install-drift.py`: (number of cases, number wrong).

    `harness install --apply` installs into a fixture `HOME`, from this repository and from tree
    instructions in the fixture. Each case changes the fixture and expects the hook to be quiet,
    or to warn with a text that names what it found."""
    base = os.path.join(FIXTURE.name, "drift")
    home, tree = base + "/home", base + "/Agents"
    claude = home + "/.claude"
    os.makedirs(claude + "/skills")
    os.makedirs(base + "/opencode")
    os.makedirs(base + "/julia")
    with open(REPO + "/Project.toml", "rb") as f, open(base + "/julia/Project.toml", "wb") as g:
        g.write(f.read())
    open(base + "/julia/Manifest.toml", "w").close()
    for name in ("instructions/research-tree.md", "rules/meta-repository.md", "README.md"):
        os.makedirs(os.path.dirname(os.path.join(tree, name)), exist_ok=True)
        with open(os.path.join(tree, name), "w") as f:
            # A rule needs a `description`, or the install exits 2 on oh-my-pi's rendering of it.
            f.write(f"---\ndescription: d\n---\n{name}\n" if name.startswith("rules/") else f"{name}\n")
    with open(REPO + "/examples/profile.toml") as f:
        lines = [f'tree_agents = "{tree}"' if l.startswith("tree_agents = ") else l for l in f.read().splitlines()]
    with open(base + "/profile.toml", "w") as f:
        f.write("\n".join(lines) + "\n")
    env = {**CLEAN, "HOME": home, "OPENCODE_CONFIG_DIR": base + "/opencode", "RESEARCH_HARNESS_JULIA": base + "/julia",
           "PI_CODING_AGENT_DIR": base + "/omp"}

    def apply():
        """`harness install --apply` on the fixture; an exit other than 0 raises."""
        p = subprocess.run([sys.executable, REPO + "/bin/harness", "--profile", base + "/profile.toml", "--models",
                            REPO + "/examples/models.toml", "install", "--apply"],
                           capture_output=True, text=True, env=env, timeout=120)
        if p.returncode != 0:
            raise RuntimeError(f"harness install --apply exits {p.returncode}: {(p.stdout + p.stderr)[-200:]}")

    def edit(path, text="an edit that is not installed\n"):
        with open(path, "a") as f:
            f.write(text)

    def read_stamp():
        with open(claude + "/" + STAMP) as f:
            return json.load(f)

    def write_stamp(data):
        with open(claude + "/" + STAMP, "w") as f:
            f.write(data)

    def copy_sources():
        """The stamp with its rules/ and hooks/ sources pointed at copies of this repository's."""
        copies = {REPO + "/rules": base + "/rules", REPO + "/hooks": base + "/hooks"}
        for source, copy in copies.items():
            shutil.copytree(source, copy)
        stamp = read_stamp()
        stamp["sources"] = [[copies.get(s[0], s[0]), *s[1:]] for s in stamp["sources"]]
        write_stamp(json.dumps(stamp))

    def toggle_x(path):
        """`path` with its owner's execute bit flipped."""
        os.chmod(path, os.stat(path).st_mode ^ 0o100)

    rules = tree + "/rules"

    # (label, the change before the hook runs, the expected result, a text the warning holds)
    steps = [
        ("the installation that --apply made is current", lambda: apply(), "quiet", ""),
        ("a payload that is not JSON changes nothing", None, "quiet", ""),
        ("an edit in the tree instructions is drift", lambda: edit(tree + "/rules/meta-repository.md"),
         "warn", "behind"),
        ("after a second --apply, the installation is current", lambda: apply(), "quiet", ""),
        ("a rename in a source, with the same bytes and the same order, is drift",
         lambda: os.rename(rules + "/meta-repository.md", rules + "/meta-repository0.md"), "warn", "behind"),
        ("the name restored, the installation is current",
         lambda: os.rename(rules + "/meta-repository0.md", rules + "/meta-repository.md"), "quiet", ""),
        ("a hidden file in a source, such as .DS_Store, is no drift", lambda: edit(rules + "/.DS_Store"), "quiet", ""),
        ("a FIFO in a source is a warning that names it", lambda: os.mkfifo(rules + "/fifo"), "warn", rules + "/fifo"),
        ("a symlinked directory in a source is a warning that names it",
         lambda: (os.remove(rules + "/fifo"), os.symlink(rules, tree + "/linked")), "warn", tree + "/linked"),
        ("the stamp names copies of rules/ and hooks/, which equal them",
         lambda: (os.remove(tree + "/linked"), copy_sources()), "quiet", ""),
        ("a mode change of a hooks/ source is drift", lambda: toggle_x(base + "/hooks/install-drift.py"),
         "warn", "behind"),
        ("an edit in rules/ is drift",
         lambda: (toggle_x(base + "/hooks/install-drift.py"), edit(base + "/rules/julia-code.md")),
         "warn", "behind"),
        ("a missing stamp is drift", lambda: os.remove(claude + "/" + STAMP), "warn", claude + "/" + STAMP),
        ("a stamp that is not JSON is a warning that names it", lambda: write_stamp("{ not json"),
         "warn", claude + "/" + STAMP),
        ("a source tree that cannot be read is a warning that names it",
         lambda: (apply(), os.chmod(tree + "/rules", 0)), "warn", tree + "/rules"),
        ("a source tree that does not exist is a warning that names it",
         lambda: (os.chmod(tree + "/rules", 0o755), os.rename(tree, tree + "-moved")), "warn", tree),
    ]
    total = wrong = 0
    for label, change, expected, text in steps:
        try:
            if change is not None:
                change()
            got, message = drift(env, "not json at all" if label.startswith("a payload") else "{}")
        except Exception as e:  # a case that crashes is wrong, and the next case still runs
            got, message = f"raised {type(e).__name__}", str(e)
        ok = got == expected and text in message
        total += 1
        wrong += not ok
        print(f"{'ok ' if ok else 'BAD'} exp {expected} got {got}  [inst-drif]  {label}: {message[:160]!r}")
    return total, wrong


def main():
    try:
        fixture()
        return cases()
    finally:
        FIXTURE.cleanup()


def cases():
    wrong = 0
    total = 0
    for script, command, expected in CASES:
        got = run(script, json.dumps({"tool_input": {"command": command}, "cwd": CWD}))
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [{script.rsplit('/', 1)[-1][:9]}]  {command}")
    for command, expected in GHAPI_CASES:
        got = decision(GHAPI, json.dumps({"tool_input": {"command": command}}))
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [gh-api-wr]  {command}")
    for payload, expected in DIRSCOPE_CASES:
        got = decision(DIRSCOPE, payload)
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [dir-scope]  {payload!r}")
    for cwd, command, expected in RMSCOPE_CASES:
        got = decision(RMSCOPE, json.dumps({"tool_input": {"command": command}, "cwd": cwd}))
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [rm-scope ]  {command!r} in {cwd}")
    for payload, expected in RMSCOPE_PAYLOADS:
        got = decision(RMSCOPE, payload)
        total += 1
        wrong += got != expected
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} exp {expected} got {got}  [rm-scope ]  payload {payload!r}")
    log = os.path.join(FIXTURE.name, "probe-prompt-log.jsonl")
    for payload in PROMPTLOG_CASES:
        proc = call(PROMPTLOG, payload, {**ENV, "LOG": log})
        if proc is None:
            got = "timeout"
        else:
            got = "pass" if proc.returncode == 0 and not proc.stdout else f"exit {proc.returncode}"
        total += 1
        wrong += got != "pass"
        mark = "ok " if got == "pass" else "BAD"
        print(f"{mark} exp pass got {got}  [prompt-lo]  {payload[:60]!r}")
    try:
        with open(log, encoding="utf-8") as lines:
            logged = sum(1 for _ in lines)
    except FileNotFoundError:
        logged = 0
    total += 1
    wrong += logged != 2
    print(f"{'ok ' if logged == 2 else 'BAD'} exp 2 got {logged}  [prompt-lo]  lines logged")
    for payload in FAIL_OPEN:
        for script in (WRITE, SANDBOX, STAGE, GHAPI):
            got = run(script, payload)
            total += 1
            wrong += got != 0
            mark = "ok " if got == 0 else "BAD"
            print(f"{mark} exp 0 got {got}  [{script.rsplit('/', 1)[-1][:9]}]  fail-open: {payload!r}")
    for payload in WORKTREE_CASES:
        got = run(WORKTREE, payload)
        total += 1
        wrong += got != 1
        mark = "ok " if got == 1 else "BAD"
        print(f"{mark} exp 1 got {got}  [worktree ]  fail-closed: {payload!r}")
    n, bad = drift_cases()
    total, wrong = total + n, wrong + bad
    n, bad = omp_cases()
    total, wrong = total + n, wrong + bad
    n, bad = oc_cases()
    total, wrong = total + n, wrong + bad
    print(f"\n{total} cases, {wrong} wrong")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
