#!/bin/sh
# Infrastructure only: prepare /data layout and writability before Python startup.
set -eu

log() {
  printf '[entrypoint] %s\n' "$*" >&2
}

fatal() {
  log "FATAL: $*"
  exit 1
}

for dir in /data /data/sessions /data/runtime /data/logs /app/var/runtime; do
  mkdir -p "$dir" || fatal "mkdir failed: ${dir}"
done

if ! touch /data/.write_test 2>/dev/null; then
  fatal "/data is not writable"
fi
rm -f /data/.write_test

APP_USER="${NEWSROOM_APP_USER:-appuser}"
if [ "$(id -u)" = "0" ] && id "$APP_USER" >/dev/null 2>&1; then
  chown -R "${APP_USER}:${APP_USER}" /data /app/var/runtime || fatal "chown failed"
  log "filesystem ready"
  exec gosu "$APP_USER" python -m app.main
fi

log "filesystem ready"
exec python -m app.main
