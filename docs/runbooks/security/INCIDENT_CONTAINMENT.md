# INCIDENT_CONTAINMENT

## Detection

- Active incident: leak, compromise, or runaway publish

## Containment

1. `DRY_RUN=true` or stop processes
2. Revoke/rotate tokens if leak suspected
3. Block outbound if exfiltration suspected (host firewall)

## Recovery

- Follow specific runbook (leak / tamper / compromise)

## Evidence preservation

- Snapshot logs and `OUTPUT_DIR` before cleanup
- Record `correlation_id` / time range

## Rollback

- [SAFE_ROLLBACK.md](../upgrades/SAFE_ROLLBACK.md) after containment

## Escalation

- Management per org policy

## Post-incident validation

- `python3 tools/security_readiness.py --strict`
- Postmortem in private tracker
