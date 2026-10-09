#!/bin/sh
# The Claude Code status line: model, effort, tokens in and out, and the five-hour and weekly
# rate limits, coloured by use. POSIX sh, jq, and `date +%s` only, so it runs on macOS and Linux.

IFS='	' read -r model effort tin tout five reset week <<EOF
$(jq -r '[.model.display_name // "?", .effort.level // "-",
          .context_window.total_input_tokens // 0, .context_window.total_output_tokens // 0,
          .rate_limits.five_hour.used_percentage // "", .rate_limits.five_hour.resets_at // "",
          .rate_limits.seven_day.used_percentage // ""] | map(tostring) | join("\t")')
EOF

esc=$(printf '\033')
reset_c="${esc}[0m" dim="${esc}[2m" bold="${esc}[1m"
cyan="${esc}[36m" magenta="${esc}[35m" green="${esc}[32m" yellow="${esc}[33m" red="${esc}[31m"
sep=" ${dim}│${reset_c} "

# 1234 -> 1.2k, 1234567 -> 1.2M
human() {
    awk -v n="$1" 'BEGIN { if (n >= 1e6) printf "%.1fM", n / 1e6
                           else if (n >= 1e3) printf "%.1fk", n / 1e3
                           else printf "%d", n }'
}

# A percentage, green below 50, yellow below 80, red above; "-" when unknown.
usage() {
    [ -z "$1" ] && { printf '%s-%s' "$dim" "$reset_c"; return; }
    p=$(printf '%.0f' "$1")
    if [ "$p" -ge 80 ]; then c=$red; elif [ "$p" -ge 50 ]; then c=$yellow; else c=$green; fi
    printf '%s%s%%%s' "$c" "$p" "$reset_c"
}

# The time until an epoch second, as 2h13m or 7m.
until_epoch() {
    [ -z "$1" ] && return
    left=$(( ${1%.*} - $(date +%s) ))
    [ "$left" -lt 0 ] && left=0
    h=$(( left / 3600 )) m=$(( left % 3600 / 60 ))
    if [ "$h" -gt 0 ]; then printf ' %s↻ %dh%02dm%s' "$dim" "$h" "$m" "$reset_c"
    else printf ' %s↻ %dm%s' "$dim" "$m" "$reset_c"; fi
}

case $effort in
    high|xhigh|max) ec=$magenta ;;
    *) ec=$dim ;;
esac

printf '%s%s%s%s' "$bold$cyan" "$model" "$reset_c" "$sep"
printf '%s%s%s%s' "$ec" "$effort" "$reset_c" "$sep"
printf '%s↓%s ↑%s%s%s' "$dim" "$(human "$tin")" "$(human "$tout")" "$reset_c" "$sep"
printf '5h %s%s%s' "$(usage "$five")" "$(until_epoch "$reset")" "$sep"
printf 'week %s' "$(usage "$week")"
