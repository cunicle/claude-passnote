#!/usr/bin/env bash
# Entry point of the passnote hooks (hooks/hooks.json): usage hook.sh {prompt|post|stop}, hook input on stdin.
# Sessions that did not opt in (PASSNOTE_ENABLE=1, or this session's id in PASSNOTE_HOME/sessions) exit here, without
# starting Python or touching the network. The session id comes from the hook input (session_id), else from
# CLAUDE_CODE_SESSION_ID. Runs under Git Bash on Windows.
[ "$PASSNOTE_ENABLE" = 0 ] && exit 0
sessions="${PASSNOTE_HOME:-$HOME/.config/claude-passnote}/sessions"
[ "$PASSNOTE_ENABLE" = 1 ] || [ -s "$sessions" ] || exit 0
input="$(cat)"
if [ "$PASSNOTE_ENABLE" != 1 ]; then
  re='"session_id"[[:space:]]*:[[:space:]]*"([^"]*)"'
  sid="${CLAUDE_CODE_SESSION_ID:-no-session}"
  [[ $input =~ $re ]] && sid="${BASH_REMATCH[1]}"
  grep -qsxF -- "$sid" "$sessions" || exit 0
fi
dir="$(dirname "$0")"
# hook.py exits 0 whenever Python 3 runs it; a missing command, a Microsoft Store alias or Python 2 fails: try the next
for py in ${PASSNOTE_PYTHON:+"$PASSNOTE_PYTHON"} python python3 py; do
  printf '%s' "$input" | "$py" "$dir/hook.py" "$1" 2>/dev/null && break
done
exit 0
