# Telegram failure

## Symptoms

- `conflict_detected: true` on `/health`
- `publish.failed` / FloodWait in logs
- Bot buttons dead

## Diagnosis

```bash
make newsroom-status
grep -E 'conflict|FloodWait|publish.channel_send_failed' logs/local-run.log | tail -20
```

## Fix (conflict)

Only one host may poll:

```bash
# Stop remote
ssh VPS 'docker stop telegram-newsroom'
# Or stop Mac
bash scripts/stop_local_newsroom.sh
```

## Fix (publish timeout)

- Wait for `failed_drafts` auto-retry (heartbeat)
- Or manual: approve draft again in admin UI

## Expected

`conflict_detected: false`, publish `outcome=ok` in logs.
