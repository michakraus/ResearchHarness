#!/usr/bin/env bash
# Two totals of transcripts.jl, computed again on a separate path: jq over the raw transcripts.
#
#   crosscheck.sh <from-iso> <to-iso>
#
# 1. All context tokens (input + cache write + cache read) of the Claude Code transcripts, every
#    API message counted once, records of a sub-agent inside a main file left out.
# 2. The cache reads of the julia-builder runs, found by their .meta.json.
#
# Compare with the sums over runs.tsv of input, cache_write_5m, cache_write_1h and cache_read:
# all source=claude rows for 1, the agent_type=julia-builder rows for 2.
set -euo pipefail
from=$1
to=$2
root=$HOME/.claude/projects

# shellcheck disable=SC2016
usage='[.[] | select(.type == "assistant" and .timestamp >= $from and .timestamp < $to
                     and .message.usage != null and .message.model != "<synthetic>"
                     and (($sub == "1") or (.isSidechain != true)))]
       | group_by(.message.id) | map(.[0].message.usage)
       | map((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0), (.cache_read_input_tokens // 0))
       | [([.[range(0; length; 2)]] | add // 0), ([.[range(1; length; 2)]] | add // 0)] | @tsv'

total=0
builder_read=0
failed=()
while IFS= read -r -d '' f; do
  sub=0
  [[ $f == */subagents/* ]] && sub=1
  if ! out=$(jq -rs --arg from "$from" --arg to "$to" --arg sub "$sub" "$usage" "$f" 2>/dev/null); then
    failed+=("$f")
    continue
  fi
  read -r all read_ <<<"$out"
  total=$((total + all))
  if [[ $sub == 1 && -f ${f%.jsonl}.meta.json ]] && grep -q '"agentType":"julia-builder"' "${f%.jsonl}.meta.json"; then
    builder_read=$((builder_read + read_))
  fi
done < <(find "$root" -name '*.jsonl' -newermt "${from:0:10}" -print0)

echo "context tokens, all Claude Code runs: $total"
echo "cache reads, julia-builder runs: $builder_read"
echo "files jq could not parse: ${#failed[@]}"
printf '  %s\n' "${failed[@]}"
