#!/usr/bin/env bash
# Start the passnote server unless it is already running, for a machine without sudo (no systemd unit): run it once by
# hand and from cron, so it comes back after a reboot or a crash (README.md):
#   @reboot      $HOME/passnote/run.sh
#   */5 * * * *  $HOME/passnote/run.sh
# Expects server.py, tokens.json, cert.pem and key.pem next to this script; writes passnote.db, server.log, server.pid
# there. PASSNOTE_PORT overrides the port (default 8765). Without cert.pem the server speaks plain HTTP (only for a
# private network or a reverse proxy that adds TLS).
d="$(cd "$(dirname "$0")" && pwd)"
pid="$(cat "$d/server.pid" 2>/dev/null)"
if [ -n "$pid" ] && grep -qs server.py "/proc/$pid/cmdline"; then
  exit 0
fi
if [ -f "$d/server.log" ] && [ "$(stat -c %s "$d/server.log")" -gt 20000000 ]; then
  mv -f "$d/server.log" "$d/server.log.1"
fi
tls=()
[ -f "$d/cert.pem" ] && tls=(--cert "$d/cert.pem" --key "$d/key.pem")
cd "$d" || exit 1
nohup python3 "$d/server.py" serve --db "$d/passnote.db" --tokens "$d/tokens.json" \
  --bind "0.0.0.0:${PASSNOTE_PORT:-8765}" "${tls[@]}" >> "$d/server.log" 2>&1 < /dev/null &
echo $! > "$d/server.pid"
