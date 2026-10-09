#!/usr/bin/env bash
# Build the tree-sitter-julia library that sgconfig.yml registers as ast-grep's `julia`.
# Julia is not one of ast-grep's built-in languages. Run this once per machine, and again
# after a change to the pinned commit. It writes julia.dylib beside itself, which is
# gitignored. The grammar source goes to a temporary directory, not into this vault.

set -eo pipefail

commit=e0f9dcd180fdcfcfa8d79a3531e11d99e79321d3
here=$(cd "$(dirname "$0")" && pwd)
src=$(mktemp -d "${TMPDIR:-/tmp}/tree-sitter-julia.XXXXXX")

git -C "$src" init --quiet
git -C "$src" fetch --quiet --depth 1 https://github.com/tree-sitter/tree-sitter-julia "$commit"
git -C "$src" checkout --quiet FETCH_HEAD

cc -O2 -fPIC -shared -I "$src/src" "$src/src/parser.c" "$src/src/scanner.c" -o "$here/julia.dylib"
rm -rf "$src"
printf 'built %s at %s\n' "$here/julia.dylib" "$commit"
