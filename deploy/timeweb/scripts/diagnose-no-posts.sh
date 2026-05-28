#!/usr/bin/env bash
# Why no new drafts? Run on VPS: bash deploy/timeweb/scripts/diagnose-no-posts.sh
set -euo pipefail

CONTAINER="${NEWSROOM_CONTAINER:-telegram-newsroom}"
PORT="${HEALTH_HTTP_PORT:-8080}"

echo "=== Health ==="
curl -sf "http://127.0.0.1:${PORT}/health" | python3 -m json.tool 2>/dev/null | head -40 || echo "health unreachable"

echo ""
echo "=== Runtime / ops ==="
curl -sf "http://127.0.0.1:${PORT}/runtime/status" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
om=d.get('operational_mode')or{}
pl=d.get('pipeline')or{}
print('mode:', om.get('mode'), '| scheduler:', om.get('scheduler_allowed'))
print('pipeline:', pl)
" 2>/dev/null || echo "runtime/status unreachable"

echo ""
echo "=== DB queue (inside container) ==="
docker exec "$CONTAINER" python3 -c "
import sqlite3
c=sqlite3.connect('/data/newsroom.db')
t=c.execute('select count(*) from raw_posts').fetchone()[0]
u=c.execute('select count(*) from raw_posts where processed_at is null').fetchone()[0]
p=c.execute(\"select count(*) from drafts where status='pending'\").fetchone()[0]
pub=c.execute(\"select count(*) from drafts where status='published'\").fetchone()[0]
print('raw_posts total:', t)
print('unprocessed:', u)
print('pending drafts:', p)
print('published drafts:', pub)
if u:
    rows=c.execute('select id,channel_name,message_id,substr(text,1,60) from raw_posts where processed_at is null order by id desc limit 5').fetchall()
    print('latest unprocessed:')
    for r in rows:
        print(' ', r)
"

echo ""
echo "=== Last pipeline / collector lines ==="
docker logs "$CONTAINER" 2>&1 | tail -200 | grep -E \
  'posts_collected|no_unprocessed|cluster_below_min|collector skipped|collector running|drafts_created|ingestion_paused|telethon|summarize_skipped|pipeline\.idle' \
  | tail -25 || echo "(no matches)"

echo ""
echo "=== Env (ingest + channels) ==="
docker exec "$CONTAINER" sh -c 'grep -E "^(SOURCE_CHANNELS|MIN_RAW_POSTS|RUNTIME_OPERATIONAL|DRY_RUN|OPS_INGESTION)=" /app/.env 2>/dev/null || true'
