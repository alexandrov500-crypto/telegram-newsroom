# Production rollback procedures

## Trigger criteria

- Certification gates fail after deploy
- Epistemic stability < SLO for > 1h
- Unbounded queue backlog
- Cost anomaly > 2× daily budget
- Operator declares incident severity ≥ SEV-2

## Fast rollback (application)

1. Stop new deploy: `systemctl stop newsroom` or scale deployment to 0
2. Restore previous image/tag from last known-good
3. Restore env from backup (no schema downgrade without migration review)
4. Start with `OPS_BURNIN_ENABLED=true` for 24h observation
5. Run `python -m bot.operations.cli smoke`

## Data rollback

- PostgreSQL: restore from last snapshot before deploy (point-in-time if available)
- SQLite dev: restore `var/backups/` copy
- Redis Streams: do not truncate without incident bundle export

## Verification

```bash
python -m bot.operations.cli nightly-cert
curl -s http://127.0.0.1:8080/ready
```

## Communication

- Export incident: `python -m bot.operations.cli incident-export rollback-<date>`
- Attach bundle to postmortem (`docs/operations/postmortem_template.md`)
