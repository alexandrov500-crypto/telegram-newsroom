# Deploy runbook

## Preconditions

- Mac: `RUNTIME_NODE_ROLE=control`, polling off
- VPS: single worker, container stopped on Mac during Mac test

## Deploy

```bash
make deploy-safe
# or on VPS:
cd /opt/newsroom/deploy/timeweb && bash scripts/production-deploy.sh
```

## Verify

```bash
curl -sf http://127.0.0.1:8080/health
curl -sf http://127.0.0.1:8080/ops/panel.json
make reliability-test   # from dev machine against repo
```

## Rollback

1. `docker compose down` / stop process  
2. Restore `.env` + DB backup  
3. `docker compose up -d` previous image

See `docs/runbooks/upgrades/SAFE_ROLLBACK.md`.
