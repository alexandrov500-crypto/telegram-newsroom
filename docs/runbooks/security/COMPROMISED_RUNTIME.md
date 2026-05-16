# COMPROMISED_RUNTIME

## Detection

- Unauthorized publishes or admin actions
- Unexpected files under `OUTPUT_DIR` or `RUNTIME_STATE_DIR`
- Host intrusion indicators

## Containment

1. [INCIDENT_CONTAINMENT.md](INCIDENT_CONTAINMENT.md)
2. Stop all newsroom processes
3. Isolate host network if needed

## Recovery

- Rebuild host from known-good image
- Restore `backup_cli` + snapshot from **pre-incident** known-good
- Rotate all tokens

## Evidence preservation

- Disk snapshot for forensics before wipe
- `verify-runtime` output from suspect tree (do not trust OK)

## Rollback

- Full restore from clean backup only

## Escalation

- Host-level incident response team

## Post-incident validation

- `make governance-validate` on clean deploy
- Review `UNSAFE_CONFIGURATION.md` findings
