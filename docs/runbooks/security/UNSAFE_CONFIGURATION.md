# UNSAFE_CONFIGURATION

## Detection

```bash
python3 tools/security_posture_check.py --fail-on MEDIUM
```

## Containment

- Apply remediation hints from tool output
- Reduce to single worker until Redis/locks fixed

## Recovery

- Enable recommended flags per [feature_flag_governance.md](../../feature_flag_governance.md)
- Fix directory permissions on `OUTPUT_DIR`

## Evidence preservation

- Save JSON report from posture check

## Rollback

- Revert `.env` if change caused outage

## Escalation

- Architecture review if multi-worker required without Redis

## Post-incident validation

- Posture check `status: OK`
